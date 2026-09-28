"""Проверка ядра.
  python scripts/check_router.py            — тест текста + одной картинки-раскраски
  python scripts/check_router.py --models   — какие модели доступны по вашим ключам
  python scripts/check_router.py --status   — кто на паузе, расход за сегодня
  python scripts/check_router.py --reset    — снять все паузы
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import AllProvidersFailed, load_routers  # noqa: E402

PAGE_PROMPT = ("children's coloring book page, {subject}, thick clean black outlines, "
               "pure white background, no shading, no gray, no color, simple shapes, "
               "cute cartoon style for kids age 4-8, full body centered, line art")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()

    text, image = load_routers()

    if args.reset:
        text.state.reset()
        print("Паузы сняты.")
        return
    if args.status:
        for row in text.state.report():
            print(json.dumps(row, ensure_ascii=False))
        return
    if args.models:
        for name, models in text.list_models().items():
            print(f"\n== {name} ==")
            print(models if isinstance(models, str) else "\n".join(models))
        return

    print("\n--- ТЕКСТ ---")
    try:
        r = text.chat_json("Придумай 3 темы для детской книжки-раскраски (4-8 лет). "
                           'Формат: {"themes": [{"title": "...", "subjects": ["...", "..."]}]}')
        print(f"[{r['provider']} / {r['model']}]")
        print(json.dumps(r["data"], ensure_ascii=False, indent=2))
    except AllProvidersFailed as e:
        print(e)

    print("\n--- КАРТИНКА ---")
    try:
        r = image.generate(PAGE_PROMPT.format(subject="a happy dinosaur holding a balloon"))
        out = ROOT / "out"
        out.mkdir(exist_ok=True)
        path = out / f"test_{r['provider']}_{r['seed']}.png"
        r["image"].save(path)
        print(f"[{r['provider']}] сохранено: {path}  размер {r['image'].size}")
    except AllProvidersFailed as e:
        print(e)


if __name__ == "__main__":
    main()
