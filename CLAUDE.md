# priority-email — agent guidance

## Deployment
- **Code changes ship themselves — do not deploy manually.** Every push/merge to `main` runs the
  `CI` workflow; on success the `Deploy` workflow automatically builds, pushes, and rolls out the
  exact CI-passing commit's image via GitHub OIDC. Land the change on `main` and let the
  pipeline run.
- **Deploys are change-scoped.** The workflow diffs against the last deployed commit and only
  rolls out when image-affecting paths changed: `Dockerfile`, `scripts/**`, `filters/**`, or
  `deploy.yml` itself. Documentation-only changes stop after CI.
- **Operator-only surface.** Runtime secrets, filter values, the observability secret, and
  infrastructure add-ons are NOT applied by CI — bootstrap them locally with
  `scripts/aws/deploy-to-aws.sh`.
- **Placeholder policy.** Real resource identifiers (account ID, cluster name, role ARN) live in
  GitHub repository secrets (`AWS_ACCOUNT_ID`, `AWS_DEPLOY_ROLE_ARN`, `EKS_CLUSTER_NAME`) and the
  local gitignored `.env`; committed files must keep placeholders — the CI secret scan fails on
  real identifiers. See `DEPLOYMENT_PLAN.md` Phase 9 for the full deployment flow.
