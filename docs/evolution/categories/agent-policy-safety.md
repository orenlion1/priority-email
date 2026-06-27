# Agent Policy And Safety Evolution

## Timeline

| Date | Milestone | Evidence |
| --- | --- | --- |
| 2026-06-21 | `.gitignore` started protecting `.env`, generated secret files, Terraform state/vars, and local filter values. | `.gitignore` |
| 2026-06-21 | Filter values were split from committed templates so GitHub only receives `filters/*.txt.template`. | `.gitignore`, `filters/*.txt.template`, `REQUIREMENTS.md` |
| 2026-06-21 | Google OAuth client secret filename patterns were added to `.gitignore`. | `.gitignore` |
| 2026-06-21 | Reference platform EVOLUTION policy was promoted into global Codex guidance. | `<codex-home>/AGENTS.md` |
| 2026-06-21 | Priority Email adopted repo-local documentation, evolution, secret-safety, and platform-standard policy. | `AGENTS.md`, `EVOLUTION.md` |
| 2026-06-21 | An reference-style generated evolution flow diagram package was added. | `EVOLUTION.md`, `docs/evolution/README.md`, `docs/evolution/diagrams/` |
| 2026-06-21 | External team engineering skills were imported into repo policy and applied to poller quality/security. | `AGENTS.md`, `tests/test_poll_email.py`, `scripts/poll-email.py`, `REQUIREMENTS.md` |
| 2026-06-21 | GitHub publication created the `example/priority-email` repo after verifying the staged set excludes local secrets, state, and real filter values. | `README.md`, `.gitignore`, `EVOLUTION.md` |
| 2026-06-21 | The CI/CD automation skill was imported and applied as a secret-safe GitHub Actions quality gate. | `AGENTS.md`, `.github/workflows/ci.yml`, `scripts/ci/` |
| 2026-06-21 | Repo policy was updated so functional runtime changes must push to GitHub, pass CI, deploy the same commit to AWS, and verify the live image. | `AGENTS.md`, `DEPLOYMENT_PLAN.md`, `.github/workflows/ci.yml` |
| 2026-06-21 | Public GitHub readiness redacted personal, account, project, workspace, local-path, and private deployment identifiers from tracked files. | `.env.example`, `DEPLOYMENT_PLAN.md`, `EVOLUTION.md`, `infra/k8s/deployment.yaml`, `scripts/aws/` |
| 2026-06-27 | A Priority Email-specific skill made post-test AWS deployment and live verification mandatory for every notification configuration update while keeping real filter values uncommitted. | `<team-skills>/skills/priority-email-notification-updates/SKILL.md`, `AGENTS.md`, `EVOLUTION.md` |

## Current Policy Shape

Future key milestones should update `EVOLUTION.md`, the matching category file, and generated evolution diagrams when the project flow changes. Secret, filter, and public-identifier safety are first-class repo policy. Notification configuration changes must pass tests, deploy immediately, and be verified live without exposing private values.
