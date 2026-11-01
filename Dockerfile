FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# فتح المنفذين: 5000 للتطبيق المصاب، و8080 للبوت
EXPOSE 5000
EXPOSE 8080

# سكريبت التشغيل (لتشغيل التطبيق في الخلفية والبوت في المقدمة)
CMD python vulnerable_app.py & python exploit_bot.py
