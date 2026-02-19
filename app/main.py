"""He&She PG Backend - FastAPI Application"""

import os
import logging
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import engine, Base
from app.database import SessionLocal

# Import all models so Base.metadata.create_all() picks up every table
import app.models  # noqa: F401

from app.routers import (
    auth_router,
    users_router,
    properties_router,
    bookings_router,
    favorites_router,
    reviews_router,
    messages_router,
    admin_router,
    owner_router,
    roommates_router,
    referrals_router,
    payments_router,
    wallet_router,
    maintenance_router,
)
from app.routers.websocket import router as websocket_router
from app.routers.cities import router as cities_router
from app.routers.announcements import router as announcements_router
from app.routers.host import router as host_router

# =========================
# Settings & Logging
# =========================
settings = get_settings()

log_level = logging.DEBUG if settings.debug else logging.INFO
logging.basicConfig(level=log_level)
logger = logging.getLogger("heandshepg")

# =========================
# Rate Limiting (Optional)
# =========================
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded

    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["100/minute"]
    )
    RATE_LIMITING_AVAILABLE = True
except ImportError:
    limiter = None
    RATE_LIMITING_AVAILABLE = False

# =========================
# App Lifespan
# =========================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup & Shutdown logic
    """
    # Always ensure tables exist - safe to call even if tables already exist
    try:
        logger.info("Ensuring database tables exist...")
        
        # Create PostgreSQL enum types first (models use create_type=False)
        from sqlalchemy import text
        with engine.connect() as conn:
            enums = {
                "gender_preference": ("male", "female", "mixed"),
                "booking_status": ("requested", "accepted", "paid", "checked_in", "active", "completed", "cancelled", "vacate_requested", "vacated"),
                "payment_status": ("pending", "completed", "failed", "refunded"),
                "payment_type": ("booking", "monthly_rent", "refund", "commission"),
                "invoice_status": ("pending", "paid", "overdue", "cancelled"),
                "transaction_type": ("credit", "debit", "hold", "release"),
                "transaction_status": ("pending", "otp_sent", "verified", "completed", "failed", "refunded"),
            }
            for enum_name, values in enums.items():
                values_str = ", ".join(f"'{v}'" for v in values)
                try:
                    conn.execute(text(
                        f"DO $$ BEGIN "
                        f"CREATE TYPE {enum_name} AS ENUM ({values_str}); "
                        f"EXCEPTION WHEN duplicate_object THEN NULL; "
                        f"END $$;"
                    ))
                except Exception as e:
                    logger.warning(f"Enum {enum_name} creation note: {e}")
            conn.commit()
            logger.info("PostgreSQL enum types ready")
        
        # Enable uuid-ossp extension
        with engine.connect() as conn:
            try:
                conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'))
                conn.commit()
            except Exception:
                pass
        
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables ready")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        if not settings.debug:
            logger.error("CRITICAL: Database tables could not be created in production!")
        raise

    # Scheduler
    from app.scheduler import setup_scheduler
    scheduler = setup_scheduler(app)

    yield

    if scheduler:
        scheduler.shutdown(wait=False)

# =========================
# FastAPI App
# =========================
APP_ENV = os.getenv("APP_ENV", "production")
print(f"[STARTUP] APP_ENV={APP_ENV}, DEBUG={settings.debug}")

if APP_ENV == "production":
    app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
else:
    app = FastAPI(
        title="He&She PG API",
        description="Backend API for He&She PG Booking Platform",
        version="1.0.0",
        lifespan=lifespan,
    )

# =========================
# Rate Limiter
# =========================
if RATE_LIMITING_AVAILABLE and not settings.debug:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# =========================
# CORS Configuration
# =========================
origins = list(set(filter(None, [
    # Local
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://localhost:*",

    # Production
    "https://heandshepg.com",
    "https://www.heandshepg.com",
    settings.frontend_url,
])))

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Exception Handlers
# =========================
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    origin = request.headers.get("origin", "")
    response = JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )
    if origin in origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    return response


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled Exception")
    logger.error(traceback.format_exc())

    message = str(exc) if settings.debug else "Internal server error"

    origin = request.headers.get("origin", "")
    response = JSONResponse(
        status_code=500,
        content={"detail": message},
    )
    if origin in origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    return response

# =========================
# API Routers
# =========================
app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(properties_router, prefix="/api")
app.include_router(bookings_router, prefix="/api")
app.include_router(favorites_router, prefix="/api")
app.include_router(reviews_router, prefix="/api")
app.include_router(messages_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(owner_router, prefix="/api")
app.include_router(roommates_router, prefix="/api")
app.include_router(referrals_router, prefix="/api")
app.include_router(payments_router, prefix="/api")
app.include_router(wallet_router, prefix="/api")
app.include_router(maintenance_router, prefix="/api")
app.include_router(websocket_router, prefix="/api")
app.include_router(cities_router, prefix="/api")
app.include_router(announcements_router)
app.include_router(host_router, prefix="/api")

# =========================
# Static Uploads
# =========================
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# =========================
# Health & Root
# =========================
@app.get("/")
async def root():
    return {
        "name": "He&She PG API",
        "status": "running",
        "docs": "/docs",
        "time": datetime.now(timezone.utc),
    }


@app.get("/health")
async def health():
    status = {"status": "healthy", "database": "unknown"}

    try:
        from sqlalchemy import text
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        status["database"] = "connected"
    except Exception as e:
        status["status"] = "degraded"
        status["database"] = "disconnected"
        if settings.debug:
            status["error"] = str(e)

    return status


@app.get("/api")
async def api_root():
    return {
        "message": "He&She PG API",
        "version": "1.0.0",
    }
