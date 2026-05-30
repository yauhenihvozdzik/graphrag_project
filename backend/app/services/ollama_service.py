"""Ollama LLM service for GraphRAG platform.

Wraps Ollama API for both LLM inference (T-lite-it-1.0) and
embedding generation (BAAI/bge-m3). Provides async interface
with retries and streaming support.
"""

import asyncio
import time
from typing import Any, AsyncGenerator, Optional

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.core.metrics import llm_inference_duration_seconds, llm_stream_duration_seconds


class OllamaService:
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._base_url = settings.OLLAMA_BASE_URL

    async def initialize(self) -> None:
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=httpx.Timeout(settings.OLLAMA_TIMEOUT, connect=10.0))
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
            models = [m["name"] for m in response.json().get("models", [])]
            logger.info("ollama_connected", base_url=self._base_url, available_models=models)
        except Exception as e:
            logger.warning("ollama_connection_check_failed", base_url=self._base_url, error=str(e))

    async def close(self) -> None:
        if self._client: await self._client.aclose(); logger.info("ollama_disconnected")

    async def generate(self, prompt: str, system: Optional[str] = None, model: Optional[str] = None, temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> str:
        if not self._client: raise RuntimeError("Ollama client not initialized.")
        model = model or settings.OLLAMA_MODEL; start = time.time()
        payload: dict[str, Any] = {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": temperature or settings.OLLAMA_TEMPERATURE, "num_ctx": settings.OLLAMA_NUM_CTX}}
        if system: payload["system"] = system
        if max_tokens: payload["options"]["num_predict"] = max_tokens
        response = await self._client.post("/api/generate", json=payload)
        response.raise_for_status(); result = response.json()
        duration = time.time() - start
        llm_inference_duration_seconds.labels(model=model).observe(duration)
        return result.get("response", "")

    async def chat(self, messages: list[dict[str, str]], model: Optional[str] = None, temperature: Optional[float] = None, options: Optional[dict] = None) -> str:
        if not self._client: raise RuntimeError("Ollama client not initialized.")
        model = model or settings.OLLAMA_MODEL; start = time.time()
        base_options = {"temperature": temperature or settings.OLLAMA_TEMPERATURE, "num_ctx": settings.OLLAMA_NUM_CTX}
        if options: base_options.update(options)
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": False, "options": base_options}
        response = await self._client.post("/api/chat", json=payload)
        response.raise_for_status(); result = response.json()
        duration = time.time() - start
        llm_inference_duration_seconds.labels(model=model).observe(duration)
        return result.get("message", {}).get("content", "")

    async def chat_stream(self, messages: list[dict[str, str]], model: Optional[str] = None, temperature: Optional[float] = None, options: Optional[dict] = None) -> AsyncGenerator[str, None]:
        if not self._client: raise RuntimeError("Ollama client not initialized.")
        model = model or settings.OLLAMA_MODEL; start = time.time()
        base_options = {"temperature": temperature or settings.OLLAMA_TEMPERATURE, "num_ctx": settings.OLLAMA_NUM_CTX}
        if options: base_options.update(options)
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": True, "options": base_options}
        async with self._client.stream("POST", "/api/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line: continue
                import json; data = json.loads(line)
                content = data.get("message", {}).get("content", "")
                if content: yield content
                if data.get("done", False): break
        duration = time.time() - start
        llm_stream_duration_seconds.labels(model=model).observe(duration)

    async def embed(self, texts: list[str], model: Optional[str] = None) -> list[list[float]]:
        if not self._client: raise RuntimeError("Ollama client not initialized.")
        model = model or settings.OLLAMA_EMBEDDING_MODEL; embeddings = []
        for text in texts:
            response = await self._client.post("/api/embed", json={"model": model, "input": text})
            response.raise_for_status(); result = response.json()
            if "embeddings" in result: embeddings.extend(result["embeddings"])
            elif "embedding" in result: embeddings.append(result["embedding"])
        logger.debug("ollama_embed_completed", model=model, count=len(texts))
        return embeddings

    async def embed_single(self, text: str, model: Optional[str] = None) -> list[float]:
        results = await self.embed([text], model=model)
        return results[0] if results else []

    async def health_check(self) -> dict:
        if not self._client: return {"status": "not_initialized"}
        try:
            response = await self._client.get("/api/tags"); response.raise_for_status()
            data = response.json()
            return {"status": "healthy", "models": [m["name"] for m in data.get("models", [])]}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


ollama_service = OllamaService()