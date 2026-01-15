from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import os
from app.core.config import settings
from app.api.v1.router import api_router

app = FastAPI(
    title="WorkSight API",
    description="Property discovery, analysis, and lead enrichment API",
    version="2.0.0",
)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    from fastapi.openapi.utils import get_openapi
    
    openapi_schema = get_openapi(
        title="WorkSight API",
        version="2.0.0",
        description="Property discovery, analysis, and lead enrichment API",
        routes=app.routes,
    )
    
    # Add security scheme
    openapi_schema["components"]["securitySchemes"] = {
        "HTTPBearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# Get CORS origins from settings or use defaults
cors_origins = getattr(settings, 'CORS_ORIGINS', [
    "https://app.worksight.biz",
    "http://localhost:3000",
    "http://localhost:3001",
])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,  # Allow cookies/auth headers
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
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
    return {
        "message": "WorkSight API",
        "version": "2.0.0",
        "description": "Property discovery, analysis, and lead enrichment platform",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}


app.include_router(api_router, prefix=settings.API_V1_PREFIX)

# Mount static files for CV images
# This serves files from storage/cv_images at /api/v1/images
cv_images_path = settings.CV_IMAGE_STORAGE_PATH
if os.path.exists(cv_images_path):
    app.mount(
        settings.CV_IMAGE_BASE_URL,
        StaticFiles(directory=cv_images_path),
        name="cv_images"
    )
else:
    # Create the directory if it doesn't exist
    os.makedirs(cv_images_path, exist_ok=True)
    app.mount(
        settings.CV_IMAGE_BASE_URL,
        StaticFiles(directory=cv_images_path),
        name="cv_images"
    )


# Allow running directly: python -m app.main
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.ENVIRONMENT == "development",
    )
