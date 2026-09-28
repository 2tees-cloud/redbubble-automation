"""Автопилот: одна книга в день. Запускается планировщиком (scripts/schedule.py) или вручную.
  python scripts/daily.py            — сделать сегодняшнюю книгу (или доделать незаконченную)
  python scripts/daily.py --force    — ещё одну книгу, даже если сегодня уже была
  python scripts/daily.py --status   — последние запуски
Шаги: исследование ниши → страницы → интерьер → обложка и метаданные → загрузка в KDP.
Уведомления — NTFY_TOPIC / TELEGRAM_* в .env. Журнал — data/logs/.
"""
import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import autopilot, load_routers  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if args.status:
        for p in sorted((ROOT / "data" / "runs").glob("*.json"))[-10:]:
            r = json.loads(p.read_text(encoding="utf-8"))
            print(f"{r['id']:14} {r['status']:8} шаг={r['step']:9} {r.get('title') or (r.get('plan') or {}).get('phrase', '')}"
                  + (f"\n{'':15}! {r['error']}" if r.get("error") and r["status"] != "done" else ""))
        return

    logs = ROOT / "data" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    text, image = load_routers()
    fh = logging.FileHandler(logs / f"{dt.date.today().isoformat()}.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(fh)

    try:
        run = autopilot.Autopilot(cfg, text, image).run(force=args.force)
    except RuntimeError as e:  # уже запущен
        sys.exit(str(e))
    if run is None:
        print("Книга на сегодня уже сделана. Ещё одну: --force")
    else:
        print(f"{run['id']}: {run['status']} (шаг {run['step']})" + (f" — {run['error']}" if run["error"] else ""))


if __name__ == "__main__":
    main()
