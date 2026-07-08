Write-Host "=== 1. Health Check ==="
$health = curl.exe -s http://localhost:8000/api/v1/health 2>&1
Write-Host $health
Write-Host ""

Write-Host "=== 2. Login as Admin ==="
$loginResp = curl.exe -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d "@d:\Work\graphrag_project\login.json" 2>&1
Write-Host $loginResp
Write-Host ""

Write-Host "=== 3. Get My Profile ==="
$loginObj = $loginResp | ConvertFrom-Json
$token = $loginObj.access_token
$profile = curl.exe -s http://localhost:8000/api/v1/auth/me -H "Authorization: Bearer $token" 2>&1
Write-Host $profile
Write-Host ""

Write-Host "=== 4. List Users ==="
$users = curl.exe -s http://localhost:8000/api/v1/auth/users -H "Authorization: Bearer $token" 2>&1
Write-Host $users
Write-Host ""

Write-Host "=== 5. Admin Settings ==="
$settings = curl.exe -s http://localhost:8000/api/v1/admin/settings -H "Authorization: Bearer $token" 2>&1
Write-Host $settings
Write-Host ""

Write-Host "=== 6. Chat Sessions ==="
$sessions = curl.exe -s http://localhost:8000/api/v1/chat/sessions -H "Authorization: Bearer $token" 2>&1
Write-Host $sessions
Write-Host ""

Write-Host "=== 7. Files ==="
$files = curl.exe -s http://localhost:8000/api/v1/ingest/files -H "Authorization: Bearer $token" 2>&1
Write-Host $files
Write-Host ""

Write-Host "=== 8. Graph Status ==="
$graph = curl.exe -s http://localhost:8000/api/v1/graph/status -H "Authorization: Bearer $token" 2>&1
Write-Host $graph
Write-Host ""

Write-Host "=== 9. Departments ==="
$depts = curl.exe -s http://localhost:8000/api/v1/departments/ -H "Authorization: Bearer $token" 2>&1
Write-Host $depts
Write-Host ""

Write-Host "=== 10. Tests ==="
$tests = curl.exe -s http://localhost:8000/api/v1/tests/ -H "Authorization: Bearer $token" 2>&1
Write-Host $tests
Write-Host ""

Write-Host "=== 11. RBAC: Analyst accessing admin endpoint ==="
$analystLogin = curl.exe -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"email":"analyst@graphrag.local","password":"Analyst123!"}' 2>&1
Write-Host $analystLogin
$analystObj = $analystLogin | ConvertFrom-Json
if ($analystObj.access_token) {
    $rbacTest = curl.exe -s http://localhost:8000/api/v1/auth/users -H "Authorization: Bearer $analystObj.access_token" 2>&1
    Write-Host $rbacTest
}
Write-Host ""

Write-Host "=== 12. Login as Viewer ==="
$viewerLogin = curl.exe -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"email":"viewer@graphrag.local","password":"Viewer123!"}' 2>&1
Write-Host $viewerLogin
Write-Host ""

Write-Host "=== ALL TESTS COMPLETE ==="
