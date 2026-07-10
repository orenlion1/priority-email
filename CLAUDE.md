# priority-email — agent guidance

## Deployment
- **Serverless since 2026-07-10.** The poller runs as a scheduled AWS Lambda (Python 3.13),
  invoked by EventBridge Scheduler every 5 minutes; each invocation is one poll cycle. It
  replaced the looping pod on the ensemble-grafana EKS cluster, which was decommissioned in the
  ensemble-retail cost-reduction migration. State and filters live in the
  `priority-email-state-<account>` S3 bucket (was: PVC + ConfigMap). See `DEPLOYMENT_PLAN.md`.
- **Code changes ship themselves — do not deploy manually.** Every push/merge to `main` runs the
  `CI` workflow; on success the `Deploy` workflow builds the Lambda zip and runs
  `update-function-code` for the exact CI-passing commit via GitHub OIDC. Land the change on
  `main` and let the pipeline run.
- **Deploys are change-scoped.** The workflow diffs against the last deployed commit: Lambda code
  rollout when `scripts/**`, filter templates, or `deploy.yml` changed; filter sync to S3 when
  `filters/ops/**` or `scripts/filters/**` changed. Documentation-only changes stop after CI.
- **Filter updates are remote and approval-free.** Run
  `scripts/filters/add-filter-op.sh <add|remove> <kind> <value>` (encrypts with the committed
  age public key), commit the new `filters/ops/*.age` file, push to `main`. The Deploy workflow
  decrypts with the `AGE_SECRET_KEY` secret, assembles the filters, uploads them to the S3 filter
  store, and checksum-verifies — never commit plaintext filter values or the age private key.
- **Operator-only surface.** Runtime secrets and infrastructure are NOT applied by CI — sync the
  runtime secret with `scripts/aws/bootstrap-aws.sh` and provision the Lambda/S3/schedule with
  `terraform -chdir=infra/terraform apply`.
- **Placeholder policy.** Real resource identifiers (account ID, role ARN) live in GitHub
  repository secrets (`AWS_ACCOUNT_ID`, `AWS_DEPLOY_ROLE_ARN`) and the local gitignored `.env`;
  committed files must keep placeholders — the CI secret scan fails on real identifiers. The
  deploy role needs `lambda:UpdateFunctionCode`/`PublishVersion`/`GetFunction` on
  `priority-email-poller` and `s3:PutObject`/`GetObject` on the state bucket.
