from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.sync_tally_reviews import CSV_HEADERS, map_response_to_row


def test_map_response_to_row_defaults_new_reviews_to_pending():
    response = {
        "id": "response-123",
        "submittedAt": "2026-04-12T01:00:00Z",
        "answers": [
            {"question": {"label": "Category"}, "value": "Kitchen"},
            {"question": {"label": "Brand"}, "value": "GreenSip"},
            {"question": {"label": "Name"}, "value": "Reusable Straw"},
            {"question": {"label": "Total Rating"}, "value": 5},
            {"question": {"label": "Reccommend"}, "value": "Yes"},
            {"question": {"label": "Comment"}, "value": "Easy to carry and clean."},
        ],
    }

    row = map_response_to_row(response)

    assert list(row.keys()) == CSV_HEADERS
    assert row["Timestamp"] == "2026-04-12T01:00:00Z"
    assert row["Category"] == "Kitchen"
    assert row["Brand"] == "GreenSip"
    assert row["Product"] == "Reusable Straw"
    assert row["Rating"] == "5"
    assert row["Recommended"] == "Yes"
    assert row["Comment"] == "Easy to carry and clean."
    assert row["Status"] == "Pending"
