"""Офлайн-тест робота KDP на макете (tests/kdp_mock.py): python tests/test_kdp.py
Нужен playwright и Chromium; путь к браузеру — KDP_TEST_BROWSER (по умолчанию /opt/pw-browsers/chromium,
иначе браузер playwright по умолчанию)."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import kdp_mock  # noqa: E402
from core import kdp  # noqa: E402

SRV, BASE = kdp_mock.start()
META = {"title": "Cute Axolotl Coloring Book", "subtitle": "For Kids Ages 4-8", "author": "Anna Green",
        "description": "<p>Fun <b>axolotl</b> pages.</p>", "keywords": [f"axolotl kw {i}" for i in range(7)]}
CATS = [["Children's Books", "Activities, Crafts & Games", "Coloring Books"]]


def cfg(tmp):
    c = {"base_url": BASE, "headless": True, "slow_mo_ms": 0, "timeout_s": 5, "processing_timeout_s": 5, "profile_dir": str(tmp / "profile"),
         "price_usd": 7.99}
    path = os.getenv("KDP_TEST_BROWSER", "/opt/pw-browsers/chromium")
    if Path(path).exists():
        c["browser_path"] = path
    return c


def book(tmp):
    d = tmp / "book"
    d.mkdir()
    (d / "interior.pdf").write_bytes(b"%PDF-1.4 test")
    (d / "cover.pdf").write_bytes(b"%PDF-1.4 cover")
    return d


def reset(**kw):
    kdp_mock.STATE.update({"saves": {"details": 0, "content": 0, "pricing": 0}, "data": {},
                           "login_challenge": False, "break_cover": False, **kw})


def upload(tmp, d, publish=True):
    with kdp.KdpUploader(cfg(tmp)) as up:
        return up.upload(d, meta=META, interior=d / "interior.pdf", cover=d / "cover.pdf", trim=(8.5, 8.5),
                         pages=60, categories=CATS, publish=publish)


def test_full_publish():
    reset()
    tmp = Path(tempfile.mkdtemp())
    d = book(tmp)
    st = upload(tmp, d)
    assert st["result"] == "published" and st["title_id"] == "T123" and st["price"] == 7.99
    data = kdp_mock.STATE["data"]
    det = data["details"]
    assert det["title"] == META["title"] and det["first"] == "Anna" and det["last"] == "Green"
    assert det["keywords"] == META["keywords"] and "<b>axolotl</b>" in det["description"]
    assert det["category"] == "Children's Books>Activities, Crafts & Games>Coloring Books"
    con = data["content"]
    assert con["trim"] == "8.5x8.5" and con["ink"] == "bw-white" and con["bleed"] == "no" and con["finish"] == "matte"
    assert con["interior"] == "interior.pdf" and con["cover"] == "cover.pdf" and con["approved"] == 1
    assert con["ai"] == "yes" and con["ai_images"] == "Entire work, with minimal or no editing" and con["ai_tool"]
    assert data["pricing"] == {"price": "7.99", "kind": "publish"}
    # повторный запуск ничего не делает
    assert upload(tmp, d)["result"] == "published" and kdp_mock.STATE["saves"]["pricing"] == 1


def test_resume_after_failure_with_debug():
    reset(break_cover=True)
    tmp = Path(tempfile.mkdtemp())
    d = book(tmp)
    try:
        upload(tmp, d)
        raise AssertionError("должно было упасть на обложке")
    except kdp.KdpError as e:
        assert e.step == "content" and e.debug and e.debug.exists() and e.debug.with_suffix(".html").exists()
    assert kdp_mock.STATE["saves"]["details"] == 1
    kdp_mock.STATE["break_cover"] = False
    st = upload(tmp, d)
    assert st["result"] == "published"
    assert kdp_mock.STATE["saves"] == {"details": 1, "content": 1, "pricing": 1}  # детали не повторялись


def test_login_challenge_needs_human():
    reset(login_challenge=True)
    tmp = Path(tempfile.mkdtemp())
    try:
        upload(tmp, book(tmp))
        raise AssertionError("нужен человек")
    except kdp.NeedsHuman as e:
        assert "kdp_login" in str(e)


def test_draft_mode_and_price():
    reset()
    tmp = Path(tempfile.mkdtemp())
    assert upload(tmp, book(tmp), publish=False)["result"] == "draft"
    assert kdp_mock.STATE["data"]["pricing"]["kind"] == "draft"
    assert kdp.choose_price(200, 5.0) == 6.99 and kdp.choose_price(24, 7.99) == 7.99


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\nВсе {len(tests)} тестов прошли.")
