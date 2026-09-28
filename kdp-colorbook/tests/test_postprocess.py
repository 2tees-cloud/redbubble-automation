"""Офлайн-тесты постобработки и сборки PDF: python tests/test_postprocess.py"""
import io
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import book, postprocess  # noqa: E402


def dirty_page(seed=1):
    """Похоже на выдачу FLUX: контур + серая тень + мусорные точки + размытие + JPEG."""
    rng = np.random.default_rng(seed)
    im = Image.new("L", (1024, 1024), 255)
    d = ImageDraw.Draw(im)
    d.ellipse((260, 300, 760, 760), fill=205)
    d.ellipse((250, 290, 770, 770), outline=0, width=14)
    d.ellipse((490, 230, 520, 260), fill=0)
    for _ in range(300):
        x, y = rng.integers(20, 1000, 2)
        d.ellipse((x - 2, y - 2, x + 2, y + 2), fill=int(rng.integers(0, 120)))
    im = im.filter(ImageFilter.GaussianBlur(1.2))
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=70)
    return Image.open(io.BytesIO(buf.getvalue()))


def test_binarize_removes_gray_and_specks():
    ink = postprocess.binarize(dirty_page(), upscale=1)
    # центр серой тени — белый
    assert not ink[530, 530]
    # контур — чёрный
    assert ink[530, 256]
    # остались только кольцо и глаз (+ возможно точки, прилипшие к линии)
    import cv2
    n, _ = cv2.connectedComponents(ink.astype(np.uint8))
    assert n - 1 <= 4, n - 1


def test_vectorize_roundtrip_matches_mask():
    ink = postprocess.binarize(dirty_page(), upscale=1)
    page = postprocess.vectorize(ink)
    # кольцо = 2 контура (внешний + дырка), глаз = 1
    assert 3 <= len(page.subpaths) <= 6, len(page.subpaths)
    back = postprocess.render(page, (page.width, page.height))
    iou = (back & ink).sum() / (back | ink).sum()
    assert iou > 0.9, iou
    assert not back[530, 530], "дырка внутри кольца должна остаться белой (even-odd)"
    svg = postprocess.to_svg(page)
    assert svg.startswith("<svg") and 'fill-rule="evenodd"' in svg


def test_upscaled_render_is_sharp():
    page = postprocess.process(dirty_page())
    m = postprocess.render(page, (2550, 2550))
    assert m.shape == (2550, 2550)
    assert 0.01 < m.mean() < 0.1, m.mean()


def test_gutter_table():
    assert book.gutter_inches(24) == 0.375
    assert book.gutter_inches(151) == 0.5
    assert book.gutter_inches(828) == 0.875
    try:
        book.gutter_inches(900)
        raise AssertionError("должно было упасть")
    except ValueError:
        pass


def pdf_pages(path):
    """Разбор без внешних библиотек: (MediaBox, распакованный контент) каждой страницы по порядку."""
    import re
    import zlib
    raw = Path(path).read_bytes()
    objs = {int(m[1]): m[2] for m in re.finditer(rb"(\d+) 0 obj(.*?)endobj", raw, re.S)}
    pages = []
    for body in objs.values():
        if re.search(rb"/Type /Page\b", body):
            box = [float(x) for x in re.search(rb"/MediaBox \[([^\]]*)\]", body)[1].split()]
            cref = int(re.search(rb"/Contents (\d+) 0 R", body)[1])
            stream = re.search(rb"stream\r?\n(.*?)\r?\nendstream", objs[cref], re.S)[1]
            pages.append((box, zlib.decompress(stream) if b"FlateDecode" in objs[cref] else stream))
    return pages, raw


def test_build_interior_pdf():
    page = postprocess.process(dirty_page())
    out = Path(tempfile.mkdtemp()) / "i.pdf"
    res = book.build_interior([page] * 13, out)
    assert res["page_count"] == 26
    pages, raw = pdf_pages(out)
    assert len(pages) == 26
    assert pages[0][0] == [0, 0, 612, 792]           # 8.5×11" в пунктах
    assert b"/Font" not in raw                        # никакого текста → нет проблем со шрифтами
    assert b" c" in pages[0][1] and b"f*" in pages[0][1]   # кривые Безье, заливка even-odd
    assert len(pages[1][1]) < 50                      # оборот пустой
    # поле у корешка: на правой странице рисунок сдвинут вправо, на левой — влево
    assert res["gutter"] == 0.5


def test_odd_pages_padded_to_even():
    page = postprocess.process(dirty_page())
    res = book.build_interior([page] * 25, Path(tempfile.mkdtemp()) / "i.pdf", blank_backs=False)
    assert res["page_count"] == 26


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\nВсе {len(tests)} тестов прошли.")
