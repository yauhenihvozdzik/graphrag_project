#!/bin/sh
# Pull required Ollama models on startup
echo "=== Pulling bge-m3 (embedding model) ==="
ollama pull bge-m3
echo "=== Pulling qwen2.5:7b (LLM model) ==="
ollama pull qwen2.5:7b
echo "=== Models pulled successfully ==="