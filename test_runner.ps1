# GraphRAG Platform — End-to-End Test Script
Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  GraphRAG Platform — E2E Test Suite          ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── 1. Health Check ──
Write-Host "▸ 1. Health Check" -ForegroundColor Yellow
$health = curl.exe -s http://localhost:8000/api/v1/health 2>&1
Write-Host "  $health"
Write-Host ""

# ── 2. Login as Admin ──
Write-Host "▸ 2. Login as Admin" -ForegroundColor Yellow
$loginResp = curl.exe -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d "@d:\Work\graphrag_project\login.json" 2>&1
$token = ($loginResp | ConvertFrom-Json).access_token
if ($token) {
    Write-Host "  ✓ Token obtained: $($token.Substring(0, 30))..." -ForegroundColor Green
} else {
    Write-Host "  ✗ Login failed: $loginResp" -ForegroundColor Red
    exit 1
}
Write-Host ""

# ── 3. Get My Profile ──
Write-Host "▸ 3. My Profile (GET /auth/me)" -ForegroundColor Yellow
$profile = curl.exe -s http://localhost:8000/api/v1/auth/me -H "Authorization: Bearer $token" 2>&1
Write-Host "  $profile"
Write-Host ""

# ── 4. List Users (admin only) ──
Write-Host "▸ 4. List Users (GET /auth/users)" -ForegroundColor Yellow
$users = curl.exe -s http://localhost:8000/api/v1/auth/users -H "Authorization: Bearer $token" 2>&1
Write-Host "  $users"
Write-Host ""

# ── 5. Admin Settings ──
Write-Host "▸ 5. Admin Settings (GET /admin/settings)" -ForegroundColor Yellow
$settings = curl.exe -s http://localhost:8000/api/v1/admin/settings -H "Authorization: Bearer $token" 2>&1
Write-Host "  $settings"
Write-Host ""

# ── 6. Chat Sessions ──
Write-Host "▸ 6. Chat Sessions (GET /chat/sessions)" -ForegroundColor Yellow
$sessions = curl.exe -s http://localhost:8000/api/v1/chat/sessions -H "Authorization: Bearer $token" 2>&1
Write-Host "  $sessions"
Write-Host ""

# ── 7. Documents / Files ──
Write-Host "▸ 7. Files (GET /ingest/files)" -ForegroundColor Yellow
$files = curl.exe -s http://localhost:8000/api/v1/ingest/files -H "Authorization: Bearer $token" 2>&1
Write-Host "  $files"
Write-Host ""

# ── 8. Graph Status ──
Write-Host "▸ 8. Graph Status (GET /graph/status)" -ForegroundColor Yellow
$graph = curl.exe -s http://localhost:8000/api/v1/graph/status -H "Authorization: Bearer $token" 2>&1
Write-Host "  $graph"
Write-Host ""

# ── 9. Departments ──
Write-Host "▸ 9. Departments (GET /departments/)" -ForegroundColor Yellow
$depts = curl.exe -s http://localhost:8000/api/v1/departments/ -H "Authorization: Bearer $token" 2>&1
Write-Host "  $depts"
Write-Host ""

# ── 10. Tests ──
Write-Host "▸ 10. Tests (GET /tests/)" -ForegroundColor Yellow
$tests = curl.exe -s http://localhost:8000/api/v1/tests/ -H "Authorization: Bearer $token" 2>&1
Write-Host "  $tests"
Write-Host ""

# ── 11. Login as Analyst ──
Write-Host "▸ 11. Login as Analyst" -ForegroundColor Yellow
$analystLogin = curl.exe -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"email":"analyst@graphrag.local","password":"Analyst123!"}' 2>&1
$analystToken = ($analystLogin | ConvertFrom-Json).access_token
if ($analystToken) {
    Write-Host "  ✓ Analyst token obtained" -ForegroundColor Green
} else {
    Write-Host "  ✗ Analyst login failed: $analystLogin" -ForegroundColor Red
}
Write-Host ""

# ── 12. RBAC test: analyst tries admin endpoint ──
Write-Host "▸ 12. RBAC test: Analyst tries admin endpoint" -ForegroundColor Yellow
if ($analystToken) {
    $rbacTest = curl.exe -s http://localhost:8000/api/v1/auth/users -H "Authorization: Bearer $analystToken" 2>&1
    Write-Host "  Analyst accessing /auth/users: $rbacTest"
} else {
    Write-Host "  Skipped (no token)" -ForegroundColor Gray
}
Write-Host ""

# ── 13. Login as Viewer ──
Write-Host "▸ 13. Login as Viewer" -ForegroundColor Yellow
$viewerLogin = curl.exe -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"email":"viewer@graphrag.local","password":"Viewer123!"}' 2>&1
$viewerToken = ($viewerLogin | ConvertFrom-Json).access_token
if ($viewerToken) {
    Write-Host "  ✓ Viewer token obtained" -ForegroundColor Green
} else {
    Write-Host "  ✗ Viewer login failed: $viewerLogin" -ForegroundColor Red
}
Write-Host ""

Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  Testing Complete!                           ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Cyan
