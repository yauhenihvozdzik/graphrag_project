#!/usr/bin/env python3
"""Debug DB issues directly - detailed."""
import sys
sys.path.insert(0, '/app')

from app.services.database import database_service

# Test basic session
print("=== Test basic session ===")
from sqlmodel import Session as SQLModelSession, select
from app.models.user import User
from app.models.department import Department

try:
    with SQLModelSession(database_service.sync_engine) as s:
        print("Session created OK")
        # Simple query
        users = s.exec(select(User)).all()
        print(f"Users count: {len(list(users))}")
except Exception as e:
    import traceback
    print(f"ERROR: {type(e).__name__}: {e}")
    traceback.print_exc()

print("\n=== Test departments ===")
try:
    with SQLModelSession(database_service.sync_engine) as s:
        deps = s.exec(select(Department).order_by(Department.name)).all()
        for d in deps:
            print(f"  Dept: {d.name} ({d.code})")
except Exception as e:
    import traceback
    print(f"ERROR: {type(e).__name__}: {e}")
    traceback.print_exc()

print("\n=== Test users paginated ===")
try:
    with SQLModelSession(database_service.sync_engine) as s:
        from sqlalchemy import func
        q = select(User)
        total_q = select(func.count()).select_from(q.subquery())
        print(f"Query: {total_q}")
        total = s.exec(total_q).one()
        print(f"Total: {total}")
except Exception as e:
    import traceback
    print(f"ERROR: {type(e).__name__}: {e}")
    traceback.print_exc()
