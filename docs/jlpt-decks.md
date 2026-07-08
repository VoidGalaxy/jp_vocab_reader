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

3. **(Optional) Register it as a shared deck**, using the existing
   `import_deck_package` + `publish_deck` repository functions (no new DB
   writes logic, no schema change):

   ```bash
   cd backend
   .\.venv\Scripts\Activate.ps1
   python .\scripts\seed_jlpt_shared_decks.py --input .\data\jlpt\jlpt_n5_recommended_deck.json
   ```

   This defaults to a **read-only dry run** that only prints what it would
   do. Pass `--apply` to actually create the personal deck (owned by the
   dev/admin user) and publish it as a public shared deck. Because this
   script connects to whatever `DATABASE_URL` is configured -- which may be
   a real deployed database, not a local throwaway one -- always review the
   dry-run output first, and never run `--apply` against a database you
   don't intend to change. Pass `--skip-publish` to only create the
   personal deck without publishing it.

## Scaling to N4–N1

This step is intentionally deferred, not built yet:

- Add `backend/data/jlpt/n4_sample.csv`, `n3_sample.csv`, etc., using the
  same column format and the same sourcing rules above.
- Re-run `build_jlpt_deck_package.py --level N4 ...` per level -- the script
  is already level-generic.
- Only commit a level's CSV once its word source and example sentences are
  confirmed license-clean. A large, unreviewed bulk list should stay outside
  Git (or in a local-only/private location) until reviewed, the same way
  `krdict_raw_real.jsonl` and similar bulk fetcher output are excluded from
  Git today (see [dictionary-data.md](dictionary-data.md)).

## What is intentionally out of scope for this step

- No automatic write to the production database. `seed_jlpt_shared_decks.py`
  only writes when `--apply` is explicitly passed.
- No DB schema changes -- deck packages and shared decks reuse the existing
  `decks` / `vocab_items` / `shared_decks` tables and repository functions.
- No full source-text storage. A deck package only ever contains short
  per-word `example_sentence` fields (and now, optionally, a short
  `context_explanation_ko` translation/note) -- never a book/web-novel's
  full text, matching the app's existing copyright-risk policy for shared
  decks.
