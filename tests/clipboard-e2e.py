#!/usr/bin/env python3
"""Test plain mouse selection and middle-click paste between Kitty and tmux."""

import ctypes
import ctypes.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time


REPO = Path(__file__).resolve().parents[1]
TMUX_TOKEN = "TMUX_TO_KITTY_PRIMARY_7F3A"
KITTY_TOKEN = "KITTY_TO_TMUX_PRIMARY_9B2C"


def run(command, **kwargs):
    return subprocess.run(command, check=True, text=True, capture_output=True, **kwargs)


def under_xvfb():
    command = ["xvfb-run", "-a", "-s", "-screen 0 1920x1080x24",
               sys.executable, str(Path(__file__).resolve()), "--inside-xvfb"]
    subprocess.run(command, check=True)


class X11Mouse:
    def __init__(self):
        x11_name = ctypes.util.find_library("X11")
        xtst_name = ctypes.util.find_library("Xtst")
        if not x11_name or not xtst_name:
            raise RuntimeError("libX11 and libXtst are required for mouse input")
        self.x11 = ctypes.CDLL(x11_name)
        self.xtst = ctypes.CDLL(xtst_name)
        self.x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.x11.XOpenDisplay.restype = ctypes.c_void_p
        self.x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.x11.XMoveWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                         ctypes.c_int, ctypes.c_int]
        self.x11.XMapRaised.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.x11.XSetInputFocus.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                           ctypes.c_int, ctypes.c_ulong]
        self.display = self.x11.XOpenDisplay(None)
        if not self.display:
            raise RuntimeError("could not connect to the Xvfb display")
        self.xtst.XTestFakeMotionEvent.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong
        ]
        self.xtst.XTestFakeButtonEvent.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong
        ]

    def move(self, x, y):
        self.xtst.XTestFakeMotionEvent(self.display, -1, x, y, 0)
        self.x11.XSync(self.display, 0)

    def button(self, number, pressed):
        self.xtst.XTestFakeButtonEvent(self.display, number, int(pressed), 0)
        self.x11.XSync(self.display, 0)

    def click(self, window, number, x, y):
        self.focus(window)
        self.move(x, y)
        self.button(number, True)
        time.sleep(0.12)
        self.button(number, False)

    def drag(self, window, start_x, end_x, y):
        self.focus(window)
        self.move(start_x, y)
        self.button(1, True)
        time.sleep(0.12)
        self.move(end_x, y)
        time.sleep(0.12)
        self.button(1, False)
        time.sleep(0.2)

    def focus(self, window):
        self.x11.XMapRaised(self.display, window)
        self.x11.XSetInputFocus(self.display, window, 2, 0)
        self.x11.XSync(self.display, 0)

    def place(self, window, x, y):
        self.x11.XMoveWindow(self.display, window, x, y)
        self.x11.XMapRaised(self.display, window)
        self.x11.XSync(self.display, 0)


def start_kitty(config, socket, command, env):
    process = subprocess.Popen(
        ["kitty", "--config", str(config),
         "--override", "allow_remote_control=yes",
         "--override", "initial_window_width=90c",
         "--override", "initial_window_height=24c",
         "--listen-on", "unix:" + str(socket), *command],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    remote = ["kitty", "@", "--to", "unix:" + str(socket)]
    for _ in range(80):
        if process.poll() is not None:
            raise RuntimeError("Kitty exited before opening its control socket")
        try:
            run(remote + ["ls"], env=env)
            return process, remote
        except subprocess.CalledProcessError:
            time.sleep(0.125)
    raise RuntimeError("Kitty control socket did not become ready")


def screen_text(remote, env):
    return subprocess.run(remote + ["get-text", "--extent", "screen"],
                          check=False, text=True, capture_output=True, env=env).stdout


def wait_for_row(remote, text, env):
    screen = ""
    for _ in range(80):
        screen = screen_text(remote, env)
        lines = screen.splitlines()
        for row, line in enumerate(lines):
            if line.strip() == text:
                return row
        time.sleep(0.125)
    raise RuntimeError(f"could not find expected text in Kitty screen: {text}\n{screen}")


def wait_for_prompt(remote, env):
    prompt_pattern = re.compile(r"[$#]\s*$")
    for _ in range(80):
        lines = screen_text(remote, env).splitlines()
        prompts = [i for i, line in enumerate(lines) if prompt_pattern.search(line)]
        if prompts:
            return prompts[-1]
        time.sleep(0.125)
    raise RuntimeError("could not find a shell prompt in Kitty screen")


def kitty_geometry(remote, env):
    listing = json.loads(run(remote + ["ls"], env=env).stdout)
    window = listing[0]["tabs"][0]["windows"][0]
    xid = listing[0]["platform_window_id"]
    geometry = run(["xwininfo", "-id", "0x%x" % xid], env=env).stdout
    values = dict(re.findall(r"(Absolute upper-left [XY]|Width|Height):\s+(\d+)", geometry))
    columns = window["columns"]
    lines = window["lines"]
    return {
        "id": xid,
        "x": int(values["Absolute upper-left X"]),
        "y": int(values["Absolute upper-left Y"]),
        "cell_width": int(values["Width"]) // columns,
        "cell_height": int(values["Height"]) // lines,
    }


def copy_line(mouse, geometry, row, text):
    y = geometry["y"] + row * geometry["cell_height"] + geometry["cell_height"] // 2
    start_x = geometry["x"]
    end_x = start_x + len(text) * geometry["cell_width"] + geometry["cell_width"] // 2
    mouse.drag(geometry["id"], start_x, end_x, y)


def middle_paste(mouse, geometry, row):
    y = geometry["y"] + row * geometry["cell_height"] + geometry["cell_height"] // 2
    mouse.click(geometry["id"], 2, geometry["x"] + 15, y)


def primary_text(env):
    return subprocess.run(["xclip", "-o", "-selection", "primary"],
                          check=False, text=True, capture_output=True,
                          timeout=3, env=env).stdout


def stop_process(process):
    if process is None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()


def inside_xvfb():
    missing = [name for name in ("kitty", "tmux", "xclip", "xwininfo") if not shutil.which(name)]
    if missing:
        raise RuntimeError("missing required commands: " + ", ".join(missing))

    test_dir = Path(tempfile.mkdtemp(prefix="kitty-tmux-clipboard-"))
    home = test_dir / "home"
    home.mkdir()
    tmux_socket = "clip-e2e-" + str(os.getpid())
    tmux_cmd = ["tmux", "-L", tmux_socket]
    child_env = os.environ.copy()
    child_env.update({"HOME": str(home), "LIBGL_ALWAYS_SOFTWARE": "1"})
    tmux_kitty = None
    naked_kitty = None

    try:
        run(tmux_cmd + ["-f", str(REPO / "src/tmux/common.conf"), "new-session",
                        "-d", "-s", "clip", "-x", "90", "-y", "24"], env=child_env)
        mouse_mode = run(tmux_cmd + ["show-options", "-gqv", "mouse"], env=child_env).stdout.strip()
        if mouse_mode != "off":
            raise RuntimeError(f"tmux mouse mode should be off, got {mouse_mode!r}")

        tmux_attach = f"export TERM=xterm-kitty; exec tmux -L {tmux_socket} attach -t clip"
        tmux_kitty, tmux_remote = start_kitty(
            REPO / "src/kitty/kitty.conf", test_dir / "kitty-tmux.sock",
            ["sh", "-lc", tmux_attach], child_env)
        naked_kitty, naked_remote = start_kitty(
            REPO / "src/kitty/kitty.conf", test_dir / "kitty-naked.sock",
            ["sh", "-lc", "exec bash --noprofile --norc -i"], child_env)

        tmux_geometry = kitty_geometry(tmux_remote, child_env)
        naked_geometry = kitty_geometry(naked_remote, child_env)
        mouse = X11Mouse()
        mouse.place(naked_geometry["id"], 900, 0)
        naked_geometry = kitty_geometry(naked_remote, child_env)

        # Copy from the tmux pane with a plain drag, then middle-click into a naked Kitty shell.
        run(tmux_cmd + ["send-keys", "-t", "clip:0.0",
                        "printf '%s\\n' '" + TMUX_TOKEN + "'", "Enter"], env=child_env)
        tmux_row = wait_for_row(tmux_remote, TMUX_TOKEN, child_env)
        tmux_prompt = wait_for_prompt(tmux_remote, child_env)
        copy_line(mouse, tmux_geometry, tmux_row, TMUX_TOKEN)
        if primary_text(child_env) != TMUX_TOKEN:
            raise RuntimeError("plain drag in tmux did not copy the full PRIMARY selection")
        middle_paste(mouse, naked_geometry, 1)
        time.sleep(0.25)
        if TMUX_TOKEN not in screen_text(naked_remote, child_env):
            raise RuntimeError("middle-click did not paste tmux text into naked Kitty")
        run(tmux_cmd + ["send-keys", "-t", "clip:0.0", "C-c"], env=child_env)
        print("PASS: plain drag copied from tmux and middle-click pasted into naked Kitty")

        # Copy from the naked Kitty shell and middle-click back into the tmux prompt.
        run(naked_remote + ["send-text", "\x03"], env=child_env)
        naked_command = "echo " + KITTY_TOKEN + "\r"
        run(naked_remote + ["send-text", naked_command], env=child_env)
        naked_row = wait_for_row(naked_remote, KITTY_TOKEN, child_env)
        copy_line(mouse, naked_geometry, naked_row, KITTY_TOKEN)
        if primary_text(child_env) != KITTY_TOKEN:
            raise RuntimeError("plain drag in naked Kitty did not copy the full PRIMARY selection")
        middle_paste(mouse, tmux_geometry, tmux_prompt)
        for _ in range(20):
            pane = run(tmux_cmd + ["capture-pane", "-t", "clip:0.0", "-p"], env=child_env).stdout
            if KITTY_TOKEN in pane:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("middle-click did not paste naked Kitty text into tmux")
        print("PASS: plain drag copied from naked Kitty and middle-click pasted into tmux")
    finally:
        stop_process(naked_kitty)
        stop_process(tmux_kitty)
        subprocess.run(tmux_cmd + ["kill-server"], check=False, capture_output=True, env=child_env)
        shutil.rmtree(test_dir)


if __name__ == "__main__":
    if sys.argv[1:] == ["--inside-xvfb"]:
        inside_xvfb()
    else:
        if not shutil.which("xvfb-run"):
            raise SystemExit("xvfb-run is required")
        under_xvfb()
