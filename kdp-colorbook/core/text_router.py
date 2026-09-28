"""Текстовый роутер. Все провайдеры в конфиге — OpenAI-совместимые (/chat/completions),
включая Gemini (через его OpenAI-эндпоинт), Groq, OpenRouter, Z.AI, Mistral, Cerebras, xAI."""
import base64
import io
import json
import os
import re

from PIL import Image

from .base import BadOutput, BaseRouter

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
_DECODER = json.JSONDecoder()


class TextRouter(BaseRouter):
    kind = "text"

    def _call(self, p: dict, messages: list[dict], temperature: float, max_tokens: int,
              json_mode: bool = False) -> str:
        body = {"model": p["model"], "messages": messages,
                "temperature": temperature, "max_tokens": max_tokens}
        if json_mode and p.get("json_mode"):
            body["response_format"] = {"type": "json_object"}
        body.update(p.get("extra_body", {}))  # параметры провайдера из config.yaml (например, выключить thinking)
        r = self.client.post(
            p["base_url"].rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {os.environ[p['key_env']]}", **p.get("headers", {})},
            json=body,
        )
        r.raise_for_status()
        try:
            text = r.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise BadOutput(f"неожиданный ответ: {r.text[:200]}") from e
        if not text.strip():
            raise BadOutput("пустой ответ")
        return text.strip()

    def chat(self, prompt: str | list[dict], *, system: str | None = None,
             temperature: float = 0.7, max_tokens: int = 2000) -> dict:
        """Возвращает {"text", "provider", "model"}."""
        messages = prompt if isinstance(prompt, list) else [{"role": "user", "content": prompt}]
        if system:
            messages = [{"role": "system", "content": system}, *messages]
        text, p = self._run(lambda p: self._call(p, messages, temperature, max_tokens))
        return {"text": text, "provider": p["name"], "model": p["model"]}

    def vision_providers(self) -> list[dict]:
        """Провайдеры с vision_model в конфиге. Своё имя в состоянии: пауза vision не блокирует текст."""
        return [{**p, "name": f"{p['name']}:vision", "model": p["vision_model"]}
                for p in self.providers if p.get("vision_model")]

    @staticmethod
    def _image_part(img: Image.Image, max_side: int = 768) -> dict:
        img = img.copy()
        img.thumbnail((max_side, max_side))  # меньше токенов, для оценки раскраски детали не нужны
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "PNG", optimize=True)
        url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        return {"type": "image_url", "image_url": {"url": url}}

    def chat_json(self, prompt: str, *, system: str | None = None, images: list[Image.Image] | None = None,
                  temperature: float = 0.5, max_tokens: int = 3000) -> dict:
        """Как chat, но гарантирует валидный JSON: если провайдер вернул мусор — пробуем следующего.
        images — картинки для vision-моделей (идут только провайдеры с vision_model)."""
        sys_msg = (system + "\n\n" if system else "") + \
            "Отвечай ТОЛЬКО валидным JSON, без пояснений и без ```."
        content = prompt
        if images:
            content = [{"type": "text", "text": prompt}, *(self._image_part(i) for i in images)]
        messages = [{"role": "system", "content": sys_msg}, {"role": "user", "content": content}]

        def call(p):
            raw = self._call(p, messages, temperature, max_tokens, json_mode=True)
            cleaned = _FENCE.sub("", raw).strip()
            start = min((i for i in (cleaned.find("{"), cleaned.find("[")) if i >= 0), default=-1)
            if start < 0:
                raise BadOutput(f"нет JSON в ответе: {raw[:120]}")
            try:
                # raw_decode: текст после JSON («Надеюсь, помог!») не ломает разбор
                return _DECODER.raw_decode(cleaned[start:])[0]
            except json.JSONDecodeError as e:
                raise BadOutput(f"невалидный JSON: {e}") from e

        data, p = self._run(call, self.vision_providers() if images else None)
        return {"data": data, "provider": p["name"], "model": p["model"]}

    def list_models(self) -> dict[str, list[str] | str]:
        """Какие модели реально доступны по каждому ключу — чтобы выбрать model в config.yaml."""
        out = {}
        for p in self.providers:
            try:
                r = self.client.get(p["base_url"].rstrip("/") + "/models",
                                    headers={"Authorization": f"Bearer {os.environ[p['key_env']]}"})
                r.raise_for_status()
                out[p["name"]] = sorted(m["id"] for m in r.json().get("data", []))
            except Exception as e:  # noqa: BLE001
                out[p["name"]] = f"ошибка: {e}"
        return out
