FROM python:3.13-slim

# Calibre + WQY TrueType 字型（reportlab 相容）+ xvfb
RUN apt-get update && apt-get install -y --no-install-recommends \
        calibre \
        fonts-wqy-microhei \
        fonts-wqy-zenhei \
        xvfb \
    && rm -rf /var/lib/apt/lists/*

# Calibre 無頭執行環境
ENV DISPLAY=:99
ENV QT_QPA_PLATFORM=offscreen
ENV QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-gpu"

WORKDIR /app

COPY epub-web-translate/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY epub-web-translate/ .

RUN mkdir -p /tmp/epub_jobs

EXPOSE 8080

CMD ["gunicorn", "-w", "1", "--threads", "4", "--timeout", "600", "-b", "0.0.0.0:8080", "app:app"]
