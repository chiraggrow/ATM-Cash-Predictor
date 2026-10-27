from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import User

password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(user: User, settings: Settings) -> tuple[str, int]:
    expires_in = settings.access_token_expire_minutes * 60
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    token = jwt.encode(
        {"sub": str(user.id), "role": user.role, "exp": expires_at},
        settings.jwt_secret_key.get_secret_value(),
        algorithm="HS256",
    )
    return token, expires_in


def build_current_user_dependency(settings: Settings, session_dependency):
    def get_current_user(
        token: str = Depends(oauth2_scheme),
        db: Session = Depends(session_dependency),
    ) -> User:
        credentials_error = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key.get_secret_value(),
                algorithms=["HS256"],
            )
            user_id = int(payload["sub"])
        except (JWTError, KeyError, TypeError, ValueError) as error:
            raise credentials_error from error

        user = db.scalar(select(User).where(User.id == user_id))
        if user is None or not user.is_active:
            raise credentials_error
        return user

    return get_current_user


def build_admin_dependency(current_user_dependency):
    def get_admin_user(user: User = Depends(current_user_dependency)) -> User:
        if user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Administrator role required.",
            )
        return user

    return get_admin_user
