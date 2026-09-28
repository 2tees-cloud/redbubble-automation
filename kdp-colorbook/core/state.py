"""Состояние провайдеров: кто на паузе (cooldown), сколько раз подряд падал, расход за день.
Хранится в SQLite, поэтому переживает перезапуск процесса."""
import datetime as dt
import sqlite3
import threading
import time
from pathlib import Path

# Базовая пауза (сек) по типу ошибки. Для rate/quota/server растёт экспоненциально.
BASE_COOLDOWN = {
    "rate": 60,          # 429 — лимит в минуту/день
    "quota": 6 * 3600,   # 402 — закончились кредиты
    "auth": 24 * 3600,   # 401/403 — неверный или отозванный ключ
    "server": 30,        # 5xx, таймаут, обрыв сети
    "bad_request": 10,   # 400 — провайдер не понял запрос (модель, параметры)
    "bad_output": 30,    # пустой ответ, битая картинка, невалидный JSON
}
MAX_COOLDOWN = 12 * 3600


class State:
    def __init__(self, path: str | Path = "data/router_state.db"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS provider (
                name TEXT PRIMARY KEY,
                cooldown_until REAL DEFAULT 0,
                fails INTEGER DEFAULT 0,
                last_error TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS usage (
                name TEXT, day TEXT, ok INTEGER DEFAULT 0, failed INTEGER DEFAULT 0,
                PRIMARY KEY (name, day)
            );
            """
        )
        self.db.commit()

    @staticmethod
    def _today() -> str:
        return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")

    def _ensure(self, name: str) -> None:
        self.db.execute("INSERT OR IGNORE INTO provider(name) VALUES (?)", (name,))
        self.db.execute("INSERT OR IGNORE INTO usage(name, day) VALUES (?, ?)", (name, self._today()))

    def cooldown_left(self, name: str) -> float:
        row = self.db.execute("SELECT cooldown_until FROM provider WHERE name=?", (name,)).fetchone()
        return max(0.0, (row[0] if row else 0) - time.time())

    def success(self, name: str) -> None:
        with self._lock:
            self._ensure(name)
            self.db.execute("UPDATE provider SET fails=0, cooldown_until=0, last_error='' WHERE name=?", (name,))
            self.db.execute("UPDATE usage SET ok=ok+1 WHERE name=? AND day=?", (name, self._today()))
            self.db.commit()

    def failure(self, name: str, kind: str, detail: str, retry_after: float | None = None) -> float:
        """Ставит провайдера на паузу. Возвращает длину паузы в секундах."""
        with self._lock:
            self._ensure(name)
            fails = self.db.execute("SELECT fails FROM provider WHERE name=?", (name,)).fetchone()[0] + 1
            base = BASE_COOLDOWN.get(kind, 30)
            if retry_after:
                delay = min(retry_after, MAX_COOLDOWN)
            elif kind in ("rate", "server", "bad_output"):
                delay = min(base * 2 ** (fails - 1), MAX_COOLDOWN)
            else:
                delay = base  # auth/quota: фиксированная пауза, потолок MAX_COOLDOWN к ним не относится
            self.db.execute(
                "UPDATE provider SET fails=?, cooldown_until=?, last_error=? WHERE name=?",
                (fails, time.time() + delay, f"{kind}: {detail}"[:500], name),
            )
            self.db.execute("UPDATE usage SET failed=failed+1 WHERE name=? AND day=?", (name, self._today()))
            self.db.commit()
            return delay

    def reset(self, name: str | None = None) -> None:
        with self._lock:
            if name:
                self.db.execute("UPDATE provider SET fails=0, cooldown_until=0 WHERE name=?", (name,))
            else:
                self.db.execute("UPDATE provider SET fails=0, cooldown_until=0")
            self.db.commit()

    def report(self) -> list[dict]:
        rows = self.db.execute(
            """SELECT p.name, p.cooldown_until, p.fails, p.last_error,
                      COALESCE(u.ok,0), COALESCE(u.failed,0)
               FROM provider p LEFT JOIN usage u ON u.name=p.name AND u.day=?
               ORDER BY p.name""",
            (self._today(),),
        ).fetchall()
        now = time.time()
        return [
            {"name": r[0], "cooldown_s": max(0, int(r[1] - now)), "fails": r[2],
             "last_error": r[3], "ok_today": r[4], "failed_today": r[5]}
            for r in rows
        ]
