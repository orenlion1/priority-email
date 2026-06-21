# Deployment And Operations Evolution

## Timeline

| Date | Milestone | Evidence |
| --- | --- | --- |
| 2026-06-21 | AWS deployment planning started from the Ensemble deployment pattern. | `DEPLOYMENT_PLAN.md` |
| 2026-06-21 | Priority Email was segregated from Ensemble runtime resources with a dedicated `priority-email` Kubernetes namespace. | `DEPLOYMENT_PLAN.md` |
| 2026-06-21 | Filter files were committed to a ConfigMap-mounted deployment strategy. | `DEPLOYMENT_PLAN.md` |
| 2026-06-21 | AWS End User Messaging Push was selected as the preferred production push provider. | `PUSH_NOTIFICATION_OPTIONS.md`, `DEPLOYMENT_PLAN.md` |
| 2026-06-21 | Local `.env` and AWS Secrets Manager/Kubernetes secret paths were documented. | `.env.example`, `REQUIREMENTS.md`, `DEPLOYMENT_PLAN.md` |
| 2026-06-21 | Gmail OAuth was configured in Google Cloud project `priority-email-500114` with Web Application and Desktop App OAuth clients. | `.env.example`, `DEPLOYMENT_PLAN.md` |
| 2026-06-21 | A local Gmail OAuth initialization script was added to capture refresh tokens into gitignored `.env`. | `scripts/init-gmail-oauth.py`, `DEPLOYMENT_PLAN.md` |
| 2026-06-21 | Gmail OAuth authorization completed locally and `.env` was populated with client values and refresh token. | `.env`, `DEPLOYMENT_PLAN.md`, `EVOLUTION.md` |
| 2026-06-21 | A metadata-only Gmail read validation script was added. | `scripts/validate-gmail-read.py`, `DEPLOYMENT_PLAN.md` |
| 2026-06-21 | Gmail read validation reached Google but was blocked because Gmail API is disabled for project number `877694096009`. | `scripts/validate-gmail-read.py`, `DEPLOYMENT_PLAN.md`, `EVOLUTION.md` |
| 2026-06-21 | Gmail API was enabled and metadata-only Gmail read validation succeeded. | `scripts/validate-gmail-read.py`, `DEPLOYMENT_PLAN.md`, `EVOLUTION.md` |
| 2026-06-21 | Configurable provider pollers were added with Gmail implemented and Yahoo/iCloud stubs. | `scripts/poll-email.py`, `.env.example`, `REQUIREMENTS.md` |
| 2026-06-21 | Default polling interval was set to 10 minutes. | `.env.example`, `REQUIREMENTS.md`, `DEPLOYMENT_PLAN.md` |
| 2026-06-21 | Gmail poller validation succeeded: first run inspected 20 messages and the immediate incremental run returned 0 newer messages. | `scripts/poll-email.py`, `.state/email-poller-state.json`, `EVOLUTION.md` |
| 2026-06-21 | Gemini created and installed Slack app `Priority Email` in workspace `ensemble-grafana` with `chat:write` scope. | `DEPLOYMENT_PLAN.md`, `EVOLUTION.md` |
| 2026-06-21 | A Slack message test script was added; first post reached Slack but failed with `not_in_channel`. | `scripts/test-slack-message.py`, `DEPLOYMENT_PLAN.md`, `EVOLUTION.md` |
| 2026-06-21 | Slack posting validation succeeded after inviting the `Priority Email` app/bot to the configured channel. | `scripts/test-slack-message.py`, `DEPLOYMENT_PLAN.md`, `EVOLUTION.md` |
| 2026-06-21 | Generated evolution flow diagrams were added for light and dark documentation surfaces. | `docs/evolution/diagrams/`, `EVOLUTION.md` |
| 2026-06-21 | Gmail incremental polling was hardened to page all messages newer than the checkpoint and avoid metadata output unless `--verbose` is used. | `scripts/poll-email.py`, `tests/test_poll_email.py`, `REQUIREMENTS.md` |
| 2026-06-21 | Priority Email adopted Ensemble's local AWS profile and account/region settings without copying static AWS keys. | `.env.example`, `REQUIREMENTS.md`, `DEPLOYMENT_PLAN.md` |
| 2026-06-21 | Priority Email was packaged and pushed to AWS: ECR image, Secrets Manager runtime secret, ConfigMap filters, and a live EKS worker in the `priority-email` namespace. | `Dockerfile`, `infra/k8s/`, `scripts/aws/`, `DEPLOYMENT_PLAN.md` |
| 2026-06-21 | PVC-backed checkpointing was attempted but deferred because the Ensemble EKS cluster has no EBS CSI add-on installed. Durable checkpoints remain planned for DynamoDB. | `DEPLOYMENT_PLAN.md`, `infra/k8s/deployment.yaml` |
| 2026-06-21 | AWS deployment hard parts were captured: Docker daemon readiness, missing ECR repo creation, safe secret/filter propagation, immutable image pinning, a bad image URI capture bug, no EBS CSI provisioner, and rollout verification for a sleeping worker. | `EVOLUTION.md`, `scripts/aws/deploy-to-aws.sh`, `scripts/kubernetes/apply-manifests.sh` |
| 2026-06-21 | CI/CD automation was added for pull requests and pushes to `main`, with offline quality gates that do not require production secrets. | `.github/workflows/ci.yml`, `.github/dependabot.yml`, `scripts/ci/` |
| 2026-06-21 | Provider request failures were wired to Slack error notifications with sanitized request details and saved provider error state. | `scripts/poll-email.py`, `tests/test_poll_email.py`, `REQUIREMENTS.md` |
| 2026-06-21 | Functional runtime changes were standardized to push to GitHub, wait for CI, deploy the same commit to AWS, and verify the live image tag. GitHub Actions were upgraded to Node 24-compatible action versions. | `.github/workflows/ci.yml`, `AGENTS.md`, `DEPLOYMENT_PLAN.md` |

## Current Operations Shape

Priority Email now runs as a Kubernetes worker on the Ensemble EKS cluster while remaining isolated in its own namespace. Runtime secrets are synced to AWS Secrets Manager and a namespace-local Kubernetes secret. Filter files are mounted from a namespace-local ConfigMap. Durable runtime state is still planned for DynamoDB; the first worker deployment uses pod-local file state until the data-stack checkpoint backend is implemented. GitHub Actions enforces offline quality gates before source changes land on `main`, using Node 24-compatible official actions. Provider request failures are surfaced to Slack with sanitized details. Functional runtime changes now continue through AWS deployment after GitHub CI passes. The AWS deployment notes preserve the operational traps found during the first push so the next deployment can avoid repeating them.
