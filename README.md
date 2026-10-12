# Personal Linux desktop configuration

Portable configuration for i3, Sway, kitty, and tmux. `build-bundle` creates
one self-contained `dotfiles.run` file for machines that cannot be managed over
Ansible. The bundle works offline after it has been copied to the target.

## Build and install

From a checkout of this private repository, run the installer directly. There
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

To avoid remembering updates, the installer also installs a user-level systemd
timer. Enable it once with:

```sh
systemctl --user daemon-reload
systemctl --user enable --now personal-dotfiles-update.timer
```

It checks GitHub weekly and, when the checkout advances, reapplies the Sway
configuration. It does not install packages or restart Sway. Managed files are
backed up by the normal installer before replacement. The timer runs while your
user session is active and catches up after a missed scheduled run. Check its
next run with `systemctl --user list-timers`; inspect the last run with
`journalctl --user -u personal-dotfiles-update.service`.

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

The configuration is not activated until the next Sway session. Log out and
back in to Sway after installation. Existing config files are copied to the
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
- Gemini and Goose remain in the shared status line as labels; tmux does not
  invoke either CLI. Optional host-specific tmux settings can go in `work.conf`
  or `local.conf`.
- The installer never installs Goose or other network-fetched user tools.

The optional `build-bundle` command creates a single-file archive for machines
that cannot clone the private repository. That offline transfer route is
separate from the normal clone/pull workflow. The `packages` command prints
the package names selected for a mode. `check` verifies installed commands,
OS identity, and package availability without changing the machine.

