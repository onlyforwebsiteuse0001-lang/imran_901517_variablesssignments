"""Language layer: script detection, Roman-Urdu normalisation, transliteration hooks.

Why this exists: Roman Urdu has no orthographic standard — one word can be spelled
five ways ("kia / kya / kiya", "mujhe / mujhay / muje"). LLMs degrade badly on it.
A 2025 LoResMT paper reached Char-BLEU 96–97 on Urdu↔Roman-Urdu with a dedicated
m2m100 model, beating GPT-4o Mini — proof that "just let the LLM handle it" is not
good enough for the students we care about.

Everything here is stdlib-only and works offline. An external transliteration model
can be plugged in via `set_transliterator()`.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Callable, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Script detection
# ---------------------------------------------------------------------------

_ARABIC_RANGES = (
    (0x0600, 0x06FF),   # Arabic (incl. Urdu)
    (0x0750, 0x077F),   # Arabic supplement
    (0xFB50, 0xFDFF),   # Arabic presentation forms
    (0xFE70, 0xFEFF),   # Arabic presentation forms-B
)
_DEVANAGARI = ((0x0900, 0x097F),)


def detect_script(text: str) -> str:
    """Return one of: 'urdu', 'latin', 'devanagari', 'mixed', 'empty'."""
    if not text or not text.strip():
        return "empty"
    counts = {"urdu": 0, "latin": 0, "devanagari": 0}
    for ch in text:
        cp = ord(ch)
        if any(lo <= cp <= hi for lo, hi in _ARABIC_RANGES):
            counts["urdu"] += 1
        elif any(lo <= cp <= hi for lo, hi in _DEVANAGARI):
            counts["devanagari"] += 1
        elif ch.isalpha() and cp < 0x0250:
            counts["latin"] += 1
    total = sum(counts.values())
    if total == 0:
        return "empty"
    top = max(counts, key=counts.get)
    if counts[top] / total >= 0.7:
        return top
    return "mixed"


def is_urdu(text: str) -> bool:
    return detect_script(text) in ("urdu", "mixed")


# ---------------------------------------------------------------------------
# Roman-Urdu normalisation
# ---------------------------------------------------------------------------
# Canonicalise the highest-frequency spelling variants seen in Pakistani chat.
# Keyed on a word-boundary regex; values are canonical *latin* forms. This is
# deliberately conservative: only variants that are unambiguous are folded.

_ROMAN_VARIANTS: Dict[str, str] = {
    # question / what
    "kia": "kya", "kiya": "kya", "kyaa": "kya", "kiaa": "kya",
    "kyun": "kyu", "kyuun": "kyu", "kyon": "kyu", "q": "kyu",
    "kaise": "kese", "kaisay": "kese", "kese": "kese", "kesay": "kese",
    "kaun": "kon", "koun": "kon", "kon": "kon",
    "kab": "kab", "kub": "kab",
    "kahan": "kahan", "kaha": "kahan", "kahan pe": "kahan",
    # pronouns
    "mujhe": "mujhe", "mujhay": "mujhe", "muje": "mujhe", "mujhy": "mujhe",
    "tumhe": "tumhe", "tumhay": "tumhe", "tumhen": "tumhe",
    "apko": "aapko", "ap ko": "aapko", "aapko": "aapko",
    "mera": "mera", "mara": "mera",
    "hum": "hum", "hm": "hum",
    "ap": "aap", "aap": "aap",
    # verbs / auxiliaries
    "hy": "hai", "hae": "hai", "hai": "hai", "he": "hai",
    "hain": "hain", "hen": "hain", "hyn": "hain",
    "tha": "tha", "the": "the", "thi": "thi",
    "kr": "kar", "ker": "kar", "kar": "kar",
    "krna": "karna", "karna": "karna", "krnaa": "karna",
    "krta": "karta", "kerta": "karta",
    "kro": "karo", "karo": "karo",
    "ho": "ho", "hu": "ho",
    "hota": "hota", "huta": "hota",
    "chahiye": "chahiye", "chahye": "chahiye", "chaiye": "chahiye",
    "samajh": "samajh", "smjh": "samajh", "samjh": "samajh",
    "samajh nahi": "samajh nahi", "smjh ni": "samajh nahi",
    "nahi": "nahi", "ni": "nahi", "nhi": "nahi", "nae": "nahi",
    # study domain
    "parhai": "parhai", "parhayi": "parhai", "prhai": "parhai", "padhai": "parhai",
    "parhna": "parhna", "parh": "parh", "prh": "parh",
    "sawal": "sawal", "sawwal": "sawal", "question": "sawal",
    "jawab": "jawab", "jwab": "jawab",
    "teacher": "teacher", "sir": "sir", "mam": "maam", "maam": "maam",
    "test": "test", "paper": "paper", "exam": "exam", "imtehan": "exam",
    "tayari": "tayari", "tyari": "tayari",
    "mushkil": "mushkil", "mushkel": "mushkil", "mshkil": "mushkil",
    "aasan": "aasan", "asan": "aasan", "easy": "aasan",
    "thak": "thak", "thaka": "thaka",
    " motivate": "motivate", "motivat": "motivate",
    # misc high-frequency
    "acha": "acha", "achha": "acha", "accha": "acha", "theek": "theek",
    "thek": "theek", "thik": "theek", "tek": "theek",
    "zaroor": "zaroor", "zroor": "zaroor",
    "shukriya": "shukriya", "shukria": "shukriya", "thanks": "shukriya",
    "please": "please", "plz": "please", "pls": "please",
    "kuch": "kuch", "kch": "kuch",
    "bahut": "bahut", "bohot": "bahut", "boht": "bahut", "bht": "bahut",
    "bahot": "bahut",
    "matlab": "matlab", "mtlb": "matlab",
    "wapis": "wapis", "waps": "wapis",
    "kal": "kal", "kl": "kal",
    "aaj": "aaj", "aj": "aaj",
}

_COMPILED_VARIANTS = [
    (re.compile(r"\b" + re.escape(k) + r"\b", re.IGNORECASE), v)
    for k, v in sorted(_ROMAN_VARIANTS.items(), key=lambda kv: -len(kv[0]))
]

_REPEAT_CHARS = re.compile(r"(.)\1{2,}")          # "helloooo" -> "helloo"
_EXTRA_SPACE = re.compile(r"\s+")


def normalize_roman_urdu(text: str) -> str:
    """Fold Roman-Urdu spelling variants to canonical forms.

    This normalises *input* before reasoning. It never rewrites the student's own
    words back at them — output is generated in the student's chosen register.
    """
    if not text:
        return ""
    out = unicodedata.normalize("NFC", text)
    out = _REPEAT_CHARS.sub(r"\1\1", out)          # keep emphasis, drop spam
    for pattern, canonical in _COMPILED_VARIANTS:
        out = pattern.sub(canonical, out)
    return _EXTRA_SPACE.sub(" ", out).strip()


# ---------------------------------------------------------------------------
# Transliteration hook (optional, pluggable)
# ---------------------------------------------------------------------------

_transliterator: Optional[Callable[[str, str], str]] = None


def set_transliterator(fn: Optional[Callable[[str, str], str]]) -> None:
    """Register `fn(text, target_script) -> text`.

    Intended for a dedicated Urdu↔Roman-Urdu model (e.g. the LoResMT-2025 m2m100
    approach, Char-BLEU 96.37 / 97.44). Optional: the system runs fine without it.
    """
    global _transliterator
    _transliterator = fn


def transliterate(text: str, target: str = "ur") -> str:
    if _transliterator is None:
        return text
    try:
        return _transliterator(text, target)
    except Exception:
        return text


# ---------------------------------------------------------------------------
# Language profile + request normalisation
# ---------------------------------------------------------------------------

SUPPORTED_LANGUAGES = {
    "roman_urdu": "Roman Urdu (Latin script)",
    "urdu": "Urdu (Nastaliq)",
    "english": "English",
    "mixed": "Urdu + English mix (most common in Pakistani classrooms)",
}


def detect_language(text: str) -> str:
    """Best-effort guess of which register the student is writing in."""
    script = detect_script(text)
    if script in ("urdu",):
        return "urdu"
    if script in ("devanagari", "empty"):
        return "english"
    # Latin: Roman Urdu markers vs plain English
    lowered = " " + normalize_roman_urdu(text).lower() + " "
    markers = ["hai", "kya", "nahi", "mujhe", "kaise", "kyu", "karna", "parhai",
               "samajh", "acha", "theek", "bahut", "matlab", "chahiye", "hota"]
    hits = sum(1 for m in markers if f" {m} " in lowered)
    if hits >= 2:
        return "roman_urdu"
    if hits == 1:
        return "mixed"
    return "english"


def prepare_input(text: str) -> Tuple[str, str]:
    """Return (normalised_text, detected_language). Call this before any reasoning."""
    lang = detect_language(text)
    normalised = normalize_roman_urdu(text) if lang in ("roman_urdu", "mixed") else text
    return normalised, lang


# ---------------------------------------------------------------------------
# Language contract injected into every tutor prompt
# ---------------------------------------------------------------------------

LANGUAGE_CONTRACT = """LANGUAGE RULES (non-negotiable):
- Reply in the same register the student wrote in: {register}.
- Roman Urdu / Urdu + English mixing is normal and welcome. Do NOT "correct" the student's English.
- Use simple, spoken sentences. Short lines. No lecture tone.
- Explain technical terms in Urdu first, then give the English term in brackets.
- Never switch to formal English because the topic is academic.
"""
