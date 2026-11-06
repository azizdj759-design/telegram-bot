FROM python:3.10-slim

WORKDIR /app

# تثبيت الحزم الأساسية
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# تشغيل التطبيق على المنفذ الذي يطلبه Render
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "10000"]
