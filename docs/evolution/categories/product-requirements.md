# Product And Requirements Evolution

## Timeline

| Date | Milestone | Evidence |
| --- | --- | --- |
| 2026-06-21 | Initial requirements defined Priority Email as a service for surfacing important messages from Gmail and Yahoo Mail. | `REQUIREMENTS.md` |
| 2026-06-21 | Apple iCloud Mail was added as a supported provider. | `REQUIREMENTS.md` |
| 2026-06-21 | Sender filtering was scoped to display name, exact email address, and domain. | `REQUIREMENTS.md`, `filters/` |
| 2026-06-21 | Platform standards were added: Grafana Labs for observability and AWS for cloud resources. | `REQUIREMENTS.md` |
| 2026-06-21 | Push provider selection became an architecture and cost requirement requiring primary-source verification. | `REQUIREMENTS.md`, `PUSH_NOTIFICATION_OPTIONS.md` |
| 2026-06-21 | Email provider request failures must post sanitized error details to Slack when Slack error notifications are enabled. | `REQUIREMENTS.md`, `scripts/poll-email.py` |

## Current Product Shape

Priority Email monitors connected Gmail, Yahoo Mail, and Apple iCloud Mail accounts. Matching messages trigger phone push notifications and Slack summaries. Initial filtering uses separate local text files for domains, exact sender email addresses, and sender display names. Email provider request failures surface in Slack with sanitized diagnostic detail.
