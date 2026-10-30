#!/usr/bin/env python3
"""Test plain mouse selection and middle-click paste in Kitty, tmux, and Chrome."""

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
APP_MOUSE_TOKEN = "APP_MOUSE_CAPTURE_PRIMARY_6C1D"


def run(command, **kwargs):
    return subprocess.run(command, check=True, text=True, capture_output=True, **kwargs)


def under_xvfb():
    command = ["xvfb-run", "-a", "-s", "-screen 0 1920x1080x24",
               "dbus-run-session", "--",
               sys.executable, str(Path(__file__).resolve()), "--inside-xvfb"]
    result = subprocess.run(command, text=True, encoding="utf-8", errors="replace",
                            capture_output=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode:
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        raise subprocess.CalledProcessError(result.returncode, command)


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


def start_kitty(config, socket, command, env, debug_log=None):
    stderr = open(debug_log, "w") if debug_log else subprocess.DEVNULL
    args = ["kitty", "--config", str(config)]
    if debug_log:
        args.append("--debug-input")
    process = subprocess.Popen(
        [*args, "--override", "allow_remote_control=yes",
         "--override", "initial_window_width=90c",
         "--override", "initial_window_height=24c",
         "--listen-on", "unix:" + str(socket), *command],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=stderr,
    )
    if debug_log:
        stderr.close()
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


def start_chrome(test_dir, env):
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service

    options = webdriver.ChromeOptions()
    options.binary_location = shutil.which("chromium")
    for arg in ("--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                "--no-first-run", "--window-size=900,520",
                "--user-data-dir=" + str(test_dir / "chrome-profile")):
        options.add_argument(arg)
    service = Service(shutil.which("chromedriver"), log_output=subprocess.DEVNULL)
    driver = webdriver.Chrome(service=service, options=options)
    driver.get((test_dir / "chrome.html").as_uri())
    driver.set_window_position(0, 540)
    return driver


def chrome_element_point(driver, element_id):
    return driver.execute_script("""
      const e = document.getElementById(arguments[0]);
      const r = e.getBoundingClientRect();
      return {
        x: Math.round(window.screenX + (window.outerWidth - window.innerWidth) / 2 + r.left),
        y: Math.round(window.screenY + (window.outerHeight - window.innerHeight) + r.top + r.height / 2),
        width: Math.round(r.width)
      };
    """, element_id)


def chrome_window_id(title):
    tree = run(["xwininfo", "-root", "-tree"]).stdout
    match = re.search(r'(0x[0-9a-f]+) "[^"]*Chromium"[^\n]*\b\d+x\d+\+', tree)
    if not match:
        raise RuntimeError("could not find the Chrome test window in the X11 tree")
    return int(match.group(1), 16)


def chrome_drag(mouse, driver, element_id):
    point = chrome_element_point(driver, element_id)
    mouse.drag(chrome_window_id(driver.title), point["x"] + 2,
               point["x"] + point["width"] - 2, point["y"])


def chrome_middle_paste(mouse, driver, element_id):
    point = chrome_element_point(driver, element_id)
    mouse.click(chrome_window_id(driver.title), 2, point["x"] + 8, point["y"])


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
    missing = [name for name in ("kitty", "tmux", "xclip", "xwininfo",
                                  "chromium", "chromedriver", "dbus-run-session")
               if not shutil.which(name)]
    if missing:
        raise RuntimeError("missing required commands: " + ", ".join(missing))
    try:
        import selenium  # noqa: F401
    except ImportError as error:
        raise RuntimeError("Python Selenium is required for the Chrome test") from error

    # Keep Chromium on the isolated test bus. This server's system D-Bus broker
    # drops Chromium clients under Xvfb, which otherwise prevents the test from starting.
    os.environ["DBUS_SYSTEM_BUS_ADDRESS"] = os.environ["DBUS_SESSION_BUS_ADDRESS"]

    test_dir = Path(tempfile.mkdtemp(prefix="kitty-tmux-clipboard-"))
    home = test_dir / "home"
    home.mkdir()
    tmux_socket = "clip-e2e-" + str(os.getpid())
    tmux_cmd = ["tmux", "-L", tmux_socket]
    child_env = os.environ.copy()
    child_env.update({"HOME": str(home), "LIBGL_ALWAYS_SOFTWARE": "1"})
    tmux_kitty = None
    naked_kitty = None
    chrome = None

    try:
        run(tmux_cmd + ["-f", str(REPO / "src/tmux/common.conf"), "new-session",
                        "-d", "-s", "clip", "-x", "90", "-y", "24"], env=child_env)
        mouse_mode = run(tmux_cmd + ["show-options", "-gqv", "mouse"], env=child_env).stdout.strip()
        if mouse_mode != "off":
            raise RuntimeError(f"tmux mouse mode should be off, got {mouse_mode!r}")

        tmux_attach = f"export TERM=xterm-kitty; exec tmux -L {tmux_socket} attach -t clip"
        tmux_kitty, tmux_remote = start_kitty(
            REPO / "src/kitty/kitty.conf", test_dir / "kitty-tmux.sock",
            ["sh", "-lc", tmux_attach], child_env,
            debug_log=test_dir / "kitty-tmux-debug.log")
        naked_kitty, naked_remote = start_kitty(
            REPO / "src/kitty/kitty.conf", test_dir / "kitty-naked.sock",
            ["sh", "-lc", "exec bash --noprofile --norc -i"], child_env)

        (test_dir / "chrome.html").write_text("""<!doctype html>
<title>Clipboard E2E Chrome</title>
<style>body{font:24px monospace;margin:40px}#source{margin:40px 0}textarea{font:20px monospace;width:700px;height:90px}</style>
<div id="source">CHROME_TO_TMUX_PRIMARY_4D8E</div>
<textarea id="target" autofocus></textarea>
""")
        chrome = start_chrome(test_dir, child_env)

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
        run(tmux_cmd + ["send-keys", "-t", "clip:0.0", "C-c", "C-u"], env=child_env)
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

        # Reproduce an interactive terminal application such as Codex that enables
        # terminal mouse reporting. Kitty's grabbed-mode left mapping must still
        # allow ordinary drag selection without Shift.
        app_script = test_dir / "mouse-capture.py"
        app_script.write_text(
            "import sys, time\n"
            "sys.stdout.write('\\x1b[?1000h\\x1b[?1006h')\n"
            "print('" + APP_MOUSE_TOKEN + "', flush=True)\n"
            "time.sleep(30)\n"
        )
        run(tmux_cmd + ["new-window", "-t", "clip", "-n", "mouse-capture",
                        "python3", str(app_script)], env=child_env)
        app_row = wait_for_row(tmux_remote, APP_MOUSE_TOKEN, child_env)
        copy_line(mouse, tmux_geometry, app_row, APP_MOUSE_TOKEN)
        if primary_text(child_env) != APP_MOUSE_TOKEN:
            debug = (test_dir / "kitty-tmux-debug.log").read_text(errors="replace")
            selected = subprocess.run(tmux_remote + ["get-text", "--extent", "selection"],
                                      text=True, encoding="utf-8", errors="replace",
                                      capture_output=True, env=child_env).stdout
            raise RuntimeError("plain drag failed while the terminal app had grabbed mouse reporting; "
                               f"PRIMARY={primary_text(child_env)!r}, selection={selected!r}\n" + debug[-5000:])
        run(tmux_cmd + ["send-keys", "-t", "clip:mouse-capture.0", "C-c"], env=child_env)
        run(tmux_cmd + ["select-window", "-t", "clip:0"], env=child_env)
        print("PASS: plain drag selected text while a terminal app grabbed mouse reporting")

        # Plain drag from tmux, middle-click into Chrome's real textarea.
        run(tmux_cmd + ["send-keys", "-t", "clip:0.0",
                        "printf '%s\\n' '" + TMUX_TOKEN + "'", "Enter"], env=child_env)
        tmux_row = wait_for_row(tmux_remote, TMUX_TOKEN, child_env)
        copy_line(mouse, tmux_geometry, tmux_row, TMUX_TOKEN)
        if primary_text(child_env) != TMUX_TOKEN:
            raise RuntimeError("plain drag in tmux did not copy text for Chrome")
        chrome_middle_paste(mouse, chrome, "target")
        if chrome.find_element("id", "target").get_attribute("value") != TMUX_TOKEN:
            raise RuntimeError("middle-click did not paste tmux text into Chrome")
        print("PASS: plain drag copied from tmux and middle-click pasted into Chrome")

        # Plain drag in Chrome, then middle-click into the tmux prompt.
        source = chrome.find_element("id", "source")
        chrome.execute_script("arguments[0].scrollIntoView()", source)
        chrome_drag(mouse, chrome, "source")
        if primary_text(child_env) != "CHROME_TO_TMUX_PRIMARY_4D8E":
            raise RuntimeError("plain drag in Chrome did not copy the full PRIMARY selection")
        tmux_prompt = wait_for_prompt(tmux_remote, child_env)
        middle_paste(mouse, tmux_geometry, tmux_prompt)
        for _ in range(20):
            pane = run(tmux_cmd + ["capture-pane", "-t", "clip:0.0", "-p"], env=child_env).stdout
            if "CHROME_TO_TMUX_PRIMARY_4D8E" in pane:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("middle-click did not paste Chrome text into tmux")
        print("PASS: plain drag copied from Chrome and middle-click pasted into tmux")
    finally:
        if chrome is not None:
            chrome.quit()
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
