from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os

load_dotenv()

class Settings(BaseSettings):
    # Application settings
    APP_NAME: str = "Secure Auth System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # Security settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30  # 30 minutes
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7      # 7 days
    
    # Database settings
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./auth.db")
    
    # CORS settings
    BACKEND_CORS_ORIGINS: list = ["http://localhost:5500", "http://127.0.0.1:5500"]
    
    class Config:
        env_file = ".env"

settings = Settings()