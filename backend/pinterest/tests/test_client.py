"""backend/pinterest/client.py 的單元測試——全部用 mock，不打真的 Pinterest API。

三個情境對應 find_reference_image() 文件裡承諾的行為：沒有 token 就直接跳過、
比對到關鍵字就回傳分數最高那個 pin 的圖片網址、比對不到（或板子找不到）就
回傳 None，且任何一種情況都不能丟例外。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.pinterest import client as pinterest_client
from backend.shared.schemas import Intent


@pytest.fixture(autouse=True)
def _clear_board_cache():
    # board_id 快取是模組層級的 dict，測試之間要清乾淨，不然後面的測試
    # 會讀到前一個測試殘留的快取值，而不是真的走一次比對邏輯。
    pinterest_client._board_id_cache.clear()
    yield
    pinterest_client._board_id_cache.clear()


def _mock_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = payload
    return resp


def test_no_token_returns_none_without_calling_api(monkeypatch):
    monkeypatch.delenv("PINTEREST_ACCESS_TOKEN", raising=False)
    intent = Intent(item_type="外套", colors=["黑色"])

    with patch("backend.pinterest.client.requests.get") as mock_get:
        result = pinterest_client.find_reference_image(intent)

    assert result is None
    mock_get.assert_not_called()  # 沒有 token 應該直接跳過，連 API 都不用打


def test_finds_best_matching_pin(monkeypatch):
    monkeypatch.setenv("PINTEREST_ACCESS_TOKEN", "fake-token")
    monkeypatch.setenv("PINTEREST_BOARD_NAME", "intentweave-references")
    intent = Intent(item_type="外套", colors=["黑色"], occasion="正式場合")

    boards_resp = _mock_response(
        {"items": [{"id": "board123", "name": "intentweave-references"}]}
    )
    pins_resp = _mock_response(
        {
            "items": [
                {
                    "id": "pin1",
                    "title": "休閒白色 T-shirt",
                    "description": "夏天穿的休閒上衣",
                    "media": {"images": {"600x": {"url": "https://example.com/pin1.jpg"}}},
                },
                {
                    "id": "pin2",
                    "title": "黑色正式外套",
                    "description": "適合正式場合的黑色外套",
                    "media": {"images": {"600x": {"url": "https://example.com/pin2.jpg"}}},
                },
            ]
        }
    )

    with patch(
        "backend.pinterest.client.requests.get", side_effect=[boards_resp, pins_resp]
    ):
        result = pinterest_client.find_reference_image(intent)

    # pin2 同時命中「黑色」「外套」「正式場合」三個關鍵字，分數比 pin1 高。
    assert result == "https://example.com/pin2.jpg"


def test_no_match_returns_none(monkeypatch):
    monkeypatch.setenv("PINTEREST_ACCESS_TOKEN", "fake-token")
    monkeypatch.setenv("PINTEREST_BOARD_NAME", "intentweave-references")
    intent = Intent(item_type="洋裝", colors=["粉紅色"])

    boards_resp = _mock_response(
        {"items": [{"id": "board123", "name": "intentweave-references"}]}
    )
    pins_resp = _mock_response(
        {
            "items": [
                {
                    "id": "pin1",
                    "title": "登山外套",
                    "description": "戶外用的機能外套",
                    "media": {"images": {"600x": {"url": "https://example.com/pin1.jpg"}}},
                }
            ]
        }
    )

    with patch(
        "backend.pinterest.client.requests.get", side_effect=[boards_resp, pins_resp]
    ):
        result = pinterest_client.find_reference_image(intent)

    assert result is None


def test_board_not_found_returns_none_without_fetching_pins(monkeypatch):
    monkeypatch.setenv("PINTEREST_ACCESS_TOKEN", "fake-token")
    monkeypatch.setenv("PINTEREST_BOARD_NAME", "some-other-board")
    intent = Intent(item_type="外套")

    boards_resp = _mock_response(
        {"items": [{"id": "board123", "name": "intentweave-references"}]}
    )

    with patch(
        "backend.pinterest.client.requests.get", return_value=boards_resp
    ) as mock_get:
        result = pinterest_client.find_reference_image(intent)

    assert result is None
    assert mock_get.call_count == 1  # 找板子那次打了，但找不到名稱吻合的板子就不會再去拉 pins


def test_api_error_returns_none_instead_of_raising(monkeypatch):
    monkeypatch.setenv("PINTEREST_ACCESS_TOKEN", "fake-token")
    intent = Intent(item_type="外套")

    with patch(
        "backend.pinterest.client.requests.get", side_effect=ConnectionError("boom")
    ):
        result = pinterest_client.find_reference_image(intent)

    assert result is None  # 網路錯誤絕對不能讓這個函式往外丟例外
