from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field, validator
from datetime import datetime, timedelta
from typing import Optional, List
import uvicorn
import re
from jose import JWTError, jwt
from passlib.context import CryptContext
import secrets
import string

# ==================== CONFIGURATION ====================
SECRET_KEY = "your-secret-key-change-in-production-12345"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
APP_NAME = "Secure Auth System (Simplified)"
APP_VERSION = "1.0.0"

# ==================== PASSWORD HASHING ====================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

# ==================== JWT TOKENS ====================
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# ==================== DATA MODELS (instead of database) ====================
# In-memory "database" - SIMPLE Python dictionaries
users_db = {}
refresh_tokens_db = {}

class UserRole:
    ADMIN = "admin"
    USER = "user"
    MODERATOR = "moderator"

# ==================== PYDANTIC SCHEMAS ====================
class UserBase(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    full_name: Optional[str] = None

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    
    @validator('password')
    def validate_password(cls, v):
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one number')
        return v

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(UserBase):
    id: int
    role: str
    is_active: bool
    is_verified: bool
    created_at: str

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class TokenPayload(BaseModel):
    sub: str
    exp: int
    role: str

# ==================== AUTH DEPENDENCIES ====================
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = users_db.get(username)
    if user is None:
        raise credentials_exception
    
    if not user["is_active"]:
        raise HTTPException(status_code=400, detail="Inactive user")
    
    return user

def get_current_active_user(current_user = Depends(get_current_user)):
    if not current_user["is_active"]:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

def require_role(required_role: str):
    def role_checker(current_user = Depends(get_current_active_user)):
        if current_user["role"] != required_role and current_user["role"] != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {required_role} required"
            )
        return current_user
    return role_checker

# ==================== FASTAPI APP ====================
app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Secure Authentication System (No Database Version)",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5500", "http://127.0.0.1:5500", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== API ENDPOINTS ====================

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "app": APP_NAME,
        "version": APP_VERSION,
        "timestamp": datetime.now().isoformat(),
        "users_count": len(users_db)
    }

@app.post("/api/auth/register", response_model=UserResponse)
async def register(user_data: UserCreate):
    """Register a new user"""
    # Check if user exists
    if user_data.username in users_db:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Check if email exists
    for user in users_db.values():
        if user["email"] == user_data.email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
    
    # Create new user
    user_id = len(users_db) + 1
    hashed_password = get_password_hash(user_data.password)
    
    # Determine role (first user is admin, rest are regular users)
    role = UserRole.ADMIN if len(users_db) == 0 else UserRole.USER
    
    new_user = {
        "id": user_id,
        "email": user_data.email,
        "username": user_data.username,
        "full_name": user_data.full_name,
        "hashed_password": hashed_password,
        "role": role,
        "is_active": True,
        "is_verified": False,
        "created_at": datetime.now().isoformat()
    }
    
    users_db[user_data.username] = new_user
    
    # Return user without password
    return {
        "id": new_user["id"],
        "email": new_user["email"],
        "username": new_user["username"],
        "full_name": new_user["full_name"],
        "role": new_user["role"],
        "is_active": new_user["is_active"],
        "is_verified": new_user["is_verified"],
        "created_at": new_user["created_at"]
    }

@app.post("/api/auth/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Login and get tokens"""
    # Find user
    user = users_db.get(form_data.username)
    
    # If not found by username, try email
    if not user:
        for u in users_db.values():
            if u["email"] == form_data.username:
                user = u
                break
    
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"], "role": user["role"]},
        expires_delta=access_token_expires
    )
    
    # Create simple refresh token
    refresh_token = secrets.token_urlsafe(32)
    
    # Store refresh token (in memory)
    refresh_tokens_db[refresh_token] = {
        "username": user["username"],
        "expires": (datetime.utcnow() + timedelta(days=7)).isoformat()
    }
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

@app.post("/api/auth/refresh", response_model=Token)
async def refresh_token(refresh_request: RefreshTokenRequest):
    """Get new access token using refresh token"""
    # Check if refresh token exists
    token_data = refresh_tokens_db.get(refresh_request.refresh_token)
    
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    # Check if expired
    expires = datetime.fromisoformat(token_data["expires"])
    if datetime.utcnow() > expires:
        del refresh_tokens_db[refresh_request.refresh_token]
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired"
        )
    
    # Get user
    user = users_db.get(token_data["username"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    # Delete old refresh token
    del refresh_tokens_db[refresh_request.refresh_token]
    
    # Create new tokens
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"], "role": user["role"]},
        expires_delta=access_token_expires
    )
    
    new_refresh_token = secrets.token_urlsafe(32)
    refresh_tokens_db[new_refresh_token] = {
        "username": user["username"],
        "expires": (datetime.utcnow() + timedelta(days=7)).isoformat()
    }
    
    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer"
    }

@app.post("/api/auth/logout")
async def logout(refresh_token: RefreshTokenRequest):
    """Logout - revoke refresh token"""
    if refresh_token.refresh_token in refresh_tokens_db:
        del refresh_tokens_db[refresh_token.refresh_token]
    return {"message": "Successfully logged out"}

@app.get("/api/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user = Depends(get_current_active_user)):
    """Get current authenticated user info"""
    return {
        "id": current_user["id"],
        "email": current_user["email"],
        "username": current_user["username"],
        "full_name": current_user["full_name"],
        "role": current_user["role"],
        "is_active": current_user["is_active"],
        "is_verified": current_user["is_verified"],
        "created_at": current_user["created_at"]
    }

@app.get("/api/users", response_model=List[UserResponse])
async def read_users(current_user = Depends(require_role(UserRole.ADMIN))):
    """Get all users (admin only)"""
    users_list = []
    for user in users_db.values():
        users_list.append({
            "id": user["id"],
            "email": user["email"],
            "username": user["username"],
            "full_name": user["full_name"],
            "role": user["role"],
            "is_active": user["is_active"],
            "is_verified": user["is_verified"],
            "created_at": user["created_at"]
        })
    return users_list

@app.get("/api/admin/dashboard")
async def admin_dashboard(current_user = Depends(require_role(UserRole.ADMIN))):
    """Admin dashboard (admin only)"""
    return {
        "message": "Welcome to Admin Dashboard",
        "user": current_user["username"],
        "role": current_user["role"],
        "stats": {
            "total_users": len(users_db),
            "active_sessions": len(refresh_tokens_db),
            "pending_actions": 0
        }
    }

@app.get("/api/user/dashboard")
async def user_dashboard(current_user = Depends(get_current_active_user)):
    """User dashboard (any authenticated user)"""
    return {
        "message": f"Welcome {current_user['username']}",
        "role": current_user["role"],
        "dashboard": "User Dashboard"
    }

# Create initial admin user on startup
@app.on_event("startup")
async def create_initial_admin():
    """Create initial admin user if not exists"""
    if "admin" not in users_db:
        admin_user = {
            "id": 1,
            "email": "admin@example.com",
            "username": "admin",
            "full_name": "System Administrator",
            "hashed_password": get_password_hash("Admin123!"),
            "role": UserRole.ADMIN,
            "is_active": True,
            "is_verified": True,
            "created_at": datetime.now().isoformat()
        }
        users_db["admin"] = admin_user
        print("✅ Initial admin user created")
        print("   Username: admin")
        print("   Password: Admin123!")
    
    # Create a demo user
    if "user" not in users_db:
        demo_user = {
            "id": 2,
            "email": "user@example.com",
            "username": "user",
            "full_name": "Demo User",
            "hashed_password": get_password_hash("User123!"),
            "role": UserRole.USER,
            "is_active": True,
            "is_verified": True,
            "created_at": datetime.now().isoformat()
        }
        users_db["user"] = demo_user
        print("✅ Demo user created")
        print("   Username: user")
        print("   Password: User123!")

# ==================== SERVER STARTUP ====================
if __name__ == "__main__":
    print("=" * 50)
    print("🚀 STARTING SIMPLIFIED AUTH SERVER")
    print("=" * 50)
    print("📚 API Docs: http://localhost:8000/api/docs")
    print("🔑 Auth endpoints: http://localhost:8000/api/auth/*")
    print("🩺 Health check: http://localhost:8000/api/health")
    print("=" * 50)
    print("✅ NO DATABASE NEEDED - Using in-memory storage")
    print("=" * 50)
    print("Press CTRL+C to stop the server")
    print("=" * 50)
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )