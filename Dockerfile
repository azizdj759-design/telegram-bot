# استخدام نسخة بايثون خفيفة
FROM python:3.11-slim

# تثبيت الأدوات الأساسية التي قد تحتاجها مكتبات مثل numba و pyvsmc
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    software-properties-common \
    && rm -rf /var/lib/apt/lists/*

# تحديد مجلد العمل
WORKDIR /app

# نسخ ملف المتطلبات وتثبيتها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات المشروع
COPY . .

# كشف المنفذ الافتراضي لـ Streamlit
EXPOSE 8501

# أمر التشغيل (مهم جداً لـ Render)
# نستخدم $PORT الذي يوفره Render، وإذا لم يوجد نستخدم 8501
CMD streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0
