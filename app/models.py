# models.py
from pydantic import BaseModel


class Service(BaseModel):
    name: str
    type: str
    target: str
    check_frequency: int
    retry_threshold: int
    grace_period: int
    alert_email: str

class ServiceUpdate(Service):
    id: int

class UserCreate(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str


class SMTPConfig(BaseModel):
    host: str
    port: int
    username: str
    password: str
    from_email: str  # Changed from EmailStr to str
    use_tls: bool = True
