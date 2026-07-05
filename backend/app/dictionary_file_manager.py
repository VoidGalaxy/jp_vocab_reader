from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


DICTIONARY_DIR = Path(__file__).resolve().parents[1] / "data" / "dictionary"
DEFAULT_JMDICT_FULL_PATH = DICTIONARY_DIR / "jmdict_full.json"
JMDICT_FULL_JSON_PATH_ENV = "JMDICT_FULL_JSON_PATH"
JMDICT_FULL_JSON_URL_ENV = "JMDICT_FULL_JSON_URL"
DOWNLOAD_TIMEOUT_SECONDS = 120

logger = logging.getLogger(__name__)


def get_full_dictionary_path() -> Path:
    configured_path = os.getenv(JMDICT_FULL_JSON_PATH_ENV, "").strip()
    if configured_path:
        return Path(configured_path).expanduser()
    return DEFAULT_JMDICT_FULL_PATH


def get_full_dictionary_url() -> str:
    return os.getenv(JMDICT_FULL_JSON_URL_ENV, "").strip()


def ensure_full_dictionary_file() -> dict[str, str]:
    full_path = get_full_dictionary_path()
    if full_path.exists():
        logger.info("JMdict full dictionary already exists: %s", full_path)
        return {"status": "exists", "path": str(full_path)}

    url = get_full_dictionary_url()
    if not url:
        logger.info("JMDICT_FULL_JSON_URL not configured; using local fallback")
        return {"status": "not-configured", "path": str(full_path)}

    full_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = full_path.with_name(f"{full_path.name}.download")

    logger.info("Downloading JMdict full dictionary to %s", full_path)
    try:
        with urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            with temp_path.open("wb") as output:
                shutil.copyfileobj(response, output)

        if temp_path.stat().st_size <= 0:
            raise OSError("downloaded file is empty")

        os.replace(temp_path, full_path)
    except (HTTPError, URLError, OSError, TimeoutError, ValueError) as exc:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Failed to remove temporary JMdict download file: %s", temp_path)
        logger.warning(
            "Failed to download JMdict full dictionary; falling back to sample (%s)",
            exc,
        )
        return {"status": "failed", "path": str(full_path)}

    logger.info(
        "JMdict full dictionary downloaded: %s (%s bytes)",
        full_path,
        full_path.stat().st_size,
    )
    return {"status": "downloaded", "path": str(full_path)}
