from functools import wraps
from typing import Callable

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.auth import get_current_user
from app.models.user import User, UserRole, UserPermission, RolePermission, Permission


async def check_permission(
    user_id: int,
    is_admin: bool,
    module: str,
    operation: str,
    db: AsyncSession,
) -> bool:
    """Check if a user has a specific permission via roles or direct grants."""
    if is_admin:
        return True

    # Check direct user permissions
    direct = await db.execute(
        select(Permission)
        .join(UserPermission, UserPermission.permission_id == Permission.id)
        .where(
            UserPermission.user_id == user_id,
            Permission.module == module,
            Permission.operation == operation,
        )
    )
    if direct.scalar_one_or_none():
        return True

    # Check role-based permissions
    role_perm = await db.execute(
        select(Permission)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(
            UserRole.user_id == user_id,
            Permission.module == module,
            Permission.operation == operation,
        )
    )
    if role_perm.scalar_one_or_none():
        return True

    return False


def require_permission(module: str, operation: str) -> Callable:
    """FastAPI dependency factory for permission-based access control."""

    async def dependency(
        current_user: dict = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> dict:
        has_perm = await check_permission(
            user_id=current_user["user_id"],
            is_admin=current_user.get("is_admin", False),
            module=module,
            operation=operation,
            db=db,
        )
        if not has_perm:
            raise HTTPException(
                403,
                f"Permission denied: {module}.{operation}",
            )
        return current_user

    return dependency
