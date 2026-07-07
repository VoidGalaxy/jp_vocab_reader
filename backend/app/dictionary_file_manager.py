from __future__ import annotations

import gzip
import logging
import os
import shutil
import json
import zipfile
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


DICTIONARY_DIR = Path(__file__).resolve().parents[1] / "data" / "dictionary"
DEFAULT_JMDICT_FULL_PATH = DICTIONARY_DIR / "jmdict_full.json"
JMDICT_FULL_JSON_PATH_ENV = "JMDICT_FULL_JSON_PATH"
JMDICT_FULL_JSON_URL_ENV = "JMDICT_FULL_JSON_URL"

DEFAULT_EN_KO_FULL_PATH = DICTIONARY_DIR / "en_ko_full.json"
EN_KO_DICTIONARY_PATH_ENV = "EN_KO_DICTIONARY_PATH"
EN_KO_DICTIONARY_URL_ENV = "EN_KO_DICTIONARY_URL"

DEFAULT_KRDICT_REVERSE_FULL_PATH = DICTIONARY_DIR / "krdict_reverse_full.json"
KRDICT_REVERSE_PATH_ENV = "KRDIC_REVERSE_PATH"
KRDICT_REVERSE_URL_ENV = "KRDIC_REVERSE_URL"

DOWNLOAD_TIMEOUT_SECONDS = 120
ZIP_SUFFIXES = (".zip", ".json.zip")
GZIP_SUFFIXES = (".gz", ".json.gz")
JSON_SUFFIX = ".json"

logger = logging.getLogger(__name__)


def get_full_dictionary_path() -> Path:
    configured_path = os.getenv(JMDICT_FULL_JSON_PATH_ENV, "").strip()
    if configured_path:
        return Path(configured_path).expanduser()
    return DEFAULT_JMDICT_FULL_PATH


def get_full_dictionary_url() -> str:
    return os.getenv(JMDICT_FULL_JSON_URL_ENV, "").strip()


def get_en_ko_dictionary_path() -> Path:
    configured_path = os.getenv(EN_KO_DICTIONARY_PATH_ENV, "").strip()
    if configured_path:
        return Path(configured_path).expanduser()
    return DEFAULT_EN_KO_FULL_PATH


def get_en_ko_dictionary_url() -> str:
    return os.getenv(EN_KO_DICTIONARY_URL_ENV, "").strip()


def get_krdict_reverse_path() -> Path:
    configured_path = os.getenv(KRDICT_REVERSE_PATH_ENV, "").strip()
    if configured_path:
        return Path(configured_path).expanduser()
    return DEFAULT_KRDICT_REVERSE_FULL_PATH


def get_krdict_reverse_url() -> str:
    return os.getenv(KRDICT_REVERSE_URL_ENV, "").strip()


def _url_matches_suffix(url: str, suffixes: tuple[str, ...]) -> bool:
    url_path = url.split("?", 1)[0].split("#", 1)[0].lower()
    return url_path.endswith(suffixes)


def _select_json_member(names: list[str], name_prefix: str) -> str | None:
    json_names = [name for name in names if name.lower().endswith(JSON_SUFFIX)]
    if not json_names:
        return None

    for name in json_names:
        filename = Path(name).name.lower()
        if filename.startswith(name_prefix) and filename.endswith(JSON_SUFFIX):
            return name

    for name in json_names:
        filename = Path(name).name.lower()
        if name_prefix in filename and filename.endswith(JSON_SUFFIX):
            return name

    return json_names[0]


def _validate_json_file(path: Path) -> None:
    with path.open("r", encoding="utf-8") as input_file:
        json.load(input_file)


def validate_krdict_reverse_json_file(path: Path) -> None:
    """Structural check for a krdict reverse index file: a JSON object
    mapping English gloss strings to lists of Korean candidate strings,
    with at least one entry. Deliberately shallow (no deep Korean-text
    validation) so it stays fast on a large file."""
    with path.open("r", encoding="utf-8") as input_file:
        data = json.load(input_file)
    if not isinstance(data, dict):
        raise ValueError("krdict reverse index root must be a JSON object")
    if not data:
        raise ValueError("krdict reverse index is empty")
    for key, value in data.items():
        if not isinstance(key, str):
            raise ValueError("krdict reverse index keys must be strings")
        if not isinstance(value, list):
            raise ValueError(f"krdict reverse index value for {key!r} must be a list")
        if not all(isinstance(item, str) for item in value):
            raise ValueError(
                f"krdict reverse index value for {key!r} must contain only strings"
            )


def _prepare_downloaded_dictionary(
    *,
    downloaded_path: Path,
    prepared_path: Path,
    source_url: str,
    name_prefix: str,
    validate: Callable[[Path], None] = _validate_json_file,
) -> None:
    if _url_matches_suffix(source_url, ZIP_SUFFIXES):
        logger.info("Detected ZIP dictionary archive")
        with zipfile.ZipFile(downloaded_path) as archive:
            member_name = _select_json_member(archive.namelist(), name_prefix)
            if not member_name:
                raise ValueError("ZIP archive does not contain a JSON file")
            with archive.open(member_name) as input_file:
                with prepared_path.open("wb") as output_file:
                    shutil.copyfileobj(input_file, output_file)
        logger.info("Extracted JSON from dictionary archive")
    elif _url_matches_suffix(source_url, GZIP_SUFFIXES):
        logger.info("Detected GZIP dictionary file")
        with gzip.open(downloaded_path, "rb") as input_file:
            with prepared_path.open("wb") as output_file:
                shutil.copyfileobj(input_file, output_file)
        logger.info("Decompressed GZIP dictionary file")
    else:
        shutil.copyfile(downloaded_path, prepared_path)

    if prepared_path.stat().st_size <= 0:
        raise OSError("prepared dictionary file is empty")

    validate(prepared_path)
    logger.info("Validated dictionary JSON")


def _ensure_dictionary_file(
    *,
    get_path,
    get_url,
    name_prefix: str,
    label: str,
    validate: Callable[[Path], None] = _validate_json_file,
) -> dict[str, str]:
    full_path = get_path()
    if full_path.exists():
        logger.info("%s already exists: %s", label, full_path)
        return {"status": "exists", "path": str(full_path)}

    url = get_url()
    if not url:
        logger.info("%s URL not configured; using local fallback", label)
        return {"status": "not-configured", "path": str(full_path)}

    full_path.parent.mkdir(parents=True, exist_ok=True)
    download_path = full_path.with_name(f"{full_path.name}.download")
    prepared_path = full_path.with_name(f"{full_path.name}.prepared")

    logger.info("Downloading %s", label)
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
            name_prefix=name_prefix,
            validate=validate,
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
        gzip.BadGzipFile,
    ) as exc:
        for path in (download_path, prepared_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Failed to remove temporary file: %s", path)
        logger.warning(
            "Failed to prepare %s; falling back to sample (%s)",
            label,
            exc,
        )
        return {"status": "failed", "path": str(full_path)}
    finally:
        for path in (download_path, prepared_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Failed to remove temporary file: %s", path)

    logger.info(
        "%s downloaded: %s (%s bytes)",
        label,
        full_path,
        full_path.stat().st_size,
    )
    return {"status": "downloaded", "path": str(full_path)}


def ensure_full_dictionary_file() -> dict[str, str]:
    return _ensure_dictionary_file(
        get_path=get_full_dictionary_path,
        get_url=get_full_dictionary_url,
        name_prefix="jmdict",
        label="JMdict full dictionary",
    )


def ensure_en_ko_dictionary_file() -> dict[str, str]:
    return _ensure_dictionary_file(
        get_path=get_en_ko_dictionary_path,
        get_url=get_en_ko_dictionary_url,
        name_prefix="en_ko",
        label="English-Korean dictionary",
    )


def ensure_krdict_reverse_file() -> dict[str, str]:
    return _ensure_dictionary_file(
        get_path=get_krdict_reverse_path,
        get_url=get_krdict_reverse_url,
        name_prefix="krdict",
        label="krdict reverse index",
        validate=validate_krdict_reverse_json_file,
    )
