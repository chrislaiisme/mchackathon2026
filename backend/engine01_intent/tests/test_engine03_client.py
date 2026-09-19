"""backend/engine01_intent/engine03_client.py 的單元測試——全部用 mock，不打真的 ENGINE03。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from backend.engine01_intent import engine03_client


def _mock_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = payload
    return resp


def test_submit_feedback_success_returns_response_dict():
    payload = {
        "contract_version": "0.6.0",
        "session_id": "s1",
        "round": 2,
        "engine02_feedback": {"chosen_item_ids": ["a"], "rejected_item_ids": [], "choice_history": [], "design_weight_delta": {}},
        "attribute_evidence": [],
    }
    with patch("backend.engine01_intent.engine03_client.requests.post", return_value=_mock_response(payload)) as mock_post:
        result = engine03_client.submit_feedback(
            "s1", [], {"round": 2, "shown_item_ids": ["a"], "item_feedbacks": [{"item_id": "a", "favorited": True}]},
            authorization="Bearer test-token",
        )

    assert result == payload
    sent_json = mock_post.call_args.kwargs["json"]
    assert sent_json["session_id"] == "s1"
    assert sent_json["round"] == 2
    assert sent_json["item_feedbacks"] == [{"item_id": "a", "favorited": True}]
    # Authorization header 一定要原樣轉發——ENGINE03 掛了 get_current_user，
    # 跟完全不驗證的 ENGINE02 不一樣，漏了這步在 DEV_BYPASS_AUTH=false 會直接 401。
    assert mock_post.call_args.kwargs["headers"] == {"Authorization": "Bearer test-token"}


def test_submit_feedback_without_authorization_sends_no_header():
    payload = {"engine02_feedback": {}}
    with patch("backend.engine01_intent.engine03_client.requests.post", return_value=_mock_response(payload)) as mock_post:
        engine03_client.submit_feedback("s1", [], {"round": 1, "shown_item_ids": []})

    assert mock_post.call_args.kwargs["headers"] == {}


def test_submit_feedback_connection_error_returns_none():
    with patch(
        "backend.engine01_intent.engine03_client.requests.post",
        side_effect=requests.exceptions.ConnectionError("no route"),
    ):
        assert engine03_client.submit_feedback("s1", [], {"round": 1, "shown_item_ids": []}) is None


def test_submit_feedback_http_error_returns_none():
    resp = MagicMock()
    resp.raise_for_status.side_effect = requests.exceptions.HTTPError("422")
    with patch("backend.engine01_intent.engine03_client.requests.post", return_value=resp):
        assert engine03_client.submit_feedback("s1", [], {"round": 1, "shown_item_ids": []}) is None


def test_submit_feedback_missing_engine02_feedback_key_returns_none():
    with patch(
        "backend.engine01_intent.engine03_client.requests.post",
        return_value=_mock_response({"session_id": "s1", "round": 1}),
    ):
        assert engine03_client.submit_feedback("s1", [], {"round": 1, "shown_item_ids": []}) is None
