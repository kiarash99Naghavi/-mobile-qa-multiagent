"""
ADB (Android Debug Bridge) tooling for mobile device automation.
"""
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple


class ADBError(Exception):
    """Raised when ADB command fails."""
    pass


class ADB:
    """Wrapper for ADB commands to interact with Android devices/emulators."""

    def __init__(self, device_id: Optional[str] = None):
        """
        Initialize ADB wrapper.

        Args:
            device_id: Device serial number (e.g., 'emulator-5554').
                      If None, uses the only connected device.
        """
        self.device_id = device_id
        self._verify_adb()

    def _verify_adb(self):
        """Verify ADB is installed and accessible."""
        try:
            subprocess.run(['adb', 'version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise ADBError("ADB not found. Please install Android SDK Platform-Tools.")

    def _run_command(self, cmd: list, capture_binary: bool = False, check: bool = True) -> subprocess.CompletedProcess:
        """
        Run an ADB command.

        Args:
            cmd: Command as list of strings
            capture_binary: If True, capture output as bytes
            check: If True, raise exception on non-zero exit

        Returns:
            CompletedProcess result
        """
        full_cmd = ['adb']
        if self.device_id:
            full_cmd.extend(['-s', self.device_id])
        full_cmd.extend(cmd)

        try:
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                check=check,
                text=not capture_binary
            )
            return result
        except subprocess.CalledProcessError as e:
            raise ADBError(f"ADB command failed: {' '.join(full_cmd)}\nError: {e.stderr}")

    def install_apk(self, apk_path: str, replace: bool = True) -> bool:
        """
        Install an APK on the device.

        Args:
            apk_path: Path to APK file
            replace: If True, replace existing app

        Returns:
            True if successful
        """
        if not Path(apk_path).exists():
            raise ADBError(f"APK not found: {apk_path}")

        cmd = ['install']
        if replace:
            cmd.append('-r')
        cmd.append(apk_path)

        result = self._run_command(cmd)
        return 'Success' in result.stdout

    def list_packages(self, filter_text: Optional[str] = None) -> list[str]:
        """
        List installed packages on device.

        Args:
            filter_text: Optional text to filter package names

        Returns:
            List of package names
        """
        cmd = ['shell', 'pm', 'list', 'packages']
        if filter_text:
            cmd.append(filter_text)

        result = self._run_command(cmd)
        packages = [line.replace('package:', '').strip()
                   for line in result.stdout.split('\n') if line.strip()]
        return packages

    def wm_size(self) -> Tuple[int, int]:
        """
        Get device screen size.

        Returns:
            Tuple of (width, height)
        """
        result = self._run_command(['shell', 'wm', 'size'])
        # Output format: "Physical size: 1080x2400"
        size_line = result.stdout.strip().split('\n')[-1]
        if ':' in size_line:
            size_str = size_line.split(':')[-1].strip()
            width, height = map(int, size_str.split('x'))
            return (width, height)
        raise ADBError(f"Could not parse screen size: {result.stdout}")

    def screenshot(self, output_path: str) -> bool:
        """
        Take a screenshot and save to file.

        Args:
            output_path: Local path to save screenshot (PNG format)

        Returns:
            True if successful
        """
        # Use exec-out to get raw PNG data without line ending conversion
        result = self._run_command(['exec-out', 'screencap', '-p'], capture_binary=True)

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'wb') as f:
            f.write(result.stdout)

        return output_file.exists() and output_file.stat().st_size > 0

    def tap_xy(self, x: int, y: int, wait_after: float = 0.0) -> bool:
        """
        Tap at specific coordinates.

        Args:
            x: X coordinate
            y: Y coordinate
            wait_after: Seconds to wait after tap (default 0.0, ZERO WAIT)

        Returns:
            True if successful
        """
        self._run_command(['shell', 'input', 'tap', str(x), str(y)])
        return True

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 150, wait_after: float = 0.0) -> bool:
        """
        Swipe from one point to another.

        Args:
            x1, y1: Start coordinates
            x2, y2: End coordinates
            duration_ms: Swipe duration in milliseconds (default 150, SUPER FAST)
            wait_after: Seconds to wait after swipe (default 0.0, ZERO WAIT)

        Returns:
            True if successful
        """
        self._run_command([
            'shell', 'input', 'swipe',
            str(x1), str(y1), str(x2), str(y2), str(duration_ms)
        ])
        return True

    def keyevent(self, keycode: int | str, wait_after: float = 0.0) -> bool:
        """
        Send a key event.

        Args:
            keycode: Key code (int) or name (str)
                    Common codes: KEYCODE_HOME=3, KEYCODE_BACK=4, KEYCODE_ENTER=66
            wait_after: Seconds to wait after keypress (default 0.0, ZERO WAIT)

        Returns:
            True if successful
        """
        self._run_command(['shell', 'input', 'keyevent', str(keycode)])
        return True

    def type_text(self, text: str, wait_after: float = 0.0) -> bool:
        """
        Type text (note: only works for ASCII, spaces become %s).

        Args:
            text: Text to type
            wait_after: Seconds to wait after typing (default 0.0, ZERO WAIT)

        Returns:
            True if successful
        """
        # Escape spaces and special characters for shell
        escaped_text = text.replace(' ', '%s')
        self._run_command(['shell', 'input', 'text', escaped_text])
        return True

    def start_activity(self, package: str, activity: Optional[str] = None, wait_after: float = 0.0) -> bool:
        """
        Start an app activity.

        Args:
            package: Package name
            activity: Activity name (if None, launches default)
            wait_after: Seconds to wait after launch (default 0.0, ZERO WAIT)

        Returns:
            True if successful
        """
        cmd = ['shell', 'am', 'start', '-n']
        if activity:
            cmd.append(f"{package}/{activity}")
        else:
            # Launch default activity
            cmd = ['shell', 'monkey', '-p', package, '-c', 'android.intent.category.LAUNCHER', '1']

        self._run_command(cmd)
        return True

    def clear_app_data(self, package: str) -> bool:
        """
        Clear app data and cache.

        Args:
            package: Package name

        Returns:
            True if successful
        """
        result = self._run_command(['shell', 'pm', 'clear', package])
        return 'Success' in result.stdout

    def shell(self, command: str) -> str:
        """
        Execute arbitrary shell command.

        Args:
            command: Shell command to execute

        Returns:
            Command output
        """
        result = self._run_command(['shell', command])
        return result.stdout.strip()
