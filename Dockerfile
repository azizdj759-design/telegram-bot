FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    gcc \
    libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# تشغيل البوت بدلاً من سيرفر الويب
CMD python bot.py
