"""SQLAlchemy models package."""
from app.models.user import User, Profile, UserRole, OwnersProfile, AppRole, KycStatus
from app.models.property import Property, Room, GenderPreference
from app.models.booking import Booking, Payment, Invoice, BookingStatus, PaymentStatus, PaymentType, InvoiceStatus
from app.models.review import Review, Favorite
from app.models.message import Conversation, Message, Notification
from app.models.admin import AuditLog, SystemSettings
from app.models.features import RoommateProfile, RoommateMatch, ReferralCode, Referral
from app.models.city import City, Area
from app.models.notification_log import NotificationLog
from app.models.wallet import Wallet, WalletTransaction, TransactionOTP, TransactionType, TransactionStatus
from app.models.email_verification import EmailVerification


__all__ = [
    # User models
    "User",
    "Profile", 
    "UserRole",
    "OwnersProfile",
    "AppRole",
    "KycStatus",
    # Property models
    "Property",
    "Room",
    "GenderPreference",
    # Booking models
    "Booking",
    "Payment",
    "Invoice",
    "BookingStatus",
    "PaymentStatus",
    "PaymentType",
    "InvoiceStatus",
    # Review models
    "Review",
    "Favorite",
    # Message models
    "Conversation",
    "Message",
    "Notification",
    # Admin models
    "AuditLog",
    "SystemSettings",
    # Feature models
    "RoommateProfile",
    "RoommateMatch",
    "ReferralCode",
    "Referral",
    # Location models
    "City",
    "Area",
    # Notification models
    "NotificationLog",
    # Wallet models
    "Wallet",
    "WalletTransaction",
    "TransactionOTP",
    "TransactionType",
    "TransactionStatus",
    # Email verification
    "EmailVerification",
]


