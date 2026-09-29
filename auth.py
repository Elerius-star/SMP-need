from datetime import datetime, timedelta
from typing import Optional, Union
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
import secrets
import string

from . import models, schemas
from .config import settings

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AuthService:
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a plain password against a hashed password"""
        return pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        """Hash a password"""
        return pwd_context.hash(password)
    
    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT access token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire, "type": "access"})
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return encoded_jwt
    
    @staticmethod
    def create_refresh_token(data: dict) -> str:
        """Create a refresh token (JWT + random string)"""
        # Create JWT part
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": expire, "type": "refresh"})
        jwt_part = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        
        # Add random part for extra security
        random_part = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
        return f"{jwt_part}.{random_part}"
    
    @staticmethod
    def decode_token(token: str) -> dict:
        """Decode and validate a JWT token"""
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            return payload
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    @staticmethod
    def authenticate_user(db: Session, username: str, password: str) -> Optional[models.User]:
        """Authenticate a user by username and password"""
        user = db.query(models.User).filter(
            (models.User.username == username) | (models.User.email == username)
        ).first()
        
        if not user:
            return None
        if not AuthService.verify_password(password, user.hashed_password):
            return None
        
        return user
    
    @staticmethod
    def create_user(db: Session, user_data: schemas.UserCreate) -> models.User:
        """Create a new user"""
        # Check if user exists
        existing_user = db.query(models.User).filter(
            (models.User.username == user_data.username) | 
            (models.User.email == user_data.email)
        ).first()
        
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username or email already registered"
            )
        
        # Create new user
        hashed_password = AuthService.get_password_hash(user_data.password)
        db_user = models.User(
            email=user_data.email,
            username=user_data.username,
            full_name=user_data.full_name,
            hashed_password=hashed_password,
            role=models.UserRole.USER
        )
        
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user
    
    @staticmethod
    def store_refresh_token(db: Session, user_id: int, token: str, expires_at: datetime):
        """Store refresh token in database"""
        db_token = models.RefreshToken(
            token=token,
            user_id=user_id,
            expires_at=expires_at
        )
        db.add(db_token)
        db.commit()
    
    @staticmethod
    def revoke_refresh_token(db: Session, token: str):
        """Revoke a refresh token"""
        db_token = db.query(models.RefreshToken).filter(
            models.RefreshToken.token == token
        ).first()
        if db_token:
            db_token.revoked = True
            db.commit()
    
    @staticmethod
    def validate_refresh_token(db: Session, token: str) -> Optional[int]:
        """Validate a refresh token and return user_id"""
        # Split token
        parts = token.split('.')
        if len(parts) != 2:
            return None
        
        jwt_part = parts[0]
        
        # Decode JWT part
        try:
            payload = jwt.decode(jwt_part, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            if payload.get('type') != 'refresh':
                return None
            
            # Check in database
            db_token = db.query(models.RefreshToken).filter(
                models.RefreshToken.token == token,
                models.RefreshToken.revoked == False,
                models.RefreshToken.expires_at > datetime.utcnow()
            ).first()
            
            if db_token:
                return db_token.user_id
            return None
        except JWTError:
            return None