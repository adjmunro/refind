# AGENTS.md

Instructions for any AI agent (Claude Code, Codex, etc.) working in this repo.

## What this is

The rEFInd boot menu for **magikarp**, a CachyOS desktop that triple-boots
CachyOS, Windows and Linux Mint: config, six themes, and **rEFInd Manager**,
a self-contained configurator. The repo lives at `/data/repos/refind` on
magikarp and is pushed to github.com/adjmunro/refind.

The user configures everything in the browser, never the terminal:

1. Double-click `rEFInd Manager.desktop` (or the applications-menu entry), or
   ask an agent to start it. `scripts/refind-manager` fetches + fast-forwards,
   installs/updates the system parts if needed (one pkexec password dialog),
   (re)starts the server and opens the page.
2. The page is at **http://magikarp/refind/** from any of the user's devices.
   The magikarp home page (port 80; separate repo `/data/repos/magikarp-home`,
   `routes` in its config.json) reverse-proxies `/refind/` to this server on
   127.0.0.1:8765, so the page must keep using relative URLs (including its
   `../api/...` calls). Never take over port 80. `http://magikarp:8765/` works
   too. The user's browsers (Helium, Zen) do DNS-over-HTTPS, so they need
   Tailscale names exempted to resolve `magikarp` (see README).
3. **Save & apply** writes `src/config.json`, builds, commits, pushes, then
   starts `refind-esp-sync.service`, which copies the build onto the ESP.

When the user asks you to "spin it up" from another machine:
`ssh magikarp /data/repos/refind/scripts/refind-manager --no-open` (it prints
the URL), then open it in their browser (on macOS: `open <url>`).

The ESP is **not** a git checkout on purpose (FAT32, root-only, shared with the
CachyOS kernels). It gets only runtime files, and `/boot/EFI/refind/DEPLOYED`
records which commit is installed. `CLAUDE.md` only contains `@AGENTS.md`:
keep it. Per the Claude Code docs, a CLAUDE.md importing AGENTS.md works in
every version, while AGENTS.md on its own needs v2.1.277+ and isn't read in
some sessions.

## Git workflow (always)

There is one branch, `main`, and it tracks the current state. No feature
branches, no PRs.

1. **Before changing anything:** `git pull --rebase`. The configurator commits
   and pushes by itself ("Configure boot menu" commits), so main moves.
2. Make the change. If it touches `src/` (config, icons, palettes, backgrounds,
   templates) or `entries.conf`, run `python3 src/build.py --preview` and
   commit the regenerated files with it.
3. **After every change:** commit with a clear message and `git push`.

If you change `system/`, `bin/refind-theme` or `efi/`, the root-installed copies
(and our rEFInd on the ESP) are stale until the user next opens rEFInd Manager
on magikarp's desktop and approves the password prompt. Tell them. After an
`efi/` change, run `efi/build.sh` yourself so the launcher has nothing to build.

## Hard rules

- **Never reboot, shut down, or restart system services** on magikarp. Other
  jobs run there. Restarting the user-level `refind-manager` server is fine.
- **Never write to `/boot` yourself.** You have no sudo password. Changes reach
  the ESP through Save (or `sudo scripts/deploy.sh`, which the user runs).
- Every `menuentry` in `entries.conf` must point at a loader that exists;
  `refind-esp-sync` checks and refuses otherwise. `scanfor manual` means a broken
  entry is a missing OS, not a fallback.
- `refind-esp-sync` runs as root on files from this repo. Keep it data-only:
  it must never execute anything from the repo, and must keep refusing symlinks,
  odd theme names and non-PNG theme files.
- Deleted options are gone on purpose: respect `src/removed.json` (fetch and
  generate scripts already skip its entries).
- Don't edit `upstream/` (vendored originals) or generated files:
  `refind.conf`, `themes/`, `preview/data.js`, `preview/candidates/`,
  `preview/backgrounds/`, `docs/preview-*.jpg`, `src/candidates/`,
  `src/backgrounds/`, `src/icons/os_win.svg`, `src/icons/os_cachyos.svg`.

## Layout

| Path | What |
|---|---|
| `src/config.json` | **The settings**: icon picks, each theme's background, rotation (mode + pool), fixed theme, boot timeout/default. The configurator edits this. |
| `src/build.py` | Builds `refind.conf` and `themes/*` from config. Theme palettes (`THEMES`) and the background library (`BACKGROUNDS`) live here. |
| `src/refind.conf.in` | Template for `refind.conf` (`@TIMEOUT@`, `@DEFAULT@`, `@ROTATION@`). |
| `efi/refind-magikarp.patch`, `efi/build.sh` | Our rEFInd: upstream 0.14.2 with plain labels ("CachyOS", "Shutdown", "Reboot", "BIOS"), a `showtools` that really replaces the default list, and `theme_rotate`. `efi/build.sh` builds it (with its own gnu-efi) into `efi/build/` (ignored by git); `install-system.sh` installs it. |
| `entries.conf` | The boot entries. `{theme}` in icon paths becomes the active theme's name. |
| `src/backgrounds/` | Generated backgrounds (`src/tools/gen_backgrounds.py`: synthwave, automata, five magikarp scenes; the fish itself is `src/tools/magikarp.py`). |
| `src/removed.json` | Icon candidates (`slot/id`) and backgrounds the user deleted in the configurator. Never re-add, fetch or generate anything listed here. |
| `src/icons/`, `src/candidates/` | Our icon masters, and every candidate per slot (`src/tools/fetch_candidates.py`, provenance in `SOURCES.md`). |
| `preview/index.html` | The configurator page. |
| `src/serve.py` | Its server: static files + `/api/state` + `/api/save`. Binds the Tailscale IP only. |
| `scripts/refind-manager`, `rEFInd Manager.desktop` | The launcher. Runs the server as user unit `refind-manager`. |
| `scripts/install-system.sh` | Root setup (via pkexec): installs `system/*`, `bin/refind-theme`, the polkit rule, `/etc/refind-manager.conf` and our rEFInd (the original stays as `refind_x64.efi.stock`). `--uninstall` removes it and puts the stock rEFInd back. |
| `system/refind-esp-sync` (+ `.service`) | Root, data-only copy of the build onto the ESP. Polkit lets the repo owner start just this unit without a password. |
| `bin/refind-theme` | Composes `rotation/<name>.conf` and `active-theme.conf` on the ESP; `status` shows the rotation and what rEFInd showed last. |
| `scripts/deploy.sh` | Terminal route for the same deploy (`sudo scripts/deploy.sh [--dry-run]`). |
| `scripts/inventory.sh` | Read-only report of everything bootable (root). Output: `docs/inventory.md`. |
| `docs/boot-entries.md` | What rEFInd can boot on this machine and why the menu is shaped this way. |

## How theming works

rEFInd only allows one level of `include`, so `refind-theme` composes one file
per theme on the ESP, `rotation/<name>.conf`, from `themes/<name>/theme.conf` +
`entries.conf` (with `{theme}` substituted), plus `active-theme.conf` for the
fixed theme. With rotation on, `refind.conf` has
`theme_rotate next|random rotation/<a>.conf rotation/<b>.conf ...` before
`include active-theme.conf`: our rEFInd picks one of those files every time it
starts (so a restart from rEFInd's own menu rotates too), remembers the pick in
its `ThemeRotation` EFI variable, and skips the include. A stock rEFInd ignores
`theme_rotate` and shows the fixed theme. `refind-esp-sync` writes
`rotation.conf` (`MODE=off|next|random`, `THEMES=...`), has `refind-theme`
compose the files, and picks the fixed theme.

Stock CachyOS rEFInd doesn't clear its default tool list when `showtools` is
set, so `refind.conf` pads `showtools` with `csr_rotate` (a Mac-only tool that
shows nothing) to overwrite the leftovers. Our rEFInd doesn't need it.

## Icon and background rules

- Display is 1920×1080. OS icons are 128 px, tool icons 48 px, selection images
  rEFInd's tile sizes (144, 64). Backgrounds are cut to exactly 1920×1080.
  Nothing is rescaled by rEFInd.
- `build.py` trims every candidate to its visible pixels and scales it to fill
  `FILL` (74% OS, 80% tools), then recolours it in the theme's palette.
- `own` SVGs are two-tone: `#ffffff` = glyph, `#999999` = shade. Masks must use
  the keywords `white`/`black` so the colour swap doesn't touch them.
- rEFInd picks black or white label text from the background's top-left pixel.
- Add a candidate: add it to `SLOTS` in `src/tools/fetch_candidates.py`
  (permissive licences only), rerun it, rebuild. Add a background: drop a PNG
  in `src/backgrounds/` (or add a generator), rebuild. Add a theme: add a
  palette to `THEMES` and an entry in `config.json` `themes`, rebuild.

## Machine facts

- CachyOS ESP: `nvme0n1p3`, mounted at `/boot`, PARTUUID `4b221d21-84b6-4d2d-9563-5100d01ac340`.
  Holds rEFInd (`/EFI/refind`), Limine (`/EFI/limine/limine_x64.efi`) and the CachyOS kernels.
- Windows ESP: `nvme1n1p1`, PARTUUID `fac9bf60-88c6-48fd-ba43-33268e15baf0`. Holds
  `bootmgfw.efi` and Mint's shim + GRUB (`/EFI/ubuntu/`).
- Linux Mint root: `nvme0n1p1` (ext4). Secure Boot is off.
- Desktop: XFCE on X11, polkit-gnome agent, Firefox. Tailscale IP 100.70.83.116.
- Firmware boot order puts rEFInd first; Limine is a separate firmware entry,
  which is the fallback if rEFInd is ever broken (pick it from the firmware boot menu).
