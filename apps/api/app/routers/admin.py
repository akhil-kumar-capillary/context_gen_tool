"""Admin panel endpoints — user management, RBAC, platform variables, audit logs."""
import json
import logging
import re as re_module
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.core.auth import require_admin, get_current_user
from app.core.cache import app_cache
from app.models.user import User, Role, Permission, UserRole, UserPermission
from app.models.audit_log import AuditLog
from app.models.platform_settings import PlatformSettings
from app.models.platform_variable import PlatformVariable
from app.config import settings
from pydantic import BaseModel
from app.schemas.admin import (
    GrantRoleRequest, RevokeRoleRequest,
    GrantPermissionRequest, RevokePermissionRequest,
    ToggleAdminRequest, SetPermissionsRequest,
)
from app.schemas.platform_variable import (
    PlatformVariableCreate, PlatformVariableUpdate,
    PlatformVariableImportRequest,
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


# ── Theme Customization ─────────────────────────────────────────────

THEME_PRESETS = {
    "slate_blue": {"light": "215 70% 55%", "dark": "215 70% 65%"},
    "indigo":     {"light": "239 84% 67%", "dark": "239 84% 74%"},
    "teal":       {"light": "172 66% 50%", "dark": "172 66% 60%"},
    "emerald":    {"light": "160 84% 39%", "dark": "160 84% 49%"},
    "rose":       {"light": "346 77% 50%", "dark": "346 77% 60%"},
    "amber":      {"light": "38 92% 50%",  "dark": "38 92% 60%"},
}

DEFAULT_THEME = THEME_PRESETS["slate_blue"]


import re

_HSL_PATTERN = re.compile(r"^\d{1,3}\s+\d{1,3}%\s+\d{1,3}%$")
_VALID_PRESETS = set(THEME_PRESETS.keys()) | {"custom"}


class ThemeUpdateRequest(BaseModel):
    theme_preset: str = "slate_blue"
    primary_hsl_light: str = DEFAULT_THEME["light"]
    primary_hsl_dark: str = DEFAULT_THEME["dark"]
    dark_mode_default: bool = False

    def validate_theme(self):
        if self.theme_preset not in _VALID_PRESETS:
            raise HTTPException(400, f"Invalid preset: {self.theme_preset}")
        if not _HSL_PATTERN.match(self.primary_hsl_light):
            raise HTTPException(400, f"Invalid HSL for light mode: {self.primary_hsl_light}")
        if not _HSL_PATTERN.match(self.primary_hsl_dark):
            raise HTTPException(400, f"Invalid HSL for dark mode: {self.primary_hsl_dark}")


@router.get("/theme")
async def get_theme(db: AsyncSession = Depends(get_db)):
    """Public endpoint — returns current platform theme. No auth required."""
    result = await db.execute(select(PlatformSettings).where(PlatformSettings.id == 1))
    s = result.scalar_one_or_none()
    if not s:
        return {
            "theme_preset": "slate_blue",
            "primary_hsl_light": DEFAULT_THEME["light"],
            "primary_hsl_dark": DEFAULT_THEME["dark"],
            "dark_mode_default": False,
            "presets": THEME_PRESETS,
        }
    return {
        "theme_preset": s.theme_preset,
        "primary_hsl_light": s.primary_hsl_light,
        "primary_hsl_dark": s.primary_hsl_dark,
        "dark_mode_default": s.dark_mode_default,
        "presets": THEME_PRESETS,
    }


@router.put("/theme")
async def update_theme(
    req: ThemeUpdateRequest,
    request: Request,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin only — update platform theme."""
    req.validate_theme()
    result = await db.execute(select(PlatformSettings).where(PlatformSettings.id == 1))
    s = result.scalar_one_or_none()
    if not s:
        s = PlatformSettings(id=1)
        db.add(s)

    s.theme_preset = req.theme_preset
    s.primary_hsl_light = req.primary_hsl_light
    s.primary_hsl_dark = req.primary_hsl_dark
    s.dark_mode_default = req.dark_mode_default
    s.updated_by = current_user["user_id"]

    await _audit(
        db,
        user_id=current_user["user_id"],
        user_email=current_user.get("email", ""),
        action="update_theme",
        module="admin",
        resource_type="platform_settings",
        resource_id="theme",
        details={"preset": req.theme_preset, "dark_mode_default": req.dark_mode_default},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return {"message": "Theme updated", "theme_preset": s.theme_preset}


@router.post("/theme/reset")
async def reset_theme(
    request: Request,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin only — reset theme to Slate Blue defaults."""
    result = await db.execute(select(PlatformSettings).where(PlatformSettings.id == 1))
    s = result.scalar_one_or_none()
    if not s:
        s = PlatformSettings(id=1)
        db.add(s)

    s.theme_preset = "slate_blue"
    s.primary_hsl_light = DEFAULT_THEME["light"]
    s.primary_hsl_dark = DEFAULT_THEME["dark"]
    s.dark_mode_default = False
    s.updated_by = current_user["user_id"]

    await _audit(
        db,
        user_id=current_user["user_id"],
        user_email=current_user.get("email", ""),
        action="reset_theme",
        module="admin",
        resource_type="platform_settings",
        resource_id="theme",
        details={},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return {"message": "Theme reset to Slate Blue"}


# ── Platform Variables ─────────────────────────────────────────────

_VALID_VALUE_TYPES = {"string", "number", "boolean", "json", "url", "text"}
_KEY_PATTERN = re_module.compile(r"^[a-zA-Z0-9/_\-\.]+$")


def _validate_variable_value(
    value: str | None, value_type: str, validation_rule: str | None = None,
) -> None:
    """Validate a platform variable value against its type and optional regex."""
    if value is None or value == "":
        return
    if value_type == "number":
        try:
            float(value)
        except ValueError:
            raise HTTPException(400, f"Value must be a valid number, got: {value}")
    elif value_type == "boolean":
        if value.lower() not in ("true", "false"):
            raise HTTPException(400, f"Value must be 'true' or 'false', got: {value}")
    elif value_type == "json":
        try:
            json.loads(value)
        except (json.JSONDecodeError, TypeError):
            raise HTTPException(400, "Value must be valid JSON")
    elif value_type == "url":
        if not value.startswith(("http://", "https://")):
            raise HTTPException(400, "Value must be a valid URL starting with http:// or https://")
    if validation_rule:
        try:
            pattern = re_module.compile(validation_rule)
        except re_module.error:
            raise HTTPException(400, f"Invalid validation regex: {validation_rule}")
        if not pattern.match(value):
            raise HTTPException(400, f"Value does not match validation rule: {validation_rule}")


def _serialize_variable(v: PlatformVariable) -> dict:
    return {
        "id": v.id,
        "key": v.key,
        "value": v.value,
        "value_type": v.value_type,
        "group_name": v.group_name,
        "description": v.description,
        "default_value": v.default_value,
        "is_required": v.is_required,
        "validation_rule": v.validation_rule,
        "sort_order": v.sort_order,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "updated_at": v.updated_at.isoformat() if v.updated_at else None,
    }


@router.get("/platform-variables")
async def list_platform_variables(
    group: str | None = Query(None),
    search: str | None = Query(None),
    value_type: str | None = Query(None),
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all platform variables with optional filters."""
    query = select(PlatformVariable).order_by(
        PlatformVariable.group_name, PlatformVariable.sort_order, PlatformVariable.key,
    )
    if group:
        query = query.where(PlatformVariable.group_name == group)
    if value_type:
        query = query.where(PlatformVariable.value_type == value_type)
    if search:
        like_term = f"%{search}%"
        query = query.where(
            PlatformVariable.key.ilike(like_term)
            | PlatformVariable.value.ilike(like_term)
            | PlatformVariable.description.ilike(like_term)
        )

    result = await db.execute(query)
    variables = result.scalars().all()

    # Group counts
    group_result = await db.execute(
        select(PlatformVariable.group_name, func.count(PlatformVariable.id))
        .group_by(PlatformVariable.group_name)
        .order_by(PlatformVariable.group_name)
    )
    groups = [
        {"name": name or "Ungrouped", "count": count}
        for name, count in group_result.all()
    ]

    return {
        "variables": [_serialize_variable(v) for v in variables],
        "groups": groups,
    }


@router.post("/platform-variables")
async def create_platform_variable(
    req: PlatformVariableCreate,
    request: Request,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new platform variable."""
    # Validate key format
    if not _KEY_PATTERN.match(req.key):
        raise HTTPException(400, "Key must contain only letters, numbers, /, _, -, .")

    # Validate value_type
    if req.value_type not in _VALID_VALUE_TYPES:
        raise HTTPException(400, f"Invalid value_type. Must be one of: {', '.join(sorted(_VALID_VALUE_TYPES))}")

    # Check uniqueness
    existing = await db.execute(
        select(PlatformVariable).where(PlatformVariable.key == req.key)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Variable with key '{req.key}' already exists")

    # Validate value
    _validate_variable_value(req.value, req.value_type, req.validation_rule)

    var = PlatformVariable(
        key=req.key,
        value=req.value,
        value_type=req.value_type,
        group_name=req.group_name,
        description=req.description,
        default_value=req.default_value,
        is_required=req.is_required,
        validation_rule=req.validation_rule,
        sort_order=req.sort_order,
        created_by=current_user["user_id"],
        updated_by=current_user["user_id"],
    )
    db.add(var)

    await _audit(
        db,
        user_id=current_user["user_id"],
        user_email=current_user.get("email", ""),
        action="create_platform_variable",
        module="admin",
        resource_type="platform_variable",
        resource_id=req.key,
        details={"key": req.key, "value": req.value, "value_type": req.value_type, "group": req.group_name},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(var)
    app_cache.invalidate_prefix("platform_vars:")

    return {"message": f"Variable '{req.key}' created", "variable": _serialize_variable(var)}


@router.put("/platform-variables/{variable_id}")
async def update_platform_variable(
    variable_id: int,
    req: PlatformVariableUpdate,
    request: Request,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing platform variable."""
    result = await db.execute(
        select(PlatformVariable).where(PlatformVariable.id == variable_id)
    )
    var = result.scalar_one_or_none()
    if not var:
        raise HTTPException(404, "Variable not found")

    old_value = var.value

    # Determine effective value_type for validation
    effective_type = req.value_type if req.value_type is not None else var.value_type
    if req.value_type is not None and req.value_type not in _VALID_VALUE_TYPES:
        raise HTTPException(400, f"Invalid value_type. Must be one of: {', '.join(sorted(_VALID_VALUE_TYPES))}")

    # Determine effective validation_rule
    effective_rule = req.validation_rule if req.validation_rule is not None else var.validation_rule

    # Validate new value if provided
    if req.value is not None:
        _validate_variable_value(req.value, effective_type, effective_rule)

    # Apply updates (only non-None fields)
    if req.value is not None:
        var.value = req.value
    if req.value_type is not None:
        var.value_type = req.value_type
    if req.group_name is not None:
        var.group_name = req.group_name
    if req.description is not None:
        var.description = req.description
    if req.default_value is not None:
        var.default_value = req.default_value
    if req.is_required is not None:
        var.is_required = req.is_required
    if req.validation_rule is not None:
        var.validation_rule = req.validation_rule
    if req.sort_order is not None:
        var.sort_order = req.sort_order
    var.updated_by = current_user["user_id"]

    await _audit(
        db,
        user_id=current_user["user_id"],
        user_email=current_user.get("email", ""),
        action="update_platform_variable",
        module="admin",
        resource_type="platform_variable",
        resource_id=str(variable_id),
        details={
            "key": var.key,
            "old_value": old_value,
            "new_value": req.value if req.value is not None else old_value,
            "change_reason": req.change_reason,
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(var)
    app_cache.invalidate_prefix("platform_vars:")

    return {"message": f"Variable '{var.key}' updated", "variable": _serialize_variable(var)}


@router.delete("/platform-variables/{variable_id}")
async def delete_platform_variable(
    variable_id: int,
    request: Request,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a platform variable."""
    result = await db.execute(
        select(PlatformVariable).where(PlatformVariable.id == variable_id)
    )
    var = result.scalar_one_or_none()
    if not var:
        raise HTTPException(404, "Variable not found")

    key = var.key
    last_value = var.value

    await _audit(
        db,
        user_id=current_user["user_id"],
        user_email=current_user.get("email", ""),
        action="delete_platform_variable",
        module="admin",
        resource_type="platform_variable",
        resource_id=str(variable_id),
        details={"key": key, "last_value": last_value},
        ip_address=request.client.host if request.client else None,
    )
    await db.delete(var)
    await db.commit()
    app_cache.invalidate_prefix("platform_vars:")

    return {"message": f"Variable '{key}' deleted"}


@router.get("/platform-variables/groups")
async def list_platform_variable_groups(
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get unique groups with counts."""
    result = await db.execute(
        select(PlatformVariable.group_name, func.count(PlatformVariable.id))
        .group_by(PlatformVariable.group_name)
        .order_by(PlatformVariable.group_name)
    )
    return {
        "groups": [
            {"name": name or "Ungrouped", "count": count}
            for name, count in result.all()
        ]
    }


@router.get("/platform-variables/values")
async def get_platform_variable_values(
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint — flat {key: value} dict for app consumption. No admin required."""
    cached = app_cache.get("platform_vars:values")
    if cached is not None:
        return cached

    result = await db.execute(
        select(PlatformVariable.key, PlatformVariable.value, PlatformVariable.default_value)
    )
    values = {}
    for key, value, default_value in result.all():
        values[key] = value if value is not None else default_value

    app_cache.set("platform_vars:values", values)
    return values


@router.get("/platform-variables/{variable_id}/history")
async def get_platform_variable_history(
    variable_id: int,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get audit trail for a specific platform variable."""
    result = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.resource_type == "platform_variable",
            AuditLog.resource_id == str(variable_id),
        )
        .order_by(AuditLog.created_at.desc())
        .limit(50)
    )
    logs = result.scalars().all()
    return {
        "history": [
            {
                "id": log.id,
                "user_email": log.user_email,
                "action": log.action,
                "details": log.details,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]
    }


@router.post("/platform-variables/import")
async def import_platform_variables(
    req: PlatformVariableImportRequest,
    request: Request,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Bulk import platform variables from JSON."""
    created = 0
    updated = 0
    errors = []

    for item in req.variables:
        if not _KEY_PATTERN.match(item.key):
            errors.append(f"Invalid key format: {item.key}")
            continue
        if item.value_type not in _VALID_VALUE_TYPES:
            errors.append(f"Invalid value_type for {item.key}: {item.value_type}")
            continue
        try:
            _validate_variable_value(item.value, item.value_type, item.validation_rule)
        except HTTPException as e:
            errors.append(f"{item.key}: {e.detail}")
            continue

        existing_result = await db.execute(
            select(PlatformVariable).where(PlatformVariable.key == item.key)
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            if not req.overwrite:
                errors.append(f"Key '{item.key}' already exists (overwrite=false)")
                continue
            existing.value = item.value
            existing.value_type = item.value_type
            existing.group_name = item.group_name
            existing.description = item.description
            existing.default_value = item.default_value
            existing.is_required = item.is_required
            existing.validation_rule = item.validation_rule
            existing.sort_order = item.sort_order
            existing.updated_by = current_user["user_id"]
            updated += 1
        else:
            db.add(PlatformVariable(
                key=item.key,
                value=item.value,
                value_type=item.value_type,
                group_name=item.group_name,
                description=item.description,
                default_value=item.default_value,
                is_required=item.is_required,
                validation_rule=item.validation_rule,
                sort_order=item.sort_order,
                created_by=current_user["user_id"],
                updated_by=current_user["user_id"],
            ))
            created += 1

    await _audit(
        db,
        user_id=current_user["user_id"],
        user_email=current_user.get("email", ""),
        action="import_platform_variables",
        module="admin",
        resource_type="platform_variable",
        details={"created": created, "updated": updated, "errors": len(errors), "overwrite": req.overwrite},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    app_cache.invalidate_prefix("platform_vars:")

    return {
        "message": f"Import complete: {created} created, {updated} updated, {len(errors)} errors",
        "created": created,
        "updated": updated,
        "errors": errors,
    }


@router.get("/platform-variables/export")
async def export_platform_variables(
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Export all platform variables as JSON."""
    result = await db.execute(
        select(PlatformVariable).order_by(PlatformVariable.group_name, PlatformVariable.sort_order)
    )
    variables = result.scalars().all()
    return {
        "variables": [
            {
                "key": v.key,
                "value": v.value,
                "value_type": v.value_type,
                "group_name": v.group_name,
                "description": v.description,
                "default_value": v.default_value,
                "is_required": v.is_required,
                "validation_rule": v.validation_rule,
                "sort_order": v.sort_order,
            }
            for v in variables
        ]
    }
