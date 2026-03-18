"""Referral program router."""
from typing import List, Optional
from uuid import UUID
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.models import User, Profile, ReferralCode, Referral, Booking
from app.utils.security import get_current_user

router = APIRouter(prefix="/referrals", tags=["Referral Program"])

# Reward amount per successful referral (can be configured via system settings)
REFERRAL_REWARD_AMOUNT = 500.0  # INR


# ========== Pydantic Schemas ==========

class ReferralCodeResponse(BaseModel):
    id: UUID
    code: str
    is_active: bool
    total_referrals: int = 0
    total_rewards: float = 0
    created_at: datetime

    class Config:
        from_attributes = True


class ReferralResponse(BaseModel):
    id: UUID
    referee_id: Optional[UUID] = None  # For frontend compatibility
    referred_name: Optional[str] = None
    referred_email: Optional[str] = None
    status: str
    reward_amount: float
    reward_claimed: bool
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ReferralStatsResponse(BaseModel):
    total_referrals: int
    successful_referrals: int
    pending_referrals: int
    total_rewards_earned: float
    unclaimed_rewards: float
    referral_code: Optional[str] = None


class ApplyReferralRequest(BaseModel):
    referral_code: str


# ========== Endpoints ==========

from app.services.referral_service import ReferralService

@router.get("/code", response_model=ReferralCodeResponse)
async def get_or_create_referral_code(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get or create user's referral code."""
    code = ReferralService.get_or_create_referral_code(db, current_user.id)
    stats = ReferralService.get_referral_stats(db, current_user.id)
    
    response = ReferralCodeResponse.model_validate(code)
    response.total_referrals = stats["total_referrals"]
    response.total_rewards = stats["total_rewards_earned"]
    
    return response


@router.get("/stats", response_model=ReferralStatsResponse)
async def get_referral_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get referral statistics for current user."""
    stats = ReferralService.get_referral_stats(db, current_user.id)
    return ReferralStatsResponse(**stats)


@router.get("/list", response_model=List[ReferralResponse])
async def get_my_referrals(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get list of referrals made by current user."""
    return ReferralService.get_user_referrals(db, current_user.id)


@router.post("/apply")
async def apply_referral_code(
    request: ApplyReferralRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Apply a referral code (for new users)."""
    # Check if already referred
    existing = db.query(Referral).filter(Referral.referred_id == current_user.id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already used a referral code"
        )
    
    # Find referral code
    code = db.query(ReferralCode).filter(
        ReferralCode.code == request.referral_code.upper(),
        ReferralCode.is_active == True
    ).first()
    
    if not code:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid referral code"
        )
    
    # Can't refer yourself
    if code.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot use your own referral code"
        )
    
    # Create referral (pending until first booking)
    referral = Referral(
        referrer_id=code.user_id,
        referred_id=current_user.id,
        referral_code_id=code.id,
        status="pending",
        reward_amount=0  # Will be set when completed
    )
    db.add(referral)
    db.commit()
    
    return {"message": "Referral code applied successfully. Reward will be credited after your first booking."}


@router.post("/claim")
async def claim_referral_rewards(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Claim unclaimed referral rewards."""
    unclaimed = db.query(Referral).filter(
        Referral.referrer_id == current_user.id,
        Referral.status == "completed",
        Referral.reward_claimed == False
    ).all()
    
    if not unclaimed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No unclaimed rewards available"
        )
    
    from app.services.wallet_service import WalletService
    from app.models import WalletTransaction, TransactionType, TransactionStatus
    
    # Get user wallet
    wallet = WalletService.get_or_create_wallet(db, current_user.id)
    
    total_claimed = 0
    for ref in unclaimed:
        ref.reward_claimed = True
        total_claimed += ref.reward_amount
    
    # Add to wallet (convert INR to paise)
    amount_paise = int(total_claimed * 100)
    wallet.balance += amount_paise
    
    # Create a wallet transaction for the reward
    transaction = WalletTransaction(
        wallet_id=wallet.id,
        payer_id=None, # System
        receiver_id=current_user.id,
        amount=amount_paise,
        transaction_type=TransactionType.credit,
        status=TransactionStatus.completed,
        description=f"Referral reward claimed for {len(unclaimed)} successful referrals"
    )
    db.add(transaction)
    db.commit()
    
    return {
        "message": f"Successfully claimed ₹{total_claimed}",
        "amount_claimed": total_claimed
    }


# Helper function to complete a referral when booking is confirmed
def complete_referral_for_booking(db: Session, customer_id: UUID, booking_id: UUID):
    """Complete pending referral when user makes their first booking."""
    referral = db.query(Referral).filter(
        Referral.referred_id == customer_id,
        Referral.status == "pending"
    ).first()
    
    if referral:
        referral.status = "completed"
        referral.reward_amount = REFERRAL_REWARD_AMOUNT
        referral.booking_id = booking_id
        referral.completed_at = datetime.utcnow()
        db.commit()
        return True
    return False
