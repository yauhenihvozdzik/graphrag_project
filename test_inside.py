#!/usr/bin/env python3
"""Comprehensive API test script for GraphRAG Platform."""
import json
import urllib.request
import urllib.error
import time

BASE = "http://backend:8000/api/v1"

def req(method, path, data=None, token=None):
    url = f"{BASE}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode() if data else None
    try:
        r = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except:
            return e.code, {"error": str(e)}
    except Exception as e:
        return 0, {"error": str(e)}

def test(name, method, path, data=None, token=None):
    time.sleep(0.3)  # avoid rate limit
    status, data = req(method, path, data, token)
    status_str = "\u2713" if status in (200, 201) else "\u2717"
    detail = json.dumps(data, ensure_ascii=False, indent=2)[:300]
    print(f"  {status_str} [{status}] {name}: {detail}")
    return status, data

print("=" * 60)
print("GraphRAG Platform - E2E API Tests")
print("=" * 60)

# 1. Health
print("\n1. HEALTH CHECK")
test("Health", "GET", "/health")

# 2. Login
print("\n2. AUTHENTICATION")
s, login_data = test("Login admin", "POST", "/auth/login",
    {"email": "admin@graphrag.local", "password": "Admin123!"})
TOKEN = login_data.get("access_token", "")
if not TOKEN:
    print("  FAILED: No token obtained")
    exit(1)

# 3. Profile
print("\n3. USER PROFILE")
test("My profile", "GET", "/auth/me", token=TOKEN)

# 4. Users (admin only)
print("\n4. ADMIN: LIST USERS")
test("List users", "GET", "/auth/users", token=TOKEN)

# 5. Admin settings
print("\n5. ADMIN SETTINGS")
test("Settings list", "GET", "/admin/settings", token=TOKEN)

# 6. Chat - try chat endpoint (POST)
print("\n6. CHAT ENDPOINTS")
test("Create session (via auth)", "POST", "/auth/sessions", token=TOKEN)
test("List sessions (via auth)", "GET", "/auth/sessions", token=TOKEN)

# 7. Ingest
print("\n7. INGEST / DOCUMENTS")
test("Graph documents list", "GET", "/graph/documents", token=TOKEN)

# 8. Graph
print("\n8. GRAPH")
test("Graph stats", "GET", "/graph/stats", token=TOKEN)
test("Graph visualize", "GET", "/graph/visualize", token=TOKEN)

# 9. Departments
print("\n9. DEPARTMENTS")
test("Departments list", "GET", "/departments/", token=TOKEN)

# 10. Tests
print("\n10. TESTS")
test("Tests run (POST - no auth)", "POST", "/tests/run", token=TOKEN)

# 11. Admin debug
print("\n11. ADMIN DEBUG")
test("Settings categories", "GET", "/admin/settings/history", token=TOKEN)

# 12. RBAC: Analyst access
print("\n12. RBAC TESTS")
s, analyst_login = test("Login analyst", "POST", "/auth/login",
    {"email": "analyst@graphrag.local", "password": "Analyst123!"})
ANALYST_TOKEN = analyst_login.get("access_token", "")
if ANALYST_TOKEN:
    test("Analyst -> /auth/users (should be 403)", "GET", "/auth/users", token=ANALYST_TOKEN)

# 13. Login as viewer
test("Login viewer", "POST", "/auth/login",
    {"email": "viewer@graphrag.local", "password": "Viewer123!"})

# 14. Health check after operations
print("\n14. FINAL HEALTH CHECK")
test("Health", "GET", "/health")

print("\n" + "=" * 60)
print("ALL TESTS COMPLETE")
print("=" * 60)
