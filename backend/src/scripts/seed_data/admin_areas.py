"""Administrative areas for the validation cases.

Hand-picked subset covering 김포시 + 평택시 (Scenario A/B 검증 케이스 영역)
plus a few 행정동 used by Scenario C 매장 데이터. Real ETL will load the
full 행정안전부 master, but for seeding we only need the rows that the
validation cases actually reference.
"""

from __future__ import annotations

from typing import TypedDict


class AdminAreaSeed(TypedDict):
    code: str
    name: str
    level: str
    parent_code: str | None
    centroid: tuple[float, float] | None  # (lon, lat) in EPSG:4326


# Top-level (시·도)
SIDOS: list[AdminAreaSeed] = [
    {"code": "41", "name": "경기도", "level": "sido",
     "parent_code": None, "centroid": (127.5183, 37.4138)},
    {"code": "11", "name": "서울특별시", "level": "sido",
     "parent_code": None, "centroid": (126.9780, 37.5665)},
]

# 시·군·구
SIGUNGUS: list[AdminAreaSeed] = [
    {"code": "41280", "name": "김포시", "level": "sigungu",
     "parent_code": "41", "centroid": (126.7155, 37.6154)},
    {"code": "41220", "name": "평택시", "level": "sigungu",
     "parent_code": "41", "centroid": (127.1128, 36.9921)},
    {"code": "41131", "name": "성남시 분당구", "level": "sigungu",
     "parent_code": "41", "centroid": (127.1086, 37.3520)},
    {"code": "41117", "name": "수원시 영통구", "level": "sigungu",
     "parent_code": "41", "centroid": (127.0723, 37.2580)},
    {"code": "11680", "name": "강남구", "level": "sigungu",
     "parent_code": "11", "centroid": (127.0473, 37.5172)},
]

# 읍·면·동 (only those touched by validation cases)
EUPMYEONDONGS: list[AdminAreaSeed] = [
    # 김포시
    {"code": "4128010100", "name": "김포본동", "level": "eupmyeondong",
     "parent_code": "41280", "centroid": (126.7146, 37.6166)},
    {"code": "4128010200", "name": "사우동", "level": "eupmyeondong",
     "parent_code": "41280", "centroid": (126.7300, 37.6188)},
    {"code": "4128010300", "name": "풍무동", "level": "eupmyeondong",
     "parent_code": "41280", "centroid": (126.7341, 37.6062)},
    {"code": "4128010400", "name": "장기동", "level": "eupmyeondong",
     "parent_code": "41280", "centroid": (126.6699, 37.6280)},
    {"code": "4128010500", "name": "운양동", "level": "eupmyeondong",
     "parent_code": "41280", "centroid": (126.6534, 37.6517)},
    {"code": "4128025000", "name": "고촌읍", "level": "eupmyeondong",
     "parent_code": "41280", "centroid": (126.7674, 37.6138)},
    {"code": "4128025500", "name": "양촌읍", "level": "eupmyeondong",
     "parent_code": "41280", "centroid": (126.6234, 37.6643)},
    # 평택시
    {"code": "4122010100", "name": "비전동", "level": "eupmyeondong",
     "parent_code": "41220", "centroid": (127.1128, 36.9921)},
    {"code": "4122010200", "name": "동삭동", "level": "eupmyeondong",
     "parent_code": "41220", "centroid": (127.0823, 36.9803)},
    {"code": "4122010300", "name": "지산동", "level": "eupmyeondong",
     "parent_code": "41220", "centroid": (127.0997, 36.9820)},
    {"code": "4122010400", "name": "이충동", "level": "eupmyeondong",
     "parent_code": "41220", "centroid": (127.0644, 37.0099)},
    {"code": "4122010500", "name": "용이동", "level": "eupmyeondong",
     "parent_code": "41220", "centroid": (127.0846, 36.9890)},
    {"code": "4122025000", "name": "고덕면", "level": "eupmyeondong",
     "parent_code": "41220", "centroid": (127.0438, 37.0327)},
]

ALL_AREAS: list[AdminAreaSeed] = [*SIDOS, *SIGUNGUS, *EUPMYEONDONGS]
