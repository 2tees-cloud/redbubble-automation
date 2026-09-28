"""Автопилот: одна книга в день без участия человека.

research → pages → interior → cover (+ метаданные) → upload → done

Состояние запуска — data/runs/<id>.json, каждый шаг идемпотентен. Если шаг упал из-за лимитов
бесплатных API, капчи Amazon или KDP, запуск ждёт («waiting») и продолжается при следующем
вызове: незаконченная книга всегда доделывается раньше, чем начинается новая.
Все события уходят в core.notify (ntfy/Telegram).
"""
import datetime as dt
import json
import logging
import math
import os
import time
from pathlib import Path

from . import assemble, book, kdp, notify, pipeline, research, safety
from .base import AllProvidersFailed

log = logging.getLogger("autopilot")
ROOT = Path(__file__).resolve().parent.parent
STEPS = ["research", "pages", "interior", "cover", "upload", "done"]


class Run:
    def __init__(self, path: Path, data: dict):
        self.path, self.data = path, data

    @classmethod
    def load(cls, path: Path) -> "Run":
        return cls(path, json.loads(path.read_text(encoding="utf-8")))

    def save(self) -> None:
        self.data["updated"] = dt.datetime.now().isoformat(timespec="seconds")
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def __getitem__(self, k):
        return self.data.get(k)

    def __setitem__(self, k, v):
        self.data[k] = v


class Lock:
    """Не даёт запустить два автопилота сразу (планировщик + ручной запуск)."""

    def __init__(self, path: Path, stale_hours: float = 6):
        self.path, self.stale = path, stale_hours * 3600

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and time.time() - self.path.stat().st_mtime < self.stale:
            raise RuntimeError(f"автопилот уже работает (lock {self.path}); если это не так — удалите файл")
        self.path.write_text(str(os.getpid()))
        return self

    def __exit__(self, *exc):
        self.path.unlink(missing_ok=True)


class Autopilot:
    def __init__(self, cfg: dict, text, image, *, data_dir: Path = ROOT / "data", out_dir: Path = ROOT / "out",
                 amazon: research.AmazonClient | None = None, uploader_factory=None, today: dt.date | None = None):
        self.cfg, self.text, self.image = cfg, text, image
        self.acfg = cfg.get("autopilot") or {}
        self.kcfg = {**(cfg.get("kdp") or {})}
        self.kcfg.setdefault("email", os.getenv("KDP_EMAIL", ""))
        self.kcfg.setdefault("password", os.getenv("KDP_PASSWORD", ""))
        self.data_dir, self.out_dir = Path(data_dir), Path(out_dir)
        self.runs_dir = self.data_dir / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.today = today or dt.date.today()
        self.history = research.History(self.data_dir / "history.json")
        self.amazon = amazon or research.AmazonClient(
            self.data_dir / "cache", domain=(cfg.get("research") or {}).get("domain", "www.amazon.com"))
        self.uploader_factory = uploader_factory or (lambda: kdp.KdpUploader(self.kcfg))
        self.moderation_required = (cfg.get("safety") or {}).get("llm_required", True)
        safety.configure(cfg.get("safety"))

    # --- выбор запуска --------------------------------------------------------------
    def _runs(self) -> list[Run]:
        return [Run.load(p) for p in sorted(self.runs_dir.glob("*.json"))]

    def pick_run(self, force: bool = False) -> Run | None:
        """Незаконченная книга → её; иначе новая, если сегодня ещё не делали (или force)."""
        runs = self._runs()
        for r in runs:
            if r["status"] in ("running", "waiting"):
                return r
        if not force and any(r["id"].startswith(self.today.isoformat()) and r["status"] == "done" for r in runs):
            return None
        rid = self.today.isoformat()
        n = 1
        while (self.runs_dir / f"{rid}.json").exists():
            n += 1
            rid = f"{self.today.isoformat()}-{n}"
        run = Run(self.runs_dir / f"{rid}.json", {"id": rid, "status": "running", "step": "research",
                                                    "started": dt.datetime.now().isoformat(timespec="seconds"),
                                                    "upload_attempts": 0, "log": []})
        run.save()
        return run

    # --- шаги ------------------------------------------------------------------------------
    def _log(self, run: Run, msg: str) -> None:
        log.info("[%s] %s", run["id"], msg)
        run["log"] = (run["log"] or [])[-50:] + [f"{dt.datetime.now():%H:%M} {msg}"]
        run.save()

    def _advance(self, run: Run, step: str) -> None:
        run["step"] = STEPS[STEPS.index(step) + 1]
        run.save()

    def step_research(self, run: Run) -> bool:
        plan, _ = research.research(amazon=self.amazon, text_router=self.text, history=self.history,
                                    rc=research.ResearchConfig.from_config(self.cfg.get("research")),
                                    report_dir=self.data_dir / "research", keepa=research.keepa_from_env(),
                                    today=self.today, moderation_required=self.moderation_required)
        if not plan:
            run["status"] = "failed"
            run["error"] = "не найдено подходящей ниши"
            self._log(run, run["error"])
            notify.send("KDP: ниша не найдена", "Сегодня книга не делается. Отчёт: data/research/", priority="high")
            return False
        run["plan"] = plan
        run["book_dir"] = str(self.out_dir / f"{run['id']}_{pipeline._slug(plan['phrase'], 30)}")
        self._log(run, f"ниша: {plan['phrase']} (оценка {plan['niche']['score']}, {plan['niche']['confidence']})")
        self._advance(run, "research")
        return True

    def step_pages(self, run: Run) -> bool:
        plan, bdir = run["plan"], Path(run["book_dir"])
        prof, pp_cfg, lim = pipeline.resolve(self.cfg, plan["audience"])
        min_images = math.ceil(book.MIN_PAGES / 2) if (self.cfg.get("book") or {}).get("blank_backs", True) \
            else book.MIN_PAGES
        min_images = max(min_images, int(self.acfg.get("min_images", 20)))
        target = max(int(plan["pages"]), min_images)  # не меньше минимума KDP
        for _ in range(2):
            d = pipeline.make_pages(self.text, self.image, theme=plan["theme"], count=target,
                                    out_dir=bdir, age=plan.get("age") or "4-8", audience=plan["audience"],
                                    profile=prof, pp_cfg=pp_cfg, limits=lim,
                                    use_vision=self.acfg.get("vision", True))
            if len(d["accepted"]) >= min_images:
                break
            # сюжеты кончились, а страниц мало — один раз придумываем новые сюжеты
            d.pop("subjects", None)
            pipeline.Manifest.write(bdir / "manifest.json", d)
        d["trim"] = plan["trim"]
        pipeline.Manifest.write(bdir / "manifest.json", d)
        if len(d["accepted"]) < min_images:
            run["status"] = "failed"
            run["error"] = f"принято только {len(d['accepted'])} страниц из нужных {min_images}"
            self._log(run, run["error"])
            notify.send("KDP: мало качественных страниц", f"{plan['phrase']}: {run['error']}", priority="high")
            return False
        self._log(run, f"страниц принято: {len(d['accepted'])}, брак: {len(d['rejected'])}")
        self._advance(run, "pages")
        return True

    def step_interior(self, run: Run) -> bool:
        res = assemble.interior(Path(run["book_dir"]), self.cfg)
        run["interior_pages"] = res["page_count"]
        self._log(run, f"интерьер: {res['page_count']} стр.")
        self._advance(run, "interior")
        return True

    def step_cover(self, run: Run) -> bool:
        try:
            meta, warn, res = assemble.meta_and_cover(
                Path(run["book_dir"]), self.cfg, self.text, author=self.acfg.get("author", ""),
                paper=self.kcfg.get("paper", "white"), strict=True,
                seed=int(time.time()) % 1000, moderation_required=self.moderation_required)
        except assemble.UnsafeMetadata as e:
            run["status"] = "failed"
            run["error"] = f"метаданные небезопасны: {e}"
            self._log(run, run["error"])
            notify.send("KDP: книга остановлена", run["error"], priority="high")
            return False
        if not meta.get("author"):
            run["status"] = "failed"
            run["error"] = "не задан автор (autopilot.author в config.yaml)"
            self._log(run, run["error"])
            notify.send("KDP: нужна настройка", run["error"], priority="high")
            return False
        run["title"] = meta["title"]
        self._log(run, f"обложка и метаданные: «{meta['title']}»" + (f", предупреждения: {len(warn)}" if warn else ""))
        self._advance(run, "cover")
        return True

    def _publish_now(self) -> bool:
        if not self.kcfg.get("publish", True):
            return False
        if self.kcfg.get("first_run_draft", True):
            # первая книга — черновиком: убедиться глазами, что робот заполнил KDP правильно
            return any(h.get("kdp") in ("published", "draft") for h in self.history.items)
        return True

    def step_upload(self, run: Run) -> bool:
        bdir = Path(run["book_dir"])
        plan = run["plan"]
        meta = json.loads((bdir / "metadata.json").read_text(encoding="utf-8"))["meta"]
        cats = (self.kcfg.get("categories") or {}).get(plan["audience"], [])
        publish = self._publish_now()
        run["upload_attempts"] = (run["upload_attempts"] or 0) + 1
        run.save()
        try:
            with self.uploader_factory() as up:
                st = up.upload(bdir, meta=meta, interior=bdir / "interior.pdf", cover=bdir / "cover.pdf",
                               trim=book.parse_trim(plan["trim"]), pages=int(run["interior_pages"]),
                               categories=cats, publish=publish)
        except kdp.NeedsHuman as e:
            run["status"] = "waiting"
            run["error"] = str(e)
            self._log(run, run["error"])
            notify.send("KDP: нужен вход", f"{e}\nКнига готова и ждёт: {bdir}", priority="high")
            return False
        except kdp.KdpError as e:
            limit = int(self.acfg.get("max_upload_attempts", 3))
            run["status"] = "failed" if run["upload_attempts"] >= limit else "waiting"
            run["error"] = str(e)
            self._log(run, run["error"])
            notify.send("KDP: ошибка загрузки",
                        f"{e}\nПопытка {run['upload_attempts']}/{limit}. Селекторы: kdp_selectors.yaml",
                        priority="high")
            return False
        run["kdp"] = st
        self._log(run, f"KDP: {st['result']}, цена ${st['price']}")
        self._advance(run, "upload")
        return True

    def step_done(self, run: Run) -> bool:
        plan, st = run["plan"], run["kdp"] or {}
        self.history.add(phrase=plan["phrase"], theme=plan["theme"], title=run["title"], book_dir=run["book_dir"],
                         kdp=st.get("result"), price=st.get("price"), run=run["id"])
        run["status"] = "done"
        run.save()
        what = "отправлена на проверку KDP" if st.get("result") == "published" else \
            "сохранена ЧЕРНОВИКОМ — проверьте в KDP и нажмите Publish (дальше будет автоматически)"
        notify.send("KDP: книга готова", f"«{run['title']}» {what}.\nНиша: {plan['phrase']}")
        return True

    # --- запуск --------------------------------------------------------------------------------
    def run(self, force: bool = False) -> Run | None:
        with Lock(self.data_dir / "autopilot.lock"):
            run = self.pick_run(force)
            if run is None:
                log.info("книга на сегодня уже сделана")
                return None
            run["status"] = "running"
            run.save()
            while run["status"] == "running":
                step = run["step"]
                try:
                    if not getattr(self, f"step_{step}")(run):
                        break
                except AllProvidersFailed as e:
                    run["status"] = "waiting"
                    run["error"] = f"{step}: лимиты бесплатных API — продолжу при следующем запуске"
                    self._log(run, f"{run['error']} ({str(e).splitlines()[0]})")
                    notify.send("KDP: пауза", run["error"], priority="low")
                    break
                except Exception as e:  # noqa: BLE001 — неожиданное: не теряем прогресс, сообщаем
                    errs = run["errors"] or {}
                    errs[step] = errs.get(step, 0) + 1
                    run["errors"] = errs
                    # одна и та же ошибка 3 раза подряд — не зацикливаемся, книгу бросаем
                    run["status"] = "failed" if errs[step] >= 3 else "waiting"
                    run["error"] = f"{step}: {type(e).__name__}: {e}"
                    self._log(run, run["error"])
                    notify.send("KDP: сбой автопилота", run["error"], priority="high")
                    log.exception("шаг %s упал", step)
                    break
            return run
