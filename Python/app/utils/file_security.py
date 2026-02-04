"""Secure file upload utilities.

Provides MIME type validation, filename sanitization, and secure file handling
to prevent security issues with file uploads.
"""
import os
import re
import uuid
import logging
from typing import Optional, Tuple, Set
from pathlib import Path

from fastapi import UploadFile, HTTPException, status

logger = logging.getLogger(__name__)

# Allowed MIME types grouped by category
ALLOWED_MIME_TYPES = {
    # Images
    "image/jpeg": [".jpg", ".jpeg"],
    "image/png": [".png"],
    "image/webp": [".webp"],
    "image/gif": [".gif"],
    # Documents
    "application/pdf": [".pdf"],
}

# Flatten to set for quick lookup
ALLOWED_MIMES: Set[str] = set(ALLOWED_MIME_TYPES.keys())
ALLOWED_EXTENSIONS: Set[str] = {ext for exts in ALLOWED_MIME_TYPES.values() for ext in exts}

# File size limits
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB for images
MAX_FILES_PER_USER = 50  # Maximum files per user directory

# Magic bytes for common file types (first N bytes)
FILE_SIGNATURES = {
    b'\xff\xd8\xff': 'image/jpeg',
    b'\x89PNG\r\n\x1a\n': 'image/png',
    b'RIFF': 'image/webp',  # WebP starts with RIFF
    b'GIF87a': 'image/gif',
    b'GIF89a': 'image/gif',
    b'%PDF': 'application/pdf',
}


def detect_mime_type(content: bytes) -> Optional[str]:
    """
    Detect MIME type from file content using magic bytes.
    
    This is more reliable than trusting the Content-Type header
    or file extension provided by the client.
    """
    for signature, mime_type in FILE_SIGNATURES.items():
        if content.startswith(signature):
            return mime_type
    
    # Special check for WebP (RIFF + WEBP)
    if content[:4] == b'RIFF' and content[8:12] == b'WEBP':
        return 'image/webp'
    
    return None


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal and other attacks.
    
    - Removes directory components
    - Removes special characters
    - Limits length
    - Converts to lowercase
    """
    if not filename:
        return str(uuid.uuid4().hex)
    
    # Get just the filename, no path
    filename = os.path.basename(filename)
    
    # Remove any null bytes or other control characters
    filename = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', filename)
    
    # Split into name and extension
    name, ext = os.path.splitext(filename)
    
    # Remove dangerous characters from name
    # Allow only alphanumeric, underscore, hyphen, period
    name = re.sub(r'[^a-zA-Z0-9_\-.]', '_', name)
    
    # Limit name length
    name = name[:50]
    
    # Normalize extension
    ext = ext.lower()
    
    # Ensure extension is allowed
    if ext not in ALLOWED_EXTENSIONS:
        ext = ''
    
    return f"{name}{ext}" if name else str(uuid.uuid4().hex) + ext


def generate_secure_filename(original_filename: str, prefix: str = "") -> str:
    """
    Generate a secure, unique filename.
    
    Combines a UUID with sanitized original extension for uniqueness
    while preserving the file type.
    """
    _, ext = os.path.splitext(original_filename)
    ext = ext.lower()
    
    # Validate extension
    if ext not in ALLOWED_EXTENSIONS:
        ext = ""
    
    unique_id = uuid.uuid4().hex
    
    if prefix:
        prefix = re.sub(r'[^a-zA-Z0-9_\-]', '_', prefix)[:20]
        return f"{prefix}_{unique_id}{ext}"
    
    return f"{unique_id}{ext}"


async def validate_file_upload(
    file: UploadFile,
    allowed_types: Optional[Set[str]] = None,
    max_size: int = MAX_FILE_SIZE
) -> Tuple[bytes, str]:
    """
    Validate an uploaded file for security.
    
    Args:
        file: FastAPI UploadFile object
        allowed_types: Set of allowed MIME types (defaults to all allowed)
        max_size: Maximum file size in bytes
        
    Returns:
        Tuple of (file_content, detected_mime_type)
        
    Raises:
        HTTPException: If validation fails
    """
    allowed = allowed_types or ALLOWED_MIMES
    
    # Read file content
    content = await file.read()
    
    # Check file size
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size is {max_size // 1024 // 1024}MB."
        )
    
    # Check for empty file
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file not allowed."
        )
    
    # Detect actual MIME type from content
    detected_mime = detect_mime_type(content)
    
    if detected_mime is None:
        # Couldn't detect, fall back to extension check
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
            )
        # Warn but allow if extension is valid
        logger.warning(f"Could not detect MIME type for file with extension {ext}")
        # Guess MIME from extension
        for mime, exts in ALLOWED_MIME_TYPES.items():
            if ext in exts:
                detected_mime = mime
                break
    
    if detected_mime not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{detected_mime}' not allowed. Allowed types: {', '.join(allowed)}"
        )
    
    # Validate extension matches content (prevent .pdf with image content, etc.)
    if file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        expected_exts = ALLOWED_MIME_TYPES.get(detected_mime, [])
        if ext and expected_exts and ext not in expected_exts:
            logger.warning(
                f"Extension mismatch: file {file.filename} has extension {ext} "
                f"but content is {detected_mime}"
            )
            # Allow but log - the content type is what matters
    
    return content, detected_mime


def check_user_file_limit(user_dir: str, max_files: int = MAX_FILES_PER_USER) -> bool:
    """
    Check if user has exceeded file upload limit.
    
    Returns True if under limit, False if exceeded.
    """
    if not os.path.exists(user_dir):
        return True
    
    try:
        file_count = sum(1 for _ in Path(user_dir).iterdir() if _.is_file())
        return file_count < max_files
    except Exception as e:
        logger.error(f"Error checking user file limit: {e}")
        return True  # Allow on error


def save_file_securely(
    content: bytes,
    directory: str,
    filename: str,
    overwrite: bool = False
) -> str:
    """
    Save file content securely.
    
    Args:
        content: File content bytes
        directory: Target directory (must already exist)
        filename: Target filename (should be sanitized)
        overwrite: Whether to overwrite existing file
        
    Returns:
        Full path to saved file
        
    Raises:
        HTTPException: If save fails
    """
    # Ensure directory exists
    os.makedirs(directory, exist_ok=True)
    
    # Build full path
    file_path = os.path.join(directory, filename)
    
    # Verify path is within expected directory (prevent path traversal)
    real_dir = os.path.realpath(directory)
    real_path = os.path.realpath(file_path)
    
    if not real_path.startswith(real_dir):
        logger.error(f"Path traversal attempt detected: {file_path}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename."
        )
    
    # Check if file exists
    if os.path.exists(file_path) and not overwrite:
        # Generate new unique name
        name, ext = os.path.splitext(filename)
        filename = f"{name}_{uuid.uuid4().hex[:8]}{ext}"
        file_path = os.path.join(directory, filename)
    
    # Write file
    try:
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.error(f"Failed to save file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save file."
        )
    
    return file_path
