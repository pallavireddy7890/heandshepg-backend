"""SQLAlchemy models for wallet and transactions."""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID, ENUM
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from app.database import Base


class TransactionType(str, enum.Enum):
    credit = "credit"
    debit = "debit"
    hold = "hold"
    release = "release"
    withdrawal = "withdrawal"


class TransactionStatus(str, enum.Enum):
    pending = "pending"
    otp_sent = "otp_sent"
    verified = "verified"
    completed = "completed"
    failed = "failed"
    refunded = "refunded"
    rejected = "rejected"


class Wallet(Base):
    """User wallet for storing balance."""
    __tablename__ = "wallets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    balance = Column(Integer, default=0)  # Balance in paise (INR * 100)
    pending_balance = Column(Integer, default=0)  # Money awaiting OTP verification
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="wallet")
    transactions = relationship("WalletTransaction", back_populates="wallet", cascade="all, delete-orphan")


class WalletTransaction(Base):
    """Transaction record for wallet operations."""
    __tablename__ = "wallet_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wallet_id = Column(UUID(as_uuid=True), ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False)
    booking_id = Column(UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="SET NULL"))
    
    # Parties involved
    payer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))  # Customer
    receiver_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))  # Owner
    
    # Transaction details
    amount = Column(Integer, nullable=False)  # Amount in paise
    payment_type = Column(String(20), default='total')  # 'rent', 'deposit', 'total', 'maintenance'
    transaction_type = Column(ENUM('credit', 'debit', 'hold', 'release', 'withdrawal',
                                   name='transaction_type', create_type=False), nullable=False)
    status = Column(ENUM('pending', 'otp_sent', 'verified', 'completed', 'failed', 'refunded', 'rejected',
                         name='transaction_status', create_type=False), default='pending')
    
    # Withdrawal details (snapshots of bank details at time of request)
    bank_account_number = Column(String(50))
    bank_ifsc_code = Column(String(20))
    bank_name = Column(String(255))
    
    # Admin notes/Rejection reason
    admin_notes = Column(Text)
    
    # OTP verification
    otp_verified = Column(Boolean, default=False)
    otp_verified_at = Column(DateTime(timezone=True))
    
    # Payment reference
    razorpay_payment_id = Column(String(255))
    razorpay_order_id = Column(String(255))
    
    # Description
    description = Column(Text)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    wallet = relationship("Wallet", back_populates="transactions")
    booking = relationship("Booking")
    otp = relationship("TransactionOTP", back_populates="transaction", uselist=False, cascade="all, delete-orphan")


class TransactionOTP(Base):
    """OTP for transaction verification."""
    __tablename__ = "transaction_otps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("wallet_transactions.id", ondelete="CASCADE"), nullable=False)
    
    # OTP details
    otp_code = Column(String(6), nullable=False)
    otp_type = Column(String(20), nullable=False)  # 'customer' or 'owner'
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Verification
    is_verified = Column(Boolean, default=False)
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    
    # Expiration
    expires_at = Column(DateTime(timezone=True), nullable=False)
    verified_at = Column(DateTime(timezone=True))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    transaction = relationship("WalletTransaction", back_populates="otp")
