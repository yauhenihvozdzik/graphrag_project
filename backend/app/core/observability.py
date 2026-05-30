"""OpenTelemetry observability setup for GraphRAG platform.

Configures tracing with OTLP exporter for Jaeger/Tempo integration.
"""

from app.core.config import settings
from app.core.logging import logger


def setup_opentelemetry():
    """Initialize OpenTelemetry tracing with OTLP exporter."""
    if not settings.OTEL_ENABLED:
        logger.info("opentelemetry_disabled")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create(
            {
                "service.name": settings.OTEL_SERVICE_NAME,
                "service.version": settings.VERSION,
                "deployment.environment": settings.ENVIRONMENT.value,
            }
        )

        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_ENDPOINT, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        logger.info(
            "opentelemetry_initialized",
            service_name=settings.OTEL_SERVICE_NAME,
            exporter_endpoint=settings.OTEL_EXPORTER_ENDPOINT,
        )
    except ImportError:
        logger.warning("opentelemetry_packages_not_installed")
    except Exception as e:
        logger.exception("opentelemetry_init_failed", error=str(e))


def instrument_fastapi(app):
    """Instrument FastAPI app with OpenTelemetry."""
    if not settings.OTEL_ENABLED:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        logger.info("fastapi_instrumented_with_otel")
    except ImportError:
        logger.warning("opentelemetry_fastapi_instrumentor_not_available")
    except Exception as e:
        logger.warning("fastapi_instrumentation_failed", error=str(e))


def get_tracer(name: str = "graphrag"):
    """Get an OpenTelemetry tracer instance."""
    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except ImportError:
        return None
