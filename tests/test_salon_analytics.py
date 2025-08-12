import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.analytics import AnalyticsService
from app import config


def test_get_salon_analytics(tmp_path, monkeypatch):
    file = tmp_path / "salon.json"
    sample = {
        "mercury": [
            {
                "date": "2024-01-01",
                "visitors": 10,
                "revenue": 100,
                "deals": 2,
                "rpv": 10,
                "admin": "A",
            }
        ]
    }
    file.write_text(json.dumps(sample), encoding="utf-8")
    monkeypatch.setattr(config, "SALON_ANALYTICS_FILE", str(file))
    from app.services import analytics
    monkeypatch.setattr(analytics, "SALON_ANALYTICS_FILE", str(file))

    svc = AnalyticsService()
    data = asyncio.run(svc.get_salon_analytics("mercury"))
    assert len(data) == 1
    assert data[0]["visitors"] == 10
