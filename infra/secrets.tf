# Secret CONTAINERS only. Values are set out-of-band (operator, not CI), so the
# plaintext never lands in Terraform state -- the state bucket is shared across
# repos in this account.
#
# The runtime secret (priority-email/runtime) is deliberately NOT here: it is
# owned by scripts/aws/sync-runtime-secret.sh and referenced by literal ARN in
# poller.tf. Only the Slack-handler secrets, new with the command bot, are
# managed as containers.
#
# Populate after apply (operator role, never CI):
#   read -rs V && aws secretsmanager put-secret-value \
#     --secret-id priority-email/<name> --secret-string "$V" \
#     --region us-east-1 && unset V

resource "aws_secretsmanager_secret" "slack_signing_secret" {
  name        = "priority-email/slack-signing-secret"
  description = "Slack signing secret, verified on every request to the Slack events Function URL."
}

resource "aws_secretsmanager_secret" "slack_bot_token" {
  name        = "priority-email/slack-bot-token"
  description = "Slack bot token the events handler uses to reply in the management channel."
}
