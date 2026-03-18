"""Referral service for business logic."""
from uuid import UUID
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Referral, ReferralCode, User, Profile, SystemSettings

# Default reward amount if not set in system settings
DEFAULT_REFERRAL_REWARD_AMOUNT = 500.0  # INR

class ReferralService:
    @staticmethod
    def _get_reward_amount(db: Session) -> float:
        """Get referral reward amount from system settings."""
        try:
            setting = db.query(SystemSettings).filter(SystemSettings.key == "referral_reward").first()
            if setting and setting.value:
                return float(setting.value)
        except Exception as e:
            print(f"Error fetching referral_reward_amount setting: {e}")
        return DEFAULT_REFERRAL_REWARD_AMOUNT
    @staticmethod
    def get_or_create_referral_code(db: Session, user_id: UUID) -> ReferralCode:
        """Get or create user's referral code."""
        import secrets
        import string
        
        code = db.query(ReferralCode).filter(ReferralCode.user_id == user_id).first()
        
        if not code:
            # Generate unique code
            while True:
                # Generate a random 8-character uppercase alphanumeric code
                chars = string.ascii_uppercase + string.digits
                new_code = ''.join(secrets.choice(chars) for _ in range(8))
                
                existing = db.query(ReferralCode).filter(ReferralCode.code == new_code).first()
                if not existing:
                    break
            
            code = ReferralCode(
                user_id=user_id,
                code=new_code
            )
            db.add(code)
            db.commit()
            db.refresh(code)
            
        return code

    @staticmethod
    def complete_referral_for_booking(db: Session, customer_id: UUID, booking_id: UUID) -> bool:
        """
        Complete pending referral when user makes their first booking.
        Logic:
        1. Find pending referral where referred_id = customer_id
        2. Mark as completed
        3. Set reward amount
        4. Link to booking_id
        """
        referral = db.query(Referral).filter(
            Referral.referred_id == customer_id,
            Referral.status == "pending"
        ).first()
        
        if referral:
            referral.status = "completed"
            referral.reward_amount = ReferralService._get_reward_amount(db)
            referral.booking_id = booking_id
            referral.completed_at = datetime.utcnow()
            db.commit()
            return True
        return False

    @staticmethod
    def get_referral_stats(db: Session, user_id: UUID) -> dict:
        """Get referral statistics for a user."""
        referrals = db.query(Referral).filter(Referral.referrer_id == user_id).all()
        
        total = len(referrals)
        successful = len([r for r in referrals if r.status == "completed"])
        pending = len([r for r in referrals if r.status == "pending"])
        total_rewards = sum(r.reward_amount for r in referrals if r.status == "completed")
        unclaimed = sum(r.reward_amount for r in referrals if r.status == "completed" and not r.reward_claimed)
        
        code_obj = db.query(ReferralCode).filter(ReferralCode.user_id == user_id).first()
        
        return {
            "total_referrals": total,
            "successful_referrals": successful,
            "pending_referrals": pending,
            "total_rewards_earned": total_rewards,
            "unclaimed_rewards": unclaimed,
            "referral_code": code_obj.code if code_obj else None,
            "current_reward_amount": ReferralService._get_reward_amount(db)
        }

    @staticmethod
    def get_user_referrals(db: Session, user_id: UUID) -> List[dict]:
        """Get detailed list of referrals for a user."""
        referrals = db.query(Referral).filter(
            Referral.referrer_id == user_id
        ).order_by(Referral.created_at.desc()).all()
        
        result = []
        for ref in referrals:
            referred_profile = db.query(Profile).filter(Profile.user_id == ref.referred_id).first()
            referred_user = db.query(User).filter(User.id == ref.referred_id).first()
            
            result.append({
                "id": str(ref.id),
                "referee_id": str(ref.referred_id) if ref.referred_id else None,
                "referred_name": referred_profile.name if referred_profile else None,
                "referred_email": referred_user.email if referred_user else None,
                "status": ref.status,
                "reward_amount": ref.reward_amount,
                "reward_claimed": ref.reward_claimed,
                "created_at": ref.created_at,
                "completed_at": ref.completed_at
            })
            
        return result
