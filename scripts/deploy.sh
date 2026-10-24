#!/usr/bin/env bash
# Terminal route to what the configurator's Save does after committing:
# make sure the system parts are current, then copy the build onto the ESP.
#
#   sudo scripts/deploy.sh --dry-run    checks every boot entry, shows what would change
#   sudo scripts/deploy.sh [--force]    deploy (--force allows uncommitted changes)
#
# If efi/ changed, run efi/build.sh as yourself first: the system parts include
# our rEFInd, and this won't build it as root.
#
# Never reboots or restarts anything; the result shows on the next boot.
set -euo pipefail

REPO=$(cd "$(dirname "$0")/.." && pwd)
[[ $EUID -eq 0 ]] || { echo "deploy: run with sudo" >&2; exit 1; }

if [[ $("$REPO/scripts/system-version.sh") != "$(cat /usr/local/lib/refind-manager/VERSION 2>/dev/null)" ]]; then
    "$REPO/scripts/install-system.sh"
fi
exec /usr/local/lib/refind-manager/refind-esp-sync "$@"
