FROM python:3.10-slim

# تعيين مجلد العمل داخل الحاوية
WORKDIR /app

# نسخ ملف المتطلبات وتثبيت المكتبات
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات المشروع
COPY . .

# أمر تشغيل التطبيق على البورت الذي يحدده Render
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "10000"]
