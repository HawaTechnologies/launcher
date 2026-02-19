import os
import shutil
from pathlib import Path
from typing import List, Tuple
from .yesbut import enumerate


# This is the partition where all the Dragonshark saves exist.
# This partition is ext4 and everything there will be owned by
# the non-privileged user: "pi:pi". Permissions used here will
# always be "rwxr-xr-x". This partition keeps saves for:
#
# 1. EmulationStation: /mnt/SAVES/{platform}.
# 2. DragonShark: /mnt/SAVES/dragonshark.
#
# Partition size: whatever is available.
SAVES_DISK = "/mnt/SAVES"

# This is the particular location for DragonShark games. Therein,
# games will be stored into /mnt/SAVES/dragonshark/{package}/{app},
# where the {package} is literally a package base (e.g. inverted
# domain name), which will typically be unique. Inside, the {app}
# will then be a name that will be unique inside the package base.
# As an example, let's consider the base "com.mycompany.play" (it
# might come from play.mycompany.com actually) and the app name as
# simple as "MyGame". The final location for the game's saves will
# become: "/mnt/SAVES/dragonshark/com.mycompany.play/MyGame".
DRAGONSHARK_SAVES_LOCATION = f"{SAVES_DISK}/dragonshark"

# This is the partition where the save of the current game will be
# stored. Instead of "pi:pi", the owner for this partition will be
# "pi:gamer", and the permissions will be "rwxrwx---". This would
# allow users like "gamer:gamer" to read/write into this partition.
# This partition is also ext4.
#
# Partition size: 15mb.
CURRENT_SAVE_DISK = "/mnt/CURRENT_SAVE"
CURRENT_SAVE_LOCATION = CURRENT_SAVE_DISK


def _copy(*, from_dir: str | Path, to_dir: str | Path, what: str) -> None:
    """
    Copy {from_dir}/{what} -> {to_dir}/{what}.

    Preconditions (per your spec):
      - from_dir and to_dir exist, are writable directories
      - what is a relative path
      - {from_dir}/{what} exists
      - Must ensure {to_dir}/{what} exists (create intermediate dirs as needed)
    """
    src_root = Path(from_dir)
    dst_root = Path(to_dir)

    # what is relative (precondition), but we still normalize it
    rel = Path(what)

    src = (src_root / rel)
    dst = (dst_root / rel)

    if src.is_dir():
        # Ensure destination directory exists, including parents
        dst.mkdir(parents=True, exist_ok=True)

        # Copy contents of src into dst (merge-style)
        # (Python 3.8+)
        shutil.copytree(src, dst, dirs_exist_ok=True, copy_function=shutil.copy2)
    else:
        # Ensure parent directories exist
        dst.parent.mkdir(parents=True, exist_ok=True)

        # Copy file (preserve metadata)
        shutil.copy2(src, dst)


def get_dragonshark_game_save_path(package_base: str, app: str):
    """
    Generates the save directory for a game.
    :param package_base: The package base.
    :param app: The app name.
    :return: The full path.
    """

    return f"{DRAGONSHARK_SAVES_LOCATION}/{package_base}/{app}"


def store_dragonshark_save(package_base: str, app: str, save_filters: List[Tuple[str, List[str]]]):
    """
    Stores a save from a game, if available. This implies copying
    everything from the /mnt/CURRENT_SAVE into /mnt/SAVES into the
    proper package/app directory.
    :param package_base: The package base. Presumed as validated.
    :param app: The app name. Presumed as validated.
    :param save_filters: The save filters.
    """

    source = CURRENT_SAVE_LOCATION
    target = get_dragonshark_game_save_path(package_base, app)
    # First, touch the tmp/target directories to ensure they exist.
    # The source directory already exists.
    os.system(f"mkdir -p {SAVES_DISK}/~tmp && mkdir -p {target}")

    # Copy all the allowed elements.
    for element in enumerate(save_filters, CURRENT_SAVE_LOCATION):
        relative_element = element[len(CURRENT_SAVE_LOCATION)+1:]
        if not relative_element:
            continue
        _copy(from_dir=CURRENT_SAVE_LOCATION, to_dir=target, what=relative_element)

    instructions = [
        # Remember that these all instructions will be executed by root,
        # actually (the service itself, which runs root, will be calling
        # this function).

        # First, copy the save, if any, into the SAVES_DISK/~tmp directory.
        # If these operations (actually: the second one) cannot be performed,
        # then this stops here: there's nothing to save.
        f"cp -r {source}/* {SAVES_DISK}/~tmp",
        # Then, remove any previous target directory and move SAVES_DISK/~tmp
        # to this target directory.
        f"rm -rf {target}",
        f"mv {SAVES_DISK}/~tmp {target}",
        # Finally, make a chown to pi:pi of all the new  files (since they'll
        # be root:root now) and a chmod to 0700.
        f"chown -R pi:pi {target}",
        f"chmod -R 0700 {target}"
    ]
    os.system(' && '.join(instructions))


def load_dragonshark_save(package_base: str, app: str):
    """
    Loads a save for a game, if available. This implies cleaning the
    /mnt/CURRENT_SAVE directory and then loading, if available, any
    contents from the /mnt/SAVES (for the current game) into that
    /mnt/CURRENT_SAVE directory.
    :param package_base: The package base. Presumed as validated.
    :param app: The app name. Presumed as validated.
    """

    source = get_dragonshark_game_save_path(package_base, app)
    target = CURRENT_SAVE_LOCATION
    # First, clear the target directory.
    os.system(f"rm -rf {target}/*")
    instructions = [
        # Remember that these all instructions will be executed by root,
        # actually (the service itself, which runs root, will be calling
        # this function).

        # First, copy the save contents from the source into the target.
        # If this fails, then there's nothing else to do.
        f"cp -r {source}/* {target}",
        # Then, chown and chmod everything so "gamer" user can take it.
        # At most 15mb can be moved this way.
        f"chown -R pi:gamer {target}",
        f"chmod -R 0770 {target}"
    ]
    os.system(' && '.join(instructions))
