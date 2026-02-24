# He&She PG Backend

A **FastAPI** backend for the He&She PG Booking Platform — a comprehensive property/PG management system with multi-tenant support, payment integration, and real-time features.

---

## 🚀 Tech Stack

| Category | Technology |
|----------|------------|
| **Framework** | FastAPI 0.109.0 |
| **Database** | PostgreSQL + SQLAlchemy 2.0 |
| **Migrations** | Alembic |
| **Authentication** | JWT (python-jose) + bcrypt |
| **Payments** | Razorpay |
| **SMS** | Twilio |
| **Scheduler** | APScheduler |
| **Rate Limiting** | SlowAPI |

---

## 📁 Project Structure

```
heandshepg-backend/
├── app/
│   ├── main.py          # FastAPI application entry point
│   ├── config.py        # Settings & environment config
│   ├── database.py      # Database connection
│   ├── models/          # SQLAlchemy ORM models
│   ├── routers/         # API route handlers
│   ├── schemas/         # Pydantic request/response schemas
│   ├── services/        # Business logic services
│   ├── utils/           # Utility functions
│   └── scheduler.py     # Background job scheduler
├── alembic/             # Database migrations
├── uploads/             # Static file uploads
├── tests/               # Test suite
├── requirements.txt     # Python dependencies
└── .env.example         # Environment variable template
```

---

## ⚡ Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL database
- (Optional) Razorpay & Twilio accounts for payments/SMS

### 1. Clone & Setup Environment

```bash
# Clone the repository
git clone <repository-url>
cd heandshepg-backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows (PowerShell)
.\venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
# Copy the example env file
cp .env.example .env

# Edit .env with your actual values
# Key configurations:
# - DATABASE_URL: PostgreSQL connection string
# - SECRET_KEY: Generate with: python -c "import secrets; print(secrets.token_urlsafe(64))"
# - RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET: Payment gateway keys
# - TWILIO_* : SMS service credentials
```

### 4. Setup Database

```bash
# Run database migrations
alembic upgrade head

# OR initialize database directly (development only)
python init_db.py
```

### 5. Run the Server

```bash
# Development (with auto-reload)
uvicorn app.main:app --reload --port 8000

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 🔗 API Endpoints

Once running, access the API at:

| Endpoint | Description |
|----------|-------------|
| `http://localhost:8000` | Root endpoint |
| `http://localhost:8000/docs` | Swagger UI (Interactive API docs) |
| `http://localhost:8000/redoc` | ReDoc (Alternative API docs) |
| `http://localhost:8000/health` | Health check endpoint |

### Core API Modules

| Module | Prefix | Description |
|--------|--------|-------------|
| Auth | `/api/auth` | Login, Register, JWT tokens |
| Users | `/api/users` | User profile management |
| Properties | `/api/properties` | Property CRUD, search |
| Bookings | `/api/bookings` | Booking management |
| Payments | `/api/payments` | Razorpay payment integration |
| Wallet | `/api/wallet` | User wallet & transactions |
| Reviews | `/api/reviews` | Property reviews |
| Messages | `/api/messages` | In-app messaging |
| Favorites | `/api/favorites` | Saved properties |
| Maintenance | `/api/maintenance` | Maintenance requests |
| Referrals | `/api/referrals` | Referral system |
| Admin | `/api/admin` | Admin dashboard APIs |
| Owner | `/api/owner` | Property owner APIs |

---

## 🗄️ Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "description of changes"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history
```

---

## 🧪 Testing

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=app
```

---

## 🐳 Docker

```bash
# Build image
docker build -t heandshepg-backend .

# Run container
docker run -p 8000:8000 --env-file .env heandshepg-backend
```

---

## 📝 Environment Variables

See [`.env.example`](.env.example) for all available configuration options:

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | ✅ |
| `SECRET_KEY` | JWT signing key | ✅ |
| `FRONTEND_URL` | Frontend URL for CORS | ✅ |
| `RAZORPAY_KEY_ID` | Razorpay API key | ⚠️ |
| `RAZORPAY_KEY_SECRET` | Razorpay secret | ⚠️ |
| `TWILIO_ACCOUNT_SID` | Twilio SID for SMS | ⚠️ |
| `TWILIO_AUTH_TOKEN` | Twilio auth token | ⚠️ |
| `SMTP_*` | Email configuration | ⚠️ |
| `DEBUG` | Enable debug mode | ❌ |

✅ Required | ⚠️ Required for feature | ❌ Optional

---

## 🚀 Deployment

The project includes configuration for:

- **Render**: `render.yaml`
- **Railway/Nixpacks**: `nixpacks.toml`
- **Heroku**: `Procfile`, `runtime.txt`
- **Docker**: `Dockerfile`

---

## 📄 License

This project is proprietary software for He&She PG.
