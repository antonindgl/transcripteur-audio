"""Transcription audio via Faster-Whisper (PyAV intégré : ffmpeg non requis).

Les fichiers sont décodés en flux vers un fichier PCM 16 kHz sur disque, puis
transcrits par morceaux de quelques minutes (coupés aux silences). La mémoire reste
presque constante, quelle que soit la durée (1 h et plus).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:  # faster_whisper est chargé seulement au moment de transcrire (démarrage léger)
    from faster_whisper import WhisperModel

SUPPORTED_EXTENSIONS = ("mp3", "wav", "m4a", "flac", "ogg")
MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v3"]
SAMPLE_RATE = 16000


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class TranscriptionResult:
    segments: list[Segment] = field(default_factory=list)
    language: str = ""
    language_probability: float = 0.0
    duration: float = 0.0

    @property
    def text(self) -> str:
        return "\n".join(s.text for s in self.segments)


def load_model(size: str = "small", device: str = "auto", compute_type: str = "int8",
               cpu_threads: int = 0) -> WhisperModel:
    """Charge (et télécharge au 1er usage) le modèle Whisper.

    `int8` divise la mémoire par ~3 par rapport à float32 (précision quasi identique).
    `cpu_threads=0` utilise tous les cœurs ; l'hébergement gratuit en impose 2.
    """
    from faster_whisper import WhisperModel

    return WhisperModel(size, device=device, compute_type=compute_type,
                        cpu_threads=cpu_threads, num_workers=1)


# ------------------------------------------------------------------ décodage et découpe
def decode_to_pcm(audio_path: str, pcm_path: str) -> int:
    """Décode n'importe quel audio en PCM 16 kHz mono 16 bits, en flux (mémoire minimale).

    Retourne le nombre d'échantillons écrits.
    """
    import av

    resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    total = 0
    tmp = pcm_path + ".part"
    with av.open(audio_path) as container, open(tmp, "wb") as out:
        stream = container.streams.audio[0]
        for frame in container.decode(stream):
            for f in resampler.resample(frame):
                arr = f.to_ndarray().reshape(-1)
                out.write(arr.astype("<i2").tobytes())
                total += arr.shape[0]
        for f in resampler.resample(None):  # vide le tampon du rééchantillonneur
            arr = f.to_ndarray().reshape(-1)
            out.write(arr.astype("<i2").tobytes())
            total += arr.shape[0]
    os.replace(tmp, pcm_path)
    return total


def plan_chunks(pcm, chunk_s: float, search_s: float = 25.0) -> list[int]:
    """Bornes (en échantillons) de morceaux d'environ `chunk_s` secondes, coupés au silence."""
    import numpy as np

    n = len(pcm)
    size = int(chunk_s * SAMPLE_RATE)
    frame = SAMPLE_RATE // 5  # 0,2 s
    bounds = [0]
    while n - bounds[-1] > size * 1.2:
        target = bounds[-1] + size
        lo = max(bounds[-1] + frame, target - int(search_s * SAMPLE_RATE))
        seg = np.asarray(pcm[lo:target], dtype=np.float32)
        usable = (len(seg) // frame) * frame
        if usable < frame:
            bounds.append(target)
            continue
        energy = (seg[:usable].reshape(-1, frame) ** 2).mean(axis=1)
        bounds.append(lo + int(energy.argmin()) * frame + frame // 2)
    bounds.append(n)
    return bounds


def transcribe_chunked(
    model: WhisperModel,
    audio_path: str,
    language: Optional[str] = None,
    chunk_s: float = 240.0,
    beam_size: int = 5,
    resume_sample: int = 0,
    cancel=None,
    on_info: Optional[Callable[[dict], None]] = None,
    on_segment: Optional[Callable[[Segment], None]] = None,
    on_chunk_done: Optional[Callable[[int, float], None]] = None,
) -> bool:
    """Transcrit par morceaux. Retourne False si interrompu par `cancel`.

    `resume_sample` : borne de morceau déjà traitée (pour reprendre après une interruption).
    `on_chunk_done(fin_en_echantillons, progression)` est appelé après chaque morceau.
    """
    import numpy as np

    pcm_path = audio_path + ".pcm"
    if not os.path.exists(pcm_path):
        decode_to_pcm(audio_path, pcm_path)
    pcm = np.memmap(pcm_path, dtype="<i2", mode="r")
    n = len(pcm)
    duration = n / SAMPLE_RATE
    if on_info:
        on_info({"duration": duration})

    bounds = plan_chunks(pcm, chunk_s)
    if resume_sample > 0:
        # repart exactement à la position sauvegardée, quelle que soit la taille de morceau actuelle
        bounds = [resume_sample] + [x for x in bounds if x > resume_sample]
    lang = language
    for a, b in zip(bounds[:-1], bounds[1:]):
        if cancel is not None and cancel.is_set():
            return False
        if b - a >= SAMPLE_RATE * 0.3:
            audio = np.asarray(pcm[a:b], dtype=np.float32) / 32768.0
            segments, info = model.transcribe(
                audio, language=lang, vad_filter=True, beam_size=beam_size
            )
            if lang is None:  # la langue est détectée sur le premier morceau puis imposée
                lang = info.language
                if on_info:
                    on_info({"language": info.language, "probability": info.language_probability})
            offset = a / SAMPLE_RATE
            for seg in segments:  # générateur : le décodage se fait ici
                if cancel is not None and cancel.is_set():
                    return False
                text = seg.text.strip()
                if text and on_segment:
                    on_segment(Segment(offset + seg.start, offset + seg.end, text))
            del audio
        if on_chunk_done:
            on_chunk_done(b, b / n)
    return True


# ------------------------------------------------------------------ version simple (fichiers courts)
def transcribe(
    model: WhisperModel,
    audio_path: str,
    language: Optional[str] = None,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> TranscriptionResult:
    """Transcrit un fichier d'un bloc via les morceaux. `language=None` : détection automatique."""
    result = TranscriptionResult()

    def info(d: dict):
        result.duration = d.get("duration", result.duration)
        result.language = d.get("language", result.language)
        result.language_probability = d.get("probability", result.language_probability)

    try:
        transcribe_chunked(
            model, audio_path, language,
            on_info=info,
            on_segment=result.segments.append,
            on_chunk_done=(lambda end, p: progress_cb(p)) if progress_cb else None,
        )
    finally:
        pcm = audio_path + ".pcm"
        if os.path.exists(pcm):
            os.remove(pcm)
    if language and not result.language:
        result.language, result.language_probability = language, 1.0
    return result
