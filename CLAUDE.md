# priority-email — agent guidance

## Deployment
- **Code changes ship themselves — do not deploy manually.** Every push/merge to `main` runs the
  `CI` workflow; on success the `Deploy` workflow automatically builds, pushes, and rolls out the
  exact CI-passing commit's image via GitHub OIDC. Land the change on `main` and let the
  pipeline run.
- **Deploys are change-scoped.** The workflow diffs against the last deployed commit: image
 rollout when `Dockerfile`, `scripts/**`, filter templates, or `deploy.yml` changed; live filter
 ConfigMap sync when `filters/ops/**` or `scripts/filters/**` changed. Documentation-only
 changes stop after CI.
- **Filter updates are remote and approval-free.** Run
 `scripts/filters/add-filter-op.sh <add|remove> <kind> <value>` (encrypts with the committed
 age public key), commit the new `filters/ops/*.age` file, push to `main`. The Deploy
 workflow decrypts with the `AGE_SECRET_KEY` secret, applies the ConfigMap, restarts the
 worker, and checksum-verifies — never commit plaintext filter values or the age private key.
- **Operator-only surface.** Runtime secrets, the observability secret, and infrastructure
 add-ons are NOT applied by CI — bootstrap them locally with `scripts/aws/deploy-to-aws.sh`.
- **Placeholder policy.** Real resource identifiers (account ID, cluster name, role ARN) live in
  GitHub repository secrets (`AWS_ACCOUNT_ID`, `AWS_DEPLOY_ROLE_ARN`, `EKS_CLUSTER_NAME`) and the
  local gitignored `.env`; committed files must keep placeholders — the CI secret scan fails on
  real identifiers. See `DEPLOYMENT_PLAN.md` Phase 9 for the full deployment flow.
