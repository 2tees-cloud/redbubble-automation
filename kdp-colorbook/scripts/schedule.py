"""Поставить автопилот в расписание компьютера (раз в день).
  python scripts/schedule.py --time 09:15         — Windows: Планировщик заданий; macOS/Linux: crontab
  python scripts/schedule.py --remove
Компьютер должен быть включён в это время (для Windows можно разрешить пробуждение в свойствах задачи).
"""
import argparse
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASK = "KDP-Colorbook-Autopilot"
MARK = "# kdp-colorbook-autopilot"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--time", default="09:15", help="ЧЧ:ММ, местное время")
    ap.add_argument("--remove", action="store_true")
    args = ap.parse_args()
    py, script = sys.executable, ROOT / "scripts" / "daily.py"

    if platform.system() == "Windows":
        if args.remove:
            cmd = ["schtasks", "/Delete", "/TN", TASK, "/F"]
        else:
            cmd = ["schtasks", "/Create", "/F", "/SC", "DAILY", "/ST", args.time, "/TN", TASK,
                   "/TR", f'"{py}" "{script}"']
        subprocess.run(cmd, check=True)
    else:
        cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        lines = [ln for ln in cur.splitlines() if MARK not in ln]
        if not args.remove:
            hh, mm = args.time.split(":")
            lines.append(f"{int(mm)} {int(hh)} * * * mkdir -p '{ROOT}/data/logs' && cd '{ROOT}' && '{py}' '{script}' "
                         f">> '{ROOT}/data/logs/cron.log' 2>&1 {MARK}")
        subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True, check=True)
    print("Расписание удалено." if args.remove else f"Автопилот будет запускаться ежедневно в {args.time}.")


if __name__ == "__main__":
    main()
