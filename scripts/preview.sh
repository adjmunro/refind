#!/usr/bin/env bash
# Run the preview server (src/serve.py) in the background as a transient user
# service, reachable from your other devices at http://magikarp:8765/.
# Lasts until it's stopped or the machine reboots; running this again replaces it.
#
#   scripts/preview.sh                          start
#   systemctl --user stop refind-preview        stop
#   journalctl --user -u refind-preview         logs
set -euo pipefail

REPO=$(cd "$(dirname "$0")/.." && pwd)
systemctl --user stop refind-preview 2>/dev/null || true
systemd-run --user --unit=refind-preview --collect --quiet \
    --working-directory="$REPO" python3 "$REPO/src/serve.py" "$@"
sleep 1
systemctl --user --quiet is-active refind-preview || { journalctl --user -u refind-preview -n 20 --no-pager; exit 1; }
echo "Preview: http://$(hostname):8765/  (stop: systemctl --user stop refind-preview)"
