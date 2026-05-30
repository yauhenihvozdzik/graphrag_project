"""Chat API endpoints with streaming support."""

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.v1.auth import get_access_context, get_current_user
from app.core.config import settings
from app.core.langgraph.agent import graphrag_agent
from app.core.logging import logger
from app.core.security.guardrails import guardrails_service
from app.core.security.rbac import AccessContext
from app.models.schemas import ChatRequest, ChatResponse, Message
from app.services.database import database_service

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: Request, chat_request: ChatRequest,
    current_user: dict = Depends(get_current_user),
    access_context: AccessContext = Depends(get_access_context),
):
    try:
        logger.info("chat_request_received", user_id=current_user["user_id"], message_count=len(chat_request.messages))
        last_msg = chat_request.messages[-1]
        guard_result = guardrails_service.check_input(last_msg.content)
        if not guard_result.is_safe:
            return ChatResponse(messages=[Message(role="assistant", content=f"⚠️ Запрос отклонён: {guard_result.blocked_reason}")], sources=[])

        try:
            database_service.save_message(user_id=current_user["user_id"], role="user", content=last_msg.content)
        except Exception as e:
            logger.warning("save_user_message_failed", error=str(e))

        messages = [{"role": m.role, "content": m.content} for m in chat_request.messages]
        messages[-1]["content"] = guard_result.sanitized_text

        access_ctx = {"user_id": str(current_user["user_id"]), "role": current_user.get("role", "viewer"),
                       "department": current_user.get("department", "all"), "clearance_level": current_user.get("clearance_level", 0)}

        result = await graphrag_agent.get_response(
            messages=messages, session_id=chat_request.session_id or f"default_{current_user['user_id']}", access_context=access_ctx)

        response_text = result.get("response", "")
        sources = result.get("sources", [])

        try:
            database_service.save_message(
                user_id=current_user["user_id"], role="assistant", content=response_text,
                sources=json.dumps(sources, ensure_ascii=False) if sources else None,
            )
        except Exception as e:
            logger.warning("save_assistant_message_failed", error=str(e))

        logger.info("chat_request_processed", user_id=current_user["user_id"], sources_count=len(sources))
        return ChatResponse(messages=[Message(role="assistant", content=response_text)], sources=sources)
    except Exception as e:
        logger.exception("chat_request_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Ошибка обработки запроса")


@router.post("/chat/stream")
async def chat_stream(
    request: Request, chat_request: ChatRequest,
    current_user: dict = Depends(get_current_user),
    access_context: AccessContext = Depends(get_access_context),
):
    last_msg = chat_request.messages[-1]
    guard_result = guardrails_service.check_input(last_msg.content)
    if not guard_result.is_safe:
        async def err(): yield f"data: {json.dumps({'event':'error','data':guard_result.blocked_reason})}\n\n"; yield "data: [DONE]\n\n"
        return StreamingResponse(err(), media_type="text/event-stream")

    try: database_service.save_message(user_id=current_user["user_id"], role="user", content=last_msg.content)
    except Exception: pass

    messages = [{"role": m.role, "content": m.content} for m in chat_request.messages]
    messages[-1]["content"] = guard_result.sanitized_text
    access_ctx = {"user_id": str(current_user["user_id"]), "role": current_user.get("role","viewer"),
                   "department": current_user.get("department","all"), "clearance_level": current_user.get("clearance_level",0)}

    async def event_generator():
        full_response = ""
        try:
            async for chunk in graphrag_agent.get_streaming_response(messages=messages, session_id=chat_request.session_id or f"default_{current_user['user_id']}", access_context=access_ctx):
                full_response += chunk
                yield f"data: {json.dumps({'event':'token','data':chunk}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            try: database_service.save_message(user_id=current_user["user_id"], role="assistant", content=full_response)
            except Exception: pass
        except Exception as e:
            logger.exception("chat_stream_failed", error=str(e))
            yield f"data: {json.dumps({'event':'error','data':str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream",
        headers={"Cache-Control":"no-cache","Connection":"keep-alive","X-Accel-Buffering":"no"})


@router.get("/chat/history")
async def get_chat_history(current_user: dict = Depends(get_current_user), limit: int = 100):
    try:
        messages = database_service.get_chat_history(user_id=current_user["user_id"], limit=limit)
        return {"success": True, "messages": [
            {"id": m.id, "role": m.role, "content": m.content, "sources": json.loads(m.sources) if m.sources else None,
             "created_at": m.created_at.isoformat() if m.created_at else None}
            for m in messages
        ]}
    except Exception as e:
        logger.exception("get_chat_history_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Ошибка получения истории")


@router.delete("/chat/history")
async def clear_chat_history(current_user: dict = Depends(get_current_user)):
    try:
        count = database_service.clear_chat_history(user_id=current_user["user_id"])
        return {"success": True, "deleted": count}
    except Exception as e:
        logger.exception("clear_chat_history_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Ошибка очистки истории")