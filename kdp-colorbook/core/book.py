"""Сборка интерьера книги-раскраски в PDF под требования KDP (paperback, без bleed).

Страницы — векторные (из postprocess), поэтому печать чёткая при любом DPI.
PDF пишем сами, без reportlab: он добавляет на каждую страницу невстроенный Helvetica
даже без текста, а невстроенные шрифты — частая причина отказа KDP. Здесь шрифтов нет вообще.
"""
import logging
import zlib
from pathlib import Path

from .postprocess import VectorPage

log = logging.getLogger("book")

MIN_PAGES = 24  # минимум KDP для paperback

# Популярные для раскрасок форматы KDP paperback (дюймы). Имя = как в форме KDP.
TRIMS = {
    "8.5x11": (8.5, 11.0),    # стандарт раскрасок, дети и взрослые
    "8.5x8.5": (8.5, 8.5),    # квадрат — малыши, мандалы
    "8.25x8.25": (8.25, 8.25),
    "8x10": (8.0, 10.0),
    "8.25x11": (8.25, 11.0),
    "6x9": (6.0, 9.0),        # карманный формат (в дорогу)
}


def parse_trim(value) -> tuple[float, float]:
    """'8.5x11' | [8.5, 11] → (8.5, 11.0); только форматы из TRIMS."""
    if isinstance(value, str):
        key = value.lower().replace(" ", "").replace("×", "x")
    else:
        key = f"{float(value[0]):g}x{float(value[1]):g}"
    if key not in TRIMS:
        raise ValueError(f"формат {value!r} не поддерживается, есть: {', '.join(TRIMS)}")
    return TRIMS[key]


def trim_name(trim: tuple[float, float]) -> str:
    return f"{trim[0]:g}x{trim[1]:g}"

# Внутреннее поле (у корешка) по числу страниц — таблица KDP.
_GUTTER = [(150, 0.375), (300, 0.5), (500, 0.625), (700, 0.75), (828, 0.875)]


def gutter_inches(page_count: int) -> float:
    for limit, g in _GUTTER:
        if page_count <= limit:
            return g
    raise ValueError(f"KDP paperback: максимум 828 страниц, а тут {page_count}")


PT = 72  # пунктов в дюйме


def _page_ops(page: VectorPage, x: float, y: float, w: float, h: float) -> bytes:
    """Операторы PDF: страница вписана в прямоугольник (x, y, w, h) в пунктах, пропорции сохранены."""
    s = min(w / page.width, h / page.height)
    ox = x + (w - page.width * s) / 2
    oy = y + (h - page.height * s) / 2 + page.height * s
    # матрица cm переводит пиксели (Y вниз) в координаты PDF (Y вверх)
    out = [f"q {s:.6f} 0 0 {-s:.6f} {ox:.3f} {oy:.3f} cm 0 g"]
    for sp in page.subpaths:
        for op in sp:
            nums = " ".join(f"{v:.2f}" for v in op[1:])
            out.append(f"{nums} {'m' if op[0] == 'M' else 'l' if op[0] == 'L' else 'c'}")
        out.append("h")
    out.append("f* Q")  # f* = заливка even-odd: внутренние контуры = дырки
    return "\n".join(out).encode()


def _write_pdf(path: Path, size: tuple[float, float], contents: list[bytes], title: str,
               images: dict[int, tuple[bytes, int, int]] | None = None) -> None:
    """contents — операторы каждой страницы. images: {номер страницы: (JPEG, ширина, высота)},
    картинка доступна на странице как /Im0."""
    images = images or {}
    objs: list[bytes] = []  # objs[i] → объект номер i+1

    def add(body: bytes) -> int:
        objs.append(body)
        return len(objs)

    def esc(t: str) -> str:
        return t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    catalog = add(b"")  # заполним после pages
    pages = add(b"")
    kids = []
    for i, data in enumerate(contents):
        z = zlib.compress(data, 9)
        c = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(z) + z + b"\nendstream")
        res = b""
        if i in images:
            jpg, w, h = images[i]
            im = add(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB "
                     b"/BitsPerComponent 8 /Filter /DCTDecode /Length %d >>\nstream\n" % (w, h, len(jpg))
                     + jpg + b"\nendstream")
            res = b"/XObject << /Im0 %d 0 R >>" % im
        kids.append(add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.3f %.3f] /Contents %d 0 R "
                        b"/Resources << %s >> >>" % (pages, size[0], size[1], c, res)))
    objs[catalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % pages
    objs[pages - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % k for k in kids), len(kids))
    info = add(f"<< /Title ({esc(title)}) /Producer (kdp-colorbook) >>".encode("latin-1", "replace"))

    buf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(buf))
        buf += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(buf)
    buf += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    buf += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    buf += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objs) + 1, catalog, info, xref)
    Path(path).write_bytes(bytes(buf))


def build_interior(pages: list[VectorPage], out_path: str | Path, *,
                   trim: tuple[float, float] = (8.5, 11), margin: float = 0.5,
                   blank_backs: bool = True, title: str = "") -> dict:
    """Собирает PDF интерьера. Возвращает {"path", "page_count", "gutter"}.

    trim         — формат в дюймах (8.5×11 — стандарт раскрасок).
    margin       — внешние поля (KDP минимум 0.25", для раскрасок лучше 0.5": дети не упираются в край).
    blank_backs  — каждая картинка на правой странице, оборот пустой: маркер не просвечивает
                   на следующий рисунок. Стандарт жанра.
    """
    if not pages:
        raise ValueError("нет страниц")
    count = page_count(len(pages), blank_backs)  # в печатной книге чётное число страниц
    if count < MIN_PAGES:
        log.warning("Страниц %d, KDP требует минимум %d — добавьте картинок", count, MIN_PAGES)
    gutter = max(gutter_inches(max(count, MIN_PAGES)), margin)

    W, H = trim[0] * PT, trim[1] * PT

    def page_box(num: int) -> tuple[float, float, float, float]:
        # нечётные страницы — правые (корешок слева), чётные — левые (корешок справа)
        left = gutter if num % 2 else margin
        right = margin if num % 2 else gutter
        return left * PT, margin * PT, W - (left + right) * PT, H - 2 * margin * PT

    contents = []
    for page in pages:
        contents.append(_page_ops(page, *page_box(len(contents) + 1)))
        if blank_backs:
            contents.append(b"")
    contents += [b""] * (count - len(contents))  # добиваем до чётного
    _write_pdf(Path(out_path), (W, H), contents, title)
    return {"path": str(out_path), "page_count": count, "gutter": gutter}


def page_count(images: int, blank_backs: bool = True) -> int:
    """Сколько страниц будет в интерьере (нужно для ширины корешка)."""
    n = images * 2 if blank_backs else images
    return n + n % 2


def write_image_pdf(path: str | Path, img, size_in: tuple[float, float], title: str = "") -> None:
    """Одна страница точного размера (дюймы) с картинкой на весь лист — для обложки.
    Размер страницы задаётся в пунктах, поэтому не зависит от округления пикселей."""
    import io
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=95, subsampling=0, dpi=(300, 300))
    W, H = size_in[0] * PT, size_in[1] * PT
    _write_pdf(Path(path), (W, H), [f"q {W:.3f} 0 0 {H:.3f} 0 0 cm /Im0 Do Q".encode()], title,
               {0: (buf.getvalue(), img.width, img.height)})
