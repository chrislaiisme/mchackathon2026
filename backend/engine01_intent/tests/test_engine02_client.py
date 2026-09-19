"""backend/engine01_intent/engine02_client.py 的單元測試——全部用 mock，不打真的 ENGINE02。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from backend.engine01_intent import engine02_client
from backend.shared.schemas import Intent


def _mock_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = payload
    return resp


def test_intent_rank_success_returns_retrieval_result():
    payload = {
        "session_id": "u1:s1",
        "round": 1,
        "match_score": 0.78,
        "products": [
            {
                "product_id": "12345",
                "image_url": "http://localhost:8000/engine02/images/12345",
                "title": "Navy Slim Fit Shirt",
                "score": 0.82,
                "reason": "符合你要求的正式場合",
            }
        ],
        "engine02": {"unresolved_from_intent": []},  # 多餘欄位，Pydantic 應該忽略
    }
    with patch("backend.engine01_intent.engine02_client.requests.post", return_value=_mock_response(payload)):
        result = engine02_client.intent_rank(Intent(item_type="襯衫"), "s1", 1, "我想要件襯衫")

    assert result is not None
    assert result.match_score == 0.78
    assert len(result.products) == 1
    assert result.products[0].product_id == "12345"


def test_intent_rank_namespaces_session_id_with_user_sub():
    payload = {"session_id": "x", "round": 0, "match_score": 0.0, "products": []}
    with patch("backend.engine01_intent.engine02_client.requests.post", return_value=_mock_response(payload)) as mock_post:
        engine02_client.intent_rank(Intent(), "s1", 0, "訊息", user_sub="user123")

    sent_json = mock_post.call_args.kwargs["json"]
    assert sent_json["session_id"] == "user123:s1"


def test_intent_rank_injects_gender_into_intent_payload():
    payload = {"session_id": "x", "round": 0, "match_score": 0.0, "products": []}
    with patch("backend.engine01_intent.engine02_client.requests.post", return_value=_mock_response(payload)) as mock_post:
        engine02_client.intent_rank(Intent(), "s1", 0, "訊息", gender="女")

    sent_json = mock_post.call_args.kwargs["json"]
    assert sent_json["intent"]["gender"] == "女"


def test_intent_rank_translates_frontend_english_gender_to_engine02_chinese():
    # 2026-09-19 真人測試發現：前端 onboarding（GENDER_OPTIONS）存的是英文
    # "Woman"/"Man"/"Non-binary"，但 ENGINE02 的 ZH_GENDER 表只認得中文詞，
    # 兩邊詞彙沒對過，等於 gender 訊號一直沒真的送到——使用者選了 Woman，
    # 還是被推薦男生商品。這裡確認 intent_rank() 有把英文轉成中文再送出去。
    payload = {"session_id": "x", "round": 0, "match_score": 0.0, "products": []}
    with patch("backend.engine01_intent.engine02_client.requests.post", return_value=_mock_response(payload)) as mock_post:
        engine02_client.intent_rank(Intent(), "s1", 0, "訊息", gender="Woman")

    sent_json = mock_post.call_args.kwargs["json"]
    assert sent_json["intent"]["gender"] == "女"


def test_intent_rank_drops_gender_with_no_engine02_mapping():
    # "Prefer not to say" 對不到任何 ENGINE02 認得的值，寧可完全不送這個
    # 欄位，也不要硬塞一個查不到的字串進去。
    payload = {"session_id": "x", "round": 0, "match_score": 0.0, "products": []}
    with patch("backend.engine01_intent.engine02_client.requests.post", return_value=_mock_response(payload)) as mock_post:
        engine02_client.intent_rank(Intent(), "s1", 0, "訊息", gender="Prefer not to say")

    sent_json = mock_post.call_args.kwargs["json"]
    assert "gender" not in sent_json["intent"]


def test_intent_rank_connection_error_returns_none():
    with patch(
        "backend.engine01_intent.engine02_client.requests.post",
        side_effect=requests.exceptions.ConnectionError("boom"),
    ):
        result = engine02_client.intent_rank(Intent(), "s1", 0, "訊息")
    assert result is None


def test_intent_rank_malformed_response_returns_none():
    # 缺少必填欄位 (match_score) -- RetrievalResult(**data) 應該丟 ValidationError，
    # 被 engine02_client 接住轉成 None，不能讓例外往外炸。
    with patch(
        "backend.engine01_intent.engine02_client.requests.post",
        return_value=_mock_response({"session_id": "x", "round": 0, "products": []}),
    ):
        result = engine02_client.intent_rank(Intent(), "s1", 0, "訊息")
    assert result is None


def test_visual_search_success_builds_product_cards():
    payload = {
        "response": {
            "items": [
                {"item_id": "abc", "title": "Black Sweater", "score": 0.9, "category": "top"},
            ]
        }
    }
    with patch("backend.engine01_intent.engine02_client.requests.post", return_value=_mock_response(payload)):
        cards = engine02_client.visual_search(b"fake-image-bytes", "black sweater")

    assert cards is not None
    assert len(cards) == 1
    assert cards[0].product_id == "abc"
    assert cards[0].attributes["category"] == "top"
    assert cards[0].explanation_source == "visual_search"


def test_visual_search_sends_non_empty_retrieval_text():
    # 回歸測試：一定要帶非空 retrieval_text，不能重演 ENGINE02 那個
    # 「retrieval_text 空字串時 80% 權重變成通用詞彙」的已知 bug。
    payload = {"response": {"items": []}}
    with patch("backend.engine01_intent.engine02_client.requests.post", return_value=_mock_response(payload)) as mock_post:
        engine02_client.visual_search(b"fake-image-bytes", "黑色 外套")

    sent_json = mock_post.call_args.kwargs["json"]
    assert sent_json["retrieval_text"] == "黑色 外套"
    assert sent_json["retrieval_text"] != ""


def test_visual_search_connection_error_returns_none():
    with patch(
        "backend.engine01_intent.engine02_client.requests.post",
        side_effect=requests.exceptions.ConnectionError("boom"),
    ):
        result = engine02_client.visual_search(b"fake-image-bytes", "黑色 外套")
    assert result is None


def test_complete_look_finds_target_zone_slate():
    payload = {
        "slates": [
            {"category": "outerwear", "items": [{"item_id": "o1", "title": "Coat", "score": 0.5}]},
            {
                "category": "bottom",
                "items": [
                    {"item_id": "b1", "title": "Navy Trousers", "score": 0.91, "reason": "顏色跟你選的上衣很搭"},
                ],
            },
        ]
    }
    with patch("backend.engine01_intent.engine02_client.requests.post", return_value=_mock_response(payload)) as mock_post:
        cards = engine02_client.complete_look("anchor1", "bottom")

    sent_json = mock_post.call_args.kwargs["json"]
    assert sent_json["anchor_item_ids"] == ["anchor1"]
    assert cards is not None
    assert len(cards) == 1
    assert cards[0].product_id == "b1"
    assert cards[0].reason == "顏色跟你選的上衣很搭"
    assert cards[0].explanation_source == "complete_look"


def test_complete_look_returns_none_when_target_zone_slate_missing():
    payload = {"slates": [{"category": "outerwear", "items": [{"item_id": "o1", "title": "Coat", "score": 0.5}]}]}
    with patch("backend.engine01_intent.engine02_client.requests.post", return_value=_mock_response(payload)):
        cards = engine02_client.complete_look("anchor1", "bottom")
    assert cards is None


def test_complete_look_unknown_anchor_returns_none():
    resp = MagicMock()
    resp.raise_for_status.side_effect = requests.exceptions.HTTPError("400 unknown anchor_item_ids")
    with patch("backend.engine01_intent.engine02_client.requests.post", return_value=resp):
        cards = engine02_client.complete_look("not-a-real-item", "bottom")
    assert cards is None
