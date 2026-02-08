#!/usr/bin/env python3
import os
import subprocess
import stat
from pathlib import Path

def _get_mount_point(file_path):
    """
    Find the mount point for a given file path.
    Traverses up until the current directory is
    a mount point. If it does not belong to a
    mount point, returns None.
    """
    
    path = Path(file_path).resolve()
    
    # Walk up the directory tree until we find a mount point
    while not os.path.ismount(path):
        parent = path.parent
        if parent == path:  # Reached root
            return None
        path = parent
    
    return str(path)

def _get_device_for_mount_point(mount_point):
    """
    Get the device (e.g. /dev/sda) for a mount point.
    If it does not belong to a mounted device, it
    returns None.
    """
    
    try:
        result = subprocess.run(
            ['findmnt', '-n', '-o', 'SOURCE', mount_point],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None

def _is_fat_filesystem(mount_point):
    """
    Check if the mount point is a FAT filesystem.
    """
    
    try:
        result = subprocess.run(
            ['findmnt', '-n', '-o', 'FSTYPE', mount_point],
            capture_output=True,
            text=True,
            check=True
        )
        fstype = result.stdout.strip().lower()
        return fstype in ['vfat', 'fat', 'fat32', 'exfat']
    except subprocess.CalledProcessError:
        return False

def _has_execute_permission(file_path):
    """
    Check if a file has execute permission.
    """
    
    try:
        st = os.stat(file_path)
        return bool(st.st_mode & stat.S_IXUSR)
    except OSError:
        return False

def _remount_with_exec(mount_point, device):
    """
    Remount a filesystem with execute permissions. This involves
    three steps:
    1. Unmount.
    2. Re-create directory.
    3. Re-mount with masks 0000.
    """
    
    try:
        # Unmount
        subprocess.run(['sudo', 'umount', mount_point], check=True)
        
        # Recreate mount point if needed
        subprocess.run(['sudo', 'mkdir', '-p', mount_point], check=True)
        
        # Remount with fmask=0000,dmask=0000
        subprocess.run([
            'sudo', 'mount', '-o', 
            'fmask=0000,dmask=0000', 
            device, mount_point
        ], check=True)
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error remounting: {e}")
        return False

def ensure_executable(script_path):
    """
    Ensure a script is executable.
    Returns: (success: bool, executable_path: str, error_message: str).
    """

    # Step 1: Check if file exists
    if not os.path.isfile(script_path):
        return False, None, f"File does not exist: {script_path}"
    
    # Step 2: Check if already executable
    if has_execute_permission(script_path):
        return True, script_path, None
    
    # Try simple chmod first
    try:
        os.chmod(script_path, os.stat(script_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        if _has_execute_permission(script_path):
            return True, script_path, None
    except (OSError, PermissionError):
        pass  # chmod failed, continue to remount strategy
    
    # Get mount point and check if it's FAT
    mount_point = _get_mount_point(script_path)
    if not mount_point:
        return False, None, "Could not determine mount point"
    
    # If not a FAT filesystem, we have a different problem
    if not _is_fat_filesystem(mount_point):
        return False, None, f"File is not executable and chmod failed (filesystem: {mount_point})"
    
    # It's a FAT filesystem - need to remount
    device = _get_device_for_mount_point(mount_point)
    if not device:
        return False, None, f"Could not determine device for mount point: {mount_point}"
    
    print(f"FAT filesystem detected. Remounting {device} at {mount_point} with execute permissions...")
    
    if not _remount_with_exec(mount_point, device):
        return False, None, "Failed to remount filesystem"
    
    # Check again after remount
    if _has_execute_permission(script_path):
        return True, script_path, None
    else:
        return False, None, "File still not executable after remount"
