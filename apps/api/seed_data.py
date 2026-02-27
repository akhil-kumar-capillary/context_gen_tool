"""Seed script to populate roles, permissions, and primary admin.
Run after initial migration: python seed_data.py
"""
import sys
import asyncio
import traceback
from sqlalchemy import select
from app.database import async_session
from app.models.user import User, Role, Permission, RolePermission, UserRole
from app.config import settings

# Module definitions
MODULES = {
    "databricks": ["view", "extract", "analyze", "generate"],
    "confluence": ["view", "connect", "extract", "generate"],
    "config_apis": ["view", "fetch", "analyze", "generate"],
    "context_management": ["view", "create", "edit", "delete", "refactor"],
    "context_engine": ["view", "edit", "generate", "sync"],
    "admin": ["view", "manage_users", "manage_secrets"],
}

# Role definitions
# Roles define the *access level* (what operations a user can do).
# Module access is granted independently by admin via direct UserPermissions.
# See ROLE_CAPABILITIES in app/core/rbac.py for how these interact.
ROLES = {
    "admin": {
        "description": "Full access to all modules and administration",
        "permissions": "all",
    },
    "operator": {
        "description": "Full CRUD access level (modules granted separately by admin)",
        "permissions": {
            "context_management": ["view", "create", "edit", "delete", "refactor"],
            "context_engine": ["view", "edit", "generate", "sync"],
        },
    },
    "viewer": {
        "description": "Read-only access level (modules granted separately by admin)",
        "permissions": {
            "context_management": ["view"],
            "context_engine": ["view"],
        },
    },
}


async def seed():
    async with async_session() as db:
        # 1. Seed permissions
        all_perms = {}
        for module, operations in MODULES.items():
            for op in operations:
                result = await db.execute(
                    select(Permission).where(
                        Permission.module == module,
                        Permission.operation == op,
                    )
                )
                perm = result.scalar_one_or_none()
                if not perm:
                    perm = Permission(
                        module=module,
                        operation=op,
                        description=f"{module}.{op}",
                    )
                    db.add(perm)
                    await db.flush()
                all_perms[(module, op)] = perm

        # 2. Seed roles
        for role_name, role_def in ROLES.items():
            result = await db.execute(select(Role).where(Role.name == role_name))
            role = result.scalar_one_or_none()
            if not role:
                role = Role(name=role_name, description=role_def["description"])
                db.add(role)
                await db.flush()

            # Assign permissions to role
            if role_def["permissions"] == "all":
                target_perms = list(all_perms.values())
            else:
                target_perms = []
                for mod, ops in role_def["permissions"].items():
                    for op in ops:
                        if (mod, op) in all_perms:
                            target_perms.append(all_perms[(mod, op)])

            for perm in target_perms:
                existing = await db.execute(
                    select(RolePermission).where(
                        RolePermission.role_id == role.id,
                        RolePermission.permission_id == perm.id,
                    )
                )
                if not existing.scalar_one_or_none():
                    db.add(RolePermission(role_id=role.id, permission_id=perm.id))

            # Remove stale RolePermissions no longer in the role definition
            # (e.g. viewer losing databricks:view after role narrowing)
            target_perm_ids = {p.id for p in target_perms}
            all_role_perms = await db.execute(
                select(RolePermission).where(RolePermission.role_id == role.id)
            )
            for rp in all_role_perms.scalars().all():
                if rp.permission_id not in target_perm_ids:
                    await db.delete(rp)

        # 3. Seed primary admin user
        result = await db.execute(
            select(User).where(User.email == settings.primary_admin_email)
        )
        admin_user = result.scalar_one_or_none()
        if not admin_user:
            admin_user = User(
                email=settings.primary_admin_email,
                display_name="Akhil Kumar",
                is_admin=True,
                is_active=True,
            )
            db.add(admin_user)
            await db.flush()

            # Assign admin role
            admin_role = await db.execute(select(Role).where(Role.name == "admin"))
            admin_role = admin_role.scalar_one()
            db.add(UserRole(user_id=admin_user.id, role_id=admin_role.id))

        await db.commit()
        print("Seed data applied successfully!", flush=True)
        print(f"  - {len(all_perms)} permissions", flush=True)
        print(f"  - {len(ROLES)} roles", flush=True)
        print(f"  - Primary admin: {settings.primary_admin_email}", flush=True)


if __name__ == "__main__":
    print("seed_data.py: starting...", flush=True)
    try:
        asyncio.run(seed())
    except Exception as e:
        print(f"seed_data.py FAILED: {e}", flush=True)
        traceback.print_exc()
        sys.exit(1)
