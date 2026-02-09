from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List
import logging

logger = logging.getLogger(__name__)

# Known insecure secret keys that should never be used in production
INSECURE_SECRETS = {
    "your-super-secret-key-change-this-in-production",
    "change-me",
    "secret",
    "your-secret-key",
}


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://postgres:password@localhost:5432/heandshepg"
    
    # JWT - No default for secret_key forces explicit configuration
    secret_key: str = "your-super-secret-key-change-this-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # CORS
    frontend_url: str = "http://localhost:8080"
    allowed_origins: List[str] = [
        "https://heandshepg.com",
        "https://www.heandshepg.com",
    ]
    
    # Razorpay
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    
    # Email (SMTP/SendGrid)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@heandshepg.com"
    smtp_from_name: str = "He&She PG"
    
    # SMS (Twilio)
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    
    # Notification Settings
    notification_rate_limit_hours: int = 24  # Don't send duplicate confirmations within this period
    
    # Debug - Default is False for production safety
    debug: bool = False
    
    class Config:
        env_file = ".env"
        extra = "allow"
    
    def validate_production_settings(self) -> bool:
        """Validate that production-critical settings are properly configured."""
        is_valid = True
        
        if not self.debug:
            # In production mode, enforce security requirements
            if self.secret_key in INSECURE_SECRETS:
                logger.critical(
                    "SECURITY ERROR: Using insecure SECRET_KEY in production! "
                    "Generate a secure key: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
                )
                is_valid = False
            
            if len(self.secret_key) < 32:
                logger.warning("SECRET_KEY is shorter than recommended (32+ characters)")
        
        return is_valid


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    # Validate on first load
    if not settings.debug:
        if not settings.validate_production_settings():
            logger.critical("Production validation failed! Check configuration.")
    return settings

