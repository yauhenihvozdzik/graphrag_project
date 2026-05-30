"""Department management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.v1.auth import get_current_user
from app.models.schemas import DepartmentCreate, DepartmentResponse, DepartmentUpdate
from app.services.database import database_service

router = APIRouter()


@router.get("/", response_model=list[DepartmentResponse])
async def list_departments(user: dict = Depends(get_current_user)):
    """Get all departments."""
    return database_service.get_departments()


@router.post("/", response_model=DepartmentResponse)
async def create_department(data: DepartmentCreate, user: dict = Depends(get_current_user)):
    """Create a new department (admin only)."""
    if user.get("role") != "admin":
        raise HTTPException(403, "Только администратор")
    try:
        d = database_service.create_department(name=data.name, code=data.code, description=data.description)
        return {"id": d.id, "name": d.name, "code": d.code, "description": d.description}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.put("/{dep_id}", response_model=DepartmentResponse)
async def update_department(dep_id: int, data: DepartmentUpdate, user: dict = Depends(get_current_user)):
    """Update an existing department (admin only)."""
    if user.get("role") != "admin":
        raise HTTPException(403, "Только администратор")
    try:
        d = database_service.update_department(dep_id=dep_id, name=data.name, code=data.code, description=data.description)
        if not d:
            raise HTTPException(404, "Отдел не найден")
        return {"id": d.id, "name": d.name, "code": d.code, "description": d.description}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.delete("/{dep_id}")
async def delete_department(dep_id: int, user: dict = Depends(get_current_user)):
    """Delete a department (admin only). Fails if users are assigned."""
    if user.get("role") != "admin":
        raise HTTPException(403, "Только администратор")
    try:
        ok = database_service.delete_department(dep_id)
        if not ok:
            raise HTTPException(404, "Отдел не найден")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))