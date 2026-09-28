"""Тема → готовые проверенные страницы (и PDF).
  python scripts/make_pages.py "dinosaurs" -n 30 --pdf     → out/dinosaurs/pages/*.png|svg, interior.pdf
  python scripts/make_pages.py "dinosaurs" -n 30 --pdf     (повторно — продолжит с места остановки)
  python scripts/make_pages.py "space" -n 25 --age 8-12 --no-vision
  python scripts/make_pages.py "floral mandalas for adults" -n 40 --trim 8.5x8.5   (аудитория adults — сама)
Отбракованные картинки с причинами — out/<тема>/rejected и manifest.json.
"""
import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import AllProvidersFailed, book, load_routers, pipeline, profiles, safety  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("theme")
    ap.add_argument("-n", "--count", type=int, default=30, help="сколько страниц нужно")
    ap.add_argument("--age", default="4-8", help="возраст для детских книг")
    ap.add_argument("--audience", choices=["auto", *profiles.PROFILES], default="auto",
                    help="kids / adults; auto — по словам темы (adult, mandala, stress relief…)")
    ap.add_argument("--trim", default=None, help=f"формат книги: {', '.join(book.TRIMS)} (по умолчанию из config)")
    ap.add_argument("--out", type=Path, help="папка книги (по умолчанию out/<тема>)")
    ap.add_argument("--attempts", type=int, default=3, help="попыток на один сюжет")
    ap.add_argument("--no-vision", action="store_true", help="без проверки vision-моделью")
    ap.add_argument("--pdf", action="store_true", help="собрать interior.pdf из принятых страниц")
    args = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    book_cfg = cfg.get("book", {})
    trim = book.parse_trim(args.trim or book_cfg.get("trim", "8.5x11"))
    audience = profiles.detect(args.theme) if args.audience == "auto" else args.audience
    prof, pp_cfg, lim = pipeline.resolve(cfg, audience)
    safety.configure(cfg.get("safety"))
    if bad := safety.blocked_terms(args.theme):
        sys.exit(f"Тема содержит бренд/запрещённое слово: {', '.join(bad)} — KDP может заблокировать аккаунт.")
    out = args.out or ROOT / "out" / pipeline._slug(args.theme)
    text, image = load_routers()
    print(f"Аудитория: {audience}, формат {book.trim_name(trim)}")

    try:
        d = pipeline.make_pages(text, image, theme=args.theme, count=args.count, out_dir=out, age=args.age,
                                attempts=args.attempts, use_vision=not args.no_vision, pp_cfg=pp_cfg,
                                limits=lim, audience=audience, profile=prof)
        d.setdefault("trim", book.trim_name(trim))
        pipeline.Manifest.write(out / "manifest.json", d)
    except AllProvidersFailed as e:
        sys.exit(f"{e}\n\nПрогресс сохранён в {out / 'manifest.json'} — запустите ту же команду позже.")

    acc, rej = len(d["accepted"]), len(d["rejected"])
    print(f"\nПринято {acc}/{args.count}, отбраковано {rej} ({rej / max(acc + rej, 1):.0%}). Папка: {out}")
    if args.pdf and acc:
        res = book.build_interior(pipeline.load_vectors(out, pp_cfg), out / "interior.pdf",
                                  trim=book.parse_trim(d["trim"]), margin=book_cfg.get("margin", 0.5),
                                  blank_backs=book_cfg.get("blank_backs", True), title=args.theme)
        print(f"PDF: {res['path']}  страниц {res['page_count']}")


if __name__ == "__main__":
    main()
