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

This is **not** a main translation engine, and it is **not a candidate
generator either** -- it is a validator/ranking booster for the
Kaikki/Wiktionary-based `en_ko` fallback candidates that
`en_ko_dictionary_service.translate_glosses_to_korean` already produces:

- A Kaikki candidate that also appears in the krdict reverse index for the
  same gloss is scored higher (treated as verified/higher confidence).
- A candidate that krdict has but Kaikki does not is only added at a low
  score, and never for a gloss judged "risky" (see below) -- krdict cannot
  introduce a brand-new candidate on the strength of a generic/ambiguous
  gloss alone.
- A candidate flagged as a generically risky Korean word (see below) is
  never boosted by a krdict match, even if krdict confirms it.
- The priority order is unchanged: user-defined term meaning, user-saved
  `meaning_ko`, and the built-in Japanese-to-Korean dictionary are still
  checked first and always win. krdict only influences the JMdict-gloss →
  Kaikki/en_ko fallback tier below those.

### Automatic meaning quality filter (`app/meaning_quality_filter.py`)

Rather than hand-fixing individual Japanese lemmas one at a time (not
practical at the scale of a full novel's vocabulary), `meaning_ko` candidates
from the Kaikki/krdict tier go through a general scoring filter:

- **Risky English glosses** -- very broad glosses like `point`, `tip`,
  `thing`, `one`, `part`, `place`, `way`, `matter`, `case`, `time`, `end`,
  `side`, `line`, `form`, `mark`, `sign`, `piece`, `object` match almost any
  noun in a bilingual dictionary, so a Korean candidate sourced only from one
  of these is weak evidence and is scored down.
- **Risky Korean candidates** -- generic/ambiguous words like `포인트`, `팁`,
  `점`, `것`, `수`, `때`, `곳`, `부분`, `경우`, `문제`, `정`, `문신`, `끌`,
  `형태`, `라인`, `사이드`, `오브젝트` are demoted (not hard-removed -- a few
  are occasionally the genuinely correct meaning, so they can still surface
  if nothing better scores higher).
- **Confidence threshold** -- a candidate scoring below the threshold is
  dropped entirely. If every candidate for a token ends up below threshold,
  `meaning_ko` is left as an empty string. **An empty meaning is preferred
  over showing a wrong one.**
- **Single hiragana token guardrail** -- a one-character hiragana token
  tagged as an interjection/conjunction/adnominal/affix (or with no reliable
  part-of-speech at all) -- e.g. `え` as a filler/interjection -- skips
  gloss-based translation entirely rather than guessing from whatever
  JMdict/Kaikki sense happens to exist for that character.
- Genuinely broken/archaic/invalid text is still hard-removed as before via
  `meaning_ranker.is_valid_korean_candidate` -- the filter above is about
  demoting *plausible-looking but low-confidence* candidates, not replacing
  that existing garbage filter.

Manual per-lemma overrides (`app/gloss_ko_mapper.py`'s small exception table)
remain a last-resort hotfix mechanism only, not the primary fix path -- the
quality filter is meant to generalize across the full vocabulary of a book
without hand-curating each word.

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

### krdict API fetcher (development/preprocessing only)

`backend/scripts/fetch_krdict_api.py` can call the real 국립국어원
한국어기초사전/우리말샘 Open API to build the raw JSONL input for
`build_krdict_reverse_index.py`. This is a manual developer tool, never a
runtime code path -- the deployed app never calls the krdict API.

- The API key is read from the `KRDIC_API_KEY` or `KRDICT_API_KEY`
  environment variable (either name works). Resolution order: the current
  process environment is checked first; only if neither variable is set
  there does the script fall back to loading `backend/.env` (via
  `python-dotenv` if installed, otherwise a small built-in `KEY=VALUE`
  parser so a missing optional dependency never crashes the script) and
  check both names again.
  - Local development: put `KRDIC_API_KEY=...` in `backend/.env`. `.env` is
    never committed (see `.gitignore`); `.env.example` only documents the
    variable name (`KRDIC_API_KEY=`), never a real key.
  - CI/Render/other platforms: inject `KRDIC_API_KEY` as a platform
    environment variable (Render's dashboard, GitHub Actions secrets,
    etc.). No `.env` file is needed there since process-level environment
    variables are checked first.
  - Setting `$env:KRDIC_API_KEY` directly in a PowerShell session is fine
    for a one-off manual test, but is not the supported way to run this
    regularly -- it does not persist across sessions/processes and can
    also silently shadow a correct `backend/.env` value if it lingers in a
    long-lived shell. Use `backend/.env` (local) or a platform environment
    variable (CI/Render) instead.
  - The API key itself is never logged or included in error messages; the
    script only reports whether a key was found, its source (process
    environment vs. the `.env` path), and its length.
- Default collection is small and safe: `--limit 100` and a `--sleep 0.5`
  delay between requests. Larger runs require explicitly passing a bigger
  `--limit`.
- The fetcher reads Korean words from a seed word list
  (`--seed-file`, default `data/dictionary/krdict_seed_sample.txt`) and
  writes one JSON object per line to `--output` (default
  `data/dictionary/krdict_raw_real.jsonl`).
- Re-running with the same `--output` resumes by default (`--resume`,
  skips words already present) so a large seed list can be collected across
  multiple runs; pass `--overwrite` to start clean instead.
- No API key or network access is needed to try the script: `--input-sample
  data/dictionary/krdict_api_response_sample.xml` (or `.json`) replays a
  committed sample API response through the same parsing/output code path.
  `python scripts/check_krdict_fetcher.py` runs this offline check plus a
  compatibility check against `build_krdict_reverse_index.py` and always
  passes without a key.
- Before running a large collection, confirm the 국립국어원 Open API terms
  of use, call-rate limits, and any required source attribution.
- Fetcher output (`krdict_raw_real.jsonl` and similar `krdict_raw_*` files)
  is raw collected data and is not committed to Git.
- Convert fetcher output into the reverse index with the same command used
  for any other raw input:

  ```bash
  cd backend
  python scripts/fetch_krdict_api.py --seed-file data/dictionary/krdict_seed_sample.txt --output data/dictionary/krdict_raw_real.jsonl --limit 100
  python scripts/build_krdict_reverse_index.py --input data/dictionary/krdict_raw_real.jsonl --output data/dictionary/krdict_reverse_full.json
  ```

  `krdict_reverse_full.json` is not committed either (see above).
- This stage only produces a local, reviewable `krdict_reverse_full.json`
  for development. See "Production delivery" below for getting it onto
  Render.

### Generating a real-world-sized krdict_reverse_full.json

To go beyond the small built-in seed list, `backend/scripts/build_krdict_seed_from_en_ko.py`
extracts Korean candidate words from the Kaikki/Wiktionary-derived
`en_ko_full.json` (falling back to the committed `en_ko_sample.json` if the
full file is not present) and writes them as a plain-text seed list, one
word per line, cleaned of Hanja/romanization annotations, combined
candidates, and broken/overlong entries. It only reads `en_ko_full.json`;
it never writes to it, and `en_ko_full.json` itself stays out of Git as
already documented above.

Full pipeline, from Kaikki data to a real-scale local reverse index:

```bash
cd backend
.\.venv\Scripts\Activate.ps1

# 1. Extract a large Korean seed list from en_ko_full.json, plus a small
#    curated core-vocabulary seed list that is always kept (never truncated
#    away by --limit).
python scripts/build_krdict_seed_from_en_ko.py --limit 3000 --extra-seed-file data/dictionary/krdict_seed_core_sample.txt --output data/dictionary/krdict_seed_generated.txt

# 2. Call the real krdict API for each seed word (small, resumable batches;
#    re-running with the same --output skips words already collected).
python scripts/fetch_krdict_api.py --seed-file data/dictionary/krdict_seed_generated.txt --limit 3000 --sleep 0.5 --output data/dictionary/krdict_raw_real.jsonl

# 3. Build the local reverse index and check it.
python scripts/build_krdict_reverse_index.py --input data/dictionary/krdict_raw_real.jsonl --output data/dictionary/krdict_reverse_full.json
python scripts/check_krdict_reverse.py
```

Notes:

- `krdict_seed_generated.txt`, `krdict_raw_real.jsonl`, and
  `krdict_reverse_full.json` are all generated files and are **not**
  committed to Git (see `.gitignore`). Only the small
  `krdict_seed_sample.txt` and `krdict_seed_core_sample.txt` seed lists are
  committed.
- The API key is managed only through `backend/.env` (local) or a platform
  environment variable (CI/Render) -- see the fetcher section above. It is
  never placed in code, docs, or committed files.
- Before running a large `--limit`, confirm the 국립국어원 Open API terms
  of use, call-rate limits, and any required source attribution.
- This whole pipeline is a preprocessing step run manually by a developer,
  not something the running app calls at request time. In production,
  Render instead downloads an already-built `krdict_reverse_full.json.gz`
  via `KRDIC_REVERSE_URL` at startup -- see "Production delivery" below.
- If a fetch run is interrupted, seed words that failed every retry are
  logged to `<output>.failed.txt` (e.g.
  `krdict_raw_real.jsonl.failed.txt`) for visibility. They are not written
  to the main JSONL output, so a later run with `--resume` (the default)
  retries them automatically without needing that log as input.

### Production delivery (Render)

`krdict_reverse_full.json` is built offline (as above) and shipped to
Render the same way `jmdict_full.json` and `en_ko_full.json` already are --
`app/dictionary_file_manager.py` provides `ensure_krdict_reverse_file()`,
which mirrors `ensure_full_dictionary_file()`/`ensure_en_ko_dictionary_file()`
exactly (same download/gzip/zip/atomic-replace/fallback-on-failure
machinery), plus a krdict-specific structural JSON check.

Steps to publish an update:

1. Build `krdict_reverse_full.json` locally (see above), then gzip it:
   `python -c "import gzip,shutil; shutil.copyfileobj(open('data/dictionary/krdict_reverse_full.json','rb'), gzip.open('data/dictionary/krdict_reverse_full.json.gz','wb'))"`
   (or any gzip tool).
2. Upload `krdict_reverse_full.json.gz` (plain `.json` and `.zip` also work)
   to a GitHub Release asset, Cloudflare R2, S3, or similar file storage.
3. On Render, set the `KRDIC_REVERSE_URL` environment variable to that
   file's URL. Optionally set `KRDIC_REVERSE_PATH` to store it somewhere
   other than the default `backend/data/dictionary/krdict_reverse_full.json`.
4. On the next backend restart, `startup()` calls
   `ensure_krdict_reverse_file()` (alongside the existing JMdict/en_ko
   calls), which downloads, decompresses if needed, validates the JSON
   structure, and atomically replaces the local file only after validation
   passes. `krdict_reverse_service` then loads it and reports
   `source: "full"`.

Failure handling, matching the existing JMdict/en_ko behavior exactly:

- No `KRDIC_REVERSE_URL` set: no download is attempted; the app uses
  whatever local file is already there, or the committed
  `krdict_reverse_sample.json` if there is none.
- Download/decompress/validation fails: the temporary/partial file is
  discarded, any existing local full file is left untouched, and the app
  falls back to the sample -- it never crashes on a bad or unreachable URL.
- `/health` and `/dictionary-status` expose `krdict_reverse.source`
  (`full`/`sample`/`none`/`fallback`), `entries`, `download_enabled`
  (whether `KRDIC_REVERSE_URL` is set -- not the URL value itself), and
  `path_exists`, so a bad production config is visible without exposing
  the URL.
- Runtime API calls are never made for this: the 국립국어원 API key is only
  used by the offline `scripts/fetch_krdict_api.py` preprocessing step and
  is not needed (or read) for normal analyze requests in production.

Check the delivery setup locally without hitting the network:

```bash
cd backend
python scripts/check_krdict_delivery.py
```

Pass `--url <file-url>` to that script to test an actual download (to a
throwaway temp path, never the real configured path).

## Source Notice

The dictionary fallback can use JMdict/EDICT project data by EDRDG and Kaikki/Wiktionary data. JMdict/EDICT has its own license requirements, and Kaikki/Wiktionary data can require CC-BY-SA/GFDL attribution and share-alike handling. The optional krdict reverse index can use 국립국어원 한국어기초사전/우리말샘 data, subject to Korea's 공공데이터 이용조건 and any required attribution. Keep appropriate source and license notices in product and deployment documentation. User-defined terms and personal vocabulary data are stored separately from dictionary source data.
