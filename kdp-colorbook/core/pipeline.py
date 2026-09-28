"""Конвейер страниц: тема → сюжеты → генерация → чистка → фильтр брака → принятые страницы.

Всё состояние — в <out_dir>/manifest.json, он пишется после каждой страницы. Если бесплатные
лимиты кончились посреди книги, запуск той же командой продолжит с места остановки.
"""
import json
import logging
import re
from pathlib import Path

from PIL import Image

from . import postprocess, quality
from .base import AllProvidersFailed

log = logging.getLogger("pipeline")

PAGE_PROMPT = ("children's coloring book page, {subject}, thick clean black outlines, "
               "pure white background, no shading, no gray, no color, no text, simple shapes, "
               "cute cartoon style for kids age {age}, whole subject fully inside the frame, line art")

SUBJECTS_PROMPT = """Theme of a coloring book: "{theme}". Audience: kids age {age}.
Invent {count} DIFFERENT page ideas. Each is one concrete visual scene in English, 5-12 words,
one main character doing something, simple background (no crowds, no text, no small details).
All ideas must be visually distinct from each other.
Format: {{"subjects": ["...", "..."]}}"""


def _slug(s: str, n: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:n] or "page"


def plan_subjects(text, theme: str, count: int, age: str) -> list[str]:
    res = text.chat_json(SUBJECTS_PROMPT.format(theme=theme, count=count, age=age), temperature=0.9)
    data = res["data"]
    items = data.get("subjects", []) if isinstance(data, dict) else data
    seen, out = set(), []
    for s in items:
        s = str(s).strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    if not out:
        raise ValueError(f"модель не вернула сюжетов: {str(data)[:200]}")
    return out


class Manifest:
    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)  # атомарно: падение посреди записи не портит файл


def make_pages(text, image, *, theme: str, count: int, out_dir: str | Path, age: str = "4-8",
               attempts: int = 3, extra: float = 0.4, use_vision: bool = True,
               pp_cfg: dict | None = None, limits: quality.Limits | None = None,
               prompt: str = PAGE_PROMPT) -> dict:
    """Генерирует страницы, пока не наберётся count принятых. Возвращает манифест.

    attempts — сколько раз перегенерировать один сюжет (с новым seed), прежде чем взять следующий.
    extra    — запас сюжетов сверх count: часть отсеется фильтром.
    """
    out = Path(out_dir)
    (out / "pages").mkdir(parents=True, exist_ok=True)
    (out / "rejected").mkdir(exist_ok=True)
    pp_cfg, lim = pp_cfg or {}, limits or quality.Limits()
    man = Manifest(out / "manifest.json")
    d = man.data
    d.setdefault("theme", theme)
    d.setdefault("age", age)
    d.setdefault("accepted", [])
    d.setdefault("rejected", [])

    if "subjects" not in d:
        d["subjects"] = plan_subjects(text, theme, int(count * (1 + extra)) + 1, age)
        man.save()
        log.info("сюжетов: %d", len(d["subjects"]))

    deduper = quality.Deduper(lim.dup_distance)
    for a in d["accepted"]:
        deduper.add(a["phash"], a["file"])
    done = {a["subject"] for a in d["accepted"]} | {r["subject"] for r in d["rejected"] if r.get("final")}

    for subject in d["subjects"]:
        if len(d["accepted"]) >= count:
            break
        if subject in done:
            continue
        tries = sum(1 for r in d["rejected"] if r["subject"] == subject)
        while tries < attempts:
            tries += 1
            try:
                g = image.generate(prompt.format(subject=subject, age=age))
            except AllProvidersFailed:
                man.save()
                raise
            ink = postprocess.binarize(g["image"], **{k: v for k, v in pp_cfg.items() if k != "smooth"})
            verdict = quality.evaluate(g["image"], ink, subject=subject, lim=lim, deduper=deduper,
                                 text_router=text if use_vision else None)
            name = f"{len(d['accepted']) + 1:03d}_{_slug(subject)}"
            rec = {"subject": subject, "provider": g["provider"], "seed": g["seed"],
                   "metrics": {k: m for k, m in verdict.metrics.items() if k != "phash"}}
            if verdict.ok:
                g["image"].save(out / "pages" / f"{name}.png")
                vec = postprocess.vectorize(ink, smooth=pp_cfg.get("smooth", 1.0))
                (out / "pages" / f"{name}.svg").write_text(postprocess.to_svg(vec), encoding="utf-8")
                deduper.add(verdict.metrics["phash"], name)
                d["accepted"].append({**rec, "file": name, "phash": verdict.metrics["phash"]})
                log.info("✓ %s  [%s]", name, g["provider"])
                man.save()
                break
            rej = f"{len(d['rejected']) + 1:03d}_{_slug(subject)}"
            g["image"].save(out / "rejected" / f"{rej}.png")
            d["rejected"].append({**rec, "file": rej, "reasons": verdict.reasons, "final": tries >= attempts})
            log.info("✗ %s: %s", subject, "; ".join(verdict.reasons))
            man.save()

    if len(d["accepted"]) < count:
        log.warning("принято %d из %d: сюжеты кончились. Удалите \"subjects\" из manifest.json "
                    "или увеличьте extra, чтобы придумать новые", len(d["accepted"]), count)
    return d


def load_vectors(out_dir: str | Path, pp_cfg: dict | None = None) -> list[postprocess.VectorPage]:
    """Векторные страницы принятых картинок — в порядке манифеста (для book.build_interior)."""
    out = Path(out_dir)
    d = Manifest(out / "manifest.json").data
    return [postprocess.process(Image.open(out / "pages" / f"{a['file']}.png"), **(pp_cfg or {}))
            for a in d.get("accepted", [])]
