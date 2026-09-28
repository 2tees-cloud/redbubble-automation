"""Сборка файлов книги из папки make_pages: interior.pdf, метаданные, cover.pdf.
Общая для ручных скриптов и автопилота."""
import json
from pathlib import Path

from PIL import Image

from . import book, cover, metadata, pipeline, postprocess, safety
from .base import AllProvidersFailed


class UnsafeMetadata(RuntimeError):
    pass


def _manifest(book_dir: Path) -> dict:
    d = json.loads((Path(book_dir) / "manifest.json").read_text(encoding="utf-8"))
    if not d.get("accepted"):
        raise ValueError("в книге нет принятых страниц — сначала make_pages")
    return d


def _trim(d: dict, cfg: dict) -> tuple[float, float]:
    return book.parse_trim(d.get("trim") or (cfg.get("book") or {}).get("trim", "8.5x11"))


def interior(book_dir: Path, cfg: dict) -> dict:
    d = _manifest(book_dir)
    bcfg = cfg.get("book") or {}
    _, pp_cfg, _ = pipeline.resolve(cfg, d.get("audience", "kids"))
    return book.build_interior(pipeline.load_vectors(book_dir, pp_cfg), Path(book_dir) / "interior.pdf",
                               trim=_trim(d, cfg), margin=bcfg.get("margin", 0.5),
                               blank_backs=bcfg.get("blank_backs", True), title=d["theme"])


def meta_and_cover(book_dir: Path, cfg: dict, text_router, *, author: str = "", title: str | None = None,
                   subtitle: str | None = None, palette: str | None = None, paper: str = "white", seed: int = 0,
                   new_meta: bool = False, strict: bool = False, tries: int = 3,
                   moderation_required: bool = True) -> tuple[dict, list[str], dict]:
    """Метаданные (генерирует один раз, хранит в metadata.json) + обложка.
    strict=True (автопилот): бренд/запрет в названии или описании → перегенерация, затем UnsafeMetadata;
    название и подзаголовок дополнительно проходят LLM-модерацию."""
    book_dir = Path(book_dir)
    d = _manifest(book_dir)
    acc = d["accepted"]
    bcfg = cfg.get("book") or {}
    trim = _trim(d, cfg)
    audience = d.get("audience", "kids")
    _, pp_cfg, _ = pipeline.resolve(cfg, audience)
    pages = book.page_count(len(acc), bcfg.get("blank_backs", True))

    meta_path = book_dir / "metadata.json"
    meta = warn = None
    if meta_path.exists() and not new_meta:
        saved = json.loads(meta_path.read_text(encoding="utf-8"))
        meta, warn = saved["meta"], saved["warnings"]
    else:
        for _ in range(max(1, tries if strict else 1)):
            try:
                meta, warn = metadata.generate(text_router, theme=d["theme"], age=d.get("age", "4-8"),
                                               images=len(acc), trim=f"{trim[0]:g} x {trim[1]:g} in",
                                               examples=[a["subject"] for a in acc], audience=audience)
            except AllProvidersFailed:
                if strict or not title:
                    raise
                meta, warn = metadata.sanitize({"title": title})
                warn.append("метаданные не сгенерированы (нет провайдера) — заполните описание и ключевые фразы")
            if not strict:
                break
            if not meta.get("unsafe"):
                rej = safety.moderate([f"{meta['title']}: {meta.get('subtitle', '')}"], text_router,
                                      required=moderation_required)
                if not rej:
                    break
                meta["unsafe"] = list(rej.values())
        if strict and meta.get("unsafe"):
            raise UnsafeMetadata("; ".join(meta["unsafe"]))
    if title:
        meta["title"] = title
    if subtitle:
        meta["subtitle"] = subtitle
    meta["author"] = author or bcfg.get("author") or meta.get("author", "")
    meta_path.write_text(json.dumps({"meta": meta, "warnings": warn}, ensure_ascii=False, indent=2), encoding="utf-8")
    (book_dir / "metadata.txt").write_text(metadata.to_text(meta, warn), encoding="utf-8")

    # лицо — страница с лучшей оценкой vision, задник — следующие 4
    ranked = sorted(acc, key=lambda a: -float((a.get("metrics", {}).get("vision") or {}).get("score", 0) or 0))
    vec = {a["file"]: postprocess.process(Image.open(book_dir / "pages" / f"{a['file']}.png"), **pp_cfg)
           for a in ranked[:5]}
    spec = cover.CoverSpec(trim[0], trim[1], pages, paper)
    res = cover.build_cover(spec, title=meta["title"], subtitle=meta.get("subtitle", ""), author=meta["author"],
                            hero=vec[ranked[0]["file"]], previews=[vec[a["file"]] for a in ranked[1:5]],
                            back_text=meta.get("back_text", ""), out_pdf=book_dir / "cover.pdf",
                            preview_png=book_dir / "cover_preview.png", palette=palette, seed=seed)
    res["pages"] = pages
    return meta, warn, res
