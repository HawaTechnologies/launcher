import re
import os
import json
import pygame
import logging
import subprocess
import socketserver
import traceback
from typing import List, Tuple
from . import run_web, run_native


MAIN_BINDING = "/run/Hawa/game-launcher.sock"
LOGGER = logging.getLogger("launch-server:main")
LOGGER.setLevel(logging.INFO)


class GameLauncherServer(socketserver.ThreadingUnixStreamServer):
    """
    This is a very small server that attends a command request
    to launch a game.
    """

    def __init__(self, server_address, request_handler_class):
        super().__init__(server_address, request_handler_class)
        self.locked = False

    def server_activate(self) -> None:
        super().server_activate()
        pygame.init()
        os.system(f"chgrp hawalnch {MAIN_BINDING}")
        os.system(f"chmod g+rw {MAIN_BINDING}")
        os.system(f"chmod o-rwx {MAIN_BINDING}")


class GameLauncherRequestHandler(socketserver.StreamRequestHandler):
    """
    This handler receives only one command from the user and,
    after parsing it, launches a game (if possible).
    """

    def _recv_command(self):
        """
        Parses a command up to its line. Only ONE command will
        be parsed like this (other lines will be discarded).
        The line will be JSON, with specific fields: "package",
        "app", "directory", "command".
        :return: A (package, app, directory, command, save_filters) tuple.
        """

        # Read the JSON payload from the socket.
        payload = b""
        while True:
            data = self.request.recv(1024)
            if not data:
                break
            payload += data
            if b"\n" in payload:
                payload = payload[:payload.index(b"\n")]
                break

        # Extract the fields and return them.
        obj = json.loads(payload.strip().decode("utf-8"))
        return obj["package"], obj["app"], obj["directory"], obj["command"], obj["save_filters"]

    def _get_executable_type(self, real_directory_path: str, command_path: str):
        """
        Tells whether the executable is an HTML page (returns "web") or another type.
        This "another type" might be an ELF 32-bit or ELF 64-bit, or a shell script,
        but in any case the command type will be the same for them (returns "exe").
        :returns: The type: "web" or "exe".
        """

        output = subprocess.check_output(["file", command_path], cwd=real_directory_path).decode('utf-8')
        LOGGER.info(f"The command ({command_path}) file type is: {output}")
        if re.search(r"HTML document", output):
            return "web"
        else:
            return "exe"

    def handle(self):
        """
        Parses and runs the entire command.
        """

        # Parse the payload and validate values are present.
        try:
            package, app, directory, command, save_filters = self._recv_command()
            package, app, directory, command = package.strip(), app.strip(), directory.strip(), command.strip()
            if not all([directory, app, package, command]):
                raise KeyError()
        except KeyError:
            self._send_response({"status": "error", "hint": "request:format"})
            return
        except (ValueError, json.JSONDecodeError):
            self._send_response({"status": "error", "hint": "request:format"})
            return

        # Check if the directory exists and is valid.
        if not os.path.isdir(directory):
            self._send_response({"status": "error", "hint": "directory:invalid"})
            return

        # Check if the command path is valid.
        command_path = os.path.join(directory, command)
        real_command_path = os.path.realpath(command_path)
        real_directory_path = os.path.realpath(directory)
        if not real_command_path.startswith(real_directory_path.rstrip("/") + "/"):
            self._send_response({"status": "error", "hint": "command:invalid"})
            return
        real_relative_command_path = real_command_path[len(real_directory_path) + 1:]

        # Check if the command path is a file.
        if not os.path.isfile(real_command_path):
            self._send_response({"status": "error", "hint": "command:invalid-format"})
            return

        # Launch the executable. This may raise more errors.
        self._launch_executable(real_directory_path, real_relative_command_path, package, app,
                                save_filters)

        # Close the socket
        self.request.close()

    def _send_response(self, response: dict):
        serialized_response = json.dumps(response).encode("utf-8")
        self.request.sendall(serialized_response + b"\n")

    def _launch_executable(self, real_directory_path: str, real_relative_command_path: str, package: str, app: str,
                           save_filters: List[Tuple[str, List[str]]]):
        """
        Launches the game. This includes:
        - Lock test-and-set.
        - Determining format.
        - Preparing save directory, if any.
        - Launching the game.
        - Waiting for it to be terminated.
        - Releasing & storing save directory, if any.
        :param real_directory_path: The directory path.
        :param real_relative_command_path: The command executable path.
        :param package: The command package (e.g. inverted domain).
        :param app: The command app.
        """

        # 1. Lock test-and-set.
        assert isinstance(self.server, GameLauncherServer)
        if self.server.locked:
            self._send_response({"status": "error", "hint": "command:game-already-running"})
            return
        self.server.locked = True

        # 2. Determining format.
        format = self._get_executable_type(real_directory_path, real_relative_command_path)

        # 3. Launching the game. Passing a callback to it, to handle
        #    termination in any way.
        def _release():
            self.server.locked = False

        try:
            if format != "web":
                run_native.run_game(real_directory_path, real_relative_command_path, package, app,
                                    save_filters, _release)
            else:
                run_web.run_game(real_directory_path, real_relative_command_path, package, app, _release)
        except Exception as e:
            self._send_response({"status": "error", "hint": "unknown", "type": type(e).__name__,
                                 "traceback": traceback.format_exc()})


def launch_main_server():
    """
    Launches the server using the main binding.
    """

    os.system(f"rm {MAIN_BINDING}")
    os.system(f"sudo mkdir -p {os.path.dirname(MAIN_BINDING)}")
    with GameLauncherServer(MAIN_BINDING, GameLauncherRequestHandler) as f:
        f.serve_forever()
