# Hawa Launcher

A service that launches a Hawa game. Games are running using a special command described later.

This service is compatible with Python 3.12.

## Installation

Ensure you run this server always in the context of `root` user.

Ensure the proper packages are installed. Either use virtualenv or `sudo apt install python-pip`:

    pip install -r requirements.txt

Then, run the server always in the context of `root` user (or sudo):

    sudo ./launch-server

Or perhaps running it as a service owned by root (e.g. create the /etc/systemd/system/hawa-launcher.service file):

    [Unit]
    Description=Hawa Launcher
    After=network.target

    [Service]
    User=root
    Group=root
    WorkingDirectory=/opt/Hawa/launcher
    ExecStart=/opt/Hawa/launcher/launch-server
    ExecStop=pkill launch-server
    Restart=always
    TimeoutStopSec=1s

    [Install]
    WantedBy=multi-user.target

Then, enable the new service:

    sudo systemctl enable hawa-launcher.service

Finally, ensure `virtualpad-admin` is owned by the group `hawamgmt`.

    sudo groupadd hawalnch
    sudo ln -s /opt/Hawa/launcher/launch-game /usr/local/bin/launch-game
    sudo chmod ug+rx /opt/Hawa/launcher/launch-game
    sudo chgrp hawalnch /opt/Hawa/launcher/launch-game

All the users that will be able to access the launch-game app must belong to that group:

    sudo usermod -aG hawalnch {username}

This code assumes this codebase is installed into `/opt/Hawa/launcher`.
