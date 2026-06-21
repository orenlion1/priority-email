# Priority Email AWS Deployment Plan

## Reference Deployment

Use the AWS deployment pattern from `/Users/orenlion/Documents/Codex/ensemble` as the target model.

Key reference files:

- `/Users/orenlion/Documents/Codex/ensemble/skills/infrastructure/SKILLS.md`
- `/Users/orenlion/Documents/Codex/ensemble/docs/deployment.md`
- `/Users/orenlion/Documents/Codex/ensemble/infra/terraform/stacks/README.md`
- `/Users/orenlion/Documents/Codex/ensemble/infra/terraform/stacks/data/main.tf`
- `/Users/orenlion/Documents/Codex/ensemble/infra/terraform/stacks/workload-iam/main.tf`
- `/Users/orenlion/Documents/Codex/ensemble/infra/k8s/services.yaml`
- `/Users/orenlion/Documents/Codex/ensemble/infra/k8s/ingress.yaml`
- `/Users/orenlion/Documents/Codex/ensemble/infra/k8s/policies/network-policies.yaml`
- `/Users/orenlion/Documents/Codex/ensemble/scripts/kubernetes/apply-manifests.sh`
- `/Users/orenlion/Documents/Codex/priority-email/PUSH_NOTIFICATION_OPTIONS.md`

The Ensemble stack order is:

```text
network -> edge-static -> auth -> cluster -> data -> workload-iam -> kubernetes
```

Priority Email should reuse the already-established AWS substrate where appropriate: VPC, EKS, ALB ingress controller, Route53/ACM/WAF patterns, Secrets Manager, DynamoDB, IRSA, and Grafana observability hooks. It should not share the `ensemble-grafana` Kubernetes namespace or application secrets.

## Deployment Target

Deploy `priority-email-service` as a Kubernetes workload on the Ensemble EKS cluster in a dedicated `priority-email` namespace.

Current AWS deployment status:

- AWS account: `629513454417`
- AWS region: `us-east-1`
- EKS cluster: `ensemble-grafana`
- Kubernetes namespace: `priority-email`
- ECR repository: `629513454417.dkr.ecr.us-east-1.amazonaws.com/priority-email-service`
- Runtime secret path: AWS Secrets Manager `priority-email/runtime`
- Kubernetes secret: `priority-email/priority-email-secrets`
- Kubernetes ConfigMap: `priority-email/priority-email-filters`
- Deployed image tag: `d6d007c`
- Image digest: `sha256:0e6e3f1cf0273070858295514918626acb386863d0ebff9539be1db716b1b5b2`
- Live worker status: deployed as one replica in `priority-email`.

Current runtime limitation:

- The first AWS worker deployment uses the local file checkpoint backend on pod-local `/tmp`, matching the current script implementation.
- The Ensemble EKS cluster currently has no EBS CSI add-on installed, so a PVC-backed checkpoint volume could not be provisioned during the initial deploy.
- Durable AWS-hosted checkpoints remain the next data-stack step, preferably DynamoDB as already planned below.

Initial service shape:

- One backend service container.
- Dedicated Kubernetes namespace: `priority-email`.
- No public frontend required initially.
- Internal polling worker for Gmail, Yahoo Mail, and Apple iCloud Mail.
- Optional HTTP endpoints for health, metrics, and operational status.
- Slack and push notification integrations driven by secrets.
- File-based filters mounted from a Kubernetes ConfigMap for the first version.
- Preferred production push provider: AWS End User Messaging Push.

## Phase 1: Application Packaging

1. Create a service implementation with:
   - filter loading from `filters/domain-filters.txt`, `filters/email-address-filters.txt`, and `filters/sender-name-filters.txt`
   - local setup that copies `filters/*.txt.template` to ignored `filters/*.txt` value files before real filters are added
   - provider adapters for Gmail, Yahoo Mail, and iCloud Mail
   - configurable pollers for Gmail, Yahoo Mail, and iCloud Mail
   - provider checkpoints so each poll cycle only inspects messages newer than the prior successful poll
   - initialization behavior that inspects only the latest 20 messages per provider before setting the first checkpoint
   - Slack notification adapter
   - push notification adapter
   - processed-message deduplication
   - health and metrics endpoints

2. Add a `Dockerfile` following the Ensemble service pattern:
   - non-root runtime user
   - small production image
   - read-only root filesystem compatible behavior
   - `/tmp` as the only writable path
   - `.dockerignore` excludes local `.env`, real filters, OAuth client secret JSON, state, and generated secret material from the Docker build context

3. Push images to ECR using the Ensemble naming pattern:

```text
629513454417.dkr.ecr.us-east-1.amazonaws.com/priority-email-service:<version>
```

If the ECR repository does not exist, add it to the appropriate Terraform stack or create it with the same tagging conventions used by Ensemble.

Current helper scripts:

- `scripts/aws/ensure-ecr.sh`
- `scripts/aws/sync-runtime-secret.sh`
- `scripts/aws/build-and-push-image.sh`
- `scripts/kubernetes/apply-manifests.sh`
- `scripts/aws/deploy-to-aws.sh`

## Phase 2: Data Stack Changes

Extend the Ensemble `data` stack or create a new Priority Email data stack using the same pattern as `/Users/orenlion/Documents/Codex/ensemble/infra/terraform/stacks/data`.

Recommended initial DynamoDB tables:

- `priority-email-processed-messages`
  - hash key: `messageKey`
  - purpose: deduplicate processed provider/account/message combinations
  - enable point-in-time recovery
  - enable server-side encryption

- `priority-email-checkpoints`
  - hash key: `accountKey`
  - purpose: store last successful poll checkpoint per provider/account
  - enable point-in-time recovery
  - enable server-side encryption

Optional later table:

- `priority-email-notification-log`
  - hash key: `notificationId`
  - purpose: record notification attempts and failures

Use tags consistent with Ensemble:

```text
Application = "priority-email"
Stack       = "data"
Service     = "priority-email"
```

Add Terraform outputs for table names and ARNs so the workload IAM stack can consume them.

## Phase 3: Secrets

Store runtime credentials in a Priority Email-specific AWS Secrets Manager secret and sync them to a Kubernetes opaque secret in the `priority-email` namespace, matching the workflow in Ensemble's `infra/k8s/secrets.example.yaml` without reusing Ensemble's secret object.

For local development, store credentials in `.env`. Commit only `.env.example`; `.env`, `.env.*`, generated secret YAML, and Terraform variable files must remain gitignored so secrets are not pushed to GitHub.

Recommended secret names:

- AWS Secrets Manager: `priority-email/runtime`
- Kubernetes: `priority-email-secrets`

Initial secret keys:

- `AWS_PROFILE`
- `AWS_ACCOUNT_ID`
- `GMAIL_GOOGLE_CLOUD_PROJECT_ID`
- `GMAIL_CLIENT_ID`
- `GMAIL_CLIENT_SECRET`
- `GMAIL_REFRESH_TOKENS`
- `YAHOO_CLIENT_ID`
- `YAHOO_CLIENT_SECRET`
- `YAHOO_REFRESH_TOKENS`
- `ICLOUD_ACCOUNTS`
- `SLACK_BOT_TOKEN`
- `SLACK_CHANNEL_ID`
- `PUSH_PROVIDER`
- `PUSH_APPLICATION_ID`
- `PUSH_PROVIDER_TOKEN`
- `PUSH_CHANNELS_ENABLED`
- `AWS_REGION`
- `DYNAMODB_PROCESSED_MESSAGES_TABLE`
- `DYNAMODB_CHECKPOINTS_TABLE`
- `EMAIL_POLL_ENABLED_PROVIDERS`
- `EMAIL_POLL_INTERVAL_SECONDS`
- `EMAIL_POLL_INITIAL_MAX_MESSAGES`
- `EMAIL_POLL_MAX_MESSAGES`
- `EMAIL_POLL_STATE_FILE`

Do not commit real secret files. Keep only example schemas in source.

AWS credential status:

- Local AWS profile: `ensemble-grafana`
- AWS account ID: `629513454417`
- AWS region: `us-east-1`
- Credential source: local AWS CLI profile/credential chain, shared with the Ensemble deployment workflow.
- Validation command: `aws sts get-caller-identity --profile ensemble-grafana`
- Static AWS access keys must not be copied into `.env`, `.env.example`, docs, Terraform variables, or Kubernetes secrets.

Gmail OAuth setup status:

- Google Cloud project: `Priority Email`
- Google Cloud project ID: `priority-email-500114`
- OAuth consent screen app name: `Priority Email`
- OAuth 2.0 clients: Web Application and Desktop App, both named `Priority Email - OAuth client`
- Credential source: https://console.cloud.google.com/auth/clients?project=priority-email-500114
- Local status: gitignored `.env` has been populated with `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, and `GMAIL_REFRESH_TOKENS`.
- Local initialization script: `python3 scripts/init-gmail-oauth.py`
- Local read validation script: `python3 scripts/validate-gmail-read.py`
- Local Gmail poller script: `python3 scripts/poll-email.py --provider gmail`
- Local Gmail poller verbose debug command: `python3 scripts/poll-email.py --provider gmail --verbose`
- Default poll interval: `EMAIL_POLL_INTERVAL_SECONDS=600`
- Local read validation status: succeeded after enabling Gmail API for Google Cloud project number `877694096009`.
- Validation command: `python3 scripts/validate-gmail-read.py`
- Do not commit downloaded Google OAuth client secret JSON files; `.gitignore` contains `client_secret_*.apps.googleusercontent.com*`.

Slack app setup status:

- Slack app name: `Priority Email`
- Slack workspace: `ensemble-grafana`
- App creation path: Slack API `Create New App` -> `From scratch` -> select workspace `ensemble-grafana`
- OAuth scope configured: `chat:write`
- App installation status: installed to workspace
- Local status: gitignored `.env` has been populated with `SLACK_BOT_TOKEN` and `SLACK_CHANNEL_ID`.
- Local Slack test script: `python3 scripts/test-slack-message.py`
- Local Slack test status: succeeded after inviting the `Priority Email` app/bot to the configured Slack channel.
- Do not commit or document the Bot User OAuth Token value.

## Phase 4: Workload IAM

Extend the Ensemble `workload-iam` stack or create a small Priority Email workload IAM stack using the same IRSA approach as `/Users/orenlion/Documents/Codex/ensemble/infra/terraform/stacks/workload-iam/main.tf`.

Create:

- Kubernetes service account subject:

```text
system:serviceaccount:priority-email:priority-email-service
```

- IAM role:

```text
priority-email-service
```

- Narrow inline policy allowing:
  - `dynamodb:GetItem`
  - `dynamodb:PutItem`
  - `dynamodb:UpdateItem`
  - `dynamodb:DeleteItem` only if message checkpoint cleanup is required
- `secretsmanager:GetSecretValue` for the Priority Email runtime secret only
  - AWS End User Messaging Push send permissions if AWS push is enabled

Output:

- `priority_email_service_role_arn`

Use that output as the `eks.amazonaws.com/role-arn` annotation on the Kubernetes service account.

## Phase 5: Kubernetes Manifests

Add Priority Email Kubernetes manifests following Ensemble's `infra/k8s/services.yaml` baseline, but keep them in Priority Email-owned files rather than adding this workload to the Ensemble service manifest.

Create:

- `Namespace`
- `ServiceAccount`
- `Deployment`
- `Service`
- `PodDisruptionBudget`
- `ConfigMap` for initial filter files
- network policy entries

Deployment baseline:

- namespace: `priority-email`
- replicas: `1` for initial polling safety
- rolling update with `maxSurge: 1` and `maxUnavailable: 0`
- run as non-root
- drop all Linux capabilities
- disable privilege escalation
- read-only root filesystem
- mount `/tmp` as `emptyDir`
- expose app port, for example `8084`
- readiness probe: `/health/ready`
- liveness probe: `/health/live`
- metrics endpoint: `/metrics`

Namespace baseline:

- name: `priority-email`
- labels:
  - `app.kubernetes.io/part-of: priority-email`
  - `pod-security.kubernetes.io/enforce: restricted`
  - `pod-security.kubernetes.io/audit: restricted`
  - `pod-security.kubernetes.io/warn: restricted`

ConfigMap strategy:

- Create a ConfigMap named `priority-email-filters` from:
  - `filters/domain-filters.txt`
  - `filters/email-address-filters.txt`
  - `filters/sender-name-filters.txt`
- Mount it read-only into the container, for example `/app/filters`.
- Keep newest filter entries at the head of each file.
- Update filters by editing the source files, recreating/applying the ConfigMap, and restarting or rolling the deployment so the service reloads the mounted files predictably.
- Commit only `filters/*.txt.template` files to GitHub. Never commit real `filters/*.txt` values.

## Phase 6: Ingress And Routing

The service does not need public user-facing API routes at first.

Initial choice:

- Do not add `priority-email-service` to the public ALB ingress.
- Keep health and metrics reachable inside the cluster.

If an operational API is needed later, extend `/Users/orenlion/Documents/Codex/ensemble/infra/k8s/ingress.yaml` with a protected route such as:

```text
https://api.ensemble-grafana.com/api/priority-email
```

Require authentication before exposing any account, filter, message, or notification metadata.

## Phase 7: Network Policies

Create Priority Email-specific network policies in the `priority-email` namespace. Use Ensemble's `/Users/orenlion/Documents/Codex/ensemble/infra/k8s/policies/network-policies.yaml` as the reference pattern, but do not mix Priority Email selectors into Ensemble's policy file.

Initial rules:

- allow ingress to `priority-email-service` only from cluster monitoring components and, if needed, the ALB controller path
- allow metrics scraping on the service port
- preserve default-deny ingress
- scope all selectors to `app=priority-email-service` in namespace `priority-email`

Because the worker must call Gmail, Yahoo Mail, iCloud Mail, Slack, push provider APIs, DynamoDB, and Secrets Manager, egress policy should be handled carefully if default-deny egress is introduced later.

## Phase 8: Observability

Follow the Ensemble observability convention:

- add Prometheus scrape annotations or ServiceMonitor metadata
- emit service logs with `service=priority-email-service`
- emit low-cardinality metrics:
  - emails checked
  - matched emails
  - notifications sent
  - Slack post failures
  - push notification failures
  - provider polling failures
  - duplicate messages skipped
- emit traces for provider polling and notification sends if the runtime supports OTEL
- send OTEL traces to the in-cluster Alloy endpoint already used by Ensemble services

## Phase 9: Deployment Flow

Use the Ensemble deployment gate:

1. Run local tests for filter loading, matching, deduplication, and notification formatting.
2. Build the container.
3. Push the exact code revision to GitHub.
4. Wait for CI to pass.
5. Build and push the ECR image for the passing commit.
6. Apply Terraform changes in stack order:
   - data
   - workload-iam
7. Update kubeconfig:

```bash
aws eks update-kubeconfig --name ensemble-grafana --region us-east-1
```

8. Apply Kubernetes manifests:

```bash
kubectl apply -f infra/k8s/namespace.yaml
kubectl apply -f infra/k8s/priority-email-service.yaml
kubectl apply -f infra/k8s/network-policies.yaml
```

9. Verify rollout:

```bash
kubectl rollout status deployment/priority-email-service -n priority-email
kubectl logs -n priority-email deployment/priority-email-service
kubectl get pods -n priority-email -l app=priority-email-service
```

## Phase 10: Validation

Required checks:

- Unit tests pass with `python3 -m unittest discover tests`.
- domain filter `grafana.com` matches `person@grafana.com`
- exact email filter matches only the exact sender address
- sender display name filter is case-insensitive
- one email matching multiple filters sends only one Slack post and one push notification
- processed messages are recorded in DynamoDB
- service restart does not re-alert already processed messages
- missing Slack token fails closed with a clear log message
- provider auth failure does not stop other providers from polling
- Kubernetes readiness and liveness probes pass
- service logs include provider, account, message id hash, and match type without exposing full email body

## Open Decisions

- Whether the first direct-to-phone MVP uses AWS End User Messaging Push immediately or temporarily relies on Slack mobile notifications plus Pushover/ntfy until a mobile app/device-token flow exists.
- Whether iCloud Mail uses app-specific password plus IMAP or a forwarding-based workaround.
- Whether to create separate Terraform stacks for Priority Email or extend Ensemble's current `data` and `workload-iam` stacks.
