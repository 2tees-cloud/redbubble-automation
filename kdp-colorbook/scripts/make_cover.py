"""Обложка + метаданные листинга для книги, собранной make_pages.py.
  python scripts/make_cover.py out/dinosaurs --author "Anna Green"
  python scripts/make_cover.py out/dinosaurs --title "My Title" --subtitle "..." --palette jungle
Результат в папке книги: cover.pdf (загружать в KDP), cover_preview.png (с разметкой обреза,
корешка, безопасной зоны и штрихкода), metadata.json / metadata.txt (для копирования в форму KDP).
Метаданные генерируются один раз; --new-meta — придумать заново.
"""
import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import AllProvidersFailed, assemble, cover, load_routers, safety  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("book_dir", type=Path)
    ap.add_argument("--author", help="по умолчанию book.author из config.yaml")
    ap.add_argument("--title")
    ap.add_argument("--subtitle")
    ap.add_argument("--palette", choices=sorted(cover.PALETTES))
    ap.add_argument("--paper", choices=sorted(cover.PAPER), default="white")
    ap.add_argument("--seed", type=int, default=0, help="другой seed — другие цвета раскраски")
    ap.add_argument("--new-meta", action="store_true", help="сгенерировать метаданные заново")
    args = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    safety.configure(cfg.get("safety"))
    text, _ = load_routers()
    try:
        meta, warn, res = assemble.meta_and_cover(args.book_dir, cfg, text, author=args.author or "",
                                                  title=args.title, subtitle=args.subtitle, palette=args.palette,
                                                  paper=args.paper, seed=args.seed, new_meta=args.new_meta)
    except AllProvidersFailed as e:
        sys.exit(f"{e}\n\nНет текстового провайдера — задайте хотя бы --title (и --subtitle).")
    except ValueError as e:
        sys.exit(str(e))
    pages = res["pages"]

    print(f"Обложка: {res['path']}")
    print(f"  размер {res['size_in'][0]} x {res['size_in'][1]} in ({res['size_px'][0]}x{res['size_px'][1]} px, 300 DPI)")
    print(f"  страниц в интерьере {pages}, корешок {res['spine_in']} in, текст на корешке: "
          f"{'да' if res['spine_text'] else f'нет (KDP разрешает от {cover.SPINE_TEXT_MIN_PAGES} страниц)'}")
    print(f"Превью с разметкой: {args.book_dir / 'cover_preview.png'}")
    print(f"Метаданные: {args.book_dir / 'metadata.txt'}")
    for w in warn:
        print(f"  ! {w}")


if __name__ == "__main__":
    main()
