"""Роутер картинок. Каждый тип провайдера — свой метод _<type>. Любой ответ проверяется
через Pillow: если это не картинка (например, HTML с ошибкой) — провайдер считается упавшим."""
import base64
import io
import os
import random
from urllib.parse import quote

from PIL import Image

from .base import BadOutput, BaseRouter

MIN_SIDE = 512


class ImageRouter(BaseRouter):
    kind = "image"

    # --- провайдеры -------------------------------------------------------
    def _cloudflare(self, p, prompt, w, h, seed):
        acc = os.environ[p["account_env"]]
        url = f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/{p['model']}"
        body = {"prompt": prompt, "steps": p.get("steps", 8), "seed": seed}
        if p.get("send_size"):
            body.update(width=w, height=h)
        r = self.client.post(url, headers={"Authorization": f"Bearer {os.environ[p['key_env']]}"}, json=body)
        r.raise_for_status()
        if r.headers.get("content-type", "").startswith("image/"):
            return r.content
        data = r.json()
        img = (data.get("result") or {}).get("image")
        if not img:
            raise BadOutput(f"нет image в ответе: {str(data)[:200]}")
        return base64.b64decode(img)

    def _pollinations(self, p, prompt, w, h, seed):
        url = p["url_template"].format(prompt=quote(prompt, safe=""), width=w, height=h,
                                       seed=seed, model=p.get("model", "flux"))
        headers = {}
        if os.getenv(p.get("key_env", ""), ""):
            headers["Authorization"] = f"Bearer {os.environ[p['key_env']]}"
        r = self.client.get(url, headers=headers)
        r.raise_for_status()
        return r.content

    def _huggingface(self, p, prompt, w, h, seed):
        r = self.client.post(
            f"https://router.huggingface.co/hf-inference/models/{p['model']}",
            headers={"Authorization": f"Bearer {os.environ[p['key_env']]}"},
            json={"inputs": prompt, "parameters": {"width": w, "height": h, "seed": seed}},
        )
        r.raise_for_status()
        return r.content

    def _openai_images(self, p, prompt, w, h, seed):
        r = self.client.post(
            p["base_url"].rstrip("/") + "/images/generations",
            headers={"Authorization": f"Bearer {os.environ[p['key_env']]}"},
            json={"model": p["model"], "prompt": prompt, "n": 1,
                  "size": p.get("size", f"{w}x{h}"), "response_format": "b64_json"},
        )
        r.raise_for_status()
        item = r.json()["data"][0]
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])
        return self.client.get(item["url"]).content

    # --- публичный API ----------------------------------------------------
    def generate(self, prompt: str, *, width: int = 1024, height: int = 1024,
                 seed: int | None = None) -> dict:
        """Возвращает {"image": PIL.Image, "provider", "seed"}."""
        seed = seed if seed is not None else random.randint(1, 2**31 - 1)

        def call(p):
            raw = getattr(self, f"_{p['type']}")(p, prompt, width, height, seed)
            try:
                img = Image.open(io.BytesIO(raw))
                img.load()
            except Exception as e:  # noqa: BLE001
                raise BadOutput(f"не картинка ({len(raw)} байт)") from e
            if min(img.size) < MIN_SIDE:
                raise BadOutput(f"слишком маленькая картинка {img.size}")
            return img.convert("RGB")

        img, p = self._run(call)
        return {"image": img, "provider": p["name"], "seed": seed}
