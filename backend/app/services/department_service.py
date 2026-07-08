"""Сервис для работы с отделами."""
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.department import Department


class DepartmentService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> List[Department]:
        result = await self.session.execute(
            select(Department).order_by(Department.name)
        )
        return list(result.scalars().all())

    async def get_by_id(self, dept_id: int) -> Optional[Department]:
        result = await self.session.execute(
            select(Department).where(Department.id == dept_id)
        )
        return result.scalar_one_or_none()

    async def create(self, name: str, code: str, description: Optional[str] = None) -> Department:
        dept = Department(name=name, code=code, description=description)
        self.session.add(dept)
        await self.session.commit()
        await self.session.refresh(dept)
        return dept

    async def update(self, dept_id: int, **kwargs) -> Optional[Department]:
        dept = await self.get_by_id(dept_id)
        if not dept:
            return None
        for key, value in kwargs.items():
            if value is not None and hasattr(dept, key):
                setattr(dept, key, value)
        await self.session.commit()
        await self.session.refresh(dept)
        return dept

    async def delete(self, dept_id: int) -> bool:
        dept = await self.get_by_id(dept_id)
        if not dept:
            return False
        await self.session.delete(dept)
        await self.session.commit()
        return True
