"""
Update Manager - Handles automatic update checking, downloading, and installation.

Follows the same pattern as other managers (DeviceManager, DatabaseManager):
- Integrates with TimerService for periodic checks
- Uses Qt signals for UI notifications
- Runs network operations in background threads
"""

import os
import sys
import json
import hashlib
import logging
import subprocess
import platform
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from PyQt5.QtCore import QObject, QThread, pyqtSignal, QTimer

from config import version_number, save_path


# Update check interval: 24 hours (in milliseconds)
UPDATE_CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000

# Version manifest URL - configure this before deployment
VERSION_MANIFEST_URL = "https://YOUR-VPS-URL/multilogger/version.json"

# User agent for HTTP requests
USER_AGENT = f"Airmodus-MultiLogger/{version_number}"


class VersionCheckWorker(QThread):
    """Background thread for checking version without blocking UI."""

    finished = pyqtSignal(dict)  # Emits version info or empty dict on error
    error = pyqtSignal(str)      # Emits error message

    def __init__(self, manifest_url: str):
        super().__init__()
        self.manifest_url = manifest_url

    def run(self):
        try:
            request = Request(self.manifest_url, headers={'User-Agent': USER_AGENT})
            with urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                self.finished.emit(data)
        except (URLError, HTTPError, json.JSONDecodeError) as e:
            logging.warning(f"Version check failed: {e}")
            self.error.emit(str(e))
            self.finished.emit({})


class DownloadWorker(QThread):
    """Background thread for downloading update file."""

    progress = pyqtSignal(int, int)  # (downloaded_bytes, total_bytes)
    finished = pyqtSignal(str)       # Emits path to downloaded file
    error = pyqtSignal(str)          # Emits error message

    def __init__(self, download_url: str, expected_hash: str, expected_size: int):
        super().__init__()
        self.download_url = download_url
        self.expected_hash = expected_hash
        self.expected_size = expected_size
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        # Define temp_file path upfront so it's available in exception handler
        temp_dir = os.path.join(save_path, '.update_temp')
        temp_file = os.path.join(temp_dir, 'update.exe')

        try:
            # Create temp directory for download
            os.makedirs(temp_dir, exist_ok=True)

            request = Request(self.download_url, headers={'User-Agent': USER_AGENT})

            # Use longer timeout for large file downloads (10 minutes)
            with urlopen(request, timeout=600) as response:
                total_size = int(response.headers.get('content-length', self.expected_size))
                downloaded = 0
                hash_obj = hashlib.sha256()

                with open(temp_file, 'wb') as f:
                    while True:
                        if self._cancelled:
                            # Clean up on cancel
                            try:
                                os.remove(temp_file)
                            except:
                                pass
                            self.error.emit("Download cancelled")
                            return

                        chunk = response.read(8192)
                        if not chunk:
                            break

                        f.write(chunk)
                        hash_obj.update(chunk)
                        downloaded += len(chunk)
                        self.progress.emit(downloaded, total_size)

            # Verify hash if provided
            if self.expected_hash and hash_obj.hexdigest().lower() != self.expected_hash.lower():
                os.remove(temp_file)
                self.error.emit("Download verification failed - hash mismatch")
                return

            self.finished.emit(temp_file)

        except Exception as e:
            logging.exception("Download failed")
            # Clean up partial download
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except:
                pass
            self.error.emit(str(e))


class UpdateManager(QObject):
    """
    Manages automatic update checking and installation.

    Usage:
        update_manager = UpdateManager(main_window)
        update_manager.start()  # Starts periodic checks
        update_manager.check_now()  # Manual check

    Signals:
        update_available: Emitted when a new version is found
        download_progress: Emitted during download (bytes, total)
        update_ready: Emitted when download completes and update is ready to install
        error: Emitted on any error
    """

    update_available = pyqtSignal(dict)    # version_info dict
    download_progress = pyqtSignal(int, int)
    update_ready = pyqtSignal(str)         # path to downloaded exe
    error = pyqtSignal(str)

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.current_version = version_number
        self.latest_version_info = None
        self.downloaded_exe_path = None

        # Background workers
        self._check_worker = None
        self._download_worker = None

        # Periodic check timer
        self._check_timer = QTimer(self)
        self._check_timer.timeout.connect(self.check_now)

        # Track user preference for deferring updates
        self._update_deferred = False
        self._last_check_time = None

    def start(self):
        """Start periodic update checking."""
        # Clean up any leftover temp files from previous failed updates
        self._cleanup_temp_files()

        # Check immediately on startup (after a short delay to let UI load)
        QTimer.singleShot(5000, self.check_now)

        # Start periodic timer
        self._check_timer.start(UPDATE_CHECK_INTERVAL_MS)
        logging.info("Update manager started, checking every 24 hours")

    def _cleanup_temp_files(self):
        """Clean up any leftover temp files from failed updates."""
        try:
            temp_dir = os.path.join(save_path, '.update_temp')
            if os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
                logging.info("Cleaned up leftover update temp files")
        except Exception as e:
            logging.warning(f"Failed to clean up temp files: {e}")

    def stop(self):
        """Stop update checking and cancel any in-progress operations."""
        self._check_timer.stop()

        if self._check_worker and self._check_worker.isRunning():
            self._check_worker.terminate()

        if self._download_worker and self._download_worker.isRunning():
            self._download_worker.cancel()
            self._download_worker.wait(5000)

    def check_now(self):
        """Trigger an immediate version check."""
        if self._check_worker and self._check_worker.isRunning():
            logging.debug("Version check already in progress")
            return

        logging.info("Checking for updates...")
        self._check_worker = VersionCheckWorker(VERSION_MANIFEST_URL)
        self._check_worker.finished.connect(self._on_version_check_complete)
        self._check_worker.error.connect(lambda e: logging.warning(f"Update check error: {e}"))
        self._check_worker.start()

    def _on_version_check_complete(self, version_info: dict):
        """Handle version check result."""
        self._last_check_time = datetime.now()

        if not version_info:
            logging.info("No version info received")
            return

        latest = version_info.get('latest_version', '')
        if not latest:
            return

        self.latest_version_info = version_info

        # Compare versions
        if self._is_newer_version(latest, self.current_version):
            logging.info(f"New version available: {latest} (current: {self.current_version})")

            # Check if this is a critical update
            if version_info.get('critical', False):
                self._update_deferred = False  # Force show for critical updates

            if not self._update_deferred:
                self.update_available.emit(version_info)
        else:
            logging.info(f"Current version {self.current_version} is up to date")

    def _is_newer_version(self, new_version: str, current_version: str) -> bool:
        """Compare semantic versions (Major.Minor.Patch)."""
        try:
            new_parts = [int(x) for x in new_version.split('.')]
            current_parts = [int(x) for x in current_version.split('.')]

            # Pad with zeros if needed
            while len(new_parts) < 3:
                new_parts.append(0)
            while len(current_parts) < 3:
                current_parts.append(0)

            return new_parts > current_parts
        except (ValueError, AttributeError):
            return False

    def download_update(self):
        """Start downloading the update."""
        if not self.latest_version_info:
            self.error.emit("No update information available")
            return

        if self._download_worker and self._download_worker.isRunning():
            logging.warning("Download already in progress")
            return

        # Check if we already have a downloaded update ready
        if self.downloaded_exe_path and os.path.exists(self.downloaded_exe_path):
            logging.info("Update already downloaded, emitting ready signal")
            self.update_ready.emit(self.downloaded_exe_path)
            return

        download_url = self.latest_version_info.get('download_url', '')
        expected_hash = self.latest_version_info.get('sha256', '')
        expected_size = self.latest_version_info.get('file_size_bytes', 0)

        if not download_url:
            self.error.emit("No download URL in version info")
            return

        logging.info(f"Starting download from: {download_url}")

        self._download_worker = DownloadWorker(download_url, expected_hash, expected_size)
        self._download_worker.progress.connect(self.download_progress.emit)
        self._download_worker.finished.connect(self._on_download_complete)
        self._download_worker.error.connect(self._on_download_error)
        self._download_worker.start()

    def _on_download_complete(self, exe_path: str):
        """Handle successful download."""
        self.downloaded_exe_path = exe_path
        logging.info(f"Update downloaded to: {exe_path}")
        self.update_ready.emit(exe_path)

    def _on_download_error(self, error_msg: str):
        """Handle download failure."""
        logging.error(f"Download failed: {error_msg}")
        self.error.emit(f"Download failed: {error_msg}")

    def install_update(self):
        """
        Install the downloaded update.

        Creates a batch script that:
        1. Waits for this process to exit
        2. Replaces the current exe with the new one
        3. Restarts the application
        """
        if not self.downloaded_exe_path or not os.path.exists(self.downloaded_exe_path):
            self.error.emit("No update file available")
            return

        # Get current exe path
        if getattr(sys, 'frozen', False):
            current_exe = sys.executable
        else:
            # Running as script - can't self-update
            self.error.emit("Cannot self-update when running as script. Please download the update manually.")
            return

        # Only support Windows for self-update (batch script approach)
        if platform.system() != 'Windows':
            self.error.emit("Auto-update is only supported on Windows. Please download the update manually.")
            return

        # Create updater batch script
        updater_script = self._create_updater_script(current_exe, self.downloaded_exe_path)

        logging.info(f"Starting updater script: {updater_script}")

        # Launch the updater script (detached from this process) - Windows only
        subprocess.Popen(
            ['cmd', '/c', updater_script],
            creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS,
            close_fds=True
        )

        # Save any pending configuration
        if hasattr(self.main_window, 'save_ini'):
            self.main_window.save_ini()

        # Close the application
        from PyQt5.QtWidgets import QApplication
        QApplication.instance().quit()

    def _create_updater_script(self, current_exe: str, new_exe: str) -> str:
        """
        Create batch script for update installation.

        The script:
        1. Waits for the current process to exit
        2. Moves the old exe to backup
        3. Moves the new exe to the target location
        4. Restarts the application
        5. Cleans up temp files
        """
        script_dir = os.path.join(save_path, '.update_temp')
        script_path = os.path.join(script_dir, 'updater.bat')

        # Get the target exe name from current exe
        exe_name = os.path.basename(current_exe)
        exe_dir = os.path.dirname(current_exe)
        backup_exe = os.path.join(exe_dir, f"{exe_name}.old")

        # Get version for new exe name
        new_version = self.latest_version_info.get('latest_version', 'unknown')
        final_exe_name = f"Airmodus_MultiLogger_{new_version}.exe"
        final_exe_path = os.path.join(exe_dir, final_exe_name)

        script_content = f'''@echo off
setlocal enabledelayedexpansion

echo Airmodus MultiLogger Updater
echo ============================
echo.
echo Waiting for application to close...

:: Wait for the main process to exit (check every second for up to 30 seconds)
set /a count=0
:waitloop
tasklist /FI "IMAGENAME eq {exe_name}" 2>NUL | find /I /N "{exe_name}">NUL
if "%ERRORLEVEL%"=="0" (
    set /a count+=1
    if !count! geq 30 (
        echo Timeout waiting for application to close.
        echo Please close the application manually and try again.
        pause
        exit /b 1
    )
    timeout /t 1 /nobreak >nul
    goto waitloop
)

echo Application closed.
echo.
echo Installing update...

:: Create backup of old exe
if exist "{current_exe}" (
    echo Creating backup...
    move /Y "{current_exe}" "{backup_exe}" >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo Failed to create backup. Update aborted.
        pause
        exit /b 1
    )
)

:: Copy new exe to target location
echo Copying new version...
copy /Y "{new_exe}" "{final_exe_path}" >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo Failed to copy new version.
    echo Restoring backup...
    move /Y "{backup_exe}" "{current_exe}" >nul 2>&1
    pause
    exit /b 1
)

echo.
echo Update installed successfully!
echo.

:: Clean up temp files
echo Cleaning up...
del /F /Q "{new_exe}" >nul 2>&1
del /F /Q "{backup_exe}" >nul 2>&1
rmdir /S /Q "{script_dir}" >nul 2>&1

:: Restart application
echo Starting updated application...
start "" "{final_exe_path}"

:: This script will delete itself
(goto) 2>nul & del "%~f0"
'''

        with open(script_path, 'w') as f:
            f.write(script_content)

        return script_path

    def defer_update(self):
        """User chose to defer the update for now."""
        self._update_deferred = True
        logging.info("Update deferred by user")

    def get_status(self) -> dict:
        """Get current update status for diagnostics."""
        return {
            'current_version': self.current_version,
            'latest_version': self.latest_version_info.get('latest_version') if self.latest_version_info else None,
            'last_check': self._last_check_time.isoformat() if self._last_check_time else None,
            'update_available': self.latest_version_info is not None and
                               self._is_newer_version(
                                   self.latest_version_info.get('latest_version', ''),
                                   self.current_version
                               ),
            'update_deferred': self._update_deferred,
            'downloaded': self.downloaded_exe_path is not None
        }
