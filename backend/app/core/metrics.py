"""Prometheus metrics for GraphRAG platform."""

from prometheus_client import Counter, Histogram, Gauge

# ── HTTP ──
http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds", "HTTP request duration", ["method", "endpoint"]
)

# ── LLM ──
llm_inference_duration_seconds = Histogram(
    "llm_inference_duration_seconds",
    "LLM inference duration",
    ["model"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)
llm_stream_duration_seconds = Histogram(
    "llm_stream_duration_seconds",
    "LLM streaming duration",
    ["model"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

# ── GraphRAG Pipeline ──
documents_ingested_total = Counter(
    "documents_ingested_total", "Total documents ingested", ["status"]
)
entities_extracted_total = Counter(
    "entities_extracted_total", "Total entities extracted", ["entity_type"]
)
graph_nodes_total = Gauge("graph_nodes_total", "Total nodes in knowledge graph")
graph_edges_total = Gauge("graph_edges_total", "Total edges in knowledge graph")
vector_search_duration_seconds = Histogram(
    "vector_search_duration_seconds",
    "Vector similarity search duration",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0],
)
graph_query_duration_seconds = Histogram(
    "graph_query_duration_seconds",
    "Graph traversal query duration",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0],
)

# ── Security ──
guardrail_blocks_total = Counter(
    "guardrail_blocks_total", "Requests blocked by guardrails", ["reason"]
)
auth_attempts_total = Counter(
    "auth_attempts_total", "Authentication attempts", ["status"]
)

# ── GPU (NVIDIA) ──
gpu_utilization = Gauge("gpu_utilization_percent", "GPU utilization %", ["gpu"])
gpu_memory_used_mb = Gauge("gpu_memory_used_mb", "GPU memory used MB", ["gpu"])
gpu_memory_total_mb = Gauge("gpu_memory_total_mb", "GPU memory total MB", ["gpu"])
gpu_temperature_celsius = Gauge("gpu_temperature_celsius", "GPU temperature °C", ["gpu"])

_gpu_collect_started = False


def _collect_gpu_metrics():
    """Background thread collecting NVIDIA GPU metrics via pynvml."""
    global _gpu_collect_started
    if _gpu_collect_started:
        return
    _gpu_collect_started = True
    import threading
    import time

    def _collect():
        try:
            import pynvml
            pynvml.nvmlInit()
        except Exception:
            return
        while True:
            try:
                count = pynvml.nvmlDeviceGetCount()
                for i in range(count):
                    handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                    util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                    mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                    gpu_label = str(i)
                    gpu_utilization.labels(gpu=gpu_label).set(util.gpu)
                    gpu_memory_used_mb.labels(gpu=gpu_label).set(mem.used // 1024 // 1024)
                    gpu_memory_total_mb.labels(gpu=gpu_label).set(mem.total // 1024 // 1024)
                    gpu_temperature_celsius.labels(gpu=gpu_label).set(temp)
            except Exception:
                pass
            time.sleep(10)

    t = threading.Thread(target=_collect, daemon=True)
    t.start()


def setup_metrics(app):
    """Set up Prometheus metrics endpoint."""
    try:
        from starlette_prometheus import metrics, PrometheusMiddleware

        app.add_middleware(PrometheusMiddleware)
        app.add_route("/metrics", metrics)
    except ImportError:
        from app.core.logging import logger

        logger.warning("starlette_prometheus_not_installed")
    _collect_gpu_metrics()