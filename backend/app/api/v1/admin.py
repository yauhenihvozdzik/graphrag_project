"""Admin settings API router.

Provides endpoints for managing dynamic configuration:
- View all / category settings
- Update single or batch settings
- Reload settings cache
- View settings change history

All endpoints require the ``admin`` role.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.v1.auth import get_access_context, get_current_user
from app.core.config import settings
from app.core.logging import logger
from app.core.security.guardrails import guardrails_service
from app.core.security.rbac import RBACService, Role
from app.core.settings_registry import SettingsRegistry
from app.models.schemas import (
    AdminSettingResponse,
    AdminSettingsAll,
    AdminSettingsCategory,
    AdminSettingsHistory,
    AdminSettingUpdate,
    AdminSettingsUpdateRequest,
)
from app.services.database import database_service
from app.models.admin import AdminSetting, AdminSettingsAudit

router = APIRouter(prefix="/admin", tags=["admin"])


def _setting_to_response(setting: Any) -> dict:
    """Convert an ORM AdminSetting row to a dict matching AdminSettingResponse."""
    import json

    try:
        value = json.loads(setting.value) if setting.value else setting.value
    except (json.JSONDecodeError, TypeError):
        value = setting.value
    return {
        "id": setting.id,
        "category": setting.category,
        "key": setting.key,
        "value": value,
        "description": setting.description,
        "is_active": setting.is_active,
        "updated_at": setting.updated_at,
    }


@router.get("/settings", response_model=AdminSettingsAll)
async def get_all_settings(
    current_user: dict = Depends(get_current_user),
    access_context: Any = Depends(get_access_context),
):
    """Get all settings, grouped by category.

    Returns a dict of ``{category_name: [setting, ...]}``.
    """
    RBACService.require_role(access_context, Role.ADMIN)
    registry = SettingsRegistry()

    # Try cache first, fall back to DB
    categories: dict[str, list[dict]] = {}
    if registry._settings:
        for cat, kv in registry._settings.items():
            rows = database_service.get_admin_settings_by_category(cat)
            categories[cat] = [_setting_to_response(r) for r in rows]
    else:
        rows = database_service.get_all_admin_settings()
        for row in rows:
            categories.setdefault(row.category, []).append(_setting_to_response(row))

    logger.info("admin_get_all_settings", categories=list(categories.keys()))
    return AdminSettingsAll(categories=categories)


@router.put("/settings/{setting_id}", response_model=AdminSettingResponse)
async def update_setting(
    setting_id: int,
    update: AdminSettingUpdate,
    current_user: dict = Depends(get_current_user),
    access_context: Any = Depends(get_access_context),
):
    """Update a single setting by ID.

    Performs the update in DB, reloads the registry cache, and re-compiles
    guardrail patterns if the setting belongs to the ``guardrails`` category.
    """
    RBACService.require_role(access_context, Role.ADMIN)

    updated = database_service.update_admin_setting(
        setting_id=setting_id,
        value=update.value,
        updated_by=current_user["user_id"],
    )
    if not updated:
        raise HTTPException(
            status_code=404,
            detail=f"Настройка с ID {setting_id} не найдена",
        )

    # Reload registry cache
    registry = SettingsRegistry()
    await registry.reload()

    # Re-compile guardrail patterns if guardrails category changed
    if updated.category == "guardrails":
        guardrails_service.reload_config()

    logger.info(
        "admin_setting_updated",
        setting_id=setting_id,
        category=updated.category,
        key=updated.key,
    )
    return _setting_to_response(updated)


@router.put("/settings/category/{category}", response_model=AdminSettingsCategory)
async def update_category_settings(
    category: str,
    body: AdminSettingsUpdateRequest,
    current_user: dict = Depends(get_current_user),
    access_context: Any = Depends(get_access_context),
):
    """Bulk-update all settings in a category.

    Accepts a ``AdminSettingsUpdateRequest`` containing a list of
    ``AdminSettingUpdate`` items. Each item's order corresponds to the
    order of settings returned by :meth:`get_settings_by_category`.
    """
    RBACService.require_role(access_context, Role.ADMIN)

    settings = body.settings

    rows = database_service.get_admin_settings_by_category(category)
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"Категория '{category}' не найдена",
        )
    if len(settings) != len(rows):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Количество переданных настроек ({len(settings)}) "
                f"не совпадает с количеством в категории ({len(rows)})"
            ),
        )

    updated_rows = []
    for row, upd in zip(rows, settings):
        updated = database_service.update_admin_setting(
            setting_id=row.id,
            value=upd.value,
            updated_by=current_user["user_id"],
        )
        if updated:
            updated_rows.append(updated)

    # Reload registry and re-compile guardrails
    registry = SettingsRegistry()
    await registry.reload()

    if category == "guardrails":
        guardrails_service.reload_config()

    logger.info("admin_category_updated", category=category, count=len(updated_rows))
    return AdminSettingsCategory(
        category=category,
        settings=[_setting_to_response(r) for r in updated_rows],
    )


@router.get("/_debug/registry")
async def debug_registry(
    current_user: dict = Depends(get_current_user),
    access_context: Any = Depends(get_access_context),
):
    """DEBUG: Show raw registry state."""
    if not settings.DEBUG:
        raise HTTPException(404, "Not found")
    RBACService.require_role(access_context, Role.ADMIN)
    registry = SettingsRegistry()
    return {
        "registry_id": id(registry),
        "settings_keys": list(registry._settings.keys()),
        "settings_data": {
            cat: list(kv.keys()) for cat, kv in registry._settings.items()
        },
        "injection_compiled": len(registry._injection_compiled),
        "pii_compiled": list(registry._pii_compiled.keys()),
        "system_prompt_from_registry": registry.get_system_prompt()[:200] if registry.get_system_prompt() else None,
    }


@router.post("/settings/reload")
async def reload_settings(
    current_user: dict = Depends(get_current_user),
    access_context: Any = Depends(get_access_context),
):
    """Force-reload the settings registry cache from the database."""
    RBACService.require_role(access_context, Role.ADMIN)

    registry = SettingsRegistry()
    await registry.reload()

    # Re-compile guardrail patterns from the fresh cache
    guardrails_service.reload_config()

    logger.info("admin_settings_reloaded")
    return {"success": True, "message": "Кэш настроек перезагружен"}


@router.get("/settings/history", response_model=list[AdminSettingsHistory])
async def get_settings_history(
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
    access_context: Any = Depends(get_access_context),
):
    """Return paginated audit history of setting changes."""
    RBACService.require_role(access_context, Role.ADMIN)

    audit_records = database_service.get_admin_settings_history(
        limit=limit, offset=offset,
    )

    result: list[dict] = []
    for audit in audit_records:
        # Resolve the setting key and category using sync engine
        with database_service._get_sync_session() as s:
            setting_row = s.get(AdminSetting, audit.setting_id)

        # Resolve the user who made the change
        changed_by_name: str | None = None
        if audit.changed_by:
            user_row = database_service.get_user_by_id(audit.changed_by)
            if user_row:
                changed_by_name = user_row.email or user_row.username

        result.append(
            AdminSettingsHistory(
                id=audit.id,
                setting_key=setting_row.key if setting_row else f"id:{audit.setting_id}",
                category=setting_row.category if setting_row else "unknown",
                old_value=audit.old_value,
                new_value=audit.new_value,
                changed_at=audit.changed_at,
                changed_by=changed_by_name,
            ).model_dump()
        )

    logger.info("admin_get_history", count=len(result), limit=limit, offset=offset)
    return result


@router.get("/settings/{category}", response_model=AdminSettingsCategory)
async def get_settings_by_category(
    category: str,
    current_user: dict = Depends(get_current_user),
    access_context: Any = Depends(get_access_context),
):
    """Get all settings for a specific category."""
    RBACService.require_role(access_context, Role.ADMIN)

    rows = database_service.get_admin_settings_by_category(category)
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"Категория '{category}' не найдена или не содержит настроек",
        )

    logger.info("admin_get_category", category=category, count=len(rows))
    return AdminSettingsCategory(
        category=category,
        settings=[_setting_to_response(r) for r in rows],
    )
