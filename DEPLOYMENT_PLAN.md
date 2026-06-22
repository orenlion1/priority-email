# Priority Email AWS Deployment Plan

## Reference Deployment

Use the AWS deployment pattern from `<local-ensemble-repo>` as the target model.

Key reference files:

- `<local-ensemble-repo>/skills/infrastructure/SKILLS.md`
- `<local-ensemble-repo>/docs/deployment.md`
- `<local-ensemble-repo>/infra/terraform/stacks/README.md`
- `<local-ensemble-repo>/infra/terraform/stacks/data/main.tf`
- `<local-ensemble-repo>/infra/terraform/stacks/workload-iam/main.tf`
- `<local-ensemble-repo>/infra/k8s/services.yaml`
- `<local-ensemble-repo>/infra/k8s/ingress.yaml`
- `<local-ensemble-repo>/infra/k8s/policies/network-policies.yaml`
- `<local-ensemble-repo>/scripts/kubernetes/apply-manifests.sh`
- `<local-priority-email-repo>/PUSH_NOTIFICATION_OPTIONS.md`

The reference stack order is:

```text
network -> edge-static -> auth -> cluster -> data -> workload-iam -> kubernetes
```

Priority Email should reuse the already-established AWS substrate where appropriate: VPC, EKS, ALB ingress controller, Route53/ACM/WAF patterns, Secrets Manager, DynamoDB, IRSA, and Grafana observability hooks. It should not share the `example-platform` Kubernetes namespace or application secrets.

## Deployment Target

Deploy `priority-email-service` as a Kubernetes workload on the reference EKS cluster in a dedicated `priority-email` namespace.

Current AWS deployment status:

- AWS account: `<aws-account-id>`
- AWS region: `us-east-1`
- EKS cluster: `example-platform`
- Kubernetes namespace: `priority-email`
- ECR repository: `<aws-account-id>.dkr.ecr.<aws-region>.amazonaws.com/priority-email-service`
- Runtime secret path: AWS Secrets Manager `priority-email/runtime`
- Kubernetes secret: `priority-email/priority-email-secrets`
- Kubernetes ConfigMap: `priority-email/priority-email-filters`
- Deployed image tag: `<image-tag>`
- Image digest: `<image-digest>`
- Live worker status: deployed as one replica in `priority-email`.

Current runtime limitation:

- Production checkpoint and notification-dedupe state is stored in `/var/lib/priority-email/email-poller-state.json`.
- `/var/lib/priority-email` is backed by the `priority-email-state` Kubernetes PersistentVolumeClaim using the cluster `gp2` storage class.
- The deployment uses `Recreate` so only one worker pod mounts the `ReadWriteOnce` state volume at a time.

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

2. Add a `Dockerfile` following the reference service pattern:
   - non-root runtime user
   - small production image
   - read-only root filesystem compatible behavior
   - `/tmp` for transient poll logs and `/var/lib/priority-email` for durable production poller state
   - `.dockerignore` excludes local `.env`, real filters, OAuth client secret JSON, state, and generated secret material from the Docker build context

3. Push images to ECR using the reference platform naming pattern:

```text
<aws-account-id>.dkr.ecr.<aws-region>.amazonaws.com/priority-email-service:<version>
```

If the ECR repository does not exist, add it to the appropriate Terraform stack or create it with the same tagging conventions used by the reference platform.

Current helper scripts:

- `scripts/aws/ensure-ecr.sh`
- `scripts/aws/sync-runtime-secret.sh`
- `scripts/aws/build-and-push-image.sh`
- `scripts/kubernetes/apply-manifests.sh`
- `scripts/aws/deploy-to-aws.sh`

## Phase 2: Data Stack Changes

Extend the reference platform `data` stack or create a new Priority Email data stack using the same pattern as `<local-ensemble-repo>/infra/terraform/stacks/data`.

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

Use tags consistent with the reference platform:

```text
Application = "priority-email"
Stack       = "data"
Service     = "priority-email"
```

Add Terraform outputs for table names and ARNs so the workload IAM stack can consume them.

## Phase 3: Secrets

Store runtime credentials in a Priority Email-specific AWS Secrets Manager secret and sync them to a Kubernetes opaque secret in the `priority-email` namespace, matching the workflow in reference platform's `infra/k8s/secrets.example.yaml` without reusing reference platform's secret object.

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

- Local AWS profile: `example-platform`
- AWS account ID: `<aws-account-id>`
- AWS region: `us-east-1`
- Credential source: local AWS CLI profile/credential chain, shared with the reference deployment workflow.
- Validation command: `aws sts get-caller-identity --profile example-platform`
- Static AWS access keys must not be copied into `.env`, `.env.example`, docs, Terraform variables, or Kubernetes secrets.

Gmail OAuth setup status:

- Google Cloud project: `Priority Email`
- Google Cloud project ID: `example-priority-email-project`
- OAuth consent screen app name: `Priority Email`
- OAuth 2.0 clients: Web Application and Desktop App, both named `Priority Email - OAuth client`
- Credential source: https://console.cloud.google.com/auth/clients?project=example-priority-email-project
- Local status: gitignored `.env` has been populated with `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, and `GMAIL_REFRESH_TOKENS`.
- Local initialization script: `python3 scripts/init-gmail-oauth.py`
- Local read validation script: `python3 scripts/validate-gmail-read.py`
- Local Gmail poller script: `python3 scripts/poll-email.py --provider gmail`
- Local Gmail poller verbose debug command: `python3 scripts/poll-email.py --provider gmail --verbose`
- Default poll interval: `EMAIL_POLL_INTERVAL_SECONDS=600`
- Local read validation status: succeeded after enabling Gmail API for Google Cloud project number `<google-cloud-project-number>`.
- Validation command: `python3 scripts/validate-gmail-read.py`
- Do not commit downloaded Google OAuth client secret JSON files; `.gitignore` contains `client_secret_*.apps.googleusercontent.com*`.

Slack app setup status:

- Slack app name: `Priority Email`
- Slack workspace: `example-platform`
- App creation path: Slack API `Create New App` -> `From scratch` -> select workspace `example-platform`
- OAuth scope configured: `chat:write`
- App installation status: installed to workspace
- Local status: gitignored `.env` has been populated with `SLACK_BOT_TOKEN` and `SLACK_CHANNEL_ID`.
- Local Slack test script: `python3 scripts/test-slack-message.py`
- Local Slack test status: succeeded after inviting the `Priority Email` app/bot to the configured Slack channel.
- Do not commit or document the Bot User OAuth Token value.

## Phase 4: Workload IAM

Extend the reference platform `workload-iam` stack or create a small Priority Email workload IAM stack using the same IRSA approach as `<local-ensemble-repo>/infra/terraform/stacks/workload-iam/main.tf`.

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

Add Priority Email Kubernetes manifests following reference platform's `infra/k8s/services.yaml` baseline, but keep them in Priority Email-owned files rather than adding this workload to the reference service manifest.

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

State persistence strategy:

- Create a PersistentVolumeClaim named `priority-email-state`.
- Mount it read/write at `/var/lib/priority-email`.
- Store production `EMAIL_POLL_STATE_FILE` at `/var/lib/priority-email/email-poller-state.json`.
- Use a single worker replica and a `Recreate` deployment strategy to avoid concurrent writes and EBS multi-attach conflicts.

## Phase 6: Ingress And Routing

The service does not need public user-facing API routes at first.

Initial choice:

- Do not add `priority-email-service` to the public ALB ingress.
- Keep health and metrics reachable inside the cluster.

If an operational API is needed later, extend `<local-ensemble-repo>/infra/k8s/ingress.yaml` with a protected route such as:

```text
https://api.example-platform.com/api/priority-email
```

Require authentication before exposing any account, filter, message, or notification metadata.

## Phase 7: Network Policies

Create Priority Email-specific network policies in the `priority-email` namespace. Use reference platform's `<local-ensemble-repo>/infra/k8s/policies/network-policies.yaml` as the reference pattern, but do not mix Priority Email selectors into reference platform's policy file.

Initial rules:

- allow ingress to `priority-email-service` only from cluster monitoring components and, if needed, the ALB controller path
- allow metrics scraping on the service port
- preserve default-deny ingress
- scope all selectors to `app=priority-email-service` in namespace `priority-email`

Because the worker must call Gmail, Yahoo Mail, iCloud Mail, Slack, push provider APIs, DynamoDB, and Secrets Manager, egress policy should be handled carefully if default-deny egress is introduced later.

## Phase 8: Observability

Follow the reference platform observability convention:

- run a dedicated Grafana Alloy collector in the `priority-email` namespace for Priority Email signals
- collect pod logs from the `priority-email` namespace through Alloy and export them to Grafana Cloud
- emit structured service logs with `service=priority-email-service`
- emit low-cardinality metrics:
  - provider poll cycles
  - messages checked
  - provider polling failures
  - Slack error notification outcomes
  - poll cycle duration
- emit traces for provider polling attempts
- send OTLP metrics and traces to `http://alloy.priority-email.svc.cluster.local:4318`
- keep telemetry export fail-open so collector issues do not block email polling

Current implementation:

- `scripts/telemetry.py` emits structured JSON logs, OTLP metrics, and OTLP traces without adding runtime package dependencies.
- `infra/k8s/alloy.yaml` deploys Grafana Alloy with OTLP HTTP/gRPC receivers, Kubernetes pod log collection for the `priority-email` namespace, and Grafana Cloud OTLP export.
- `infra/k8s/deployment.yaml` configures the worker with `OTEL_SERVICE_NAME=priority-email-service` and the namespace-local Alloy endpoint.
- `infra/k8s/network-policy.yaml` allows in-namespace OTLP ingress to Alloy while preserving default-deny ingress.
- `.env` must provide `GRAFANA_CLOUD_OTLP_ENDPOINT`, `GRAFANA_CLOUD_INSTANCE_ID`, and `GRAFANA_CLOUD_API_KEY`; the deploy script copies only those keys into the narrow `priority-email-observability-secrets` Kubernetes secret for Alloy.

## Phase 9: Deployment Flow

Use the reference deployment gate. Functional runtime changes must move through both GitHub and AWS: push the exact source commit to GitHub, wait for CI to pass, deploy that same commit to AWS, and verify that the live Kubernetes image tag matches the commit SHA. Documentation-only changes may stop after GitHub and CI.

1. Run local tests for filter loading, matching, deduplication, and notification formatting.
2. Build the container.
3. Push the exact code revision to GitHub.
4. Wait for CI to pass.
5. For functional runtime changes, run:

```bash
scripts/aws/deploy-to-aws.sh
```

6. Confirm the deploy script built and pushed the ECR image for the passing commit.
7. Apply Terraform changes in stack order when infrastructure changes require it:
   - data
   - workload-iam
8. Update kubeconfig when needed:

```bash
aws eks update-kubeconfig --name example-platform --region us-east-1
```

9. Apply Kubernetes manifests manually only when not using the deploy script:

```bash
kubectl apply -f infra/k8s/namespace.yaml
kubectl apply -f infra/k8s/serviceaccount.yaml
kubectl apply -f infra/k8s/network-policy.yaml
kubectl apply -f infra/k8s/deployment.yaml
kubectl apply -f infra/k8s/poddisruptionbudget.yaml
```

10. Verify rollout:

```bash
kubectl rollout status deployment/priority-email-service -n priority-email
kubectl logs -n priority-email deployment/priority-email-service
kubectl get deployment priority-email-service -n priority-email -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
kubectl get pods -n priority-email -l app.kubernetes.io/name=priority-email-service
```

## Phase 10: Validation

Required checks:

- Unit tests pass with `python3 -m unittest discover tests`.
- domain filter `example.com` matches `sender@example.com`
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
- Whether to create separate Terraform stacks for Priority Email or extend reference platform's current `data` and `workload-iam` stacks.
