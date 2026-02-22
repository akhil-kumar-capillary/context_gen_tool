from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.auth import login_to_capillary, create_session_token, get_current_user
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse, UserResponse, OrgResponse, SelectOrgRequest
from app.config import settings

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    # Authenticate via Capillary Intouch
    cap_result = await login_to_capillary(req.username, req.password, req.cluster)

    # Upsert user in local DB
    result = await db.execute(select(User).where(User.email == cap_result["email"]))
    user = result.scalar_one_or_none()

    if user is None:
        is_admin = cap_result["email"] == settings.primary_admin_email
        user = User(
            email=cap_result["email"],
            display_name=cap_result["display_name"],
            cluster=cap_result["cluster"],
            base_url=cap_result["base_url"],
            is_admin=is_admin,
            last_login_at=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.flush()
    else:
        user.cluster = cap_result["cluster"]
        user.base_url = cap_result["base_url"]
        user.last_login_at = datetime.now(timezone.utc)
        if cap_result["display_name"]:
            user.display_name = cap_result["display_name"]

    await db.commit()
    await db.refresh(user)

    # Create session JWT
    token = create_session_token(
        user_id=user.id,
        email=user.email,
        is_admin=user.is_admin,
        capillary_token=cap_result["capillary_token"],
        cluster=cap_result["cluster"],
        base_url=cap_result["base_url"],
    )

    return LoginResponse(
        token=token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            displayName=user.display_name or user.email,
            isAdmin=user.is_admin,
            orgs=[OrgResponse(**o) for o in cap_result["orgs"]],
        ),
    )


@router.get("/user")
async def get_user(current_user: dict = Depends(get_current_user)):
    return {
        "user_id": current_user["user_id"],
        "email": current_user["email"],
        "is_admin": current_user["is_admin"],
    }
