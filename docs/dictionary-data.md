# Dictionary Data

The app keeps dictionary data file-based. PostgreSQL stores user data only, such as accounts, decks, saved vocabulary, custom terms, shared decks, and review progress. Do not import the full JMdict or Kaikki/Wiktionary datasets into PostgreSQL.

## Local Dictionary Files

- Default development dictionary: `backend/data/dictionary/jmdict_sample.json`
- Optional full dictionary: `backend/data/dictionary/jmdict_full.json`
- English-to-Korean fallback sample: `backend/data/dictionary/en_ko_sample.json`
- Optional full English-to-Korean fallback: `backend/data/dictionary/en_ko_full.json`

If `jmdict_full.json` exists and is valid, the backend loads it before the sample file. If it is missing or invalid, the app falls back to `jmdict_sample.json`. If neither file can be loaded, the app still starts and returns empty JMdict fallback results.

`jmdict_full.json` is intentionally ignored by Git because it can be large. Keep `jmdict_sample.json` committed for local development and tests.

`en_ko_full.json` is generated from Kaikki/Wiktionary raw data and is also ignored by Git. Keep `en_ko_sample.json` committed for local development and smoke tests.

## Supported JSON Entry Formats

The loader accepts a list of entries, or an object with an entry list under `entries`, `words`, `jmdict`, or `JMdict`.

App-normalized format:

```json
{
  "kanji": ["怠惰"],
  "kana": ["たいだ"],
  "glosses": ["laziness", "sloth"]
}
```

Object format:

```json
{
  "kanji": [{"text": "怠惰"}],
  "kana": [{"text": "たいだ"}],
  "sense": [{"gloss": [{"text": "laziness"}]}]
}
```

`k_ele` / `r_ele` / `sense` format:

```json
{
  "k_ele": [{"keb": "怠惰"}],
  "r_ele": [{"reb": "たいだ"}],
  "sense": [{"gloss": ["laziness"]}]
}
```

For best runtime behavior, normalize full dictionary data into the app-normalized format:

```bash
cd backend
python scripts/normalize_jmdict_json.py --input raw_jmdict.json --output data/dictionary/jmdict_full.json
```

Check the active dictionary without printing full contents:

```bash
cd backend
python scripts/check_dictionary_file.py
python scripts/check_en_ko_dictionary.py
```

Build an English-to-Korean fallback subset from a Kaikki/Wiktionary JSON or JSONL dump:

```bash
cd backend
python scripts/build_en_ko_from_kaikki.py --input kaikki_raw.jsonl --output data/dictionary/en_ko_full.json
```

## Meaning Priority

`meaning_ko` is resolved in this order:

1. User-defined term meaning
2. Built-in Korean dictionary meaning
3. Korean fallback mapped from local JMdict glosses through `en_ko_full.json` or `en_ko_sample.json`
4. Deprecated manual exception mapper for small gaps
5. Empty string

`dictionary_gloss` remains auxiliary data. The main learning UI should prioritize Korean meanings.

## Production Placement Strategy

Render deployments may not include `jmdict_full.json` automatically. The current production delivery path is environment-variable based:

- Put the normalized full dictionary JSON file in private storage that can be read by the backend.
- Set `JMDICT_FULL_JSON_URL` in the Render backend environment to that file URL.
- The URL may point to a plain `.json` file or a `.json.zip` / `.zip` archive. GitHub release asset ZIP URLs are supported; the backend extracts one JSON file and stores only JSON content as `jmdict_full.json`.
- On backend startup, if `backend/data/dictionary/jmdict_full.json` is missing, the app downloads the file to a temporary path, extracts it if needed, validates it as JSON, and then moves it into place.
- If the file already exists, startup skips the download.
- If `JMDICT_FULL_JSON_URL` is missing or the download fails, the app continues with `jmdict_sample.json` fallback.
- A `sha256:...` value is an integrity hash, not a download URL. Do not put hash text in `JMDICT_FULL_JSON_URL`.

Do not commit the full files, and do not store the full JMdict or Kaikki/Wiktionary data in PostgreSQL. Render's filesystem can be ephemeral, so the file may need to be downloaded again after restart or redeploy. A Render persistent disk or a dedicated dictionary artifact/storage flow can be reviewed later for paid or more stable operations.

Optional environment variables:

- `JMDICT_FULL_JSON_URL`: URL for the normalized full dictionary JSON file, either plain `.json` or zipped `.json.zip` / `.zip`.
- `JMDICT_FULL_JSON_PATH`: custom local path for the downloaded or pre-mounted full dictionary file.

Neither variable should contain secrets in committed documentation. If the URL is private or signed, configure it only in the host environment UI.

## Source Notice

The dictionary fallback can use JMdict/EDICT project data by EDRDG and Kaikki/Wiktionary data. JMdict/EDICT has its own license requirements, and Kaikki/Wiktionary data can require CC-BY-SA/GFDL attribution and share-alike handling. Keep appropriate source and license notices in product and deployment documentation. User-defined terms and personal vocabulary data are stored separately from dictionary source data.
