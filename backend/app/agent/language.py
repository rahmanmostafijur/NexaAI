"""Deterministic language detection for English, Bengali, Banglish and mixed text.

A rule-based detector is fast, free and fully testable, and it is accurate for
this problem: Bengali script is identified by its Unicode block, and Banglish
(Bengali written in Latin letters) by a lexicon of very common romanised words.
"""

from __future__ import annotations

import re

from app.agent.types import LanguageInfo

_BENGALI_CHAR = re.compile(r"[ঀ-৿]")
_LETTER = re.compile(r"[A-Za-zঀ-৿]")
_LATIN_WORD = re.compile(r"[A-Za-z]+")

# Frequent romanised Bengali words. Ambiguous short English words ("a", "to", "ki"
# is fine) are deliberately excluded.
BANGLISH_LEXICON = frozenset(
    """
    ki kii koto kotota kon konta kothay kothai keno kemon kivabe kibhabe kokhon
    ache achhe asen achen nai nei hoise hoyeche hoyse hoyechhe hocche hoche hobe hoy hoini
    chilo chhilo chila korbo korte kore koro korsi korechi korchi bolo bolen bolun dekhao dekhan
    amar amader apnar apnader tomar tomader tar tader eta ota ekta ei oi shei sei
    gula gulo guli ta ti er ke theke pore age mash masher bochor bochore bochorer din diner
    shob sob shobcheye sobcheye shobche beshi kom bikri taka tk dam ekhon jonno niye abar
    kintu ar ba na haan hya ji bhai vai apu ektu onek kichu kotojon kotogula sathe diye
    pawa pabo pai jay jai lagbe lage parbo parben dorkar chai chaai janao jante janben
    kinse kinechhe kinlo kinbo bechi becha ferot shubidha niyom niti chuti mot gorbo
    """.split()
)

LABELS = {"en": "English", "bn": "Bengali", "banglish": "Banglish", "mixed": "Bengali + English"}


def detect_language(text: str) -> LanguageInfo:
    letters = _LETTER.findall(text)
    bengali = _BENGALI_CHAR.findall(text)
    ratio = len(bengali) / len(letters) if letters else 0.0
    latin_words = [w.lower() for w in _LATIN_WORD.findall(text)]

    if bengali:
        # Bengali script with (almost) no Latin words is Bengali; otherwise mixed.
        code = "bn" if ratio >= 0.85 and len(latin_words) <= 1 else "mixed"
        return LanguageInfo(code, LABELS[code], round(ratio, 3))  # type: ignore[arg-type]

    if latin_words:
        hits = sum(1 for word in latin_words if word in BANGLISH_LEXICON)
        if hits >= 2 and hits / len(latin_words) >= 0.25:
            return LanguageInfo("banglish", LABELS["banglish"], 0.0)
        if hits == 1 and len(latin_words) <= 3:
            return LanguageInfo("banglish", LABELS["banglish"], 0.0)
    return LanguageInfo("en", LABELS["en"], round(ratio, 3))
