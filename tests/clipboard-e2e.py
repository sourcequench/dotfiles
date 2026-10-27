#!/usr/bin/env python3
"""Exercise Kitty primary selection and middle-click paste inside tmux under Xvfb."""

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
TOKEN = "PRIMARY_E2E_TOKEN_7F3A"


def run(command, **kwargs):
    return subprocess.run(command, check=True, text=True, capture_output=True, **kwargs)


def under_xvfb():
    command = ["xvfb-run", "-a", sys.executable, str(Path(__file__).resolve()), "--inside-xvfb"]
    subprocess.run(command, check=True)


def x11_mouse():
    x11 = ctypes.CDLL(ctypes.util.find_library("X11"))
    xtst_name = ctypes.util.find_library("Xtst")
    if not xtst_name:
        raise RuntimeError("libXtst is required for mouse input")
    xtst = ctypes.CDLL(xtst_name)
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
    display = x11.XOpenDisplay(None)
    if not display:
        raise RuntimeError("could not connect to the Xvfb display")
    xtst.XTestFakeMotionEvent.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong
    ]
    xtst.XTestFakeButtonEvent.argtypes = [
        ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong
    ]

    def move(x, y):
        xtst.XTestFakeMotionEvent(display, -1, x, y, 0)
        x11.XSync(display, 0)

    def button(number, pressed):
        xtst.XTestFakeButtonEvent(display, number, int(pressed), 0)
        x11.XSync(display, 0)

    return move, button


def inside_xvfb():
    missing = [name for name in ("kitty", "tmux", "xclip", "xwininfo") if not shutil.which(name)]
    if missing:
        raise RuntimeError("missing required commands: " + ", ".join(missing))

    test_dir = Path(tempfile.mkdtemp(prefix="kitty-tmux-clipboard-"))
    home = test_dir / "home"
    home.mkdir()
    tmux_socket = "clip-e2e-" + str(os.getpid())
    kitty_socket = test_dir / "kitty.sock"
    child_env = os.environ.copy()
    child_env.update({"HOME": str(home), "LIBGL_ALWAYS_SOFTWARE": "1"})
    tmux_cmd = ["tmux", "-L", tmux_socket]
    kitty_process = None

    try:
        run(tmux_cmd + ["-f", str(REPO / "src/tmux/common.conf"), "new-session",
                        "-d", "-s", "clip", "-x", "90", "-y", "24"], env=child_env)
        mouse_mode = run(tmux_cmd + ["show-options", "-gqv", "mouse"], env=child_env).stdout.strip()
        if mouse_mode != "off":
            raise RuntimeError(f"tmux mouse mode should be off, got {mouse_mode!r}")

        attach = f"export TERM=xterm-kitty; exec tmux -L {tmux_socket} attach -t clip"
        kitty_process = subprocess.Popen(
            ["kitty", "--config", str(REPO / "src/kitty/kitty.conf"),
             "--override", "allow_remote_control=yes",
             "--override", "initial_window_width=90c",
             "--override", "initial_window_height=24c",
             "--listen-on", "unix:" + str(kitty_socket), "sh", "-lc", attach],
            env=child_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        remote = ["kitty", "@", "--to", "unix:" + str(kitty_socket)]
        for _ in range(80):
            if kitty_process.poll() is not None:
                raise RuntimeError("Kitty exited before opening its control socket")
            try:
                run(remote + ["ls"], env=child_env)
                break
            except subprocess.CalledProcessError:
                time.sleep(0.125)
        else:
            raise RuntimeError("Kitty control socket did not become ready")

        run(tmux_cmd + ["send-keys", "-t", "clip:0.0",
                        "printf '%s\\n' '" + TOKEN + "'", "Enter"], env=child_env)
        screen = ""
        token_row = None
        prompt_row = None
        prompt_pattern = re.compile(r"[$#]\s*$")
        for _ in range(80):
            screen = subprocess.run(remote + ["get-text", "--extent", "screen"],
                                    check=False, text=True, capture_output=True, env=child_env).stdout
            lines = screen.splitlines()
            token_row = next((i for i, line in enumerate(lines) if line.strip() == TOKEN), None)
            prompts = [i for i, line in enumerate(lines) if prompt_pattern.search(line)]
            prompt_row = prompts[-1] if prompts else None
            if token_row is not None and prompt_row is not None:
                break
            time.sleep(0.125)
        else:
            raise RuntimeError("could not locate the printed token and shell prompt")

        listing = json.loads(run(remote + ["ls"], env=child_env).stdout)
        window = listing[0]["tabs"][0]["windows"][0]
        columns = window["columns"]
        lines = window["lines"]
        if columns < len(TOKEN) + 2:
            raise RuntimeError("Kitty test window is too narrow")
        xid = "0x%x" % listing[0]["platform_window_id"]
        geometry = run(["xwininfo", "-id", xid], env=child_env).stdout
        values = dict(re.findall(r"(Absolute upper-left [XY]|Width|Height):\s+(\d+)", geometry))
        origin_x = int(values["Absolute upper-left X"])
        origin_y = int(values["Absolute upper-left Y"])
        pixel_width = int(values["Width"])
        pixel_height = int(values["Height"])
        cell_width = pixel_width // columns
        cell_height = pixel_height // lines
        select_y = origin_y + token_row * cell_height + cell_height // 2
        prompt_y = origin_y + prompt_row * cell_height + cell_height // 2
        select_end_x = origin_x + len(TOKEN) * cell_width + cell_width // 2

        move, button = x11_mouse()
        move(origin_x, select_y)
        button(1, True)
        time.sleep(0.15)
        move(select_end_x, select_y)
        time.sleep(0.15)
        button(1, False)
        time.sleep(0.25)

        primary = subprocess.run(["xclip", "-o", "-selection", "primary"],
                                 check=False, text=True, capture_output=True,
                                 timeout=3, env=child_env).stdout
        if primary != TOKEN:
            raise RuntimeError(f"left-drag PRIMARY was {primary!r}, expected {TOKEN!r}")

        move(origin_x + 15, prompt_y)
        button(2, True)
        time.sleep(0.15)
        button(2, False)
        time.sleep(0.35)
        pane = run(tmux_cmd + ["capture-pane", "-t", "clip:0.0", "-p"], env=child_env).stdout
        if TOKEN not in pane:
            raise RuntimeError("middle-click did not paste the PRIMARY text into tmux")

        print("PASS: plain left-drag selected the full PRIMARY string")
        print("PASS: middle-click pasted it into the tmux prompt")
    finally:
        if kitty_process is not None:
            kitty_process.terminate()
            try:
                kitty_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                kitty_process.kill()
        subprocess.run(tmux_cmd + ["kill-server"], check=False, capture_output=True, env=child_env)
        shutil.rmtree(test_dir)


if __name__ == "__main__":
    if sys.argv[1:] == ["--inside-xvfb"]:
        inside_xvfb()
    else:
        if not shutil.which("xvfb-run"):
            raise SystemExit("xvfb-run is required")
        under_xvfb()
