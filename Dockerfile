FROM php:8.2-apache

# تحديث وتثبيت مكتبات SQLite
RUN apt-get update && apt-get install -y \
    libsqlite3-dev \
    && docker-php-ext-install pdo pdo_sqlite

# نسخ الملفات إلى الخادم
COPY . /var/www/html/

# ضبط الصلاحيات
RUN chown -R www-data:www-data /var/www/html
