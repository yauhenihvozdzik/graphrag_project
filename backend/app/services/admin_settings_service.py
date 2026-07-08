"""Сервис для работы с admin settings."""
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.admin import AdminSetting


class AdminSettingsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> List[AdminSetting]:
        result = await self.session.execute(
            select(AdminSetting).order_by(AdminSetting.category, AdminSetting.key)
        )
        return list(result.scalars().all())

    async def get_by_key(self, key: str) -> Optional[AdminSetting]:
        result = await self.session.execute(
            select(AdminSetting).where(AdminSetting.key == key)
        )
        return result.scalar_one_or_none()

    async def set(self, key: str, value: str, updated_by: int) -> AdminSetting:
        setting = await self.get_by_key(key)
        if setting:
            setting.value = value
            setting.updated_by = updated_by
        else:
            setting = AdminSetting(key=key, value=value, updated_by=updated_by)
            self.session.add(setting)
        await self.session.commit()
        await self.session.refresh(setting)
        return setting

    async def get_history(self, key: str) -> List[AdminSetting]:
        result = await self.session.execute(
            select(AdminSetting)
            .where(AdminSetting.key == key)
            .order_by(AdminSetting.updated_at.desc())
        )
        return list(result.scalars().all())
