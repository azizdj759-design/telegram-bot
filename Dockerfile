FROM python:3.10-slim

WORKDIR /app

# تثبيت الحزم الأساسية للنظام إذا لزم الأمر
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# نسخ وتثبيت متطلبات بايثون
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات المشروع إلى الحاوية
COPY . .

# تشغيل التطبيق باستخدام منفذ Render المخصص أو المنفذ الافتراضي
CMD uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}
