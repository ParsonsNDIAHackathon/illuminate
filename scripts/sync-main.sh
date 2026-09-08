#!/usr/bin/env bash
set -euo pipefail
set +x

usage() {
  cat <<'EOF'
Usage: scripts/sync-main.sh [--check|--publish]

Synchronize the checked-out main branch with origin/main without rewriting history.

  --check    Fetch and fast-forward main when GitHub is ahead. Never push. (default)
  --publish  Do the same checks, then push reviewed local main commits.

The command refuses dirty trees, non-main branches, unexpected tracking
configuration, and diverged history. In Replit, HTTPS GitHub operations use the
GITHUB_KEY secret automatically without storing it in Git configuration.
EOF
}

mode=check
case "${1:---check}" in
  --check) mode=check ;;
  --publish) mode=publish ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac
[[ $# -le 1 ]] || { usage >&2; exit 2; }

fail() {
  printf 'sync-main: ERROR: %s\n' "$*" >&2
  exit 1
}

git rev-parse --is-inside-work-tree >/dev/null 2>&1 ||
  fail "run this command from inside the Illuminate Git repository."

root="$(git rev-parse --show-toplevel)"
cd "$root"

branch="$(git symbolic-ref --quiet --short HEAD 2>/dev/null)" ||
  fail "HEAD is detached. Switch to main before synchronizing."
[[ "$branch" == main ]] ||
  fail "current branch is '$branch', not 'main'. Finish and merge task-branch work before synchronizing canonical main."

[[ "$(git config --get branch.main.remote || true)" == origin &&
   "$(git config --get branch.main.merge || true)" == refs/heads/main ]] ||
  fail "main must track origin/main. Repair with: git branch --set-upstream-to=origin/main main"

git remote get-url origin >/dev/null 2>&1 ||
  fail "remote 'origin' is missing. Restore the GitHub origin before synchronizing."

origin_url="$(git remote get-url origin)"
git_command=(git)
askpass_dir=

cleanup() {
  if [[ -n "$askpass_dir" ]]; then
    rm -rf "$askpass_dir"
  fi
}
trap cleanup EXIT HUP INT TERM

is_replit=false
if [[ -n "${REPL_ID:-}${REPL_SLUG:-}${REPLIT_DEV_DOMAIN:-}" ]]; then
  is_replit=true
fi

if [[ "$is_replit" == true && "$origin_url" == https://github.com/* ]]; then
  [[ -n "${GITHUB_KEY:-}" ]] ||
    fail "GITHUB_KEY is unavailable in this Replit workspace. Add or restore the existing Replit secret, then rerun; never paste it into a remote URL or Git configuration."

  askpass_dir="$(mktemp -d "${TMPDIR:-/tmp}/illuminate-git-askpass.XXXXXX")" ||
    fail "could not create temporary Git authentication files."
  chmod 700 "$askpass_dir"
  cat >"$askpass_dir/askpass.sh" <<'EOF'
#!/usr/bin/env bash
set +x
case "${1:-}" in
  *sername*) printf '%s\n' 'x-access-token' ;;
  *assword*) printf '%s\n' "${GITHUB_KEY:?}" ;;
  *) exit 1 ;;
esac
EOF
  chmod 700 "$askpass_dir/askpass.sh"
  export GIT_ASKPASS="$askpass_dir/askpass.sh"
  export GIT_TERMINAL_PROMPT=0
  git_command=(git -c credential.helper= -c credential.username=x-access-token)
fi

fetch_main() {
  "${git_command[@]}" fetch --no-tags origin refs/heads/main:refs/remotes/origin/main
}

printf 'sync-main: fetching origin/main...\n'
if ! fetch_main; then
  if [[ "$is_replit" == true && "$origin_url" == https://github.com/* ]]; then
    fail "authenticated fetch failed. Confirm GITHUB_KEY is valid for this repository and has read access; no local history was changed."
  fi
  fail "fetch failed. Confirm GitHub authentication and network access; no local history was changed."
fi

git show-ref --verify --quiet refs/remotes/origin/main ||
  fail "origin/main was not fetched. Confirm the remote has a main branch."

if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  fail "the worktree has staged, unstaged, or untracked changes. Commit intended work on its task branch or stash it, then rerun."
fi

evaluated_oid="$(git rev-parse refs/heads/main)"
read -r ahead behind < <(git rev-list --left-right --count "$evaluated_oid"...refs/remotes/origin/main)

if (( ahead > 0 && behind > 0 )); then
  fail "main and origin/main have diverged ($ahead local, $behind remote). Review the commits, merge origin/main without rebasing or force-pushing, resolve conflicts, validate, and rerun."
fi

if (( behind > 0 )); then
  printf 'sync-main: fast-forwarding main by %s commit(s)...\n' "$behind"
  git merge --ff-only refs/remotes/origin/main ||
    fail "fast-forward failed. Inspect the repository state; do not reset or force-push shared history."
  evaluated_oid="$(git rev-parse refs/remotes/origin/main)"
  ahead=0
fi

if [[ "$mode" == check ]]; then
  if (( ahead > 0 )); then
    printf 'sync-main: main is %s commit(s) ahead of origin/main; no push was attempted.\n' "$ahead"
    printf 'sync-main: after review and validation, run: make sync-publish\n'
  else
    printf 'sync-main: main and origin/main agree at %s.\n' "$(git rev-parse --short HEAD)"
  fi
  exit 0
fi

if (( ahead > 0 )); then
  printf 'sync-main: pushing %s reviewed commit(s) to origin/main...\n' "$ahead"
  if ! "${git_command[@]}" push origin "$evaluated_oid:refs/heads/main"; then
    fail "push was rejected or failed. Do not force-push. Fetch again, satisfy branch protection/checks or use the required pull-request workflow, then rerun."
  fi
fi

if ! fetch_main; then
  fail "the verification fetch failed after push. Rerun --check when connectivity is restored."
fi

[[ "$(git rev-parse HEAD)" == "$(git rev-parse refs/remotes/origin/main)" ]] ||
  fail "verification found main and origin/main at different commits. A local or remote ref may have moved concurrently; review both histories and rerun."

printf 'sync-main: main and origin/main agree at %s.\n' "$(git rev-parse --short HEAD)"