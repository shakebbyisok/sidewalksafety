from pydantic_settings import BaseSettings
from typing import Optional
import secrets


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    SUPABASE_DB_URL: Optional[str] = None
    
    # Google Maps
    GOOGLE_MAPS_KEY: str
    
    # Apollo.io
    APOLLO_API_KEY: Optional[str] = None
    
    # Roboflow (for YOLOv8 crack detection)
    ROBOFLOW_API_KEY: Optional[str] = None
    
    # Security
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    
    # App
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Create settings instance
_settings = Settings()

# Generate SECRET_KEY if not provided (development only)
if not _settings.SECRET_KEY:
    if _settings.ENVIRONMENT == "development":
        _settings.SECRET_KEY = secrets.token_urlsafe(32)
        print("⚠️  WARNING: Using auto-generated SECRET_KEY. Set SECRET_KEY in .env for production!")
    else:
        raise ValueError("SECRET_KEY is required in production. Set it in .env file.")

settings = _settings

