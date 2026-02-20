import os
import json
import logging
import threading
import subprocess
from http.server import HTTPServer
from typing import Callable, Tuple
from .hotkeys import do_on_hotkey
from .saves import get_dragonshark_game_save_path
from .static_server import GzipHTTPRequestHandler


LOGGER = logging.getLogger("launch-server:run-web")
LOGGER.setLevel(logging.INFO)


# These are the arguments for the chromium process. Ideally, they
# will do the following:
# - Suppress any warning(s) or notifications.
# - Allow only 10mb to localhost:8888 and 0mb of storage at all to any other site.
# - Allow no cache at all, to any site.
# - Open the required page in kiosk mode.


CHROMIUM_BROWSER_ARGS = ["--disk-cache-size=0", "--enable-features=FileSystemAPI",
                         "--disable-site-isolation-trials", "--disable-site-isolation-for-policy",
                         "--disable-features=IsolateOrigins,site-per-process,OverscrollHistoryNavigation",
                         "--disable-local-storage", "--disable-session-storage", "--disable-quota",
                         "--disable-indexeddb", "--disable-app-cache", "--disable-background-networking",
                         "--disable-sync", "--disable-breakpad", "--disable-client-side-phishing-detection",
                         "--disable-default-apps", "--disable-extensions", "--no-default-browser-check",
                         "--no-first-run", "--disable-translate", "--safebrowsing-disable-auto-update",
                         "--site-per-process", "--site-storage-quota-policy=per_host", "--per-process-gpu",
                         "--kiosk", "--enable-fullscreen", "--activate-on-launch", "--noerrdialogs",
                         "--disable-pinch", "--start-maximized", "--disable-infobars", "--disable-notifications",
                         "--disable-session-crashed-bubble", "--no-first-run", "--enable-offline-auto-reload",
                         "--autoplay-policy=no-user-gesture-required", "--deny-permission-prompts",
                         "--disable-search-geolocation-disclosure", "--enable-ipv6",
                         "--simulate-outdated-no-au='Tue, 31 Dec 2099 23:59:59 GMT'", "--use-angle=gles"]


def _start_http_server(directory: str, command: str) -> Tuple[str, HTTPServer]:
    """
    Runs the server in a separate thread.
    """

    httpd = HTTPServer(("0.0.0.0", 8888), lambda *args, **kwargs: GzipHTTPRequestHandler(
        *args, directory=directory, **kwargs
    ))
    threading.Thread(target=httpd.serve_forever).start()
    return f"http://localhost:8888/{command}", httpd


def _prepare_save_size_preference(save_directory: str):
    """
    Prepares the save size preferences (10mb) in the save directory.
    :param save_directory: The save directory for this game.
    :returns: The preferences file.
    """

    prefs_file = os.path.join(save_directory, "preferences.json")
    os.makedirs(save_directory, mode=0o700, exist_ok=True)
    os.system("chown pi:pi " + save_directory)
    with open(prefs_file, "w") as f:
        json.dump({"SiteStorage": {"localhost:8888": 10485760, "*": 0}}, f)
    return prefs_file


def _run_browser(save_directory: str, prefs_file: str, url: str):
    """
    Runs the browser game. This is done in the "pi" context, with the
    given preferences file, and with a lot of custom browser settings
    that convert the experience to a non-browser-seeming game hitting
    the game url.
    :param save_directory: The save directory.
    :param prefs_file: The preferences file.
    :param url: The URL.
    :return: The game's browser process.
    """

    sudo = "DISPLAY=:0 sudo -u pi"
    custom = [f"--user-data-dir={save_directory}", f"--user-preferences-file={prefs_file}"]
    chromium_command = sudo + ' ' + ' '.join(["chromium"] + custom + CHROMIUM_BROWSER_ARGS + [url])
    return subprocess.Popen(chromium_command, shell=True)


def run_game(directory: str, command: str, package: str, app: str, on_end: Callable[[], None]):
    """
    Executes a web game.
    :param directory: Where is the game stored.
    :param command: The command, inside the game.
    :param package: The game's package.
    :param app: The game's app.
    :param on_end: What happens when the game is completely terminated and
      cleaned up.
    """

    save_directory = get_dragonshark_game_save_path(package, app)

    # PLEASE CONSIDER SOMETHING: THIS DOES NOT REQUIRE ANY SAVE-FILE(S)
    # MANAGEMENT, AS IT IS NEEDED IN THE NATIVE GAMES.

    # 1. Prepare the URL and mount a server right there.
    LOGGER.info("Preparing local http server")
    url, web_server = _start_http_server(directory, command)

    # 2. Prepare the preferences in the game's save directory.
    LOGGER.info("Preparing preferences into the save directory")
    prefs_file = _prepare_save_size_preference(save_directory)

    # 3. Run the game.
    LOGGER.info("Running the game")
    process = _run_browser(save_directory, prefs_file, url)

    def _func():
        process.wait()
        LOGGER.info("Killing local http server")
        web_server.shutdown()
        on_end()
    threading.Thread(target=_func).start()

    # 4. Wait for the process and, when done, invoke the callback.
    #    Also install a signal to kill it on hotkey Start + Select (hold both 3 seconds).
    def check():
        return process.poll() is None

    def terminate():
        os.system("pkill chromium")

    do_on_hotkey(check, terminate)
