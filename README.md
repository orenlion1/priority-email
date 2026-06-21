# Priority Email

Priority Email monitors connected mail accounts for important sender matches, then alerts through Slack and eventually phone push notifications.

## Current Status

- Gmail OAuth is configured and metadata read validation succeeds.
- Gmail polling is implemented with checkpointed incremental reads.
- Yahoo Mail and Apple iCloud Mail pollers are stubbed for future implementation.
- Slack posting is validated through the `Priority Email` Slack app.
- AWS deployment is live in the reference AWS account through the `example-platform` AWS CLI profile.
- The live Kubernetes worker runs in the dedicated `priority-email` namespace.
- Observability is standardized on Grafana Labs tooling and services.
- The worker emits structured JSON logs with `service=priority-email-service`, OTLP traces, and OTLP metrics.
- A namespace-local Grafana Alloy collector receives Priority Email OTLP signals and collects Priority Email pod logs.

## Local Commands

```bash
python3 -m unittest discover tests
python3 scripts/validate-gmail-read.py
python3 scripts/poll-email.py --provider gmail
python3 scripts/test-slack-message.py
```

Use `--verbose` with the Gmail poller only when message metadata is needed for debugging:

```bash
python3 scripts/poll-email.py --provider gmail --verbose
```

Provider request failures are posted to Slack by default when `SLACK_BOT_TOKEN` and `SLACK_CHANNEL_ID` are configured. Set `EMAIL_POLL_SLACK_ERROR_NOTIFICATIONS_ENABLED=false` for local troubleshooting without Slack error posts.

Each provider poll appends one JSON line to `EMAIL_POLL_LOG_FILE` for local audit/debugging. The Kubernetes default is `/tmp/email-poller.log`, and the local template default is `.state/email-poller.log`. Audit entries include `level=INFO` for successful polls and `level=ERROR` for failed polls.

Runtime stdout logging is controlled by `EMAIL_LOG_LEVEL`. Production currently defaults to `INFO`, so successful poll-cycle logs are emitted to stdout for Alloy/Grafana and are also kept in the poll logfile. Provider failures emit `ERROR` logs with sanitized request, duration, Slack notification, and checkpoint context.

For local OTEL testing, run an OTLP HTTP collector on `localhost:4318` or set `OTEL_EXPORTER_OTLP_ENDPOINT` to another collector. Telemetry export is fail-open: email polling continues if the collector is unavailable.

## CI Commands

```bash
python3 -m unittest discover tests
python3 -m compileall scripts tests
bash -n scripts/aws/ensure-ecr.sh scripts/aws/sync-runtime-secret.sh scripts/aws/build-and-push-image.sh scripts/aws/deploy-to-aws.sh scripts/kubernetes/apply-manifests.sh
sh -n scripts/run-poller-loop.sh
python3 scripts/ci/k8s-static-check.py
python3 scripts/ci/secret-scan.py
docker build --platform linux/amd64 -t priority-email-service:ci .
```

## Secrets And Filters

Do not commit local secrets or real filter values.

- Copy `.env.example` to `.env` for local secrets.
- Commit only `filters/*.txt.template`.
- Keep real filter values in ignored `filters/*.txt` files.
- Keep Google OAuth client secret JSON files local and ignored.
- Set `AWS_PROFILE` and `AWS_ACCOUNT_ID` in local `.env`; do not copy static AWS access keys into this repo.

## AWS Deploy

```bash
scripts/aws/deploy-to-aws.sh
```

The deploy script syncs `.env` to AWS Secrets Manager, builds and pushes the Docker image to ECR, mounts real local filter files as a Kubernetes ConfigMap, and applies the dedicated `priority-email` Kubernetes workload.

Grafana Cloud ingest values must be present in gitignored `.env` before deployment. The deploy script copies only these Grafana keys into the narrow Kubernetes `priority-email-observability-secrets` object for Alloy:

- `GRAFANA_CLOUD_OTLP_ENDPOINT`
- `GRAFANA_CLOUD_INSTANCE_ID`
- `GRAFANA_CLOUD_API_KEY`

For functional runtime changes, push the source commit to GitHub first, wait for CI to pass, then run the AWS deploy script from that same commit. Documentation-only changes do not require an AWS rollout.

## Documentation

- [Requirements](REQUIREMENTS.md)
- [Deployment Plan](DEPLOYMENT_PLAN.md)
- [Push Notification Options](PUSH_NOTIFICATION_OPTIONS.md)
- [Evolution](EVOLUTION.md)
- [Agent Policy](AGENTS.md)
