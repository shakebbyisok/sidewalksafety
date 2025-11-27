"""
Database setup script.
Creates tables if they don't exist.
"""
from app.db.base import Base, engine
from app.models import Deal, Evaluation

if __name__ == "__main__":
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created successfully!")

