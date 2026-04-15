# Conscious_Consumer Study Notes

Crafted with <3 by abhirsc :)

## Learning Style First

Use this project in this order:

1. Start from the user flow.
2. Read the data file shape.
3. Read the sync script.
4. Read the page that renders the table.
5. Run the offline test before touching live data.

This project is easiest to understand if you think in layers:

- Input layer: Tally collects form responses.
- Sync layer: Python maps responses into CSV rows.
- Content layer: `reviews.csv` becomes the source of truth for reviews.
- Presentation layer: Quarto reads the CSV and renders the table on the website.

## Core Theory

### Why use a CSV

The site is static. A static site cannot directly write to a server-side database during page rendering, so the project stores reviews in `reviews.csv`. That file acts like a lightweight table.

### Why use a sync script

Tally stores submissions in its own system. The Python sync script translates Tally response fields into the exact column names the site expects.

### Why use persisted state

The file `.github/tally_state.json` remembers the last processed submission. This prevents duplicated rows when the scheduled workflow runs again.

### Why the website only shows approved rows

The Quarto page reads `reviews.csv` and filters rows where `Status == "Approved"`. This gives a simple moderation gate before public display.

## Important Files

- `index.qmd`: renders the public review table.
- `reviews.csv`: the table data source.
- `scripts/sync_tally_reviews.py`: fetches and maps Tally responses.
- `.github/workflows/sync-tally.yml`: runs the sync on a schedule.
- `.github/tally_state.json`: stores deduplication state.

## How To Use

### Offline learning/test path

Run the script with the sample payload first:

```bash
cd /Users/abhirsc/Documents/Conscious_Consumer
python3 scripts/sync_tally_reviews.py \
  --responses-file tests/data/sample_tally_responses.json \
  --dry-run
```

### Live path

Set these first:

- `TALLY_API_KEY`
- `TALLY_FORM_ID`

Then run:

```bash
cd /Users/abhirsc/Documents/Conscious_Consumer
python3 scripts/sync_tally_reviews.py \
  --csv-path reviews.csv \
  --state-file .github/tally_state.json
```

## Practical Mental Model

Think of the project as:

`form submission -> normalized record -> CSV row -> rendered website table`

If something breaks, check it in that same order.
