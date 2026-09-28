"""Офлайн-тесты профилей аудитории, форматов и фильтра опасных тем: python tests/test_profiles_safety.py"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import State, TextRouter, book, cover, metadata, pipeline, postprocess, profiles, quality, safety  # noqa: E402

os.environ["T_KEY"] = "x"


def mandala():
    im = Image.new("L", (1024, 1024), 255)
    d = ImageDraw.Draw(im)
    c = 512
    for r in range(60, 480, 42):
        d.ellipse((c - r, c - r, c + r, c + r), outline=0, width=4)
    for k in range(36):
        a = 2 * math.pi * k / 36
        d.line((c + 60 * math.cos(a), c + 60 * math.sin(a), c + 480 * math.cos(a), c + 480 * math.sin(a)),
               fill=0, width=4)
    return im.convert("RGB")


def router(answer_fn, calls=None):
    def handler(req):
        body = json.loads(req.content)
        if calls is not None:
            calls.append(body)
        ans = answer_fn(body)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(ans)}}]})
    return TextRouter([{"name": "t", "base_url": "https://t.test/v1", "model": "m", "key_env": "T_KEY"}],
                      State(Path(tempfile.mkdtemp()) / "s.db"),
                      client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_detect_audience():
    assert profiles.detect("floral mandala coloring book for adults") == "adults"
    assert profiles.detect("Stress Relief Ocean Animals") == "adults"
    assert profiles.detect("coloring book for women") == "adults"
    assert profiles.detect("dinosaur coloring book for kids ages 4-8") == "kids"
    assert profiles.detect("cute farm animals for toddlers") == "kids"


def test_resolve_priority():
    cfg = {"quality": {"max_regions": 150, "min_ink": 0.03}, "postprocess": {"smooth": 1.0, "upscale": 2},
           "profiles": {"adults": {"quality": {"max_regions": 9000}}}}
    prof, pp, lim = pipeline.resolve(cfg, "adults")
    assert lim.max_regions == 9000          # config profiles.adults — сильнее всего
    assert lim.max_ink == 0.45              # из встроенного профиля
    assert lim.min_ink == 0.04              # профиль сильнее общей секции
    assert pp == {"smooth": 0.9, "upscale": 2}
    _, _, kids = pipeline.resolve(cfg, "kids")
    assert kids.max_regions == 150 and kids.min_ink == 0.03


def test_mandala_adult_ok_kids_rejected():
    img = mandala()
    ink = postprocess.binarize(img)
    _, _, kids = pipeline.resolve({}, "kids")
    _, _, adults = pipeline.resolve({}, "adults")
    assert not quality.evaluate(img, ink, lim=kids).ok
    assert quality.evaluate(img, ink, lim=adults).ok


def test_blocklist():
    assert safety.blocked_terms("Pokemon Coloring Book") == ["pokemon"]
    assert safety.blocked_terms("Bluey & Bingo fun") == ["bluey"]
    assert safety.blocked_terms("swear word coloring book") == ["swear"]
    for ok in ("frozen treats", "bloodhound puppies", "cross stitch flowers", "cute dinosaurs", "mandalas"):
        assert safety.blocked_terms(ok) == [], ok
    safety.configure({"extra_terms": ["unicorn academy"]})
    assert safety.blocked_terms("Unicorn Academy girls") == ["unicorn academy"]
    safety.configure(None)
    assert safety.blocked_terms("Unicorn Academy girls") == []


def test_moderation_llm_and_fail_closed():
    def ans(body):
        items = [ln[2:] for ln in body["messages"][1]["content"].splitlines() if ln.startswith("- ")
                 and ("dino" in ln or "Wednesday" in ln or "otters" in ln)]
        return {"results": [{"item": i, "safe": "Wednesday" not in i, "reason": "TV character"} for i in items
                            if "otters" not in i]}  # про выдр модель «забыла» ответить
    rej = safety.moderate(["cute dino friends", "Wednesday-style gothic girl", "Minecraft world",
                           "sleepy otters"], router(ans))
    assert "cute dino friends" not in rej
    assert rej["Wednesday-style gothic girl"].startswith("модерация")
    assert rej["Minecraft world"].startswith("запрещённые слова")
    assert rej["sleepy otters"] == "модель не дала вердикт"
    # модель недоступна → всё отклоняем (fail-closed)
    empty = TextRouter([], State(Path(tempfile.mkdtemp()) / "s.db"))
    assert safety.moderate(["cute dino"], empty) == {"cute dino": "модерация недоступна"}
    assert safety.moderate(["cute dino"], empty, required=False) == {}


def test_subjects_drop_brands_and_use_profile():
    calls = []
    r = router(lambda b: {"subjects": ["a fox in a forest", "Pikachu surfing", "an owl mandala"]}, calls)
    subs = pipeline.plan_subjects(r, "animals", 3, "", profiles.get("adults"))
    assert subs == ["a fox in a forest", "an owl mandala"]
    prompt = calls[0]["messages"][1]["content"]
    assert "adults" in prompt and "mandala" in prompt


def test_metadata_brands_flagged():
    meta, warn = metadata.sanitize({"title": "Paw Patrol Coloring Book", "subtitle": "Fun",
                                    "description": "Great pages", "keywords": ["pokemon pages", "cute puppies"]})
    assert meta["unsafe"] == ["title: paw patrol"]
    assert meta["keywords"] == ["cute puppies"]
    ok, _ = metadata.sanitize({"title": "Cute Puppies Coloring Book", "keywords": ["puppies"]})
    assert ok["unsafe"] == []


def test_metadata_prompt_uses_audience():
    calls = []
    r = router(lambda b: {"title": "Floral Mandalas", "keywords": []}, calls)
    metadata.generate(r, theme="floral mandalas", age="", images=40, audience="adults")
    p = calls[0]["messages"][1]["content"]
    assert "adults (relaxation" in p and "Stress Relief" in p


def test_trims():
    assert book.parse_trim("8.5x8.5") == (8.5, 8.5) and book.parse_trim([8.5, 11]) == (8.5, 11.0)
    assert book.trim_name((8.5, 11.0)) == "8.5x11"
    try:
        book.parse_trim("5x5")
        raise AssertionError("должно было упасть")
    except ValueError:
        pass
    page = postprocess.process(mandala())
    out = Path(tempfile.mkdtemp())
    book.build_interior([page] * 12, out / "i.pdf", trim=book.parse_trim("6x9"))
    raw = (out / "i.pdf").read_bytes()
    assert b"/MediaBox [0 0 432.000 648.000]" in raw
    spec = cover.CoverSpec(8.5, 8.5, 24)
    assert abs(spec.size_in[1] - 8.75) < 1e-9


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\nВсе {len(tests)} тестов прошли.")
