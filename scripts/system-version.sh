#!/usr/bin/env bash
# Print a fingerprint of the root-installed parts (system/ and bin/refind-theme).
# install-system.sh stores it in /usr/local/lib/refind-manager/VERSION; the
# launcher and server compare against it to know whether setup must run again.
set -euo pipefail
cd "$(dirname "$0")/.."
cat system/* bin/refind-theme | sha256sum | cut -c1-16
