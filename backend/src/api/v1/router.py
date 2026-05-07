"""API v1 root router — composes every scenario sub-router.

Each sub-router gets its own ``prefix`` and ``tags`` so the OpenAPI surface
groups cleanly in Swagger UI.
"""

from __future__ import annotations

from fastapi import APIRouter

from src.api.v1 import (
    analysis,
    predictions,
    projects,
    recommendations,
    roads,
    stores,
)

api_router = APIRouter()

api_router.include_router(
    projects.router,
    prefix="/projects",
    tags=["scenario-a:projects"],
)
api_router.include_router(
    roads.router,
    prefix="/roads",
    tags=["scenario-b:roads"],
)
api_router.include_router(
    stores.router,
    prefix="/stores",
    tags=["scenario-c:stores"],
)
api_router.include_router(
    analysis.router,
    prefix="/analysis",
    tags=["analysis"],
)
api_router.include_router(
    recommendations.router,
    prefix="/recommendations",
    tags=["recommendations"],
)
api_router.include_router(
    predictions.router,
    prefix="/predictions",
    tags=["scenario-c:predictions"],
)
