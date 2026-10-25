import math
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from app.auth.security import decode_access_token
from app.config import get_settings
from app.services.rate_limiter import rate_limiter
from app.services.user_store import User, user_store

# tokenUrl makes the "Authorize" button in /docs work with the login endpoint.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    user_id = decode_access_token(token)
    user = user_store.get(user_id) if user_id else None
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def client_ip(request: Request) -> str:
    # Behind a proxy, uvicorn --proxy-headers sets this from X-Forwarded-For.
    return request.client.host if request.client else "unknown"


def _enforce(key: str, limit: int, window_seconds: int) -> None:
    retry_after = rate_limiter.hit(key, limit, window_seconds)
    if retry_after is not None:
        seconds = math.ceil(retry_after)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many requests. Please try again in {seconds} seconds.",
            headers={"Retry-After": str(seconds)},
        )


def limit_per_user(scope: str, limit_setting: str, window_seconds: int):
    """Dependency: authenticate, then rate-limit by user id. Returns the user."""

    async def dependency(user: CurrentUser) -> User:
        _enforce(f"{scope}:{user.user_id}", getattr(get_settings(), limit_setting), window_seconds)
        return user

    return dependency


def limit_per_ip(scope: str, limit_setting: str, window_seconds: int):
    """Dependency: rate-limit by client IP (for unauthenticated endpoints)."""

    async def dependency(request: Request) -> None:
        _enforce(f"{scope}:{client_ip(request)}", getattr(get_settings(), limit_setting), window_seconds)

    return dependency


ChatUser = Annotated[User, Depends(limit_per_user("chat", "rate_limit_chat_per_minute", 60))]
UploadUser = Annotated[User, Depends(limit_per_user("upload", "rate_limit_upload_per_hour", 3600))]
AuthRateLimit = Depends(limit_per_ip("auth", "rate_limit_auth_per_minute", 60))
