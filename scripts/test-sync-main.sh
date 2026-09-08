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

assert_secret_absent() {
  local secret="$1"
  ! grep -R -F "$secret" "$TMP/output" "$2/.git/config" >/dev/null 2>&1 || {
    printf 'FAIL: credential material leaked into output or persistent Git configuration\n' >&2
    exit 1
  }
}

make_auth_git_wrapper() {
  local base="$1"
  mkdir -p "$base/bin"
  cat >"$base/bin/git" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "-c" && "${2:-}" == "credential.helper=" &&
      "${3:-}" == "-c" && "${4:-}" == "credential.username=x-access-token" &&
      "${5:-}" == "-c" && "${6:-}" == core.hooksPath=* &&
      ( "${7:-}" == fetch || "${7:-}" == push ) ]]; then
  hooks_path="${6#core.hooksPath=}"
  operation="$7"
  shift 7
  [[ -z "${GITHUB_KEY:-}" ]]
  [[ "${GIT_TRACE_REDACT:-}" == 1 ]]
  [[ "${GIT_TERMINAL_PROMPT:-}" == 0 ]]
  [[ -x "${GIT_ASKPASS:-}" ]]
  [[ -d "$hooks_path" ]]
  [[ -z "$(find "$hooks_path" -mindepth 1 -print -quit)" ]]
  username="$("$GIT_ASKPASS" 'Username for https://github.com:')"
  password="$("$GIT_ASKPASS" 'Password for https://github.com:')"
  [[ "$username" == x-access-token ]]
  if [[ "$password" != "$EXPECTED_GITHUB_KEY" || "${REJECT_AUTH:-0}" == 1 ]]; then
    echo "fatal: Authentication failed for GitHub" >&2
    exit 128
  fi
  printf '%s\n' "$operation" >>"$AUTH_TRACE"
  if [[ "$operation" == fetch ]]; then
    [[ "${1:-}" == --no-tags && "${2:-}" == origin ]]
    exec "$REAL_GIT" -c core.hooksPath="$hooks_path" fetch --no-tags "$AUTH_REMOTE" "${@:3}"
  fi
  [[ "${1:-}" == origin ]]
  exec "$REAL_GIT" -c core.hooksPath="$hooks_path" push "$AUTH_REMOTE" "${@:2}"
fi
exec "$REAL_GIT" "$@"
EOF
  chmod +x "$base/bin/git"
}

make_plain_git_wrapper() {
  local base="$1"
  mkdir -p "$base/bin"
  cat >"$base/bin/git" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == fetch || "${1:-}" == push ]]; then
  operation="$1"
  shift
  [[ "${GIT_ASKPASS:-}" != */illuminate-git-askpass.*/* ]]
  if [[ -n "${CREDENTIAL_HELPER:-}" ]]; then
    "$CREDENTIAL_HELPER" get <<CREDENTIAL
protocol=https
host=github.com

CREDENTIAL
  fi
  printf '%s\n' "$operation" >>"$AUTH_TRACE"
  if [[ "$operation" == fetch ]]; then
    [[ "${1:-}" == --no-tags && "${2:-}" == origin ]]
    exec "$REAL_GIT" fetch --no-tags "$AUTH_REMOTE" "${@:3}"
  fi
  [[ "${1:-}" == origin ]]
  exec "$REAL_GIT" push "$AUTH_REMOTE" "${@:2}"
fi
exec "$REAL_GIT" "$@"
EOF
  chmod +x "$base/bin/git"
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

real_git="$(command -v git)"
secret='sync-test-token-must-not-leak'

new_fixture secret_auth
make_auth_git_wrapper "$TMP/secret_auth"
git -C "$TMP/secret_auth/work" remote set-url origin https://github.com/example/illuminate.git
run_ok "Replit HTTPS fetch uses ephemeral GITHUB_KEY authentication" \
  env PATH="$TMP/secret_auth/bin:$PATH" REAL_GIT="$real_git" \
    AUTH_REMOTE="$TMP/secret_auth/origin.git" AUTH_TRACE="$TMP/secret_auth/trace" \
    EXPECTED_GITHUB_KEY="$secret" GITHUB_KEY="$secret" GIT_TRACE_REDACT=0 REPL_ID=test-repl \
    bash -c "cd '$TMP/secret_auth/work' && '$SYNC' --check"
grep -Fx fetch "$TMP/secret_auth/trace" >/dev/null
assert_secret_absent "$secret" "$TMP/secret_auth/work"
[[ "$(git -C "$TMP/secret_auth/work" remote get-url origin)" == https://github.com/example/illuminate.git ]]
! git -C "$TMP/secret_auth/work" config --get credential.helper >/dev/null
! find "${TMPDIR:-/tmp}" -maxdepth 1 -type d -name 'illuminate-git-askpass.*' -print -quit | grep . >/dev/null

new_fixture secret_push
make_auth_git_wrapper "$TMP/secret_push"
git -C "$TMP/secret_push/work" remote set-url origin https://github.com/example/illuminate.git
printf 'local\n' >>"$TMP/secret_push/work/history.txt"
git -C "$TMP/secret_push/work" commit -am local >/dev/null
run_ok "Replit HTTPS publish uses ephemeral GITHUB_KEY authentication" \
  env PATH="$TMP/secret_push/bin:$PATH" REAL_GIT="$real_git" \
    AUTH_REMOTE="$TMP/secret_push/origin.git" AUTH_TRACE="$TMP/secret_push/trace" \
    EXPECTED_GITHUB_KEY="$secret" GITHUB_KEY="$secret" REPL_ID=test-repl \
    bash -c "cd '$TMP/secret_push/work' && '$SYNC' --publish"
[[ "$(grep -c '^fetch$' "$TMP/secret_push/trace")" == 2 ]]
grep -Fx push "$TMP/secret_push/trace" >/dev/null
assert_secret_absent "$secret" "$TMP/secret_push/work"

hook_leak="$TMP/secret_push/hook-leak"
cat >"$TMP/secret_push/work/.git/hooks/pre-push" <<'EOF'
#!/usr/bin/env bash
set +x
{
  if [[ -n "${GITHUB_KEY_FD:-}" ]]; then
    cat <&"$GITHUB_KEY_FD" || true
  fi
  if [[ -x "${GIT_ASKPASS:-}" ]]; then
    "$GIT_ASKPASS" 'Password for https://github.com:' || true
  fi
} >"${HOOK_LEAK:?}"
EOF
chmod +x "$TMP/secret_push/work/.git/hooks/pre-push"
printf 'hook isolation\n' >>"$TMP/secret_push/work/history.txt"
git -C "$TMP/secret_push/work" commit -am "hook isolation" >/dev/null
run_ok "Replit secret authentication cannot reach repository hooks" \
  env PATH="$TMP/secret_push/bin:$PATH" REAL_GIT="$real_git" \
    AUTH_REMOTE="$TMP/secret_push/origin.git" AUTH_TRACE="$TMP/secret_push/trace" \
    EXPECTED_GITHUB_KEY="$secret" GITHUB_KEY="$secret" HOOK_LEAK="$hook_leak" REPL_ID=test-repl \
    bash -c "cd '$TMP/secret_push/work' && '$SYNC' --publish"
[[ ! -e "$hook_leak" ]]
assert_secret_absent "$secret" "$TMP/secret_push/work"

new_fixture missing_secret
git -C "$TMP/missing_secret/work" remote set-url origin https://github.com/example/illuminate.git
run_fail_with "missing Replit secret gives safe actionable guidance" "GITHUB_KEY is unavailable" \
  env -u GITHUB_KEY REPL_ID=test-repl bash -c "cd '$TMP/missing_secret/work' && '$SYNC' --check"

new_fixture rejected_secret
make_auth_git_wrapper "$TMP/rejected_secret"
git -C "$TMP/rejected_secret/work" remote set-url origin https://github.com/example/illuminate.git
run_fail_with "rejected Replit secret gives safe actionable guidance" "Confirm GITHUB_KEY is valid" \
  env PATH="$TMP/rejected_secret/bin:$PATH" REAL_GIT="$real_git" \
    AUTH_REMOTE="$TMP/rejected_secret/origin.git" AUTH_TRACE="$TMP/rejected_secret/trace" \
    EXPECTED_GITHUB_KEY="$secret" GITHUB_KEY="$secret" REPL_ID=test-repl REJECT_AUTH=1 \
    bash -c "cd '$TMP/rejected_secret/work' && '$SYNC' --check"
assert_secret_absent "$secret" "$TMP/rejected_secret/work"

new_fixture local_credentials
make_plain_git_wrapper "$TMP/local_credentials"
cat >"$TMP/local_credentials/helper" <<'EOF'
#!/usr/bin/env bash
set -e
printf '%s\n' "$1" >>"$HELPER_TRACE"
cat >/dev/null
printf 'username=local-user\npassword=local-password\n'
EOF
chmod +x "$TMP/local_credentials/helper"
git -C "$TMP/local_credentials/work" remote set-url origin https://github.com/example/illuminate.git
run_ok "non-Replit HTTPS operation preserves local credential helper behavior" \
  env -u GITHUB_KEY -u REPL_ID -u REPL_SLUG -u REPLIT_DEV_DOMAIN \
    PATH="$TMP/local_credentials/bin:$PATH" REAL_GIT="$real_git" \
    AUTH_REMOTE="$TMP/local_credentials/origin.git" AUTH_TRACE="$TMP/local_credentials/trace" \
    CREDENTIAL_HELPER="$TMP/local_credentials/helper" HELPER_TRACE="$TMP/local_credentials/helper-trace" \
    bash -c "cd '$TMP/local_credentials/work' && '$SYNC' --check"
grep -Fx get "$TMP/local_credentials/helper-trace" >/dev/null
grep -Fx fetch "$TMP/local_credentials/trace" >/dev/null

new_fixture ssh_bypass
make_plain_git_wrapper "$TMP/ssh_bypass"
git -C "$TMP/ssh_bypass/work" remote set-url origin git@github.com:example/illuminate.git
run_ok "Replit SSH origin bypasses GITHUB_KEY authentication" \
  env PATH="$TMP/ssh_bypass/bin:$PATH" REAL_GIT="$real_git" \
    AUTH_REMOTE="$TMP/ssh_bypass/origin.git" AUTH_TRACE="$TMP/ssh_bypass/trace" \
    GITHUB_KEY="$secret" REPL_ID=test-repl \
    bash -c "cd '$TMP/ssh_bypass/work' && '$SYNC' --check"
grep -Fx fetch "$TMP/ssh_bypass/trace" >/dev/null
assert_secret_absent "$secret" "$TMP/ssh_bypass/work"

new_fixture xtrace
make_auth_git_wrapper "$TMP/xtrace"
git -C "$TMP/xtrace/work" remote set-url origin https://github.com/example/illuminate.git
run_ok "accidental shell tracing cannot print GITHUB_KEY" \
  env PATH="$TMP/xtrace/bin:$PATH" REAL_GIT="$real_git" \
    AUTH_REMOTE="$TMP/xtrace/origin.git" AUTH_TRACE="$TMP/xtrace/trace" \
    EXPECTED_GITHUB_KEY="$secret" GITHUB_KEY="$secret" REPL_ID=test-repl \
    bash -x -c "cd '$TMP/xtrace/work' && '$SYNC' --check"
assert_secret_absent "$secret" "$TMP/xtrace/work"

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