#!/bin/sh
# Runs inside the `backup` compose service (python:3-alpine). Archives the Neo4j volume and the API
# data dir (encrypted vault, workspace settings, caches) into backups/illuminate-<stamp>.tgz.
#
# Mounts: /neo4j (neo4j-data volume, ro)  /api-data (./api/data, ro)  /backups (./backups, rw)
# Env:    NAME  optional archive name (default illuminate-YYYYmmdd-HHMMSS.tgz)
#         HOST_UID/HOST_GID  owner for the written archive (make passes the caller's ids)
set -eu
name="${NAME:-illuminate-$(date +%Y%m%d-%H%M%S).tgz}"
case "$name" in *.tgz|*.tar.gz) ;; *) name="$name.tgz" ;; esac
out="/backups/$name"

if [ ! -d /neo4j/databases ]; then
  echo "backup: /neo4j has no databases/ — is the neo4j-data volume mounted?" >&2; exit 1
fi
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
  echo "backup: Neo4j is running — stop it first (make backup does this for you)" >&2; exit 1
fi

mkdir -p /api-data
tar czf "$out" -C / neo4j api-data
echo "backup: wrote $name ($(du -h "$out" | cut -f1))"
echo "$name" > /backups/.latest
chown "${HOST_UID:-0}:${HOST_GID:-0}" "$out" /backups/.latest
