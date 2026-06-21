FROM python:3.14-slim

RUN useradd --system --uid 10001 --create-home appuser

WORKDIR /app
COPY --chown=appuser:appuser scripts/ /app/scripts/
COPY --chown=appuser:appuser filters/*.txt.template /app/filters/

RUN chmod +x /app/scripts/run-poller-loop.sh

USER 10001

ENV EMAIL_POLL_STATE_FILE=/tmp/email-poller-state.json

ENTRYPOINT ["/app/scripts/run-poller-loop.sh"]
