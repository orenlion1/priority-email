# Priority Email

Priority Email monitors connected mail accounts for important sender matches, then alerts through Slack and eventually phone push notifications.

## Current Status

- Gmail OAuth is configured and metadata read validation succeeds.
- Gmail polling is implemented with checkpointed incremental reads.
- Yahoo Mail and Apple iCloud Mail pollers are stubbed for future implementation.
- Slack posting is validated through the `Priority Email` Slack app.
- AWS deployment planning targets the Ensemble AWS account through the `ensemble-grafana` AWS CLI profile.
- Observability is standardized on Grafana Labs tooling and services.

## Local Commands

```bash
python3 -m unittest discover tests
python3 scripts/validate-gmail-read.py
python3 scripts/poll-email.py --provider gmail
python3 scripts/test-slack-message.py
```

Use `--verbose` with the Gmail poller only when message metadata is needed for debugging:

```bash
python3 scripts/poll-email.py --provider gmail --verbose
```

## Secrets And Filters

Do not commit local secrets or real filter values.

- Copy `.env.example` to `.env` for local secrets.
- Commit only `filters/*.txt.template`.
- Keep real filter values in ignored `filters/*.txt` files.
- Keep Google OAuth client secret JSON files local and ignored.
- Use `AWS_PROFILE=ensemble-grafana`; do not copy static AWS access keys into this repo.

## Documentation

- [Requirements](REQUIREMENTS.md)
- [Deployment Plan](DEPLOYMENT_PLAN.md)
- [Push Notification Options](PUSH_NOTIFICATION_OPTIONS.md)
- [Evolution](EVOLUTION.md)
- [Agent Policy](AGENTS.md)
