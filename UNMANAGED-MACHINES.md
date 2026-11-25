# Externally managed machines: setup and updates

These instructions are for Debian machines that are not managed with Ansible
(e.g. work-managed machines). The installer configures the user account;
required system packages must already be installed or the machine's
administrator must install them.

## First-time setup

```sh
git clone https://github.com/sourcequench/dotfiles.git ~/.local/share/personal-dotfiles
cd ~/.local/share/personal-dotfiles
./install check --cron-updates
./install --install-packages --cron-updates
```

If `check` reports unavailable packages, ask the administrator to install them,
then rerun. The installer sets up both i3 and sway, installs Signal and Helium
to `~/bin` (if the apt repos are not configured), aligns Obsidian configuration
for `~/md` via Remotely Save, actuates the sync service, and installs an hourly
cron job that pulls and reapplies dotfiles updates. Its output is written to
`~/.local/state/personal-dotfiles/update.log`.

## Obsidian configuration and sync

Obsidian is assumed to be installed via standard Debian package (`/usr/bin/obsidian`).
The dotfiles installer aligns the following configuration:
- Vault ignore filters in `~/md/.obsidian/app.json` to prevent indexing overhead.
- Remotely Save community plugin with WebDAV sync (`https://dav.sourcequench.org`).
- Disabling native Obsidian Sync to prevent sync conflicts.
- Actuating the headless service (`obsidian.service`) on headless hosts (e.g. `server`). On interactive desktops/laptops, the GUI runs as the main instance with CLI integration.

Obsidian WebDAV sync credentials can be supplied in any of the following ways:
1. Log in and unlock Bitwarden CLI (`bw unlock`), which provides the token from item `Obsidian WebDAV Sync`.
2. Add `OBSIDIAN_WEBDAV_PASSWORD=<token>` to `~/.config/personal-dotfiles/obsidian.env` with permissions 0600.
3. Paste the WebDAV token once in Obsidian under Settings > Community plugins > Remotely Save.

Backups of replaced files are saved under
`~/.local/state/personal-dotfiles/backup-*`.

## Ansible (machines you control)

For machines where you have full access (personal workstations, servers):

```sh
ansible-playbook -i ~/md/home/ansible/hosts ansible/setup_desktop.yml --limit workstation
```

This adds the Signal and Helium apt repos, installs packages, clones the
dotfiles, runs install, and enables the update timer.

## Manual update

```sh
cd ~/.local/share/personal-dotfiles && git pull --ff-only && ./install --cron-updates
```

## Useful checks

```sh
crontab -l | grep personal-dotfiles-update
tail ~/.local/state/personal-dotfiles/update.log
```

After a config change, reload sway with `Alt+Shift+C` or i3 with `Alt+Shift+R`.
Logging out and back in is only needed after first install or package changes.
