"""Офлайн-тесты обложки и метаданных: python tests/test_cover.py"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from core import State, TextRouter, cover, metadata, pipeline, postprocess  # noqa: E402
from test_quality import draw, make_routers  # noqa: E402


def test_spec_matches_kdp_formula():
    s = cover.CoverSpec(8.5, 11, 30)
    assert abs(s.spine - 30 * 0.002252) < 1e-9
    w, h = s.size_in
    assert abs(w - (0.125 + 8.5 + 30 * 0.002252 + 8.5 + 0.125)) < 1e-9 and h == 11.25
    assert not s.spine_text and cover.CoverSpec(8.5, 11, 79).spine_text
    assert cover.CoverSpec(8.5, 11, 100, "cream").spine == 0.25
    x0, y0, x1, y1 = s.barcode  # штрихкод внутри задника, в 0.25" от обреза
    assert abs(x1 - (s.back[2] - 0.25)) < 1e-9 and abs(y1 - (s.back[3] - 0.25)) < 1e-9
    assert x0 > s.back[0] and abs((x1 - x0) - 2.0) < 1e-9


def test_colorize_fills_regions_only():
    page = postprocess.process(draw("house"))
    im = np.asarray(cover.colorize(page, (600, 600), cover.PALETTES["candy"], seed=1))
    assert im[5, 5, 3] == 0                      # фон вокруг — прозрачный
    assert im[300, 300, 3] == 255                # внутри дома — залито
    assert tuple(im[300, 300, :3]) != (255, 255, 255)


def pdf_box_and_images(path):
    raw = Path(path).read_bytes()
    box = [float(x) for x in re.search(rb"/MediaBox \[([^\]]*)\]", raw)[1].split()]
    return box, raw.count(b"/Subtype /Image"), raw


def chan_std(a):
    return float(a.reshape(-1, 3).std(0).max())


def build(pages_count, tmp):
    p = postprocess.process(draw("bear"))
    spec = cover.CoverSpec(8.5, 11, pages_count)
    res = cover.build_cover(spec, title="Bear Coloring Book", subtitle="For Kids Ages 4-8", author="A. Author",
                            hero=p, previews=[p, p], back_text="Fun pages.", out_pdf=tmp / "c.pdf",
                            preview_png=tmp / "p.png", palette="candy")
    return spec, res


def test_cover_pdf_exact_size_barcode_clear_spine_text():
    tmp = Path(tempfile.mkdtemp())
    for n in (30, 120):
        spec, res = build(n, tmp)
        box, n_img, raw = pdf_box_and_images(tmp / "c.pdf")
        assert abs(box[2] / 72 - spec.size_in[0]) < 0.001 and abs(box[3] / 72 - spec.size_in[1]) < 0.001
        assert n_img == 1 and b"/Font" not in raw
        # вытаскиваем JPEG обложки и проверяем растр
        jpg = raw[raw.index(b"\xff\xd8"):raw.rindex(b"\xff\xd9") + 2]
        import io
        im = np.asarray(Image.open(io.BytesIO(jpg)).convert("RGB")).astype(int)
        assert im.shape[1] == res["size_px"][0]
        bx = cover._box_px(spec.barcode)
        assert chan_std(im[bx[1]:bx[3], bx[0]:bx[2]]) < 3, "место под штрихкод должно быть пустым"
        sx = cover._box_px(spec.spine_box)
        spine = im[sx[1]:sx[3], sx[0] + 2:sx[2] - 2]
        assert (chan_std(spine) > 5) == spec.spine_text, (n, chan_std(spine))
    assert Image.open(tmp / "p.png").width <= 1800


def test_metadata_sanitize():
    meta, warn = metadata.sanitize({
        "title": "Bestseller Dino Coloring Book",
        "subtitle": "For Kids",
        "description": '<p class="x">Great <b>fun</b></p><script>alert(1)</script><a href="u">link</a> free pages',
        "keywords": ["dinosaur coloring book", "Dinosaur Coloring Book", "free coloring pages kids",
                     "a" * 30 + " " + "b" * 30, "kindle dinosaur", "", "t rex"],
        "back_text": "<b>Roar!</b> &amp; color",
    })
    assert any("title" in w and "bestseller" in w for w in warn)
    assert meta["keywords"] == ["dinosaur coloring book", "coloring pages kids", "a" * 30, "dinosaur", "t rex"]
    assert any("5 из 7" in w for w in warn)
    assert meta["description"].startswith("<p>Great <b>fun</b></p>") and "script" not in meta["description"]
    assert "<a" not in meta["description"] and any("описание" in w for w in warn)
    assert meta["back_text"] == "Roar! & color"


def test_metadata_generate_with_router():
    answer = {"title": "Dino Coloring Book", "subtitle": "For Kids Ages 4-8", "description": "Fun.",
              "keywords": [f"kw {i}" for i in range(9)], "back_text": "Roar!", "categories": ["A", "B", "C", "D"]}
    os.environ["T_KEY"] = "x"

    def handler(req):
        body = json.loads(req.content)
        assert "dinosaurs" in body["messages"][1]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer)}}]})
    r = TextRouter([{"name": "t", "base_url": "https://t.test/v1", "model": "m", "key_env": "T_KEY"}],
                   State(Path(tempfile.mkdtemp()) / "s.db"), client=httpx.Client(transport=httpx.MockTransport(handler)))
    meta, warn = metadata.generate(r, theme="dinosaurs", age="4-8", images=12)
    assert len(meta["keywords"]) == 7 and len(meta["categories"]) == 3 and not warn
    txt = metadata.to_text({**meta, "author": "X"}, warn)
    assert "AI-generated" in txt and "7. kw 6" in txt


def test_make_cover_script_offline():
    out = Path(tempfile.mkdtemp())
    text, image, _ = make_routers(["a bear", "a house"], {"bear": "bear", "house": "house"})
    pipeline.make_pages(text, image, theme="animals", count=2, out_dir=out)
    env = {**os.environ, **{k: "" for k in ("GEMINI_API_KEY", "GROQ_API_KEY", "CEREBRAS_API_KEY", "ZAI_API_KEY",
                                            "MISTRAL_API_KEY", "OPENROUTER_API_KEY", "XAI_API_KEY")}}
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "make_cover.py"), str(out), "--title", "Animals",
                        "--author", "Me"], capture_output=True, text=True, env=env, cwd=ROOT)
    assert r.returncode == 0, r.stderr[-800:]
    assert "корешок 0.009" in r.stdout  # 2 картинки → 4 страницы
    for f in ("cover.pdf", "cover_preview.png", "metadata.json", "metadata.txt"):
        assert (out / f).exists(), f
    assert "Animals" in (out / "metadata.txt").read_text()


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\nВсе {len(tests)} тестов прошли.")
