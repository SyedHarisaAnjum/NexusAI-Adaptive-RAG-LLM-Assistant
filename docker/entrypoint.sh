#!/bin/sh
set -e

# Hosting platforms usually mount the persistent volume owned by root.
# Give the app user its directories, then drop root privileges.
if [ "$(id -u)" = "0" ]; then
    mkdir -p "$DATA_DIR" "$BACKUP_DIR"
    chown -R appuser:appuser "$DATA_DIR" "$BACKUP_DIR"
    exec setpriv --reuid=appuser --regid=appuser --init-groups "$@"
fi

exec "$@"
