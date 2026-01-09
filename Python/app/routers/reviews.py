"""Reviews router."""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Review, Property, Profile
from app.schemas import ReviewCreate, ReviewUpdate, ReviewResponse, ReviewWithUser
from app.utils.security import get_current_user

router = APIRouter(prefix="/reviews", tags=["Reviews"])


@router.get("/property/{property_id}", response_model=List[ReviewWithUser])
async def get_property_reviews(
    property_id: UUID,
    db: Session = Depends(get_db)
):
    """Get reviews for a property."""
    reviews = db.query(Review).filter(Review.property_id == property_id).order_by(
        Review.created_at.desc()
    ).all()
    
    result = []
    for review in reviews:
        profile = db.query(Profile).filter(Profile.user_id == review.user_id).first()
        review_response = ReviewWithUser.model_validate(review)
        review_response.user_name = profile.name if profile else "Anonymous"
        review_response.user_photo = profile.profile_photo if profile else None
        result.append(review_response)
    
    return result


@router.post("/property/{property_id}", response_model=ReviewResponse)
async def create_review(
    property_id: UUID,
    review_data: ReviewCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a review for a property."""
    # Check if property exists
    property = db.query(Property).filter(Property.id == property_id).first()
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    # Can't review own property
    if property.owner_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot review your own property"
        )
    
    # Check if user already reviewed
    existing = db.query(Review).filter(
        Review.property_id == property_id,
        Review.user_id == current_user.id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already reviewed this property"
        )
    
    # Create review
    review = Review(
        property_id=property_id,
        user_id=current_user.id,
        **review_data.model_dump()
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


@router.put("/{review_id}", response_model=ReviewResponse)
async def update_review(
    review_id: UUID,
    review_data: ReviewUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a review."""
    review = db.query(Review).filter(
        Review.id == review_id,
        Review.user_id == current_user.id
    ).first()
    
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found or you don't have permission to edit it"
        )
    
    update_data = review_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(review, field, value)
    
    db.commit()
    db.refresh(review)
    return review


@router.delete("/{review_id}")
async def delete_review(
    review_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a review."""
    review = db.query(Review).filter(
        Review.id == review_id,
        Review.user_id == current_user.id
    ).first()
    
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found or you don't have permission to delete it"
        )
    
    db.delete(review)
    db.commit()
    return {"message": "Review deleted successfully"}
