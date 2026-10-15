# Externally managed machines: setup and updates

These instructions are for Debian machines that are not managed with Ansible
(e.g. work-managed machines). The installer configures the user account;
required system packages must already be installed or the machine's
administrator must install them.

## First-time setup

```sh
git clone https://github.com/sourcequench/dotfiles.git ~/.local/share/personal-dotfiles
cd ~/.local/share/personal-dotfiles
./install check
./install --install-packages
```

If `check` reports unavailable packages, ask the administrator to install them,
then rerun. The installer sets up both i3 and sway, installs Signal and Helium
to `~/bin` (if the apt repos are not configured), and enables a weekly
auto-update timer.

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
cd ~/.local/share/personal-dotfiles && git pull && ./install
```

## Useful checks

```sh
systemctl --user list-timers
systemctl --user status personal-dotfiles-update.timer
journalctl --user -u personal-dotfiles-update.service
```

After a config change, reload sway with `Alt+Shift+C` or i3 with `Alt+Shift+R`.
Logging out and back in is only needed after first install or package changes.
