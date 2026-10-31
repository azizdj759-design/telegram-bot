# استخدام الصورة الرسمية من Playwright التي تحتوي على المتصفحات والاعتماديات
FROM mcr.microsoft.com/playwright/python:v1.40.0-focal

WORKDIR /app

# نسخ المتطلبات وتثبيتها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي الملفات
COPY . .

# تشغيل التطبيق
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
