"""Lightweight unit tests for ORM construction + relationship topology.

These tests do NOT require a running PostgreSQL — they exercise the
metadata, key relationships, and Pydantic-style invariants that hold
without a connection. Integration tests with PostGIS are gated behind
``REALESTATE_PG_DSN`` and live in ``test_models_integration.py``.
"""

from __future__ import annotations

from src.models import (
    AdminArea,
    AnalysisResult,
    Base,
    Building,
    LandTransaction,
    OfficialLandPrice,
    PopulationStat,
    Project,
    ProjectStage,
    Recommendation,
    RoadExpansionStage,
    RoadSegment,
    Store,
    StoreBrand,
    StoreFeature,
    StoreImpactAnalysis,
    TrafficVolume,
)


def test_metadata_has_all_seventeen_tables() -> None:
    expected = {
        "admin_areas", "projects", "project_stages", "land_transactions",
        "road_segments", "road_expansion_stages", "traffic_volumes",
        "population_stats",
        "store_brands", "stores", "buildings", "official_land_prices",
        "store_features", "candidate_lands", "store_impact_analysis",
        "analysis_results", "recommendations",
    }
    assert set(Base.metadata.tables.keys()) == expected


def test_admin_area_self_reference_via_parent_code() -> None:
    columns = {c.name: c for c in AdminArea.__table__.columns}
    fk = next(iter(columns["parent_code"].foreign_keys))
    assert fk.column.table.name == "admin_areas"


def test_project_to_stage_relationship_is_cascade_delete() -> None:
    rel = Project.__mapper__.relationships["stages"]
    assert "delete-orphan" in (rel.cascade or "")
    # Reverse direction
    back = ProjectStage.__mapper__.relationships["project"]
    assert back.argument == Project or back.entity.class_ is Project


def test_store_brand_one_to_many_to_store() -> None:
    rel = StoreBrand.__mapper__.relationships["stores"]
    assert rel.entity.class_ is Store
    assert "delete-orphan" in (rel.cascade or "")


def test_store_to_building_uses_pnu_fk() -> None:
    pnu_col = Store.__table__.columns["pnu"]
    fks = list(pnu_col.foreign_keys)
    assert len(fks) == 1
    assert fks[0].column.table.name == "buildings"


def test_official_land_price_unique_pnu_year() -> None:
    constraints = {c.name for c in OfficialLandPrice.__table__.constraints}
    assert "uq_official_land_prices_pnu_year" in constraints


def test_store_feature_unique_per_snapshot_version() -> None:
    constraints = {c.name for c in StoreFeature.__table__.constraints}
    assert "uq_store_features_store_date_version" in constraints


def test_recommendation_unique_per_source_target_version() -> None:
    constraints = {c.name for c in Recommendation.__table__.constraints}
    assert "uq_recommendations_source_target_version" in constraints


def test_analysis_result_uses_uuid_pk() -> None:
    pk = list(AnalysisResult.__table__.primary_key.columns)[0]
    # On Postgres this maps to UUID; in metadata it's the SQLAlchemy UUID type.
    assert pk.name == "id"
    # Just ensure the type spells "UUID" (works across SA versions).
    assert "UUID" in repr(pk.type).upper()


def test_road_segment_to_traffic_back_populates() -> None:
    fwd = RoadSegment.__mapper__.relationships["traffic_volumes"]
    back = TrafficVolume.__mapper__.relationships["road"]
    assert back.argument == RoadSegment or back.entity.class_ is RoadSegment
    assert fwd.entity.class_ is TrafficVolume


def test_admin_area_back_populates_population() -> None:
    rel = AdminArea.__mapper__.relationships["population_stats"]
    assert rel.entity.class_ is PopulationStat


def test_store_impact_links_to_store() -> None:
    rel = Store.__mapper__.relationships["impact_analyses"]
    assert rel.entity.class_ is StoreImpactAnalysis


def test_land_transaction_source_id_unique() -> None:
    col = LandTransaction.__table__.columns["source_id"]
    assert col.unique


def test_road_segment_unique_name_route() -> None:
    constraints = {c.name for c in RoadSegment.__table__.constraints}
    assert "uq_road_segments_name_route" in constraints


def test_road_expansion_stage_unique_per_road_stage_date() -> None:
    constraints = {c.name for c in RoadExpansionStage.__table__.constraints}
    assert "uq_road_expansion_stages_road_stage_date" in constraints


def test_building_pk_is_pnu_string() -> None:
    pk = list(Building.__table__.primary_key.columns)[0]
    assert pk.name == "pnu"
    assert pk.type.length == 19


def test_indexes_include_postgis_gist_for_geometry_columns() -> None:
    """Every table with a geometry column has at least one GIST index named ``gix_*``."""
    geom_tables = [
        "admin_areas", "projects", "land_transactions", "road_segments",
        "buildings", "stores", "candidate_lands",
    ]
    for tbl_name in geom_tables:
        tbl = Base.metadata.tables[tbl_name]
        gix = [i for i in tbl.indexes if i.name and i.name.startswith("gix_")]
        assert gix, f"{tbl_name} is missing a GIST (gix_*) index"
