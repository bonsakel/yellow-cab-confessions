#!/usr/bin/env bash
set -euo pipefail

secret_file=/run/airflow-secrets/jwt_secret
if [[ ! -s "$secret_file" ]]; then
    echo "Airflow JWT secret is missing; start the airflow-secrets-init service first." >&2
    exit 1
fi

export AIRFLOW__API_AUTH__JWT_SECRET="$(cat "$secret_file")"
exec /entrypoint "$@"
