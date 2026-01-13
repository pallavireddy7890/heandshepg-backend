"""Favorites router."""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Favorite, Property
from app.schemas import FavoriteResponse, FavoriteWithProperty
from app.utils.security import get_current_user

router = APIRouter(prefix="/favorites", tags=["Favorites"])


@router.get("")
async def list_favorites(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List user's favorite properties."""
    try:
        favorites = db.query(Favorite).filter(Favorite.user_id == current_user.id).all()
        
        result = []
        for fav in favorites:
            property_obj = db.query(Property).filter(Property.id == fav.property_id).first()
            fav_dict = {
                "id": str(fav.id),
                "user_id": str(fav.user_id),
                "property_id": str(fav.property_id),
                "created_at": fav.created_at.isoformat() if fav.created_at else None,
            }
            if property_obj:
                fav_dict["property"] = {
                    "id": str(property_obj.id),
                    "title": property_obj.title,
                    "city": property_obj.city,
                    "locality": property_obj.locality,
                    "monthly_rent": property_obj.monthly_rent,
                    "photos": property_obj.photos,
                    "gender_preference": property_obj.gender_preference,
                }
            result.append(fav_dict)
        
        return result
    except Exception as e:
        print(f"Error in list_favorites: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ids", response_model=List[str])
async def list_favorite_ids(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get list of favorited property IDs (for quick lookup)."""
    favorites = db.query(Favorite.property_id).filter(
        Favorite.user_id == current_user.id
    ).all()
    return [str(f.property_id) for f in favorites]


@router.post("/{property_id}", response_model=FavoriteResponse)
async def add_favorite(
    property_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add a property to favorites."""
    # Check if property exists
    property = db.query(Property).filter(Property.id == property_id).first()
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    # Check if already favorited
    existing = db.query(Favorite).filter(
        Favorite.user_id == current_user.id,
        Favorite.property_id == property_id
    ).first()
    
    if existing:
        return existing
    
    # Create favorite
    favorite = Favorite(
        user_id=current_user.id,
        property_id=property_id
    )
    db.add(favorite)
    db.commit()
    db.refresh(favorite)
    return favorite


@router.delete("/{property_id}")
async def remove_favorite(
    property_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove a property from favorites."""
    favorite = db.query(Favorite).filter(
        Favorite.user_id == current_user.id,
        Favorite.property_id == property_id
    ).first()
    
    if not favorite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Favorite not found"
        )
    
    db.delete(favorite)
    db.commit()
    return {"message": "Removed from favorites"}


@router.post("/{property_id}/toggle")
async def toggle_favorite(
    property_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Toggle favorite status for a property."""
    # Check if property exists
    property = db.query(Property).filter(Property.id == property_id).first()
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    # Check if already favorited
    existing = db.query(Favorite).filter(
        Favorite.user_id == current_user.id,
        Favorite.property_id == property_id
    ).first()
    
    if existing:
        db.delete(existing)
        db.commit()
        return {"is_favorite": False, "message": "Removed from favorites"}
    else:
        favorite = Favorite(
            user_id=current_user.id,
            property_id=property_id
        )
        db.add(favorite)
        db.commit()
        return {"is_favorite": True, "message": "Added to favorites"}
