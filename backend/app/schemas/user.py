from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: str = "viewer"
    department: Optional[str] = None


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    department: Optional[str] = None
    is_active: Optional[bool] = None


class PasswordChange(BaseModel):
    new_password: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    department: Optional[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
