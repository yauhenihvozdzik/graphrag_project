#!/bin/bash
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiZW1haWwiOiJhZG1pbkBncmFwaHJhZy5sb2NhbCIsInJvbGUiOiJhZG1pbiIsImV4cCI6MTc4NjA5ODY3NCwiaWF0IjoxNzgzNTA2Njc0fQ.ffCh6Ldnt-N6xzwEzeSRhk069m8VLHCaKCwv5QOIN6g"

echo "===== 1. PROFILE ====="
curl -s http://localhost:8000/api/v1/auth/me -H "Authorization: Bearer $TOKEN"
echo ""

echo "===== 2. USERS ====="
curl -s http://localhost:8000/api/v1/auth/users -H "Authorization: Bearer $TOKEN"
echo ""

echo "===== 3. ADMIN SETTINGS ====="
curl -s http://localhost:8000/api/v1/admin/settings -H "Authorization: Bearer $TOKEN"
echo ""

echo "===== 4. CHAT SESSIONS ====="
curl -s http://localhost:8000/api/v1/chat/sessions -H "Authorization: Bearer $TOKEN"
echo ""

echo "===== 5. FILES ====="
curl -s http://localhost:8000/api/v1/ingest/files -H "Authorization: Bearer $TOKEN"
echo ""

echo "===== 6. GRAPH STATUS ====="
curl -s http://localhost:8000/api/v1/graph/status -H "Authorization: Bearer $TOKEN"
echo ""

echo "===== 7. DEPARTMENTS ====="
curl -s http://localhost:8000/api/v1/departments/ -H "Authorization: Bearer $TOKEN"
echo ""

echo "===== 8. TESTS ====="
curl -s http://localhost:8000/api/v1/tests/ -H "Authorization: Bearer $TOKEN"
echo ""

echo "===== DONE ====="
