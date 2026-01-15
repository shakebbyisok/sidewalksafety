from fastapi import APIRouter
from app.api.v1.endpoints import auth, properties, discovery, usage, settings, scoring_prompts

api_router = APIRouter()

# Core endpoints
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(discovery.router, prefix="/discover", tags=["discovery"])

# Properties (uses /parking-lots URL for frontend compatibility)
api_router.include_router(properties.router, prefix="/parking-lots", tags=["properties"])

# Usage & Settings
api_router.include_router(usage.router, prefix="/usage", tags=["usage"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(scoring_prompts.router, prefix="/scoring-prompts", tags=["scoring-prompts"])
