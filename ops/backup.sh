#!/bin/sh
# Back up the NexaAI database (pg_dump, custom format) and the uploaded documents.
#
#   ./ops/backup.sh
#   BACKUP_DIR=/mnt/backups RETENTION_DAYS=30 ./ops/backup.sh
#   COMPOSE_CMD="docker compose -f docker-compose.yml -f docker-compose.prod.yml" ./ops/backup.sh
#
# Produces, in $BACKUP_DIR:
#   nexa-db-<UTC timestamp>.dump        PostgreSQL custom-format archive (schema, data, grants)
#   nexa-uploads-<UTC timestamp>.tar.gz uploaded source documents (/data/uploads)
#
# The database archive is verified before the script reports success. Redis holds only queue
# state and rate-limit counters, so it is not backed up.
set -eu

COMPOSE_CMD=${COMPOSE_CMD:-docker compose}
BACKUP_DIR=${BACKUP_DIR:-./backups}
RETENTION_DAYS=${RETENTION_DAYS:-14}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
DB_FILE="$BACKUP_DIR/nexa-db-$STAMP.dump"
UPLOADS_FILE="$BACKUP_DIR/nexa-uploads-$STAMP.tar.gz"

mkdir -p "$BACKUP_DIR"

echo "Dumping the database..."
# Written to a temporary name first so a failed dump never looks like a good backup.
$COMPOSE_CMD exec -T postgres sh -c \
    'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner' \
    > "$DB_FILE.partial"

echo "Verifying the archive..."
if ! $COMPOSE_CMD exec -T postgres pg_restore --list < "$DB_FILE.partial" > /dev/null; then
    rm -f "$DB_FILE.partial"
    echo "ERROR: the database archive is not readable; no backup was kept." >&2
    exit 1
fi
mv "$DB_FILE.partial" "$DB_FILE"

echo "Archiving uploaded documents..."
if $COMPOSE_CMD exec -T backend tar -C /data -czf - uploads > "$UPLOADS_FILE.partial" 2>/dev/null; then
    mv "$UPLOADS_FILE.partial" "$UPLOADS_FILE"
else
    rm -f "$UPLOADS_FILE.partial"
    echo "WARNING: could not archive uploads (is the backend container running?)." >&2
fi

echo "Removing backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -maxdepth 1 -name 'nexa-*' -type f -mtime +"$RETENTION_DAYS" -delete

echo "Backup complete:"
ls -lh "$BACKUP_DIR"/nexa-*-"$STAMP".* 2>/dev/null || true
