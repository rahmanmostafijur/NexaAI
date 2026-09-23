import pytest

from app.agent.heuristics import classify
from app.agent.types import Route
from app.sql.schema_retriever import keyword_hits


@pytest.mark.parametrize(
    ("question", "route"),
    [
        ("How many orders were placed last month?", Route.SQL),
        ("How many refunds happened last month?", Route.SQL),
        ("Which category generated the most revenue?", Route.SQL),
        ("Who are our highest-value customers?", Route.SQL),
        ("What is our refund policy?", Route.RAG),
        ("What is the refund period?", Route.RAG),
        ("What does the warranty policy say?", Route.RAG),
        ("Explain what a database index is.", Route.GENERAL),
        ("What is FastAPI?", Route.GENERAL),
        (
            "Which product had the highest number of returns, and what does our return "
            "policy say about it?",
            Route.HYBRID,
        ),
        ("গত ৩ মাসে কোন product সবচেয়ে বেশি বিক্রি হয়েছে?", Route.SQL),
        ("আমাদের return policy কী?", Route.RAG),
        ("employee leave policy কী?", Route.RAG),
        ("Kon product shobcheye beshi sell hoise?", Route.SQL),
    ],
)
def test_heuristic_routes(question: str, route: Route) -> None:
    assert classify(question).route == route


def test_signals_are_explainable() -> None:
    result = classify("How many orders were returned last month?")
    signals = result.as_signals()
    assert "returns" in signals["matched_tables"]
    assert signals["heuristic_route"] == "SQL"
    assert 0 < result.confidence <= 0.9


def test_keyword_hits_respect_word_boundaries() -> None:
    assert keyword_hits("order history", ["order"]) == 1
    assert keyword_hits("disorder", ["order"]) == 0
    assert keyword_hits("গত মাসে বিক্রি", ["বিক্রি"]) == 1
