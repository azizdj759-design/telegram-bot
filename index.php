<?php
/* ============================================================
   TRACKER PRO ULTIMATE — Single File
   Fixed Syntax Error & Translated to English
   ============================================================ */

// ==================== 1. CONFIGURATION ====================
define('APP_NAME', 'Tracker Pro');
define('APP_TIMEZONE', 'Africa/Algiers');
define('DB_PATH', __DIR__ . '/tracker.db');
define('DASHBOARD_PASSWORD', 'csj123');

// ✏️ TELEGRAM BOT CONFIGURATION
define('TELEGRAM_BOT_TOKEN', '8895436088:AAEP3Gynyzoh8VG5YQTnBZl4xH1vh4wMvo4'); // ⚠️ Revoke this!
define('TELEGRAM_CHAT_ID', ''); // ✏️ Put your Chat ID here

define('RATE_LIMIT_CREATE', 30);
define('RATE_LIMIT_VISIT', 300);
define('DEFAULT_OG_IMAGE', 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=600&auto=format&fit=crop&q=60');

date_default_timezone_set(APP_TIMEZONE);
ini_set('display_errors', '0');
error_reporting(E_ALL);
ini_set('log_errors', '1');
ini_set('error_log', __DIR__ . '/php-error.log');

if (session_status() === PHP_SESSION_NONE) {
    session_start(['cookie_httponly'=>true,'cookie_samesite'=>'Lax','cookie_secure'=>isset($_SERVER['HTTPS'])]);
}

// ==================== 2. DATABASE ====================
function db(): PDO {
    static $pdo = null;
    if ($pdo === null) {
        $pdo = new PDO('sqlite:' . DB_PATH);
        $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
        $pdo->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);
        $pdo->exec("PRAGMA journal_mode = WAL");
        $pdo->exec("PRAGMA synchronous = NORMAL");
        $pdo->exec("PRAGMA busy_timeout = 5000");
        migrate($pdo);
    }
    return $pdo;
}

function migrate(PDO $db): void {
    $v = (int)$db->query("PRAGMA user_version")->fetchColumn();
    if ($v >= 3) return;

    $db->exec("CREATE TABLE IF NOT EXISTS links (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, target_url TEXT, meta_title TEXT, meta_image TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)");
    $db->exec("CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, public_ip TEXT, local_ip TEXT, port TEXT, country TEXT, city TEXT, lat TEXT, lon TEXT, isp TEXT, device_info TEXT, screen_res TEXT, timezone TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)");

    $cols = [
        'links' => [
            'password_hash'=>'TEXT','expires_at'=>'DATETIME','max_clicks'=>'INTEGER DEFAULT 0',
            'click_count'=>'INTEGER DEFAULT 0','is_active'=>'INTEGER DEFAULT 1',
            'allow_countries'=>'TEXT','block_countries'=>'TEXT','ab_mode'=>'INTEGER DEFAULT 0',
            'meta_pixel'=>'TEXT','tiktok_pixel'=>'TEXT','google_tag'=>'TEXT',
        ],
        'logs' => [
            'visitor_hash'=>'TEXT','referer'=>'TEXT','language'=>'TEXT','is_bot'=>'INTEGER DEFAULT 0',
            'browser'=>'TEXT','os'=>'TEXT','device_brand'=>'TEXT','device_model'=>'TEXT',
            'gpu_vendor'=>'TEXT','gpu_renderer'=>'TEXT','canvas_hash'=>'TEXT','webgl_hash'=>'TEXT',
            'fonts_hash'=>'TEXT','audio_hash'=>'TEXT','battery'=>'TEXT','connection'=>'TEXT',
            'cores'=>'INTEGER','memory_gb'=>'INTEGER','touch'=>'INTEGER','page_load_ms'=>'INTEGER',
        ],
    ];
    foreach ($cols as $tbl => $list) foreach ($list as $c => $def) {
        try { $db->exec("ALTER TABLE $tbl ADD COLUMN $c $def"); } catch (Exception $e) {}
    }

    foreach ([
        "CREATE INDEX IF NOT EXISTS idx_links_code ON links(code)",
        "CREATE INDEX IF NOT EXISTS idx_logs_code ON logs(code)",
        "CREATE INDEX IF NOT EXISTS idx_logs_created ON logs(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_logs_visitor ON logs(visitor_hash)",
        "CREATE INDEX IF NOT EXISTS idx_logs_bot ON logs(is_bot)",
    ] as $sql) $db->exec($sql);

    $db->exec("CREATE TABLE IF NOT EXISTS api_keys (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, key_hash TEXT UNIQUE NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, last_used_at DATETIME, is_active INTEGER DEFAULT 1)");
    $db->exec("CREATE TABLE IF NOT EXISTS ab_variants (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL, variant_url TEXT NOT NULL, weight INTEGER DEFAULT 50)");
    $db->exec("CREATE TABLE IF NOT EXISTS webhooks (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, url TEXT NOT NULL, secret TEXT, events TEXT DEFAULT 'visit', is_active INTEGER DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)");
    $db->exec("CREATE TABLE IF NOT EXISTS webhook_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, webhook_id INTEGER, response_code INTEGER, success INTEGER, error TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)");
    $db->exec("CREATE TABLE IF NOT EXISTS ip_blacklist (id INTEGER PRIMARY KEY AUTOINCREMENT, ip TEXT UNIQUE NOT NULL, reason TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)");

    $db->exec("PRAGMA user_version = 3");
}

// ==================== 3. HELPERS ====================
function e(?string $s): string { return htmlspecialchars((string)$s, ENT_QUOTES|ENT_SUBSTITUTE, 'UTF-8'); }

function is_safe_url(string $url): bool {
    $p = parse_url($url);
    if (!$p || !in_array($p['scheme'] ?? '', ['http','https'], true)) return false;
    $host = $p['host'] ?? '';
    if ($host === '' || preg_match('/^(localhost|.*\.local|.*\.internal|.*\.lan)$/i', $host)) return false;
    $ips = @gethostbynamel($host) ?: [];
    if (!$ips) return false;
    foreach ($ips as $ip) if (!filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_NO_PRIV_RANGE|FILTER_FLAG_NO_RES_RANGE)) return false;
    return true;
}

function rate_limit(string $key, int $max, int $windowSec): bool {
    $f = sys_get_temp_dir() . '/rl_' . sha1($key);
    $now = time();
    $d = ['count'=>0,'start'=>$now];
    if (file_exists($f)) { $r=@file_get_contents($f); $x=$r?json_decode($r,true):null; if (is_array($x)) $d=$x; }
    if ($now - $d['start'] > $windowSec) $d = ['count'=>0,'start'=>$now];
    $d['count']++;
    @file_put_contents($f, json_encode($d), LOCK_EX);
    return $d['count'] <= $max;
}

function get_real_ip(): string {
    $trusted = [];
    $r = $_SERVER['REMOTE_ADDR'] ?? '0.0.0.0';
    if (in_array($r, $trusted, true) && !empty($_SERVER['HTTP_X_FORWARDED_FOR']))
        return trim(explode(',', $_SERVER['HTTP_X_FORWARDED_FOR'])[0]);
    return $r;
}

function is_ip_blacklisted(string $ip): bool {
    $s = db()->prepare("SELECT 1 FROM ip_blacklist WHERE ip = ?");
    $s->execute([$ip]);
    return (bool)$s->fetch();
}

function generate_code(int $len = 7): string {
    $chars = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789';
    do {
        $code = '';
        for ($i = 0; $i < $len; $i++) $code .= $chars[random_int(0, strlen($chars)-1)];
    } while (db()->query("SELECT 1 FROM links WHERE code = " . db()->quote($code))->fetch());
    return $code;
}

function is_bot_ua(string $ua): bool {
    if ($ua === '' || $ua === 'Unknown') return true;
    $pats = ['bot','crawl','spider','slurp','facebookexternalhit','whatsapp','telegrambot','preview','skype','linkedinbot','twitterbot','pinterest','discordbot','headless','phantom','puppeteer','playwright','selenium','python-requests','curl','wget','go-http','java/','okhttp'];
    foreach ($pats as $p) if (stripos($ua, $p) !== false) return true;
    return false;
}

function parse_ua(string $ua): array {
    $b='Unknown'; $o='Unknown'; $br='Unknown'; $m=null;
    if (preg_match('/Edg\//',$ua)) $b='Edge';
    elseif (preg_match('/OPR\//',$ua)) $b='Opera';
    elseif (preg_match('/Chrome\//',$ua)) $b='Chrome';
    elseif (preg_match('/Firefox\//',$ua)) $b='Firefox';
    elseif (preg_match('/Safari\//',$ua)) $b='Safari';
    if (stripos($ua,'Windows NT 10')!==false) $o='Windows 10/11';
    elseif (stripos($ua,'Windows')!==false) $o='Windows';
    elseif (stripos($ua,'Android')!==false) $o='Android';
    elseif (stripos($ua,'iPhone')!==false) $o='iOS';
    elseif (stripos($ua,'iPad')!==false) $o='iPadOS';
    elseif (stripos($ua,'Mac OS X')!==false) $o='macOS';
    elseif (stripos($ua,'Linux')!==false) $o='Linux';
    foreach (['Samsung'=>'Samsung','Huawei'=>'Huawei','Xiaomi'=>'Xiaomi','Redmi'=>'Xiaomi','Oppo'=>'Oppo','Vivo'=>'Vivo','OnePlus'=>'OnePlus','Pixel'=>'Google','iPhone'=>'Apple'] as $n=>$name)
        if (stripos($ua,$n)!==false) { $br=$name; break; }
    if ($br==='Unknown' && stripos($ua,'Android')!==false) $br='Android';
    if (preg_match('/;\s*([^;)]+?)\s+Build\//', $ua, $mm)) $m = trim($mm[1]);
    return ['browser'=>$b,'os'=>$o,'brand'=>$br,'model'=>$m];
}

function parse_isp(string $isp, string $org): string {
    $c = "$isp $org";
    if (stripos($c,'Mobilis')!==false) return 'Mobilis';
    if (stripos($c,'Djezzy')!==false || stripos($c,'Optimum')!==false) return 'Djezzy';
    if (stripos($c,'Ooredoo')!==false || stripos($c,'Wataniya')!==false) return 'Ooredoo';
    if (preg_match('/Alg[ée]rie T[ée]l[ée]com|AlgerieTelecom/i', $c)) return 'Algérie Télécom';
    return trim($isp) ?: 'Unknown';
}

function get_ip_details(string $ip): array {
    $fb = ['country'=>'Unknown','city'=>'Unknown','lat'=>'36.7538','lon'=>'3.0588','isp'=>'Unknown'];
    if (in_array($ip, ['127.0.0.1','::1','0.0.0.0'], true))
        return ['country'=>'Algeria (Local)','city'=>'Local','lat'=>'36.7538','lon'=>'3.0588','isp'=>'Localhost'];
    if (filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_NO_PRIV_RANGE|FILTER_FLAG_NO_RES_RANGE) === false) return $fb;

    $cd = sys_get_temp_dir() . '/geocache';
    if (!is_dir($cd)) @mkdir($cd, 0700, true);
    $cf = $cd . '/' . sha1($ip) . '.json';
    if (file_exists($cf) && time() - filemtime($cf) < 86400) {
        $c = json_decode(file_get_contents($cf), true);
        if (is_array($c)) return $c;
    }

    $ctx = stream_context_create(['http'=>['timeout'=>2,'user_agent'=>'TrackerPro/1.0']]);
    $json = @file_get_contents("http://ip-api.com/json/{$ip}?fields=status,country,city,lat,lon,isp,org", false, $ctx);
    $d = $json ? json_decode($json, true) : null;
    if (is_array($d) && ($d['status']??'')==='success') {
        $r = ['country'=>$d['country']??'Unknown','city'=>$d['city']??'Unknown','lat'=>(string)($d['lat']??'36.7538'),'lon'=>(string)($d['lon']??'3.0588'),'isp'=>parse_isp($d['isp']??'',$d['org']??'')];
        @file_put_contents($cf, json_encode($r), LOCK_EX);
        return $r;
    }
    return $fb;
}

function fetch_real_meta(string $url): array {
    if (!is_safe_url($url)) return ['title'=>parse_url($url, PHP_URL_HOST)?:'Link','image'=>DEFAULT_OG_IMAGE];
    $title = ''; $image = '';
    if (preg_match('/(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})/', $url, $m)) {
        $image = "https://img.youtube.com/vi/{$m[1]}/hqdefault.jpg";
        $ch = curl_init("https://www.youtube.com/oembed?url=" . urlencode($url) . "&format=json");
        curl_setopt_array($ch, [CURLOPT_RETURNTRANSFER=>true, CURLOPT_TIMEOUT=>3]);
        $j = curl_exec($ch); curl_close($ch);
        if ($j) { $d = json_decode($j, true); if (!empty($d['title'])) $title = $d['title']; }
    }
    if (empty($title)) {
        $ch = curl_init($url);
        curl_setopt_array($ch, [CURLOPT_RETURNTRANSFER=>true,CURLOPT_FOLLOWLOCATION=>true,CURLOPT_MAXREDIRS=>3,CURLOPT_TIMEOUT=>4,CURLOPT_USERAGENT=>'Mozilla/5.0 (compatible; TrackerPro/1.0)']);
        $html = curl_exec($ch); curl_close($ch);
        if ($html && strlen($html) < 3_000_000) {
            $dom = new DOMDocument();
            @$dom->loadHTML(mb_convert_encoding($html, 'HTML-ENTITIES', 'UTF-8'), LIBXML_NOWARNING|LIBXML_NOERROR);
            $xp = new DOMXPath($dom);
            $q = $xp->query('//meta[@property="og:title"]/@content | //meta[@name="twitter:title"]/@content');
            if ($q->length) $title = $q->item(0)->nodeValue;
            else { $t = $dom->getElementsByTagName('title'); if ($t->length) $title = $t->item(0)->nodeValue; }
            if (empty($image)) {
                $q = $xp->query('//meta[@property="og:image"]/@content | //meta[@name="twitter:image"]/@content');
                if ($q->length) {
                    $img = $q->item(0)->nodeValue;
                    if ($img && strpos($img, 'http') !== 0) {
                        $p = parse_url($url);
                        $img = ($p['scheme']??'https') . '://' . ($p['host']??'') . '/' . ltrim($img, '/');
                    }
                    $image = $img;
                }
            }
        }
    }
    if (empty($title)) $title = parse_url($url, PHP_URL_HOST)?:'Link';
    if (empty($image)) $image = DEFAULT_OG_IMAGE;
    return ['title'=>mb_substr(trim($title),0,200),'image'=>trim($image)];
}

function notify_telegram(array $link, string $ip, array $geo, array $ua): void {
    if (!TELEGRAM_BOT_TOKEN || !TELEGRAM_CHAT_ID) return;
    $flag = match($geo['country']) {
        'Algeria'=>'🇩🇿','France'=>'🇫🇷','Tunisia'=>'🇹🇳','Morocco'=>'🇲🇦',
        'Egypt'=>'🇪🇬','Saudi Arabia'=>'🇸🇦','United States'=>'🇺🇸',
        'United Kingdom'=>'🇬🇧','Germany'=>'🇩🇪','Turkey'=>'🇹🇷',default=>'🌍'
    };
    $text = "🔔 <b>New Visit</b>\n\n📎 <code>".e($link['code'])."</code>\n{$flag} {$geo['country']} / {$geo['city']}\n🌐 <code>{$ip}</code>\n📡 {$geo['isp']}\n📱 {$ua['brand']} - {$ua['os']}\n🌐 {$ua['browser']}";
    $url = "https://api.telegram.org/bot" . TELEGRAM_BOT_TOKEN . "/sendMessage";
    $ctx = stream_context_create(['http'=>['method'=>'POST','header'=>"Content-Type: application/x-www-form-urlencoded\r\n",'content'=>http_build_query(['chat_id'=>TELEGRAM_CHAT_ID,'text'=>$text,'parse_mode'=>'HTML','disable_web_page_preview'=>'true']),'timeout'=>3]]);
    @file_get_contents($url, false, $ctx);
}

function fire_webhooks(array $link, array $payload): void {
    $db = db();
    $s = $db->prepare("SELECT * FROM webhooks WHERE (code = ? OR code IS NULL OR code = '') AND is_active = 1");
    $s->execute([$link['code']]);
    foreach ($s as $wh) {
        if (!is_safe_url($wh['url'])) continue;
        $body = json_encode(['event'=>'visit','code'=>$link['code'],'ts'=>time(),'data'=>$payload]);
        $secret = $wh['secret'] ?: 'default';
        $sig = 'sha256=' . hash_hmac('sha256', $body, $secret);
        $ctx = stream_context_create(['http'=>['method'=>'POST','header'=>"Content-Type: application/json\r\nX-Signature: {$sig}\r\n",'content'=>$body,'timeout'=>3,'ignore_errors'=>true]]);
        $resp = @file_get_contents($wh['url'], false, $ctx);
        $code = 0;
        if (!empty($http_response_header[0]) && preg_match('/\s(\d{3})\s/', $http_response_header[0], $mm)) $code = (int)$mm[1];
        $db->prepare("INSERT INTO webhook_logs (webhook_id, response_code, success, error, created_at) VALUES (?,?,?,?,?)")
           ->execute([$wh['id'], $code, $resp!==false && $code<400 ? 1 : 0, $resp===false?'failed':'', date('Y-m-d H:i:s')]);
    }
}

// ==================== 4. ROUTER ====================
$action = $_GET['action'] ?? '';

// ---------- 4.a SSE ----------
if ($action === 'sse') {
    if (empty($_SESSION['auth'])) { http_response_code(401); exit; }
    header('Content-Type: text/event-stream'); header('Cache-Control: no-cache'); header('X-Accel-Buffering: no');
    while (ob_get_level() > 0) ob_end_flush();
    @ini_set('output_buffering', '0');
    $db = db();
    $lastId = (int)($_GET['last_id'] ?? $db->query("SELECT COALESCE(MAX(id),0) FROM logs")->fetchColumn());
    $end = time() + 300;
    while (time() < $end && !connection_aborted()) {
        $s = $db->prepare("SELECT id,code,public_ip,country,city,isp,device_info,screen_res,is_bot,browser,os,created_at FROM logs WHERE id > ? ORDER BY id ASC LIMIT 20");
        $s->execute([$lastId]);
        foreach ($s as $r) {
            $lastId = (int)$r['id'];
            echo "id: {$r['id']}\nevent: visit\ndata: " . json_encode($r) . "\n\n";
        }
        echo ": hb " . time() . "\n\n";
        @ob_flush(); @flush(); sleep(2);
    }
    exit;
}

// ---------- 4.b API ----------
if ($action === 'api') {
    header('Content-Type: application/json; charset=utf-8');
    if (empty($_SESSION['auth'])) {
        $auth = $_SERVER['HTTP_AUTHORIZATION'] ?? '';
        $key = str_starts_with($auth, 'Bearer ') ? substr($auth, 7) : '';
        $r = db()->prepare("SELECT id FROM api_keys WHERE key_hash = ? AND is_active = 1");
        $r->execute([hash('sha256', $key)]);
        if (!$r->fetch()) { http_response_code(401); die(json_encode(['error'=>'unauthorized'])); }
    }
    try {
        $db = db(); $op = $_GET['op'] ?? '';
        if ($op === 'create' && $_SERVER['REQUEST_METHOD'] === 'POST') {
            if (!rate_limit('api:create:' . get_real_ip(), RATE_LIMIT_CREATE, 3600)) { http_response_code(429); die(json_encode(['error'=>'rate_limit'])); }
            $b = json_decode(file_get_contents('php://input'), true) ?: $_POST;
            $url = trim($b['url'] ?? '');
            if (!filter_var($url, FILTER_VALIDATE_URL)) $url = 'https://' . $url;
            if (!is_safe_url($url)) { http_response_code(400); die(json_encode(['error'=>'unsafe_url'])); }
            $meta = fetch_real_meta($url); $code = generate_code();
            $s = $db->prepare("INSERT INTO links (code,target_url,meta_title,meta_image,password_hash,expires_at,max_clicks) VALUES (?,?,?,?,?,?,?)");
            $s->execute([$code, $url, $meta['title'], $meta['image'], !empty($b['password'])?password_hash($b['password'], PASSWORD_DEFAULT):null, $b['expires_at']??null, (int)($b['max_clicks']??0)]);
            die(json_encode(['ok'=>true,'code'=>$code,'title'=>$meta['title']]));
        }
        if ($op === 'stats') {
            $code = $_GET['code'] ?? '';
            $s = $db->prepare("SELECT * FROM links WHERE code = ?"); $s->execute([$code]);
            if (!$l = $s->fetch()) { http_response_code(404); die(json_encode(['error'=>'not_found'])); }
            $t = $db->prepare("SELECT COUNT(*) FROM logs WHERE code = ? AND is_bot = 0"); $t->execute([$code]);
            $u = $db->prepare("SELECT COUNT(DISTINCT visitor_hash) FROM logs WHERE code = ? AND is_bot = 0"); $u->execute([$code]);
            die(json_encode(['link'=>$l,'total'=>(int)$t->fetchColumn(),'unique'=>(int)$u->fetchColumn()]));
        }
        if ($op === 'list') die(json_encode(['links'=>$db->query("SELECT * FROM links ORDER BY id DESC LIMIT 100")->fetchAll()]));
        die(json_encode(['error'=>'unknown_op']));
    } catch (Exception $ex) { error_log('api: ' . $ex->getMessage()); http_response_code(500); die(json_encode(['error'=>'server_error'])); }
}

// ---------- 4.c stats_json ----------
if ($action === 'stats_json') {
    if (empty($_SESSION['auth'])) { http_response_code(401); exit; }
    header('Content-Type: application/json; charset=utf-8');
    $db = db();
    echo json_encode([
        'by_country' => $db->query("SELECT country, COUNT(*) c FROM logs WHERE is_bot = 0 GROUP BY country ORDER BY c DESC LIMIT 10")->fetchAll(),
        'by_device'  => $db->query("SELECT device_info, COUNT(*) c FROM logs WHERE is_bot = 0 GROUP BY device_info ORDER BY c DESC LIMIT 6")->fetchAll(),
        'by_hour'    => $db->query("SELECT strftime('%H', created_at) h, COUNT(*) c FROM logs WHERE is_bot = 0 AND created_at >= datetime('now','-1 day') GROUP BY h ORDER BY h")->fetchAll(),
        'map_points' => $db->query("SELECT lat, lon, city, country, COUNT(*) c FROM logs WHERE is_bot = 0 AND lat NOT IN ('','0') AND lon NOT IN ('','0') GROUP BY city ORDER BY c DESC LIMIT 200")->fetchAll(),
        'heatmap'    => $db->query("SELECT date(created_at) d, strftime('%H', created_at) h, COUNT(*) c FROM logs WHERE is_bot = 0 AND created_at >= datetime('now','-7 day') GROUP BY d,h")->fetchAll(),
        'total' => (int)$db->query("SELECT COUNT(*) FROM logs WHERE is_bot = 0")->fetchColumn(),
        'unique'=> (int)$db->query("SELECT COUNT(DISTINCT visitor_hash) FROM logs WHERE is_bot = 0")->fetchColumn(),
        'bots'  => (int)$db->query("SELECT COUNT(*) FROM logs WHERE is_bot = 1")->fetchColumn(),
    ]);
    exit;
}

// ---------- 4.d CSV Export ----------
if ($action === 'export_csv') {
    if (empty($_SESSION['auth'])) { http_response_code(401); exit; }
    $code = $_GET['code'] ?? '';
    $db = db();
    $sql = "SELECT * FROM logs WHERE is_bot = 0";
    $params = [];
    if ($code) { $sql .= " AND code = ?"; $params[] = $code; }
    $sql .= " ORDER BY id DESC LIMIT 5000";
    $s = $db->prepare($sql); $s->execute($params);
    $fname = 'tracker_' . ($code ?: 'all') . '_' . date('Ymd_His') . '.csv';
    header('Content-Type: text/csv; charset=utf-8');
    header("Content-Disposition: attachment; filename=\"$fname\"");
    $out = fopen('php://output', 'w');
    fwrite($out, "\xEF\xBB\xBF"); // BOM for Excel
    $first = true;
    foreach ($s as $row) {
        if ($first) { fputcsv($out, array_keys($row)); $first = false; }
        fputcsv($out, array_values($row));
    }
    fclose($out); exit;
}

// ---------- 4.e Public stats page ----------
if ($action === 'public_stats') {
    $code = $_GET['code'] ?? '';
    $db = db();
    $s = $db->prepare("SELECT * FROM links WHERE code = ?"); $s->execute([$code]);
    $link = $s->fetch();
    if (!$link) { http_response_code(404); die('Not found'); }
    $tot = $db->prepare("SELECT COUNT(*) FROM logs WHERE code = ? AND is_bot = 0"); $tot->execute([$code]);
    $uni = $db->prepare("SELECT COUNT(DISTINCT visitor_hash) FROM logs WHERE code = ? AND is_bot = 0"); $uni->execute([$code]);
    $cnt = $db->prepare("SELECT country, COUNT(*) c FROM logs WHERE code = ? AND is_bot = 0 GROUP BY country ORDER BY c DESC LIMIT 10"); $cnt->execute([$code]);
    $dev = $db->prepare("SELECT browser, COUNT(*) c FROM logs WHERE code = ? AND is_bot = 0 GROUP BY browser ORDER BY c DESC LIMIT 6"); $dev->execute([$code]);
    $total = (int)$tot->fetchColumn(); $unique = (int)$uni->fetchColumn();
    $countries = $cnt->fetchAll(); $browsers = $dev->fetchAll();
    ?><!DOCTYPE html><html lang="en" dir="ltr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Stats for <?= e($link['meta_title']) ?></title>
    <style>body{margin:0;padding:20px;font-family:sans-serif;background:#0b0f17;color:#e2e8f0}
    .box{max-width:700px;margin:0 auto;background:#131b2e;border:1px solid #1e293b;border-radius:12px;padding:25px}
    h1{font-size:18px;margin:0 0 5px}.sub{color:#64748b;font-size:12px;margin-bottom:20px}
    .stats{display:grid;grid-template-columns:1fr 1fr;gap:15px;margin-bottom:20px}
    .stat{background:#0f172a;padding:15px;border-radius:8px;text-align:center}
    .stat .l{font-size:11px;color:#64748b;text-transform:uppercase}.stat .v{font-size:28px;font-weight:bold;margin-top:5px}
    .bar{background:#0f172a;border-radius:4px;height:8px;margin:6px 0 14px;overflow:hidden}
    .bar>div{height:100%;background:#3b82f6;border-radius:4px}
    .row{display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px}</style></head>
    <body><div class="box">
    <h1><?= e($link['meta_title']) ?></h1>
    <div class="sub">Live Stats — <a href="<?= e($link['target_url']) ?>" style="color:#38bdf8" target="_blank">Visit Link</a></div>
    <div class="stats">
        <div class="stat"><div class="l">Total Visits</div><div class="v" style="color:#3b82f6"><?= $total ?></div></div>
        <div class="stat"><div class="l">Unique Visitors</div><div class="v" style="color:#10b981"><?= $unique ?></div></div>
    </div>
    <?php if ($countries): $mx = max(array_column($countries, 'c')); ?>
    <h3 style="font-size:13px;color:#94a3b8">Top Countries</h3>
    <?php foreach ($countries as $c): ?>
        <div class="row"><span><?= e($c['country']) ?></span><span><?= $c['c'] ?></span></div>
        <div class="bar"><div style="width:<?= round($c['c']/$mx*100) ?>%"></div></div>
    <?php endforeach; endif; ?>
    <?php if ($browsers): $mx = max(array_column($browsers, 'c')); ?>
    <h3 style="font-size:13px;color:#94a3b8">Browsers</h3>
    <?php foreach ($browsers as $b): ?>
        <div class="row"><span><?= e($b['browser'] ?: 'Unknown') ?></span><span><?= $b['c'] ?></span></div>
        <div class="bar"><div style="width:<?= round($b['c']/$mx*100) ?>%;background:#10b981"></div></div>
    <?php endforeach; endif; ?>
    </div></body></html><?php
    exit;
}

// ---------- 4.f Link Actions ----------
if ($action === 'link_action' && $_SERVER['REQUEST_METHOD'] === 'POST' && !empty($_SESSION['auth'])) {
    header('Content-Type: application/json');
    $db = db(); $op = $_POST['op'] ?? ''; $code = $_POST['code'] ?? '';
    if (!$code) die(json_encode(['error'=>'no_code']));
    try {
        if ($op === 'delete') {
            $db->prepare("DELETE FROM links WHERE code = ?")->execute([$code]);
            $db->prepare("DELETE FROM ab_variants WHERE code = ?")->execute([$code]);
            die(json_encode(['ok'=>true]));
        }
        if ($op === 'toggle') {
            $db->prepare("UPDATE links SET is_active = 1 - is_active WHERE code = ?")->execute([$code]);
            $s = $db->prepare("SELECT is_active FROM links WHERE code = ?"); $s->execute([$code]);
            die(json_encode(['ok'=>true,'active'=>(int)$s->fetchColumn()]));
        }
        if ($op === 'reset_count') {
            $db->prepare("UPDATE links SET click_count = 0 WHERE code = ?")->execute([$code]);
            die(json_encode(['ok'=>true]));
        }
        die(json_encode(['error'=>'unknown_op']));
    } catch (Exception $ex) { die(json_encode(['error'=>$ex->getMessage()])); }
}

// ---------- 4.g Webhook test ----------
if ($action === 'webhook_add' && $_SERVER['REQUEST_METHOD'] === 'POST' && !empty($_SESSION['auth'])) {
    header('Content-Type: application/json');
    $code = trim($_POST['code'] ?? '');
    $url = trim($_POST['url'] ?? '');
    $secret = trim($_POST['secret'] ?? '');
    if (!is_safe_url($url)) die(json_encode(['error'=>'unsafe_url']));
    db()->prepare("INSERT INTO webhooks (code, url, secret, events) VALUES (?,?,?,'visit')")->execute([$code ?: null, $url, $secret]);
    die(json_encode(['ok'=>true,'id'=>db()->lastInsertId()]));
}

if ($action === 'webhook_delete' && $_SERVER['REQUEST_METHOD'] === 'POST' && !empty($_SESSION['auth'])) {
    header('Content-Type: application/json');
    db()->prepare("DELETE FROM webhooks WHERE id = ?")->execute([(int)($_POST['id']??0)]);
    die(json_encode(['ok'=>true]));
}

// ---------- 4.h IP blacklist ----------
if ($action === 'blacklist_add' && $_SERVER['REQUEST_METHOD'] === 'POST' && !empty($_SESSION['auth'])) {
    header('Content-Type: application/json');
    $ip = trim($_POST['ip'] ?? ''); $reason = trim($_POST['reason'] ?? '');
    if (!filter_var($ip, FILTER_VALIDATE_IP)) die(json_encode(['error'=>'invalid_ip']));
    try { db()->prepare("INSERT INTO ip_blacklist (ip, reason) VALUES (?,?)")->execute([$ip, $reason]); }
    catch (Exception $e) { die(json_encode(['error'=>'duplicate'])); }
    die(json_encode(['ok'=>true]));
}

if ($action === 'blacklist_remove' && $_SERVER['REQUEST_METHOD'] === 'POST' && !empty($_SESSION['auth'])) {
    header('Content-Type: application/json');
    db()->prepare("DELETE FROM ip_blacklist WHERE id = ?")->execute([(int)($_POST['id']??0)]);
    die(json_encode(['ok'=>true]));
}

// ---------- 4.i Bulk create ----------
if ($action === 'bulk_create' && $_SERVER['REQUEST_METHOD'] === 'POST' && !empty($_SESSION['auth'])) {
    header('Content-Type: application/json');
    $urls = array_filter(array_map('trim', explode("\n", $_POST['urls'] ?? '')));
    if (count($urls) > 50) die(json_encode(['error'=>'too_many']));
    $db = db(); $results = [];
    foreach ($urls as $u) {
        if (!filter_var($u, FILTER_VALIDATE_URL)) $u = 'https://' . $u;
        if (!is_safe_url($u)) { $results[] = ['url'=>$u,'error'=>'unsafe']; continue; }
        $meta = fetch_real_meta($u); $code = generate_code();
        $db->prepare("INSERT INTO links (code,target_url,meta_title,meta_image) VALUES (?,?,?,?)")->execute([$code, $u, $meta['title'], $meta['image']]);
        $results[] = ['url'=>$u,'code'=>$code,'title'=>$meta['title']];
    }
    die(json_encode(['ok'=>true,'results'=>$results]));
}

// ---------- 4.j Redirect / Fingerprint ----------
if (isset($_GET['r'])) {
    $code = $_GET['r'];
    if (!preg_match('/^[a-zA-Z0-9]{4,16}$/', $code)) { http_response_code(404); exit('Not found'); }
    $db = db();
    $s = $db->prepare("SELECT * FROM links WHERE code = ?"); $s->execute([$code]);
    $link = $s->fetch();
    if (!$link) { http_response_code(404); exit('Link not found'); }
    if ((int)($link['is_active'] ?? 1) === 0) { http_response_code(410); exit('Disabled'); }
    if (!empty($link['expires_at']) && strtotime($link['expires_at']) < time()) { http_response_code(410); exit('Expired'); }
    if ((int)$link['max_clicks'] > 0 && (int)$link['click_count'] >= (int)$link['max_clicks']) { http_response_code(410); exit('Limit reached'); }
    $ip = get_real_ip();
    if (is_ip_blacklisted($ip)) { http_response_code(403); exit('Access denied'); }

    // Password Gate
    if (!empty($link['password_hash']) && empty($_SESSION['unlocked_' . $code])) {
        $err = '';
        if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['password'])) {
            if (password_verify($_POST['password'], $link['password_hash'])) { $_SESSION['unlocked_' . $code] = true; header("Location: ?r={$code}"); exit; }
            $err = 'Incorrect password';
        }
        ?><!DOCTYPE html><html lang="en" dir="ltr"><head><meta charset="UTF-8"><title>Protected</title><style>body{margin:0;height:100vh;display:flex;justify-content:center;align-items:center;background:#0b0f17;color:#e2e8f0;font-family:sans-serif}.box{background:#131b2e;padding:30px;border-radius:12px;border:1px solid #1e293b;width:340px;text-align:center}h3{margin:0 0 20px;font-size:16px}input{width:100%;padding:12px;background:#0f172a;border:1px solid #1e293b;border-radius:6px;color:#fff;box-sizing:border-box;margin-bottom:12px}button{width:100%;padding:12px;background:#3b82f6;color:#fff;border:none;border-radius:6px;font-weight:600;cursor:pointer}.err{color:#ef4444;font-size:13px;margin-bottom:10px}</style></head><body><form class="box" method="POST"><h3>🔒 Protected Link</h3><?php if ($err): ?><div class="err"><?= e($err) ?></div><?php endif; ?><input type="password" name="password" placeholder="Enter password" required autofocus><button>Enter</button></form></body></html><?php
        exit;
    }

    // A/B Variant
    $target = $link['target_url'];
    if ((int)($link['ab_mode'] ?? 0) === 1) {
        $vs = $db->prepare("SELECT variant_url, weight FROM ab_variants WHERE code = ?"); $vs->execute([$code]);
        $vv = $vs->fetchAll();
        if ($vv) {
            $tot = array_sum(array_column($vv, 'weight')) ?: 100;
            $pick = random_int(1, $tot); $acc = 0;
            foreach ($vv as $v) { $acc += (int)$v['weight']; if ($pick <= $acc) { $target = $v['variant_url']; break; } }
        }
    }

    $geo = get_ip_details($ip);
    $allow = array_filter(array_map('trim', explode(',', $link['allow_countries'] ?? '')));
    $block = array_filter(array_map('trim', explode(',', $link['block_countries'] ?? '')));
    if ($allow && !in_array($geo['country'], $allow, true)) { http_response_code(403); exit('Not available in your region'); }
    if ($block && in_array($geo['country'], $block, true)) { http_response_code(403); exit('Not available in your region'); }

    if ($_SERVER['REQUEST_METHOD'] === 'POST' && ($_POST['log_visit'] ?? '') === '1') {
        header('Content-Type: application/json');
        if (!rate_limit('visit:' . $ip, RATE_LIMIT_VISIT, 60)) { echo json_encode(['ok'=>false,'error'=>'rate']); exit; }
        $ua = $_SERVER['HTTP_USER_AGENT'] ?? '';
        $isBot = is_bot_ua($ua) ? 1 : 0;
        $p = parse_ua($ua);
        $fp = array_slice((array)($_POST['fp'] ?? []), 0, 40, true);
        $vh = hash('sha256', ($fp['canvas']??'') . ($fp['webgl']??'') . $ip . $ua . ($fp['tz']??''));
        try {
            $ins = $db->prepare("INSERT INTO logs (code,public_ip,local_ip,port,country,city,lat,lon,isp,device_info,screen_res,timezone,referer,language,is_bot,browser,os,device_brand,device_model,gpu_vendor,gpu_renderer,canvas_hash,webgl_hash,fonts_hash,audio_hash,battery,connection,cores,memory_gb,touch,page_load_ms,visitor_hash,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)");
            $ins->execute([
                $code, $ip, $fp['local_ip']??'', $_SERVER['REMOTE_PORT']??'',
                $geo['country'], $geo['city'], $geo['lat'], $geo['lon'], $geo['isp'],
                $p['brand'].' - '.$p['os'], $fp['screen']??'', $fp['tz']??'',
                substr($_SERVER['HTTP_REFERER']??'',0,500), $fp['lang']??'',
                $isBot, $p['browser'], $p['os'], $p['brand'], $p['model']??'',
                $fp['gpu_vendor']??'', $fp['gpu_renderer']??'',
                $fp['canvas']??'', $fp['webgl']??'', $fp['fonts']??'', $fp['audio']??'',
                $fp['battery']??'', $fp['connection']??'',
                (int)($fp['cores']??0), (int)($fp['memory']??0), (int)($fp['touch']??0),
                (int)($fp['page_load_ms']??0), $vh, date('Y-m-d H:i:s'),
            ]);
            $db->prepare("UPDATE links SET click_count = click_count + 1 WHERE code = ?")->execute([$code]);
            if (!$isBot) { notify_telegram($link, $ip, $geo, $p); fire_webhooks($link, ['ip'=>$ip,'geo'=>$geo,'ua'=>$p,'fp'=>$fp]); }
            echo json_encode(['ok'=>true]);
        } catch (Exception $ex) { error_log('log: ' . $ex->getMessage()); echo json_encode(['ok'=>false]); }
        exit;
    }

    $og_title = $link['meta_title'] ?: 'Redirecting...';
    $og_image = $link['meta_image'] ?: DEFAULT_OG_IMAGE;

    // Retargeting Pixels
    $pixels = '';
    if (!empty($link['meta_pixel'])) $pixels .= "!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}(window,document,'script','https://connect.facebook.net/en_US/fbevents.js');fbq('init','".e($link['meta_pixel'])."');fbq('track','PageView');";
    if (!empty($link['tiktok_pixel'])) $pixels .= "!function(w,d,t){w.TiktokAnalyticsObject=t;var ttq=w[t]=w[t]||[];ttq.methods=['page','track','identify','instances','debug','on','off','once','ready','alias','group','enableCookie','disableCookie'];ttq.setAndDefer=function(t,e){t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}};for(var i=0;i<ttq.methods.length;i++)ttq.setAndDefer(ttq,ttq.methods[i]);ttq.load=function(e,n){var r='https://analytics.tiktok.com/i18n/pixel/events.js';ttq._i=ttq._i||{};ttq._i[e]=[];ttq._i[e]._u=r;ttq._t=ttq._t||{};ttq._t[e]=+new Date;ttq._o=ttq._o||{};ttq._o[e]=n||{};var o=document.createElement('script');o.type='text/javascript';o.async=!0;o.src=r+'?sdkid='+e+'&lib='+t;var a=document.getElementsByTagName('script')[0];a.parentNode.insertBefore(o,a)};ttq.load('".e($link['tiktok_pixel'])."');ttq.page()}(window,document,'ttq');";
    if (!empty($link['google_tag'])) $pixels .= "(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src='https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);})(window,document,'script','dataLayer','".e($link['google_tag'])."');";
    ?><!DOCTYPE html><html lang="en" dir="ltr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title><?= e($og_title) ?></title><meta property="og:title" content="<?= e($og_title) ?>"><meta property="og:image" content="<?= e($og_image) ?>"><meta property="og:type" content="website"><style>body{margin:0;background:#000;color:#fff;font-family:sans-serif;height:100vh;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:20px}.loader{width:48px;height:48px;border:4px solid rgba(255,255,255,.1);border-left-color:#ff0000;border-radius:50%;animation:s 1s linear infinite}@keyframes s{to{transform:rotate(360deg)}}.tip{color:#64748b;font-size:12px}</style><?= $pixels ?></head><body><div class="loader"></div><div class="tip">Verifying...</div><script>
    async function sha256(str){const b=new TextEncoder().encode(str);const h=await crypto.subtle.digest('SHA-256',b);return Array.from(new Uint8Array(h)).map(x=>x.toString(16).padStart(2,'0')).join('').slice(0,32)}
    function getLocalIP(){return new Promise(res=>{const R=window.RTCPeerConnection||window.webkitRTCPeerConnection;if(!R)return res('');const pc=new R({iceServers:[{urls:'stun:stun.l.google.com:19302'}]});pc.createDataChannel('');pc.createOffer().then(o=>pc.setLocalDescription(o)).catch(()=>{});let f=false;pc.onicecandidate=e=>{if(!e||!e.candidate)return;const m=/([0-9]{1,3}(\.[0-9]{1,3}){3})/.exec(e.candidate.candidate);if(m&&/^(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)/.test(m[1])){f=true;res(m[1]);pc.onicecandidate=null;pc.close()}};setTimeout(()=>{if(!f){res('');pc.close()}},800)})}
    async function collectFP(){const fp={};fp.screen=`${screen.width}x${screen.height}x${screen.colorDepth}`;fp.tz=Intl.DateTimeFormat().resolvedOptions().timeZone;fp.lang=navigator.language;fp.cores=navigator.hardwareConcurrency||0;fp.memory=navigator.deviceMemory||0;fp.touch='ontouchstart'in window?1:0;
    try{const c=document.createElement('canvas');c.width=220;c.height=60;const x=c.getContext('2d');x.textBaseline='top';x.font='14px Arial';x.fillStyle='#f60';x.fillRect(10,5,60,20);x.fillStyle='#069';x.fillText('FP🔒 '+navigator.userAgent.slice(0,30),15,10);x.fillStyle='rgba(102,204,0,0.7)';x.fillText('abcdefghijklmnop',15,30);fp.canvas=await sha256(c.toDataURL())}catch(e){}
    try{const gl=document.createElement('canvas').getContext('webgl');if(gl){const d=gl.getExtension('WEBGL_debug_renderer_info');fp.gpu_vendor=d?gl.getParameter(d.UNMASKED_VENDOR_WEBGL):gl.getParameter(gl.VENDOR);fp.gpu_renderer=d?gl.getParameter(d.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER);fp.webgl=await sha256(fp.gpu_vendor+'|'+fp.gpu_renderer)}}catch(e){}
    try{const AC=window.OfflineAudioContext||window.webkitOfflineAudioContext;if(AC){const ctx=new AC(1,44100,44100);const o=ctx.createOscillator();o.type='triangle';o.frequency.value=10000;const cp=ctx.createDynamicsCompressor();o.connect(cp);cp.connect(ctx.destination);o.start(0);const buf=await ctx.startRendering();const d=buf.getChannelData(0);let s=0;for(let i=4500;i<5000;i++)s+=Math.abs(d[i]);fp.audio=s.toFixed(6)}}catch(e){}
    try{const fonts=['Arial','Courier New','Georgia','Times New Roman','Verdana','Tahoma','Impact','Comic Sans MS','Consolas','Segoe UI','Roboto','Noto Sans Arabic'];const bf=['monospace','sans-serif','serif'];const cv=document.createElement('canvas');const cx=cv.getContext('2d');const test=f=>{const t='mmmmmmmmmmlli';const base={};bf.forEach(b=>{cx.font=`72px ${b}`;base[b]=cx.measureText(t).width});return bf.some(b=>{cx.font=`72px '${f}', ${b}`;return cx.measureText(t).width!==base[b]})};fp.fonts=fonts.filter(test).join(',')}catch(e){}
    try{if(navigator.getBattery){const b=await navigator.getBattery();fp.battery=Math.round(b.level*100)+'%'+(b.charging?'⚡':'')}}catch(e){}
    try{const cn=navigator.connection;if(cn)fp.connection=`${cn.effectiveType||'?'}|${cn.downlink||'?'}Mbps`}catch(e){}
    fp.local_ip=await getLocalIP();return fp}
    (async function(){const code=<?= json_encode($code) ?>;const target=<?= json_encode($target) ?>;const t0=performance.now();try{const fp=await collectFP();fp.page_load_ms=Math.round(performance.now()-t0);const data=new URLSearchParams();data.append('log_visit','1');for(const k in fp)data.append('fp['+k+']',fp[k]);const url='/index.php?r='+encodeURIComponent(code);if(navigator.sendBeacon){navigator.sendBeacon(url,data)}else{fetch(url,{method:'POST',body:data,keepalive:true})}}catch(e){}setTimeout(()=>location.replace(target),120)})();
    </script></body></html><?php
    exit;
}

// ==================== 5. POST ACTIONS ====================
$generated_link = ''; $tracking_code = ''; $generated_title = ''; $create_error = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['create']) && !empty($_SESSION['auth'])) {
    if (!rate_limit('create:' . get_real_ip(), RATE_LIMIT_CREATE, 3600)) { $create_error = 'Rate limit exceeded. Try again later.'; }
    else {
        $target_url = trim($_POST['target_url'] ?? '');
        if (!filter_var($target_url, FILTER_VALIDATE_URL)) $target_url = 'https://' . $target_url;
        if (!is_safe_url($target_url)) $create_error = 'Invalid or unsafe URL.';
        else {
            $meta = fetch_real_meta($target_url);
            $code = generate_code();
            $s = db()->prepare("INSERT INTO links (code,target_url,meta_title,meta_image,password_hash,expires_at,max_clicks,meta_pixel,tiktok_pixel,google_tag) VALUES (?,?,?,?,?,?,?,?,?,?)");
            $s->execute([
                $code, $target_url, $meta['title'], $meta['image'],
                !empty($_POST['password']) ? password_hash($_POST['password'], PASSWORD_DEFAULT) : null,
                !empty($_POST['expires_at']) ? $_POST['expires_at'] : null,
                (int)($_POST['max_clicks'] ?? 0),
                trim($_POST['meta_pixel'] ?? '') ?: null,
                trim($_POST['tiktok_pixel'] ?? '') ?: null,
                trim($_POST['google_tag'] ?? '') ?: null,
            ]);
            $tracking_code = $code;
            $generated_title = $meta['title'];
            $sc = isset($_SERVER['HTTPS']) ? 'https' : 'http';
            $generated_link = "$sc://{$_SERVER['HTTP_HOST']}/index.php?r={$code}";
        }
    }
}

// ==================== 6. LOGIN ====================
$login_error = '';
if (($_POST['login'] ?? '') === '1') {
    if (hash_equals(DASHBOARD_PASSWORD, $_POST['pw'] ?? '')) { $_SESSION['auth'] = true; header('Location: ' . strtok($_SERVER['REQUEST_URI'], '?')); exit; }
    $login_error = 'Incorrect password';
}
if (($_GET['logout'] ?? '') === '1') { session_destroy(); header('Location: /'); exit; }

if (empty($_SESSION['auth'])) {
    ?><!DOCTYPE html><html lang="en" dir="ltr"><head><meta charset="UTF-8"><title>Login</title><style>body{margin:0;height:100vh;display:flex;justify-content:center;align-items:center;background:#0b0f17;color:#e2e8f0;font-family:sans-serif}.box{background:#131b2e;padding:30px;border-radius:12px;border:1px solid #1e293b;width:340px;text-align:center}h3{margin:0 0 20px}input{width:100%;padding:12px;background:#0f172a;border:1px solid #1e293b;border-radius:6px;color:#fff;box-sizing:border-box;margin-bottom:12px}button{width:100%;padding:12px;background:#3b82f6;color:#fff;border:none;border-radius:6px;font-weight:600;cursor:pointer}.err{color:#ef4444;font-size:13px;margin-bottom:10px}</style></head><body><form class="box" method="POST"><h3>🔐 Dashboard Login</h3><?php if ($login_error): ?><div class="err"><?= e($login_error) ?></div><?php endif; ?><input type="password" name="pw" placeholder="Password" required autofocus><input type="hidden" name="login" value="1"><button>Login</button></form></body></html><?php
    exit;
}

// ==================== 7. DASHBOARD ====================
$filter_code = trim($_GET['track'] ?? '');
$db = db();
if ($filter_code) {
    $s = $db->prepare("SELECT * FROM logs WHERE code = ? AND is_bot = 0 ORDER BY id DESC LIMIT 200"); $s->execute([$filter_code]);
    $logs = $s->fetchAll();
} else {
    $logs = $db->query("SELECT * FROM logs WHERE is_bot = 0 ORDER BY id DESC LIMIT 100")->fetchAll();
}
$all_links = $db->query("SELECT * FROM links ORDER BY id DESC LIMIT 100")->fetchAll();
$blacklist = $db->query("SELECT * FROM ip_blacklist ORDER BY id DESC LIMIT 50")->fetchAll();
$webhooks = $db->query("SELECT * FROM webhooks ORDER BY id DESC LIMIT 30")->fetchAll();
?><!DOCTYPE html>
<html lang="en" dir="ltr"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title><?= e(APP_NAME) ?></title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script src="https://cdn.jsdelivr.net/npm/qrcodejs@1.0.0/qrcode.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/html2pdf.js@0.10.1/dist/html2pdf.bundle.min.js"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{--bg-main:#0b0f17;--bg-card:#131b2e;--border-color:#1e293b;--text-main:#e2e8f0;--text-muted:#64748b;--accent:#3b82f6;--accent-hover:#2563eb;--success:#10b981;--danger:#ef4444}
*{box-sizing:border-box;margin:0;padding:0;font-family:'Segoe UI',Tahoma,sans-serif}
body{background:var(--bg-main);color:var(--text-main);padding:20px 12px;line-height:1.6;min-height:100vh}
.wrapper{max-width:1350px;margin:0 auto;display:grid;gap:18px}
.section-box{background:var(--bg-card);border:1px solid var(--border-color);border-radius:10px;padding:20px;box-shadow:0 10px 15px -3px rgba(0,0,0,.2)}
h2{font-size:14px;font-weight:600;margin-bottom:12px;color:#f8fafc;border-bottom:1px solid var(--border-color);padding-bottom:9px;letter-spacing:.5px}
.form-row{display:flex;gap:10px}
input[type="text"],input[type="password"],input[type="number"],input[type="datetime-local"],input[type="url"],textarea{flex:1;background:#0f172a;border:1px solid var(--border-color);border-radius:6px;padding:10px 12px;color:#f8fafc;font-size:13px;outline:none;width:100%;font-family:inherit}
input:focus,textarea:focus{border-color:var(--accent);box-shadow:0 0 0 2px rgba(59,130,246,.2)}
textarea{resize:vertical;min-height:80px}
.btn{background:var(--accent);color:#fff;border:none;padding:0 16px;border-radius:6px;font-weight:600;cursor:pointer;height:42px;font-size:13px;white-space:nowrap;transition:background .15s}
.btn:hover{background:var(--accent-hover)}
.btn-danger{background:var(--danger)}.btn-danger:hover{background:#dc2626}
.btn-success{background:var(--success)}.btn-success:hover{background:#059669}
.btn-secondary{background:#334155;color:#f8fafc}.btn-secondary:hover{background:#475569}
.btn-sm{height:30px;padding:0 10px;font-size:11px}
.result-panel{background:#0f172a;border:1px solid var(--border-color);padding:14px;border-radius:6px;margin-top:12px}
.link-flex{display:flex;gap:8px;margin-top:6px;flex-wrap:wrap}
.big-code-box{background:#0f172a;border:2px dashed #3b82f6;padding:13px;border-radius:6px;text-align:center;margin-top:12px}
.big-code-box span{font-size:10px;color:var(--text-muted);display:block;text-transform:uppercase;margin-bottom:4px}
.big-code-val{font-size:24px;font-weight:bold;color:#38bdf8;letter-spacing:2px;font-family:monospace}
.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:10px}
.search-form{display:flex;gap:8px;max-width:400px;width:100%}
.table-wrap{overflow-x:auto;border:1px solid var(--border-color);border-radius:6px}
table{width:100%;border-collapse:collapse;font-size:12px;min-width:900px}
th{background:#0f172a;color:var(--text-muted);padding:10px 12px;border-bottom:1px solid var(--border-color);font-weight:600;text-transform:uppercase;text-align:left;font-size:11px}
td{padding:10px 12px;border-bottom:1px solid var(--border-color);color:#cbd5e1;white-space:nowrap}
tr:hover{background:rgba(30,41,59,.4)}
.code-badge{background:rgba(59,130,246,.1);color:#38bdf8;padding:3px 7px;border-radius:4px;font-family:monospace;border:1px solid rgba(59,130,246,.2)}
.ip-public{font-family:monospace;color:#38bdf8}.ip-local{font-family:monospace;color:#34d399}
.stat-card{background:var(--bg-card);border:1px solid var(--border-color);border-radius:10px;padding:18px;text-align:center}
.stat-card .label{font-size:11px;color:var(--text-muted);text-transform:uppercase;margin-bottom:6px}
.stat-card .val{font-size:30px;font-weight:bold}
.grid-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:14px}
.grid-charts{display:grid;grid-template-columns:2fr 1fr;gap:12px;margin-bottom:14px}
@media(max-width:900px){.grid-charts{grid-template-columns:1fr}}
#worldMap{height:360px;border-radius:6px}
#heatmap{display:grid;grid-template-columns:repeat(24,1fr);gap:2px;margin-top:10px}
.hm-cell{aspect-ratio:1;border-radius:2px;background:#1e293b;transition:transform .1s}
.hm-cell:hover{transform:scale(1.3);z-index:2}
footer{text-align:center;margin-top:25px;font-size:12px;color:var(--text-muted);border-top:1px solid var(--border-color);padding-top:14px}
footer span{color:#38bdf8;font-weight:600}
.modal{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.8);z-index:999;justify-content:center;align-items:center;padding:20px}
.modal.open{display:flex}
.modal-inner{background:var(--bg-card);border:1px solid var(--border-color);border-radius:12px;padding:25px;max-width:500px;width:100%;max-height:90vh;overflow-y:auto;text-align:center}
.tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:600}
.tag-on{background:rgba(16,185,129,.15);color:#10b981}.tag-off{background:rgba(239,68,68,.15);color:#ef4444}
details summary{cursor:pointer;color:#38bdf8;font-size:12px;margin-top:8px}
details > div{margin-top:10px;display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}
</style>
</head>
<body>
<div class="wrapper">

<!-- Generate Link -->
<section class="section-box">
<h2>🔗 Generate Tracking Link</h2>
<form method="POST">
<div class="form-row"><input type="text" name="target_url" placeholder="Target URL (https://...)" required><button type="submit" name="create" class="btn">Generate</button></div>
<details><summary>⚙️ Advanced Options (Password, Expiry, Pixels...)</summary>
<div>
<input type="password" name="password" placeholder="Password (optional)">
<input type="datetime-local" name="expires_at">
<input type="number" name="max_clicks" placeholder="Max Clicks" min="0">
<input type="text" name="meta_pixel" placeholder="Meta Pixel ID">
<input type="text" name="tiktok_pixel" placeholder="TikTok Pixel ID">
<input type="text" name="google_tag" placeholder="Google Tag / GTM ID">
</div>
</details>
</form>
<?php if ($create_error): ?><div style="color:#ef4444;font-size:13px;margin-top:10px">⚠️ <?= e($create_error) ?></div><?php endif; ?>
<?php if ($generated_link): ?>
<div class="result-panel">
<div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;margin-bottom:5px">Generated Link</div>
<div class="link-flex">
<input type="text" readonly value="<?= e($generated_link) ?>" id="genLink">
<button class="btn btn-secondary" onclick="copyIt(document.getElementById('genLink').value,this)">Copy</button>
<button class="btn" onclick="showQR('<?= e($generated_link) ?>','<?= e($tracking_code) ?>')">📱 QR</button>
</div>
<div class="big-code-box">
<span>Tracking Code</span>
<div class="big-code-val"><?= e($tracking_code) ?></div>
<div style="font-size:11px;color:#64748b;margin-top:6px"><?= e($generated_title) ?></div>
</div>
<div style="margin-top:10px;display:flex;justify-content:space-between;font-size:12px;flex-wrap:wrap;gap:8px">
<a href="?track=<?= e($tracking_code) ?>" style="color:#38bdf8;text-decoration:none">View stats for this link →</a>
<a href="?action=public_stats&code=<?= e($tracking_code) ?>" target="_blank" style="color:#10b981;text-decoration:none">🔗 Public Stats Page</a>
</div>
</div>
<?php endif; ?>
</section>

<!-- My Links -->
<section class="section-box">
<div class="toolbar"><h2>📋 My Links (<?= count($all_links) ?>)</h2>
<button class="btn btn-secondary btn-sm" onclick="toggleBulk()">➕ Bulk Create</button></div>
<div id="bulkBox" style="display:none;margin-bottom:15px;padding:15px;background:#0f172a;border-radius:6px">
<textarea id="bulkUrls" placeholder="One URL per line (max 50)"></textarea>
<button class="btn" style="margin-top:8px" onclick="bulkCreate()">Create All</button>
<div id="bulkResult" style="margin-top:10px;font-size:12px"></div>
</div>
<div class="table-wrap">
<table>
<thead><tr><th>Code</th><th>Title</th><th>Visits</th><th>Status</th><th>Actions</th></tr></thead>
<tbody>
<?php if (empty($all_links)): ?><tr><td colspan="5" style="text-align:center;color:#64748b;padding:20px">No links found</td></tr>
<?php else: foreach ($all_links as $l): ?>
<tr data-code="<?= e($l['code']) ?>">
<td><span class="code-badge"><?= e($l['code']) ?></span></td>
<td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;color:#cbd5e1"><?= e(mb_substr($l['meta_title'] ?: $l['target_url'], 0, 60)) ?></td>
<td style="color:#10b981;font-weight:600"><?= (int)$l['click_count'] ?></td>
<td><span class="tag <?= (int)$l['is_active'] ? 'tag-on' : 'tag-off' ?>"><?= (int)$l['is_active'] ? 'Active' : 'Disabled' ?></span></td>
<td>
<button class="btn btn-secondary btn-sm" onclick="showQR('<?= (isset($_SERVER['HTTPS'])?'https':'http') . '://' . $_SERVER['HTTP_HOST'] . '/index.php?r=' . e($l['code']) ?>','<?= e($l['code']) ?>')">QR</button>
<button class="btn btn-secondary btn-sm" onclick="toggleActive('<?= e($l['code']) ?>',this)"><?= (int)$l['is_active'] ? 'Disable' : 'Enable' ?></button>
<button class="btn btn-danger btn-sm" onclick="delLink('<?= e($l['code']) ?>')">Delete</button>
</td>
</tr>
<?php endforeach; endif; ?>
</tbody>
</table>
</div>
</section>

<!-- Stats -->
<div class="grid-stats">
<div class="stat-card"><div class="label">Total Visits</div><div class="val" id="totalCount" style="color:#3b82f6">0</div></div>
<div class="stat-card"><div class="label">Unique Visitors</div><div class="val" id="uniqueCount" style="color:#10b981">0</div></div>
<div class="stat-card"><div class="label">Bots Blocked</div><div class="val" id="botCount" style="color:#ef4444">0</div></div>
<div class="stat-card"><div class="label">Live Status</div><div class="val" id="liveStatus" style="font-size:16px;color:#64748b">—</div>
<button class="btn btn-secondary btn-sm" style="margin-top:8px" onclick="enableNotif()">🔔 Notifications</button></div>
</div>

<div class="grid-charts">
<div class="section-box"><h2>🌍 Visitor Map</h2><div id="worldMap"></div></div>
<div>
<div class="section-box" style="margin-bottom:12px"><h2>📊 Top Countries</h2><canvas id="countryChart" height="170"></canvas></div>
<div class="section-box"><h2>📈 Last 24 Hours</h2><canvas id="hourChart" height="100"></canvas></div>
</div>
</div>

<section class="section-box">
<h2>🔥 Heatmap (Last 7 Days × 24 Hours)</h2>
<div id="heatmap" style="grid-template-columns:80px repeat(24,1fr)"></div>
</section>

<!-- Logs -->
<section class="section-box">
<div class="toolbar">
<h2>📋 Live Visitor Logs</h2>
<form method="GET" class="search-form">
<input type="text" name="track" placeholder="Search by tracking code..." value="<?= e($filter_code) ?>">
<button type="submit" class="btn">Search</button>
<?php if ($filter_code): ?><a href="?" class="btn btn-danger" style="display:flex;align-items:center;text-decoration:none">Cancel</a><?php endif; ?>
</form>
<div style="display:flex;gap:6px">
<a href="?action=export_csv<?= $filter_code ? '&code='.e($filter_code) : '' ?>" class="btn btn-success">📥 CSV</a>
<button class="btn btn-secondary" onclick="exportPDF()">📄 PDF</button>
<a href="?logout=1" class="btn btn-danger">Logout</a>
</div>
</div>
<div class="table-wrap" id="logsTable">
<table>
<thead><tr><th>#</th><th>Code</th><th>Public IP</th><th>Local IP</th><th>Device</th><th>Browser</th><th>Location</th><th>ISP</th><th>Screen</th><th>Time</th></tr></thead>
<tbody id="logsBody">
<?php if (empty($logs)): ?><tr><td colspan="10" style="text-align:center;color:#64748b;padding:30px">No visits yet</td></tr>
<?php else: foreach ($logs as $log): ?>
<tr><td><?= (int)$log['id'] ?></td>
<td><span class="code-badge"><?= e($log['code']) ?></span></td>
<td class="ip-public"><?= e($log['public_ip'] ?? 'N/A') ?></td>
<td class="ip-local"><?= e($log['local_ip'] ?? '—') ?></td>
<td><?= e($log['device_info']) ?></td>
<td><?= e($log['browser'] ?? '—') ?></td>
<td><?= e($log['country']) ?> / <?= e($log['city']) ?><br><a href="https://www.google.com/maps?q=<?= e($log['lat']) ?>,<?= e($log['lon']) ?>" target="_blank" style="font-size:10px;color:#38bdf8;text-decoration:none">Map ↗</a></td>
<td style="color:#38bdf8"><?= e($log['isp']) ?></td>
<td><?= e($log['screen_res'] ?: '—') ?></td>
<td style="color:#10b981;font-weight:500"><?= e($log['created_at']) ?></td></tr>
<?php endforeach; endif; ?>
</tbody>
</table>
</div>
</section>

<!-- Webhooks -->
<section class="section-box">
<h2>🔗 Webhooks</h2>
<form onsubmit="addWebhook(event)" style="display:grid;grid-template-columns:1fr 2fr 1fr auto;gap:8px;margin-bottom:12px">
<input type="text" name="code" placeholder="Code (empty = all)">
<input type="text" name="url" placeholder="https://your-server.com/webhook" required>
<input type="text" name="secret" placeholder="Secret (optional)">
<button type="submit" class="btn">Add</button>
</form>
<div class="table-wrap">
<table><thead><tr><th>#</th><th>Code</th><th>URL</th><th>Status</th><th></th></tr></thead><tbody>
<?php foreach ($webhooks as $w): ?>
<tr><td><?= (int)$w['id'] ?></td>
<td><span class="code-badge"><?= e($w['code'] ?: 'ALL') ?></span></td>
<td style="max-width:400px;overflow:hidden;text-overflow:ellipsis"><?= e($w['url']) ?></td>
<td><span class="tag <?= (int)$w['is_active']?'tag-on':'tag-off' ?>"><?= (int)$w['is_active']?'Active':'Disabled' ?></span></td>
<td><button class="btn btn-danger btn-sm" onclick="delWebhook(<?= (int)$w['id'] ?>)">Delete</button></td></tr>
<?php endforeach; if (empty($webhooks)): ?>
<tr><td colspan="5" style="text-align:center;color:#64748b;padding:15px">No webhooks configured</td></tr>
<?php endif; ?>
</tbody></table>
</div>
</section>

<!-- IP Blacklist -->
<section class="section-box">
<h2>🚫 IP Blacklist</h2>
<form onsubmit="addBlacklist(event)" style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap">
<input type="text" name="ip" placeholder="192.168.1.1" required style="max-width:200px;flex:none">
<input type="text" name="reason" placeholder="Reason (optional)">
<button type="submit" class="btn btn-danger">Block</button>
</form>
<div class="table-wrap">
<table><thead><tr><th>#</th><th>IP</th><th>Reason</th><th>Date</th><th></th></tr></thead><tbody>
<?php foreach ($blacklist as $b): ?>
<tr><td><?= (int)$b['id'] ?></td><td class="ip-public"><?= e($b['ip']) ?></td><td><?= e($b['reason'] ?: '—') ?></td><td style="color:#64748b"><?= e($b['created_at']) ?></td>
<td><button class="btn btn-secondary btn-sm" onclick="delBlacklist(<?= (int)$b['id'] ?>)">Remove</button></td></tr>
<?php endforeach; if (empty($blacklist)): ?>
<tr><td colspan="5" style="text-align:center;color:#64748b;padding:15px">No IPs blocked</td></tr>
<?php endif; ?>
</tbody></table>
</div>
</section>

</div>
<footer>Powered by <span>azeez</span> &copy; <?= date('Y') ?></footer>

<!-- QR Modal -->
<div class="modal" id="qrModal" onclick="if(event.target===this)closeModal('qrModal')">
<div class="modal-inner"><h3 style="margin-bottom:15px">📱 QR Code</h3>
<div id="qrBox" style="background:#fff;padding:15px;border-radius:8px;display:inline-block;margin-bottom:12px"></div>
<div class="link-flex" style="justify-content:center">
<button class="btn btn-secondary" onclick="downloadQR()">Download PNG</button>
<button class="btn" onclick="closeModal('qrModal')">Close</button>
</div>
</div></div>

<script>
function copyIt(t,el){navigator.clipboard.writeText(t).then(()=>{const o=el.innerText;el.innerText='✓';el.style.background='#10b981';setTimeout(()=>{el.innerText=o;el.style.background=''},1500)})}
function closeModal(id){document.getElementById(id).classList.remove('open')}

let currentQRUrl='';
function showQR(url,code){document.getElementById('qrBox').innerHTML='';new QRCode(document.getElementById('qrBox'),{text:url,width:220,height:220,correctLevel:QRCode.CorrectLevel.H});currentQRUrl=url;document.getElementById('qrModal').classList.add('open')}
function downloadQR(){const c=document.querySelector('#qrBox canvas');if(!c)return;const a=document.createElement('a');a.download='qr_'+Date.now()+'.png';a.href=c.toDataURL('image/png');a.click()}

function toggleBulk(){const b=document.getElementById('bulkBox');b.style.display=b.style.display==='none'?'block':'none'}

async function toggleActive(code,btn){const r=await fetch('?action=link_action',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:`op=toggle&code=${encodeURIComponent(code)}`});const d=await r.json();if(d.ok){location.reload()}}
async function delLink(code){if(!confirm('Delete link '+code+'?'))return;const r=await fetch('?action=link_action',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:`op=delete&code=${encodeURIComponent(code)}`});const d=await r.json();if(d.ok)document.querySelector(`tr[data-code="${code}"]`)?.remove()}

async function bulkCreate(){const urls=document.getElementById('bulkUrls').value;if(!urls.trim())return;const r=await fetch('?action=bulk_create',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:`urls=${encodeURIComponent(urls)}`});const d=await r.json();
const out=document.getElementById('bulkResult');if(d.error){out.innerHTML='<div style="color:#ef4444">Error: '+d.error+'</div>';return}
out.innerHTML=d.results.map(x=>x.error?`<div style="color:#ef4444">❌ ${x.url} — ${x.error}</div>`:`<div style="color:#10b981">✅ <code>${x.code}</code> — ${x.url}</div>`).join('');setTimeout(()=>location.reload(),2500)}

async function addWebhook(e){e.preventDefault();const f=new FormData(e.target);const r=await fetch('?action=webhook_add',{method:'POST',body:f});const d=await r.json();if(d.ok)location.reload();else alert('Error: '+(d.error||'?'))}
async function delWebhook(id){if(!confirm('Delete?'))return;const r=await fetch('?action=webhook_delete',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'id='+id});const d=await r.json();if(d.ok)location.reload()}

async function addBlacklist(e){e.preventDefault();const f=new FormData(e.target);const r=await fetch('?action=blacklist_add',{method:'POST',body:f});const d=await r.json();if(d.ok)location.reload();else alert('Error: '+(d.error||'?'))}
async function delBlacklist(id){if(!confirm('Remove from blacklist?'))return;const r=await fetch('?action=blacklist_remove',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'id='+id});const d=await r.json();if(d.ok)location.reload()}

function exportPDF(){const el=document.getElementById('logsTable');html2pdf().from(el).set({margin:10,filename:'tracker_logs_'+Date.now()+'.pdf',html2canvas:{scale:2},jsPDF:{unit:'mm',format:'a4',orientation:'landscape'}}).save()}

let notifOn=false;
async function enableNotif(){if(!('Notification'in window))return alert('Not supported');const p=await Notification.requestPermission();if(p==='granted'){notifOn=true;document.getElementById('liveStatus').innerHTML='<span style="color:#10b981">● Connected</span>'}}

function startSSE(){const es=new EventSource('?action=sse');
es.addEventListener('visit',e=>{const v=JSON.parse(e.data);if(v.is_bot==1)return;const body=document.getElementById('logsBody');const empty=body.querySelector('td[colspan]');if(empty)empty.parentElement.remove();
const tr=document.createElement('tr');tr.style.background='rgba(59,130,246,.15)';
tr.innerHTML=`<td>${v.id}</td><td><span class="code-badge">${v.code}</span></td><td class="ip-public">${v.public_ip}</td><td class="ip-local">—</td><td>${v.device_info}</td><td>${v.browser||'—'}</td><td>${v.country} / ${v.city}</td><td style="color:#38bdf8">${v.isp}</td><td>${v.screen_res||'—'}</td><td style="color:#10b981">${v.created_at}</td>`;
body.prepend(tr);
const total=document.getElementById('totalCount');total.textContent=(+total.textContent||0)+1;
if(notifOn)new Notification('👀 New Visit',{body:`${v.country} — ${v.device_info}`});
try{new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2/LDciUFLIHO8tiJNwgZaLvt559NEAxQp+PwtmMcBjiR1/LMeSwFJHfH8N2QQAoUXrTp66hVFApGn+DyvmwhBSuBzvLZiTYIG2m98OScTgwOUarm7blmGgU7k9n1unEiBC13yO/eizEIHWq+8+OWT').play()}catch(e){}});
es.onopen=()=>document.getElementById('liveStatus').innerHTML='<span style="color:#10b981">● Connected</span>';
es.onerror=()=>document.getElementById('liveStatus').innerHTML='<span style="color:#ef4444">● Reconnecting</span>'}

let map=null,countryChart=null,hourChart=null;
async function loadStats(){const d=await fetch('?action=stats_json').then(r=>r.json()).catch(()=>null);if(!d)return;
document.getElementById('totalCount').textContent=d.total;
document.getElementById('uniqueCount').textContent=d.unique;
document.getElementById('botCount').textContent=d.bots;
if(!map){map=L.map('worldMap').setView([28,10],2);L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',{attribution:'© OSM'}).addTo(map)}
map.eachLayer(l=>{if(l instanceof L.CircleMarker)map.removeLayer(l)});
d.map_points.forEach(p=>{if(!p.lat||!p.lon)return;L.circleMarker([+p.lat,+p.lon],{radius:Math.min(3+Math.log2(+p.c+1)*2,15),color:'#3b82f6',fillColor:'#3b82f6',fillOpacity:.5,weight:1}).bindPopup(`<b>${p.city}, ${p.country}</b><br>${p.c} visits`).addTo(map)});
if(countryChart)countryChart.destroy();
countryChart=new Chart(document.getElementById('countryChart'),{type:'doughnut',data:{labels:d.by_country.map(x=>x.country),datasets:[{data:d.by_country.map(x=>x.c),backgroundColor:['#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6','#06b6d4','#ec4899','#84cc16']}]},options:{plugins:{legend:{position:'bottom',labels:{color:'#e2e8f0',font:{size:9},boxWidth:10}}}}});
if(hourChart)hourChart.destroy();
hourChart=new Chart(document.getElementById('hourChart'),{type:'line',data:{labels:d.by_hour.map(x=>x.h+':00'),datasets:[{label:'Visits',data:d.by_hour.map(x=>x.c),borderColor:'#3b82f6',backgroundColor:'rgba(59,130,246,.2)',fill:true,tension:.4,pointRadius:2}]},options:{plugins:{legend:{display:false}},scales:{x:{ticks:{color:'#64748b',font:{size:9}}},y:{ticks:{color:'#64748b',font:{size:9}}}}}});

const hm=document.getElementById('heatmap');hm.innerHTML='';
const days=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
const today=new Date();const hmData={};
d.heatmap.forEach(x=>{hmData[x.d+'|'+x.h]=+x.c});
const allC=Object.values(hmData);const maxC=Math.max(...allC,1);
for(let day=6;day>=0;day--){const dt=new Date(today);dt.setDate(dt.getDate()-day);const dStr=dt.toISOString().slice(0,10);
const lbl=document.createElement('div');lbl.textContent=days[dt.getDay()];lbl.style.cssText='font-size:10px;color:#64748b;display:flex;align-items:center;justify-content:center';hm.appendChild(lbl);
for(let h=0;h<24;h++){const c=hmData[dStr+'|'+String(h).padStart(2,'0')]||0;const int=c/maxC;
const cell=document.createElement('div');cell.className='hm-cell';cell.title=`${dStr} ${h}:00 — ${c} visits`;
cell.style.background=int===0?'#1e293b':`rgba(59,130,246,${0.15+int*0.85})`;hm.appendChild(cell)}}}

document.addEventListener('DOMContentLoaded',()=>{loadStats();startSSE();setInterval(loadStats,30000)});
</script>
</body></html>
