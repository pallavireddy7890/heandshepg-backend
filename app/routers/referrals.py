"""Referral program router."""
from typing import List, Optional
from uuid import UUID
import secrets
import string

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
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

@router.get("/code", response_model=ReferralCodeResponse)
async def get_or_create_referral_code(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get or create user's referral code."""
    code = db.query(ReferralCode).filter(ReferralCode.user_id == current_user.id).first()
    
    if not code:
        # Generate unique code
        while True:
            new_code = generate_referral_code()
            existing = db.query(ReferralCode).filter(ReferralCode.code == new_code).first()
            if not existing:
                break
        
        code = ReferralCode(
            user_id=current_user.id,
            code=new_code
        )
        db.add(code)
        db.commit()
        db.refresh(code)
    
    # Get stats
    referral_stats = db.query(
        func.count(Referral.id).label("total"),
        func.sum(Referral.reward_amount).label("rewards")
    ).filter(Referral.referrer_id == current_user.id).first()
    
    response = ReferralCodeResponse.model_validate(code)
    response.total_referrals = referral_stats.total or 0
    response.total_rewards = float(referral_stats.rewards or 0)
    
    return response


def generate_referral_code(length: int = 8) -> str:
    """Generate a random referral code."""
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


@router.get("/stats", response_model=ReferralStatsResponse)
async def get_referral_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get referral statistics for current user."""
    referrals = db.query(Referral).filter(Referral.referrer_id == current_user.id).all()
    
    total = len(referrals)
    successful = len([r for r in referrals if r.status == "completed"])
    pending = len([r for r in referrals if r.status == "pending"])
    total_rewards = sum(r.reward_amount for r in referrals if r.status == "completed")
    unclaimed = sum(r.reward_amount for r in referrals if r.status == "completed" and not r.reward_claimed)
    
    code = db.query(ReferralCode).filter(ReferralCode.user_id == current_user.id).first()
    
    return ReferralStatsResponse(
        total_referrals=total,
        successful_referrals=successful,
        pending_referrals=pending,
        total_rewards_earned=total_rewards,
        unclaimed_rewards=unclaimed,
        referral_code=code.code if code else None
    )


@router.get("/list", response_model=List[ReferralResponse])
async def get_my_referrals(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get list of referrals made by current user."""
    referrals = db.query(Referral).filter(
        Referral.referrer_id == current_user.id
    ).order_by(Referral.created_at.desc()).all()
    
    result = []
    for ref in referrals:
        referred_profile = db.query(Profile).filter(Profile.user_id == ref.referred_id).first()
        referred_user = db.query(User).filter(User.id == ref.referred_id).first()
        
        result.append(ReferralResponse(
            id=ref.id,
            referred_name=referred_profile.name if referred_profile else None,
            referred_email=referred_user.email if referred_user else None,
            status=ref.status,
            reward_amount=ref.reward_amount,
            reward_claimed=ref.reward_claimed,
            created_at=ref.created_at,
            completed_at=ref.completed_at
        ))
    
    return result


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
    
    total_claimed = 0
    for ref in unclaimed:
        ref.reward_claimed = True
        total_claimed += ref.reward_amount
    
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
