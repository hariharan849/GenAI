#!/bin/bash
set -e

# Run schema migration ONLY for the daemon — it starts after postgres is healthy
# and the webserver depends on service_started so migration completes first.
# dagster instance migrate is idempotent; safe to run on every daemon restart.
if [ "${SERVICE}" = "daemon" ]; then
  dagster instance migrate
fi

case "${SERVICE}" in
  code-server)
    exec dagster code-server start -h 0.0.0.0 -p 4000 -f definitions.py
    ;;
  webserver)
    exec dagster-webserver -h 0.0.0.0 -p 3000 -w /app/workspace.yaml
    ;;
  daemon)
    exec dagster-daemon run
    ;;
  *)
    echo "Unknown SERVICE: ${SERVICE}" >&2
    exit 1
    ;;
esac
