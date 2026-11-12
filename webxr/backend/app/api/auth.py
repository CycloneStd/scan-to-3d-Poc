import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..dependencies import get_current_user
from ..db import get_db
from ..models import AuthToken, User, utcnow
from ..rate_limit import rate_limit
from ..schemas import (EmailRequest, LoginRequest, MessageResponse, PasswordChangeRequest, PasswordResetRequest,
                       RefreshRequest, RegisterRequest, TokenPair, TokenRequest, UserResponse)
from ..security import create_access_token, hash_password, hash_token, new_opaque_token, verify_password
from ..services.email import send_security_email
from ..services.email_templates import password_reset_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])
_DUMMY_PASSWORD_HASH = hash_password("webxr-invalid-user-password-hash")


def _issue_refresh_token(db: Session, user: User) -> str:
    settings = get_settings()
    raw = new_opaque_token()
    db.add(AuthToken(
        user_id=user.id, kind="refresh", token_hash=hash_token(raw),
        expires_at=utcnow() + timedelta(days=settings.refresh_token_days),
    ))
    return raw


def _token_pair(db: Session, user: User) -> TokenPair:
    access, expires_in = create_access_token(user.id)
    refresh = _issue_refresh_token(db, user)
    return TokenPair(access_token=access, refresh_token=refresh, expires_in=expires_in)


def _send_token_email(user: User, raw_token: str, kind: str) -> None:
    settings = get_settings()
    if kind == "verify":
        url = f"{settings.frontend_base_url}/verify-email?token={raw_token}"
        subject = "Verify your Cyclone account"
        message = f"Hello,\n\nVerify your email address using this link:\n{url}\n\nThis link expires in {settings.verification_token_minutes} minutes. If you did not create this account, ignore this email."
    else:
        url = f"{settings.frontend_base_url}/reset-password?token={raw_token}"
        subject = "Reset your Reality to 3D password"
        message = f"Hello,\n\nChoose a new password using this link:\n{url}\n\nThis link expires in {settings.password_reset_token_minutes} minutes. If you did not request this, ignore this email."
    try:
        html = password_reset_email(url, settings.password_reset_token_minutes) if kind == "reset" else None
        provider_id = send_security_email(user.email, subject, message, html)
        logger.info(
            "Security email accepted by provider: kind=%s user_id=%s provider_id=%s",
            kind, user.id, provider_id or "unavailable",
        )
    except Exception as exc:
        logger.exception("Security email delivery failed for user id %s", user.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email delivery is temporarily unavailable. Please try again later.",
        ) from exc


def _resend_verification_for_user(user: User, db: Session) -> None:
    raw = new_opaque_token()
    settings = get_settings()
    db.execute(update(AuthToken).where(
        AuthToken.user_id == user.id,
        AuthToken.kind == "verify",
        AuthToken.consumed_at.is_(None),
    ).values(consumed_at=utcnow()))
    db.add(AuthToken(
        user_id=user.id,
        kind="verify",
        token_hash=hash_token(raw),
        expires_at=utcnow() + timedelta(minutes=settings.verification_token_minutes),
    ))
    db.commit()
    _send_token_email(user, raw, "verify")


@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit("register", 5))])
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    email = str(payload.email).lower()
    user = db.scalar(select(User).where(User.email == email).with_for_update())
    if user:
        if user.is_active and not user.email_verified_at:
            _resend_verification_for_user(user, db)
        return MessageResponse(message="If the address can be registered, verification instructions will be sent.")
    user = User(email=email, password_hash=hash_password(payload.password))
    raw_token = new_opaque_token()
    settings = get_settings()
    db.add(user)
    try:
        db.flush()
        db.add(AuthToken(user_id=user.id, kind="verify", token_hash=hash_token(raw_token),
                         expires_at=utcnow() + timedelta(minutes=settings.verification_token_minutes)))
        db.commit()
    except IntegrityError:
        db.rollback()
        return MessageResponse(message="If the address can be registered, verification instructions will be sent.")
    _send_token_email(user, raw_token, "verify")
    return MessageResponse(message="If the address can be registered, verification instructions will be sent.")


@router.post("/verify-email", response_model=TokenPair,
             dependencies=[Depends(rate_limit("verify-email", 10))])
def verify_email(payload: TokenRequest, db: Session = Depends(get_db)):
    record = db.scalar(select(AuthToken).where(AuthToken.token_hash == hash_token(payload.token), AuthToken.kind == "verify").with_for_update())
    if not record or record.consumed_at or record.expires_at <= utcnow():
        raise HTTPException(status_code=400, detail="Verification link is invalid or expired")
    user = db.get(User, record.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Verification link is invalid or expired")
    record.consumed_at = utcnow()
    user.email_verified_at = utcnow()
    tokens = _token_pair(db, user)
    db.commit()
    return tokens


@router.post("/resend-verification", response_model=MessageResponse,
             dependencies=[Depends(rate_limit("resend-verification", 3))])
def resend_verification(payload: EmailRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(payload.email).lower()))
    if user and user.is_active and not user.email_verified_at:
        _resend_verification_for_user(user, db)
    return MessageResponse(message="If the account needs verification, a new link has been sent.")


@router.post("/login", response_model=TokenPair, dependencies=[Depends(rate_limit("login", 10))])
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(payload.email).lower()))
    # Run Argon2 for unknown users as well, reducing timing-based account discovery.
    valid = verify_password(payload.password, user.password_hash if user else _DUMMY_PASSWORD_HASH)
    if not user or not user.is_active or not valid:
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    if not user.email_verified_at:
        raise HTTPException(status_code=403, detail="Verify your email address before signing in")
    pair = _token_pair(db, user)
    db.commit()
    return pair


@router.post("/refresh", response_model=TokenPair, dependencies=[Depends(rate_limit("refresh", 20))])
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    record = db.scalar(select(AuthToken).where(AuthToken.token_hash == hash_token(payload.refresh_token), AuthToken.kind == "refresh").with_for_update())
    if not record or record.consumed_at or record.expires_at <= utcnow():
        raise HTTPException(status_code=401, detail="Refresh token is invalid or expired")
    user = db.get(User, record.user_id)
    if not user or not user.is_active or not user.email_verified_at:
        raise HTTPException(status_code=401, detail="Refresh token is invalid or expired")
    record.consumed_at = utcnow()
    pair = _token_pair(db, user)
    db.commit()
    return pair


@router.post("/logout", response_model=MessageResponse, status_code=200)
def logout(payload: RefreshRequest, db: Session = Depends(get_db)):
    record = db.scalar(select(AuthToken).where(AuthToken.token_hash == hash_token(payload.refresh_token), AuthToken.kind == "refresh").with_for_update())
    if record and not record.consumed_at:
        record.consumed_at = utcnow()
        db.commit()
    return MessageResponse(message="Signed out")


@router.post("/password/forgot", response_model=MessageResponse,
             dependencies=[Depends(rate_limit("password-forgot", 5))])
def forgot_password(payload: EmailRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(payload.email).lower()))
    if user and user.is_active:
        raw = new_opaque_token()
        settings = get_settings()
        db.execute(update(AuthToken).where(AuthToken.user_id == user.id, AuthToken.kind == "reset", AuthToken.consumed_at.is_(None)).values(consumed_at=utcnow()))
        db.add(AuthToken(user_id=user.id, kind="reset", token_hash=hash_token(raw),
                         expires_at=utcnow() + timedelta(minutes=settings.password_reset_token_minutes)))
        db.commit()
        _send_token_email(user, raw, "reset")
    return MessageResponse(message="If an account exists for that email, password reset instructions have been sent.")


@router.post("/password/reset", response_model=MessageResponse,
             dependencies=[Depends(rate_limit("password-reset", 8))])
def reset_password(payload: PasswordResetRequest, db: Session = Depends(get_db)):
    record = db.scalar(select(AuthToken).where(AuthToken.token_hash == hash_token(payload.token), AuthToken.kind == "reset").with_for_update())
    if not record or record.consumed_at or record.expires_at <= utcnow():
        raise HTTPException(status_code=400, detail="Reset link is invalid or expired")
    user = db.get(User, record.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Reset link is invalid or expired")
    user.password_hash = hash_password(payload.new_password)
    record.consumed_at = utcnow()
    db.execute(update(AuthToken).where(AuthToken.user_id == user.id, AuthToken.kind == "refresh", AuthToken.consumed_at.is_(None)).values(consumed_at=utcnow()))
    db.commit()
    return MessageResponse(message="Password updated. Please sign in with your new password.")


@router.post("/password/change", response_model=MessageResponse, dependencies=[Depends(rate_limit("password-change", 5))])
def change_password(payload: PasswordChangeRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    db.execute(update(AuthToken).where(AuthToken.user_id == user.id, AuthToken.kind == "refresh",
                                      AuthToken.consumed_at.is_(None)).values(consumed_at=utcnow()))
    db.commit()
    return MessageResponse(message="Password changed. Please sign in again on your other devices.")


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return UserResponse(id=user.id, email=user.email,
                        email_verified=bool(user.email_verified_at), created_at=user.created_at)
