"""Один раз войти в KDP вручную (почта, пароль, код 2FA). Сессия сохранится в data/kdp_profile,
и дальше робот работает без вас. Повторить, если придёт уведомление «KDP: нужен вход».
  python scripts/kdp_login.py
"""
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import kdp  # noqa: E402


def main() -> None:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    kcfg = {**(cfg.get("kdp") or {}), "headless": False}
    with kdp.KdpUploader(kcfg) as up:
        up.page.goto(f"{up.base}/bookshelf")
        print("Войдите в KDP в открывшемся окне (включая код подтверждения). Жду до 10 минут…")
        deadline = time.time() + 600
        while time.time() < deadline:
            if up.exists("login", "signed_in", timeout=2000):
                print("Готово: вход выполнен, сессия сохранена. Окно можно закрыть.")
                time.sleep(3)
                return
        sys.exit("Не дождался входа. Запустите ещё раз.")


if __name__ == "__main__":
    main()
