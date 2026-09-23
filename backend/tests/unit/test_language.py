import pytest

from app.agent.language import detect_language


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Which product sold the most?", "en"),
        ("Show me total revenue for the last quarter.", "en"),
        ("What is the average age of our customers?", "en"),
        ("আমাদের রিটার্ন নীতি কী?", "bn"),
        ("গত মাসে মোট কতগুলো অর্ডার হয়েছে?", "bn"),
        ("কোন product সবচেয়ে বেশি বিক্রি হয়েছে?", "mixed"),
        ("গত ৩০ দিনে total sales কত?", "mixed"),
        ("গত মাসে কোন product er sales beshi chilo?", "mixed"),
        ("Kon product shobcheye beshi sell hoise?", "banglish"),
        ("amader return policy ki?", "banglish"),
        ("Dhaka te delivery koto din lage?", "banglish"),
        ("stock koto?", "banglish"),
    ],
)
def test_detects_language_variants(text: str, expected: str) -> None:
    assert detect_language(text).code == expected


def test_labels_and_ratio() -> None:
    info = detect_language("আমাদের নীতি")
    assert info.label == "Bengali"
    assert info.bengali_ratio == 1.0
    assert detect_language("hello world").as_dict() == {"code": "en", "label": "English"}


def test_empty_and_numeric_input_defaults_to_english() -> None:
    assert detect_language("").code == "en"
    assert detect_language("12345 ?!").code == "en"
