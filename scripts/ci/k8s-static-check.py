#!/usr/bin/env python3
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
K8S_DIR = ROOT / "infra" / "k8s"
REQUIRED = {
    "namespace.yaml": ("Namespace", "priority-email"),
    "serviceaccount.yaml": ("ServiceAccount", "priority-email-service"),
    "deployment.yaml": ("Deployment", "priority-email-service"),
    "network-policy.yaml": ("NetworkPolicy", "default-deny-ingress"),
    "poddisruptionbudget.yaml": ("PodDisruptionBudget", "priority-email-service"),
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
    ]
    for fragment in required_fragments:
        if fragment not in deployment:
            failures.append(f"deployment.yaml: missing {fragment}")
    if failures:
        print("Kubernetes static check failed:")
        print("\n".join(failures))
        return 1
    print("Kubernetes static check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
