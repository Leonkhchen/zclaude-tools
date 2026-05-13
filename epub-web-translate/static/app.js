/* app.js — EPUB 翻譯轉換器前端 */

// ── 狀態 ─────────────────────────────────────────────────────────────────────
let jobId        = null;
let pendingFiles = [];   // {name, size, id?, status, outFiles}
let converting   = false;

// ── DOM refs ──────────────────────────────────────────────────────────────────
const dropZone       = document.getElementById("drop-zone");
const fileInput      = document.getElementById("file-input");
const fileListSec    = document.getElementById("file-list-section");
const fileListEl     = document.getElementById("file-list");
const clearBtn       = document.getElementById("clear-btn");
const convertBtn     = document.getElementById("convert-btn");
const progressArea   = document.getElementById("progress-area");
const progressBar    = document.getElementById("progress-bar");
const progressLabel  = document.getElementById("progress-label");
const progressPct    = document.getElementById("progress-pct");
const logSection     = document.getElementById("log-section");
const logBox         = document.getElementById("log-box");
const doneModal      = document.getElementById("done-modal");
const doneTitle      = document.getElementById("done-title");

// ── 翻譯卡片選取高亮 ──────────────────────────────────────────────────────────
document.querySelectorAll(".trans-card").forEach(card => {
  card.addEventListener("click", () => {
    document.querySelectorAll(".trans-card").forEach(c => c.classList.remove("selected"));
    card.classList.add("selected");
  });
});

// ── 拖放 ──────────────────────────────────────────────────────────────────────
dropZone.addEventListener("dragover",  e => { e.preventDefault(); dropZone.classList.add("drag-over"); });
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", e => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  handleFiles([...e.dataTransfer.files]);
});
fileInput.addEventListener("change", () => {
  handleFiles([...fileInput.files]);
  fileInput.value = "";
});

// ── 工具函式 ──────────────────────────────────────────────────────────────────
function fmtSize(b) {
  if (b < 1024)       return `${b} B`;
  if (b < 1024*1024)  return `${(b/1024).toFixed(1)} KB`;
  return `${(b/1024/1024).toFixed(1)} MB`;
}

function getFmt()   { return document.querySelector('input[name="fmt"]:checked')?.value  || "pdf"; }
function getTrans() { return document.querySelector('input[name="trans"]:checked')?.value || "none"; }

function statusIcon(s) {
  if (s === "pending")    return `<span class="text-slate-400 text-lg">⏳</span>`;
  if (s === "converting") return `<span class="text-blue-500 text-lg animate-spin inline-block">⚙</span>`;
  if (s === "ok")         return `<span class="text-green-500 text-lg">✅</span>`;
  if (s === "error")      return `<span class="text-red-500 text-lg">✖</span>`;
  return "";
}

function statusLabel(s) {
  if (s === "pending")    return `<span class="text-slate-400 text-xs">待轉換</span>`;
  if (s === "converting") return `<span class="text-blue-500 text-xs">轉換中…</span>`;
  if (s === "error")      return `<span class="text-red-500 text-xs">失敗</span>`;
  return "";
}

function addLog(text) {
  logBox.textContent += text + "\n";
  logBox.scrollTop = logBox.scrollHeight;
}

// ── 渲染檔案清單 ──────────────────────────────────────────────────────────────
function renderList() {
  fileListEl.innerHTML = "";
  pendingFiles.forEach((f, idx) => {
    const isErr = f.status === "error";
    const div = document.createElement("div");
    div.className = `flex items-start gap-3 p-3 rounded-xl border ${
      isErr ? "bg-red-50 border-red-200" : "bg-slate-50 border-slate-200"
    }`;
    div.id = `file-row-${idx}`;

    // 下載按鈕
    let dlButtons = "";
    if (f.status === "ok" && f.outFiles && f.outFiles.length) {
      dlButtons = f.outFiles.map(name =>
        `<a href="/api/download/${jobId}/${encodeURIComponent(name)}"
            download="${name}"
            class="inline-flex items-center gap-1 text-xs bg-blue-600 hover:bg-blue-700
                   text-white rounded-lg px-3 py-1 transition-colors">
          ⬇ ${name}
         </a>`
      ).join(" ");
    }

    div.innerHTML = `
      <div class="mt-0.5 shrink-0">${statusIcon(f.status)}</div>
      <div class="flex-1 min-w-0">
        <p class="text-sm font-medium text-slate-700 truncate">${f.name}</p>
        <p class="text-xs text-slate-400">${fmtSize(f.size)}</p>
        ${isErr ? `<p class="text-xs text-red-500 mt-1">${f.error || ""}</p>` : ""}
        ${dlButtons ? `<div class="flex flex-wrap gap-2 mt-2">${dlButtons}</div>` : ""}
      </div>
      <div class="shrink-0">${statusLabel(f.status)}</div>
    `;
    fileListEl.appendChild(div);
  });

  fileListSec.classList.toggle("hidden", pendingFiles.length === 0);
}

// ── 處理選取的檔案 ────────────────────────────────────────────────────────────
function handleFiles(files) {
  if (converting) return;
  const valid = files.filter(f =>
    f.name.toLowerCase().endsWith(".epub") ||
    f.name.toLowerCase().endsWith(".pdf")
  );
  if (!valid.length) { alert("請選擇 .epub 或 .pdf 檔案。"); return; }
  pendingFiles = [...pendingFiles, ...valid.map(f => ({
    name: f.name, size: f.size,
    status: "pending", outFiles: [], error: "",
  }))];
  renderList();
}

// ── 清空清單 ──────────────────────────────────────────────────────────────────
clearBtn.addEventListener("click", () => {
  if (converting) return;
  pendingFiles = [];
  jobId = null;
  progressArea.classList.add("hidden");
  logSection.classList.add("hidden");
  logBox.textContent = "";
  renderList();
});

// ── 開始轉換 ──────────────────────────────────────────────────────────────────
convertBtn.addEventListener("click", async () => {
  if (converting || pendingFiles.length === 0) return;
  converting = true;
  convertBtn.disabled = true;
  convertBtn.innerHTML = `<svg class="animate-spin h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24">
    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
  </svg> 轉換中…`;

  logSection.classList.remove("hidden");
  logBox.textContent = "";
  progressArea.classList.remove("hidden");
  progressBar.style.width = "0%";
  progressLabel.textContent = "上傳中…";
  progressPct.textContent = "0%";

  try {
    // ① 上傳
    const form = new FormData();
    const fileObjs = await gatherFileObjects();
    fileObjs.forEach(f => form.append("files", f));
    const upRes  = await fetch("/api/upload", { method: "POST", body: form });
    const upData = await upRes.json();
    if (!upRes.ok) throw new Error(upData.error || "上傳失敗");
    jobId = upData.job_id;
    // 對應伺服器回傳的 id
    upData.files.forEach((srv, i) => { pendingFiles[i].id = srv.id; });
    addLog("上傳完成，開始轉換…");

    // ② 開始轉換
    const trans = getTrans();
    const cvRes  = await fetch(`/api/convert/${jobId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fmt: getFmt(), translation_mode: trans }),
    });
    const cvData = await cvRes.json();
    if (!cvRes.ok) throw new Error(cvData.error || "啟動失敗");
    if (trans !== "none") addLog(`翻譯模式：${{"bilingual":"雙語對照","zh":"全繁體中文"}[trans]}`);

    // ③ SSE 進度
    await listenProgress();

  } catch (err) {
    addLog(`錯誤：${err.message}`);
    alert(`轉換失敗：${err.message}`);
  } finally {
    converting = false;
    convertBtn.disabled = false;
    convertBtn.innerHTML = "▶ 開始轉換";
  }
});

// 取得真實 File 物件（重新觸發 input）
function gatherFileObjects() {
  return new Promise(resolve => {
    // 直接用 fileInput.files 快取的 File 物件（若還在 FileList 中）
    // 實作上，pendingFiles 裡存的只是 {name,size,...}
    // 需要使用者重新選擇——這裡改為在 handleFiles 時直接保存 File reference
    resolve(_pendingFileObjs);
  });
}

let _pendingFileObjs = [];

// 覆寫 handleFiles 保存真實 File
(function () {
  const orig = handleFiles;
  window.handleFiles = function(files) {
    if (converting) return;
    const valid = files.filter(f =>
      f.name.toLowerCase().endsWith(".epub") ||
      f.name.toLowerCase().endsWith(".pdf")
    );
    if (!valid.length) { alert("請選擇 .epub 或 .pdf 檔案。"); return; }
    _pendingFileObjs = [..._pendingFileObjs, ...valid];
    pendingFiles = [...pendingFiles, ...valid.map(f => ({
      name: f.name, size: f.size,
      status: "pending", outFiles: [], error: "",
    }))];
    renderList();
  };
  // 重新綁定事件
  fileInput.removeEventListener("change", fileInput._handler);
})();

// 同時清空 _pendingFileObjs
const _origClear = clearBtn.onclick;
clearBtn.addEventListener("click", () => { _pendingFileObjs = []; });

// 重新綁定拖放與 input（使用覆寫後的 handleFiles）
dropZone.addEventListener("drop", e => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  handleFiles([...e.dataTransfer.files]);
}, true);
fileInput.addEventListener("change", () => {
  handleFiles([...fileInput.files]);
  fileInput.value = "";
}, true);

// ── SSE 進度監聽 ──────────────────────────────────────────────────────────────
function listenProgress() {
  return new Promise((resolve, reject) => {
    const es = new EventSource(`/api/progress/${jobId}`);
    es.onmessage = e => {
      const msg = JSON.parse(e.data);
      if (msg.type === "connected") return;

      if (msg.event === "log") {
        addLog(msg.data.text);
        return;
      }
      if (msg.event === "file_status") {
        const { id, status, out_files, error, pct } = msg.data;
        const idx = pendingFiles.findIndex(f => f.id === id);
        if (idx >= 0) {
          pendingFiles[idx].status   = status;
          pendingFiles[idx].outFiles = out_files || [];
          pendingFiles[idx].error    = error || "";
        }
        if (pct !== undefined) {
          progressBar.style.width = pct + "%";
          progressPct.textContent  = pct + "%";
          progressLabel.textContent = `轉換中… (${msg.data.idx+1}/${msg.data.total})`;
        }
        renderList();
        return;
      }
      if (msg.event === "done") {
        es.close();
        progressBar.style.width = "100%";
        progressPct.textContent  = "100%";
        progressLabel.textContent = "完成";
        const { ok, errors } = msg.data;
        if (errors === 0) {
          doneTitle.textContent = `✅ 全部完成！（${ok} 個檔案）`;
        } else {
          doneTitle.textContent = `⚠️ 完成，${ok} 成功 / ${errors} 失敗`;
        }
        doneModal.classList.remove("hidden");
        renderList();
        resolve();
      }
    };
    es.onerror = err => {
      es.close();
      reject(new Error("SSE 連線中斷"));
    };
  });
}
