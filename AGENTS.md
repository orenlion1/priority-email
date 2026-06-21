# Priority Email Agent Policy

This repository follows the global Codex evolution-history policy in `/Users/orenlion/.codex/AGENTS.md`.

## Imported Team Skills

Apply these external team skills when working in this repository:

- `/Users/orenlion/Documents/Codex/team skills eval/agent-skills/skills/spec-driven-development/SKILL.md`
- `/Users/orenlion/Documents/Codex/team skills eval/agent-skills/skills/test-driven-development/SKILL.md`
- `/Users/orenlion/Documents/Codex/team skills eval/agent-skills/skills/code-review-and-quality/SKILL.md`
- `/Users/orenlion/Documents/Codex/team skills eval/agent-skills/skills/code-simplification/SKILL.md`
- `/Users/orenlion/Documents/Codex/team skills eval/agent-skills/skills/security-and-hardening/SKILL.md`
- `/Users/orenlion/Documents/Codex/team skills eval/agent-skills/skills/git-workflow-and-versioning/SKILL.md`

Applied working rules:

- Keep `REQUIREMENTS.md` as the living specification before significant implementation changes.
- Add tests before or alongside new behavior; use `python3 -m unittest discover tests` for local Python logic.
- Review changes across correctness, readability, architecture, security, and performance before considering them ready.
- Prefer simple standard-library code and avoid dependencies unless they earn their cost.
- Treat every external API response, email header, Slack response, and config file as untrusted input.
- Never print or commit tokens, OAuth client secrets, refresh tokens, real filter values, or `.env` contents.
- Keep changes small and separately reviewable; do not mix large refactors with feature work.

## Required Documentation Updates

- Update `REQUIREMENTS.md` when product behavior, provider scope, security requirements, platform standards, or filter semantics change.
- Update `DEPLOYMENT_PLAN.md` when AWS, Kubernetes, namespace, IAM, secrets, ConfigMap, observability, rollout, or validation behavior changes.
- Update `PUSH_NOTIFICATION_OPTIONS.md` when push provider status, pricing, lifecycle, or recommendation changes. Verify provider pricing and support status from primary sources where possible.
- Update `EVOLUTION.md` whenever a change becomes a key project milestone, changes the end-to-end build or deployment story, adds or revises repo policy, changes secret-handling rules, records notable operational evidence, or changes how Priority Email should be explained from first prompt to current state.
- Update the matching file under `docs/evolution/categories/` whenever `EVOLUTION.md` changes because of timeline content.

## Secret And Filter Safety

- Never commit `.env`, `.env.*`, real OAuth client secret files, generated secret YAML, Terraform variable files, or real filter value files.
- Commit only `.env.example` and `filters/*.txt.template` files.
- If a secret-like file is discovered in the worktree, add an ignore pattern before any future GitHub push and mention the risk in the work summary.

## Platform Standards

- Standardize observability on Grafana Labs tooling and services.
- Standardize cloud infrastructure, compute, storage, secrets, IAM, networking, and managed runtime resources on AWS.
- Keep Priority Email segregated from Ensemble application runtime resources by using a dedicated `priority-email` Kubernetes namespace and service-specific secrets.
