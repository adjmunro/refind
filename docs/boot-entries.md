# What rEFInd can boot on magikarp

## Disks

| Partition | Size | What | PARTUUID |
|---|---|---|---|
| `nvme0n1p1` | 30 G | Linux Mint root (ext4) | `7329656e-545b-4481-ad5a-daf07790e2e4` |
| `nvme0n1p2` | 250 G | CachyOS root (btrfs, `@` subvolume) | `f9d6d804-e52b-4c2a-8e72-faafe65fef78` |
| `nvme0n1p3` | 4.3 G | **CachyOS ESP**, `/boot`: rEFInd, Limine, CachyOS kernels | `4b221d21-84b6-4d2d-9563-5100d01ac340` |
| `nvme0n1p4` | 1 T | LVM `storage` → `/data` (xfs) | — |
| `nvme1n1p1` | 200 M | **Windows ESP**: Windows Boot Manager, Mint's shim + GRUB | `fac9bf60-88c6-48fd-ba43-33268e15baf0` |
| `nvme1n1p3` | 476 G | Windows (NTFS) | — |
| `nvme1n1p4` | 743 M | Windows Recovery Environment | — |

## Firmware boot entries (efibootmgr)

| Entry | Loader | Order |
|---|---|---|
| Boot0002 rEFInd Boot Manager | CachyOS ESP `\EFI\refind\refind_x64.efi` | **1st** |
| Boot0001 Limine | CachyOS ESP `\EFI\limine\limine_x64.efi` | 2nd |
| Boot0000 Windows Boot Manager | Windows ESP `\EFI\Microsoft\Boot\bootmgfw.efi` | 3rd |
| Boot0003 Ubuntu (= Mint) | Windows ESP `\EFI\ubuntu\shimx64.efi` | 4th |
| Boot0009 UEFI OS | CachyOS ESP `\EFI\BOOT\BOOTX64.EFI` (fallback loader) | 5th |

## What rEFInd's auto-scan finds (why the old menu was cluttered)

By default rEFInd scans every ESP and every filesystem it has a driver for,
so on this machine it turns up roughly:

- **Limine** (`\EFI\limine\limine_x64.efi`): the proper way into CachyOS.
- **CachyOS kernels sitting in the ESP root** (`vmlinuz-linux-cachyos` and
  friends): rEFInd boots these directly and can only call them something
  generic like "Linux", which is the mislabelled entry. It also bypasses Limine
  and its snapshot menu.
- **`\EFI\BOOT\BOOTX64.EFI`**: the removable-media fallback copy of a loader,
  which duplicates one of the others.
- **Windows Boot Manager** (`bootmgfw.efi`).
- **Mint's `shimx64.efi` / `grubx64.efi` / `mmx64.efi`** (shim, GRUB and MokManager)
  in `\EFI\ubuntu`: up to three entries for one OS.
- **Mint's kernels** in `/boot` on its ext4 root, if rEFInd's ext4 driver is loaded.
- **Windows Recovery** as a tool, plus the default tools row (shell, MOK
  manager, about, exit, hidden tags, etc.).

The exact list needs root to read both ESPs. Run
`sudo scripts/inventory.sh > docs/inventory.md` (read-only) to get it.

## The new menu (`entries.conf` + `scanfor manual`)

`scanfor manual` turns auto-scan off, so the menu shows exactly:

| Entry | Goes to | Notes |
|---|---|---|
| **CachyOS** | Limine (`\EFI\limine\limine_x64.efi`) | Limine's own menu then offers kernels, LTS/fallback and btrfs snapshots. |
| **Windows** | `bootmgfw.efi` on the Windows ESP | Straight into Windows. |
| **Linux Mint** | `shimx64.efi` on the Windows ESP → GRUB | See below for skipping GRUB. |

Tools row: **power off**, **restart**, **firmware setup**. rEFInd labels the
last one "Reboot to Computer Setup Utility". It reboots into the UEFI firmware
setup, which is what everyone calls the BIOS. That wording is built into
rEFInd's binary, not the config, so it can't be renamed without rebuilding rEFInd.

## Mint: GRUB or not?

Right now the Mint entry chainloads shim → GRUB, which is the safest option
because Mint's updates keep GRUB correct. Options to skip the GRUB screen:

1. **Make GRUB invisible** (recommended): in Mint, set `GRUB_TIMEOUT_STYLE=hidden`
   and `GRUB_TIMEOUT=0` in `/etc/default/grub`, then `sudo update-grub`. Clicking
   Mint in rEFInd then goes straight to Mint, and holding Shift still reaches GRUB.
2. **Boot Mint's kernel from rEFInd directly**: a `menuentry` with
   `volume 7329656e-…`, `loader /boot/vmlinuz`, `initrd /boot/initrd.img` and
   Mint's kernel options. This needs rEFInd's ext4 driver and that rEFInd follows
   Mint's `vmlinuz` symlinks, and it skips anything GRUB was doing. Possible, but
   more fragile.
3. **Install Limine for Mint too.** That's more moving parts than it's worth.
