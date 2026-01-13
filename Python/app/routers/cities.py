"""Cities router for location management."""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models import City, Area


class AreaResponse(BaseModel):
    id: UUID
    name: str
    
    class Config:
        from_attributes = True


class CityResponse(BaseModel):
    id: UUID
    name: str
    image_url: Optional[str] = None
    areas: List[AreaResponse] = []
    
    class Config:
        from_attributes = True


router = APIRouter(prefix="/cities", tags=["Cities"])


@router.get("", response_model=List[CityResponse])
async def get_cities(
    db: Session = Depends(get_db),
    include_areas: bool = True
):
    """Get all active cities with their areas."""
    query = db.query(City).filter(City.is_active == True).order_by(City.display_order, City.name)
    cities = query.all()
    
    result = []
    for city in cities:
        city_data = {
            "id": city.id,
            "name": city.name,
            "image_url": city.image_url,
            "areas": []
        }
        if include_areas:
            areas = db.query(Area).filter(
                Area.city_id == city.id,
                Area.is_active == True
            ).order_by(Area.display_order, Area.name).all()
            city_data["areas"] = [{"id": a.id, "name": a.name} for a in areas]
        result.append(city_data)
    
    return result


@router.get("/{city_id}", response_model=CityResponse)
async def get_city(
    city_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a specific city with its areas."""
    city = db.query(City).filter(City.id == city_id).first()
    if not city:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="City not found"
        )
    
    areas = db.query(Area).filter(
        Area.city_id == city.id,
        Area.is_active == True
    ).order_by(Area.display_order, Area.name).all()
    
    return {
        "id": city.id,
        "name": city.name,
        "image_url": city.image_url,
        "areas": [{"id": a.id, "name": a.name} for a in areas]
    }
