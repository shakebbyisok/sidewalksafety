# Sidewalk Safety

Lead scraping and deal evaluation platform for landscaping companies.

## Quick Start

### Backend Setup

```bash
cd backend
cp env.example .env
# Fill in your .env file
pip install -r requirements.txt
python setup_db.py
uvicorn app.main:app --reload
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

## Documentation

- [API Reference](docs/API.md)
- [Architecture](docs/ARCHITECTURE.md)

## Tech Stack

- **Backend**: FastAPI + SQLAlchemy + Supabase
- **Frontend**: Next.js + React + Tailwind CSS
- **AI**: Cloud APIs (Roboflow, Google Maps)

