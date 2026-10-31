# استخدام صورة PHP 8.2 الرسمية مع Apache
FROM php:8.2-apache

# تثبيت الإضافات الضرورية
# curl: لطلب البيانات من APIs
# mbstring: لمعالجة النصوص والترميز (مهم للغة العربية)
RUN apt-get update && apt-get install -y \
    libcurl4-openssl-dev \
    libonig-dev \
    && docker-php-ext-install curl mbstring

# تفعيل mod_rewrite في Apache (مفيد إذا كنت ستستخدم مسارات لاحقاً)
RUN a2enmod rewrite

# نسخ ملفات المشروع إلى مجلد الخادم
COPY . /var/www/html/

# تغيير صلاحيات الملفات لضمان عملها
RUN chown -R www-data:www-data /var/www/html

# المنفذ الافتراضي الذي تستخدمه Render
EXPOSE 80
