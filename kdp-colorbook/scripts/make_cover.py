"""Обложка + метаданные листинга для книги, собранной make_pages.py.
  python scripts/make_cover.py out/dinosaurs --author "Anna Green"
  python scripts/make_cover.py out/dinosaurs --title "My Title" --subtitle "..." --palette jungle
Результат в папке книги: cover.pdf (загружать в KDP), cover_preview.png (с разметкой обреза,
корешка, безопасной зоны и штрихкода), metadata.json / metadata.txt (для копирования в форму KDP).
Метаданные генерируются один раз; --new-meta — придумать заново.
"""
import argparse
import json
import sys
from pathlib import Path

import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import AllProvidersFailed, book, cover, load_routers, metadata, pipeline, postprocess, safety  # noqa: E402


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
    book_cfg = cfg.get("book", {})
    d = json.loads((args.book_dir / "manifest.json").read_text(encoding="utf-8"))
    acc = d.get("accepted", [])
    if not acc:
        sys.exit("В книге нет принятых страниц — сначала make_pages.py")
    trim = book.parse_trim(d.get("trim") or book_cfg.get("trim", "8.5x11"))
    audience = d.get("audience", "kids")
    _, pp_cfg, _ = pipeline.resolve(cfg, audience)
    safety.configure(cfg.get("safety"))
    pages = book.page_count(len(acc), book_cfg.get("blank_backs", True))

    # --- метаданные
    meta_path = args.book_dir / "metadata.json"
    if meta_path.exists() and not args.new_meta:
        saved = json.loads(meta_path.read_text(encoding="utf-8"))
        meta, warn = saved["meta"], saved["warnings"]
    else:
        try:
            text, _ = load_routers()
            meta, warn = metadata.generate(text, theme=d["theme"], age=d.get("age", "4-8"), images=len(acc),
                                           trim=f"{trim[0]} x {trim[1]} in",
                                           examples=[a["subject"] for a in acc], audience=audience)
        except AllProvidersFailed as e:
            if not args.title:
                sys.exit(f"{e}\n\nНет текстового провайдера — задайте хотя бы --title (и --subtitle).")
            meta, warn = metadata.sanitize({"title": args.title})
            warn.append("метаданные не сгенерированы (нет провайдера) — заполните описание и ключевые фразы")
    for k in ("title", "subtitle"):
        if getattr(args, k):
            meta[k] = getattr(args, k)
    meta["author"] = args.author or book_cfg.get("author") or meta.get("author", "")
    meta_path.write_text(json.dumps({"meta": meta, "warnings": warn}, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    (args.book_dir / "metadata.txt").write_text(metadata.to_text(meta, warn), encoding="utf-8")

    # --- обложка: на лицо — страница с лучшей оценкой vision, на задник — следующие 4
    ranked = sorted(acc, key=lambda a: -float((a.get("metrics", {}).get("vision") or {}).get("score", 0) or 0))
    vec = {a["file"]: postprocess.process(Image.open(args.book_dir / "pages" / f"{a['file']}.png"), **pp_cfg)
           for a in ranked[:5]}
    hero, previews = vec[ranked[0]["file"]], [vec[a["file"]] for a in ranked[1:5]]
    spec = cover.CoverSpec(trim[0], trim[1], pages, args.paper)
    res = cover.build_cover(spec, title=meta["title"], subtitle=meta.get("subtitle", ""), author=meta["author"],
                            hero=hero, previews=previews, back_text=meta.get("back_text", ""),
                            out_pdf=args.book_dir / "cover.pdf", preview_png=args.book_dir / "cover_preview.png",
                            palette=args.palette, seed=args.seed)

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
