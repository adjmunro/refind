#!/usr/bin/env bash
# Read-only report of everything rEFInd can see: firmware entries, every ESP's
# loaders, Linux installs and their kernels, and the live rEFInd config.
#
#   sudo scripts/inventory.sh > docs/inventory.md
#
# Partitions that aren't mounted are mounted read-only (ext4 with noload, so no
# journal replay) under /run and unmounted again before exit.
set -euo pipefail

MOUNTS=()
cleanup() { local m; for m in "${MOUNTS[@]}"; do umount "$m" && rmdir "$m"; done; }
trap cleanup EXIT

[[ $EUID -eq 0 ]] || { echo "inventory: run with sudo" >&2; exit 1; }

ESP_TYPE=c12a7328-f81f-11d2-ba4b-00a0c93ec93b

mount_ro() {
    local dev=$1 fstype=$2 mnt opts=ro
    mnt=$(findmnt -nro TARGET -S "$dev" | head -n1)
    if [[ -z $mnt ]]; then
        [[ $fstype == ext4 ]] && opts=ro,noload
        mnt=$(mktemp -d /run/refind-inventory.XXXXXX)
        mount -o "$opts" "$dev" "$mnt"
        MOUNTS+=("$mnt")
    fi
    echo "$mnt"
}

open() { printf '\n## %s\n\n```\n' "$1"; }
close() { printf '```\n'; }

echo "# magikarp boot inventory"
echo
echo "Generated $(date -Is) by scripts/inventory.sh."

open "Firmware boot entries (efibootmgr)"
efibootmgr
close

open "Partitions"
lsblk -o NAME,SIZE,FSTYPE,PARTTYPENAME,PARTLABEL,LABEL,PARTUUID,MOUNTPOINTS
close

while read -r dev type fstype; do
    if [[ $type == "$ESP_TYPE" ]]; then
        root=$(mount_ro "$dev" vfat)
        open "ESP $dev (PARTUUID $(lsblk -no PARTUUID "$dev"))"
        (cd "$root" && find . -maxdepth 4 -not -path './EFI/refind/themes/*/*' | sort)
        close
    elif [[ $fstype == ext4 || $fstype == btrfs ]]; then
        root=$(mount_ro "$dev" "$fstype")
        [[ -r $root/etc/os-release ]] || continue
        open "Linux on $dev: $(. "$root/etc/os-release"; echo "$PRETTY_NAME")"
        ls -la "$root/boot" 2>/dev/null || true
        [[ -r $root/etc/default/grub ]] && grep -E '^GRUB_(DEFAULT|TIMEOUT|TIMEOUT_STYLE|CMDLINE_LINUX|DISABLE_OS_PROBER)' "$root/etc/default/grub"
        close
    fi
done < <(lsblk -nrpo NAME,PARTTYPE,FSTYPE | awk 'NF >= 2')

open "Live rEFInd config (/boot/EFI/refind/refind.conf, comments stripped)"
grep -v -E '^[[:space:]]*(#|$)' /boot/EFI/refind/refind.conf || true
close

if [[ -f /boot/EFI/refind/active-theme.conf ]]; then
    open "Active theme include (comments stripped)"
    grep -v -E '^[[:space:]]*(#|$)' /boot/EFI/refind/active-theme.conf || true
    close
fi
