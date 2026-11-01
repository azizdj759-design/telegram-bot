FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# تشغيل التطبيق الوهمي في الخلفية & تشغيل البوت في المقدمة
CMD python vulnerable_app.py & python exploit_bot.py
