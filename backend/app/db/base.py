from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

database_url = settings.DATABASE_URL
db_schema = settings.DB_SCHEMA

is_supabase_pooler = "pooler.supabase.com" in database_url or "supabase.co" in database_url

if is_supabase_pooler:
    if "?" not in database_url:
        database_url += "?sslmode=require"
    elif "sslmode" not in database_url:
        database_url += "&sslmode=require"

# Build connect_args with schema search_path
connect_args = {
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    "options": f"-csearch_path={db_schema},public",
    }

pool_config = {
    "pool_pre_ping": True,
    "echo": False,
    "connect_args": connect_args,
}

if is_supabase_pooler:
    is_transaction_mode = ":6543" in database_url
    
    if is_transaction_mode:
        pool_config.update({
            "pool_size": 5,
            "max_overflow": 2,
            "pool_recycle": 300,
            "pool_timeout": 20,
        })
    else:
        pool_config.update({
            "pool_size": 3,
            "max_overflow": 2,
            "pool_recycle": 600,
            "pool_timeout": 20,
        })
else:
    pool_config.update({
        "pool_size": 10,
        "max_overflow": 5,
        "pool_recycle": 3600,
    })

engine = create_engine(database_url, **pool_config)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Set schema in Base metadata so all models use it
Base = declarative_base()
Base.metadata.schema = db_schema if db_schema != "public" else None

print(f"[DB] Schema: {db_schema}")


def get_db():
    """Dependency for getting database session."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
