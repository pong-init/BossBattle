from opentelemetry import trace, metrics
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.instrumentation.langchain import LangchainInstrumentor


def setup_observability():
    """Initialize OpenTelemetry instrumentation for the BossBattle agent.

    Sets up both trace and metric pipelines. The LangchainInstrumentor
    (OpenLLMetry) auto-emits:
      - gen_ai_client_operation_duration_seconds (LLM call latency)
      - gen_ai_client_token_usage (input/output token counts)

    The OTel Collector's spanmetrics connector adds:
      - traces_span_metrics_calls_total (call count per span)
      - traces_span_metrics_duration_milliseconds (latency per span)
    """

    resource = Resource(attributes={
        SERVICE_NAME: "bossbattle-agent"
    })

    endpoint = "http://localhost:4317"

    # --- Metrics (enables OpenLLMetry's native metric emission) ---
    metric_exporter = OTLPMetricExporter(endpoint=endpoint, insecure=True)
    metric_reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=5000)
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # --- Traces ---
    provider = TracerProvider(resource=resource)
    otlp_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    trace.set_tracer_provider(provider)

    # Auto-instrument LangChain (emits traces + metrics)
    LangchainInstrumentor().instrument()

    print("OpenTelemetry instrumentation initialized (traces + metrics → localhost:4317)")


if __name__ == "__main__":
    setup_observability()
