"""
Nerq Design System v13 — "Bloomberg Terminal of Trust"
======================================================
Render functions for all nerq.ai page components.
CSS lives in /static/nerq.css (external, cached 7 days).
Only critical above-fold CSS is inlined.

Import: from agentindex.nerq_design import (
    NERQ_CSS, NERQ_NAV, NERQ_FOOTER,
    render_head, render_nav, render_verdict_box, render_breadcrumb,
    render_trust_breakdown, render_cross_links, render_footer, render_faq,
    nerq_head, nerq_page
)
"""

import html as _html
from datetime import date

_CSS_VERSION = 13
_SITE = "https://nerq.ai"
_TODAY = date.today().isoformat()
_YEAR = date.today().year

# All supported languages for hreflang tags
HREFLANG_LANGS = ["en", "es", "pt", "fr", "de", "ja", "ru", "ko", "it", "tr",
                   "nl", "pl", "id", "th", "vi", "hi", "sv", "cs", "ro", "zh", "da", "no", "ar"]


def render_hreflang(path):
    """Generate hreflang link tags for all supported languages.
    path: the English URL path (e.g., '/safe/express' or '/is-tiktok-safe').
    Returns HTML string with all hreflang <link> tags.
    """
    tags = []
    en_url = f"{_SITE}{path}"
    tags.append(f'<link rel="alternate" hreflang="en" href="{en_url}">')
    tags.append(f'<link rel="alternate" hreflang="x-default" href="{en_url}">')
    for lang in HREFLANG_LANGS:
        if lang == "en":
            continue
        tags.append(f'<link rel="alternate" hreflang="{lang}" href="{_SITE}/{lang}{path}">')
    return "\n".join(tags)

def _esc(s):
    return _html.escape(str(s)) if s else ""


# ── Score/grade color helpers ──────────────────────────────

def _score_class(score):
    """CSS class for a trust score value."""
    if score is None: return "sc-mid"
    s = float(score)
    if s >= 80: return "sc-high"
    if s >= 60: return "sc-good"
    if s >= 40: return "sc-mid"
    if s >= 20: return "sc-low"
    return "sc-crit"

def _grade_bg(grade):
    """CSS class for grade badge background."""
    if not grade: return "bg-mid"
    g = grade.upper()[0]
    if g == "A": return "bg-high"
    if g == "B": return "bg-good"
    if g == "C": return "bg-mid"
    if g == "D": return "bg-low"
    return "bg-crit"


# ── Critical inline CSS (above-fold only, <2KB) ───────────

_CRITICAL_CSS = """<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#0f172a;line-height:1.6;background:#fff;font-size:15px}
a{color:#2563eb;text-decoration:none}
.nav{border-bottom:1px solid #e2e8f0;padding:10px 0;position:sticky;top:0;background:#fff;z-index:100}
.nav-inner{max-width:1100px;margin:0 auto;padding:0 20px;display:flex;align-items:center;gap:16px}
.nav-logo{font-size:20px;font-weight:700;color:#0f172a;text-decoration:none}
.nav-logo:hover{text-decoration:none}
.nav-logo span{font-weight:400;color:#64748b;font-size:13px;margin-left:6px}
.nav-links{display:flex;gap:16px;font-size:13px;margin-left:auto}
.nav-links a{color:#64748b;text-decoration:none}
.container{max-width:780px;margin:0 auto;padding:0 20px}
.verdict{border:1px solid #e2e8f0;border-radius:12px;padding:24px 28px;margin:8px 0 20px;display:flex;align-items:center;gap:24px}
.verdict-num{font-size:38px;font-weight:700;line-height:1}
.sc-high{color:#16a34a}.sc-good{color:#22c55e}.sc-mid{color:#f59e0b}.sc-low{color:#ef4444}.sc-crit{color:#991b1b}
</style>"""


# ── Backward-compatible NERQ_CSS (inline, for legacy pages) ──

NERQ_CSS = f"""<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#0f172a;line-height:1.6;font-size:15px;background:#fff}}
a{{color:#2563eb;text-decoration:none}}a:hover{{color:#1d4ed8;text-decoration:underline}}
code,pre{{font-family:ui-monospace,'SF Mono','Cascadia Mono',monospace}}
code{{background:#f1f5f9;padding:1px 5px;font-size:.9em;border-radius:3px}}
pre{{background:#f1f5f9;padding:16px;overflow-x:auto;font-size:13px;line-height:1.5;border:1px solid #e2e8f0;border-radius:6px}}
h1,h2,h3,h4{{font-weight:700;line-height:1.3}}
h1{{font-size:1.5rem;margin-bottom:8px}}
h2{{font-size:1.15rem;margin:24px 0 8px;padding-top:16px;border-top:1px solid #f1f5f9}}
h3{{font-size:1rem;margin:16px 0 6px}}
table{{width:100%;border-collapse:collapse;font-size:14px;margin:12px 0}}
th{{text-align:left;padding:8px 10px;border-bottom:2px solid #e2e8f0;color:#64748b;font-weight:600;font-size:13px}}
td{{padding:8px 10px;border-bottom:1px solid #f1f5f9}}
tr:nth-child(even){{background:#fafbfc}}
.container{{max-width:780px;margin:0 auto;padding:0 20px}}
.nav{{border-bottom:1px solid #e2e8f0;padding:10px 0;position:sticky;top:0;background:#fff;z-index:100}}
.nav-inner{{max-width:1100px;margin:0 auto;padding:0 20px;display:flex;align-items:center;gap:16px}}
.nav-logo{{font-size:20px;font-weight:700;color:#0f172a;text-decoration:none}}
.nav-logo:hover{{text-decoration:none}}
.nav-logo span{{font-weight:400;color:#64748b;font-size:13px;margin-left:6px}}
.nav-links{{display:flex;gap:16px;font-size:13px;margin-left:auto}}
.nav-links a{{color:#64748b;text-decoration:none}}
.nav-links a:hover{{color:#0f172a}}
.pill{{display:inline-block;padding:1px 8px;font-size:12px;font-weight:600;border-radius:4px}}
.pill-green{{background:#f0fdf4;color:#16a34a}}
.pill-yellow{{background:#fffbeb;color:#d97706}}
.pill-red{{background:#fef2f2;color:#ef4444}}
.pill-gray{{background:#f8fafc;color:#64748b}}
.breadcrumb{{font-size:13px;color:#64748b;padding:14px 0 6px}}
.breadcrumb a{{color:#64748b;text-decoration:none}}
.breadcrumb a:hover{{color:#0f172a}}
.section{{margin:20px 0}}
.desc{{color:#64748b;font-size:14px;margin:4px 0 12px}}
.cross-links{{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0}}
.cross-link{{font-size:13px;padding:5px 14px;border:1px solid #e2e8f0;border-radius:20px;color:#475569;text-decoration:none}}
.cross-link:hover{{background:#f8fafc;color:#0f172a;text-decoration:none}}
footer{{border-top:1px solid #e2e8f0;padding:24px 0;margin-top:40px;font-size:13px;color:#94a3b8}}
footer .inner,.footer .wide-container{{max-width:1100px;margin:0 auto;padding:0 20px}}
.footer-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:24px}}
.footer-col h4{{font-size:13px;font-weight:600;color:#64748b;margin-bottom:8px}}
.footer a{{color:#64748b;text-decoration:none;display:block;padding:2px 0}}
.footer a:hover{{color:#0f172a}}
.footer-bottom{{margin-top:16px;padding-top:12px;border-top:1px solid #f1f5f9;font-size:12px;color:#94a3b8}}
@media(max-width:768px){{
.nav-inner{{flex-wrap:wrap}}
.nav-links{{gap:10px;font-size:12px}}
.footer-grid{{grid-template-columns:repeat(2,1fr)}}
table{{font-size:13px}}
th,td{{padding:6px 8px}}
}}
/* RTL support (Arabic) */
[dir="rtl"]{{direction:rtl;text-align:right}}
[dir="rtl"] .breadcrumb,[dir="rtl"] .nav-links{{flex-direction:row-reverse}}
[dir="rtl"] pre,[dir="rtl"] code{{direction:ltr;text-align:left}}
[dir="rtl"] .pplx-verdict{{border-left:none;border-right:4px solid #16a34a}}
[dir="rtl"] table th{{text-align:right}}
[dir="rtl"] td:first-child{{text-align:right}}
[dir="rtl"] .signal-card,.alt-card,.cross-link{{text-align:right}}
</style>"""


# ── Nav HTML ───────────────────────────────────────────────

NERQ_NAV = """<nav class="nav"><div class="nav-inner">
<a href="/" class="nav-logo">Nerq<span>Trust Intelligence</span></a>
<div class="nav-links">
<a href="/discover">Search</a>
<div class="nav-dropdown" style="position:relative;display:inline-block">
<a href="/categories" class="nav-drop-trigger" style="cursor:pointer">Categories &#9662;</a>
<div class="nav-drop-menu" style="display:none;position:absolute;top:100%;left:-60px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px 20px;min-width:420px;box-shadow:0 8px 24px rgba(0,0,0,.1);z-index:100;line-height:1.8">
<div style="display:grid;grid-template-columns:1fr 1fr;gap:0 24px">
<div><strong style="font-size:11px;text-transform:uppercase;color:#64748b;letter-spacing:.05em">Security &amp; Privacy</strong><br>
<a href="/vpns">VPNs</a><br><a href="/apps">Apps</a><br><a href="/games">Games</a></div>
<div><strong style="font-size:11px;text-transform:uppercase;color:#64748b;letter-spacing:.05em">Developer Tools</strong><br>
<a href="/npm">npm</a><br><a href="/pypi">PyPI</a><br><a href="/crates">Rust Crates</a><br><a href="/wordpress-plugins">WordPress</a><br><a href="/packagist">Packagist</a><br><a href="/extensions">VS Code</a><br><a href="/gems">RubyGems</a><br><a href="/homebrew">Homebrew</a></div>
<div style="margin-top:8px"><strong style="font-size:11px;text-transform:uppercase;color:#64748b;letter-spacing:.05em">More</strong><br>
<a href="/crypto">Crypto</a><br><a href="/discover">AI Tools</a><br><a href="/categories">All Categories</a></div>
</div>
<div style="margin-top:10px;padding-top:8px;border-top:1px solid #e2e8f0;font-size:12px"><a href="/categories">View all 18 categories &rarr;</a></div>
</div>
</div>
<a href="/compare">Compare</a>
<a href="/nerq/docs">API</a>
<select id="nerq-lang" onchange="(function(s){var v=s.value,p=location.pathname;if(v==='en'){p=p.replace(/^\\/[a-z]{2}\\//,'/');location.href=p||'/';}else{var m=p.match(/^\\/([a-z]{2})\\//);if(m){p=p.replace(/^\\/[a-z]{2}\\//,'/'+v+'/');}else if(p==='/'){p='/'+v+'/';}else{p='/'+v+p;}location.href=p;}})(this)" style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:2px 4px;font-size:12px;color:#64748b;cursor:pointer">
<option value="en">EN</option><option value="es">ES</option><option value="de">DE</option><option value="fr">FR</option><option value="ja">JA</option><option value="pt">PT</option><option value="id">ID</option><option value="cs">CS</option><option value="th">TH</option><option value="ro">RO</option><option value="tr">TR</option><option value="hi">HI</option><option value="ru">RU</option><option value="pl">PL</option><option value="it">IT</option><option value="ko">KO</option><option value="vi">VI</option><option value="nl">NL</option><option value="sv">SV</option><option value="zh">ZH</option><option value="da">DA</option><option value="no">NO</option>
</select>
</div>
</div></nav>
<style>.nav-dropdown:hover .nav-drop-menu{display:block!important}@media(max-width:768px){.nav-drop-menu{left:0!important;min-width:90vw!important}.nav-drop-menu div[style*="grid"]{grid-template-columns:1fr!important}}</style>
<script>(function(){var m=location.pathname.match(/^\\/([a-z]{2})\\//);if(m){var s=document.getElementById('nerq-lang');if(s)s.value=m[1];}})();</script>"""


# ── Footer HTML ────────────────────────────────────────────

NERQ_EXPLORE = """<div class="cross-links" style="margin-top:2rem;padding-top:1.5rem;border-top:1px solid #e2e8f0">
<a href="/apps" class="cross-link">Apps</a>
<a href="/npm" class="cross-link">npm</a>
<a href="/pypi" class="cross-link">PyPI</a>
<a href="/vpns" class="cross-link">VPNs</a>
<a href="/games" class="cross-link">Games</a>
<a href="/categories" class="cross-link">All Categories</a>
<a href="/compare" class="cross-link">Compare</a>
</div>"""

NERQ_FOOTER = NERQ_EXPLORE + """<footer class="footer"><div class="wide-container">
<div class="footer-grid">
<div class="footer-col"><h4>Check Safety</h4>
<a href="/apps">Mobile Apps</a><a href="/vpns">VPNs</a><a href="/games">Games</a>
<a href="/wordpress-plugins">WordPress</a><a href="/categories">All Categories</a></div>
<div class="footer-col"><h4>Packages</h4>
<a href="/npm">npm</a><a href="/pypi">PyPI</a><a href="/crates">Rust Crates</a>
<a href="/packagist">Packagist</a><a href="/extensions">VS Code</a></div>
<div class="footer-col"><h4>Resources</h4>
<a href="/guides">Safety Guides</a><a href="/compare">Compare</a><a href="/check-website">Check Website</a>
<a href="/nerq/docs">API</a><a href="/badges">Trust Badges</a><a href="/llms.txt">llms.txt</a></div>
<div class="footer-col"><h4>Nerq</h4>
<p style="font-size:12px;color:#94a3b8;line-height:1.5">Trust scores for software, apps, VPNs, games, and packages. Independent. Data-driven.</p>
<a href="/about" style="margin-top:6px">About</a><a href="https://zarq.ai">zarq.ai (crypto)</a></div>
</div>
<div class="footer-bottom">nerq.ai &mdash; trust scores for all software &middot; 7.5M+ entities &middot; 26 registries &middot; 22 languages &middot; <a href="/privacy" style="color:#94a3b8">Privacy</a> &middot; <a href="/terms" style="color:#94a3b8">Terms</a> &middot; <a href="mailto:hello@nerq.ai" style="color:#94a3b8">hello@nerq.ai</a></div>
</div></footer>
<div id="ck-banner" style="position:fixed;bottom:0;left:0;right:0;background:#1e293b;color:#e2e8f0;padding:10px 20px;display:flex;justify-content:space-between;align-items:center;z-index:9999;font-size:13px">
<span>We use cookies for analytics and caching. <a href="/privacy" style="color:#38bdf8">Privacy Policy</a></span>
<button onclick="this.parentElement.style.display='none';localStorage.setItem('ck_ok','1')" style="background:#38bdf8;color:#0f172a;border:none;padding:6px 16px;border-radius:4px;cursor:pointer;font-weight:600;font-size:13px">Accept</button>
</div>
<script>if(localStorage.getItem('ck_ok'))document.getElementById('ck-banner').style.display='none'</script>"""


# ── Render functions ───────────────────────────────────────

def render_head(title, description="", canonical="", extra_meta="", extra_ld="", lang="en"):
    """Full <head> with external CSS, critical inline CSS, meta tags."""
    canon = f'<link rel="canonical" href="{_esc(canonical)}">' if canonical else ""
    desc = f'<meta name="description" content="{_esc(description)}">' if description else ""
    return f"""<!DOCTYPE html>
<html lang="{_esc(lang)}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
{desc}
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
{canon}
<link rel="alternate" type="application/atom+xml" href="/feed/recent" title="Nerq Trust Scores">
{extra_meta}
{extra_ld}
{_CRITICAL_CSS}
<link rel="stylesheet" href="/static/nerq.css?v={_CSS_VERSION}">
</head>
<body>"""


_UI = {
    "en": {"search":"Search","categories":"Categories","compare":"Compare","sec_priv":"Security &amp; Privacy","dev_tools":"Developer Tools","more":"More","all_cats":"All Categories","view_all":"View all 18 categories &rarr;","crypto":"Crypto","ai_tools":"AI Tools",
           "check_safety":"Check Safety","mobile_apps":"Mobile Apps","games":"Games","packages":"Packages","resources":"Resources","guides":"Safety Guides","check_web":"Check Website","badges":"Trust Badges","about":"About",
           "tagline":"Trust scores for software, apps, VPNs, games, and packages. Independent. Data-driven.",
           "bottom":"nerq.ai &mdash; trust scores for all software","privacy":"Privacy","terms":"Terms","contact":"Contact","cookies":"We use cookies for analytics and caching.","accept":"Accept"},
    "sv": {"search":"Sök","categories":"Kategorier","compare":"Jämför","sec_priv":"Säkerhet &amp; integritet","dev_tools":"Utvecklarverktyg","more":"Mer","crypto":"Krypto","ai_tools":"AI-verktyg","all_cats":"Alla kategorier","view_all":"Visa alla 18 kategorier &rarr;",
           "check_safety":"Kontrollera säkerhet","mobile_apps":"Mobilappar","games":"Spel","packages":"Paket","resources":"Resurser","guides":"Säkerhetsguider","check_web":"Kontrollera webbplats","badges":"Förtroendemärken","about":"Om",
           "tagline":"Förtroendepoäng för mjukvara, appar, VPN, spel och paket. Oberoende. Datadriven.",
           "bottom":"nerq.ai &mdash; förtroendepoäng för all mjukvara","privacy":"Integritet","terms":"Villkor","contact":"Kontakt","cookies":"Vi använder cookies för analys och cachelagring.","accept":"Acceptera"},
    "vi": {"search":"Tìm kiếm","categories":"Danh mục","compare":"So sánh","sec_priv":"Bảo mật &amp; Quyền riêng tư","dev_tools":"Công cụ phát triển","more":"Thêm","crypto":"Crypto","ai_tools":"Công cụ AI","all_cats":"Tất cả danh mục","view_all":"Xem tất cả 18 danh mục &rarr;",
           "check_safety":"Kiểm tra bảo mật","mobile_apps":"Ứng dụng di động","games":"Trò chơi","packages":"Gói","resources":"Tài nguyên","guides":"Hướng dẫn bảo mật","check_web":"Kiểm tra trang web","badges":"Huy hiệu tin cậy","about":"Giới thiệu",
           "tagline":"Điểm tin cậy cho phần mềm, ứng dụng, VPN, trò chơi và gói. Độc lập. Dựa trên dữ liệu.",
           "bottom":"nerq.ai &mdash; điểm tin cậy cho tất cả phần mềm","privacy":"Quyền riêng tư","terms":"Điều khoản","contact":"Liên hệ","cookies":"Chúng tôi sử dụng cookie cho phân tích và bộ nhớ đệm.","accept":"Chấp nhận"},
    "ja": {"search":"検索","categories":"カテゴリ","compare":"比較","sec_priv":"セキュリティ &amp; プライバシー","dev_tools":"開発者ツール","more":"その他","crypto":"暗号資産","ai_tools":"AIツール","all_cats":"全カテゴリ","view_all":"全18カテゴリを見る &rarr;",
           "check_safety":"安全確認","mobile_apps":"モバイルアプリ","games":"ゲーム","packages":"パッケージ","resources":"リソース","guides":"安全ガイド","check_web":"ウェブサイト確認","badges":"信頼バッジ","about":"概要",
           "tagline":"ソフトウェア、アプリ、VPN、ゲーム、パッケージの信頼スコア。独立。データ駆動。",
           "bottom":"nerq.ai &mdash; 全ソフトウェアの信頼スコア","privacy":"プライバシー","terms":"利用規約","contact":"お問い合わせ","cookies":"分析とキャッシュにCookieを使用しています。","accept":"承認"},
    "ar": {"search":"بحث","categories":"الفئات","compare":"مقارنة","sec_priv":"الأمان &amp; الخصوصية","dev_tools":"أدوات المطورين","more":"المزيد","crypto":"كريبتو","ai_tools":"أدوات الذكاء الاصطناعي","all_cats":"جميع الفئات","view_all":"عرض جميع 18 فئة &rarr;",
           "check_safety":"فحص الأمان","mobile_apps":"تطبيقات الجوال","games":"ألعاب","packages":"حزم","resources":"موارد","guides":"أدلة الأمان","check_web":"فحص الموقع","badges":"شارات الثقة","about":"حول",
           "tagline":"درجات الثقة للبرمجيات والتطبيقات وVPN والألعاب والحزم. مستقل. قائم على البيانات.",
           "bottom":"nerq.ai &mdash; درجات الثقة لجميع البرمجيات","privacy":"الخصوصية","terms":"الشروط","contact":"اتصل بنا","cookies":"نستخدم ملفات تعريف الارتباط للتحليلات والتخزين المؤقت.","accept":"قبول"},
    "de": {"search":"Suche","categories":"Kategorien","compare":"Vergleichen","sec_priv":"Sicherheit &amp; Datenschutz","dev_tools":"Entwicklertools","more":"Mehr","crypto":"Krypto","ai_tools":"KI-Tools","all_cats":"Alle Kategorien","view_all":"Alle 18 Kategorien &rarr;",
           "check_safety":"Sicherheit prüfen","mobile_apps":"Mobile Apps","games":"Spiele","packages":"Pakete","resources":"Ressourcen","guides":"Sicherheitsratgeber","check_web":"Website prüfen","badges":"Vertrauenssiegel","about":"Über",
           "tagline":"Vertrauenswerte für Software, Apps, VPNs, Spiele und Pakete. Unabhängig. Datenbasiert.",
           "bottom":"nerq.ai &mdash; Vertrauenswerte für alle Software","privacy":"Datenschutz","terms":"AGB","contact":"Kontakt","cookies":"Wir verwenden Cookies für Analysen und Caching.","accept":"Akzeptieren"},
    "es": {"search":"Buscar","categories":"Categorías","compare":"Comparar","sec_priv":"Seguridad &amp; Privacidad","dev_tools":"Herramientas de desarrollo","more":"Más","crypto":"Cripto","ai_tools":"Herramientas IA","all_cats":"Todas las categorías","view_all":"Ver las 18 categorías &rarr;",
           "check_safety":"Verificar seguridad","mobile_apps":"Apps móviles","games":"Juegos","packages":"Paquetes","resources":"Recursos","guides":"Guías de seguridad","check_web":"Verificar sitio web","badges":"Insignias de confianza","about":"Acerca de",
           "tagline":"Puntuaciones de confianza para software, apps, VPNs, juegos y paquetes. Independiente. Basado en datos.",
           "bottom":"nerq.ai &mdash; puntuaciones de confianza para todo el software","privacy":"Privacidad","terms":"Términos","contact":"Contacto","cookies":"Usamos cookies para análisis y caché.","accept":"Aceptar"},
    "fr": {"search":"Rechercher","categories":"Catégories","compare":"Comparer","sec_priv":"Sécurité &amp; Confidentialité","dev_tools":"Outils développeur","more":"Plus","crypto":"Crypto","ai_tools":"Outils IA","all_cats":"Toutes les catégories","view_all":"Voir les 18 catégories &rarr;",
           "check_safety":"Vérifier la sécurité","mobile_apps":"Apps mobiles","games":"Jeux","packages":"Paquets","resources":"Ressources","guides":"Guides de sécurité","check_web":"Vérifier le site","badges":"Badges de confiance","about":"À propos",
           "tagline":"Scores de confiance pour logiciels, apps, VPN, jeux et paquets. Indépendant. Basé sur les données.",
           "bottom":"nerq.ai &mdash; scores de confiance pour tous les logiciels","privacy":"Confidentialité","terms":"CGU","contact":"Contact","cookies":"Nous utilisons des cookies pour l'analyse et le cache.","accept":"Accepter"},
    "ko": {"search":"검색","categories":"카테고리","compare":"비교","sec_priv":"보안 &amp; 개인정보","dev_tools":"개발자 도구","more":"더보기","crypto":"암호화폐","ai_tools":"AI 도구","all_cats":"전체 카테고리","view_all":"18개 카테고리 모두 보기 &rarr;",
           "check_safety":"안전 확인","mobile_apps":"모바일 앱","games":"게임","packages":"패키지","resources":"리소스","guides":"보안 가이드","check_web":"웹사이트 확인","badges":"신뢰 배지","about":"소개",
           "tagline":"소프트웨어, 앱, VPN, 게임, 패키지의 신뢰 점수. 독립적. 데이터 기반.",
           "bottom":"nerq.ai &mdash; 모든 소프트웨어의 신뢰 점수","privacy":"개인정보","terms":"이용약관","contact":"문의","cookies":"분석 및 캐싱을 위해 쿠키를 사용합니다.","accept":"수락"},
    "zh": {"search":"搜索","categories":"分类","compare":"比较","sec_priv":"安全 &amp; 隐私","dev_tools":"开发者工具","more":"更多","crypto":"加密货币","ai_tools":"AI工具","all_cats":"所有分类","view_all":"查看全部18个分类 &rarr;",
           "check_safety":"安全检查","mobile_apps":"移动应用","games":"游戏","packages":"软件包","resources":"资源","guides":"安全指南","check_web":"检查网站","badges":"信任徽章","about":"关于",
           "tagline":"软件、应用、VPN、游戏和软件包的信任评分。独立。数据驱动。",
           "bottom":"nerq.ai &mdash; 所有软件的信任评分","privacy":"隐私","terms":"条款","contact":"联系","cookies":"我们使用Cookie进行分析和缓存。","accept":"接受"},
    "pt": {"search":"Pesquisar","categories":"Categorias","compare":"Comparar","check_safety":"Verificar segurança","mobile_apps":"Apps móveis","games":"Jogos","packages":"Pacotes","resources":"Recursos","guides":"Guias de segurança","about":"Sobre","privacy":"Privacidade","terms":"Termos","contact":"Contato","cookies":"Usamos cookies para análise e cache.","accept":"Aceitar","sec_priv":"Segurança &amp; Privacidade","dev_tools":"Ferramentas de desenvolvimento","more":"Mais","crypto":"Cripto","ai_tools":"Ferramentas IA","all_cats":"Todas as categorias","view_all":"Ver todas as 18 categorias &rarr;","tagline":"Pontuações de confiança para software. Independente. Baseado em dados.","bottom":"nerq.ai &mdash; pontuações de confiança","check_web":"Verificar site","badges":"Selos de confiança"},
    "nl": {"search":"Zoeken","categories":"Categorieën","compare":"Vergelijken","sec_priv":"Beveiliging &amp; Privacy","dev_tools":"Ontwikkelaarstools","more":"Meer","crypto":"Crypto","ai_tools":"AI-tools","all_cats":"Alle categorieën","view_all":"Bekijk alle 18 categorieën &rarr;",
           "check_safety":"Veiligheid controleren","mobile_apps":"Mobiele apps","games":"Games","packages":"Pakketten","resources":"Bronnen","guides":"Veiligheidsgidsen","check_web":"Website controleren","badges":"Vertrouwensbadges","about":"Over",
           "tagline":"Vertrouwensscores voor software, apps, VPN's, games en pakketten. Onafhankelijk. Datagedreven.",
           "bottom":"nerq.ai &mdash; vertrouwensscores voor alle software","privacy":"Privacy","terms":"Voorwaarden","contact":"Contact","cookies":"We gebruiken cookies voor analyse en caching.","accept":"Accepteren"},
    "id": {"search":"Cari","categories":"Kategori","compare":"Bandingkan","sec_priv":"Keamanan &amp; Privasi","dev_tools":"Alat Pengembang","more":"Lainnya","crypto":"Kripto","ai_tools":"Alat AI","all_cats":"Semua Kategori","view_all":"Lihat semua 18 kategori &rarr;",
           "check_safety":"Periksa Keamanan","mobile_apps":"Aplikasi Seluler","games":"Game","packages":"Paket","resources":"Sumber Daya","guides":"Panduan Keamanan","check_web":"Periksa Situs","badges":"Lencana Kepercayaan","about":"Tentang",
           "tagline":"Skor kepercayaan untuk perangkat lunak, aplikasi, VPN, game, dan paket. Independen. Berbasis data.",
           "bottom":"nerq.ai &mdash; skor kepercayaan untuk semua perangkat lunak","privacy":"Privasi","terms":"Ketentuan","contact":"Kontak","cookies":"Kami menggunakan cookie untuk analitik dan caching.","accept":"Terima"},
    "cs": {"search":"Hledat","categories":"Kategorie","compare":"Porovnat","sec_priv":"Bezpečnost &amp; Soukromí","dev_tools":"Vývojářské nástroje","more":"Více","crypto":"Krypto","ai_tools":"AI nástroje","all_cats":"Všechny kategorie","view_all":"Zobrazit všech 18 kategorií &rarr;",
           "check_safety":"Zkontrolovat bezpečnost","mobile_apps":"Mobilní aplikace","games":"Hry","packages":"Balíčky","resources":"Zdroje","guides":"Bezpečnostní průvodci","check_web":"Zkontrolovat web","badges":"Odznaky důvěry","about":"O nás",
           "tagline":"Skóre důvěry pro software, aplikace, VPN, hry a balíčky. Nezávislé. Založeno na datech.",
           "bottom":"nerq.ai &mdash; skóre důvěry pro veškerý software","privacy":"Soukromí","terms":"Podmínky","contact":"Kontakt","cookies":"Používáme cookies pro analýzu a ukládání do mezipaměti.","accept":"Přijmout"},
    "th": {"search":"ค้นหา","categories":"หมวดหมู่","compare":"เปรียบเทียบ","sec_priv":"ความปลอดภัย &amp; ความเป็นส่วนตัว","dev_tools":"เครื่องมือนักพัฒนา","more":"เพิ่มเติม","crypto":"คริปโต","ai_tools":"เครื่องมือ AI","all_cats":"หมวดหมู่ทั้งหมด","view_all":"ดูทั้ง 18 หมวดหมู่ &rarr;",
           "check_safety":"ตรวจสอบความปลอดภัย","mobile_apps":"แอปมือถือ","games":"เกม","packages":"แพ็คเกจ","resources":"ทรัพยากร","guides":"คู่มือความปลอดภัย","check_web":"ตรวจสอบเว็บไซต์","badges":"ป้ายความน่าเชื่อถือ","about":"เกี่ยวกับ",
           "tagline":"คะแนนความเชื่อถือสำหรับซอฟต์แวร์ แอป VPN เกม และแพ็คเกจ เป็นอิสระ ใช้ข้อมูลเป็นหลัก",
           "bottom":"nerq.ai &mdash; คะแนนความเชื่อถือสำหรับซอฟต์แวร์ทั้งหมด","privacy":"ความเป็นส่วนตัว","terms":"ข้อกำหนด","contact":"ติดต่อ","cookies":"เราใช้คุกกี้สำหรับการวิเคราะห์และแคช","accept":"ยอมรับ"},
    "ro": {"search":"Caută","categories":"Categorii","compare":"Compară","sec_priv":"Securitate &amp; Confidențialitate","dev_tools":"Instrumente dezvoltatori","more":"Mai mult","crypto":"Cripto","ai_tools":"Instrumente AI","all_cats":"Toate categoriile","view_all":"Vezi toate cele 18 categorii &rarr;",
           "check_safety":"Verifică securitatea","mobile_apps":"Aplicații mobile","games":"Jocuri","packages":"Pachete","resources":"Resurse","guides":"Ghiduri de securitate","check_web":"Verifică site-ul","badges":"Insigne de încredere","about":"Despre",
           "tagline":"Scoruri de încredere pentru software, aplicații, VPN, jocuri și pachete. Independent. Bazat pe date.",
           "bottom":"nerq.ai &mdash; scoruri de încredere pentru tot software-ul","privacy":"Confidențialitate","terms":"Termeni","contact":"Contact","cookies":"Folosim cookie-uri pentru analiză și cache.","accept":"Acceptă"},
    "tr": {"search":"Ara","categories":"Kategoriler","compare":"Karşılaştır","sec_priv":"Güvenlik &amp; Gizlilik","dev_tools":"Geliştirici Araçları","more":"Daha fazla","crypto":"Kripto","ai_tools":"AI Araçları","all_cats":"Tüm Kategoriler","view_all":"Tüm 18 kategoriyi gör &rarr;",
           "check_safety":"Güvenliği kontrol et","mobile_apps":"Mobil Uygulamalar","games":"Oyunlar","packages":"Paketler","resources":"Kaynaklar","guides":"Güvenlik Rehberleri","check_web":"Siteyi kontrol et","badges":"Güven Rozetleri","about":"Hakkında",
           "tagline":"Yazılım, uygulama, VPN, oyun ve paketler için güven puanları. Bağımsız. Veri odaklı.",
           "bottom":"nerq.ai &mdash; tüm yazılımlar için güven puanları","privacy":"Gizlilik","terms":"Koşullar","contact":"İletişim","cookies":"Analiz ve önbelleğe alma için çerezler kullanıyoruz.","accept":"Kabul et"},
    "hi": {"search":"खोजें","categories":"श्रेणियाँ","compare":"तुलना करें","sec_priv":"सुरक्षा &amp; गोपनीयता","dev_tools":"डेवलपर टूल्स","more":"और देखें","crypto":"क्रिप्टो","ai_tools":"AI उपकरण","all_cats":"सभी श्रेणियाँ","view_all":"सभी 18 श्रेणियाँ देखें &rarr;",
           "check_safety":"सुरक्षा जाँचें","mobile_apps":"मोबाइल ऐप्स","games":"गेम्स","packages":"पैकेज","resources":"संसाधन","guides":"सुरक्षा गाइड","check_web":"वेबसाइट जाँचें","badges":"विश्वास बैज","about":"हमारे बारे में",
           "tagline":"सॉफ़्टवेयर, ऐप्स, VPN, गेम्स और पैकेज के लिए विश्वास स्कोर। स्वतंत्र। डेटा-संचालित।",
           "bottom":"nerq.ai &mdash; सभी सॉफ़्टवेयर के लिए विश्वास स्कोर","privacy":"गोपनीयता","terms":"शर्तें","contact":"संपर्क","cookies":"हम विश्लेषण और कैशिंग के लिए कुकीज़ का उपयोग करते हैं।","accept":"स्वीकार करें"},
    "ru": {"search":"Поиск","categories":"Категории","compare":"Сравнить","sec_priv":"Безопасность &amp; Конфиденциальность","dev_tools":"Инструменты разработчика","more":"Ещё","crypto":"Крипто","ai_tools":"ИИ-инструменты","all_cats":"Все категории","view_all":"Все 18 категорий &rarr;",
           "check_safety":"Проверить безопасность","mobile_apps":"Мобильные приложения","games":"Игры","packages":"Пакеты","resources":"Ресурсы","guides":"Руководства по безопасности","check_web":"Проверить сайт","badges":"Знаки доверия","about":"О нас",
           "tagline":"Оценки доверия для ПО, приложений, VPN, игр и пакетов. Независимо. На основе данных.",
           "bottom":"nerq.ai &mdash; оценки доверия для всего ПО","privacy":"Конфиденциальность","terms":"Условия","contact":"Контакт","cookies":"Мы используем файлы cookie для аналитики и кэширования.","accept":"Принять"},
    "pl": {"search":"Szukaj","categories":"Kategorie","compare":"Porównaj","sec_priv":"Bezpieczeństwo &amp; Prywatność","dev_tools":"Narzędzia deweloperskie","more":"Więcej","crypto":"Krypto","ai_tools":"Narzędzia AI","all_cats":"Wszystkie kategorie","view_all":"Zobacz wszystkie 18 kategorii &rarr;",
           "check_safety":"Sprawdź bezpieczeństwo","mobile_apps":"Aplikacje mobilne","games":"Gry","packages":"Pakiety","resources":"Zasoby","guides":"Przewodniki bezpieczeństwa","check_web":"Sprawdź stronę","badges":"Odznaki zaufania","about":"O nas",
           "tagline":"Oceny zaufania dla oprogramowania, aplikacji, VPN, gier i pakietów. Niezależne. Oparte na danych.",
           "bottom":"nerq.ai &mdash; oceny zaufania dla całego oprogramowania","privacy":"Prywatność","terms":"Regulamin","contact":"Kontakt","cookies":"Używamy plików cookie do analiz i buforowania.","accept":"Akceptuj"},
    "it": {"search":"Cerca","categories":"Categorie","compare":"Confronta","sec_priv":"Sicurezza &amp; Privacy","dev_tools":"Strumenti sviluppatore","more":"Altro","crypto":"Cripto","ai_tools":"Strumenti IA","all_cats":"Tutte le categorie","view_all":"Vedi tutte le 18 categorie &rarr;",
           "check_safety":"Verifica sicurezza","mobile_apps":"App mobili","games":"Giochi","packages":"Pacchetti","resources":"Risorse","guides":"Guide alla sicurezza","check_web":"Verifica sito","badges":"Badge di fiducia","about":"Chi siamo",
           "tagline":"Punteggi di fiducia per software, app, VPN, giochi e pacchetti. Indipendente. Basato sui dati.",
           "bottom":"nerq.ai &mdash; punteggi di fiducia per tutto il software","privacy":"Privacy","terms":"Termini","contact":"Contatti","cookies":"Utilizziamo i cookie per analisi e caching.","accept":"Accetta"},
    "da": {"search":"Søg","categories":"Kategorier","compare":"Sammenlign","sec_priv":"Sikkerhed &amp; Privatliv","dev_tools":"Udviklerværktøjer","more":"Mere","crypto":"Krypto","ai_tools":"AI-værktøjer","all_cats":"Alle kategorier","view_all":"Se alle 18 kategorier &rarr;",
           "check_safety":"Tjek sikkerhed","mobile_apps":"Mobilapps","games":"Spil","packages":"Pakker","resources":"Ressourcer","guides":"Sikkerhedsguider","check_web":"Tjek hjemmeside","badges":"Tillidsbadges","about":"Om",
           "tagline":"Tillidsscorer for software, apps, VPN, spil og pakker. Uafhængig. Datadrevet.",
           "bottom":"nerq.ai &mdash; tillidsscorer for al software","privacy":"Privatliv","terms":"Vilkår","contact":"Kontakt","cookies":"Vi bruger cookies til analyse og caching.","accept":"Acceptér"},
    "no": {"search":"Søk","categories":"Kategorier","compare":"Sammenlign","sec_priv":"Sikkerhet &amp; Personvern","dev_tools":"Utviklerverktøy","more":"Mer","crypto":"Krypto","ai_tools":"AI-verktøy","all_cats":"Alle kategorier","view_all":"Se alle 18 kategorier &rarr;",
           "check_safety":"Sjekk sikkerhet","mobile_apps":"Mobilapper","games":"Spill","packages":"Pakker","resources":"Ressurser","guides":"Sikkerhetsguider","check_web":"Sjekk nettsted","badges":"Tillitsmerker","about":"Om",
           "tagline":"Tillitspoeng for programvare, apper, VPN, spill og pakker. Uavhengig. Datadrevet.",
           "bottom":"nerq.ai &mdash; tillitspoeng for all programvare","privacy":"Personvern","terms":"Vilkår","contact":"Kontakt","cookies":"Vi bruker informasjonskapsler for analyse og hurtiglagring.","accept":"Godta"},
}

def _u(key, lang="en"):
    """Get UI string for nav/footer. Falls back to English."""
    return _UI.get(lang, {}).get(key) or _UI["en"].get(key, key)


def render_nav(lang="en", current_category=None):
    """Language-aware navigation bar."""
    u = lambda k: _u(k, lang)
    lp = f"/{lang}" if lang != "en" else ""
    return f"""<nav class="nav"><div class="nav-inner">
<a href="{lp}/" class="nav-logo">Nerq<span>Trust Intelligence</span></a>
<div class="nav-links">
<a href="{lp}/discover">{u("search")}</a>
<div class="nav-dropdown" style="position:relative;display:inline-block">
<a href="{lp}/categories" class="nav-drop-trigger" style="cursor:pointer">{u("categories")} &#9662;</a>
<div class="nav-drop-menu" style="display:none;position:absolute;top:100%;left:-60px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px 20px;min-width:420px;box-shadow:0 8px 24px rgba(0,0,0,.1);z-index:100;line-height:1.8">
<div style="display:grid;grid-template-columns:1fr 1fr;gap:0 24px">
<div><strong style="font-size:11px;text-transform:uppercase;color:#64748b;letter-spacing:.05em">{u("sec_priv")}</strong><br>
<a href="{lp}/vpns">VPNs</a><br><a href="{lp}/apps">Apps</a><br><a href="{lp}/games">{u("games")}</a></div>
<div><strong style="font-size:11px;text-transform:uppercase;color:#64748b;letter-spacing:.05em">{u("dev_tools")}</strong><br>
<a href="{lp}/npm">npm</a><br><a href="{lp}/pypi">PyPI</a><br><a href="{lp}/crates">Rust Crates</a><br><a href="{lp}/wordpress-plugins">WordPress</a><br><a href="{lp}/packagist">Packagist</a><br><a href="{lp}/extensions">VS Code</a><br><a href="{lp}/gems">RubyGems</a><br><a href="{lp}/homebrew">Homebrew</a></div>
<div style="margin-top:8px"><strong style="font-size:11px;text-transform:uppercase;color:#64748b;letter-spacing:.05em">{u("more")}</strong><br>
<a href="{lp}/crypto">{u("crypto")}</a><br><a href="{lp}/discover">{u("ai_tools")}</a><br><a href="{lp}/categories">{u("all_cats")}</a></div>
</div>
<div style="margin-top:10px;padding-top:8px;border-top:1px solid #e2e8f0;font-size:12px"><a href="{lp}/categories">{u("view_all")}</a></div>
</div>
</div>
<a href="{lp}/compare">{u("compare")}</a>
<a href="/nerq/docs">API</a>
""" + """<select id="nerq-lang" onchange="(function(s){var v=s.value,p=location.pathname;if(v==='en'){p=p.replace(/^\\/[a-z]{2}\\//,'/');location.href=p||'/';}else{var m=p.match(/^\\/([a-z]{2})\\//);if(m){p=p.replace(/^\\/[a-z]{2}\\//,'/'+v+'/');}else if(p==='/'){p='/'+v+'/';}else{p='/'+v+p;}location.href=p;}})(this)" style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:2px 4px;font-size:12px;color:#64748b;cursor:pointer">
<option value="en">EN</option><option value="es">ES</option><option value="de">DE</option><option value="fr">FR</option><option value="ja">JA</option><option value="pt">PT</option><option value="id">ID</option><option value="cs">CS</option><option value="th">TH</option><option value="ro">RO</option><option value="tr">TR</option><option value="hi">HI</option><option value="ru">RU</option><option value="pl">PL</option><option value="it">IT</option><option value="ko">KO</option><option value="vi">VI</option><option value="nl">NL</option><option value="sv">SV</option><option value="zh">ZH</option><option value="da">DA</option><option value="no">NO</option>
</select>
</div>
</div></nav>
<style>.nav-dropdown:hover .nav-drop-menu{display:block!important}@media(max-width:768px){.nav-drop-menu{left:0!important;min-width:90vw!important}.nav-drop-menu div[style*="grid"]{grid-template-columns:1fr!important}}</style>
<script>(function(){var m=location.pathname.match(/^\\/([a-z]{2})\\//);if(m){var s=document.getElementById('nerq-lang');if(s)s.value=m[1];}})();</script>"""


def render_footer(lang="en"):
    """Language-aware footer."""
    u = lambda k: _u(k, lang)
    lp = f"/{lang}" if lang != "en" else ""
    return f"""<div class="cross-links" style="margin-top:2rem;padding-top:1.5rem;border-top:1px solid #e2e8f0">
<a href="{lp}/apps" class="cross-link">Apps</a>
<a href="{lp}/npm" class="cross-link">npm</a>
<a href="{lp}/pypi" class="cross-link">PyPI</a>
<a href="{lp}/vpns" class="cross-link">VPNs</a>
<a href="{lp}/games" class="cross-link">{u("games")}</a>
<a href="{lp}/categories" class="cross-link">{u("all_cats")}</a>
<a href="{lp}/compare" class="cross-link">{u("compare")}</a>
</div><footer class="footer"><div class="wide-container">
<div class="footer-grid">
<div class="footer-col"><h4>{u("check_safety")}</h4>
<a href="{lp}/apps">{u("mobile_apps")}</a><a href="{lp}/vpns">VPNs</a><a href="{lp}/games">{u("games")}</a>
<a href="{lp}/wordpress-plugins">WordPress</a><a href="{lp}/categories">{u("all_cats")}</a></div>
<div class="footer-col"><h4>{u("packages")}</h4>
<a href="{lp}/npm">npm</a><a href="{lp}/pypi">PyPI</a><a href="{lp}/crates">Rust Crates</a>
<a href="{lp}/packagist">Packagist</a><a href="{lp}/extensions">VS Code</a></div>
<div class="footer-col"><h4>{u("resources")}</h4>
<a href="{lp}/guides">{u("guides")}</a><a href="{lp}/compare">{u("compare")}</a><a href="{lp}/check-website">{u("check_web")}</a>
<a href="/nerq/docs">API</a><a href="/badges">{u("badges")}</a><a href="/llms.txt">llms.txt</a></div>
<div class="footer-col"><h4>Nerq</h4>
<p style="font-size:12px;color:#94a3b8;line-height:1.5">{u("tagline")}</p>
<a href="{lp}/about" style="margin-top:6px">{u("about")}</a><a href="https://zarq.ai">zarq.ai (crypto)</a></div>
</div>
<div class="footer-bottom">{u("bottom")} &middot; 7.5M+ entities &middot; 26 registries &middot; 22 languages &middot; <a href="/privacy" style="color:#94a3b8">{u("privacy")}</a> &middot; <a href="/terms" style="color:#94a3b8">{u("terms")}</a> &middot; <a href="mailto:hello@nerq.ai" style="color:#94a3b8">hello@nerq.ai</a></div>
</div></footer>
<div id="ck-banner" style="position:fixed;bottom:0;left:0;right:0;background:#1e293b;color:#e2e8f0;padding:10px 20px;display:flex;justify-content:space-between;align-items:center;z-index:9999;font-size:13px">
<span>{u("cookies")} <a href="/privacy" style="color:#38bdf8">{u("privacy")}</a></span>
<button onclick="this.parentElement.style.display='none';localStorage.setItem('ck_ok','1')" style="background:#38bdf8;color:#0f172a;border:none;padding:6px 16px;border-radius:4px;cursor:pointer;font-weight:600;font-size:13px">{u("accept")}</button>
</div>
<script>if(localStorage.getItem('ck_ok'))document.getElementById('ck-banner').style.display='none'</script>"""


def render_verdict_box(name, category, score, grade, verdict, updated=None):
    """Visual trust score verdict box. aria-hidden since info is in first paragraph."""
    sc = float(score) if score is not None else 0
    sc_cls = _score_class(sc)
    gr_cls = _grade_bg(grade)
    upd = updated or _TODAY
    return f"""<div class="verdict" aria-hidden="true">
<div class="verdict-score">
<div class="verdict-num {sc_cls}">{sc:.0f}</div>
<div class="verdict-of">/100</div>
<span class="verdict-grade {gr_cls}">{_esc(grade or 'N/A')}</span>
</div>
<div class="verdict-info">
<div class="verdict-name">{_esc(name)}</div>
<div class="verdict-cat">{_esc(category or '')}</div>
<div class="verdict-text {sc_cls}">{_esc(verdict or '')}</div>
<div class="verdict-date">Last analyzed: {_esc(upd)}</div>
</div>
</div>"""


def render_breadcrumb(items):
    """Breadcrumb nav. items = [(url, label), ...]. Last item has no url.
    Also returns BreadcrumbList JSON-LD."""
    bc_html = '<nav class="breadcrumb" aria-label="Breadcrumb">'
    bc_items = []
    for i, (url, label) in enumerate(items):
        if i > 0:
            bc_html += '<span class="sep">&rsaquo;</span>'
        if url:
            bc_html += f'<a href="{_esc(url)}">{_esc(label)}</a>'
        else:
            bc_html += f'<span>{_esc(label)}</span>'
        bc_items.append(f'{{"@type":"ListItem","position":{i+1},"name":"{_esc(label)}","item":"{_esc(url or "")}"}}')
    bc_html += '</nav>'

    ld = f"""<script type="application/ld+json">{{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{",".join(bc_items)}]}}</script>"""
    return bc_html + "\n" + ld


def render_trust_breakdown(scores):
    """Trust score breakdown bars. scores = dict of {label: score}."""
    if not scores:
        return ""
    html = '<div class="section"><h2 class="section-title">Trust Score Breakdown</h2>'
    for label, val in scores.items():
        v = float(val) if val is not None else 0
        cls = _score_class(v)
        color = {"sc-high": "#16a34a", "sc-good": "#22c55e", "sc-mid": "#f59e0b", "sc-low": "#ef4444", "sc-crit": "#991b1b"}.get(cls, "#94a3b8")
        html += f"""<div class="breakdown-item">
<span class="breakdown-label">{_esc(label)}</span>
<div class="breakdown-bar"><div class="breakdown-fill" style="width:{v:.0f}%;background:{color}"></div></div>
<span class="breakdown-val {cls}">{v:.0f}</span>
</div>"""
    html += '</div>'
    return html


def render_cross_links(entity_slug, patterns=None):
    """Pill-button links to other URL patterns for the same entity."""
    if not entity_slug:
        return ""
    s = _esc(entity_slug)
    default_patterns = [
        (f"/is-{s}-safe", "Safety"),
        (f"/is-{s}-legit", "Legit?"),
        (f"/is-{s}-a-scam", "Scam?"),
        (f"/privacy/{s}", "Privacy"),
        (f"/review/{s}", "Review"),
        (f"/pros-cons/{s}", "Pros & Cons"),
        (f"/is-{s}-safe-for-kids", "Safe for Kids?"),
        (f"/alternatives/{s}", "Alternatives"),
        (f"/who-owns/{s}", "Who Owns?"),
        (f"/what-is/{s}", "What Is?"),
    ]
    links = patterns or default_patterns
    html = '<nav class="cross-links" aria-label="Related analyses">'
    for url, label in links:
        html += f'<a href="{url}" class="cross-link">{_esc(label)}</a>'
    html += '</nav>'
    return html


def render_faq(qas):
    """FAQ section using native <details>/<summary>. qas = [(question, answer), ...]."""
    if not qas:
        return ""
    html = '<div class="section faq"><h2 class="section-title">FAQ</h2>'
    for q, a in qas:
        html += f"""<details>
<summary>{_esc(q)}</summary>
<div class="faq-a">{a}</div>
</details>"""
    html += '</div>'
    return html


# render_footer defined above with full i18n support


# ── Backward-compatible helpers ────────────────────────────

def nerq_head(title: str, description: str = "", canonical: str = "") -> str:
    """Legacy: generate <head> with inline CSS. Use render_head() for new pages."""
    canon = f'<link rel="canonical" href="{_esc(canonical)}">' if canonical else ""
    desc = f'<meta name="description" content="{_esc(description)}">' if description else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
{desc}
{canon}
{NERQ_CSS}
<link rel="stylesheet" href="/static/nerq.css?v={_CSS_VERSION}">
</head>
<body>
{NERQ_NAV}"""


def nerq_page(title: str, body: str, description: str = "", canonical: str = "") -> str:
    """Legacy: wrap body in a full page. Use render_head() + render_footer() for new pages."""
    return f"""{nerq_head(title, description, canonical)}
<main class="container" style="padding-top:20px;padding-bottom:40px">
{body}
</main>
{NERQ_FOOTER}
</body>
</html>"""
