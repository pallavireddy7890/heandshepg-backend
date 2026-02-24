"""Property photo upload endpoint."""
import os
import uuid as uuid_lib
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from app.utils.security import get_current_user
from app.models import User

router = APIRouter(prefix="/properties", tags=["Properties"])

# Configure upload directory
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "properties")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB per file
MAX_FILES = 20


@router.post("/upload-photos")
async def upload_property_photos(
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
):
    """Upload multiple property photos. Returns list of URL paths."""
    if len(files) > MAX_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_FILES} files allowed at once",
        )

    uploaded_urls = []

    for file in files:
        # Validate extension
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{file.filename}' has unsupported type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
            )

        # Read and validate size
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{file.filename}' exceeds 5MB limit",
            )

        # Create user-specific directory
        user_dir = os.path.join(UPLOAD_DIR, str(current_user.id))
        os.makedirs(user_dir, exist_ok=True)

        # Save with unique name
        unique_filename = f"prop_{uuid_lib.uuid4().hex}{ext}"
        file_path = os.path.join(user_dir, unique_filename)

        with open(file_path, "wb") as f:
            f.write(content)

        url_path = f"/uploads/properties/{current_user.id}/{unique_filename}"
        uploaded_urls.append(url_path)

    return {"urls": uploaded_urls, "count": len(uploaded_urls)}
