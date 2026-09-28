"""Офлайн-тесты исследования ниш: python tests/test_research.py"""
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core import State, TextRouter, research  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
SEARCH = (FIX / "amazon_search.html").read_text()
PRODUCT = (FIX / "amazon_product.html").read_text()
CAPTCHA = (FIX / "amazon_captcha.html").read_text()
os.environ["T_KEY"] = "x"


def test_parse_search():
    r = research.parse_search(SEARCH)
    assert r["total"] == 2000
    assert [i["asin"] for i in r["items"]] == ["B0AAAAAAA1", "B0AAAAAAA2", "B0AAAAAAA3", "B0AAAAAAA4"]
    assert [i["reviews"] for i in r["items"]] == [5120, 1204, 12, 0]
    assert [i["sponsored"] for i in r["items"]] == [True, False, False, False]
    assert r["items"][1]["title"] == "Axolotl Coloring Book for Kids"


def test_parse_bsr_and_captcha():
    assert research.parse_bsr(PRODUCT) == 45210
    for fn in (research.parse_search, research.parse_bsr):
        try:
            fn(CAPTCHA)
            raise AssertionError("должна быть капча")
        except research.Blocked:
            pass


def test_score_logic():
    easy = research.score(research.Niche("axolotl coloring book", suggest_score=0.8, total=2000,
                                         top_reviews=[12, 5, 30, 400], top_bsr=[40_000, 90_000, 150_000]))
    hard = research.score(research.Niche("coloring book for kids", suggest_score=1.0, total=100_000,
                                         top_reviews=[20000, 15000, 9000, 8000], top_bsr=[300, 800, 1200]))
    dead = research.score(research.Niche("obscure coloring book", suggest_score=0.3, total=50,
                                         top_reviews=[0, 1], top_bsr=[2_000_000, 3_000_000]))
    assert easy.confidence == "high" and easy.weak_spots == 3
    assert "зайти трудно" in hard.notes[0]
    assert easy.score > hard.score, (easy.score, hard.score)   # «окно» лучше забитой ниши
    assert "спроса нет" in dead.notes[-1]
    low = research.score(research.Niche("x coloring book", suggest_score=0.6))
    assert low.confidence == "low" and low.score == 0.3


def test_seasons():
    names = [n for n, _ in research.upcoming(dt.date(2026, 9, 28))]
    assert names == ["Halloween", "Thanksgiving"]
    assert research._easter(2026) == dt.date(2026, 4, 5)
    assert [n for n, _ in research.upcoming(dt.date(2026, 12, 10))] == ["Valentine's Day"]


def test_candidate_filter_and_similarity():
    assert research.is_candidate("axolotl coloring book for kids")
    assert not research.is_candidate("axolotl plush toy")
    assert not research.is_candidate("pokemon coloring book")
    assert not research.is_candidate("coloring book for kids ages 4-8")   # нет темы — слишком широко
    assert research.similar("cute axolotl coloring book", "axolotl coloring book for kids") > 0.4
    assert research.similar("farm animals coloring book", "space coloring book for adults") == 0


def amazon_mock(blocked=False):
    def handler(req: httpx.Request):
        url = str(req.url)
        if "completion.amazon.com" in url:
            prefix = parse_qs(urlparse(url).query)["prefix"][0]
            sug = {"coloring book for kids": ["coloring book for kids ages 4-8", "coloring book for kids axolotl"],
                   "axolotl coloring book": ["axolotl coloring book", "axolotl coloring book for kids"],
                   "halloween coloring book": ["halloween coloring book for kids", "halloween coloring book"]}
            vals = sug.get(prefix, [])
            return httpx.Response(200, json={"suggestions": [{"value": v} for v in vals]})
        if blocked:
            return httpx.Response(200, text=CAPTCHA)
        if "/dp/" in url:
            return httpx.Response(200, text=PRODUCT)
        return httpx.Response(200, text=SEARCH)
    return httpx.Client(transport=httpx.MockTransport(handler))


def text_mock(unsafe=()):
    def handler(req):
        body = json.loads(req.content)
        p = body["messages"][1]["content"]
        if "research Amazon KDP" in p:
            ans = {"phrases": ["axolotl coloring book", "bluey coloring book"]}
        elif "Plan a coloring book" in p:
            ans = {"theme": "cute axolotls", "audience": "kids", "age": "4-8", "trim": "8.5x8.5", "pages": 99}
        else:  # модерация
            items = [ln[2:] for ln in p.splitlines() if ln.startswith("- ")]
            ans = {"results": [{"item": i, "safe": i not in unsafe, "reason": "x"} for i in items]}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(ans)}}]})
    return TextRouter([{"name": "t", "base_url": "https://t.test/v1", "model": "m", "key_env": "T_KEY"}],
                      State(Path(tempfile.mkdtemp()) / "s.db"), client=httpx.Client(transport=httpx.MockTransport(handler)))


def run(blocked=False, unsafe=(), history_items=()):
    tmp = Path(tempfile.mkdtemp())
    amazon = research.AmazonClient(tmp / "cache", delay=(0, 0), suggest_delay=(0, 0), client=amazon_mock(blocked))
    hist = research.History(tmp / "history.json")
    for h in history_items:
        hist.add(phrase=h)
    rc = research.ResearchConfig(seeds=["coloring book for kids"], alphabet="", evaluate_top=5, bsr_top=2)
    plan, short = research.research(amazon=amazon, text_router=text_mock(unsafe), history=hist, rc=rc,
                                    report_dir=tmp / "reports", today=dt.date(2026, 9, 28))
    report = json.loads((tmp / "reports" / "2026-09-28.json").read_text())
    return plan, short, report


def test_research_end_to_end():
    plan, short, report = run()
    phrases = [n.phrase for n in short]
    assert "bluey coloring book" not in phrases                      # бренд отсеян ещё до оценки
    assert "halloween coloring book for kids" in phrases              # сезонные семена в деле
    hw = next(n for n in short if n.phrase == "halloween coloring book for kids")
    assert hw.season == "Halloween"
    assert all(n.confidence == "high" and n.top_bsr == [45210, 45210] for n in short)
    assert plan["trim"] == "8.5x8.5" and plan["pages"] == 50 and plan["audience"] == "kids"
    assert plan["phrase"] == short[0].phrase and report["chosen"]["phrase"] == plan["phrase"]
    assert report["season"] == ["Halloween", "Thanksgiving"]


def test_research_blocked_amazon_still_chooses():
    plan, short, report = run(blocked=True)
    assert report["amazon_blocked"] is True
    assert plan is not None and all(n.confidence == "low" for n in short)


def test_research_skips_unsafe_and_recent():
    first, _, _ = run()
    plan, short, _ = run(unsafe=(first["phrase"],), history_items=["halloween coloring book"])
    assert plan["phrase"] != first["phrase"]
    assert not any(n.phrase.startswith("halloween coloring book") for n in short)


def test_keepa_parsing():
    def handler(req):
        assert req.url.params["term"] == "axolotl coloring book" and req.url.params["key"] == "k"
        cur = [-1] * 20
        cur[3], cur[17] = 12345, 42
        return httpx.Response(200, json={"products": [{"asin": "B01", "title": "T", "stats": {"current": cur}},
                                                      {"asin": "B02", "title": "U", "stats": {"current": [-1] * 20}}]})
    k = research.KeepaClient("k", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert k.search("axolotl coloring book") == [{"asin": "B01", "title": "T", "reviews": 42, "bsr": 12345},
                                                 {"asin": "B02", "title": "U", "reviews": 0, "bsr": None}]


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\nВсе {len(tests)} тестов прошли.")
