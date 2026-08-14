"""
ocr_client.py — 呼叫 Colab 端辨識服務的薄客戶端。

Colab 端點是可設定的（存在 settings.json，也能透過 /api/settings 動態更
新），所以這裡完全不寫死網址；同一份程式碼可以指向任何一個實作了同樣
/health、/models、/switch_model、/ocr 介面的服務（例如未來把 Colab 換成
正式部署的服務時，這裡不用改）。
"""

from __future__ import annotations

import requests

DEFAULT_TIMEOUT = 30


class OCRServiceError(RuntimeError):
    """呼叫 Colab 辨識服務失敗時拋出，帶有給使用者看的訊息。"""


def _base(endpoint: str) -> str:
    return endpoint.rstrip("/")


def check_health(endpoint: str) -> dict:
    try:
        resp = requests.get(f"{_base(endpoint)}/health", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        raise OCRServiceError(f"連不上 Colab 端點：{exc}") from exc


def list_models(endpoint: str) -> dict:
    try:
        resp = requests.get(f"{_base(endpoint)}/models", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        raise OCRServiceError(f"取得模型清單失敗：{exc}") from exc


def switch_model(endpoint: str, name: str) -> dict:
    try:
        resp = requests.post(f"{_base(endpoint)}/switch_model", json={"name": name}, timeout=120)
        if resp.status_code == 400:
            raise OCRServiceError(resp.json().get("detail", "切換模型失敗"))
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        raise OCRServiceError(f"切換模型失敗：{exc}") from exc


def recognize(endpoint: str, image_bytes: bytes, filename: str = "photo.jpg") -> dict:
    """送出照片給 Colab 端辨識，回傳 {text, model, elapsed_ms}。"""
    try:
        resp = requests.post(
            f"{_base(endpoint)}/ocr",
            files={"file": (filename, image_bytes, "application/octet-stream")},
            timeout=DEFAULT_TIMEOUT,
        )
        if resp.status_code == 503:
            raise OCRServiceError("Colab 端尚未載入任何模型，請先到設定頁切換模型")
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        raise OCRServiceError(
            f"辨識失敗，請確認 Colab 端點是否還在線上（免費版 Colab 閒置會斷線）：{exc}"
        ) from exc
