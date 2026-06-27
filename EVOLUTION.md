# Priority Email Evolution

This file summarizes how Priority Email evolved from the initial requirements prompt into the current project shape.

The repository does not contain a literal transcript of every prompt. This chronology is reconstructed from project artifacts such as requirements, deployment plans, filter templates, provider option docs, and repo policy files.

## At A Glance

![Priority Email evolution flow dark version](docs/evolution/diagrams/priority-email-evolution-flow-dark.png)

For dark-background docs, slides, or Grafana-style presentation surfaces, use the dark flow export: [docs/evolution/diagrams/priority-email-evolution-flow-dark.png](docs/evolution/diagrams/priority-email-evolution-flow-dark.png).

- Full evolution package: [docs/evolution/README.md](docs/evolution/README.md)
- High-resolution PNG: [docs/evolution/diagrams/priority-email-evolution-flow.png](docs/evolution/diagrams/priority-email-evolution-flow.png)
- Dark high-resolution PNG: [docs/evolution/diagrams/priority-email-evolution-flow-dark.png](docs/evolution/diagrams/priority-email-evolution-flow-dark.png)
- SVG source export: [docs/evolution/diagrams/priority-email-evolution-flow.svg](docs/evolution/diagrams/priority-email-evolution-flow.svg)
- Dark SVG export: [docs/evolution/diagrams/priority-email-evolution-flow-dark.svg](docs/evolution/diagrams/priority-email-evolution-flow-dark.svg)
- Graphviz DOT source: [docs/evolution/diagrams/priority-email-evolution-flow.dot](docs/evolution/diagrams/priority-email-evolution-flow.dot)
- Dark Graphviz DOT source: [docs/evolution/diagrams/priority-email-evolution-flow-dark.dot](docs/evolution/diagrams/priority-email-evolution-flow-dark.dot)

## Prompt Categories

| Category | Evolution file | What changed |
| --- | --- | --- |
| Product and requirements | [product-requirements.md](docs/evolution/categories/product-requirements.md) | The product scope, supported mail providers, filtering model, notification behavior, platform standards, and security requirements were defined. |
| Deployment and operations | [deployment-operations.md](docs/evolution/categories/deployment-operations.md) | AWS deployment, Kubernetes namespace segregation, ConfigMap filters, secrets handling, and Grafana Labs observability standards were established. |
| Agent policy and safety | [agent-policy-safety.md](docs/evolution/categories/agent-policy-safety.md) | Global and repo-local evolution policy, GitHub safety rules, secret ignore patterns, and filter template rules were added. |

## Chronology

### June 21, 2026: Define The Product

Priority Email began as a requirements document for surfacing important email buried across Gmail, Yahoo Mail, and Apple iCloud Mail accounts.

Key evidence:

- `REQUIREMENTS.md`: product overview, goals, supported email providers, sender filter criteria, phone push notifications, Slack summaries, privacy requirements, reliability requirements, and acceptance criteria.
- `filters/domain-filters.txt`: local domain filter values for initial testing.

### June 21, 2026: Keep Initial Configuration Simple

The project adopted plain text filter files for the initial version, with separate files for sender domains, exact sender email addresses, and sender display names.

Key evidence:

- `filters/domain-filters.txt`
- `filters/email-address-filters.txt`
- `filters/sender-name-filters.txt`
- `REQUIREMENTS.md`: initial filter storage rules.

### June 21, 2026: Move To The Codex Workspace

The project moved from iCloud Drive to the Codex workspace at `<local-priority-email-repo>`.

Key evidence:

- Current project path: `<local-priority-email-repo>`.
- Compatibility symlink from the old iCloud Drive path to the new workspace path.

### June 21, 2026: Plan AWS Deployment

The deployment plan was created by referencing the reference platform AWS deployment pattern while keeping Priority Email isolated in its own Kubernetes namespace.

Key evidence:

- `DEPLOYMENT_PLAN.md`: references the reference deployment pattern, EKS, DynamoDB, Secrets Manager, IRSA, ConfigMap-mounted filters, dedicated `priority-email` namespace, and rollout validation.
- `REQUIREMENTS.md`: platform standards require AWS for cloud resources and Grafana Labs for observability.

### June 21, 2026: Choose Push Notification Direction

Push provider evaluation was documented with AWS-native resources preferred for deployment simplicity and cost control.

Key evidence:

- `PUSH_NOTIFICATION_OPTIONS.md`: recommends AWS End User Messaging Push for production and documents fallback options such as Slack mobile notifications, Pushover, and ntfy.
- `REQUIREMENTS.md`: push provider selection must verify provider status, support lifecycle, free tier, and pricing from primary sources where possible.

### June 21, 2026: Protect Secrets And Filter Values

The repository added local secret and filter-value safety rules before any future GitHub push.

Key evidence:

- `.gitignore`: ignores `.env`, `.env.*`, Google OAuth client secret files, generated secret YAML, Terraform variable/state files, and real `filters/*.txt` values.
- `.env.example`: committed-safe local environment template.
- `filters/*.txt.template`: committed-safe filter templates.
- `REQUIREMENTS.md`: local secrets must live in `.env`, real filter values must not be pushed, and only templates should be committed.

### June 21, 2026: Adopt Evolution Policy

The reference platform EVOLUTION policy was promoted into global Codex guidance and applied to this repository.

Key evidence:

- `<codex-home>/AGENTS.md`: global Codex evolution-history policy.
- `AGENTS.md`: Priority Email repo policy for documentation updates, secret safety, filter safety, and platform standards.
- `EVOLUTION.md`: initial project chronology.
- `docs/evolution/categories/`: category-level evolution files for product requirements, deployment operations, and agent policy safety.

### June 21, 2026: Configure Gmail OAuth Project

Gmail OAuth moved from planned configuration to a concrete Google Cloud setup.

Key evidence:

- Google Cloud project: `Priority Email` with project ID `example-priority-email-project`.
- OAuth consent screen app name: `Priority Email`.
- OAuth 2.0 clients: Web Application and Desktop App, both named `Priority Email - OAuth client`.
- `DEPLOYMENT_PLAN.md`: records the credential source and local status for gitignored `.env` values.
- `scripts/init-gmail-oauth.py`: local loopback OAuth helper for capturing `GMAIL_REFRESH_TOKENS` without printing secret values.
- `scripts/validate-gmail-read.py`: metadata-only Gmail read validation helper.
- Local Gmail read validation succeeded after enabling Gmail API for project number `<google-cloud-project-number>`; the script read one message's metadata without printing tokens or full body content.
- `.env`: populated locally with Gmail OAuth client values and refresh token; this file remains gitignored.
- `.env.example`: includes `GMAIL_GOOGLE_CLOUD_PROJECT_ID=` without exposing client secrets.

### June 21, 2026: Add Configurable Email Pollers

The project added a local poller entrypoint with Gmail implemented and Yahoo Mail/iCloud Mail stubs in place.

Key evidence:

- `scripts/poll-email.py`: configurable provider poller with Gmail support, local checkpoint state, and provider stubs for Yahoo Mail and iCloud Mail.
- `.env.example`: poller configuration keys for enabled providers, 10-minute interval, initialization limit, normal poll page size, and state file path.
- `REQUIREMENTS.md`: pollers must inspect only messages newer than the previous checkpoint after initialization and inspect only the latest 20 messages during first initialization.
- Local validation: Gmail initialization poll inspected 20 messages and set a checkpoint; the immediate second incremental poll returned 0 messages because no messages were newer than the checkpoint.

### June 21, 2026: Configure Slack App

Gemini configured the Slack integration for Priority Email.

Key evidence:

- Slack API flow completed: `Create New App` -> `From scratch` -> select workspace `example-platform`.
- Slack app name: `Priority Email`.
- OAuth & Permissions configured with `chat:write`.
- Slack app installed to the `example-platform` workspace.
- Bot User OAuth Token was copied for local use and must be stored only in gitignored `.env` as `SLACK_BOT_TOKEN`.
- `DEPLOYMENT_PLAN.md`: records the non-secret Slack app setup status and token handling rule.

### June 21, 2026: Add Slack Message Test

The project added a local Slack post validation script and attempted the first test message.

Key evidence:

- `scripts/test-slack-message.py`: posts a test message with `SLACK_BOT_TOKEN` and `SLACK_CHANNEL_ID` from gitignored `.env`.
- Local test initially returned `not_in_channel`; after the `Priority Email` app/bot was invited to the configured Slack channel, the Slack post test succeeded.
- `DEPLOYMENT_PLAN.md`: records the Slack test command and current blocker.

### June 21, 2026: Generate Evolution Flow Diagram

The project gained an reference-style generated evolution flow diagram package.

Key evidence:

- `docs/evolution/README.md`: documents the evolution reading path and regeneration commands.
- `docs/evolution/diagrams/priority-email-evolution-flow.dot`: light Graphviz DOT source.
- `docs/evolution/diagrams/priority-email-evolution-flow-dark.dot`: dark Graphviz DOT source.
- Generated SVG and PNG exports exist for both light and dark variants.

### June 21, 2026: Import Team Engineering Skills

The repo pulled in and applied external team skills for specification, testing, review, simplification, security, and git workflow.

Key evidence:

- `AGENTS.md`: references the imported team skill files and converts them into repo working rules.
- `tests/test_poll_email.py`: adds unit coverage for Gmail poller initialization and incremental pagination behavior.
- `scripts/poll-email.py`: incremental Gmail polling now pages all messages newer than the prior checkpoint, and metadata output is opt-in with `--verbose`.
- `REQUIREMENTS.md`: documents development quality requirements and poller safety requirements.
- Generated evolution flow diagrams now include the team-skills quality gate.

### June 21, 2026: Reference Platform AWS Profile

Priority Email pulled in the non-secret AWS credential configuration needed to align with the reference deployment workflow.

Key evidence:

- `.env` and `.env.example`: include `AWS_PROFILE=`, `AWS_ACCOUNT_ID=`, and `AWS_REGION=us-east-1`.
- AWS CLI validation: `aws sts get-caller-identity --profile example-platform` resolves to account `<aws-account-id>`.
- `REQUIREMENTS.md`: static AWS access keys must not be copied into project files.
- `DEPLOYMENT_PLAN.md`: documents profile-based AWS credential resolution.

### June 21, 2026: Publish Private GitHub Repository

The repository was prepared for its first GitHub push with committed-safe files only and published as a GitHub repository at `https://github.com/example/priority-email`.

Key evidence:

- `README.md`: landing page with status, commands, documentation links, and secret/filter safety rules.
- `.gitignore`: excludes `.env`, real filter values, local state, pycache, Terraform state/vars, generated secret YAML, and Google OAuth client secret files.
- Initial staged set excludes gitignored `.env`, `.state/`, `filters/*.txt`, and `client_secret_*.apps.googleusercontent.com*`.
- `python3 -m unittest discover tests`: unit tests pass before publication.
- Staged safety scan found no forbidden paths or populated secret values before publication.

### June 21, 2026: Push Worker To AWS

Priority Email was packaged as a non-root Docker worker and deployed to the reference EKS cluster in the dedicated `priority-email` namespace.

Key evidence:

- `Dockerfile` and `.dockerignore`: package only safe runtime files and exclude local secrets, real filters, state, and OAuth client secret JSON from the build context.
- `scripts/aws/deploy-to-aws.sh`: syncs `.env` to AWS Secrets Manager, builds/pushes the image to ECR, and applies Kubernetes manifests.
- `infra/k8s/`: namespace, service account, deployment, network policy, and PodDisruptionBudget for the isolated `priority-email` workload.
- AWS Secrets Manager: `priority-email/runtime` created or updated with the local runtime configuration.
- ECR image: `<aws-account-id>.dkr.ecr.<aws-region>.amazonaws.com/priority-email-service:<image-tag>`, digest `<image-digest>`.
- Kubernetes: `priority-email-service` rolled out successfully with one running replica.
- First AWS poller log: Gmail initialization inspected 20 messages and wrote the checkpoint to `/tmp/email-poller-state.json`.
- Storage finding: PVC-backed file checkpoints were not available during this first deploy, so durable checkpoints were temporarily deferred.

Hard parts encountered:

- Docker was installed but the daemon was not running at first, so the image build/push path required starting Docker Desktop and waiting for the daemon before ECR work could continue.
- The ECR repository `priority-email-service` did not exist yet, so deployment automation had to create it with encryption, image scanning, and Priority Email tags before pushing an image.
- Secret handling needed two parallel safety paths: real `.env` values were synced to AWS Secrets Manager and a namespace-local Kubernetes secret, while `.dockerignore`, `.gitignore`, and CI scans kept `.env`, OAuth client JSON, real filter values, and generated secret material out of Git and Docker build context.
- Filter values had to stay uncommitted locally while still reaching the cluster, so the Kubernetes deploy script creates `priority-email-filters` from ignored `filters/*.txt` files instead of committed templates.
- The first image was deployed as `latest`, then the workflow was tightened to pin Kubernetes to the immutable Git SHA image tag so source, ECR, and the live deployment can be correlated.
- A deploy-script bug captured verbose Docker push output as part of the image URI. The live deployment stayed healthy on the prior image, the bad intermediate ReplicaSet was corrected, and the script now captures only the final image URI line before calling `kubectl set image`.
- PVC-backed file checkpointing looked attractive for preserving poller state across pod restarts, but the initial volume rollout could not be completed cleanly. The deployment was restored to pod-local `/tmp` state until the later `priority-email-state` PVC hardening step moved production state to `/var/lib/priority-email`.
- Rolling a sleeping worker creates brief old-pod/new-pod overlap while Kubernetes drains the previous poll loop. Final verification had to check ReplicaSets and the actual live pod image, not just a single `kubectl logs deployment/...` sample.
- `.env` must be treated as dotenv data, not a shell script. A Grafana Cloud token contained shell-significant characters during monitoring rollout, so deploy helpers now parse only the AWS key/value fields they need instead of sourcing the whole secrets file.

### June 21, 2026: Add CI/CD Automation Skill

Priority Email imported the team CI/CD automation skill and added a GitHub Actions quality gate for every pull request and push to `main`.

Key evidence:

- `AGENTS.md`: imports the CI/CD automation skill and adds repo rules for CI quality gates and secret-safe automation.
- `.github/workflows/ci.yml`: runs Python syntax checks, unit tests, shell syntax checks, Kubernetes static checks, secret/path scanning, and Docker build validation without production secrets.
- `.github/dependabot.yml`: enables weekly dependency metadata updates for GitHub Actions and Docker.
- `scripts/ci/secret-scan.py`: blocks committed secret-like values and forbidden local-only paths.
- `scripts/ci/k8s-static-check.py`: checks the dedicated `priority-email` Kubernetes manifests for expected names, namespace isolation, ConfigMap/secret references, and hardening flags.
- `REQUIREMENTS.md` and `README.md`: document CI expectations and local CI commands.

### June 21, 2026: Add Slack Error Notifications For Provider Requests

Provider request failures now notify Slack with sanitized details so email integration failures are visible without requiring a shell on the worker pod.

Key evidence:

- `scripts/poll-email.py`: catches `EmailProviderRequestError`, records the sanitized error in provider state, posts details to Slack when configured, and continues the poll cycle without crashing the worker.
- Error notifications include provider, method, sanitized URL, HTTP status, reason, and truncated provider response details.
- URL sanitization redacts sensitive query parameters such as `access_token`, `client_secret`, `code`, `key`, `password`, and `token`.
- `EMAIL_POLL_SLACK_ERROR_NOTIFICATIONS_ENABLED=false` disables Slack error posts for local troubleshooting.
- `tests/test_poll_email.py`: covers Slack error posting, redaction, saved error state, and the disable switch.
- `REQUIREMENTS.md`: documents provider request error notification behavior and secret-safety requirements.

### June 21, 2026: Add Priority Email Grafana Observability

Priority Email moved from documented observability intent to concrete Grafana Alloy collection and OpenTelemetry emission.

Key evidence:

- `scripts/telemetry.py`: emits structured JSON logs with `service=priority-email-service`, OTLP metrics, and OTLP traces without adding third-party runtime dependencies.
- `scripts/poll-email.py`: wraps each provider poll cycle in a trace span and records poll cycles, messages checked, provider request failures, Slack error notification outcomes, and poll duration.
- `infra/k8s/alloy.yaml`: deploys a dedicated Grafana Alloy collector in the `priority-email` namespace, receives OTLP on ports `4317` and `4318`, collects Priority Email pod logs, and exports logs, metrics, and traces to Grafana Cloud using a narrow observability secret.
- `infra/k8s/deployment.yaml`: sends worker OTLP telemetry to the namespace-local Alloy service at `http://alloy.priority-email.svc.cluster.local:4318`.
- `infra/k8s/network-policy.yaml`: preserves default-deny ingress while allowing in-namespace OTLP traffic to Alloy.
- `.env.example` and `DEPLOYMENT_PLAN.md`: document the required Grafana Cloud ingest settings without exposing credentials.

### June 21, 2026: Add Poll Log Levels

Priority Email added explicit log levels for runtime and poll-audit logging.

Key evidence:

- `scripts/telemetry.py`: supports configurable runtime log-level filtering through `EMAIL_LOG_LEVEL` or `LOG_LEVEL`.
- `scripts/poll-email.py`: writes one structured poll logfile entry per provider poll, using `INFO` for successful polls and `ERROR` for failed polls.
- `scripts/poll-email.py`: emits provider failures at runtime `ERROR` level with sanitized request details, duration, Slack notification result, state/log file paths, and non-secret checkpoint state.
- `scripts/run-poller-loop.sh`: suppresses wrapper poll-cycle INFO messages when the configured log level is `ERROR`.
- `infra/k8s/deployment.yaml`: sets the production `EMAIL_LOG_LEVEL` runtime value.

### June 21, 2026: Add Provider Request RED Metrics

Priority Email added request-level rate, error, and duration metrics for email provider interactions.

Key evidence:

- `scripts/poll-email.py`: wraps Gmail API, Yahoo API, and Yahoo IMAP operations with provider request metrics.
- `scripts/poll-email.py`: emits `priority_email_provider_requests_total`, `priority_email_provider_request_errors_total`, and `priority_email_provider_request_duration_ms`.
- `tests/test_poll_email.py`: verifies provider request metrics include provider, operation, method, outcome, status, and reason labels without leaking request secrets.

### June 21, 2026: Add External Dependency RED Metrics

Priority Email broadened request-level observability from email-provider-specific calls to all outbound dependencies.

Key evidence:

- `scripts/poll-email.py`: emits `priority_email_external_dependency_requests_total`, `priority_email_external_dependency_request_errors_total`, and `priority_email_external_dependency_request_duration_ms`.
- `scripts/poll-email.py`: records Slack `chat.postMessage` success, HTTP failures, transport failures, invalid JSON responses, and Slack app-level errors such as `not_in_channel` without exposing Slack tokens.
- `tests/test_poll_email.py`: verifies generic dependency metrics for provider calls and Slack calls, including Slack app-level errors.

### June 22, 2026: Add Matched Email Slack Summaries

Priority Email implemented the missing path from sender filters to Slack summaries for newly polled messages.

Key evidence:

- `scripts/poll-email.py`: loads domain, exact email address, and sender-name filters from the mounted filter files.
- `scripts/poll-email.py`: matches sender metadata case-insensitively, posts one Slack summary per matched message, and deduplicates posts by provider/message ID within runtime state.
- `scripts/poll-email.py`: skips matched-message Slack summaries during provider initialization by default to avoid reposting the latest inspected messages after pod cold starts while state is still local to the pod.
- `tests/test_poll_email.py`: verifies filter matching, initialization skip behavior, Slack summary formatting, and duplicate-post suppression.

### June 22, 2026: Add Durable Production Poller State

Priority Email moved production checkpoint and notification-dedupe state from pod-local `/tmp` to a persistent Kubernetes volume.

Key evidence:

- `infra/k8s/state-pvc.yaml`: creates the `priority-email-state` PersistentVolumeClaim using the cluster `gp2` storage class.
- `infra/k8s/deployment.yaml`: stores `EMAIL_POLL_STATE_FILE` at `/var/lib/priority-email/email-poller-state.json` and mounts the PVC at `/var/lib/priority-email`.
- `infra/k8s/deployment.yaml`: uses `Recreate` rollout strategy so only one worker pod mounts the `ReadWriteOnce` state volume at a time.
- `scripts/aws/ensure-ebs-csi-addon.sh`: ensures the AWS managed EBS CSI add-on is active with an IRSA role before applying the state PVC.
- `scripts/kubernetes/apply-manifests.sh` and `scripts/ci/k8s-static-check.py`: apply and validate the state PVC as part of the normal deployment flow.

### June 21, 2026: Standardize Functional Change Delivery

Priority Email standardized the delivery flow for functional runtime changes: push the source commit to GitHub, wait for CI to pass, deploy the same commit to AWS, and verify the live EKS image tag.

Key evidence:

- `.github/workflows/ci.yml`: upgrades official GitHub Actions to Node 24-compatible major versions, `actions/checkout@v5` and `actions/setup-python@v6`.
- `AGENTS.md`: records that functional runtime changes require both GitHub push and AWS deploy after CI passes.
- `DEPLOYMENT_PLAN.md`: updates the deployment flow around `scripts/aws/deploy-to-aws.sh`, commit-tagged ECR images, and live image verification.
- `REQUIREMENTS.md` and `README.md`: document that documentation-only changes may stop after GitHub/CI, while functional runtime changes continue through AWS.

### June 21, 2026: Prepare For Public GitHub Visibility

The repository was redacted for public GitHub readiness by replacing personal, account, project, workspace, local-path, and private deployment identifiers in committed files with placeholders.

Key evidence:

- `.env.example`: uses blank local configuration values for AWS profile, AWS account ID, and Google Cloud project ID.
- `DEPLOYMENT_PLAN.md`, `EVOLUTION.md`, and category docs: replace real AWS account IDs, Google Cloud project IDs/numbers, local filesystem paths, private GitHub owner text, Slack workspace names, EKS cluster/profile names, ECR image hosts, image tags, and image digests with public-safe placeholders.
- `infra/k8s/deployment.yaml`: uses a non-deployable public example image placeholder; the deploy script still pins the real ECR image after build.
- `scripts/aws/*.sh`: require `AWS_PROFILE` and `AWS_ACCOUNT_ID` from local environment or gitignored `.env` instead of carrying public default account/profile values.
- Public-safety scans found no tracked real AWS account ID, Google project number, user home path, private GitHub owner URL, or private image digest.

### June 27, 2026: Make Notification Updates Deploy Immediately

Priority Email added a repository-specific notification-update skill so notification configuration changes cannot stop after editing and testing. Once unit tests pass, the agent must deploy the update to AWS in the same task and verify the live rollout and configuration.

Key evidence:

- `<team-skills>/skills/priority-email-notification-updates/SKILL.md`: defines validation, secret-safe filter handling, mandatory post-test deployment, and narrow live verification.
- `AGENTS.md`: imports the skill and makes immediate deployment mandatory for every notification configuration update.
- Filter-only changes remain uncommitted and are deployed with the current CI-green source revision, preserving the rule that real filter values never enter Git.

## Current Shape

1. `REQUIREMENTS.md` defines the product, security, provider, and platform requirements.
2. `DEPLOYMENT_PLAN.md` defines the AWS/EKS deployment path with a dedicated `priority-email` namespace.
3. `PUSH_NOTIFICATION_OPTIONS.md` captures provider comparison and recommends AWS End User Messaging Push for production.
4. `.env.example` and `.gitignore` protect local secrets and prevent accidental GitHub pushes of credentials.
5. `filters/*.txt.template` files are safe to commit, while real `filters/*.txt` values stay local.
6. Gmail OAuth has a configured Google Cloud project and OAuth clients, with secrets still expected to live only in gitignored `.env`.
7. `scripts/poll-email.py` provides the first configurable Gmail poller with checkpointed incremental polling.
8. Slack app `Priority Email` is installed in workspace `example-platform` with `chat:write`; the bot token remains a gitignored local/deployment secret.
9. `scripts/test-slack-message.py` validates Slack posting once the app is invited to the configured channel.
10. Team engineering skills, including the Priority Email notification-update workflow, are imported into `AGENTS.md` and backed by unit tests for poller behavior.
11. AWS deployment access uses the reference platform `example-platform` AWS CLI profile instead of static keys.
12. `README.md` documents the current safe local workflow for the GitHub repo.
13. `EVOLUTION.md`, `docs/evolution/categories/`, and generated Graphviz flow diagrams preserve the project chronology.
14. `Dockerfile`, AWS helper scripts, and Kubernetes manifests deploy the initial Gmail poller worker to AWS.
15. GitHub Actions now enforces a secret-safe CI quality gate before changes reach `main`.
16. Provider request failures are posted to Slack with sanitized error details.
17. Functional runtime changes are delivered by pushing to GitHub, waiting for CI, and deploying the same commit to AWS.
18. Public GitHub readiness redacts account, project, workspace, path, and deployment identifiers from tracked files.
19. Notification configuration updates must pass unit tests, deploy to AWS in the same task, and receive live rollout/configuration verification.
