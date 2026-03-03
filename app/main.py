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
    wallet_router,
    maintenance_router,
)
from app.routers.websocket import router as websocket_router
from app.routers.cities import router as cities_router
from app.routers.announcements import router as announcements_router
from app.routers.host import router as host_router
from app.routers.upload_photos import router as upload_photos_router

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
                "payment_status": ("pending", "completed", "failed", "refunded", "pending_verification"),
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
        
        # Sync missing columns for ALL tables (safe to run on every startup)
        with engine.connect() as conn:
            sync_statements = [
                # === PROFILES ===
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS display_name VARCHAR(255)",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS business_name VARCHAR(255)",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS about TEXT",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS phone_verified BOOLEAN DEFAULT FALSE",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS profile_photo TEXT",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS current_address TEXT",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS permanent_address TEXT",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS gender VARCHAR(20)",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS date_of_birth VARCHAR(20)",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS work_type VARCHAR(100)",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS work_place VARCHAR(255)",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS mother_tongue VARCHAR(50)",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS languages_known TEXT[]",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS emergency_contact_name VARCHAR(255)",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS emergency_contact_phone VARCHAR(20)",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS emergency_contact_address TEXT",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS payment_reminders_enabled BOOLEAN DEFAULT TRUE",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS rent_reminder_day INTEGER DEFAULT 1",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS rent_due_day INTEGER DEFAULT 5",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS rent_reminder_message TEXT",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS maintenance_reminders_enabled BOOLEAN DEFAULT TRUE",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS email_notifications BOOLEAN DEFAULT TRUE",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS sms_notifications BOOLEAN DEFAULT TRUE",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS push_notifications BOOLEAN DEFAULT FALSE",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS hide_contact_info BOOLEAN DEFAULT FALSE",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS bank_account_number VARCHAR(50)",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS bank_ifsc_code VARCHAR(20)",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS bank_name VARCHAR(255)",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS pan_card_url TEXT",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS gst_doc_url TEXT",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS aadhar_front_url TEXT",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS aadhar_back_url TEXT",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS dl_front_url TEXT",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS dl_back_url TEXT",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS college_company_id_url TEXT",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS profile_verification_status VARCHAR(20) DEFAULT 'pending'",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS hosting_since DATE",
                # === PROPERTIES ===
                "ALTER TABLE properties ADD COLUMN IF NOT EXISTS city_id UUID REFERENCES cities(id) ON DELETE SET NULL",
                "ALTER TABLE properties ADD COLUMN IF NOT EXISTS locality VARCHAR(100)",
                "ALTER TABLE properties ADD COLUMN IF NOT EXISTS latitude NUMERIC(10,8)",
                "ALTER TABLE properties ADD COLUMN IF NOT EXISTS longitude NUMERIC(11,8)",
                "ALTER TABLE properties ADD COLUMN IF NOT EXISTS monthly_rent INTEGER",
                "ALTER TABLE properties ADD COLUMN IF NOT EXISTS deposit INTEGER",
                "ALTER TABLE properties ADD COLUMN IF NOT EXISTS grace_period INTEGER DEFAULT 0",
                "ALTER TABLE properties ADD COLUMN IF NOT EXISTS auto_approve BOOLEAN DEFAULT FALSE",
                "ALTER TABLE properties ADD COLUMN IF NOT EXISTS instant_booking BOOLEAN DEFAULT FALSE",
                "ALTER TABLE properties ADD COLUMN IF NOT EXISTS cancellation_policy TEXT",
                "ALTER TABLE properties ADD COLUMN IF NOT EXISTS virtual_tour_url TEXT",
                "ALTER TABLE properties ADD COLUMN IF NOT EXISTS safety_score INTEGER",
                "ALTER TABLE properties ADD COLUMN IF NOT EXISTS nearby_amenities JSONB",
                # === ROOMS ===
                "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS floor_number INTEGER DEFAULT 1",
                "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS room_number VARCHAR(20)",
                "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS deposit INTEGER",
                "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS security_deposit INTEGER",
                "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS monthly_price INTEGER",
                "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS daily_price INTEGER",
                "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS maintenance_charge INTEGER DEFAULT 0",
                "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS stay_type VARCHAR(20) DEFAULT 'monthly'",
                "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS min_stay INTEGER DEFAULT 1",
                "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS is_extension_allowed BOOLEAN DEFAULT TRUE",
                "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS complementaries TEXT[]",
                "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS room_photos TEXT[]",
                "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS room_description TEXT",
                "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS area_sqft INTEGER",
                "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS width_ft INTEGER",
                "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS has_ventilation BOOLEAN DEFAULT TRUE",
                # === ROOM_BEDS ===
                "ALTER TABLE room_beds ADD COLUMN IF NOT EXISTS bed_number VARCHAR(20)",
                "ALTER TABLE room_beds ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'available'",
                "ALTER TABLE room_beds ADD COLUMN IF NOT EXISTS current_tenant_id UUID REFERENCES users(id) ON DELETE SET NULL",
                # === BOOKINGS ===
                "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS bed_id UUID REFERENCES room_beds(id) ON DELETE SET NULL",
                "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS maintenance_charge INTEGER DEFAULT 0",
                "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS rent_paid BOOLEAN DEFAULT FALSE",
                "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS deposit_paid BOOLEAN DEFAULT FALSE",
                "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS maintenance_paid BOOLEAN DEFAULT FALSE",
                "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS last_payment_date TIMESTAMPTZ",
                "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS stay_type VARCHAR(20) DEFAULT 'monthly'",
                "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS duration_days INTEGER",
                "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS payment_id UUID",
                "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ",
                "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS cancel_reason TEXT",
                "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS customer_documents TEXT[]",
                "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS customer_snapshot JSONB",
                # === PAYMENTS ===
                "ALTER TABLE payments ADD COLUMN IF NOT EXISTS payment_method VARCHAR(20) DEFAULT 'online'",
                "ALTER TABLE payments ADD COLUMN IF NOT EXISTS offline_reference TEXT",
                "ALTER TABLE payments ADD COLUMN IF NOT EXISTS verified_by_id UUID REFERENCES users(id) ON DELETE SET NULL",
                "ALTER TABLE payments ADD COLUMN IF NOT EXISTS payment_date TIMESTAMPTZ",
                "ALTER TABLE payments ADD COLUMN IF NOT EXISTS commission_amount INTEGER DEFAULT 0",
                "ALTER TABLE payments ADD COLUMN IF NOT EXISTS payment_metadata JSONB",
                # === WALLET_TRANSACTIONS ===
                "ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS payer_id UUID REFERENCES users(id) ON DELETE SET NULL",
                "ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS receiver_id UUID REFERENCES users(id) ON DELETE SET NULL",
                "ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS payment_type VARCHAR(20) DEFAULT 'total'",
                "ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS bank_account_number VARCHAR(50)",
                "ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS bank_ifsc_code VARCHAR(20)",
                "ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS bank_name VARCHAR(255)",
                "ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS admin_notes TEXT",
                "ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS otp_verified BOOLEAN DEFAULT FALSE",
                "ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS otp_verified_at TIMESTAMPTZ",
                "ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS payment_method VARCHAR(20) DEFAULT 'online'",
                "ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS offline_notes TEXT",
                "ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS offline_reference TEXT",
                "ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS razorpay_payment_id VARCHAR(255)",
                "ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS razorpay_order_id VARCHAR(255)",
                "ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS description TEXT",
                # === WALLETS ===
                "ALTER TABLE wallets ADD COLUMN IF NOT EXISTS pending_balance INTEGER DEFAULT 0",
                # === REVIEWS ===
                "ALTER TABLE reviews ADD COLUMN IF NOT EXISTS cleanliness_rating INTEGER",
                "ALTER TABLE reviews ADD COLUMN IF NOT EXISTS food_rating INTEGER",
                "ALTER TABLE reviews ADD COLUMN IF NOT EXISTS safety_rating INTEGER",
                # === ROOMMATE_PROFILES ===
                "ALTER TABLE roommate_profiles ADD COLUMN IF NOT EXISTS dietary_preference VARCHAR(50)",
                "ALTER TABLE roommate_profiles ADD COLUMN IF NOT EXISTS smoking BOOLEAN DEFAULT FALSE",
                "ALTER TABLE roommate_profiles ADD COLUMN IF NOT EXISTS drinking BOOLEAN DEFAULT FALSE",
                "ALTER TABLE roommate_profiles ADD COLUMN IF NOT EXISTS pets_allowed BOOLEAN DEFAULT FALSE",
                "ALTER TABLE roommate_profiles ADD COLUMN IF NOT EXISTS cleanliness_level INTEGER DEFAULT 3",
                # === REFERRALS ===
                "ALTER TABLE referrals ADD COLUMN IF NOT EXISTS reward_amount FLOAT DEFAULT 0",
                "ALTER TABLE referrals ADD COLUMN IF NOT EXISTS reward_claimed BOOLEAN DEFAULT FALSE",
                "ALTER TABLE referrals ADD COLUMN IF NOT EXISTS booking_id UUID REFERENCES bookings(id) ON DELETE SET NULL",
                "ALTER TABLE referrals ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ",
                # === MAINTENANCE_TICKETS ===
                "ALTER TABLE maintenance_tickets ADD COLUMN IF NOT EXISTS room_id UUID REFERENCES rooms(id) ON DELETE SET NULL",
                "ALTER TABLE maintenance_tickets ADD COLUMN IF NOT EXISTS booking_id UUID REFERENCES bookings(id) ON DELETE SET NULL",
            ]
            for sql in sync_statements:
                try:
                    conn.execute(text(sql))
                except Exception as e:
                    logger.warning(f"Column sync note: {e}")
            conn.commit()
            logger.info("All table columns synced successfully")
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

    # Production origins
    "https://heandshepg.com",
    "https://www.heandshepg.com",
    settings.frontend_url,
])))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
app.include_router(wallet_router, prefix="/api")
app.include_router(maintenance_router, prefix="/api")
app.include_router(websocket_router, prefix="/api")
app.include_router(cities_router, prefix="/api")
app.include_router(announcements_router)
app.include_router(host_router, prefix="/api")
app.include_router(upload_photos_router, prefix="/api")

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
