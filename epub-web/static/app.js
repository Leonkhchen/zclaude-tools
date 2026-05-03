/**
 * app.js  —  EPUB/PDF 轉換器 Web 前端
 * 功能：拖放上傳、格式選擇、SSE 進度顯示、下載連結
 */

// ── 狀態 ──────────────────────────────────────────────────────────────────────
let jobId      = null;
let filesMeta  = [];          // [{id, name, size}]
let converting = false;

// ── DOM refs ──────────────────────────────────────────────────────────────────
const dropZone       = document.getElementById("drop-zone");
const fileInput      = document.getElementById("file-input");
const fileListSec    = document.getElementById("file-list-section");
const fileList       = document.getElementById("file-list");
const convertBtn     = document.getElementById("convert-btn");
const clearBtn       = document.getElementById("clear-btn");
const totalProgress  = document.getElementById("total-progress");
const progressBar    = document.getElementById("progress-bar");
const progressLabel  = document.getElementById("progress-label");
const progressPct    = document.getElementById("progress-pct");
const logSection     = document.getElementById("log-section");
const logBox         = document.getElementById("log-box");
const clearLogBtn    = document.getElementById("clear-log-btn");
const resultModal    = document.getElementById("result-modal");
const modalTitle     = document.getElementById("modal-title");
const modalBody      = document.getElementById("modal-body");

// ── 拖放 ──────────────────────────────────────────────────────────────────────
dropZone.addEventListener("dragover",  e => { e.preventDefault(); dropZone.classList.add("drag-over"); });
dropZone.addEventListener("dragleave", ()  => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop",      e => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  handleFiles(Array.from(e.dataTransfer.files));
});
fileInput.addEventListener("change", e => handleFiles(Array.from(e.target.files)));

// ── 清空 / Log ─────────────────────────────────────────────────────────────────
clearBtn.addEventListener("click", () => {
  if (converting) return;
  resetAll();
});
clearLogBtn.addEventListener("click", () => { logBox.textContent = ""; });
convertBtn.addEventListener("click", startConvert);

// ── 格式選擇 ──────────────────────────────────────────────────────────────────
function getFmt() {
  return document.querySelector('input[name="fmt"]:checked')?.value || "pdf";
}

// ═══════════════════════════════════════════════════════════════════════════════
//  檔案處理 & 上傳
// ═══════════════════════════════════════════════════════════════════════════════

function handleFiles(files) {
  const valid = files.filter(f => /\.(epub|pdf)$/i.test(f.name));
  if (!valid.length) {
    alert("請選擇 .epub 或 .pdf 檔案");
    return;
  }
  uploadFiles(valid);
}

async function uploadFiles(files) {
  convertBtn.disabled = true;
  convertBtn.textContent = "上傳中…";

  const fd = new FormData();
  files.forEach(f => fd.append("files", f));

  try {
    const res  = await fetch("/api/upload", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "上傳失敗");

    jobId     = data.job_id;
    filesMeta = data.files;
    renderFileList(filesMeta);
    fileListSec.classList.remove("hidden");
    convertBtn.disabled    = false;
    convertBtn.textContent = "▶ 開始轉換";
  } catch (err) {
    alert("上傳失敗：" + err.message);
    convertBtn.disabled    = false;
    convertBtn.textContent = "▶ 開始轉換";
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
//  檔案清單渲染
// ═══════════════════════════════════════════════════════════════════════════════

function renderFileList(files) {
  fileList.innerHTML = "";
  files.forEach(f => {
    const row = document.createElement("div");
    row.id    = `row-${f.id}`;
    row.className = "flex items-center gap-3 p-3 rounded-lg bg-slate-50 border border-slate-200";
    row.innerHTML = `
      <span id="icon-${f.id}" class="text-lg shrink-0">⏳</span>
      <div class="flex-1 min-w-0">
        <p class="text-sm font-medium text-slate-700 truncate">${escHtml(f.name)}</p>
        <p class="text-xs text-slate-400">${fmtSize(f.size)}</p>
        <div id="out-${f.id}" class="mt-1 flex flex-wrap gap-2 hidden"></div>
      </div>
      <span id="badge-${f.id}" class="text-xs text-slate-400 shrink-0">待轉換</span>
    `;
    fileList.appendChild(row);
  });
}

function updateFileRow(id, {status, out_files, error}) {
  const iconEl  = document.getElementById(`icon-${id}`);
  const badgeEl = document.getElementById(`badge-${id}`);
  const outEl   = document.getElementById(`out-${id}`);
  const rowEl   = document.getElementById(`row-${id}`);

  if (!iconEl) return;

  const icons   = { converting:"⚙️", ok:"✅", error:"❌" };
  const badges  = { converting:"轉換中…", ok:"成功", error:"失敗" };
  const colors  = {
    converting: "border-blue-200 bg-blue-50",
    ok:         "border-green-200 bg-green-50",
    error:      "border-red-200 bg-red-50",
  };

  iconEl.textContent  = icons[status]  || "⏳";
  badgeEl.textContent = badges[status] || status;
  if (colors[status]) {
    rowEl.className = `flex items-center gap-3 p-3 rounded-lg border ${colors[status]}`;
  }

  if (status === "error" && error) {
    badgeEl.textContent = "失敗";
    badgeEl.className   = "text-xs text-red-500 shrink-0";
    const errP = document.createElement("p");
    errP.className = "text-xs text-red-500 mt-1";
    errP.textContent = error;
    outEl.parentElement.appendChild(errP);
  }

  if (status === "ok" && out_files?.length) {
    outEl.classList.remove("hidden");
    outEl.innerHTML = "";
    out_files.forEach(fname => {
      const a = document.createElement("a");
      a.href      = `/api/download/${jobId}/${encodeURIComponent(fname)}`;
      a.download  = fname;
      a.className = "inline-flex items-center gap-1 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded px-2 py-1 transition-colors";
      a.innerHTML = `⬇ ${escHtml(fname)}`;
      outEl.appendChild(a);
    });
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
//  轉換 & SSE
// ═══════════════════════════════════════════════════════════════════════════════

async function startConvert() {
  if (converting || !jobId) return;
  converting = true;
  convertBtn.disabled    = true;
  convertBtn.textContent = "⏹ 轉換中…";

  // 顯示進度條
  totalProgress.classList.remove("hidden");
  progressBar.style.width = "0%";
  progressLabel.textContent = "準備中…";
  progressPct.textContent   = "";
  logSection.classList.remove("hidden");
  addLog("開始轉換…\n");

  try {
    const res = await fetch(`/api/convert/${jobId}`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ fmt: getFmt() }),
    });
    if (!res.ok) throw new Error((await res.json()).error || "轉換啟動失敗");
  } catch (err) {
    alert("錯誤：" + err.message);
    resetConvertBtn();
    return;
  }

  // SSE
  const evtSrc = new EventSource(`/api/progress/${jobId}`);

  evtSrc.onmessage = e => {
    let msg;
    try { msg = JSON.parse(e.data); } catch { return; }

    switch (msg.event) {
      case "log":
        addLog(msg.data.text);
        break;

      case "file_status": {
        const d = msg.data;
        updateFileRow(d.id, d);
        if (d.pct != null) {
          progressBar.style.width = d.pct + "%";
          progressPct.textContent = d.pct + "%";
          progressLabel.textContent = `${d.idx + 1} / ${d.total}`;
        }
        break;
      }

      case "done": {
        const d = msg.data;
        progressBar.style.width = "100%";
        progressPct.textContent = "100%";
        progressLabel.textContent = `完成：${d.ok} 成功 / ${d.errors} 失敗`;
        evtSrc.close();
        showResult(d);
        resetConvertBtn();
        break;
      }
    }
  };

  evtSrc.onerror = () => {
    evtSrc.close();
    resetConvertBtn();
  };
}

function resetConvertBtn() {
  converting = false;
  convertBtn.disabled    = false;
  convertBtn.textContent = "▶ 開始轉換";
}

// ═══════════════════════════════════════════════════════════════════════════════
//  結果彈窗
// ═══════════════════════════════════════════════════════════════════════════════

function showResult(d) {
  if (d.errors === 0) {
    modalTitle.textContent = `✅ 全部完成！（${d.ok} 個檔案）`;
    modalTitle.className   = "text-xl font-bold mb-4 text-green-700";
  } else {
    modalTitle.textContent = `⚠️ 完成，${d.ok} 成功 / ${d.errors} 失敗`;
    modalTitle.className   = "text-xl font-bold mb-4 text-orange-600";
  }
  modalBody.innerHTML = "<p>請在檔案清單中點擊 ⬇ 下載轉換後的檔案。</p>";
  resultModal.classList.remove("hidden");
}

// ═══════════════════════════════════════════════════════════════════════════════
//  輔助
// ═══════════════════════════════════════════════════════════════════════════════

function resetAll() {
  jobId      = null;
  filesMeta  = [];
  fileList.innerHTML = "";
  fileListSec.classList.add("hidden");
  totalProgress.classList.add("hidden");
  logSection.classList.add("hidden");
  logBox.textContent = "";
  fileInput.value = "";
  resetConvertBtn();
}

function addLog(text) {
  logBox.textContent += text + (text.endsWith("\n") ? "" : "\n");
  logBox.scrollTop    = logBox.scrollHeight;
}

function fmtSize(bytes) {
  if (bytes < 1024)        return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1024 / 1024).toFixed(2) + " MB";
}

function escHtml(s) {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
