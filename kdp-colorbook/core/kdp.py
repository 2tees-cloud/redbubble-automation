"""Робот загрузки paperback в KDP (Playwright, настоящий браузер).

Официального API публикации у KDP нет, поэтому робот заполняет те же формы, что и человек:
Details → Content → Pricing → Publish. Важно понимать риски:
  - условия Amazon запрещают роботов; за автоматизацию KDP может заблокировать аккаунт;
  - вёрстка KDP меняется — селекторы вынесены в kdp_selectors.yaml, при сбое сохраняются
    скриншот и HTML (папка книги/kdp_debug), по ним селектор правится без изменения кода;
  - вход: постоянный профиль браузера (data/kdp_profile). Один раз войти вручную
    (scripts/kdp_login.py) — дальше сессия живёт неделями. Капча/2FA → NeedsHuman и уведомление.

Прогресс по шагам хранится в <книга>/kdp_state.json: повторный запуск продолжает с того же места
(ID книги в KDP запоминается после первого «Save and Continue»).
"""
import json
import logging
import re
import time
from contextlib import contextmanager
from pathlib import Path

import yaml

log = logging.getLogger("kdp")
ROOT = Path(__file__).resolve().parent.parent


class KdpError(RuntimeError):
    def __init__(self, step: str, detail: str, debug: Path | None = None):
        super().__init__(f"KDP, шаг «{step}»: {detail}" + (f" (скриншот: {debug})" if debug else ""))
        self.step, self.debug = step, debug


class NeedsHuman(KdpError):
    """Нужен человек: вход, капча, двухфакторная проверка."""


def print_cost_usd(pages: int) -> float:
    """Себестоимость печати ч/б paperback на amazon.com (правила KDP 2023+: до 108 стр. — фикс)."""
    return 2.30 if pages <= 108 else round(1.00 + 0.012 * pages, 2)


def min_price_usd(pages: int, royalty: float = 0.60) -> float:
    """Минимальная цена, при которой роялти ≥ 0: цена × 60% ≥ печать."""
    return round(print_cost_usd(pages) / royalty + 0.005, 2)


def choose_price(pages: int, wanted: float) -> float:
    """Цена не ниже минимальной (+$1 запаса на роялти), с окончанием .99."""
    p = max(wanted, min_price_usd(pages) + 1.0)
    price = int(p) + 0.99
    return round(price if price >= p else price + 1, 2)


class KdpUploader:
    def __init__(self, cfg: dict, *, selectors_path: Path = ROOT / "kdp_selectors.yaml"):
        self.cfg = cfg
        self.base = cfg.get("base_url", "https://kdp.amazon.com/en_US").rstrip("/")
        self.sel = yaml.safe_load(Path(selectors_path).read_text(encoding="utf-8"))
        self.timeout = float(cfg.get("timeout_s", 30)) * 1000
        # обработка PDF и превьюер KDP занимают минуты
        self.long_timeout = float(cfg.get("processing_timeout_s", 900)) * 1000
        self.page = None
        self._pw = self._ctx = None
        self.debug_dir: Path | None = None

    # --- браузер ------------------------------------------------------------------
    def __enter__(self):
        from playwright.sync_api import sync_playwright  # импорт тут: без KDP-шага playwright не нужен
        self._pw = sync_playwright().start()
        opts = dict(headless=bool(self.cfg.get("headless", False)), slow_mo=int(self.cfg.get("slow_mo_ms", 80)),
                    viewport={"width": 1400, "height": 1000}, accept_downloads=False)
        if self.cfg.get("browser_path"):
            opts["executable_path"] = self.cfg["browser_path"]
        elif self.cfg.get("channel"):
            opts["channel"] = self.cfg["channel"]  # "chrome" — установленный Google Chrome (меньше подозрений)
        profile = Path(self.cfg.get("profile_dir") or ROOT / "data" / "kdp_profile")
        if not profile.is_absolute():
            profile = ROOT / profile  # относительно папки проекта, а не текущей директории
        profile.mkdir(parents=True, exist_ok=True)
        self._ctx = self._pw.chromium.launch_persistent_context(str(profile), **opts)
        self.page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        self.page.set_default_timeout(self.timeout)
        return self

    def __exit__(self, *exc):
        try:
            if self._ctx:
                self._ctx.close()
        finally:
            if self._pw:
                self._pw.stop()

    # --- поиск элементов ------------------------------------------------------------
    def _loc(self, selector: str):
        if selector.startswith("label="):
            return self.page.get_by_label(selector[6:], exact=False)
        return self.page.locator(selector)

    def find(self, group: str, key: str, *, timeout: float | None = None, fmt: dict | None = None,
             required: bool = True):
        """Первый видимый/существующий элемент из вариантов селектора. Ждёт до timeout (мс)."""
        variants = [v.format(**fmt) if fmt else v for v in self.sel[group][key]]
        deadline = time.time() + (self.timeout if timeout is None else timeout) / 1000
        while True:
            for v in variants:
                try:
                    loc = self._loc(v)
                    if loc.count() > 0:
                        first = loc.first
                        # поля загрузки файлов в KDP скрыты — для них видимость не требуется
                        if first.is_visible() or first.get_attribute("type") == "file":
                            return first
                except Exception:  # noqa: BLE001 — кривой селектор не должен ронять поиск
                    continue
            if time.time() >= deadline:
                if required:
                    raise LookupError(f"не найден элемент {group}.{key} (варианты: {variants})")
                return None
            time.sleep(0.3)

    def exists(self, group: str, key: str, timeout: float = 0) -> bool:
        return self.find(group, key, timeout=timeout, required=False) is not None

    def click(self, group, key, **kw):
        self.find(group, key, **kw).click()

    def fill(self, group, key, value: str, **kw):
        el = self.find(group, key, **kw)
        el.fill("")
        el.fill(value)

    @contextmanager
    def step(self, name: str):
        try:
            yield
        except (KdpError, NeedsHuman):
            raise
        except Exception as e:  # noqa: BLE001
            shot = None
            if self.debug_dir and self.page:
                self.debug_dir.mkdir(parents=True, exist_ok=True)
                shot = self.debug_dir / f"{time.strftime('%H%M%S')}_{name}.png"
                try:
                    self.page.screenshot(path=str(shot), full_page=True)
                    shot.with_suffix(".html").write_text(self.page.content(), encoding="utf-8")
                except Exception:  # noqa: BLE001
                    shot = None
            raise KdpError(name, f"{type(e).__name__}: {str(e)[:300]}", shot) from e

    # --- вход -------------------------------------------------------------------------
    def ensure_login(self, email: str = "", password: str = "") -> None:
        with self.step("login"):
            self.page.goto(f"{self.base}/bookshelf")
            if self.exists("login", "signed_in", timeout=8000):
                return
            if self.exists("login", "challenge"):
                raise NeedsHuman("login", "Amazon просит капчу/код — запустите scripts/kdp_login.py и войдите вручную")
            if not (email and password):
                raise NeedsHuman("login", "сессия истекла — запустите scripts/kdp_login.py и войдите вручную")
            if el := self.find("login", "email", timeout=5000, required=False):
                el.fill(email)
                if c := self.find("login", "continue", timeout=2000, required=False):
                    c.click()
            self.fill("login", "password", password)
            self.click("login", "submit")
            if self.exists("login", "challenge", timeout=5000):
                raise NeedsHuman("login", "после пароля Amazon просит код/капчу — войдите вручную через scripts/kdp_login.py")
            self.find("login", "signed_in", timeout=20000)

    # --- состояние книги ------------------------------------------------------------------
    @staticmethod
    def _state_path(book_dir: Path) -> Path:
        return Path(book_dir) / "kdp_state.json"

    def _load_state(self, book_dir: Path) -> dict:
        p = self._state_path(book_dir)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"done": []}

    def _save_state(self, book_dir: Path, st: dict) -> None:
        self._state_path(book_dir).write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")

    def _remember_title(self, st: dict) -> None:
        if m := re.search(r"/title-setup/paperback/([^/?#]+)/", self.page.url):
            if m.group(1) != "new":
                st["title_id"] = m.group(1)

    def _url(self, st: dict, tab: str) -> str:
        return f"{self.base}/title-setup/paperback/{st.get('title_id', 'new')}/{tab}"

    # --- шаги -----------------------------------------------------------------------------------
    def _details(self, meta: dict, categories: list[list[str]]) -> None:
        p = self.page
        self.fill("details", "title", meta["title"])
        if meta.get("subtitle"):
            self.fill("details", "subtitle", meta["subtitle"])
        first, _, last = (meta.get("author") or "").strip().partition(" ")
        self.fill("details", "author_first", first or meta.get("author", ""))
        self.fill("details", "author_last", last or first)
        # описание: редактор CKEditor в iframe; запасной путь — скрытый textarea
        frame_el = self.find("details", "description_frame", timeout=5000, required=False)
        if frame_el is not None:
            frame = frame_el.content_frame  # в новых Playwright — свойство, в старых — метод
            body = (frame() if callable(frame) else frame).locator("body")
            body.evaluate("(b, html) => { b.innerHTML = html; }", meta["description"])
            body.click()
            p.keyboard.press("End")
        else:
            ta = self.find("details", "description_textarea")
            ta.evaluate("(t, html) => { t.value = html; t.dispatchEvent(new Event('input', {bubbles:true}));"
                        " t.dispatchEvent(new Event('change', {bubbles:true})); }", meta["description"])
        self.click("details", "rights_own")
        if el := self.find("details", "adult_content_no", timeout=2000, required=False):
            el.check()
        for i, kw in enumerate(meta.get("keywords", [])[:7]):
            self.fill("details", "keyword", kw, fmt={"i": i})
        if categories:
            self._categories(categories)
        self.click("details", "save_continue")
        p.wait_for_url(re.compile(r".*/title-setup/paperback/(?!new)[^/]+/content.*"), timeout=self.timeout * 2)

    def _categories(self, categories: list[list[str]]) -> None:
        """Каждая категория — путь выпадающих списков; последний элемент — чекбокс «размещения»."""
        self.click("details", "categories_button")
        modal = self.find("details", "categories_modal", timeout=10000)
        for path in categories[:3]:
            selects = modal.locator("select")
            for level, label in enumerate(path[:-1]):
                selects.nth(level).select_option(label=label)
                time.sleep(0.5)
            modal.get_by_label(path[-1], exact=False).first.check()
        self.click("details", "categories_save")

    def _content(self, interior: Path, cover: Path, trim: tuple[float, float], paper: str,
                 finish: str, ai_tool: str) -> None:
        p = self.page
        if not self.exists("content", "isbn_assigned", timeout=2000):
            self.click("content", "isbn_free")
            self.click("content", "isbn_confirm", timeout=15000)
            self.find("content", "isbn_assigned", timeout=30000)
        self.click("content", "ink_bw_cream" if paper == "cream" else "ink_bw_white")
        key = f"{trim[0]:g}x{trim[1]:g}".replace(".", "_")
        label = f"{trim[0]:g} x {trim[1]:g} in"
        self.click("content", "trim_open")
        self.click("content", "trim_option", fmt={"key": key, "label": label})
        self.click("content", "no_bleed")
        self.click("content", "finish_glossy" if finish == "glossy" else "finish_matte")
        self.find("content", "manuscript_input").set_input_files(str(interior))
        self.find("content", "manuscript_done", timeout=self.long_timeout)
        self.click("content", "cover_own")
        self.find("content", "cover_input").set_input_files(str(cover))
        self.find("content", "cover_done", timeout=self.long_timeout)
        # раскрытие AI-контента: текст сгенерирован ИИ частично, иллюстрации — полностью
        self.click("content", "ai_yes")
        for key_, value in (("ai_text_select", self.cfg.get("ai_text", "Some sections, with extensive editing")),
                            ("ai_images_select", self.cfg.get("ai_images", "Entire work, with minimal or no editing")),
                            ("ai_translation_select", "None")):
            if el := self.find("content", key_, timeout=3000, required=False):
                el.select_option(label=value)
        if el := self.find("content", "ai_images_tool", timeout=3000, required=False):
            el.fill(ai_tool)
        self.click("content", "preview_launch")
        self.click("content", "preview_approve", timeout=self.long_timeout)
        self.click("content", "save_continue", timeout=60000)
        p.wait_for_url(re.compile(r".*/pricing.*"), timeout=self.timeout * 2)

    def _pricing(self, price: float, publish: bool) -> str:
        if el := self.find("pricing", "all_territories", timeout=3000, required=False):
            el.click()
        self.fill("pricing", "price_us", f"{price:.2f}")
        self.page.keyboard.press("Tab")  # KDP пересчитывает цены других рынков по US
        if publish:
            self.click("pricing", "publish")
            self.find("pricing", "published", timeout=120000)
            return "published"
        self.click("pricing", "save_draft")
        self.find("pricing", "saved", timeout=60000)
        return "draft"

    # --- всё вместе ---------------------------------------------------------------------------
    def upload(self, book_dir: Path, *, meta: dict, interior: Path, cover: Path, trim: tuple[float, float],
               pages: int, categories: list[list[str]] | None = None, publish: bool = True) -> dict:
        """Загружает книгу; повторный вызов продолжает с незавершённого шага. → состояние."""
        book_dir = Path(book_dir)
        self.debug_dir = book_dir / "kdp_debug"
        st = self._load_state(book_dir)
        if st.get("result") in ("published", "draft") and (st["result"] == "published" or not publish):
            return st
        price = choose_price(pages, float(self.cfg.get("price_usd", 7.99)))
        st["price"] = price
        self.ensure_login(self.cfg.get("email", ""), self.cfg.get("password", ""))
        if "details" not in st["done"]:
            with self.step("details"):
                self.page.goto(self._url(st, "details"))
                self._details(meta, categories or [])
                self._remember_title(st)
                st["done"].append("details")
                self._save_state(book_dir, st)
        if "content" not in st["done"]:
            with self.step("content"):
                self.page.goto(self._url(st, "content"))
                self._content(interior, cover, trim, self.cfg.get("paper", "white"),
                              self.cfg.get("cover_finish", "matte"), self.cfg.get("ai_tool", "FLUX.1 [schnell]"))
                st["done"].append("content")
                self._save_state(book_dir, st)
        with self.step("pricing"):
            self.page.goto(self._url(st, "pricing"))
            st["result"] = self._pricing(price, publish)
            st["done"].append("pricing")
            self._save_state(book_dir, st)
        return st
