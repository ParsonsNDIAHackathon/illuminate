#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SYNC="$ROOT/scripts/sync-main.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export GIT_AUTHOR_NAME="Sync Test"
export GIT_AUTHOR_EMAIL="sync-test@example.invalid"
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME"
export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"

pass=0
new_fixture() {
  local name="$1"
  local base="$TMP/$name"
  git init --bare --initial-branch=main "$base/origin.git" >/dev/null
  git clone "$base/origin.git" "$base/seed" >/dev/null 2>&1
  (
    cd "$base/seed"
    printf 'initial\n' > history.txt
    git add history.txt
    git commit -m initial >/dev/null
    git push origin main >/dev/null 2>&1
  )
  git clone "$base/origin.git" "$base/work" >/dev/null 2>&1
  git -C "$base/work" branch --set-upstream-to=origin/main main >/dev/null
}

run_ok() {
  local description="$1"; shift
  "$@" >"$TMP/output" 2>&1 || {
    cat "$TMP/output" >&2
    printf 'FAIL: %s\n' "$description" >&2
    exit 1
  }
  pass=$((pass + 1))
  printf 'ok %d - %s\n' "$pass" "$description"
}

run_fail_with() {
  local description="$1" expected="$2"; shift 2
  if "$@" >"$TMP/output" 2>&1; then
    printf 'FAIL: %s unexpectedly succeeded\n' "$description" >&2
    exit 1
  fi
  grep -F "$expected" "$TMP/output" >/dev/null || {
    cat "$TMP/output" >&2
    printf 'FAIL: %s lacked expected guidance: %s\n' "$description" "$expected" >&2
    exit 1
  }
  pass=$((pass + 1))
  printf 'ok %d - %s\n' "$pass" "$description"
}

new_fixture equal
run_ok "clean equality" bash -c "cd '$TMP/equal/work' && '$SYNC' --check"
run_ok "idempotent rerun" bash -c "cd '$TMP/equal/work' && '$SYNC' --check"

new_fixture incoming
(
  cd "$TMP/incoming/seed"
  printf 'remote\n' >> history.txt
  git commit -am remote >/dev/null
  git push origin main >/dev/null 2>&1
)
run_ok "incoming commits fast-forward" bash -c "cd '$TMP/incoming/work' && '$SYNC' --check"
[[ "$(git -C "$TMP/incoming/work" rev-parse HEAD)" == "$(git -C "$TMP/incoming/seed" rev-parse HEAD)" ]]

new_fixture outgoing
(
  cd "$TMP/outgoing/work"
  printf 'local\n' >> history.txt
  git commit -am local >/dev/null
)
remote_before="$(git --git-dir="$TMP/outgoing/origin.git" rev-parse main)"
run_ok "local-ahead check does not push" bash -c "cd '$TMP/outgoing/work' && '$SYNC' --check"
[[ "$remote_before" == "$(git --git-dir="$TMP/outgoing/origin.git" rev-parse main)" ]]
run_ok "outgoing commits publish" bash -c "cd '$TMP/outgoing/work' && '$SYNC' --publish"
[[ "$(git -C "$TMP/outgoing/work" rev-parse HEAD)" == "$(git --git-dir="$TMP/outgoing/origin.git" rev-parse main)" ]]

new_fixture diverged
(
  cd "$TMP/diverged/work"
  printf 'local\n' >> history.txt
  git commit -am local >/dev/null
  cd "$TMP/diverged/seed"
  printf 'remote\n' >> history.txt
  git commit -am remote >/dev/null
  git push origin main >/dev/null 2>&1
)
run_fail_with "two-sided divergence is refused" "have diverged" \
  bash -c "cd '$TMP/diverged/work' && '$SYNC' --check"

new_fixture dirty
printf 'dirty\n' >> "$TMP/dirty/work/history.txt"
run_fail_with "dirty worktree is refused" "worktree has staged, unstaged, or untracked changes" \
  bash -c "cd '$TMP/dirty/work' && '$SYNC' --check"

new_fixture auth
git -C "$TMP/auth/work" remote set-url origin "$TMP/auth/missing-origin.git"
run_fail_with "fetch failure gives authentication guidance" "Confirm GitHub authentication" \
  bash -c "cd '$TMP/auth/work' && '$SYNC' --check"

new_fixture rejected
(
  cd "$TMP/rejected/work"
  printf 'local\n' >> history.txt
  git commit -am local >/dev/null
)
cat > "$TMP/rejected/origin.git/hooks/pre-receive" <<'EOF'
#!/usr/bin/env bash
echo "protected branch" >&2
exit 1
EOF
chmod +x "$TMP/rejected/origin.git/hooks/pre-receive"
run_fail_with "rejected push forbids force-push" "Do not force-push" \
  bash -c "cd '$TMP/rejected/work' && '$SYNC' --publish"

new_fixture remote_race
(
  cd "$TMP/remote_race/work"
  printf 'local\n' >> history.txt
  git commit -am local >/dev/null
)
cat > "$TMP/remote_race/work/.git/hooks/pre-push" <<EOF
#!/usr/bin/env bash
set -e
rm -f "\$0"
cd "$TMP/remote_race/seed"
printf 'concurrent remote\n' >> history.txt
git commit -am concurrent-remote >/dev/null
git push origin main >/dev/null 2>&1
EOF
chmod +x "$TMP/remote_race/work/.git/hooks/pre-push"
run_fail_with "concurrent remote push preserves both histories" "Do not force-push" \
  bash -c "cd '$TMP/remote_race/work' && '$SYNC' --publish"
[[ "$(git -C "$TMP/remote_race/work" rev-parse HEAD)" != "$(git --git-dir="$TMP/remote_race/origin.git" rev-parse main)" ]]

new_fixture local_race
(
  cd "$TMP/local_race/work"
  printf 'reviewed\n' >> history.txt
  git commit -am reviewed >/dev/null
)
reviewed_oid="$(git -C "$TMP/local_race/work" rev-parse HEAD)"
(
  cd "$TMP/local_race/work"
  git switch -c concurrent >/dev/null 2>&1
  printf 'unreviewed\n' >> history.txt
  git commit -am unreviewed >/dev/null
  concurrent_oid="$(git rev-parse HEAD)"
  git switch main >/dev/null 2>&1
  printf '%s\n' "$concurrent_oid" > "$TMP/local_race/concurrent-oid"
)
cat > "$TMP/local_race/origin.git/hooks/pre-receive" <<EOF
#!/usr/bin/env bash
env -i PATH="$PATH" HOME="$HOME" \
  git -C "$TMP/local_race/work" update-ref refs/heads/main "\$(cat '$TMP/local_race/concurrent-oid')"
EOF
chmod +x "$TMP/local_race/origin.git/hooks/pre-receive"
run_fail_with "concurrent local commits are not published" "may have moved concurrently" \
  bash -c "cd '$TMP/local_race/work' && '$SYNC' --publish"
[[ "$(git --git-dir="$TMP/local_race/origin.git" rev-parse main)" == "$reviewed_oid" ]]
[[ "$(git -C "$TMP/local_race/work" rev-parse main)" == "$(cat "$TMP/local_race/concurrent-oid")" ]]

new_fixture evaluation_race
(
  cd "$TMP/evaluation_race/work"
  printf 'reviewed\n' >> history.txt
  git commit -am reviewed >/dev/null
)
reviewed_oid="$(git -C "$TMP/evaluation_race/work" rev-parse HEAD)"
(
  cd "$TMP/evaluation_race/work"
  git switch -c concurrent >/dev/null 2>&1
  printf 'unreviewed\n' >> history.txt
  git commit -am unreviewed >/dev/null
  git rev-parse HEAD > "$TMP/evaluation_race/concurrent-oid"
  git switch main >/dev/null 2>&1
)
mkdir "$TMP/evaluation_race/bin"
real_git="$(command -v git)"
cat > "$TMP/evaluation_race/bin/git" <<'EOF'
#!/usr/bin/env bash
set -e
if [[ "${1:-}" == rev-list ]]; then
  output="$("$REAL_GIT" "$@")"
  "$REAL_GIT" -C "$RACE_WORK" update-ref refs/heads/main "$RACE_OID"
  printf '%s\n' "$output"
else
  exec "$REAL_GIT" "$@"
fi
EOF
chmod +x "$TMP/evaluation_race/bin/git"
run_fail_with "evaluation snapshot excludes concurrent local commits" "may have moved concurrently" \
  bash -c "cd '$TMP/evaluation_race/work' && PATH='$TMP/evaluation_race/bin':\$PATH REAL_GIT='$real_git' RACE_WORK='$TMP/evaluation_race/work' RACE_OID='$(cat "$TMP/evaluation_race/concurrent-oid")' '$SYNC' --publish"
[[ "$(git --git-dir="$TMP/evaluation_race/origin.git" rev-parse main)" == "$reviewed_oid" ]]
[[ "$(git -C "$TMP/evaluation_race/work" rev-parse main)" == "$(cat "$TMP/evaluation_race/concurrent-oid")" ]]

new_fixture stale_tracking
git -C "$TMP/stale_tracking/work" config --unset-all remote.origin.fetch
git -C "$TMP/stale_tracking/work" config --add remote.origin.fetch \
  +refs/heads/main:refs/remotes/origin/alternate
(
  cd "$TMP/stale_tracking/seed"
  printf 'remote despite alternate refspec\n' >> history.txt
  git commit -am remote >/dev/null
  git push origin main >/dev/null 2>&1
)
run_ok "explicit fetch refreshes origin/main despite alternate refspec" \
  bash -c "cd '$TMP/stale_tracking/work' && '$SYNC' --check"
[[ "$(git -C "$TMP/stale_tracking/work" rev-parse main)" == "$(git --git-dir="$TMP/stale_tracking/origin.git" rev-parse main)" ]]
[[ "$(git -C "$TMP/stale_tracking/work" rev-parse origin/main)" == "$(git --git-dir="$TMP/stale_tracking/origin.git" rev-parse main)" ]]

printf '1..%d\n' "$pass"