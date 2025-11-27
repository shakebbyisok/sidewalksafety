from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from app.core.config import settings
import hashlib


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    try:
        password_bytes = plain_password.encode('utf-8', errors='replace')
    except Exception:
        return False
    
    # Pre-hash with SHA256 (since we always store pre-hashed passwords)
    pre_hashed = hashlib.sha256(password_bytes).hexdigest()
    
    # Verify using bcrypt
    try:
        if isinstance(hashed_password, str):
            hashed_password_bytes = hashed_password.encode('utf-8')
        else:
            hashed_password_bytes = hashed_password
        
        return bcrypt.checkpw(pre_hashed.encode('utf-8'), hashed_password_bytes)
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Hash a password - pre-hashes with SHA256 to handle any length."""
    if not password:
        raise ValueError("Password cannot be empty")
    
    try:
        password_bytes = password.encode('utf-8', errors='replace')
    except Exception as e:
        raise ValueError(f"Invalid password encoding: {e}")
    
    # Pre-hash with SHA256, then hash with bcrypt
    pre_hashed = hashlib.sha256(password_bytes).hexdigest()
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pre_hashed.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None

