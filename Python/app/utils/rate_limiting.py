"""Rate limiting utilities for auth endpoints.

Provides decorators and helpers for rate limiting sensitive endpoints
to prevent brute force attacks, OTP abuse, and email bombing.
"""
import time
import logging
from typing import Dict, Optional, Tuple
from collections import defaultdict
from functools import wraps

from fastapi import Request, HTTPException, status

logger = logging.getLogger(__name__)


class InMemoryRateLimiter:
    """
    Simple in-memory rate limiter for auth endpoints.
    
    This is a fallback when slowapi is not available or for more granular control.
    For production with multiple instances, use Redis-backed rate limiting.
    
    Rate limits by IP + endpoint:
    - /auth/signup: 3 requests per minute
    - /auth/login: 5 requests per minute  
    - /auth/verify-email: 5 requests per minute
    - /auth/resend-otp: 3 requests per minute
    - /auth/forgot-password: 2 requests per minute
    """
    
    # Rate limits: (max_requests, window_seconds)
    LIMITS = {
        "/api/auth/signup": (3, 60),
        "/api/auth/login": (5, 60),
        "/api/auth/login/json": (5, 60),
        "/api/auth/verify-email": (5, 60),
        "/api/auth/resend-otp": (3, 60),
        "/api/auth/forgot-password": (2, 60),
    }
    
    # Default limit for other auth endpoints
    DEFAULT_LIMIT = (10, 60)  # 10 requests per minute
    
    def __init__(self):
        # Structure: {(ip, path): [(timestamp1), (timestamp2), ...]}
        self._requests: Dict[Tuple[str, str], list] = defaultdict(list)
        self._last_cleanup = time.time()
        self._cleanup_interval = 300  # Cleanup every 5 minutes
    
    def _cleanup_old_entries(self):
        """Remove entries older than the largest window."""
        now = time.time()
        
        # Only cleanup periodically
        if now - self._last_cleanup < self._cleanup_interval:
            return
        
        self._last_cleanup = now
        max_window = max(limit[1] for limit in self.LIMITS.values())
        cutoff = now - max_window - 60  # Add buffer
        
        keys_to_delete = []
        for key, timestamps in self._requests.items():
            # Remove old timestamps
            self._requests[key] = [ts for ts in timestamps if ts > cutoff]
            if not self._requests[key]:
                keys_to_delete.append(key)
        
        for key in keys_to_delete:
            del self._requests[key]
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request, handling proxies."""
        # Check for forwarded header (behind proxy/load balancer)
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Take the first IP (original client)
            return forwarded.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # Fall back to direct client
        return request.client.host if request.client else "unknown"
    
    def check_rate_limit(self, request: Request) -> Optional[Tuple[int, int]]:
        """
        Check if request is within rate limit.
        
        Returns:
            None if within limit
            (retry_after_seconds, limit) if rate limited
        """
        self._cleanup_old_entries()
        
        client_ip = self._get_client_ip(request)
        path = request.url.path
        
        # Get limit for this path
        max_requests, window_seconds = self.LIMITS.get(path, self.DEFAULT_LIMIT)
        
        key = (client_ip, path)
        now = time.time()
        
        # Clean old timestamps for this key
        window_start = now - window_seconds
        self._requests[key] = [ts for ts in self._requests[key] if ts > window_start]
        
        # Check if over limit
        if len(self._requests[key]) >= max_requests:
            # Calculate retry-after
            oldest = min(self._requests[key])
            retry_after = int(oldest + window_seconds - now) + 1
            
            logger.warning(
                f"Rate limit exceeded for {client_ip} on {path}: "
                f"{len(self._requests[key])}/{max_requests} in {window_seconds}s"
            )
            
            return (retry_after, max_requests)
        
        # Record this request
        self._requests[key].append(now)
        return None
    
    def is_rate_limited(self, request: Request) -> bool:
        """Simple check if rate limited."""
        return self.check_rate_limit(request) is not None


# Global rate limiter instance
auth_rate_limiter = InMemoryRateLimiter()


async def check_auth_rate_limit(request: Request):
    """
    FastAPI dependency to check rate limits on auth endpoints.
    
    Usage:
        @router.post("/signup")
        async def signup(
            request: Request,
            rate_limit: None = Depends(check_auth_rate_limit),
            ...
        ):
    """
    result = auth_rate_limiter.check_rate_limit(request)
    
    if result is not None:
        retry_after, limit = result
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many requests. Please try again in {retry_after} seconds.",
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
            }
        )
    
    return None


def rate_limit_auth(
    max_requests: int = 5,
    window_seconds: int = 60,
    message: str = "Too many attempts. Please try again later."
):
    """
    Decorator for rate limiting individual functions.
    
    Usage:
        @rate_limit_auth(max_requests=3, window_seconds=60)
        async def signup(...):
    """
    def decorator(func):
        requests_by_ip: Dict[str, list] = defaultdict(list)
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Find request in args
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if not request:
                request = kwargs.get('request')
            
            if request:
                # Get client IP
                forwarded = request.headers.get("x-forwarded-for")
                client_ip = (
                    forwarded.split(",")[0].strip() if forwarded
                    else request.client.host if request.client
                    else "unknown"
                )
                
                now = time.time()
                window_start = now - window_seconds
                
                # Clean and check
                requests_by_ip[client_ip] = [
                    ts for ts in requests_by_ip[client_ip]
                    if ts > window_start
                ]
                
                if len(requests_by_ip[client_ip]) >= max_requests:
                    oldest = min(requests_by_ip[client_ip])
                    retry_after = int(oldest + window_seconds - now) + 1
                    
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=message,
                        headers={"Retry-After": str(retry_after)}
                    )
                
                requests_by_ip[client_ip].append(now)
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator
