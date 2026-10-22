#!/usr/bin/env bash
# Install this repo onto the ESP (/boot/EFI/refind) and the system.
#
#   sudo scripts/deploy.sh --dry-run    show what would change; touches nothing
#   sudo scripts/deploy.sh [theme]      install; keeps the active theme unless one is named
#   sudo scripts/deploy.sh --force      deploy even with uncommitted changes
#
# Checks that every loader in entries.conf exists first, backs up the live
# refind.conf, copies config + themes, installs refind-theme and its systemd
# unit, and records the deployed commit in /boot/EFI/refind/DEPLOYED. Only the
# runtime files go to the ESP; the ESP is a build target, not a git checkout.
# Never reboots, never restarts services; the result shows on next boot.
set -euo pipefail

REPO=$(cd "$(dirname "$0")/.." && pwd)
ESP=/boot
DEST=$ESP/EFI/refind
DRY=0
FORCE=0
THEME=
MOUNTS=()

die() { echo "deploy: $*" >&2; exit 1; }
cleanup() { local m; for m in "${MOUNTS[@]}"; do umount "$m" && rmdir "$m"; done; }
trap cleanup EXIT
# git as the repo's owner, not root (root trips git's dubious-ownership check)
repo_git() { sudo -u "$(stat -c %U "$REPO")" git -C "$REPO" "$@"; }

for arg; do
    case $arg in
        -n|--dry-run) DRY=1 ;;
        -f|--force) FORCE=1 ;;
        -*) die "unknown option $arg" ;;
        *) THEME=$arg ;;
    esac
done

[[ $EUID -eq 0 ]] || die "needs root to write the ESP; run with sudo"
mountpoint -q "$ESP" || die "$ESP is not mounted"
[[ -f $DEST/refind_x64.efi ]] || die "rEFInd not found in $DEST"
[[ -z $THEME || -f $REPO/themes/$THEME/theme.conf ]] || die "no such theme: $THEME"

# The ESP should always match a commit, so what's installed can be traced.
if [[ -n $(repo_git status --porcelain) ]] && (( ! FORCE )); then
    repo_git status --short >&2
    die "uncommitted changes; commit (and push) first, or pass --force"
fi
COMMIT=$(repo_git log -1 --format='%h %s')
[[ -z $(repo_git rev-list '@{u}..HEAD' 2>/dev/null) ]] || echo "deploy: note: $COMMIT is not pushed yet" >&2

# Where a partition (by PARTUUID) is mounted, mounting it read-only if it isn't.
mount_ro() {
    local dev=/dev/disk/by-partuuid/$1 mnt
    [[ -e $dev ]] || return 1
    mnt=$(findmnt -nro TARGET -S "$(readlink -f "$dev")" | head -n1)
    if [[ -z $mnt ]]; then
        mnt=$(mktemp -d /run/refind-deploy.XXXXXX)
        mount -o ro "$dev" "$mnt"
        MOUNTS+=("$mnt")
    fi
    echo "$mnt"
}

echo "== Checking boot entries"
ok=1
while read -r title volume loader; do
    if [[ $volume == - ]]; then
        root=$ESP
    elif ! root=$(mount_ro "$volume"); then
        echo "  ✗ ${title//_/ }: volume $volume not found"; ok=0; continue
    fi
    if [[ -f $root$loader ]]; then
        echo "  ✓ ${title//_/ }: $loader"
    else
        echo "  ✗ ${title//_/ }: $loader missing on ${volume/#-/rEFInd ESP}"; ok=0
    fi
done < <(awk '
    /^menuentry/          { match($0, /"[^"]+"/); t = substr($0, RSTART + 1, RLENGTH - 2); v = "-"; l = "" }
    /^[[:space:]]*volume/ { v = $2 }
    /^[[:space:]]*loader/ { l = $2 }
    /^}/                  { gsub(/ /, "_", t); print t, v, l }' "$REPO/entries.conf")
(( ok )) || die "fix entries.conf before deploying (a missing loader is a dead menu entry)"

if (( DRY )); then
    echo "== Would deploy $COMMIT (live: $(sed -n 's/^commit *//p' "$DEST/DEPLOYED" 2>/dev/null || echo 'never deployed from this repo'))"
    echo "== refind.conf changes (live → repo)"
    diff -u "$DEST/refind.conf" "$REPO/refind.conf" || true
    echo "== File changes"
    rsync -rtn --modify-window=2 --itemize-changes "$REPO/entries.conf" "$DEST/" || true
    for t in "$REPO"/themes/*/; do
        rsync -rtn --delete --modify-window=2 --itemize-changes "$t" "$DEST/themes/$(basename "$t")/" || true
    done
    echo "== Would install /usr/local/bin/refind-theme and /etc/systemd/system/refind-theme-rotate.service"
    exit 0
fi

echo "== Backing up live config"
[[ -e $DEST/refind.conf.pre-repo ]] || cp "$DEST/refind.conf" "$DEST/refind.conf.pre-repo"
cp "$DEST/refind.conf" "$DEST/refind.conf.bak"

echo "== Copying config and themes to $DEST"
cp "$REPO/refind.conf" "$REPO/entries.conf" "$DEST/"
mkdir -p "$DEST/themes"
for t in "$REPO"/themes/*/; do
    rsync -rt --delete --modify-window=2 "$t" "$DEST/themes/$(basename "$t")/"
done

echo "== Installing refind-theme"
install -m 0755 "$REPO/bin/refind-theme" /usr/local/bin/refind-theme
install -m 0644 "$REPO/systemd/refind-theme-rotate.service" /etc/systemd/system/
systemctl daemon-reload

if [[ -z $THEME ]]; then
    THEME=$(refind-theme current 2>/dev/null || true)
    [[ -n $THEME && -f $DEST/themes/$THEME/theme.conf ]] || THEME=minimal
fi
refind-theme set "$THEME"
refind-theme rotate status
printf 'commit   %s%s\ndeployed %s by %s\n' "$COMMIT" "$( (( FORCE )) && echo ' (+ uncommitted changes)')" \
    "$(date -Is)" "${SUDO_USER:-root}" > "$DEST/DEPLOYED"
sync -f "$DEST/refind.conf"

cat <<EOF

Deployed $COMMIT. rEFInd picks this up on the next boot (nothing was restarted).
Undo: sudo cp $DEST/refind.conf.pre-repo $DEST/refind.conf
EOF
