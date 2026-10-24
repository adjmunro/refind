#!/usr/bin/env bash
# One-time system setup for the rEFInd manager (and again whenever system/,
# bin/refind-theme or efi/ change; the launcher notices and asks). Needs root:
# the launcher runs it through pkexec, which shows a password dialog.
#
# Installs, all root-owned:
#   /usr/local/lib/refind-manager/refind-esp-sync   copies the built config onto the ESP
#   /usr/local/bin/refind-theme                     theme switcher
#   /etc/systemd/system/refind-esp-sync.service     runs the copy (oneshot)
#   /etc/polkit-1/rules.d/50-refind-manager.rules   lets the repo owner start
#                                                   refind-esp-sync.service without a password
#   /etc/refind-manager.conf                        where the repo is and who owns it
#   /boot/EFI/refind/refind_x64.efi                 our rEFInd, built by efi/build.sh (the
#                                                   original is kept as refind_x64.efi.stock)
#
# Uninstall: scripts/install-system.sh --uninstall (puts the stock rEFInd back)
set -euo pipefail

REPO=$(cd "$(dirname "$0")/.." && pwd)
OWNER=$(stat -c %U "$REPO")
LIB=/usr/local/lib/refind-manager
RULE=/etc/polkit-1/rules.d/50-refind-manager.rules
REFIND_DIR=/boot/EFI/refind
EFI=$REPO/efi/build/refind_x64.efi

die() { echo "install-system: $*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || die "needs root (the launcher uses pkexec; or: sudo $0)"

# Before 2026-10-24 the theme rotated from Linux at boot; rEFInd does it now.
remove_rotate_service() {
    systemctl disable refind-theme-rotate.service >/dev/null 2>&1 || true
    rm -f /etc/systemd/system/refind-theme-rotate.service
}

if [[ ${1:-} == --uninstall ]]; then
    remove_rotate_service
    if [[ -f $REFIND_DIR/refind_x64.efi.stock ]]; then
        cp "$REFIND_DIR/refind_x64.efi.stock" "$REFIND_DIR/refind_x64.efi.new"
        mv -f "$REFIND_DIR/refind_x64.efi.new" "$REFIND_DIR/refind_x64.efi"
        sync -f "$REFIND_DIR/refind_x64.efi"
        echo "Restored the stock rEFInd."
    fi
    rm -f /etc/systemd/system/refind-esp-sync.service "$RULE" /etc/refind-manager.conf /usr/local/bin/refind-theme
    rm -rf "$LIB"
    systemctl daemon-reload
    echo "Uninstalled. The ESP config is untouched; /var/lib/refind-manager is kept."
    exit 0
fi

[[ $OWNER != root ]] || die "the repo is owned by root; it should belong to your user"
mountpoint -q /boot || die "/boot (the ESP) is not mounted"
[[ -f $REFIND_DIR/refind_x64.efi ]] || die "rEFInd not found in $REFIND_DIR"
want=$(cat "$REPO/efi/refind-magikarp.patch" "$REPO/efi/build.sh" | sha256sum | cut -c1-16)
[[ -f $EFI && ! -L $EFI && $(cat "$REPO/efi/build/STAMP" 2>/dev/null) == "$want" ]] \
    || die "efi/build/refind_x64.efi is missing or out of date; run efi/build.sh as $OWNER first"
[[ $(head -c2 "$EFI") == MZ ]] || die "$EFI is not an EFI executable"

install -d -m 0755 "$LIB" /var/lib/refind-manager
install -m 0755 "$REPO/system/refind-esp-sync" "$LIB/refind-esp-sync"
install -m 0755 "$REPO/bin/refind-theme" /usr/local/bin/refind-theme
install -m 0644 "$REPO/system/refind-esp-sync.service" /etc/systemd/system/
sed "s/@OWNER@/$OWNER/g" "$REPO/system/50-refind-manager.rules" > "$RULE.tmp"
chmod 0644 "$RULE.tmp" && mv -f "$RULE.tmp" "$RULE"
printf 'REPO=%q\nOWNER=%q\n' "$REPO" "$OWNER" > /etc/refind-manager.conf
chmod 0644 /etc/refind-manager.conf

# Our rEFInd. Keep the first binary we replace; package updates don't touch the
# ESP (only refind-install does), so it stays ours until this script or that runs.
[[ -e $REFIND_DIR/refind_x64.efi.stock ]] || cp "$REFIND_DIR/refind_x64.efi" "$REFIND_DIR/refind_x64.efi.stock"
cp "$EFI" "$REFIND_DIR/refind_x64.efi.new"
mv -f "$REFIND_DIR/refind_x64.efi.new" "$REFIND_DIR/refind_x64.efi"
sync -f "$REFIND_DIR/refind_x64.efi"
echo "Installed our rEFInd ($want); the original is $REFIND_DIR/refind_x64.efi.stock."
if [[ -f $REFIND_DIR/entries.conf ]]; then
    REFIND_DIR=$REFIND_DIR /usr/local/bin/refind-theme rotation
fi

remove_rotate_service
"$REPO/scripts/system-version.sh" > "$LIB/VERSION"
systemctl daemon-reload
echo "Installed refind-manager system parts for $OWNER (repo $REPO)."
