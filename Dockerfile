FROM python:3.10-slim

# تثبيت الاعتماديات الأساسية للنظام
RUN apt-get update && apt-get install -y \
    gcc \
    libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# نسخ المتطلبات وتثبيتها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- الخطوة الأهم: تثبيت متصفحات Playwright والاعتماديات الخاصة بها ---
RUN playwright install-deps chromium
RUN playwright install chromium

# نسخ باقي الملفات
COPY . .

# تشغيل التطبيق
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
