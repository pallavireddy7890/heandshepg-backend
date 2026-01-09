"""He&She PG Backend - FastAPI Application."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

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
)
from app.routers.websocket import router as websocket_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup: Create tables if they don't exist
    # Note: In production, use Alembic migrations instead
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

# CORS Configuration
origins = [
    settings.frontend_url,
    "http://localhost:8080",
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:8080",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
app.include_router(websocket_router, prefix="/api")


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
    """Health check endpoint."""
    return {"status": "healthy"}


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
