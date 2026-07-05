from __future__ import annotations

import logging
import os
import shutil
import json
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


DICTIONARY_DIR = Path(__file__).resolve().parents[1] / "data" / "dictionary"
DEFAULT_JMDICT_FULL_PATH = DICTIONARY_DIR / "jmdict_full.json"
JMDICT_FULL_JSON_PATH_ENV = "JMDICT_FULL_JSON_PATH"
JMDICT_FULL_JSON_URL_ENV = "JMDICT_FULL_JSON_URL"
DOWNLOAD_TIMEOUT_SECONDS = 120
ZIP_SUFFIXES = (".zip", ".json.zip")
JSON_SUFFIX = ".json"

logger = logging.getLogger(__name__)


def get_full_dictionary_path() -> Path:
    configured_path = os.getenv(JMDICT_FULL_JSON_PATH_ENV, "").strip()
    if configured_path:
        return Path(configured_path).expanduser()
    return DEFAULT_JMDICT_FULL_PATH


def get_full_dictionary_url() -> str:
    return os.getenv(JMDICT_FULL_JSON_URL_ENV, "").strip()


def _url_points_to_zip(url: str) -> bool:
    url_path = url.split("?", 1)[0].split("#", 1)[0].lower()
    return url_path.endswith(ZIP_SUFFIXES)


def _select_json_member(names: list[str]) -> str | None:
    json_names = [name for name in names if name.lower().endswith(JSON_SUFFIX)]
    if not json_names:
        return None

    for name in json_names:
        filename = Path(name).name.lower()
        if filename.startswith("jmdict") and filename.endswith(JSON_SUFFIX):
            return name

    for name in json_names:
        filename = Path(name).name.lower()
        if "jmdict" in filename and filename.endswith(JSON_SUFFIX):
            return name

    return json_names[0]


def _validate_json_file(path: Path) -> None:
    with path.open("r", encoding="utf-8") as input_file:
        json.load(input_file)


def _prepare_downloaded_dictionary(
    *, downloaded_path: Path, prepared_path: Path, source_url: str
) -> None:
    if _url_points_to_zip(source_url):
        logger.info("Detected ZIP dictionary archive")
        with zipfile.ZipFile(downloaded_path) as archive:
            member_name = _select_json_member(archive.namelist())
            if not member_name:
                raise ValueError("ZIP archive does not contain a JSON file")
            with archive.open(member_name) as input_file:
                with prepared_path.open("wb") as output_file:
                    shutil.copyfileobj(input_file, output_file)
        logger.info("Extracted JSON from dictionary archive")
    else:
        shutil.copyfile(downloaded_path, prepared_path)

    if prepared_path.stat().st_size <= 0:
        raise OSError("prepared dictionary file is empty")

    _validate_json_file(prepared_path)
    logger.info("Validated JMdict full dictionary JSON")


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
    download_path = full_path.with_name(f"{full_path.name}.download")
    prepared_path = full_path.with_name(f"{full_path.name}.prepared")

    logger.info("Downloading JMdict full dictionary")
    try:
        with urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            with download_path.open("wb") as output:
                shutil.copyfileobj(response, output)

        if download_path.stat().st_size <= 0:
            raise OSError("downloaded file is empty")

        _prepare_downloaded_dictionary(
            downloaded_path=download_path,
            prepared_path=prepared_path,
            source_url=url,
        )
        os.replace(prepared_path, full_path)
    except (
        HTTPError,
        URLError,
        OSError,
        TimeoutError,
        ValueError,
        json.JSONDecodeError,
        zipfile.BadZipFile,
    ) as exc:
        for path in (download_path, prepared_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Failed to remove temporary JMdict file: %s", path)
        logger.warning(
            "Failed to prepare JMdict full dictionary; falling back to sample (%s)",
            exc,
        )
        return {"status": "failed", "path": str(full_path)}
    finally:
        for path in (download_path, prepared_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Failed to remove temporary JMdict file: %s", path)

    logger.info(
        "JMdict full dictionary downloaded: %s (%s bytes)",
        full_path,
        full_path.stat().st_size,
    )
    return {"status": "downloaded", "path": str(full_path)}
