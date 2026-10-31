FROM python:3.10-slim

# تثبيت الاعتماديات الأساسية (مطلوبة لـ curl_cffi)
RUN apt-get update && apt-get install -y \
    gcc \
    libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# تحديث pip وتثبيت المتطلبات
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي الملفات
COPY . .

# تشغيل التطبيق
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
