#!/usr/bin/env bash
# Build magikarp's rEFInd: upstream 0.14.2 plus efi/refind-magikarp.patch, into
# efi/build/refind_x64.efi. Runs as your user, needs no installed packages
# beyond gcc/make/binutils (gnu-efi is built here too). Sources are pinned by
# SHA-256 and cached in efi/build/.
#
#   efi/build.sh            build if the patch or this script changed
#   efi/build.sh --force    rebuild anyway
#   efi/build.sh --stamp    print the fingerprint a build is tagged with
#
# scripts/install-system.sh (root) puts the result on the ESP, keeping the
# original as refind_x64.efi.stock. What the patch changes:
#   - menu entries are labelled with their title ("CachyOS"), not
#     "Boot CachyOS from EFI"; tools are "Shutdown", "Reboot" and "BIOS"
#   - `showtools` replaces rEFInd's default tool list completely (CachyOS's
#     build only overwrote the start of it, so "about" and repeats showed up)
#   - `theme_rotate next|random <file>...` in refind.conf includes one of the
#     files, picked each time rEFInd starts, so restarts from rEFInd's own menu
#     rotate the theme too
set -euo pipefail

cd "$(dirname "$0")"
OUT=build
REFIND=0.14.2
REFIND_SHA=f7d93ce80da76b86c567281ea225b6a87907ce86ff77233c9357a522c115c8f0
GNUEFI=3.0.18
GNUEFI_SHA=7f212c96ee66547eeefb531267b641e5473d7d8529f0bd8ccdefd33cf7413f5c

stamp() { cat refind-magikarp.patch build.sh | sha256sum | cut -c1-16; }

case ${1:-} in
    --stamp) stamp; exit 0 ;;
    --force) rm -f "$OUT/STAMP" ;;
    "") ;;
    *) echo "usage: efi/build.sh [--force|--stamp]" >&2; exit 2 ;;
esac

if [[ -f $OUT/refind_x64.efi && $(cat "$OUT/STAMP" 2>/dev/null) == "$(stamp)" ]]; then
    echo "efi/build/refind_x64.efi is up to date ($(stamp))"
    exit 0
fi

fetch() {   # fetch <file> <sha256> <url>
    [[ -f $OUT/$1 ]] && sha256sum -c --status <<<"$2  $OUT/$1" && return
    curl -fsSL -o "$OUT/$1.part" "$3"
    sha256sum -c --status <<<"$2  $OUT/$1.part" || { rm -f "$OUT/$1.part"; echo "efi/build.sh: $1 failed its checksum" >&2; exit 1; }
    mv -f "$OUT/$1.part" "$OUT/$1"
}

mkdir -p "$OUT"
fetch "refind-src-$REFIND.tar.gz" $REFIND_SHA "https://sourceforge.net/projects/refind/files/$REFIND/refind-src-$REFIND.tar.gz/download"
fetch "gnu-efi-$GNUEFI.tar.bz2" $GNUEFI_SHA "https://sourceforge.net/projects/gnu-efi/files/gnu-efi-$GNUEFI.tar.bz2/download"

rm -rf "$OUT/src" && mkdir -p "$OUT/src"
tar -xzf "$OUT/refind-src-$REFIND.tar.gz" -C "$OUT/src"
tar -xjf "$OUT/gnu-efi-$GNUEFI.tar.bz2" -C "$OUT/src"
G=$PWD/$OUT/src/gnu-efi-$GNUEFI
R=$PWD/$OUT/src/refind-$REFIND

echo "• building gnu-efi $GNUEFI"
make -C "$G" -j"$(nproc)" ARCH=x86_64 lib gnuefi >"$OUT/gnu-efi.log" 2>&1 \
    || { tail -20 "$OUT/gnu-efi.log"; exit 1; }

echo "• building rEFInd $REFIND + refind-magikarp.patch"
patch -d "$R" -p1 -s < refind-magikarp.patch
# Current binutils has no efi-app-x86_64 target name; pei-x86-64 with the EFI
# application subsystem is the same output.
make -C "$R" -j"$(nproc)" gnuefi \
    EFIINC="$G/inc" GNUEFILIB="$G/x86_64/gnuefi" EFILIB="$G/x86_64/lib" EFICRT0="$G/x86_64/gnuefi" \
    GNUEFI_LDSCRIPT="$G/gnuefi/elf_x86_64_efi.lds" FORMAT="-O pei-x86-64 --subsystem=efi-app" \
    >"$OUT/refind.log" 2>&1 || { tail -20 "$OUT/refind.log"; exit 1; }

EFI=$R/refind/refind_x64.efi
file "$EFI" | grep -q 'PE32+ executable for EFI (application), x86-64' \
    || { echo "efi/build.sh: $EFI is not an x86-64 EFI application" >&2; exit 1; }
install -m 0644 "$EFI" "$OUT/refind_x64.efi"
stamp > "$OUT/STAMP"
echo "✓ efi/build/refind_x64.efi ($(stamp))"
