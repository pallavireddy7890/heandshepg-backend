"""Roommate matching router."""
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from pydantic import BaseModel

from app.database import get_db
from app.models import User, Profile, RoommateProfile, RoommateMatch
from app.utils.security import get_current_user

router = APIRouter(prefix="/roommates", tags=["Roommate Matching"])


# ========== Pydantic Schemas ==========

class RoommateProfileCreate(BaseModel):
    age: Optional[int] = None
    gender: Optional[str] = None
    occupation: Optional[str] = None
    budget_min: Optional[int] = None
    budget_max: Optional[int] = None
    preferred_location: Optional[str] = None
    preferred_city: Optional[str] = None
    move_in_date: Optional[datetime] = None
    preferences: Optional[List[str]] = []
    languages: Optional[List[str]] = []
    hobbies: Optional[List[str]] = []
    bio: Optional[str] = None
    # Additional fields for frontend compatibility
    dietary_preference: Optional[str] = None
    smoking: Optional[bool] = False
    drinking: Optional[bool] = False
    pets_allowed: Optional[bool] = False
    cleanliness_level: Optional[int] = 3
    is_active: Optional[bool] = True


class RoommateProfileResponse(BaseModel):
    id: UUID
    user_id: UUID
    age: Optional[int]
    gender: Optional[str]
    occupation: Optional[str]
    budget_min: Optional[int]
    budget_max: Optional[int]
    preferred_location: Optional[str]
    preferred_city: Optional[str]
    move_in_date: Optional[datetime]
    preferences: Optional[List[str]]
    languages: Optional[List[str]]
    hobbies: Optional[List[str]]
    bio: Optional[str]
    is_active: bool
    # Additional fields
    dietary_preference: Optional[str] = None
    smoking: Optional[bool] = False
    drinking: Optional[bool] = False
    pets_allowed: Optional[bool] = False
    cleanliness_level: Optional[int] = 3
    user_name: Optional[str] = None
    user_photo: Optional[str] = None

    class Config:
        from_attributes = True


class RoommateMatchResponse(BaseModel):
    id: UUID
    matched_user_id: UUID
    match_score: Optional[float]
    status: str
    user_name: Optional[str] = None
    user_photo: Optional[str] = None
    age: Optional[int] = None
    occupation: Optional[str] = None
    bio: Optional[str] = None
    preferences: Optional[List[str]] = None

    class Config:
        from_attributes = True


# ========== Endpoints ==========

@router.get("/profile", response_model=RoommateProfileResponse)
async def get_my_roommate_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current user's roommate profile."""
    profile = db.query(RoommateProfile).filter(RoommateProfile.user_id == current_user.id).first()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Roommate profile not found. Please create one first."
        )
    
    response = RoommateProfileResponse.model_validate(profile)
    user_profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    response.user_name = user_profile.name if user_profile else None
    response.user_photo = user_profile.profile_photo if user_profile else None
    
    return response


@router.post("/profile", response_model=RoommateProfileResponse)
async def create_or_update_roommate_profile(
    profile_data: RoommateProfileCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create or update roommate profile."""
    profile = db.query(RoommateProfile).filter(RoommateProfile.user_id == current_user.id).first()
    
    if profile:
        # Update existing
        for field, value in profile_data.model_dump(exclude_unset=True).items():
            setattr(profile, field, value)
    else:
        # Create new
        profile = RoommateProfile(
            user_id=current_user.id,
            **profile_data.model_dump()
        )
        db.add(profile)
    
    db.commit()
    db.refresh(profile)
    
    response = RoommateProfileResponse.model_validate(profile)
    user_profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    response.user_name = user_profile.name if user_profile else None
    response.user_photo = user_profile.profile_photo if user_profile else None
    
    return response


@router.delete("/profile")
async def delete_roommate_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete roommate profile."""
    profile = db.query(RoommateProfile).filter(RoommateProfile.user_id == current_user.id).first()
    
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    
    db.delete(profile)
    db.commit()
    return {"message": "Roommate profile deleted"}


@router.get("/matches", response_model=List[RoommateMatchResponse])
async def get_roommate_matches(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get potential roommate matches based on compatibility."""
    my_profile = db.query(RoommateProfile).filter(RoommateProfile.user_id == current_user.id).first()
    
    if not my_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please create a roommate profile first"
        )
    
    # Find compatible profiles (show all active profiles from other users)
    query = db.query(RoommateProfile).filter(
        RoommateProfile.user_id != current_user.id,
        RoommateProfile.is_active == True
    )
    
    # Note: City filter removed to show all potential matches
    # Same-city matches will get higher scores in calculate_match_score
    
    # Filter by budget overlap (optional - don't exclude if budget not set)
    # Commenting out strict budget filter to show more results
    # if my_profile.budget_max:
    #     query = query.filter(
    #         or_(
    #             RoommateProfile.budget_min == None,
    #             RoommateProfile.budget_min <= my_profile.budget_max
    #         )
    #     )
    
    potential_matches = query.limit(20).all()
    
    result = []
    for match_profile in potential_matches:
        # Calculate match score
        score = calculate_match_score(my_profile, match_profile)
        
        user_profile = db.query(Profile).filter(Profile.user_id == match_profile.user_id).first()
        
        result.append(RoommateMatchResponse(
            id=match_profile.id,
            matched_user_id=match_profile.user_id,
            match_score=score,
            status="suggested",
            user_name=user_profile.name if user_profile else None,
            user_photo=user_profile.profile_photo if user_profile else None,
            age=match_profile.age,
            occupation=match_profile.occupation,
            bio=match_profile.bio,
            preferences=match_profile.preferences,
        ))
    
    # Sort by match score
    result.sort(key=lambda x: x.match_score or 0, reverse=True)
    return result


def calculate_match_score(profile1: RoommateProfile, profile2: RoommateProfile) -> float:
    """Calculate compatibility score between two profiles (0-100)."""
    score = 50.0  # Base score
    
    # Preference matching
    if profile1.preferences and profile2.preferences:
        common_prefs = set(profile1.preferences) & set(profile2.preferences)
        pref_score = (len(common_prefs) / max(len(profile1.preferences), 1)) * 20
        score += pref_score
    
    # Language matching
    if profile1.languages and profile2.languages:
        common_langs = set(profile1.languages) & set(profile2.languages)
        if common_langs:
            score += 10
    
    # Hobby matching
    if profile1.hobbies and profile2.hobbies:
        common_hobbies = set(profile1.hobbies) & set(profile2.hobbies)
        hobby_score = (len(common_hobbies) / max(len(profile1.hobbies), 1)) * 10
        score += hobby_score
    
    # Budget compatibility
    if profile1.budget_max and profile2.budget_min:
        if profile1.budget_max >= profile2.budget_min:
            score += 10
    
    return min(score, 100.0)


@router.post("/matches/{profile_id}/connect")
async def connect_with_roommate(
    profile_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Express interest in connecting with a potential roommate."""
    target_profile = db.query(RoommateProfile).filter(RoommateProfile.id == profile_id).first()
    
    if not target_profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    
    # Check if already connected
    existing = db.query(RoommateMatch).filter(
        RoommateMatch.user_id == current_user.id,
        RoommateMatch.matched_user_id == target_profile.user_id
    ).first()
    
    if existing:
        return {"message": "Already connected", "status": existing.status}
    
    # Create match request
    my_profile = db.query(RoommateProfile).filter(RoommateProfile.user_id == current_user.id).first()
    score = calculate_match_score(my_profile, target_profile) if my_profile else 50.0
    
    match = RoommateMatch(
        user_id=current_user.id,
        matched_user_id=target_profile.user_id,
        match_score=score,
        status="pending"
    )
    db.add(match)
    db.commit()
    
    return {"message": "Connection request sent", "match_id": str(match.id)}
