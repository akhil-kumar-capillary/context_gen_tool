from typing import Callable

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.auth import get_current_user
from app.models.user import User, Role, UserRole, UserPermission, RolePermission, Permission

# ---------------------------------------------------------------------------
# Role x Module matrix
# ---------------------------------------------------------------------------
# Roles define the *access level* (what operations a user can perform).
# Module access is granted independently by an admin via direct UserPermissions.
# Effective capability = role capabilities  x  granted module access.
# ---------------------------------------------------------------------------
ROLE_CAPABILITIES: dict[str, set[str] | str] = {
    "admin": "all",
    "operator": "all",       # full CRUD within granted modules
    "viewer": {"view"},      # read-only within granted modules
}


async def check_permission(
    user_id: int,
    is_admin: bool,
    module: str,
    operation: str,
    db: AsyncSession,
) -> bool:
    """Check if a user has a specific permission.

    Three resolution paths (evaluated in order):
      1. Direct UserPermission  — exact (module, operation) match
      2. Role x Module          — user has *any* direct permission for
         the module (= module access) AND a role whose capability set
         includes the requested operation
      3. Legacy role-permissions — permission attached to a Role via
         RolePermission (backward-compat, e.g. context_management ops
         granted through the viewer/operator role seed data)
    """
    if is_admin:
        return True

    # Path 1: Direct exact permission
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

    # Path 2: Module access (any direct perm for this module) + role capability
    module_access = await db.execute(
        select(Permission.id)
        .join(UserPermission, UserPermission.permission_id == Permission.id)
        .where(
            UserPermission.user_id == user_id,
            Permission.module == module,
        )
        .limit(1)
    )
    if module_access.scalar_one_or_none():
        # User has module access — check if any of their roles allow this op
        user_roles = await db.execute(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        )
        for (role_name,) in user_roles.all():
            caps = ROLE_CAPABILITIES.get(role_name)
            if caps == "all" or (isinstance(caps, set) and operation in caps):
                return True

    # Path 3: Legacy role-based permissions (role -> role_permission -> permission)
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
