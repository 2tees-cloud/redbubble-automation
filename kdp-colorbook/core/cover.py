"""Обложка KDP paperback: задник + корешок + лицо одним листом с bleed, 300 DPI.

Лицо — раскрашенная программно страница из самой книги (вектор → заливка областей палитрой):
чётко при любом размере, бесплатно и честно показывает, что внутри. Весь текст рисуется
в картинку, поэтому в PDF нет шрифтов и нечего «встраивать».
"""
import random
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import book
from .postprocess import VectorPage, render

DPI = 300
BLEED = 0.125
SAFE = 0.375                 # отступ текста/картинок от линии обреза (KDP минимум 0.125")
SPINE_TEXT_MIN_PAGES = 79    # KDP разрешает текст на корешке только от 79 страниц
SPINE_TEXT_MARGIN = 0.0625   # поля текста на корешке с каждой стороны
BARCODE = (2.0, 1.2)         # место под штрихкод KDP на задней стороне, справа внизу
PAPER = {"white": 0.002252, "cream": 0.0025}  # толщина листа, дюймы (ч/б интерьер)

ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / "assets" / "fonts" / "Fredoka.ttf"
FALLBACK_FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                  "C:/Windows/Fonts/arialbd.ttf", "/Library/Fonts/Arial Bold.ttf"]

PALETTES = {
    "candy":  {"bg": "#7ec8e3", "dark": "#1d3557",
               "fill": ["#ffadad", "#ffd6a5", "#fdffb6", "#caffbf", "#9bf6ff", "#a0c4ff", "#bdb2ff", "#ffc6ff"]},
    "sunny":  {"bg": "#ffb703", "dark": "#023047",
               "fill": ["#8ecae6", "#219ebc", "#ffb703", "#fb8500", "#90be6d", "#f9c74f", "#f28482", "#84a59d"]},
    "jungle": {"bg": "#52b788", "dark": "#1b4332",
               "fill": ["#b7e4c7", "#74c69d", "#ffd166", "#ef476f", "#06d6a0", "#f4a261", "#e9c46a", "#a8dadc"]},
    "berry":  {"bg": "#c77dff", "dark": "#240046",
               "fill": ["#ffc8dd", "#ffafcc", "#bde0fe", "#a2d2ff", "#cdb4db", "#fcf6bd", "#d0f4de", "#ff99c8"]},
}


def _rgb(h: str) -> tuple[int, int, int]:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


@dataclass
class CoverSpec:
    trim_w: float
    trim_h: float
    pages: int
    paper: str = "white"

    @property
    def spine(self) -> float:
        return self.pages * PAPER[self.paper]

    @property
    def size_in(self) -> tuple[float, float]:
        return 2 * BLEED + 2 * self.trim_w + self.spine, self.trim_h + 2 * BLEED

    @property
    def spine_text(self) -> bool:
        return self.pages >= SPINE_TEXT_MIN_PAGES

    # прямоугольники панелей в дюймах от левого верхнего угла листа (x0, y0, x1, y1), по линии обреза
    @property
    def back(self):
        return BLEED, BLEED, BLEED + self.trim_w, BLEED + self.trim_h

    @property
    def spine_box(self):
        x = BLEED + self.trim_w
        return x, BLEED, x + self.spine, BLEED + self.trim_h

    @property
    def front(self):
        x = BLEED + self.trim_w + self.spine
        return x, BLEED, x + self.trim_w, BLEED + self.trim_h

    @property
    def barcode(self):
        x1, y1 = self.back[2] - 0.25, self.back[3] - 0.25
        return x1 - BARCODE[0], y1 - BARCODE[1], x1, y1


def px(v: float) -> int:
    return round(v * DPI)


def _box_px(box, inset: float = 0.0) -> tuple[int, int, int, int]:
    return px(box[0] + inset), px(box[1] + inset), px(box[2] - inset), px(box[3] - inset)


# --- раскраска страницы ----------------------------------------------------
def colorize(page: VectorPage, size: tuple[int, int], palette: dict, seed: int = 0,
             ink_color: str | None = None) -> Image.Image:
    """Вектор → цветная картинка RGBA: области залиты палитрой, фон вокруг прозрачный."""
    rng = random.Random(seed)
    w, h = size
    ink = render(page, (w * 2, h * 2))  # рисуем вдвое крупнее, потом уменьшаем — сглаженные края
    n, labels = cv2.connectedComponents((~ink).astype(np.uint8), connectivity=4)
    border = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])))
    colors = np.zeros((n, 4), np.uint8)
    for i in range(1, n):
        if i not in border:
            colors[i] = (*_rgb(rng.choice(palette["fill"])), 255)
    out = colors[labels]
    out[ink] = (*_rgb(ink_color or "#1a1a1a"), 255)
    return Image.fromarray(out, "RGBA").resize((w, h), Image.LANCZOS)


# --- текст -----------------------------------------------------------------
def load_font(size: int, weight: int = 700, path: str | Path | None = None) -> ImageFont.FreeTypeFont:
    for p in [path, FONT, *FALLBACK_FONTS]:
        if p and Path(p).exists():
            f = ImageFont.truetype(str(p), size)
            try:
                f.set_variation_by_axes([weight, 100])  # Fredoka: [вес, ширина]
            except (OSError, AttributeError, ValueError):
                pass
            return f
    return ImageFont.load_default(size)


def fit_text(draw: ImageDraw.ImageDraw, text: str, box_w: int, box_h: int, *, max_size: int,
             weight: int = 700, stroke: float = 0.0, font_path=None, spacing: float = 1.08):
    """Подбирает крупнейший шрифт и перенос строк, чтобы текст влез в box. → (font, lines, line_h, sw)."""
    words = text.split()
    size = max_size
    while size > 8:
        f = load_font(size, weight, font_path)
        sw = round(size * stroke)
        lines, cur = [], ""
        for wd in words:
            t = f"{cur} {wd}".strip()
            if draw.textlength(t, font=f) + 2 * sw <= box_w or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = wd
        lines.append(cur)
        line_h = round(size * spacing) + 2 * sw
        widest = max(draw.textlength(ln, font=f) for ln in lines) + 2 * sw
        if widest <= box_w and line_h * len(lines) <= box_h:
            return f, lines, line_h, sw
        size = int(size * 0.94)
    return load_font(8, weight, font_path), [text], 10, 0


def draw_text(img: Image.Image, text: str, box: tuple[int, int, int, int], *, max_size: int,
              fill: str, stroke_fill: str | None = None, stroke: float = 0.0, weight: int = 700,
              valign: str = "center", font_path=None) -> int:
    """Текст по центру box. Возвращает нижнюю границу нарисованного текста (px)."""
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    f, lines, lh, sw = fit_text(d, text, x1 - x0, y1 - y0, max_size=max_size, weight=weight,
                                stroke=stroke if stroke_fill else 0, font_path=font_path)
    total = lh * len(lines)
    y = y0 if valign == "top" else y0 + (y1 - y0 - total) // 2
    for ln in lines:
        d.text(((x0 + x1) // 2, y + lh // 2), ln, font=f, fill=fill, anchor="mm",
               stroke_width=sw, stroke_fill=stroke_fill)
        y += lh
    return y


def _card(img: Image.Image, box, radius: int, fill="#ffffff", outline=None, width=0) -> None:
    ImageDraw.Draw(img).rounded_rectangle(box, radius, fill=fill, outline=outline, width=width)


def _paste_center(img: Image.Image, art: Image.Image, box) -> None:
    x0, y0, x1, y1 = box
    art = art.copy()
    art.thumbnail((x1 - x0, y1 - y0), Image.LANCZOS)
    img.paste(art, (x0 + (x1 - x0 - art.width) // 2, y0 + (y1 - y0 - art.height) // 2), art)


# --- сборка ----------------------------------------------------------------
def build_cover(spec: CoverSpec, *, title: str, subtitle: str, author: str, hero: VectorPage,
                previews: list[VectorPage], back_text: str, out_pdf: str | Path,
                preview_png: str | Path | None = None, palette: str | None = None, seed: int = 0,
                font_path=None) -> dict:
    pal = PALETTES[palette] if palette else PALETTES[sorted(PALETTES)[seed % len(PALETTES)]]
    W, H = px(spec.size_in[0]), px(spec.size_in[1])
    img = Image.new("RGB", (W, H), pal["bg"])  # фон уходит в bleed
    dark = pal["dark"]

    # --- лицо
    fx0, fy0, fx1, fy1 = _box_px(spec.front, SAFE)
    fw, fh = fx1 - fx0, fy1 - fy0
    y = draw_text(img, title, (fx0, fy0, fx1, fy0 + int(fh * 0.26)), max_size=px(1.1),
                  fill="#ffffff", stroke_fill=dark, stroke=0.09, font_path=font_path)
    y = draw_text(img, subtitle, (fx0 + fw // 12, y + px(0.08), fx1 - fw // 12, y + px(0.08) + int(fh * 0.09)),
                  max_size=px(0.36), weight=600, fill=dark, stroke_fill="#ffffff", stroke=0.08,
                  valign="top", font_path=font_path)
    author_h = int(fh * 0.06) if author else 0
    top, bottom = y + px(0.15), fy1 - author_h - (px(0.1) if author else 0)
    side = min(fw, bottom - top)  # карточка по форме картинки (квадрат), по центру свободного места
    cx, cy = (fx0 + fx1) // 2, (top + bottom) // 2
    card = (cx - side // 2, cy - side // 2, cx + side // 2, cy + side // 2)
    _card(img, card, px(0.3), outline=dark, width=px(0.05))
    pad = px(0.25)
    inner = (card[0] + pad, card[1] + pad, card[2] - pad, card[3] - pad)
    art = colorize(hero, (inner[2] - inner[0], inner[3] - inner[1]), pal, seed, ink_color=dark)
    _paste_center(img, art, inner)
    if author:
        draw_text(img, author, (fx0, fy1 - author_h, fx1, fy1), max_size=px(0.3), weight=500,
                  fill="#ffffff", stroke_fill=dark, stroke=0.08, font_path=font_path)

    # --- задник: описание сверху, превью страниц сеткой, штрихкод не трогаем
    bx0, by0, bx1, by1 = _box_px(spec.back, SAFE)
    bc = _box_px(spec.barcode)
    y = draw_text(img, back_text, (bx0 + px(0.15), by0, bx1 - px(0.15), by0 + int((by1 - by0) * 0.22)),
                  max_size=px(0.3),
                  weight=500, fill=dark, valign="center", font_path=font_path)
    grid = (bx0, y + px(0.2), bx1, bc[1] - px(0.25))
    shown = previews[:4]
    if shown:
        cols = 2 if len(shown) > 1 else 1
        rows = (len(shown) + cols - 1) // cols
        gap = px(0.2)
        cw = (grid[2] - grid[0] - gap * (cols - 1)) // cols
        ch = (grid[3] - grid[1] - gap * (rows - 1)) // rows
        side = min(cw, ch)
        ox = grid[0] + (grid[2] - grid[0] - (side * cols + gap * (cols - 1))) // 2
        for i, pv in enumerate(shown):
            r, c = divmod(i, cols)
            cell = (ox + c * (side + gap), grid[1] + r * (ch + gap))
            box = (cell[0], cell[1], cell[0] + side, cell[1] + side)
            _card(img, box, px(0.15), outline=dark, width=px(0.03))
            p = px(0.12)
            line = colorize(pv, (side - 2 * p, side - 2 * p), {"fill": ["#ffffff"]}, ink_color="#1a1a1a")
            _paste_center(img, line, (box[0] + p, box[1] + p, box[2] - p, box[3] - p))

    # --- корешок
    if spec.spine_text:
        sx0, sy0, sx1, sy1 = _box_px(spec.spine_box)
        sw, sh = sx1 - sx0 - 2 * px(SPINE_TEXT_MARGIN), sy1 - sy0 - 2 * px(0.5)
        strip = Image.new("RGB", (sh, sw), pal["bg"])  # рисуем горизонтально, потом поворачиваем
        text = f"{title}   •   {author}" if author else title
        draw_text(strip, text, (0, 0, sh, sw), max_size=sw, weight=600, fill=dark, font_path=font_path)
        img.paste(strip.rotate(-90, expand=True), (sx0 + px(SPINE_TEXT_MARGIN), sy0 + px(0.5)))

    book.write_image_pdf(out_pdf, img, spec.size_in, title=title)
    if preview_png:
        guides(img, spec).save(preview_png)
    return {"path": str(out_pdf), "size_in": tuple(round(v, 4) for v in spec.size_in),
            "size_px": (W, H), "spine_in": round(spec.spine, 4), "spine_text": spec.spine_text}


def guides(img: Image.Image, spec: CoverSpec, width: int = 1800) -> Image.Image:
    """Превью с разметкой: красный — обрез, синий — корешок, зелёный — безопасная зона, оранжевый — штрихкод."""
    im = img.copy()
    d = ImageDraw.Draw(im)
    t = max(2, px(0.02))
    for box, color, inset in [(spec.back, "red", 0), (spec.front, "red", 0), (spec.spine_box, "blue", 0),
                              (spec.back, "green", SAFE), (spec.front, "green", SAFE)]:
        d.rectangle(_box_px(box, inset), outline=color, width=t)
    d.rectangle(_box_px(spec.barcode), outline="orange", width=t)
    im.thumbnail((width, width))
    return im
