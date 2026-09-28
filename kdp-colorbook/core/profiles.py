"""Профили аудитории: всё, что отличает детскую раскраску от взрослой, в одном месте.

Промпт страницы, стиль сюжетов, как описывать аудиторию модели (сюжеты, vision, метаданные)
и пороги фильтра брака. Любое поле можно переопределить в config.yaml → profiles.<имя>.
"""
import copy
import re

PROFILES: dict[str, dict] = {
    "kids": {
        "page_prompt": ("children's coloring book page, {subject}, thick clean black outlines, "
                        "pure white background, no shading, no gray, no color, no text, simple shapes, "
                        "cute cartoon style for kids age {age}, whole subject fully inside the frame, line art"),
        "subjects_style": ("one main character doing something, simple background "
                           "(no crowds, no text, no small details)"),
        "audience": "kids age {age}",
        "listing_hint": ("subtitle like 'Coloring Book for Kids Ages {age}: ...'; description for parents; "
                         "mention thick lines and big simple pictures"),
        "quality": {},  # значения по умолчанию из quality.Limits рассчитаны на детей
        "postprocess": {},
    },
    "adults": {
        "page_prompt": ("adult coloring book page, {subject}, intricate detailed line art, crisp clean black "
                        "outlines, pure white background, no shading, no gray, no color, no text, many small "
                        "closed areas to color, decorative ornamental patterns, elegant, whole design fully "
                        "inside the frame"),
        "subjects_style": ("one striking central motif filled with decorative patterns (floral, mandala, "
                           "zentangle-inspired), relaxing and elegant; no realistic human faces, no text"),
        "audience": "adults (relaxation and stress relief)",
        "listing_hint": ("subtitle like 'An Adult Coloring Book with ...: Relaxing Designs for Stress Relief'; "
                         "description for adult colorists; mention intricate designs, single-sided pages "
                         "(markers do not bleed through), size"),
        # детальные рисунки: больше линий и мелких областей — это норма, а не брак
        "quality": {"min_ink": 0.04, "max_ink": 0.45, "max_solid": 0.06, "min_regions": 40,
                    "max_regions": 5000, "max_tiny": 0.45, "min_region_frac": 0.00012},
        "postprocess": {"smooth": 0.9},
    },
}


def get(name: str, overrides: dict | None = None) -> dict:
    """Профиль с учётом переопределений из config.yaml (profiles.<name>)."""
    if name not in PROFILES:
        raise ValueError(f"неизвестная аудитория {name!r}, есть: {', '.join(PROFILES)}")
    p = copy.deepcopy(PROFILES[name])
    for k, v in (overrides or {}).items():
        if v is None:
            continue
        if isinstance(v, dict) and isinstance(p.get(k), dict):
            p[k].update(v)
        elif v is not None:
            p[k] = v
    p["name"] = name
    return p


def detect(phrase: str) -> str:
    """Аудитория по поисковой фразе ниши."""
    if re.search(r"\b(adults?|grown[- ]ups?|women|men|seniors|teens?|mandalas?|stress relief|"
                 r"relaxation|relaxing|mindful\w*|anti[- ]stress)\b", phrase.lower()):
        return "adults"
    return "kids"
