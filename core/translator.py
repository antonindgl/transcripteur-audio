"""Traduction segment par segment (conserve les timecodes pour le SRT).

Utilise Google Translate via deep-translator : connexion Internet requise.
Les segments sont regroupés en peu de requêtes (une ligne = un segment) pour
rester sous la limite de Google, avec nouvelle tentative en cas de refus.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from .languages import translate_code
from .transcriber import Segment, TranscriptionResult

MAX_CHARS = 3500      # Google refuse ~5000 caractères par requête
MAX_LINES = 40
RETRIES = 5
PAUSE = 0.6           # secondes entre deux requêtes


def _call(translator, text: str) -> str:
    """Une requête, avec attente croissante si Google limite le débit."""
    from deep_translator.exceptions import RequestError, TooManyRequests

    for attempt in range(RETRIES):
        try:
            return translator.translate(text) or ""
        except (TooManyRequests, RequestError):
            if attempt == RETRIES - 1:
                raise
            time.sleep(2 * (attempt + 1))
    return ""


def _translate_lines(translator, lines: list[str]) -> list[str]:
    """Traduit des lignes en une requête ; si l'alignement se perd, une par une."""
    joined = "\n".join(lines)
    out = _call(translator, joined).split("\n")
    if len(out) == len(lines):
        return out
    result = []
    for line in lines:
        result.append(_call(translator, line))
        time.sleep(PAUSE)
    return result


def _groups(texts: list[str]):
    group, size = [], 0
    for i, t in enumerate(texts):
        if group and (size + len(t) > MAX_CHARS or len(group) >= MAX_LINES):
            yield group
            group, size = [], 0
        group.append(i)
        size += len(t) + 1
    if group:
        yield group


def translate_result(
    result: TranscriptionResult,
    target: str,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> TranscriptionResult:
    from deep_translator import GoogleTranslator

    source = translate_code(result.language) if result.language else "auto"
    translator = GoogleTranslator(source=source, target=translate_code(target))

    out = TranscriptionResult(
        language=target, language_probability=1.0, duration=result.duration
    )
    segs = result.segments
    texts = [" ".join(s.text.split()) for s in segs]  # une seule ligne par segment
    done = 0
    translated: list[str] = [""] * len(segs)
    for idx in _groups(texts):
        lines = _translate_lines(translator, [texts[i] for i in idx])
        for i, t in zip(idx, lines):
            translated[i] = t.strip() or texts[i]
        done += len(idx)
        if progress_cb:
            progress_cb(done / len(segs))
        time.sleep(PAUSE)
    for s, t in zip(segs, translated):
        out.segments.append(Segment(s.start, s.end, t))
    return out
