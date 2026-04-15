#!/usr/bin/env python3
"""Sync reviews from Tally into the local CSV file.

This script fetches all form responses from the configured Tally form, maps
answers onto the `reviews.csv` schema, deduplicates already-processed
responses, and appends any new reviews. State is persisted between runs so
that duplicate rows are not added even if the workflow is executed multiple
 times per day.

It can be executed directly (for local development) or from the GitHub Action
workflow defined in `.github/workflows/sync-tally.yml`.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

TALLY_API_BASE = "https://api.tally.so"
CSV_HEADERS = [
    "Timestamp",
    "Category",
    "Brand",
    "Product",
    "Rating",
    "Recommended",
    "Comment",
    "Status",
]

# Question label aliases allow the script to gracefully handle minor wording
# changes in the Tally form without requiring code updates.
LABEL_ALIASES = {
    "Category": "Category",
    "Product category": "Category",
    "What product category are you reviewing?": "Category",
    "2. What product category are you reviewing?": "Category",
    "Brand": "Brand",
    "Brand name": "Brand",
    "Brand Name": "Brand",
    "Brand of this product?": "Brand",
    "3. Brand of this product?": "Brand",
    "Product": "Product",
    "Product name": "Product",
    "Product Name": "Product",
    "Name": "Product",
    "What product are you reviewing?": "Product",
    "Name of this product?": "Product",
    "4. Name of this product?": "Product",
    "Rating": "Rating",
    "Total Rating": "Rating",
    "Rate it out of 5": "Rating",
    "How would you rate it out of 5?": "Rating",
    "Would you recommend it?": "Recommended",
    "Recommend": "Recommended",
    "Reccommend": "Recommended",
    "Recommendation": "Recommended",
    "Do you recommend this product?": "Recommended",
    "Would you recommend this in Sydney?": "Recommended",
    "6. Would you recommend this in Sydney?": "Recommended",
    "Comment": "Comment",
    "Quick comment": "Comment",
    "Tell us why": "Comment",
    "How companies can make this product better for you?": "Comment",
    "Anything else you'd like to share with our team?": "Comment",
    "7. How companies can make this product better for you?": "Comment",
    "8. Anything else you'd like to share with our team?": "Comment",
}

RATING_SIGNAL_LABELS = {
    "🌱 Eco-friendly",
    "💰 Affordable",
    "🌍 Local / Ethical",
    "💪 Durable / Quality",
    "😍 Aesthetic / Packaging",
}

SCORE_PATTERN = re.compile(r"\s*\[(\d+(?:\.\d+)?)\]\s*$")


def clean_text(value: str) -> str:
    cleaned = html.unescape(str(value))
    cleaned = cleaned.replace("\xa0", " ")
    return " ".join(cleaned.split()).strip()


def strip_score_suffix(value: str) -> str:
    return SCORE_PATTERN.sub("", clean_text(value)).strip()


def extract_score(value: str) -> Optional[float]:
    match = SCORE_PATTERN.search(clean_text(value))
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


@dataclass
class SyncState:
    """Represents the state persisted between runs."""

    last_response_id: Optional[str] = None
    last_submission: Optional[str] = None

    @classmethod
    def from_file(cls, path: Path) -> "SyncState":
        if not path.exists():
            return cls()
        with path.open("r", encoding="utf-8") as fh:
            try:
                payload = json.load(fh)
            except json.JSONDecodeError:
                return cls()
        return cls(
            last_response_id=payload.get("last_response_id"),
            last_submission=payload.get("last_submission"),
        )

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "last_response_id": self.last_response_id,
            "last_submission": self.last_submission,
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)
            fh.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync reviews from Tally")
    parser.add_argument(
        "--csv-path",
        default="reviews.csv",
        help="Path to the reviews CSV that should be updated.",
    )
    parser.add_argument(
        "--state-file",
        default=".github/tally_state.json",
        help="File used to store the last processed response metadata.",
    )
    parser.add_argument(
        "--form-id",
        default=os.environ.get("TALLY_FORM_ID"),
        help="The Tally form ID (overrides TALLY_FORM_ID env var).",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("TALLY_API_KEY"),
        help="The Tally API key (overrides TALLY_API_KEY env var).",
    )
    parser.add_argument(
        "--responses-file",
        help="Optional local JSON file containing pre-fetched Tally responses (for testing).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and map responses without writing to disk.",
    )
    return parser.parse_args()


def fetch_responses(api_key: str, form_id: str) -> Iterable[Dict[str, Any]]:
    import json as _json
    from urllib import parse, request
    from urllib.error import HTTPError, URLError

    page = 1
    while True:
        url = f"{TALLY_API_BASE}/forms/{form_id}/submissions"
        params = {"page": page, "limit": 100, "filter": "all"}
        req = request.Request(url + "?" + parse.urlencode(params))
        req.add_header("Authorization", f"Bearer {api_key}")
        try:
            with request.urlopen(req, timeout=30) as response:
                payload = _json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:  # pragma: no cover - network errors surface to user
            raise SystemExit(
                f"Failed to fetch Tally responses (HTTP {exc.code}): {exc.reason}"
            ) from exc
        except URLError as exc:  # pragma: no cover
            raise SystemExit(f"Failed to reach Tally: {exc.reason}") from exc
        data = normalise_submissions_payload(payload)
        if not data:
            break
        for item in data:
            yield item
        page += 1
        if page > payload.get("totalPages", page):
            break


def load_responses(args: argparse.Namespace) -> List[Dict[str, Any]]:
    if args.responses_file:
        with open(args.responses_file, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        if isinstance(payload, dict) and "submissions" in payload:
            return normalise_submissions_payload(payload)
        if isinstance(payload, list):
            return payload
        raise ValueError("Unsupported responses JSON structure")

    if not args.api_key or not args.form_id:
        raise SystemExit(
            "TALLY_API_KEY and TALLY_FORM_ID must be provided unless --responses-file is used."
        )

    return list(fetch_responses(args.api_key, args.form_id))


def normalise_label(label: str) -> Optional[str]:
    return LABEL_ALIASES.get(clean_text(label)) if label else None


def normalise_submissions_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    questions = {
        item.get("id"): clean_text(item.get("title") or "")
        for item in payload.get("questions", [])
        if item.get("id")
    }

    normalised: List[Dict[str, Any]] = []
    for submission in payload.get("submissions", []):
        answers = []
        for response in submission.get("responses", []):
            label = questions.get(response.get("questionId"), "")
            answers.append(
                {
                    "question": {"label": label},
                    "value": response.get("answer"),
                }
            )
        normalised.append(
            {
                "id": submission.get("id"),
                "submittedAt": submission.get("submittedAt") or submission.get("createdAt"),
                "createdAt": submission.get("createdAt"),
                "answers": answers,
            }
        )
    return normalised


def extract_value(answer: Dict[str, Any]) -> str:
    value = answer.get("value")
    if isinstance(value, list):
        return ", ".join(strip_score_suffix(str(v)) for v in value if v not in (None, ""))
    if isinstance(value, dict):
        # Tally selects use {"label": ""} or {"labels": []}
        if "label" in value:
            return strip_score_suffix(str(value["label"]))  # single select
        if "labels" in value:
            return ", ".join(strip_score_suffix(str(v)) for v in value["labels"] if v)
        if "text" in value:
            return clean_text(str(value["text"]))
    if value is None:
        return ""
    return clean_text(str(value))


def map_response_to_row(response: Dict[str, Any]) -> Dict[str, str]:
    row = {key: "" for key in CSV_HEADERS}
    submitted_at = response.get("submittedAt") or response.get("createdAt") or ""
    row["Timestamp"] = str(submitted_at)
    row["Status"] = "Pending"
    rating_scores: List[float] = []
    for answer in response.get("answers", []):
        question = answer.get("question", {})
        label = question.get("label")
        cleaned_label = clean_text(label) if label else ""
        if cleaned_label in RATING_SIGNAL_LABELS:
            raw_value = answer.get("value")
            values = raw_value if isinstance(raw_value, list) else [raw_value]
            for item in values:
                if item in (None, ""):
                    continue
                score = extract_score(str(item))
                if score is not None:
                    rating_scores.append(score)
        canonical = normalise_label(label)
        if not canonical:
            continue
        value = extract_value(answer)
        if canonical == "Comment" and row["Comment"] and value:
            row["Comment"] = f"{row['Comment']} | {value}"
        elif value:
            row[canonical] = value
    if not row["Rating"] and rating_scores:
        average_score = sum(rating_scores) / len(rating_scores)
        row["Rating"] = f"{round(average_score * 5, 1):g}"
    return row


def filter_new_responses(
    responses: Iterable[Dict[str, Any]], state: SyncState
) -> List[Dict[str, Any]]:
    baseline = parse_timestamp(state.last_submission)
    if not baseline:
        return list(responses)

    new_items: List[Dict[str, Any]] = []
    for response in responses:
        submitted_at = response.get("submittedAt") or response.get("createdAt")
        submitted = parse_timestamp(submitted_at)
        if not submitted:
            new_items.append(response)
            continue
        if submitted > baseline:
            new_items.append(response)
        elif submitted == baseline:
            if response.get("id") != state.last_response_id:
                new_items.append(response)
    return new_items


def append_rows_to_csv(csv_path: Path, rows: List[Dict[str, str]]) -> None:
    if not rows:
        return

    csv_exists = csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_HEADERS)
        if not csv_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def update_state(state: SyncState, responses: List[Dict[str, Any]]) -> SyncState:
    if not responses:
        return state
    dated_responses: List[Tuple[Dict[str, Any], datetime]] = []
    for resp in responses:
        submitted_at = resp.get("submittedAt") or resp.get("createdAt")
        parsed = parse_timestamp(submitted_at)
        if parsed:
            dated_responses.append((resp, parsed))
    if not dated_responses:
        return state
    latest, _ = max(
        dated_responses,
        key=lambda item: (item[1], item[0].get("id", "")),
    )
    submitted_at = latest.get("submittedAt") or latest.get("createdAt")
    state.last_submission = submitted_at
    state.last_response_id = latest.get("id")
    return state


def main() -> None:
    args = parse_args()
    state_path = Path(args.state_file)
    csv_path = Path(args.csv_path)

    responses = load_responses(args)
    responses.sort(key=lambda resp: resp.get("submittedAt") or resp.get("createdAt") or "")

    state = SyncState.from_file(state_path)
    new_responses = filter_new_responses(responses, state)
    mapped_rows = [map_response_to_row(resp) for resp in new_responses]

    if args.dry_run:
        print(json.dumps(mapped_rows, indent=2))
        return

    append_rows_to_csv(csv_path, mapped_rows)

    if new_responses:
        update_state(state, new_responses)
        state.save(state_path)


if __name__ == "__main__":
    main()
