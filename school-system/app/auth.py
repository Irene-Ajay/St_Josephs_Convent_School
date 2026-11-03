"""Login, sessions and access control.

Signed cookies rather than JWTs. For a server-rendered app used inside one
school this is simpler, has no token-refresh machinery, and is just as safe
when the cookie is httpOnly and signed.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.config import SECRET_KEY
from app.database import get_db
from app.models import ActivityLog, User

serializer = URLSafeTimedSerializer(SECRET_KEY, salt="session")

COOKIE_NAME = "school_session"
SESSION_HOURS = 12  # a school day plus margin; teachers log in once a morning

# bcrypt is used directly rather than through passlib.
#
# passlib has been unmaintained since 2020 and crashes on import with
# bcrypt 4.1+ ("password cannot be longer than 72 bytes"). Depending on it
# would mean this system breaks the next time someone installs it on a fresh
# computer — unacceptable for software the school must run for years without
# a maintainer. bcrypt (from pyca) is actively maintained and is all we need.

BCRYPT_MAX_BYTES = 72  # a hard limit of the bcrypt algorithm itself


def _prepare(plain: str) -> bytes:
    """bcrypt refuses passwords longer than 72 bytes.

    Real school passwords are nowhere near this, but truncating explicitly
    means an unusually long one is accepted instead of crashing the login.
    """
    return plain.encode("utf-8")[:BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_prepare(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # A malformed stored hash must fail the login, never crash it.
        return False


def create_session_cookie(user: User) -> str:
    return serializer.dumps({"uid": user.id, "role": user.role})


def read_session_cookie(token: str) -> dict | None:
    try:
        return serializer.loads(token, max_age=SESSION_HOURS * 3600)
    except (BadSignature, SignatureExpired):
        return None


def set_session(response, user: User) -> None:
    response.set_cookie(
        COOKIE_NAME,
        create_session_cookie(user),
        httponly=True,       # JavaScript cannot read it
        samesite="lax",
        max_age=SESSION_HOURS * 3600,
        # secure=True once the school has HTTPS. Left off so it works on a
        # plain http:// LAN address, which is how most schools will run it.
    )


def clear_session(response) -> None:
    response.delete_cookie(COOKIE_NAME)


def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    data = read_session_cookie(token)
    if not data:
        return None
    user = db.get(User, data["uid"])
    return user if user and user.is_active else None


class LoginRequired(Exception):
    """Raised instead of returning 401, so the browser gets a redirect to the
    login page rather than a JSON error the teacher cannot understand."""


class AccessDenied(Exception):
    pass


def require_login(request: Request, db: Session = Depends(get_db)) -> User:
    user = current_user(request, db)
    if user is None:
        raise LoginRequired()
    return user


def require_admin(request: Request, db: Session = Depends(get_db)) -> User:
    user = require_login(request, db)
    if not user.is_admin:
        raise AccessDenied("This page is for office staff only.")
    return user


def can_access_section(user: User, section_id: int, db: Session) -> bool:
    """Object-level check.

    Office staff see every section. A teacher sees only sections where they
    are the class teacher. Without this, any teacher could edit any class's
    attendance simply by changing the number in the address bar.
    """
    if user.is_admin:
        return True
    from app.models import Section

    section = db.get(Section, section_id)
    return section is not None and section.class_teacher_id == user.id


def log_activity(
    db: Session, user: User | None, action: str, details: str = ""
) -> None:
    db.add(
        ActivityLog(
            user_id=user.id if user else None,
            username=user.username if user else None,
            action=action,
            details=details,
        )
    )
    db.commit()


def touch_login(db: Session, user: User) -> None:
    user.last_login = datetime.now()
    db.commit()
