"""Test runner API — стриминговый запуск pytest через SSE."""

import asyncio
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.logging import logger

router = APIRouter()

# Paths inside Docker container: /app = backend, /app/tests = tests
BACKEND_DIR = Path("/app")
TESTS_DIR = Path("/app/tests")


async def _verify_admin(request: Request) -> dict:
    """Verify JWT token and check admin role without DB lookup."""
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    from app.utils.auth import verify_token

    security = HTTPBearer()
    credentials: HTTPAuthorizationCredentials = await security(request)
    token = credentials.credentials
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(401, "Недействительный токен")
    if payload.get("role") != "admin":
        raise HTTPException(403, "Требуется роль администратора")
    return payload


@router.post("/run")
async def run_tests_stream(request: Request):
    """Запускает pytest и стримит результат через Server-Sent Events (admin only)."""
    payload = await _verify_admin(request)
    logger.info("tests_run_requested", user_id=payload.get("sub", "unknown"))

    async def event_stream():
        import json
        import re

        yield f"data: {json.dumps({'event': 'status', 'data': '⏳ Запуск pytest...'}, ensure_ascii=False)}\n\n"

        try:
            env = {**__import__("os").environ, "PYTHONPATH": str(BACKEND_DIR)}
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pytest",
                str(TESTS_DIR),
                "-v",
                "--tb=short",
                "--color=no",
                "--timeout=30",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(BACKEND_DIR),
                env=env,
            )

            passed = 0
            failed = 0
            errors = 0
            full_output = ""

            assert proc.stdout is not None
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace")
                full_output += text
                # Stream each line immediately
                yield f"data: {json.dumps({'event': 'line', 'data': text.rstrip()}, ensure_ascii=False)}\n\n"

            await proc.wait()

            # Parse summary
            for summary_line in full_output.split("\n"):
                if "passed" in summary_line and "=" in summary_line:
                    m = re.search(r"(\d+)\s+passed", summary_line)
                    if m:
                        passed = int(m.group(1))
                    m = re.search(r"(\d+)\s+failed", summary_line)
                    if m:
                        failed = int(m.group(1))
                    m = re.search(r"(\d+)\s+errors?", summary_line)
                    if m:
                        errors = int(m.group(1))

            total = passed + failed + errors
            success = proc.returncode == 0 and failed == 0 and errors == 0

            summary = {
                "event": "done",
                "data": {
                    "success": success,
                    "passed": passed,
                    "failed": failed,
                    "errors": errors,
                    "total": total,
                    "exit_code": proc.returncode,
                },
            }
            yield f"data: {json.dumps(summary, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

            logger.info(
                "tests_run_completed",
                passed=passed,
                failed=failed,
                errors=errors,
                exit_code=proc.returncode,
            )

        except Exception as e:
            logger.exception("tests_run_failed", error=str(e))
            yield f"data: {json.dumps({'event': 'error', 'data': str(e)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )