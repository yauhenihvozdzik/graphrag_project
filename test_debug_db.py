#!/usr/bin/env python3
"""Debug DB issues directly."""
import sys
sys.path.insert(0, '/app')

from app.services.database import database_service

# Test 1: get_users_paginated
print("=== Testing get_users_paginated ===")
try:
    result = database_service.get_users_paginated()
    print(f"OK: {result}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")

# Test 2: get_departments
print("\n=== Testing get_departments ===")
try:
    result = database_service.get_departments()
    print(f"OK: {result}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")

# Test 3: create session via session_service
print("\n=== Testing SessionService.create_session ===")
from app.services.session_service import SessionService
import asyncio

async def test_session():
    async with database_service.async_session() as session:
        ss = SessionService(session)
        try:
            s = await ss.create_session(user_id=1, title="New Chat")
            print(f"OK: session id={s.id}, name={s.name}")
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")

asyncio.run(test_session())
