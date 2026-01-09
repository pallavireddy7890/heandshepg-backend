# He&She PG Backend

Python FastAPI backend for He&She PG Booking Platform.

## Quick Start

```bash
# Create virtual environment
python -m venv venv
.\venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Setup database
psql -U postgres -c "CREATE DATABASE heandshepg_db;"
psql -d heandshepg_db -f sql/init_schema.sql

# Create .env file (copy from .env.example)
cp .env.example .env

# Run server
uvicorn app.main:app --reload --port 8000
```

## API Documentation
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Structure
```
├── alembic/          # Database migrations
│   └── versions/     # Migration files
├── app/              # Main application
│   ├── models/       # SQLAlchemy models
│   ├── routers/      # API routes
│   ├── schemas/      # Pydantic schemas
│   ├── services/     # Business logic
│   └── utils/        # Utilities
├── tests/            # Test files
├── uploads/          # File uploads
└── sql/              # SQL scripts
```
