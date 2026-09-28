"""Тема → готовые проверенные страницы (и PDF).
  python scripts/make_pages.py "dinosaurs" -n 30 --pdf     → out/dinosaurs/pages/*.png|svg, interior.pdf
  python scripts/make_pages.py "dinosaurs" -n 30 --pdf     (повторно — продолжит с места остановки)
  python scripts/make_pages.py "space" -n 25 --age 8-12 --no-vision
Отбракованные картинки с причинами — out/<тема>/rejected и manifest.json.
"""
import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import AllProvidersFailed, book, load_routers, pipeline, quality  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("theme")
    ap.add_argument("-n", "--count", type=int, default=30, help="сколько страниц нужно")
    ap.add_argument("--age", default="4-8")
    ap.add_argument("--out", type=Path, help="папка книги (по умолчанию out/<тема>)")
    ap.add_argument("--attempts", type=int, default=3, help="попыток на один сюжет")
    ap.add_argument("--no-vision", action="store_true", help="без проверки vision-моделью")
    ap.add_argument("--pdf", action="store_true", help="собрать interior.pdf из принятых страниц")
    args = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    pp_cfg, book_cfg = cfg.get("postprocess", {}), cfg.get("book", {})
    out = args.out or ROOT / "out" / pipeline._slug(args.theme)
    text, image = load_routers()

    try:
        d = pipeline.make_pages(text, image, theme=args.theme, count=args.count, out_dir=out, age=args.age,
                                attempts=args.attempts, use_vision=not args.no_vision, pp_cfg=pp_cfg,
                                limits=quality.Limits.from_config(cfg.get("quality")),
                                prompt=cfg.get("page_prompt") or pipeline.PAGE_PROMPT)
    except AllProvidersFailed as e:
        sys.exit(f"{e}\n\nПрогресс сохранён в {out / 'manifest.json'} — запустите ту же команду позже.")

    acc, rej = len(d["accepted"]), len(d["rejected"])
    print(f"\nПринято {acc}/{args.count}, отбраковано {rej} ({rej / max(acc + rej, 1):.0%}). Папка: {out}")
    if args.pdf and acc:
        res = book.build_interior(pipeline.load_vectors(out, pp_cfg), out / "interior.pdf",
                                  trim=tuple(book_cfg.get("trim", (8.5, 11))), margin=book_cfg.get("margin", 0.5),
                                  blank_backs=book_cfg.get("blank_backs", True), title=args.theme)
        print(f"PDF: {res['path']}  страниц {res['page_count']}")


if __name__ == "__main__":
    main()
