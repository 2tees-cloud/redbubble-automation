"""Уведомления автопилота на телефон: ntfy.sh (бесплатно, без регистрации) и/или Telegram.

.env:
  NTFY_TOPIC=kdp-my-secret-topic-123     → приложение ntfy, подписаться на этот топик
  TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...
Ничего не задано — сообщения только в лог. Сбой отправки никогда не роняет автопилот.
"""
import logging
import os

import httpx

log = logging.getLogger("notify")


def send(title: str, text: str, *, priority: str = "default", client: httpx.Client | None = None) -> list[str]:
    """Отправляет во все настроенные каналы. Возвращает, куда удалось отправить."""
    log.info("%s: %s", title, text)
    sent = []
    c = client or httpx.Client(timeout=15)
    if topic := os.getenv("NTFY_TOPIC", "").strip():
        server = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
        try:
            # заголовки HTTP — только latin-1, поэтому заголовок сообщения кладём в тело
            c.post(f"{server}/{topic}", content=f"{title}\n{text}".encode(),
                   headers={"Priority": {"high": "4", "low": "2"}.get(priority, "3")}).raise_for_status()
            sent.append("ntfy")
        except httpx.HTTPError as e:
            log.warning("ntfy не отправлен: %s", e)
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN", "").strip(), os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if token and chat:
        try:
            c.post(f"https://api.telegram.org/bot{token}/sendMessage",
                   json={"chat_id": chat, "text": f"{title}\n{text}"[:4000]}).raise_for_status()
            sent.append("telegram")
        except httpx.HTTPError as e:
            log.warning("telegram не отправлен: %s", e)
    return sent
