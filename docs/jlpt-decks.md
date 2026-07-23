# JLPT Level-Based Recommended Vocabulary Decks

This documents the groundwork for building N5–N1 "recommended vocabulary"
shared decks. **These are not official JLPT word lists.**

## Why "recommended," not "official"

The new-format JLPT (since 2010) does not publish an official vocabulary,
kanji, or grammar list. Any word list claiming to be "the official JLPT N5
list" is a third party's reconstruction/estimate, not a document released by
the Japan Foundation or JEES. To avoid misrepresenting the app's data and to
reduce copyright/license risk from copying someone else's reconstructed
list, this app never labels a deck as "공식 JLPT" ("official JLPT") or
implies it is the complete, authoritative exam vocabulary.

Instead, decks built with this pipeline are labeled and described as:

- "JLPT N5 추천 어휘" (JLPT N5 recommended vocabulary)
- "JLPT 대비 추천 단어장" (JLPT-prep recommended deck)
- "레벨별 추천 어휘 덱" (level-based recommended vocabulary deck)

Avoid in any UI copy, deck name, or deck description:

- "공식 JLPT 단어장" (official JLPT wordlist)
- "JLPT 필수 공식 어휘" (official required JLPT vocabulary)
- "실제 시험 출제 단어 전체" (the complete set of words that appear on the
  real exam)

The generated deck description (see `build_jlpt_deck_package.py`) already
uses the approved wording:

> 공식 JLPT 어휘 목록이 아니라, 공개 학습 자료와 내부 사전 데이터를 바탕으로
> 구성한 레벨별 추천 어휘 덱입니다. 시험 대비와 원문 읽기 입문용으로
> 활용하세요.

## Source policy

- No automated crawling of any website. Word lists are hand-curated CSV seed
  files (`backend/data/jlpt/*.csv`), written or reviewed by a person, not
  scraped.
- No copying of textbook, web-novel, or commercial wordbook example
  sentences. Every `example_sentence` in a seed CSV must be short and
  self-written (or otherwise confirmed license-free) for this project --
  not lifted from a JLPT prep book, app, or copyrighted text.
- Only public/openly licensed source material may inform which words go into
  a seed CSV (e.g. widely available beginner vocabulary that appears
  identically across many independent free learning resources, not a
  specific book's curated list + commentary).
- Large, bulk JLPT word list files are **not** committed until their source
  and license are confirmed. MVP ships only a small, hand-written N5 sample
  (`backend/data/jlpt/n5_sample.csv`, ~30 words) to prove out the pipeline.
- Meaning enrichment (`meaning_ko`) falls back to this app's existing
  dictionary pipeline (JMdict + Kaikki/Wiktionary en_ko fallback + krdict
  reverse index boosting), which already has its own sourcing/licensing
  documented in [dictionary-data.md](dictionary-data.md). JMdict/EDRDG data
  is licensed CC BY-SA 4.0 by the Electronic Dictionary Research and
  Development Group (EDRDG); keep that attribution wherever dictionary-gloss
  data is surfaced or redistributed, same as the rest of the app already
  does (see the Info tab and the Source Notice in dictionary-data.md).
- English gloss (`dictionary_gloss`) is populated on generated vocab items
  for parity with normal `/analyze`-created items, but the frontend never
  renders it by default -- same policy as everywhere else in the app.

## Pipeline (MVP: N5 sample only)

1. **Seed CSV** -- `backend/data/jlpt/n5_sample.csv`. Columns:

   ```
   level,surface,reading,meaning_hint_ko,example_sentence,example_translation_ko,note_ko
   ```

   `reading` and `meaning_hint_ko` are optional per row; if blank, the build
   script fills them in from the existing dictionary/analyze pipeline.
   `example_translation_ko` and `note_ko` are folded into
   `context_explanation_ko` on the generated vocab item (e.g. `해석: ... /
   참고: ...`) since deck packages have no dedicated translation/note field.

2. **Build the deck package JSON** (no database access, no network):

   ```bash
   cd backend
   .\.venv\Scripts\Activate.ps1
   python .\scripts\build_jlpt_deck_package.py --level N5 --input .\data\jlpt\n5_sample.csv --output .\data\jlpt\jlpt_n5_recommended_deck.json
   ```

   This produces a `jp_vocab_reader_deck` package JSON in the exact shape
   `POST /decks/import-package` already accepts (same `DeckPackage` schema
   used by the existing deck-sharing feature) -- no new API, no new package
   format.

3. **(Optional) Register it as a shared deck.** As of the
   shared-lexeme/progress storage change (see
   [../architecture/shared-lexeme-progress-storage.md](../architecture/shared-lexeme-progress-storage.md)),
   this **defaults to the new lexeme-mode registration path**: each word is
   upserted once into the shared `lexemes` table and linked to the shared
   deck via `shared_deck_words` -- no personal deck is created, and no
   user's `vocab_items` are touched. Pass `--legacy` to fall back to the old
   behavior (create a personal deck for the dev/admin user, copying every
   word into `vocab_items`, then publish that deck the old
   `shared_deck_items`-based way) if you specifically need it.

   ```bash
   cd backend
   .\.venv\Scripts\Activate.ps1
   python .\scripts\seed_jlpt_shared_decks.py --input .\data\jlpt\jlpt_n5_recommended_deck.json
   ```

   This defaults to a **read-only dry run** that only prints what it would
   do. Pass `--apply` to actually write. Because this script connects to
   whatever `DATABASE_URL` is configured -- which may be a real deployed
   database, not a local throwaway one -- always review the dry-run output
   first, and never run `--apply` against a database you don't intend to
   change. `--skip-publish` only applies together with `--legacy` (create
   the personal deck without publishing it).

## Pipeline for externally-sourced word lists (quality review)

The MVP pipeline above works for a small, hand-written sample where you
already trust every field. For a word list obtained from an external source
(e.g. a downloaded JLPT study CSV), don't feed it straight into a shared
deck -- run it through this quality-review pipeline first so a human (or an
LLM given the CSV) can catch mistakes before anything is published:

```
1. Confirm the source/license of the external CSV -- see "Source policy" above.
   Save it to backend/data/jlpt/raw/<level>.csv (not committed).

2. Normalize whatever column names it uses into the standard shape:
   cd backend
   .\.venv\Scripts\Activate.ps1
   python .\scripts\normalize_jlpt_word_list.py --input .\data\jlpt\raw\n5.csv --output .\data\jlpt\work\n5_normalized.csv --level N5

3. Generate a first-pass Korean meaning + audit warnings using this app's
   own dictionary/analyze pipeline (no runtime API calls, no trusting the
   external English/Korean gloss blindly):
   python .\scripts\build_jlpt_quality_draft.py --input .\data\jlpt\work\n5_normalized.csv --output .\data\jlpt\work\n5_quality_draft.csv

4. A human reviews data\jlpt\work\n5_quality_draft.csv (open it in a
   spreadsheet, or upload it to an LLM for a first-pass review). For each
   row: check the `warnings` column first, confirm/correct
   `generated_meaning_ko`, fill in `note_ko` if useful, and only keep short
   self-written example sentences (or leave `example_sentence` blank).
   Save the approved result as backend/data/jlpt/reviewed/n5_reviewed.csv
   with `generated_meaning_ko` renamed/promoted to `meaning_ko` (the
   required column for the next step).

5. Validate the reviewed CSV and split it into a clean CSV and a
   needs_review CSV. **Required for N3 and up** (and any CSV a human hasn't
   line-by-line approved) -- a reviewed CSV can still carry leftover
   placeholder text (e.g. `확인 필요: ...`, `source English: ...`) or
   katakana entries whose "meaning" is just the reading transliterated into
   Hangul. Only the clean CSV is safe to turn into a shared deck:
   python .\scripts\validate_jlpt_reviewed_csv.py --input .\data\jlpt\reviewed\n5_reviewed.csv --clean-output .\data\jlpt\work\n5_clean.csv --needs-review-output .\data\jlpt\work\n5_needs_review.csv

   A human reviews `n5_needs_review.csv` (the `reason` column explains why
   each row was pulled out -- see the table below), fixes what can be fixed,
   and either moves corrected rows back into the reviewed CSV for
   re-validation or leaves them out of this deck entirely. Rows still
   showing "확인 필요" must never be added to a shared deck.

6. Build the deck package from the **clean** CSV:
   python .\scripts\build_jlpt_deck_from_reviewed_csv.py --level N5 --input .\data\jlpt\work\n5_clean.csv --output .\data\jlpt\packages\jlpt_n5_recommended_deck.json

   This script also refuses to build (exit code 1, one line per offending
   row) if the input still contains `확인 필요`, `TODO`,
   `MEANING_NEEDS_REVIEW`, or `source English` in `meaning_ko`/`note_ko` --
   even if you skip step 5 and point `--input` at the raw reviewed CSV
   directly. This is a last-line-of-defense guard, not a substitute for
   running the validator; only pass `--allow-unreviewed` if you have a
   specific, deliberate reason to publish an unreviewed row (this should be
   rare enough to need a second person's sign-off).

7. Import it (POST /decks/import-package, or the existing deck-package
   import UI) or register it as a shared deck with
   scripts/seed_jlpt_shared_decks.py (dry-run by default; --apply to write).
```

### validate_jlpt_reviewed_csv.py: reason codes

Every row that fails at least one check goes to the needs_review CSV with a
`reason` column (semicolon-separated if more than one applies) instead of
the clean CSV:

| Code | Meaning |
| --- | --- |
| `EMPTY_MEANING` | `meaning_ko` is blank. |
| `HAS_CONFIRM_NEEDED` | `meaning_ko` or `note_ko` contains `확인 필요`. |
| `HAS_TODO` | `meaning_ko` or `note_ko` contains `TODO` or `MEANING_NEEDS_REVIEW`. |
| `HAS_SOURCE_ENGLISH` | `meaning_ko` or `note_ko` contains `source English`. |
| `ENGLISH_REMAINS` | `meaning_ko` has as many or more ASCII letters than Hangul characters -- an English gloss leaked into a user-facing field. |
| `TOO_MANY_MEANINGS` | More than `--max-candidates` (default 4) comma-separated candidates in `meaning_ko`. |
| `TOO_LONG_MEANING` | `meaning_ko` is longer than `--max-meaning-length` (default 40 characters). |
| `TOO_GENERIC_MEANING` | `meaning_ko` is exactly one of a short list of near-meaningless words (기타/것/수/때/점/부분/경우). |
| `KATAKANA_TRANSLITERATION_ONLY` | `surface` is a katakana word and `meaning_ko` is a single bare candidate -- see below. |

Every rule runs independently and all matching reasons are recorded, so a
row like `확인 필요: to avoid (physical contact)` typically shows
`HAS_CONFIRM_NEEDED;ENGLISH_REMAINS`.

**Katakana policy**: a katakana loanword whose `meaning_ko` is a single,
comma-free candidate (e.g. テーマ → "테마", タイプ → "타입", スピーチ →
"스피치") is *always* routed to needs_review, even though some of these are
in fact correct -- Korean borrows plenty of the same loanwords, so "발음
그대로"can legitimately be the right answer (e.g. 엔진 → "엔진",
스위치 → "스위치"). The validator has no reliable way to tell a correct
loanword apart from a garbled pipeline artifact (real examples found in
n3_reviewed.csv: アイスクリーム → "아이스쿠리무", バッグ → "바구", ゲーム →
"게무" -- all wrong), so per policy it never guesses; it always defers to a
human, who can move the good ones back into the clean CSV. Prefer the
actual Korean meaning over the bare transliteration wherever one exists
(다리미, not "아이론", for アイロン).

Everything under `raw/`, `work/`, `reviewed/`, and `packages/` is git-ignored
-- see `backend/data/jlpt/README.md`. Nothing before step 6 touches the
database, and nothing is published as a shared deck until a human has
reviewed the quality draft.

### build_jlpt_quality_draft.py: how generated_meaning_ko is decided

For each row, `surface` is run through the exact same tokenize + dictionary
lookup pipeline `/analyze` uses (`app.analyzer`, single headword instead of
a sentence):

1. If the pipeline (JMdict full-text lookup → Kaikki/en_ko fallback → krdict
   boosting → `meaning_quality_filter`) produces a `meaning_ko`, that is used
   as `generated_meaning_ko`. Confidence is `high` if JMdict itself has a
   matching entry (`dictionary_found=True`), `medium` if the meaning came
   from elsewhere (e.g. the small built-in exception dictionary) without a
   JMdict match.
2. Only if the pipeline produces nothing does the external CSV's
   `source_meaning_ko` get considered, and only after passing the same
   Korean-candidate validator (`is_valid_korean_candidate`) and risky-word
   filter (`is_risky_korean`) used everywhere else in the app. This is the
   "참고하되 그대로 맹신하지 않음" (reference it, don't blindly trust it)
   policy from the product requirements. Confidence is `low` in this case.
3. If nothing survives either step, `generated_meaning_ko` is left empty
   (confidence `none`) -- an empty meaning is preferred over a wrong one,
   matching the existing meaning-quality-filter policy documented in
   [dictionary-data.md](dictionary-data.md).

`source_meaning_en` (the external CSV's English gloss, if any) is carried
through the draft CSV for reference only; it is never shown in the app UI
and never used as the Korean meaning.

### Audit warning columns

`build_jlpt_quality_draft.py` fills a `warnings` column (semicolon-separated
codes) so a reviewer can triage rows by risk instead of reading every row
equally:

| Code | Meaning |
| --- | --- |
| `NO_DICTIONARY_MATCH` | JMdict has no entry for this surface/base form -- the word may be a name, slang, or outside the current dictionary data. |
| `EMPTY_MEANING` | No usable Korean meaning was produced at all. |
| `READING_MISMATCH` | The external CSV's reading and the analyzer-derived reading disagree after hiragana normalization -- check for a wrong kanji/homograph. |
| `LOW_CONFIDENCE_MEANING` | `meaning_confidence` is `medium` or `low` -- worth a second look. |
| `RISKY_KOREAN_CANDIDATE` | One of the final candidates is flagged by `meaning_quality_filter.is_risky_korean` (generic/ambiguous word) even after the pipeline's own filtering -- a belt-and-suspenders check. |
| `TOO_MANY_MEANINGS` | More Korean candidates than the configured max (should be rare; the pipeline caps this already). |
| `MULTIPLE_SENSES` | Best-effort heuristic: the dictionary entry has many plain-ASCII-looking gloss segments, suggesting a versatile/polysemous word worth confirming the chosen sense fits this level. Not precise -- the underlying JMdict data interleaves multiple languages under one headword, so this is noisy by nature. |
| `SOURCE_EN_MISMATCH` | The external CSV's English gloss shares no words with our dictionary's English gloss for this surface -- possible wrong-word mapping in the source file. |
| `DUPLICATE_SURFACE` | The same surface appears more than once in the input. |
| `DUPLICATE_SURFACE_READING` | The same (surface, reading) pair appears more than once -- likely a true duplicate row to remove. |

### Example sentences and notes at the draft stage

`build_jlpt_quality_draft.py` never invents example sentences. It only
fills `example_sentence`/`example_translation_ko` when the surface matches
an already-committed, self-written sample (currently `n5_sample.csv`);
otherwise both stay blank for the reviewer to fill in (short, self-written
sentences only -- never copied from a textbook, app, or web novel).
`note_ko` is always left blank at this stage; the column exists so a
reviewer has somewhere to add a short usage note.

## Scaling to N4–N1

This step is intentionally deferred, not built yet:

- For a small, fully hand-written level sample, follow the same pattern as
  `n5_sample.csv` and run `build_jlpt_deck_package.py --level N4 ...`
  directly -- both scripts are already level-generic.
- For a level built from an externally-sourced word list, use the quality
  review pipeline above (`normalize_jlpt_word_list.py` →
  `build_jlpt_quality_draft.py` → human review →
  `build_jlpt_deck_from_reviewed_csv.py`) instead of skipping straight to a
  deck package.
- Only commit a level's CSV once its word source and example sentences are
  confirmed license-clean. A large, unreviewed bulk list should stay outside
  Git (or in a local-only/private location) until reviewed, the same way
  `krdict_raw_real.jsonl` and similar bulk fetcher output are excluded from
  Git today (see [dictionary-data.md](dictionary-data.md)).
- **N3 and up must always go through `validate_jlpt_reviewed_csv.py`
  (pipeline step 5) before building a deck package.** These levels are
  large enough that a "reviewed" CSV realistically still has leftover
  placeholder markers and bad katakana transliterations a first pass
  missed -- only the resulting clean CSV should be turned into a shared
  deck; the needs_review CSV stays a human task, not something the pipeline
  guesses its way through.

## What is intentionally out of scope for this step

- No automatic write to the production database. `seed_jlpt_shared_decks.py`
  only writes when `--apply` is explicitly passed.
- Deck *package* building (steps 1-2 above) has no DB schema changes -- it
  reuses the existing `DeckPackage` JSON shape. Registration (step 3) now
  adds to the shared `lexemes` / `shared_deck_words` tables by default (an
  additive, non-destructive schema addition) -- see
  [../architecture/shared-lexeme-progress-storage.md](../architecture/shared-lexeme-progress-storage.md)
  for the full design and migration policy. `--legacy` registration still
  reuses the older `decks` / `vocab_items` / `shared_decks` tables exactly
  as before.
- No full source-text storage. A deck package only ever contains short
  per-word `example_sentence` fields (and now, optionally, a short
  `context_explanation_ko` translation/note) -- never a book/web-novel's
  full text, matching the app's existing copyright-risk policy for shared
  decks.
