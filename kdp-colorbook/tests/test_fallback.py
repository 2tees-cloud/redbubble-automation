"""Офлайн-тесты переключения провайдеров (без сети и ключей): python tests/test_fallback.py"""
import base64
import io
import os
import sys
import tempfile
from pathlib import Path

import httpx
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import AllProvidersFailed, ImageRouter, State, TextRouter  # noqa: E402

for k in ("A_KEY", "B_KEY", "C_KEY", "CF_TOKEN", "CF_ACC", "HF_KEY"):
    os.environ[k] = "x"


def text_providers():
    return [{"name": n, "base_url": f"https://{n}.test/v1", "model": "m", "key_env": f"{n.upper()}_KEY"}
            for n in ("a", "b", "c")]


def ok_chat(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def png_bytes(size=1024):
    buf = io.BytesIO()
    Image.new("RGB", (size, size), "white").save(buf, "PNG")
    return buf.getvalue()


def new_state():
    return State(Path(tempfile.mkdtemp()) / "s.db")


def test_text_fallback_and_cooldown():
    calls = []

    def handler(req):
        host = req.url.host.split(".")[0]
        calls.append(host)
        if host == "a":
            return httpx.Response(429, headers={"retry-after": "120"}, text="rate limited")
        if host == "b":
            return httpx.Response(500, text="boom")
        return ok_chat("привет")

    st = new_state()
    r = TextRouter(text_providers(), st, client=httpx.Client(transport=httpx.MockTransport(handler)))
    res = r.chat("hi")
    assert res["provider"] == "c" and res["text"] == "привет", res
    assert calls == ["a", "b", "c"]
    # a и b на паузе → второй запрос сразу идёт в c
    calls.clear()
    r.chat("hi again")
    assert calls == ["c"], calls
    assert 100 < st.cooldown_left("a") <= 120


def test_json_bad_output_falls_through():
    def handler(req):
        host = req.url.host.split(".")[0]
        if host == "a":
            return ok_chat("Конечно! Вот ответ без json")
        return ok_chat('```json\n{"themes": [1, 2]}\n```')

    r = TextRouter(text_providers(), new_state(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    res = r.chat_json("x")
    assert res["provider"] == "b" and res["data"] == {"themes": [1, 2]}


def test_all_fail():
    r = TextRouter(text_providers(), new_state(),
                   client=httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(401))))
    try:
        r.chat("x")
        raise AssertionError("должно было упасть")
    except AllProvidersFailed as e:
        assert "HTTP 401" in str(e)


def test_missing_key_skipped():
    provs = text_providers() + [{"name": "nokey", "base_url": "https://n.test", "model": "m",
                                 "key_env": "DEFINITELY_NOT_SET"}]
    r = TextRouter(provs, new_state(), client=httpx.Client())
    assert [p["name"] for p in r.providers] == ["a", "b", "c"]


def test_image_fallback_html_then_cloudflare_b64():
    def handler(req):
        if "huggingface" in req.url.host:
            return httpx.Response(200, text="<html>error page</html>")  # 200, но не картинка
        return httpx.Response(200, json={"result": {"image": base64.b64encode(png_bytes()).decode()}})

    provs = [
        {"name": "hf", "type": "huggingface", "model": "x/y", "key_env": "HF_KEY"},
        {"name": "cf", "type": "cloudflare", "model": "@cf/x", "key_env": "CF_TOKEN", "account_env": "CF_ACC"},
    ]
    st = new_state()
    r = ImageRouter(provs, st, client=httpx.Client(transport=httpx.MockTransport(handler)))
    res = r.generate("dino")
    assert res["provider"] == "cf" and res["image"].size == (1024, 1024)
    assert st.cooldown_left("hf") > 0


def test_image_too_small_rejected():
    def handler(req):
        if "pollinations" in req.url.host:
            return httpx.Response(200, content=png_bytes(128))
        return httpx.Response(200, content=png_bytes(1024))

    provs = [
        {"name": "pol", "type": "pollinations", "key_optional": True, "key_env": "NOPE",
         "url_template": "https://image.pollinations.ai/prompt/{prompt}?w={width}&h={height}&s={seed}&m={model}"},
        {"name": "hf", "type": "huggingface", "model": "x/y", "key_env": "HF_KEY"},
    ]
    r = ImageRouter(provs, new_state(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert r.generate("cat")["provider"] == "hf"


def test_json_trailing_text_and_json_mode():
    bodies = []

    def handler(req):
        import json as _j
        bodies.append(_j.loads(req.content))
        return ok_chat('{"themes": ["a"]}\n\nНадеюсь, это поможет!')

    provs = text_providers()[:1]
    provs[0].update(json_mode=True, extra_body={"reasoning_effort": "none"})
    r = TextRouter(provs, new_state(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert r.chat_json("x")["data"] == {"themes": ["a"]}
    assert bodies[0]["response_format"] == {"type": "json_object"}
    assert bodies[0]["reasoning_effort"] == "none"
    r.chat("x")  # обычный chat не просит JSON-режим
    assert "response_format" not in bodies[1] and bodies[1]["reasoning_effort"] == "none"


def test_auth_cooldown_is_full_day():
    st = new_state()
    assert st.failure("a", "auth", "401") == 24 * 3600
    assert st.failure("b", "rate", "429", retry_after=10 ** 6) == 12 * 3600


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\nВсе {len(tests)} тестов прошли.")
