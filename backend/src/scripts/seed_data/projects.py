"""Scenario A — validation projects (PRD §14.2).

Four 호재 with their full lifecycle stages, used to drive compensation
impact regression. Geometry is approximated by a 2 km × 2 km bounding box
around the centroid; real polygons load via ETL.

Source dates are paraphrased from public 보도자료 / LH 보도자료. For seed
purposes we only need the relative timing to be correct.
"""

from __future__ import annotations

from datetime import date
from typing import TypedDict


class ProjectSeed(TypedDict):
    name: str
    project_type: str
    region_code: str
    centroid: tuple[float, float]      # (lon, lat)
    bbox_half_size_deg: float
    area_ha: float
    expected_compensation_billion_krw: float | None
    planned_announcement_date: date | None
    planned_completion_date: date | None
    description: str
    source: str
    stages: list[dict[str, object]]    # {stage, occurred_at, note}


PROJECTS: list[ProjectSeed] = [
    {
        "name": "김포 한강신도시",
        "project_type": "new_town",
        "region_code": "41280",
        "centroid": (126.6534, 37.6517),
        "bbox_half_size_deg": 0.025,
        "area_ha": 1086.0,
        "expected_compensation_billion_krw": 4500.0,
        "planned_announcement_date": date(2002, 11, 1),
        "planned_completion_date": date(2017, 12, 31),
        "description": "한강 이남 김포시 일대, LH·경기도시공사 공동 시행.",
        "source": "validation:KH-NT-001",
        "stages": [
            {"stage": "announced", "occurred_at": date(2002, 11, 1),
             "note": "지구지정 공고"},
            {"stage": "designated", "occurred_at": date(2006, 11, 30),
             "note": "지구계획 확정"},
            {"stage": "compensation_started", "occurred_at": date(2009, 6, 15),
             "note": "1단계 보상 착수"},
            {"stage": "ground_break", "occurred_at": date(2010, 3, 1),
             "note": "1단계 착공"},
            {"stage": "completion", "occurred_at": date(2017, 12, 31),
             "note": "1·2단계 준공"},
        ],
    },
    {
        "name": "김포 풍무지구",
        "project_type": "urban_development",
        "region_code": "41280",
        "centroid": (126.7341, 37.6062),
        "bbox_half_size_deg": 0.012,
        "area_ha": 198.5,
        "expected_compensation_billion_krw": 1100.0,
        "planned_announcement_date": date(2010, 7, 1),
        "planned_completion_date": date(2020, 12, 31),
        "description": "풍무동 일대 도시개발사업.",
        "source": "validation:KH-UD-002",
        "stages": [
            {"stage": "announced", "occurred_at": date(2010, 7, 1),
             "note": "도시개발구역 지정 고시"},
            {"stage": "compensation_started", "occurred_at": date(2014, 5, 1),
             "note": "보상 착수"},
            {"stage": "ground_break", "occurred_at": date(2016, 11, 1),
             "note": "착공"},
            {"stage": "completion", "occurred_at": date(2020, 12, 31),
             "note": "준공"},
        ],
    },
    {
        "name": "김포 고촌지구",
        "project_type": "urban_development",
        "region_code": "41280",
        "centroid": (126.7674, 37.6138),
        "bbox_half_size_deg": 0.015,
        "area_ha": 225.7,
        "expected_compensation_billion_krw": 1280.0,
        "planned_announcement_date": date(2014, 4, 1),
        "planned_completion_date": date(2023, 12, 31),
        "description": "고촌읍 일대 도시개발사업.",
        "source": "validation:KH-UD-003",
        "stages": [
            {"stage": "announced", "occurred_at": date(2014, 4, 1),
             "note": "구역 지정 공고"},
            {"stage": "designated", "occurred_at": date(2015, 12, 15),
             "note": "지구계획 확정"},
            {"stage": "compensation_started", "occurred_at": date(2017, 9, 1),
             "note": "보상 착수"},
            {"stage": "ground_break", "occurred_at": date(2019, 6, 1),
             "note": "착공"},
            {"stage": "completion", "occurred_at": date(2023, 12, 31),
             "note": "준공"},
        ],
    },
    {
        "name": "한강2 공공주택지구",
        "project_type": "public_housing",
        "region_code": "41280",
        "centroid": (126.6699, 37.6280),
        "bbox_half_size_deg": 0.022,
        "area_ha": 731.0,
        "expected_compensation_billion_krw": 6800.0,
        "planned_announcement_date": date(2023, 11, 15),
        "planned_completion_date": date(2031, 12, 31),
        "description": "장기동·운양동 일원 3기 신도시급 공공주택지구.",
        "source": "validation:HK2-PH-001",
        "stages": [
            {"stage": "announced", "occurred_at": date(2023, 11, 15),
             "note": "후보지 발표"},
            {"stage": "designated", "occurred_at": date(2024, 8, 30),
             "note": "지구지정 고시"},
            {"stage": "compensation_planned", "occurred_at": date(2025, 6, 1),
             "note": "보상계획 공고"},
        ],
    },
]
