#!/usr/bin/env bash
# One-time system setup for the rEFInd manager (and again whenever system/ or
# bin/refind-theme change; the launcher notices and asks). Needs root: the
# launcher runs it through pkexec, which shows a password dialog.
#
# Installs, all root-owned:
#   /usr/local/lib/refind-manager/refind-esp-sync   copies the built config onto the ESP
#   /usr/local/bin/refind-theme                     theme switcher, used at boot
#   /etc/systemd/system/refind-esp-sync.service     runs the copy (oneshot)
#   /etc/systemd/system/refind-theme-rotate.service rotates the theme each boot (enabled)
#   /etc/polkit-1/rules.d/50-refind-manager.rules   lets the repo owner start
#                                                   refind-esp-sync.service without a password
#   /etc/refind-manager.conf                        where the repo is and who owns it
#
# Uninstall: scripts/install-system.sh --uninstall
set -euo pipefail

REPO=$(cd "$(dirname "$0")/.." && pwd)
OWNER=$(stat -c %U "$REPO")
LIB=/usr/local/lib/refind-manager
RULE=/etc/polkit-1/rules.d/50-refind-manager.rules

die() { echo "install-system: $*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || die "needs root (the launcher uses pkexec; or: sudo $0)"

if [[ ${1:-} == --uninstall ]]; then
    systemctl disable refind-theme-rotate.service 2>/dev/null || true
    rm -f /etc/systemd/system/refind-esp-sync.service /etc/systemd/system/refind-theme-rotate.service \
        "$RULE" /etc/refind-manager.conf /usr/local/bin/refind-theme
    rm -rf "$LIB"
    systemctl daemon-reload
    echo "Uninstalled. The ESP is untouched; /var/lib/refind-manager is kept."
    exit 0
fi

[[ $OWNER != root ]] || die "the repo is owned by root; it should belong to your user"

install -d -m 0755 "$LIB" /var/lib/refind-manager
install -m 0755 "$REPO/system/refind-esp-sync" "$LIB/refind-esp-sync"
install -m 0755 "$REPO/bin/refind-theme" /usr/local/bin/refind-theme
install -m 0644 "$REPO/system/refind-esp-sync.service" "$REPO/system/refind-theme-rotate.service" /etc/systemd/system/
sed "s/@OWNER@/$OWNER/g" "$REPO/system/50-refind-manager.rules" > "$RULE.tmp"
chmod 0644 "$RULE.tmp" && mv -f "$RULE.tmp" "$RULE"
printf 'REPO=%q\nOWNER=%q\n' "$REPO" "$OWNER" > /etc/refind-manager.conf
chmod 0644 /etc/refind-manager.conf
"$REPO/scripts/system-version.sh" > "$LIB/VERSION"

systemctl daemon-reload
systemctl enable refind-theme-rotate.service >/dev/null 2>&1
echo "Installed refind-manager system parts for $OWNER (repo $REPO)."
