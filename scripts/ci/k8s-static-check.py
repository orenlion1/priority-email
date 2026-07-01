#!/usr/bin/env python3
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
K8S_DIR = ROOT / "infra" / "k8s"
REQUIRED = {
    "alloy.yaml": ("ServiceAccount", "priority-email-alloy"),
    "namespace.yaml": ("Namespace", "priority-email"),
    "serviceaccount.yaml": ("ServiceAccount", "priority-email-service"),
    "state-pvc.yaml": ("PersistentVolumeClaim", "priority-email-state"),
    "deployment.yaml": ("Deployment", "priority-email-service"),
    "network-policy.yaml": ("NetworkPolicy", "default-deny-ingress"),
    "poddisruptionbudget.yaml": ("PodDisruptionBudget", "priority-email-service"),
    "deploy-rbac.yaml": ("Role", "priority-email-deployer"),
}


def metadata_name(text):
    match = re.search(r"(?m)^metadata:\n(?:  .*\n)*?  name: ([^\n]+)", text)
    return match.group(1).strip() if match else ""


def main():
    failures = []
    for filename, (kind, name) in REQUIRED.items():
        path = K8S_DIR / filename
        if not path.exists():
            failures.append(f"missing manifest: {path.relative_to(ROOT)}")
            continue
        text = path.read_text()
        if f"kind: {kind}" not in text:
            failures.append(f"{filename}: expected kind {kind}")
        if metadata_name(text) != name:
            failures.append(f"{filename}: expected metadata.name {name}")
        if kind != "Namespace" and "namespace: priority-email" not in text:
            failures.append(f"{filename}: expected namespace priority-email")
        if "\t" in text:
            failures.append(f"{filename}: tabs are not allowed in YAML")
    deployment = (K8S_DIR / "deployment.yaml").read_text()
    required_fragments = [
        "readOnlyRootFilesystem: true",
        "allowPrivilegeEscalation: false",
        'drop: ["ALL"]',
        "runAsNonRoot: true",
        "name: priority-email-filters",
        "name: priority-email-secrets",
        "OTEL_SERVICE_NAME",
        "priority-email-service",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://alloy.priority-email.svc.cluster.local:4318",
        "EMAIL_POLL_LOG_FILE",
        "/tmp/email-poller.log",
        "EMAIL_POLL_STATE_FILE",
        "/var/lib/priority-email/email-poller-state.json",
        "claimName: priority-email-state",
        "type: Recreate",
        "EMAIL_LOG_LEVEL",
        "INFO",
    ]
    for fragment in required_fragments:
        if fragment not in deployment:
            failures.append(f"deployment.yaml: missing {fragment}")
    alloy = (K8S_DIR / "alloy.yaml").read_text()
    alloy_fragments = [
        "kind: ConfigMap",
        "name: priority-email-alloy-config",
        "otelcol.receiver.otlp",
        "loki.source.kubernetes",
        "otelcol.exporter.otlphttp",
        "GRAFANA_CLOUD_OTLP_ENDPOINT",
        "GRAFANA_CLOUD_INSTANCE_ID",
        "GRAFANA_CLOUD_API_KEY",
        "name: priority-email-observability-secrets",
        "runAsNonRoot: true",
        "readOnlyRootFilesystem: true",
    ]
    for fragment in alloy_fragments:
        if fragment not in alloy:
            failures.append(f"alloy.yaml: missing {fragment}")
    network_policy = (K8S_DIR / "network-policy.yaml").read_text()
    for fragment in ["allow-alloy-otlp-ingress", "port: 4317", "port: 4318"]:
        if fragment not in network_policy:
            failures.append(f"network-policy.yaml: missing {fragment}")
    if failures:
        print("Kubernetes static check failed:")
        print("\n".join(failures))
        return 1
    print("Kubernetes static check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
