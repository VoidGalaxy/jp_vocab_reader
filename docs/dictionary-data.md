# Dictionary Data

The app keeps dictionary data file-based. PostgreSQL stores user data only, such as accounts, decks, saved vocabulary, custom terms, shared decks, and review progress. Do not import the full JMdict or Kaikki/Wiktionary datasets into PostgreSQL.

## Local Dictionary Files

- Default development dictionary: `backend/data/dictionary/jmdict_sample.json`
- Optional full dictionary: `backend/data/dictionary/jmdict_full.json`
- English-to-Korean fallback sample: `backend/data/dictionary/en_ko_sample.json`
- Optional full English-to-Korean fallback: `backend/data/dictionary/en_ko_full.json`
- krdict reverse index sample (boost/ranking only): `backend/data/dictionary/krdict_reverse_sample.json`
- Optional full krdict reverse index: `backend/data/dictionary/krdict_reverse_full.json`

If `jmdict_full.json` exists and is valid, the backend loads it before the sample file. If it is missing or invalid, the app falls back to `jmdict_sample.json`. If neither file can be loaded, the app still starts and returns empty JMdict fallback results.

`jmdict_full.json` is intentionally ignored by Git because it can be large. Keep `jmdict_sample.json` committed for local development and tests.

`en_ko_full.json` is generated from Kaikki/Wiktionary raw data and is also ignored by Git. Keep `en_ko_sample.json` committed for local development and smoke tests.

`krdict_reverse_full.json` (see the krdict section below) is also ignored by Git. Keep `krdict_reverse_sample.json` committed for local development and tests.

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

## English-to-Korean Fallback in Production

The Kaikki/Wiktionary-derived English-to-Korean fallback (`en_ko_full.json`) follows the same environment-variable delivery path as `jmdict_full.json`:

1. Build the file locally from a Kaikki/Wiktionary raw dump:

   ```bash
   cd backend
   python scripts/build_en_ko_from_kaikki.py --input kaikki_raw.jsonl --output data/dictionary/en_ko_full.json
   ```

2. Do not commit `en_ko_full.json`, `en_ko_raw.json`, or the Kaikki raw `jsonl`/`jsonl.gz` dump to Git; all are ignored by `.gitignore`.
3. Upload `en_ko_full.json` (or a gzipped/zipped version) to private file storage: a GitHub Release asset, Cloudflare R2, S3, or similar.
4. Set `EN_KO_DICTIONARY_URL` in the Render backend environment to that file's download URL.
5. On backend startup, if `backend/data/dictionary/en_ko_full.json` is missing, the app downloads the file to a temporary path, decompresses/extracts it if needed, validates it as JSON, and only then moves it into place. If the file already exists, startup skips the download.
6. If `EN_KO_DICTIONARY_URL` is missing, the download fails, or the downloaded/local file is not valid JSON, the app continues with `en_ko_sample.json` fallback instead of crashing.

Supported `EN_KO_DICTIONARY_URL` file types: `.json`, `.json.gz`, `.gz`, `.json.zip`, `.zip`. For a ZIP archive, the loader picks the JSON member whose filename starts with `en_ko`, falls back to any filename containing `en_ko`, and otherwise uses the first `.json` member found.

Optional environment variables:

- `EN_KO_DICTIONARY_URL`: URL for the English-to-Korean full dictionary JSON file, plain `.json`, gzipped `.json.gz`/`.gz`, or zipped `.json.zip`/`.zip`.
- `EN_KO_DICTIONARY_PATH`: custom local path for the downloaded or pre-mounted English-to-Korean full dictionary file.

Kaikki/Wiktionary data can require CC BY-SA/GFDL-style attribution and share-alike handling. If `en_ko_full.json` is published as a public release asset, keep the source and license notice alongside it (see the Source Notice section below and the Info tab in the app).

## krdict Reverse Index (Boost-Only Auxiliary Data)

`backend/app/krdict_reverse_service.py` loads an optional 국립국어원 한국어기초사전/우리말샘-style
reverse index: a flat `{"english gloss": ["korean word", ...]}` JSON mapping.

This is **not** a main translation engine. It is a small, boost-only auxiliary
data source used to correct and rank the Kaikki/Wiktionary-based `en_ko`
fallback candidates that `en_ko_dictionary_service.translate_glosses_to_korean`
already produces:

- Kaikki candidates that also appear in the krdict reverse index are ranked
  first (treated as verified/higher confidence).
- krdict candidates that Kaikki does not already have can be added as a
  supplementary candidate, still subject to the same 1-3 candidate cap and
  the same garbage/archaic-character filter as every other candidate
  (`meaning_ranker.is_valid_korean_candidate`).
- The priority order is unchanged: user-defined term meaning, user-saved
  `meaning_ko`, and the built-in Japanese-to-Korean dictionary are still
  checked first and always win. krdict only influences the JMdict-gloss →
  Kaikki/en_ko fallback tier below those.

### Local file precedence

- Default sample: `backend/data/dictionary/krdict_reverse_sample.json` (small,
  committed for local development and tests).
- Optional full index: `backend/data/dictionary/krdict_reverse_full.json`. If
  present and valid, it is used instead of the sample. It is intentionally
  ignored by Git because 국립국어원 data has its own usage terms and the file
  can be large.

### No runtime API calls

Build the reverse index file in a local/offline preprocessing step, not at
request time:

```bash
cd backend
python scripts/build_krdict_reverse_index.py --input krdict_raw.json --output data/dictionary/krdict_reverse_full.json
```

`scripts/build_krdict_reverse_index.py` only reshapes an already-exported
JSON/JSONL input file into the reverse-index shape; it does not call the
국립국어원 API itself. Exporting/fetching source data from
한국어기초사전(https://krdict.korean.go.kr) or 우리말샘 is a separate manual
step, and any bulk export or API usage must follow their published API/data
usage terms.

Check the active reverse index without printing full contents:

```bash
cd backend
python scripts/check_krdict_reverse.py
```

### Licensing and attribution

한국어기초사전/우리말샘 data is provided by 국립국어원 under the Korean
government's 공공데이터 이용조건. Confirm the current usage terms and any
required attribution before bulk-exporting data or publishing a derived
`krdict_reverse_full.json` file anywhere. Keep source/attribution notices for
this data alongside the JMdict/EDICT and Kaikki/Wiktionary notices already
documented below and in the Info tab.

## Source Notice

The dictionary fallback can use JMdict/EDICT project data by EDRDG and Kaikki/Wiktionary data. JMdict/EDICT has its own license requirements, and Kaikki/Wiktionary data can require CC-BY-SA/GFDL attribution and share-alike handling. The optional krdict reverse index can use 국립국어원 한국어기초사전/우리말샘 data, subject to Korea's 공공데이터 이용조건 and any required attribution. Keep appropriate source and license notices in product and deployment documentation. User-defined terms and personal vocabulary data are stored separately from dictionary source data.
