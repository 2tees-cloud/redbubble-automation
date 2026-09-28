"""Папка картинок → чистые векторные страницы → PDF-интерьер для KDP.
  python scripts/build_interior.py out/pages                  → out/interior.pdf
  python scripts/build_interior.py out/pages -o book.pdf --svg   (+ SVG каждой страницы рядом)
Настройки обработки и формата — секции postprocess / book в config.yaml.
"""
import argparse
import sys
import time
from pathlib import Path

import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import book, postprocess  # noqa: E402

EXT = {".png", ".jpg", ".jpeg", ".webp"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path, help="папка с картинками (порядок = сортировка по имени)")
    ap.add_argument("-o", "--out", type=Path, default=ROOT / "out" / "interior.pdf")
    ap.add_argument("--svg", action="store_true", help="сохранить очищенные SVG рядом с картинками")
    ap.add_argument("--trim", help=f"формат: {', '.join(book.TRIMS)} (по умолчанию из config)")
    args = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    pp_cfg, book_cfg = cfg.get("postprocess", {}), cfg.get("book", {})

    files = sorted(f for f in args.src.iterdir() if f.suffix.lower() in EXT)
    if not files:
        sys.exit(f"В {args.src} нет картинок ({', '.join(sorted(EXT))})")

    pages = []
    for f in files:
        t = time.time()
        page = postprocess.process(Image.open(f), **pp_cfg)
        pages.append(page)
        if args.svg:
            f.with_suffix(".clean.svg").write_text(postprocess.to_svg(page), encoding="utf-8")
        print(f"{f.name}: {len(page.subpaths)} контуров, {time.time() - t:.1f} с")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    res = book.build_interior(pages, args.out, trim=book.parse_trim(args.trim or book_cfg.get("trim", "8.5x11")),
                              margin=book_cfg.get("margin", 0.5),
                              blank_backs=book_cfg.get("blank_backs", True))
    print(f"\nГотово: {res['path']}  страниц {res['page_count']}, поле у корешка {res['gutter']}\"")
    if res["page_count"] < book.MIN_PAGES:
        print(f"ВНИМАНИЕ: KDP требует минимум {book.MIN_PAGES} страниц")


if __name__ == "__main__":
    main()
