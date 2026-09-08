#!/bin/sh
# Runs inside the `restore` compose service (python:3-alpine) before Neo4j starts. Replaces the
# Neo4j volume and the API data dir with the contents of a backup made by scripts/backup.sh.
# A no-op when BACKUP is unset, so plain `docker compose up` is unaffected.
#
# Mounts: /neo4j (neo4j-data volume, rw)  /api-data (./api/data, rw)  /backups (./backups, ro)
# Env:    BACKUP  archive name inside backups/ (a leading "backups/" is tolerated), or "latest"
#         HOST_UID/HOST_GID  owner for restored api/data files (make passes the caller's ids)
set -eu

prepare_api_data() {
  mkdir -p /api-data
  chown -R "${HOST_UID:-0}:${HOST_GID:-0}" /api-data
}

prepare_api_data
if [ -z "${BACKUP:-}" ]; then
  echo "restore: BACKUP not set, repaired api/data ownership and kept existing data"; exit 0
fi
if [ "$BACKUP" = "latest" ]; then
  [ -f /backups/.latest ] || { echo "restore: no backups/.latest marker — run make backup first" >&2; exit 1; }
  BACKUP="$(cat /backups/.latest)"
fi
f="/backups/$(basename "$BACKUP")"
[ -f "$f" ] || { echo "restore: $f not found (backups must live in ./backups)" >&2; exit 1; }
tar tzf "$f" neo4j/databases >/dev/null 2>&1 || { echo "restore: $f is not an illuminate backup (no neo4j/databases)" >&2; exit 1; }

# Neo4j (Java) holds a POSIX fcntl write lock on databases/store_lock while running. busybox
# flock cannot see fcntl locks, so probe with F_GETLK from python (image: python:3-alpine).
neo4j_running() {
  [ -f /neo4j/databases/store_lock ] || return 1
  python3 - <<'PY'
import fcntl, os, struct, sys
fd = os.open("/neo4j/databases/store_lock", os.O_RDONLY)
lk = struct.pack("hhqql", fcntl.F_WRLCK, 0, 0, 0, 0)
sys.exit(0 if struct.unpack("hhqql", fcntl.fcntl(fd, fcntl.F_GETLK, lk))[0] != fcntl.F_UNLCK else 1)
PY
}
if neo4j_running; then
  echo "restore: Neo4j is running — 'docker compose down' first" >&2; exit 1
fi

echo "restore: replacing Neo4j volume and api/data from $(basename "$f")"
find /neo4j -mindepth 1 -delete
mkdir -p /api-data && find /api-data -mindepth 1 -delete
tar xzf "$f" -C /
chown -R 7474:7474 /neo4j
prepare_api_data
echo "restore: done — $(ls /api-data | wc -l) api/data files, neo4j store $(du -sh /neo4j | cut -f1)"
