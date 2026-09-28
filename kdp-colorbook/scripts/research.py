"""Исследование ниш без генерации книги — посмотреть, что выбрал бы автопилот.
  python scripts/research.py            → таблица лучших ниш + план книги; отчёт в data/research/<дата>.json
Данные о спросе: подсказки Amazon + выдача и BSR (бесплатно, возможна капча) или Keepa (KEEPA_API_KEY в .env).
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import load_routers, research, safety  # noqa: E402


def main() -> None:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    rcfg = cfg.get("research") or {}
    safety.configure(cfg.get("safety"))
    text, _ = load_routers()
    data = ROOT / "data"
    amazon = research.AmazonClient(data / "cache", domain=rcfg.get("domain", "www.amazon.com"))
    plan, short = research.research(
        amazon=amazon, text_router=text, history=research.History(data / "history.json"),
        rc=research.ResearchConfig.from_config(rcfg), report_dir=data / "research",
        keepa=research.keepa_from_env(),
        moderation_required=(cfg.get("safety") or {}).get("llm_required", True))

    if amazon.blocked:
        print("! Amazon показал капчу — оценка частично по подсказкам (confidence low/medium)")
    print(f"\n{'оценка':>7} {'увер.':6} {'книг':>7} {'окна':>4} {'продаж/д':>8}  ниша")
    for n in short:
        total = f"{n.total:,}" if n.total else "?"
        print(f"{n.score:7.3f} {n.confidence:6} {total:>7} {n.weak_spots:>4} {n.demand:8.2f}  {n.phrase}"
              + (f"  [{n.season}]" if n.season else "") + (f"  — {'; '.join(n.notes)}" if n.notes else ""))
    if plan:
        print(f"\nВыбрано: {plan['phrase']}\n  тема: {plan['theme']} | аудитория: {plan['audience']} "
              f"{plan['age']} | формат {plan['trim']} | страниц {plan['pages']}\n  {plan.get('angle', '')}")
    else:
        print("\nПодходящей ниши не нашлось (все отсеяны модерацией/историей/спросом).")


if __name__ == "__main__":
    main()
