"""Фильтр брака: страница проходит в книгу, только если выдержала все проверки.

Порядок — от дешёвых к дорогим, первая же неудача отсекает страницу:
  1. пиксели  — доля линий, залитые чёрные пятна, число областей для раскрашивания, край
  2. дубликат — перцептивный хеш против уже принятых страниц
  3. vision   — модель смотрит на картинку: текст, лишние пальцы, обрезанный объект, тени
"""
import logging
from dataclasses import dataclass, field, fields

import cv2
import numpy as np
from PIL import Image

from .base import AllProvidersFailed

log = logging.getLogger("quality")


@dataclass
class Limits:
    min_ink: float = 0.02         # меньше — почти пустая страница
    max_ink: float = 0.30         # больше — каша из линий или тёмный фон
    max_solid: float = 0.04       # доля сплошной заливки чёрным (её не раскрасить)
    min_regions: int = 6          # областей для раскрашивания меньше — скучно
    max_regions: int = 400        # больше — слишком много областей (для детей; для взрослых поднять)
    max_tiny: float = 0.15        # доля белого в ячейках мельче карандаша — слишком мелкие детали
    max_edge_ink: float = 0.15    # доля линий на самом краю — признак фона/обрезки
    dup_distance: int = 10        # хеши ближе (из 64 бит) — дубликат
    min_vision_score: int = 7     # оценка vision-модели 1..10
    vision_required: bool = False  # True: если vision недоступен — страница не принимается

    @classmethod
    def from_config(cls, cfg: dict | None) -> "Limits":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (cfg or {}).items() if k in names})


@dataclass
class Verdict:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


# --- 1. пиксели -----------------------------------------------------------
def pixel_metrics(ink: np.ndarray) -> dict:
    h, w = ink.shape
    area = ink.size
    u8 = ink.astype(np.uint8)
    # сплошная заливка: то, что переживает «открытие» кругом ~3% ширины (линии тоньше — исчезают)
    k = max(3, int(0.03 * min(h, w)) | 1)
    solid = cv2.morphologyEx(u8, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    # белые области, в которые реально можно попасть карандашом (≥0.05% страницы)
    n, _, stats, _ = cv2.connectedComponentsWithStats((~ink).astype(np.uint8), connectivity=4)
    sizes = stats[1:, cv2.CC_STAT_AREA]
    big = sizes >= area * 0.0005
    regions = int(big.sum())
    tiny = float(sizes[~big].sum() / max(sizes.sum(), 1))  # доля белого в «неподъёмных» ячейках
    b = max(2, min(h, w) // 200)
    ring = np.concatenate([ink[:b].ravel(), ink[-b:].ravel(), ink[:, :b].ravel(), ink[:, -b:].ravel()])
    return {"ink": round(float(ink.mean()), 4), "solid": round(float(solid.mean()), 4),
            "regions": regions, "tiny": round(tiny, 4), "edge_ink": round(float(ring.mean()), 4)}


def check_pixels(m: dict, lim: Limits) -> list[str]:
    r = []
    if m["ink"] < lim.min_ink:
        r.append(f"почти пусто (линий {m['ink']:.1%})")
    if m["ink"] > lim.max_ink:
        r.append(f"слишком тёмная (линий {m['ink']:.1%})")
    if m["solid"] > lim.max_solid:
        r.append(f"сплошная чёрная заливка {m['solid']:.1%}")
    if m["tiny"] > lim.max_tiny:
        r.append(f"слишком мелкие детали ({m['tiny']:.0%} белого в крошечных ячейках)")
    elif m["regions"] < lim.min_regions:
        r.append(f"мало областей для раскраски ({m['regions']})")
    if m["regions"] > lim.max_regions:
        r.append(f"слишком мелкие детали ({m['regions']} областей)")
    if m["edge_ink"] > lim.max_edge_ink:
        r.append(f"линии упираются в край ({m['edge_ink']:.1%})")
    return r


# --- 2. дубликаты ---------------------------------------------------------
def phash(ink: np.ndarray) -> int:
    """64-битный перцептивный хеш (DCT 32×32 → верхний левый угол 8×8 против медианы)."""
    small = cv2.resize(ink.astype(np.float32), (32, 32), interpolation=cv2.INTER_AREA)
    d = cv2.dct(small)[:8, :8].ravel()[1:]  # без постоянной составляющей
    bits = d > np.median(d)
    return int("".join("1" if x else "0" for x in bits), 2)


class Deduper:
    def __init__(self, max_distance: int = 10):
        self.max_distance = max_distance
        self.hashes: list[tuple[int, str]] = []

    def find(self, h: int) -> str | None:
        """Имя похожей уже принятой страницы или None."""
        for other, name in self.hashes:
            if bin(h ^ other).count("1") <= self.max_distance:
                return name
        return None

    def add(self, h: int, name: str) -> None:
        self.hashes.append((h, name))


# --- 3. vision ------------------------------------------------------------
VISION_PROMPT = """You are a strict quality inspector for a printed children's coloring book.
The page should show: "{subject}".
Answer JSON: {{"score": 1-10 overall suitability for printing as a coloring page,
"is_line_art": true if only black outlines on white (no gray, shading or filled areas),
"has_text": true if any letters, numbers, signature or watermark,
"anatomy_errors": true if extra/missing limbs or fingers, merged or broken body parts,
"cut_off": true if the main subject is cropped by the image border,
"matches_subject": true if it depicts the requested subject,
"issues": ["short description of each problem"]}}"""

_HARD = {"is_line_art": False, "has_text": True, "anatomy_errors": True,
         "cut_off": True, "matches_subject": False}


def vision_review(img: Image.Image, subject: str, text_router, lim: Limits) -> tuple[list[str], dict]:
    """Возвращает (причины отказа, сырой ответ модели)."""
    try:
        res = text_router.chat_json(VISION_PROMPT.format(subject=subject), images=[img],
                                    temperature=0.1, max_tokens=500)
    except AllProvidersFailed as e:
        log.warning("vision недоступен: %s", str(e).splitlines()[0])
        return (["vision недоступен"] if lim.vision_required else []), {}
    data = res["data"] if isinstance(res["data"], dict) else {}
    reasons = [f"vision: {k}" for k, bad in _HARD.items() if data.get(k) is bad]
    try:
        score = float(data.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    if score < lim.min_vision_score:
        reasons.append(f"vision: оценка {score:g} < {lim.min_vision_score}")
    if reasons and data.get("issues"):
        reasons.append("; ".join(map(str, data["issues"]))[:200])
    return reasons, {**data, "provider": res["provider"]}


# --- всё вместе -----------------------------------------------------------
def evaluate(img: Image.Image, ink: np.ndarray, *, subject: str = "", lim: Limits | None = None,
             deduper: Deduper | None = None, text_router=None) -> Verdict:
    """img — исходная картинка (для vision), ink — маска после postprocess.binarize."""
    lim = lim or Limits()
    m = pixel_metrics(ink)
    reasons = check_pixels(m, lim)
    if reasons:
        return Verdict(False, reasons, m)
    m["phash"] = phash(ink)
    if deduper and (twin := deduper.find(m["phash"])):
        return Verdict(False, [f"дубликат {twin}"], m)
    if text_router is not None:
        reasons, v = vision_review(img, subject, text_router, lim)
        m["vision"] = v
        if reasons:
            return Verdict(False, reasons, m)
    return Verdict(True, [], m)
