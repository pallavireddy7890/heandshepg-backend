"""Cities router for location management."""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from app.database import get_db
from app.models import City, Area, Property


class AreaResponse(BaseModel):
    id: Optional[str] = None
    name: str
    is_popular: bool = False
    
    class Config:
        from_attributes = True


class CityResponse(BaseModel):
    id: UUID
    name: str
    slug: Optional[str] = None
    status: str = "AVAILABLE"
    image_url: Optional[str] = None
    tagline: Optional[str] = None
    property_count: int = 0
    areas: List[AreaResponse] = []
    
    class Config:
        from_attributes = True


router = APIRouter(prefix="/cities", tags=["Cities"])


@router.get("")
async def get_cities(
    db: Session = Depends(get_db),
    include_areas: bool = True
):
    """Get all cities sorted by priority, AVAILABLE first, with property counts and areas."""
    
    # Get property counts per city (case-insensitive)
    property_counts_raw = db.query(
        func.lower(Property.city), func.count(Property.id)
    ).filter(Property.status == "active").group_by(func.lower(Property.city)).all()
    
    property_counts = {c[0].lower() if c[0] else '': c[1] for c in property_counts_raw}
    
    # Get all active cities, sorted by priority_order
    cities = db.query(City).filter(
        City.is_active == True
    ).order_by(City.priority_order, City.name).all()
    
    available_cities = []
    coming_soon_cities = []
    
    for city in cities:
        # Get areas from property localities (case-insensitive city matching)
        localities = db.query(Property.locality).filter(
            Property.status == "active",
            func.lower(Property.city) == city.name.lower(),
            Property.locality.isnot(None),
            Property.locality != ""
        ).distinct().all()
        
        areas_list = []
        for loc in localities:
            if loc[0]:
                areas_list.append({
                    "id": None,
                    "name": loc[0],
                    "is_popular": True  # All areas from properties are considered popular
                })
        areas_list.sort(key=lambda x: x["name"])
        
        city_count = property_counts.get(city.name.lower(), 0)
        
        # Use admin-set status, default to AVAILABLE if not set
        # Only auto-set to COMING_SOON if no explicit status is set AND no properties
        city_status = city.status if city.status else ("AVAILABLE" if city_count > 0 else "COMING_SOON")
        
        city_data = {
            "id": city.id,
            "name": city.name,
            "slug": city.slug or city.name.lower().replace(" ", "-"),
            "status": city_status,
            "image_url": city.image_url,
            "tagline": city.tagline,
            "property_count": city_count,
            "areas": areas_list
        }
        
        if city_status == "AVAILABLE":
            available_cities.append(city_data)
        else:
            coming_soon_cities.append(city_data)
    
    # Return AVAILABLE cities first, then COMING_SOON
    return available_cities + coming_soon_cities


@router.get("/{city_id}")
async def get_city(
    city_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a specific city with its areas and property count."""
    city = db.query(City).filter(City.id == city_id).first()
    if not city:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="City not found"
        )
    
    # Get property count (case-insensitive)
    property_count = db.query(func.count(Property.id)).filter(
        Property.status == "active",
        func.lower(Property.city) == city.name.lower()
    ).scalar() or 0
    
    # Get areas from property localities (case-insensitive)
    localities = db.query(Property.locality).filter(
        Property.status == "active",
        func.lower(Property.city) == city.name.lower(),
        Property.locality.isnot(None)
    ).distinct().all()
    
    
    areas_list = [{"id": None, "name": loc[0], "is_popular": True} for loc in localities if loc[0]]
    
    # Use admin-set status, fallback to property count logic only if no status set
    city_status = city.status if city.status else ("AVAILABLE" if property_count > 0 else "COMING_SOON")
    
    return {
        "id": city.id,
        "name": city.name,
        "slug": city.slug or city.name.lower().replace(" ", "-"),
        "status": city_status,
        "image_url": city.image_url,
        "tagline": city.tagline,
        "property_count": property_count,
        "areas": areas_list
    }

