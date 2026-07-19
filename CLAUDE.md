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
- **Infrastructure is applied by CI, not laptops.** Terraform runs in GitHub Actions under scoped
  OIDC roles (orenlion1 standard — see core-infra `docs/standards/terraform-ci-oidc.md`): the
  `Infra Apply` workflow plans on every PR touching `infra/terraform/**` (read-only role) and
  applies on `main` under a write role that is only assumable from the required-reviewer
  `terraform-apply` environment. Lambda **code** still ships via the `Deploy` workflow's
  `update-function-code`; Terraform ignores the function's zip, so an infra apply never rolls code.
  Terraform state lives in the shared `ensemble-grafana-tf-state-<account>` bucket (key
  `stacks/priority-email/terraform.tfstate`, S3-native `use_lockfile` locking) that core-infra owns.
- **Operator surface (bootstrap + runtime secret only).** Sync the runtime secret with
  `scripts/aws/bootstrap-aws.sh`. Terraform's CI roles are created by a one-time laptop apply that
  bootstraps them (they can't exist before the first run); after it, set the `AWS_PLAN_ROLE_ARN` /
  `AWS_APPLY_ROLE_ARN` / `TF_STATE_BUCKET` repo variables and CI owns apply thereafter:

  ```bash
  terraform -chdir=infra/terraform init \
    -backend-config="bucket=ensemble-grafana-tf-state-<account>" \
    -backend-config="region=us-east-1" \
    -backend-config="use_lockfile=true"
  terraform -chdir=infra/terraform apply    # creates the plan + apply roles
  gh variable set AWS_PLAN_ROLE_ARN  --body "$(terraform -chdir=infra/terraform output -raw terraform_plan_role_arn)"
  gh variable set AWS_APPLY_ROLE_ARN --body "$(terraform -chdir=infra/terraform output -raw terraform_apply_role_arn)"
  ```
- **Placeholder policy.** Real resource identifiers (account ID, role ARN) live in GitHub
  repository secrets (`AWS_ACCOUNT_ID`, `AWS_DEPLOY_ROLE_ARN`) and the local gitignored `.env`;
  committed files must keep placeholders — the CI secret scan fails on real identifiers. The
  deploy role needs `lambda:UpdateFunctionCode`/`PublishVersion`/`GetFunction` on
  `priority-email-poller` and `s3:PutObject`/`GetObject` on the state bucket.
