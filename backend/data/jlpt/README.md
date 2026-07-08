# backend/data/jlpt/

Working area for building JLPT level-based **recommended vocabulary** decks.
These are not official JLPT word lists -- see
[docs/jlpt-decks.md](../../../docs/jlpt-decks.md) for the full pipeline,
sourcing rules, and licensing notes.

## Folder layout

| Path | Committed? | Contents |
| --- | --- | --- |
| `n5_sample.csv` | Yes | Small, hand-written N5 sample seed (source for `build_jlpt_deck_package.py`). |
| `samples/` | Yes | Reserved for future small, hand-written, license-clean samples. |
| `raw/` | No | Externally-sourced word list exports, as downloaded. Source/license must be confirmed before this data goes any further. |
| `work/` | No | `normalize_jlpt_word_list.py` and `build_jlpt_quality_draft.py` output (`*_normalized.csv`, `*_quality_draft.csv`). Generated; regenerate instead of committing. |
| `reviewed/` | No | Human-reviewed copies of the quality draft (`*_reviewed.csv`) with `generated_meaning_ko` promoted to a trusted `meaning_ko` column. |
| `packages/` | No | `build_jlpt_deck_from_reviewed_csv.py` / `build_jlpt_deck_package.py` output (`*_recommended_deck.json`), ready for `POST /decks/import-package` or `seed_jlpt_shared_decks.py`. |

Nothing under `raw/`, `work/`, `reviewed/`, or `packages/` is committed --
see the repo root `.gitignore`. Only hand-written, already-reviewed samples
belong in Git.

## Pipeline

```
raw external CSV
  -> normalize_jlpt_word_list.py   -> work/<level>_normalized.csv
  -> build_jlpt_quality_draft.py   -> work/<level>_quality_draft.csv
  -> (human review)                -> reviewed/<level>_reviewed.csv
  -> build_jlpt_deck_from_reviewed_csv.py -> packages/jlpt_<level>_recommended_deck.json
  -> POST /decks/import-package or scripts/seed_jlpt_shared_decks.py
```

See [docs/jlpt-decks.md](../../../docs/jlpt-decks.md) for command examples
and what each script does.
