# refind

rEFInd boot menu for **magikarp**: three themes, a unified icon set, a clean
three-OS menu (CachyOS → Limine, Windows, Linux Mint) and optional theme
rotation on every boot.

| minimal | ambience | sublime |
|---|---|---|
| ![minimal](docs/preview-minimal.jpg) | ![ambience](docs/preview-ambience.jpg) | ![sublime](docs/preview-sublime.jpg) |

Themes are our takes on [rEFInd-minimal](https://github.com/evanpurkhiser/rEFInd-minimal)
(Evan Purkhiser, MIT), [refind-ambience](https://github.com/lukechilds/refind-ambience)
(Luke Childs, MIT) and [refind-sublime](https://github.com/senpaiSubby/refind-sublime)
(senpaiSubby). The originals are in `upstream/`.

## Preview without rebooting

Open `preview/index.html` in a browser (straight from disk). It simulates the
boot screen with the real theme files:

- **←/→ ↑/↓** move, **Enter** shows what would boot, click works too
- **1–3** switch theme, **R** simulates a reboot (rotation)
- **L** opens the icon lab: try every candidate icon per slot, then copy the
  printed `CHOICES` into `src/build.py`

## Deploy

Needs root; nothing is rebooted or restarted.

```bash
sudo scripts/deploy.sh --dry-run    # checks every boot entry exists, shows the diff
sudo scripts/deploy.sh              # install (backs up the live refind.conf first)
```

Undo: `sudo cp /boot/EFI/refind/refind.conf.pre-repo /boot/EFI/refind/refind.conf`.
If rEFInd ever won't come up, pick **Limine** from the firmware boot menu.

## Themes

```bash
refind-theme list
sudo refind-theme set ambience
sudo refind-theme next              # or: random
sudo refind-theme rotate on         # new theme every CachyOS boot (on [next|random] | off | status)
```

## Change things

```bash
git pull --rebase
python3 src/build.py --preview      # after touching icons, palettes or entries
git commit -am "…" && git push
sudo scripts/deploy.sh
```

See [AGENTS.md](AGENTS.md) for the full layout and rules, and
[docs/boot-entries.md](docs/boot-entries.md) for what this machine can boot.
