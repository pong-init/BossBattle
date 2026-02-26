import os
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.langchain import LangChainInstrumentor

def setup_observability():
    """Initialize OpenTelemetry instrumentation for the BossBattle agent."""
    
    # Define the service name for traces
    resource = Resource(attributes={
        SERVICE_NAME: "bossbattle-agent"
    })

    # Set up the tracer provider
    provider = TracerProvider(resource=resource)
    
    # Configure the OTLP exporter (pointing to our local collector)
    otlp_exporter = OTLPSpanExporter(
        endpoint="http://localhost:4317", 
        insecure=True
    )
    
    # Add the batch processor to the provider
    processor = BatchSpanProcessor(otlp_exporter)
    provider.add_span_processor(processor)
    
    # Set the global tracer provider
    trace.set_tracer_provider(provider)

    # Automatically instrument all LangChain calls
    LangChainInstrumentor().instrument()

    print("OpenTelemetry instrumentation initialized. Traces pointing to localhost:4317")

if __name__ == "__main__":
    setup_observability()
