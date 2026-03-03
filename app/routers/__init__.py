"""Routers package."""
from app.routers.auth import router as auth_router
from app.routers.users import router as users_router
from app.routers.properties import router as properties_router
from app.routers.bookings import router as bookings_router
from app.routers.favorites import router as favorites_router
from app.routers.reviews import router as reviews_router
from app.routers.messages import router as messages_router
from app.routers.admin import router as admin_router
from app.routers.owner import router as owner_router
from app.routers.roommates import router as roommates_router
from app.routers.referrals import router as referrals_router
from app.routers.wallet import router as wallet_router
from app.routers.maintenance import router as maintenance_router

__all__ = [
    "auth_router",
    "users_router",
    "properties_router",
    "bookings_router",
    "favorites_router",
    "reviews_router",
    "messages_router",
    "admin_router",
    "owner_router",
    "roommates_router",
    "referrals_router",
    "wallet_router",
    "maintenance_router",
]
