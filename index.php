<?php
// إعدادات الرأس لمنع أي أخطاء في الترميز
header('Content-Type: text/html; charset=utf-8');

$result = null;
$error = null;
$username = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST' && !empty($_POST['username'])) {
    $username = trim($_POST['username']);
    // إزالة علامة @ إذا كتبها المستخدم
    $username = ltrim($username, '@');
    
    // رابط الحساب
    $url = "https://www.tiktok.com/@" . urlencode($username);
    
    $ch = curl_init();
    curl_setopt($ch, CURLOPT_URL, $url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, 15);
    
    // محاكاة متصفح حقيقي (مهم جداً لتجنب الحظر)
    $headers = [
        'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language: en-US,en;q=0.5',
        'Connection: keep-alive',
        'Upgrade-Insecure-Requests: 1'
    ];
    curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
    
    // إعدادات البروكسي (إذا كنت ستستخدمه على Render، يجب تفعيله لتجنب حظر IP)
    // curl_setopt($ch, CURLOPT_PROXY, 'http://YOUR_PROXY_IP:PORT');
    
    $html = curl_exec($ch);
    $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    if ($http_code == 200 && $html) {
        // استخراج كائن JSON المخفي في الصفحة
        if (preg_match('/<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application\/json">(.*?)<\/script>/s', $html, $matches)) {
            $json_data = json_decode($matches[1], true);
            
            // التحقق من وجود بيانات المستخدم
            if (isset($json_data['__DEFAULT_SCOPE__']['webapp.user-detail']['userInfo'])) {
                $userInfo = $json_data['__DEFAULT_SCOPE__']['webapp.user-detail']['userInfo'];
                $user = $userInfo['user'];
                $stats = $userInfo['stats'];
                
                // تجميع البيانات لتشبه مخرجات البوت في الصورة
                $result = [
                    'Username' => $user['uniqueId'] ?? 'N/A',
                    'Name' => $user['nickname'] ?? 'N/A',
                    'Region' => $user['region'] ?? 'N/A', // الدولة
                    'Private Account' => ($user['privateAccount'] ?? false) ? 'Yes ✅' : 'No ❌',
                    'Verified' => ($user['verified'] ?? false) ? 'Yes ✅' : 'No ❌',
                    'Followers' => number_format($stats['followerCount'] ?? 0),
                    'Following' => number_format($stats['followingCount'] ?? 0),
                    'Likes' => number_format($stats['heartCount'] ?? 0),
                    'Video Count' => number_format($stats['videoCount'] ?? 0),
                    'Bio' => $user['signature'] ?? '(None)',
                    'Link in Bio' => $user['bioLink']['link'] ?? '(None)',
                    // استخراج إعدادات التعليقات (إن وجدت في الـ JSON)
                    'Comment Settings' => $stats['commentSetting'] ?? 'N/A', 
                    // استخراج التاريخ (إذا توفر)
                    'Account Created' => isset($user['createTime']) ? date('Y-m-d', $user['createTime']) : 'N/A'
                ];
            } else {
                $error = "لم يتم العثور على بيانات لهذا الحساب. تأكد من اسم المستخدم.";
            }
        } else {
            $error = "تم حظر الطلب من قبل تيك توك (CAPTCHA). يرجى المحاولة لاحقاً أو استخدام بروكسي.";
        }
    } else {
        $error = "فشل في الاتصال بتيك توك. كود الخطأ: " . $http_code;
    }
}
?>

<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TikTok Advanced Info - Superior Bot</title>
    <style>
        :root { --bg: #121212; --card: #1e1e1e; --text: #e0e0e0; --accent: #00f2fe; }
        body { background-color: var(--bg); color: var(--text); font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; display: flex; justify-content: center; padding: 20px; }
        .container { background: var(--card); padding: 30px; border-radius: 12px; width: 100%; max-width: 600px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        h2 { text-align: center; color: var(--accent); margin-bottom: 25px; text-transform: uppercase; letter-spacing: 1px; }
        .input-group { display: flex; gap: 10px; margin-bottom: 20px; }
        input[type="text"] { flex: 1; padding: 12px; border-radius: 8px; border: 1px solid #333; background: #2c2c2c; color: white; font-size: 16px; outline: none; transition: 0.3s; }
        input[type="text"]:focus { border-color: var(--accent); }
        button { padding: 12px 25px; background: var(--accent); color: #000; border: none; border-radius: 8px; font-weight: bold; cursor: pointer; font-size: 16px; transition: 0.3s; }
        button:hover { background: #00d2de; transform: translateY(-2px); }
        
        /* تصميم بطاقة النتائج لتشبه البوت */
        .result-card { background: #252525; border-radius: 10px; padding: 20px; margin-top: 20px; border-left: 5px solid var(--accent); }
        .result-item { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #333; font-size: 15px; align-items: center; }
        .result-item:last-child { border-bottom: none; }
        .key { color: #aaa; font-weight: 500; }
        .value { font-weight: bold; text-align: right; word-break: break-word; max-width: 60%; }
        .bio-box { background: #1a1a1a; padding: 10px; border-radius: 5px; margin-top: 10px; font-style: italic; color: #ccc; border: 1px dashed #444; }
        .error { background: #4a1c1c; color: #ff6b6b; padding: 15px; border-radius: 8px; text-align: center; margin-top: 20px; border-left: 5px solid #ff6b6b; }
        .loading { display: none; text-align: center; margin-top: 20px; color: var(--accent); }
    </style>
</head>
<body>

<div class="container">
    <h2>TikTok Info Analyzer</h2>
    
    <form method="POST" id="searchForm">
        <div class="input-group">
            <input type="text" name="username" placeholder="Enter TikTok Username..." value="<?= htmlspecialchars($username) ?>" required>
            <button type="submit" onclick="document.querySelector('.loading').style.display='block';">Analyze</button>
        </div>
    </form>

    <div class="loading" id="loading">Fetching data from TikTok Servers...</div>

    <?php if ($error): ?>
        <div class="error"><?= htmlspecialchars($error) ?></div>
    <?php endif; ?>

    <?php if ($result): ?>
        <div class="result-card">
            <?php foreach ($result as $key => $value): ?>
                <?php if ($key == 'Bio'): ?>
                    <div class="result-item" style="flex-direction: column; align-items: flex-start;">
                        <span class="key">Bio:</span>
                        <div class="bio-box"><?= htmlspecialchars($value) ?></div>
                    </div>
                <?php else: ?>
                    <div class="result-item">
                        <span class="key"><?= htmlspecialchars($key) ?>:</span>
                        <span class="value"><?= htmlspecialchars($value) ?></span>
                    </div>
                <?php endif; ?>
            <?php endforeach; ?>
        </div>
    <?php endif; ?>
</div>

<script>
    // إخفاء رسالة التحميل عند اكتمال تحميل الصفحة
    window.onload = function() {
        document.getElementById('loading').style.display = 'none';
    };
</script>

</body>
</html>
