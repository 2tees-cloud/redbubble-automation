"""Общая логика перебора провайдеров: пропуск тех, кто на паузе, классификация ошибок, fallback."""
import logging
import os
from typing import Any, Callable

import httpx

from .state import State

log = logging.getLogger("router")


class BadOutput(Exception):
    """Провайдер ответил 200, но результат непригоден (пусто, битая картинка, не JSON)."""


class AllProvidersFailed(RuntimeError):
    pass


def classify(exc: Exception) -> tuple[str, float | None]:
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        ra = exc.response.headers.get("retry-after", "")
        retry = float(ra) if ra.replace(".", "", 1).isdigit() else None
        if code == 429:
            return "rate", retry
        if code == 402:
            return "quota", None
        if code in (401, 403):
            return "auth", None
        if code >= 500:
            return "server", retry
        return "bad_request", None
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return "server", None
    return "bad_output", None


def short_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
    return f"{type(exc).__name__}: {exc}"[:300]


class BaseRouter:
    kind = "base"

    def __init__(self, providers: list[dict], state: State, client: httpx.Client | None = None,
                 timeout: float = 120):
        self.state = state
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=True)
        self.providers = []
        for p in providers:
            if not p.get("enabled", True):
                continue
            missing = [os.getenv(e) is None or os.getenv(e) == "" for e in self._required_env(p)]
            if any(missing):
                log.info("[%s] %s пропущен: нет ключа в .env", self.kind, p["name"])
                continue
            self.providers.append(p)
        if not self.providers:
            log.warning("[%s] нет ни одного провайдера с ключами", self.kind)

    @staticmethod
    def _required_env(p: dict) -> list[str]:
        return [v for k, v in p.items() if k.endswith("_env") and not p.get("key_optional")]

    def _run(self, call: Callable[[dict], Any], providers: list[dict] | None = None) -> tuple[Any, dict]:
        providers = self.providers if providers is None else providers
        if not providers:
            raise AllProvidersFailed(f"[{self.kind}] нет ни одного подходящего провайдера с ключом — заполните .env")
        errors = []
        for p in providers:
            name = p["name"]
            left = self.state.cooldown_left(name)
            if left > 0:
                errors.append(f"{name}: на паузе ещё {int(left)} с")
                continue
            try:
                result = call(p)
                self.state.success(name)
                return result, p
            except Exception as exc:  # noqa: BLE001 — любой сбой = переход к следующему
                kind, retry = classify(exc)
                detail = short_error(exc)
                delay = self.state.failure(name, kind, detail, retry)
                log.warning("[%s] %s упал (%s), пауза %d с → следующий", self.kind, name, detail, delay)
                errors.append(f"{name}: {detail}")
        raise AllProvidersFailed(f"[{self.kind}] все провайдеры недоступны:\n  " + "\n  ".join(errors))
