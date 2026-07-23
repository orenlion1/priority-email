# Priority Email

Priority Email monitors connected mail accounts for important sender matches, then alerts through Slack and eventually phone push notifications.

## Current Status

- Gmail OAuth is configured and metadata read validation succeeds.
- Gmail polling is implemented with checkpointed incremental reads.
- Yahoo Mail and Apple iCloud Mail pollers are stubbed for future implementation.
- Slack posting is validated through the `Priority Email` Slack app.
- Incremental messages matching sender-name, exact email, or domain filters post Slack summaries when `SLACK_BOT_TOKEN` and `SLACK_CHANNEL_ID` are configured.
- **Serverless since 2026-07-10.** The poller runs as a scheduled AWS Lambda (Python 3.13) invoked by EventBridge every 5 minutes; each invocation is one poll cycle. It replaced the looping pod on the ensemble-grafana EKS cluster, decommissioned in the ensemble-retail cost-reduction migration. See `DEPLOYMENT_PLAN.md`.
- Checkpoint and notification-dedupe state, and the assembled filter files, live in the `priority-email-state-<account>` S3 bucket (was: a PVC + a ConfigMap).
- Observability is standardized on Grafana Labs tooling: the Lambda emits structured JSON logs with `service=priority-email-service` plus OTLP traces/metrics directly to Grafana Cloud, and CloudWatch retains function logs.

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

Provider HTTP requests retry transport failures and HTTP `408`, `429`, `500`, `502`, `503`, and `504` responses up to three total attempts with one- and two-second backoff delays. Each attempt emits RED metrics; the poll failure and Slack error notification are surfaced only after retries are exhausted. Non-transient failures such as invalid credentials and malformed responses fail immediately.

Matched email summaries are posted to Slack by default when `EMAIL_POLL_SLACK_SUMMARIES_ENABLED=true`. Provider initialization skips Slack summaries unless `EMAIL_NOTIFY_ON_INITIALIZATION=true`, which avoids reposting the latest inspected messages after cold starts.

Each provider poll appends one JSON line to `EMAIL_POLL_LOG_FILE` for local audit/debugging. The Kubernetes default is `/tmp/email-poller.log`, and the local template default is `.state/email-poller.log`. Audit entries include `level=INFO` for successful polls and `level=ERROR` for failed polls.

Production stores `EMAIL_POLL_STATE_FILE` at `/var/lib/priority-email/email-poller-state.json` on a Kubernetes PVC backed by the cluster `gp2` storage class. The deployment uses `Recreate` so only one worker pod mounts the state volume at a time.

Runtime stdout logging is controlled by `EMAIL_LOG_LEVEL`. Production currently defaults to `INFO`, so successful poll-cycle logs are emitted to stdout for Alloy/Grafana and are also kept in the poll logfile. Provider failures emit `ERROR` logs with sanitized request, duration, Slack notification, and checkpoint context.

Provider request RED metrics are emitted for Gmail/Yahoo API and IMAP operations with `provider`, `operation`, `method`, `outcome`, `status`, and `reason` labels:

- `priority_email_provider_requests_total`
- `priority_email_provider_request_errors_total`
- `priority_email_provider_request_duration_ms`

External dependency RED metrics are emitted for email providers, Slack, and future outbound integrations with `dependency`, `operation`, `method`, `outcome`, `status`, and `reason` labels:

- `priority_email_external_dependency_requests_total`
- `priority_email_external_dependency_request_errors_total`
- `priority_email_external_dependency_request_duration_ms`

For local OTEL testing, run an OTLP HTTP collector on `localhost:4318` or set `OTEL_EXPORTER_OTLP_ENDPOINT` to another collector. Telemetry export is fail-open: email polling continues if the collector is unavailable.

## CI Commands

```bash
python3 -m unittest discover tests
python3 -m compileall scripts tests
bash -n scripts/aws/ensure-ecr.sh scripts/aws/ensure-ebs-csi-addon.sh scripts/aws/sync-runtime-secret.sh scripts/aws/build-and-push-image.sh scripts/aws/bootstrap-aws.sh scripts/kubernetes/apply-manifests.sh scripts/filters/add-filter-op.sh scripts/filters/decrypt-filters.sh scripts/filters/sync-filters-from-ops.sh
sh -n scripts/run-poller-loop.sh
python3 scripts/ci/k8s-static-check.py
python3 scripts/ci/secret-scan.py
docker build --platform linux/amd64 -t priority-email-service:ci .
```

## Slack Management Commands

The Slack management channel understands a `command sub-command [args]` grammar,
parsed in `scripts/slack/commands.py`: `filter list | add <kind> <value> |
remove <kind> <value>` (kinds: `domain`, `email-address`, `sender-name`),
`provider list`, `poll now`, and `help [<command>]`. Filter-value rules mirror
`scripts/filters/assemble-filters.py`, so anything accepted here survives
assembly.

The shared grammar mechanics — verb dispatch, Slack markup stripping, the
`ParseError` reply type, the `help` / `help <command>` renderer, signing-secret
verification, and the Events request lifecycle — come from the internal
[`slackkit`](https://github.com/orenlion1/slackkit) package (also used by
`re-rank`); only priority-email's own verbs, validation, and help text are local.

`slackkit` is published to a private AWS CodeArtifact repository. CI installs it
by assuming the read-only `slackkit-reader` role via GitHub OIDC — no long-lived
keys. To run the tests locally, install it the same way:

```bash
aws codeartifact login --tool pip --domain orenlion1 \
  --domain-owner "$AWS_ACCOUNT_ID" --repository python
pip install slackkit
python3 -m unittest discover tests
```

## Secrets And Filters

Do not commit local secrets or plaintext filter values.

- Copy `.env.example` to `.env` for local secrets.
- Commit only `filters/*.txt.template`, the age public key `filters/age-recipients.pub`, and encrypted ops under `filters/ops/`.
- Keep plaintext filter values in ignored `filters/*.txt` files; they are derived from the encrypted ops log.
- Keep Google OAuth client secret JSON files local and ignored. Never commit the age private key.
- Set `AWS_PROFILE` and `AWS_ACCOUNT_ID` in local `.env`; do not copy static AWS access keys into this repo.

## Updating Filters (from anywhere)

The source of truth for filter values is the age-encrypted, append-only ops log in `filters/ops/`. Adding or removing a filter needs only the committed public key, so it works from any device — including a coding agent driven from a phone — with no human approval step:

```bash
scripts/filters/add-filter-op.sh add domain example.com
scripts/filters/add-filter-op.sh remove sender-name "Jane Smith"
git add filters/ops && git commit -m "chore: update filters" && git push
```

Once CI passes on `main`, the `Deploy` workflow's `sync-filters` job decrypts the ops with the `AGE_SECRET_KEY` secret, assembles the filter files, applies the `priority-email-filters` ConfigMap, restarts the worker, and checksum-verifies the live ConfigMap without printing filter values.

One practical note for remote agents: they need the `age` binary (one `apt-get`/`brew install` in their workspace) and push access to `main`.

Operators can regenerate local plaintext filter files with `scripts/filters/decrypt-filters.sh` (requires the age key at `~/.config/priority-email/age.key`, or `AGE_SECRET_KEY`/`AGE_KEY_FILE`).

## AWS Deploy

Deployment is GitHub-based: pushing to `main` builds, pushes, and rolls out the image and syncs live filters automatically. The only local script is the operator bootstrap for secrets and infrastructure:

```bash
scripts/aws/bootstrap-aws.sh
```

The bootstrap script syncs `.env` to AWS Secrets Manager and the namespace Kubernetes secrets, ensures the AWS managed `aws-ebs-csi-driver` EKS add-on is active with an IRSA role, and applies the dedicated `priority-email` Kubernetes workload manifests, preserving the currently deployed ECR image. It does not build images or deliver filter values — those are owned by the `Deploy` workflow.

Grafana Cloud ingest values must be present in gitignored `.env` before bootstrap. The bootstrap script copies only these Grafana keys into the narrow Kubernetes `priority-email-observability-secrets` object for Alloy:

- `GRAFANA_CLOUD_OTLP_ENDPOINT`
- `GRAFANA_CLOUD_INSTANCE_ID`
- `GRAFANA_CLOUD_API_KEY`

Merges to `main` auto-deploy: after CI passes, the `Deploy` GitHub Actions workflow (`.github/workflows/deploy.yml`) automatically builds, pushes, and rolls out the CI-passing commit's image using GitHub OIDC, and syncs the live filter ConfigMap when the encrypted ops log changed. Documentation-only changes skip both jobs: the workflow diffs against the last deployed commit and only acts when `Dockerfile`, `scripts/**`, `filters/**`, or the workflow itself changed. This requires the `AWS_ACCOUNT_ID`, `AWS_DEPLOY_ROLE_ARN`, and `AGE_SECRET_KEY` GitHub Actions secrets. The `scripts/aws/bootstrap-aws.sh` script remains the local operator/bootstrap path for secrets and infrastructure.

For functional runtime changes, push the source commit to GitHub first and wait for CI to pass; the automated `Deploy` workflow then rolls out that same commit. Operator bootstrap of secrets and infrastructure still runs locally via the bootstrap script. Documentation-only changes do not require an AWS rollout.

## Documentation

- [Requirements](REQUIREMENTS.md)
- [Deployment Plan](DEPLOYMENT_PLAN.md)
- [Push Notification Options](PUSH_NOTIFICATION_OPTIONS.md)
- [Evolution](EVOLUTION.md)
- [Agent Policy](AGENTS.md)
