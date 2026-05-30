"""Seed initial departments into PostgreSQL database."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.services.database import database_service
from app.core.logging import logger

DEFAULT_DEPARTMENTS = [
    {"name": "Все", "code": "all", "description": "Все отделы (доступ без ограничений)"},
    {"name": "Юридический", "code": "legal", "description": "Юридический отдел"},
    {"name": "Исследования", "code": "research", "description": "Отдел исследований и аналитики"},
    {"name": "Управление", "code": "management", "description": "Руководство и управление"},
    {"name": "Комплаенс", "code": "compliance", "description": "Отдел комплаенс и внутреннего контроля"},
    {"name": "HR", "code": "hr", "description": "Отдел кадров"},
    {"name": "Финансы", "code": "finance", "description": "Финансовый отдел"},
    {"name": "IT", "code": "it", "description": "Информационные технологии"},
]

if __name__ == "__main__":
    existing = database_service.get_departments()
    existing_codes = {d["code"] for d in existing}
    created = 0
    for dep in DEFAULT_DEPARTMENTS:
        if dep["code"] not in existing_codes:
            try:
                database_service.create_department(name=dep["name"], code=dep["code"], description=dep["description"])
                created += 1
                print(f"  ✅ {dep['name']} ({dep['code']})")
            except Exception as e:
                print(f"  ⚠️ {dep['name']}: {e}")
    if created:
        print(f"\nСоздано отделов: {created}")
    else:
        print("\nВсе отделы уже существуют.")