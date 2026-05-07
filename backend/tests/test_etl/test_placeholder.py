"""Placeholder ETL test module — Stage 2 will fill in real ingestion tests."""

from __future__ import annotations


def test_etl_packages_importable() -> None:
    import importlib

    for name in (
        "src.etl",
        "src.etl.molit_real_estate",
        "src.etl.admin_population",
        "src.etl.building_registry",
        "src.etl.land_price",
        "src.etl.store_scraper",
        "src.etl.store_scraper.base",
        "src.etl.store_scraper.starbucks",
        "src.etl.store_scraper.mcdonalds",
    ):
        importlib.import_module(name)
