"""Сервис для работы с метаданными файлов."""
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.file_metadata import FileMetadata


class FileService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, file_id: int) -> Optional[FileMetadata]:
        result = await self.session.execute(
            select(FileMetadata).where(FileMetadata.id == file_id)
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> FileMetadata:
        file = FileMetadata(**kwargs)
        self.session.add(file)
        await self.session.commit()
        await self.session.refresh(file)
        return file

    async def update(self, file_id: int, **kwargs) -> Optional[FileMetadata]:
        file = await self.get_by_id(file_id)
        if not file:
            return None
        for key, value in kwargs.items():
            if value is not None and hasattr(file, key):
                setattr(file, key, value)
        await self.session.commit()
        await self.session.refresh(file)
        return file

    async def delete(self, file_id: int) -> bool:
        file = await self.get_by_id(file_id)
        if not file:
            return False
        await self.session.delete(file)
        await self.session.commit()
        return True
