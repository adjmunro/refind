#!/usr/bin/env bash
# Print a fingerprint of the root-installed parts (system/, bin/refind-theme and
# our rEFInd's sources in efi/). install-system.sh stores it in
# /usr/local/lib/refind-manager/VERSION; the launcher and server compare against
# it to know whether setup must run again.
set -euo pipefail
cd "$(dirname "$0")/.."
cat system/* bin/refind-theme efi/refind-magikarp.patch efi/build.sh | sha256sum | cut -c1-16
