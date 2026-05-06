FROM python:3.13-slim

# 安裝系統套件：Calibre + Noto CJK 字型 + 必要工具
# xvfb 提供虛擬 X display 讓 Calibre QtWebEngine 正常運作
RUN apt-get update && apt-get install -y --no-install-recommends \
        calibre \
        fonts-noto-cjk \
        fonts-wqy-microhei \
        fonts-wqy-zenhei \
        xvfb \
    && rm -rf /var/lib/apt/lists/*

# 讓 Calibre 在無頭 Docker 容器中正常運行
# converter.py 會在執行 ebook-convert 時透過 xvfb-run 包裝
# 並在 subprocess env 中明確設定 QTWEBENGINE_CHROMIUM_FLAGS
ENV DISPLAY=:99
ENV QT_QPA_PLATFORM=offscreen
ENV QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-gpu"

WORKDIR /app

COPY epub-web/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY epub-web/ .

# 建立暫存目錄
RUN mkdir -p /tmp/epub_jobs

EXPOSE 8080

CMD ["gunicorn", "-w", "1", "--threads", "4", "--timeout", "300", "-b", "0.0.0.0:8080", "app:app"]
