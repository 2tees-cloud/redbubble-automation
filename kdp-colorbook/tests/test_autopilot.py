"""Офлайн-тест автопилота целиком (всё внешнее подменено): python tests/test_autopilot.py"""
import datetime as dt
import io
import json
import os
import sys
import tempfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from core import ImageRouter, State, TextRouter, autopilot, kdp, notify, research  # noqa: E402
from test_quality import draw, png  # noqa: E402
from test_research import amazon_mock  # noqa: E402

for k in ("T_KEY", "CF_TOKEN", "CF_ACC"):
    os.environ[k] = "x"
SENT = []
ORIG_SEND = notify.send
notify.send = lambda title, text, **kw: SENT.append((title, text)) or []
KINDS = ["bear", "house"]


def text_router(meta_title="Cute Axolotl Coloring Book"):
    def handler(req):
        body = json.loads(req.content)
        msgs = body["messages"]
        user = msgs[1]["content"]
        if isinstance(user, list):  # vision
            ans = {"score": 9, "is_line_art": True, "has_text": False, "anatomy_errors": False,
                   "cut_off": False, "matches_subject": True}
        elif "research Amazon KDP" in user:
            ans = {"phrases": ["axolotl coloring book"]}
        elif "Plan a coloring book" in user:
            ans = {"theme": "cute axolotls", "audience": "kids", "age": "4-8", "trim": "8.5x11", "pages": 30}
        elif "You check themes" in user:
            items = [ln[2:] for ln in user.splitlines() if ln.startswith("- ")]
            ans = {"results": [{"item": i, "safe": True} for i in items]}
        elif "Invent" in user:
            ans = {"subjects": [f"axolotl scene {i}" for i in range(40)]}
        else:  # метаданные
            ans = {"title": meta_title, "subtitle": "For Kids Ages 4-8", "description": "<p>Fun</p>",
                   "keywords": [f"axolotl {i}" for i in range(7)], "back_text": "Fun!"}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(ans)}}]})
    return TextRouter([{"name": "t", "base_url": "https://t.test/v1", "model": "m", "vision_model": "v",
                        "key_env": "T_KEY"}], State(Path(tempfile.mkdtemp()) / "s.db"),
                      client=httpx.Client(transport=httpx.MockTransport(handler)))


def image_router(fail_after=None):
    n = {"i": 0}

    def handler(req):
        n["i"] += 1
        if fail_after is not None and n["i"] > fail_after:
            return httpx.Response(429, text="limit")
        # разные рисунки, чтобы дубликаты не отсеивали всё: сдвиг по номеру
        import numpy as np
        from PIL import Image
        base = np.asarray(draw(KINDS[n["i"] % 2]))
        img = Image.fromarray(np.roll(base, (n["i"] * 97) % 400 - 200, axis=0 if n["i"] % 4 < 2 else 1))
        return httpx.Response(200, content=png(img), headers={"content-type": "image/png"})
    return ImageRouter([{"name": "cf", "type": "cloudflare", "model": "@cf/x", "key_env": "CF_TOKEN",
                         "account_env": "CF_ACC"}], State(Path(tempfile.mkdtemp()) / "s.db"),
                       client=httpx.Client(transport=httpx.MockTransport(handler)))


class FakeUploader:
    calls = []
    fail = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def upload(self, book_dir, **kw):
        FakeUploader.calls.append(kw)
        if FakeUploader.fail:
            raise FakeUploader.fail
        assert Path(kw["interior"]).exists() and Path(kw["cover"]).exists()
        return {"result": "published" if kw["publish"] else "draft", "price": 7.99}


CFG = {"autopilot": {"author": "Anna Green", "min_images": 6},
       "research": {"seeds": ["coloring book for kids"], "alphabet": "", "llm_ideas": 5, "evaluate_top": 3,
                    "bsr_top": 1, "min_pages": 8, "max_pages": 8},
       "kdp": {"publish": True, "first_run_draft": True,
               "categories": {"kids": [["Children's Books", "Activities, Crafts & Games", "Coloring Books"]]}}}


def pilot(tmp, day, text=None, image=None):
    amazon = research.AmazonClient(tmp / "cache", delay=(0, 0), suggest_delay=(0, 0), client=amazon_mock())
    return autopilot.Autopilot(CFG, text or text_router(), image or image_router(), data_dir=tmp / "data",
                               out_dir=tmp / "out", amazon=amazon, uploader_factory=FakeUploader, today=day)


def test_full_day_then_second_day_publishes():
    FakeUploader.calls, FakeUploader.fail, SENT[:] = [], None, []
    tmp = Path(tempfile.mkdtemp())
    run = pilot(tmp, dt.date(2026, 9, 28)).run()
    assert run["status"] == "done", run.data
    assert FakeUploader.calls[0]["publish"] is False               # первая книга — черновиком
    assert FakeUploader.calls[0]["categories"][0][-1] == "Coloring Books"
    book = Path(run["book_dir"])
    for f in ("interior.pdf", "cover.pdf", "cover_preview.png", "metadata.txt", "manifest.json"):
        assert (book / f).exists(), f
    hist = json.loads((tmp / "data" / "history.json").read_text())
    assert hist[0]["kdp"] == "draft" and hist[0]["title"] == "Cute Axolotl Coloring Book"
    assert "ЧЕРНОВИКОМ" in SENT[-1][1]
    # тот же день — ничего не делаем
    assert pilot(tmp, dt.date(2026, 9, 28)).run() is None
    # следующий день — новая книга, уже публикуется; прошлая ниша не повторяется
    run2 = pilot(tmp, dt.date(2026, 9, 29)).run()
    assert run2["status"] == "done" and FakeUploader.calls[-1]["publish"] is True
    assert run2["plan"]["phrase"] != run["plan"]["phrase"]


def test_limits_pause_then_resume():
    FakeUploader.calls, FakeUploader.fail = [], None
    tmp = Path(tempfile.mkdtemp())
    run = pilot(tmp, dt.date(2026, 9, 28), image=image_router(fail_after=3)).run()
    assert run["status"] == "waiting" and run["step"] == "pages" and "лимиты" in run["error"]
    # на следующий день продолжаем ту же книгу, а не начинаем новую
    run2 = pilot(tmp, dt.date(2026, 9, 29)).run()
    assert run2["id"] == run["id"] and run2["status"] == "done"


def test_needs_human_waits_and_notifies():
    FakeUploader.calls, SENT[:] = [], []
    FakeUploader.fail = kdp.NeedsHuman("login", "нужен вход")
    tmp = Path(tempfile.mkdtemp())
    run = pilot(tmp, dt.date(2026, 9, 28)).run()
    assert run["status"] == "waiting" and run["step"] == "upload"
    assert SENT[-1][0] == "KDP: нужен вход"
    FakeUploader.fail = None
    assert pilot(tmp, dt.date(2026, 9, 28)).run()["status"] == "done"


def test_upload_errors_give_up_after_limit():
    FakeUploader.fail = kdp.KdpError("content", "селектор не найден")
    tmp = Path(tempfile.mkdtemp())
    statuses = [pilot(tmp, dt.date(2026, 9, 28)).run()["status"] for _ in range(3)]
    assert statuses == ["waiting", "waiting", "failed"]
    FakeUploader.fail = None


def test_unsafe_metadata_stops_book():
    FakeUploader.fail = None
    tmp = Path(tempfile.mkdtemp())
    run = pilot(tmp, dt.date(2026, 9, 28), text=text_router("Bluey Axolotl Coloring Book")).run()
    assert run["status"] == "failed" and "небезопасны" in run["error"]


def test_lock():
    tmp = Path(tempfile.mkdtemp())
    (tmp / "data").mkdir()
    (tmp / "data" / "autopilot.lock").write_text("1")
    try:
        pilot(tmp, dt.date(2026, 9, 28)).run()
        raise AssertionError("должен быть lock")
    except RuntimeError as e:
        assert "уже работает" in str(e)


def test_notify_channels():
    got = []

    def handler(req):
        got.append((req.url.host, req.url.path, req.content.decode()))
        return httpx.Response(200)
    os.environ.update(NTFY_TOPIC="my-topic", TELEGRAM_BOT_TOKEN="tok", TELEGRAM_CHAT_ID="42")
    try:
        sent = ORIG_SEND("KDP: книга готова", "текст", client=httpx.Client(transport=httpx.MockTransport(handler)))
    finally:
        for k in ("NTFY_TOPIC", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
            os.environ.pop(k)
    assert sent == ["ntfy", "telegram"]
    assert got[0][:2] == ("ntfy.sh", "/my-topic") and "книга готова" in got[0][2]
    assert got[1][1] == "/bottok/sendMessage" and json.loads(got[1][2])["chat_id"] == "42"
    # без настроек — только лог, без ошибок
    assert ORIG_SEND("t", "x", client=httpx.Client(transport=httpx.MockTransport(handler))) == []


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\nВсе {len(tests)} тестов прошли.")
