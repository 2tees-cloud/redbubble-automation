"""Конвейер страниц: тема → сюжеты → генерация → чистка → фильтр брака → принятые страницы.

Всё состояние — в <out_dir>/manifest.json, он пишется после каждой страницы. Если бесплатные
лимиты кончились посреди книги, запуск той же командой продолжит с места остановки.
"""
import json
import logging
import re
from pathlib import Path

from PIL import Image

from . import postprocess, profiles, quality, safety
from .base import AllProvidersFailed

log = logging.getLogger("pipeline")

PAGE_PROMPT = profiles.PROFILES["kids"]["page_prompt"]  # совместимость: промпт по умолчанию

SUBJECTS_PROMPT = """Theme of a coloring book: "{theme}". Audience: {audience}.
Invent {count} DIFFERENT page ideas. Each is one concrete visual scene in English, 5-12 words:
{style}.
All ideas must be visually distinct from each other. No brands, franchises, famous characters or real people.
Format: {{"subjects": ["...", "..."]}}"""


def resolve(cfg: dict, audience: str) -> tuple[dict, dict, quality.Limits]:
    """Профиль + настройки обработки + пороги фильтра. Приоритет (слабый → сильный):
    общие секции config.yaml → встроенный профиль → config.yaml profiles.<audience>."""
    prof = profiles.get(audience, (cfg.get("profiles") or {}).get(audience))
    pp_cfg = {**(cfg.get("postprocess") or {}), **prof.get("postprocess", {})}
    lim = quality.Limits.from_config({**(cfg.get("quality") or {}), **prof.get("quality", {})})
    return prof, pp_cfg, lim


def _slug(s: str, n: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:n] or "page"


def plan_subjects(text, theme: str, count: int, age: str, profile: dict | None = None) -> list[str]:
    profile = profile or profiles.get("kids")
    res = text.chat_json(SUBJECTS_PROMPT.format(theme=theme, count=count, style=profile["subjects_style"],
                                                audience=profile["audience"].format(age=age)), temperature=0.9)
    data = res["data"]
    items = data.get("subjects", []) if isinstance(data, dict) else data
    seen, out = set(), []
    for s in items:
        s = str(s).strip()
        if s and s.lower() not in seen and not safety.blocked_terms(s):  # бренды/запрещённое — выкидываем
            seen.add(s.lower())
            out.append(s)
    if not out:
        raise ValueError(f"модель не вернула сюжетов: {str(data)[:200]}")
    return out


class Manifest:
    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    @classmethod
    def write(cls, path: Path, data: dict) -> None:
        m = cls(path)
        m.data = data
        m.save()

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)  # атомарно: падение посреди записи не портит файл


def make_pages(text, image, *, theme: str, count: int, out_dir: str | Path, age: str = "4-8",
               attempts: int = 3, extra: float = 0.4, use_vision: bool = True,
               pp_cfg: dict | None = None, limits: quality.Limits | None = None,
               prompt: str | None = None, audience: str = "kids", profile: dict | None = None) -> dict:
    """Генерирует страницы, пока не наберётся count принятых. Возвращает манифест.

    attempts — сколько раз перегенерировать один сюжет (с новым seed), прежде чем взять следующий.
    extra    — запас сюжетов сверх count: часть отсеется фильтром.
    """
    out = Path(out_dir)
    (out / "pages").mkdir(parents=True, exist_ok=True)
    (out / "rejected").mkdir(exist_ok=True)
    man = Manifest(out / "manifest.json")
    d = man.data
    d.setdefault("theme", theme)
    d.setdefault("age", age)
    d.setdefault("audience", audience)
    profile = profile or profiles.get(d["audience"])
    pp_cfg = pp_cfg if pp_cfg is not None else dict(profile.get("postprocess", {}))
    lim = limits or quality.Limits.from_config(profile.get("quality"))
    prompt = prompt or profile["page_prompt"]
    aud_text = profile["audience"].format(age=d["age"])
    d.setdefault("accepted", [])
    d.setdefault("rejected", [])

    if "subjects" not in d:
        d["subjects"] = plan_subjects(text, theme, int(count * (1 + extra)) + 1, d["age"], profile)
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
                g = image.generate(prompt.format(subject=subject, age=d["age"]))
            except AllProvidersFailed:
                man.save()
                raise
            ink = postprocess.binarize(g["image"], **{k: v for k, v in pp_cfg.items() if k != "smooth"})
            verdict = quality.evaluate(g["image"], ink, subject=subject, lim=lim, deduper=deduper,
                                 text_router=text if use_vision else None, audience=aud_text)
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
    cfg = pp_cfg if pp_cfg is not None else profiles.get(d.get("audience", "kids")).get("postprocess", {})
    return [postprocess.process(Image.open(out / "pages" / f"{a['file']}.png"), **cfg)
            for a in d.get("accepted", [])]
