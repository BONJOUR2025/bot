import pandas as pd
import asyncio
from pathlib import Path
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.analytics import AnalyticsService
from app import config


def create_sales_file(path: Path):
    # Create dataframe with at least 9 columns to match usecols "A,B,E,G,I"
    rows = [
        ["2024-01", "001", None, None, "Alice", None, "Shampoo", None, 100],
        ["2024-02", "002", None, None, "Bob", None, "Conditioner", None, "200"],
        ["bad", "003", None, None, "Charlie", None, "Mask", None, 300],
        ["2024-03", "", None, None, "Dave", None, "Gel", None, 400],
        [None, None, None, None, None, None, None, None, None],
    ]
    df = pd.DataFrame(rows)
    df.to_excel(path, index=False, header=False)


def test_load_and_filter_sales(tmp_path, monkeypatch):
    file = tmp_path / "sales.xlsx"
    create_sales_file(file)
    monkeypatch.setattr(config, "SALES_FILE", str(file))
    from app.services import analytics
    monkeypatch.setattr(analytics, "SALES_FILE", str(file))
    svc = AnalyticsService()
    result = asyncio.run(svc.get_sales_details())
    assert result["count"] == 2
    assert len(result["items"]) == 2
    assert result["items"][0]["employee"] == "Alice"
    assert result["items"][1]["cost"] == 200

    result = asyncio.run(svc.get_sales_details(name_substr="cond"))
    assert result["count"] == 1
    assert result["items"][0]["item"] == "Conditioner"

    result = asyncio.run(svc.get_sales_details(page=2, page_size=1))
    assert result["page"] == 2
    assert result["pages"] == 2
    assert len(result["items"]) == 1


def test_sales_rating(tmp_path, monkeypatch):
    file = tmp_path / "sales.xlsx"
    create_sales_file(file)
    monkeypatch.setattr(config, "SALES_FILE", str(file))
    from app.services import analytics
    monkeypatch.setattr(analytics, "SALES_FILE", str(file))
    svc = AnalyticsService()

    rating = asyncio.run(svc.get_sales_rating())
    assert rating[0]["employee"] == "Bob"
    assert rating[0]["total"] == 200
    assert rating[1]["employee"] == "Alice"
    assert rating[1]["total"] == 100

    rating = asyncio.run(svc.get_sales_rating(date_to="2024-01-31"))
    assert len(rating) == 1
    assert rating[0]["employee"] == "Alice"
