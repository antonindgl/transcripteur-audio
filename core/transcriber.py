"""Transcription audio via Faster-Whisper (PyAV intégré : ffmpeg non requis)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from faster_whisper import WhisperModel

SUPPORTED_EXTENSIONS = ("mp3", "wav", "m4a", "flac", "ogg")
MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v3"]


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


def load_model(size: str = "small", device: str = "auto", compute_type: str = "int8") -> WhisperModel:
    """Charge (et télécharge au 1er usage) le modèle Whisper.

    `int8` divise la mémoire par ~3 par rapport à float32 (précision quasi identique) :
    indispensable sur un hébergement gratuit (~1 Go) et plus rapide sur processeur.
    """
    return WhisperModel(size, device=device, compute_type=compute_type, cpu_threads=2, num_workers=1)


def transcribe(
    model: WhisperModel,
    audio_path: str,
    language: Optional[str] = None,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> TranscriptionResult:
    """Transcrit un fichier. `language=None` active la détection automatique.

    `progress_cb` reçoit une valeur entre 0.0 et 1.0.
    """
    segments_iter, info = model.transcribe(
        audio_path,
        language=language,
        vad_filter=True,
        beam_size=5,
    )
    result = TranscriptionResult(
        language=info.language,
        language_probability=info.language_probability,
        duration=info.duration,
    )
    for seg in segments_iter:  # générateur : le décodage se fait ici
        text = seg.text.strip()
        if text:
            result.segments.append(Segment(seg.start, seg.end, text))
        if progress_cb and info.duration:
            progress_cb(min(seg.end / info.duration, 1.0))
    if progress_cb:
        progress_cb(1.0)
    return result
