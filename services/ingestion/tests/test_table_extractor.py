import pytest
from pipeline.parsers.table_extractor import (
    markdown_table_to_json, generate_table_description
)


SAMPLE_MARKDOWN = """
| Quarter | Revenue | Growth |
|---------|---------|--------|
| Q1 2024 | $4.2M   | 12%    |
| Q2 2024 | $5.1M   | 21%    |
| Q3 2024 | $6.8M   | 33%    |
""".strip()


def test_markdown_table_to_json_basic():
    result = markdown_table_to_json(SAMPLE_MARKDOWN)
    assert result is not None
    assert result["headers"] == ["Quarter", "Revenue", "Growth"]
    assert len(result["rows"]) == 3
    assert result["rows"][0]["Quarter"] == "Q1 2024"
    assert result["rows"][2]["Growth"] == "33%"


def test_markdown_table_to_json_returns_none_for_invalid():
    assert markdown_table_to_json("no table here") is None
    assert markdown_table_to_json("") is None
    assert markdown_table_to_json("| only one row |") is None


def test_generate_table_description_contains_key_info():
    table_dict = markdown_table_to_json(SAMPLE_MARKDOWN)
    desc = generate_table_description(table_dict)
    assert "Quarter" in desc
    assert "Q3 2024" in desc
    assert "$6.8M" in desc or "6.8" in desc


def test_generate_table_description_with_caption():
    table_dict = {"headers": ["A", "B"], "rows": [{"A": "1", "B": "2"}], "caption": "Key Metrics"}
    desc = generate_table_description(table_dict)
    assert "Key Metrics" in desc
