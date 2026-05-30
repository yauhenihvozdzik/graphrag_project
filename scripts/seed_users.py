#!/usr/bin/env python3
"""
GraphRAG Platform — Seed Demo Users
Creates demo users with different RBAC roles for testing.
"""

import json
import sys
import time

import requests

API_BASE = "http://localhost:8000/api/v1"

DEMO_USERS = [
    {
        "email": "admin@graphrag.local",
        "password": "Admin123!",
        "full_name": "Администратор",
        "role": "admin",
        "department": "management",
        "clearance_level": "top_secret",
    },
    {
        "email": "analyst@graphrag.local",
        "password": "Analyst123!",
        "full_name": "Аналитик Иванов",
        "role": "analyst",
        "department": "legal",
        "clearance_level": "secret",
    },
    {
        "email": "viewer@graphrag.local",
        "password": "Viewer123!",
        "full_name": "Пользователь Петров",
        "role": "viewer",
        "department": "research",
        "clearance_level": "confidential",
    },
    {
        "email": "legal@graphrag.local",
        "password": "Legal123!",
        "full_name": "Юрист Сидорова",
        "role": "analyst",
        "department": "legal",
        "clearance_level": "secret",
    },
]


def wait_for_backend(max_retries: int = 30, delay: float = 2.0) -> bool:
    """Wait for backend to become available."""
    for i in range(max_retries):
        try:
            r = requests.get(f"{API_BASE}/health", timeout=5)
            if r.status_code == 200:
                return True
        except requests.ConnectionError:
            pass
        print(f"  Waiting for backend... ({i + 1}/{max_retries})")
        time.sleep(delay)
    return False


def seed_users():
    """Register demo users via API."""
    print("▸ Seeding demo users...")

    if not wait_for_backend():
        print("  ✗ Backend is not available. Start it first.")
        sys.exit(1)

    results = []
    for user in DEMO_USERS:
        try:
            resp = requests.post(
                f"{API_BASE}/auth/register",
                json=user,
                timeout=10,
            )
            if resp.status_code in (200, 201):
                print(f"  ✓ Created: {user['email']} (role={user['role']})")
                results.append({"email": user["email"], "status": "created"})
            elif resp.status_code == 409:
                print(f"  ○ Exists:  {user['email']}")
                results.append({"email": user["email"], "status": "exists"})
            else:
                print(f"  ✗ Failed:  {user['email']} — {resp.status_code}: {resp.text}")
                results.append({"email": user["email"], "status": "error", "detail": resp.text})
        except Exception as e:
            print(f"  ✗ Error:   {user['email']} — {e}")
            results.append({"email": user["email"], "status": "error", "detail": str(e)})

    print(f"\n  Summary: {len([r for r in results if r['status'] in ('created', 'exists')])} / {len(DEMO_USERS)} users ready")
    return results


if __name__ == "__main__":
    seed_users()
