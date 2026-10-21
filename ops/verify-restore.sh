#!/bin/sh
# Prove that a backup restores: load it into a scratch database and compare row counts with the
# live database, then drop the scratch database. Never modifies live data.
#
#   ./ops/verify-restore.sh                              # newest dump in ./backups
#   ./ops/verify-restore.sh backups/nexa-db-<stamp>.dump
#
# Counts can legitimately differ if the live database changed after the backup was taken; the
# script reports the difference and exits non-zero so a scheduled run notices a bad backup.
set -eu

COMPOSE_CMD=${COMPOSE_CMD:-docker compose}
BACKUP_DIR=${BACKUP_DIR:-./backups}
SCRATCH_DB=${SCRATCH_DB:-nexa_restore_check}
DUMP=${1:-}

if [ -z "$DUMP" ]; then
    DUMP=$(ls -1t "$BACKUP_DIR"/nexa-db-*.dump 2>/dev/null | head -n 1 || true)
fi
[ -n "$DUMP" ] && [ -f "$DUMP" ] || { echo "No dump file found." >&2; exit 2; }

HERE=$(cd "$(dirname "$0")" && pwd)
echo "Verifying $DUMP"
TARGET_DB=$SCRATCH_DB COMPOSE_CMD="$COMPOSE_CMD" "$HERE/restore.sh" "$DUMP"

# Row counts of the tables that matter most.
TABLES="public.users public.documents public.document_chunks public.conversations public.messages public.agent_runs commerce.customers commerce.orders commerce.order_items commerce.products"

count_rows() {
    database=$1
    for table in $TABLES; do
        n=$($COMPOSE_CMD exec -T postgres sh -c \
            "psql -U \"\$POSTGRES_USER\" -d \"$database\" -At -c 'SELECT count(*) FROM $table'")
        printf '%s=%s\n' "$table" "$n"
    done
}

live_db=$($COMPOSE_CMD exec -T postgres sh -c 'printf %s "$POSTGRES_DB"')
count_rows "$live_db" > "$BACKUP_DIR/.live-counts.$$"
count_rows "$SCRATCH_DB" > "$BACKUP_DIR/.restored-counts.$$"

status=0
if diff "$BACKUP_DIR/.live-counts.$$" "$BACKUP_DIR/.restored-counts.$$" > /dev/null; then
    echo "OK: every checked table has the same row count in the restored copy."
    cat "$BACKUP_DIR/.restored-counts.$$"
else
    echo "DIFFERENCE between live (<) and restored (>) row counts:" >&2
    diff "$BACKUP_DIR/.live-counts.$$" "$BACKUP_DIR/.restored-counts.$$" >&2 || true
    status=1
fi

rm -f "$BACKUP_DIR/.live-counts.$$" "$BACKUP_DIR/.restored-counts.$$"
$COMPOSE_CMD exec -T postgres sh -c \
    "psql -U \"\$POSTGRES_USER\" -d postgres -c 'DROP DATABASE IF EXISTS \"$SCRATCH_DB\"'" > /dev/null
exit $status
