"""Исследование ниш: какую раскраску делать сегодня.

1. Кандидаты: подсказки поиска Amazon (что реально набирают покупатели) по базовым фразам,
   сезонным событиям и идеям LLM; раскрутка по алфавиту («…for kids a», «…for kids b»).
2. Конкуренция: выдача Amazon (сколько книг, сколько отзывов у топ-10) + рейтинг продаж (BSR)
   лидеров — со страниц товаров бесплатно или через Keepa API (если задан KEEPA_API_KEY).
3. Оценка: спрос (продажи лидеров) × «окна» (книги в топе с малым числом отзывов — туда реально
   зайти) × сезонность ÷ конкуренция. Повторы недавних ниш отсекаются по истории.

Всё сетевое — в AmazonClient/KeepaClient; разбор HTML и оценка — чистые функции (тестируются офлайн).
Amazon может показать капчу: тогда кандидаты оцениваются по подсказкам без данных о конкуренции,
и это явно помечено в отчёте (confidence: low).
"""
import datetime as dt
import hashlib
import json
import logging
import math
import os
import random
import re
import statistics
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import quote_plus

import httpx

from . import book, profiles, safety
from .base import AllProvidersFailed

log = logging.getLogger("research")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/128.0.0.0 Safari/537.36")


class Blocked(RuntimeError):
    """Amazon показал капчу / отказал — данные с этой страницы недоступны."""


# --- разбор HTML (чистые функции) -----------------------------------------------
_RESULTS = re.compile(r"(?:of\s+(?:over\s+)?|^\s*)([\d,]+)\s+results\s+for", re.I | re.M)
_ITEM_START = re.compile(r'<div[^>]*data-component-type="s-search-result"[^>]*>')
_ASIN = re.compile(r'data-asin="([A-Z0-9]{10})"')
_TITLE = re.compile(r"<h2[^>]*>.*?<span[^>]*>(.*?)</span>", re.S)
_REVIEWS = [re.compile(r'aria-label="([\d,]+)\s+ratings?"'),
            re.compile(r'<span[^>]*class="[^"]*s-underline-text[^"]*"[^>]*>\(?([\d,.]+K?)\)?</span>')]
_BSR = re.compile(r"#\s?([\d,]+)\s+in\s+Books\b")
CAPTCHA_MARKERS = ("captcha", "robot check", "enter the characters you see", "api-services-support@amazon")


def _num(s: str) -> int:
    s = s.replace(",", "").strip()
    return int(float(s[:-1]) * 1000) if s.upper().endswith("K") else int(float(s))


def check_blocked(html: str) -> None:
    low = html[:20000].lower()
    if any(m in low for m in CAPTCHA_MARKERS) and "s-search-result" not in low and "productTitle" not in html:
        raise Blocked("Amazon показал капчу")


def parse_search(html: str) -> dict:
    """Выдача Amazon → {"total": int|None, "items": [{"asin", "title", "reviews", "sponsored"}]}."""
    check_blocked(html)
    m = _RESULTS.search(re.sub(r"<[^>]+>", " ", html[:200000]))
    total = _num(m.group(1)) if m else None
    items = []
    starts = [m.start() for m in _ITEM_START.finditer(html)] + [len(html)]
    for a, b in zip(starts, starts[1:]):
        chunk = html[a:min(b, a + 30000)]  # тег карточки целиком: data-asin может стоять до/после
        asin = _ASIN.search(chunk)
        if not asin:
            continue
        t = _TITLE.search(chunk)
        title = re.sub(r"<[^>]+>|\s+", " ", t.group(1)).strip() if t else ""
        reviews = 0
        for rx in _REVIEWS:
            if r := rx.search(chunk):
                reviews = _num(r.group(1))
                break
        items.append({"asin": asin.group(1), "title": title, "reviews": reviews,
                      "sponsored": "Sponsored" in chunk[:6000]})
    return {"total": total, "items": items}


def parse_bsr(html: str) -> int | None:
    check_blocked(html)
    m = _BSR.search(re.sub(r"<[^>]+>", " ", html))
    return _num(m.group(1)) if m else None


def parse_suggestions(data: dict) -> list[str]:
    return [str(s.get("value", "")).strip().lower() for s in data.get("suggestions", []) if s.get("value")]


# --- сеть ------------------------------------------------------------------------
class AmazonClient:
    """Бесплатные данные Amazon: подсказки, выдача, BSR. Паузы между запросами, кэш на сутки,
    капча → Blocked (дальше исследование идёт без этих данных)."""

    def __init__(self, cache_dir: Path, *, domain: str = "www.amazon.com", mid: str = "ATVPDKIKX0DER",
                 delay: tuple[float, float] = (2.0, 5.0), suggest_delay: tuple[float, float] = (0.3, 0.8),
                 client: httpx.Client | None = None, cache_hours: float = 20):
        self.domain, self.mid, self.delay, self.suggest_delay = domain, mid, delay, suggest_delay
        self.cache_dir, self.cache_hours = Path(cache_dir), cache_hours
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.client = client or httpx.Client(timeout=30, follow_redirects=True, headers={
            "User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"})
        self.blocked = False
        self._last = 0.0

    def _get(self, url: str, *, delay: tuple[float, float] | None = None) -> str:
        key = self.cache_dir / (hashlib.sha1(url.encode()).hexdigest() + ".txt")
        if key.exists() and time.time() - key.stat().st_mtime < self.cache_hours * 3600:
            return key.read_text(encoding="utf-8")
        lo, hi = delay or self.delay
        wait = self._last + random.uniform(lo, hi) - time.time()
        if wait > 0:
            time.sleep(wait)
        r = self.client.get(url)
        self._last = time.time()
        if r.status_code in (503, 429, 403):
            self.blocked = True
            raise Blocked(f"HTTP {r.status_code}")
        r.raise_for_status()
        key.write_text(r.text, encoding="utf-8")
        return r.text

    def suggest(self, prefix: str) -> list[str]:
        url = (f"https://completion.amazon.com/api/2017/suggestions?limit=11&prefix={quote_plus(prefix)}"
               f"&suggestion-type=KEYWORD&page-type=Search&alias=stripbooks&site-variant=desktop&version=3"
               f"&lop=en_US&mid={self.mid}&plain-mid=1&client-info=amazon-search-ui")
        try:
            return parse_suggestions(json.loads(self._get(url, delay=self.suggest_delay)))
        except (ValueError, httpx.HTTPError) as e:
            log.debug("подсказки %r: %s", prefix, e)
            return []

    def search(self, phrase: str) -> dict:
        if self.blocked:
            raise Blocked("ранее получили капчу")
        html = self._get(f"https://{self.domain}/s?k={quote_plus(phrase)}&i=stripbooks")
        try:
            return parse_search(html)
        except Blocked:
            self.blocked = True
            raise

    def bsr(self, asin: str) -> int | None:
        if self.blocked:
            raise Blocked("ранее получили капчу")
        try:
            return parse_bsr(self._get(f"https://{self.domain}/dp/{asin}"))
        except Blocked:
            self.blocked = True
            raise


class KeepaClient:
    """BSR и отзывы через Keepa API (платно, надёжно). Включается ключом KEEPA_API_KEY в .env.
    Индексы Keepa: stats.current[3] = sales rank, [17] = число отзывов (-1 = нет данных)."""

    def __init__(self, key: str, *, domain_id: int = 1, client: httpx.Client | None = None):
        self.key, self.domain_id = key, domain_id
        self.client = client or httpx.Client(timeout=60)

    def search(self, phrase: str) -> list[dict]:
        r = self.client.get("https://api.keepa.com/search", params={
            "key": self.key, "domain": self.domain_id, "type": "product", "term": phrase, "stats": 30,
            "history": 0, "page": 0})
        r.raise_for_status()
        out = []
        for p in r.json().get("products") or []:
            cur = (p.get("stats") or {}).get("current") or []
            rank = cur[3] if len(cur) > 3 and cur[3] and cur[3] > 0 else None
            rev = cur[17] if len(cur) > 17 and cur[17] and cur[17] > 0 else 0
            out.append({"asin": p.get("asin"), "title": p.get("title") or "", "reviews": rev, "bsr": rank})
        return out


# --- сезонность ---------------------------------------------------------------------
def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(weekday - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def _easter(year: int) -> dt.date:  # алгоритм Гаусса/Мееуса для западной Пасхи
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = (h + l_ - 7 * m + 114) % 31 + 1
    return dt.date(year, month, day)


def events(year: int) -> list[tuple[str, dt.date, list[str]]]:
    return [
        ("Valentine's Day", dt.date(year, 2, 14), ["valentines", "valentine's day", "love"]),
        ("St. Patrick's Day", dt.date(year, 3, 17), ["st patricks day", "leprechaun"]),
        ("Easter", _easter(year), ["easter", "easter bunny", "easter basket stuffers"]),
        ("Mother's Day", _nth_weekday(year, 5, 6, 2), ["mothers day"]),
        ("Father's Day", _nth_weekday(year, 6, 6, 3), ["fathers day"]),
        ("Summer", dt.date(year, 6, 21), ["summer", "beach", "ocean"]),
        ("Back to School", dt.date(year, 8, 20), ["back to school", "first day of school"]),
        ("Halloween", dt.date(year, 10, 31), ["halloween", "spooky", "pumpkin"]),
        ("Thanksgiving", _nth_weekday(year, 11, 3, 4), ["thanksgiving", "fall", "autumn"]),
        ("Christmas", dt.date(year, 12, 25), ["christmas", "winter", "santa", "stocking stuffers"]),
    ]


def upcoming(today: dt.date, lead: tuple[int, int] = (30, 75)) -> list[tuple[str, list[str]]]:
    """События, до которых от lead[0] до lead[1] дней: книга успеет пройти проверку и проиндексироваться."""
    out = []
    for y in (today.year, today.year + 1):
        for name, day, words in events(y):
            if lead[0] <= (day - today).days <= lead[1]:
                out.append((name, words))
    return out


# --- оценка ---------------------------------------------------------------------------
def est_daily_sales(bsr: int | None) -> float:
    """Грубая оценка продаж бумажной книги в день по BSR на amazon.com (#1 000 ≈ 30/день, #100 000 ≈ 0.3)."""
    return 0.0 if not bsr else min(500.0, 32000.0 / bsr)


@dataclass
class Niche:
    phrase: str
    suggest_score: float = 0.0      # 0..1: как часто и как высоко фраза в подсказках
    sources: list[str] = field(default_factory=list)
    season: str = ""
    total: int | None = None        # книг в выдаче
    top_reviews: list[int] = field(default_factory=list)
    top_bsr: list[int] = field(default_factory=list)
    demand: float = 0.0             # оценка продаж лидеров, шт/день (медиана)
    competition: float = 0.0
    weak_spots: int = 0             # книги в топ-10 с < 30 отзывов (а при известном BSR — ещё и продаются)
    score: float = 0.0
    confidence: str = "low"
    notes: list[str] = field(default_factory=list)


WEAK_REVIEWS = 50       # книга в топе с меньшим числом отзывов — «слабая», её можно обогнать
WEAK_MAX_BSR = 400_000  # …если она при этом продаётся


def score(n: Niche) -> Niche:
    """Итоговая оценка: сколько продаж реально достижимо новой книге, с поправкой на насыщенность.

    Главный сигнал «окна» — в топе есть слабые книги (мало отзывов), которые продаются: значит,
    покупатель берёт и новичков. Если все лидеры с тысячами отзывов — ниша занята, даже при большом спросе.
    Без BSR (капча) — оценка по подсказкам и отзывам (confidence=medium), без выдачи — только подсказки (low).
    """
    season_k = 1.5 if n.season else 1.0
    pull = 0.5 + n.suggest_score
    if n.total is None and not n.top_reviews:
        n.score = round(n.suggest_score * season_k * 0.5, 4)
        n.confidence = "low"
        return n
    n.competition = round(math.log10((n.total or 1000) + 10), 3)
    if n.top_bsr:
        n.confidence = "high"
        sales = [est_daily_sales(b) for b in n.top_bsr]
        n.demand = round(statistics.median(sales), 3)
        weak = [est_daily_sales(bsr) for rev, bsr in zip(n.top_reviews, n.top_bsr)
                if rev < WEAK_REVIEWS and bsr < WEAK_MAX_BSR]
        n.weak_spots = len(weak)
        if weak:
            achievable = statistics.median(weak) * (1 + len(weak) / 4)
        else:
            achievable = min(sales) * 0.02  # все лидеры «забетонированы» отзывами
            n.notes.append("в топе нет слабых книг — зайти трудно")
        if n.demand < 0.2:
            n.notes.append("лидеры почти не продаются — спроса нет")
    else:
        n.confidence = "medium"
        n.weak_spots = sum(1 for rev in n.top_reviews[:10] if rev < WEAK_REVIEWS)
        med_rev = statistics.median(n.top_reviews) if n.top_reviews else 0
        achievable = pull * (1 + n.weak_spots / 4) / (1 + med_rev / 200)
    n.score = round(achievable * season_k * pull / max(n.competition, 1.0), 4)
    return n


def normalize(phrase: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' -]", " ", phrase.lower())).strip()


# слова аудитории/оформления не делают нишу другой: «cute axolotl» и «axolotl for kids» — одна тема
_STOP = {"coloring", "colouring", "book", "books", "for", "and", "the", "of", "a", "with", "pages", "in", "to",
         "kids", "adults", "adult", "toddlers", "girls", "boys", "teens", "women", "men", "ages", "age",
         "cute", "easy", "simple", "fun", "big", "large", "print", "relaxing", "relaxation", "stress", "relief",
         "activity", "gift", "gifts", "year", "old", "olds", "children", "childrens", "children's", "toddler"}


def topic_words(phrase: str) -> set[str]:
    return {w for w in phrase.split() if w not in _STOP and not re.fullmatch(r"[\d-]+", w)}


def is_candidate(phrase: str) -> bool:
    """Фраза про раскраски, с конкретной темой (не просто «coloring book for kids») и без брендов."""
    p = phrase.lower()
    return (("coloring" in p or "colouring" in p) and bool(topic_words(p))
            and not safety.blocked_terms(p))


def similar(a: str, b: str) -> float:
    wa, wb = topic_words(a), topic_words(b)
    return len(wa & wb) / max(1, len(wa | wb))


# --- история ---------------------------------------------------------------------------
class History:
    """Что уже опубликовано/сделано: не повторяем ниши. data/history.json"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.items: list[dict] = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else []

    def add(self, **rec) -> None:
        self.items.append({"date": dt.date.today().isoformat(), **rec})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.items, ensure_ascii=False, indent=2), encoding="utf-8")

    def recent_phrases(self, days: int, today: dt.date | None = None) -> list[str]:
        today = today or dt.date.today()
        return [i["phrase"] for i in self.items
                if (today - dt.date.fromisoformat(i["date"])).days <= days and i.get("phrase")]


# --- исследование целиком ----------------------------------------------------------------
IDEAS_PROMPT = """You research Amazon KDP coloring book niches. Today is {today}.
Suggest {count} specific, currently popular or evergreen coloring book topics as Amazon search phrases
buyers type (e.g. "axolotl coloring book for kids", "cozy cottage coloring book for adults").
Mix kids and adults. Prefer specific sub-niches over broad ones. {season}
No brands, franchises, characters, celebrities, sports teams, violence, religion or politics.
Format: {{"phrases": ["...", "..."]}}"""

PLAN_PROMPT = """Plan a coloring book for the Amazon search phrase "{phrase}".
Return JSON: {{"theme": "short English theme for page ideas, no brands",
"audience": "kids" or "adults", "age": "e.g. 4-8 for kids, empty for adults",
"trim": one of {trims}, "pages": number of illustrations between {min_pages} and {max_pages},
"angle": "one sentence: what makes this book stand out"}}"""


@dataclass
class ResearchConfig:
    seeds: list[str] = field(default_factory=lambda: [
        "coloring book for kids", "coloring book for adults", "coloring book for toddlers",
        "coloring book for girls", "coloring book for boys", "animal coloring book",
        "mandala coloring book", "cute coloring book"])
    alphabet: str = "abcdefghiklmnoprstuvwz"
    llm_ideas: int = 25
    evaluate_top: int = 15          # сколько лучших по подсказкам проверять выдачей Amazon
    bsr_top: int = 5                # у скольких лидеров смотреть BSR
    repeat_days: int = 60           # не повторять ниши за этот срок
    similar_max: float = 0.6        # похожесть на недавние ниши, выше — пропуск
    min_pages: int = 30
    max_pages: int = 50
    season_lead: tuple = (30, 75)

    @classmethod
    def from_config(cls, cfg: dict | None) -> "ResearchConfig":
        names = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in (cfg or {}).items() if k in names})


def collect_candidates(amazon: AmazonClient, text_router, rc: ResearchConfig,
                       today: dt.date) -> dict[str, Niche]:
    season = upcoming(today, tuple(rc.season_lead))
    seeds = list(rc.seeds)
    for name, words in season:
        seeds += [f"{w} coloring book" for w in words[:2]]
    ideas: list[str] = []
    if rc.llm_ideas and text_router is not None:
        hint = ("Upcoming events worth targeting: " + ", ".join(n for n, _ in season) + ".") if season else ""
        try:
            data = text_router.chat_json(IDEAS_PROMPT.format(today=today.isoformat(), count=rc.llm_ideas,
                                                             season=hint), temperature=0.9)["data"]
            ideas = [normalize(p) for p in (data.get("phrases", []) if isinstance(data, dict) else data)]
        except AllProvidersFailed as e:
            log.warning("идеи LLM недоступны: %s", str(e).splitlines()[0])

    found: dict[str, Niche] = {}

    def add(phrase: str, weight: float, source: str) -> None:
        phrase = normalize(phrase)
        if not is_candidate(phrase):
            return
        n = found.setdefault(phrase, Niche(phrase))
        n.suggest_score += weight
        if source not in n.sources:
            n.sources.append(source)

    for seed in seeds:
        for prefix in [seed] + [f"{seed} {ch}" for ch in rc.alphabet]:
            for pos, s in enumerate(amazon.suggest(prefix)):
                add(s, 1.0 / (1 + pos), f"suggest:{seed}")
    for idea in ideas:
        sug = amazon.suggest(idea)
        if idea in sug:  # идея LLM подтверждена: её реально ищут
            add(idea, 1.5, "llm+suggest")
        for pos, s in enumerate(sug[:5]):
            add(s, 0.5 / (1 + pos), "llm-expand")

    top = max((n.suggest_score for n in found.values()), default=1) or 1
    for n in found.values():
        n.suggest_score = round(n.suggest_score / top, 4)
        for name, words in season:
            if any(w in n.phrase for w in words):
                n.season = name
    return found


def evaluate(amazon: AmazonClient, niches: list[Niche], rc: ResearchConfig,
             keepa: KeepaClient | None = None) -> None:
    """Дополняет ниши данными выдачи и BSR (что удастся получить)."""
    for n in niches:
        try:
            res = amazon.search(n.phrase)
            n.total = res["total"]
            organic = [i for i in res["items"] if not i["sponsored"]][:10] or res["items"][:10]
            n.top_reviews = [i["reviews"] for i in organic]
            if keepa is None:
                for it in organic[:rc.bsr_top]:
                    try:
                        if b := amazon.bsr(it["asin"]):
                            n.top_bsr.append(b)
                    except (Blocked, httpx.HTTPError) as e:
                        n.notes.append(f"BSR недоступен: {e}")
                        break
        except (Blocked, httpx.HTTPError) as e:  # капча или сбой сети — оцениваем без выдачи
            n.notes.append(f"выдача недоступна: {e}")
        if keepa is not None:
            try:
                items = keepa.search(n.phrase)[:10]
                n.top_bsr = [i["bsr"] for i in items[:rc.bsr_top] if i["bsr"]]
                if not n.top_reviews:
                    n.top_reviews = [i["reviews"] for i in items]
            except httpx.HTTPError as e:
                n.notes.append(f"Keepa: {e}")
        score(n)


def plan_book(text_router, phrase: str, rc: ResearchConfig) -> dict:
    """Фраза ниши → план книги (тема, аудитория, возраст, формат, число страниц)."""
    audience = profiles.detect(phrase)
    plan = {"theme": phrase.replace("coloring book", "").strip(), "audience": audience,
            "age": "4-8" if audience == "kids" else "", "trim": "8.5x11", "pages": rc.min_pages, "angle": ""}
    try:
        data = text_router.chat_json(PLAN_PROMPT.format(phrase=phrase, trims=list(book.TRIMS),
                                                        min_pages=rc.min_pages, max_pages=rc.max_pages),
                                     temperature=0.4)["data"]
        if isinstance(data, dict):
            plan.update({k: v for k, v in data.items() if k in plan and v not in (None, "")})
    except AllProvidersFailed as e:
        log.warning("план LLM недоступен, беру значения по умолчанию: %s", str(e).splitlines()[0])
    if plan["audience"] not in profiles.PROFILES:
        plan["audience"] = audience
    try:
        book.parse_trim(plan["trim"])
    except ValueError:
        plan["trim"] = "8.5x11"
    try:
        plan["pages"] = max(rc.min_pages, min(rc.max_pages, int(plan["pages"])))
    except (TypeError, ValueError):
        plan["pages"] = rc.min_pages
    plan["phrase"] = phrase
    return plan


def research(*, amazon: AmazonClient, text_router, history: History, rc: ResearchConfig,
             report_dir: Path, keepa: KeepaClient | None = None, today: dt.date | None = None,
             moderation_required: bool = True) -> tuple[dict | None, list[Niche]]:
    """Полный цикл. Возвращает (план книги или None, все оценённые ниши). Отчёт — report_dir/<дата>.json."""
    today = today or dt.date.today()
    found = collect_candidates(amazon, text_router, rc, today)
    recent = history.recent_phrases(rc.repeat_days, today)
    fresh = []
    for n in found.values():
        sim = max((similar(n.phrase, r) for r in recent), default=0)
        if n.phrase in recent or sim > rc.similar_max:
            n.notes.append("недавно уже делали похожую нишу")
            continue
        fresh.append(n)
    fresh.sort(key=lambda n: -n.suggest_score)
    shortlist = fresh[:rc.evaluate_top]
    evaluate(amazon, shortlist, rc, keepa)
    shortlist.sort(key=lambda n: -n.score)

    plan = None
    if shortlist:
        rejected = safety.moderate([n.phrase for n in shortlist[:5]], text_router, required=moderation_required)
        for n in shortlist[:5]:
            if n.phrase in rejected:
                n.notes.append(rejected[n.phrase])
                continue
            if n.confidence != "low" and n.top_bsr and n.demand < 0.2:
                continue  # лидеры не продаются — нет смысла
            plan = plan_book(text_router, n.phrase, rc)
            if bad := safety.moderate([plan["theme"]], text_router, required=moderation_required):
                n.notes.append("тема плана не прошла модерацию: " + next(iter(bad.values())))
                plan = None
                continue
            plan["niche"] = asdict(n)
            break

    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / f"{today.isoformat()}.json").write_text(json.dumps({
        "date": today.isoformat(), "amazon_blocked": amazon.blocked, "keepa": keepa is not None,
        "season": [n for n, _ in upcoming(today, tuple(rc.season_lead))], "chosen": plan,
        "shortlist": [asdict(n) for n in shortlist],
        "candidates": len(found)}, ensure_ascii=False, indent=2), encoding="utf-8")
    return plan, shortlist


def keepa_from_env() -> KeepaClient | None:
    key = os.getenv("KEEPA_API_KEY", "").strip()
    return KeepaClient(key) if key else None
