import json

import pytest

from kpi_sync.envelope import KpiStore
from kpi_sync.pollers.ams_keymetrics import AmsKeyMetricsPoller
from kpi_sync.ratelimiter import AsyncRateLimiter
from kpi_sync.tests.conftest import FakeResponse, FakeSession

# Captured live from ams.ciphex.io on 2026-07-20.
KEY_METRICS_FIXTURE = {
    "metrics": [
        {"id": "mx_drawdown", "label": "YE 2025 - MDD", "value": -11.46, "valueType": "percentage"},
        {"id": "ytd_rtn", "label": "YTD - Return", "value": 15.06, "valueType": "percentage"},
    ],
    "lastUpdated": "2026-07-20T17:00:46.684Z",
}

PUBLIC_METRICS_FIXTURE = {
    "range": "'public-metrics'!A1:AH1000",
    "majorDimension": "ROWS",
    "values": [
        ["latestDate", "drawdown", "ytdResults"],
        ["7-10-26 3:00 PM", "-11.46%", "1.18%"],
    ],
}

PUBLIC_CHARTS_FIXTURE = {
    "range": "'public-charts'!A1:V1000",
    "majorDimension": "ROWS",
    "values": [
        ["date", "totalReturn", "hitBuys"],
        ["5-25-25 2:00 PM", "--"],
        ["8-22-25 2:00 PM", "-3.59%", "119"],
    ],
}


@pytest.mark.asyncio
async def test_ams_keymetrics_poller_writes_all_three_sources_with_correct_as_of(fake_redis):
    store = KpiStore(fake_redis)
    session = FakeSession(
        [
            FakeResponse(200, json_body=KEY_METRICS_FIXTURE),
            FakeResponse(200, json_body=PUBLIC_METRICS_FIXTURE),
            FakeResponse(200, json_body=PUBLIC_CHARTS_FIXTURE),
        ]
    )
    limiter = AsyncRateLimiter(max_calls=8, period_s=60.0)
    poller = AmsKeyMetricsPoller(store, session, limiter)

    await poller.fetch_and_store()

    key_metrics = json.loads(await fake_redis.get("kpi:ams_keymetrics:key_metrics"))
    assert key_metrics["value"] == KEY_METRICS_FIXTURE["metrics"]
    assert key_metrics["as_of"] == "2026-07-20T17:00:46.684Z"

    public_metrics = json.loads(await fake_redis.get("kpi:ams_keymetrics:public_metrics"))
    assert public_metrics["value"] == {
        "latestDate": "7-10-26 3:00 PM",
        "drawdown": "-11.46%",
        "ytdResults": "1.18%",
    }
    assert public_metrics["as_of"] == "2026-07-10T15:00:00"

    public_charts = json.loads(await fake_redis.get("kpi:ams_keymetrics:public_charts"))
    assert public_charts["value"] == [
        {"date": "5-25-25 2:00 PM", "totalReturn": "--", "hitBuys": None},
        {"date": "8-22-25 2:00 PM", "totalReturn": "-3.59%", "hitBuys": "119"},
    ]
    # as_of comes from the *last* row (most recent date), not the first.
    assert public_charts["as_of"] == "2025-08-22T14:00:00"
