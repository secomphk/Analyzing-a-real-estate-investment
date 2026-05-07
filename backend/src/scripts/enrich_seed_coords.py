"""Enrich seed store coordinates with verified Naver Local data.

Why
---
The Stage 2 seed in ``seed_data/stores.py`` carries placeholder
coordinates so the schema and pipeline could be exercised end-to-end
without a real geocoder. Now that we have the :class:`NaverGeocoder`
adapter, this script queries Naver for each seed entry and writes the
verified results to ``store_coords_verified.json``.

Usage
-----

    poetry run python -m src.scripts.enrich_seed_coords \\
        --client-id  $NAVER_CLIENT_ID \\
        --client-secret $NAVER_CLIENT_SECRET

Or, if your shell has the env vars set::

    poetry run python -m src.scripts.enrich_seed_coords

Output: ``backend/src/scripts/seed_data/store_coords_verified.json``.
The seed loader (``seed.py``) prefers this file when it exists, falling
back to the static placeholder coordinates otherwise.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.etl.geocoder import GeocodeResult, NaverGeocoder
from src.scripts.seed_data.stores import STORES

OUTPUT_PATH = (
    Path(__file__).parent / "seed_data" / "store_coords_verified.json"
)


def _build_query(store: Mapping[str, Any]) -> str:
    """Pick the most-likely-to-match keyword for ``store``.

    The brand+location combo with "DT/DI" suffix matches the real Naver
    catalog more often than the synthetic seed name (which sometimes
    invents a 동 that doesn't have that brand).
    """
    region = store["address"].split()[2] if store["address"] else ""
    if store["store_type"] in ("DT", "DI"):
        return f"{region} {store['brand']} {store['store_type']}"
    return f"{region} {store['brand']}"


def _pick_best_match(
    store: Mapping[str, Any], results: list[GeocodeResult]
) -> GeocodeResult | None:
    """Choose the result whose name best aligns with the seed.

    Naver returns up to 5 candidates. We pick:
    1. an exact name suffix match (``...DT점`` / ``...DI점``), else
    2. the first result, since Naver already ranks by relevance.
    """
    if not results:
        return None
    if store["store_type"] in ("DT", "DI"):
        suffix = store["store_type"] + "점"
        for r in results:
            if suffix in r.name:
                return r
    return results[0]


async def enrich(client_id: str, client_secret: str) -> dict[str, dict[str, Any]]:
    """Returns a ``{source_id: enriched_record}`` dict."""
    out: dict[str, dict[str, Any]] = {}
    async with NaverGeocoder(client_id, client_secret) as geo:
        for store in STORES:
            query = _build_query(store)
            try:
                results = await geo.search(query, limit=5)
            except Exception as exc:  # noqa: BLE001 — log + continue
                print(f"  ✗ {store['source_id']} {query}: {exc}")
                out[store["source_id"]] = {
                    "status": "error",
                    "query": query,
                    "error": str(exc),
                }
                continue

            best = _pick_best_match(store, results)
            if best is None:
                print(f"  ? {store['source_id']} {query}: no match")
                out[store["source_id"]] = {"status": "no_match", "query": query}
                continue

            out[store["source_id"]] = {
                "status": "ok",
                "query": query,
                "name": best.name,
                "address": best.address,
                "road_address": best.road_address,
                "latitude": best.latitude,
                "longitude": best.longitude,
                # Track the seed's original guess so we can compute drift.
                "seed_lat": store["location"][1],
                "seed_lng": store["location"][0],
                "seed_drift_km": _haversine_km(
                    (store["location"][1], store["location"][0]),
                    (best.latitude, best.longitude),
                ),
            }
            print(
                f"  ✓ {store['source_id']} {query!r} → "
                f"{best.name} ({best.latitude:.4f}, {best.longitude:.4f})"
            )

            # Naver free tier is 25k/day — be polite even though we're well
            # under quota.
            await asyncio.sleep(0.1)

    return out


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two (lat, lng) pairs, in km."""
    import math  # noqa: PLC0415

    lat1, lng1 = a
    lat2, lng2 = b
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(h)), 3)


async def main_async(client_id: str, client_secret: str) -> None:
    print(f"Enriching {len(STORES)} seed stores via Naver Local API…")
    enriched = await enrich(client_id, client_secret)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(enriched, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ok = sum(1 for v in enriched.values() if v.get("status") == "ok")
    print(
        f"\nWrote {OUTPUT_PATH.relative_to(Path.cwd())} "
        f"({ok}/{len(STORES)} matched)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--client-id",
        default=os.environ.get("NAVER_CLIENT_ID"),
        help="Naver Open API client ID (or env NAVER_CLIENT_ID)",
    )
    parser.add_argument(
        "--client-secret",
        default=os.environ.get("NAVER_CLIENT_SECRET"),
        help="Naver Open API client secret (or env NAVER_CLIENT_SECRET)",
    )
    args = parser.parse_args()
    if not args.client_id or not args.client_secret:
        raise SystemExit(
            "Naver Open API credentials missing. Pass --client-id / "
            "--client-secret or set NAVER_CLIENT_ID / NAVER_CLIENT_SECRET."
        )
    asyncio.run(main_async(args.client_id, args.client_secret))


if __name__ == "__main__":
    main()
