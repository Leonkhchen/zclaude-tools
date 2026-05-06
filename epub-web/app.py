"""
app.py  —  EPUB / PDF 轉換器 Web 版（Flask + SSE）
===================================================
路由：
  GET  /                         首頁
  POST /api/upload               上傳檔案 → {job_id, files:[{id,name,size}]}
  POST /api/convert/<job_id>     開始轉換 → {ok:true}
  GET  /api/progress/<job_id>    SSE 進度流
  GET  /api/download/<job_id>/<fname>   下載輸出檔案
  GET  /api/status/<job_id>      取得 job 完整狀態（JSON）
"""

from __future__ import annotations
import os, uuid, json, time, queue, threading, traceback, sys
from pathlib import Path
from flask import Flask, request, jsonify, send_file, Response, render_template

def _dbg(msg: str):
    print(f"[PID={os.getpid()}] {msg}", file=sys.stderr, flush=True)

from converter import (
    convert_to_pdf, convert_to_md, convert_pdf_to_epub, CALIBRE_PATH
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024   # 200 MB

JOBS_DIR   = Path(os.environ.get("JOBS_DIR", "/tmp/epub_jobs"))
JOBS_DIR.mkdir(parents=True, exist_ok=True)

# ── 全域 job 狀態 ─────────────────────────────────────────────────────────────
# jobs[job_id] = {
#   "files": [ {id, name, status, out_files:[], error} ],
#   "fmt":   "pdf"|"md"|"both",
#   "done":  False,
#   "queue": Queue(),    # SSE 事件用
# }
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

ALLOWED_EXT = {".epub", ".pdf"}


# ── 輔助 ──────────────────────────────────────────────────────────────────────

def _job_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id

def _in_dir(job_id: str) -> Path:
    p = _job_dir(job_id) / "input"
    p.mkdir(parents=True, exist_ok=True)
    return p

def _out_dir(job_id: str) -> Path:
    p = _job_dir(job_id) / "output"
    p.mkdir(parents=True, exist_ok=True)
    return p

def _push(q: queue.Queue, event: str, data: dict):
    q.put({"event": event, "data": data})

def _safe_name(name: str) -> str:
    """清理檔名，只保留安全字元。"""
    safe = "".join(c for c in name if c.isalnum() or c in "._- ()[]")
    return safe or "file"


# ═══════════════════════════════════════════════════════════════════════════════
#  路由
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html",
                            calibre_ok=bool(CALIBRE_PATH))


@app.route("/api/upload", methods=["POST"])
def upload():
    files = request.files.getlist("files")
    if not files:
        return jsonify(error="未收到檔案"), 400

    job_id   = uuid.uuid4().hex
    in_path  = _in_dir(job_id)
    out_path = _out_dir(job_id)
    file_meta = []

    for f in files:
        orig = f.filename or "unknown"
        ext  = Path(orig).suffix.lower()
        if ext not in ALLOWED_EXT:
            continue
        safe  = _safe_name(Path(orig).stem) + ext
        dest  = in_path / safe
        # 避免重名
        n = 1
        while dest.exists():
            dest = in_path / f"{_safe_name(Path(orig).stem)}_{n}{ext}"
            n += 1
        f.save(str(dest))
        size = dest.stat().st_size
        fid  = uuid.uuid4().hex[:8]
        file_meta.append({
            "id":       fid,
            "name":     safe,
            "orig":     orig,
            "path":     str(dest),
            "size":     size,
            "status":   "pending",
            "out_files": [],
            "error":    "",
        })

    if not file_meta:
        return jsonify(error="沒有有效的 .epub 或 .pdf 檔案"), 400

    with _jobs_lock:
        _jobs[job_id] = {
            "files": file_meta,
            "fmt":   "pdf",
            "done":  False,
            "queue": queue.Queue(),
        }
        _dbg(f"UPLOAD job={job_id} total_jobs={list(_jobs.keys())}")

    return jsonify(job_id=job_id,
                   files=[{"id": f["id"], "name": f["name"],
                            "size": f["size"]} for f in file_meta])


@app.route("/api/convert/<job_id>", methods=["POST"])
def start_convert(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        _dbg(f"CONVERT job={job_id} found={job is not None} all_jobs={list(_jobs.keys())}")
    if not job:
        return jsonify(error="job 不存在"), 404

    body = request.get_json(silent=True) or {}
    fmt  = body.get("fmt", "pdf")
    if fmt not in ("pdf", "md", "both"):
        fmt = "pdf"
    job["fmt"] = fmt

    t = threading.Thread(target=_worker, args=(job_id,), daemon=True)
    t.start()
    return jsonify(ok=True)


@app.route("/api/progress/<job_id>")
def progress(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify(error="job 不存在"), 404

    q: queue.Queue = job["queue"]

    def generate():
        # 傳送 keep-alive 讓瀏覽器確認連線
        yield "data: {\"type\":\"connected\"}\n\n"
        while True:
            try:
                msg = q.get(timeout=30)
            except queue.Empty:
                # heartbeat
                yield ": heartbeat\n\n"
                continue
            payload = json.dumps(msg, ensure_ascii=False)
            yield f"data: {payload}\n\n"
            if msg.get("event") == "done":
                break

    return Response(generate(),
                    content_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Accel-Buffering": "no",
                    })


@app.route("/api/download/<job_id>/<fname>")
def download(job_id: str, fname: str):
    path = _out_dir(job_id) / fname
    if not path.exists():
        return jsonify(error="檔案不存在"), 404
    return send_file(str(path), as_attachment=True, download_name=fname)


@app.route("/api/status/<job_id>")
def status(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify(error="job 不存在"), 404
    return jsonify(
        done=job["done"],
        fmt=job["fmt"],
        files=[{
            "id":       f["id"],
            "name":     f["name"],
            "status":   f["status"],
            "out_files": f["out_files"],
            "error":    f["error"],
        } for f in job["files"]]
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  背景轉換 worker
# ═══════════════════════════════════════════════════════════════════════════════

def _worker(job_id: str):
    with _jobs_lock:
        job = _jobs[job_id]

    files   = job["files"]
    fmt     = job["fmt"]
    q       = job["queue"]
    out_dir = _out_dir(job_id)
    total   = len(files)

    def log(msg: str):
        _push(q, "log", {"text": msg})

    for i, f in enumerate(files):
        src_path = Path(f["path"])
        stem     = src_path.stem
        ext      = src_path.suffix.lower()

        f["status"] = "converting"
        _push(q, "file_status", {
            "id": f["id"], "status": "converting",
            "idx": i, "total": total
        })
        log(f"\n[{i+1}/{total}]  {f['name']}")

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
                    convert_to_pdf(src_path, pdf_out, log)
                    if pdf_out.exists():
                        out_files.append(pdf_out.name)
                if fmt in ("md", "both"):
                    md_out = out_dir / (stem + ".md")
                    convert_to_md(src_path, md_out, log)
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
    _push(q, "done", {
        "total": total, "ok": ok_count, "errors": err_count
    })


# ═══════════════════════════════════════════════════════════════════════════════
#  入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
