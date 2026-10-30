# Personal Linux desktop configuration

Portable configuration for i3, Sway, kitty, and tmux. `build-bundle` creates
one self-contained `dotfiles.run` file for machines that cannot be managed over
Ansible. The bundle works offline after it has been copied to the target.

## Build and install

From a checkout of this public repository, run the installer directly. There
is no separate bundle to fetch when the laptop can clone or pull the repo:

```sh
git clone https://github.com/sourcequench/dotfiles.git ~/.local/share/personal-dotfiles
~/.local/share/personal-dotfiles/install check --wm sway
~/.local/share/personal-dotfiles/install --wm sway
```

The first command is only needed once. To update an existing checkout and
reapply its configuration later:

```sh
cd ~/.local/share/personal-dotfiles
git pull --ff-only
./install check --wm sway
./install --wm sway
```

To avoid remembering updates on a machine you control, the installer also
installs a user-level systemd timer. Enable it once with:

```sh
systemctl --user daemon-reload
systemctl --user enable --now personal-dotfiles-update.timer
```

It checks GitHub weekly and, when the checkout advances, reapplies the desktop
configuration. It does not install packages or restart Sway. It reloads a
running Waybar so bar configuration changes take effect immediately. Managed
files are backed up by the normal installer before replacement. The timer runs
while your user session is active and catches up after a missed scheduled run.
Check its next run with `systemctl --user list-timers`; inspect the last run with
`journalctl --user -u personal-dotfiles-update.service`.

For a machine that is externally managed, pass `--cron-updates` to `check` and
`install`. This installs an hourly user crontab entry instead of enabling the
systemd timer. See [UNMANAGED-MACHINES.md](UNMANAGED-MACHINES.md) for the full
setup and verification commands.

`check` reports missing commands, installable Debian packages, and package
names unavailable from the laptop's configured apt sources. If packages are
unavailable or apt installation is restricted, give the output to your system
administrator and ask for the listed packages to be provisioned. After they
are installed, rerun `check`; when it reports no missing requirements, deploy
the configuration with `./install --wm sway`.

If company policy permits the installer to use apt and sudo, this combines
package installation and configuration deployment:

```sh
./install --wm sway --install-packages
```

This command runs `apt-get update` and installs the selected packages before
writing configuration. It does not use sudo for the config files. To preview
the package names it would install, use `./install --wm sway
--install-packages --dry-run`.

Window manager configuration is not activated until the next Sway session.
Log out and back in to Sway after installation. Waybar configuration is
reloaded during installation. Existing config files are copied to the
timestamped directory printed by the installer under
`~/.local/state/personal-dotfiles/backup-*`. Restore the previous Sway config
from there if you need to roll back.

The installer recognizes Debian derivatives with `ID=debian`, including work
images whose codename is `rodete`. It reports package availability and missing
commands first. Packages are only installed when `--install-packages` is given;
the installer uses apt and sudo, and does not add repositories.

The supported modes are `i3`, `sway`, and `both`. `check` is read-only.
`install` backs up managed files under `~/.local/state/personal-dotfiles/`
before replacing them. It does not change the active session or restart a
window manager. Add host-specific settings to `~/.config/personal-dotfiles/local.conf`.

## Configuration decisions

- Alt is the modifier, with slappy's `j/k/l/;` and arrow-key navigation.
- Alt+Return starts kitty; Alt+d launches the detected menu.
- i3 uses dmenu when available. Sway prefers wmenu, then fuzzel, then tofi.
- Dunst, wpctl, brightnessctl, and tmux key behavior are shared.
- The status bar uses i3status and detects battery devices at startup. It shows
  percentage and time remaining for each battery, and omits battery blocks on
  desktops and VMs without batteries.
- Sway uses swayidle/swaylock and grim/slurp/wl-clipboard. i3 uses
  xss-lock/i3lock and maim/xclip.
- The desktop advertises a dark color-scheme preference through XDG portals
  and requests dark theme variants from GTK 3 and GTK 4 applications.
- GTK primary selection paste is enabled so highlighted text can be pasted with
  the middle mouse button in applications that honor the desktop preference.
- The center of the tmux status line shows a cached discovery item. New releases
  of Sway, i3, tmux, Kitty, Codex, and Helium take priority; a curated daily
  historical item appears when no release is new. Press `Ctrl-a i` to open the
  source. Network refreshes run outside tmux's redraw path.
- Gemini and Goose remain in the shared status line as labels; tmux does not
  invoke either CLI. Optional host-specific tmux settings can go in `work.conf`
  or `local.conf`.
- The installer never installs Goose or other network-fetched user tools.

The optional `build-bundle` command creates a single-file archive for machines
that cannot clone the public repository. That offline transfer route is
separate from the normal clone/pull workflow. The `packages` command prints
the package names selected for a mode. `check` verifies installed commands,
OS identity, and package availability without changing the machine.

For setup and scheduled update instructions for externally managed machines,
see [UNMANAGED-MACHINES.md](UNMANAGED-MACHINES.md).

## Clipboard integration test

Run `python3 tests/clipboard-e2e.py` to check plain left-drag selection and
middle-click paste in an isolated Xvfb display. It uses the repository Kitty
and tmux configs and checks both directions between tmux and naked Kitty, then
between tmux and Chromium. It also checks selection while a terminal app has
enabled mouse reporting. The test requires `xvfb-run`, `dbus-run-session`,
`xwininfo`, Kitty, tmux, Chromium, ChromeDriver, xclip, Python 3 with Selenium,
and libXtst. The test does not touch the desktop clipboard.

