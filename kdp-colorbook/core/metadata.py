"""Метаданные листинга KDP: название, подзаголовок, описание, 7 ключевых фраз.

Модель пишет черновик, а правила KDP проверяются кодом: модель их регулярно нарушает
(слова «bestseller», «free», упоминания Amazon, фразы длиннее 50 символов, запрещённый HTML).
Нарушения в ключевых фразах и описании исправляются сами, в названии — только предупреждение:
название человек должен утвердить сам.
"""
import html
import re

from . import profiles, safety

LIMITS = {"title_subtitle": 200, "keyword": 50, "keywords": 7, "description": 4000}

# Запрещено/не рекомендуется KDP в названии и ключевых словах (обещания продаж, программы Amazon)
BANNED = ["best seller", "bestseller", "best-selling", "bestselling", "free", "sale", "discount",
          "new release", "kindle unlimited", "kindle", "amazon", "kdp", "prime", "#1", "top rated",
          "cheap"]
# HTML, который KDP разрешает в описании
ALLOWED_TAGS = {"b", "i", "u", "br", "p", "h4", "h5", "h6", "ul", "ol", "li", "em", "strong"}

AI_NOTICE = ("При публикации в KDP ответьте «Да» на вопрос об AI-generated content "
             "(иллюстрации созданы ИИ). Сокрытие — нарушение правил KDP.")

PROMPT = """You write Amazon KDP listing metadata for a paperback coloring book.
Theme: "{theme}". Audience: {audience}. Interior: {images} single-sided illustrations, {trim}.
Example pages: {examples}.
Style notes: {hint}.
Return JSON:
{{"title": "catchy, contains the main search phrase, max 60 chars",
"subtitle": "max 120 chars, see style notes",
"description": "150-250 words, simple HTML allowed: <b>, <br>, <ul><li>; mention page count, single-sided pages, size",
"keywords": ["7 search phrases buyers type on Amazon, 2-5 words each, max 50 chars, do not repeat title words"],
"back_text": "1-2 cheerful sentences for the back cover, max 200 chars, no HTML",
"categories": ["3 suggested Amazon category paths"]}}
Never use: bestseller, free, sale, Amazon, Kindle, #1, brand or character names, real people."""


def _has_banned(text: str) -> list[str]:
    low = text.lower()
    return [w for w in BANNED if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", low)]


def _strip_banned(text: str) -> str:
    for w in BANNED:
        text = re.sub(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", "", text, flags=re.I)
    return re.sub(r"\s{2,}", " ", text).strip(" ,-:")


def _clean_html(desc: str) -> str:
    def tag(m):
        name = m.group(2).lower()
        return m.group(0) if name in ALLOWED_TAGS else ""
    desc = re.sub(r"<(/?)([a-zA-Z0-9]+)[^>]*>", tag, desc)
    desc = re.sub(r"<(/?)([a-zA-Z0-9]+)\s[^>]*>", r"<\1\2>", desc)  # атрибуты убираем
    return desc.strip()


def sanitize(d: dict) -> tuple[dict, list[str]]:
    """Приводит черновик к правилам KDP. Возвращает (метаданные, предупреждения)."""
    warn = []
    out = {k: (str(d.get(k) or "").strip()) for k in ("title", "subtitle", "description", "back_text")}
    out["unsafe"] = []
    for k in ("title", "subtitle"):
        if bad := _has_banned(out[k]):
            warn.append(f"{k} содержит запрещённое KDP: {', '.join(bad)} — исправьте вручную")
        if bad := safety.blocked_terms(out[k]):
            out["unsafe"].append(f"{k}: {', '.join(bad)}")
            warn.append(f"{k} содержит бренд/опасное слово: {', '.join(bad)} — публиковать нельзя")
    if len(out["title"]) + len(out["subtitle"]) > LIMITS["title_subtitle"]:
        warn.append(f"название + подзаголовок длиннее {LIMITS['title_subtitle']} символов")

    kws, seen = [], set()
    for k in d.get("keywords") or []:
        k = _strip_banned(re.sub(r"[\"“”]", "", str(k)))
        if safety.blocked_terms(k):
            continue  # фраза с брендом — выкидываем целиком
        if len(k) > LIMITS["keyword"]:
            k = k[:LIMITS["keyword"]].rsplit(" ", 1)[0]
        if k and k.lower() not in seen:
            seen.add(k.lower())
            kws.append(k)
    if len(kws) < LIMITS["keywords"]:
        warn.append(f"ключевых фраз {len(kws)} из {LIMITS['keywords']} — допишите")
    out["keywords"] = kws[:LIMITS["keywords"]]

    desc = _clean_html(out["description"])
    if bad := _has_banned(re.sub(r"<[^>]+>", " ", desc)):
        warn.append(f"описание содержит {', '.join(bad)} — проверьте формулировки")
    if bad := safety.blocked_terms(re.sub(r"<[^>]+>", " ", desc)):
        out["unsafe"].append(f"description: {', '.join(bad)}")
        warn.append(f"описание содержит бренд/опасное слово: {', '.join(bad)}")
    if len(desc) > LIMITS["description"]:
        desc = desc[:LIMITS["description"]].rsplit(" ", 1)[0]
        warn.append("описание обрезано до 4000 символов")
    out["description"] = desc
    out["back_text"] = html.unescape(re.sub(r"<[^>]+>", "", out["back_text"]))[:300]
    out["categories"] = [str(c) for c in (d.get("categories") or [])][:3]
    return out, warn


def generate(text_router, *, theme: str, age: str, images: int, trim: str = "8.5 x 11 in",
             examples: list[str] | None = None, audience: str = "kids") -> tuple[dict, list[str]]:
    ex = "; ".join((examples or [])[:6]) or theme
    prof = profiles.get(audience)
    res = text_router.chat_json(PROMPT.format(theme=theme, audience=prof["audience"].format(age=age),
                                              hint=prof["listing_hint"].format(age=age), images=images,
                                              trim=trim, examples=ex),
                                temperature=0.7, max_tokens=2500)
    data = res["data"] if isinstance(res["data"], dict) else {}
    meta, warn = sanitize(data)
    meta["provider"] = res["provider"]
    return meta, warn


def to_text(meta: dict, warnings: list[str]) -> str:
    """Для копирования в форму KDP."""
    lines = [f"TITLE:\n{meta['title']}\n", f"SUBTITLE:\n{meta['subtitle']}\n",
             f"AUTHOR:\n{meta.get('author', '')}\n", f"DESCRIPTION:\n{meta['description']}\n",
             "KEYWORDS (по одной в каждое из 7 полей):"]
    lines += [f"  {i}. {k}" for i, k in enumerate(meta["keywords"], 1)]
    if meta.get("categories"):
        lines += ["", "CATEGORIES (предложения):"] + [f"  - {c}" for c in meta["categories"]]
    lines += ["", "ВАЖНО: " + AI_NOTICE]
    if warnings:
        lines += ["", "ПРОВЕРИТЬ ВРУЧНУЮ:"] + [f"  ! {w}" for w in warnings]
    return "\n".join(lines) + "\n"
