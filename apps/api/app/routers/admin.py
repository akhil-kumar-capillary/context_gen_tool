"""Admin panel endpoints — user management, RBAC, secrets, audit logs."""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.core.auth import require_admin
from app.models.user import User, Role, Permission, UserRole, UserPermission
from app.schemas.admin import (
    GrantRoleRequest, RevokeRoleRequest,
    GrantPermissionRequest, RevokePermissionRequest,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/users")
async def list_users(
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles), selectinload(User.permissions))
        .order_by(User.email)
    )
    users = result.scalars().all()

    return {
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "display_name": u.display_name,
                "is_admin": u.is_admin,
                "is_active": u.is_active,
                "roles": [ur.role.name for ur in u.roles] if u.roles else [],
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            }
            for u in users
        ]
    }


@router.get("/roles")
async def list_roles(
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Role).order_by(Role.name))
    roles = result.scalars().all()
    return {"roles": [{"id": r.id, "name": r.name, "description": r.description} for r in roles]}


@router.get("/permissions")
async def list_permissions(
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Permission).order_by(Permission.module, Permission.operation))
    perms = result.scalars().all()
    return {
        "permissions": [
            {"id": p.id, "module": p.module, "operation": p.operation, "description": p.description}
            for p in perms
        ]
    }


@router.post("/users/grant-role")
async def grant_role(
    req: GrantRoleRequest,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # Find or create user
    user_result = await db.execute(select(User).where(User.email == req.user_email))
    user = user_result.scalar_one_or_none()
    if not user:
        user = User(email=req.user_email, is_active=True)
        db.add(user)
        await db.flush()

    # Find role
    role_result = await db.execute(select(Role).where(Role.name == req.role_name))
    role = role_result.scalar_one_or_none()
    if not role:
        raise HTTPException(404, f"Role '{req.role_name}' not found")

    # Check if already granted
    existing = await db.execute(
        select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)
    )
    if existing.scalar_one_or_none():
        return {"message": f"Role '{req.role_name}' already granted to {req.user_email}"}

    db.add(UserRole(user_id=user.id, role_id=role.id, granted_by=current_user["user_id"]))
    await db.commit()
    return {"message": f"Role '{req.role_name}' granted to {req.user_email}"}


@router.post("/users/revoke-role")
async def revoke_role(
    req: RevokeRoleRequest,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user_result = await db.execute(select(User).where(User.email == req.user_email))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, f"User '{req.user_email}' not found")

    role_result = await db.execute(select(Role).where(Role.name == req.role_name))
    role = role_result.scalar_one_or_none()
    if not role:
        raise HTTPException(404, f"Role '{req.role_name}' not found")

    existing = await db.execute(
        select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)
    )
    ur = existing.scalar_one_or_none()
    if ur:
        await db.delete(ur)
        await db.commit()
    return {"message": f"Role '{req.role_name}' revoked from {req.user_email}"}


@router.post("/users/grant-permission")
async def grant_permission(
    req: GrantPermissionRequest,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user_result = await db.execute(select(User).where(User.email == req.user_email))
    user = user_result.scalar_one_or_none()
    if not user:
        user = User(email=req.user_email, is_active=True)
        db.add(user)
        await db.flush()

    perm_result = await db.execute(
        select(Permission).where(Permission.module == req.module, Permission.operation == req.operation)
    )
    perm = perm_result.scalar_one_or_none()
    if not perm:
        raise HTTPException(404, f"Permission '{req.module}.{req.operation}' not found")

    existing = await db.execute(
        select(UserPermission).where(
            UserPermission.user_id == user.id, UserPermission.permission_id == perm.id
        )
    )
    if existing.scalar_one_or_none():
        return {"message": f"Permission already granted"}

    db.add(UserPermission(user_id=user.id, permission_id=perm.id, granted_by=current_user["user_id"]))
    await db.commit()
    return {"message": f"Permission '{req.module}.{req.operation}' granted to {req.user_email}"}


@router.post("/users/revoke-permission")
async def revoke_permission(
    req: RevokePermissionRequest,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user_result = await db.execute(select(User).where(User.email == req.user_email))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, f"User not found")

    perm_result = await db.execute(
        select(Permission).where(Permission.module == req.module, Permission.operation == req.operation)
    )
    perm = perm_result.scalar_one_or_none()
    if not perm:
        raise HTTPException(404, f"Permission not found")

    existing = await db.execute(
        select(UserPermission).where(
            UserPermission.user_id == user.id, UserPermission.permission_id == perm.id
        )
    )
    up = existing.scalar_one_or_none()
    if up:
        await db.delete(up)
        await db.commit()
    return {"message": f"Permission revoked"}


@router.get("/audit-logs")
async def get_audit_logs(
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    limit: int = 100,
    offset: int = 0,
):
    from app.models.audit_log import AuditLog
    result = await db.execute(
        select(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    logs = result.scalars().all()
    return {
        "logs": [
            {
                "id": log.id,
                "user_email": log.user_email,
                "action": log.action,
                "module": log.module,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "details": log.details,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]
    }
