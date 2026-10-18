"""Traitements en arrière-plan : une transcription (et sa traduction) continue même si la page est fermée.

Chaque travail est sauvegardé sur disque au fil de l'eau (segments, progression). Si le serveur
redémarre, le travail est marqué « interrompu » et peut être repris au dernier morceau terminé.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .transcriber import Segment, TranscriptionResult, load_model, transcribe_chunked
from .translator import translate_result

JOBS_DIR = Path(tempfile.gettempdir()) / "transcripteur_jobs"
ON_CLOUD = Path(__file__).resolve().as_posix().startswith("/mount/")
CPU_THREADS = 2 if ON_CLOUD else 0          # l'hébergement gratuit n'a que 2 cœurs partagés
CHUNK_SECONDS = 150.0 if ON_CLOUD else 300.0  # morceaux plus petits = moins de mémoire
BEAM_SIZE = 2 if ON_CLOUD else 5

_lock = threading.Lock()
_threads: dict[str, threading.Thread] = {}
_cancels: dict[str, threading.Event] = {}
_model_cache: dict = {}


@dataclass
class Job:
    id: str
    name: str
    audio_path: str
    model: str = "base"
    language: Optional[str] = None      # langue demandée (None = détection auto)
    target: Optional[str] = None        # langue de traduction (None = pas de traduction)
    status: str = "queued"              # queued | running | translating | done | error | cancelled | interrupted
    progress: float = 0.0
    duration: float = 0.0
    detected_language: str = ""
    probability: float = 0.0
    next_sample: int = 0                # borne du dernier morceau terminé (pour reprendre)
    segments: list = field(default_factory=list)    # [[début, fin, texte], ...]
    translated: list = field(default_factory=list)
    error: str = ""
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)

    # --- accès pratiques
    def result(self, translated: bool = False) -> TranscriptionResult:
        segs = self.translated if translated else self.segments
        return TranscriptionResult(
            segments=[Segment(*s) for s in segs],
            language=(self.target if translated else self.detected_language) or "",
            language_probability=1.0 if translated else self.probability,
            duration=self.duration,
        )

    @property
    def alive(self) -> bool:
        t = _threads.get(self.id)
        return bool(t and t.is_alive())

    def save(self) -> None:
        JOBS_DIR.mkdir(parents=True, exist_ok=True)
        self.updated = time.time()
        tmp = JOBS_DIR / f"{self.id}.json.tmp"
        tmp.write_text(json.dumps(self.__dict__), encoding="utf-8")
        os.replace(tmp, JOBS_DIR / f"{self.id}.json")


_jobs: dict[str, Job] = {}


def get_job(job_id: str) -> Optional[Job]:
    """Retrouve un travail (mémoire, sinon disque). Un travail orphelin devient « interrompu »."""
    if not job_id or not job_id.isalnum():
        return None
    job = _jobs.get(job_id)
    if job is None:
        path = JOBS_DIR / f"{job_id}.json"
        if not path.exists():
            return None
        try:
            job = Job(**json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return None
        _jobs[job_id] = job
    if job.status in ("queued", "running", "translating") and not job.alive:
        job.status = "interrupted"
        job.save()
    return job


def _get_model(size: str):
    """Un seul modèle gardé en mémoire à la fois (économie de RAM)."""
    with _lock:
        if _model_cache.get("size") != size:
            _model_cache.clear()
            _model_cache["model"] = load_model(size, cpu_threads=CPU_THREADS)
            _model_cache["size"] = size
        return _model_cache["model"]


def _cleanup_files(job: Job) -> None:
    for suffix in ("", ".pcm", ".pcm.part"):
        try:
            os.remove(job.audio_path + suffix)
        except OSError:
            pass


def _run(job: Job) -> None:
    cancel = _cancels[job.id]
    last_save = [time.time()]
    try:
        job.status, job.error = "running", ""
        if job.language and not job.detected_language:  # langue imposée : pas de détection
            job.detected_language, job.probability = job.language, 1.0
        job.save()
        model = _get_model(job.model)

        def on_info(d: dict):
            job.duration = d.get("duration", job.duration)
            if "language" in d:
                job.detected_language = d["language"]
                job.probability = d.get("probability", 0.0)

        def on_segment(seg: Segment):
            job.segments.append([seg.start, seg.end, seg.text])
            if time.time() - last_save[0] > 5:
                job.save()
                last_save[0] = time.time()

        def on_chunk_done(end: int, progress: float):
            job.next_sample = end
            job.progress = progress
            job.save()
            last_save[0] = time.time()

        finished = transcribe_chunked(
            model, job.audio_path, job.language or job.detected_language or None,
            chunk_s=CHUNK_SECONDS, beam_size=BEAM_SIZE, resume_sample=job.next_sample,
            cancel=cancel, on_info=on_info, on_segment=on_segment, on_chunk_done=on_chunk_done,
        )
        if not finished:
            job.status = "cancelled"
            job.save()
            return

        if job.target and job.segments and not job.translated:
            job.status = "translating"
            job.save()
            res = translate_result(
                job.result(), job.target,
                lambda p: setattr(job, "progress", p),
            )
            job.translated = [[s.start, s.end, s.text] for s in res.segments]
        job.progress, job.status = 1.0, "done"
        job.save()
        _cleanup_files(job)
    except Exception as e:  # noqa: BLE001
        job.status, job.error = "error", f"{type(e).__name__}: {e}"
        job.save()


def _launch(job: Job) -> None:
    _cancels[job.id] = threading.Event()
    t = threading.Thread(target=_run, args=(job,), daemon=True, name=f"job-{job.id}")
    _threads[job.id] = t
    t.start()


def start_job(audio_path: str, name: str, model: str, language: Optional[str],
              target: Optional[str]) -> Job:
    job = Job(id=uuid.uuid4().hex[:12], name=name, audio_path=audio_path, model=model,
              language=language, target=target)
    _jobs[job.id] = job
    job.save()
    _launch(job)
    return job


def resume_job(job: Job) -> None:
    """Reprend un travail interrompu ou en erreur au dernier morceau terminé."""
    if job.alive or not os.path.exists(job.audio_path):
        return
    _launch(job)


def cancel_job(job: Job) -> None:
    ev = _cancels.get(job.id)
    if ev:
        ev.set()


def can_resume(job: Job) -> bool:
    return job.status in ("interrupted", "error") and os.path.exists(job.audio_path)
