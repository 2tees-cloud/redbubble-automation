"""Офлайн-тесты фильтра брака и конвейера: python tests/test_quality.py"""
import io
import json
import os
import sys
import tempfile
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import AllProvidersFailed, ImageRouter, State, TextRouter, pipeline, postprocess, quality  # noqa: E402

for k in ("T_KEY", "CF_TOKEN", "CF_ACC"):
    os.environ[k] = "x"
W = dict(outline=0, width=12)


def draw(kind: str) -> Image.Image:
    im = Image.new("L", (1024, 1024), 255)
    d = ImageDraw.Draw(im)
    if kind == "bear":
        d.ellipse((250, 290, 770, 770), **W)
        d.ellipse((420, 160, 640, 360), **W)
        d.ellipse((800, 40, 960, 200), **W)
        for i in range(4):
            d.ellipse((340 + i * 90, 450, 400 + i * 90, 510), **W)
    elif kind == "house":
        d.rectangle((250, 450, 770, 900), **W)
        d.polygon([(200, 450), (512, 150), (820, 450)], **W)
        d.rectangle((450, 650, 570, 900), **W)
        d.rectangle((300, 520, 400, 620), **W)
        d.rectangle((620, 520, 720, 620), **W)
    elif kind == "blob":
        d.ellipse((250, 250, 770, 770), fill=0)
    elif kind == "grid":
        for x in range(0, 1024, 24):
            d.line((x, 0, x, 1023), fill=0, width=3)
            d.line((0, x, 1023, x), fill=0, width=3)
    return im.convert("RGB")


def verdict(kind, **kw):
    img = draw(kind)
    return quality.evaluate(img, postprocess.binarize(img), **kw)


def test_pixel_checks():
    assert verdict("bear").ok
    assert verdict("house").ok
    v = verdict("empty")
    assert not v.ok and "почти пусто" in v.reasons[0]
    v = verdict("blob")
    assert not v.ok and any("заливка" in r for r in v.reasons), v.reasons
    v = verdict("grid")
    assert not v.ok and any("мелкие детали" in r for r in v.reasons), v.reasons


def test_duplicates():
    dd = quality.Deduper(10)
    a = verdict("bear", deduper=dd)
    dd.add(a.metrics["phash"], "bear")
    assert verdict("house", deduper=dd).ok
    shifted = Image.fromarray(__import__("numpy").roll(__import__("numpy").asarray(draw("bear")), 20, axis=1))
    v = quality.evaluate(shifted, postprocess.binarize(shifted), deduper=dd)
    assert not v.ok and v.reasons == ["дубликат bear"]


def vision_router(answer, calls, state=None):
    def handler(req):
        body = json.loads(req.content)
        calls.append(body)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer)}}]})
    provs = [{"name": "t", "base_url": "https://t.test/v1", "model": "text-m", "vision_model": "vis-m",
              "key_env": "T_KEY"}]
    return TextRouter(provs, state or State(Path(tempfile.mkdtemp()) / "s.db"),
                      client=httpx.Client(transport=httpx.MockTransport(handler)))


GOOD = {"score": 9, "is_line_art": True, "has_text": False, "anatomy_errors": False,
        "cut_off": False, "matches_subject": True, "issues": []}


def test_vision_request_and_accept():
    calls = []
    v = verdict("bear", subject="a bear", text_router=vision_router(GOOD, calls))
    assert v.ok, v.reasons
    body = calls[0]
    assert body["model"] == "vis-m"
    parts = body["messages"][1]["content"]
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert "a bear" in parts[0]["text"]


def test_vision_rejects():
    v = verdict("bear", text_router=vision_router({**GOOD, "anatomy_errors": True, "issues": ["5 legs"]}, []))
    assert not v.ok and "vision: anatomy_errors" in v.reasons and "5 legs" in v.reasons[-1]
    v = verdict("bear", text_router=vision_router({**GOOD, "score": 4}, []))
    assert not v.ok and "оценка 4" in v.reasons[0]


def test_vision_unavailable():
    r = TextRouter([{"name": "t", "base_url": "https://t.test/v1", "model": "m", "key_env": "T_KEY"}],
                   State(Path(tempfile.mkdtemp()) / "s.db"), client=httpx.Client())
    assert verdict("bear", text_router=r).ok                        # нет vision_model → пропускаем
    v = verdict("bear", text_router=r, lim=quality.Limits(vision_required=True))
    assert not v.ok and v.reasons == ["vision недоступен"]


def test_vision_cooldown_separate_from_text():
    st = State(Path(tempfile.mkdtemp()) / "s.db")
    r = vision_router(GOOD, [], st)
    r.chat_json("x", images=[draw("bear")])
    assert {row["name"] for row in st.report()} == {"t:vision"}


def png(im):
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def make_routers(subjects, image_for, fail_after=None):
    """Мок: текст отдаёт сюжеты / вердикт vision, картинки рисуются по слову в промпте."""
    counter = {"img": 0, "plan": 0}

    def text_handler(req):
        body = json.loads(req.content)
        if isinstance(body["messages"][1]["content"], list):
            ans = GOOD
        else:
            counter["plan"] += 1
            ans = {"subjects": subjects}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(ans)}}]})

    def image_handler(req):
        counter["img"] += 1
        if fail_after is not None and counter["img"] > fail_after:
            return httpx.Response(429, text="daily limit")
        prompt = json.loads(req.content)["prompt"]
        kind = next(v for k, v in image_for.items() if k in prompt)
        return httpx.Response(200, content=png(draw(kind)), headers={"content-type": "image/png"})

    st = State(Path(tempfile.mkdtemp()) / "s.db")
    text = TextRouter([{"name": "t", "base_url": "https://t.test/v1", "model": "m", "vision_model": "v",
                        "key_env": "T_KEY"}], st, client=httpx.Client(transport=httpx.MockTransport(text_handler)))
    image = ImageRouter([{"name": "cf", "type": "cloudflare", "model": "@cf/x", "key_env": "CF_TOKEN",
                          "account_env": "CF_ACC"}], st,
                        client=httpx.Client(transport=httpx.MockTransport(image_handler)))
    return text, image, counter


def test_pipeline_filters_and_resumes():
    out = Path(tempfile.mkdtemp())
    subjects = ["a bear", "a bear twin", "a black blob", "a house"]
    kinds = {"bear twin": "bear", "bear": "bear", "blob": "blob", "house": "house"}

    # первый запуск: после 1 картинки лимит кончился
    text, image, c = make_routers(subjects, kinds, fail_after=1)
    try:
        pipeline.make_pages(text, image, theme="animals", count=2, out_dir=out, attempts=2)
        raise AssertionError("должно было упасть")
    except AllProvidersFailed:
        pass
    d = json.loads((out / "manifest.json").read_text())
    assert [a["subject"] for a in d["accepted"]] == ["a bear"]

    # второй запуск той же командой: продолжает, сюжеты заново не придумывает
    text, image, c = make_routers(["other"], kinds)
    d = pipeline.make_pages(text, image, theme="animals", count=2, out_dir=out, attempts=2)
    assert c["plan"] == 0
    assert [a["subject"] for a in d["accepted"]] == ["a bear", "a house"]
    reasons = {r["subject"]: r["reasons"][0] for r in d["rejected"]}
    assert reasons["a bear twin"].startswith("дубликат")
    assert "заливка" in reasons["a black blob"] or "областей" in reasons["a black blob"]
    assert sum(r["subject"] == "a bear twin" for r in d["rejected"]) == 2   # attempts=2
    assert len(list((out / "pages").glob("*.png"))) == 2 and len(list((out / "pages").glob("*.svg"))) == 2
    assert len(list((out / "rejected").glob("*.png"))) == 4
    assert len(pipeline.load_vectors(out)) == 2


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\nВсе {len(tests)} тестов прошли.")
