FROM mcr.microsoft.com/playwright/python:v1.40.0-focal

WORKDIR /app

COPY requirements.txt .

# تحديث pip وsetuptools أولاً لتجنب مشاكل البناء
RUN pip install --upgrade pip setuptools wheel

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
