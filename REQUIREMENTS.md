# Priority Email Requirements

## Overview

Priority Email helps users avoid missing important messages that are buried across personal or work email accounts. The system monitors connected Gmail, Yahoo Mail, and Apple iCloud Mail accounts, matches incoming email against user-defined sender filters, sends a push notification to the user's phone, and posts a Slack summary with links back to the matching email.

## Goals

- Detect important email across Gmail, Yahoo Mail, and Apple iCloud Mail accounts.
- Support simple sender-based filter criteria by display name, email address, or domain.
- Notify the user quickly on their phone when an important message arrives.
- Post a concise summary to Slack with links to the matching email.
- Make it easy to add, edit, pause, and remove filters.

## Current Implementation Status

- Gmail OAuth is configured through Google Cloud project `example-priority-email-project`.
- Gmail API metadata read validation has succeeded without printing tokens or full email body content.
- The Gmail poller is implemented in `scripts/poll-email.py`.
- The Gmail poller stores local checkpoint state in `.state/email-poller-state.json`.
- The first Gmail poller initialization inspected exactly the latest 20 messages and set a checkpoint.
- Subsequent Gmail poller runs only process messages newer than the checkpoint.
- Incremental Gmail polling pages through all messages newer than the prior checkpoint; `EMAIL_POLL_MAX_MESSAGES` controls page size, not a total-message cap.
- The Gmail poller prints counts and checkpoints by default; message metadata is printed only when `--verbose` is passed.
- Yahoo Mail and Apple iCloud Mail pollers are planned and currently stubbed.
- Slack app `Priority Email` is installed in workspace `example-platform` with `chat:write`.
- Slack posting validation has succeeded through `scripts/test-slack-message.py`.
- Slack summaries are implemented for incremental messages that match sender-name, exact email address, or domain filters.
- Provider initialization skips matched-message Slack summaries by default to avoid reposting the latest inspected messages after cold starts.
- Priority Email emits structured JSON logs with `service=priority-email-service`.
- Priority Email emits OTLP metrics and traces for provider poll cycles.
- Priority Email Kubernetes manifests include a dedicated namespace-local Grafana Alloy collector that receives OTLP and collects pod logs from the `priority-email` namespace.
- Local runtime secrets live in gitignored `.env`; `.env.example` is the committed-safe template.
- AWS access uses the local AWS CLI profile `example-platform` for account `<aws-account-id>`; static AWS access keys must not be copied into this repo.
- Real filter values live in gitignored `filters/*.txt`; only `filters/*.txt.template` files are safe to push to GitHub.
- Evolution history is tracked in `EVOLUTION.md`, category files, and generated Graphviz flow diagrams under `docs/evolution/diagrams/`.
- Team skills for spec-driven development, test-driven development, code review, simplification, security hardening, and git workflow are imported into `AGENTS.md`.

## Platform Standards

- Observability must be standardized on Grafana Labs tooling and services.
- Cloud infrastructure, compute, storage, secrets, IAM, networking, and managed runtime resources must be standardized on AWS.
- Non-AWS resources should be used only when required by an external integration, such as Gmail, Yahoo Mail, Apple iCloud Mail, Slack, APNs, or Firebase Cloud Messaging credentials.
- Any exception to the AWS resource standard must be documented with the reason, cost impact, security impact, and operational ownership.

## Non-Goals

- Full email client functionality such as composing, replying, archiving, or labeling email.
- Complex content-based classification or machine learning prioritization in the initial version.
- Support for providers other than Gmail, Yahoo Mail, and Apple iCloud Mail in the initial version.
- Team-wide shared inbox management.

## Users

- A user who receives important messages across multiple email accounts.
- A user who wants a phone notification only for email matching specific sender criteria.
- A user or team that wants a Slack channel to show a running summary of priority messages.

## Email Account Requirements

### Polling

- Each email provider must have its own configurable poller.
- The default poll interval must be 10 minutes.
- Pollers must store a provider-specific checkpoint after every successful poll cycle.
- After a provider checkpoint exists, each poll cycle must only inspect messages newer than the prior checkpoint.
- When initializing a provider poller with no prior checkpoint, the poller must inspect only the latest 20 email messages before setting the first checkpoint.
- The initial latest-message inspection limit must be configurable, with `20` as the default.
- Incremental pollers must not skip older-but-still-new messages when a provider returns paginated results.
- Poller logs must avoid printing email metadata unless explicitly requested for debugging or validation.
- Each provider poll attempt must append one structured JSON line to the configured poll logfile without including OAuth secrets, authorization headers, full email content, or verbose email metadata.
- Successful provider poll attempts must be recorded at `INFO` level in the poll logfile.
- Provider poll failures must emit `ERROR` level runtime logs with enough sanitized context for debugging, including provider, duration, sanitized request details, Slack error notification outcome, state/log file paths, and non-secret checkpoint state.
- Runtime stdout logging must be configurable by log level, and production must default to `ERROR`.
- If a request to an email provider fails, the poller must post an error notification to Slack with the provider name, sanitized request URL, HTTP status when available, reason, and truncated response details.
- Provider error notifications must never include OAuth tokens, refresh tokens, client secrets, authorization headers, or full email content.
- Provider error notifications should be configurable so they can be disabled for local troubleshooting.

## Development Quality Requirements

- Use spec-driven development for significant behavior, architecture, provider, deployment, or security changes.
- Use test-driven development for new logic and bug fixes.
- Code review must cover correctness, readability, architecture, security, and performance.
- Security review must treat provider responses, email headers, Slack responses, config files, and local state as untrusted data.
- CI must run on pull requests and pushes to `main`.
- CI must verify Python syntax, unit tests, shell syntax, Kubernetes manifest safety checks, secret/path safety checks, and Docker image buildability.
- CI must not require production secrets, real filter values, OAuth refresh tokens, Slack tokens, or AWS credentials.
- Functional runtime changes must be pushed to GitHub and then deployed to AWS after CI passes, using the same Git commit SHA for the ECR image tag and live Kubernetes deployment.
- GitHub Actions should use Node 24-compatible official actions where available.
- Prefer standard-library and existing project utilities before adding dependencies.
- Keep local verification commands documented and repeatable.
- Current Python test command: `python3 -m unittest discover tests`.

### Gmail

- The system must allow a user to connect one or more Gmail accounts.
- The system must request only the permissions needed to read message metadata and generate links to matching messages.
- The system must monitor newly received email after the account is connected.
- The system should avoid re-alerting for messages that were already processed.

### Yahoo Mail

- The system must allow a user to connect one or more Yahoo Mail accounts.
- The system must request only the permissions needed to read message metadata and generate links to matching messages.
- The system must monitor newly received email after the account is connected.
- The system should avoid re-alerting for messages that were already processed.

### Apple iCloud Mail

- The system must allow a user to connect one or more Apple iCloud Mail accounts.
- The system must request only the credentials or permissions needed to read message metadata and generate links to matching messages.
- The system must monitor newly received email after the account is connected.
- The system should avoid re-alerting for messages that were already processed.
- If iCloud Mail requires app-specific passwords or IMAP-based access, the setup flow must clearly guide the user through the required credential steps.

## Filter Requirements

Users must be able to create sender filters using one or more of the following criteria:

- Sender display name, such as `Jane Smith`.
- Exact sender email address, such as `jane.smith@example.com`.
- Sender email domain, such as `@example.com`.

### Matching Rules

- Display name matching should be case-insensitive.
- Email address matching should be case-insensitive and exact after trimming whitespace.
- Domain matching should be case-insensitive and match the sender email domain.
- A domain filter may be entered with or without a leading `@`; for example, `example.com` and `@example.com` should be treated as equivalent.
- A message should match if any active filter matches the sender.
- Duplicate alerts should not be sent when the same message matches multiple filters.

### Filter Management

- Users must be able to add a filter.
- Users must be able to edit a filter.
- Users must be able to delete a filter.
- Users must be able to pause or disable a filter without deleting it.
- Each filter should have an optional label so notifications can explain why a message matched.

### Initial Filter Storage

- The initial version should keep configuration simple by storing filter criteria in separate plain text files.
- Domain filters should be stored in `filters/domain-filters.txt`.
- Exact sender email address filters should be stored in `filters/email-address-filters.txt`.
- Sender display name filters should be stored in `filters/sender-name-filters.txt`.
- Real local filter value files must be gitignored and must not be pushed to GitHub.
- GitHub should receive only safe filter templates:
  - `filters/domain-filters.txt.template`
  - `filters/email-address-filters.txt.template`
  - `filters/sender-name-filters.txt.template`
- Local setup should copy the template files to the corresponding `.txt` files before adding real filter values.
- Each non-empty, non-comment line should represent one filter value.
- New filter entries should be appended at the head of the relevant file so the latest additions appear first.
- The system should normalize whitespace and ignore blank lines or lines beginning with `#`.

## Notification Requirements

### Phone Push Notification

When a new email matches an active filter, the system must send a push notification to the user's phone.

The push notification should include:

- Sender name or email address.
- Email subject.
- Email account or provider where the message was received.
- A short indication of which filter matched, when available.
- A link or deep link that opens the original email when possible.

### Push Provider Selection

- The push notification provider choice must be treated as an architecture and cost decision, not only a configuration detail.
- Before selecting or changing the push notification provider, the current provider status, support lifecycle, free tier, and pricing must be verified from primary sources where possible.
- AWS-native resources should be preferred when they simplify deployment, security, observability, and cost management.
- AWS provider options should receive extra scrutiny because the choice affects IAM, Terraform, Kubernetes runtime configuration, CloudWatch/CloudTrail visibility, and long-term operating cost.
- Provider recommendations and source links must be captured in project documentation, such as `PUSH_NOTIFICATION_OPTIONS.md`.

### Slack Summary

When a new email matches an active filter, the system must post a summary to the configured Slack destination.

The Slack summary should include:

- Sender name and email address.
- Email subject.
- Received timestamp.
- Source email account or provider.
- Matching filter label or criteria.
- Direct link to the email when supported by the provider.

The system must support selecting a Slack workspace and channel during setup.

Provider initialization should not post matched-message Slack summaries by default, because initialization is a checkpoint/bootstrap step rather than a new-message notification flow. Operators may explicitly enable initialization summaries for backfill validation.

## Email Link Requirements

- Gmail links should open the matching message in Gmail when the user has access.
- Yahoo Mail links should open the matching message in Yahoo Mail when the user has access.
- Apple iCloud Mail links should open the matching message in iCloud Mail when the user has access.
- If a direct provider link cannot be generated, the Slack summary and push notification should still include enough metadata for the user to find the email manually.

## Configuration Requirements

The user must be able to configure:

- Connected Gmail accounts.
- Connected Yahoo Mail accounts.
- Connected Apple iCloud Mail accounts.
- Slack workspace and channel.
- Phone push notification destination.
- Sender filters through the initial plain text filter files.
- Whether Slack posting is enabled.
- Whether phone push notifications are enabled.

## Security And Privacy Requirements

- Local development secrets must be stored in `.env`.
- `.env` and other local secret files must be gitignored so secrets are not pushed to GitHub when the repository is eventually published.
- A safe `.env.example` file should be committed with placeholder keys and no real secret values.
- AWS credentials should use profile or SSO-based local credential resolution. Do not store `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, or `AWS_SESSION_TOKEN` in project files.
- The system must store OAuth tokens securely.
- The system must not store full email bodies unless explicitly required by a future feature.
- The system should store only metadata needed for matching, deduplication, notification, and audit history.
- The system must allow users to disconnect an email account.
- The system must allow users to disconnect Slack.
- The system must delete or invalidate stored credentials when an integration is disconnected.

## Reliability Requirements

- The system should process new email within a few minutes of arrival.
- The system must retry transient failures when checking email, sending push notifications, or posting to Slack.
- The system must log failed notification attempts for troubleshooting.
- The system should avoid duplicate notifications for the same message.
- The system should continue monitoring other connected accounts if one provider has an error.

## Observability Requirements

- Observability must use Grafana Labs tooling and services.
- Runtime logs must be structured JSON and include `service=priority-email-service`.
- Kubernetes pod logs for Priority Email must be collected by Grafana Alloy.
- Metrics and traces must be emitted through OpenTelemetry Protocol.
- The worker must emit low-cardinality metrics for provider poll cycles, provider request failures, Slack error notification outcomes, messages checked, and poll cycle duration.
- Each request to an email provider must emit RED-style metrics with a provider label, low-cardinality operation label, method label, outcome label, status label, and reason label.
- Each request to an external dependency, including email providers, Slack, push notification providers, and AWS service integrations added later, must emit RED-style metrics with a dependency label, low-cardinality operation label, method label, outcome label, status label, and reason label.
- Traces must include one provider polling span per provider poll attempt.
- Telemetry export must be fail-open so a collector or Grafana Cloud outage does not stop email polling.
- Grafana Cloud ingest credentials must be stored only in local `.env`, AWS Secrets Manager, and the namespace-local observability Kubernetes secret; they must not be committed.
- Priority Email observability components must remain isolated in the `priority-email` Kubernetes namespace unless a future shared collector design is explicitly documented.

## Acceptance Criteria

- Given a connected Gmail account and an active domain filter for `@example.com`, when a new email arrives from `sender@example.com`, then the user receives a phone push notification and a Slack summary is posted with a link to the email.
- Given a connected Yahoo Mail account and an active exact email filter for `alerts@example.com`, when a new email arrives from `alerts@example.com`, then the user receives a phone push notification and a Slack summary is posted with a link to the email when available.
- Given a connected Apple iCloud Mail account and an active domain filter for `example.com`, when a new email arrives from `sender@example.com`, then the user receives a phone push notification and a Slack summary is posted with a link to the email when available.
- Given an active display name filter for `Jane Smith`, when a new email arrives from a sender whose display name is `jane smith`, then the message matches case-insensitively.
- Given a message matches both a domain filter and an exact email filter, then only one phone push notification and one Slack summary are sent for that message.
- Given a filter is disabled, when a matching email arrives, then no phone push notification or Slack summary is sent because of that filter.
- Given Slack posting is disabled, when a matching email arrives, then the phone push notification is still sent if phone notifications are enabled.
- Given phone notifications are disabled, when a matching email arrives, then the Slack summary is still posted if Slack posting is enabled.

## Open Questions

- Which phone push notification mechanism should be used: native iOS app, Android app, Pushover, Pushbullet, ntfy, or another provider?
- Should Slack summaries be posted as one message per email or batched into periodic digests?
- Should users be able to filter by recipient account in addition to sender?
- Should the system include email snippets in notifications, or only metadata?
- Should filters support allowlists, blocklists, or priority levels in a later version?
- What is the preferred iCloud Mail integration method: app-specific password with IMAP, another Apple-supported access path, or manual forwarding?
