FROM python:3.13-slim

# 安裝系統套件：Calibre + Noto CJK 字型 + 必要工具
RUN apt-get update && apt-get install -y --no-install-recommends \
        calibre \
        fonts-noto-cjk \
        xvfb \
    && rm -rf /var/lib/apt/lists/*

# 讓 Calibre 在無頭伺服器上正常運行
ENV DISPLAY=:99
ENV QT_QPA_PLATFORM=offscreen

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 建立暫存目錄
RUN mkdir -p /tmp/epub_jobs

EXPOSE 8080

CMD ["gunicorn", "-w", "2", "--timeout", "300", "-b", "0.0.0.0:8080", "app:app"]
