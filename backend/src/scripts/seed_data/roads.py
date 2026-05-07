"""Scenario B — 평택 만세로·이화로 + 7-year traffic & population series.

The two roads expand on different schedules so the regression has two
independent time-series. Population is keyed to the abutting 행정동.
"""

from __future__ import annotations

from datetime import date
from typing import TypedDict


class RoadSegmentSeed(TypedDict):
    name: str
    route_no: str | None
    region_code: str
    line: list[tuple[float, float]]      # ordered (lon, lat) waypoints
    length_m: float
    description: str
    source: str
    abutting_admin_codes: list[str]
    stages: list[dict[str, object]]      # {stage, occurred_at, lanes_before, lanes_after}


ROADS: list[RoadSegmentSeed] = [
    {
        "name": "평택 만세로",
        "route_no": "지방도 70호",
        "region_code": "41220",
        "line": [
            (127.0644, 37.0099),
            (127.0823, 36.9803),
            (127.1128, 36.9921),
        ],
        "length_m": 7600.0,
        "description": "이충동 ~ 비전동 4단계 확장 구간.",
        "source": "validation:PT-MS-001",
        "abutting_admin_codes": ["4122010100", "4122010200", "4122010400", "4122010500"],
        "stages": [
            {"stage": "planned", "occurred_at": date(2017, 5, 1),
             "lanes_before": 2, "lanes_after": 4},
            {"stage": "design", "occurred_at": date(2018, 6, 1),
             "lanes_before": 2, "lanes_after": 4},
            {"stage": "under_construction", "occurred_at": date(2020, 4, 1),
             "lanes_before": 2, "lanes_after": 4},
            {"stage": "completed", "occurred_at": date(2023, 11, 30),
             "lanes_before": 2, "lanes_after": 4},
        ],
    },
    {
        "name": "평택 이화로",
        "route_no": "지방도 82호",
        "region_code": "41220",
        "line": [
            (127.0823, 36.9803),
            (127.0997, 36.9820),
            (127.1128, 36.9921),
        ],
        "length_m": 4200.0,
        "description": "동삭동 ~ 지산동 확장.",
        "source": "validation:PT-IH-001",
        "abutting_admin_codes": ["4122010200", "4122010300"],
        "stages": [
            {"stage": "planned", "occurred_at": date(2017, 9, 1),
             "lanes_before": 2, "lanes_after": 4},
            {"stage": "under_construction", "occurred_at": date(2019, 3, 1),
             "lanes_before": 2, "lanes_after": 4},
            {"stage": "completed", "occurred_at": date(2022, 6, 30),
             "lanes_before": 2, "lanes_after": 4},
        ],
    },
]
