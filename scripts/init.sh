#!/usr/bin/env bash
# ══════════════════════════════════════════════
# GraphRAG Platform — Initialization Script
# ══════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# ── Default credentials (override via env vars) ─────
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@graphrag.local}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-Admin123!}"

echo "╔══════════════════════════════════════════════╗"
echo "║  GraphRAG Platform — Initialization          ║"
echo "╚══════════════════════════════════════════════╝"

# ── 1. Check prerequisites ───────────────────────────
echo ""
echo "▸ Checking prerequisites..."

for cmd in docker curl python3; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "  ✗ $cmd is not installed. Please install it first."
    exit 1
  fi
  echo "  ✓ $cmd found"
done

# ── 2. Create .env if missing ────────────────────────
if [ ! -f "$PROJECT_DIR/backend/.env" ]; then
  echo ""
  echo "▸ Creating backend/.env from template..."
  cp "$PROJECT_DIR/backend/.env.example" "$PROJECT_DIR/backend/.env" 2>/dev/null || \
    echo "  ⚠ No .env.example found, using existing .env"
fi

# ── 3. Start infrastructure ─────────────────────────
echo ""
echo "▸ Starting infrastructure services..."
cd "$PROJECT_DIR"
docker compose up -d neo4j qdrant postgres ollama jaeger prometheus grafana

echo ""
echo "▸ Waiting for services to be healthy..."
sleep 10

# Wait for Neo4j
echo "  Waiting for Neo4j..."
for i in $(seq 1 30); do
  if docker exec graphrag-neo4j cypher-shell -u neo4j -p neo4j_password "RETURN 1" &>/dev/null; then
    echo "  ✓ Neo4j is ready"
    break
  fi
  sleep 2
done

# Wait for Qdrant
echo "  Waiting for Qdrant..."
for i in $(seq 1 20); do
  if curl -sf http://localhost:6333/healthz &>/dev/null; then
    echo "  ✓ Qdrant is ready"
    break
  fi
  sleep 2
done

# Wait for PostgreSQL
echo "  Waiting for PostgreSQL..."
for i in $(seq 1 20); do
  if docker exec graphrag-postgres pg_isready -U postgres &>/dev/null; then
    echo "  ✓ PostgreSQL is ready"
    break
  fi
  sleep 2
done

# ── 4. Pull Ollama models ───────────────────────────
echo ""
echo "▸ Pulling Ollama models (this may take a while)..."
docker exec graphrag-ollama ollama pull qwen2.5:7b || echo "  ⚠ Failed to pull qwen2.5:7b model"
docker exec graphrag-ollama ollama pull bge-m3 || echo "  ⚠ Failed to pull bge-m3 model"

# ── 5. Initialize Neo4j constraints & indexes ───────
echo ""
echo "▸ Creating Neo4j constraints and indexes..."
docker exec graphrag-neo4j cypher-shell -u neo4j -p neo4j_password \
  "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE;" 2>/dev/null || true
docker exec graphrag-neo4j cypher-shell -u neo4j -p neo4j_password \
  "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE;" 2>/dev/null || true
docker exec graphrag-neo4j cypher-shell -u neo4j -p neo4j_password \
  "CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name);" 2>/dev/null || true
docker exec graphrag-neo4j cypher-shell -u neo4j -p neo4j_password \
  "CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.entity_type);" 2>/dev/null || true
docker exec graphrag-neo4j cypher-shell -u neo4j -p neo4j_password \
  "CREATE INDEX chunk_clearance IF NOT EXISTS FOR (c:Chunk) ON (c.clearance_level);" 2>/dev/null || true
echo "  ✓ Neo4j indexes created"

# ── 6. Start application services ───────────────────
echo ""
echo "▸ Starting application services..."
cd "$PROJECT_DIR"
docker compose up -d backend frontend

echo ""
echo "▸ Waiting for backend to be healthy..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/api/v1/health &>/dev/null; then
    echo "  ✓ Backend is ready"
    break
  fi
  echo "  Waiting for backend... ($i/30)"
  sleep 3
done

# ── 7. Seed departments (via standalone script) ─────
echo ""
echo "▸ Seeding departments..."
cd "$SCRIPT_DIR"
python3 seed_departments.py || echo "  ⚠ Department seeding failed"

# ── 8. Seed users (via standalone script) ───────────
echo ""
echo "▸ Seeding demo users..."
cd "$SCRIPT_DIR"
python3 seed_users.py || echo "  ⚠ User seeding failed"

# ── 9. Load demo datasets ───────────────────────────
echo ""
echo "▸ Loading demo datasets..."
cd "$SCRIPT_DIR"
python3 load_datasets.py || echo "  ⚠ Dataset loading failed"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  ✓ GraphRAG Platform is ready!               ║"
echo "╠══════════════════════════════════════════════╣"
echo "║  Frontend:    http://localhost:3000           ║"
echo "║  Backend API: http://localhost:8000/docs      ║"
echo "║  Neo4j:       http://localhost:7474           ║"
echo "║  Grafana:     http://localhost:3001           ║"
echo "║  Jaeger:      http://localhost:16686          ║"
echo "║  Prometheus:  http://localhost:9090           ║"
echo "╚══════════════════════════════════════════════╝"
