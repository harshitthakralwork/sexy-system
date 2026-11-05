"""Create or repair the development-only ``1`` / ``1`` local login.

This is intentionally a local operator convenience, not a production account
bootstrap.  It refuses to run unless the configured environment is development.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import build_engine_and_maker
from app.core.security import hash_password
from app.modules.auth.models import User


LOCAL_EMAIL = "local1@sparkxflow.dev"


async def main() -> None:
    settings = get_settings()
    if settings.app_env != "development":
        raise SystemExit("Refusing to create the local login outside development")

    engine, session_maker = build_engine_and_maker(settings.database_url, pooled=False)
    try:
        async with session_maker() as session:
            user = await session.scalar(select(User).where(User.email == LOCAL_EMAIL))
            if user is None:
                user = User(
                    email=LOCAL_EMAIL,
                    password_hash=hash_password("1"),
                    display_name="Local Operator",
                    is_active=True,
                )
                session.add(user)
                action = "created"
            else:
                user.password_hash = hash_password("1")
                user.is_active = True
                action = "repaired"
            await session.commit()
            print(f"Local login {action}: id=1 password=1")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
