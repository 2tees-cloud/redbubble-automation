"""Фильтр опасных тем: то, за что KDP блокирует книги и аккаунты.

Главные причины банов у AI-раскрасок:
  - чужие бренды и персонажи (Disney, Pokémon, Bluey…) — нарушение прав, самая частая причина блокировки;
  - реальные люди и знаменитости;
  - взрослый/жестокий/политический контент в раскрасках, особенно рядом с детской аудиторией.

Два уровня: 1) список запрещённых слов — бесплатно и мгновенно; 2) LLM-модерация — ловит то,
чего нет в списке (новый мультфильм, знаменитость, завуалированный бренд). При сомнениях — «нет»:
пропустить одну нишу дешевле, чем потерять аккаунт.
"""
import logging
import re

from .base import AllProvidersFailed

log = logging.getLogger("safety")

# Бренды, франшизы и персонажи, популярные в поиске раскрасок. Дополняется в config.yaml → safety.extra_terms
TRADEMARKS = [
    "disney", "pixar", "marvel", "dc comics", "star wars", "mickey", "minnie", "frozen elsa", "elsa and anna", "olaf",
    "moana", "encanto", "toy story", "lilo and stitch", "winnie the pooh", "princess jasmine",
    "ariel", "pokemon", "pokémon", "pikachu", "bluey", "peppa pig", "paw patrol", "spiderman", "spider-man",
    "batman", "superman", "avengers", "hulk", "barbie", "hello kitty", "sanrio", "kuromi", "my melody",
    "cinnamoroll", "minecraft", "roblox", "fortnite", "sonic the hedgehog", "super mario", "luigi", "nintendo",
    "zelda", "kirby", "harry potter", "hogwarts", "lego", "hot wheels", "transformers", "my little pony",
    "sesame street", "cocomelon", "baby shark", "squishmallow", "labubu", "gabby's dollhouse", "care bears",
    "smurfs", "garfield", "snoopy", "charlie brown", "scooby", "looney tunes", "bugs bunny", "spongebob",
    "ninja turtles", "tmnt", "power rangers", "dragon ball", "naruto", "one piece", "demon slayer",
    "jujutsu kaisen", "ghibli", "totoro", "dr seuss", "dr. seuss", "grinch", "jurassic park",
    "jurassic world", "godzilla", "wednesday addams", "bratz", "lol surprise", "shopkins", "poppy playtime",
    "huggy wuggy", "skibidi", "five nights at freddy", "fnaf", "hello neighbor", "kpop demon hunters",
    "stranger things", "taylor swift", "nfl", "nba", "fifa", "nascar", "coca-cola", "coca cola", "nike",
    "adidas", "hatsune miku", "sailor moon", "hunger games", "lord of the rings", "hobbit",
    "game of thrones", "simpsons", "family guy", "rick and morty", "thomas the tank",
    "paddington", "peter rabbit", "curious george", "clifford", "daniel tiger", "blippi", "ms rachel",
    "bing bong", "super wings", "pj masks", "doc mcstuffins", "sofia the first", "vampirina",
]

# Содержимое, неуместное для раскрасок на KDP (или требующее пометки «для взрослых»)
CONTENT = [
    r"sex\w*", r"erotic\w*", r"nud(e|ity)", r"naked", r"nsfw", r"porn\w*", r"fetish\w*", r"lingerie",
    r"gore", r"blood(y|shed)?", r"murder\w*", r"serial killer\w*", r"torture", r"suicide", r"self[- ]harm",
    r"guns?", r"rifles?", r"weapons?", r"nazi\w*", r"swastika", r"terror\w*",
    r"weed", r"cannabis", r"marijuana", r"stoner", r"drugs?", r"cocaine", r"psychedelic",
    r"swear\w*", r"cuss\w*", r"curse words?", r"profan\w*", r"f\*?ck\w*", r"shit\w*", r"bitch\w*",
    r"trump", r"biden", r"democrat\w*", r"republican\w*", r"maga", r"election",
    r"jesus", r"bible", r"quran", r"allah",  # религиозные книги возможны, но автоматом не делаем
]


def _pattern(terms: list[str], regex: bool = False) -> re.Pattern:
    alts = terms if regex else [re.escape(t) for t in terms]
    return re.compile(r"(?<![a-z0-9])(" + "|".join(alts) + r")(?![a-z0-9])", re.I)


_TM = _pattern(TRADEMARKS)
_CONTENT = _pattern(CONTENT, regex=True)
_EXTRA: re.Pattern | None = None


def configure(cfg: dict | None) -> None:
    """Дополнительные запрещённые слова из config.yaml → safety.extra_terms."""
    global _EXTRA
    extra = (cfg or {}).get("extra_terms") or []
    _EXTRA = _pattern([str(t) for t in extra]) if extra else None


def blocked_terms(text: str) -> list[str]:
    """Найденные запрещённые слова (пусто — чисто)."""
    found = [m.group(0) for p in (_TM, _CONTENT, _EXTRA) if p for m in p.finditer(text or "")]
    return sorted({f.lower() for f in found})


MODERATION_PROMPT = """You check themes for print-on-demand coloring books sold on Amazon KDP.
Reject (safe=false) if ANY of these is true:
- mentions or clearly implies a trademark, brand, franchise, fictional character owned by a company,
  sports league or team, video game, TV show, movie, band or a real person/celebrity;
- sexual, violent, gory, hateful, political, religious, drug or profanity content;
- medical or therapeutic claims ("cures anxiety", "for ADHD treatment");
- anything likely to be rejected by Amazon content guidelines.
Generic public-domain topics (animals, flowers, mandalas, vehicles, holidays, fairy tales, dinosaurs,
occupations) are safe.
Items:
{items}
Answer JSON: {{"results": [{{"item": "...", "safe": true/false, "reason": "short, empty if safe"}}]}}"""


def moderate(items: list[str], text_router, *, required: bool = True) -> dict[str, str]:
    """Проверка списка фраз. Возвращает {фраза: причина} для отклонённых (пусто — всё чисто).
    required=True: если модель недоступна или ответила непонятно — отклоняем всё (fail-closed)."""
    rejected = {}
    todo = []
    for it in items:
        if bad := blocked_terms(it):
            rejected[it] = "запрещённые слова: " + ", ".join(bad)
        else:
            todo.append(it)
    if not todo:
        return rejected
    try:
        res = text_router.chat_json(MODERATION_PROMPT.format(items="\n".join(f"- {t}" for t in todo)),
                                    temperature=0, max_tokens=1500)
    except AllProvidersFailed as e:
        log.warning("модерация недоступна: %s", str(e).splitlines()[0])
        if required:
            rejected.update({t: "модерация недоступна" for t in todo})
        return rejected
    data = res["data"] if isinstance(res["data"], dict) else {}
    verdicts = {str(r.get("item", "")).strip().lower(): r for r in data.get("results", []) if isinstance(r, dict)}
    for t in todo:
        v = verdicts.get(t.strip().lower())
        if v is None:
            if required:
                rejected[t] = "модель не дала вердикт"
        elif v.get("safe") is not True:
            rejected[t] = "модерация: " + str(v.get("reason") or "unsafe")
    return rejected
