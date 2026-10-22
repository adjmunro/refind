#!/usr/bin/env bash
# Print a fingerprint of everything install-system.sh puts in place (system/,
# bin/refind-theme, and the installer itself). It stores the fingerprint in
# /usr/local/lib/refind-manager/VERSION; the launcher and server compare against
# it to know whether setup must run again.
set -euo pipefail
cd "$(dirname "$0")/.."
cat system/* bin/refind-theme scripts/install-system.sh | sha256sum | cut -c1-16
