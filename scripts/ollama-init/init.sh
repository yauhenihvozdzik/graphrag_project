#!/bin/sh
set -e

# Pull required Ollama models via HTTP API
# Usage: run this script on a host that has network access to the Ollama server
# Default OLLAMA_HOST if not set in environment
OLLAMA_HOST="${OLLAMA_HOST:-localhost:11434}"

echo "=== Waiting for Ollama API at ${OLLAMA_HOST} ==="
for i in $(seq 1 30); do
  curl -sf "http://${OLLAMA_HOST}/api/tags" > /dev/null 2>&1 && break
  echo "  Attempt ${i}/30..."
  sleep 5
done

echo "=== Pulling bge-m3 (embedding model) ==="
curl -sf -X POST "http://${OLLAMA_HOST}/api/pull" -d '{"name":"bge-m3","stream":false}'

echo "=== Pulling qwen2.5:7b (LLM model) ==="
curl -sf -X POST "http://${OLLAMA_HOST}/api/pull" -d '{"name":"qwen2.5:7b","stream":false}'

echo "=== All models pulled successfully ==="
