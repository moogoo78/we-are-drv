#!/bin/sh
set -e
chown -R app:app /app/uploads /app/data
exec su-exec app "$@"
