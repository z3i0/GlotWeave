import logging
import requests
import threading
from PySide6.QtCore import QObject, Signal
from app.config import APP_VERSION

logger = logging.getLogger(__name__)


class UpdateChecker(QObject):
    """Checks for new versions of the application from a update URL."""
    update_available = Signal(str, str)  # Emits (new_version, download_url)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.update_url = "https://api.github.com/repos/z3i0/GlotWeave/releases/latest"

    def check_for_updates(self) -> None:
        """Trigger an update check in a background thread."""
        threading.Thread(target=self._check_worker, daemon=True).start()

    def _check_worker(self) -> None:
        """Run the actual API call in the background."""
        logger.info("Checking for application updates...")
        try:
            headers = {"User-Agent": "GlotWeave-App"}
            response = requests.get(self.update_url, headers=headers, timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                latest_version = data.get("tag_name", "").replace("v", "")
                download_url = data.get("html_url", "")
                
                # Simple semantic version check
                if latest_version and latest_version != APP_VERSION:
                    logger.info(f"New update found: {latest_version}")
                    self.update_available.emit(latest_version, download_url)
                else:
                    logger.info("Application is up to date.")
            else:
                logger.warning(f"Update check returned status code {response.status_code}")
        except Exception as e:
            logger.warning(f"Failed to check for updates: {e}")
