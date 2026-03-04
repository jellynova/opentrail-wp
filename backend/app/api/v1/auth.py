from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response, Cookie, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_active_user,
)
from app.models.user import User
from app.schemas.auth import TokenResponse, UserInfo

router = APIRouter()

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days in seconds


@router.post("/login", response_model=TokenResponse)
def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Authenticate with username + password. Returns access token; sets refresh cookie."""
    user = db.scalars(select(User).where(User.username == form_data.username)).first()
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")

    access_token = create_access_token({"sub": str(user.id), "role": user.role})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        max_age=REFRESH_COOKIE_MAX_AGE,
        samesite="lax",
        secure=False,  # set to True in production behind HTTPS
    )

    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(
    response: Response,
    db: Session = Depends(get_db),
    refresh_token: str = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
):
    """Use the httpOnly refresh cookie to obtain a new access token."""
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    user_id = payload.get("sub")
    user = db.get(User, int(user_id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    new_access = create_access_token({"sub": str(user.id), "role": user.role})
    new_refresh = create_refresh_token({"sub": str(user.id)})

    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=new_refresh,
        httponly=True,
        max_age=REFRESH_COOKIE_MAX_AGE,
        samesite="lax",
        secure=False,
    )

    return TokenResponse(access_token=new_access)


@router.post("/logout")
def logout(response: Response):
    """Clear the refresh cookie."""
    response.delete_cookie(key=REFRESH_COOKIE_NAME, httponly=True, samesite="lax")
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserInfo)
def me(current_user: User = Depends(get_current_active_user)):
    """Return current authenticated user info."""
    return current_user
