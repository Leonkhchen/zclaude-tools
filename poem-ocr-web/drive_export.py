"""
drive_export.py — 把批改結果匯出成檔案，並存到 Google Drive。

目前狀態：Google Drive 這段還沒接上真的帳號授權（需要使用者自己的 Google
Cloud 專案 OAuth 憑證，沒辦法在這個專案裡幫你先準備好），所以先落地存到
本機 exports/ 資料夾，讓整條「辨識→批改→輸出檔案」的流程可以先跑通。

要接上真正的 Google Drive，把 `_upload_to_drive()` 換成下面這樣即可，其他
程式碼都不用改：

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    def _upload_to_drive(file_path: Path, folder_name: str, creds: Credentials) -> str:
        service = build("drive", "v3", credentials=creds)
        folder_id = _get_or_create_folder(service, folder_name)
        media = MediaFileUpload(str(file_path), resumable=True)
        file = service.files().create(
            body={"name": file_path.name, "parents": [folder_id]},
            media_body=media,
            fields="id, webViewLink",
        ).execute()
        return file["webViewLink"]

`creds` 由使用者透過 Google OAuth 2.0 授權流程取得（scope 建議只要
`drive.file`），可以參考 google-auth-oauthlib 的官方教學。授權完成後把
token 存起來（例如存在 session 或資料庫），呼叫這裡時傳進來即可。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

EXPORTS_DIR = Path(__file__).parent / "exports"
EXPORTS_DIR.mkdir(exist_ok=True)

DRIVE_CONNECTED = False  # 之後接上真的 OAuth 後改成 True，或改成動態判斷


class ExportError(RuntimeError):
    pass


def _build_result_document(submission_id: str, grade_dict: dict) -> str:
    """把批改結果組成一份簡單的文字報告。之後可以換成產生 PDF。"""
    lines = [
        f"墨評批改結果",
        f"詩題：{grade_dict['poem_title']}",
        f"送出編號：{submission_id}",
        f"正確率：{grade_dict['accuracy']}%（{grade_dict['correct_count']}/{grade_dict['total_count']} 字）",
        "",
        "標準詩句：",
        grade_dict["expected_text"],
        "",
        "辨識結果：",
        grade_dict["recognized_text"],
        "",
        "逐字比對：",
    ]
    for seg in grade_dict["segments"]:
        if seg["op"] == "equal":
            continue
        if seg["op"] == "wrong":
            lines.append(f"  錯字：應為「{seg['expected']}」，寫成「{seg['got']}」")
        elif seg["op"] == "missing":
            lines.append(f"  漏字：少了「{seg['expected']}」")
        elif seg["op"] == "extra":
            lines.append(f"  多字：多寫了「{seg['got']}」")
    return "\n".join(lines)


def export_result(submission_id: str, grade_dict: dict, folder_name: str = "墨評批改結果") -> dict:
    """匯出批改結果。回傳 {stored_at, drive_url, note}。

    Google Drive 還沒串接真的帳號時，先存到本機並回傳本機路徑，`note`
    欄位會清楚告訴前端目前是本機模式。
    """
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    safe_title = grade_dict["poem_title"].replace("/", "_")
    filename = f"{safe_title}_{submission_id[:8]}_{timestamp}.txt"
    out_path = EXPORTS_DIR / filename

    content = _build_result_document(submission_id, grade_dict)
    out_path.write_text(content, encoding="utf-8")

    if not DRIVE_CONNECTED:
        return {
            "stored_at": str(out_path),
            "drive_url": None,
            "note": (
                "尚未串接 Google Drive 帳號授權，結果先存在伺服器本機 "
                f"exports/{filename}。要接上真的 Google Drive，"
                "請參考 drive_export.py 檔案開頭的說明完成 OAuth 授權。"
            ),
        }

    # drive_url = _upload_to_drive(out_path, folder_name, creds)  # 接上後啟用
    raise ExportError("DRIVE_CONNECTED 為 True 但尚未實作 _upload_to_drive()")
