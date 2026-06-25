#!/bin/bash
# Backup diario: PostgreSQL + MinIO
# Cron sugerido (cada día a las 2 AM):
#   0 2 * * * /root/Proyectos/Euro_ver_y_data/Euro_ver_y_data_API/scripts/backup.sh >> /var/log/euro-vyd-backup.log 2>&1

set -e

BACKUP_DIR="/root/backups/euro-vyd"
DATE=$(date +%Y%m%d_%H%M%S)
KEEP_DAYS=7

mkdir -p "$BACKUP_DIR/db"
mkdir -p "$BACKUP_DIR/minio"

DB_CONTAINER=$(docker ps --filter name=db --format '{{.Names}}' | head -1)
MINIO_CONTAINER=$(docker ps --filter name=minio --format '{{.Names}}' | head -1)

echo "[$DATE] Iniciando backup..."

# ── PostgreSQL ──────────────────────────────────────────────────────────────
DB_FILE="$BACKUP_DIR/db/vyd_${DATE}.sql.gz"
docker exec "$DB_CONTAINER" pg_dump -U postgres ver_y_data | gzip > "$DB_FILE"
echo "  BD -> $DB_FILE ($(du -sh "$DB_FILE" | cut -f1))"

# ── MinIO ───────────────────────────────────────────────────────────────────
MINIO_DIR="$BACKUP_DIR/minio/$DATE"
mkdir -p "$MINIO_DIR"

# Leer credenciales desde las variables de entorno del contenedor MinIO
MINIO_USER=$(docker inspect "$MINIO_CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' | grep MINIO_ROOT_USER= | cut -d= -f2-)
MINIO_PASS=$(docker inspect "$MINIO_CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' | grep MINIO_ROOT_PASSWORD= | cut -d= -f2-)

docker run --rm \
  --network host \
  --entrypoint sh \
  -e MC_USER="$MINIO_USER" \
  -e MC_PASS="$MINIO_PASS" \
  -v "$MINIO_DIR:/backup" \
  minio/mc \
  -c 'mc alias set local http://127.0.0.1:9000 "$MC_USER" "$MC_PASS" --quiet && mc mirror local/euro-contratos /backup --quiet'

echo "  MinIO -> $MINIO_DIR ($(du -sh "$MINIO_DIR" | cut -f1))"

# ── Limpieza: borrar backups de más de KEEP_DAYS días ──────────────────────
find "$BACKUP_DIR/db"    -name "*.sql.gz" -mtime +$KEEP_DAYS -delete
find "$BACKUP_DIR/minio" -maxdepth 1 -type d -mtime +$KEEP_DAYS -exec rm -rf {} + 2>/dev/null || true

echo "  Limpieza: backups de mas de $KEEP_DAYS dias eliminados"
echo "[$DATE] Backup completado."
