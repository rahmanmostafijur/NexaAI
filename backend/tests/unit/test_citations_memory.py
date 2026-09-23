from app.agent.citations import strip_citations, validate_citations
from app.agent.memory import format_history
from app.models import Message


def test_keeps_valid_citations_and_drops_fabricated_ones() -> None:
    check = validate_citations("Returns take 30 days [S1]. Refunds are fast [S7].", {"S1", "S2"})
    assert check.text == "Returns take 30 days [S1]. Refunds are fast."
    assert check.used == ["S1"]
    assert check.removed == ["S7"]


def test_normalises_grouped_and_lowercase_citations() -> None:
    check = validate_citations("Revenue was high [db1, s2; S3].", {"DB1", "S2"})
    assert check.text == "Revenue was high [DB1][S2]."
    assert check.used == ["DB1", "S2"]
    assert check.removed == ["S3"]


def test_citations_hidden_in_html_comments_are_made_visible() -> None:
    check = validate_citations(
        "Revenue was ৳500 <!-- [DB1] -->. Warranty is 3 months <!-- [S1][S9] -->.", {"DB1", "S1"}
    )
    assert check.text == "Revenue was ৳500 [DB1]. Warranty is 3 months [S1]."
    assert check.used == ["DB1", "S1"] and check.removed == ["S9"]
    assert validate_citations("A <!-- note --> b", set()).text == "A  b"


def test_fullwidth_bracket_citations_are_normalised() -> None:
    check = validate_citations("Top spender 【DB1】. Benefits 【S2†L4】 and 【S7】.", {"DB1", "S2"})
    assert check.text == "Top spender [DB1]. Benefits [S2] and."
    assert check.used == ["DB1", "S2"] and check.removed == ["S7"]


def test_strip_citations() -> None:
    assert strip_citations("A [S1] b [DB2].") == "A  b ."


def _message(role: str, content: str, details: dict | None = None) -> Message:
    return Message(role=role, content=content, details=details)


def test_history_includes_route_and_sql_for_follow_ups() -> None:
    history = format_history(
        [
            _message("user", "How many orders did we have last month?"),
            _message(
                "assistant",
                "842 orders.",
                {
                    "route": "SQL",
                    "sql": [
                        {
                            "sql": "SELECT COUNT(*) FROM orders WHERE order_date >= date_trunc('month', ...)"
                        }
                    ],
                },
            ),
        ],
        max_chars=2000,
    )
    assert history is not None
    lines = history.splitlines()
    assert lines[0] == "User: How many orders did we have last month?"
    assert "route=SQL" in lines[1] and "SELECT COUNT(*) FROM orders" in lines[1]


def test_history_is_bounded_and_keeps_newest_messages() -> None:
    messages = [_message("user", f"question {i} " + "x" * 80) for i in range(20)]
    history = format_history(messages, max_chars=400)
    assert history is not None
    assert len(history) <= 400 + 20
    assert "question 19" in history and "question 0 " not in history
    assert format_history([], 400) is None
