# Externally managed machines: setup and updates

These instructions are for Debian machines running Sway that are not managed
with Ansible. The installer configures the user account; required system
packages must already be installed or provisioned by the machine's administrator.

## First-time setup

Clone the public repository, check requirements, and install the configuration:

```sh
git clone https://github.com/sourcequench/dotfiles.git ~/.local/share/personal-dotfiles
cd ~/.local/share/personal-dotfiles
./install check --wm sway
./install --wm sway
```

If `check` reports missing packages or commands, ask the machine's
administrator to install the listed packages, then rerun `check` and `install`.
The installer backs up files it manages under
`~/.local/state/personal-dotfiles/backup-*` before replacing them.

## Enable automatic updates

The installer provides a systemd *user* timer. Enable it once:

```sh
systemctl --user daemon-reload
systemctl --user enable --now personal-dotfiles-update.timer
```

It checks GitHub weekly while your user session is active, catches up after a
missed run, and reapplies the Sway config only when a newer commit has not yet
been successfully applied. It does not install packages or restart Sway. If an
update cannot be installed (for example, a required command is missing), the
next scheduled run tries again. Review backups before removing any old ones.

Useful checks:

```sh
systemctl --user list-timers
systemctl --user status personal-dotfiles-update.timer
journalctl --user -u personal-dotfiles-update.service
```

## Manual update or recovery

To update immediately and inspect requirements first:

```sh
cd ~/.local/share/personal-dotfiles
git pull --ff-only
./install check --wm sway
./install --wm sway
```

If the timer reports an error, read the service journal above, fix the reported
issue, and run the manual update. If the machine does not permit user systemd
timers, use the manual commands periodically instead. After applying a Sway
config change, press `Mod+Shift+c` to reload Sway; logging out is not normally
needed.
