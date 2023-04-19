import json
import os
import logging
import threading
import subprocess
from .users import PI_NAME
from typing import Callable


logging.basicConfig()
LOGGER = logging.getLogger("game-runner")


# This is the partition where all the Dragonshark saves exist.
# This partition is ext4 and everything there will be owned by pi.
# Actually, the partition is /media/pi/SAVES, with the "rwxr-xr-x"
# permissions, and owned by pi:pi (recursively). Additionally, the
# "dragonshark" subdirectory will keep saves for all of the games
# (/media/pi/SAVES/{domain}/{game} for each game).
SAVES_LOCATION = "/mnt/SAVES/dragonshark"

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
                         "--simulate-outdated-no-au='Tue, 31 Dec 2099 23:59:59 GMT'"]


def run_game(directory: str, command: str, domain: str, game_id: str, on_end: Callable[[], None]):
    """
    Executes a web game.
    :param directory: Where is the game stored.
    :param command: The command, inside the game.
    :param domain: The domain of the game. This is INVERTED, typically in the
      same format for Java or React. Something like "com.mycompany".
    :param game_id: The name of the game. It might be something like this:
      "MyAwesomeGame" or "MyAwesomeGame.Main" (perhaps the game has multiple
      possible interfaces).
    :param on_end: What happens when the game is completely terminated and
      cleaned up.
    """

    # 1. Assemble the command and get its real relative path. This implies
    #    validating and knowing the internal real command.
    full_command = os.path.join(directory, command)
    prefix = directory.rstrip("/") + "/"
    if not full_command.startswith(prefix):
        LOGGER.error(f"The command '{command}' is not inside the directory '{directory}'")
        return
    real_command = full_command[len(prefix):]

    # 2. Get the directory of the path, and mount a server right there.
    subprocess.run("python -m http.server 8888", cwd=directory)
    url = f"http://localhost:8888/{real_command}"

    # 3. Run the browser command, preparing the saves and everything.
    #    This includes preparing the preferences file.
    data_dir = os.path.join(SAVES_LOCATION, domain, game_id)
    prefs_file = os.path.join(data_dir, "preferences.json")
    os.makedirs(data_dir, mode=0o700, exist_ok=True)
    with open(prefs_file, "w") as f:
        json.dump({"SiteStorage": {"localhost:8888": 10485760, "*": 0}}, f)
    sudo = ["sudo", "-u", PI_NAME]
    custom = [f"--user-data-dir={data_dir}", f"--user-preferences-file={prefs_file}"]
    chromium_command = sudo + ["chromium-browser"] + custom + CHROMIUM_BROWSER_ARGS + [url]
    process = subprocess.Popen(chromium_command)

    # 4. Wait for the process and, when done, invoke the callback.
    def _func():
        process.wait()
        on_end()
    threading.Thread(target=_func).start()