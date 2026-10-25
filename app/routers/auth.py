import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordRequestForm

from app.auth.dependencies import AuthRateLimit, CurrentUser
from app.auth.security import create_access_token, hash_password, verify_password
from app.config import get_settings
from app.schemas import RegisterRequest, TokenResponse, UserPublic
from app.services.user_store import EmailAlreadyRegisteredError, User, user_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _token_response(user: User) -> TokenResponse:
    token, expires_in = create_access_token(user.user_id)
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserPublic(**user.model_dump()),
    )


@router.post("/register", response_model=TokenResponse, status_code=201, dependencies=[AuthRateLimit])
async def register(request: RegisterRequest) -> TokenResponse:
    if not get_settings().allow_registration:
        raise HTTPException(status_code=403, detail="Registration is disabled.")
    # Argon2 hashing is deliberately slow - keep it off the event loop.
    password_hash = await run_in_threadpool(hash_password, request.password)
    try:
        user = user_store.create(request.email, password_hash)
    except EmailAlreadyRegisteredError:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    logger.info("user_registered", extra={"user_id": user.user_id})
    return _token_response(user)


@router.post("/login", response_model=TokenResponse, dependencies=[AuthRateLimit])
async def login(form: Annotated[OAuth2PasswordRequestForm, Depends()]) -> TokenResponse:
    """OAuth2 password flow: send `username` (your email) and `password` as form data."""
    user = user_store.get_by_email(form.username)
    valid = await run_in_threadpool(
        verify_password, form.password, user.password_hash if user else None
    )
    if user is None or not valid:
        logger.info("login_failed")
        # Same message either way, so attackers can't tell which emails exist.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    logger.info("login_succeeded", extra={"user_id": user.user_id})
    return _token_response(user)


@router.get("/me", response_model=UserPublic)
async def me(user: CurrentUser) -> UserPublic:
    return UserPublic(**user.model_dump())


def ensure_demo_user() -> None:
    """Create the demo account from DEMO_USER_EMAIL / DEMO_USER_PASSWORD if configured."""
    settings = get_settings()
    if not (settings.demo_user_email and settings.demo_user_password):
        return
    if user_store.get_by_email(settings.demo_user_email) is None:
        user_store.create(settings.demo_user_email, hash_password(settings.demo_user_password))
        logger.info("demo_user_created")
