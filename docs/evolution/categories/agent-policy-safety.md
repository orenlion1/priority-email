# Agent Policy And Safety Evolution

## Timeline

| Date | Milestone | Evidence |
| --- | --- | --- |
| 2026-06-21 | `.gitignore` started protecting `.env`, generated secret files, Terraform state/vars, and local filter values. | `.gitignore` |
| 2026-06-21 | Filter values were split from committed templates so GitHub only receives `filters/*.txt.template`. | `.gitignore`, `filters/*.txt.template`, `REQUIREMENTS.md` |
| 2026-06-21 | Google OAuth client secret filename patterns were added to `.gitignore`. | `.gitignore` |
| 2026-06-21 | Ensemble's EVOLUTION policy was promoted into global Codex guidance. | `/Users/orenlion/.codex/AGENTS.md` |
| 2026-06-21 | Priority Email adopted repo-local documentation, evolution, secret-safety, and platform-standard policy. | `AGENTS.md`, `EVOLUTION.md` |
| 2026-06-21 | An Ensemble-style generated evolution flow diagram package was added. | `EVOLUTION.md`, `docs/evolution/README.md`, `docs/evolution/diagrams/` |
| 2026-06-21 | External team engineering skills were imported into repo policy and applied to poller quality/security. | `AGENTS.md`, `tests/test_poll_email.py`, `scripts/poll-email.py`, `REQUIREMENTS.md` |
| 2026-06-21 | GitHub publication created the private `orenlion1/priority-email` repo after verifying the staged set excludes local secrets, state, and real filter values. | `README.md`, `.gitignore`, `EVOLUTION.md` |
| 2026-06-21 | The CI/CD automation skill was imported and applied as a secret-safe GitHub Actions quality gate. | `AGENTS.md`, `.github/workflows/ci.yml`, `scripts/ci/` |
| 2026-06-21 | Repo policy was updated so functional runtime changes must push to GitHub, pass CI, deploy the same commit to AWS, and verify the live image. | `AGENTS.md`, `DEPLOYMENT_PLAN.md`, `.github/workflows/ci.yml` |

## Current Policy Shape

Future key milestones should update `EVOLUTION.md`, the matching category file, and generated evolution diagrams when the project flow changes. Secret and filter safety are first-class repo policy, especially before any future GitHub push.
