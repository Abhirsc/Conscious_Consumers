from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.sync_tally_reviews import (
    CSV_HEADERS,
    map_response_to_row,
    normalise_submissions_payload,
)


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


def test_normalise_submissions_payload_maps_current_tally_schema():
    payload = {
        "questions": [
            {"id": "q1", "title": "2.&nbsp;What&nbsp;product&nbsp;category&nbsp;are&nbsp;you&nbsp;reviewing?"},
            {"id": "q2", "title": "3. Brand of this product?"},
            {"id": "q3", "title": "4. Name of this product?"},
            {"id": "q4", "title": "🌱 Eco-friendly"},
            {"id": "q5", "title": "💰 Affordable"},
            {"id": "q6", "title": "🌍 Local / Ethical"},
            {"id": "q7", "title": "💪 Durable / Quality"},
            {"id": "q8", "title": "😍 Aesthetic / Packaging"},
            {"id": "q9", "title": "6. Would you recommend this in Sydney?"},
            {"id": "q10", "title": "7. How companies can make this product better for you?"},
        ],
        "submissions": [
            {
                "id": "submission-1",
                "submittedAt": "2026-04-13T06:45:01.000Z",
                "createdAt": "2026-04-13T06:45:01.000Z",
                "responses": [
                    {"questionId": "q1", "answer": ["🧼 Cleaning & Laundry"]},
                    {"questionId": "q2", "answer": "Test Brand"},
                    {"questionId": "q3", "answer": "Test Product"},
                    {"questionId": "q4", "answer": ["Yes [1]"]},
                    {"questionId": "q5", "answer": ["Yes [1]"]},
                    {"questionId": "q6", "answer": ["Maybe (Need research) [0.5]"]},
                    {"questionId": "q7", "answer": ["No [0]"]},
                    {"questionId": "q8", "answer": ["Yes [1]"]},
                    {"questionId": "q9", "answer": ["Yes"]},
                    {"questionId": "q10", "answer": "Improve refill access."},
                ],
            }
        ],
    }

    responses = normalise_submissions_payload(payload)

    assert len(responses) == 1
    row = map_response_to_row(responses[0])
    assert row["Timestamp"] == "2026-04-13T06:45:01.000Z"
    assert row["Category"] == "🧼 Cleaning & Laundry"
    assert row["Brand"] == "Test Brand"
    assert row["Product"] == "Test Product"
    assert row["Recommended"] == "Yes"
    assert row["Comment"] == "Improve refill access."
    assert row["Rating"] == "3.5"
    assert row["Status"] == "Pending"
