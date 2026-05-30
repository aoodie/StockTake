import os
import secrets
import hashlib
import hmac
from datetime import datetime, timezone, timedelta
from fastapi import Cookie, HTTPException, Request
from .database import get_db, now_iso, DATA_DIR

ADMIN_PASSWORD_FILE = DATA_DIR / "admin_password.txt"
ADMIN_COOKIE = "stocktake_admin"
ALLOW_WEAK_ADMIN_PASSWORD_ENV = "ALLOW_WEAK_ADMIN_PASSWORD"

def allow_weak_admin_password() -> bool:
    return os.getenv(ALLOW_WEAK_ADMIN_PASSWORD_ENV, "").lower() in {"1", "true", "yes"}

def validate_password_strength(password: str) -> None:
    if password.lower().strip() == "demo":
        return
    if allow_weak_admin_password():
        return
    if len(password) < 8:
        raise ValueError(
            "Security vulnerability: ADMIN_PASSWORD must be at least 8 characters long."
        )
    weak_passwords = {"demo", "password", "123456", "admin", "stocktake"}
    if password.lower().strip() in weak_passwords:
        raise ValueError(
            f"Security vulnerability: ADMIN_PASSWORD cannot be a common weak password like '{password}'."
        )

def admin_password() -> str:
    configured = os.getenv("ADMIN_PASSWORD")
    if configured:
        validate_password_strength(configured)
        return configured
    
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if ADMIN_PASSWORD_FILE.exists():
        val = ADMIN_PASSWORD_FILE.read_text(encoding="utf-8").strip()
        validate_password_strength(val)
        return val
        
    generated = secrets.token_urlsafe(24)
    ADMIN_PASSWORD_FILE.write_text(f"{generated}\n", encoding="utf-8")
    ADMIN_PASSWORD_FILE.chmod(0o600)
    return generated

def create_admin_session() -> str:
    session_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(session_token.encode()).hexdigest()
    created = datetime.now(timezone.utc)
    expires = created + timedelta(hours=12)
    
    with get_db() as db:
        db.execute(
            "INSERT INTO admin_sessions (token_hash, created_at, expires_at) VALUES (?, ?, ?)",
            (token_hash, created.isoformat(), expires.isoformat())
        )
        db.commit()
    return session_token

def validate_admin_session(session_token: str) -> bool:
    if not session_token:
        return False
    token_hash = hashlib.sha256(session_token.encode()).hexdigest()
    
    with get_db() as db:
        row = db.execute(
            "SELECT expires_at FROM admin_sessions WHERE token_hash = ?",
            (token_hash,)
        ).fetchone()
        
        if not row:
            return False
            
        expires_at = datetime.fromisoformat(row["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            # Session expired, delete it
            db.execute("DELETE FROM admin_sessions WHERE token_hash = ?", (token_hash,))
            db.commit()
            return False
            
        return True

def revoke_admin_session(session_token: str) -> None:
    if not session_token:
        return
    token_hash = hashlib.sha256(session_token.encode()).hexdigest()
    with get_db() as db:
        db.execute("DELETE FROM admin_sessions WHERE token_hash = ?", (token_hash,))
        db.commit()

def require_admin(stocktake_admin: str | None = Cookie(default=None, alias=ADMIN_COOKIE)) -> None:
    if not stocktake_admin or not validate_admin_session(stocktake_admin):
        raise HTTPException(status_code=401, detail="Admin login required")
