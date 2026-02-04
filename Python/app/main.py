"""He&She PG Backend - FastAPI Application."""
from datetime import datetime, timezone
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import os
import traceback
import logging

from app.config import get_settings
from app.database import engine, Base
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

# Rate limiting imports
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    RATE_LIMITING_AVAILABLE = True
except ImportError:
    RATE_LIMITING_AVAILABLE = False

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

settings = get_settings()

# Initialize rate limiter (if available)
limiter = None
if RATE_LIMITING_AVAILABLE and not settings.debug:
    limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
    logger.info("Rate limiting enabled: 100 requests/minute per IP")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup: Create tables only in debug mode
    # In production, use Alembic migrations exclusively
    if settings.debug:
        logger.warning("DEBUG MODE: Auto-creating database tables. Use Alembic in production.")
        Base.metadata.create_all(bind=engine)
    
    # Start background scheduler
    from app.scheduler import setup_scheduler
    scheduler = setup_scheduler(app)
    
    yield
    
    # Shutdown: cleanup
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="He&She PG API",
    description="Backend API for He&She PG Booking Platform",
    version="1.0.0",
    lifespan=lifespan,
)

# Add rate limiter to app state and exception handler
if RATE_LIMITING_AVAILABLE and limiter:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS Configuration - explicit origins required when using credentials
# Note: When allow_credentials=True, cannot use wildcard "*" for allow_origins
origins = [
    "http://localhost:8080",
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:8080",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
    settings.frontend_url,
]
# Filter out None values and duplicates
origins = list(set(o for o in origins if o))

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# Custom exception handlers to ensure CORS headers are included in error responses
from fastapi import HTTPException

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with CORS headers."""
    origin = request.headers.get("origin", "")
    
    # Build response with CORS headers
    response = JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )
    
    # Add CORS headers if origin is allowed
    if origin in origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "*"
    
    return response


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions with CORS headers."""
    origin = request.headers.get("origin", "")
    
    # Log the full error for debugging
    logger.error(f"Unhandled exception: {exc}")
    logger.error(traceback.format_exc())
    
    # Build response with CORS headers
    # In production, hide internal details; in debug, show full error
    if settings.debug:
        error_detail = f"Internal server error: {str(exc)}"
    else:
        error_detail = "An internal error occurred. Please try again later."
    
    response = JSONResponse(
        status_code=500,
        content={"detail": error_detail}
    )
    
    # Add CORS headers if origin is allowed
    if origin in origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "*"
    
    return response



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

# Serve uploaded files
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "He&She PG API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint with database connectivity test."""
    from app.database import SessionLocal
    
    health_status = {
        "status": "healthy",
        "database": "unknown",
    }
    
    try:
        # Test database connectivity
        db = SessionLocal()
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        db.close()
        health_status["database"] = "connected"
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["database"] = "disconnected"
        if settings.debug:
            health_status["database_error"] = str(e)
    
    status_code = 200 if health_status["status"] == "healthy" else 503
    return JSONResponse(status_code=status_code, content=health_status)


@app.get("/api")
async def api_root():
    """API root endpoint."""
    return {
        "message": "He&She PG API",
        "endpoints": {
            "auth": "/api/auth",
            "users": "/api/users",
            "properties": "/api/properties",
            "bookings": "/api/bookings",
            "favorites": "/api/favorites",
            "reviews": "/api/reviews",
            "messages": "/api/messages",
            "admin": "/api/admin",
            "owner": "/api/owner",
        }
    }
