"""Постобработка страницы-раскраски: картинка от генератора → чистые векторные контуры.

Генератор выдаёт ~1024×1024 с серыми тенями, мусорными точками и мыльными краями. Для печати
KDP нужно 300 DPI (8.5×11" = 2550×3300 px), простое растягивание даёт размытые линии.
Поэтому: порог → чистка мусора → векторизация potrace. Вектор рисуется в PDF в любом размере
с идеально чёткими линиями.
"""
from dataclasses import dataclass

import cv2
import numpy as np
import potrace
from PIL import Image

MIN_SPECK_FRAC = 0.00004   # площадь пятна (доля от всей картинки), меньше — мусор, удаляем
MIN_HOLE_FRAC = 0.00002    # белые дырки внутри линий меньше этого — заливаем


@dataclass
class VectorPage:
    """Результат векторизации в пикселях маски (ось Y вниз, как в картинке).

    subpaths — замкнутые контуры, каждый: [("M", x, y), ("L", x, y) | ("C", x1, y1, x2, y2, x, y), ...].
    Заливать по правилу even-odd: внутренние контуры — это белые области.
    """
    subpaths: list[list[tuple]]
    width: int
    height: int


def _remove_small(mask: np.ndarray, min_area: int) -> np.ndarray:
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    keep = np.zeros(n, dtype=bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_area
    return keep[labels]


def binarize(img: Image.Image, *, upscale: int = 2, threshold: int | None = None,
             close_gaps: int = 0) -> np.ndarray:
    """Картинка → маска чернил (True = линия).

    upscale     — увеличить перед порогом: край антиалиасинга даёт субпиксельную точность.
    threshold   — фиксированный порог 0..255; None = Otsu, но не светлее 200, чтобы светло-серые
                  тени (частая болезнь FLUX) уходили в белое, а не в чёрное.
    close_gaps  — радиус морфологического замыкания (px исходника): закрывает разрывы в контурах,
                  чтобы области заливались. 0 = выключено (мелкие детали не слипаются).
    """
    gray = np.asarray(img.convert("L"))
    if upscale > 1:
        gray = cv2.resize(gray, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)   # гасит JPEG-шум, не трогая форму линий
    if threshold is None:
        otsu, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        threshold = int(min(otsu, 200))
    ink = gray < threshold

    if close_gaps:
        k = 2 * close_gaps * max(upscale, 1) + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        ink = cv2.morphologyEx(ink.astype(np.uint8), cv2.MORPH_CLOSE, kernel).astype(bool)

    area = ink.size
    ink = _remove_small(ink, max(4, int(area * MIN_SPECK_FRAC)))          # чёрный мусор
    ink = ~_remove_small(~ink, max(4, int(area * MIN_HOLE_FRAC)))          # белые дырки в линиях
    return ink


def vectorize(ink: np.ndarray, *, smooth: float = 1.0, turdsize: int = 10) -> VectorPage:
    """Маска → кривые Безье. smooth (alphamax potrace): 0 — ломаные, 1.0 — плавно, 1.33 — очень плавно."""
    # potracer трассирует False-пиксели (инвертирует вход), поэтому отдаём ему «белое = True».
    path = potrace.Bitmap(~ink).trace(turdsize=turdsize, turnpolicy=potrace.POTRACE_TURNPOLICY_MINORITY,
                                      alphamax=smooth, opticurve=True, opttolerance=0.2)
    subpaths = []
    for curve in path:
        sp = curve.start_point
        ops = [("M", sp.x, sp.y)]
        for seg in curve.segments:
            e = seg.end_point
            if seg.is_corner:
                ops += [("L", seg.c.x, seg.c.y), ("L", e.x, e.y)]
            else:
                ops.append(("C", seg.c1.x, seg.c1.y, seg.c2.x, seg.c2.y, e.x, e.y))
        subpaths.append(ops)
    h, w = ink.shape
    return VectorPage(subpaths=subpaths, width=w, height=h)


def to_svg(page: VectorPage) -> str:
    """SVG для просмотра/экспорта."""
    d = " ".join(
        "".join(op[0] + ",".join(f"{v:.2f}" for v in op[1:]) for op in sp) + "Z"
        for sp in page.subpaths
    )
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {page.width} {page.height}">'
            f'<rect width="100%" height="100%" fill="#fff"/>'
            f'<path fill="#000" fill-rule="evenodd" d="{d}"/></svg>')


def render(page: VectorPage, size: tuple[int, int]) -> np.ndarray:
    """Растеризация вектора обратно в маску (True = чернила) — для превью и проверок."""
    w, h = size
    sx, sy = w / page.width, h / page.height
    polys = []
    for sp in page.subpaths:
        pts, cur = [], (0.0, 0.0)
        for op in sp:
            if op[0] in ("M", "L"):
                cur = (op[1], op[2])
                pts.append(cur)
            else:
                p0, p1, p2, p3 = np.array(cur), np.array(op[1:3]), np.array(op[3:5]), np.array(op[5:7])
                t = np.linspace(0, 1, 12)[1:, None]
                pts += list((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3)
                cur = tuple(p3)
        polys.append((np.array(pts) * [sx, sy] * 16).round().astype(np.int32))
    out = np.zeros((h, w), np.uint8)
    # even-odd: каждый контур XOR-ится поверх, вложенные контуры вырезают дырки
    for poly in polys:
        layer = np.zeros_like(out)
        cv2.fillPoly(layer, [poly], 1, lineType=cv2.LINE_8, shift=4)
        out ^= layer
    return out.astype(bool)


def process(img: Image.Image, *, upscale: int = 2, threshold: int | None = None,
            close_gaps: int = 0, smooth: float = 1.0) -> VectorPage:
    """Полный цикл: картинка от генератора → векторная страница."""
    ink = binarize(img, upscale=upscale, threshold=threshold, close_gaps=close_gaps)
    return vectorize(ink, smooth=smooth)
