import time
from typing import Callable, Optional, Tuple
import pygame
import logging
import threading
import subprocess


TICKS_PER_SECOND = 2
SLEEP_TIME = 1.0 / TICKS_PER_SECOND
HOTKEY_HOLD_CHECK_TIME = 3 * TICKS_PER_SECOND
GAMEPAD_REFRESH_TIME = 10 * TICKS_PER_SECOND


LOGGER = logging.getLogger("launch-server:hotkeys")
LOGGER.setLevel(logging.INFO)


def _load_hotkey() -> Optional[Tuple[int, int]]:
    """
    Loads the hotkey from dragonshark-input-hotkeys-get.
    Returns None when loading/parsing/validation fails.
    """

    try:
        result = subprocess.run(
            ["dragonshark-input-hotkeys-get"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None

    if result.returncode != 0:
        return None

    parts = result.stdout.strip().split(" ")
    if len(parts) < 6:
        return None

    try:
        first = int(parts[0])
        sixth = int(parts[5])
    except ValueError:
        return None

    if first <= 0 or sixth <= 0:
        return None

    return first, sixth


def _gamepads_pressing_hotkey(hotkey):
    """
    Gets the first gamepad, and also the current hotkey.

    :returns: The list of device NAMES holding the key.
    """

    if hotkey is None:
        return []

    # Process the pygame events.
    pygame.event.pump()

    # Iterate over all the joysticks. Inside, check each
    # one to have the hotkey pressed.
    joystick_count = pygame.joystick.get_count()
    ids = []
    for i in range(joystick_count):
        joystick = pygame.joystick.Joystick(i)
        joystick.init()

        # Check whether the joystick is connected. If it is
        # connected, then check whether it is pressing the
        # hotkey or not.
        if joystick.get_init() and joystick.get_numaxes() > 0:
            if all([joystick.get_button(key) for key in hotkey]):
                ids.append(joystick.get_name())

    # Return the matched joystick instances.
    return ids


def do_on_hotkey(check: Callable[[], bool], callback: Callable[[], None]):
    """
    Executes something on hotkey or when a condition stops being met.
    :param check: The condition to check.
    :param callback: The callback on the end.
    """

    hotkey = _load_hotkey()

    def _func():
        pads = {}
        LOGGER.info("Starting hotkey-checker thread")
        while check():
            # Get all the current keys, and pads that are holding
            # the termination key.
            keys = set(pads.keys())
            LOGGER.info("Getting gamepads pressing the hotkey")
            holding_pads = _gamepads_pressing_hotkey(hotkey)
            if holding_pads:
                LOGGER.info("Gamepads are: " + ", ".join(holding_pads))
            # For each identified pad, discard them from the keys
            # and then increment the current value (starting from
            # a default of 0) by one for the name of the gamepad.
            # If a given pad reached HOTKEY_HOLD_CHECK_TIME, then
            # halt everything.
            for holding_pad in holding_pads:
                keys.discard(holding_pad)
                pads[holding_pad] = pads.get(holding_pad, 0) + 1
                if pads[holding_pad] >= HOTKEY_HOLD_CHECK_TIME:
                    LOGGER.info("Finishing hotkey loop")
                    callback()
                    return
            # Otherwise, we continue. First, we remove any key in
            # that dictionary that did not hold the buttons this
            # frame. And then, we sleep the given time.
            for key in keys:
                pads.pop(key)
            time.sleep(SLEEP_TIME)
    threading.Thread(target=_func).start()


def kill_on_hotkey(process: subprocess.Popen):
    """
    Starts a watch over the process. If the process is not killed and the
    main joypad is pressing Start + Select for 3 seconds, then the process
    will be killed (non-gracefully!).
    :param process: The process to watch.
    """

    do_on_hotkey(lambda: process.poll() is None,
                 lambda: process.kill())
