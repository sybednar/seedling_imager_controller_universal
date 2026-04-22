#!/usr/bin/env bash
# Usage:
#   ./git_update.sh -m "Commit message" [-v v0.06] [-b main] [-r]
#
# Options:
#   -m   Commit message (required)
#   -v   Version tag (optional, e.g., v0.06). Creates an annotated tag and pushes it.
#   -b   Branch name (default: main)
#   -r   Skip auto-rebase (by default we rebase onto origin/<branch> before push)
#
# Notes:
# - Script runs inside /home/sybednar/Seedling_Imager/seedling_imager_controller
# - It prints status, untracked files, and staged changes summary.
# - If rebase hits conflicts, the script exits with guidance.

set -euo pipefail

usage() {
    cat <<EOF
Usage: $0 -m <commit_message> [-v <version_tag>] [-b <branch>] [-r]

Examples:
  $0 -m "v0.06: dual-stream camera, TIFF, AF, File Manager w/ thumbnails, CSV, Camera Config, autostart & desktop launcher" -v v0.06
  $0 -m "Fix: LED live view toggle + AF settle trigger" -b main

Options:
  -m   Commit message (required)
  -v   Version tag (optional, creates annotated tag and pushes it)
  -b   Branch (default: main)
  -r   Skip auto-rebase (default behavior is to rebase onto origin/<branch> before pushing)

EOF
    exit 1
}

commit_message=""
version_tag=""
branch="main"
skip_rebase="false"

while getopts ":m:v:b:r" opt; do
    case "$opt" in
        m) commit_message="$OPTARG" ;;
        v) version_tag="$OPTARG" ;;
        b) branch="$OPTARG" ;;
        r) skip_rebase="true" ;;
        *) usage ;;
    esac
done

if [[ -z "$commit_message" ]]; then
    usage
fi

REPO_DIR="/home/sybednar/Seedling_Imager/seedling_imager_controller"

if [[ ! -d "$REPO_DIR/.git" ]]; then
    echo "Error: $REPO_DIR is not a Git repository."
    exit 1
fi

cd "$REPO_DIR"

echo "== Git remote =="
git remote -v || true

echo
echo "== Git status =="
git status || true

echo
echo "== Untracked files =="
git ls-files --others --exclude-standard || true

echo
echo "== Short diff (staged/untracked preview) =="
# show a compact patch summary; doesn't fail the script
git diff --stat || true

echo
echo "== Staging all changes (new/modified/deleted) =="
git add -A

echo
echo "== Commit =="
if git diff --cached --quiet; then
    echo "Nothing staged; no commit created."
else
    git commit -m "$commit_message"
fi

echo
echo "== Ensure branch exists locally =="
if ! git rev-parse --verify "$branch" >/dev/null 2>&1; then
    echo "Branch '$branch' not found locally. Creating it from current HEAD..."
    git branch "$branch"
fi

echo
echo "== Fetch origin =="
git fetch origin

if [[ "$skip_rebase" == "false" ]]; then
    echo
    echo "== Rebase onto origin/$branch =="
    if git rev-parse --verify "origin/$branch" >/dev/null 2>&1; then
        # Rebase local commits on top of the latest remote branch tip.
        # If conflicts occur, exit with guidance.
        set +e
        git rebase "origin/$branch"
        rebase_rc=$?
        set -e
        if [[ $rebase_rc -ne 0 ]]; then
            cat <<'EOF'
Rebase failed due to conflicts.

Resolve the conflicts, then run:
  git status
  # edit conflicted files to remove conflict markers <<<<<<< ======= >>>>>>>
  git add <resolved_file1> <resolved_file2> ...
  git rebase --continue

If you want to abort the rebase:
  git rebase --abort

After resolving, re-run:
  ./git_update.sh -m "Your commit message" [-v <tag>] [-b <branch>]
EOF
            exit $rebase_rc
        fi
    else
        echo "Warning: origin/$branch does not exist. Skipping rebase."
    fi
else
    echo "Skipping rebase (as requested with -r)."
fi

echo
echo "== Push branch to origin/$branch =="
# If push rejects due to non-fast-forward (shouldn't after rebase), print guidance.
set +e
git push origin "$branch"
push_rc=$?
set -e

if [[ $push_rc -ne 0 ]]; then
    cat <<'EOF'
Push failed. This is usually a non-fast-forward rejection.

Try:
  git fetch origin
  git rebase origin/<branch>
  git push origin <branch>

If you must overwrite remote (not recommended), use:
  git push --force-with-lease origin <branch>

EOF
    exit $push_rc
fi

if [[ -n "$version_tag" ]]; then
    echo
    echo "== Tag handling =="
    if git rev-parse "$version_tag" >/dev/null 2>&1; then
        echo "Tag '$version_tag' already exists locally. Skipping creation."
    else
        echo "Creating annotated tag '$version_tag' ..."
        git tag -a "$version_tag" -m "$commit_message"
    fi

    echo "Pushing tag '$version_tag' ..."
    set +e
    git push origin "$version_tag"
    tag_rc=$?
    set -e

    if [[ $tag_rc -ne 0 ]]; then
        cat <<EOF
Tag push failed. Possibly tag already exists remotely or network error.
You can verify and re-push with:
  git tag --list | grep -F "$version_tag"
  git push origin "$version_tag"
EOF
        exit $tag_rc
    fi
fi

echo
echo "== Update complete =="
