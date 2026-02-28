"""Admin panel endpoints — user management, RBAC, secrets, audit logs."""
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.core.auth import require_admin
from app.models.user import User, Role, Permission, UserRole, UserPermission
from app.models.audit_log import AuditLog
from app.config import settings
from app.schemas.admin import (
    GrantRoleRequest, RevokeRoleRequest,
    GrantPermissionRequest, RevokePermissionRequest,
    ToggleAdminRequest, SetPermissionsRequest,
)

router = APIRouter()
logger = logging.getLogger(__name__)


async def _audit(
    db: AsyncSession,
    *,
    user_id: int,
    user_email: str,
    action: str,
    module: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
):
    """Helper to create an audit log entry."""
    db.add(AuditLog(
        user_id=user_id,
        user_email=user_email,
        action=action,
        module=module,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
    ))


@router.get("/users")
async def list_users(
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.roles).selectinload(UserRole.role),
            selectinload(User.permissions).selectinload(UserPermission.permission),
        )
        .order_by(User.email)
    )
    users = result.scalars().all()

    superadmin = settings.primary_admin_email
    return {
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "display_name": u.display_name,
                "is_admin": u.is_admin,
                "is_superadmin": u.email == superadmin,
                "is_active": u.is_active,
                "roles": [ur.role.name for ur in u.roles] if u.roles else [],
                "direct_permissions": [
                    {"module": up.permission.module, "operation": up.permission.operation}
                    for up in u.permissions
                ] if u.permissions else [],
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


@router.post("/users/toggle-admin")
async def toggle_admin(
    req: ToggleAdminRequest,
    request: Request,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Promote or demote a user to/from admin.

    Superadmin (primary_admin_email) can never be demoted — not even
    by themselves.  Only existing admins can call this endpoint.
    """
    superadmin = settings.primary_admin_email

    # Block demoting the superadmin
    if req.user_email == superadmin:
        raise HTTPException(403, f"{superadmin} is the superadmin and cannot be demoted")

    user_result = await db.execute(select(User).where(User.email == req.user_email))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, f"User '{req.user_email}' not found")

    user.is_admin = not user.is_admin

    action = "promote_admin" if user.is_admin else "demote_admin"
    await _audit(
        db,
        user_id=current_user["user_id"],
        user_email=current_user.get("email", ""),
        action=action,
        module="admin",
        resource_type="user",
        resource_id=req.user_email,
        details={"target_user": req.user_email, "new_is_admin": user.is_admin},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()

    label = "promoted to admin" if user.is_admin else "demoted from admin"
    return {"message": f"{req.user_email} {label}", "is_admin": user.is_admin}


@router.post("/users/grant-role")
async def grant_role(
    req: GrantRoleRequest,
    request: Request,
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

    # Roles are hierarchical (admin > operator > viewer) — replace all existing
    existing_roles = await db.execute(
        select(UserRole).where(UserRole.user_id == user.id)
    )
    for ur in existing_roles.scalars().all():
        await db.delete(ur)
    await db.flush()

    db.add(UserRole(user_id=user.id, role_id=role.id, granted_by=current_user["user_id"]))

    await _audit(
        db,
        user_id=current_user["user_id"],
        user_email=current_user.get("email", ""),
        action="grant_role",
        module="admin",
        resource_type="user",
        resource_id=req.user_email,
        details={"target_user": req.user_email, "role": req.role_name},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return {"message": f"Role set to '{req.role_name}' for {req.user_email}"}


@router.post("/users/revoke-role")
async def revoke_role(
    req: RevokeRoleRequest,
    request: Request,
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

    await _audit(
        db,
        user_id=current_user["user_id"],
        user_email=current_user.get("email", ""),
        action="revoke_role",
        module="admin",
        resource_type="user",
        resource_id=req.user_email,
        details={"target_user": req.user_email, "role": req.role_name},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return {"message": f"Role '{req.role_name}' revoked from {req.user_email}"}


@router.post("/users/grant-permission")
async def grant_permission(
    req: GrantPermissionRequest,
    request: Request,
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

    await _audit(
        db,
        user_id=current_user["user_id"],
        user_email=current_user.get("email", ""),
        action="grant_permission",
        module="admin",
        resource_type="user",
        resource_id=req.user_email,
        details={"target_user": req.user_email, "permission": f"{req.module}.{req.operation}"},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return {"message": f"Permission '{req.module}.{req.operation}' granted to {req.user_email}"}


@router.post("/users/revoke-permission")
async def revoke_permission(
    req: RevokePermissionRequest,
    request: Request,
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

    await _audit(
        db,
        user_id=current_user["user_id"],
        user_email=current_user.get("email", ""),
        action="revoke_permission",
        module="admin",
        resource_type="user",
        resource_id=req.user_email,
        details={"target_user": req.user_email, "permission": f"{req.module}.{req.operation}"},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return {"message": f"Permission revoked"}


@router.post("/users/set-permissions")
async def set_permissions(
    req: SetPermissionsRequest,
    request: Request,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Bulk-set ALL direct permissions for a user (replaces existing)."""
    # Find or create user
    user_result = await db.execute(select(User).where(User.email == req.user_email))
    user = user_result.scalar_one_or_none()
    if not user:
        user = User(email=req.user_email, is_active=True)
        db.add(user)
        await db.flush()

    # Delete all existing direct permissions for this user
    existing = await db.execute(
        select(UserPermission).where(UserPermission.user_id == user.id)
    )
    for up in existing.scalars().all():
        await db.delete(up)
    await db.flush()

    # Insert new permissions
    granted = []
    for perm_req in req.permissions:
        perm_result = await db.execute(
            select(Permission).where(
                Permission.module == perm_req.module,
                Permission.operation == perm_req.operation,
            )
        )
        perm = perm_result.scalar_one_or_none()
        if perm:
            db.add(UserPermission(
                user_id=user.id,
                permission_id=perm.id,
                granted_by=current_user["user_id"],
            ))
            granted.append(f"{perm_req.module}.{perm_req.operation}")

    await _audit(
        db,
        user_id=current_user["user_id"],
        user_email=current_user.get("email", ""),
        action="set_permissions",
        module="admin",
        resource_type="user",
        resource_id=req.user_email,
        details={"target_user": req.user_email, "permissions": granted},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return {
        "message": f"Set {len(granted)} permissions for {req.user_email}",
        "granted": granted,
    }


@router.get("/audit-logs")
async def get_audit_logs(
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    limit: int = 100,
    offset: int = 0,
):
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
