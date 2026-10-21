#!/bin/sh
# Restore a backup made by ops/backup.sh.
#
#   ./ops/restore.sh backups/nexa-db-20261022T090000Z.dump                 # into a NEW database
#   CONFIRM=yes ./ops/restore.sh <dump> --replace                          # over the live database
#   ./ops/restore.sh <dump> --uploads backups/nexa-uploads-<stamp>.tar.gz  # also restore documents
#
# Without --replace the dump is restored into a separate database (default `nexa_restore`, set
# TARGET_DB to change it), which never touches live data. With --replace the live database is
# DROPPED and recreated from the archive; you must confirm with CONFIRM=yes. Stop the backend and
# worker first, and start them again afterwards: the backend applies any migrations newer than
# the backup when it starts.
#
# The archive holds the table grants for the read-only SQL role but not the role itself (roles
# belong to the PostgreSQL cluster, not the database). On a fresh server the script therefore
# creates it first, with the same settings as migration 0001, from SQL_READONLY_USER (default
# nexa_readonly) and SQL_READONLY_PASSWORD, which must match the application's configuration.
set -eu

COMPOSE_CMD=${COMPOSE_CMD:-docker compose}
DUMP=""
UPLOADS=""
REPLACE=0

while [ $# -gt 0 ]; do
    case "$1" in
        --replace) REPLACE=1 ;;
        --uploads) shift; UPLOADS=${1:?--uploads needs a file} ;;
        -*) echo "Unknown option: $1" >&2; exit 2 ;;
        *) DUMP=$1 ;;
    esac
    shift
done

[ -n "$DUMP" ] || { echo "Usage: $0 <dump-file> [--replace] [--uploads <tar.gz>]" >&2; exit 2; }
[ -f "$DUMP" ] || { echo "No such file: $DUMP" >&2; exit 2; }

live_db=$($COMPOSE_CMD exec -T postgres sh -c 'printf %s "$POSTGRES_DB"')
if [ "$REPLACE" -eq 1 ]; then
    TARGET_DB=$live_db
    if [ "${CONFIRM:-}" != "yes" ]; then
        echo "This will DROP the live database '$TARGET_DB' and recreate it from the archive." >&2
        echo "Re-run with CONFIRM=yes to proceed." >&2
        exit 3
    fi
else
    TARGET_DB=${TARGET_DB:-nexa_restore}
    if [ "$TARGET_DB" = "$live_db" ]; then
        echo "TARGET_DB equals the live database; use --replace if that is what you want." >&2
        exit 3
    fi
fi

# Runs SQL against the maintenance database; extra arguments are passed to psql.
psql_admin() {
    $COMPOSE_CMD exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 "$@"' sh "$@"
}

ensure_readonly_role() {
    role=${SQL_READONLY_USER:-nexa_readonly}
    exists=$(psql_admin -At -c "SELECT 1 FROM pg_roles WHERE rolname = '$role'")
    if [ "$exists" = "1" ]; then
        return
    fi
    if [ -z "${SQL_READONLY_PASSWORD:-}" ]; then
        echo "The read-only role '$role' does not exist on this server." >&2
        echo "Set SQL_READONLY_PASSWORD (the value the application uses) and re-run." >&2
        exit 4
    fi
    echo "Creating the read-only SQL role '$role'..."
    timeout_ms=${SQL_STATEMENT_TIMEOUT_MS:-5000}
    psql_admin -v "pw=$SQL_READONLY_PASSWORD" <<SQL > /dev/null
CREATE ROLE "$role" LOGIN PASSWORD :'pw'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION CONNECTION LIMIT 20;
ALTER ROLE "$role" SET default_transaction_read_only = on;
ALTER ROLE "$role" SET statement_timeout = $timeout_ms;
ALTER ROLE "$role" SET idle_in_transaction_session_timeout = 10000;
ALTER ROLE "$role" SET search_path = commerce;
ALTER ROLE "$role" SET work_mem = '16MB';
SQL
}

if [ "$REPLACE" -eq 1 ]; then
    echo "Disconnecting sessions from '$TARGET_DB'..."
    psql_admin -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$TARGET_DB' AND pid <> pg_backend_pid()" > /dev/null
    echo "Recreating database '$TARGET_DB'..."
else
    echo "Creating scratch database '$TARGET_DB'..."
fi
psql_admin -c "DROP DATABASE IF EXISTS \"$TARGET_DB\"" -c "CREATE DATABASE \"$TARGET_DB\"" > /dev/null

ensure_readonly_role

echo "Restoring the archive into '$TARGET_DB'..."
# pgvector must exist before the data that uses it is loaded.
$COMPOSE_CMD exec -T postgres sh -c \
    "psql -U \"\$POSTGRES_USER\" -d \"$TARGET_DB\" -v ON_ERROR_STOP=1 -c 'CREATE EXTENSION IF NOT EXISTS vector'" > /dev/null
$COMPOSE_CMD exec -T postgres sh -c \
    "pg_restore -U \"\$POSTGRES_USER\" -d \"$TARGET_DB\" --no-owner --exit-on-error" < "$DUMP"

if [ -n "$UPLOADS" ]; then
    [ -f "$UPLOADS" ] || { echo "No such file: $UPLOADS" >&2; exit 2; }
    echo "Restoring uploaded documents..."
    $COMPOSE_CMD exec -T backend tar -C /data -xzf - < "$UPLOADS"
fi

echo "Restore into '$TARGET_DB' finished."
if [ "$REPLACE" -eq 1 ]; then
    echo "Start the backend again so it reconnects and applies any newer migrations:"
    echo "  $COMPOSE_CMD up -d backend"
fi
