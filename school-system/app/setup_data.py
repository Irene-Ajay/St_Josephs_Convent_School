"""First-run setup.

Creates the initial admin account and a few sensible defaults so the system
is usable the moment it starts, without anyone running a separate script.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from sqlalchemy import select

from app.auth import hash_password
from app.config import DATA_DIR
from app.database import SessionLocal
from app.models import Section, User

FIRST_LOGIN_FILE = DATA_DIR / "FIRST_LOGIN.txt"


def ensure_first_admin() -> None:
    db = SessionLocal()
    try:
        if db.scalar(select(User.id).limit(1)) is not None:
            return  # already set up

        # A random password written to a file, rather than a hard-coded
        # "admin/admin123". Anyone who finds this system on the network
        # should not be able to guess their way in.
        password = secrets.token_urlsafe(9)
        admin = User(
            username="admin",
            password_hash=hash_password(password),
            full_name="Office Administrator",
            role="ADMIN",
            must_change_password=True,
        )
        db.add(admin)

        # A starter set of sections so the first import has somewhere to go.
        for index, name in enumerate(
            [f"Class {n}" for n in range(1, 11)], start=1
        ):
            db.add(Section(name=name, division="A", order_index=index))

        db.commit()

        FIRST_LOGIN_FILE.write_text(
            "FIRST LOGIN DETAILS\n"
            "===================\n\n"
            "  Username:  admin\n"
            f"  Password:  {password}\n\n"
            "Please log in and change this password immediately.\n"
            "You may delete this file afterwards.\n",
            encoding="utf-8",
        )
        print("\n" + "=" * 52, flush=True)
        print("  FIRST-TIME SETUP COMPLETE", flush=True)
        print("  Username: admin", flush=True)
        print(f"  Password: {password}", flush=True)
        print(f"  (also saved to {FIRST_LOGIN_FILE})", flush=True)
        print("=" * 52 + "\n", flush=True)
    finally:
        db.close()
