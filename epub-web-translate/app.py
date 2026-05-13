"""
app.py  —  EPUB / PDF 轉換器（含翻譯版）
=========================================
新增功能：
  - 翻譯模式：none / bilingual / zh
  - 簡易密碼保護（設定 APP_PASSWORD 環境變數啟用）

路由：
  GET  /                         首頁
  GET  /login                    登入頁（僅 APP_PASSWORD 啟用時）
  POST /login                    驗證密碼
  GET  /logout                   登出
  POST /api/upload               上傳檔案 → {job_id, files:[{id,name,size}]}
  POST /api/convert/<job_id>     開始轉換（含 translation_mode）
  GET  /api/progress/<job_id>    SSE 進度流
  GET  /api/download/<job_id>/<fname>   下載輸出檔案
  GET  /api/status/<job_id>      取得 job 完整狀態
"""

from __future__ import annotations
import os, uuid, json, time, queue, threading, traceback, sys, hashlib
from pathlib import Path
from functools import wraps
from flask import (Flask, request, jsonify, send_file, Response,
                   render_template, session, redirect, url_for)

def _dbg(msg: str):
    print(f"[PID={os.getpid()}] {msg}", file=sys.stderr, flush=True)

from converter import (
    convert_to_pdf, convert_to_md, convert_pdf_to_epub, CALIBRE_PATH
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(32))

JOBS_DIR     = Path(os.environ.get("JOBS_DIR", "/tmp/epub_jobs"))
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")   # 空字串 = 不啟用密碼保護
JOBS_DIR.mkdir(parents=True, exist_ok=True)

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
ALLOWED_EXT = {".epub", ".pdf"}


# ── 密碼保護 ──────────────────────────────────────────────────────────────────

def _check_auth():
    """若未啟用密碼或已登入，回傳 True。"""
    if not APP_PASSWORD:
        return True
    return session.get("authed") is True


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _check_auth():
            if request.path.startswith("/api/"):
                return jsonify(error="未授權"), 401
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET"])
def login_page():
    if _check_auth():
        return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login_post():
    pwd = request.form.get("password", "")
    if pwd == APP_PASSWORD:
        session["authed"] = True
        return redirect(url_for("index"))
    return render_template("login.html", error="密碼錯誤"), 401


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page") if APP_PASSWORD else url_for("index"))


# ── 輔助 ──────────────────────────────────────────────────────────────────────

def _job_dir(job_id):  return JOBS_DIR / job_id
def _in_dir(job_id):
    p = _job_dir(job_id) / "input"; p.mkdir(parents=True, exist_ok=True); return p
def _out_dir(job_id):
    p = _job_dir(job_id) / "output"; p.mkdir(parents=True, exist_ok=True); return p
def _push(q, event, data):
    q.put({"event": event, "data": data})
def _safe_name(name):
    safe = "".join(c for c in name if c.isalnum() or c in "._- ()[]")
    return safe or "file"


# ═══════════════════════════════════════════════════════════════════════════════
#  路由
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/")
@login_required
def index():
    return render_template("index.html",
                            calibre_ok=bool(CALIBRE_PATH),
                            has_password=bool(APP_PASSWORD))


@app.route("/api/upload", methods=["POST"])
@login_required
def upload():
    files = request.files.getlist("files")
    if not files:
        return jsonify(error="未收到檔案"), 400

    job_id   = uuid.uuid4().hex
    in_path  = _in_dir(job_id)
    _out_dir(job_id)
    file_meta = []

    for f in files:
        orig = f.filename or "unknown"
        ext  = Path(orig).suffix.lower()
        if ext not in ALLOWED_EXT:
            continue
        safe = _safe_name(Path(orig).stem) + ext
        dest = in_path / safe
        n = 1
        while dest.exists():
            dest = in_path / f"{_safe_name(Path(orig).stem)}_{n}{ext}"
            n += 1
        f.save(str(dest))
        fid = uuid.uuid4().hex[:8]
        file_meta.append({
            "id": fid, "name": safe, "orig": orig,
            "path": str(dest), "size": dest.stat().st_size,
            "status": "pending", "out_files": [], "error": "",
        })

    if not file_meta:
        return jsonify(error="沒有有效的 .epub 或 .pdf 檔案"), 400

    with _jobs_lock:
        _jobs[job_id] = {
            "files": file_meta,
            "fmt":   "pdf",
            "trans": "none",
            "done":  False,
            "queue": queue.Queue(),
        }

    return jsonify(job_id=job_id,
                   files=[{"id": f["id"], "name": f["name"],
                            "size": f["size"]} for f in file_meta])


@app.route("/api/convert/<job_id>", methods=["POST"])
@login_required
def start_convert(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify(error="job 不存在"), 404

    body  = request.get_json(silent=True) or {}
    fmt   = body.get("fmt", "pdf")
    trans = body.get("translation_mode", "none")
    if fmt not in ("pdf", "md", "both"):
        fmt = "pdf"
    if trans not in ("none", "bilingual", "zh"):
        trans = "none"
    job["fmt"]   = fmt
    job["trans"] = trans

    t = threading.Thread(target=_worker, args=(job_id,), daemon=True)
    t.start()
    return jsonify(ok=True)


@app.route("/api/progress/<job_id>")
@login_required
def progress(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify(error="job 不存在"), 404

    q = job["queue"]

    def generate():
        yield "data: {\"type\":\"connected\"}\n\n"
        while True:
            try:
                msg = q.get(timeout=30)
            except queue.Empty:
                yield ": heartbeat\n\n"
                continue
            yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
            if msg.get("event") == "done":
                break

    return Response(generate(),
                    content_type="text/event-stream",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})


@app.route("/api/download/<job_id>/<fname>")
@login_required
def download(job_id: str, fname: str):
    path = _out_dir(job_id) / fname
    if not path.exists():
        return jsonify(error="檔案不存在"), 404
    return send_file(str(path), as_attachment=True, download_name=fname)


@app.route("/api/status/<job_id>")
@login_required
def status(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify(error="job 不存在"), 404
    return jsonify(
        done=job["done"], fmt=job["fmt"], trans=job["trans"],
        files=[{"id":f["id"],"name":f["name"],"status":f["status"],
                "out_files":f["out_files"],"error":f["error"]}
               for f in job["files"]]
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  背景 Worker
# ═══════════════════════════════════════════════════════════════════════════════

def _worker(job_id: str):
    with _jobs_lock:
        job = _jobs[job_id]

    files   = job["files"]
    fmt     = job["fmt"]
    trans   = job["trans"]
    q       = job["queue"]
    out_dir = _out_dir(job_id)
    total   = len(files)

    def log(msg: str):
        _push(q, "log", {"text": msg})
        print(msg, file=sys.stderr, flush=True)

    for i, f in enumerate(files):
        src_path = Path(f["path"])
        stem     = src_path.stem
        ext      = src_path.suffix.lower()

        f["status"] = "converting"
        _push(q, "file_status", {
            "id": f["id"], "status": "converting",
            "idx": i, "total": total
        })
        log(f"\n[{i+1}/{total}]  {f['name']}  (翻譯模式: {trans})")

        try:
            out_files = []
            if ext == ".pdf":
                epub_out = out_dir / (stem + ".epub")
                log("  模式：PDF → EPUB")
                convert_pdf_to_epub(src_path, epub_out, log)
                if epub_out.exists():
                    out_files.append(epub_out.name)
            else:
                if fmt in ("pdf", "both"):
                    pdf_out = out_dir / (stem + ".pdf")
                    convert_to_pdf(src_path, pdf_out, log, translation_mode=trans)
                    if pdf_out.exists():
                        out_files.append(pdf_out.name)
                if fmt in ("md", "both"):
                    md_out = out_dir / (stem + ".md")
                    convert_to_md(src_path, md_out, log, translation_mode=trans)
                    if md_out.exists():
                        out_files.append(md_out.name)

            f["status"]    = "ok"
            f["out_files"] = out_files
            _push(q, "file_status", {
                "id": f["id"], "status": "ok",
                "out_files": out_files,
                "idx": i, "total": total,
                "pct": int((i + 1) / total * 100),
            })
            log(f"  SUCCESS: {', '.join(out_files)}")

        except Exception as e:
            f["status"] = "error"
            f["error"]  = str(e)
            _push(q, "file_status", {
                "id": f["id"], "status": "error",
                "error": str(e),
                "idx": i, "total": total,
                "pct": int((i + 1) / total * 100),
            })
            log(f"  FAIL: {e}")
            traceback.print_exc()

    job["done"] = True
    ok_count  = sum(1 for f in files if f["status"] == "ok")
    err_count = total - ok_count
    _push(q, "done", {"total": total, "ok": ok_count, "errors": err_count})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
