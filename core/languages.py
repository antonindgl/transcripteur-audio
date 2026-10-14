"""Langues supportées (codes ISO 639-1 compris par Whisper et par Google Translate)."""

LANGUAGES: dict[str, str] = {
    "en": "Anglais",
    "fr": "Français",
    "es": "Espagnol",
    "zh": "Chinois",
    "de": "Allemand",
    "ja": "Japonais",
    "ar": "Arabe",
    "pt": "Portugais",
    "ru": "Russe",
    "hi": "Hindi",
    "bn": "Bengali",
    "it": "Italien",
    "ko": "Coréen",
    "tr": "Turc",
    "vi": "Vietnamien",
    "pl": "Polonais",
    "nl": "Néerlandais",
    "uk": "Ukrainien",
    "id": "Indonésien",
    "fa": "Persan",
    "sv": "Suédois",
    "el": "Grec",
    "he": "Hébreu",
    "th": "Thaï",
    "ur": "Ourdou",
}

# Codes de traduction qui diffèrent du code Whisper
_TRANSLATE_CODES = {"zh": "zh-CN", "he": "iw"}


def label(code: str) -> str:
    return f"{LANGUAGES.get(code, code)} ({code})"


def translate_code(code: str) -> str:
    return _TRANSLATE_CODES.get(code, code)
