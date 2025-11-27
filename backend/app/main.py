from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.api.v1.router import api_router
from app.db.base import Base, engine
from app.models import Deal, Evaluation, User

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Sidewalk Safety API",
    description="Lead scraping and deal evaluation API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc) if settings.ENVIRONMENT == "development" else "Internal server error"},
        headers={"Access-Control-Allow-Origin": "*"},
    )

@app.get("/")
def root():
    return {"message": "Sidewalk Safety API", "version": "1.0.0"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

app.include_router(api_router, prefix=settings.API_V1_PREFIX)

