"""Application configuration management for GraphRAG platform."""

import os
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv


class Environment(str, Enum):
    DEVELOPMENT = "development"; STAGING = "staging"; PRODUCTION = "production"; TEST = "test"


def get_environment() -> Environment:
    match os.getenv("APP_ENV", "development").lower():
        case "production" | "prod": return Environment.PRODUCTION
        case "staging" | "stage": return Environment.STAGING
        case "test": return Environment.TEST
        case _: return Environment.DEVELOPMENT


def load_env_file():
    env = get_environment()
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    for f in [f".env.{env.value}.local", f".env.{env.value}", ".env.local", ".env"]:
        p = os.path.join(base_dir, f)
        if os.path.isfile(p): load_dotenv(dotenv_path=p); return p
    return None

ENV_FILE = load_env_file()

def parse_list_from_env(env_key: str, default=None) -> list[str]:
    value = os.getenv(env_key)
    if not value: return default or []
    value = value.strip("\"'")
    return [item.strip() for item in value.split(",") if item.strip()] if "," in value else [value]


class Settings:
    def __init__(self):
        self.ENVIRONMENT = get_environment()
        self.PROJECT_NAME = os.getenv("PROJECT_NAME", "GraphRAG Platform"); self.VERSION = os.getenv("VERSION", "1.0.0")
        self.DESCRIPTION = os.getenv("DESCRIPTION", "Защищённая платформа GraphRAG для корпоративных знаний")
        self.API_V1_STR = os.getenv("API_V1_STR", "/api/v1"); self.DEBUG = os.getenv("DEBUG", "false").lower() in ("true","1","yes")
        self.ALLOWED_ORIGINS = parse_list_from_env("ALLOWED_ORIGINS", ["*"])
        self.JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me"); self.JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
        self.JWT_ACCESS_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_DAYS", "30"))
        self.OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"); self.OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
        self.OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "bge-m3"); self.OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT","120"))
        self.OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE","0.1")); self.OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX","4096")); self.MAX_TOKENS = int(os.getenv("MAX_TOKENS","2048"))
        self.NEO4J_URI = os.getenv("NEO4J_URI","bolt://localhost:7687"); self.NEO4J_USER = os.getenv("NEO4J_USER","neo4j"); self.NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD","neo4j_password")
        self.NEO4J_DATABASE = os.getenv("NEO4J_DATABASE","neo4j"); self.NEO4J_MAX_CONNECTION_POOL_SIZE = int(os.getenv("NEO4J_MAX_CONNECTION_POOL_SIZE","50"))
        self.QDRANT_HOST = os.getenv("QDRANT_HOST","localhost"); self.QDRANT_PORT = int(os.getenv("QDRANT_PORT","6333")); self.QDRANT_GRPC_PORT = int(os.getenv("QDRANT_GRPC_PORT","6334"))
        self.QDRANT_API_KEY = os.getenv("QDRANT_API_KEY",""); self.QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION","graphrag_documents"); self.QDRANT_VECTOR_SIZE = int(os.getenv("QDRANT_VECTOR_SIZE","1024"))
        self.POSTGRES_HOST = os.getenv("POSTGRES_HOST","localhost"); self.POSTGRES_PORT = int(os.getenv("POSTGRES_PORT","5432")); self.POSTGRES_DB = os.getenv("POSTGRES_DB","graphrag_db")
        self.POSTGRES_USER = os.getenv("POSTGRES_USER","postgres"); self.POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD","postgres")
        self.POSTGRES_POOL_SIZE = int(os.getenv("POSTGRES_POOL_SIZE","20")); self.POSTGRES_MAX_OVERFLOW = int(os.getenv("POSTGRES_MAX_OVERFLOW","10"))
        self.LOG_DIR = Path(os.getenv("LOG_DIR","logs")); self.LOG_LEVEL = os.getenv("LOG_LEVEL","INFO"); self.LOG_FORMAT = os.getenv("LOG_FORMAT","json")
        self.OTEL_ENABLED = os.getenv("OTEL_ENABLED","true").lower() in ("true","1","yes"); self.OTEL_EXPORTER_ENDPOINT = os.getenv("OTEL_EXPORTER_ENDPOINT","http://localhost:4317")
        self.OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME","graphrag-backend")
        self.GUARDRAILS_ENABLED = os.getenv("GUARDRAILS_ENABLED","true").lower() in ("true","1","yes"); self.MAX_INPUT_LENGTH = int(os.getenv("MAX_INPUT_LENGTH","10000"))
        self.PROMPT_INJECTION_THRESHOLD = float(os.getenv("PROMPT_INJECTION_THRESHOLD","0.85"))
        self.RATE_LIMIT_DEFAULT = parse_list_from_env("RATE_LIMIT_DEFAULT",["200 per day","50 per hour"])
        default_endpoints = {"chat":["30 per minute"],"chat_stream":["20 per minute"],"ingest":["10 per minute"],"register":["10 per hour"],"login":["20 per minute"],"health":["60 per minute"]}
        self.RATE_LIMIT_ENDPOINTS = default_endpoints.copy()
        for ep in default_endpoints:
            val = parse_list_from_env(f"RATE_LIMIT_{ep.upper()}")
            if val: self.RATE_LIMIT_ENDPOINTS[ep] = val
        self.CHUNK_SIZE = int(os.getenv("CHUNK_SIZE","512")); self.CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP","64"))
        self.ENTITY_EXTRACTION_BATCH_SIZE = int(os.getenv("ENTITY_EXTRACTION_BATCH_SIZE","5")); self.GRAPH_COMMUNITY_ALGORITHM = os.getenv("GRAPH_COMMUNITY_ALGORITHM","louvain")
        self.RERANKER_TOP_K = int(os.getenv("RERANKER_TOP_K","5"))
        self.SMTP_HOST = os.getenv("SMTP_HOST","localhost"); self.SMTP_PORT = os.getenv("SMTP_PORT","1025"); self.SMTP_USER = os.getenv("SMTP_USER","")
        self.SMTP_PASSWORD = os.getenv("SMTP_PASSWORD",""); self.SMTP_USE_TLS = os.getenv("SMTP_USE_TLS","true")
        self.S3_ENDPOINT = os.getenv("S3_ENDPOINT","http://localhost:9000"); self.S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY","minioadmin")
        self.S3_SECRET_KEY = os.getenv("S3_SECRET_KEY","minioadmin"); self.S3_BUCKET = os.getenv("S3_BUCKET","graphrag-documents"); self.S3_REGION = os.getenv("S3_REGION","us-east-1")
        self.UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR","data/uploads")); self.PROCESSED_DIR = Path(os.getenv("PROCESSED_DIR","data/processed"))
        self._apply_environment_settings()

    def _apply_environment_settings(self):
        overrides = {
            Environment.DEVELOPMENT: {"DEBUG":True,"LOG_LEVEL":"DEBUG","LOG_FORMAT":"console"},
            Environment.STAGING: {"DEBUG":False,"LOG_LEVEL":"INFO"}, Environment.PRODUCTION: {"DEBUG":False,"LOG_LEVEL":"WARNING"},
            Environment.TEST: {"DEBUG":True,"LOG_LEVEL":"DEBUG","LOG_FORMAT":"console"},
        }
        for k, v in overrides.get(self.ENVIRONMENT,{}).items():
            if k.upper() not in os.environ: setattr(self, k, v)

    @property
    def postgres_dsn(self) -> str: return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    @property
    def postgres_async_dsn(self) -> str: return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

settings = Settings()