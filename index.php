<?php
// ==========================================
// 1. طبقة الحماية بكلمة مرور (Basic Auth)
// ==========================================
$valid_username = 'admin'; // يمكنك تغيير اسم المستخدم
$valid_password = 'SuperSecretPassword123!'; // غير كلمة المرور

if (!isset($_SERVER['PHP_AUTH_USER']) || 
    ($_SERVER['PHP_AUTH_USER'] != $valid_username) || 
    ($_SERVER['PHP_AUTH_PW'] != $valid_password)) {
    
    header('WWW-Authenticate: Basic realm="Restricted Area"');
    header('HTTP/1.0 401 Unauthorized');
    echo 'يجب إدخال كلمة المرور للوصول إلى هذه الأداة.';
    exit;
}

// ==========================================
// 2. منطق جلب البيانات (Backend Logic)
// ==========================================
$result = null;
$error = null;

if ($_SERVER['REQUEST_METHOD'] === 'POST' && !empty($_POST['username'])) {
    $username = trim($_POST['username']);
    
    // ملاحظة: هذا مجرد مثال لكيفية استخدام cURL.
    // يجب عليك استبدال الرابط برابط الـ API الحقيقي أو منطق الكشط الخاص بك.
    $api_url = "https://api.example.com/tiktok/info?username=" . urlencode($username);
    
    $ch = curl_init();
    curl_setopt($ch, CURLOPT_URL, $api_url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, 10); // مهلة 10 ثواني
    
    // مهم جداً: تمويه الطلب كأنه قادم من متصفح حقيقي (لتجنب الحظر)
    curl_setopt($ch, CURLOPT_USERAGENT, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
    
    // إذا كنت تستخدم بروكسي، قم بتفعيل هذين السطرين:
    // curl_setopt($ch, CURLOPT_PROXY, 'http://your-proxy-ip:port');
    // curl_setopt($ch, CURLOPT_PROXYUSERPWD, 'user:pass');

    $response = curl_exec($ch);
    $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    if ($response === false) {
        $error = "فشل الاتصال بالخادم.";
    } else {
        // هنا تقوم بفك تشفير JSON وتحليل البيانات
        $data = json_decode($response, true);
        if ($http_code == 200 && $data) {
            $result = $data; 
        } else {
            $error = "لم يتم العثور على بيانات أو تم حظر الطلب (كود: $http_code).";
        }
    }
}
?>

<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TikTok OSINT Tool</title>
    <style>
        /* تصميم بسيط يشبه البوت في الصورة */
        body { background-color: #121212; color: #e0e0e0; font-family: sans-serif; display: flex; justify-content: center; padding-top: 50px; }
        .container { background: #1e1e1e; padding: 20px; border-radius: 10px; width: 100%; max-width: 500px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        input[type="text"] { width: 100%; padding: 10px; margin-bottom: 10px; border-radius: 5px; border: 1px solid #333; background: #2c2c2c; color: white; box-sizing: border-box; }
        button { width: 100%; padding: 10px; background: #00f2fe; color: #000; border: none; border-radius: 5px; font-weight: bold; cursor: pointer; }
        button:hover { background: #00d2de; }
        .result-box { margin-top: 20px; background: #2c2c2c; padding: 15px; border-radius: 5px; border-right: 4px solid #00f2fe; word-wrap: break-word; }
        .error { color: #ff4c4c; margin-top: 10px; }
        pre { white-space: pre-wrap; font-size: 14px; }
    </style>
</head>
<body>

<div class="container">
    <h2 style="text-align: center;">TikTok Info Fetcher</h2>
    
    <form method="POST">
        <input type="text" name="username" placeholder="أدخل اسم المستخدم (بدون @)" required>
        <button type="submit">بحث</button>
    </form>

    <?php if ($error): ?>
        <div class="error"><?= htmlspecialchars($error) ?></div>
    <?php endif; ?>

    <?php if ($result): ?>
        <div class="result-box">
            <h3>النتائج:</h3>
            <!-- هنا يمكنك تنسيق البيانات كما تشاء بدلاً من طباعة الـ JSON الخام -->
            <pre><?= htmlspecialchars(print_r($result, true)) ?></pre>
        </div>
    <?php endif; ?>
</div>

</body>
</html>
