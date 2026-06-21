import datetime as dt
import json
import os
import secrets
import time
import urllib.error
import urllib.request


DEFAULT_SERVICE_NAME = "priority-email-service"
DEFAULT_SERVICE_NAMESPACE = "priority-email"
INSTRUMENTATION_SCOPE = "priority-email.poller"
AGGREGATION_TEMPORALITY_DELTA = 2


def now_iso():
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def now_unix_nano():
    return int(time.time() * 1_000_000_000)


def attr_value(value):
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"intValue": value}
    if isinstance(value, float):
        return {"doubleValue": value}
    return {"stringValue": "" if value is None else str(value)}


def attributes(values):
    return [{"key": key, "value": attr_value(value)} for key, value in values.items()]


def append_otlp_path(endpoint, path):
    endpoint = endpoint.rstrip("/")
    if endpoint.endswith(path):
        return endpoint
    if endpoint.endswith("/otlp"):
        return f"{endpoint}{path}"
    return f"{endpoint}{path}"


class Span:
    def __init__(self, name, provider="", attrs=None):
        self.name = name
        self.provider = provider
        self.trace_id = secrets.token_hex(16)
        self.span_id = secrets.token_hex(8)
        self.start_nano = now_unix_nano()
        self.attrs = dict(attrs or {})


class Telemetry:
    def __init__(self, values):
        env = {key: value for key, value in os.environ.items() if value}
        merged = {**values, **env}
        self.service_name = merged.get("OTEL_SERVICE_NAME", DEFAULT_SERVICE_NAME)
        self.service_namespace = merged.get(
            "OTEL_SERVICE_NAMESPACE", DEFAULT_SERVICE_NAMESPACE
        )
        self.deployment_environment = merged.get(
            "OTEL_DEPLOYMENT_ENVIRONMENT", merged.get("DEPLOYMENT_ENVIRONMENT", "production")
        )
        self.service_version = merged.get("OTEL_SERVICE_VERSION", merged.get("GIT_COMMIT_SHA", ""))
        self.endpoint = merged.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
        self.enabled = self.endpoint and merged.get("OTEL_SDK_DISABLED", "").lower() not in {
            "1",
            "true",
            "yes",
        }
        self.timeout = float(merged.get("OTEL_EXPORTER_OTLP_TIMEOUT_SECONDS", "5"))
        self.metrics = []

    def resource_attrs(self):
        attrs = {
            "service.name": self.service_name,
            "service": self.service_name,
            "service_name": self.service_name,
            "service.namespace": self.service_namespace,
            "deployment.environment.name": self.deployment_environment,
        }
        if self.service_version:
            attrs["service.version"] = self.service_version
        return attrs

    def log(self, level, event, **fields):
        record = {
            "timestamp": now_iso(),
            "level": level,
            "service": self.service_name,
            "service_name": self.service_name,
            "service.namespace": self.service_namespace,
            "event": event,
        }
        record.update(fields)
        print(json.dumps(record, sort_keys=True), flush=True)

    def start_span(self, name, provider="", **attrs):
        span = Span(name, provider=provider, attrs=attrs)
        self.log("info", f"{name}_started", provider=provider, trace_id=span.trace_id, **attrs)
        return span

    def end_span(self, span, status="ok", message="", **attrs):
        merged_attrs = {**span.attrs, **attrs, "status": status}
        end_nano = now_unix_nano()
        self.log(
            "info" if status == "ok" else "error",
            f"{span.name}_finished",
            provider=span.provider,
            trace_id=span.trace_id,
            duration_ms=round((end_nano - span.start_nano) / 1_000_000, 3),
            **merged_attrs,
        )
        if not self.enabled:
            return
        span_payload = {
            "traceId": span.trace_id,
            "spanId": span.span_id,
            "name": span.name,
            "kind": 1,
            "startTimeUnixNano": str(span.start_nano),
            "endTimeUnixNano": str(end_nano),
            "attributes": attributes(merged_attrs),
            "status": {"code": 1 if status == "ok" else 2, "message": message},
        }
        payload = {
            "resourceSpans": [
                {
                    "resource": {"attributes": attributes(self.resource_attrs())},
                    "scopeSpans": [
                        {
                            "scope": {"name": INSTRUMENTATION_SCOPE},
                            "spans": [span_payload],
                        }
                    ],
                }
            ]
        }
        self._post_otlp_json(append_otlp_path(self.endpoint, "/v1/traces"), payload, "traces")

    def count(self, name, value=1, **attrs):
        self.metrics.append(("sum", name, int(value), attrs))

    def gauge(self, name, value, **attrs):
        self.metrics.append(("gauge", name, float(value), attrs))

    def flush_metrics(self):
        if not self.enabled or not self.metrics:
            self.metrics = []
            return
        timestamp = str(now_unix_nano())
        otel_metrics = []
        for metric_type, name, value, attrs in self.metrics:
            datapoint = {"timeUnixNano": timestamp, "attributes": attributes(attrs)}
            if metric_type == "gauge":
                datapoint["asDouble"] = value
                otel_metrics.append({"name": name, "gauge": {"dataPoints": [datapoint]}})
            else:
                datapoint["asInt"] = value
                otel_metrics.append(
                    {
                        "name": name,
                        "sum": {
                            "aggregationTemporality": AGGREGATION_TEMPORALITY_DELTA,
                            "isMonotonic": True,
                            "dataPoints": [datapoint],
                        },
                    }
                )
        payload = {
            "resourceMetrics": [
                {
                    "resource": {"attributes": attributes(self.resource_attrs())},
                    "scopeMetrics": [
                        {
                            "scope": {"name": INSTRUMENTATION_SCOPE},
                            "metrics": otel_metrics,
                        }
                    ],
                }
            ]
        }
        self.metrics = []
        self._post_otlp_json(append_otlp_path(self.endpoint, "/v1/metrics"), payload, "metrics")

    def _post_otlp_json(self, url, payload, signal):
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout):
                return True
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self.log(
                "warning",
                "otel_export_failed",
                signal=signal,
                reason=type(exc).__name__,
            )
            return False
