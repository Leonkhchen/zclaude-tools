"""
app.py — 墨評：手寫詩句辨識與批改 Web 版（Flask）
=====================================================
路由：
  GET  /                          首頁
  GET  /api/poems                 取得詩句清單
  GET  /api/settings              取得目前 Colab 端點與模型設定
  POST /api/settings              更新 Colab 端點 / 切換模型
  POST /api/upload                上傳照片 → {submission_id}
  POST /api/process/<submission_id>   呼叫 Colab 辨識 + 批改 → 完整結果
  GET  /api/result/<submission_id>    取得先前的批改結果
  POST /api/export/<submission_id>    匯出批改結果（存檔 / Google Drive）
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

import drive_export
import grading
import ocr_client
from ocr_client import OCRServiceError

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB，手機照片綽綽有餘

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", BASE_DIR / "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_PATH = BASE_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "ocr_endpoint": os.environ.get("OCR_ENDPOINT", ""),
    "active_model": "",
}

# submission_id -> {image_path, poem_id, ocr, grade}
_submissions: dict[str, dict] = {}


# ── 設定檔（Colab 端點 / 模型）──────────────────────────────────────────

def _load_settings() -> dict:
    if SETTINGS_PATH.exists():
        try:
            return {**DEFAULT_SETTINGS, **json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_SETTINGS)


def _save_settings(settings: dict) -> None:
    SETTINGS_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_poems() -> list[dict]:
    return json.loads((DATA_DIR / "poems.json").read_text(encoding="utf-8"))


# ═══════════════════════════════════════════════════════════════════════
#  路由
# ═══════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/poems")
def poems():
    return jsonify(poems=_load_poems())


@app.route("/api/settings", methods=["GET"])
def get_settings():
    settings = _load_settings()
    info = {"endpoint": settings["ocr_endpoint"], "active_model": settings["active_model"],
            "available_models": [], "reachable": False, "error": None}

    if settings["ocr_endpoint"]:
        try:
            models = ocr_client.list_models(settings["ocr_endpoint"])
            info["available_models"] = models.get("available", [])
            info["active_model"] = models.get("active", settings["active_model"])
            info["reachable"] = True
        except OCRServiceError as exc:
            info["error"] = str(exc)

    return jsonify(**info)


@app.route("/api/settings", methods=["POST"])
def update_settings():
    body = request.get_json(silent=True) or {}
    settings = _load_settings()

    endpoint = body.get("endpoint")
    if endpoint is not None:
        settings["ocr_endpoint"] = endpoint.strip()

    model_name = body.get("model")
    result = {}
    if model_name and settings["ocr_endpoint"]:
        try:
            result = ocr_client.switch_model(settings["ocr_endpoint"], model_name)
            settings["active_model"] = result.get("active_model", model_name)
        except OCRServiceError as exc:
            return jsonify(error=str(exc)), 502

    _save_settings(settings)
    return jsonify(ok=True, endpoint=settings["ocr_endpoint"],
                    active_model=settings["active_model"], switch_result=result)


@app.route("/api/upload", methods=["POST"])
def upload():
    file = request.files.get("photo")
    poem_id = request.form.get("poem_id", "")
    if not file or not file.filename:
        return jsonify(error="未收到照片"), 400
    if not poem_id:
        return jsonify(error="請先選擇要比對的詩句"), 400

    submission_id = uuid.uuid4().hex
    ext = Path(file.filename).suffix.lower() or ".jpg"
    dest = UPLOAD_DIR / f"{submission_id}{ext}"
    file.save(str(dest))

    _submissions[submission_id] = {
        "image_path": str(dest),
        "poem_id": poem_id,
        "ocr": None,
        "grade": None,
    }
    return jsonify(submission_id=submission_id)


@app.route("/api/process/<submission_id>", methods=["POST"])
def process(submission_id: str):
    sub = _submissions.get(submission_id)
    if not sub:
        return jsonify(error="送出紀錄不存在，請重新上傳"), 404

    settings = _load_settings()
    if not settings["ocr_endpoint"]:
        return jsonify(error="尚未設定 Colab 辨識端點，請先到設定頁填入"), 400

    poems = {p["id"]: p for p in _load_poems()}
    poem = poems.get(sub["poem_id"])
    if not poem:
        return jsonify(error="找不到對應的詩句"), 400

    image_bytes = Path(sub["image_path"]).read_bytes()
    try:
        ocr_result = ocr_client.recognize(settings["ocr_endpoint"], image_bytes,
                                           filename=Path(sub["image_path"]).name)
    except OCRServiceError as exc:
        return jsonify(error=str(exc)), 502

    grade_result = grading.grade(
        recognized_text=ocr_result["text"],
        poem_id=poem["id"],
        poem_title=f"{poem['title']}（{poem['author']}）",
        poem_text=poem["text"],
    )
    grade_dict = grading.to_dict(grade_result)

    sub["ocr"] = ocr_result
    sub["grade"] = grade_dict

    return jsonify(ocr=ocr_result, grade=grade_dict)


@app.route("/api/result/<submission_id>")
def result(submission_id: str):
    sub = _submissions.get(submission_id)
    if not sub:
        return jsonify(error="送出紀錄不存在"), 404
    return jsonify(ocr=sub["ocr"], grade=sub["grade"])


@app.route("/api/export/<submission_id>", methods=["POST"])
def export(submission_id: str):
    sub = _submissions.get(submission_id)
    if not sub or not sub["grade"]:
        return jsonify(error="請先完成辨識與批改，才能匯出結果"), 400

    try:
        info = drive_export.export_result(submission_id, sub["grade"])
    except drive_export.ExportError as exc:
        return jsonify(error=str(exc)), 500
    return jsonify(**info)


@app.route("/uploads/<path:filename>")
def uploaded_file(filename: str):
    return send_from_directory(str(UPLOAD_DIR), filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
