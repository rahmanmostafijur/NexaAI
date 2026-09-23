"""Deterministic, localised answers used when evidence is missing.

When retrieval finds nothing or the database cannot answer, the agent replies
with these fixed messages instead of asking the model, so it never
"fills the gap" with invented facts.
"""

from __future__ import annotations

_MESSAGES: dict[str, dict[str, str]] = {
    "no_documents": {
        "en": "I couldn't find this information in the available documents.",
        "bn": "দুঃখিত, উপলব্ধ ডকুমেন্টগুলোতে এই তথ্যটি খুঁজে পাইনি।",
        "banglish": "Sorry, available documents e ei tottho khuje pai ni.",
    },
    "no_data": {
        "en": "The database does not contain enough information to answer this question.",
        "bn": "ডাটাবেসে এই প্রশ্নের উত্তর দেওয়ার মতো যথেষ্ট তথ্য নেই।",
        "banglish": "Database e ei proshner uttor dewar moto jotheshto tottho nei.",
    },
    "sql_failed": {
        "en": "I couldn't build a safe, valid database query for this question. "
        "Please try rephrasing it with more detail.",
        "bn": "এই প্রশ্নের জন্য একটি নিরাপদ ও সঠিক ডাটাবেস কোয়েরি তৈরি করতে পারিনি। "
        "অনুগ্রহ করে প্রশ্নটি আরেকটু বিস্তারিতভাবে লিখুন।",
        "banglish": "Ei proshner jonno safe database query banate parini. "
        "Ektu details diye abar jiggesh korun.",
    },
    "nothing_found": {
        "en": "I couldn't find this information in the database or in the available documents.",
        "bn": "ডাটাবেস বা উপলব্ধ ডকুমেন্ট—কোথাও এই তথ্যটি খুঁজে পাইনি।",
        "banglish": "Database ba documents kothao ei tottho khuje pai ni.",
    },
}


def localized(key: str, language_code: str, reason: str | None = None) -> str:
    variants = _MESSAGES[key]
    language = "bn" if language_code == "mixed" else language_code
    text = variants.get(language, variants["en"])
    if reason and language == "en":
        text = f"{text}\n\n_{reason}_"
    return text
