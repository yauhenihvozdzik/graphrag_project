@echo off
chcp 65001 >nul
echo.
echo ===== 1. PROFILE =====
for /f "tokens=2 delims=:," %%a in ('curl.exe -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d "@d:\Work\graphrag_project\login.json"') do (
    set "token=%%a"
    goto :got_token
)
:got_token
set token=%token:"=%
set token=%token: =%
echo Token obtained: %token:~0,30%...
echo.

echo ===== 2. GET PROFILE =====
curl.exe -s http://localhost:8000/api/v1/auth/me -H "Authorization: Bearer %token%"
echo.

echo ===== 3. LIST USERS =====
curl.exe -s http://localhost:8000/api/v1/auth/users -H "Authorization: Bearer %token%"
echo.

echo ===== 4. ADMIN SETTINGS =====
curl.exe -s http://localhost:8000/api/v1/admin/settings -H "Authorization: Bearer %token%"
echo.

echo ===== 5. CHAT SESSIONS =====
curl.exe -s http://localhost:8000/api/v1/chat/sessions -H "Authorization: Bearer %token%"
echo.

echo ===== 6. FILES =====
curl.exe -s http://localhost:8000/api/v1/ingest/files -H "Authorization: Bearer %token%"
echo.

echo ===== 7. GRAPH STATUS =====
curl.exe -s http://localhost:8000/api/v1/graph/status -H "Authorization: Bearer %token%"
echo.

echo ===== 8. DEPARTMENTS =====
curl.exe -s http://localhost:8000/api/v1/departments/ -H "Authorization: Bearer %token%"
echo.

echo ===== 9. TESTS =====
curl.exe -s http://localhost:8000/api/v1/tests/ -H "Authorization: Bearer %token%"
echo.

echo.
echo ===== ALL DONE =====
pause
