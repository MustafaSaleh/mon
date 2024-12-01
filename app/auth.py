# auth.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import sqlite3
from .database import get_db, set_database_path


SECRET_KEY = "your-secret-key-here"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def init_auth_db(db_path=None):
    if db_path:
        set_database_path(db_path)
        
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS users
            (username TEXT PRIMARY KEY,
             hashed_password TEXT)
        ''')
        conn.commit()
    finally:
        conn.close()

        

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials"
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    return username


async def create_default_admin():
    with get_db() as conn:
        # Check if admin exists
        admin = conn.execute(
            "SELECT * FROM users WHERE username = ?", 
            ("admin",)
        ).fetchone()
        
        if not admin:
            hashed_password = get_password_hash("admin")
            conn.execute(
                "INSERT INTO users (username, hashed_password) VALUES (?, ?)",
                ("admin", hashed_password)
            )
            print("Default admin user created")
