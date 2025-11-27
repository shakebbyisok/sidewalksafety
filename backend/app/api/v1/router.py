from fastapi import APIRouter
from app.api.v1.endpoints import deals, evaluation, geocoding, auth

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(deals.router, prefix="/deals", tags=["deals"])
api_router.include_router(evaluation.router, prefix="/evaluations", tags=["evaluations"])
api_router.include_router(geocoding.router, prefix="/geocoding", tags=["geocoding"])

