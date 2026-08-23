#!/usr/bin/env bash
# update.sh — sync kitty fork with upstream, build, deploy
#
# Usage:
#   ./update.sh              # sync + push + build
#   ./update.sh --no-push    # sync + build, leave origin alone
#   ./update.sh --no-build   # sync + push only
#   ./update.sh --status     # fetch + report only
#   ./update.sh --resume     # finish + push after resolving a conflict
#   ./update.sh --help
#
# Remotes expected:
#   upstream  https://github.com/kovidgoyal/kitty.git
#   origin    https://github.com/cwelsys/kitty.git
#
# Patches live on cwel, merged with master rather than rebased. Config-derived
# files are regenerated after every merge rather than merged, so conflicts in
# them resolve themselves.

set -euo pipefail

REPO_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd -P)"
SELF="$REPO_DIR/${0##*/}"
cd "$REPO_DIR"

BRANCH="cwel"
BUILD=true
PUSH=true
RESUME=false
STATUS_ONLY=false
CODESIGN_ID="Developer ID Application: CONNOR JOHN WELSH (Z76D8X6L37)"

usage() { sed -n '2,${/^#/!q; s/^# \{0,1\}//p;}' "$SELF"; }

# A system python3 of the same ABI loads fast_data_types.so, then segfaults.
pick_python() {
    local p
    for p in "$REPO_DIR"/dependencies/*/python/Python.framework/Versions/Current/bin/python3 \
        "$REPO_DIR"/dependencies/*/python/bin/python3; do
        [[ -x "$p" ]] && {
            echo "$p"
            return
        }
    done
    command -v python || command -v python3
}
PYTHON="$(pick_python)"

GENERATED_FILES=(
    kitty/options/parse.py
    kitty/options/types.py
    kitty/options/to-c-generated.h
    tools/cmd/at/set_colors.go
    tools/themes/collection.go
)

FULLY_GENERATED=(
    kitty/options/parse.py
    kitty/options/types.py
    kitty/options/to-c-generated.h
)

for arg in "$@"; do
    case "$arg" in
    --no-build) BUILD=false ;;
    --no-push) PUSH=false ;;
    --resume) RESUME=true ;;
    --status)
        STATUS_ONLY=true
        BUILD=false
        ;;
    --help | -h)
        usage
        exit 0
        ;;
    *)
        echo "unknown argument: $arg (try --help)" >&2
        exit 64
        ;;
    esac
done

short() { git rev-parse --short "$1"; }
unmerged_files() { git diff --name-only --diff-filter=U; }
merge_in_progress() { [[ -f "$(git rev-parse --git-dir)/MERGE_HEAD" ]]; }

ensure_merge_automation() {
    git config rerere.enabled true
    git config rerere.autoupdate true
    git config merge.ours.name "keep ours (generated file; regenerated after merge)"
    git config merge.ours.driver true
    local attr
    attr="$(git rev-parse --git-dir)/info/attributes"
    mkdir -p "$(dirname "$attr")"
    touch "$attr"
    local f
    for f in "${FULLY_GENERATED[@]}"; do
        grep -qxF "$f merge=ours" "$attr" || echo "$f merge=ours" >>"$attr"
    done
}

require_clean_tree() {
    merge_in_progress && return 0
    if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
        echo "!!! Working tree has uncommitted changes. Commit or stash first." >&2
        git status --short --untracked-files=no >&2
        exit 1
    fi
}

# `git fetch upstream master:master` fails while master is checked out.
require_not_on_master() {
    if [[ "$(git rev-parse --abbrev-ref HEAD)" == "master" ]]; then
        echo "!!! Currently on master. Switch to $BRANCH first:" >&2
        echo "!!!   git checkout $BRANCH" >&2
        exit 1
    fi
}

regen_config() {
    echo "==> Regenerating config-derived files..."
    if ! "$PYTHON" -O gen config; then
        echo "!!! WARN: 'gen config' failed (dev env missing? run ./dev.sh deps)." >&2
        return 1
    fi
}

conflict_banner() {
    cat <<EOF

############################################################
##
## Conflicted files:
$(unmerged_files | sed 's/^/##    /')
##
############################################################

EOF
}

finish_merge() {
    merge_in_progress || return 0
    regen_config || true
    git add -- "${GENERATED_FILES[@]}" 2>/dev/null || true
    if [[ -n "$(unmerged_files)" ]]; then
        conflict_banner
        exit 2
    fi
    git commit --no-edit --quiet
}

merge_ref() {
    echo "==> Merging $1..."
    git merge --no-edit "$1" || true
    finish_merge
}

fold_generated_into_head() {
    regen_config || return 0
    git diff --quiet -- "${GENERATED_FILES[@]}" && return 0
    git add -- "${GENERATED_FILES[@]}"
    if git merge-base --is-ancestor HEAD "origin/$BRANCH" 2>/dev/null; then
        echo "==> Committing regenerated files..."
        git commit --quiet -m "chore: regenerate config-derived files"
    else
        echo "==> Folding regenerated files into HEAD..."
        git commit --quiet --amend --no-edit
    fi
}

require_clean_tree
require_not_on_master
ensure_merge_automation

if $RESUME; then
    echo "==> Resuming after conflict resolution..."
    finish_merge
else
    echo "==> Fetching upstream + origin..."
    git fetch upstream master:master
    git fetch origin --quiet
    if ! $STATUS_ONLY && $PUSH; then
        git push origin master
    fi

    echo "==> State:"
    echo "  master        $(short master)"
    echo "  origin/$BRANCH  $(short "origin/$BRANCH")"
    echo "  local  $BRANCH  $(short "$BRANCH")"

    if $STATUS_ONLY; then
        echo "==> Upstream commits not yet in $BRANCH:"
        git log --oneline "$BRANCH..master" | sed 's/^/    /' || true
        echo "==> Commits on origin/$BRANCH not yet local:"
        git log --oneline "$BRANCH..origin/$BRANCH" | sed 's/^/    /' || true
        exit 0
    fi

    git checkout --quiet "$BRANCH"
    merge_ref "origin/$BRANCH"
    merge_ref master
fi

fold_generated_into_head

if ! git merge-base --is-ancestor master "$BRANCH"; then
    echo "!!! postcondition FAILED: master is not an ancestor of $BRANCH." >&2
    echo "!!! Nothing was pushed." >&2
    exit 1
fi

if $PUSH; then
    echo "==> Pushing $BRANCH to origin..."
    git push origin "$BRANCH"
fi

echo "==> ✓ Synced: $BRANCH@$(short "$BRANCH") contains master@$(short master)."

if ! $BUILD; then
    echo "==> Skipping build. Run './dev.sh build' when ready."
    exit 0
fi

echo "==> Building..."
./dev.sh build

if [[ "$(uname -s)" == "Darwin" ]]; then
    echo "==> Updating terminfo..."
    mkdir -p "$HOME/.local/share/terminfo/x"
    cp "$REPO_DIR/terminfo/x/xterm-kitty" "$HOME/.local/share/terminfo/x/xterm-kitty"
    mkdir -p "$HOME/.local/share/terminfo/78"
    ln -sf "../x/xterm-kitty" "$HOME/.local/share/terminfo/78/xterm-kitty"

    echo "==> Installing kitty.app to /Applications..."
    rm -rf /Applications/kitty.app
    ditto "$REPO_DIR/kitty/launcher/kitty.app" /Applications/kitty.app

    echo "==> Updating symlinks in ~/.local/bin..."
    mkdir -p "$HOME/.local/bin"
    ln -sf /Applications/kitty.app/Contents/MacOS/kitty "$HOME/.local/bin/kitty"
    ln -sf /Applications/kitty.app/Contents/MacOS/kitten "$HOME/.local/bin/kitten"

    if [[ -f "$REPO_DIR/kitty.app.icns" ]]; then
        echo "==> Embedding custom app icon..."
        cp "$REPO_DIR/kitty.app.icns" /Applications/kitty.app/Contents/Resources/kitty.icns
        rm -f /var/folders/*/*/*/com.apple.dock.iconcache
        killall Dock
    fi

    echo "==> Signing kitty.app..."
    xattr -crs /Applications/kitty.app
    codesign --force --deep --sign "$CODESIGN_ID" /Applications/kitty.app

    echo "==> Updating zsh completions..."
    ln -sf "$REPO_DIR/shell-integration/zsh/completions/_kitty" \
        "$(brew --prefix)/share/zsh/site-functions/_kitty"
fi

echo ""
