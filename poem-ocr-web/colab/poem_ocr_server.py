"""
poem_ocr_server.py — 在 Google Colab（或任何有 GPU/CPU 的機器）上執行的
手寫詩句辨識服務。

設計重點：模型可彈性替換
------------------------
所有辨識模型都實作同一個 `OCRModel` 介面（load / recognize），並註冊在
`MODEL_REGISTRY` 這張表裡。要換模型完全不需要改程式碼、不需要重跑整個
Notebook —— 呼叫 `POST /switch_model` 傳入模型名稱即可，服務會在背景載入
（第一次載入該模型才會花時間下載權重，之後會快取在記憶體裡，再切換回來是
瞬間的）。要新增一個新模型，只要新增一個繼承 OCRModel 的類別並塞進
MODEL_REGISTRY，不用動其他任何程式碼。

在 Colab 執行方式，見同目錄 README.md。

路由：
  GET  /health          服務是否存活、目前使用哪個模型
  GET  /models           列出所有可用模型、目前使用中的模型、已快取的模型
  POST /switch_model     切換使用中的模型 {"name": "cnocr"}
  POST /ocr              上傳照片辨識文字（multipart file 欄位叫 file）
"""

from __future__ import annotations

import io
import time
from abc import ABC, abstractmethod
from typing import Dict, Type

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

# ── 模型介面：新增模型只需要實作這兩個方法 ──────────────────────────────

class OCRModel(ABC):
    """所有 OCR 模型的共同介面。"""

    name: str = "base"

    @abstractmethod
    def load(self) -> None:
        """載入模型權重（第一次切換到這個模型時才會呼叫一次）。"""

    @abstractmethod
    def recognize(self, image: Image.Image) -> str:
        """輸入一張 PIL 圖片，回傳辨識出來的文字。"""


class PaddleOCRModel(OCRModel):
    """PaddleOCR：中文手寫/印刷辨識效果均衡，速度快。"""

    name = "paddleocr"

    def load(self) -> None:
        from paddleocr import PaddleOCR
        self._ocr = PaddleOCR(use_angle_cls=True, lang="chinese_cht", show_log=False)

    def recognize(self, image: Image.Image) -> str:
        import numpy as np
        result = self._ocr.ocr(np.array(image), cls=True)
        if not result or not result[0]:
            return ""
        return "".join(line[1][0] for line in result[0])


class CnOCRModel(OCRModel):
    """CnOCR：輕量、安裝快，適合當預設的原型模型。"""

    name = "cnocr"

    def load(self) -> None:
        from cnocr import CnOcr
        self._ocr = CnOcr()

    def recognize(self, image: Image.Image) -> str:
        import numpy as np
        result = self._ocr.ocr(np.array(image))
        return "".join(item["text"] for item in result)


class TrOCRModel(OCRModel):
    """TrOCR（微軟）：Transformer 架構，對手寫字辨識效果通常較好，但較重。"""

    name = "trocr"

    def load(self) -> None:
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel
        self._processor = TrOCRProcessor.from_pretrained("microsoft/trocr-base-handwritten")
        self._model = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-base-handwritten")

    def recognize(self, image: Image.Image) -> str:
        pixel_values = self._processor(images=image.convert("RGB"), return_tensors="pt").pixel_values
        generated_ids = self._model.generate(pixel_values)
        return self._processor.batch_decode(generated_ids, skip_special_tokens=True)[0]


class EasyOCRModel(OCRModel):
    """EasyOCR：支援語言多，設定簡單，適合快速比較效果。"""

    name = "easyocr"

    def load(self) -> None:
        import easyocr
        self._reader = easyocr.Reader(["ch_tra", "en"], gpu=True)

    def recognize(self, image: Image.Image) -> str:
        import numpy as np
        result = self._reader.readtext(np.array(image), detail=0)
        return "".join(result)


# 要新增模型：在這裡加一行 "名稱": 類別 即可，前端設定頁會自動列出來
MODEL_REGISTRY: Dict[str, Type[OCRModel]] = {
    "cnocr": CnOCRModel,
    "paddleocr": PaddleOCRModel,
    "trocr": TrOCRModel,
    "easyocr": EasyOCRModel,
}

DEFAULT_MODEL = "cnocr"  # 預設用最輕量的模型，方便快速起服務、原型測試


# ── 模型管理：載入、快取、切換 ──────────────────────────────────────────

_loaded_models: Dict[str, OCRModel] = {}
_active_model: OCRModel | None = None
_active_name: str = ""


def switch_model(name: str) -> OCRModel:
    """切換使用中的模型。已載入過的模型直接從快取取用，切換是瞬間的；
    第一次使用某個模型才需要花時間下載/載入權重。"""
    global _active_model, _active_name

    if name not in MODEL_REGISTRY:
        available = ", ".join(MODEL_REGISTRY)
        raise ValueError(f"未知模型：{name}，可用模型：{available}")

    if name not in _loaded_models:
        model = MODEL_REGISTRY[name]()
        model.load()
        _loaded_models[name] = model

    _active_model = _loaded_models[name]
    _active_name = name
    return _active_model


# ── FastAPI 服務 ─────────────────────────────────────────────────────

app = FastAPI(title="墨評 OCR 服務", description="手寫詩句辨識，模型可彈性替換")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _on_startup() -> None:
    switch_model(DEFAULT_MODEL)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "active_model": _active_name}


@app.get("/models")
def list_models() -> dict:
    return {
        "available": list(MODEL_REGISTRY),
        "active": _active_name,
        "loaded": list(_loaded_models),
    }


@app.post("/switch_model")
def switch(body: dict) -> dict:
    name = body.get("name", "")
    t0 = time.time()
    try:
        switch_model(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "active_model": _active_name,
        "load_ms": int((time.time() - t0) * 1000),
    }


@app.post("/ocr")
async def ocr(file: UploadFile = File(...)) -> dict:
    if _active_model is None:
        raise HTTPException(status_code=503, detail="尚未載入任何模型")

    raw = await file.read()
    try:
        image = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"無法讀取圖片：{exc}") from exc

    t0 = time.time()
    text = _active_model.recognize(image)
    return {
        "text": text,
        "model": _active_name,
        "elapsed_ms": int((time.time() - t0) * 1000),
    }


def run(port: int = 8000) -> None:
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    run()
