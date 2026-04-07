"""
Localized Routes — 20 languages x 36 patterns
================================================
Serves localized versions of all Nerq pages.
URL pattern: /{lang}/{localized-pattern-slug}
Example: /es/es-tiktok-seguro, /fr/tiktok-est-il-sur, /de/ist-tiktok-sicher

Usage:
    from agentindex.localized_routes import mount_localized_routes
    mount_localized_routes(app)
"""

import html as html_mod
import logging
import re
import time
from datetime import date

from fastapi.responses import HTMLResponse, Response
from sqlalchemy.sql import text

from agentindex.db.models import get_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER
from agentindex.translations import TRANSLATIONS, URL_PATTERNS

logger = logging.getLogger("nerq.localized")

SITE = "https://nerq.ai"
TODAY = date.today().isoformat()
YEAR = date.today().year
MY = date.today().strftime("%B %Y")

SUPPORTED_LANGS = list(URL_PATTERNS.keys())
SUPPORTED_LANGS.remove("en")  # English is default, not under /en/

_cache = {}
CACHE_TTL = 3600


def _c(k):
    e = _cache.get(k)
    return e[1] if e and (time.time() - e[0]) < CACHE_TTL else None


def _sc(k, v):
    _cache[k] = (time.time(), v)
    return v


def _esc(t):
    return html_mod.escape(str(t)) if t else ""


def _resolve(slug):
    """Resolve entity using centralized resolution (software_registry + agents)."""
    from agentindex.agent_safety_pages import _resolve_entity, _lookup_agent

    resolved = _resolve_entity(slug)
    if not resolved:
        norm = slug.lower().replace("-", "").replace("_", "").replace(" ", "")
        if norm != slug.lower():
            resolved = _resolve_entity(norm)

    if resolved:
        # Apply score floors (same as English pages in _render_agent_page)
        _score = resolved.get("trust_score") or 50
        _slug_l = slug.lower()
        from agentindex.agent_safety_pages import _render_agent_page as _rap
        # Import score floors from the English template
        try:
            import agentindex.agent_safety_pages as _asp_mod
            # Find _SCORE_FLOORS in the render function's local scope — it's defined inline
            # Use the same dict directly
            _floors = {
                "openai": 85, "anthropic": 85, "tensorflow": 88, "pytorch": 88,
                "transformers": 87, "numpy": 90, "pandas": 90, "scikit-learn": 88,
                "react": 90, "next.js": 88, "nextjs": 88, "vercel": 85,
                "stripe": 88, "fastapi": 86, "flask": 85, "django": 88,
                "express": 86, "axios": 84, "lodash": 88, "webpack": 82,
                "typescript": 90, "eslint": 85, "prettier": 84, "jest": 86,
                "vue": 88, "angular": 87, "svelte": 85, "tailwindcss": 86,
                "requests": 88, "boto3": 86, "sqlalchemy": 87,
                "chatgpt": 82, "claude": 82, "gemini": 80, "github copilot": 80,
                "nordvpn": 85, "windsurf": 75, "cursor": 78, "replit": 76,
            }
            _floor = _floors.get(_slug_l, 0) or _floors.get(resolved.get("name", "").lower(), 0)
            if _floor and _score < _floor:
                _score = float(_floor)
        except Exception:
            pass
        _grade = resolved.get("trust_grade") or "D"
        if _score >= 90: _grade = "A+"
        elif _score >= 85: _grade = "A"
        elif _score >= 80: _grade = "A-"
        elif _score >= 75: _grade = "B+"
        elif _score >= 70: _grade = "B"
        elif _score >= 65: _grade = "B-"
        elif _score >= 60: _grade = "C+"
        elif _score >= 55: _grade = "C"
        return {
            "name": resolved.get("name", slug),
            "score": _score,
            "grade": _grade,
            "stars": resolved.get("stars", 0),
            "downloads": resolved.get("stars", 0),
            "desc": resolved.get("description", ""),
            "cat": resolved.get("category", ""),
            "author": resolved.get("author", "Unknown"),
            "url": resolved.get("source_url", ""),
            "license": "",
            "type": resolved.get("source", ""),
            "sec": resolved.get("security_score"),
            "pop": resolved.get("popularity_score"),
            "act": resolved.get("maintenance_score"),
            "doc": resolved.get("quality_score"),
        }

    agent = _lookup_agent(slug)
    if agent:
        return {
            "name": agent.get("name", slug), "score": agent.get("trust_score") or 0,
            "grade": agent.get("trust_grade", "N/A"), "stars": agent.get("stars", 0),
            "downloads": 0, "desc": agent.get("description", ""),
            "cat": agent.get("category", ""), "author": agent.get("author", "Unknown"),
            "url": agent.get("source_url", ""), "license": "", "type": "",
        }
    return None


def _find_alts(name, cat, limit=3):
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT name, trust_score_v2, trust_grade FROM entity_lookup
            WHERE is_active = true AND name_lower != :n AND category = :cat AND trust_score_v2 IS NOT NULL
            ORDER BY trust_score_v2 DESC LIMIT :lim
        """), {"n": name.lower(), "cat": cat, "lim": limit}).fetchall()
        return [{"name": r[0].split("/")[-1], "score": r[1] or 0, "grade": r[2] or "D"} for r in rows]
    finally:
        session.close()


def _gc(g):
    if not g:
        return "#6b7280"
    return {"A": "#16a34a", "B": "#0d9488", "C": "#ca8a04", "D": "#f97316"}.get(g[0].upper(), "#dc2626")


def _fmt(n):
    if n is None:
        return "0"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(int(n))


# ── Travel + Charity translations for localized pages ──────────
_TRAVEL_T = {
    "en": {"score_title": "Safety Score Breakdown", "crime": "Crime & Personal Safety", "political": "Political Stability", "health": "Health & Medical", "disaster": "Natural Disaster Risk", "infra": "Infrastructure & Transport", "rights": "Traveler Rights", "safe_visit": "Is {name} safe to visit?", "safe_women": "Is {name} safe for women?", "safe_solo": "Is {name} safe for solo travelers?", "safe_lgbtq": "Is {name} safe for LGBTQ+ travelers?", "safe_families": "Is {name} safe for families?", "key_risks": "Key Safety Risks", "practical": "Practical Travel Information", "advisory": "Travel Advisory", "similar": "Similar Destinations", "methodology": "How We Calculate Scores"},
    "sv": {"score_title": "Säkerhetsbetyg i Detalj", "crime": "Brottslighet & Personlig Säkerhet", "political": "Politisk Stabilitet", "health": "Hälsa & Sjukvård", "disaster": "Naturkatastrofrisk", "infra": "Infrastruktur & Transport", "rights": "Resenärers Rättigheter", "safe_visit": "Är {name} säkert att besöka?", "safe_women": "Är {name} säkert för kvinnor?", "safe_solo": "Är {name} säkert för soloresenärer?", "safe_lgbtq": "Är {name} säkert för HBTQ+-resenärer?", "safe_families": "Är {name} säkert för familjer?", "key_risks": "Viktiga Säkerhetsrisker", "practical": "Praktisk Reseinformation", "advisory": "Reseråd", "similar": "Liknande Destinationer", "methodology": "Hur Vi Beräknar Betyg"},
    "es": {"score_title": "Desglose de Seguridad", "crime": "Crimen y Seguridad Personal", "political": "Estabilidad Política", "health": "Salud y Asistencia Médica", "disaster": "Riesgo de Desastres Naturales", "infra": "Infraestructura y Transporte", "rights": "Derechos del Viajero", "safe_visit": "¿Es seguro visitar {name}?", "safe_women": "¿Es {name} seguro para mujeres?", "safe_solo": "¿Es {name} seguro para viajeros solos?", "safe_lgbtq": "¿Es {name} seguro para viajeros LGBTQ+?", "safe_families": "¿Es {name} seguro para familias?", "key_risks": "Principales Riesgos", "practical": "Información Práctica", "advisory": "Aviso de Viaje", "similar": "Destinos Similares", "methodology": "Cómo Calculamos"},
    "fr": {"score_title": "Détail du Score de Sécurité", "crime": "Criminalité et Sécurité", "political": "Stabilité Politique", "health": "Santé et Soins", "disaster": "Risques de Catastrophes", "infra": "Infrastructure et Transport", "rights": "Droits des Voyageurs", "safe_visit": "{name} est-il sûr à visiter?", "safe_women": "{name} est-il sûr pour les femmes?", "safe_solo": "{name} est-il sûr pour voyager seul?", "safe_lgbtq": "{name} est-il sûr pour les voyageurs LGBTQ+?", "safe_families": "{name} est-il sûr pour les familles?", "key_risks": "Risques Principaux", "practical": "Informations Pratiques", "advisory": "Conseil aux Voyageurs", "similar": "Destinations Similaires", "methodology": "Comment Nous Calculons"},
    "de": {"score_title": "Sicherheitsbewertung im Detail", "crime": "Kriminalität & Sicherheit", "political": "Politische Stabilität", "health": "Gesundheit & Medizin", "disaster": "Naturkatastrophenrisiko", "infra": "Infrastruktur & Verkehr", "rights": "Reiserechte", "safe_visit": "Ist {name} sicher zu besuchen?", "safe_women": "Ist {name} sicher für Frauen?", "safe_solo": "Ist {name} sicher für Alleinreisende?", "safe_lgbtq": "Ist {name} sicher für LGBTQ+-Reisende?", "safe_families": "Ist {name} sicher für Familien?", "key_risks": "Wichtige Sicherheitsrisiken", "practical": "Praktische Reiseinformationen", "advisory": "Reisehinweis", "similar": "Ähnliche Reiseziele", "methodology": "Wie Wir Bewerten"},
    "pt": {"score_title": "Detalhes da Pontuação de Segurança", "crime": "Crime e Segurança Pessoal", "political": "Estabilidade Política", "health": "Saúde e Assistência Médica", "disaster": "Risco de Desastres Naturais", "infra": "Infraestrutura e Transporte", "rights": "Direitos do Viajante", "safe_visit": "{name} é seguro para visitar?", "safe_women": "{name} é seguro para mulheres?", "safe_solo": "{name} é seguro para viajantes solo?", "safe_lgbtq": "{name} é seguro para viajantes LGBTQ+?", "safe_families": "{name} é seguro para famílias?", "key_risks": "Principais Riscos", "practical": "Informações Práticas", "advisory": "Aviso de Viagem", "similar": "Destinos Semelhantes", "methodology": "Como Calculamos"},
    "it": {"score_title": "Dettaglio Punteggio Sicurezza", "crime": "Criminalità e Sicurezza", "political": "Stabilità Politica", "health": "Salute e Assistenza Medica", "disaster": "Rischio Disastri Naturali", "infra": "Infrastruttura e Trasporti", "rights": "Diritti dei Viaggiatori", "safe_visit": "{name} è sicuro da visitare?", "safe_women": "{name} è sicuro per le donne?", "safe_solo": "{name} è sicuro per viaggiatori singoli?", "safe_lgbtq": "{name} è sicuro per viaggiatori LGBTQ+?", "safe_families": "{name} è sicuro per le famiglie?", "key_risks": "Rischi Principali", "practical": "Informazioni Pratiche", "advisory": "Avviso di Viaggio", "similar": "Destinazioni Simili", "methodology": "Come Calcoliamo"},
    "ja": {"score_title": "安全スコアの内訳", "crime": "犯罪・個人の安全", "political": "政治的安定性", "health": "健康・医療", "disaster": "自然災害リスク", "infra": "インフラ・交通", "rights": "旅行者の権利", "safe_visit": "{name}は訪問しても安全ですか？", "safe_women": "{name}は女性にとって安全ですか？", "safe_solo": "{name}は一人旅に安全ですか？", "safe_lgbtq": "{name}はLGBTQ+旅行者に安全ですか？", "safe_families": "{name}は家族連れに安全ですか？", "key_risks": "主な安全リスク", "practical": "実用的な旅行情報", "advisory": "渡航情報", "similar": "類似の目的地", "methodology": "スコアの計算方法"},
    "ko": {"score_title": "안전 점수 상세", "crime": "범죄 및 개인 안전", "political": "정치적 안정성", "health": "건강 및 의료", "disaster": "자연재해 위험", "infra": "인프라 및 교통", "rights": "여행자 권리", "safe_visit": "{name}은(는) 방문하기 안전한가요?", "safe_women": "{name}은(는) 여성에게 안전한가요?", "safe_solo": "{name}은(는) 혼자 여행하기 안전한가요?", "safe_lgbtq": "{name}은(는) LGBTQ+ 여행자에게 안전한가요?", "safe_families": "{name}은(는) 가족 여행에 안전한가요?", "key_risks": "주요 안전 위험", "practical": "실용적인 여행 정보", "advisory": "여행 권고", "similar": "유사한 여행지", "methodology": "점수 계산 방법"},
    "zh": {"score_title": "安全评分详情", "crime": "犯罪与人身安全", "political": "政治稳定性", "health": "健康与医疗", "disaster": "自然灾害风险", "infra": "基础设施与交通", "rights": "旅行者权利", "safe_visit": "{name}安全吗？", "safe_women": "{name}对女性安全吗？", "safe_solo": "{name}适合独自旅行吗？", "safe_lgbtq": "{name}对LGBTQ+旅行者安全吗？", "safe_families": "{name}适合家庭旅行吗？", "key_risks": "主要安全风险", "practical": "实用旅行信息", "advisory": "旅行建议", "similar": "类似目的地", "methodology": "评分计算方法"},
    "ar": {"score_title": "تفاصيل درجة السلامة", "crime": "الجريمة والسلامة الشخصية", "political": "الاستقرار السياسي", "health": "الصحة والرعاية الطبية", "disaster": "مخاطر الكوارث الطبيعية", "infra": "البنية التحتية والنقل", "rights": "حقوق المسافرين", "safe_visit": "هل {name} آمنة للزيارة؟", "safe_women": "هل {name} آمنة للنساء؟", "safe_solo": "هل {name} آمنة للمسافرين بمفردهم؟", "safe_lgbtq": "هل {name} آمنة لمسافري LGBTQ+؟", "safe_families": "هل {name} آمنة للعائلات؟", "key_risks": "المخاطر الرئيسية", "practical": "معلومات عملية", "advisory": "نصائح السفر", "similar": "وجهات مماثلة", "methodology": "كيف نحسب الدرجات"},
    "hi": {"score_title": "सुरक्षा स्कोर विवरण", "crime": "अपराध और व्यक्तिगत सुरक्षा", "political": "राजनीतिक स्थिरता", "health": "स्वास्थ्य और चिकित्सा", "disaster": "प्राकृतिक आपदा जोखिम", "infra": "बुनियादी ढांचा और परिवहन", "rights": "यात्री अधिकार", "safe_visit": "क्या {name} जाना सुरक्षित है?", "safe_women": "क्या {name} महिलाओं के लिए सुरक्षित है?", "safe_solo": "क्या {name} अकेले यात्रा के लिए सुरक्षित है?", "safe_lgbtq": "क्या {name} LGBTQ+ यात्रियों के लिए सुरक्षित है?", "safe_families": "क्या {name} परिवारों के लिए सुरक्षित है?", "key_risks": "प्रमुख सुरक्षा जोखिम", "practical": "व्यावहारिक जानकारी", "advisory": "यात्रा सलाह", "similar": "समान गंतव्य", "methodology": "स्कोर गणना"},
    "ru": {"score_title": "Детали оценки безопасности", "crime": "Преступность и безопасность", "political": "Политическая стабильность", "health": "Здоровье и медицина", "disaster": "Риск стихийных бедствий", "infra": "Инфраструктура и транспорт", "rights": "Права путешественников", "safe_visit": "Безопасно ли посещать {name}?", "safe_women": "Безопасен ли {name} для женщин?", "safe_solo": "Безопасен ли {name} для одиноких путешественников?", "safe_lgbtq": "Безопасен ли {name} для ЛГБТК+ путешественников?", "safe_families": "Безопасен ли {name} для семей?", "key_risks": "Основные риски", "practical": "Практическая информация", "advisory": "Рекомендации по поездке", "similar": "Похожие направления", "methodology": "Как мы рассчитываем"},
    "nl": {"score_title": "Veiligheidsscore Details", "crime": "Criminaliteit & Veiligheid", "political": "Politieke Stabiliteit", "health": "Gezondheid & Medisch", "disaster": "Natuurrampenrisico", "infra": "Infrastructuur & Vervoer", "rights": "Rechten van Reizigers", "safe_visit": "Is {name} veilig om te bezoeken?", "safe_women": "Is {name} veilig voor vrouwen?", "safe_solo": "Is {name} veilig voor alleen reizigers?", "safe_lgbtq": "Is {name} veilig voor LGBTQ+ reizigers?", "safe_families": "Is {name} veilig voor gezinnen?", "key_risks": "Belangrijkste Risico's", "practical": "Praktische Reisinformatie", "advisory": "Reisadvies", "similar": "Vergelijkbare Bestemmingen", "methodology": "Hoe We Berekenen"},
    "pl": {"score_title": "Szczegóły Oceny Bezpieczeństwa", "crime": "Przestępczość i Bezpieczeństwo", "political": "Stabilność Polityczna", "health": "Zdrowie i Medycyna", "disaster": "Ryzyko Klęsk Żywiołowych", "infra": "Infrastruktura i Transport", "rights": "Prawa Podróżnych", "safe_visit": "Czy {name} jest bezpieczne do odwiedzenia?", "safe_women": "Czy {name} jest bezpieczne dla kobiet?", "safe_solo": "Czy {name} jest bezpieczne dla samotnych podróżników?", "safe_lgbtq": "Czy {name} jest bezpieczne dla podróżnych LGBTQ+?", "safe_families": "Czy {name} jest bezpieczne dla rodzin?", "key_risks": "Główne Zagrożenia", "practical": "Praktyczne Informacje", "advisory": "Ostrzeżenie Podróżne", "similar": "Podobne Miejsca", "methodology": "Jak Obliczamy"},
    "tr": {"score_title": "Güvenlik Puanı Detayları", "crime": "Suç ve Kişisel Güvenlik", "political": "Siyasi İstikrar", "health": "Sağlık ve Tıbbi", "disaster": "Doğal Afet Riski", "infra": "Altyapı ve Ulaşım", "rights": "Gezgin Hakları", "safe_visit": "{name} ziyaret etmek güvenli mi?", "safe_women": "{name} kadınlar için güvenli mi?", "safe_solo": "{name} tek başına seyahat için güvenli mi?", "safe_lgbtq": "{name} LGBTQ+ gezginler için güvenli mi?", "safe_families": "{name} aileler için güvenli mi?", "key_risks": "Temel Güvenlik Riskleri", "practical": "Pratik Bilgiler", "advisory": "Seyahat Uyarısı", "similar": "Benzer Yerler", "methodology": "Nasıl Hesaplıyoruz"},
    "vi": {"score_title": "Chi Tiết Điểm An Toàn", "crime": "Tội Phạm & An Ninh", "political": "Ổn Định Chính Trị", "health": "Sức Khỏe & Y Tế", "disaster": "Rủi Ro Thiên Tai", "infra": "Hạ Tầng & Giao Thông", "rights": "Quyền Lợi Du Khách", "safe_visit": "{name} có an toàn để đến thăm không?", "safe_women": "{name} có an toàn cho phụ nữ không?", "safe_solo": "{name} có an toàn cho du lịch một mình không?", "safe_lgbtq": "{name} có an toàn cho du khách LGBTQ+ không?", "safe_families": "{name} có an toàn cho gia đình không?", "key_risks": "Rủi Ro Chính", "practical": "Thông Tin Thực Tế", "advisory": "Khuyến Cáo Du Lịch", "similar": "Điểm Đến Tương Tự", "methodology": "Cách Tính Điểm"},
    "th": {"score_title": "รายละเอียดคะแนนความปลอดภัย", "crime": "อาชญากรรมและความปลอดภัยส่วนบุคคล", "political": "เสถียรภาพทางการเมือง", "health": "สุขภาพและการแพทย์", "disaster": "ความเสี่ยงภัยธรรมชาติ", "infra": "โครงสร้างพื้นฐานและการขนส่ง", "rights": "สิทธิ์นักท่องเที่ยว", "safe_visit": "{name} ปลอดภัยที่จะเยี่ยมชมหรือไม่?", "safe_women": "{name} ปลอดภัยสำหรับผู้หญิงหรือไม่?", "safe_solo": "{name} ปลอดภัยสำหรับนักท่องเที่ยวเดี่ยวหรือไม่?", "safe_lgbtq": "{name} ปลอดภัยสำหรับนักท่องเที่ยว LGBTQ+ หรือไม่?", "safe_families": "{name} ปลอดภัยสำหรับครอบครัวหรือไม่?", "key_risks": "ความเสี่ยงหลัก", "practical": "ข้อมูลที่เป็นประโยชน์", "advisory": "คำแนะนำการเดินทาง", "similar": "จุดหมายปลายทางที่คล้ายกัน", "methodology": "วิธีคำนวณคะแนน"},
    "id": {"score_title": "Detail Skor Keamanan", "crime": "Kejahatan & Keamanan", "political": "Stabilitas Politik", "health": "Kesehatan & Medis", "disaster": "Risiko Bencana Alam", "infra": "Infrastruktur & Transportasi", "rights": "Hak Wisatawan", "safe_visit": "Apakah {name} aman untuk dikunjungi?", "safe_women": "Apakah {name} aman untuk wanita?", "safe_solo": "Apakah {name} aman untuk wisatawan solo?", "safe_lgbtq": "Apakah {name} aman untuk wisatawan LGBTQ+?", "safe_families": "Apakah {name} aman untuk keluarga?", "key_risks": "Risiko Utama", "practical": "Informasi Praktis", "advisory": "Saran Perjalanan", "similar": "Destinasi Serupa", "methodology": "Cara Kami Menghitung"},
    "da": {"score_title": "Sikkerhedsscore Detaljer", "crime": "Kriminalitet & Sikkerhed", "political": "Politisk Stabilitet", "health": "Sundhed & Lægehjælp", "disaster": "Naturkatastroferisiko", "infra": "Infrastruktur & Transport", "rights": "Rejsendes Rettigheder", "safe_visit": "Er {name} sikkert at besøge?", "safe_women": "Er {name} sikkert for kvinder?", "safe_solo": "Er {name} sikkert for solorejsende?", "safe_lgbtq": "Er {name} sikkert for LGBTQ+-rejsende?", "safe_families": "Er {name} sikkert for familier?", "key_risks": "Vigtigste Risici", "practical": "Praktisk Rejseinformation", "advisory": "Rejseanbefaling", "similar": "Lignende Destinationer", "methodology": "Hvordan Vi Beregner"},
    "no": {"score_title": "Sikkerhetspoeng Detaljer", "crime": "Kriminalitet og sikkerhet", "political": "Politisk stabilitet", "health": "Helse og legehjelp", "disaster": "Naturkatastroferisiko", "infra": "Infrastruktur og transport", "rights": "Reisendes rettigheter", "safe_visit": "Er {name} trygt å besøke?", "safe_women": "Er {name} trygt for kvinner?", "safe_solo": "Er {name} trygt for soloeinreisende?", "safe_lgbtq": "Er {name} trygt for LGBTQ+-reisende?", "safe_families": "Er {name} trygt for familier?", "key_risks": "Viktigste risikoer", "practical": "Praktisk reiseinformasjon", "advisory": "Reiseanbefaling", "similar": "Lignende destinasjoner", "methodology": "Hvordan vi beregner"},
}

_CHARITY_T = {
    "en": {"score_title": "Trust Score Breakdown", "financial": "Financial Transparency", "program": "Program Effectiveness", "governance": "Governance", "donor_trust": "Donor Trust", "accountability": "Accountability", "is_trustworthy": "Is {name} trustworthy?", "how_spend": "How does {name} spend donations?", "tax_deductible": "Are donations tax-deductible?", "similar": "Similar Charities", "methodology": "How We Rate Charities"},
    "sv": {"score_title": "Förtroendepoäng i Detalj", "financial": "Finansiell Transparens", "program": "Programeffektivitet", "governance": "Styrning", "donor_trust": "Givarförtroende", "accountability": "Ansvarighet", "is_trustworthy": "Är {name} pålitlig?", "how_spend": "Hur spenderar {name} donationer?", "tax_deductible": "Är donationer avdragsgilla?", "similar": "Liknande Organisationer", "methodology": "Hur Vi Bedömer"},
    "es": {"score_title": "Desglose de Confianza", "financial": "Transparencia Financiera", "program": "Efectividad del Programa", "governance": "Gobernanza", "donor_trust": "Confianza del Donante", "accountability": "Responsabilidad", "is_trustworthy": "¿Es {name} confiable?", "how_spend": "¿Cómo gasta {name} las donaciones?", "tax_deductible": "¿Son deducibles las donaciones?", "similar": "Organizaciones Similares", "methodology": "Cómo Evaluamos"},
    "fr": {"score_title": "Détail du Score de Confiance", "financial": "Transparence Financière", "program": "Efficacité des Programmes", "governance": "Gouvernance", "donor_trust": "Confiance des Donateurs", "accountability": "Responsabilité", "is_trustworthy": "{name} est-il fiable?", "how_spend": "Comment {name} utilise les dons?", "tax_deductible": "Les dons sont-ils déductibles?", "similar": "Associations Similaires", "methodology": "Comment Nous Évaluons"},
    "de": {"score_title": "Vertrauensbewertung im Detail", "financial": "Finanzielle Transparenz", "program": "Programmwirksamkeit", "governance": "Unternehmensführung", "donor_trust": "Spendervertrauen", "accountability": "Rechenschaftspflicht", "is_trustworthy": "Ist {name} vertrauenswürdig?", "how_spend": "Wie verwendet {name} Spenden?", "tax_deductible": "Sind Spenden steuerlich absetzbar?", "similar": "Ähnliche Organisationen", "methodology": "Wie Wir Bewerten"},
    "ja": {"score_title": "信頼スコアの内訳", "financial": "財務透明性", "program": "プログラムの有効性", "governance": "ガバナンス", "donor_trust": "寄付者の信頼", "accountability": "説明責任", "is_trustworthy": "{name}は信頼できますか？", "how_spend": "{name}は寄付金をどう使っていますか？", "tax_deductible": "寄付は税控除できますか？", "similar": "類似の団体", "methodology": "評価方法"},
    "ko": {"score_title": "신뢰 점수 상세", "financial": "재정 투명성", "program": "프로그램 효과", "governance": "거버넌스", "donor_trust": "기부자 신뢰", "accountability": "책임성", "is_trustworthy": "{name}은(는) 신뢰할 수 있나요?", "how_spend": "{name}은(는) 기부금을 어떻게 사용하나요?", "tax_deductible": "기부금은 세금 공제가 되나요?", "similar": "유사한 단체", "methodology": "평가 방법"},
    "zh": {"score_title": "信任评分详情", "financial": "财务透明度", "program": "项目有效性", "governance": "治理", "donor_trust": "捐赠者信任", "accountability": "问责制", "is_trustworthy": "{name}可信吗？", "how_spend": "{name}如何使用捐款？", "tax_deductible": "捐款可以减税吗？", "similar": "类似组织", "methodology": "评分方法"},
    "ar": {"score_title": "تفاصيل درجة الثقة", "financial": "الشفافية المالية", "program": "فعالية البرامج", "governance": "الحوكمة", "donor_trust": "ثقة المتبرعين", "accountability": "المساءلة", "is_trustworthy": "هل {name} جديرة بالثقة؟", "how_spend": "كيف تنفق {name} التبرعات؟", "tax_deductible": "هل التبرعات معفاة من الضرائب؟", "similar": "منظمات مماثلة", "methodology": "كيف نقيّم"},
}
_INGREDIENT_T = {
    "en": {"score_title": "Safety Score Breakdown", "toxicology": "Toxicology", "regulatory": "Regulatory Status", "longterm": "Long-term Safety", "allergen": "Allergen Risk", "environmental": "Environmental Impact", "evidence": "Evidence Base", "safety_profile": "Safety Profile", "drug_interactions": "Drug Interactions", "quality": "Quality Standards", "skin_safety": "Skin Safety", "sensitization": "Sensitization Risk", "similar": "Similar Items", "methodology": "How We Rate Safety"},
    "sv": {"score_title": "Säkerhetsbetyg i Detalj", "toxicology": "Toxikologi", "regulatory": "Regulatorisk Status", "longterm": "Långsiktig Säkerhet", "allergen": "Allergenrisk", "environmental": "Miljöpåverkan", "evidence": "Evidensbas", "safety_profile": "Säkerhetsprofil", "drug_interactions": "Läkemedelsinteraktioner", "quality": "Kvalitetsstandarder", "skin_safety": "Hudsäkerhet", "sensitization": "Sensibiliseringsrisk", "similar": "Liknande Produkter", "methodology": "Hur Vi Bedömer Säkerhet"},
    "es": {"score_title": "Desglose de Seguridad", "toxicology": "Toxicología", "regulatory": "Estado Regulatorio", "longterm": "Seguridad a Largo Plazo", "allergen": "Riesgo Alérgeno", "environmental": "Impacto Ambiental", "evidence": "Base de Evidencia", "safety_profile": "Perfil de Seguridad", "drug_interactions": "Interacciones Medicamentosas", "quality": "Estándares de Calidad", "skin_safety": "Seguridad Cutánea", "sensitization": "Riesgo de Sensibilización", "similar": "Productos Similares", "methodology": "Cómo Evaluamos la Seguridad"},
    "fr": {"score_title": "Détail du Score de Sécurité", "toxicology": "Toxicologie", "regulatory": "Statut Réglementaire", "longterm": "Sécurité à Long Terme", "allergen": "Risque Allergène", "environmental": "Impact Environnemental", "evidence": "Base de Preuves", "safety_profile": "Profil de Sécurité", "drug_interactions": "Interactions Médicamenteuses", "quality": "Normes de Qualité", "skin_safety": "Sécurité Cutanée", "sensitization": "Risque de Sensibilisation", "similar": "Produits Similaires", "methodology": "Comment Nous Évaluons la Sécurité"},
    "de": {"score_title": "Sicherheitsbewertung im Detail", "toxicology": "Toxikologie", "regulatory": "Regulatorischer Status", "longterm": "Langzeitsicherheit", "allergen": "Allergenrisiko", "environmental": "Umweltauswirkung", "evidence": "Evidenzbasis", "safety_profile": "Sicherheitsprofil", "drug_interactions": "Arzneimittelwechselwirkungen", "quality": "Qualitätsstandards", "skin_safety": "Hautsicherheit", "sensitization": "Sensibilisierungsrisiko", "similar": "Ähnliche Produkte", "methodology": "Wie Wir Sicherheit Bewerten"},
    "pt": {"score_title": "Detalhes da Pontuação de Segurança", "toxicology": "Toxicologia", "regulatory": "Status Regulatório", "longterm": "Segurança a Longo Prazo", "allergen": "Risco Alergênico", "environmental": "Impacto Ambiental", "evidence": "Base de Evidências", "safety_profile": "Perfil de Segurança", "drug_interactions": "Interações Medicamentosas", "quality": "Padrões de Qualidade", "skin_safety": "Segurança Cutânea", "sensitization": "Risco de Sensibilização", "similar": "Produtos Similares", "methodology": "Como Avaliamos a Segurança"},
    "it": {"score_title": "Dettaglio Punteggio Sicurezza", "toxicology": "Tossicologia", "regulatory": "Stato Normativo", "longterm": "Sicurezza a Lungo Termine", "allergen": "Rischio Allergeni", "environmental": "Impatto Ambientale", "evidence": "Base di Evidenze", "safety_profile": "Profilo di Sicurezza", "drug_interactions": "Interazioni Farmacologiche", "quality": "Standard di Qualità", "skin_safety": "Sicurezza Cutanea", "sensitization": "Rischio di Sensibilizzazione", "similar": "Prodotti Simili", "methodology": "Come Valutiamo la Sicurezza"},
    "ja": {"score_title": "安全性スコアの内訳", "toxicology": "毒性学", "regulatory": "規制状況", "longterm": "長期安全性", "allergen": "アレルゲンリスク", "environmental": "環境影響", "evidence": "エビデンスベース", "safety_profile": "安全性プロファイル", "drug_interactions": "薬物相互作用", "quality": "品質基準", "skin_safety": "皮膚安全性", "sensitization": "感作リスク", "similar": "類似製品", "methodology": "安全性の評価方法"},
    "ko": {"score_title": "안전 점수 상세", "toxicology": "독성학", "regulatory": "규제 상태", "longterm": "장기 안전성", "allergen": "알레르겐 위험", "environmental": "환경 영향", "evidence": "증거 기반", "safety_profile": "안전성 프로필", "drug_interactions": "약물 상호작용", "quality": "품질 기준", "skin_safety": "피부 안전성", "sensitization": "감작 위험", "similar": "유사 제품", "methodology": "안전성 평가 방법"},
    "zh": {"score_title": "安全评分详情", "toxicology": "毒理学", "regulatory": "监管状态", "longterm": "长期安全性", "allergen": "过敏原风险", "environmental": "环境影响", "evidence": "证据基础", "safety_profile": "安全性概况", "drug_interactions": "药物相互作用", "quality": "质量标准", "skin_safety": "皮肤安全性", "sensitization": "致敏风险", "similar": "类似产品", "methodology": "安全评估方法"},
    "ar": {"score_title": "تفاصيل درجة السلامة", "toxicology": "علم السموم", "regulatory": "الحالة التنظيمية", "longterm": "السلامة طويلة المدى", "allergen": "خطر مسببات الحساسية", "environmental": "التأثير البيئي", "evidence": "قاعدة الأدلة", "safety_profile": "ملف السلامة", "drug_interactions": "التفاعلات الدوائية", "quality": "معايير الجودة", "skin_safety": "سلامة البشرة", "sensitization": "خطر التحسس", "similar": "منتجات مماثلة", "methodology": "كيف نقيّم السلامة"},
    "hi": {"score_title": "सुरक्षा स्कोर विवरण", "toxicology": "विष विज्ञान", "regulatory": "नियामक स्थिति", "longterm": "दीर्घकालिक सुरक्षा", "allergen": "एलर्जन जोखिम", "environmental": "पर्यावरणीय प्रभाव", "evidence": "साक्ष्य आधार", "safety_profile": "सुरक्षा प्रोफ़ाइल", "drug_interactions": "दवा अंतःक्रियाएँ", "quality": "गुणवत्ता मानक", "skin_safety": "त्वचा सुरक्षा", "sensitization": "संवेदीकरण जोखिम", "similar": "समान उत्पाद", "methodology": "सुरक्षा मूल्यांकन विधि"},
    "ru": {"score_title": "Детали оценки безопасности", "toxicology": "Токсикология", "regulatory": "Нормативный статус", "longterm": "Долгосрочная безопасность", "allergen": "Аллергенный риск", "environmental": "Воздействие на окружающую среду", "evidence": "Доказательная база", "safety_profile": "Профиль безопасности", "drug_interactions": "Лекарственные взаимодействия", "quality": "Стандарты качества", "skin_safety": "Безопасность для кожи", "sensitization": "Риск сенсибилизации", "similar": "Похожие продукты", "methodology": "Как мы оцениваем безопасность"},
    "nl": {"score_title": "Veiligheidsscore Details", "toxicology": "Toxicologie", "regulatory": "Regelgevingsstatus", "longterm": "Langetermijnveiligheid", "allergen": "Allergeenrisico", "environmental": "Milieueffect", "evidence": "Bewijsbasis", "safety_profile": "Veiligheidsprofiel", "drug_interactions": "Geneesmiddelinteracties", "quality": "Kwaliteitsnormen", "skin_safety": "Huidveiligheid", "sensitization": "Sensibilisatierisico", "similar": "Vergelijkbare Producten", "methodology": "Hoe We Veiligheid Beoordelen"},
    "pl": {"score_title": "Szczegóły Oceny Bezpieczeństwa", "toxicology": "Toksykologia", "regulatory": "Status Regulacyjny", "longterm": "Bezpieczeństwo Długoterminowe", "allergen": "Ryzyko Alergenowe", "environmental": "Wpływ na Środowisko", "evidence": "Baza Dowodowa", "safety_profile": "Profil Bezpieczeństwa", "drug_interactions": "Interakcje z Lekami", "quality": "Standardy Jakości", "skin_safety": "Bezpieczeństwo Skóry", "sensitization": "Ryzyko Uczulenia", "similar": "Podobne Produkty", "methodology": "Jak Oceniamy Bezpieczeństwo"},
    "tr": {"score_title": "Güvenlik Puanı Detayları", "toxicology": "Toksikoloji", "regulatory": "Düzenleyici Durum", "longterm": "Uzun Vadeli Güvenlik", "allergen": "Alerjen Riski", "environmental": "Çevresel Etki", "evidence": "Kanıt Tabanı", "safety_profile": "Güvenlik Profili", "drug_interactions": "İlaç Etkileşimleri", "quality": "Kalite Standartları", "skin_safety": "Cilt Güvenliği", "sensitization": "Hassasiyet Riski", "similar": "Benzer Ürünler", "methodology": "Güvenliği Nasıl Değerlendiriyoruz"},
    "vi": {"score_title": "Chi Tiết Điểm An Toàn", "toxicology": "Độc Chất Học", "regulatory": "Tình Trạng Quản Lý", "longterm": "An Toàn Dài Hạn", "allergen": "Rủi Ro Dị Ứng", "environmental": "Tác Động Môi Trường", "evidence": "Cơ Sở Bằng Chứng", "safety_profile": "Hồ Sơ An Toàn", "drug_interactions": "Tương Tác Thuốc", "quality": "Tiêu Chuẩn Chất Lượng", "skin_safety": "An Toàn Da", "sensitization": "Rủi Ro Mẫn Cảm", "similar": "Sản Phẩm Tương Tự", "methodology": "Cách Đánh Giá An Toàn"},
    "th": {"score_title": "รายละเอียดคะแนนความปลอดภัย", "toxicology": "พิษวิทยา", "regulatory": "สถานะการกำกับดูแล", "longterm": "ความปลอดภัยระยะยาว", "allergen": "ความเสี่ยงสารก่อภูมิแพ้", "environmental": "ผลกระทบต่อสิ่งแวดล้อม", "evidence": "ฐานหลักฐาน", "safety_profile": "โปรไฟล์ความปลอดภัย", "drug_interactions": "ปฏิกิริยาระหว่างยา", "quality": "มาตรฐานคุณภาพ", "skin_safety": "ความปลอดภัยต่อผิว", "sensitization": "ความเสี่ยงแพ้สัมผัส", "similar": "ผลิตภัณฑ์ที่คล้ายกัน", "methodology": "วิธีประเมินความปลอดภัย"},
    "id": {"score_title": "Detail Skor Keamanan", "toxicology": "Toksikologi", "regulatory": "Status Regulasi", "longterm": "Keamanan Jangka Panjang", "allergen": "Risiko Alergen", "environmental": "Dampak Lingkungan", "evidence": "Basis Bukti", "safety_profile": "Profil Keamanan", "drug_interactions": "Interaksi Obat", "quality": "Standar Kualitas", "skin_safety": "Keamanan Kulit", "sensitization": "Risiko Sensitisasi", "similar": "Produk Serupa", "methodology": "Cara Kami Menilai Keamanan"},
    "da": {"score_title": "Sikkerhedsscore Detaljer", "toxicology": "Toksikologi", "regulatory": "Regulatorisk Status", "longterm": "Langtidssikkerhed", "allergen": "Allergenrisiko", "environmental": "Miljøpåvirkning", "evidence": "Evidensbase", "safety_profile": "Sikkerhedsprofil", "drug_interactions": "Lægemiddelinteraktioner", "quality": "Kvalitetsstandarder", "skin_safety": "Hudsikkerhed", "sensitization": "Sensibiliseringsrisiko", "similar": "Lignende Produkter", "methodology": "Hvordan Vi Vurderer Sikkerhed"},
    "no": {"score_title": "Sikkerhetspoeng Detaljer", "toxicology": "Toksikologi", "regulatory": "Regulatorisk status", "longterm": "Langtidssikkerhet", "allergen": "Allergenrisiko", "environmental": "Miljøpåvirkning", "evidence": "Kunnskapsgrunnlag", "safety_profile": "Sikkerhetsprofil", "drug_interactions": "Legemiddelinteraksjoner", "quality": "Kvalitetsstandarder", "skin_safety": "Hudsikkerhet", "sensitization": "Sensibiliseringsrisiko", "similar": "Lignende produkter", "methodology": "Hvordan vi vurderer sikkerhet"},
}

# Fallback: languages not explicitly listed use English
for _d in (_TRAVEL_T, _CHARITY_T, _INGREDIENT_T):
    for _l in ("pt", "it", "hi", "ru", "nl", "pl", "tr", "vi", "th", "id", "da", "no"):
        if _l not in _d:
            _d[_l] = _d["en"]


def _risk_label(s, lang="en"):
    _labels = {"en": ("Very Low Risk", "Low Risk", "Medium Risk", "High Risk", "Very High Risk"),
               "sv": ("Mycket Låg Risk", "Låg Risk", "Medelhög Risk", "Hög Risk", "Mycket Hög Risk"),
               "es": ("Riesgo Muy Bajo", "Riesgo Bajo", "Riesgo Medio", "Riesgo Alto", "Riesgo Muy Alto"),
               "fr": ("Risque Très Faible", "Risque Faible", "Risque Moyen", "Risque Élevé", "Risque Très Élevé"),
               "de": ("Sehr Niedriges Risiko", "Niedriges Risiko", "Mittleres Risiko", "Hohes Risiko", "Sehr Hohes Risiko"),
               "ja": ("非常に低リスク", "低リスク", "中リスク", "高リスク", "非常に高リスク")}
    labels = _labels.get(lang, _labels["en"])
    if s >= 80: return labels[0]
    if s >= 60: return labels[1]
    if s >= 40: return labels[2]
    if s >= 20: return labels[3]
    return labels[4]


def _render_dimensions(a, t, lang):
    """Render registry-appropriate dimensions (travel/charity/software)."""
    registry = a.get("type", "")
    nm = _esc(a.get("name", "").split("/")[-1] if "/" in a.get("name", "") else a.get("name", ""))
    score = a.get("score") or 0

    if registry in ("country", "city"):
        tt = _TRAVEL_T.get(lang, _TRAVEL_T["en"])
        _sec = round(a.get("sec") or score)
        _pop = round(a.get("pop") or 50)
        dims = [
            (tt["crime"], round(_sec)),
            (tt["political"], round((_sec + _pop) / 2)),
            (tt["health"], round(_sec)),
            (tt["disaster"], round(max(30, score - 15))),
            (tt["infra"], round((_pop + score) / 2)),
            (tt["rights"], round((_sec + score) / 2)),
        ]
        rows = ""
        for name_d, val in dims:
            color = "#16a34a" if val >= 70 else "#f59e0b" if val >= 40 else "#dc2626"
            rows += f'<tr><td>{name_d}</td><td style="color:{color};font-weight:600;text-align:right">{val}/100</td><td style="font-size:12px;color:#6b7280">{_risk_label(val, lang)}</td></tr>'

        traveler_html = ""
        for key in ("safe_solo", "safe_women", "safe_lgbtq", "safe_families"):
            heading = tt.get(key, "").format(name=nm)
            if heading:
                traveler_html += f"<h2>{heading}</h2><p style='font-size:14px;color:#374151;margin:4px 0 16px'>Score: {score:.0f}/100.</p>"

        return f"""
<h2>{tt['score_title']}</h2>
<table><tr><th>{t.get('dimension','Dimension')}</th><th style="text-align:right">{t.get('score','Score')}</th><th></th></tr>
{rows}</table>

{traveler_html}

<h2>{tt['similar']}</h2>
<p style="font-size:14px"><a href="/best/safest-countries" style="color:#0d9488">{tt['similar']} →</a></p>
"""

    elif registry == "charity":
        ct = _CHARITY_T.get(lang, _CHARITY_T["en"])
        _sec = round(a.get("sec") or score)
        dims = [
            (ct["financial"], round(_sec)),
            (ct["program"], round(max(40, score - 20))),
            (ct["governance"], round(_sec)),
            (ct["donor_trust"], round(score)),
            (ct["accountability"], round(max(40, _sec - 10))),
        ]
        rows = ""
        for name_d, val in dims:
            color = "#16a34a" if val >= 70 else "#f59e0b" if val >= 40 else "#dc2626"
            rows += f'<tr><td>{name_d}</td><td style="color:{color};font-weight:600;text-align:right">{val}/100</td></tr>'

        return f"""
<h2>{ct['score_title']}</h2>
<table><tr><th>{t.get('dimension','Dimension')}</th><th style="text-align:right">{t.get('score','Score')}</th></tr>
{rows}</table>

<h2>{ct.get('how_spend','').format(name=nm)}</h2>
<p style="font-size:14px;color:#374151">Score: {score:.0f}/100.</p>

<h2>{ct['similar']}</h2>
<p style="font-size:14px"><a href="/best/charities" style="color:#0d9488">{ct['similar']} →</a></p>
"""

    elif registry in ("ingredient", "supplement", "cosmetic_ingredient"):
        it = _INGREDIENT_T.get(lang, _INGREDIENT_T["en"])
        _sec = round(a.get("sec") or score)
        _pop = round(a.get("pop") or 50)

        if registry == "supplement":
            dims = [
                (it["evidence"], round((_sec + score) / 2)),
                (it["safety_profile"], round(_sec)),
                (it["drug_interactions"], round(max(40, score - 15))),
                (it["quality"], round((_pop + score) / 2)),
                (it["regulatory"], round(max(40, score - 10))),
            ]
        elif registry == "cosmetic_ingredient":
            dims = [
                (it["skin_safety"], round((_sec + score) / 2)),
                (it["toxicology"], round(_sec)),
                (it["regulatory"], round(max(40, score - 10))),
                (it["sensitization"], round((_sec + score) / 2)),
                (it["environmental"], round(max(30, score - 15))),
            ]
        else:
            dims = [
                (it["toxicology"], round(_sec)),
                (it["regulatory"], round(max(40, score - 10))),
                (it["longterm"], round((_sec + score) / 2)),
                (it["allergen"], round((_sec + score) / 2)),
                (it["environmental"], round(max(30, score - 15))),
            ]

        rows = ""
        for name_d, val in dims:
            color = "#16a34a" if val >= 70 else "#f59e0b" if val >= 40 else "#dc2626"
            rows += f'<tr><td>{name_d}</td><td style="color:{color};font-weight:600;text-align:right">{val}/100</td></tr>'

        return f"""
<h2>{it['score_title']}</h2>
<table><tr><th>{t.get('dimension','Dimension')}</th><th style="text-align:right">{t.get('score','Score')}</th></tr>
{rows}</table>

<h2>{it['similar']}</h2>
<p style="font-size:14px"><a href="/safe" style="color:#0d9488">{it['similar']} →</a></p>
"""

    else:
        # Default: software dimensions (original behavior)
        return f"""
<h2>{t.get('why_this_score', 'Why This Score')}</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li>{'&#x2705;' if (a.get('sec') or 0) >= 60 else '&#x26A0;&#xFE0F;'} <strong>{t.get('security', 'Security')}</strong>: {(a.get('sec') or 0):.0f}/100</li>
<li>{'&#x2705;' if (a.get('act') or 0) >= 60 else '&#x26A0;&#xFE0F;'} <strong>{t.get('maintenance', 'Maintenance')}</strong>: {(a.get('act') or 0):.0f}/100</li>
<li>{'&#x2705;' if (a.get('pop') or 0) >= 60 else '&#x26A0;&#xFE0F;'} <strong>{t.get('community', 'Community')}</strong>: {_fmt(a.get('stars'))} stars, {_fmt(a.get('downloads'))} users</li>
<li>{'&#x2705;' if a.get('license') else '&#x26A0;&#xFE0F;'} <strong>{t.get('transparency', 'Transparency')}</strong>: {_esc(a.get('license') or t.get('unknown', 'Unknown'))}</li>
</ul>

<h2>{t.get('trust_breakdown', 'Trust Score Breakdown')}</h2>
<table>
<tr><th>{t.get('dimension', 'Dimension')}</th><th>{t.get('score', 'Score')}</th></tr>
<tr><td>{t.get('security', 'Security')}</td><td>{(a.get('sec') or 0):.0f}/100</td></tr>
<tr><td>{t.get('maintenance', 'Maintenance')}</td><td>{(a.get('act') or 0):.0f}/100</td></tr>
<tr><td>{t.get('community', 'Community')}</td><td>{(a.get('pop') or 0):.0f}/100</td></tr>
<tr><td>{t.get('transparency', 'Transparency')}</td><td>{(a.get('doc') or 0):.0f}/100</td></tr>
</table>
"""


def _render_hreflang(entity_slug, pattern):
    """Generate hreflang tags for all 20 languages."""
    tags = []
    # English default
    en_pat = URL_PATTERNS.get("en", {}).get(pattern, f"is-{entity_slug}-safe")
    en_url = f"{SITE}/{en_pat.format(slug=entity_slug)}"
    tags.append(f'<link rel="alternate" hreflang="en" href="{en_url}">')
    tags.append(f'<link rel="alternate" hreflang="x-default" href="{en_url}">')
    for lang in SUPPORTED_LANGS:
        pat = URL_PATTERNS.get(lang, {}).get(pattern, "")
        if pat:
            url = f"{SITE}/{lang}/{pat.format(slug=entity_slug)}"
            tags.append(f'<link rel="alternate" hreflang="{lang}" href="{url}">')
    return "\n".join(tags)


def _render_verdict_box(entity, pattern, t):
    """Render the verdict box with localized strings."""
    score = entity.get("score") or 0
    grade = entity.get("grade") or "D"

    if score >= 70:
        verdict = t.get("safe", "Safe")
        color = "#16a34a"; bg = "#f0fdf4"; icon = "&#x2705;"
    elif score >= 40:
        verdict = t.get("use_caution", "Use Caution")
        color = "#d97706"; bg = "#fffbeb"; icon = "&#x26A0;&#xFE0F;"
    else:
        verdict = t.get("avoid", "Avoid")
        color = "#dc2626"; bg = "#fef2f2"; icon = "&#x1F534;"

    return f"""<div style="border:2px solid {color};border-radius:12px;padding:24px;margin:20px 0;background:{bg}">
<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px">
<div><div style="font-size:3rem;font-weight:800;color:{color}">{score:.0f}/100</div>
<div style="font-size:1.1rem;color:#666">{t.get('trust_score','Trust Score')} ({grade})</div></div>
<div style="text-align:right"><div style="font-size:1.5rem;font-weight:700;color:{color}">{icon} {verdict}</div></div>
</div></div>"""


def _render_localized_page(entity_slug, pattern, lang):
    """Render localized page using the FULL English template with language overlay.
    This gives 100% content parity — same sections, same data, same structure.
    """
    ck = f"l10n:{lang}:{pattern}:{entity_slug}"
    c = _c(ck)
    if c:
        return c

    # Call the rendering pipeline with native lang support
    try:
        from agentindex.agent_safety_pages import _render_agent_page
        html = _render_agent_page(entity_slug, {"name": entity_slug}, lang=lang)
        if not html or "Not yet analyzed" in html[:200].lower() or len(html) < 500:
            # Entity not found — fall back to minimal page
            return _render_localized_page_minimal(entity_slug, pattern, lang)
    except Exception:
        return _render_localized_page_minimal(entity_slug, pattern, lang)

    # hreflang tags already rendered by base template ({{ hreflang_tags }})

    # Fast phrase-only translation (5ms) — replaces remaining English strings
    # Does NOT run _translate_html regex patterns (those caused 35-40s cold loads)
    _ct = _CONTENT_TRANSLATIONS.get(lang)
    if _ct:
        _sorted = sorted(_ct.items(), key=lambda x: -len(x[0]))
        for _en, _loc in _sorted:
            if not _en or not _loc:
                continue
            html = html.replace(f'>{_en}<', f'>{_loc}<')
            html = html.replace(f'>{_en} ', f'>{_loc} ')
            if len(_en) >= 8:
                html = html.replace(_en, _loc)

    # Localize internal links via the i18n module (fast, ReDoS-safe ~5ms).
    # Replaces the legacy _translate_html() regex which caused 35-40s cold loads.
    # See agentindex/i18n/html_rewrite.py + tests/test_i18n_html_rewrite.py.
    from agentindex.i18n.html_rewrite import localize_internal_links as _localize_links
    html = _localize_links(html, lang)

    return _sc(ck, html)


# ── Comprehensive translation maps per language ──────────────
# Sorted longest-first to prevent partial replacements

# /best/ page translations — merged into _CONTENT_TRANSLATIONS below
_BEST_PAGE_TRANSLATIONS = {
    "es": {"Ranked by Nerq Trust Score. Last updated": "Clasificado por Nerq Trust Score. Última actualización", "Ranked by Trust &amp; Security | Nerq": "Clasificación por Confianza y Seguridad | Nerq", "ranked by Nerq Trust Score. Independent security and trust analysis.": "clasificados por Nerq Trust Score. Análisis independiente de seguridad y confianza.", "Browse all categories": "Ver todas las categorías", "Not enough data yet.": "Aún no hay suficientes datos.", "Browse other categories": "Ver otras categorías"},
    "de": {"Ranked by Nerq Trust Score. Last updated": "Bewertet nach Nerq Trust Score. Zuletzt aktualisiert", "Ranked by Trust &amp; Security | Nerq": "Bewertung nach Vertrauen und Sicherheit | Nerq", "ranked by Nerq Trust Score. Independent security and trust analysis.": "bewertet nach Nerq Trust Score. Unabhängige Sicherheits- und Vertrauensanalyse.", "Browse all categories": "Alle Kategorien durchsuchen", "Not enough data yet.": "Noch nicht genügend Daten.", "Browse other categories": "Andere Kategorien durchsuchen"},
    "fr": {"Ranked by Nerq Trust Score. Last updated": "Classé par Nerq Trust Score. Dernière mise à jour", "Ranked by Trust &amp; Security | Nerq": "Classement par Confiance et Sécurité | Nerq", "ranked by Nerq Trust Score. Independent security and trust analysis.": "classés par Nerq Trust Score. Analyse indépendante de sécurité et de confiance.", "Browse all categories": "Parcourir toutes les catégories", "Not enough data yet.": "Pas encore assez de données.", "Browse other categories": "Parcourir d'autres catégories"},
    "ja": {"Ranked by Nerq Trust Score. Last updated": "Nerq Trust Scoreでランク付け。最終更新", "Ranked by Trust &amp; Security | Nerq": "信頼性とセキュリティでランク付け | Nerq", "ranked by Nerq Trust Score. Independent security and trust analysis.": "Nerq Trust Scoreでランク付け。独立したセキュリティと信頼性分析。", "Browse all categories": "すべてのカテゴリを閲覧", "Not enough data yet.": "まだ十分なデータがありません。", "Browse other categories": "他のカテゴリを閲覧"},
    "pt": {"Ranked by Nerq Trust Score. Last updated": "Classificado pelo Nerq Trust Score. Última atualização", "Ranked by Trust &amp; Security | Nerq": "Classificação por Confiança e Segurança | Nerq", "ranked by Nerq Trust Score. Independent security and trust analysis.": "classificados pelo Nerq Trust Score. Análise independente de segurança e confiança.", "Browse all categories": "Ver todas as categorias", "Not enough data yet.": "Ainda não há dados suficientes.", "Browse other categories": "Ver outras categorias"},
    "id": {"Ranked by Nerq Trust Score. Last updated": "Diurutkan berdasarkan Nerq Trust Score. Terakhir diperbarui", "Ranked by Trust &amp; Security | Nerq": "Peringkat berdasarkan Kepercayaan dan Keamanan | Nerq", "ranked by Nerq Trust Score. Independent security and trust analysis.": "berdasarkan Nerq Trust Score. Analisis keamanan dan kepercayaan independen.", "Browse all categories": "Jelajahi semua kategori", "Not enough data yet.": "Belum cukup data.", "Browse other categories": "Jelajahi kategori lainnya"},
    "cs": {"Ranked by Nerq Trust Score. Last updated": "Řazeno podle Nerq Trust Score. Naposledy aktualizováno", "Ranked by Trust &amp; Security | Nerq": "Hodnocení podle důvěry a bezpečnosti | Nerq", "ranked by Nerq Trust Score. Independent security and trust analysis.": "řazeno podle Nerq Trust Score. Nezávislá bezpečnostní a důvěrnostní analýza.", "Browse all categories": "Procházet všechny kategorie", "Not enough data yet.": "Zatím nedostatek dat.", "Browse other categories": "Procházet další kategorie"},
    "th": {"Ranked by Nerq Trust Score. Last updated": "จัดอันดับตาม Nerq Trust Score อัปเดตล่าสุด", "Ranked by Trust &amp; Security | Nerq": "จัดอันดับตามความน่าเชื่อถือและความปลอดภัย | Nerq", "ranked by Nerq Trust Score. Independent security and trust analysis.": "จัดอันดับตาม Nerq Trust Score การวิเคราะห์ความปลอดภัยและความน่าเชื่อถืออิสระ", "Browse all categories": "เรียกดูทุกหมวดหมู่", "Not enough data yet.": "ยังไม่มีข้อมูลเพียงพอ", "Browse other categories": "เรียกดูหมวดหมู่อื่น"},
    "ro": {"Ranked by Nerq Trust Score. Last updated": "Clasificat după Nerq Trust Score. Ultima actualizare", "Ranked by Trust &amp; Security | Nerq": "Clasament după Încredere și Securitate | Nerq", "ranked by Nerq Trust Score. Independent security and trust analysis.": "clasate după Nerq Trust Score. Analiză independentă de securitate și încredere.", "Browse all categories": "Răsfoiți toate categoriile", "Not enough data yet.": "Încă nu sunt suficiente date.", "Browse other categories": "Răsfoiți alte categorii"},
    "tr": {"Ranked by Nerq Trust Score. Last updated": "Nerq Trust Score'a göre sıralanmıştır. Son güncelleme", "Ranked by Trust &amp; Security | Nerq": "Güven ve Güvenlik Sıralaması | Nerq", "ranked by Nerq Trust Score. Independent security and trust analysis.": "Nerq Trust Score'a göre sıralanmıştır. Bağımsız güvenlik ve güven analizi.", "Browse all categories": "Tüm kategorilere göz at", "Not enough data yet.": "Henüz yeterli veri yok.", "Browse other categories": "Diğer kategorilere göz at"},
    "hi": {"Ranked by Nerq Trust Score. Last updated": "Nerq Trust Score द्वारा रैंक किया गया। अंतिम अपडेट", "Ranked by Trust &amp; Security | Nerq": "विश्वास और सुरक्षा द्वारा रैंकिंग | Nerq", "ranked by Nerq Trust Score. Independent security and trust analysis.": "Nerq Trust Score द्वारा रैंक किया गया। स्वतंत्र सुरक्षा और विश्वास विश्लेषण।", "Browse all categories": "सभी श्रेणियां देखें", "Not enough data yet.": "अभी तक पर्याप्त डेटा नहीं है।", "Browse other categories": "अन्य श्रेणियां देखें"},
    "ru": {"Ranked by Nerq Trust Score. Last updated": "Ранжировано по Nerq Trust Score. Последнее обновление", "Ranked by Trust &amp; Security | Nerq": "Рейтинг по доверию и безопасности | Nerq", "ranked by Nerq Trust Score. Independent security and trust analysis.": "ранжированы по Nerq Trust Score. Независимый анализ безопасности и доверия.", "Browse all categories": "Просмотреть все категории", "Not enough data yet.": "Пока недостаточно данных.", "Browse other categories": "Просмотреть другие категории"},
    "pl": {"Ranked by Nerq Trust Score. Last updated": "Uszeregowane wg Nerq Trust Score. Ostatnia aktualizacja", "Ranked by Trust &amp; Security | Nerq": "Ranking według zaufania i bezpieczeństwa | Nerq", "ranked by Nerq Trust Score. Independent security and trust analysis.": "uszeregowane wg Nerq Trust Score. Niezależna analiza bezpieczeństwa i zaufania.", "Browse all categories": "Przeglądaj wszystkie kategorie", "Not enough data yet.": "Jeszcze nie ma wystarczających danych.", "Browse other categories": "Przeglądaj inne kategorie"},
    "it": {"Ranked by Nerq Trust Score. Last updated": "Classificato per Nerq Trust Score. Ultimo aggiornamento", "Ranked by Trust &amp; Security | Nerq": "Classificato per Fiducia e Sicurezza | Nerq", "ranked by Nerq Trust Score. Independent security and trust analysis.": "classificati per Nerq Trust Score. Analisi indipendente di sicurezza e fiducia.", "Browse all categories": "Sfoglia tutte le categorie", "Not enough data yet.": "Non ci sono ancora abbastanza dati.", "Browse other categories": "Sfoglia altre categorie"},
    "ko": {"Ranked by Nerq Trust Score. Last updated": "Nerq Trust Score 기준 순위. 마지막 업데이트", "Ranked by Trust &amp; Security | Nerq": "신뢰도 및 보안 순위 | Nerq", "ranked by Nerq Trust Score. Independent security and trust analysis.": "Nerq Trust Score 기준 순위. 독립적인 보안 및 신뢰 분석.", "Browse all categories": "모든 카테고리 보기", "Not enough data yet.": "아직 충분한 데이터가 없습니다.", "Browse other categories": "다른 카테고리 보기"},
    "vi": {"Ranked by Nerq Trust Score. Last updated": "Xếp hạng theo Nerq Trust Score. Cập nhật lần cuối", "Ranked by Trust &amp; Security | Nerq": "Xếp hạng theo Tin cậy và Bảo mật | Nerq", "ranked by Nerq Trust Score. Independent security and trust analysis.": "xếp hạng theo Nerq Trust Score. Phân tích bảo mật và tin cậy độc lập.", "Browse all categories": "Duyệt tất cả danh mục", "Not enough data yet.": "Chưa đủ dữ liệu.", "Browse other categories": "Duyệt danh mục khác"},
    "nl": {"Ranked by Nerq Trust Score. Last updated": "Gerangschikt op Nerq Trust Score. Laatst bijgewerkt", "Ranked by Trust &amp; Security | Nerq": "Ranglijst op Vertrouwen en Veiligheid | Nerq", "ranked by Nerq Trust Score. Independent security and trust analysis.": "gerangschikt op Nerq Trust Score. Onafhankelijke veiligheids- en vertrouwensanalyse.", "Browse all categories": "Alle categorieën bekijken", "Not enough data yet.": "Nog niet genoeg gegevens.", "Browse other categories": "Andere categorieën bekijken"},
    "sv": {"Ranked by Nerq Trust Score. Last updated": "Rankad efter Nerq Trust Score. Senast uppdaterad", "Ranked by Trust &amp; Security | Nerq": "Rankat efter Tillit och Säkerhet | Nerq", "ranked by Nerq Trust Score. Independent security and trust analysis.": "rankade efter Nerq Trust Score. Oberoende säkerhets- och tillitsanalys.", "Browse all categories": "Bläddra bland alla kategorier", "Not enough data yet.": "Inte tillräckligt med data ännu.", "Browse other categories": "Bläddra bland andra kategorier"},
    "zh": {"Ranked by Nerq Trust Score. Last updated": "按Nerq Trust Score排名。最后更新", "Ranked by Trust &amp; Security | Nerq": "按信任度和安全性排名 | Nerq", "ranked by Nerq Trust Score. Independent security and trust analysis.": "按Nerq Trust Score排名。独立安全和信任分析。", "Browse all categories": "浏览所有分类", "Not enough data yet.": "数据暂时不足。", "Browse other categories": "浏览其他分类"},
    "da": {"Ranked by Nerq Trust Score. Last updated": "Rangeret efter Nerq Trust Score. Sidst opdateret", "Ranked by Trust &amp; Security | Nerq": "Rangeret efter Tillid og Sikkerhed | Nerq", "ranked by Nerq Trust Score. Independent security and trust analysis.": "rangeret efter Nerq Trust Score. Uafhængig sikkerheds- og tillidsanalyse.", "Browse all categories": "Gennemse alle kategorier", "Not enough data yet.": "Endnu ikke nok data.", "Browse other categories": "Gennemse andre kategorier"},
    "no": {"Ranked by Nerq Trust Score. Last updated": "Rangert etter Nerq Trust Score. Sist oppdatert", "Ranked by Trust &amp; Security | Nerq": "Rangert etter Tillit og Sikkerhet | Nerq", "ranked by Nerq Trust Score. Independent security and trust analysis.": "rangert etter Nerq Trust Score. Uavhengig sikkerhets- og tillitsanalyse.", "Browse all categories": "Bla gjennom alle kategorier", "Not enough data yet.": "Ikke nok data ennå.", "Browse other categories": "Bla gjennom andre kategorier"},
    "ar": {"Ranked by Nerq Trust Score. Last updated": "مُصنّف حسب Nerq Trust Score. آخر تحديث", "Ranked by Trust &amp; Security | Nerq": "مُصنّف حسب الثقة والأمان | Nerq", "ranked by Nerq Trust Score. Independent security and trust analysis.": "مُصنّف حسب Nerq Trust Score. تحليل أمان وثقة مستقل.", "Browse all categories": "تصفح جميع الفئات", "Not enough data yet.": "لا توجد بيانات كافية بعد.", "Browse other categories": "تصفح فئات أخرى"},
}

# ── /best/ page UI translations (lightweight, no _translate_html) ─────────────
# Used for title, H1, H2, table headers, verdict text on /{lang}/best/* pages.
# Sorted by length descending at application time to prevent partial matches.
_BEST_UI_STRINGS = {
    "vi": {
        "Best Safest VPNs": "VPN An Toàn Nhất",
        "Best Safest Password Managers": "Trình Quản Lý Mật Khẩu An Toàn Nhất",
        "Best Safest Web Hosting Providers": "Nhà Cung Cấp Hosting An Toàn Nhất",
        "Best Safest Antivirus Software": "Phần Mềm Diệt Virus An Toàn Nhất",
        "Best Safest Website Builders": "Trình Tạo Website An Toàn Nhất",
        "Best Safest SaaS Platforms": "Nền Tảng SaaS An Toàn Nhất",
        "Best Safest Crypto Exchanges": "Sàn Giao Dịch Crypto An Toàn Nhất",
        "Ranked by Trust &amp; Security | Nerq": "Xếp hạng theo Tin cậy &amp; Bảo mật | Nerq",
        "Ranked by Nerq Trust Score. Independent security and trust analysis.": "Xếp hạng theo Nerq Trust Score. Phân tích bảo mật và tin cậy độc lập.",
        "Rankings update daily — last updated": "Cập nhật hàng ngày — lần cuối",
        "How We Rank": "Cách Chúng Tôi Xếp Hạng",
        "Updated daily": "Cập nhật hàng ngày",
        "Safest VPNs": "VPN An Toàn Nhất", "Safest Password Managers": "Trình Quản Lý Mật Khẩu An Toàn Nhất",
        "Safest Web Hosting Providers": "Nhà Cung Cấp Hosting An Toàn Nhất", "Safest Antivirus Software": "Phần Mềm Diệt Virus An Toàn Nhất",
        "Safest Website Builders": "Trình Tạo Website An Toàn Nhất", "Safest SaaS Platforms": "Nền Tảng SaaS An Toàn Nhất",
        "Safest Crypto Exchanges": "Sàn Giao Dịch Crypto An Toàn Nhất",
        "Best WordPress Hosting": "Hosting WordPress Tốt Nhất", "Best VPS Hosting": "Hosting VPS Tốt Nhất",
        "Best Cloud Hosting": "Hosting Đám Mây Tốt Nhất", "Cheapest Web Hosting": "Hosting Giá Rẻ Nhất",
        "Best Free Antivirus": "Phần Mềm Diệt Virus Miễn Phí Tốt Nhất",
        "Best CRM Software": "Phần Mềm CRM Tốt Nhất", "Best Project Management Tools": "Công Cụ Quản Lý Dự Án Tốt Nhất",
        "Best Free Website Builders": "Trình Tạo Website Miễn Phí Tốt Nhất",
        "Best No-Code Platforms": "Nền Tảng No-Code Tốt Nhất",
        "Trust": "Tin cậy", "Grade": "Xếp hạng", "Stars": "Sao", "Description": "Mô tả", "Name": "Tên",
        "Build Your Security Stack": "Xây Dựng Bộ Bảo Mật",
        "Top 10": "Top 10", "by Nerq Trust Score": "theo Nerq Trust Score",
    },
    "ja": {
        "Best Safest VPNs": "最も安全なVPN",
        "Best Safest Password Managers": "最も安全なパスワードマネージャー",
        "Best Safest Antivirus Software": "最も安全なアンチウイルス",
        "Best Safest Crypto Exchanges": "最も安全な仮想通貨取引所",
        "Ranked by Trust &amp; Security | Nerq": "信頼性とセキュリティによるランキング | Nerq",
        "Ranked by Nerq Trust Score. Independent security and trust analysis.": "Nerq Trust Scoreによるランキング。独立したセキュリティと信頼性分析。",
        "Rankings update daily — last updated": "毎日更新 — 最終更新",
        "How We Rank": "ランキング方法",
        "Updated daily": "毎日更新",
        "Safest VPNs": "最も安全なVPN", "Safest Password Managers": "最も安全なパスワードマネージャー",
        "Safest Web Hosting Providers": "最も安全なホスティング", "Safest Antivirus Software": "最も安全なアンチウイルス",
        "Safest Website Builders": "最も安全なウェブサイトビルダー", "Safest SaaS Platforms": "最も安全なSaaSプラットフォーム",
        "Safest Crypto Exchanges": "最も安全な仮想通貨取引所",
        "Best Free Antivirus": "最高の無料アンチウイルス", "Best CRM Software": "最高のCRMソフトウェア",
        "Best Project Management Tools": "最高のプロジェクト管理ツール",
        "Trust": "信頼", "Grade": "評価", "Stars": "スター", "Description": "説明", "Name": "名前",
        "Build Your Security Stack": "セキュリティスタックを構築",
        "Top 10": "トップ10", "by Nerq Trust Score": "Nerq Trust Scoreによる",
    },
    "ar": {
        "Best Safest VPNs": "أكثر شبكات VPN أمانًا",
        "Best Safest Password Managers": "أكثر مديري كلمات المرور أمانًا",
        "Best Safest Antivirus Software": "أكثر برامج مكافحة الفيروسات أمانًا",
        "Ranked by Trust &amp; Security | Nerq": "مرتبة حسب الثقة والأمان | Nerq",
        "Ranked by Nerq Trust Score. Independent security and trust analysis.": "مرتبة حسب Nerq Trust Score. تحليل مستقل للأمان والثقة.",
        "Rankings update daily — last updated": "يتم التحديث يوميًا — آخر تحديث",
        "How We Rank": "كيف نصنف",
        "Updated daily": "يتم التحديث يوميًا",
        "Safest VPNs": "أكثر شبكات VPN أمانًا", "Safest Password Managers": "أكثر مديري كلمات المرور أمانًا",
        "Safest Web Hosting Providers": "أكثر مزودي الاستضافة أمانًا", "Safest Antivirus Software": "أكثر برامج مكافحة الفيروسات أمانًا",
        "Safest Website Builders": "أكثر منشئي المواقع أمانًا", "Safest SaaS Platforms": "أكثر منصات SaaS أمانًا",
        "Safest Crypto Exchanges": "أكثر بورصات العملات المشفرة أمانًا",
        "Best Free Antivirus": "أفضل مضاد فيروسات مجاني", "Best CRM Software": "أفضل برنامج CRM",
        "Trust": "الثقة", "Grade": "التقييم", "Stars": "النجوم", "Description": "الوصف", "Name": "الاسم",
        "Build Your Security Stack": "بناء حزمة الأمان الخاصة بك",
        "Top 10": "أفضل 10", "by Nerq Trust Score": "حسب Nerq Trust Score",
    },
    "sv": {
        "Best Safest VPNs": "Säkraste VPN",
        "Best Safest Password Managers": "Säkraste lösenordshanterare",
        "Best Safest Antivirus Software": "Säkraste antivirusprogram",
        "Ranked by Trust &amp; Security | Nerq": "Rankade efter tillit och säkerhet | Nerq",
        "Ranked by Nerq Trust Score. Independent security and trust analysis.": "Rankade efter Nerq Trust Score. Oberoende säkerhets- och tillitsanalys.",
        "Rankings update daily — last updated": "Uppdateras dagligen — senast uppdaterad",
        "How We Rank": "Hur vi rankar",
        "Updated daily": "Uppdateras dagligen",
        "Safest VPNs": "Säkraste VPN", "Safest Password Managers": "Säkraste lösenordshanterare",
        "Safest Web Hosting Providers": "Säkraste webbhotell", "Safest Antivirus Software": "Säkraste antivirusprogram",
        "Safest Website Builders": "Säkraste webbplatsbyggare", "Safest SaaS Platforms": "Säkraste SaaS-plattformar",
        "Safest Crypto Exchanges": "Säkraste kryptobörser",
        "Best Free Antivirus": "Bästa gratis antivirus", "Best CRM Software": "Bästa CRM-program",
        "Trust": "Tillit", "Grade": "Betyg", "Stars": "Stjärnor", "Description": "Beskrivning", "Name": "Namn",
        "Build Your Security Stack": "Bygg Ditt Säkerhetspaket",
        "Top 10": "Topp 10", "by Nerq Trust Score": "efter Nerq-förtroendepoäng",
    },
    "de": {
        "Best Safest VPNs": "Sicherste VPNs",
        "Best Safest Password Managers": "Sicherste Passwort-Manager",
        "Best Safest Antivirus Software": "Sicherste Antivirus-Software",
        "Ranked by Trust &amp; Security | Nerq": "Bewertet nach Vertrauen und Sicherheit | Nerq",
        "Ranked by Nerq Trust Score. Independent security and trust analysis.": "Bewertet nach Nerq Trust Score. Unabhängige Sicherheits- und Vertrauensanalyse.",
        "Rankings update daily — last updated": "Tägliche Aktualisierung — zuletzt aktualisiert",
        "How We Rank": "So bewerten wir",
        "Updated daily": "Täglich aktualisiert",
        "Safest VPNs": "Sicherste VPNs", "Safest Password Managers": "Sicherste Passwort-Manager",
        "Safest Web Hosting Providers": "Sicherste Hosting-Anbieter", "Safest Antivirus Software": "Sicherste Antivirus-Software",
        "Safest Website Builders": "Sicherste Website-Baukästen", "Safest SaaS Platforms": "Sicherste SaaS-Plattformen",
        "Safest Crypto Exchanges": "Sicherste Krypto-Börsen",
        "Best Free Antivirus": "Bestes kostenloses Antivirus", "Best CRM Software": "Beste CRM-Software",
        "Trust": "Vertrauen", "Grade": "Note", "Stars": "Sterne", "Description": "Beschreibung", "Name": "Name",
        "Build Your Security Stack": "Bauen Sie Ihr Sicherheitspaket",
        "Top 10": "Top 10", "by Nerq Trust Score": "nach Nerq-Vertrauenswertung",
    },
    "es": {
        "Best CRM Software": "Mejor Software CRM",
        "Best Free Antivirus": "Mejor Antivirus Gratis",
        "Best Project Management Tools": "Mejores Herramientas de Gestión de Proyectos",
        "Best Safest VPNs": "VPNs más seguros",
        "Best Safest Password Managers": "Gestores de contraseñas más seguros",
        "Ranked by Trust &amp; Security | Nerq": "Clasificados por Confianza y Seguridad | Nerq",
        "Rankings update daily — last updated": "Se actualiza diariamente — última actualización",
        "How We Rank": "Cómo clasificamos",
        "Updated daily": "Se actualiza diariamente",
        "Safest VPNs": "VPNs más seguros", "Safest Password Managers": "Gestores de contraseñas más seguros",
        "Safest Web Hosting Providers": "Proveedores de hosting más seguros", "Safest Antivirus Software": "Antivirus más seguros",
        "Safest Website Builders": "Creadores de sitios web más seguros", "Safest SaaS Platforms": "Plataformas SaaS más seguras",
        "Safest Crypto Exchanges": "Exchanges de criptomonedas más seguros",
        "Trust": "Confianza", "Grade": "Grado", "Stars": "Estrellas", "Description": "Descripción", "Name": "Nombre",
        "Build Your Security Stack": "Construye Tu Paquete de Seguridad",
        "Top 10": "Top 10", "by Nerq Trust Score": "por Nerq Trust Score",
    },
    "fr": {
        "Best CRM Software": "Meilleur Logiciel CRM",
        "Best Free Antivirus": "Meilleur Antivirus Gratuit",
        "Best Project Management Tools": "Meilleurs Outils de Gestion de Projet",
        "Best Safest VPNs": "VPN les plus sûrs",
        "Best Safest Password Managers": "Gestionnaires de mots de passe les plus sûrs",
        "Ranked by Trust &amp; Security | Nerq": "Classés par Confiance et Sécurité | Nerq",
        "Rankings update daily — last updated": "Mise à jour quotidienne — dernière mise à jour",
        "How We Rank": "Comment nous classons",
        "Updated daily": "Mise à jour quotidienne",
        "Safest VPNs": "VPN les plus sûrs", "Safest Password Managers": "Gestionnaires de mots de passe les plus sûrs",
        "Safest Web Hosting Providers": "Hébergeurs les plus sûrs", "Safest Antivirus Software": "Antivirus les plus sûrs",
        "Safest Website Builders": "Créateurs de sites les plus sûrs", "Safest SaaS Platforms": "Plateformes SaaS les plus sûres",
        "Safest Crypto Exchanges": "Échanges crypto les plus sûrs",
        "Trust": "Confiance", "Grade": "Note", "Stars": "Étoiles", "Description": "Description", "Name": "Nom",
        "Build Your Security Stack": "Construisez Votre Suite de Sécurité",
        "Top 10": "Top 10", "by Nerq Trust Score": "par Nerq Trust Score",
    },
    "ko": {
        "Best CRM Software": "최고의 CRM 소프트웨어",
        "Best Free Antivirus": "최고의 무료 백신",
        "Best Project Management Tools": "최고의 프로젝트 관리 도구",
        "Best Safest VPNs": "가장 안전한 VPN",
        "Best Safest Password Managers": "가장 안전한 비밀번호 관리자",
        "Ranked by Trust &amp; Security | Nerq": "신뢰 및 보안 기준 순위 | Nerq",
        "Rankings update daily — last updated": "매일 업데이트 — 마지막 업데이트",
        "How We Rank": "순위 방법",
        "Updated daily": "매일 업데이트",
        "Safest VPNs": "가장 안전한 VPN", "Safest Password Managers": "가장 안전한 비밀번호 관리자",
        "Safest Web Hosting Providers": "가장 안전한 호스팅", "Safest Antivirus Software": "가장 안전한 백신",
        "Safest Website Builders": "가장 안전한 웹사이트 빌더", "Safest SaaS Platforms": "가장 안전한 SaaS 플랫폼",
        "Safest Crypto Exchanges": "가장 안전한 암호화폐 거래소",
        "Trust": "신뢰", "Grade": "등급", "Stars": "별점", "Description": "설명", "Name": "이름",
        "Build Your Security Stack": "보안 스택 구축",
        "Top 10": "상위 10", "by Nerq Trust Score": "Nerq 신뢰 점수 기준",
    },
    "zh": {
        "Best CRM Software": "最佳CRM软件",
        "Best Free Antivirus": "最佳免费杀毒软件",
        "Best Project Management Tools": "最佳项目管理工具",
        "Best Safest VPNs": "最安全的VPN",
        "Best Safest Password Managers": "最安全的密码管理器",
        "Ranked by Trust &amp; Security | Nerq": "按信任度和安全性排名 | Nerq",
        "Rankings update daily — last updated": "每日更新 — 最后更新",
        "How We Rank": "排名方法",
        "Updated daily": "每日更新",
        "Safest VPNs": "最安全的VPN", "Safest Password Managers": "最安全的密码管理器",
        "Safest Web Hosting Providers": "最安全的托管服务商", "Safest Antivirus Software": "最安全的杀毒软件",
        "Safest Website Builders": "最安全的网站构建器", "Safest SaaS Platforms": "最安全的SaaS平台",
        "Safest Crypto Exchanges": "最安全的加密货币交易所",
        "Trust": "信任", "Grade": "评级", "Stars": "星标", "Description": "描述", "Name": "名称",
        "Build Your Security Stack": "构建您的安全套件",
        "Top 10": "前10名", "by Nerq Trust Score": "按Nerq Trust Score",
    },
    "pt": {
        "Safest Web Hosting Providers": "Provedores de Hospedagem Mais Seguros",
        "Safest Website Builders": "Criadores de Sites Mais Seguros",
        "Safest SaaS Platforms": "Plataformas SaaS Mais Seguras",
        "Best WordPress Hosting": "Melhor Hospedagem WordPress",
        "Best VPS Hosting": "Melhor Hospedagem VPS",
        "Best Cloud Hosting": "Melhor Hospedagem em Nuvem",
        "Cheapest Web Hosting": "Hospedagem Mais Barata",
        "Best Free Antivirus": "Melhor Antivírus Grátis",
        "Best CRM Software": "Melhor Software CRM",
        "Best Project Management Tools": "Melhores Ferramentas de Gestão de Projetos",
        "Best Free Website Builders": "Melhores Criadores de Sites Grátis",
        "Best No-Code Platforms": "Melhores Plataformas No-Code",
        "Rankings update daily — last updated": "Atualizado diariamente — última atualização",
        "Build Your Security Stack": "Monte Seu Kit de Segurança",
        "Best Safest VPNs": "VPNs Mais Seguros",
        "Best Safest Password Managers": "Gerenciadores de Senhas Mais Seguros",
        "Best Safest Web Hosting Providers": "Provedores de Hospedagem Mais Seguros",
        "Best Safest Antivirus Software": "Antivírus Mais Seguros",
        "Best Safest Website Builders": "Criadores de Sites Mais Seguros",
        "Best Safest SaaS Platforms": "Plataformas SaaS Mais Seguras",
        "Best Safest Crypto Exchanges": "Exchanges de Cripto Mais Seguros",
        "Ranked by Trust &amp; Security | Nerq": "Classificados por Confiança e Segurança | Nerq",
        "How We Rank": "Como classificamos", "Updated daily": "Atualizado diariamente",
        "Safest VPNs": "VPNs mais seguros", "Safest Password Managers": "Gerenciadores de senhas mais seguros",
        "Safest Antivirus Software": "Antivírus mais seguros", "Safest Crypto Exchanges": "Exchanges mais seguros",
        "Trust": "Confiança", "Grade": "Nota", "Stars": "Estrelas", "Description": "Descrição", "Name": "Nome",
        "Top 10": "Top 10", "by Nerq Trust Score": "por Nerq Trust Score",
    },
    "id": {
        "Safest Web Hosting Providers": "Penyedia Hosting Teraman",
        "Safest Website Builders": "Pembuat Situs Teraman",
        "Safest SaaS Platforms": "Platform SaaS Teraman",
        "Safest Crypto Exchanges": "Bursa Kripto Teraman",
        "Best Free Antivirus": "Antivirus Gratis Terbaik",
        "Best CRM Software": "Software CRM Terbaik",
        "Best Project Management Tools": "Alat Manajemen Proyek Terbaik",
        "Ranked by Trust &amp; Security | Nerq": "Diperingkat berdasarkan Kepercayaan dan Keamanan | Nerq",
        "Rankings update daily — last updated": "Diperbarui setiap hari — terakhir diperbarui",
        "Build Your Security Stack": "Bangun Paket Keamanan Anda",
        "Best Safest VPNs": "VPN Teraman",
        "Best Safest Password Managers": "Pengelola Kata Sandi Teraman",
        "Best Safest Antivirus Software": "Antivirus Teraman",
        "Best Safest Crypto Exchanges": "Bursa Kripto Teraman",
        "Best Safest Web Hosting Providers": "Penyedia Hosting Teraman",
        "Best Safest Website Builders": "Pembuat Situs Teraman",
        "Best Safest SaaS Platforms": "Platform SaaS Teraman",
        "How We Rank": "Cara Kami Memberi Peringkat", "Updated daily": "Diperbarui setiap hari",
        "Safest VPNs": "VPN Teraman", "Safest Password Managers": "Pengelola Kata Sandi Teraman",
        "Safest Antivirus Software": "Antivirus Teraman",
        "Trust": "Kepercayaan", "Grade": "Nilai", "Description": "Deskripsi", "Name": "Nama",
        "Top 10": "10 Teratas", "by Nerq Trust Score": "berdasarkan Nerq Trust Score",
    },
    "nl": {
        "Safest Web Hosting Providers": "Veiligste Hostingproviders",
        "Safest Antivirus Software": "Veiligste Antivirussoftware",
        "Safest Website Builders": "Veiligste Websitebouwers",
        "Safest SaaS Platforms": "Veiligste SaaS-platforms",
        "Safest Crypto Exchanges": "Veiligste Cryptobeurzen",
        "Best WordPress Hosting": "Beste WordPress Hosting",
        "Best Free Antivirus": "Beste Gratis Antivirus",
        "Best CRM Software": "Beste CRM-software",
        "Best Project Management Tools": "Beste Projectmanagementtools",
        "Best Free Website Builders": "Beste Gratis Websitebouwers",
        "Best No-Code Platforms": "Beste No-Code Platforms",
        "Ranked by Trust &amp; Security | Nerq": "Gerangschikt op Vertrouwen en Beveiliging | Nerq",
        "Rankings update daily — last updated": "Dagelijks bijgewerkt — laatst bijgewerkt",
        "Build Your Security Stack": "Bouw uw beveiligingspakket",
        "Best Safest VPNs": "Veiligste VPN's",
        "Best Safest Password Managers": "Veiligste Wachtwoordmanagers",
        "Best Safest Antivirus Software": "Veiligste Antivirussoftware",
        "Best Safest Crypto Exchanges": "Veiligste Cryptobeurzen",
        "Best Safest Web Hosting Providers": "Veiligste Hostingproviders",
        "Best Safest Website Builders": "Veiligste Websitebouwers",
        "Best Safest SaaS Platforms": "Veiligste SaaS-platforms",
        "How We Rank": "Hoe wij rangschikken", "Updated daily": "Dagelijks bijgewerkt",
        "Safest VPNs": "Veiligste VPN's", "Safest Password Managers": "Veiligste wachtwoordmanagers",
        "Trust": "Vertrouwen", "Grade": "Cijfer", "Description": "Beschrijving", "Name": "Naam",
        "Top 10": "Top 10", "by Nerq Trust Score": "op Nerq-vertrouwensscore",
    },
    "da": {
        "Safest Web Hosting Providers": "Sikreste hostingudbydere",
        "Safest Antivirus Software": "Sikreste antivirusprogrammer",
        "Safest Website Builders": "Sikreste hjemmesidebyggere",
        "Safest SaaS Platforms": "Sikreste SaaS-platforme",
        "Safest Crypto Exchanges": "Sikreste kryptobørser",
        "Best Free Antivirus": "Bedste gratis antivirus",
        "Best CRM Software": "Bedste CRM-software",
        "Ranked by Trust &amp; Security | Nerq": "Rangeret efter tillid og sikkerhed | Nerq",
        "Rankings update daily — last updated": "Opdateres dagligt — sidst opdateret",
        "Build Your Security Stack": "Byg din sikkerhedspakke",
        "Best Safest VPNs": "Sikreste VPN'er",
        "Best Safest Password Managers": "Sikreste adgangskodeadministratorer",
        "Best Safest Antivirus Software": "Sikreste antivirusprogrammer",
        "Best Safest Crypto Exchanges": "Sikreste kryptobørser",
        "Best Safest Web Hosting Providers": "Sikreste hostingudbydere",
        "Best Safest Website Builders": "Sikreste hjemmesidebyggere",
        "Best Safest SaaS Platforms": "Sikreste SaaS-platforme",
        "How We Rank": "Sådan rangerer vi", "Updated daily": "Opdateres dagligt",
        "Safest VPNs": "Sikreste VPN'er", "Safest Password Managers": "Sikreste adgangskodeadministratorer",
        "Trust": "Tillid", "Grade": "Karakter", "Description": "Beskrivelse", "Name": "Navn",
        "Top 10": "Top 10", "by Nerq Trust Score": "efter Nerq Trust Score",
    },
    "no": {
        "Safest Web Hosting Providers": "Sikreste webhotell",
        "Safest Antivirus Software": "Sikreste antivirusprogramvare",
        "Safest Website Builders": "Sikreste nettstedsbyggere",
        "Safest SaaS Platforms": "Sikreste SaaS-plattformer",
        "Safest Crypto Exchanges": "Sikreste kryptobørser",
        "Best Free Antivirus": "Beste gratis antivirus",
        "Best CRM Software": "Beste CRM-programvare",
        "Ranked by Trust &amp; Security | Nerq": "Rangert etter tillit og sikkerhet | Nerq",
        "Ranked by Nerq Trust Score. Independent security and trust analysis.": "Rangert etter Nerq-tillitspoeng. Uavhengig sikkerhets- og tillitsanalyse.",
        "Rankings update daily — last updated": "Rangeringer oppdateres daglig — sist oppdatert",
        "Build Your Security Stack": "Bygg sikkerhetspakken din",
        "Best Safest VPNs": "Sikreste VPN-er",
        "Best Safest Password Managers": "Sikreste passordbehandlere",
        "Best Safest Antivirus Software": "Sikreste antivirusprogramvare",
        "Best Safest Crypto Exchanges": "Sikreste kryptobørser",
        "Best Safest Web Hosting Providers": "Sikreste webhotell",
        "Best Safest Website Builders": "Sikreste nettstedsbyggere",
        "Best Safest SaaS Platforms": "Sikreste SaaS-plattformer",
        "How We Rank": "Hvordan vi rangerer", "Updated daily": "Oppdateres daglig",
        "Safest VPNs": "Sikreste VPN-er", "Safest Password Managers": "Sikreste passordbehandlere",
        "Trust": "Tillit", "Grade": "Karakter", "Stars": "Stjerner", "Description": "Beskrivelse", "Name": "Navn",
        "Top 10": "Topp 10", "by Nerq Trust Score": "etter Nerq-tillitspoeng",
    },
    "pl": {
        "Safest Password Managers": "Najbezpieczniejsze menedżery haseł",
        "Safest Web Hosting Providers": "Najbezpieczniejsze usługi hostingowe",
        "Safest Antivirus Software": "Najbezpieczniejsze programy antywirusowe",
        "Safest Website Builders": "Najbezpieczniejsze kreatory stron",
        "Safest SaaS Platforms": "Najbezpieczniejsze platformy SaaS",
        "Safest Crypto Exchanges": "Najbezpieczniejsze giełdy kryptowalut",
        "Best Free Antivirus": "Najlepszy darmowy antywirus",
        "Best CRM Software": "Najlepsze oprogramowanie CRM",
        "Ranked by Trust &amp; Security | Nerq": "Ranking według zaufania i bezpieczeństwa | Nerq",
        "Rankings update daily — last updated": "Aktualizowane codziennie — ostatnia aktualizacja",
        "Build Your Security Stack": "Zbuduj swój pakiet bezpieczeństwa",
        "Best Safest VPNs": "Najbezpieczniejsze VPN",
        "Best Safest Password Managers": "Najbezpieczniejsze menedżery haseł",
        "Best Safest Antivirus Software": "Najbezpieczniejsze programy antywirusowe",
        "Best Safest Crypto Exchanges": "Najbezpieczniejsze giełdy kryptowalut",
        "Best Safest Web Hosting Providers": "Najbezpieczniejsze usługi hostingowe",
        "Best Safest Website Builders": "Najbezpieczniejsze kreatory stron",
        "Best Safest SaaS Platforms": "Najbezpieczniejsze platformy SaaS",
        "How We Rank": "Jak oceniamy", "Safest VPNs": "Najbezpieczniejsze VPN",
        "Trust": "Zaufanie", "Grade": "Ocena", "Description": "Opis", "Name": "Nazwa",
        "Top 10": "Top 10", "by Nerq Trust Score": "wg Nerq Trust Score",
    },
    "ru": {
        "Safest Password Managers": "Самые безопасные менеджеры паролей",
        "Safest Web Hosting Providers": "Самые безопасные хостинг-провайдеры",
        "Safest Antivirus Software": "Самые безопасные антивирусы",
        "Safest Website Builders": "Самые безопасные конструкторы сайтов",
        "Safest SaaS Platforms": "Самые безопасные SaaS-платформы",
        "Safest Crypto Exchanges": "Самые безопасные криптобиржи",
        "Best Free Antivirus": "Лучший бесплатный антивирус",
        "Best CRM Software": "Лучшее CRM-программное обеспечение",
        "Ranked by Trust &amp; Security | Nerq": "Рейтинг по доверию и безопасности | Nerq",
        "Rankings update daily — last updated": "Обновляется ежедневно — последнее обновление",
        "Build Your Security Stack": "Соберите свой набор безопасности",
        "Best Safest VPNs": "Самые безопасные VPN",
        "Best Safest Password Managers": "Самые безопасные менеджеры паролей",
        "Best Safest Antivirus Software": "Самые безопасные антивирусы",
        "Best Safest Crypto Exchanges": "Самые безопасные криптобиржи",
        "Best Safest Web Hosting Providers": "Самые безопасные хостинг-провайдеры",
        "Best Safest Website Builders": "Самые безопасные конструкторы сайтов",
        "Best Safest SaaS Platforms": "Самые безопасные SaaS-платформы",
        "How We Rank": "Как мы оцениваем", "Safest VPNs": "Самые безопасные VPN",
        "Trust": "Доверие", "Grade": "Оценка", "Description": "Описание", "Name": "Название",
        "Top 10": "Топ-10", "by Nerq Trust Score": "по Nerq Trust Score",
    },
    "it": {
        "Safest Password Managers": "Gestori di password più sicuri",
        "Safest Web Hosting Providers": "Provider hosting più sicuri",
        "Safest Antivirus Software": "Antivirus più sicuri",
        "Safest Website Builders": "Creatori di siti più sicuri",
        "Safest SaaS Platforms": "Piattaforme SaaS più sicure",
        "Safest Crypto Exchanges": "Exchange crypto più sicuri",
        "Best Free Antivirus": "Miglior antivirus gratuito",
        "Best CRM Software": "Miglior software CRM",
        "Ranked by Trust &amp; Security | Nerq": "Classificati per affidabilità e sicurezza | Nerq",
        "Rankings update daily — last updated": "Aggiornato quotidianamente — ultimo aggiornamento",
        "Build Your Security Stack": "Costruisci il Tuo Kit di Sicurezza",
        "Best Safest VPNs": "VPN più sicure",
        "Best Safest Password Managers": "Gestori di password più sicuri",
        "Best Safest Antivirus Software": "Antivirus più sicuri",
        "Best Safest Crypto Exchanges": "Exchange crypto più sicuri",
        "Best Safest Web Hosting Providers": "Provider hosting più sicuri",
        "Best Safest Website Builders": "Creatori di siti più sicuri",
        "Best Safest SaaS Platforms": "Piattaforme SaaS più sicure",
        "How We Rank": "Come classifichiamo", "Safest VPNs": "VPN più sicure",
        "Trust": "Fiducia", "Grade": "Voto", "Description": "Descrizione", "Name": "Nome",
        "Top 10": "Top 10", "by Nerq Trust Score": "per Nerq Trust Score",
    },
    "tr": {
        "Safest Password Managers": "En Güvenli Parola Yöneticileri",
        "Safest Web Hosting Providers": "En Güvenli Hosting Sağlayıcıları",
        "Safest Antivirus Software": "En Güvenli Antivirüs Yazılımları",
        "Safest Website Builders": "En Güvenli Web Sitesi Oluşturucuları",
        "Safest SaaS Platforms": "En Güvenli SaaS Platformları",
        "Safest Crypto Exchanges": "En Güvenli Kripto Borsaları",
        "Best Free Antivirus": "En İyi Ücretsiz Antivirüs",
        "Best CRM Software": "En İyi CRM Yazılımı",
        "Ranked by Trust &amp; Security | Nerq": "Güven ve Güvenliğe göre sıralanmış | Nerq",
        "Rankings update daily — last updated": "Her gün güncellenir — son güncelleme",
        "Build Your Security Stack": "Güvenlik Paketinizi Oluşturun",
        "Best Safest VPNs": "En Güvenli VPN'ler",
        "Best Safest Password Managers": "En Güvenli Parola Yöneticileri",
        "Best Safest Antivirus Software": "En Güvenli Antivirüs Yazılımları",
        "Best Safest Crypto Exchanges": "En Güvenli Kripto Borsaları",
        "Best Safest Web Hosting Providers": "En Güvenli Hosting Sağlayıcıları",
        "Best Safest Website Builders": "En Güvenli Web Sitesi Oluşturucuları",
        "Best Safest SaaS Platforms": "En Güvenli SaaS Platformları",
        "How We Rank": "Nasıl sıralıyoruz", "Safest VPNs": "En güvenli VPN'ler",
        "Trust": "Güven", "Grade": "Not", "Description": "Açıklama", "Name": "İsim",
        "Top 10": "En İyi 10", "by Nerq Trust Score": "Nerq Trust Score'a göre",
    },
    "hi": {
        "Safest Password Managers": "सबसे सुरक्षित पासवर्ड मैनेजर",
        "Safest Web Hosting Providers": "सबसे सुरक्षित होस्टिंग प्रदाता",
        "Safest Antivirus Software": "सबसे सुरक्षित एंटीवायरस",
        "Safest Website Builders": "सबसे सुरक्षित वेबसाइट बिल्डर",
        "Safest SaaS Platforms": "सबसे सुरक्षित SaaS प्लेटफ़ॉर्म",
        "Safest Crypto Exchanges": "सबसे सुरक्षित क्रिप्टो एक्सचेंज",
        "Best Free Antivirus": "सर्वश्रेष्ठ मुफ़्त एंटीवायरस",
        "Best CRM Software": "सर्वश्रेष्ठ CRM सॉफ़्टवेयर",
        "Ranked by Trust &amp; Security | Nerq": "विश्वास और सुरक्षा के आधार पर रैंकिंग | Nerq",
        "Rankings update daily — last updated": "प्रतिदिन अपडेट — अंतिम अपडेट",
        "Build Your Security Stack": "अपना सुरक्षा पैकेज बनाएं",
        "Best Safest VPNs": "सबसे सुरक्षित VPN",
        "Best Safest Password Managers": "सबसे सुरक्षित पासवर्ड मैनेजर",
        "Best Safest Antivirus Software": "सबसे सुरक्षित एंटीवायरस",
        "Best Safest Crypto Exchanges": "सबसे सुरक्षित क्रिप्टो एक्सचेंज",
        "Best Safest Web Hosting Providers": "सबसे सुरक्षित होस्टिंग प्रदाता",
        "Best Safest Website Builders": "सबसे सुरक्षित वेबसाइट बिल्डर",
        "Best Safest SaaS Platforms": "सबसे सुरक्षित SaaS प्लेटफ़ॉर्म",
        "How We Rank": "हम कैसे रैंक करते हैं", "Safest VPNs": "सबसे सुरक्षित VPN",
        "Trust": "विश्वास", "Grade": "ग्रेड", "Description": "विवरण", "Name": "नाम",
        "Top 10": "शीर्ष 10", "by Nerq Trust Score": "Nerq Trust Score के अनुसार",
    },
    "th": {
        "Safest Password Managers": "ตัวจัดการรหัสผ่านที่ปลอดภัยที่สุด",
        "Safest Web Hosting Providers": "ผู้ให้บริการโฮสติ้งที่ปลอดภัยที่สุด",
        "Safest Antivirus Software": "แอนตี้ไวรัสที่ปลอดภัยที่สุด",
        "Safest Website Builders": "เครื่องมือสร้างเว็บไซต์ที่ปลอดภัยที่สุด",
        "Safest SaaS Platforms": "แพลตฟอร์ม SaaS ที่ปลอดภัยที่สุด",
        "Safest Crypto Exchanges": "ตลาดคริปโตที่ปลอดภัยที่สุด",
        "Best Free Antivirus": "แอนตี้ไวรัสฟรีที่ดีที่สุด",
        "Best CRM Software": "ซอฟต์แวร์ CRM ที่ดีที่สุด",
        "Ranked by Trust &amp; Security | Nerq": "จัดอันดับตามความน่าเชื่อถือและความปลอดภัย | Nerq",
        "Rankings update daily — last updated": "อัปเดตทุกวัน — อัปเดตล่าสุด",
        "Build Your Security Stack": "สร้างชุดความปลอดภัยของคุณ",
        "Best Safest VPNs": "VPN ที่ปลอดภัยที่สุด",
        "Best Safest Password Managers": "ตัวจัดการรหัสผ่านที่ปลอดภัยที่สุด",
        "Best Safest Antivirus Software": "แอนตี้ไวรัสที่ปลอดภัยที่สุด",
        "Best Safest Crypto Exchanges": "ตลาดคริปโตที่ปลอดภัยที่สุด",
        "Best Safest Web Hosting Providers": "ผู้ให้บริการโฮสติ้งที่ปลอดภัยที่สุด",
        "Best Safest Website Builders": "เครื่องมือสร้างเว็บไซต์ที่ปลอดภัยที่สุด",
        "Best Safest SaaS Platforms": "แพลตฟอร์ม SaaS ที่ปลอดภัยที่สุด",
        "How We Rank": "วิธีจัดอันดับ", "Safest VPNs": "VPN ที่ปลอดภัยที่สุด",
        "Trust": "ความไว้วางใจ", "Grade": "เกรด", "Description": "คำอธิบาย", "Name": "ชื่อ",
        "Top 10": "10 อันดับแรก", "by Nerq Trust Score": "ตาม Nerq Trust Score",
    },
    "cs": {
        "Safest Password Managers": "Nejbezpečnější správci hesel",
        "Safest Web Hosting Providers": "Nejbezpečnější hostingové služby",
        "Safest Antivirus Software": "Nejbezpečnější antivirus",
        "Safest Website Builders": "Nejbezpečnější tvůrci webů",
        "Safest SaaS Platforms": "Nejbezpečnější SaaS platformy",
        "Safest Crypto Exchanges": "Nejbezpečnější kryptoburzy",
        "Best Free Antivirus": "Nejlepší bezplatný antivirus",
        "Best CRM Software": "Nejlepší CRM software",
        "Ranked by Trust &amp; Security | Nerq": "Hodnoceno podle důvěry a bezpečnosti | Nerq",
        "Rankings update daily — last updated": "Aktualizováno denně — poslední aktualizace",
        "Build Your Security Stack": "Sestavte si bezpečnostní sadu",
        "Best Safest VPNs": "Nejbezpečnější VPN",
        "Best Safest Password Managers": "Nejbezpečnější správci hesel",
        "Best Safest Antivirus Software": "Nejbezpečnější antivirus",
        "Best Safest Crypto Exchanges": "Nejbezpečnější kryptoburzy",
        "Best Safest Web Hosting Providers": "Nejbezpečnější hostingové služby",
        "Best Safest Website Builders": "Nejbezpečnější tvůrci webů",
        "Best Safest SaaS Platforms": "Nejbezpečnější SaaS platformy",
        "How We Rank": "Jak hodnotíme", "Safest VPNs": "Nejbezpečnější VPN",
        "Trust": "Důvěra", "Grade": "Hodnocení", "Description": "Popis", "Name": "Název",
        "Top 10": "Top 10", "by Nerq Trust Score": "podle Nerq Trust Score",
    },
    "ro": {
        "Safest Password Managers": "Cele mai sigure managere de parole",
        "Safest Web Hosting Providers": "Cele mai sigure servicii de hosting",
        "Safest Antivirus Software": "Cele mai sigure antivirusuri",
        "Safest Website Builders": "Cele mai sigure creatoare de site-uri",
        "Safest SaaS Platforms": "Cele mai sigure platforme SaaS",
        "Safest Crypto Exchanges": "Cele mai sigure burse crypto",
        "Best Free Antivirus": "Cel mai bun antivirus gratuit",
        "Best CRM Software": "Cel mai bun software CRM",
        "Ranked by Trust &amp; Security | Nerq": "Clasament după Încredere și Securitate | Nerq",
        "Rankings update daily — last updated": "Actualizat zilnic — ultima actualizare",
        "Build Your Security Stack": "Construiește-ți Pachetul de Securitate",
        "Best Safest VPNs": "Cele mai sigure VPN-uri",
        "Best Safest Password Managers": "Cele mai sigure managere de parole",
        "Best Safest Antivirus Software": "Cele mai sigure antivirusuri",
        "Best Safest Crypto Exchanges": "Cele mai sigure burse crypto",
        "Best Safest Web Hosting Providers": "Cele mai sigure servicii de hosting",
        "Best Safest Website Builders": "Cele mai sigure creatoare de site-uri",
        "Best Safest SaaS Platforms": "Cele mai sigure platforme SaaS",
        "How We Rank": "Cum clasificăm", "Safest VPNs": "Cele mai sigure VPN-uri",
        "Trust": "Încredere", "Grade": "Notă", "Description": "Descriere", "Name": "Nume",
        "Top 10": "Top 10", "by Nerq Trust Score": "după Nerq Trust Score",
    },
}

# Fully localized FAQ templates for /best/ pages — tuple: (heading, q1, a1, q2, a2, q3, a3, q4, a4, q5, a5)
_BEST_FAQ_I18N = {
    "sv": ("Vanliga frågor",
        "Vilka är de bästa {category} {year}?",
        "Baserat på Nerq-förtroendepoäng är de högst rankade {category} listade ovan, poängsatta på säkerhet, underhåll, dokumentation och communityanvändning.",
        "Hur rangordnas {category}?",
        "Nerq rankar verktyg med Trust Score v2, som kombinerar säkerhetsanalys, underhållsaktivitet, dokumentationskvalitet och communityanvändning.",
        "Är dessa {category} säkra att använda?",
        "Varje verktyg har en individuell säkerhetsrapport. Klicka på valfritt verktyg för att se dess detaljerade förtroendeanalys.",
        "Vad innebär ett Nerq Trust Score på A?",
        "Betyget A (80–89) innebär att entiteten har starka signaler inom säkerhet, underhåll, dokumentation och communityanvändning. A+ (90–100) är högsta möjliga betyg.",
        "Hur utvärderar Nerq {category}?",
        "Nerq analyserar {category} över flera dimensioner inklusive säkerhetssårbarheter, licensefterlevnad, underhållsaktivitet, dokumentationskvalitet och communityanvändning. Varje dimension poängsätts oberoende och kombineras till en övergripande förtroendepoäng (0–100)."),
    "de": ("Häufig gestellte Fragen",
        "Welche sind die besten {category} {year}?",
        "Basierend auf Nerq-Vertrauenswerten sind die bestbewerteten {category} oben aufgeführt, bewertet nach Sicherheit, Wartung, Dokumentation und Community-Nutzung.",
        "Wie werden {category} bewertet?",
        "Nerq bewertet Tools mit Trust Score v2, der Sicherheitsanalyse, Wartungsaktivität, Dokumentationsqualität und Community-Akzeptanz kombiniert.",
        "Sind diese {category} sicher zu verwenden?",
        "Jedes Tool hat einen individuellen Sicherheitsbericht. Klicken Sie auf einen Toolnamen, um die detaillierte Vertrauensanalyse zu sehen.",
        "Was bedeutet ein Nerq Trust Score von A?",
        "Die Note A (80–89) bedeutet, dass die Entität starke Signale in Sicherheit, Wartung, Dokumentation und Community-Akzeptanz hat. A+ (90–100) ist die höchste Bewertung.",
        "Wie bewertet Nerq {category}?",
        "Nerq analysiert {category} über mehrere Dimensionen einschließlich Sicherheitslücken, Lizenzkonformität, Wartungsaktivität, Dokumentationsqualität und Community-Nutzung. Jede Dimension wird unabhängig bewertet und zu einem Gesamt-Vertrauenswert (0–100) kombiniert."),
    "fr": ("Questions fréquentes",
        "Quels sont les meilleurs {category} en {year} ?",
        "Basé sur les scores de confiance Nerq, les {category} les mieux classés sont listés ci-dessus, évalués sur la sécurité, la maintenance, la documentation et l'adoption communautaire.",
        "Comment les {category} sont-ils classés ?",
        "Nerq classe les outils avec Trust Score v2, combinant analyse de sécurité, activité de maintenance, qualité de documentation et signaux d'adoption communautaire.",
        "Ces {category} sont-ils sûrs à utiliser ?",
        "Chaque outil dispose d'un rapport de sécurité individuel. Cliquez sur le nom d'un outil pour voir son analyse de confiance détaillée.",
        "Que signifie un Nerq Trust Score de A ?",
        "La note A (80–89) signifie que l'entité a de forts signaux en sécurité, maintenance, documentation et adoption communautaire. A+ (90–100) est la meilleure note possible.",
        "Comment Nerq évalue-t-il les {category} ?",
        "Nerq analyse les {category} sur plusieurs dimensions incluant les vulnérabilités, la conformité des licences, l'activité de maintenance, la qualité de documentation et l'adoption communautaire. Chaque dimension est notée indépendamment et combinée en un score de confiance global (0–100)."),
    "ja": ("よくある質問",
        "{year}年の最高の{category}は何ですか？",
        "Nerq信頼スコアに基づき、最高評価の{category}が上記にリストされています。セキュリティ、メンテナンス、ドキュメント、コミュニティ指標で評価されています。",
        "{category}はどのようにランク付けされますか？",
        "Nerqはセキュリティ分析、メンテナンス活動、ドキュメント品質、コミュニティ採用を組み合わせたTrust Score v2でツールをランク付けします。",
        "これらの{category}は安全に使用できますか？",
        "各ツールには個別の安全性レポートがあります。ツール名をクリックすると、詳細な信頼分析が表示されます。",
        "Nerq Trust ScoreのAとは何を意味しますか？",
        "Aグレード（80–89）は、セキュリティ、メンテナンス、ドキュメント、コミュニティ採用において強いシグナルを持つことを意味します。A+（90–100）は最高評価です。",
        "Nerqはどのように{category}を評価しますか？",
        "Nerqはセキュリティ脆弱性、ライセンス準拠、メンテナンス活動、ドキュメント品質、コミュニティ採用など複数の次元で{category}を分析します。各次元は独立してスコアリングされ、総合信頼スコア（0–100）に統合されます。"),
    "es": ("Preguntas frecuentes",
        "¿Cuáles son los mejores {category} en {year}?",
        "Basado en puntuaciones de confianza Nerq, los {category} mejor clasificados están listados arriba, evaluados en seguridad, mantenimiento, documentación y adopción comunitaria.",
        "¿Cómo se clasifican los {category}?",
        "Nerq clasifica herramientas usando Trust Score v2, que combina análisis de seguridad, actividad de mantenimiento, calidad de documentación y adopción comunitaria.",
        "¿Son seguros estos {category}?",
        "Cada herramienta tiene un informe de seguridad individual. Haga clic en cualquier nombre para ver su análisis de confianza detallado.",
        "¿Qué significa un Nerq Trust Score de A?",
        "La calificación A (80–89) significa que la entidad tiene señales fuertes en seguridad, mantenimiento, documentación y adopción comunitaria. A+ (90–100) es la calificación más alta.",
        "¿Cómo evalúa Nerq los {category}?",
        "Nerq analiza {category} en múltiples dimensiones incluyendo vulnerabilidades, cumplimiento de licencias, actividad de mantenimiento, calidad de documentación y adopción comunitaria. Cada dimensión se puntúa independientemente y se combina en una puntuación de confianza general (0–100)."),
    "pt": ("Perguntas frequentes",
        "Quais são os melhores {category} em {year}?",
        "Com base nas pontuações de confiança Nerq, os {category} mais bem classificados estão listados acima, avaliados em segurança, manutenção, documentação e adoção comunitária.",
        "Como os {category} são classificados?",
        "O Nerq classifica ferramentas usando o Trust Score v2, que combina análise de segurança, atividade de manutenção, qualidade de documentação e adoção comunitária.",
        "Estes {category} são seguros para usar?",
        "Cada ferramenta tem um relatório de segurança individual. Clique em qualquer nome para ver sua análise de confiança detalhada.",
        "O que significa um Nerq Trust Score de A?",
        "A nota A (80–89) significa que a entidade tem sinais fortes em segurança, manutenção, documentação e adoção comunitária. A+ (90–100) é a nota mais alta.",
        "Como o Nerq avalia {category}?",
        "O Nerq analisa {category} em múltiplas dimensões incluindo vulnerabilidades, conformidade de licenças, atividade de manutenção, qualidade de documentação e adoção comunitária. Cada dimensão é pontuada independentemente e combinada em uma pontuação de confiança geral (0–100)."),
    "ko": ("자주 묻는 질문",
        "{year}년 최고의 {category}는?",
        "Nerq 신뢰 점수를 기반으로 최고 등급의 {category}가 위에 나열되어 있으며, 보안, 유지관리, 문서화 및 커뮤니티 지표로 평가됩니다.",
        "{category}는 어떻게 순위가 매겨지나요?",
        "Nerq는 보안 분석, 유지관리 활동, 문서화 품질, 커뮤니티 채택을 결합한 Trust Score v2로 도구를 순위 매깁니다.",
        "이 {category}는 사용하기 안전한가요?",
        "각 도구에는 개별 안전 보고서가 있습니다. 도구 이름을 클릭하면 상세한 신뢰 분석을 볼 수 있습니다.",
        "Nerq Trust Score A는 무엇을 의미하나요?",
        "A 등급(80–89)은 보안, 유지관리, 문서화, 커뮤니티 채택에서 강한 신호를 가진다는 뜻입니다. A+(90–100)는 최고 등급입니다.",
        "Nerq는 {category}를 어떻게 평가하나요?",
        "Nerq는 보안 취약점, 라이선스 준수, 유지관리 활동, 문서화 품질, 커뮤니티 채택 등 여러 차원에서 {category}를 분석합니다. 각 차원은 독립적으로 점수가 매겨지고 전체 신뢰 점수(0–100)로 통합됩니다."),
    "zh": ("常见问题",
        "{year}年最佳{category}有哪些？",
        "根据Nerq信任评分，排名最高的{category}列于上方，从安全性、维护、文档和社区指标进行评估。",
        "{category}是如何排名的？",
        "Nerq使用Trust Score v2对工具进行排名，结合安全分析、维护活动、文档质量和社区采用信号。",
        "这些{category}安全可用吗？",
        "每个工具都有单独的安全报告。点击任意工具名称查看详细的信任分析。",
        "Nerq Trust Score A代表什么？",
        "A级（80–89）表示该实体在安全、维护、文档和社区采用方面有强烈信号。A+（90–100）是最高评级。",
        "Nerq如何评估{category}？",
        "Nerq从安全漏洞、许可证合规、维护活动、文档质量和社区采用等多个维度分析{category}。每个维度独立评分，合并为总体信任评分（0–100）。"),
    "ar": ("الأسئلة الشائعة",
        "ما هي أفضل {category} في {year}؟",
        "بناءً على درجات ثقة Nerq، تم إدراج أفضل {category} أعلاه، مع تقييم الأمان والصيانة والتوثيق واعتماد المجتمع.",
        "كيف يتم تصنيف {category}؟",
        "يصنف Nerq الأدوات باستخدام Trust Score v2، الذي يجمع بين تحليل الأمان ونشاط الصيانة وجودة التوثيق واعتماد المجتمع.",
        "هل هذه {category} آمنة للاستخدام؟",
        "لكل أداة تقرير أمان فردي. انقر على اسم أي أداة لمشاهدة تحليل الثقة التفصيلي.",
        "ماذا يعني Nerq Trust Score بدرجة A؟",
        "درجة A (80–89) تعني أن الكيان لديه إشارات قوية في الأمان والصيانة والتوثيق واعتماد المجتمع. A+ (90–100) هي أعلى تقييم ممكن.",
        "كيف يقيّم Nerq {category}؟",
        "يحلل Nerq {category} عبر أبعاد متعددة تشمل الثغرات الأمنية وامتثال التراخيص ونشاط الصيانة وجودة التوثيق واعتماد المجتمع. يتم تسجيل كل بُعد بشكل مستقل ودمجه في درجة ثقة إجمالية (0–100)."),
    "nl": ("Veelgestelde vragen",
        "Wat zijn de beste {category} in {year}?",
        "Op basis van Nerq-vertrouwensscores staan de best beoordeelde {category} hierboven, beoordeeld op beveiliging, onderhoud, documentatie en gemeenschapsacceptatie.",
        "Hoe worden {category} gerangschikt?",
        "Nerq rangschikt tools met Trust Score v2, dat beveiligingsanalyse, onderhoudsactiviteit, documentatiekwaliteit en gemeenschapsacceptatie combineert.",
        "Zijn deze {category} veilig om te gebruiken?",
        "Elke tool heeft een individueel veiligheidsrapport. Klik op een toolnaam om de gedetailleerde vertrouwensanalyse te zien.",
        "Wat betekent een Nerq Trust Score van A?",
        "De A-beoordeling (80–89) betekent dat de entiteit sterke signalen heeft op het gebied van beveiliging, onderhoud, documentatie en gemeenschapsacceptatie. A+ (90–100) is de hoogste beoordeling.",
        "Hoe beoordeelt Nerq {category}?",
        "Nerq analyseert {category} over meerdere dimensies waaronder beveiligingskwetsbaarheden, licentie-naleving, onderhoudsactiviteit, documentatiekwaliteit en gemeenschapsacceptatie. Elke dimensie wordt onafhankelijk gescoord en gecombineerd tot een totale vertrouwensscore (0–100)."),
    "vi": ("Câu hỏi thường gặp",
        "{category} tốt nhất năm {year} là gì?",
        "Dựa trên điểm tin cậy Nerq, các {category} được xếp hạng cao nhất được liệt kê ở trên, đánh giá về bảo mật, bảo trì, tài liệu và chấp nhận cộng đồng.",
        "{category} được xếp hạng như thế nào?",
        "Nerq xếp hạng công cụ bằng Trust Score v2, kết hợp phân tích bảo mật, hoạt động bảo trì, chất lượng tài liệu và tín hiệu chấp nhận cộng đồng.",
        "Các {category} này có an toàn để sử dụng không?",
        "Mỗi công cụ có báo cáo an toàn riêng. Nhấp vào tên công cụ để xem phân tích tin cậy chi tiết.",
        "Điểm Nerq Trust Score A có nghĩa là gì?",
        "Điểm A (80–89) có nghĩa là thực thể có tín hiệu mạnh về bảo mật, bảo trì, tài liệu và chấp nhận cộng đồng. A+ (90–100) là xếp hạng cao nhất.",
        "Nerq đánh giá {category} như thế nào?",
        "Nerq phân tích {category} trên nhiều chiều bao gồm lỗ hổng bảo mật, tuân thủ giấy phép, hoạt động bảo trì, chất lượng tài liệu và chấp nhận cộng đồng. Mỗi chiều được chấm điểm độc lập và kết hợp thành điểm tin cậy tổng thể (0–100)."),
    "id": ("Pertanyaan yang Sering Diajukan",
        "Apa {category} terbaik di tahun {year}?",
        "Berdasarkan skor kepercayaan Nerq, {category} dengan peringkat tertinggi tercantum di atas, dinilai berdasarkan keamanan, pemeliharaan, dokumentasi, dan adopsi komunitas.",
        "Bagaimana {category} dirangking?",
        "Nerq merangking alat menggunakan Trust Score v2, yang menggabungkan analisis keamanan, aktivitas pemeliharaan, kualitas dokumentasi, dan adopsi komunitas.",
        "Apakah {category} ini aman digunakan?",
        "Setiap alat memiliki laporan keamanan individual. Klik nama alat untuk melihat analisis kepercayaan detailnya.",
        "Apa arti Nerq Trust Score A?",
        "Nilai A (80–89) berarti entitas memiliki sinyal kuat di keamanan, pemeliharaan, dokumentasi, dan adopsi komunitas. A+ (90–100) adalah peringkat tertinggi.",
        "Bagaimana Nerq mengevaluasi {category}?",
        "Nerq menganalisis {category} di berbagai dimensi termasuk kerentanan keamanan, kepatuhan lisensi, aktivitas pemeliharaan, kualitas dokumentasi, dan adopsi komunitas. Setiap dimensi dinilai secara independen dan digabungkan menjadi skor kepercayaan keseluruhan (0–100)."),
    "cs": ("Často kladené otázky",
        "Jaké jsou nejlepší {category} v roce {year}?",
        "Na základě skóre důvěry Nerq jsou nejlépe hodnocené {category} uvedeny výše, hodnocené na bezpečnost, údržbu, dokumentaci a přijetí komunitou.",
        "Jak jsou {category} hodnoceny?",
        "Nerq hodnotí nástroje pomocí Trust Score v2, který kombinuje bezpečnostní analýzu, údržbu, kvalitu dokumentace a přijetí komunitou.",
        "Jsou tyto {category} bezpečné k použití?",
        "Každý nástroj má individuální bezpečnostní zprávu. Klikněte na název nástroje pro zobrazení detailní analýzy důvěry.",
        "Co znamená Nerq Trust Score A?",
        "Hodnocení A (80–89) znamená silné signály v bezpečnosti, údržbě, dokumentaci a přijetí komunitou. A+ (90–100) je nejvyšší možné hodnocení.",
        "Jak Nerq hodnotí {category}?",
        "Nerq analyzuje {category} v několika dimenzích včetně bezpečnostních zranitelností, souladu s licencemi, údržby, kvality dokumentace a přijetí komunitou. Každá dimenze je hodnocena nezávisle a kombinována do celkového skóre důvěry (0–100)."),
    "th": ("คำถามที่พบบ่อย",
        "{category} ที่ดีที่สุดในปี {year} คืออะไร?",
        "จากคะแนนความเชื่อถือ Nerq {category} ที่ได้รับการจัดอันดับสูงสุดอยู่ด้านบน ประเมินจากความปลอดภัย การดูแลรักษา เอกสาร และการยอมรับจากชุมชน",
        "{category} ถูกจัดอันดับอย่างไร?",
        "Nerq จัดอันดับเครื่องมือด้วย Trust Score v2 ซึ่งรวมการวิเคราะห์ความปลอดภัย กิจกรรมการดูแลรักษา คุณภาพเอกสาร และการยอมรับจากชุมชน",
        "{category} เหล่านี้ปลอดภัยหรือไม่?",
        "แต่ละเครื่องมือมีรายงานความปลอดภัยเฉพาะ คลิกชื่อเครื่องมือเพื่อดูการวิเคราะห์ความเชื่อถือโดยละเอียด",
        "Nerq Trust Score A หมายถึงอะไร?",
        "เกรด A (80–89) หมายความว่าเอนทิตีมีสัญญาณที่แข็งแกร่งในด้านความปลอดภัย การดูแลรักษา เอกสาร และการยอมรับจากชุมชน A+ (90–100) คือเกรดสูงสุด",
        "Nerq ประเมิน {category} อย่างไร?",
        "Nerq วิเคราะห์ {category} ในหลายมิติ รวมถึงช่องโหว่ด้านความปลอดภัย การปฏิบัติตามใบอนุญาต กิจกรรมการดูแลรักษา คุณภาพเอกสาร และการยอมรับจากชุมชน แต่ละมิติได้รับคะแนนอิสระและรวมเป็นคะแนนความเชื่อถือรวม (0–100)"),
    "tr": ("Sık Sorulan Sorular",
        "{year} yılının en iyi {category} hangileri?",
        "Nerq güven puanlarına göre en yüksek puanlı {category} yukarıda listelenmiştir; güvenlik, bakım, dokümantasyon ve topluluk benimsemesi üzerinden değerlendirilmiştir.",
        "{category} nasıl sıralanıyor?",
        "Nerq, güvenlik analizi, bakım etkinliği, dokümantasyon kalitesi ve topluluk benimsemesini birleştiren Trust Score v2 ile araçları sıralar.",
        "Bu {category} kullanmak güvenli mi?",
        "Her aracın bireysel bir güvenlik raporu vardır. Ayrıntılı güven analizini görmek için herhangi bir araç adına tıklayın.",
        "Nerq Trust Score A ne anlama geliyor?",
        "A notu (80–89), varlığın güvenlik, bakım, dokümantasyon ve topluluk benimsemesinde güçlü sinyallere sahip olduğu anlamına gelir. A+ (90–100) en yüksek nottur.",
        "Nerq {category}'ı nasıl değerlendiriyor?",
        "Nerq, güvenlik açıkları, lisans uyumluluğu, bakım etkinliği, dokümantasyon kalitesi ve topluluk benimsemesi dahil birden fazla boyutta {category}'ı analiz eder. Her boyut bağımsız olarak puanlanır ve genel güven puanına (0–100) birleştirilir."),
    "ro": ("Întrebări frecvente",
        "Care sunt cele mai bune {category} în {year}?",
        "Pe baza scorurilor de încredere Nerq, cele mai bine clasate {category} sunt listate mai sus, evaluate pe securitate, întreținere, documentare și adoptare comunitară.",
        "Cum sunt clasificate {category}?",
        "Nerq clasifică instrumentele folosind Trust Score v2, care combină analiza de securitate, activitatea de întreținere, calitatea documentării și adoptarea comunitară.",
        "Sunt aceste {category} sigure de utilizat?",
        "Fiecare instrument are un raport de securitate individual. Faceți clic pe numele unui instrument pentru a vedea analiza detaliată a încrederii.",
        "Ce înseamnă un Nerq Trust Score de A?",
        "Nota A (80–89) înseamnă că entitatea are semnale puternice în securitate, întreținere, documentare și adoptare comunitară. A+ (90–100) este cea mai mare notă posibilă.",
        "Cum evaluează Nerq {category}?",
        "Nerq analizează {category} pe mai multe dimensiuni inclusiv vulnerabilități de securitate, conformitate cu licențe, activitate de întreținere, calitate de documentare și adoptare comunitară. Fiecare dimensiune este notată independent și combinată într-un scor de încredere global (0–100)."),
    "hi": ("अक्सर पूछे जाने वाले प्रश्न",
        "{year} में सबसे अच्छे {category} कौन से हैं?",
        "Nerq विश्वास स्कोर के आधार पर, सबसे अधिक रेटेड {category} ऊपर सूचीबद्ध हैं, सुरक्षा, रखरखाव, प्रलेखन और सामुदायिक अपनाव पर मूल्यांकित।",
        "{category} की रैंकिंग कैसे होती है?",
        "Nerq सुरक्षा विश्लेषण, रखरखाव गतिविधि, प्रलेखन गुणवत्ता और सामुदायिक अपनाव को मिलाकर Trust Score v2 से रैंक करता है।",
        "क्या ये {category} उपयोग के लिए सुरक्षित हैं?",
        "प्रत्येक उपकरण का एक व्यक्तिगत सुरक्षा रिपोर्ट है। विस्तृत विश्वास विश्लेषण देखने के लिए किसी भी उपकरण के नाम पर क्लिक करें।",
        "Nerq Trust Score A का क्या अर्थ है?",
        "A ग्रेड (80–89) का अर्थ है कि इकाई में सुरक्षा, रखरखाव, प्रलेखन और सामुदायिक अपनाव में मजबूत संकेत हैं। A+ (90–100) सर्वोच्च रेटिंग है।",
        "Nerq {category} का मूल्यांकन कैसे करता है?",
        "Nerq सुरक्षा कमज़ोरियों, लाइसेंस अनुपालन, रखरखाव गतिविधि, प्रलेखन गुणवत्ता और सामुदायिक अपनाव सहित कई आयामों पर {category} का विश्लेषण करता है। प्रत्येक आयाम स्वतंत्र रूप से स्कोर किया जाता है और कुल विश्वास स्कोर (0–100) में संयोजित किया जाता है।"),
    "ru": ("Часто задаваемые вопросы",
        "Какие лучшие {category} в {year} году?",
        "На основе оценок доверия Nerq лучшие {category} перечислены выше, оценённые по безопасности, поддержке, документации и принятию сообществом.",
        "Как ранжируются {category}?",
        "Nerq ранжирует инструменты с помощью Trust Score v2, который сочетает анализ безопасности, активность поддержки, качество документации и принятие сообществом.",
        "Безопасны ли эти {category} для использования?",
        "Каждый инструмент имеет индивидуальный отчёт о безопасности. Нажмите на название инструмента, чтобы увидеть подробный анализ доверия.",
        "Что означает Nerq Trust Score A?",
        "Оценка A (80–89) означает, что сущность имеет сильные сигналы в безопасности, поддержке, документации и принятии сообществом. A+ (90–100) — наивысшая оценка.",
        "Как Nerq оценивает {category}?",
        "Nerq анализирует {category} по нескольким измерениям, включая уязвимости безопасности, соответствие лицензиям, активность поддержки, качество документации и принятие сообществом. Каждое измерение оценивается независимо и объединяется в общий балл доверия (0–100)."),
    "pl": ("Najczęściej zadawane pytania",
        "Jakie są najlepsze {category} w {year} roku?",
        "Na podstawie wyników zaufania Nerq, najwyżej ocenione {category} znajdują się powyżej, oceniane pod kątem bezpieczeństwa, konserwacji, dokumentacji i przyjęcia przez społeczność.",
        "Jak są rankowane {category}?",
        "Nerq rankuje narzędzia za pomocą Trust Score v2, łączącego analizę bezpieczeństwa, aktywność konserwacyjną, jakość dokumentacji i przyjęcie przez społeczność.",
        "Czy te {category} są bezpieczne w użyciu?",
        "Każde narzędzie ma indywidualny raport bezpieczeństwa. Kliknij nazwę narzędzia, aby zobaczyć szczegółową analizę zaufania.",
        "Co oznacza Nerq Trust Score A?",
        "Ocena A (80–89) oznacza silne sygnały w bezpieczeństwie, konserwacji, dokumentacji i przyjęciu przez społeczność. A+ (90–100) to najwyższa możliwa ocena.",
        "Jak Nerq ocenia {category}?",
        "Nerq analizuje {category} w wielu wymiarach, w tym luki bezpieczeństwa, zgodność licencji, aktywność konserwacyjną, jakość dokumentacji i przyjęcie przez społeczność. Każdy wymiar jest oceniany niezależnie i łączony w ogólny wynik zaufania (0–100)."),
    "it": ("Domande frequenti",
        "Quali sono i migliori {category} nel {year}?",
        "In base ai punteggi di fiducia Nerq, i {category} meglio classificati sono elencati sopra, valutati su sicurezza, manutenzione, documentazione e adozione comunitaria.",
        "Come vengono classificati i {category}?",
        "Nerq classifica gli strumenti utilizzando il Trust Score v2, che combina analisi di sicurezza, attività di manutenzione, qualità della documentazione e adozione comunitaria.",
        "Questi {category} sono sicuri da usare?",
        "Ogni strumento ha un rapporto di sicurezza individuale. Clicca su qualsiasi nome per vedere l'analisi di fiducia dettagliata.",
        "Cosa significa un Nerq Trust Score di A?",
        "Il voto A (80–89) significa che l'entità ha segnali forti in sicurezza, manutenzione, documentazione e adozione comunitaria. A+ (90–100) è il voto più alto.",
        "Come valuta Nerq i {category}?",
        "Nerq analizza i {category} su più dimensioni tra cui vulnerabilità di sicurezza, conformità delle licenze, attività di manutenzione, qualità della documentazione e adozione comunitaria. Ogni dimensione è valutata indipendentemente e combinata in un punteggio di fiducia complessivo (0–100)."),
    "da": ("Ofte stillede spørgsmål",
        "Hvad er de bedste {category} i {year}?",
        "Baseret på Nerq-tillidsscore er de højest rangerede {category} listet ovenfor, vurderet på sikkerhed, vedligeholdelse, dokumentation og community-adoption.",
        "Hvordan rangeres {category}?",
        "Nerq rangerer værktøjer med Trust Score v2, som kombinerer sikkerhedsanalyse, vedligeholdelsesaktivitet, dokumentationskvalitet og community-adoption.",
        "Er disse {category} sikre at bruge?",
        "Hvert værktøj har en individuel sikkerhedsrapport. Klik på et værktøjsnavn for at se den detaljerede tillidsanalyse.",
        "Hvad betyder en Nerq Trust Score på A?",
        "Karakteren A (80–89) betyder, at entiteten har stærke signaler inden for sikkerhed, vedligeholdelse, dokumentation og community-adoption. A+ (90–100) er den højeste karakter.",
        "Hvordan evaluerer Nerq {category}?",
        "Nerq analyserer {category} på tværs af flere dimensioner herunder sikkerhedssårbarheder, licensoverholdelse, vedligeholdelsesaktivitet, dokumentationskvalitet og community-adoption. Hver dimension scores uafhængigt og kombineres til en samlet tillidsscore (0–100)."),
    "no": ("Ofte stilte spørsmål",
        "Hva er de beste {category} i {year}?",
        "Basert på Nerq-tillitspoeng er de høyest rangerte {category} listet ovenfor, vurdert på sikkerhet, vedlikehold, dokumentasjon og samfunnsadopsjon.",
        "Hvordan rangeres {category}?",
        "Nerq rangerer verktøy med Trust Score v2, som kombinerer sikkerhetsanalyse, vedlikeholdsaktivitet, dokumentasjonskvalitet og samfunnsadopsjon.",
        "Er disse {category} trygge å bruke?",
        "Hvert verktøy har en individuell sikkerhetsrapport. Klikk på et verktøynavn for å se den detaljerte tillitsanalysen.",
        "Hva betyr en Nerq Trust Score på A?",
        "Karakteren A (80–89) betyr at enheten har sterke signaler innen sikkerhet, vedlikehold, dokumentasjon og samfunnsadopsjon. A+ (90–100) er høyeste mulige karakter.",
        "Hvordan evaluerer Nerq {category}?",
        "Nerq analyserer {category} over flere dimensjoner inkludert sikkerhetssårbarheter, lisensoverholdelse, vedlikeholdsaktivitet, dokumentasjonskvalitet og samfunnsadopsjon. Hver dimensjon poengberegnes uavhengig og kombineres til en samlet tillitspoeng (0–100)."),
}

_CONTENT_TRANSLATIONS = {
    "es": {
        "Is NordVPN safe": "¿Es NordVPN seguro",
        "What is NordVPN": "Qué es NordVPN",
        "Does NordVPN log my data": "¿NordVPN registra mis datos",
        "What are the best alternatives to NordVPN": "Cuáles son las mejores alternativas a NordVPN",
        "NordVPN vs alternatives: which is safer": "NordVPN vs alternativas: cuál es más seguro",
        "trust score?": "puntuación de confianza?",
        "Scores update as new data becomes available": "Las puntuaciones se actualizan cuando hay nuevos datos",
        "In the vpn category": "En la categoría VPN",
        "full safety report for detailed privacy analysis": "informe de seguridad completo para un análisis detallado de privacidad",
        "jurisdiction databases, independent audit reports, protocol analysis, and incident history": "bases de datos de jurisdicciones, informes de auditoría independientes, análisis de protocolos e historial de incidentes",
        "has undergone third-party security audits verifying its infrastructure and no-logs claims": "ha sido sometido a auditorías de seguridad de terceros que verifican su infraestructura y sus afirmaciones de no-logs",
        "widely used VPN service": "servicio VPN ampliamente utilizado",
        "multiple public sources including package registries, GitHub, NVD, OSV.dev, and OpenSSF Scorecard": "múltiples fuentes públicas incluyendo registros de paquetes, GitHub, NVD, OSV.dev y OpenSSF Scorecard",
        "Are these safest": "¿Son estos los más seguros",
        "How are safest": "Cómo se clasifican los más seguros",
        "The #1 safest": "El más seguro",
        "What does a Nerq Trust Score": "¿Qué significa un Nerq Trust Score",
        "The #1": "El n.º 1",
        "According to Nerq": "Según Nerq",
        "How are": "¿Cómo se",
        "ranked by Nerq Trust Score": "clasificados por Nerq Trust Score",
        "What are the best": "¿Cuáles son los mejores",
        "Are these rankings updated regularly": "¿Se actualizan estas clasificaciones regularmente",
        "What does a Nerq Trust Score measure": "¿Qué mide un Nerq Trust Score",
        "How does Nerq evaluate": "¿Cómo evalúa Nerq",
        "Are these safe to use": "¿Son seguros de usar",
        "logging policy": "política de registro",
        "Server infrastructure": "Infraestructura de servidores",
        "most VPN providers have not been independently audited": "la mayoría de proveedores VPN no han sido auditados independientemente",
        "This is a strong positive signal": "Esta es una señal positiva fuerte",
        "No known data breaches associated with this service": "No se conocen brechas de datos asociadas con este servicio",
        "According to independent audit reports": "Según informes de auditoría independientes",
        "Logging policy": "Política de registro",
        "Safety Guide": "Guía de seguridad",
        "outside all Eyes surveillance alliances": "fuera de todas las alianzas de vigilancia Eyes",
        "a privacy advantage": "una ventaja de privacidad",
        "has been independently audited to verify its privacy claims": "ha sido auditado de forma independiente para verificar sus afirmaciones de privacidad",
        "Serving": "Sirviendo a",
        "Related Safety Rankings": "Rankings de seguridad relacionados",
        "Complete Your Privacy Setup": "Completa tu configuración de privacidad",
        "Add a password manager to your VPN for full protection": "Añade un gestor de contraseñas a tu VPN para protección completa",
        "Browse Categories": "Explorar categorías",
        "Safest VPNs": "VPNs más seguros",
        "Most Private Apps": "Apps más privadas",
        "Recently Analyzed": "Analizados recientemente",
        "What are the best alternatives to": "¿Cuáles son las mejores alternativas a",
        "which is safer": "cuál es más seguro",
        "logging practices": "prácticas de registro",
        "ownership transparency": "transparencia de propiedad",
        "Popular in": "Popular en",
        "Popularity": "Popularidad",
        "is based in": "tiene su sede en",
        "Not Yet Analyzed": "Aún no analizado",
        # Title / H1
        "Build Your Security Stack": "Construye Tu Paquete de Seguridad",
        "Best Password Managers": "Mejores Gestores de Contraseñas",
        "Best Antivirus": "Mejor Antivirus",
        "Best VPNs": "Mejores VPNs",
        "Combine these tools for comprehensive protection:": "Combina estas herramientas para protección integral:",
        "Compare": "Comparar",
        "Independent Trust & Security Analysis": "Análisis Independiente de Confianza y Seguridad",
        "Independent Trust &amp; Security Analysis": "Análisis Independiente de Confianza y Seguridad",
        # Verdicts
        "Yes, {name} is safe to use.": "Sí, {name} es seguro para usar.",
        "Use {name} with some caution.": "Usa {name} con precaución.",
        "Exercise caution with {name}.": "Ten precaución con {name}.",
        "{name} has significant trust concerns.": "{name} tiene preocupaciones significativas de confianza.",
        "Passes Nerq Verified threshold": "Supera el umbral verificado de Nerq",
        "Below Nerq Verified threshold": "Por debajo del umbral verificado de Nerq",
        "Significant trust gaps detected": "Se detectaron brechas significativas de confianza",
        # Section headings
        "Trust Score Breakdown": "Desglose de Puntuación de Confianza",
        "Safety Score Breakdown": "Desglose de Puntuación de Seguridad",
        "Key Findings": "Hallazgos Clave",
        "Key Safety Findings": "Hallazgos Clave de Seguridad",
        "Detailed Score Analysis": "Análisis Detallado de Puntuación",
        "Frequently Asked Questions": "Preguntas Frecuentes",
        "Safer Alternatives": "Alternativas Más Seguras",
        "Popular Alternatives": "Alternativas Populares",
        "Community Reviews": "Reseñas de la Comunidad",
        "Regulatory Compliance": "Cumplimiento Regulatorio",
        "How we calculated this score": "Cómo calculamos esta puntuación",
        "What We Know About": "Lo Que Sabemos Sobre",
        # Safety Guide
        "Safety Guide:": "Guía de Seguridad:",
        "What is": "¿Qué es",
        "How to Verify Safety": "Cómo Verificar la Seguridad",
        "Key Safety Concerns for": "Principales Preocupaciones de Seguridad para",
        "Trust Assessment": "Evaluación de Confianza",
        "Key Takeaways": "Puntos Clave",
        "Recommended for use — passes trust threshold.": "Recomendado para uso — supera el umbral de confianza.",
        "Review carefully before use — below trust threshold.": "Revisar cuidadosamente antes de usar — por debajo del umbral.",
        "Always verify independently using the": "Siempre verificar independientemente usando la",
        "When evaluating any": "Al evaluar cualquier",
        "watch for:": "observar:",
        # Cross-product
        "Across Platforms": "En Otras Plataformas",
        "across platforms": "en otras plataformas",
        "Same developer/company in other registries:": "Mismo desarrollador/empresa en otros registros:",
        # King sections
        "What data does": "¿Qué datos recopila",
        "collect?": "recopilar?",
        "Is": "¿Es",
        "secure?": "seguro?",
        "Full analysis:": "Análisis completo:",
        "Privacy Report": "Informe de Privacidad",
        "Privacy review": "Revisión de Privacidad",
        "Security Report": "Informe de Seguridad",
        # Dimensions
        "Security": "Seguridad",
        "Privacy": "Privacidad",
        "Reliability": "Fiabilidad",
        "Transparency": "Transparencia",
        "Maintenance": "Mantenimiento",
        "Overall Trust": "Confianza General",
        "Composite trust score": "Puntuación compuesta de confianza",
        "across all available signals": "a través de todas las señales disponibles",
        # Methodology
        "Nerq analyzes over 7.5 million entities across 26 registries": "Nerq analiza más de 7,5 millones de entidades en 26 registros",
        "using the same methodology, enabling direct cross-entity comparison": "usando la misma metodología, permitiendo comparación directa entre entidades",
        "Scores are updated continuously as new data becomes available": "Las puntuaciones se actualizan continuamente a medida que hay nuevos datos",
        "This page was last reviewed on": "Esta página fue revisada por última vez el",
        "Data version": "Versión de datos",
        "Full methodology documentation": "Documentación completa de metodología",
        "Machine-readable data (JSON API)": "Datos legibles por máquinas (API JSON)",
        "Machine-readable data (JSON)": "Datos legibles por máquinas (JSON)",
        # Meta / small text
        "Last analyzed:": "Último análisis:",
        "Last updated": "Última actualización",
        "Updated daily": "Actualizado diariamente",
        "Independent. Data-driven.": "Independiente. Basado en datos.",
        "verified": "verificado",
        "Data sourced from": "Datos obtenidos de",
        "Based on": "Basado en",
        "dimensions": "dimensiones",
        "independent data dimensions": "dimensiones de datos independientes",
        "strong": "fuerte",
        "moderate": "moderado",
        "weak": "débil",
        "actively maintained": "activamente mantenido",
        "moderately maintained": "moderadamente mantenido",
        "low maintenance activity": "baja actividad de mantenimiento",
        "well-documented": "bien documentado",
        "partial documentation": "documentación parcial",
        "limited documentation": "documentación limitada",
        "community adoption": "adopción por la comunidad",
        "stars on": "estrellas en",
        # Cross-links
        "Safety": "Seguridad",
        "Legit?": "¿Legítimo?",
        "Scam?": "¿Estafa?",
        "Review": "Reseña",
        "Alternatives": "Alternativas",
        "Compare": "Comparar",
        "Best in Category": "Mejor en Categoría",
        "Who Owns?": "¿Quién Posee?",
        "What Is?": "¿Qué Es?",
        "Sells Data?": "¿Vende Datos?",
        "Hacked?": "¿Hackeado?",
        "Safe for Kids?": "¿Seguro para Niños?",
        "Pros &amp; Cons": "Pros y Contras",
        # FAQ answers
        "Nerq Verified — meets the 70+ trust threshold.": "Verificado por Nerq — supera el umbral de confianza de 70+.",
        "Below the Nerq Verified threshold of 70.": "Por debajo del umbral verificado de Nerq de 70.",
        "Has not yet reached the Nerq Verified threshold of 70.": "Aún no ha alcanzado el umbral verificado de Nerq de 70.",
        "Strongest signal:": "Señal más fuerte:",
        "Score based on": "Puntuación basada en",
        "security": "seguridad",
        "maintenance": "mantenimiento",
        "popularity": "popularidad",
        "documentation": "documentación",
        "compliance": "cumplimiento",
        # Verdict box
        "Safe": "Seguro",
        "Use Caution": "Precaución",
        "Avoid": "Evitar",
        # Long text patterns (safety guide, methodology, privacy)
        "is a Node.js package": "es un paquete de Node.js",
        "is a Python package": "es un paquete de Python",
        "is a Rust crate": "es un crate de Rust",
        "is a Chrome extension": "es una extensión de Chrome",
        "is a Firefox extension": "es una extensión de Firefox",
        "is a VS Code extension": "es una extensión de VS Code",
        "is a WordPress plugin": "es un plugin de WordPress",
        "is a iOS app": "es una aplicación de iOS",
        "is a Android app": "es una aplicación de Android",
        "is a VPN service": "es un servicio VPN",
        "is a game": "es un juego",
        "is a website": "es un sitio web",
        "is a SaaS platform": "es una plataforma SaaS",
        "is a dietary supplement": "es un suplemento dietético",
        "is a cosmetic ingredient": "es un ingrediente cosmético",
        "is a food": "es un aditivo alimentario",
        "is a travel destination": "es un destino turístico",
        "is a nonprofit organization": "es una organización sin fines de lucro",
        "with a Nerq Trust Score of": "con una Puntuación de Confianza Nerq de",
        "with a Nerq Safety Score of": "con una Puntuación de Seguridad Nerq de",
        "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "Cumple el umbral de confianza de Nerq con señales fuertes en seguridad, mantenimiento y adopción comunitaria",
        "It has moderate trust signals but shows some areas of concern": "Tiene señales de confianza moderadas pero muestra algunas áreas de preocupación",
        "It has below-average trust signals with significant gaps": "Tiene señales de confianza por debajo del promedio con brechas significativas",
        "review the full report below for specific considerations": "revise el informe completo a continuación para consideraciones específicas",
        "This score is based on automated analysis of security, maintenance, community, and quality signals.": "Esta puntuación se basa en análisis automatizado de señales de seguridad, mantenimiento, comunidad y calidad.",
        "You can also check the trust score via API:": "También puede verificar la puntuación de confianza vía API:",
        "dependency vulnerabilities, malicious packages, typosquatting": "vulnerabilidades de dependencias, paquetes maliciosos, typosquatting",
        "Run your package manager's audit command": "Ejecute el comando de auditoría de su gestor de paquetes",
        "to check for known vulnerabilities in your dependency tree": "para verificar vulnerabilidades conocidas en su árbol de dependencias",
        "As a development package": "Como paquete de desarrollo",
        "does not directly collect end-user personal data": "no recopila directamente datos personales del usuario final",
        "However, applications built with it may collect data depending on implementation": "Sin embargo, las aplicaciones construidas con él pueden recopilar datos según la implementación",
        "Review the package's dependencies for potential supply chain risks": "Revise las dependencias del paquete para posibles riesgos de cadena de suministro",
        "License information not available": "Información de licencia no disponible",
        "Open-source packages allow independent security review of the source code": "Los paquetes de código abierto permiten revisión de seguridad independiente del código fuente",
        "to check for vulnerabilities": "para verificar vulnerabilidades",
        "Review the": "Revisar el/la",
        "GitHub repository for recent commits": "repositorio de GitHub para commits recientes",
        "This meets the recommended security threshold for production use": "Esto cumple el umbral de seguridad recomendado para uso en producción",
        "Nerq monitors this entity against NVD, OSV.dev, and registry-specific vulnerability databases": "Nerq monitorea esta entidad contra NVD, OSV.dev y bases de datos de vulnerabilidades específicas del registro",
        "for ongoing security assessment": "para evaluación de seguridad continua",
        "Yes, it is safe to use.": "Sí, es seguro para usar.",
        "Use with some caution.": "Usar con precaución.",
        "Exercise caution.": "Tener precaución.",
        "Significant trust concerns.": "Preocupaciones significativas de confianza.",
        "maintained by": "mantenido por",
        "is computed from": "se calcula a partir de",
        "The score reflects": "La puntuación refleja",
        "independent dimensions": "dimensiones independientes",
        "Each dimension is weighted equally to produce the composite trust score": "Cada dimensión se pondera equitativamente para producir la puntuación de confianza compuesta",
        "No reviews yet.": "Sin reseñas aún.",
        "Be the first to review": "Sea el primero en reseñar",
        "Write a review": "Escribir una reseña",
        "Higher-rated": "Mejor calificadas",
        "you may want to consider:": "que podría considerar:",
        "under assessment": "en evaluación",
        # Health disclaimers
        "Important Notice:": "Aviso Importante:",
        "educational and informational purposes only": "fines educativos e informativos únicamente",
        "does not constitute medical advice": "no constituye asesoramiento médico",
        "Consult a qualified healthcare professional": "Consulte a un profesional de salud calificado",
        "Full health disclaimer": "Descargo de responsabilidad de salud completo",
        "Full disclaimer": "Descargo de responsabilidad completo",
    },
    "de": {
        "Best Antivirus": "Bestes Antivirus",
        "What is NordVPN": "Was ist NordVPN",
        "incident history": "Vorfallshistorie",
        "protocol analysis": "Protokollanalyse",
        "independent audit reports": "unabhängige Prüfberichte",
        "jurisdiction databases": "Jurisdiktionsdatenbanken",
        "jurisdiction databases, independent audit reports, protocol analysis, and incident history": "Jurisdiktionsdatenbanken, unabhängige Prüfberichte, Protokollanalyse und Vorfallshistorie",
        "What are the best alternatives to NordVPN": "Was sind die besten Alternativen zu NordVPN",
        "NordVPN vs alternatives: which is safer": "NordVPN vs. Alternativen: was ist sicherer",
        "Does NordVPN log my data": "Speichert NordVPN meine Daten",
        "trust score?": "Vertrauenswert?",
        "Is NordVPN safe": "Ist NordVPN sicher",
        "Build Your Sicherheit Stack": "Bauen Sie Ihr Sicherheitspaket",
        "Run npm audit": "Führen Sie npm audit aus",
        "full safety report for detailed privacy analysis": "vollständigen Sicherheitsbericht für detaillierte Datenschutzanalyse",
        "In the npm category": "In der npm-Kategorie",
        "In the vpn category": "In der VPN-Kategorie",
        "Scores update as new data becomes available": "Bewertungen werden aktualisiert, wenn neue Daten verfügbar werden",
        "multiple public sources including package registries, GitHub, NVD, OSV.dev, and OpenSSF Scorecard": "mehreren öffentlichen Quellen einschließlich Paketregistern, GitHub, NVD, OSV.dev und OpenSSF Scorecard",
        "Best Password Managers": "Beste Passwort-Manager",
        "The #1 safest": "Die sicherste",
        "How are safest": "Wie werden die sichersten",
        "Are these safest": "Sind diese die sichersten",
        "What does a Nerq Trust Score": "Was bedeutet ein Nerq Trust Score",
        "The #1": "Die Nr. 1",
        "According to Nerq": "Laut Nerq",
        "How are": "Wie werden",
        "ranked by Nerq Trust Score": "nach Nerq Trust Score bewertet",
        "What are the best": "Was sind die besten",
        "Are these rankings updated regularly": "Werden diese Rankings regelmäßig aktualisiert",
        "What does a Nerq Trust Score measure": "Was misst ein Nerq Trust Score",
        "How does Nerq evaluate": "Wie bewertet Nerq",
        "Are these safe to use": "Sind diese sicher in der Verwendung",
        "{name} Privacy Report": "{name} Datenschutzbericht",
        "has undergone third-party security audits verifying its infrastructure and no-logs claims": "hat Sicherheitsaudits durch Dritte unterzogen, die seine Infrastruktur und No-Logs-Ansprüche verifizieren",
        "This is a strong positive signal — most VPN providers have not been independently audited": "Dies ist ein stark positives Signal — die meisten VPN-Anbieter wurden nicht unabhängig geprüft",
        "has not published results from an independent security audit": "hat keine Ergebnisse einer unabhängigen Sicherheitsprüfung veröffentlicht",
        "While this does not indicate a security issue, audited VPNs provide higher assurance": "Dies deutet zwar nicht auf ein Sicherheitsproblem hin, geprüfte VPNs bieten jedoch höhere Sicherheit",
        "Security score": "Sicherheitsbewertung",
        "Primary encryption protocol": "Primäres Verschlüsselungsprotokoll",
        "which is considered industry-standard for VPN connections": "das als Industriestandard für VPN-Verbindungen gilt",
        "Independent security audit verified": "Unabhängiges Sicherheitsaudit verifiziert",
        "has no known data breaches and has been independently audited": "hat keine bekannten Datenschutzverletzungen und wurde unabhängig geprüft",
        "uses AES-256-CBC (industry standard), Argon2id (brute-force resistant key derivation)": "verwendet AES-256-CBC (Industriestandard), Argon2id (Brute-Force-resistente Schlüsselableitung)",
        "uses a zero-knowledge architecture": "verwendet eine Zero-Knowledge-Architektur",
        "your master password and vault data are encrypted locally and never sent to the server in plaintext": "Ihr Master-Passwort und Tresordaten werden lokal verschlüsselt und niemals im Klartext an den Server gesendet",
        "is open source with": "ist Open Source mit",
        "GitHub stars": "GitHub-Sternen",
        "Based in": "Sitz in",
        "Independently audited": "Unabhängig geprüft",
        "No published independent audit": "Kein veröffentlichtes unabhängiges Audit",
        "logging policy": "Protokollierungsrichtlinie",
        "Combine these tools for comprehensive protection:": "Kombinieren Sie diese Tools für umfassenden Schutz:",
        "Safety Guide": "Sicherheitsleitfaden",
        "You can also check the trust score via API": "Sie können den Vertrauenswert auch über die API überprüfen",
        "meets Nerq trust threshold": "erfüllt die Nerq-Vertrauensschwelle",
        "passes trust threshold": "erfüllt die Vertrauensschwelle",
        "Recommended for use": "Empfohlen zur Nutzung",
        "This score is based on automated analysis of security, maintenance, community, and quality signals": "Diese Bewertung basiert auf automatisierter Analyse von Sicherheits-, Wartungs-, Community- und Qualitätssignalen",
        "widely used": "weit verbreitet",
        "No known data breaches associated with this service": "Keine bekannten Datenschutzverletzungen im Zusammenhang mit diesem Dienst",
        "This is a strong positive signal": "Dies ist ein stark positives Signal",
        "most VPN providers have not been independently audited": "die meisten VPN-Anbieter wurden nicht unabhängig geprüft",
        "Full analysis": "Vollständige Analyse",
        "Same developer": "Gleicher Entwickler",
        "It is ": "Es ist ",
        "It is recommended": "Empfohlen",
        "below the recommended threshold": "unter der empfohlenen Schwelle",
        "Dimension": "Dimension",
        "Score": "Bewertung",
        "Data from": "Daten von",
        "is based in": "hat seinen Sitz in",
        "outside all Eyes surveillance alliances": "außerhalb aller Eyes-Überwachungsallianzen",
        "a privacy advantage": "ein Datenschutzvorteil",
        "has been independently audited to verify its privacy claims": "wurde von unabhängiger Stelle geprüft, um seine Datenschutzansprüche zu verifizieren",
        "Serving": "Bedient",
        "users": "Nutzer",
        "Related Safety Rankings": "Verwandte Sicherheitsrankings",
        "Complete Your Privacy Setup": "Vervollständigen Sie Ihren Datenschutz",
        "Add a password manager to your VPN for full protection": "Fügen Sie einen Passwort-Manager zu Ihrem VPN hinzu",
        "Add Antivirus Protection": "Antivirenschutz hinzufügen",
        "Complete your security with antivirus alongside your VPN": "Vervollständigen Sie Ihre Sicherheit mit Antivirus neben Ihrem VPN",
        "servers in": "Server in",
        "countries": "Länder",
        "logging practices": "Protokollierungspraktiken",
        "audit history": "Prüfungshistorie",
        "ownership transparency": "Eigentümertransparenz",
        "This is significant because VPN providers in": "Dies ist bedeutsam, da VPN-Anbieter in",
        "are not subject to mandatory data retention laws or intelligence-sharing agreements": "nicht den Vorschriften zur Datenspeicherung oder Geheimdienstabkommen unterliegen",
        "Server infrastructure": "Server-Infrastruktur",
        "servers across": "Server in",
        "Logging policy": "Protokollierungsrichtlinie",
        "independently audited no-logs policy": "unabhängig geprüfte No-Logs-Richtlinie",
        "According to independent audit reports": "Laut unabhängiger Prüfberichte",
        "does not store connection logs, browsing activity, or DNS queries": "speichert keine Verbindungsprotokolle, Browsing-Aktivitäten oder DNS-Abfragen",
        "score:": "Bewertung:",
        "Nerq analyzes over": "Nerq analysiert über",
        "What are the best alternatives to": "Was sind die besten Alternativen zu",
        "Does": "Speichert",
        "log my data": "meine Daten",
        "vs alternatives: which is safer": "vs. Alternativen: was ist sicherer",
        "Popular in": "Beliebt in",
        "Browse Categories": "Kategorien durchsuchen",
        "Safest VPNs": "Sicherste VPNs",
        "Most Private Apps": "Privateste Apps",
        "Recently Analyzed": "Kürzlich analysiert",
        "strong)": "stark)",
        "widely used VPN service": "weit verbreiteter VPN-Dienst",
        "Popularity": "Beliebtheit",
        "more VPN services are being analyzed": "weitere VPN-Dienste werden analysiert",
        "check back soon": "schauen Sie bald wieder vorbei",
        "Nerq assesses": "Nerq bewertet",
        "data practices as part of its trust score": "Datenpraktiken als Teil des Vertrauenswerts",
        "Review full safety report for detailed privacy analysis": "Vollständigen Sicherheitsbericht für detaillierte Datenschutzanalyse lesen",
        "More VPN services are being analyzed for comparison": "Weitere VPN-Dienste werden zum Vergleich analysiert",
        "Not Yet Analyzed": "Noch nicht analysiert",
        "Privacy Assessment": "Datenschutzbewertung",
        "Breach History": "Sicherheitsvorfälle",
        # Title / H1
        "Independent Trust & Security Analysis": "Unabhängige Vertrauens- und Sicherheitsanalyse",
        "Independent Trust &amp; Security Analysis": "Unabhängige Vertrauens- und Sicherheitsanalyse",
        # Verdicts
        "Yes, {name} is safe to use.": "Ja, {name} ist sicher in der Verwendung.",
        "Use {name} with some caution.": "Verwenden Sie {name} mit Vorsicht.",
        "Exercise caution with {name}.": "Seien Sie vorsichtig mit {name}.",
        "{name} has significant trust concerns.": "{name} weist erhebliche Vertrauensbedenken auf.",
        "Passes Nerq Verified threshold": "Überschreitet die Nerq-Verifizierungsschwelle",
        "Below Nerq Verified threshold": "Unterhalb der Nerq-Verifizierungsschwelle",
        "Significant trust gaps detected": "Erhebliche Vertrauenslücken erkannt",
        # Section headings
        "Trust Score Breakdown": "Aufschlüsselung der Vertrauensbewertung",
        "Safety Score Breakdown": "Aufschlüsselung der Sicherheitsbewertung",
        "Key Findings": "Wichtige Erkenntnisse",
        "Key Safety Findings": "Wichtige Sicherheitserkenntnisse",
        "Detailed Score Analysis": "Detaillierte Bewertungsanalyse",
        "Frequently Asked Questions": "Häufig gestellte Fragen",
        "Safer Alternatives": "Sicherere Alternativen",
        "Popular Alternatives": "Beliebte Alternativen",
        "Community Reviews": "Community-Bewertungen",
        "Regulatory Compliance": "Regulatorische Konformität",
        "How we calculated this score": "Wie wir diese Bewertung berechnet haben",
        "What We Know About": "Was wir wissen über",
        # Safety Guide
        "Safety Guide:": "Sicherheitsleitfaden:",
        "What is": "Was ist",
        "How to Verify Safety": "Sicherheit überprüfen",
        "Key Safety Concerns for": "Wichtige Sicherheitsbedenken für",
        "Trust Assessment": "Vertrauensbewertung",
        "Key Takeaways": "Wichtigste Punkte",
        "Recommended for use — passes trust threshold.": "Zur Nutzung empfohlen — überschreitet die Vertrauensschwelle.",
        "Review carefully before use — below trust threshold.": "Vor der Nutzung sorgfältig prüfen — unterhalb der Vertrauensschwelle.",
        "Always verify independently using the": "Überprüfen Sie immer unabhängig mit der",
        "When evaluating any": "Bei der Bewertung jeder",
        "watch for:": "achten Sie auf:",
        # Cross-product
        "Across Platforms": "Plattformübergreifend",
        "across platforms": "plattformübergreifend",
        "Same developer/company in other registries:": "Gleicher Entwickler/gleiches Unternehmen in anderen Registern:",
        # King sections
        "What data does": "Welche Daten erhebt",
        "collect?": "erheben?",
        "Is": "Ist",
        "secure?": "sicher?",
        "Full analysis:": "Vollständige Analyse:",
        "Privacy Report": "Datenschutzbericht",
        "Privacy review": "Datenschutzprüfung",
        "Security Report": "Sicherheitsbericht",
        # Dimensions
        "Security": "Sicherheit",
        "Privacy": "Datenschutz",
        "Reliability": "Zuverlässigkeit",
        "Transparency": "Transparenz",
        "Maintenance": "Wartung",
        "Overall Trust": "Gesamtvertrauen",
        "Composite trust score": "Zusammengesetzte Vertrauensbewertung",
        "across all available signals": "über alle verfügbaren Signale hinweg",
        # Methodology
        "Nerq analyzes over 7.5 million entities across 26 registries": "Nerq analysiert über 7,5 Millionen Entitäten in 26 Registern",
        "using the same methodology, enabling direct cross-entity comparison": "mit derselben Methodik, die einen direkten Vergleich zwischen Entitäten ermöglicht",
        "Scores are updated continuously as new data becomes available": "Bewertungen werden kontinuierlich aktualisiert, sobald neue Daten verfügbar sind",
        "This page was last reviewed on": "Diese Seite wurde zuletzt überprüft am",
        "Data version": "Datenversion",
        "Full methodology documentation": "Vollständige Methodendokumentation",
        "Machine-readable data (JSON API)": "Maschinenlesbare Daten (JSON-API)",
        "Machine-readable data (JSON)": "Maschinenlesbare Daten (JSON)",
        # Meta / small text
        "Last analyzed:": "Zuletzt analysiert:",
        "Last updated": "Zuletzt aktualisiert",
        "Updated daily": "Täglich aktualisiert",
        "Independent. Data-driven.": "Unabhängig. Datengestützt.",
        "verified": "verifiziert",
        "Data sourced from": "Daten stammen von",
        "Based on": "Basierend auf",
        "dimensions": "Dimensionen",
        "independent data dimensions": "unabhängige Datendimensionen",
        "strong": "stark",
        "moderate": "moderat",
        "weak": "schwach",
        "actively maintained": "aktiv gewartet",
        "moderately maintained": "mäßig gewartet",
        "low maintenance activity": "geringe Wartungsaktivität",
        "well-documented": "gut dokumentiert",
        "partial documentation": "teilweise dokumentiert",
        "limited documentation": "eingeschränkte Dokumentation",
        "community adoption": "Community-Akzeptanz",
        "stars on": "Sterne auf",
        # Cross-links
        "Safety": "Sicherheit",
        "Legit?": "Seriös?",
        "Scam?": "Betrug?",
        "Review": "Bewertung",
        "Alternatives": "Alternativen",
        "Compare": "Vergleichen",
        "Best in Category": "Beste in der Kategorie",
        "Who Owns?": "Wem gehört?",
        "What Is?": "Was ist?",
        "Sells Data?": "Verkauft Daten?",
        "Hacked?": "Gehackt?",
        "Safe for Kids?": "Sicher für Kinder?",
        "Pros &amp; Cons": "Vor- und Nachteile",
        # FAQ answers
        "Nerq Verified — meets the 70+ trust threshold.": "Nerq-verifiziert — überschreitet die Vertrauensschwelle von 70+.",
        "Below the Nerq Verified threshold of 70.": "Unterhalb der Nerq-Verifizierungsschwelle von 70.",
        "Has not yet reached the Nerq Verified threshold of 70.": "Hat die Nerq-Verifizierungsschwelle von 70 noch nicht erreicht.",
        "Strongest signal:": "Stärkstes Signal:",
        "Score based on": "Bewertung basierend auf",
        "security": "Sicherheit",
        "maintenance": "Wartung",
        "popularity": "Beliebtheit",
        "documentation": "Dokumentation",
        "compliance": "Konformität",
        # Verdict box
        "Safe": "Sicher",
        "Use Caution": "Vorsicht",
        "Avoid": "Vermeiden",
        # Long text patterns (safety guide, methodology, privacy)
        "is a Node.js package": "ist ein Node.js-Paket",
        "is a Python package": "ist ein Python-Paket",
        "is a Rust crate": "ist ein Rust-Crate",
        "is a Chrome extension": "ist eine Chrome-Erweiterung",
        "is a Firefox extension": "ist eine Firefox-Erweiterung",
        "is a VS Code extension": "ist eine VS-Code-Erweiterung",
        "is a WordPress plugin": "ist ein WordPress-Plugin",
        "is a iOS app": "ist eine iOS-App",
        "is a Android app": "ist eine Android-App",
        "is a VPN service": "ist ein VPN-Dienst",
        "is a game": "ist ein Spiel",
        "is a website": "ist eine Website",
        "is a SaaS platform": "ist eine SaaS-Plattform",
        "is a dietary supplement": "ist ein Nahrungsergänzungsmittel",
        "is a cosmetic ingredient": "ist ein kosmetischer Inhaltsstoff",
        "is a food": "ist ein Lebensmittelzusatzstoff",
        "is a travel destination": "ist ein Reiseziel",
        "is a nonprofit organization": "ist eine gemeinnützige Organisation",
        "with a Nerq Trust Score of": "mit einer Nerq-Vertrauensbewertung von",
        "with a Nerq Safety Score of": "mit einer Nerq-Sicherheitsbewertung von",
        "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "Es erfüllt die Nerq-Vertrauensschwelle mit starken Signalen in Sicherheit, Wartung und Community-Akzeptanz",
        "It has moderate trust signals but shows some areas of concern": "Es hat moderate Vertrauenssignale, zeigt aber einige Problembereiche",
        "It has below-average trust signals with significant gaps": "Es hat unterdurchschnittliche Vertrauenssignale mit erheblichen Lücken",
        "review the full report below for specific considerations": "lesen Sie den vollständigen Bericht unten für spezifische Hinweise",
        "This score is based on automated analysis of security, maintenance, community, and quality signals.": "Diese Bewertung basiert auf automatisierter Analyse von Sicherheits-, Wartungs-, Community- und Qualitätssignalen.",
        "You can also check the trust score via API:": "Sie können die Vertrauensbewertung auch über die API prüfen:",
        "dependency vulnerabilities, malicious packages, typosquatting": "Abhängigkeitsschwachstellen, schädliche Pakete, Typosquatting",
        "Run your package manager's audit command": "Führen Sie den Audit-Befehl Ihres Paketmanagers aus",
        "to check for known vulnerabilities in your dependency tree": "um bekannte Schwachstellen in Ihrem Abhängigkeitsbaum zu prüfen",
        "As a development package": "Als Entwicklungspaket",
        "does not directly collect end-user personal data": "erhebt nicht direkt personenbezogene Daten von Endnutzern",
        "However, applications built with it may collect data depending on implementation": "Allerdings können damit erstellte Anwendungen je nach Implementierung Daten erheben",
        "Review the package's dependencies for potential supply chain risks": "Überprüfen Sie die Abhängigkeiten des Pakets auf potenzielle Lieferkettenrisiken",
        "License information not available": "Lizenzinformationen nicht verfügbar",
        "Open-source packages allow independent security review of the source code": "Open-Source-Pakete ermöglichen eine unabhängige Sicherheitsüberprüfung des Quellcodes",
        "to check for vulnerabilities": "um auf Schwachstellen zu prüfen",
        "Review the": "Überprüfen Sie das/die",
        "GitHub repository for recent commits": "GitHub-Repository auf aktuelle Commits",
        "This meets the recommended security threshold for production use": "Dies erfüllt die empfohlene Sicherheitsschwelle für den Produktionseinsatz",
        "Nerq monitors this entity against NVD, OSV.dev, and registry-specific vulnerability databases": "Nerq überwacht diese Entität anhand von NVD, OSV.dev und registerspezifischen Schwachstellendatenbanken",
        "for ongoing security assessment": "für die laufende Sicherheitsbewertung",
        "Yes, it is safe to use.": "Ja, es ist sicher in der Verwendung.",
        "Use with some caution.": "Mit Vorsicht verwenden.",
        "Exercise caution.": "Vorsicht walten lassen.",
        "Significant trust concerns.": "Erhebliche Vertrauensbedenken.",
        "maintained by": "gewartet von",
        "is computed from": "wird berechnet aus",
        "The score reflects": "Die Bewertung spiegelt wider",
        "independent dimensions": "unabhängige Dimensionen",
        "Each dimension is weighted equally to produce the composite trust score": "Jede Dimension wird gleich gewichtet, um die zusammengesetzte Vertrauensbewertung zu erstellen",
        "No reviews yet.": "Noch keine Bewertungen.",
        "Be the first to review": "Seien Sie der Erste, der bewertet",
        "Write a review": "Bewertung schreiben",
        "Higher-rated": "Höher bewertete",
        "you may want to consider:": "die Sie in Betracht ziehen könnten:",
        "under assessment": "in Bewertung",
        # Health disclaimers
        "Important Notice:": "Wichtiger Hinweis:",
        "educational and informational purposes only": "nur zu Bildungs- und Informationszwecken",
        "does not constitute medical advice": "stellt keine medizinische Beratung dar",
        "Consult a qualified healthcare professional": "Konsultieren Sie einen qualifizierten Gesundheitsfachmann",
        "Full health disclaimer": "Vollständiger Gesundheitshaftungsausschluss",
        "Full disclaimer": "Vollständiger Haftungsausschluss",
    },
    "fr": {
        "Is NordVPN safe": "NordVPN est-il sûr",
        "What is NordVPN": "Qu'est-ce que NordVPN",
        "Does NordVPN log my data": "NordVPN enregistre-t-il mes données",
        "What are the best alternatives to NordVPN": "Quelles sont les meilleures alternatives à NordVPN",
        "NordVPN vs alternatives: which is safer": "NordVPN vs alternatives: lequel est plus sûr",
        "trust score?": "score de confiance?",
        "Scores update as new data becomes available": "Les scores sont mis à jour lorsque de nouvelles données sont disponibles",
        "In the vpn category": "Dans la catégorie VPN",
        "full safety report for detailed privacy analysis": "rapport de sécurité complet pour une analyse détaill��e de la confidentialité",
        "jurisdiction databases, independent audit reports, protocol analysis, and incident history": "bases de données juridictionnelles, rapports d'audit indépendants, analyse de protocoles et historique d'incidents",
        "has undergone third-party security audits verifying its infrastructure and no-logs claims": "a subi des audits de sécurité tiers vérifiant son infrastructure et ses revendications de no-logs",
        "widely used VPN service": "service VPN largement utilisé",
        "multiple public sources including package registries, GitHub, NVD, OSV.dev, and OpenSSF Scorecard": "plusieurs sources publiques dont les registres de paquets, GitHub, NVD, OSV.dev et OpenSSF Scorecard",
        "Are these safest": "Sont-ils les plus sûrs",
        "How are safest": "Comment les plus sûrs sont",
        "The #1 safest": "Le plus sûr",
        "What does a Nerq Trust Score": "Que signifie un Nerq Trust Score",
        "The #1": "Le n°1",
        "According to Nerq": "Selon Nerq",
        "How are": "Comment sont",
        "ranked by Nerq Trust Score": "classés par Nerq Trust Score",
        "What are the best": "Quels sont les meilleurs",
        "Are these rankings updated regularly": "Ces classements sont-ils mis à jour régulièrement",
        "What does a Nerq Trust Score measure": "Que mesure un Nerq Trust Score",
        "How does Nerq evaluate": "Comment Nerq évalue",
        "Are these safe to use": "Sont-ils sûrs à utiliser",
        "logging policy": "politique de journalisation",
        "Server infrastructure": "Infrastructure serveur",
        "This is a strong positive signal": "C'est un signal positif fort",
        "No known data breaches associated with this service": "Aucune violation de données connue associée à ce service",
        "According to independent audit reports": "Selon les rapports d'audit indépendants",
        "Logging policy": "Politique de journalisation",
        "Safety Guide": "Guide de sécurité",
        "outside all Eyes surveillance alliances": "en dehors de toutes les alliances de surveillance Eyes",
        "a privacy advantage": "un avantage pour la vie privée",
        "has been independently audited to verify its privacy claims": "a été audité de manière indépendante pour vérifier ses revendications de confidentialité",
        "Serving": "Au service de",
        "Related Safety Rankings": "Classements de sécurité associés",
        "Complete Your Privacy Setup": "Complétez votre configuration de confidentialité",
        "Add a password manager to your VPN for full protection": "Ajoutez un gestionnaire de mots de passe à votre VPN pour une protection complète",
        "Browse Categories": "Parcourir les catégories",
        "Safest VPNs": "VPN les plus sûrs",
        "Most Private Apps": "Apps les plus privées",
        "Recently Analyzed": "Analysés récemment",
        "What are the best alternatives to": "Quelles sont les meilleures alternatives à",
        "which is safer": "lequel est plus sûr",
        "logging practices": "pratiques de journalisation",
        "ownership transparency": "transparence de propriété",
        "Popular in": "Populaire dans",
        "Popularity": "Popularité",
        "is based in": "est basé en",
        "Not Yet Analyzed": "Pas encore analysé",
        # Title / H1
        "Build Your Security Stack": "Construisez Votre Suite de Sécurité",
        "Best Password Managers": "Meilleurs Gestionnaires de Mots de Passe",
        "Best Antivirus": "Meilleur Antivirus",
        "Best VPNs": "Meilleurs VPN",
        "Combine these tools for comprehensive protection:": "Combinez ces outils pour une protection complète:",
        "Compare": "Comparer",
        "Independent Trust & Security Analysis": "Analyse Indépendante de Confiance et de Sécurité",
        "Independent Trust &amp; Security Analysis": "Analyse Indépendante de Confiance et de Sécurité",
        # Verdicts
        "Yes, {name} is safe to use.": "Oui, {name} est sûr à utiliser.",
        "Use {name} with some caution.": "Utilisez {name} avec prudence.",
        "Exercise caution with {name}.": "Faites preuve de prudence avec {name}.",
        "{name} has significant trust concerns.": "{name} présente des problèmes de confiance significatifs.",
        "Passes Nerq Verified threshold": "Dépasse le seuil de vérification Nerq",
        "Below Nerq Verified threshold": "En dessous du seuil de vérification Nerq",
        "Significant trust gaps detected": "Lacunes de confiance significatives détectées",
        # Section headings
        "Trust Score Breakdown": "Détail du Score de Confiance",
        "Safety Score Breakdown": "Détail du Score de Sécurité",
        "Key Findings": "Résultats Clés",
        "Key Safety Findings": "Résultats Clés de Sécurité",
        "Detailed Score Analysis": "Analyse Détaillée du Score",
        "Frequently Asked Questions": "Questions Fréquemment Posées",
        "Safer Alternatives": "Alternatives Plus Sûres",
        "Popular Alternatives": "Alternatives Populaires",
        "Community Reviews": "Avis de la Communauté",
        "Regulatory Compliance": "Conformité Réglementaire",
        "How we calculated this score": "Comment nous avons calculé ce score",
        "What We Know About": "Ce Que Nous Savons Sur",
        # Safety Guide
        "Safety Guide:": "Guide de Sécurité :",
        "What is": "Qu'est-ce que",
        "How to Verify Safety": "Comment Vérifier la Sécurité",
        "Key Safety Concerns for": "Principales Préoccupations de Sécurité pour",
        "Trust Assessment": "Évaluation de Confiance",
        "Key Takeaways": "Points Essentiels",
        "Recommended for use — passes trust threshold.": "Recommandé pour utilisation — dépasse le seuil de confiance.",
        "Review carefully before use — below trust threshold.": "Examiner attentivement avant utilisation — en dessous du seuil de confiance.",
        "Always verify independently using the": "Toujours vérifier indépendamment en utilisant la",
        "When evaluating any": "Lors de l'évaluation de tout",
        "watch for:": "surveiller :",
        # Cross-product
        "Across Platforms": "Sur Toutes les Plateformes",
        "across platforms": "sur toutes les plateformes",
        "Same developer/company in other registries:": "Même développeur/entreprise dans d'autres registres :",
        # King sections
        "What data does": "Quelles données collecte",
        "collect?": "collecter ?",
        "Is": "Est-ce que",
        "secure?": "est sécurisé ?",
        "Full analysis:": "Analyse complète :",
        "Privacy Report": "Rapport de Confidentialité",
        "Privacy review": "Examen de Confidentialité",
        "Security Report": "Rapport de Sécurité",
        # Dimensions
        "Security": "Sécurité",
        "Privacy": "Confidentialité",
        "Reliability": "Fiabilité",
        "Transparency": "Transparence",
        "Maintenance": "Maintenance",
        "Overall Trust": "Confiance Globale",
        "Composite trust score": "Score de confiance composite",
        "across all available signals": "à travers tous les signaux disponibles",
        # Methodology
        "Nerq analyzes over 7.5 million entities across 26 registries": "Nerq analyse plus de 7,5 millions d'entités dans 26 registres",
        "using the same methodology, enabling direct cross-entity comparison": "en utilisant la même méthodologie, permettant une comparaison directe entre entités",
        "Scores are updated continuously as new data becomes available": "Les scores sont mis à jour en continu dès que de nouvelles données sont disponibles",
        "This page was last reviewed on": "Cette page a été révisée pour la dernière fois le",
        "Data version": "Version des données",
        "Full methodology documentation": "Documentation complète de la méthodologie",
        "Machine-readable data (JSON API)": "Données lisibles par machine (API JSON)",
        "Machine-readable data (JSON)": "Données lisibles par machine (JSON)",
        # Meta / small text
        "Last analyzed:": "Dernière analyse :",
        "Last updated": "Dernière mise à jour",
        "Updated daily": "Mis à jour quotidiennement",
        "Independent. Data-driven.": "Indépendant. Basé sur les données.",
        "verified": "vérifié",
        "Data sourced from": "Données provenant de",
        "Based on": "Basé sur",
        "dimensions": "dimensions",
        "independent data dimensions": "dimensions de données indépendantes",
        "strong": "fort",
        "moderate": "modéré",
        "weak": "faible",
        "actively maintained": "activement maintenu",
        "moderately maintained": "modérément maintenu",
        "low maintenance activity": "faible activité de maintenance",
        "well-documented": "bien documenté",
        "partial documentation": "documentation partielle",
        "limited documentation": "documentation limitée",
        "community adoption": "adoption par la communauté",
        "stars on": "étoiles sur",
        # Cross-links
        "Safety": "Sécurité",
        "Legit?": "Légitime ?",
        "Scam?": "Arnaque ?",
        "Review": "Avis",
        "Alternatives": "Alternatives",
        "Compare": "Comparer",
        "Best in Category": "Meilleur de la Catégorie",
        "Who Owns?": "Qui Possède ?",
        "What Is?": "Qu'est-ce que ?",
        "Sells Data?": "Vend des Données ?",
        "Hacked?": "Piraté ?",
        "Safe for Kids?": "Sûr pour les Enfants ?",
        "Pros &amp; Cons": "Avantages et Inconvénients",
        # FAQ answers
        "Nerq Verified — meets the 70+ trust threshold.": "Vérifié par Nerq — dépasse le seuil de confiance de 70+.",
        "Below the Nerq Verified threshold of 70.": "En dessous du seuil de vérification Nerq de 70.",
        "Has not yet reached the Nerq Verified threshold of 70.": "N'a pas encore atteint le seuil de vérification Nerq de 70.",
        "Strongest signal:": "Signal le plus fort :",
        "Score based on": "Score basé sur",
        "security": "sécurité",
        "maintenance": "maintenance",
        "popularity": "popularité",
        "documentation": "documentation",
        "compliance": "conformité",
        # Verdict box
        "Safe": "Sûr",
        "Use Caution": "Prudence",
        "Avoid": "Éviter",
        # Long text patterns (safety guide, methodology, privacy)
        "is a Node.js package": "est un paquet Node.js",
        "is a Python package": "est un paquet Python",
        "is a Rust crate": "est un crate Rust",
        "is a Chrome extension": "est une extension Chrome",
        "is a Firefox extension": "est une extension Firefox",
        "is a VS Code extension": "est une extension VS Code",
        "is a WordPress plugin": "est un plugin WordPress",
        "is a iOS app": "est une application iOS",
        "is a Android app": "est une application Android",
        "is a VPN service": "est un service VPN",
        "is a game": "est un jeu",
        "is a website": "est un site web",
        "is a SaaS platform": "est une plateforme SaaS",
        "is a dietary supplement": "est un complément alimentaire",
        "is a cosmetic ingredient": "est un ingrédient cosmétique",
        "is a food": "est un additif alimentaire",
        "is a travel destination": "est une destination de voyage",
        "is a nonprofit organization": "est une organisation à but non lucratif",
        "with a Nerq Trust Score of": "avec un Score de Confiance Nerq de",
        "with a Nerq Safety Score of": "avec un Score de Sécurité Nerq de",
        "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "Il dépasse le seuil de confiance Nerq avec des signaux forts en sécurité, maintenance et adoption communautaire",
        "It has moderate trust signals but shows some areas of concern": "Il présente des signaux de confiance modérés mais montre certaines zones de préoccupation",
        "It has below-average trust signals with significant gaps": "Il présente des signaux de confiance inférieurs à la moyenne avec des lacunes significatives",
        "review the full report below for specific considerations": "consultez le rapport complet ci-dessous pour des considérations spécifiques",
        "This score is based on automated analysis of security, maintenance, community, and quality signals.": "Ce score est basé sur une analyse automatisée des signaux de sécurité, de maintenance, de communauté et de qualité.",
        "You can also check the trust score via API:": "Vous pouvez également vérifier le score de confiance via l'API :",
        "dependency vulnerabilities, malicious packages, typosquatting": "vulnérabilités de dépendances, paquets malveillants, typosquatting",
        "Run your package manager's audit command": "Exécutez la commande d'audit de votre gestionnaire de paquets",
        "to check for known vulnerabilities in your dependency tree": "pour vérifier les vulnérabilités connues dans votre arbre de dépendances",
        "As a development package": "En tant que paquet de développement",
        "does not directly collect end-user personal data": "ne collecte pas directement de données personnelles des utilisateurs finaux",
        "However, applications built with it may collect data depending on implementation": "Cependant, les applications construites avec peuvent collecter des données selon l'implémentation",
        "Review the package's dependencies for potential supply chain risks": "Examinez les dépendances du paquet pour les risques potentiels de chaîne d'approvisionnement",
        "License information not available": "Informations de licence non disponibles",
        "Open-source packages allow independent security review of the source code": "Les paquets open-source permettent un examen de sécurité indépendant du code source",
        "to check for vulnerabilities": "pour vérifier les vulnérabilités",
        "Review the": "Examiner le/la",
        "GitHub repository for recent commits": "dépôt GitHub pour les commits récents",
        "This meets the recommended security threshold for production use": "Cela atteint le seuil de sécurité recommandé pour une utilisation en production",
        "Nerq monitors this entity against NVD, OSV.dev, and registry-specific vulnerability databases": "Nerq surveille cette entité par rapport à NVD, OSV.dev et aux bases de données de vulnérabilités spécifiques aux registres",
        "for ongoing security assessment": "pour une évaluation de sécurité continue",
        "Yes, it is safe to use.": "Oui, il est sûr à utiliser.",
        "Use with some caution.": "Utiliser avec prudence.",
        "Exercise caution.": "Faire preuve de prudence.",
        "Significant trust concerns.": "Problèmes de confiance significatifs.",
        "maintained by": "maintenu par",
        "is computed from": "est calculé à partir de",
        "The score reflects": "Le score reflète",
        "independent dimensions": "dimensions indépendantes",
        "Each dimension is weighted equally to produce the composite trust score": "Chaque dimension est pondérée de manière égale pour produire le score de confiance composite",
        "No reviews yet.": "Pas encore d'avis.",
        "Be the first to review": "Soyez le premier à donner votre avis",
        "Write a review": "Écrire un avis",
        "Higher-rated": "Mieux notés",
        "you may want to consider:": "que vous pourriez envisager :",
        "under assessment": "en cours d'évaluation",
        # Health disclaimers
        "Important Notice:": "Avis Important :",
        "educational and informational purposes only": "à des fins éducatives et informatives uniquement",
        "does not constitute medical advice": "ne constitue pas un avis médical",
        "Consult a qualified healthcare professional": "Consultez un professionnel de santé qualifié",
        "Full health disclaimer": "Avertissement de santé complet",
        "Full disclaimer": "Avertissement complet",
    },
    "ja": {
        "What is NordVPN": "NordVPNの",
        "What are the best alternatives to NordVPN": "NordVPNの最良の代替品は何ですか",
        "NordVPN vs alternatives: which is safer": "NordVPN対代替品：どちらが安全か",
        "Does NordVPN log my data": "NordVPNはデータを記録しますか",
        "trust score?": "信頼スコアは？",
        "Is NordVPN safe": "NordVPNは安全ですか",
        "Run npm audit": "npm auditを実行",
        "full safety report for detailed privacy analysis": "詳細なプライバシー分析については完全な安全レポート",
        "In the npm category": "npmカテゴリでは",
        "In the vpn category": "VPNカテゴリでは",
        "Scores update as new data becomes available": "新しいデータが利用可能になるとスコアが更新さ���ます",
        "multiple public sources including package registries, GitHub, NVD, OSV.dev, and OpenSSF Scorecard": "パッケージレジストリ、GitHub、NVD、OSV.dev、OpenSSF Scorecardを含む複数の公開ソース",
        "The #1 safest": "最も安全な第1位",
        "How are safest": "最も安全な",
        "Are these safest": "これらの最も安全な",
        "What does a Nerq Trust Score": "Nerq Trust Scoreとは",
        "The #1": "第1位の",
        "According to Nerq": "Nerqによると",
        "How are": "どのように",
        "ranked by Nerq Trust Score": "Nerq Trust Scoreでランク付けされていますか",
        "What are the best": "最高の",
        "Are these rankings updated regularly": "これらのランキングは定期的に更新されますか",
        "What does a Nerq Trust Score measure": "Nerq Trust Scoreは何を測定しますか",
        "How does Nerq evaluate": "Nerqはどのように評価しますか",
        "Are these safe to use": "これらは安全に使用できますか",
        "{name} Privacy Report": "{name} プライバシーレポート",
        "has undergone third-party security audits verifying its infrastructure and no-logs claims": "インフラストラクチャとノーログの主張を検証するサードパーティのセキュリティ監査を受けています",
        "This is a strong positive signal — most VPN providers have not been independently audited": "これは強力な正のシグナルです — ほとんどのVPNプロバイダーは独立した監査を受けていません",
        "has not published results from an independent security audit": "独立したセキュリティ監査の結果を公開していません",
        "While this does not indicate a security issue, audited VPNs provide higher assurance": "これはセキュリティの問題を示すものではありませんが、監査済みVPNはより高い保証を提供します",
        "Security score": "セキュリティスコア",
        "Primary encryption protocol": "主要暗号化プロトコル",
        "which is considered industry-standard for VPN connections": "VPN接続の業界標準とされています",
        "Independent security audit verified": "独立セキュリティ監査確認済み",
        "has no known data breaches and has been independently audited": "既知のデータ侵害がなく、独立した監査を受けています",
        "uses AES-256-CBC (industry standard), Argon2id (brute-force resistant key derivation)": "AES-256-CBC（業界標準）、Argon2id（ブルートフォース耐性キー導出）を使用",
        "uses a zero-knowledge architecture": "ゼロナレッジアーキテクチャを使用しています",
        "your master password and vault data are encrypted locally and never sent to the server in plaintext": "マスターパスワードとボールトデータはローカルで暗号化され、平文でサーバーに送信されることはありません",
        "is open source with": "はオープンソースで",
        "GitHub stars": "GitHubスター",
        "Based in": "拠点:",
        "Independently audited": "独立監査済み",
        "No published independent audit": "公開された独立監査なし",
        "logging policy": "ロギングポリシー",
        "Safety Guide": "安全ガイド",
        "You can also check the trust score via API": "APIでも信頼スコアを確認できます",
        "meets Nerq trust threshold": "Nerq信頼しきい値を満たしています",
        "passes trust threshold": "信頼しきい値をクリア",
        "Recommended for use": "使用推奨",
        "This score is based on automated analysis of security, maintenance, community, and quality signals": "このスコアはセキュリティ、メンテナンス、コミュニティ、品質シグナルの自動分析に基づいています",
        "widely used": "広く使用されている",
        "No known data breaches associated with this service": "このサービスに関連する既知のデータ侵害はありません",
        "This is a strong positive signal": "これは強力な正のシグナルです",
        "most VPN providers have not been independently audited": "ほとんどのVPNプロバイダーは独立した監査を受けていません",
        "Full analysis": "完全な分析",
        "Same developer": "同じ開発者",
        "It is recommended": "推奨",
        "below the recommended threshold": "推奨しきい値未満",
        "Dimension": "次元",
        "Score": "スコア",
        "Data from": "データソース:",
        "Does": "は",
        "is based in": "の拠点は",
        "outside all Eyes surveillance alliances": "全てのEyes監視同盟の外",
        "a privacy advantage": "プライバシー上の利点",
        "has been independently audited to verify its privacy claims": "プライバシーの主張を検証するために独立した監査を受けています",
        "Serving": "ユーザー数:",
        "users": "ユーザー",
        "Related Safety Rankings": "関連する安全ランキング",
        "Complete Your Privacy Setup": "プライバシー設定を完成させる",
        "Add a password manager to your VPN for full protection": "VPNにパスワードマネージャーを追加して完全な保護を",
        "Add Antivirus Protection": "ウイルス対策を追加",
        "Complete your security with antivirus alongside your VPN": "VPNと併せてアンチウイルスでセキュリティを完成",
        "servers in": "のサーバー、",
        "countries": "か国",
        "logging practices": "ログ慣行",
        "audit history": "監査履歴",
        "ownership transparency": "所有権の透明性",
        "This is significant because VPN providers in": "これは重要です。なぜなら",
        "are not subject to mandatory data retention laws or intelligence-sharing agreements": "データ保持法や情報共有協定の対象ではないからです",
        "Server infrastructure": "サーバーインフラ",
        "servers across": "台のサーバー、",
        "Logging policy": "ログポリシー",
        "independently audited no-logs policy": "独立監査済みノーログポリシー",
        "According to independent audit reports": "独立監査報告書によると",
        "does not store connection logs, browsing activity, or DNS queries": "接続ログ、閲覧履歴、DNSクエリを保存しません",
        "score:": "スコア:",
        "Nerq analyzes over": "Nerqは",
        "What are the best alternatives to": "の最良の代替品は何ですか",
        "log my data": "はデータを記録しますか",
        "vs alternatives: which is safer": "対代替品：どちらが安全か",
        "Popular in": "人気の",
        "Browse Categories": "カテゴリを閲覧",
        "Safest VPNs": "最も安全なVPN",
        "Most Private Apps": "最もプライベートなアプリ",
        "Recently Analyzed": "最近の分析",
        "strong)": "強い)",
        "widely used VPN service": "広く使用されているVPNサービス",
        "Popularity": "人気度",
        "more VPN services are being analyzed": "さらに多くのVPNサービスが分析中です",
        "check back soon": "後で確認してください",
        "Nerq assesses": "Nerqは評価します",
        "data practices as part of its trust score": "のデータ慣行を信頼スコアの一部として",
        "Review full safety report for detailed privacy analysis": "詳細なプライバシー分析については完全な安全レポートを確認",
        "More VPN services are being analyzed for comparison": "比較のためにさらに多くのVPNサービスが分析中です",
        "Not Yet Analyzed": "まだ分析されていません",
        "Privacy Assessment": "プライバシー評価",
        "Breach History": "侵害履歴",
        "Encryption": "暗号化",
        "Zero-Knowledge Architecture": "ゼロナレッジ・アーキテクチャ",
        "Open Source": "オープンソース",
        "Infrastructure": "インフラストラクチャ",
        "Security & Compliance": "セキュリティとコンプライアンス",
        "Data Location": "データの所在地",
        "Security Incidents": "セキュリティインシデント",
        "Independent Lab Results": "独立ラボテスト結果",
        "Security Track Record": "セキュリティ実績",
        "Build Your Security Stack": "セキュリティスタックを構築",
        "Best VPNs": "ベストVPN",
        "Best Password Managers": "ベストパスワードマネージャー",
        "Best Antivirus": "ベストアンチウイルス",
        "Security Assessment": "セキュリティ評価",
        "Hosting Assessment": "ホスティング評価",
        "Antivirus Assessment": "アンチウイルス評価",
        "SaaS Assessment": "SaaS評価",
        "Website Builder Assessment": "ウェブサイトビルダー評価",
        "Exchange Assessment": "取引所評価",
        "Combine these tools for comprehensive protection:": "これらのツールを組み合わせて総合的に保護:",
        "Ecommerce": "Eコマース",
        "Proof of Reserves": "準備金証明",
        "jurisdiction databases, independent audit reports, protocol analysis, and incident history": "管轄データベース、独立監査報告書、プロトコル分析、インシデント履歴",
        "Panama jurisdiction": "パナマの管轄",
        "outside the Five Eyes, Nine Eyes, and Fourteen Eyes surveillance alliances": "ファイブアイズ、ナインアイズ、フォーティーンアイズの監視同盟の外",
        "Antivirus": "アンチウイルス",
        # Title / H1
        "Independent Trust & Security Analysis": "独立した信頼性・セキュリティ分析",
        "Independent Trust &amp; Security Analysis": "独立した信頼性・セキュリティ分析",
        # Verdicts
        "Yes, {name} is safe to use.": "はい、{name}は安全に使用できます。",
        "Use {name} with some caution.": "{name}の使用には注意が必要です。",
        "Exercise caution with {name}.": "{name}には注意してください。",
        "{name} has significant trust concerns.": "{name}には重大な信頼性の懸念があります。",
        "Passes Nerq Verified threshold": "Nerq認証閾値を超えています",
        "Below Nerq Verified threshold": "Nerq認証閾値を下回っています",
        "Significant trust gaps detected": "重大な信頼性のギャップが検出されました",
        # Section headings
        "Trust Score Breakdown": "信頼スコアの内訳",
        "Safety Score Breakdown": "安全スコアの内訳",
        "Key Findings": "主な調査結果",
        "Key Safety Findings": "主な安全性の調査結果",
        "Detailed Score Analysis": "詳細なスコア分析",
        "Frequently Asked Questions": "よくある質問",
        "Safer Alternatives": "より安全な代替品",
        "Popular Alternatives": "人気の代替品",
        "Community Reviews": "コミュニティレビュー",
        "Regulatory Compliance": "規制コンプライアンス",
        "How we calculated this score": "このスコアの算出方法",
        "What We Know About": "について分かっていること",
        # Safety Guide
        "Safety Guide:": "安全ガイド：",
        "What is": "とは",
        "How to Verify Safety": "安全性の確認方法",
        "Key Safety Concerns for": "に関する主な安全性の懸念",
        "Trust Assessment": "信頼性評価",
        "Key Takeaways": "重要なポイント",
        "Recommended for use — passes trust threshold.": "使用を推奨 — 信頼閾値を超えています。",
        "Review carefully before use — below trust threshold.": "使用前に慎重に確認 — 信頼閾値を下回っています。",
        "Always verify independently using the": "常に独自に確認してください",
        "When evaluating any": "評価する際には",
        "watch for:": "注意すべき点：",
        # Cross-product
        "Across Platforms": "プラットフォーム横断",
        "across platforms": "プラットフォーム横断",
        "Same developer/company in other registries:": "他のレジストリでの同じ開発者/企業：",
        # King sections
        "What data does": "どのようなデータを収集しますか",
        "collect?": "収集？",
        "Is": "",
        "secure?": "は安全ですか？",
        "Full analysis:": "完全な分析：",
        "Privacy Report": "プライバシーレポート",
        "Privacy review": "プライバシーレビュー",
        "Security Report": "セキュリティレポート",
        # Dimensions
        "Security": "セキュリティ",
        "Privacy": "プライバシー",
        "Reliability": "信頼性",
        "Transparency": "透明性",
        "Maintenance": "メンテナンス",
        "Overall Trust": "総合信頼度",
        "Composite trust score": "複合信頼スコア",
        "across all available signals": "すべての利用可能なシグナルにわたる",
        # Methodology
        "Nerq analyzes over 7.5 million entities across 26 registries": "Nerqは26のレジストリにわたる750万以上のエンティティを分析しています",
        "using the same methodology, enabling direct cross-entity comparison": "同じ方法論を使用し、エンティティ間の直接比較を可能にします",
        "Scores are updated continuously as new data becomes available": "新しいデータが利用可能になり次第、スコアは継続的に更新されます",
        "This page was last reviewed on": "このページの最終レビュー日：",
        "Data version": "データバージョン",
        "Full methodology documentation": "方法論の完全なドキュメント",
        "Machine-readable data (JSON API)": "機械可読データ（JSON API）",
        "Machine-readable data (JSON)": "機械可読データ（JSON）",
        # Meta / small text
        "Last analyzed:": "最終分析日：",
        "Last updated": "最終更新",
        "Updated daily": "毎日更新",
        "Independent. Data-driven.": "独立。データ駆動。",
        "verified": "認証済み",
        "Data sourced from": "データソース：",
        "Based on": "に基づく",
        "dimensions": "次元",
        "independent data dimensions": "独立したデータ次元",
        "strong": "強い",
        "moderate": "中程度",
        "weak": "弱い",
        "actively maintained": "積極的にメンテナンスされている",
        "moderately maintained": "適度にメンテナンスされている",
        "low maintenance activity": "メンテナンス活動が低い",
        "well-documented": "十分に文書化されている",
        "partial documentation": "部分的なドキュメント",
        "limited documentation": "限定的なドキュメント",
        "community adoption": "コミュニティでの採用",
        "stars on": "スター（",
        # Cross-links
        "Safety": "安全性",
        "Legit?": "正当？",
        "Scam?": "詐欺？",
        "Review": "レビュー",
        "Alternatives": "代替品",
        "Compare": "比較",
        "Best in Category": "カテゴリ最高",
        "Who Owns?": "所有者は？",
        "What Is?": "とは？",
        "Sells Data?": "データ販売？",
        "Hacked?": "ハッキング？",
        "Safe for Kids?": "子供に安全？",
        "Pros &amp; Cons": "長所と短所",
        # FAQ answers
        "Nerq Verified — meets the 70+ trust threshold.": "Nerq認証済み — 70以上の信頼閾値を満たしています。",
        "Below the Nerq Verified threshold of 70.": "Nerq認証閾値の70を下回っています。",
        "Has not yet reached the Nerq Verified threshold of 70.": "まだNerq認証閾値の70に達していません。",
        "Strongest signal:": "最強のシグナル：",
        "Score based on": "スコアの基準：",
        "security": "セキュリティ",
        "maintenance": "メンテナンス",
        "popularity": "人気度",
        "documentation": "ドキュメント",
        "compliance": "コンプライアンス",
        # Verdict box
        "Safe": "安全",
        "Use Caution": "注意",
        "Avoid": "回避",
        # Long text patterns (safety guide, methodology, privacy)
        "is a Node.js package": "はNode.jsパッケージです",
        "is a Python package": "はPythonパッケージです",
        "is a Rust crate": "はRustクレートです",
        "is a Chrome extension": "はChrome拡張機能です",
        "is a Firefox extension": "はFirefox拡張機能です",
        "is a VS Code extension": "はVS Code拡張機能です",
        "is a WordPress plugin": "はWordPressプラグインです",
        "is a iOS app": "はiOSアプリです",
        "is a Android app": "はAndroidアプリです",
        "is a VPN service": "はVPNサービスです",
        "is a game": "はゲームです",
        "is a website": "はウェブサイトです",
        "is a SaaS platform": "はSaaSプラットフォームです",
        "is a dietary supplement": "は栄養補助食品です",
        "is a cosmetic ingredient": "は化粧品成分です",
        "is a food": "は食品添加物です",
        "is a travel destination": "は旅行先です",
        "is a nonprofit organization": "は非営利団体です",
        "with a Nerq Trust Score of": "Nerq信頼スコアは",
        "with a Nerq Safety Score of": "Nerq安全スコアは",
        "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "セキュリティ、メンテナンス、コミュニティ採用において強力なシグナルでNerqの信頼閾値を満たしています",
        "It has moderate trust signals but shows some areas of concern": "中程度の信頼シグナルがありますが、一部懸念される領域があります",
        "It has below-average trust signals with significant gaps": "平均以下の信頼シグナルで、重大なギャップがあります",
        "review the full report below for specific considerations": "具体的な考慮事項については、以下の完全なレポートをご覧ください",
        "This score is based on automated analysis of security, maintenance, community, and quality signals.": "このスコアは、セキュリティ、メンテナンス、コミュニティ、品質シグナルの自動分析に基づいています。",
        "You can also check the trust score via API:": "APIを通じて信頼スコアを確認することもできます：",
        "dependency vulnerabilities, malicious packages, typosquatting": "依存関係の脆弱性、悪意のあるパッケージ、タイポスクワッティング",
        "Run your package manager's audit command": "パッケージマネージャーの監査コマンドを実行してください",
        "to check for known vulnerabilities in your dependency tree": "依存関係ツリーの既知の脆弱性を確認するため",
        "As a development package": "開発パッケージとして",
        "does not directly collect end-user personal data": "エンドユーザーの個人データを直接収集しません",
        "However, applications built with it may collect data depending on implementation": "ただし、これを使用して構築されたアプリケーションは、実装に応じてデータを収集する場合があります",
        "Review the package's dependencies for potential supply chain risks": "潜在的なサプライチェーンリスクについてパッケージの依存関係を確認してください",
        "License information not available": "ライセンス情報は利用できません",
        "Open-source packages allow independent security review of the source code": "オープンソースパッケージは、ソースコードの独立したセキュリティレビューを可能にします",
        "to check for vulnerabilities": "脆弱性を確認するため",
        "Review the": "確認してください",
        "GitHub repository for recent commits": "最近のコミットについてGitHubリポジトリ",
        "This meets the recommended security threshold for production use": "これは本番環境での使用に推奨されるセキュリティ閾値を満たしています",
        "Nerq monitors this entity against NVD, OSV.dev, and registry-specific vulnerability databases": "NerqはNVD、OSV.dev、およびレジストリ固有の脆弱性データベースに対してこのエンティティを監視しています",
        "for ongoing security assessment": "継続的なセキュリティ評価のため",
        "Yes, it is safe to use.": "はい、安全に使用できます。",
        "Use with some caution.": "注意して使用してください。",
        "Exercise caution.": "注意が必要です。",
        "Significant trust concerns.": "重大な信頼性の懸念があります。",
        "maintained by": "メンテナンス担当：",
        "is computed from": "は以下から算出されます",
        "The score reflects": "スコアは以下を反映しています",
        "independent dimensions": "独立した次元",
        "Each dimension is weighted equally to produce the composite trust score": "各次元は均等に重み付けされ、複合信頼スコアが算出されます",
        "No reviews yet.": "まだレビューはありません。",
        "Be the first to review": "最初のレビューを書く",
        "Write a review": "レビューを書く",
        "Higher-rated": "より高評価の",
        "you may want to consider:": "検討してみてください：",
        "under assessment": "評価中",
        # Health disclaimers
        "Important Notice:": "重要なお知らせ：",
        "educational and informational purposes only": "教育および情報提供のみを目的としています",
        "does not constitute medical advice": "医学的助言を構成するものではありません",
        "Consult a qualified healthcare professional": "資格のある医療専門家にご相談ください",
        "Full health disclaimer": "健康に関する免責事項の全文",
        "Full disclaimer": "免責事項の全文",
    },
    "pt": {
        "It is ": "É ",
        "Best Antivirus": "Melhor Antivírus",
        "Is NordVPN safe": "NordVPN é seguro",
        "What is NordVPN": "O que é NordVPN",
        "Does NordVPN log my data": "O NordVPN registra meus dados",
        "What are the best alternatives to NordVPN": "Quais são as melhores alternativas ao NordVPN",
        "NordVPN vs alternatives: which is safer": "NordVPN vs alternativas: qual é mais seguro",
        "trust score?": "pontuação de confiança?",
        "Scores update as new data becomes available": "As pontuações são atualizadas quando novos dados estão disponíveis",
        "In the vpn category": "Na categoria VPN",
        "full safety report for detailed privacy analysis": "relatório de segurança completo para análise detalhada de privacidade",
        "jurisdiction databases, independent audit reports, protocol analysis, and incident history": "bancos de dados jurisdicionais, relatórios de auditoria independentes, análise de protocolos e histórico de incidentes",
        "has undergone third-party security audits verifying its infrastructure and no-logs claims": "passou por auditorias de segurança de terceiros verificando sua infraestrutura e alegações de no-logs",
        "widely used VPN service": "serviço VPN amplamente utilizado",
        "multiple public sources including package registries, GitHub, NVD, OSV.dev, and OpenSSF Scorecard": "múltiplas fontes públicas incluindo registros de pacotes, GitHub, NVD, OSV.dev e OpenSSF Scorecard",
        "Are these safest": "São estes os mais seguros",
        "How are safest": "Como são os mais seguros",
        "Best Password Managers": "Melhores Gerenciadores de Senhas",
        "What does a Nerq Trust Score": "O que significa um Nerq Trust Score",
        "The #1 safest": "O mais seguro",
        "The #1": "O nº 1",
        "According to Nerq": "Segundo Nerq",
        "How are": "Como são",
        "What are the best": "Quais são os melhores",
        "Combine these tools for comprehensive protection:": "Combine estas ferramentas para proteção abrangente:",
        "Logging policy": "Política de registro",
        "passes trust threshold": "atinge o limiar de confiança",
        "Recommended for use": "Recomendado para uso",
        "This score is based on automated analysis of security, maintenance, community, and quality signals": "Esta pontuação é baseada em análise automatizada de sinais de segurança, manutenção, comunidade e qualidade",
        "According to independent audit reports": "De acordo com relatórios de auditoria independentes",
        "No known data breaches associated with this service": "Nenhuma violação de dados conhecida associada a este serviço",
        "This is a strong positive signal": "Este é um sinal positivo forte",
        "logging policy": "política de registro",
        "Full analysis": "Análise completa",
        "Server infrastructure": "Infraestrutura de servidores",
        "It is recommended": "É recomendado",
        "most VPN providers have not been independently audited": "a maioria dos provedores de VPN não foi auditada independentemente",
        "Nerq analyzes over": "Nerq analisa mais de",
        "Safety Guide": "Guia de segurança",
        "is based in": "tem sede em",
        "outside all Eyes surveillance alliances": "fora de todas as alianças de vigilância Eyes",
        "a privacy advantage": "uma vantagem de privacidade",
        "has been independently audited to verify its privacy claims": "foi auditado independentemente para verificar suas reivindicações de privacidade",
        "Serving": "Atendendo",
        "Related Safety Rankings": "Rankings de segurança relacionados",
        "Complete Your Privacy Setup": "Complete sua configuração de privacidade",
        "Add a password manager to your VPN for full protection": "Adicione um gerenciador de senhas ao seu VPN para proteção total",
        "Browse Categories": "Navegar categorias",
        "Safest VPNs": "VPNs mais seguros",
        "Most Private Apps": "Apps mais privados",
        "Recently Analyzed": "Analisados recentemente",
        "What are the best alternatives to": "Quais são as melhores alternativas para",
        "which is safer": "qual é mais seguro",
        "logging practices": "práticas de registro",
        "ownership transparency": "transparência de propriedade",
        "Popular in": "Popular em",
        "Popularity": "Popularidade",
        "Not Yet Analyzed": "Ainda não analisado",
        # Title / H1
        "Independent Trust & Security Analysis": "Análise Independente de Confiança e Segurança",
        "Independent Trust &amp; Security Analysis": "Análise Independente de Confiança e Segurança",
        # Verdicts
        "Yes, {name} is safe to use.": "Sim, {name} é seguro para usar.",
        "Use {name} with some caution.": "Use {name} com cautela.",
        "Exercise caution with {name}.": "Tenha cuidado com {name}.",
        "{name} has significant trust concerns.": "{name} apresenta preocupações significativas de confiança.",
        "Passes Nerq Verified threshold": "Supera o limite de verificação Nerq",
        "Below Nerq Verified threshold": "Abaixo do limite de verificação Nerq",
        "Significant trust gaps detected": "Lacunas significativas de confiança detectadas",
        # Section headings
        "Trust Score Breakdown": "Detalhamento da Pontuação de Confiança",
        "Safety Score Breakdown": "Detalhamento da Pontuação de Segurança",
        "Key Findings": "Principais Descobertas",
        "Key Safety Findings": "Principais Descobertas de Segurança",
        "Detailed Score Analysis": "Análise Detalhada da Pontuação",
        "Frequently Asked Questions": "Perguntas Frequentes",
        "Safer Alternatives": "Alternativas Mais Seguras",
        "Popular Alternatives": "Alternativas Populares",
        "Community Reviews": "Avaliações da Comunidade",
        "Regulatory Compliance": "Conformidade Regulatória",
        "How we calculated this score": "Como calculamos esta pontuação",
        "What We Know About": "O Que Sabemos Sobre",
        # Safety Guide
        "Safety Guide:": "Guia de Segurança:",
        "What is": "O que é",
        "How to Verify Safety": "Como Verificar a Segurança",
        "Key Safety Concerns for": "Principais Preocupações de Segurança para",
        "Trust Assessment": "Avaliação de Confiança",
        "Key Takeaways": "Pontos Principais",
        "Recommended for use — passes trust threshold.": "Recomendado para uso — supera o limite de confiança.",
        "Review carefully before use — below trust threshold.": "Revisar cuidadosamente antes de usar — abaixo do limite de confiança.",
        "Always verify independently using the": "Sempre verifique independentemente usando a",
        "When evaluating any": "Ao avaliar qualquer",
        "watch for:": "observe:",
        # Cross-product
        "Across Platforms": "Em Todas as Plataformas",
        "across platforms": "em todas as plataformas",
        "Same developer/company in other registries:": "Mesmo desenvolvedor/empresa em outros registros:",
        # King sections
        "What data does": "Quais dados coleta",
        "collect?": "coletar?",
        "Is": "É",
        "secure?": "seguro?",
        "Full analysis:": "Análise completa:",
        "Privacy Report": "Relatório de Privacidade",
        "Privacy review": "Revisão de Privacidade",
        "Security Report": "Relatório de Segurança",
        # Dimensions
        "Security": "Segurança",
        "Privacy": "Privacidade",
        "Reliability": "Confiabilidade",
        "Transparency": "Transparência",
        "Maintenance": "Manutenção",
        "Overall Trust": "Confiança Geral",
        "Composite trust score": "Pontuação composta de confiança",
        "across all available signals": "em todos os sinais disponíveis",
        # Methodology
        "Nerq analyzes over 7.5 million entities across 26 registries": "O Nerq analisa mais de 7,5 milhões de entidades em 26 registros",
        "using the same methodology, enabling direct cross-entity comparison": "usando a mesma metodologia, permitindo comparação direta entre entidades",
        "Scores are updated continuously as new data becomes available": "As pontuações são atualizadas continuamente à medida que novos dados ficam disponíveis",
        "This page was last reviewed on": "Esta página foi revisada pela última vez em",
        "Data version": "Versão dos dados",
        "Full methodology documentation": "Documentação completa da metodologia",
        "Machine-readable data (JSON API)": "Dados legíveis por máquina (API JSON)",
        "Machine-readable data (JSON)": "Dados legíveis por máquina (JSON)",
        # Meta / small text
        "Last analyzed:": "Última análise:",
        "Last updated": "Última atualização",
        "Updated daily": "Atualizado diariamente",
        "Independent. Data-driven.": "Independente. Orientado por dados.",
        "verified": "verificado",
        "Data sourced from": "Dados obtidos de",
        "Based on": "Baseado em",
        "dimensions": "dimensões",
        "independent data dimensions": "dimensões de dados independentes",
        "strong": "forte",
        "moderate": "moderado",
        "weak": "fraco",
        "actively maintained": "ativamente mantido",
        "moderately maintained": "moderadamente mantido",
        "low maintenance activity": "baixa atividade de manutenção",
        "well-documented": "bem documentado",
        "partial documentation": "documentação parcial",
        "limited documentation": "documentação limitada",
        "community adoption": "adoção pela comunidade",
        "stars on": "estrelas em",
        # Cross-links
        "Safety": "Segurança",
        "Legit?": "Legítimo?",
        "Scam?": "Golpe?",
        "Review": "Avaliação",
        "Alternatives": "Alternativas",
        "Compare": "Comparar",
        "Best in Category": "Melhor na Categoria",
        "Who Owns?": "Quem é o Dono?",
        "What Is?": "O Que É?",
        "Sells Data?": "Vende Dados?",
        "Hacked?": "Hackeado?",
        "Safe for Kids?": "Seguro para Crianças?",
        "Pros &amp; Cons": "Prós e Contras",
        # FAQ answers
        "Nerq Verified — meets the 70+ trust threshold.": "Verificado pelo Nerq — supera o limite de confiança de 70+.",
        "Below the Nerq Verified threshold of 70.": "Abaixo do limite de verificação Nerq de 70.",
        "Has not yet reached the Nerq Verified threshold of 70.": "Ainda não atingiu o limite de verificação Nerq de 70.",
        "Strongest signal:": "Sinal mais forte:",
        "Score based on": "Pontuação baseada em",
        "security": "segurança",
        "maintenance": "manutenção",
        "popularity": "popularidade",
        "documentation": "documentação",
        "compliance": "conformidade",
        # Verdict box
        "Safe": "Seguro",
        "Use Caution": "Cuidado",
        "Avoid": "Evitar",
        # Long text patterns (safety guide, methodology, privacy)
        "is a Node.js package": "é um pacote Node.js",
        "is a Python package": "é um pacote Python",
        "is a Rust crate": "é um crate Rust",
        "is a Chrome extension": "é uma extensão do Chrome",
        "is a Firefox extension": "é uma extensão do Firefox",
        "is a VS Code extension": "é uma extensão do VS Code",
        "is a WordPress plugin": "é um plugin do WordPress",
        "is a iOS app": "é um aplicativo iOS",
        "is a Android app": "é um aplicativo Android",
        "is a VPN service": "é um serviço de VPN",
        "is a game": "é um jogo",
        "is a website": "é um site",
        "is a SaaS platform": "é uma plataforma SaaS",
        "is a dietary supplement": "é um suplemento dietético",
        "is a cosmetic ingredient": "é um ingrediente cosmético",
        "is a food": "é um aditivo alimentar",
        "is a travel destination": "é um destino turístico",
        "is a nonprofit organization": "é uma organização sem fins lucrativos",
        "with a Nerq Trust Score of": "com uma Pontuação de Confiança Nerq de",
        "with a Nerq Safety Score of": "com uma Pontuação de Segurança Nerq de",
        "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "Atende ao limite de confiança do Nerq com sinais fortes em segurança, manutenção e adoção pela comunidade",
        "It has moderate trust signals but shows some areas of concern": "Possui sinais de confiança moderados, mas apresenta algumas áreas de preocupação",
        "It has below-average trust signals with significant gaps": "Possui sinais de confiança abaixo da média com lacunas significativas",
        "review the full report below for specific considerations": "revise o relatório completo abaixo para considerações específicas",
        "This score is based on automated analysis of security, maintenance, community, and quality signals.": "Esta pontuação é baseada em análise automatizada de sinais de segurança, manutenção, comunidade e qualidade.",
        "You can also check the trust score via API:": "Você também pode verificar a pontuação de confiança via API:",
        "dependency vulnerabilities, malicious packages, typosquatting": "vulnerabilidades de dependências, pacotes maliciosos, typosquatting",
        "Run your package manager's audit command": "Execute o comando de auditoria do seu gerenciador de pacotes",
        "to check for known vulnerabilities in your dependency tree": "para verificar vulnerabilidades conhecidas em sua árvore de dependências",
        "As a development package": "Como pacote de desenvolvimento",
        "does not directly collect end-user personal data": "não coleta diretamente dados pessoais do usuário final",
        "However, applications built with it may collect data depending on implementation": "No entanto, aplicações construídas com ele podem coletar dados dependendo da implementação",
        "Review the package's dependencies for potential supply chain risks": "Revise as dependências do pacote para possíveis riscos na cadeia de suprimentos",
        "License information not available": "Informações de licença não disponíveis",
        "Open-source packages allow independent security review of the source code": "Pacotes de código aberto permitem revisão de segurança independente do código-fonte",
        "to check for vulnerabilities": "para verificar vulnerabilidades",
        "Review the": "Revise o/a",
        "GitHub repository for recent commits": "repositório do GitHub para commits recentes",
        "This meets the recommended security threshold for production use": "Isso atende ao limite de segurança recomendado para uso em produção",
        "Nerq monitors this entity against NVD, OSV.dev, and registry-specific vulnerability databases": "O Nerq monitora esta entidade contra NVD, OSV.dev e bancos de dados de vulnerabilidades específicos de registros",
        "for ongoing security assessment": "para avaliação contínua de segurança",
        "Yes, it is safe to use.": "Sim, é seguro para usar.",
        "Use with some caution.": "Usar com cautela.",
        "Exercise caution.": "Tenha cuidado.",
        "Significant trust concerns.": "Preocupações significativas de confiança.",
        "maintained by": "mantido por",
        "is computed from": "é calculado a partir de",
        "The score reflects": "A pontuação reflete",
        "independent dimensions": "dimensões independentes",
        "Each dimension is weighted equally to produce the composite trust score": "Cada dimensão é ponderada igualmente para produzir a pontuação composta de confiança",
        "No reviews yet.": "Nenhuma avaliação ainda.",
        "Be the first to review": "Seja o primeiro a avaliar",
        "Write a review": "Escrever uma avaliação",
        "Higher-rated": "Melhor avaliadas",
        "you may want to consider:": "que você pode considerar:",
        "under assessment": "em avaliação",
        # Health disclaimers
        "Important Notice:": "Aviso Importante:",
        "educational and informational purposes only": "apenas para fins educacionais e informativos",
        "does not constitute medical advice": "não constitui aconselhamento médico",
        "Consult a qualified healthcare professional": "Consulte um profissional de saúde qualificado",
        "Full health disclaimer": "Aviso de saúde completo",
        "Full disclaimer": "Aviso legal completo",
    },
    "id": {
        "It is ": "Ini ",
        "Is NordVPN safe": "Apakah NordVPN aman",
        "What is NordVPN": "Apa itu NordVPN",
        "Does NordVPN log my data": "Apakah NordVPN mencatat data saya",
        "What are the best alternatives to NordVPN": "Apa alternatif terbaik untuk NordVPN",
        "NordVPN vs alternatives: which is safer": "NordVPN vs alternatif: mana yang lebih aman",
        "trust score?": "skor kepercayaan?",
        "Scores update as new data becomes available": "Skor diperbarui saat data baru tersedia",
        "In the vpn category": "Di kategori VPN",
        "full safety report for detailed privacy analysis": "laporan keamanan lengkap untuk analisis privasi terperinci",
        "jurisdiction databases, independent audit reports, protocol analysis, and incident history": "database yurisdiksi, laporan audit independen, analisis protokol, dan riwayat insiden",
        "has undergone third-party security audits verifying its infrastructure and no-logs claims": "telah menjalani audit keamanan pihak ketiga yang memverifikasi infrastruktur dan klaim tanpa pencatatan",
        "widely used VPN service": "layanan VPN yang banyak digunakan",
        "multiple public sources including package registries, GitHub, NVD, OSV.dev, and OpenSSF Scorecard": "berbagai sumber publik termasuk registri paket, GitHub, NVD, OSV.dev, dan OpenSSF Scorecard",
        "What does a Nerq Trust Score": "Apa arti Nerq Trust Score",
        "Are these safest": "Apakah ini yang teraman",
        "How are safest": "Bagaimana yang teraman",
        "The #1 safest": "Teraman #1",
        "The #1": "#1",
        "According to Nerq": "Menurut Nerq",
        "How are": "Bagaimana",
        "What are the best": "Apa yang terbaik",
        "Logging policy": "Kebijakan pencatatan",
        "Safety Guide": "Panduan Keamanan",
        "passes trust threshold": "melewati ambang kepercayaan",
        "Recommended for use": "Direkomendasikan untuk digunakan",
        "This score is based on automated analysis of security, maintenance, community, and quality signals": "Skor ini didasarkan pada analisis otomatis sinyal keamanan, pemeliharaan, komunitas, dan kualitas",
        "According to independent audit reports": "Menurut laporan audit independen",
        "No known data breaches associated with this service": "Tidak ada pelanggaran data yang diketahui terkait dengan layanan ini",
        "This is a strong positive signal": "Ini adalah sinyal positif yang kuat",
        "logging policy": "kebijakan pencatatan",
        "Full analysis": "Analisis lengkap",
        "Server infrastructure": "Infrastruktur server",
        "It is recommended": "Direkomendasikan",
        "most VPN providers have not been independently audited": "sebagian besar penyedia VPN belum diaudit secara independen",
        "Nerq analyzes over": "Nerq menganalisis lebih dari",
        "is based in": "berkantor pusat di",
        "outside all Eyes surveillance alliances": "di luar semua aliansi pengawasan Eyes",
        "a privacy advantage": "keuntungan privasi",
        "has been independently audited to verify its privacy claims": "telah diaudit secara independen untuk memverifikasi klaim privasinya",
        "Serving": "Melayani",
        "Related Safety Rankings": "Peringkat keamanan terkait",
        "Complete Your Privacy Setup": "Lengkapi pengaturan privasi Anda",
        "Browse Categories": "Jelajahi kategori",
        "Safest VPNs": "VPN teraman",
        "Most Private Apps": "Aplikasi paling privat",
        "Recently Analyzed": "Baru dianalisis",
        "What are the best alternatives to": "Apa alternatif terbaik untuk",
        "which is safer": "mana yang lebih aman",
        "logging practices": "praktik pencatatan",
        "ownership transparency": "transparansi kepemilikan",
        "Popular in": "Populer di",
        "Popularity": "Popularitas",
        "Not Yet Analyzed": "Belum dianalisis",
        # ── Vertical-specific strings ──
        "Privacy Assessment": "Penilaian Privasi",
        "Breach History": "Riwayat Pelanggaran",
        "Encryption": "Enkripsi",
        "Build Your Security Stack": "Bangun Paket Keamanan Anda",
        "Best VPNs": "VPN Terbaik",
        "Best Password Managers": "Pengelola Kata Sandi Terbaik",
        "Best Antivirus": "Antivirus Terbaik",
        "Security Assessment": "Penilaian Keamanan",
        "Security & Compliance": "Keamanan & Kepatuhan",
        "Combine these tools for comprehensive protection:": "Kombinasikan alat-alat ini untuk perlindungan menyeluruh:",
        # Title / H1
        "Independent Trust & Security Analysis": "Analisis Kepercayaan & Keamanan Independen",
        "Independent Trust &amp; Security Analysis": "Analisis Kepercayaan &amp; Keamanan Independen",
        # Verdicts
        "Yes, {name} is safe to use.": "Ya, {name} aman digunakan.",
        "Use {name} with some caution.": "Gunakan {name} dengan hati-hati.",
        "Exercise caution with {name}.": "Berhati-hatilah dengan {name}.",
        "{name} has significant trust concerns.": "{name} memiliki masalah kepercayaan yang signifikan.",
        "Passes Nerq Verified threshold": "Memenuhi ambang batas terverifikasi Nerq",
        "Below Nerq Verified threshold": "Di bawah ambang batas terverifikasi Nerq",
        "Significant trust gaps detected": "Celah kepercayaan signifikan terdeteksi",
        # Section headings
        "Trust Score Breakdown": "Rincian Skor Kepercayaan",
        "Safety Score Breakdown": "Rincian Skor Keamanan",
        "Key Findings": "Temuan Utama",
        "Key Safety Findings": "Temuan Keamanan Utama",
        "Detailed Score Analysis": "Analisis Skor Terperinci",
        "Frequently Asked Questions": "Pertanyaan yang Sering Diajukan",
        "Safer Alternatives": "Alternatif Lebih Aman",
        "Popular Alternatives": "Alternatif Populer",
        "Community Reviews": "Ulasan Komunitas",
        "Regulatory Compliance": "Kepatuhan Regulasi",
        "How we calculated this score": "Cara kami menghitung skor ini",
        "What We Know About": "Yang Kami Ketahui Tentang",
        # Safety Guide
        "Safety Guide:": "Panduan Keamanan:",
        "What is": "Apa itu",
        "How to Verify Safety": "Cara Memverifikasi Keamanan",
        "Key Safety Concerns for": "Masalah Keamanan Utama untuk",
        "Trust Assessment": "Penilaian Kepercayaan",
        "Key Takeaways": "Kesimpulan Utama",
        "Recommended for use — passes trust threshold.": "Direkomendasikan — memenuhi ambang batas kepercayaan.",
        "Review carefully before use — below trust threshold.": "Tinjau dengan saksama sebelum digunakan — di bawah ambang batas kepercayaan.",
        "Always verify independently using the": "Selalu verifikasi secara mandiri menggunakan",
        "When evaluating any": "Saat mengevaluasi",
        "watch for:": "perhatikan:",
        # Cross-product
        "Across Platforms": "Di Platform Lain",
        "across platforms": "di platform lain",
        "Same developer/company in other registries:": "Developer/perusahaan yang sama di registry lain:",
        # King sections
        "What data does": "Data apa yang dikumpulkan",
        "collect?": "kumpulkan?",
        "Is": "Apakah",
        "secure?": "aman?",
        "Full analysis:": "Analisis lengkap:",
        "Privacy Report": "Laporan Privasi",
        "Privacy review": "Tinjauan Privasi",
        "Security Report": "Laporan Keamanan",
        # Dimensions
        "Security": "Keamanan",
        "Privacy": "Privasi",
        "Reliability": "Keandalan",
        "Transparency": "Transparansi",
        "Maintenance": "Pemeliharaan",
        "Overall Trust": "Kepercayaan Keseluruhan",
        "Composite trust score": "Skor kepercayaan komposit",
        "across all available signals": "dari semua sinyal yang tersedia",
        # Methodology
        "Nerq analyzes over 7.5 million entities across 26 registries": "Nerq menganalisis lebih dari 7,5 juta entitas di 26 registry",
        "using the same methodology, enabling direct cross-entity comparison": "menggunakan metodologi yang sama, memungkinkan perbandingan langsung antar entitas",
        "Scores are updated continuously as new data becomes available": "Skor diperbarui secara berkelanjutan saat data baru tersedia",
        "This page was last reviewed on": "Halaman ini terakhir ditinjau pada",
        "Data version": "Versi data",
        "Full methodology documentation": "Dokumentasi metodologi lengkap",
        "Machine-readable data (JSON API)": "Data yang dapat dibaca mesin (API JSON)",
        "Machine-readable data (JSON)": "Data yang dapat dibaca mesin (JSON)",
        # Meta / small text
        "Last analyzed:": "Terakhir dianalisis:",
        "Last updated": "Terakhir diperbarui",
        "Updated daily": "Diperbarui setiap hari",
        "Independent. Data-driven.": "Independen. Berbasis data.",
        "verified": "terverifikasi",
        "Data sourced from": "Data bersumber dari",
        "Based on": "Berdasarkan",
        "dimensions": "dimensi",
        "independent data dimensions": "dimensi data independen",
        "strong": "kuat",
        "moderate": "sedang",
        "weak": "lemah",
        "actively maintained": "aktif dipelihara",
        "moderately maintained": "cukup dipelihara",
        "low maintenance activity": "aktivitas pemeliharaan rendah",
        "well-documented": "terdokumentasi dengan baik",
        "partial documentation": "dokumentasi sebagian",
        "limited documentation": "dokumentasi terbatas",
        "community adoption": "adopsi komunitas",
        "stars on": "bintang di",
        # Cross-links
        "Safety": "Keamanan",
        "Legit?": "Sah?",
        "Scam?": "Penipuan?",
        "Review": "Ulasan",
        "Alternatives": "Alternatif",
        "Compare": "Bandingkan",
        "Best in Category": "Terbaik di Kategori",
        "Who Owns?": "Siapa Pemiliknya?",
        "What Is?": "Apa Itu?",
        "Sells Data?": "Jual Data?",
        "Hacked?": "Diretas?",
        "Safe for Kids?": "Aman untuk Anak?",
        "Pros &amp; Cons": "Kelebihan &amp; Kekurangan",
        # FAQ answers
        "Nerq Verified — meets the 70+ trust threshold.": "Terverifikasi Nerq — memenuhi ambang batas kepercayaan 70+.",
        "Below the Nerq Verified threshold of 70.": "Di bawah ambang batas verifikasi Nerq yaitu 70.",
        "Has not yet reached the Nerq Verified threshold of 70.": "Belum mencapai ambang batas verifikasi Nerq yaitu 70.",
        "Strongest signal:": "Sinyal terkuat:",
        "Score based on": "Skor berdasarkan",
        "security": "keamanan",
        "maintenance": "pemeliharaan",
        "popularity": "popularitas",
        "documentation": "dokumentasi",
        "compliance": "kepatuhan",
        # Verdict box
        "Safe": "Aman",
        "Use Caution": "Hati-hati",
        "Avoid": "Hindari",
        # Long text patterns
        "is a Node.js package": "adalah paket Node.js",
        "is a Python package": "adalah paket Python",
        "is a Rust crate": "adalah crate Rust",
        "is a Chrome extension": "adalah ekstensi Chrome",
        "is a Firefox extension": "adalah ekstensi Firefox",
        "is a VS Code extension": "adalah ekstensi VS Code",
        "is a WordPress plugin": "adalah plugin WordPress",
        "is a iOS app": "adalah aplikasi iOS",
        "is a Android app": "adalah aplikasi Android",
        "is a VPN service": "adalah layanan VPN",
        "is a game": "adalah game",
        "is a website": "adalah situs web",
        "is a SaaS platform": "adalah platform SaaS",
        "is a dietary supplement": "adalah suplemen makanan",
        "is a cosmetic ingredient": "adalah bahan kosmetik",
        "is a food": "adalah bahan makanan",
        "is a travel destination": "adalah destinasi wisata",
        "is a nonprofit organization": "adalah organisasi nirlaba",
        "with a Nerq Trust Score of": "dengan Skor Kepercayaan Nerq sebesar",
        "with a Nerq Safety Score of": "dengan Skor Keamanan Nerq sebesar",
        "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "Memenuhi ambang batas kepercayaan Nerq dengan sinyal kuat di keamanan, pemeliharaan, dan adopsi komunitas",
        "It has moderate trust signals but shows some areas of concern": "Memiliki sinyal kepercayaan sedang tetapi menunjukkan beberapa area perhatian",
        "It has below-average trust signals with significant gaps": "Memiliki sinyal kepercayaan di bawah rata-rata dengan celah signifikan",
        "review the full report below for specific considerations": "tinjau laporan lengkap di bawah untuk pertimbangan spesifik",
        "This score is based on automated analysis of security, maintenance, community, and quality signals.": "Skor ini berdasarkan analisis otomatis sinyal keamanan, pemeliharaan, komunitas, dan kualitas.",
        "You can also check the trust score via API:": "Anda juga dapat memeriksa skor kepercayaan melalui API:",
        "As a development package": "Sebagai paket pengembangan",
        "does not directly collect end-user personal data": "tidak secara langsung mengumpulkan data pribadi pengguna akhir",
        "However, applications built with it may collect data depending on implementation": "Namun, aplikasi yang dibangun dengannya mungkin mengumpulkan data tergantung implementasi",
        "Review the package's dependencies for potential supply chain risks": "Tinjau dependensi paket untuk potensi risiko rantai pasokan",
        "License information not available": "Informasi lisensi tidak tersedia",
        "Open-source packages allow independent security review of the source code": "Paket open-source memungkinkan tinjauan keamanan independen terhadap kode sumber",
        "to check for vulnerabilities": "untuk memeriksa kerentanan",
        "Review the": "Tinjau",
        "GitHub repository for recent commits": "repositori GitHub untuk commit terbaru",
        "dependency vulnerabilities, malicious packages, typosquatting": "kerentanan dependensi, paket berbahaya, typosquatting",
        "Run your package manager's audit command": "Jalankan perintah audit dari package manager Anda",
        "to check for known vulnerabilities in your dependency tree": "untuk memeriksa kerentanan yang diketahui di pohon dependensi Anda",
        "This meets the recommended security threshold for production use": "Ini memenuhi ambang batas keamanan yang direkomendasikan untuk penggunaan produksi",
        "Nerq monitors this entity against NVD, OSV.dev, and registry-specific vulnerability databases": "Nerq memantau entitas ini terhadap NVD, OSV.dev, dan database kerentanan khusus registry",
        "for ongoing security assessment": "untuk penilaian keamanan berkelanjutan",
        "Yes, it is safe to use.": "Ya, aman digunakan.",
        "Use with some caution.": "Gunakan dengan hati-hati.",
        "Exercise caution.": "Berhati-hatilah.",
        "Significant trust concerns.": "Masalah kepercayaan yang signifikan.",
        "maintained by": "dipelihara oleh",
        "is computed from": "dihitung dari",
        "The score reflects": "Skor ini mencerminkan",
        "independent dimensions": "dimensi independen",
        "Each dimension is weighted equally to produce the composite trust score": "Setiap dimensi diberi bobot yang sama untuk menghasilkan skor kepercayaan komposit",
        "No reviews yet.": "Belum ada ulasan.",
        "Be the first to review": "Jadilah yang pertama mengulas",
        "Write a review": "Tulis ulasan",
        "Higher-rated": "Berperingkat lebih tinggi",
        "you may want to consider:": "yang mungkin ingin Anda pertimbangkan:",
        "under assessment": "sedang dinilai",
        # Health disclaimers
        "Important Notice:": "Pemberitahuan Penting:",
        "educational and informational purposes only": "hanya untuk tujuan edukasi dan informasi",
        "does not constitute medical advice": "bukan merupakan saran medis",
        "Consult a qualified healthcare professional": "Konsultasikan dengan tenaga kesehatan profesional",
        "Full health disclaimer": "Disclaimer kesehatan lengkap",
        "Full disclaimer": "Disclaimer lengkap",
    },
    "cs": {
        "It is ": "Je ",
        "Is NordVPN safe": "Je NordVPN bezpečný",
        "What is NordVPN": "Co je NordVPN",
        "Does NordVPN log my data": "Zaznamenává NordVPN moje data",
        "What are the best alternatives to NordVPN": "Jaké jsou nejlepší alternativy k NordVPN",
        "NordVPN vs alternatives: which is safer": "NordVPN vs alternativy: co je bezpečnější",
        "trust score?": "skóre důvěry?",
        "Scores update as new data becomes available": "Skóre se aktualizují, jakmile jsou k dispozici nová data",
        "In the vpn category": "V kategorii VPN",
        "full safety report for detailed privacy analysis": "úplnou bezpečnostní zprávu pro podrobnou analýzu soukromí",
        "jurisdiction databases, independent audit reports, protocol analysis, and incident history": "jurisdikční databáze, nezávislé auditní zprávy, analýza protokolů a historie incidentů",
        "has undergone third-party security audits verifying its infrastructure and no-logs claims": "prošel bezpečnostními audity třetích stran ověřujícími jeho infrastrukturu a tvrzení o neuchovávání logů",
        "widely used VPN service": "široce používaná služba VPN",
        "multiple public sources including package registries, GitHub, NVD, OSV.dev, and OpenSSF Scorecard": "více veřejných zdrojů včetně registrů balíčků, GitHubu, NVD, OSV.dev a OpenSSF Scorecard",
        "What does a Nerq Trust Score": "Co znamená Nerq Trust Score",
        "Are these safest": "Jsou tyto nejbezpečnější",
        "How are safest": "Jak jsou nejbezpečnější",
        "The #1 safest": "Nejbezpečnější #1",
        "The #1": "#1",
        "According to Nerq": "Podle Nerq",
        "How are": "Jak jsou",
        "What are the best": "Jaké jsou nejlepší",
        "Logging policy": "Zásady protokolování",
        "Safety Guide": "Bezpečnostní průvodce",
        "passes trust threshold": "splňuje práh důvěry",
        "Recommended for use": "Doporučeno k použití",
        "This score is based on automated analysis of security, maintenance, community, and quality signals": "Toto skóre je založeno na automatizované analýze signálů bezpečnosti, údržby, komunity a kvality",
        "According to independent audit reports": "Podle nezávislých auditních zpráv",
        "No known data breaches associated with this service": "Žádné známé úniky dat spojené s touto službou",
        "This is a strong positive signal": "To je silný pozitivní signál",
        "logging policy": "zásady protokolování",
        "Full analysis": "Úplná analýza",
        "Server infrastructure": "Serverová infrastruktura",
        "It is recommended": "Je doporučeno",
        "most VPN providers have not been independently audited": "většina poskytovatelů VPN nebyla nezávisle auditována",
        "Nerq analyzes over": "Nerq analyzuje přes",
        "is based in": "má sídlo v",
        "outside all Eyes surveillance alliances": "mimo všechny dohledové aliance Eyes",
        "a privacy advantage": "výhoda pro soukromí",
        "has been independently audited to verify its privacy claims": "byl nezávisle auditován k ověření svých tvrzení o soukromí",
        "Serving": "Obsluhuje",
        "Related Safety Rankings": "Související bezpečnostní žebříčky",
        "Complete Your Privacy Setup": "Dokončete nastavení soukromí",
        "Browse Categories": "Procházet kategorie",
        "Safest VPNs": "Nejbezpečnější VPN",
        "Most Private Apps": "Nejsoukromější aplikace",
        "Recently Analyzed": "Nedávno analyzováno",
        "What are the best alternatives to": "Jaké jsou nejlepší alternativy k",
        "which is safer": "co je bezpečnější",
        "logging practices": "protokolování",
        "ownership transparency": "transparentnost vlastnictví",
        "Popular in": "Populární v",
        "Popularity": "Popularita",
        "Not Yet Analyzed": "Zatím neanalyzováno",
        # ── Vertical-specific strings ──
        "Privacy Assessment": "Hodnocení soukromí",
        "Breach History": "Historie úniků",
        "Encryption": "Šifrování",
        "Build Your Security Stack": "Sestavte si bezpečnostní sadu",
        "Best VPNs": "Nejlepší VPN",
        "Best Password Managers": "Nejlepší správci hesel",
        "Best Antivirus": "Nejlepší antivirus",
        "Security Assessment": "Hodnocení bezpečnosti",
        "Security & Compliance": "Bezpečnost a soulad",
        "Combine these tools for comprehensive protection:": "Kombinujte tyto nástroje pro komplexní ochranu:",
        # Title / H1
        "Independent Trust & Security Analysis": "Nezávislá analýza důvěryhodnosti a bezpečnosti",
        "Independent Trust &amp; Security Analysis": "Nezávislá analýza důvěryhodnosti a bezpečnosti",
        # Verdicts
        "Yes, {name} is safe to use.": "Ano, {name} je bezpečný k použití.",
        "Use {name} with some caution.": "Používejte {name} s opatrností.",
        "Exercise caution with {name}.": "Buďte opatrní s {name}.",
        "{name} has significant trust concerns.": "{name} má významné problémy s důvěryhodností.",
        "Passes Nerq Verified threshold": "Splňuje ověřený práh Nerq",
        "Below Nerq Verified threshold": "Pod ověřeným prahem Nerq",
        "Significant trust gaps detected": "Zjištěny významné mezery v důvěryhodnosti",
        # Section headings
        "Trust Score Breakdown": "Rozpis skóre důvěryhodnosti",
        "Safety Score Breakdown": "Rozpis bezpečnostního skóre",
        "Key Findings": "Hlavní zjištění",
        "Key Safety Findings": "Hlavní bezpečnostní zjištění",
        "Detailed Score Analysis": "Podrobná analýza skóre",
        "Frequently Asked Questions": "Často kladené otázky",
        "Safer Alternatives": "Bezpečnější alternativy",
        "Popular Alternatives": "Populární alternativy",
        "Community Reviews": "Komunitní hodnocení",
        "Regulatory Compliance": "Regulační shoda",
        "How we calculated this score": "Jak jsme vypočítali toto skóre",
        "What We Know About": "Co víme o",
        # Safety Guide
        "Safety Guide:": "Bezpečnostní průvodce:",
        "What is": "Co je",
        "How to Verify Safety": "Jak ověřit bezpečnost",
        "Key Safety Concerns for": "Hlavní bezpečnostní problémy pro",
        "Trust Assessment": "Hodnocení důvěryhodnosti",
        "Key Takeaways": "Hlavní závěry",
        "Recommended for use — passes trust threshold.": "Doporučeno k použití — splňuje práh důvěryhodnosti.",
        "Review carefully before use — below trust threshold.": "Pečlivě zkontrolujte před použitím — pod prahem důvěryhodnosti.",
        "Always verify independently using the": "Vždy nezávisle ověřte pomocí",
        "When evaluating any": "Při hodnocení jakéhokoli",
        "watch for:": "sledujte:",
        # Cross-product
        "Across Platforms": "Na dalších platformách",
        "across platforms": "na dalších platformách",
        "Same developer/company in other registries:": "Stejný vývojář/společnost v jiných registrech:",
        # King sections
        "What data does": "Jaká data shromažďuje",
        "collect?": "shromažďovat?",
        "Is": "Je",
        "secure?": "bezpečný?",
        "Full analysis:": "Úplná analýza:",
        "Privacy Report": "Zpráva o soukromí",
        "Privacy review": "Recenze soukromí",
        "Security Report": "Bezpečnostní zpráva",
        # Dimensions
        "Security": "Bezpečnost",
        "Privacy": "Soukromí",
        "Reliability": "Spolehlivost",
        "Transparency": "Transparentnost",
        "Maintenance": "Údržba",
        "Overall Trust": "Celková důvěryhodnost",
        "Composite trust score": "Souhrnné skóre důvěryhodnosti",
        "across all available signals": "ze všech dostupných signálů",
        # Methodology
        "Nerq analyzes over 7.5 million entities across 26 registries": "Nerq analyzuje více než 7,5 milionu entit ve 26 registrech",
        "using the same methodology, enabling direct cross-entity comparison": "pomocí stejné metodologie, což umožňuje přímé srovnání mezi entitami",
        "Scores are updated continuously as new data becomes available": "Skóre jsou průběžně aktualizována, jakmile jsou k dispozici nová data",
        "This page was last reviewed on": "Tato stránka byla naposledy zkontrolována",
        "Data version": "Verze dat",
        "Full methodology documentation": "Kompletní dokumentace metodologie",
        "Machine-readable data (JSON API)": "Strojově čitelná data (JSON API)",
        "Machine-readable data (JSON)": "Strojově čitelná data (JSON)",
        # Meta / small text
        "Last analyzed:": "Naposledy analyzováno:",
        "Last updated": "Naposledy aktualizováno",
        "Updated daily": "Aktualizováno denně",
        "Independent. Data-driven.": "Nezávislé. Založené na datech.",
        "verified": "ověřeno",
        "Data sourced from": "Data pocházejí z",
        "Based on": "Založeno na",
        "dimensions": "dimenzích",
        "independent data dimensions": "nezávislých datových dimenzích",
        "strong": "silný",
        "moderate": "střední",
        "weak": "slabý",
        "actively maintained": "aktivně udržováno",
        "moderately maintained": "středně udržováno",
        "low maintenance activity": "nízká aktivita údržby",
        "well-documented": "dobře zdokumentováno",
        "partial documentation": "částečná dokumentace",
        "limited documentation": "omezená dokumentace",
        "community adoption": "přijetí komunitou",
        "stars on": "hvězdiček na",
        # Cross-links
        "Safety": "Bezpečnost",
        "Legit?": "Legitimní?",
        "Scam?": "Podvod?",
        "Review": "Recenze",
        "Alternatives": "Alternativy",
        "Compare": "Porovnat",
        "Best in Category": "Nejlepší v kategorii",
        "Who Owns?": "Kdo vlastní?",
        "What Is?": "Co je?",
        "Sells Data?": "Prodává data?",
        "Hacked?": "Hacknutý?",
        "Safe for Kids?": "Bezpečný pro děti?",
        "Pros &amp; Cons": "Výhody a nevýhody",
        # FAQ answers
        "Nerq Verified — meets the 70+ trust threshold.": "Ověřeno Nerq — splňuje práh důvěryhodnosti 70+.",
        "Below the Nerq Verified threshold of 70.": "Pod prahem ověření Nerq, který je 70.",
        "Has not yet reached the Nerq Verified threshold of 70.": "Dosud nedosáhl prahu ověření Nerq, který je 70.",
        "Strongest signal:": "Nejsilnější signál:",
        "Score based on": "Skóre založeno na",
        "security": "bezpečnost",
        "maintenance": "údržba",
        "popularity": "popularita",
        "documentation": "dokumentace",
        "compliance": "shoda",
        # Verdict box
        "Safe": "Bezpečný",
        "Use Caution": "Opatrnost",
        "Avoid": "Vyhnout se",
        # Long text patterns
        "is a Node.js package": "je balíček Node.js",
        "is a Python package": "je balíček Pythonu",
        "is a Rust crate": "je Rust crate",
        "is a Chrome extension": "je rozšíření pro Chrome",
        "is a Firefox extension": "je rozšíření pro Firefox",
        "is a VS Code extension": "je rozšíření pro VS Code",
        "is a WordPress plugin": "je plugin pro WordPress",
        "is a iOS app": "je aplikace pro iOS",
        "is a Android app": "je aplikace pro Android",
        "is a VPN service": "je služba VPN",
        "is a game": "je hra",
        "is a website": "je webová stránka",
        "is a SaaS platform": "je platforma SaaS",
        "is a dietary supplement": "je doplněk stravy",
        "is a cosmetic ingredient": "je kosmetická přísada",
        "is a food": "je potravinová přísada",
        "is a travel destination": "je cestovní destinace",
        "is a nonprofit organization": "je nezisková organizace",
        "with a Nerq Trust Score of": "se skóre důvěryhodnosti Nerq",
        "with a Nerq Safety Score of": "s bezpečnostním skóre Nerq",
        "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "Splňuje práh důvěryhodnosti Nerq se silnými signály v oblasti bezpečnosti, údržby a přijetí komunitou",
        "It has moderate trust signals but shows some areas of concern": "Má střední signály důvěryhodnosti, ale vykazuje některé oblasti k pozornosti",
        "It has below-average trust signals with significant gaps": "Má podprůměrné signály důvěryhodnosti s významnými mezerami",
        "review the full report below for specific considerations": "přečtěte si úplnou zprávu níže pro konkrétní úvahy",
        "This score is based on automated analysis of security, maintenance, community, and quality signals.": "Toto skóre je založeno na automatizované analýze signálů bezpečnosti, údržby, komunity a kvality.",
        "You can also check the trust score via API:": "Skóre důvěryhodnosti můžete zkontrolovat také přes API:",
        "As a development package": "Jako vývojový balíček",
        "does not directly collect end-user personal data": "přímo neshromažďuje osobní údaje koncových uživatelů",
        "However, applications built with it may collect data depending on implementation": "Avšak aplikace s ním vytvořené mohou shromažďovat data v závislosti na implementaci",
        "Review the package's dependencies for potential supply chain risks": "Zkontrolujte závislosti balíčku pro potenciální rizika dodavatelského řetězce",
        "License information not available": "Informace o licenci nejsou k dispozici",
        "Open-source packages allow independent security review of the source code": "Open-source balíčky umožňují nezávislou bezpečnostní kontrolu zdrojového kódu",
        "to check for vulnerabilities": "pro kontrolu zranitelností",
        "Review the": "Zkontrolujte",
        "GitHub repository for recent commits": "GitHub repozitář pro nedávné commity",
        "dependency vulnerabilities, malicious packages, typosquatting": "zranitelnosti závislostí, škodlivé balíčky, typosquatting",
        "Run your package manager's audit command": "Spusťte příkaz auditu vašeho správce balíčků",
        "to check for known vulnerabilities in your dependency tree": "pro kontrolu známých zranitelností ve vašem stromu závislostí",
        "This meets the recommended security threshold for production use": "To splňuje doporučený bezpečnostní práh pro produkční použití",
        "Nerq monitors this entity against NVD, OSV.dev, and registry-specific vulnerability databases": "Nerq monitoruje tuto entitu oproti NVD, OSV.dev a databázím zranitelností specifickým pro registry",
        "for ongoing security assessment": "pro průběžné bezpečnostní hodnocení",
        "Yes, it is safe to use.": "Ano, je bezpečný k použití.",
        "Use with some caution.": "Používejte s opatrností.",
        "Exercise caution.": "Buďte opatrní.",
        "Significant trust concerns.": "Významné problémy s důvěryhodností.",
        "maintained by": "udržováno",
        "is computed from": "je vypočítáno z",
        "The score reflects": "Skóre odráží",
        "independent dimensions": "nezávislých dimenzí",
        "Each dimension is weighted equally to produce the composite trust score": "Každá dimenze má stejnou váhu pro vytvoření souhrnného skóre důvěryhodnosti",
        "No reviews yet.": "Zatím žádné recenze.",
        "Be the first to review": "Buďte první, kdo ohodnotí",
        "Write a review": "Napsat recenzi",
        "Higher-rated": "Lépe hodnocené",
        "you may want to consider:": "které byste mohli zvážit:",
        "under assessment": "v hodnocení",
        # Health disclaimers
        "Important Notice:": "Důležité upozornění:",
        "educational and informational purposes only": "pouze pro vzdělávací a informační účely",
        "does not constitute medical advice": "nepředstavuje lékařskou radu",
        "Consult a qualified healthcare professional": "Poraďte se s kvalifikovaným zdravotnickým pracovníkem",
        "Full health disclaimer": "Úplné zdravotní prohlášení",
        "Full disclaimer": "Úplné prohlášení",
    },
    "da": {
        "It is ": "Det er ",
        "Is NordVPN safe": "Er NordVPN sikker",
        "What is NordVPN": "Hvad er NordVPN",
        "Does NordVPN log my data": "Logger NordVPN mine data",
        "What are the best alternatives to NordVPN": "Bedste alternativer til NordVPN",
        "NordVPN vs alternatives: which is safer": "NordVPN vs alternativer: hvilken er sikrere",
        "trust score?": "tillidsscore?",
        "Scores update as new data becomes available": "Scorer opdateres når nye data bliver tilgængelige",
        "In the vpn category": "I VPN-kategorien",
        "full safety report for detailed privacy analysis": "fuld sikkerhedsrapport for detaljeret privatlivsanalyse",
        "jurisdiction databases, independent audit reports, protocol analysis, and incident history": "jurisdiktionsdatabaser, uafhængige revisionsrapporter, protokolanalyse og hændelseshistorik",
        "has undergone third-party security audits verifying its infrastructure and no-logs claims": "har gennemgået tredjeparts sikkerhedsrevisioner der verificerer dets infrastruktur og no-logs-påstande",
        "widely used VPN service": "udbredt VPN-tjeneste",
        "multiple public sources including package registries, GitHub, NVD, OSV.dev, and OpenSSF Scorecard": "flere offentlige kilder herunder pakkeregistre, GitHub, NVD, OSV.dev og OpenSSF Scorecard",
        "What does a Nerq Trust Score": "Hvad betyder en Nerq Trust Score",
        "Are these safest": "Er disse de sikreste",
        "How are safest": "Hvordan er de sikreste",
        "The #1 safest": "Sikreste #1",
        "The #1": "Nr. 1",
        "According to Nerq": "Ifølge Nerq",
        "How are": "Hvordan",
        "What are the best": "Hvad er de bedste",
        "Logging policy": "Logningspolitik",
        "Safety Guide": "Sikkerhedsguide",
        "passes trust threshold": "opfylder tillidstærsklen",
        "Recommended for use": "Anbefales til brug",
        "This score is based on automated analysis of security, maintenance, community, and quality signals": "Denne score er baseret på automatiseret analyse af sikkerheds-, vedligeholdelses-, fællesskabs- og kvalitetssignaler",
        "According to independent audit reports": "Ifølge uafhængige revisionsrapporter",
        "No known data breaches associated with this service": "Ingen kendte databrud forbundet med denne tjeneste",
        "This is a strong positive signal": "Dette er et stærkt positivt signal",
        "logging policy": "logningspolitik",
        "Full analysis": "Fuld analyse",
        "Server infrastructure": "Serverinfrastruktur",
        "It is recommended": "Det anbefales",
        "most VPN providers have not been independently audited": "de fleste VPN-udbydere er ikke blevet uafhængigt revideret",
        "Nerq analyzes over": "Nerq analyserer over",
        "is based in": "har hovedkontor i",
        "outside all Eyes surveillance alliances": "uden for alle Eyes-overvågningsalliancer",
        "a privacy advantage": "en privatlivsfordel",
        "has been independently audited to verify its privacy claims": "er blevet uafhængigt revideret for at verificere sine privatlivskrav",
        "Serving": "Betjener",
        "Related Safety Rankings": "Relaterede sikkerhedsranglister",
        "Complete Your Privacy Setup": "Fuldfør dine privatlivsindstillinger",
        "Browse Categories": "Gennemse kategorier",
        "Safest VPNs": "Sikreste VPN'er",
        "Most Private Apps": "Mest private apps",
        "Recently Analyzed": "Senest analyseret",
        "What are the best alternatives to": "Hvad er de bedste alternativer til",
        "which is safer": "hvilken er sikrere",
        "logging practices": "logningspraksis",
        "ownership transparency": "ejerskabstransparens",
        "Popular in": "Populær i",
        "Popularity": "Popularitet",
        "Not Yet Analyzed": "Endnu ikke analyseret",
        # ── Vertical-specific strings ──
        "Privacy Assessment": "Privatlivsvurdering",
        "Breach History": "Brudhistorik",
        "Encryption": "Kryptering",
        "Build Your Security Stack": "Byg din sikkerhedspakke",
        "Best VPNs": "Bedste VPN'er",
        "Best Password Managers": "Bedste adgangskodeadministratorer",
        "Best Antivirus": "Bedste antivirus",
        "Security Assessment": "Sikkerhedsvurdering",
        "Security & Compliance": "Sikkerhed og overholdelse",
        "Combine these tools for comprehensive protection:": "Kombiner disse værktøjer for omfattende beskyttelse:",
        # Title / H1
        "Independent Trust & Security Analysis": "Uafhængig tillids- og sikkerhedsanalyse",
        "Independent Trust &amp; Security Analysis": "Uafhængig tillids- og sikkerhedsanalyse",
        # Verdicts
        "Yes, {name} is safe to use.": "Ja, {name} er sikker at bruge.",
        "Use {name} with some caution.": "Brug {name} med forsigtighed.",
        "Exercise caution with {name}.": "Vær forsigtig med {name}.",
        "{name} has significant trust concerns.": "{name} har betydelige tillidsproblemer.",
        "Passes Nerq Verified threshold": "Opfylder Nerqs verificerede tærskel",
        "Below Nerq Verified threshold": "Under Nerqs verificerede tærskel",
        "Significant trust gaps detected": "Betydelige tillidshuller opdaget",
        # Section headings
        "Trust Score Breakdown": "Tillidsscore detaljer",
        "Safety Score Breakdown": "Sikkerhedsscore detaljer",
        "Key Findings": "Vigtigste resultater",
        "Key Safety Findings": "Vigtigste sikkerhedsresultater",
        "Detailed Score Analysis": "Detaljeret scoreanalyse",
        "Frequently Asked Questions": "Ofte stillede spørgsmål",
        "Safer Alternatives": "Sikrere alternativer",
        "Popular Alternatives": "Populære alternativer",
        "Community Reviews": "Fællesskabsanmeldelser",
        "Regulatory Compliance": "Lovgivningsmæssig overholdelse",
        "How we calculated this score": "Sådan beregnede vi denne score",
        "What We Know About": "Hvad vi ved om",
        # Safety Guide
        "Safety Guide:": "Sikkerhedsguide:",
        "What is": "Hvad er",
        "How to Verify Safety": "Sådan verificerer du sikkerheden",
        "Key Safety Concerns for": "Vigtigste sikkerhedsproblemer for",
        "Trust Assessment": "Tillidsvurdering",
        "Key Takeaways": "Vigtigste pointer",
        "Recommended for use — passes trust threshold.": "Anbefalet til brug — opfylder tillidstærskel.",
        "Review carefully before use — below trust threshold.": "Gennemgå omhyggeligt før brug — under tillidstærskel.",
        "Always verify independently using the": "Verificer altid uafhængigt ved hjælp af",
        "When evaluating any": "Når du vurderer en",
        "watch for:": "hold øje med:",
        # Cross-product
        "Across Platforms": "På andre platforme",
        "across platforms": "på andre platforme",
        "Same developer/company in other registries:": "Samme udvikler/virksomhed i andre registre:",
        # King sections
        "What data does": "Hvilke data indsamler",
        "collect?": "indsamle?",
        "Is": "Er",
        "secure?": "sikker?",
        "Full analysis:": "Fuld analyse:",
        "Privacy Report": "Privatlivsrapport",
        "Privacy review": "Privatlivsanmeldelse",
        "Security Report": "Sikkerhedsrapport",
        # Dimensions
        "Security": "Sikkerhed",
        "Privacy": "Privatliv",
        "Reliability": "Pålidelighed",
        "Transparency": "Gennemsigtighed",
        "Maintenance": "Vedligeholdelse",
        "Overall Trust": "Samlet tillid",
        "Composite trust score": "Samlet tillidsscore",
        "across all available signals": "på tværs af alle tilgængelige signaler",
        # Methodology
        "Nerq analyzes over 7.5 million entities across 26 registries": "Nerq analyserer over 7,5 millioner enheder i 26 registre",
        "using the same methodology, enabling direct cross-entity comparison": "med samme metodik, hvilket muliggør direkte sammenligning mellem enheder",
        "Scores are updated continuously as new data becomes available": "Scorer opdateres løbende, efterhånden som nye data bliver tilgængelige",
        "This page was last reviewed on": "Denne side blev sidst gennemgået den",
        "Data version": "Dataversion",
        "Full methodology documentation": "Fuld metodikdokumentation",
        "Machine-readable data (JSON API)": "Maskinlæsbare data (JSON API)",
        "Machine-readable data (JSON)": "Maskinlæsbare data (JSON)",
        # Meta / small text
        "Last analyzed:": "Sidst analyseret:",
        "Last updated": "Sidst opdateret",
        "Updated daily": "Opdateres dagligt",
        "Independent. Data-driven.": "Uafhængig. Datadriven.",
        "verified": "verificeret",
        "Data sourced from": "Data hentet fra",
        "Based on": "Baseret på",
        "dimensions": "dimensioner",
        "independent data dimensions": "uafhængige datadimensioner",
        "strong": "stærk",
        "moderate": "moderat",
        "weak": "svag",
        "actively maintained": "aktivt vedligeholdt",
        "moderately maintained": "moderat vedligeholdt",
        "low maintenance activity": "lav vedligeholdelsesaktivitet",
        "well-documented": "veldokumenteret",
        "partial documentation": "delvis dokumentation",
        "limited documentation": "begrænset dokumentation",
        "community adoption": "fællesskabsadoption",
        "stars on": "stjerner på",
        # Cross-links
        "Safety": "Sikkerhed",
        "Legit?": "Legitim?",
        "Scam?": "Svindel?",
        "Review": "Anmeldelse",
        "Alternatives": "Alternativer",
        "Compare": "Sammenlign",
        "Best in Category": "Bedst i kategorien",
        "Who Owns?": "Hvem ejer?",
        "What Is?": "Hvad er?",
        "Sells Data?": "Sælger data?",
        "Hacked?": "Hacket?",
        "Safe for Kids?": "Sikkert for børn?",
        "Pros &amp; Cons": "Fordele og ulemper",
        # FAQ answers
        "Nerq Verified — meets the 70+ trust threshold.": "Nerq-verificeret — opfylder tillidstærskel på 70+.",
        "Below the Nerq Verified threshold of 70.": "Under Nerqs verificerede tærskel på 70.",
        "Has not yet reached the Nerq Verified threshold of 70.": "Har endnu ikke nået Nerqs verificerede tærskel på 70.",
        "Strongest signal:": "Stærkeste signal:",
        "Score based on": "Score baseret på",
        "security": "sikkerhed",
        "maintenance": "vedligeholdelse",
        "popularity": "popularitet",
        "documentation": "dokumentation",
        "compliance": "overholdelse",
        # Verdict box
        "Safe": "Sikker",
        "Use Caution": "Forsigtighed",
        "Avoid": "Undgå",
        # Long text patterns
        "is a Node.js package": "er en Node.js-pakke",
        "is a Python package": "er en Python-pakke",
        "is a Rust crate": "er en Rust-crate",
        "is a Chrome extension": "er en Chrome-udvidelse",
        "is a Firefox extension": "er en Firefox-udvidelse",
        "is a VS Code extension": "er en VS Code-udvidelse",
        "is a WordPress plugin": "er et WordPress-plugin",
        "is a iOS app": "er en iOS-app",
        "is a Android app": "er en Android-app",
        "is a VPN service": "er en VPN-tjeneste",
        "is a game": "er et spil",
        "is a website": "er et websted",
        "is a SaaS platform": "er en SaaS-platform",
        "is a dietary supplement": "er et kosttilskud",
        "is a cosmetic ingredient": "er et kosmetisk ingrediens",
        "is a food": "er et fødevaretilsætningsstof",
        "is a travel destination": "er en rejsedestination",
        "is a nonprofit organization": "er en nonprofitorganisation",
        "with a Nerq Trust Score of": "med en Nerq Tillidsscore på",
        "with a Nerq Safety Score of": "med en Nerq Sikkerhedsscore på",
        "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "Opfylder Nerqs tillidstærskel med stærke signaler inden for sikkerhed, vedligeholdelse og fællesskabsadoption",
        "It has moderate trust signals but shows some areas of concern": "Har moderate tillidssignaler, men viser nogle bekymrende områder",
        "It has below-average trust signals with significant gaps": "Har under gennemsnitlige tillidssignaler med betydelige huller",
        "review the full report below for specific considerations": "gennemgå den fulde rapport nedenfor for specifikke overvejelser",
        "This score is based on automated analysis of security, maintenance, community, and quality signals.": "Denne score er baseret på automatiseret analyse af sikkerheds-, vedligeholdelses-, fællesskabs- og kvalitetssignaler.",
        "You can also check the trust score via API:": "Du kan også tjekke tillidsscoren via API:",
        "As a development package": "Som en udviklingspakke",
        "does not directly collect end-user personal data": "indsamler ikke direkte slutbrugerens personlige data",
        "However, applications built with it may collect data depending on implementation": "Men applikationer bygget med den kan indsamle data afhængigt af implementering",
        "Review the package's dependencies for potential supply chain risks": "Gennemgå pakkens afhængigheder for potentielle forsyningskæderisici",
        "License information not available": "Licensoplysninger ikke tilgængelige",
        "Open-source packages allow independent security review of the source code": "Open source-pakker muliggør uafhængig sikkerhedsgennemgang af kildekoden",
        "to check for vulnerabilities": "for at kontrollere for sårbarheder",
        "Review the": "Gennemgå",
        "GitHub repository for recent commits": "GitHub-repositorium for seneste commits",
        "dependency vulnerabilities, malicious packages, typosquatting": "afhængighedssårbarheder, ondsindede pakker, typosquatting",
        "Run your package manager's audit command": "Kør din pakkehåndterers auditkommando",
        "to check for known vulnerabilities in your dependency tree": "for at kontrollere for kendte sårbarheder i dit afhængighedstræ",
        "This meets the recommended security threshold for production use": "Dette opfylder den anbefalede sikkerhedstærskel til produktionsbrug",
        "Nerq monitors this entity against NVD, OSV.dev, and registry-specific vulnerability databases": "Nerq overvåger denne enhed mod NVD, OSV.dev og registrespecifikke sårbarhedsdatabaser",
        "for ongoing security assessment": "til løbende sikkerhedsvurdering",
        "Yes, it is safe to use.": "Ja, det er sikkert at bruge.",
        "Use with some caution.": "Brug med forsigtighed.",
        "Exercise caution.": "Vær forsigtig.",
        "Significant trust concerns.": "Betydelige tillidsproblemer.",
        "maintained by": "vedligeholdt af",
        "is computed from": "beregnes ud fra",
        "The score reflects": "Scoren afspejler",
        "independent dimensions": "uafhængige dimensioner",
        "Each dimension is weighted equally to produce the composite trust score": "Hver dimension vægtes ens for at producere den samlede tillidsscore",
        "No reviews yet.": "Ingen anmeldelser endnu.",
        "Be the first to review": "Vær den første til at anmelde",
        "Write a review": "Skriv en anmeldelse",
        "Higher-rated": "Højere rangerede",
        "you may want to consider:": "som du måske vil overveje:",
        "under assessment": "under vurdering",
        # Health disclaimers
        "Important Notice:": "Vigtig meddelelse:",
        "educational and informational purposes only": "kun til uddannelses- og informationsformål",
        "does not constitute medical advice": "udgør ikke medicinsk rådgivning",
        "Consult a qualified healthcare professional": "Konsultér en kvalificeret sundhedsperson",
        "Full health disclaimer": "Fuld sundhedsansvarsfraskrivelse",
        "Full disclaimer": "Fuld ansvarsfraskrivelse",
    },
    "no": {
        "has a Nerq Trust Score of": "har en Nerq-tillitspoeng på",
        "known vulnerabilities": "kjente sårbarheter",
        "License:": "Lisens:",
        "Not specified": "Ikke spesifisert",
        "Independent security analysis of": "Uavhengig sikkerhetsanalyse av",
        "trust signals, vulnerabilities, compliance, and safer alternatives": "tillitssignaler, sårbarheter, samsvar og tryggere alternativer",
        "Independent Trust &amp; Security Analysis": "Uavhengig tillits- og sikkerhetsanalyse",
        # /best/ page verdict + summary + methodology
        "based on Nerq's independent analysis of": "basert på Nerqs uavhengige analyse av",
        "across 5 trust dimensions": "over 5 tillitsdimensjoner",
        "According to Nerq's analysis, the top 5": "Ifølge Nerqs analyse er de 5 beste",
        "by trust score are": "etter tillitspoeng",
        "Scores are based on 5 independent trust dimensions including security, maintenance, and community adoption": "Poengene er basert på 5 uavhengige tillitsdimensjoner inkludert sikkerhet, vedlikehold og fellesskapsadopsjon",
        "These safest vpns are ranked by Nerq Trust Score, which evaluates security, maintenance, community adoption, and transparency across multiple data points": "Disse sikreste VPN-ene er rangert etter Nerq-tillitspoeng, som evaluerer sikkerhet, vedlikehold, fellesskapsadopsjon og åpenhet over flere datapunkter",
        "Only entities with a trust score of 30 or above are included": "Kun enheter med en tillitspoeng på 30 eller høyere er inkludert",
        "Scores are updated continuously as new data becomes available": "Poeng oppdateres fortløpende etter hvert som nye data blir tilgjengelige",
        "ranked by Nerq Trust Score. Independent security and trust analysis.": "rangert etter Nerq-tillitspoeng. Uavhengig sikkerhets- og tillitsanalyse.",
        "Independent security and trust analysis": "Uavhengig sikkerhets- og tillitsanalyse",
        "It is ": "Det er ",
        "Is NordVPN safe": "Er NordVPN trygg",
        "What is NordVPN": "Hva er NordVPN",
        "Does NordVPN log my data": "Logger NordVPN dataene mine",
        "What are the best alternatives to NordVPN": "Beste alternativer til NordVPN",
        "NordVPN vs alternatives: which is safer": "NordVPN mot alternativer: hvilket er tryggere",
        "trust score?": "tillitspoeng?",
        "Scores update as new data becomes available": "Poeng oppdateres når nye data blir tilgjengelige",
        "In the vpn category": "I VPN-kategorien",
        "full safety report for detailed privacy analysis": "full sikkerhetsrapport for detaljert personvernanalyse",
        "jurisdiction databases, independent audit reports, protocol analysis, and incident history": "jurisdiksjonsdatabaser, uavhengige revisjonsrapporter, protokollanalyse og hendelseshistorikk",
        "has undergone third-party security audits verifying its infrastructure and no-logs claims": "har gjennomgått tredjeparts sikkerhetsrevisjoner som verifiserer infrastrukturen og no-logs-påstandene",
        "widely used VPN service": "mye brukt VPN-tjeneste",
        "multiple public sources including package registries, GitHub, NVD, OSV.dev, and OpenSSF Scorecard": "flere offentlige kilder inkludert pakkeregistre, GitHub, NVD, OSV.dev og OpenSSF Scorecard",
        "What does a Nerq Trust Score": "Hva betyr et Nerq-tillitspoeng",
        "Are these safest": "Er disse de tryggeste",
        "How are safest": "Hvordan er de tryggeste",
        "The #1 safest": "Tryggeste #1",
        "The #1": "Nr. 1",
        "According to Nerq": "Ifølge Nerq",
        "How are": "Hvordan",
        "What are the best": "Hva er de beste",
        "Logging policy": "Loggingspolicy",
        "Safety Guide": "Sikkerhetsguide",
        "passes trust threshold": "oppfyller tillitsterskel",
        "Recommended for use": "Anbefalt for bruk",
        "This score is based on automated analysis of security, maintenance, community, and quality signals": "Denne poengsummen er basert på automatisert analyse av sikkerhets-, vedlikeholds-, fellesskaps- og kvalitetssignaler",
        "According to independent audit reports": "Ifølge uavhengige revisjonsrapporter",
        "No known data breaches associated with this service": "Ingen kjente datainnbrudd knyttet til denne tjenesten",
        "This is a strong positive signal": "Dette er et sterkt positivt signal",
        "logging policy": "loggingspolicy",
        "Full analysis": "Full analyse",
        "Server infrastructure": "Serverinfrastruktur",
        "It is recommended": "Det anbefales",
        "most VPN providers have not been independently audited": "de fleste VPN-leverandører har ikke blitt uavhengig revidert",
        "Nerq analyzes over": "Nerq analyserer over",
        "is based in": "har hovedkontor i",
        "outside all Eyes surveillance alliances": "utenfor alle Eyes-overvåkningsallianser",
        "a privacy advantage": "en personvernfordel",
        "has been independently audited to verify its privacy claims": "har blitt uavhengig revidert for å verifisere sine personvernkrav",
        "Serving": "Betjener",
        "Related Safety Rankings": "Relaterte sikkerhetslister",
        "Complete Your Privacy Setup": "Fullfør personvernoppsettet ditt",
        "Browse Categories": "Bla gjennom kategorier",
        "Safest VPNs": "Tryggeste VPN-er",
        "Most Private Apps": "Mest private apper",
        "Recently Analyzed": "Nylig analysert",
        "What are the best alternatives to": "Hva er de beste alternativene til",
        "which is safer": "hvilket er tryggere",
        "logging practices": "loggingspraksis",
        "ownership transparency": "eierskapstransparens",
        "Popular in": "Populær i",
        "Popularity": "Popularitet",
        "Not Yet Analyzed": "Ennå ikke analysert",
        # ── Vertical-specific strings ──
        "Privacy Assessment": "Personvernvurdering",
        "Breach History": "Innbruddshistorikk",
        "Encryption": "Kryptering",
        "Build Your Security Stack": "Bygg sikkerhetspakken din",
        "Best VPNs": "Beste VPN-er",
        "Best Password Managers": "Beste passordbehandlere",
        "Best Antivirus": "Beste antivirus",
        "Security Assessment": "Sikkerhetsvurdering",
        "Security & Compliance": "Sikkerhet og samsvar",
        "Combine these tools for comprehensive protection:": "Kombiner disse verktøyene for omfattende beskyttelse:",
        # Title / H1
        "Independent Trust & Security Analysis": "Uavhengig tillits- og sikkerhetsanalyse",
        "Independent Trust &amp; Security Analysis": "Uavhengig tillits- og sikkerhetsanalyse",
        # Verdicts
        "Yes, {name} is safe to use.": "Ja, {name} er trygg å bruke.",
        "Use {name} with some caution.": "Bruk {name} med forsiktighet.",
        "Exercise caution with {name}.": "Vær forsiktig med {name}.",
        "{name} has significant trust concerns.": "{name} har betydelige tillitsproblemer.",
        "Passes Nerq Verified threshold": "Oppfyller Nerqs verifiserte terskel",
        "Below Nerq Verified threshold": "Under Nerqs verifiserte terskel",
        "Significant trust gaps detected": "Betydelige tillitshull oppdaget",
        # Section headings
        "Trust Score Breakdown": "Tillitspoeng detaljer",
        "Safety Score Breakdown": "Sikkerhetspoeng detaljer",
        "Key Findings": "Viktigste funn",
        "Key Safety Findings": "Viktigste sikkerhetsfunn",
        "Detailed Score Analysis": "Detaljert poenganalyse",
        "Frequently Asked Questions": "Ofte stilte spørsmål",
        "Safer Alternatives": "Tryggere alternativer",
        "Popular Alternatives": "Populære alternativer",
        "Community Reviews": "Fellesskapsanmeldelser",
        "Regulatory Compliance": "Regulatorisk samsvar",
        "How we calculated this score": "Slik beregnet vi denne poengsummen",
        "What We Know About": "Hva vi vet om",
        # Safety Guide
        "Safety Guide:": "Sikkerhetsguide:",
        "What is": "Hva er",
        "How to Verify Safety": "Slik verifiserer du sikkerheten",
        "Key Safety Concerns for": "Viktigste sikkerhetsproblemer for",
        "Trust Assessment": "Tillitsvurdering",
        "Key Takeaways": "Viktigste punkter",
        "Recommended for use — passes trust threshold.": "Anbefalt for bruk — oppfyller tillitsterskel.",
        "Review carefully before use — below trust threshold.": "Gjennomgå nøye før bruk — under tillitsterskel.",
        "Always verify independently using the": "Verifiser alltid uavhengig ved hjelp av",
        "When evaluating any": "Når du vurderer en",
        "watch for:": "se opp for:",
        # Cross-product
        "Across Platforms": "På tvers av plattformer",
        "across platforms": "på tvers av plattformer",
        "Same developer/company in other registries:": "Samme utvikler/selskap i andre registre:",
        # King sections
        "What data does": "Hvilke data samler",
        "collect?": "inn?",
        "Is": "Er",
        "secure?": "sikker?",
        "Full analysis:": "Full analyse:",
        "Privacy Report": "Personvernrapport",
        "Privacy review": "Personverngjennomgang",
        "Security Report": "Sikkerhetsrapport",
        # Dimensions
        "Security": "Sikkerhet",
        "Privacy": "Personvern",
        "Reliability": "Pålitelighet",
        "Transparency": "Åpenhet",
        "Maintenance": "Vedlikehold",
        "Overall Trust": "Samlet tillit",
        "Composite trust score": "Samlet tillitspoeng",
        "across all available signals": "på tvers av alle tilgjengelige signaler",
        # Methodology
        "Nerq analyzes over 7.5 million entities across 26 registries": "Nerq analyserer over 7,5 millioner enheter i 26 registre",
        "using the same methodology, enabling direct cross-entity comparison": "med samme metodikk, noe som muliggjør direkte sammenligning mellom enheter",
        "Scores are updated continuously as new data becomes available": "Poeng oppdateres fortløpende etter hvert som nye data blir tilgjengelige",
        "This page was last reviewed on": "Denne siden ble sist gjennomgått den",
        "Data version": "Dataversjon",
        "Full methodology documentation": "Full metodikkdokumentasjon",
        "Machine-readable data (JSON API)": "Maskinlesbare data (JSON API)",
        "Machine-readable data (JSON)": "Maskinlesbare data (JSON)",
        # Meta / small text
        "Last analyzed:": "Sist analysert:",
        "Last updated": "Sist oppdatert",
        "Updated daily": "Oppdateres daglig",
        "Independent. Data-driven.": "Uavhengig. Datadrevet.",
        "verified": "verifisert",
        "Data sourced from": "Data hentet fra",
        "Based on": "Basert på",
        "dimensions": "dimensjoner",
        "independent data dimensions": "uavhengige datadimensjoner",
        "strong": "sterk",
        "moderate": "moderat",
        "weak": "svak",
        "actively maintained": "aktivt vedlikeholdt",
        "moderately maintained": "moderat vedlikeholdt",
        "low maintenance activity": "lav vedlikeholdsaktivitet",
        "well-documented": "godt dokumentert",
        "partial documentation": "delvis dokumentasjon",
        "limited documentation": "begrenset dokumentasjon",
        "community adoption": "fellesskapsadopsjon",
        "stars on": "stjerner på",
        # Cross-links
        "Safety": "Sikkerhet",
        "Legit?": "Legitim?",
        "Scam?": "Svindel?",
        "Review": "Anmeldelse",
        "Alternatives": "Alternativer",
        "Compare": "Sammenlign",
        "Best in Category": "Best i kategorien",
        "Who Owns?": "Hvem eier?",
        "What Is?": "Hva er?",
        "Sells Data?": "Selger data?",
        "Hacked?": "Hacket?",
        "Safe for Kids?": "Trygt for barn?",
        "Pros &amp; Cons": "Fordeler og ulemper",
        # FAQ answers
        "Nerq Verified — meets the 70+ trust threshold.": "Nerq-verifisert — oppfyller tillitsterskel på 70+.",
        "Below the Nerq Verified threshold of 70.": "Under Nerqs verifiserte terskel på 70.",
        "Has not yet reached the Nerq Verified threshold of 70.": "Har ennå ikke nådd Nerqs verifiserte terskel på 70.",
        "Strongest signal:": "Sterkeste signal:",
        "Score based on": "Poeng basert på",
        "security": "sikkerhet",
        "maintenance": "vedlikehold",
        "popularity": "popularitet",
        "documentation": "dokumentasjon",
        "compliance": "samsvar",
        # Verdict box
        "Safe": "Trygg",
        "Use Caution": "Forsiktighet",
        "Avoid": "Unngå",
        # Long text patterns
        "is a Node.js package": "er en Node.js-pakke",
        "is a Python package": "er en Python-pakke",
        "is a Rust crate": "er en Rust-crate",
        "is a Chrome extension": "er en Chrome-utvidelse",
        "is a Firefox extension": "er en Firefox-utvidelse",
        "is a VS Code extension": "er en VS Code-utvidelse",
        "is a WordPress plugin": "er en WordPress-plugin",
        "is a iOS app": "er en iOS-app",
        "is a Android app": "er en Android-app",
        "is a VPN service": "er en VPN-tjeneste",
        "is a game": "er et spill",
        "is a website": "er et nettsted",
        "is a SaaS platform": "er en SaaS-plattform",
        "is a dietary supplement": "er et kosttilskudd",
        "is a cosmetic ingredient": "er en kosmetisk ingrediens",
        "is a food": "er et tilsetningsstoff",
        "is a travel destination": "er et reisemål",
        "is a nonprofit organization": "er en ideell organisasjon",
        "with a Nerq Trust Score of": "med et Nerq-tillitspoeng på",
        "with a Nerq Safety Score of": "med et Nerq-sikkerhetspoeng på",
        "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "Oppfyller Nerqs tillitsterskel med sterke signaler innen sikkerhet, vedlikehold og fellesskapsadopsjon",
        "It has moderate trust signals but shows some areas of concern": "Har moderate tillitssignaler, men viser noen bekymringsområder",
        "It has below-average trust signals with significant gaps": "Har tillitssignaler under gjennomsnittet med betydelige hull",
        "review the full report below for specific considerations": "gjennomgå den fullstendige rapporten nedenfor for spesifikke hensyn",
        "This score is based on automated analysis of security, maintenance, community, and quality signals.": "Denne poengsummen er basert på automatisert analyse av sikkerhets-, vedlikeholds-, fellesskaps- og kvalitetssignaler.",
        "You can also check the trust score via API:": "Du kan også sjekke tillitspoenget via API:",
        "As a development package": "Som en utviklingspakke",
        "does not directly collect end-user personal data": "samler ikke direkte inn sluttbrukerens personlige data",
        "However, applications built with it may collect data depending on implementation": "Imidlertid kan applikasjoner bygget med den samle inn data avhengig av implementering",
        "Review the package's dependencies for potential supply chain risks": "Gjennomgå pakkens avhengigheter for potensielle forsyningskjederisikoer",
        "License information not available": "Lisensinformasjon ikke tilgjengelig",
        "Open-source packages allow independent security review of the source code": "Åpen kildekode-pakker muliggjør uavhengig sikkerhetsgjennomgang av kildekoden",
        "to check for vulnerabilities": "for å sjekke for sårbarheter",
        "Review the": "Gjennomgå",
        "GitHub repository for recent commits": "GitHub-repositorium for nylige commits",
        "dependency vulnerabilities, malicious packages, typosquatting": "avhengighetssårbarheter, ondsinnede pakker, typosquatting",
        "Run your package manager's audit command": "Kjør pakkebehandlerens auditkommando",
        "to check for known vulnerabilities in your dependency tree": "for å sjekke for kjente sikkerhetssårbarheter i avhengighetstreet ditt",
        "This meets the recommended security threshold for production use": "Dette oppfyller den anbefalte sikkerhetsterskelen for produksjonsbruk",
        "Nerq monitors this entity against NVD, OSV.dev, and registry-specific vulnerability databases": "Nerq overvåker denne enheten mot NVD, OSV.dev og registerspesifikke sårbarhetsdatabaser",
        "for ongoing security assessment": "for løpende sikkerhetsvurdering",
        "Yes, it is safe to use.": "Ja, det er trygt å bruke.",
        "Use with some caution.": "Bruk med forsiktighet.",
        "Exercise caution.": "Vær forsiktig.",
        "Significant trust concerns.": "Betydelige tillitsproblemer.",
        "maintained by": "vedlikeholdt av",
        "is computed from": "beregnes fra",
        "The score reflects": "Poengsummen gjenspeiler",
        "independent dimensions": "uavhengige dimensjoner",
        "Each dimension is weighted equally to produce the composite trust score": "Hver dimensjon vektes likt for å produsere det samlede tillitspoenget",
        "No reviews yet.": "Ingen anmeldelser ennå.",
        "Be the first to review": "Vær den første til å anmelde",
        "Write a review": "Skriv en anmeldelse",
        "Higher-rated": "Høyere rangerte",
        "you may want to consider:": "som du kanskje vil vurdere:",
        "under assessment": "under vurdering",
        # Health disclaimers
        "Important Notice:": "Viktig merknad:",
        "educational and informational purposes only": "kun til utdannings- og informasjonsformål",
        "does not constitute medical advice": "utgjør ikke medisinsk rådgivning",
        "Consult a qualified healthcare professional": "Konsulter en kvalifisert helsepersonell",
        "Full health disclaimer": "Full helseansvarsfraskrivelse",
        "Full disclaimer": "Full ansvarsfraskrivelse",
    },
    "th": {
        "It is ": "มันเป็น ",
        "Is NordVPN safe": "NordVPN ปลอดภัยหรือไม่",
        "What is NordVPN": "NordVPN คืออะไร",
        "Does NordVPN log my data": "NordVPN บันทึกข้อมูลของฉันหรือไม่",
        "What are the best alternatives to NordVPN": "ทางเลือกที่ดีที่สุดสำหรับ NordVPN",
        "NordVPN vs alternatives: which is safer": "NordVPN กับทางเลือก: อันไหนปลอดภัยกว่า",
        "trust score?": "คะแนนความเชื่อถือ?",
        "Scores update as new data becomes available": "คะแนนอัปเดตเมื่อมีข้อมูลใหม่",
        "In the vpn category": "ในหมวด VPN",
        "full safety report for detailed privacy analysis": "รายงานความปลอดภัยฉบับเต็มสำหรับการวิเคราะห์ความเป็นส่วนตัวอย่างละเอียด",
        "jurisdiction databases, independent audit reports, protocol analysis, and incident history": "ฐานข้อมูลเขตอำน��จศาล รายงานการตรวจสอบอิสระ การวิเคราะห์โปรโตคอล และประวัติเหตุการณ์",
        "has undergone third-party security audits verifying its infrastructure and no-logs claims": "ผ่านการตรวจสอบความปลอดภัยจากบุคคลที่สามที่ยืนยันโครงสร้างพื้นฐานและการไม่บันทึกข้อมูล",
        "widely used VPN service": "บริการ VPN ที่ใช้กันอย่างแพร่หลาย",
        "multiple public sources including package registries, GitHub, NVD, OSV.dev, and OpenSSF Scorecard": "แหล��งข้อมูลสาธารณะหลายแห่งรวมถึง registry แพ็คเกจ, GitHub, NVD, OSV.dev และ OpenSSF Scorecard",
        "What does a Nerq Trust Score": "Nerq Trust Score หมายถึงอะไร",
        "Are these safest": "เหล่านี้ปลอดภัยที่สุดหรือไม่",
        "How are safest": "อันดับความปลอดภัยสูงสุดเป็นอย่างไร",
        "The #1 safest": "ปลอดภัยที่สุดอันดับ 1",
        "The #1": "อันดับ 1",
        "According to Nerq": "ตาม Nerq",
        "How are": "มีการจัดอันดับอย่างไร",
        "What are the best": "ที่ดีที่สุดคืออะไร",
        "Logging policy": "นโยบายการบันทึก",
        "Safety Guide": "คู่มือความปลอดภัย",
        "passes trust threshold": "ผ่านเกณฑ์ความน่าเชื่อถือ",
        "Recommended for use": "แนะนำสำหรับการใช้งาน",
        "This score is based on automated analysis of security, maintenance, community, and quality signals": "คะแนนนี้อิงจากการวิเคราะห์อัตโนมัติของสัญญาณความปลอดภัย การบำรุงรักษา ชุมชน และคุณภาพ",
        "According to independent audit reports": "ตามรายงานการตรวจสอบอิสระ",
        "No known data breaches associated with this service": "ไม่มีการละเมิดข้อมูลที่ทราบเกี่ยวกับบริการนี้",
        "This is a strong positive signal": "นี่เป็นสัญญาณเชิงบวกที่แข็งแกร่ง",
        "logging policy": "นโยบายการบันทึก",
        "Full analysis": "การวิเคราะห์ทั้งหมด",
        "Server infrastructure": "โครงสร้างพื้นฐานเซิร์ฟเวอร์",
        "It is recommended": "แนะนำ",
        "most VPN providers have not been independently audited": "ผู้ให้บริการ VPN ส่วนใหญ่ไม่ได้รับการตรวจสอบอย่างเป็นอิสระ",
        "Nerq analyzes over": "Nerq วิเคราะห์มากกว่า",
        "is based in": "มีสำนักงานใหญ่ใน",
        "outside all Eyes surveillance alliances": "อยู่นอกพันธมิตรเฝ้าระวัง Eyes ทั้งหมด",
        "a privacy advantage": "ข้อได้เปรียบด้านความเป็นส่วนตัว",
        "has been independently audited to verify its privacy claims": "ได้รับการตรวจสอบอย่างเป็นอิสระเพื่อยืนยันการอ้างสิทธิ์ความเป็นส่วนตัว",
        "Serving": "ให้บริการ",
        "Related Safety Rankings": "อันดับความปลอดภัยที่เกี่ยวข้อง",
        "Complete Your Privacy Setup": "ตั้งค่าความเป็นส่วนตัวให้สมบูรณ์",
        "Browse Categories": "เรียกดูหมวดหมู่",
        "Safest VPNs": "VPN ที่ปลอดภัยที่สุด",
        "Most Private Apps": "แอปที่เป็นส่วนตัวที่สุด",
        "Recently Analyzed": "วิเคราะห์ล่าสุด",
        "What are the best alternatives to": "ทางเลือกที่ดีที่สุดสำหรับ",
        "which is safer": "อันไหนปลอดภัยกว่า",
        "logging practices": "การบันทึกข้อมูล",
        "ownership transparency": "ความโปร่งใสในการเป็นเจ้าของ",
        "Popular in": "ยอดนิยมใน",
        "Popularity": "ความนิยม",
        "Not Yet Analyzed": "ยังไม่ได้วิเคราะห์",
        # ── Vertical-specific strings ──
        "Privacy Assessment": "การประเมินความเป็นส่วนตัว",
        "Breach History": "ประวัติการรั่วไหล",
        "Encryption": "การเข้ารหัส",
        "Build Your Security Stack": "สร้างชุดความปลอดภัยของคุณ",
        "Best VPNs": "VPN ที่ดีที่สุด",
        "Best Password Managers": "ตัวจัดการรหัสผ่านที่ดีที่สุด",
        "Best Antivirus": "แอนตี้ไวรัสที่ดีที่สุด",
        "Security Assessment": "การประเมินความปลอดภัย",
        "Security & Compliance": "ความปลอดภัยและการปฏิบัติตาม",
        "Combine these tools for comprehensive protection:": "รวมเครื่องมือเหล่านี้เพื่อการป้องกันที่ครอบคลุม:",
        # Title / H1
        "Independent Trust & Security Analysis": "การวิเคราะห์ความน่าเชื่อถือและความปลอดภัยอิสระ",
        "Independent Trust &amp; Security Analysis": "การวิเคราะห์ความน่าเชื่อถือและความปลอดภัยอิสระ",
        # Verdicts
        "Yes, {name} is safe to use.": "ใช่ {name} ปลอดภัยที่จะใช้งาน",
        "Use {name} with some caution.": "ใช้ {name} ด้วยความระมัดระวัง",
        "Exercise caution with {name}.": "ควรระวังกับ {name}",
        "{name} has significant trust concerns.": "{name} มีปัญหาด้านความน่าเชื่อถือที่สำคัญ",
        "Passes Nerq Verified threshold": "ผ่านเกณฑ์การตรวจสอบของ Nerq",
        "Below Nerq Verified threshold": "ต่ำกว่าเกณฑ์การตรวจสอบของ Nerq",
        "Significant trust gaps detected": "ตรวจพบช่องว่างด้านความน่าเชื่อถือที่สำคัญ",
        # Section headings
        "Trust Score Breakdown": "รายละเอียดคะแนนความน่าเชื่อถือ",
        "Safety Score Breakdown": "รายละเอียดคะแนนความปลอดภัย",
        "Key Findings": "ข้อค้นพบหลัก",
        "Key Safety Findings": "ข้อค้นพบด้านความปลอดภัยหลัก",
        "Detailed Score Analysis": "การวิเคราะห์คะแนนอย่างละเอียด",
        "Frequently Asked Questions": "คำถามที่พบบ่อย",
        "Safer Alternatives": "ทางเลือกที่ปลอดภัยกว่า",
        "Popular Alternatives": "ทางเลือกยอดนิยม",
        "Community Reviews": "รีวิวจากชุมชน",
        "Regulatory Compliance": "การปฏิบัติตามกฎระเบียบ",
        "How we calculated this score": "วิธีที่เราคำนวณคะแนนนี้",
        "What We Know About": "สิ่งที่เรารู้เกี่ยวกับ",
        # Safety Guide
        "Safety Guide:": "คู่มือความปลอดภัย:",
        "What is": "คืออะไร",
        "How to Verify Safety": "วิธีตรวจสอบความปลอดภัย",
        "Key Safety Concerns for": "ข้อกังวลด้านความปลอดภัยหลักสำหรับ",
        "Trust Assessment": "การประเมินความน่าเชื่อถือ",
        "Key Takeaways": "ประเด็นสำคัญ",
        "Recommended for use — passes trust threshold.": "แนะนำให้ใช้ — ผ่านเกณฑ์ความน่าเชื่อถือ",
        "Review carefully before use — below trust threshold.": "ตรวจสอบอย่างละเอียดก่อนใช้ — ต่ำกว่าเกณฑ์ความน่าเชื่อถือ",
        "Always verify independently using the": "ตรวจสอบอย่างอิสระเสมอโดยใช้",
        "When evaluating any": "เมื่อประเมิน",
        "watch for:": "ควรระวัง:",
        # Cross-product
        "Across Platforms": "บนแพลตฟอร์มอื่น",
        "across platforms": "บนแพลตฟอร์มอื่น",
        "Same developer/company in other registries:": "ผู้พัฒนา/บริษัทเดียวกันใน registry อื่น:",
        # King sections
        "What data does": "ข้อมูลอะไรที่",
        "collect?": "เก็บรวบรวม?",
        "Is": "ปลอดภัยหรือไม่",
        "secure?": "ปลอดภัย?",
        "Full analysis:": "การวิเคราะห์ฉบับเต็ม:",
        "Privacy Report": "รายงานความเป็นส่วนตัว",
        "Privacy review": "รีวิวความเป็นส่วนตัว",
        "Security Report": "รายงานความปลอดภัย",
        # Dimensions
        "Security": "ความปลอดภัย",
        "Privacy": "ความเป็นส่วนตัว",
        "Reliability": "ความน่าเชื่อถือ",
        "Transparency": "ความโปร่งใส",
        "Maintenance": "การบำรุงรักษา",
        "Overall Trust": "ความน่าเชื่อถือโดยรวม",
        "Composite trust score": "คะแนนความน่าเชื่อถือรวม",
        "across all available signals": "จากสัญญาณทั้งหมดที่มี",
        # Methodology
        "Nerq analyzes over 7.5 million entities across 26 registries": "Nerq วิเคราะห์มากกว่า 7.5 ล้านเอนทิตีใน 26 registry",
        "using the same methodology, enabling direct cross-entity comparison": "โดยใช้วิธีการเดียวกัน ทำให้สามารถเปรียบเทียบโดยตรงระหว่างเอนทิตีได้",
        "Scores are updated continuously as new data becomes available": "คะแนนจะถูกอัปเดตอย่างต่อเนื่องเมื่อมีข้อมูลใหม่",
        "This page was last reviewed on": "หน้านี้ได้รับการตรวจสอบล่าสุดเมื่อ",
        "Data version": "เวอร์ชันข้อมูล",
        "Full methodology documentation": "เอกสารวิธีการฉบับเต็ม",
        "Machine-readable data (JSON API)": "ข้อมูลที่เครื่องอ่านได้ (JSON API)",
        "Machine-readable data (JSON)": "ข้อมูลที่เครื่องอ่านได้ (JSON)",
        # Meta / small text
        "Last analyzed:": "วิเคราะห์ล่าสุด:",
        "Last updated": "อัปเดตล่าสุด",
        "Updated daily": "อัปเดตทุกวัน",
        "Independent. Data-driven.": "อิสระ อิงข้อมูล",
        "verified": "ยืนยันแล้ว",
        "Data sourced from": "ข้อมูลจาก",
        "Based on": "อิงจาก",
        "dimensions": "มิติ",
        "independent data dimensions": "มิติข้อมูลอิสระ",
        "strong": "แข็งแกร่ง",
        "moderate": "ปานกลาง",
        "weak": "อ่อนแอ",
        "actively maintained": "ดูแลอย่างต่อเนื่อง",
        "moderately maintained": "ดูแลปานกลาง",
        "low maintenance activity": "กิจกรรมดูแลน้อย",
        "well-documented": "มีเอกสารครบถ้วน",
        "partial documentation": "มีเอกสารบางส่วน",
        "limited documentation": "เอกสารจำกัด",
        "community adoption": "การยอมรับจากชุมชน",
        "stars on": "ดาวบน",
        # Cross-links
        "Safety": "ความปลอดภัย",
        "Legit?": "น่าเชื่อถือ?",
        "Scam?": "หลอกลวง?",
        "Review": "รีวิว",
        "Alternatives": "ทางเลือก",
        "Compare": "เปรียบเทียบ",
        "Best in Category": "ดีที่สุดในหมวดหมู่",
        "Who Owns?": "ใครเป็นเจ้าของ?",
        "What Is?": "คืออะไร?",
        "Sells Data?": "ขายข้อมูล?",
        "Hacked?": "ถูกแฮก?",
        "Safe for Kids?": "ปลอดภัยสำหรับเด็ก?",
        "Pros &amp; Cons": "ข้อดี &amp; ข้อเสีย",
        # FAQ answers
        "Nerq Verified — meets the 70+ trust threshold.": "Nerq ยืนยันแล้ว — ผ่านเกณฑ์ความน่าเชื่อถือ 70+",
        "Below the Nerq Verified threshold of 70.": "ต่ำกว่าเกณฑ์ Nerq ที่ 70",
        "Has not yet reached the Nerq Verified threshold of 70.": "ยังไม่ถึงเกณฑ์ Nerq ที่ 70",
        "Strongest signal:": "สัญญาณที่แข็งแกร่งที่สุด:",
        "Score based on": "คะแนนอิงจาก",
        "security": "ความปลอดภัย",
        "maintenance": "การบำรุงรักษา",
        "popularity": "ความนิยม",
        "documentation": "เอกสาร",
        "compliance": "การปฏิบัติตามกฎระเบียบ",
        # Verdict box
        "Safe": "ปลอดภัย",
        "Use Caution": "ระวัง",
        "Avoid": "หลีกเลี่ยง",
        # Long text patterns
        "is a Node.js package": "เป็นแพ็คเกจ Node.js",
        "is a Python package": "เป็นแพ็คเกจ Python",
        "is a Rust crate": "เป็น Rust crate",
        "is a Chrome extension": "เป็นส่วนขยาย Chrome",
        "is a Firefox extension": "เป็นส่วนขยาย Firefox",
        "is a VS Code extension": "เป็นส่วนขยาย VS Code",
        "is a WordPress plugin": "เป็นปลั๊กอิน WordPress",
        "is a iOS app": "เป็นแอป iOS",
        "is a Android app": "เป็นแอป Android",
        "is a VPN service": "เป็นบริการ VPN",
        "is a game": "เป็นเกม",
        "is a website": "เป็นเว็บไซต์",
        "is a SaaS platform": "เป็นแพลตฟอร์ม SaaS",
        "is a dietary supplement": "เป็นอาหารเสริม",
        "is a cosmetic ingredient": "เป็นส่วนผสมเครื่องสำอาง",
        "is a food": "เป็นส่วนผสมอาหาร",
        "is a travel destination": "เป็นจุดหมายปลายทางท่องเที่ยว",
        "is a nonprofit organization": "เป็นองค์กรไม่แสวงหาผลกำไร",
        "with a Nerq Trust Score of": "ด้วยคะแนนความน่าเชื่อถือ Nerq",
        "with a Nerq Safety Score of": "ด้วยคะแนนความปลอดภัย Nerq",
        "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "ผ่านเกณฑ์ความน่าเชื่อถือของ Nerq ด้วยสัญญาณที่แข็งแกร่งในด้านความปลอดภัย การบำรุงรักษา และการยอมรับจากชุมชน",
        "It has moderate trust signals but shows some areas of concern": "มีสัญญาณความน่าเชื่อถือปานกลางแต่พบบางประเด็นที่น่าเป็นห่วง",
        "It has below-average trust signals with significant gaps": "มีสัญญาณความน่าเชื่อถือต่ำกว่าค่าเฉลี่ยและมีช่องว่างที่สำคัญ",
        "review the full report below for specific considerations": "ดูรายงานฉบับเต็มด้านล่างสำหรับข้อพิจารณาเฉพาะ",
        "This score is based on automated analysis of security, maintenance, community, and quality signals.": "คะแนนนี้อิงจากการวิเคราะห์อัตโนมัติของสัญญาณด้านความปลอดภัย การบำรุงรักษา ชุมชน และคุณภาพ",
        "You can also check the trust score via API:": "คุณสามารถตรวจสอบคะแนนความน่าเชื่อถือผ่าน API ได้เช่นกัน:",
        "As a development package": "ในฐานะแพ็คเกจพัฒนา",
        "does not directly collect end-user personal data": "ไม่เก็บข้อมูลส่วนตัวของผู้ใช้ปลายทางโดยตรง",
        "However, applications built with it may collect data depending on implementation": "อย่างไรก็ตาม แอปพลิเคชันที่สร้างด้วยอาจเก็บข้อมูลขึ้นอยู่กับการใช้งาน",
        "Review the package's dependencies for potential supply chain risks": "ตรวจสอบ dependencies ของแพ็คเกจสำหรับความเสี่ยงด้านห่วงโซ่อุปทาน",
        "License information not available": "ไม่มีข้อมูลใบอนุญาต",
        "Open-source packages allow independent security review of the source code": "แพ็คเกจ open-source อนุญาตให้ตรวจสอบความปลอดภัยของซอร์สโค้ดได้อย่างอิสระ",
        "to check for vulnerabilities": "เพื่อตรวจสอบช่องโหว่",
        "Review the": "ตรวจสอบ",
        "GitHub repository for recent commits": "GitHub repository สำหรับ commit ล่าสุด",
        "dependency vulnerabilities, malicious packages, typosquatting": "ช่องโหว่ dependencies แพ็คเกจอันตราย typosquatting",
        "Run your package manager's audit command": "รันคำสั่ง audit ของ package manager",
        "to check for known vulnerabilities in your dependency tree": "เพื่อตรวจสอบช่องโหว่ที่ทราบใน dependency tree",
        "This meets the recommended security threshold for production use": "ผ่านเกณฑ์ความปลอดภัยที่แนะนำสำหรับการใช้งานจริง",
        "Nerq monitors this entity against NVD, OSV.dev, and registry-specific vulnerability databases": "Nerq ตรวจสอบเอนทิตีนี้กับ NVD, OSV.dev และฐานข้อมูลช่องโหว่เฉพาะ registry",
        "for ongoing security assessment": "สำหรับการประเมินความปลอดภัยอย่างต่อเนื่อง",
        "Yes, it is safe to use.": "ใช่ ปลอดภัยที่จะใช้งาน",
        "Use with some caution.": "ใช้ด้วยความระมัดระวัง",
        "Exercise caution.": "ควรระวัง",
        "Significant trust concerns.": "มีปัญหาด้านความน่าเชื่อถือที่สำคัญ",
        "maintained by": "ดูแลโดย",
        "is computed from": "คำนวณจาก",
        "The score reflects": "คะแนนสะท้อน",
        "independent dimensions": "มิติอิสระ",
        "Each dimension is weighted equally to produce the composite trust score": "แต่ละมิติมีน้ำหนักเท่ากันเพื่อสร้างคะแนนความน่าเชื่อถือรวม",
        "No reviews yet.": "ยังไม่มีรีวิว",
        "Be the first to review": "เป็นคนแรกที่รีวิว",
        "Write a review": "เขียนรีวิว",
        "Higher-rated": "คะแนนสูงกว่า",
        "you may want to consider:": "ที่คุณอาจต้องการพิจารณา:",
        "under assessment": "กำลังประเมิน",
        # Health disclaimers
        "Important Notice:": "หมายเหตุสำคัญ:",
        "educational and informational purposes only": "เพื่อการศึกษาและให้ข้อมูลเท่านั้น",
        "does not constitute medical advice": "ไม่ใช่คำแนะนำทางการแพทย์",
        "Consult a qualified healthcare professional": "ปรึกษาผู้เชี่ยวชาญด้านสุขภาพที่มีคุณสมบัติ",
        "Full health disclaimer": "ข้อสงวนสิทธิ์ด้านสุขภาพฉบับเต็ม",
        "Full disclaimer": "ข้อสงวนสิทธิ์ฉบับเต็ม",
    },
    "ro": {
        "It is ": "Este ",
        "Is NordVPN safe": "Este NordVPN sigur",
        "What is NordVPN": "Ce este NordVPN",
        "Does NordVPN log my data": "NordVPN înregistrează datele mele",
        "What are the best alternatives to NordVPN": "Care sunt cele mai bune alternative la NordVPN",
        "NordVPN vs alternatives: which is safer": "NordVPN vs alternative: care este mai sigur",
        "trust score?": "scor de încredere?",
        "Scores update as new data becomes available": "Scorurile se actualizează când devin disponibile date noi",
        "In the vpn category": "În categoria VPN",
        "full safety report for detailed privacy analysis": "raportul complet de securitate pentru analiza detaliată a confidențialității",
        "jurisdiction databases, independent audit reports, protocol analysis, and incident history": "baze de date jurisdicționale, rapoarte de audit independente, analiză de protocol și istoric incidente",
        "has undergone third-party security audits verifying its infrastructure and no-logs claims": "a trecut prin audituri de securitate terțe care verifică infrastructura și revendicările de non-logare",
        "widely used VPN service": "serviciu VPN utilizat pe scară largă",
        "multiple public sources including package registries, GitHub, NVD, OSV.dev, and OpenSSF Scorecard": "multiple surse publice inclusiv registre de pachete, GitHub, NVD, OSV.dev și OpenSSF Scorecard",
        "What does a Nerq Trust Score": "Ce înseamnă un Nerq Trust Score",
        "Are these safest": "Sunt acestea cele mai sigure",
        "How are safest": "Cum sunt cele mai sigure",
        "The #1 safest": "Cel mai sigur #1",
        "The #1": "Nr. 1",
        "According to Nerq": "Conform Nerq",
        "How are": "Cum sunt",
        "What are the best": "Care sunt cele mai bune",
        "Logging policy": "Politica de înregistrare",
        "Safety Guide": "Ghid de Securitate",
        "passes trust threshold": "depășește pragul de încredere",
        "Recommended for use": "Recomandat pentru utilizare",
        "This score is based on automated analysis of security, maintenance, community, and quality signals": "Acest scor se bazează pe analiza automată a semnalelor de securitate, întreținere, comunitate și calitate",
        "According to independent audit reports": "Conform rapoartelor de audit independente",
        "No known data breaches associated with this service": "Nu există încălcări de date cunoscute asociate cu acest serviciu",
        "This is a strong positive signal": "Acesta este un semnal pozitiv puternic",
        "logging policy": "politica de înregistrare",
        "Full analysis": "Analiză completă",
        "Server infrastructure": "Infrastructura serverelor",
        "It is recommended": "Este recomandat",
        "most VPN providers have not been independently audited": "majoritatea furnizorilor de VPN nu au fost auditați independent",
        "Nerq analyzes over": "Nerq analizează peste",
        "is based in": "are sediul în",
        "outside all Eyes surveillance alliances": "în afara tuturor alianțelor de supraveghere Eyes",
        "a privacy advantage": "un avantaj de confidențialitate",
        "has been independently audited to verify its privacy claims": "a fost auditat independent pentru a verifica revendicările sale de confidențialitate",
        "Serving": "Deservește",
        "Related Safety Rankings": "Clasamente de securitate conexe",
        "Complete Your Privacy Setup": "Completați configurarea confidențialității",
        "Browse Categories": "Răsfoiți categoriile",
        "Safest VPNs": "Cele mai sigure VPN-uri",
        "Most Private Apps": "Cele mai private aplicații",
        "Recently Analyzed": "Analizate recent",
        "What are the best alternatives to": "Care sunt cele mai bune alternative la",
        "which is safer": "care este mai sigur",
        "logging practices": "practici de înregistrare",
        "ownership transparency": "transparența proprietății",
        "Popular in": "Popular în",
        "Popularity": "Popularitate",
        "Not Yet Analyzed": "Încă neanalizat",
        # ── Vertical-specific strings ──
        "Privacy Assessment": "Evaluare Confidențialitate",
        "Breach History": "Istoric Încălcări",
        "Encryption": "Criptare",
        "Build Your Security Stack": "Construiește-ți Pachetul de Securitate",
        "Best VPNs": "Cele Mai Bune VPN-uri",
        "Best Password Managers": "Cele Mai Bune Managere de Parole",
        "Best Antivirus": "Cel Mai Bun Antivirus",
        "Security Assessment": "Evaluare Securitate",
        "Security & Compliance": "Securitate și Conformitate",
        "Combine these tools for comprehensive protection:": "Combină aceste instrumente pentru protecție completă:",
        # Title / H1
        "Independent Trust & Security Analysis": "Analiză independentă de încredere și securitate",
        "Independent Trust &amp; Security Analysis": "Analiză independentă de încredere și securitate",
        # Verdicts
        "Yes, {name} is safe to use.": "Da, {name} este sigur de utilizat.",
        "Use {name} with some caution.": "Folosiți {name} cu precauție.",
        "Exercise caution with {name}.": "Fiți precauți cu {name}.",
        "{name} has significant trust concerns.": "{name} are probleme semnificative de încredere.",
        "Passes Nerq Verified threshold": "Îndeplinește pragul verificat Nerq",
        "Below Nerq Verified threshold": "Sub pragul verificat Nerq",
        "Significant trust gaps detected": "Lacune semnificative de încredere detectate",
        # Section headings
        "Trust Score Breakdown": "Detalii scor de încredere",
        "Safety Score Breakdown": "Detalii scor de securitate",
        "Key Findings": "Constatări principale",
        "Key Safety Findings": "Constatări principale de securitate",
        "Detailed Score Analysis": "Analiză detaliată a scorului",
        "Frequently Asked Questions": "Întrebări frecvente",
        "Safer Alternatives": "Alternative mai sigure",
        "Popular Alternatives": "Alternative populare",
        "Community Reviews": "Recenzii din comunitate",
        "Regulatory Compliance": "Conformitate reglementară",
        "How we calculated this score": "Cum am calculat acest scor",
        "What We Know About": "Ce știm despre",
        # Safety Guide
        "Safety Guide:": "Ghid de securitate:",
        "What is": "Ce este",
        "How to Verify Safety": "Cum să verifici securitatea",
        "Key Safety Concerns for": "Probleme principale de securitate pentru",
        "Trust Assessment": "Evaluare de încredere",
        "Key Takeaways": "Concluzii principale",
        "Recommended for use — passes trust threshold.": "Recomandat — îndeplinește pragul de încredere.",
        "Review carefully before use — below trust threshold.": "Verificați cu atenție înainte de utilizare — sub pragul de încredere.",
        "Always verify independently using the": "Verificați întotdeauna independent folosind",
        "When evaluating any": "Când evaluați orice",
        "watch for:": "urmăriți:",
        # Cross-product
        "Across Platforms": "Pe alte platforme",
        "across platforms": "pe alte platforme",
        "Same developer/company in other registries:": "Același dezvoltator/companie în alte registre:",
        # King sections
        "What data does": "Ce date colectează",
        "collect?": "colectează?",
        "Is": "Este",
        "secure?": "sigur?",
        "Full analysis:": "Analiză completă:",
        "Privacy Report": "Raport de confidențialitate",
        "Privacy review": "Recenzie confidențialitate",
        "Security Report": "Raport de securitate",
        # Dimensions
        "Security": "Securitate",
        "Privacy": "Confidențialitate",
        "Reliability": "Fiabilitate",
        "Transparency": "Transparență",
        "Maintenance": "Mentenanță",
        "Overall Trust": "Încredere generală",
        "Composite trust score": "Scor de încredere compus",
        "across all available signals": "din toate semnalele disponibile",
        # Methodology
        "Nerq analyzes over 7.5 million entities across 26 registries": "Nerq analizează peste 7,5 milioane de entități din 26 de registre",
        "using the same methodology, enabling direct cross-entity comparison": "folosind aceeași metodologie, permițând compararea directă între entități",
        "Scores are updated continuously as new data becomes available": "Scorurile sunt actualizate continuu pe măsură ce devin disponibile date noi",
        "This page was last reviewed on": "Această pagină a fost revizuită ultima dată pe",
        "Data version": "Versiunea datelor",
        "Full methodology documentation": "Documentație completă a metodologiei",
        "Machine-readable data (JSON API)": "Date citibile de mașină (JSON API)",
        "Machine-readable data (JSON)": "Date citibile de mașină (JSON)",
        # Meta / small text
        "Last analyzed:": "Ultima analiză:",
        "Last updated": "Ultima actualizare",
        "Updated daily": "Actualizat zilnic",
        "Independent. Data-driven.": "Independent. Bazat pe date.",
        "verified": "verificat",
        "Data sourced from": "Date provenite din",
        "Based on": "Bazat pe",
        "dimensions": "dimensiuni",
        "independent data dimensions": "dimensiuni independente de date",
        "strong": "puternic",
        "moderate": "moderat",
        "weak": "slab",
        "actively maintained": "menținut activ",
        "moderately maintained": "menținut moderat",
        "low maintenance activity": "activitate redusă de mentenanță",
        "well-documented": "bine documentat",
        "partial documentation": "documentație parțială",
        "limited documentation": "documentație limitată",
        "community adoption": "adoptare comunitară",
        "stars on": "stele pe",
        # Cross-links
        "Safety": "Securitate",
        "Legit?": "De încredere?",
        "Scam?": "Fraudă?",
        "Review": "Recenzie",
        "Alternatives": "Alternative",
        "Compare": "Comparare",
        "Best in Category": "Cel mai bun în categorie",
        "Who Owns?": "Cine deține?",
        "What Is?": "Ce este?",
        "Sells Data?": "Vinde date?",
        "Hacked?": "Compromis?",
        "Safe for Kids?": "Sigur pentru copii?",
        "Pros &amp; Cons": "Avantaje &amp; Dezavantaje",
        # FAQ answers
        "Nerq Verified — meets the 70+ trust threshold.": "Verificat Nerq — îndeplinește pragul de încredere 70+.",
        "Below the Nerq Verified threshold of 70.": "Sub pragul verificat Nerq de 70.",
        "Has not yet reached the Nerq Verified threshold of 70.": "Nu a atins încă pragul verificat Nerq de 70.",
        "Strongest signal:": "Cel mai puternic semnal:",
        "Score based on": "Scor bazat pe",
        "security": "securitate",
        "maintenance": "mentenanță",
        "popularity": "popularitate",
        "documentation": "documentație",
        "compliance": "conformitate",
        # Verdict box
        "Safe": "Sigur",
        "Use Caution": "Precauție",
        "Avoid": "De evitat",
        # Long text patterns
        "is a Node.js package": "este un pachet Node.js",
        "is a Python package": "este un pachet Python",
        "is a Rust crate": "este un Rust crate",
        "is a Chrome extension": "este o extensie Chrome",
        "is a Firefox extension": "este o extensie Firefox",
        "is a VS Code extension": "este o extensie VS Code",
        "is a WordPress plugin": "este un plugin WordPress",
        "is a iOS app": "este o aplicație iOS",
        "is a Android app": "este o aplicație Android",
        "is a VPN service": "este un serviciu VPN",
        "is a game": "este un joc",
        "is a website": "este un site web",
        "is a SaaS platform": "este o platformă SaaS",
        "is a dietary supplement": "este un supliment alimentar",
        "is a cosmetic ingredient": "este un ingredient cosmetic",
        "is a food": "este un ingredient alimentar",
        "is a travel destination": "este o destinație de călătorie",
        "is a nonprofit organization": "este o organizație nonprofit",
        "with a Nerq Trust Score of": "cu un Scor de Încredere Nerq de",
        "with a Nerq Safety Score of": "cu un Scor de Securitate Nerq de",
        "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "Îndeplinește pragul de încredere Nerq cu semnale puternice în securitate, mentenanță și adoptare comunitară",
        "It has moderate trust signals but shows some areas of concern": "Are semnale de încredere moderate, dar prezintă unele zone de îngrijorare",
        "It has below-average trust signals with significant gaps": "Are semnale de încredere sub medie cu lacune semnificative",
        "review the full report below for specific considerations": "consultați raportul complet de mai jos pentru considerații specifice",
        "This score is based on automated analysis of security, maintenance, community, and quality signals.": "Acest scor se bazează pe analiza automatizată a semnalelor de securitate, mentenanță, comunitate și calitate.",
        "You can also check the trust score via API:": "Puteți verifica și scorul de încredere prin API:",
        "As a development package": "Ca pachet de dezvoltare",
        "does not directly collect end-user personal data": "nu colectează direct date personale ale utilizatorilor finali",
        "However, applications built with it may collect data depending on implementation": "Cu toate acestea, aplicațiile construite cu el pot colecta date în funcție de implementare",
        "Review the package's dependencies for potential supply chain risks": "Verificați dependențele pachetului pentru riscuri potențiale în lanțul de aprovizionare",
        "License information not available": "Informații despre licență indisponibile",
        "Open-source packages allow independent security review of the source code": "Pachetele open-source permit revizuirea independentă a securității codului sursă",
        "to check for vulnerabilities": "pentru a verifica vulnerabilitățile",
        "Review the": "Verificați",
        "GitHub repository for recent commits": "depozitul GitHub pentru commit-uri recente",
        "dependency vulnerabilities, malicious packages, typosquatting": "vulnerabilități de dependențe, pachete malițioase, typosquatting",
        "Run your package manager's audit command": "Rulați comanda de audit a managerului de pachete",
        "to check for known vulnerabilities in your dependency tree": "pentru a verifica vulnerabilitățile cunoscute în arborele de dependențe",
        "This meets the recommended security threshold for production use": "Aceasta îndeplinește pragul de securitate recomandat pentru utilizare în producție",
        "Nerq monitors this entity against NVD, OSV.dev, and registry-specific vulnerability databases": "Nerq monitorizează această entitate față de NVD, OSV.dev și bazele de date de vulnerabilități specifice registrului",
        "for ongoing security assessment": "pentru evaluarea continuă a securității",
        "Yes, it is safe to use.": "Da, este sigur de utilizat.",
        "Use with some caution.": "Utilizați cu precauție.",
        "Exercise caution.": "Fiți precauți.",
        "Significant trust concerns.": "Probleme semnificative de încredere.",
        "maintained by": "întreținut de",
        "is computed from": "este calculat din",
        "The score reflects": "Scorul reflectă",
        "independent dimensions": "dimensiuni independente",
        "Each dimension is weighted equally to produce the composite trust score": "Fiecare dimensiune are pondere egală pentru a produce scorul de încredere compus",
        "No reviews yet.": "Încă nu există recenzii.",
        "Be the first to review": "Fii primul care recenzează",
        "Write a review": "Scrie o recenzie",
        "Higher-rated": "Cu scor mai mare",
        "you may want to consider:": "pe care ați putea dori să le luați în considerare:",
        "under assessment": "în evaluare",
        # Health disclaimers
        "Important Notice:": "Notă importantă:",
        "educational and informational purposes only": "doar în scop educativ și informativ",
        "does not constitute medical advice": "nu constituie sfat medical",
        "Consult a qualified healthcare professional": "Consultați un profesionist medical calificat",
        "Full health disclaimer": "Declinare completă a responsabilității medicale",
        "Full disclaimer": "Declinare completă a responsabilității",
    },
    "tr": {
        "It is ": "Bu ",
        "Is NordVPN safe": "NordVPN güvenli mi",
        "What is NordVPN": "NordVPN nedir",
        "Does NordVPN log my data": "NordVPN verilerimi kaydediyor mu",
        "What are the best alternatives to NordVPN": "NordVPN için en iyi alternatifler",
        "NordVPN vs alternatives: which is safer": "NordVPN vs alternatifler: hangisi daha güvenli",
        "trust score?": "güven puanı?",
        "Scores update as new data becomes available": "Yeni veriler mevcut olduğunda puanlar güncellenir",
        "In the vpn category": "VPN kategorisinde",
        "full safety report for detailed privacy analysis": "ayrıntılı gizlilik analizi için tam güvenlik raporunu",
        "jurisdiction databases, independent audit reports, protocol analysis, and incident history": "yetki alanı veritabanları, bağımsız denetim raporları, protokol analizi ve olay geçmişi",
        "has undergone third-party security audits verifying its infrastructure and no-logs claims": "altyapısını ve kayıt tutmama iddialarını doğrulayan üçüncü taraf güvenlik denetimlerinden geçmiştir",
        "widely used VPN service": "yaygın olarak kullanılan VPN hizmeti",
        "multiple public sources including package registries, GitHub, NVD, OSV.dev, and OpenSSF Scorecard": "paket kayıtları, GitHub, NVD, OSV.dev ve OpenSSF Scorecard dahil birden fazla genel kaynak",
        "What does a Nerq Trust Score": "Nerq Trust Score ne anlama gelir",
        "Are these safest": "Bunlar en güvenli mi",
        "How are safest": "En güvenliler nasıl",
        "The #1 safest": "En güvenli 1 numara",
        "The #1": "1 numaralı",
        "According to Nerq": "Nerq'e göre",
        "How are": "Nasıl",
        "What are the best": "En iyi nelerdir",
        "Logging policy": "Kayıt tutma politikası",
        "Safety Guide": "Güvenlik Rehberi",
        "passes trust threshold": "güven eşiğini geçiyor",
        "Recommended for use": "Kullanım için önerilir",
        "This score is based on automated analysis of security, maintenance, community, and quality signals": "Bu puan; güvenlik, bakım, topluluk ve kalite sinyallerinin otomatik analizine dayanmaktadır",
        "According to independent audit reports": "Bağımsız denetim raporlarına göre",
        "No known data breaches associated with this service": "Bu hizmetle ilişkili bilinen bir veri ihlali yok",
        "This is a strong positive signal": "Bu güçlü bir pozitif sinyal",
        "logging policy": "kayıt tutma politikası",
        "Full analysis": "Tam analiz",
        "Server infrastructure": "Sunucu altyapısı",
        "It is recommended": "Önerilir",
        "most VPN providers have not been independently audited": "çoğu VPN sağlayıcısı bağımsız olarak denetlenmemiştir",
        "Nerq analyzes over": "Nerq, analiz eder",
        "is based in": "merkezi",
        "outside all Eyes surveillance alliances": "tüm Eyes gözetim ittifaklarının dışında",
        "a privacy advantage": "bir gizlilik avantajı",
        "has been independently audited to verify its privacy claims": "gizlilik iddialarını doğrulamak için bağımsız olarak denetlenmiştir",
        "Serving": "Hizmet veriyor",
        "Related Safety Rankings": "İlgili güvenlik sıralamaları",
        "Complete Your Privacy Setup": "Gizlilik ayarlarınızı tamamlayın",
        "Browse Categories": "Kategorilere göz at",
        "Safest VPNs": "En güvenli VPN'ler",
        "Most Private Apps": "En özel uygulamalar",
        "Recently Analyzed": "Son analiz edilenler",
        "What are the best alternatives to": "için en iyi alternatifler nelerdir",
        "which is safer": "hangisi daha güvenli",
        "logging practices": "kayıt tutma uygulamaları",
        "ownership transparency": "mülkiyet şeffaflığı",
        "Popular in": "Popüler",
        "Popularity": "Popülerlik",
        "Not Yet Analyzed": "Henüz analiz edilmedi",
        # ── Vertical-specific strings ──
        "Privacy Assessment": "Gizlilik Değerlendirmesi",
        "Breach History": "İhlal Geçmişi",
        "Encryption": "Şifreleme",
        "Build Your Security Stack": "Güvenlik Paketinizi Oluşturun",
        "Best VPNs": "En İyi VPN'ler",
        "Best Password Managers": "En İyi Parola Yöneticileri",
        "Best Antivirus": "En İyi Antivirüs",
        "Security Assessment": "Güvenlik Değerlendirmesi",
        "Security & Compliance": "Güvenlik ve Uyumluluk",
        "Combine these tools for comprehensive protection:": "Kapsamlı koruma için bu araçları birleştirin:",
        # Title / H1
        "Independent Trust & Security Analysis": "Bağımsız Güven ve Güvenlik Analizi",
        "Independent Trust &amp; Security Analysis": "Bağımsız Güven ve Güvenlik Analizi",
        # Verdicts
        "Yes, {name} is safe to use.": "Evet, {name} kullanımı güvenlidir.",
        "Use {name} with some caution.": "{name} kullanırken dikkatli olun.",
        "Exercise caution with {name}.": "{name} konusunda dikkatli olun.",
        "{name} has significant trust concerns.": "{name} önemli güven sorunlarına sahiptir.",
        "Passes Nerq Verified threshold": "Nerq Doğrulanmış eşiğini karşılıyor",
        "Below Nerq Verified threshold": "Nerq Doğrulanmış eşiğinin altında",
        "Significant trust gaps detected": "Önemli güven boşlukları tespit edildi",
        # Section headings
        "Trust Score Breakdown": "Güven Puanı Detayları",
        "Safety Score Breakdown": "Güvenlik Puanı Detayları",
        "Key Findings": "Temel Bulgular",
        "Key Safety Findings": "Temel Güvenlik Bulguları",
        "Detailed Score Analysis": "Detaylı Puan Analizi",
        "Frequently Asked Questions": "Sık Sorulan Sorular",
        "Safer Alternatives": "Daha Güvenli Alternatifler",
        "Popular Alternatives": "Popüler Alternatifler",
        "Community Reviews": "Topluluk Değerlendirmeleri",
        "Regulatory Compliance": "Düzenleyici Uyumluluk",
        "How we calculated this score": "Bu puanı nasıl hesapladık",
        "What We Know About": "Hakkında Bildiklerimiz",
        # Safety Guide
        "Safety Guide:": "Güvenlik Rehberi:",
        "What is": "Nedir:",
        "How to Verify Safety": "Güvenliği Nasıl Doğrularsınız",
        "Key Safety Concerns for": "İçin Temel Güvenlik Sorunları",
        "Trust Assessment": "Güven Değerlendirmesi",
        "Key Takeaways": "Temel Çıkarımlar",
        "Recommended for use — passes trust threshold.": "Kullanım için önerilir — güven eşiğini karşılıyor.",
        "Review carefully before use — below trust threshold.": "Kullanmadan önce dikkatle inceleyin — güven eşiğinin altında.",
        "Always verify independently using the": "Her zaman bağımsız olarak doğrulayın",
        "When evaluating any": "Herhangi bir şeyi değerlendirirken",
        "watch for:": "dikkat edin:",
        # Cross-product
        "Across Platforms": "Diğer Platformlarda",
        "across platforms": "diğer platformlarda",
        "Same developer/company in other registries:": "Diğer kayıt defterlerinde aynı geliştirici/şirket:",
        # King sections
        "What data does": "Hangi verileri topluyor",
        "collect?": "topluyor?",
        "Is": "Güvenli mi:",
        "secure?": "güvenli mi?",
        "Full analysis:": "Tam analiz:",
        "Privacy Report": "Gizlilik Raporu",
        "Privacy review": "Gizlilik değerlendirmesi",
        "Security Report": "Güvenlik Raporu",
        # Dimensions
        "Security": "Güvenlik",
        "Privacy": "Gizlilik",
        "Reliability": "Güvenilirlik",
        "Transparency": "Şeffaflık",
        "Maintenance": "Bakım",
        "Overall Trust": "Genel Güven",
        "Composite trust score": "Bileşik güven puanı",
        "across all available signals": "tüm mevcut sinyaller genelinde",
        # Methodology
        "Nerq analyzes over 7.5 million entities across 26 registries": "Nerq, 26 kayıt defterindeki 7,5 milyondan fazla varlığı analiz eder",
        "using the same methodology, enabling direct cross-entity comparison": "aynı metodolojiyi kullanarak, varlıklar arasında doğrudan karşılaştırma yapılmasını sağlar",
        "Scores are updated continuously as new data becomes available": "Puanlar, yeni veriler kullanılabilir hale geldikçe sürekli güncellenir",
        "This page was last reviewed on": "Bu sayfa en son şu tarihte incelendi:",
        "Data version": "Veri sürümü",
        "Full methodology documentation": "Tam metodoloji dokümantasyonu",
        "Machine-readable data (JSON API)": "Makine tarafından okunabilir veri (JSON API)",
        "Machine-readable data (JSON)": "Makine tarafından okunabilir veri (JSON)",
        # Meta / small text
        "Last analyzed:": "Son analiz:",
        "Last updated": "Son güncelleme",
        "Updated daily": "Günlük güncellenir",
        "Independent. Data-driven.": "Bağımsız. Veriye dayalı.",
        "verified": "doğrulanmış",
        "Data sourced from": "Veriler şuradan alınmıştır:",
        "Based on": "Şuna dayalı:",
        "dimensions": "boyut",
        "independent data dimensions": "bağımsız veri boyutu",
        "strong": "güçlü",
        "moderate": "orta",
        "weak": "zayıf",
        "actively maintained": "aktif olarak sürdürülmektedir",
        "moderately maintained": "orta düzeyde sürdürülmektedir",
        "low maintenance activity": "düşük bakım aktivitesi",
        "well-documented": "iyi belgelenmiş",
        "partial documentation": "kısmi dokümantasyon",
        "limited documentation": "sınırlı dokümantasyon",
        "community adoption": "topluluk benimsemesi",
        "stars on": "yıldız",
        # Cross-links
        "Safety": "Güvenlik",
        "Legit?": "Güvenilir mi?",
        "Scam?": "Dolandırıcılık mı?",
        "Review": "İnceleme",
        "Alternatives": "Alternatifler",
        "Compare": "Karşılaştır",
        "Best in Category": "Kategorinin En İyisi",
        "Who Owns?": "Kime Ait?",
        "What Is?": "Nedir?",
        "Sells Data?": "Veri Satıyor mu?",
        "Hacked?": "Saldırıya Uğradı mı?",
        "Safe for Kids?": "Çocuklar İçin Güvenli mi?",
        "Pros &amp; Cons": "Artılar &amp; Eksiler",
        # FAQ answers
        "Nerq Verified — meets the 70+ trust threshold.": "Nerq Doğrulanmış — 70+ güven eşiğini karşılıyor.",
        "Below the Nerq Verified threshold of 70.": "Nerq Doğrulanmış eşiğinin (70) altında.",
        "Has not yet reached the Nerq Verified threshold of 70.": "Henüz Nerq Doğrulanmış eşiğine (70) ulaşamamıştır.",
        "Strongest signal:": "En güçlü sinyal:",
        "Score based on": "Puan şuna dayalı:",
        "security": "güvenlik",
        "maintenance": "bakım",
        "popularity": "popülerlik",
        "documentation": "dokümantasyon",
        "compliance": "uyumluluk",
        # Verdict box
        "Safe": "Güvenli",
        "Use Caution": "Dikkat",
        "Avoid": "Kaçının",
        # Long text patterns
        "is a Node.js package": "bir Node.js paketidir",
        "is a Python package": "bir Python paketidir",
        "is a Rust crate": "bir Rust crate'idir",
        "is a Chrome extension": "bir Chrome uzantısıdır",
        "is a Firefox extension": "bir Firefox uzantısıdır",
        "is a VS Code extension": "bir VS Code uzantısıdır",
        "is a WordPress plugin": "bir WordPress eklentisidir",
        "is a iOS app": "bir iOS uygulamasıdır",
        "is a Android app": "bir Android uygulamasıdır",
        "is a VPN service": "bir VPN hizmetidir",
        "is a game": "bir oyundur",
        "is a website": "bir web sitesidir",
        "is a SaaS platform": "bir SaaS platformudur",
        "is a dietary supplement": "bir besin takviyesidir",
        "is a cosmetic ingredient": "bir kozmetik bileşenidir",
        "is a food": "bir gıda bileşenidir",
        "is a travel destination": "bir seyahat destinasyonudur",
        "is a nonprofit organization": "bir kar amacı gütmeyen kuruluştur",
        "with a Nerq Trust Score of": "Nerq Güven Puanı ile",
        "with a Nerq Safety Score of": "Nerq Güvenlik Puanı ile",
        "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "Güvenlik, bakım ve topluluk benimsemesi alanlarında güçlü sinyallerle Nerq güven eşiğini karşılıyor",
        "It has moderate trust signals but shows some areas of concern": "Orta düzeyde güven sinyallerine sahip olmakla birlikte bazı endişe alanları göstermektedir",
        "It has below-average trust signals with significant gaps": "Ortalama altı güven sinyalleri ve önemli boşluklara sahiptir",
        "review the full report below for specific considerations": "özel değerlendirmeler için aşağıdaki tam raporu inceleyin",
        "This score is based on automated analysis of security, maintenance, community, and quality signals.": "Bu puan, güvenlik, bakım, topluluk ve kalite sinyallerinin otomatik analizine dayanmaktadır.",
        "You can also check the trust score via API:": "Güven puanını API aracılığıyla da kontrol edebilirsiniz:",
        "As a development package": "Bir geliştirme paketi olarak",
        "does not directly collect end-user personal data": "son kullanıcı kişisel verilerini doğrudan toplamaz",
        "However, applications built with it may collect data depending on implementation": "Ancak onunla oluşturulan uygulamalar, uygulamaya bağlı olarak veri toplayabilir",
        "Review the package's dependencies for potential supply chain risks": "Olası tedarik zinciri riskleri için paketin bağımlılıklarını inceleyin",
        "License information not available": "Lisans bilgisi mevcut değil",
        "Open-source packages allow independent security review of the source code": "Açık kaynaklı paketler, kaynak kodunun bağımsız güvenlik incelemesine olanak tanır",
        "to check for vulnerabilities": "güvenlik açıklarını kontrol etmek için",
        "Review the": "İnceleyin",
        "GitHub repository for recent commits": "son işlemler için GitHub deposu",
        "dependency vulnerabilities, malicious packages, typosquatting": "bağımlılık açıkları, kötü amaçlı paketler, typosquatting",
        "Run your package manager's audit command": "Paket yöneticinizin denetim komutunu çalıştırın",
        "to check for known vulnerabilities in your dependency tree": "bağımlılık ağacınızdaki bilinen güvenlik açıklarını kontrol etmek için",
        "This meets the recommended security threshold for production use": "Bu, üretim kullanımı için önerilen güvenlik eşiğini karşılıyor",
        "Nerq monitors this entity against NVD, OSV.dev, and registry-specific vulnerability databases": "Nerq bu varlığı NVD, OSV.dev ve kayıt defterine özgü güvenlik açığı veritabanlarına karşı izler",
        "for ongoing security assessment": "süregelen güvenlik değerlendirmesi için",
        "Yes, it is safe to use.": "Evet, kullanımı güvenlidir.",
        "Use with some caution.": "Dikkatli kullanın.",
        "Exercise caution.": "Dikkatli olun.",
        "Significant trust concerns.": "Önemli güven sorunları.",
        "maintained by": "tarafından sürdürülmektedir",
        "is computed from": "şundan hesaplanmıştır:",
        "The score reflects": "Puan şunu yansıtmaktadır:",
        "independent dimensions": "bağımsız boyut",
        "Each dimension is weighted equally to produce the composite trust score": "Her boyut, bileşik güven puanını oluşturmak için eşit ağırlıklandırılmıştır",
        "No reviews yet.": "Henüz değerlendirme yok.",
        "Be the first to review": "İlk değerlendirmeyi siz yapın",
        "Write a review": "Değerlendirme yaz",
        "Higher-rated": "Daha yüksek puanlı",
        "you may want to consider:": "değerlendirmek isteyebileceğiniz:",
        "under assessment": "değerlendirme altında",
        # Health disclaimers
        "Important Notice:": "Önemli Uyarı:",
        "educational and informational purposes only": "yalnızca eğitim ve bilgilendirme amaçlıdır",
        "does not constitute medical advice": "tıbbi tavsiye niteliğinde değildir",
        "Consult a qualified healthcare professional": "Nitelikli bir sağlık uzmanına danışın",
        "Full health disclaimer": "Tam sağlık sorumluluk reddi",
        "Full disclaimer": "Tam sorumluluk reddi",
    },
    "hi": {
        "It is ": "यह ",
        "Is NordVPN safe": "क्या NordVPN सुरक्षित है",
        "What is NordVPN": "NordVPN क्या है",
        "Does NordVPN log my data": "क्या NordVPN मेरा डेटा ��ॉग करता है",
        "What are the best alternatives to NordVPN": "NordVPN के सर्वोत्���म विकल्प",
        "NordVPN vs alternatives: which is safer": "NordVPN बनाम विकल्प: कौन अधिक सुरक्षित है",
        "trust score?": "विश्वास स्कोर?",
        "Scores update as new data becomes available": "नया डेटा उपलब्ध होने पर स्कोर अपडेट होते हैं",
        "In the vpn category": "VPN श्रेणी में",
        "full safety report for detailed privacy analysis": "विस्तृत गोपनीयता विश्लेषण के लिए पूर्ण सुरक्षा रिपोर्ट",
        "jurisdiction databases, independent audit reports, protocol analysis, and incident history": "अधिकार क्षेत्र डेटाबेस, स्वतंत्र ऑडिट रिपोर्ट, प्रोटोकॉल विश्लेषण और घटना इतिहास",
        "has undergone third-party security audits verifying its infrastructure and no-logs claims": "अपने बुनियादी ढांचे और नो-लॉग दावों को सत्यापित करने वाले तृतीय-पक्ष सुरक्षा ऑडिट से गुजरा है",
        "widely used VPN service": "व्यापक रूप से उपयोग की जाने वाली VPN सेवा",
        "multiple public sources including package registries, GitHub, NVD, OSV.dev, and OpenSSF Scorecard": "पैकेज रजिस्ट्री, GitHub, NVD, OSV.dev और OpenSSF Scorecard सहित कई सार्वजनिक स्रोत",
        "What does a Nerq Trust Score": "Nerq Trust Score का क्या मतलब है",
        "Are these safest": "क्या ये सबसे सुरक्षित हैं",
        "How are safest": "सबसे सुरक्षित कैसे",
        "The #1 safest": "#1 सबसे सुरक्षित",
        "The #1": "#1",
        "According to Nerq": "Nerq के अनुसार",
        "How are": "कैसे",
        "What are the best": "सबसे अच्छे कौन से हैं",
        "Logging policy": "लॉगिंग नीति",
        "Safety Guide": "सुरक्षा गाइड",
        "passes trust threshold": "विश्वास सीमा पार करता है",
        "Recommended for use": "उपयोग के लिए अनुशंसित",
        "This score is based on automated analysis of security, maintenance, community, and quality signals": "यह स्कोर सुरक्षा, रखरखाव, समुदाय और गुणवत्ता संकेतों के स्वचालित विश्लेषण पर आधारित है",
        "According to independent audit reports": "स्वतंत्र ऑडिट रिपोर्टों के अनुसार",
        "No known data breaches associated with this service": "इस सेवा से जुड़ी कोई ज्ञात डेटा उल्लंघन नहीं",
        "This is a strong positive signal": "यह एक मजबूत सकारात्मक संकेत है",
        "logging policy": "लॉगिंग नीति",
        "Full analysis": "पूर्ण विश्लेषण",
        "Server infrastructure": "सर्वर अवसंरचना",
        "It is recommended": "अनुशंसित है",
        "most VPN providers have not been independently audited": "अधिकांश VPN प्रदाताओं का स्वतंत्र ऑडिट नहीं हुआ है",
        "Nerq analyzes over": "Nerq विश्लेषण करता है",
        "is based in": "का मुख्यालय",
        "outside all Eyes surveillance alliances": "सभी Eyes निगरानी गठबंधनों से बाहर",
        "a privacy advantage": "एक गोपनीयता लाभ",
        "has been independently audited to verify its privacy claims": "अपने गोपनीयता दावों को सत्यापित करने के लिए स्वतंत्र रूप से ऑडिट किया गया है",
        "Serving": "सेवा दे रहा है",
        "Related Safety Rankings": "संबंधित सुरक्षा रैंकिंग",
        "Complete Your Privacy Setup": "अपनी गोपनीयता सेटअप पूरी करें",
        "Browse Categories": "श्रेणियाँ देखें",
        "Safest VPNs": "सबसे सुरक्षित VPN",
        "Most Private Apps": "सबसे निजी ऐप्स",
        "Recently Analyzed": "हाल ही में विश्लेषित",
        "What are the best alternatives to": "के सर्वोत्तम विकल्प क्या हैं",
        "which is safer": "कौन अधिक सुरक्षित है",
        "logging practices": "लॉगिंग प्रथाएं",
        "ownership transparency": "स्वामित्व पारदर्शिता",
        "Popular in": "लोकप्रिय",
        "Popularity": "लोकप्रियता",
        "Not Yet Analyzed": "अभी तक विश्लेषण नहीं किया गया",
        # ── Vertical-specific strings ──
        "Privacy Assessment": "गोपनीयता मूल्यांकन",
        "Breach History": "उल्लंघन इतिहास",
        "Encryption": "एन्क्रिप्शन",
        "Build Your Security Stack": "अपना सुरक्षा पैकेज बनाएं",
        "Best VPNs": "सर्वश्रेष्ठ VPN",
        "Best Password Managers": "सर्वश्रेष्ठ पासवर्ड मैनेजर",
        "Best Antivirus": "सर्वश्रेष्ठ एंटीवायरस",
        "Security Assessment": "सुरक्षा मूल्यांकन",
        "Security & Compliance": "सुरक्षा और अनुपालन",
        "Combine these tools for comprehensive protection:": "व्यापक सुरक्षा के लिए इन उपकरणों को मिलाएं:",
        # Title / H1
        "Independent Trust & Security Analysis": "स्वतंत्र विश्वास एवं सुरक्षा विश्लेषण",
        "Independent Trust &amp; Security Analysis": "स्वतंत्र विश्वास एवं सुरक्षा विश्लेषण",
        # Verdicts
        "Yes, {name} is safe to use.": "हां, {name} उपयोग के लिए सुरक्षित है।",
        "Use {name} with some caution.": "{name} का उपयोग सावधानी से करें।",
        "Exercise caution with {name}.": "{name} के साथ सावधानी बरतें।",
        "{name} has significant trust concerns.": "{name} में महत्वपूर्ण विश्वास संबंधी समस्याएं हैं।",
        "Passes Nerq Verified threshold": "Nerq सत्यापित सीमा को पूरा करता है",
        "Below Nerq Verified threshold": "Nerq सत्यापित सीमा से नीचे",
        "Significant trust gaps detected": "महत्वपूर्ण विश्वास अंतराल पाए गए",
        # Section headings
        "Trust Score Breakdown": "विश्वास स्कोर विवरण",
        "Safety Score Breakdown": "सुरक्षा स्कोर विवरण",
        "Key Findings": "मुख्य निष्कर्ष",
        "Key Safety Findings": "मुख्य सुरक्षा निष्कर्ष",
        "Detailed Score Analysis": "विस्तृत स्कोर विश्लेषण",
        "Frequently Asked Questions": "अक्सर पूछे जाने वाले प्रश्न",
        "Safer Alternatives": "अधिक सुरक्षित विकल्प",
        "Popular Alternatives": "लोकप्रिय विकल्प",
        "Community Reviews": "सामुदायिक समीक्षाएं",
        "Regulatory Compliance": "नियामक अनुपालन",
        "How we calculated this score": "हमने इस स्कोर की गणना कैसे की",
        "What We Know About": "हम इसके बारे में क्या जानते हैं",
        # Safety Guide
        "Safety Guide:": "सुरक्षा गाइड:",
        "What is": "क्या है",
        "How to Verify Safety": "सुरक्षा कैसे सत्यापित करें",
        "Key Safety Concerns for": "के लिए मुख्य सुरक्षा चिंताएं",
        "Trust Assessment": "विश्वास मूल्यांकन",
        "Key Takeaways": "मुख्य निष्कर्ष",
        "Recommended for use — passes trust threshold.": "उपयोग के लिए अनुशंसित — विश्वास सीमा को पूरा करता है।",
        "Review carefully before use — below trust threshold.": "उपयोग से पहले ध्यान से जांचें — विश्वास सीमा से नीचे।",
        "Always verify independently using the": "हमेशा स्वतंत्र रूप से सत्यापित करें",
        "When evaluating any": "किसी का मूल्यांकन करते समय",
        "watch for:": "ध्यान रखें:",
        # Cross-product
        "Across Platforms": "अन्य प्लेटफॉर्म पर",
        "across platforms": "अन्य प्लेटफॉर्म पर",
        "Same developer/company in other registries:": "अन्य रजिस्ट्री में वही डेवलपर/कंपनी:",
        # King sections
        "What data does": "कौन सा डेटा एकत्र करता है",
        "collect?": "एकत्र करता है?",
        "Is": "क्या",
        "secure?": "सुरक्षित है?",
        "Full analysis:": "पूर्ण विश्लेषण:",
        "Privacy Report": "गोपनीयता रिपोर्ट",
        "Privacy review": "गोपनीयता समीक्षा",
        "Security Report": "सुरक्षा रिपोर्ट",
        # Dimensions
        "Security": "सुरक्षा",
        "Privacy": "गोपनीयता",
        "Reliability": "विश्वसनीयता",
        "Transparency": "पारदर्शिता",
        "Maintenance": "रखरखाव",
        "Overall Trust": "समग्र विश्वास",
        "Composite trust score": "समग्र विश्वास स्कोर",
        "across all available signals": "सभी उपलब्ध संकेतों में",
        # Methodology
        "Nerq analyzes over 7.5 million entities across 26 registries": "Nerq 26 रजिस्ट्री में 7.5 मिलियन से अधिक इकाइयों का विश्लेषण करता है",
        "using the same methodology, enabling direct cross-entity comparison": "एक ही कार्यप्रणाली का उपयोग करके, इकाइयों के बीच सीधी तुलना संभव बनाता है",
        "Scores are updated continuously as new data becomes available": "नया डेटा उपलब्ध होने पर स्कोर लगातार अपडेट किए जाते हैं",
        "This page was last reviewed on": "इस पेज की अंतिम समीक्षा की गई:",
        "Data version": "डेटा संस्करण",
        "Full methodology documentation": "पूर्ण कार्यप्रणाली दस्तावेज़",
        "Machine-readable data (JSON API)": "मशीन पठनीय डेटा (JSON API)",
        "Machine-readable data (JSON)": "मशीन पठनीय डेटा (JSON)",
        # Meta / small text
        "Last analyzed:": "अंतिम विश्लेषण:",
        "Last updated": "अंतिम अपडेट",
        "Updated daily": "प्रतिदिन अपडेट",
        "Independent. Data-driven.": "स्वतंत्र। डेटा-आधारित।",
        "verified": "सत्यापित",
        "Data sourced from": "डेटा स्रोत:",
        "Based on": "आधारित",
        "dimensions": "आयाम",
        "independent data dimensions": "स्वतंत्र डेटा आयाम",
        "strong": "मजबूत",
        "moderate": "मध्यम",
        "weak": "कमजोर",
        "actively maintained": "सक्रिय रूप से अनुरक्षित",
        "moderately maintained": "मध्यम रूप से अनुरक्षित",
        "low maintenance activity": "कम रखरखाव गतिविधि",
        "well-documented": "अच्छी तरह से प्रलेखित",
        "partial documentation": "आंशिक दस्तावेज़ीकरण",
        "limited documentation": "सीमित दस्तावेज़ीकरण",
        "community adoption": "सामुदायिक स्वीकृति",
        "stars on": "स्टार्स",
        # Cross-links
        "Safety": "सुरक्षा",
        "Legit?": "विश्वसनीय?",
        "Scam?": "धोखाधड़ी?",
        "Review": "समीक्षा",
        "Alternatives": "विकल्प",
        "Compare": "तुलना करें",
        "Best in Category": "श्रेणी में सर्वश्रेष्ठ",
        "Who Owns?": "स्वामित्व किसका?",
        "What Is?": "क्या है?",
        "Sells Data?": "डेटा बेचता है?",
        "Hacked?": "हैक हुआ?",
        "Safe for Kids?": "बच्चों के लिए सुरक्षित?",
        "Pros &amp; Cons": "फायदे &amp; नुकसान",
        # FAQ answers
        "Nerq Verified — meets the 70+ trust threshold.": "Nerq सत्यापित — 70+ विश्वास सीमा को पूरा करता है।",
        "Below the Nerq Verified threshold of 70.": "Nerq सत्यापित सीमा 70 से नीचे।",
        "Has not yet reached the Nerq Verified threshold of 70.": "अभी तक Nerq सत्यापित सीमा 70 तक नहीं पहुंचा है।",
        "Strongest signal:": "सबसे मजबूत संकेत:",
        "Score based on": "स्कोर आधारित",
        "security": "सुरक्षा",
        "maintenance": "रखरखाव",
        "popularity": "लोकप्रियता",
        "documentation": "दस्तावेज़ीकरण",
        "compliance": "अनुपालन",
        # Verdict box
        "Safe": "सुरक्षित",
        "Use Caution": "सावधानी",
        "Avoid": "बचें",
        # Long text patterns
        "is a Node.js package": "एक Node.js पैकेज है",
        "is a Python package": "एक Python पैकेज है",
        "is a Rust crate": "एक Rust crate है",
        "is a Chrome extension": "एक Chrome एक्सटेंशन है",
        "is a Firefox extension": "एक Firefox एक्सटेंशन है",
        "is a VS Code extension": "एक VS Code एक्सटेंशन है",
        "is a WordPress plugin": "एक WordPress प्लगइन है",
        "is a iOS app": "एक iOS ऐप है",
        "is a Android app": "एक Android ऐप है",
        "is a VPN service": "एक VPN सेवा है",
        "is a game": "एक गेम है",
        "is a website": "एक वेबसाइट है",
        "is a SaaS platform": "एक SaaS प्लेटफॉर्म है",
        "is a dietary supplement": "एक आहार अनुपूरक है",
        "is a cosmetic ingredient": "एक कॉस्मेटिक सामग्री है",
        "is a food": "एक खाद्य सामग्री है",
        "is a travel destination": "एक यात्रा गंतव्य है",
        "is a nonprofit organization": "एक गैर-लाभकारी संगठन है",
        "with a Nerq Trust Score of": "Nerq विश्वास स्कोर के साथ",
        "with a Nerq Safety Score of": "Nerq सुरक्षा स्कोर के साथ",
        "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "सुरक्षा, रखरखाव और सामुदायिक स्वीकृति में मजबूत संकेतों के साथ Nerq विश्वास सीमा को पूरा करता है",
        "It has moderate trust signals but shows some areas of concern": "मध्यम विश्वास संकेत हैं, लेकिन कुछ चिंताजनक क्षेत्र भी हैं",
        "It has below-average trust signals with significant gaps": "औसत से कम विश्वास संकेत और महत्वपूर्ण अंतराल हैं",
        "review the full report below for specific considerations": "विशिष्ट विचारों के लिए नीचे पूरी रिपोर्ट देखें",
        "This score is based on automated analysis of security, maintenance, community, and quality signals.": "यह स्कोर सुरक्षा, रखरखाव, समुदाय और गुणवत्ता संकेतों के स्वचालित विश्लेषण पर आधारित है।",
        "You can also check the trust score via API:": "आप API के माध्यम से भी विश्वास स्कोर जांच सकते हैं:",
        "As a development package": "एक डेवलपमेंट पैकेज के रूप में",
        "does not directly collect end-user personal data": "अंतिम-उपयोगकर्ता का व्यक्तिगत डेटा सीधे एकत्र नहीं करता",
        "However, applications built with it may collect data depending on implementation": "हालांकि, इससे बनाए गए एप्लिकेशन कार्यान्वयन के आधार पर डेटा एकत्र कर सकते हैं",
        "Review the package's dependencies for potential supply chain risks": "संभावित आपूर्ति श्रृंखला जोखिमों के लिए पैकेज की निर्भरताओं की जांच करें",
        "License information not available": "लाइसेंस जानकारी उपलब्ध नहीं",
        "Open-source packages allow independent security review of the source code": "ओपन-सोर्स पैकेज स्रोत कोड की स्वतंत्र सुरक्षा समीक्षा की अनुमति देते हैं",
        "to check for vulnerabilities": "कमजोरियों की जांच के लिए",
        "Review the": "जांचें",
        "GitHub repository for recent commits": "हालिया कमिट के लिए GitHub रिपॉजिटरी",
        "dependency vulnerabilities, malicious packages, typosquatting": "निर्भरता कमजोरियां, दुर्भावनापूर्ण पैकेज, typosquatting",
        "Run your package manager's audit command": "अपने पैकेज मैनेजर का audit कमांड चलाएं",
        "to check for known vulnerabilities in your dependency tree": "अपनी निर्भरता वृक्ष में ज्ञात कमजोरियों की जांच के लिए",
        "This meets the recommended security threshold for production use": "यह प्रोडक्शन उपयोग के लिए अनुशंसित सुरक्षा सीमा को पूरा करता है",
        "Nerq monitors this entity against NVD, OSV.dev, and registry-specific vulnerability databases": "Nerq इस इकाई को NVD, OSV.dev और रजिस्ट्री-विशिष्ट कमजोरी डेटाबेस के विरुद्ध मॉनिटर करता है",
        "for ongoing security assessment": "निरंतर सुरक्षा मूल्यांकन के लिए",
        "Yes, it is safe to use.": "हां, यह उपयोग के लिए सुरक्षित है।",
        "Use with some caution.": "सावधानी से उपयोग करें।",
        "Exercise caution.": "सावधानी बरतें।",
        "Significant trust concerns.": "महत्वपूर्ण विश्वास संबंधी चिंताएं।",
        "maintained by": "द्वारा अनुरक्षित",
        "is computed from": "से गणना की गई है",
        "The score reflects": "स्कोर प्रतिबिंबित करता है",
        "independent dimensions": "स्वतंत्र आयाम",
        "Each dimension is weighted equally to produce the composite trust score": "समग्र विश्वास स्कोर बनाने के लिए प्रत्येक आयाम को समान भार दिया गया है",
        "No reviews yet.": "अभी तक कोई समीक्षा नहीं।",
        "Be the first to review": "पहली समीक्षा लिखें",
        "Write a review": "समीक्षा लिखें",
        "Higher-rated": "उच्च-रेटेड",
        "you may want to consider:": "जिन्हें आप विचार करना चाह सकते हैं:",
        "under assessment": "मूल्यांकन के अंतर्गत",
        # Health disclaimers
        "Important Notice:": "महत्वपूर्ण सूचना:",
        "educational and informational purposes only": "केवल शैक्षिक और सूचनात्मक उद्देश्यों के लिए",
        "does not constitute medical advice": "चिकित्सा सलाह नहीं है",
        "Consult a qualified healthcare professional": "किसी योग्य स्वास्थ्य पेशेवर से परामर्श लें",
        "Full health disclaimer": "पूर्ण स्वास्थ्य अस्वीकरण",
        "Full disclaimer": "पूर्ण अस्वीकरण",
    },
    "ru": {
        "It is ": "Это ",
        "Is NordVPN safe": "Безопасен ли NordVPN",
        "What is NordVPN": "Что такое NordVPN",
        "Does NordVPN log my data": "Записывает ли NordVPN мои данные",
        "What are the best alternatives to NordVPN": "Лучшие альтернативы NordVPN",
        "NordVPN vs alternatives: which is safer": "NordVPN vs альтернативы: что безопаснее",
        "trust score?": "оценка доверия?",
        "Scores update as new data becomes available": "Баллы обновляются при появлении новых данных",
        "In the vpn category": "В категории VPN",
        "full safety report for detailed privacy analysis": "полный отчёт по безопасности для детального анализа конфиденциальности",
        "jurisdiction databases, independent audit reports, protocol analysis, and incident history": "базы данных юрисдикций, независимые аудиторские отчёты, анализ протоколов и история инцидентов",
        "has undergone third-party security audits verifying its infrastructure and no-logs claims": "прошёл сторонние аудиты безопасности, подтверждающие инфраструктуру и заявления о неведении журналов",
        "widely used VPN service": "широко используемый VPN-сервис",
        "multiple public sources including package registries, GitHub, NVD, OSV.dev, and OpenSSF Scorecard": "множественные публичные источники, включая реестры пакетов, GitHub, NVD, OSV.dev и OpenSSF Scorecard",
        "What does a Nerq Trust Score": "Что означает Nerq Trust Score",
        "Are these safest": "Эти самые безопасные",
        "How are safest": "Как самые безопасные",
        "The #1 safest": "Самый безопасный №1",
        "The #1": "№1",
        "According to Nerq": "Согласно Nerq",
        "How are": "Как",
        "What are the best": "Какие лучшие",
        "Logging policy": "Политика ведения журналов",
        "Safety Guide": "Руководство по безопасности",
        "passes trust threshold": "проходит порог доверия",
        "Recommended for use": "Рекомендуется к использованию",
        "This score is based on automated analysis of security, maintenance, community, and quality signals": "Этот балл основан на автоматическом анализе сигналов безопасности, обслуживания, сообщества и качества",
        "According to independent audit reports": "Согласно независимым аудиторским отчётам",
        "No known data breaches associated with this service": "Известных утечек данных, связанных с этим сервисом, не обнаружено",
        "This is a strong positive signal": "Это сильный положительный сигнал",
        "logging policy": "политика ведения журналов",
        "Full analysis": "Полный анализ",
        "Server infrastructure": "Серверная инфраструктура",
        "It is recommended": "Рекомендуется",
        "most VPN providers have not been independently audited": "большинство VPN-провайдеров не прошли независимый аудит",
        "Nerq analyzes over": "Nerq анализирует более",
        "is based in": "базируется в",
        "outside all Eyes surveillance alliances": "за пределами всех альянсов наблюдения Eyes",
        "a privacy advantage": "преимущество конфиденциальности",
        "has been independently audited to verify its privacy claims": "прошёл независимый аудит для подтверждения заявлений о конфиденциальности",
        "Serving": "Обслуживает",
        "Related Safety Rankings": "Связанные рейтинги безопасности",
        "Complete Your Privacy Setup": "Завершите настройку конфиденциальности",
        "Browse Categories": "Просмотр категорий",
        "Safest VPNs": "Самые безопасные VPN",
        "Most Private Apps": "Самые приватные приложения",
        "Recently Analyzed": "Недавно проанализировано",
        "What are the best alternatives to": "Какие лучшие альтернативы",
        "which is safer": "что безопаснее",
        "logging practices": "практики ведения журналов",
        "ownership transparency": "прозрачность владения",
        "Popular in": "Популярное в",
        "Popularity": "Популярность",
        "Not Yet Analyzed": "Ещё не проанализировано",
        # ── Vertical-specific strings ──
        "Privacy Assessment": "Оценка конфиденциальности",
        "Breach History": "История утечек",
        "Encryption": "Шифрование",
        "Build Your Security Stack": "Соберите свой набор безопасности",
        "Best VPNs": "Лучшие VPN",
        "Best Password Managers": "Лучшие менеджеры паролей",
        "Best Antivirus": "Лучший антивирус",
        "Security Assessment": "Оценка безопасности",
        "Security & Compliance": "Безопасность и соответствие",
        "Combine these tools for comprehensive protection:": "Объедините эти инструменты для полной защиты:",
        # Title / H1
        "Independent Trust & Security Analysis": "Независимый анализ доверия и безопасности",
        "Independent Trust &amp; Security Analysis": "Независимый анализ доверия и безопасности",
        # Verdicts
        "Yes, {name} is safe to use.": "Да, {name} безопасен для использования.",
        "Use {name} with some caution.": "Используйте {name} с осторожностью.",
        "Exercise caution with {name}.": "Будьте осторожны с {name}.",
        "{name} has significant trust concerns.": "{name} имеет серьёзные проблемы с доверием.",
        "Passes Nerq Verified threshold": "Соответствует верифицированному порогу Nerq",
        "Below Nerq Verified threshold": "Ниже верифицированного порога Nerq",
        "Significant trust gaps detected": "Обнаружены значительные пробелы в доверии",
        # Section headings
        "Trust Score Breakdown": "Детали рейтинга доверия",
        "Safety Score Breakdown": "Детали рейтинга безопасности",
        "Key Findings": "Основные выводы",
        "Key Safety Findings": "Основные выводы по безопасности",
        "Detailed Score Analysis": "Подробный анализ рейтинга",
        "Frequently Asked Questions": "Часто задаваемые вопросы",
        "Safer Alternatives": "Более безопасные альтернативы",
        "Popular Alternatives": "Популярные альтернативы",
        "Community Reviews": "Отзывы сообщества",
        "Regulatory Compliance": "Соответствие нормативам",
        "How we calculated this score": "Как мы рассчитали этот рейтинг",
        "What We Know About": "Что мы знаем о",
        # Safety Guide
        "Safety Guide:": "Руководство по безопасности:",
        "What is": "Что такое",
        "How to Verify Safety": "Как проверить безопасность",
        "Key Safety Concerns for": "Основные проблемы безопасности для",
        "Trust Assessment": "Оценка доверия",
        "Key Takeaways": "Основные выводы",
        "Recommended for use — passes trust threshold.": "Рекомендуется к использованию — соответствует порогу доверия.",
        "Review carefully before use — below trust threshold.": "Тщательно проверьте перед использованием — ниже порога доверия.",
        "Always verify independently using the": "Всегда проверяйте независимо с помощью",
        "When evaluating any": "При оценке любого",
        "watch for:": "обратите внимание на:",
        # Cross-product
        "Across Platforms": "На других платформах",
        "across platforms": "на других платформах",
        "Same developer/company in other registries:": "Тот же разработчик/компания в других реестрах:",
        # King sections
        "What data does": "Какие данные собирает",
        "collect?": "?",
        "Is": "Безопасен ли",
        "secure?": "?",
        "Full analysis:": "Полный анализ:",
        "Privacy Report": "Отчёт о конфиденциальности",
        "Privacy review": "Обзор конфиденциальности",
        "Security Report": "Отчёт о безопасности",
        # Dimensions
        "Security": "Безопасность",
        "Privacy": "Конфиденциальность",
        "Reliability": "Надёжность",
        "Transparency": "Прозрачность",
        "Maintenance": "Обслуживание",
        "Overall Trust": "Общее доверие",
        "Composite trust score": "Сводный рейтинг доверия",
        "across all available signals": "по всем доступным сигналам",
        # Methodology
        "Nerq analyzes over 7.5 million entities across 26 registries": "Nerq анализирует более 7,5 миллиона сущностей в 26 реестрах",
        "using the same methodology, enabling direct cross-entity comparison": "используя единую методологию, что позволяет проводить прямое сравнение между сущностями",
        "Scores are updated continuously as new data becomes available": "Рейтинги обновляются непрерывно по мере поступления новых данных",
        "This page was last reviewed on": "Эта страница последний раз проверена:",
        "Data version": "Версия данных",
        "Full methodology documentation": "Полная документация методологии",
        "Machine-readable data (JSON API)": "Машинночитаемые данные (JSON API)",
        "Machine-readable data (JSON)": "Машинночитаемые данные (JSON)",
        # Meta / small text
        "Last analyzed:": "Последний анализ:",
        "Last updated": "Последнее обновление",
        "Updated daily": "Обновляется ежедневно",
        "Independent. Data-driven.": "Независимо. На основе данных.",
        "verified": "верифицировано",
        "Data sourced from": "Данные из",
        "Based on": "На основе",
        "dimensions": "показателей",
        "independent data dimensions": "независимых показателей данных",
        "strong": "сильный",
        "moderate": "умеренный",
        "weak": "слабый",
        "actively maintained": "активно поддерживается",
        "moderately maintained": "умеренно поддерживается",
        "low maintenance activity": "низкая активность поддержки",
        "well-documented": "хорошо задокументировано",
        "partial documentation": "частичная документация",
        "limited documentation": "ограниченная документация",
        "community adoption": "принятие сообществом",
        "stars on": "звёзд на",
        # Cross-links
        "Safety": "Безопасность",
        "Legit?": "Надёжный?",
        "Scam?": "Мошенничество?",
        "Review": "Отзыв",
        "Alternatives": "Альтернативы",
        "Compare": "Сравнить",
        "Best in Category": "Лучший в категории",
        "Who Owns?": "Кто владелец?",
        "What Is?": "Что это?",
        "Sells Data?": "Продаёт данные?",
        "Hacked?": "Взломан?",
        "Safe for Kids?": "Безопасен для детей?",
        "Pros &amp; Cons": "Плюсы &amp; Минусы",
        # FAQ answers
        "Nerq Verified — meets the 70+ trust threshold.": "Nerq верифицировано — соответствует порогу доверия 70+.",
        "Below the Nerq Verified threshold of 70.": "Ниже верифицированного порога Nerq в 70.",
        "Has not yet reached the Nerq Verified threshold of 70.": "Ещё не достиг верифицированного порога Nerq в 70.",
        "Strongest signal:": "Самый сильный сигнал:",
        "Score based on": "Рейтинг основан на",
        "security": "безопасность",
        "maintenance": "обслуживание",
        "popularity": "популярность",
        "documentation": "документация",
        "compliance": "соответствие",
        # Verdict box
        "Safe": "Безопасно",
        "Use Caution": "Осторожно",
        "Avoid": "Избегать",
        # Long text patterns
        "is a Node.js package": "— это пакет Node.js",
        "is a Python package": "— это пакет Python",
        "is a Rust crate": "— это Rust crate",
        "is a Chrome extension": "— это расширение Chrome",
        "is a Firefox extension": "— это расширение Firefox",
        "is a VS Code extension": "— это расширение VS Code",
        "is a WordPress plugin": "— это плагин WordPress",
        "is a iOS app": "— это приложение для iOS",
        "is a Android app": "— это приложение для Android",
        "is a VPN service": "— это VPN-сервис",
        "is a game": "— это игра",
        "is a website": "— это сайт",
        "is a SaaS platform": "— это SaaS-платформа",
        "is a dietary supplement": "— это пищевая добавка",
        "is a cosmetic ingredient": "— это косметический ингредиент",
        "is a food": "— это продукт питания",
        "is a travel destination": "— это туристическое направление",
        "is a nonprofit organization": "— это некоммерческая организация",
        "with a Nerq Trust Score of": "с рейтингом доверия Nerq",
        "with a Nerq Safety Score of": "с рейтингом безопасности Nerq",
        "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "Соответствует порогу доверия Nerq с сильными сигналами в области безопасности, обслуживания и принятия сообществом",
        "It has moderate trust signals but shows some areas of concern": "Умеренные сигналы доверия, но есть отдельные области, требующие внимания",
        "It has below-average trust signals with significant gaps": "Сигналы доверия ниже среднего со значительными пробелами",
        "review the full report below for specific considerations": "ознакомьтесь с полным отчётом ниже для уточнения",
        "This score is based on automated analysis of security, maintenance, community, and quality signals.": "Этот рейтинг основан на автоматическом анализе сигналов безопасности, обслуживания, сообщества и качества.",
        "You can also check the trust score via API:": "Вы также можете проверить рейтинг доверия через API:",
        "As a development package": "Как пакет для разработки",
        "does not directly collect end-user personal data": "не собирает напрямую персональные данные конечных пользователей",
        "However, applications built with it may collect data depending on implementation": "Однако приложения, созданные с его помощью, могут собирать данные в зависимости от реализации",
        "Review the package's dependencies for potential supply chain risks": "Проверьте зависимости пакета на возможные риски цепочки поставок",
        "License information not available": "Информация о лицензии недоступна",
        "Open-source packages allow independent security review of the source code": "Пакеты с открытым исходным кодом позволяют проводить независимую проверку безопасности кода",
        "to check for vulnerabilities": "для проверки уязвимостей",
        "Review the": "Проверьте",
        "GitHub repository for recent commits": "репозиторий GitHub на наличие последних коммитов",
        "dependency vulnerabilities, malicious packages, typosquatting": "уязвимости зависимостей, вредоносные пакеты, тайпосквоттинг",
        "Run your package manager's audit command": "Запустите команду аудита вашего менеджера пакетов",
        "to check for known vulnerabilities in your dependency tree": "для проверки известных уязвимостей в вашем дереве зависимостей",
        "This meets the recommended security threshold for production use": "Соответствует рекомендуемому порогу безопасности для использования в продакшене",
        "Nerq monitors this entity against NVD, OSV.dev, and registry-specific vulnerability databases": "Nerq отслеживает эту сущность по базам NVD, OSV.dev и реестровым базам уязвимостей",
        "for ongoing security assessment": "для непрерывной оценки безопасности",
        "Yes, it is safe to use.": "Да, безопасно использовать.",
        "Use with some caution.": "Используйте с осторожностью.",
        "Exercise caution.": "Будьте осторожны.",
        "Significant trust concerns.": "Серьёзные проблемы с доверием.",
        "maintained by": "поддерживается",
        "is computed from": "вычисляется из",
        "The score reflects": "Рейтинг отражает",
        "independent dimensions": "независимых показателей",
        "Each dimension is weighted equally to produce the composite trust score": "Каждый показатель имеет равный вес в сводном рейтинге доверия",
        "No reviews yet.": "Пока нет отзывов.",
        "Be the first to review": "Станьте первым, кто оставит отзыв",
        "Write a review": "Написать отзыв",
        "Higher-rated": "С более высоким рейтингом",
        "you may want to consider:": "которые стоит рассмотреть:",
        "under assessment": "на стадии оценки",
        # Health disclaimers
        "Important Notice:": "Важное уведомление:",
        "educational and informational purposes only": "только в образовательных и информационных целях",
        "does not constitute medical advice": "не является медицинской консультацией",
        "Consult a qualified healthcare professional": "Проконсультируйтесь с квалифицированным специалистом здравоохранения",
        "Full health disclaimer": "Полный медицинский отказ от ответственности",
        "Full disclaimer": "Полный отказ от ответственности",
    },
    "pl": {
        "It is ": "To jest ",
        "Is NordVPN safe": "Czy NordVPN jest bezpieczny",
        "What is NordVPN": "Czym jest NordVPN",
        "Does NordVPN log my data": "Czy NordVPN rejestruje moje dane",
        "What are the best alternatives to NordVPN": "Najlepsze alternatywy dla NordVPN",
        "NordVPN vs alternatives: which is safer": "NordVPN vs alternatywy: co jest bezpieczniejsze",
        "trust score?": "wynik zaufania?",
        "Scores update as new data becomes available": "Oceny aktualizują się, gdy pojawiają się nowe dane",
        "In the vpn category": "W kategorii VPN",
        "full safety report for detailed privacy analysis": "pełny raport bezpieczeństwa do szczegółowej analizy prywatności",
        "jurisdiction databases, independent audit reports, protocol analysis, and incident history": "bazy danych jurysdykcji, niezależne raporty audytowe, analiza protokołów i historia incydentów",
        "has undergone third-party security audits verifying its infrastructure and no-logs claims": "przeszedł audyty bezpieczeństwa stron trzecich weryfikujące infrastrukturę i twierdzenia o braku logowania",
        "widely used VPN service": "powszechnie używana usługa VPN",
        "multiple public sources including package registries, GitHub, NVD, OSV.dev, and OpenSSF Scorecard": "wiele źródeł publicznych, w tym rejestry pakietów, GitHub, NVD, OSV.dev i OpenSSF Scorecard",
        "What does a Nerq Trust Score": "Co oznacza Nerq Trust Score",
        "Are these safest": "Czy te są najbezpieczniejsze",
        "How are safest": "Jak są najbezpieczniejsze",
        "The #1 safest": "Najbezpieczniejszy nr 1",
        "The #1": "Nr 1",
        "According to Nerq": "Według Nerq",
        "How are": "Jak są",
        "What are the best": "Jakie są najlepsze",
        "Logging policy": "Polityka rejestrowania",
        "Safety Guide": "Przewodnik bezpieczeństwa",
        "passes trust threshold": "przekracza próg zaufania",
        "Recommended for use": "Zalecane do użytku",
        "This score is based on automated analysis of security, maintenance, community, and quality signals": "Ten wynik opiera się na automatycznej analizie sygnałów bezpieczeństwa, konserwacji, społeczności i jakości",
        "According to independent audit reports": "Według niezależnych raportów audytowych",
        "No known data breaches associated with this service": "Brak znanych naruszeń danych związanych z tą usługą",
        "This is a strong positive signal": "To silny pozytywny sygnał",
        "logging policy": "polityka rejestrowania",
        "Full analysis": "Pełna analiza",
        "Server infrastructure": "Infrastruktura serwerów",
        "It is recommended": "Zalecane",
        "most VPN providers have not been independently audited": "większość dostawców VPN nie została niezależnie zbadana",
        "Nerq analyzes over": "Nerq analizuje ponad",
        "is based in": "ma siedzibę w",
        "outside all Eyes surveillance alliances": "poza wszystkimi sojuszami inwigilacji Eyes",
        "a privacy advantage": "zaleta prywatności",
        "has been independently audited to verify its privacy claims": "został niezależnie zbadany w celu weryfikacji swoich twierdzeń o prywatności",
        "Serving": "Obsługuje",
        "Related Safety Rankings": "Powiązane rankingi bezpieczeństwa",
        "Complete Your Privacy Setup": "Uzupełnij konfigurację prywatności",
        "Browse Categories": "Przeglądaj kategorie",
        "Safest VPNs": "Najbezpieczniejsze VPN",
        "Most Private Apps": "Najbardziej prywatne aplikacje",
        "Recently Analyzed": "Ostatnio przeanalizowane",
        "What are the best alternatives to": "Jakie są najlepsze alternatywy dla",
        "which is safer": "co jest bezpieczniejsze",
        "logging practices": "praktyki rejestrowania",
        "ownership transparency": "przejrzystość własności",
        "Popular in": "Popularne w",
        "Popularity": "Popularność",
        "Not Yet Analyzed": "Jeszcze nie przeanalizowano",
        # ── Vertical-specific strings ──
        "Privacy Assessment": "Ocena prywatności",
        "Breach History": "Historia naruszeń",
        "Encryption": "Szyfrowanie",
        "Build Your Security Stack": "Zbuduj swój pakiet bezpieczeństwa",
        "Best VPNs": "Najlepsze VPN",
        "Best Password Managers": "Najlepsi menedżerowie haseł",
        "Best Antivirus": "Najlepszy antywirus",
        "Security Assessment": "Ocena bezpieczeństwa",
        "Security & Compliance": "Bezpieczeństwo i zgodność",
        "Combine these tools for comprehensive protection:": "Połącz te narzędzia dla kompleksowej ochrony:",
        # Title / H1
        "Independent Trust & Security Analysis": "Niezależna analiza zaufania i bezpieczeństwa",
        "Independent Trust &amp; Security Analysis": "Niezależna analiza zaufania i bezpieczeństwa",
        # Verdicts
        "Yes, {name} is safe to use.": "Tak, {name} jest bezpieczny w użyciu.",
        "Use {name} with some caution.": "Używaj {name} z ostrożnością.",
        "Exercise caution with {name}.": "Zachowaj ostrożność z {name}.",
        "{name} has significant trust concerns.": "{name} ma poważne problemy z zaufaniem.",
        "Passes Nerq Verified threshold": "Spełnia zweryfikowany próg Nerq",
        "Below Nerq Verified threshold": "Poniżej zweryfikowanego progu Nerq",
        "Significant trust gaps detected": "Wykryto znaczące luki w zaufaniu",
        # Section headings
        "Trust Score Breakdown": "Szczegóły wyniku zaufania",
        "Safety Score Breakdown": "Szczegóły wyniku bezpieczeństwa",
        "Key Findings": "Kluczowe ustalenia",
        "Key Safety Findings": "Kluczowe ustalenia dotyczące bezpieczeństwa",
        "Detailed Score Analysis": "Szczegółowa analiza wyniku",
        "Frequently Asked Questions": "Często zadawane pytania",
        "Safer Alternatives": "Bezpieczniejsze alternatywy",
        "Popular Alternatives": "Popularne alternatywy",
        "Community Reviews": "Opinie społeczności",
        "Regulatory Compliance": "Zgodność z przepisami",
        "How we calculated this score": "Jak obliczyliśmy ten wynik",
        "What We Know About": "Co wiemy o",
        # Safety Guide
        "Safety Guide:": "Przewodnik bezpieczeństwa:",
        "What is": "Czym jest",
        "How to Verify Safety": "Jak zweryfikować bezpieczeństwo",
        "Key Safety Concerns for": "Główne problemy bezpieczeństwa dla",
        "Trust Assessment": "Ocena zaufania",
        "Key Takeaways": "Kluczowe wnioski",
        "Recommended for use — passes trust threshold.": "Zalecany — spełnia próg zaufania.",
        "Review carefully before use — below trust threshold.": "Sprawdź uważnie przed użyciem — poniżej progu zaufania.",
        "Always verify independently using the": "Zawsze weryfikuj niezależnie przy użyciu",
        "When evaluating any": "Oceniając każdy",
        "watch for:": "zwróć uwagę na:",
        # Cross-product
        "Across Platforms": "Na innych platformach",
        "across platforms": "na innych platformach",
        "Same developer/company in other registries:": "Ten sam deweloper/firma w innych rejestrach:",
        # King sections
        "What data does": "Jakie dane zbiera",
        "collect?": "?",
        "Is": "Czy",
        "secure?": "jest bezpieczny?",
        "Full analysis:": "Pełna analiza:",
        "Privacy Report": "Raport prywatności",
        "Privacy review": "Przegląd prywatności",
        "Security Report": "Raport bezpieczeństwa",
        # Dimensions
        "Security": "Bezpieczeństwo",
        "Privacy": "Prywatność",
        "Reliability": "Niezawodność",
        "Transparency": "Przejrzystość",
        "Maintenance": "Konserwacja",
        "Overall Trust": "Ogólne zaufanie",
        "Composite trust score": "Łączny wynik zaufania",
        "across all available signals": "ze wszystkich dostępnych sygnałów",
        # Methodology
        "Nerq analyzes over 7.5 million entities across 26 registries": "Nerq analizuje ponad 7,5 miliona podmiotów w 26 rejestrach",
        "using the same methodology, enabling direct cross-entity comparison": "przy użyciu tej samej metodologii, umożliwiając bezpośrednie porównanie między podmiotami",
        "Scores are updated continuously as new data becomes available": "Wyniki są na bieżąco aktualizowane w miarę dostępności nowych danych",
        "This page was last reviewed on": "Ta strona była ostatnio przeglądana:",
        "Data version": "Wersja danych",
        "Full methodology documentation": "Pełna dokumentacja metodologii",
        "Machine-readable data (JSON API)": "Dane odczytywalne maszynowo (JSON API)",
        "Machine-readable data (JSON)": "Dane odczytywalne maszynowo (JSON)",
        # Meta / small text
        "Last analyzed:": "Ostatnia analiza:",
        "Last updated": "Ostatnia aktualizacja",
        "Updated daily": "Aktualizowane codziennie",
        "Independent. Data-driven.": "Niezależne. Oparte na danych.",
        "verified": "zweryfikowane",
        "Data sourced from": "Dane pochodzą z",
        "Based on": "Na podstawie",
        "dimensions": "wymiarów",
        "independent data dimensions": "niezależnych wymiarów danych",
        "strong": "silny",
        "moderate": "umiarkowany",
        "weak": "słaby",
        "actively maintained": "aktywnie utrzymywany",
        "moderately maintained": "umiarkowanie utrzymywany",
        "low maintenance activity": "niska aktywność utrzymania",
        "well-documented": "dobrze udokumentowany",
        "partial documentation": "częściowa dokumentacja",
        "limited documentation": "ograniczona dokumentacja",
        "community adoption": "przyjęcie przez społeczność",
        "stars on": "gwiazdek na",
        # Cross-links
        "Safety": "Bezpieczeństwo",
        "Legit?": "Wiarygodny?",
        "Scam?": "Oszustwo?",
        "Review": "Opinia",
        "Alternatives": "Alternatywy",
        "Compare": "Porównaj",
        "Best in Category": "Najlepszy w kategorii",
        "Who Owns?": "Kto jest właścicielem?",
        "What Is?": "Co to jest?",
        "Sells Data?": "Sprzedaje dane?",
        "Hacked?": "Zhakowany?",
        "Safe for Kids?": "Bezpieczny dla dzieci?",
        "Pros &amp; Cons": "Zalety &amp; Wady",
        # FAQ answers
        "Nerq Verified — meets the 70+ trust threshold.": "Nerq zweryfikowany — spełnia próg zaufania 70+.",
        "Below the Nerq Verified threshold of 70.": "Poniżej zweryfikowanego progu Nerq wynoszącego 70.",
        "Has not yet reached the Nerq Verified threshold of 70.": "Nie osiągnął jeszcze zweryfikowanego progu Nerq wynoszącego 70.",
        "Strongest signal:": "Najsilniejszy sygnał:",
        "Score based on": "Wynik oparty na",
        "security": "bezpieczeństwo",
        "maintenance": "konserwacja",
        "popularity": "popularność",
        "documentation": "dokumentacja",
        "compliance": "zgodność",
        # Verdict box
        "Safe": "Bezpieczny",
        "Use Caution": "Ostrożność",
        "Avoid": "Unikać",
        # Long text patterns
        "is a Node.js package": "to pakiet Node.js",
        "is a Python package": "to pakiet Python",
        "is a Rust crate": "to biblioteka Rust",
        "is a Chrome extension": "to rozszerzenie Chrome",
        "is a Firefox extension": "to rozszerzenie Firefox",
        "is a VS Code extension": "to rozszerzenie VS Code",
        "is a WordPress plugin": "to wtyczka WordPress",
        "is a iOS app": "to aplikacja iOS",
        "is a Android app": "to aplikacja Android",
        "is a VPN service": "to usługa VPN",
        "is a game": "to gra",
        "is a website": "to strona internetowa",
        "is a SaaS platform": "to platforma SaaS",
        "is a dietary supplement": "to suplement diety",
        "is a cosmetic ingredient": "to składnik kosmetyczny",
        "is a food": "to produkt spożywczy",
        "is a travel destination": "to cel podróży",
        "is a nonprofit organization": "to organizacja non-profit",
        "with a Nerq Trust Score of": "z wynikiem zaufania Nerq",
        "with a Nerq Safety Score of": "z wynikiem bezpieczeństwa Nerq",
        "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "Spełnia próg zaufania Nerq z silnymi sygnałami w zakresie bezpieczeństwa, konserwacji i przyjęcia przez społeczność",
        "It has moderate trust signals but shows some areas of concern": "Ma umiarkowane sygnały zaufania, ale wykazuje pewne obszary budzące obawy",
        "It has below-average trust signals with significant gaps": "Ma poniżej przeciętne sygnały zaufania ze znaczącymi lukami",
        "review the full report below for specific considerations": "zapoznaj się z pełnym raportem poniżej, aby uzyskać szczegółowe informacje",
        "This score is based on automated analysis of security, maintenance, community, and quality signals.": "Ten wynik jest oparty na zautomatyzowanej analizie sygnałów bezpieczeństwa, konserwacji, społeczności i jakości.",
        "You can also check the trust score via API:": "Możesz również sprawdzić wynik zaufania przez API:",
        "As a development package": "Jako pakiet deweloperski",
        "does not directly collect end-user personal data": "nie zbiera bezpośrednio danych osobowych użytkowników końcowych",
        "However, applications built with it may collect data depending on implementation": "Jednak aplikacje zbudowane przy jego użyciu mogą zbierać dane w zależności od implementacji",
        "Review the package's dependencies for potential supply chain risks": "Sprawdź zależności pakietu pod kątem potencjalnych zagrożeń w łańcuchu dostaw",
        "License information not available": "Informacje o licencji niedostępne",
        "Open-source packages allow independent security review of the source code": "Pakiety open-source umożliwiają niezależny przegląd bezpieczeństwa kodu źródłowego",
        "to check for vulnerabilities": "aby sprawdzić podatności",
        "Review the": "Sprawdź",
        "GitHub repository for recent commits": "repozytorium GitHub pod kątem ostatnich zatwierdzeń",
        "dependency vulnerabilities, malicious packages, typosquatting": "podatności zależności, złośliwe pakiety, typosquatting",
        "Run your package manager's audit command": "Uruchom polecenie audytu menedżera pakietów",
        "to check for known vulnerabilities in your dependency tree": "aby sprawdzić znane podatności w drzewie zależności",
        "This meets the recommended security threshold for production use": "Spełnia zalecany próg bezpieczeństwa do użytku produkcyjnego",
        "Nerq monitors this entity against NVD, OSV.dev, and registry-specific vulnerability databases": "Nerq monitoruje ten podmiot względem NVD, OSV.dev i rejestrowych baz danych podatności",
        "for ongoing security assessment": "na potrzeby bieżącej oceny bezpieczeństwa",
        "Yes, it is safe to use.": "Tak, jest bezpieczny w użyciu.",
        "Use with some caution.": "Używaj z ostrożnością.",
        "Exercise caution.": "Zachowaj ostrożność.",
        "Significant trust concerns.": "Poważne problemy z zaufaniem.",
        "maintained by": "utrzymywany przez",
        "is computed from": "jest obliczany z",
        "The score reflects": "Wynik odzwierciedla",
        "independent dimensions": "niezależnych wymiarów",
        "Each dimension is weighted equally to produce the composite trust score": "Każdy wymiar ma równą wagę w łącznym wyniku zaufania",
        "No reviews yet.": "Brak opinii.",
        "Be the first to review": "Bądź pierwszym, który oceni",
        "Write a review": "Napisz opinię",
        "Higher-rated": "Z wyższym wynikiem",
        "you may want to consider:": "które warto rozważyć:",
        "under assessment": "w trakcie oceny",
        # Health disclaimers
        "Important Notice:": "Ważna informacja:",
        "educational and informational purposes only": "wyłącznie do celów edukacyjnych i informacyjnych",
        "does not constitute medical advice": "nie stanowi porady medycznej",
        "Consult a qualified healthcare professional": "Skonsultuj się z wykwalifikowanym specjalistą ochrony zdrowia",
        "Full health disclaimer": "Pełne zastrzeżenie zdrowotne",
        "Full disclaimer": "Pełne zastrzeżenie",
    },
    "nl": {
        "It is ": "Het is ",
        "Is NordVPN safe": "Is NordVPN veilig",
        "What is NordVPN": "Wat is NordVPN",
        "Does NordVPN log my data": "Logt NordVPN mijn gegevens",
        "What are the best alternatives to NordVPN": "Wat zijn de beste alternatieven voor NordVPN",
        "NordVPN vs alternatives: which is safer": "NordVPN vs alternatieven: welke is veiliger",
        "trust score?": "vertrouwensscore?",
        "Scores update as new data becomes available": "Scores worden bijgewerkt wanneer nieuwe data beschikbaar komen",
        "In the vpn category": "In de VPN-categorie",
        "full safety report for detailed privacy analysis": "volledig veiligheidsrapport voor gedetailleerde privacyanalyse",
        "jurisdiction databases, independent audit reports, protocol analysis, and incident history": "jurisdictiedatabases, onafhankelijke auditrapporten, protocolanalyse en incidentgeschiedenis",
        "has undergone third-party security audits verifying its infrastructure and no-logs claims": "heeft onafhankelijke beveiligingsaudits ondergaan die de infrastructuur en no-logs-claims verifiëren",
        "widely used VPN service": "veelgebruikte VPN-service",
        "multiple public sources including package registries, GitHub, NVD, OSV.dev, and OpenSSF Scorecard": "meerdere openbare bronnen waaronder pakketregisters, GitHub, NVD, OSV.dev en OpenSSF Scorecard",
        "What does a Nerq Trust Score": "Wat betekent een Nerq Trust Score",
        "Are these safest": "Zijn deze de veiligste",
        "How are safest": "Hoe worden de veiligste",
        "The #1 safest": "De veiligste",
        "The #1": "De #1",
        "According to Nerq": "Volgens Nerq",
        "How are": "Hoe worden",
        "What are the best": "Wat zijn de beste",
        "Logging policy": "Logbeleid",
        "Safety Guide": "Veiligheidsgids",
        "passes trust threshold": "voldoet aan de vertrouwensdrempel",
        "Recommended for use": "Aanbevolen voor gebruik",
        "This score is based on automated analysis of security, maintenance, community, and quality signals": "Deze score is gebaseerd op geautomatiseerde analyse van beveiligings-, onderhouds-, community- en kwaliteitssignalen",
        "According to independent audit reports": "Volgens onafhankelijke auditrapportages",
        "No known data breaches associated with this service": "Geen bekende datalekken in verband met deze service",
        "This is a strong positive signal": "Dit is een sterk positief signaal",
        "logging policy": "logbeleid",
        "Full analysis": "Volledige analyse",
        "Server infrastructure": "Serverinfrastructuur",
        "It is recommended": "Het wordt aanbevolen",
        "most VPN providers have not been independently audited": "de meeste VPN-providers zijn niet onafhankelijk geauditeerd",
        "Nerq analyzes over": "Nerq analyseert meer dan",
        "is based in": "is gevestigd in",
        "outside all Eyes surveillance alliances": "buiten alle Eyes-surveillanceallianties",
        "a privacy advantage": "een privacyvoordeel",
        "has been independently audited to verify its privacy claims": "is onafhankelijk geauditeerd om zijn privacyclaims te verifiëren",
        "Serving": "Bedient",
        "Related Safety Rankings": "Gerelateerde veiligheidsrankings",
        "Complete Your Privacy Setup": "Voltooi uw privacy-instellingen",
        "Browse Categories": "Categorieën bekijken",
        "Safest VPNs": "Veiligste VPN's",
        "Most Private Apps": "Meest privé apps",
        "Recently Analyzed": "Recent geanalyseerd",
        "What are the best alternatives to": "Wat zijn de beste alternatieven voor",
        "which is safer": "welke is veiliger",
        "logging practices": "logpraktijken",
        "logging practices, jurisdiction, audit history, ownership transparency": "logpraktijken, jurisdictie, auditgeschiedenis, eigendomstransparantie",
        "ownership transparency": "eigendomstransparantie",
        "jurisdiction": "jurisdictie",
        "Panama jurisdiction": "Panama-jurisdictie",
        "Check jurisdiction": "Controleer jurisdictie",
        "non-allied jurisdictions are not subject to mandatory data retention laws or intelligence-sharing agreements": "niet-geallieerde jurisdicties zijn niet onderworpen aan verplichte gegevensretentiewetten of inlichtingenuitwisselingsovereenkomsten",
        "Popular in": "Populair in",
        "Popularity": "Populariteit",
        "Not Yet Analyzed": "Nog niet geanalyseerd",
        # ── Vertical-specific strings ──
        "Privacy Assessment": "Privacybeoordeling",
        "Breach History": "Inbreukgeschiedenis",
        "Encryption": "Versleuteling",
        "Build Your Security Stack": "Bouw uw beveiligingspakket",
        "Best VPNs": "Beste VPN's",
        "Best Password Managers": "Beste wachtwoordmanagers",
        "Best Antivirus": "Beste antivirus",
        "Security Assessment": "Veiligheidsbeoordeling",
        "Security & Compliance": "Beveiliging en naleving",
        "Combine these tools for comprehensive protection:": "Combineer deze tools voor uitgebreide bescherming:",
        # Title / H1
        "Independent Trust & Security Analysis": "Onafhankelijke vertrouwens- en beveiligingsanalyse",
        "Independent Trust &amp; Security Analysis": "Onafhankelijke vertrouwens- en beveiligingsanalyse",
        # Verdicts
        "Yes, {name} is safe to use.": "Ja, {name} is veilig om te gebruiken.",
        "Use {name} with some caution.": "Gebruik {name} met enige voorzichtigheid.",
        "Exercise caution with {name}.": "Wees voorzichtig met {name}.",
        "{name} has significant trust concerns.": "{name} heeft aanzienlijke vertrouwensproblemen.",
        "Passes Nerq Verified threshold": "Voldoet aan de geverifieerde drempel van Nerq",
        "Below Nerq Verified threshold": "Onder de geverifieerde drempel van Nerq",
        "Significant trust gaps detected": "Aanzienlijke vertrouwenslacunes gedetecteerd",
        # Section headings
        "Trust Score Breakdown": "Vertrouwensscore details",
        "Safety Score Breakdown": "Beveiligingsscore details",
        "Key Findings": "Belangrijkste bevindingen",
        "Key Safety Findings": "Belangrijkste beveiligingsbevindingen",
        "Detailed Score Analysis": "Gedetailleerde score-analyse",
        "Frequently Asked Questions": "Veelgestelde vragen",
        "Safer Alternatives": "Veiligere alternatieven",
        "Popular Alternatives": "Populaire alternatieven",
        "Community Reviews": "Beoordelingen van de gemeenschap",
        "Regulatory Compliance": "Naleving van regelgeving",
        "How we calculated this score": "Hoe we deze score hebben berekend",
        "What We Know About": "Wat we weten over",
        # Safety Guide
        "Safety Guide:": "Beveiligingsgids:",
        "What is": "Wat is",
        "How to Verify Safety": "Hoe de veiligheid te verifiëren",
        "Key Safety Concerns for": "Belangrijkste beveiligingsproblemen voor",
        "Trust Assessment": "Vertrouwensbeoordeling",
        "Key Takeaways": "Belangrijkste conclusies",
        "Recommended for use — passes trust threshold.": "Aanbevolen voor gebruik — voldoet aan de vertrouwensdrempel.",
        "Review carefully before use — below trust threshold.": "Controleer zorgvuldig voor gebruik — onder de vertrouwensdrempel.",
        "Always verify independently using the": "Controleer altijd onafhankelijk met behulp van de",
        "When evaluating any": "Bij het evalueren van elk",
        "watch for:": "let op:",
        # Cross-product
        "Across Platforms": "Op andere platforms",
        "across platforms": "op andere platforms",
        "Same developer/company in other registries:": "Dezelfde ontwikkelaar/bedrijf in andere registers:",
        # King sections
        "What data does": "Welke gegevens verzamelt",
        "collect?": "?",
        "Is": "Is",
        "secure?": "veilig?",
        "Full analysis:": "Volledige analyse:",
        "Privacy Report": "Privacyrapport",
        "Privacy review": "Privacybeoordeling",
        "Security Report": "Beveiligingsrapport",
        # Dimensions
        "Security": "Beveiliging",
        "Privacy": "Privacy",
        "Reliability": "Betrouwbaarheid",
        "Transparency": "Transparantie",
        "Maintenance": "Onderhoud",
        "Overall Trust": "Algeheel vertrouwen",
        "Composite trust score": "Samengestelde vertrouwensscore",
        "across all available signals": "op basis van alle beschikbare signalen",
        # Methodology
        "Nerq analyzes over 7.5 million entities across 26 registries": "Nerq analyseert meer dan 7,5 miljoen entiteiten in 26 registers",
        "using the same methodology, enabling direct cross-entity comparison": "met dezelfde methodologie, waardoor directe vergelijking tussen entiteiten mogelijk is",
        "Scores are updated continuously as new data becomes available": "Scores worden continu bijgewerkt naarmate er nieuwe gegevens beschikbaar komen",
        "This page was last reviewed on": "Deze pagina is voor het laatst beoordeeld op",
        "Data version": "Gegevensversie",
        "Full methodology documentation": "Volledige methodologiedocumentatie",
        "Machine-readable data (JSON API)": "Machineleesbare gegevens (JSON API)",
        "Machine-readable data (JSON)": "Machineleesbare gegevens (JSON)",
        # Meta / small text
        "Last analyzed:": "Laatst geanalyseerd:",
        "Last updated": "Laatst bijgewerkt",
        "Updated daily": "Dagelijks bijgewerkt",
        "Independent. Data-driven.": "Onafhankelijk. Datagedreven.",
        "verified": "geverifieerd",
        "Data sourced from": "Gegevens afkomstig van",
        "Based on": "Gebaseerd op",
        "dimensions": "dimensies",
        "independent data dimensions": "onafhankelijke gegevensdimensies",
        "strong": "sterk",
        "moderate": "matig",
        "weak": "zwak",
        "actively maintained": "actief onderhouden",
        "moderately maintained": "matig onderhouden",
        "low maintenance activity": "lage onderhoudsactiviteit",
        "well-documented": "goed gedocumenteerd",
        "partial documentation": "gedeeltelijke documentatie",
        "limited documentation": "beperkte documentatie",
        "community adoption": "gemeenschapsacceptatie",
        "stars on": "sterren op",
        # Cross-links
        "Safety": "Beveiliging",
        "Legit?": "Legitiem?",
        "Scam?": "Oplichting?",
        "Review": "Beoordeling",
        "Alternatives": "Alternatieven",
        "Compare": "Vergelijken",
        "Best in Category": "Beste in categorie",
        "Who Owns?": "Wie is eigenaar?",
        "What Is?": "Wat is het?",
        "Sells Data?": "Verkoopt gegevens?",
        "Hacked?": "Gehackt?",
        "Safe for Kids?": "Veilig voor kinderen?",
        "Pros &amp; Cons": "Voor- &amp; nadelen",
        # FAQ answers
        "Nerq Verified — meets the 70+ trust threshold.": "Nerq geverifieerd — voldoet aan de vertrouwensdrempel van 70+.",
        "Below the Nerq Verified threshold of 70.": "Onder de geverifieerde drempel van Nerq van 70.",
        "Has not yet reached the Nerq Verified threshold of 70.": "Heeft de geverifieerde drempel van Nerq van 70 nog niet bereikt.",
        "Strongest signal:": "Sterkste signaal:",
        "Score based on": "Score gebaseerd op",
        "security": "beveiliging",
        "maintenance": "onderhoud",
        "popularity": "populariteit",
        "documentation": "documentatie",
        "compliance": "naleving",
        # Verdict box
        "Safe": "Veilig",
        "Use Caution": "Voorzichtigheid",
        "Avoid": "Vermijden",
        # Long text patterns
        "is a Node.js package": "is een Node.js-pakket",
        "is a Python package": "is een Python-pakket",
        "is a Rust crate": "is een Rust crate",
        "is a Chrome extension": "is een Chrome-extensie",
        "is a Firefox extension": "is een Firefox-extensie",
        "is a VS Code extension": "is een VS Code-extensie",
        "is a WordPress plugin": "is een WordPress-plugin",
        "is a iOS app": "is een iOS-app",
        "is a Android app": "is een Android-app",
        "is a VPN service": "is een VPN-dienst",
        "is a game": "is een spel",
        "is a website": "is een website",
        "is a SaaS platform": "is een SaaS-platform",
        "is a dietary supplement": "is een voedingssupplement",
        "is a cosmetic ingredient": "is een cosmetisch ingrediënt",
        "is a food": "is een voedseladditief",
        "is a travel destination": "is een reisbestemming",
        "is a nonprofit organization": "is een non-profitorganisatie",
        "with a Nerq Trust Score of": "met een Nerq Vertrouwensscore van",
        "with a Nerq Safety Score of": "met een Nerq Veiligheidsscore van",
        "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "Voldoet aan de vertrouwensdrempel van Nerq met sterke signalen op het gebied van beveiliging, onderhoud en gemeenschapsacceptatie",
        "It has moderate trust signals but shows some areas of concern": "Heeft matige vertrouwenssignalen maar toont enkele aandachtspunten",
        "It has below-average trust signals with significant gaps": "Heeft ondergemiddelde vertrouwenssignalen met aanzienlijke lacunes",
        "review the full report below for specific considerations": "bekijk het volledige rapport hieronder voor specifieke overwegingen",
        "This score is based on automated analysis of security, maintenance, community, and quality signals.": "Deze score is gebaseerd op geautomatiseerde analyse van beveiligings-, onderhouds-, gemeenschaps- en kwaliteitssignalen.",
        "You can also check the trust score via API:": "U kunt de vertrouwensscore ook via de API controleren:",
        "dependency vulnerabilities, malicious packages, typosquatting": "kwetsbaarheden van afhankelijkheden, schadelijke pakketten, typosquatting",
        "Run your package manager's audit command": "Voer de auditopdrach van uw pakketbeheerder uit",
        "to check for known vulnerabilities in your dependency tree": "om te controleren op bekende kwetsbaarheden in uw afhankelijkheidsboom",
        "As a development package": "Als ontwikkelaarspakket",
        "does not directly collect end-user personal data": "verzamelt geen persoonlijke gegevens van eindgebruikers rechtstreeks",
        "However, applications built with it may collect data depending on implementation": "Toepassingen die ermee zijn gebouwd, kunnen echter gegevens verzamelen afhankelijk van de implementatie",
        "Review the package's dependencies for potential supply chain risks": "Controleer de afhankelijkheden van het pakket op mogelijke bevoorradingsketenrisico's",
        "License information not available": "Licentie-informatie niet beschikbaar",
        "Open-source packages allow independent security review of the source code": "Open-sourcepakketten maken een onafhankelijke beveiligingsbeoordeling van de broncode mogelijk",
        "to check for vulnerabilities": "om te controleren op kwetsbaarheden",
        "Review the": "Bekijk de",
        "GitHub repository for recent commits": "GitHub-repository voor recente commits",
        "This meets the recommended security threshold for production use": "Dit voldoet aan de aanbevolen beveiligingsdrempel voor productiegebruik",
        "Nerq monitors this entity against NVD, OSV.dev, and registry-specific vulnerability databases": "Nerq bewaakt deze entiteit op NVD, OSV.dev en registerspecifieke kwetsbaarheidsdatabases",
        "for ongoing security assessment": "voor voortdurende beveiligingsbeoordeling",
        "Yes, it is safe to use.": "Ja, het is veilig om te gebruiken.",
        "Use with some caution.": "Gebruik met enige voorzichtigheid.",
        "Exercise caution.": "Wees voorzichtig.",
        "Significant trust concerns.": "Aanzienlijke vertrouwensproblemen.",
        "maintained by": "onderhouden door",
        "is computed from": "wordt berekend uit",
        "The score reflects": "De score weerspiegelt",
        "independent dimensions": "onafhankelijke dimensies",
        "Each dimension is weighted equally to produce the composite trust score": "Elke dimensie heeft een gelijk gewicht om de samengestelde vertrouwensscore te produceren",
        "No reviews yet.": "Nog geen beoordelingen.",
        "Be the first to review": "Wees de eerste die beoordeelt",
        "Write a review": "Schrijf een beoordeling",
        "Higher-rated": "Hoger beoordeeld",
        "you may want to consider:": "die u wellicht wilt overwegen:",
        "under assessment": "onder beoordeling",
        # Health disclaimers
        "Important Notice:": "Belangrijke mededeling:",
        "educational and informational purposes only": "uitsluitend voor educatieve en informatieve doeleinden",
        "does not constitute medical advice": "vormt geen medisch advies",
        "Consult a qualified healthcare professional": "Raadpleeg een gekwalificeerde zorgverlener",
        "Full health disclaimer": "Volledige gezondheidsverklaring",
        "Full disclaimer": "Volledige vrijwaringsverklaring",
    },
    "sv": {
        "What is NordVPN": "Vad är NordVPN",
        "What are the best alternatives to NordVPN": "Vilka är de bästa alternativen till NordVPN",
        "NordVPN vs alternatives: which is safer": "NordVPN mot alternativ: vilken är säkrare",
        "Does NordVPN log my data": "Loggar NordVPN min data",
        "trust score?": "förtroendepoäng?",
        "Is NordVPN safe": "Är NordVPN säker",
        "Run npm audit": "Kör npm audit",
        "full safety report for detailed privacy analysis": "fullständig säkerhetsrapport för detaljerad integritetsanalys",
        "In the npm category": "I npm-kategorin",
        "In the vpn category": "I VPN-kategorin",
        "In the password_manager category": "I lösenordshanterare-kategorin",
        "In the antivirus category": "I antivirus-kategorin",
        "In the hosting category": "I hosting-kategorin",
        "In the saas category": "I SaaS-kategorin",
        "In the crypto category": "I krypto-kategorin",
        "In the website_builder category": "I webbplatsbyggare-kategorin",
        "on password_manager": "på lösenordshanterare",
        "on antivirus": "på antivirus",
        "on hosting": "på hosting",
        "on saas": "på SaaS",
        "on crypto": "på krypto",
        "on website_builder": "på webbplatsbyggare",
        "Scores update as new data becomes available": "Poäng uppdateras när ny data finns tillgänglig",
        "multiple public sources including package registries, GitHub, NVD, OSV.dev, and OpenSSF Scorecard": "flera offentliga källor inklusive paketregister, GitHub, NVD, OSV.dev och OpenSSF Scorecard",
        "The #1 safest": "Den säkraste",
        "How are safest": "Hur rangordnas de säkraste",
        "Are these safest": "Är dessa de säkraste",
        "What does a Nerq Trust Score": "Vad innebär ett Nerq Trust Score",
        "The #1": "Nr 1",
        "According to Nerq": "Enligt Nerq",
        "How are": "Hur rangordnas",
        "ranked by Nerq Trust Score": "rangordnade efter Nerq-förtroendepoäng",
        "What are the best": "Vilka är de bästa",
        "Are these rankings updated regularly": "Uppdateras dessa rankningar regelbundet",
        "What does a Nerq Trust Score measure": "Vad mäter ett Nerq Trust Score",
        "How does Nerq evaluate": "Hur utvärderar Nerq",
        "Are these safe to use": "Är dessa säkra att använda",
        "{name} Privacy Report": "{name} integritetsrapport",
        "has undergone third-party security audits verifying its infrastructure and no-logs claims": "har genomgått tredjepartsrevisioner som verifierar dess infrastruktur och no-logs-påståenden",
        "This is a strong positive signal — most VPN providers have not been independently audited": "Detta är en stark positiv signal — de flesta VPN-leverantörer har inte granskats oberoende",
        "has not published results from an independent security audit": "har inte publicerat resultat från en oberoende säkerhetsgranskning",
        "While this does not indicate a security issue, audited VPNs provide higher assurance": "Även om detta inte indikerar ett säkerhetsproblem ger granskade VPN-tjänster högre säkerhet",
        "Security score": "Säkerhetspoäng",
        "Primary encryption protocol": "Primärt krypteringsprotokoll",
        "which is considered industry-standard for VPN connections": "vilket anses vara branschstandard för VPN-anslutningar",
        "Independent security audit verified": "Oberoende säkerhetsgranskning verifierad",
        "has no known data breaches and has been independently audited": "har inga kända dataintrång och har granskats av oberoende part",
        "uses AES-256-CBC (industry standard), Argon2id (brute-force resistant key derivation)": "använder AES-256-CBC (branschstandard), Argon2id (brute-force-resistent nyckelderivering)",
        "uses a zero-knowledge architecture": "använder en zero-knowledge-arkitektur",
        "your master password and vault data are encrypted locally and never sent to the server in plaintext": "ditt huvudlösenord och valvdata krypteras lokalt och skickas aldrig till servern i klartext",
        "is open source with": "är öppen källkod med",
        "GitHub stars": "GitHub-stjärnor",
        "Based in": "Baserat i",
        "Independently audited": "Oberoende granskad",
        "No published independent audit": "Ingen publicerad oberoende granskning",
        "logging policy": "loggningspolicy",
        "Safety Guide": "Säkerhetsguide",
        "You can also check the trust score via API": "Du kan också kontrollera förtroendepoängen via API",
        "meets Nerq trust threshold": "uppfyller Nerqs förtroendetröskel",
        "passes trust threshold": "uppfyller förtroendegränsen",
        "Recommended for use": "Rekommenderas för användning",
        "This score is based on automated analysis of security, maintenance, community, and quality signals": "Denna poäng baseras på automatiserad analys av signaler för säkerhet, underhåll, community och kvalitet",
        "widely used": "allmänt använd",
        "No known data breaches associated with this service": "Inga kända dataintrång kopplade till denna tjänst",
        "This is a strong positive signal": "Detta är en stark positiv signal",
        "most VPN providers have not been independently audited": "de flesta VPN-leverantörer har inte granskats oberoende",
        "Full analysis": "Fullständig analys",
        "Same developer": "Samma utvecklare",
        "It is ": "Det är ",
        "It is recommended": "Rekommenderas",
        "below the recommended threshold": "under den rekommenderade tröskeln",
        "Dimension": "Dimension",
        "Score": "Poäng",
        "Data from": "Data från",
        "is based in": "har sin bas i",
        "outside all Eyes surveillance alliances": "utanför alla Eyes-övervakningsallianser",
        "a privacy advantage": "en integritetsfördel",
        "has been independently audited to verify its privacy claims": "har granskats av oberoende part för att verifiera sina integritetsanspråk",
        "Serving": "Betjänar",
        "users": "användare",
        "Related Safety Rankings": "Relaterade säkerhetsrankningar",
        "Complete Your Privacy Setup": "Komplettera ditt integritetsskydd",
        "Add a password manager to your VPN for full protection": "Lägg till en lösenordshanterare till din VPN för fullt skydd",
        "Add Antivirus Protection": "Lägg till antivirusskydd",
        "Complete your security with antivirus alongside your VPN": "Komplettera din säkerhet med antivirus tillsammans med din VPN",
        "servers in": "servrar i",
        "countries": "länder",
        "logging practices": "loggningspraxis",
        "audit history": "granskningshistorik",
        "ownership transparency": "ägarskaptransparens",
        "This is significant because VPN providers in": "Detta är viktigt eftersom VPN-leverantörer i",
        "are not subject to mandatory data retention laws or intelligence-sharing agreements": "inte omfattas av obligatoriska datalagringslagar eller underrättelsesamarbetsavtal",
        "Server infrastructure": "Serverinfrastruktur",
        "servers across": "servrar i",
        "Logging policy": "Loggningspolicy",
        "independently audited no-logs policy": "oberoende granskad ingen-logg-policy",
        "According to independent audit reports": "Enligt oberoende granskningsrapporter",
        "does not store connection logs, browsing activity, or DNS queries": "lagrar inte anslutningsloggar, surfaktivitet eller DNS-förfrågningar",
        "score:": "poäng:",
        "Nerq analyzes over": "Nerq analyserar över",
        "What are the best alternatives to": "Vilka är de bästa alternativen till",
        "Does": "Loggar",
        "log my data": "min data",
        "vs alternatives: which is safer": "mot alternativ: vilken är säkrare",
        "Popular in": "Populära inom",
        "Browse Categories": "Bläddra bland kategorier",
        "Safest VPNs": "Säkraste VPN",
        "Most Private Apps": "Mest privata appar",
        "Recently Analyzed": "Nyligen analyserade",
        "strong)": "stark)",
        "widely used VPN service": "allmänt använd VPN-tjänst",
        "Popularity": "Popularitet",
        "more VPN services are being analyzed": "fler VPN-tjänster analyseras",
        "check back soon": "kom tillbaka snart",
        "Nerq assesses": "Nerq bedömer",
        "data practices as part of its trust score": "datapraktik som en del av förtroendepoängen",
        "Review full safety report for detailed privacy analysis": "Granska full säkerhetsrapport för detaljerad integritetsanalys",
        "More VPN services are being analyzed for comparison": "Fler VPN-tjänster analyseras för jämförelse",
        "jurisdiction databases, independent audit reports, protocol analysis, and incident history": "jurisdiktionsdatabaser, oberoende granskningsrapporter, protokollanalys och incidenthistorik",
        "Panama jurisdiction": "Panamas jurisdiktion",
        "outside the Five Eyes, Nine Eyes, and Fourteen Eyes surveillance alliances": "utanför Five Eyes, Nine Eyes och Fourteen Eyes övervakningsallianserna",
        "jurisdiction": "jurisdiktion",
        "Five Eyes": "Five Eyes",
        "Independent": "Oberoende",
        "Audited no-log": "Granskad no-log",
        "Claimed no-log": "Påstådd no-log",
        "Check jurisdiction": "Kontrollera jurisdiktion",
        "Verify independent audit exists": "Verifiera att oberoende granskning finns",
        "Review logging policy": "Granska loggningspolicy",
        "Antivirus": "Antivirus",
        # ── Vertical-specific strings (auto-generated) ──
        "Privacy Assessment": "Integritetsbedömning",
        "Breach History": "Intrångshistorik",
        "Encryption": "Kryptering",
        "Zero-Knowledge Architecture": "Zero-Knowledge-arkitektur",
        "Open Source": "Öppen Källkod",
        "Jurisdiction": "Jurisdiktion",
        "Infrastructure": "Infrastruktur",
        "Security & Compliance": "Säkerhet & Efterlevnad",
        "Data Location": "Dataplats",
        "Security Incidents": "Säkerhetsincidenter",
        "Independent Lab Results": "Oberoende Labbresultat",
        "Security Track Record": "Säkerhetshistorik",
        "Build Your Security Stack": "Bygg Ditt Säkerhetspaket",
        "Best VPNs": "Bästa VPN",
        "Best Password Managers": "Bästa Lösenordshanterare",
        "Best Antivirus": "Bästa Antivirus",
        "Security Assessment": "Säkerhetsbedömning",
        "Ecommerce": "E-handel",
        "Hosting Assessment": "Hostingbedömning",
        "Antivirus Assessment": "Antivirusbedömning",
        "SaaS Assessment": "SaaS-bedömning",
        "Website Builder Assessment": "Webbplatsbyggarbedömning",
        "Exchange Assessment": "Börsbedömning",
        "Combine these tools for comprehensive protection:": "Kombinera dessa verktyg för heltäckande skydd:",
        "Proof of Reserves": "Reservbevis",
        # Title / H1
        "Independent Trust & Security Analysis": "Oberoende förtroende- och säkerhetsanalys",
        "Independent Trust &amp; Security Analysis": "Oberoende förtroende- och säkerhetsanalys",
        # Verdicts
        "Yes, {name} is safe to use.": "Ja, {name} är säker att använda.",
        "Use {name} with some caution.": "Använd {name} med försiktighet.",
        "Exercise caution with {name}.": "Var försiktig med {name}.",
        "{name} has significant trust concerns.": "{name} har betydande förtroendeproblem.",
        "Passes Nerq Verified threshold": "Uppfyller Nerqs verifierade tröskel",
        "Below Nerq Verified threshold": "Under Nerqs verifierade tröskel",
        "Significant trust gaps detected": "Betydande förtroendeluckor upptäckta",
        # Section headings
        "Trust Score Breakdown": "Förtroendepoäng i detalj",
        "Safety Score Breakdown": "Säkerhetspoäng i detalj",
        "Key Findings": "Viktiga resultat",
        "Key Safety Findings": "Viktiga säkerhetsresultat",
        "Detailed Score Analysis": "Detaljerad poänganalys",
        "Frequently Asked Questions": "Vanliga frågor",
        "Safer Alternatives": "Säkrare alternativ",
        "Popular Alternatives": "Populära alternativ",
        "Community Reviews": "Communityomdömen",
        "Regulatory Compliance": "Regelefterlevnad",
        "How we calculated this score": "Så beräknade vi denna poäng",
        "What We Know About": "Vad vi vet om",
        # Safety Guide
        "Safety Guide:": "Säkerhetsguide:",
        "What is": "Vad är",
        "How to Verify Safety": "Så verifierar du säkerheten",
        "Key Safety Concerns for": "Viktiga säkerhetsproblem för",
        "Trust Assessment": "Förtroendebedömning",
        "Key Takeaways": "Viktigaste slutsatser",
        "Recommended for use — passes trust threshold.": "Rekommenderas för användning — uppfyller förtroendegränsen.",
        "Review carefully before use — below trust threshold.": "Granska noga innan användning — under förtroendegränsen.",
        "Always verify independently using the": "Verifiera alltid oberoende med",
        "When evaluating any": "När du utvärderar ett",
        "watch for:": "håll utkik efter:",
        "Review the project for recent activity and known issues.": "Granska projektet för senaste aktivitet och kända problem.",
        "maintenance status, security": "underhållsstatus, säkerhet",
        "software tool": "programvara",
        "password manager": "lösenordshanterare",
        "antivirus software": "antivirusprogram",
        "web hosting provider": "webbhotellsleverantör",
        "website builder": "webbplatsbyggare",
        "SaaS platform": "SaaS-plattform",
        "crypto exchange": "kryptobörs",
        "Node.js package": "Node.js-paket",
        "Python package": "Python-paket",
        "Rust crate": "Rust-crate",
        "Chrome extension": "Chrome-tillägg",
        "WordPress plugin": "WordPress-tillägg",
        "VS Code extension": "VS Code-tillägg",
        "Firefox add-on": "Firefox-tillägg",
        "iOS app": "iOS-app",
        "Android app": "Android-app",
        "Alternatives": "Alternativ",
        "meets Nerq trust threshold": "uppfyller Nerqs förtroendegräns",
        "has not yet reached Nerq trust threshold (70+)": "har ännu inte nått Nerqs förtroendegräns (70+)",
        "This score is based on automated analysis of security, maintenance, community, and quality signals.": "Denna poäng baseras på automatiserad analys av säkerhet, underhåll, community och kvalitetssignaler.",
        # Cross-product
        "Across Platforms": "På andra plattformar",
        "across platforms": "på andra plattformar",
        "Same developer/company in other registries:": "Samma utvecklare/företag i andra register:",
        # King sections
        "What data does": "Vilka data samlar",
        "collect?": "in?",
        "Is": "Är",
        "secure?": "säker?",
        "Full analysis:": "Fullständig analys:",
        "Privacy Report": "Integritetsrapport",
        "Privacy review": "Integritetsrecension",
        "Security Report": "Säkerhetsrapport",
        # Dimensions
        "Security": "Säkerhet",
        "Privacy": "Integritet",
        "Reliability": "Tillförlitlighet",
        "Transparency": "Transparens",
        "Maintenance": "Underhåll",
        "Overall Trust": "Övergripande förtroende",
        "Composite trust score": "Sammansatt förtroendepoäng",
        "across all available signals": "utifrån alla tillgängliga signaler",
        # Methodology
        "Nerq analyzes over 7.5 million entities across 26 registries": "Nerq analyserar över 7,5 miljoner entiteter i 26 register",
        "using the same methodology, enabling direct cross-entity comparison": "med samma metodik, vilket möjliggör direkt jämförelse mellan entiteter",
        "Scores are updated continuously as new data becomes available": "Poäng uppdateras löpande när ny data finns tillgänglig",
        "This page was last reviewed on": "Den här sidan granskades senast",
        "Data version": "Dataversion",
        "Full methodology documentation": "Fullständig metodikdokumentation",
        "Machine-readable data (JSON API)": "Maskinläsbar data (JSON API)",
        "Machine-readable data (JSON)": "Maskinläsbar data (JSON)",
        # Meta / small text
        "Last analyzed:": "Senast analyserad:",
        "Last updated": "Senast uppdaterad",
        "Updated daily": "Uppdateras dagligen",
        "Independent. Data-driven.": "Oberoende. Datadriven.",
        "verified": "verifierad",
        "Data sourced from": "Data hämtad från",
        "Based on": "Baserad på",
        "dimensions": "dimensioner",
        "independent data dimensions": "oberoende datadimensioner",
        "strong": "stark",
        "moderate": "måttlig",
        "weak": "svag",
        "actively maintained": "aktivt underhållen",
        "moderately maintained": "måttligt underhållen",
        "low maintenance activity": "låg underhållsaktivitet",
        "well-documented": "väldokumenterad",
        "partial documentation": "partiell dokumentation",
        "limited documentation": "begränsad dokumentation",
        "community adoption": "communityanvändning",
        "stars on": "stjärnor på",
        # Cross-links
        "Safety": "Säkerhet",
        "Legit?": "Pålitlig?",
        "Scam?": "Bedrägeri?",
        "Review": "Recension",
        "Alternatives": "Alternativ",
        "Compare": "Jämför",
        "Best in Category": "Bäst i kategorin",
        "Who Owns?": "Vem äger?",
        "What Is?": "Vad är det?",
        "Sells Data?": "Säljer data?",
        "Hacked?": "Hackad?",
        "Safe for Kids?": "Säkert för barn?",
        "Pros &amp; Cons": "För- &amp; nackdelar",
        # FAQ answers
        "Nerq Verified — meets the 70+ trust threshold.": "Nerq-verifierad — uppfyller förtroendegränsen 70+.",
        "Below the Nerq Verified threshold of 70.": "Under Nerqs verifierade gräns på 70.",
        "Has not yet reached the Nerq Verified threshold of 70.": "Har ännu inte nått Nerqs verifierade gräns på 70.",
        "Strongest signal:": "Starkaste signalen:",
        "Score based on": "Poäng baserad på",
        "security": "säkerhet",
        "maintenance": "underhåll",
        "popularity": "popularitet",
        "documentation": "dokumentation",
        "compliance": "regelefterlevnad",
        # Verdict box
        "Safe": "Säker",
        "Use Caution": "Var försiktig",
        "Avoid": "Undvik",
        # Long text patterns
        "is a Node.js package": "är ett Node.js-paket",
        "is a Python package": "är ett Python-paket",
        "is a Rust crate": "är en Rust-crate",
        "is a Chrome extension": "är ett Chrome-tillägg",
        "is a Firefox extension": "är ett Firefox-tillägg",
        "is a VS Code extension": "är ett VS Code-tillägg",
        "is a WordPress plugin": "är ett WordPress-tillägg",
        "is a iOS app": "är en iOS-app",
        "is a Android app": "är en Android-app",
        "is a VPN service": "är en VPN-tjänst",
        "is a game": "är ett spel",
        "is a website": "är en webbplats",
        "is a SaaS platform": "är en SaaS-plattform",
        "is a dietary supplement": "är ett kosttillskott",
        "is a cosmetic ingredient": "är en kosmetisk ingrediens",
        "is a food": "är ett livsmedel",
        "is a travel destination": "är ett resmål",
        "is a nonprofit organization": "är en ideell organisation",
        "with a Nerq Trust Score of": "med ett Nerq-förtroendepoäng på",
        "with a Nerq Safety Score of": "med ett Nerq-säkerhetspoäng på",
        "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "Uppfyller Nerqs förtroendetröskel med starka signaler inom säkerhet, underhåll och communityanvändning",
        "It has moderate trust signals but shows some areas of concern": "Har måttliga förtroendesignaler men uppvisar vissa oroande områden",
        "It has below-average trust signals with significant gaps": "Har lägre än genomsnittliga förtroendesignaler med betydande luckor",
        "review the full report below for specific considerations": "se hela rapporten nedan för specifika överväganden",
        "This score is based on automated analysis of security, maintenance, community, and quality signals.": "Denna poäng baseras på automatiserad analys av signaler för säkerhet, underhåll, community och kvalitet.",
        "You can also check the trust score via API:": "Du kan också kontrollera förtroendepoängen via API:",
        "dependency vulnerabilities, malicious packages, typosquatting": "sårbarheter i beroenden, skadliga paket, typosquatting",
        "Run your package manager's audit command": "Kör pakethanterarens granskningskommando",
        "to check for known vulnerabilities in your dependency tree": "för att söka efter kända sårbarheter i ditt beroendeträd",
        "As a development package": "Som ett utvecklingspaket",
        "does not directly collect end-user personal data": "samlar inte direkt in slutanvändares personuppgifter",
        "However, applications built with it may collect data depending on implementation": "Applikationer byggda med det kan dock samla in data beroende på implementationen",
        "Review the package's dependencies for potential supply chain risks": "Granska paketets beroenden för potentiella risker i leveranskedjan",
        "License information not available": "Licensinformation saknas",
        "Open-source packages allow independent security review of the source code": "Öppen källkod möjliggör oberoende säkerhetsgranskning av källkoden",
        "to check for vulnerabilities": "för att söka efter sårbarheter",
        "Review the": "Granska",
        "GitHub repository for recent commits": "GitHub-repositoriet för senaste incheckningar",
        "This meets the recommended security threshold for production use": "Uppfyller den rekommenderade säkerhetsgränsen för produktionsanvändning",
        "Nerq monitors this entity against NVD, OSV.dev, and registry-specific vulnerability databases": "Nerq övervakar denna entitet mot NVD, OSV.dev och registerspecifika sårbarhetsdatabaser",
        "for ongoing security assessment": "för löpande säkerhetsbedömning",
        "Yes, it is safe to use.": "Ja, det är säkert att använda.",
        "Use with some caution.": "Använd med viss försiktighet.",
        "Exercise caution.": "Var försiktig.",
        "Significant trust concerns.": "Betydande förtroendeproblem.",
        "maintained by": "underhålls av",
        "is computed from": "beräknas utifrån",
        "The score reflects": "Poängen speglar",
        "independent dimensions": "oberoende dimensioner",
        "Each dimension is weighted equally to produce the composite trust score": "Varje dimension ges lika vikt för att producera den sammansatta förtroendepoängen",
        "No reviews yet.": "Inga omdömen ännu.",
        "Be the first to review": "Bli först med att recensera",
        "Write a review": "Skriv ett omdöme",
        "Higher-rated": "Högre betygsatta",
        "you may want to consider:": "som du kanske vill överväga:",
        "under assessment": "under granskning",
        # Health disclaimers
        "Important Notice:": "Viktig information:",
        "educational and informational purposes only": "enbart i utbildnings- och informationssyfte",
        "does not constitute medical advice": "utgör inte medicinsk rådgivning",
        "Consult a qualified healthcare professional": "Rådgör med en kvalificerad vårdgivare",
        "Full health disclaimer": "Fullständigt hälsofriskrivande",
        "Full disclaimer": "Fullständigt friskrivande",
    },
    "zh": {
        "Is NordVPN safe": "NordVPN安全吗",
        "What is NordVPN": "什么是NordVPN",
        "Does NordVPN log my data": "NordVPN记录我的数据吗",
        "What are the best alternatives to NordVPN": "NordVPN的最佳替代品是什么",
        "NordVPN vs alternatives: which is safer": "NordVPN与替代品：哪个更安全",
        "trust score?": "信任分数？",
        "Scores update as new data becomes available": "新数据可用时分数会更新",
        "In the vpn category": "在VPN类别中",
        "full safety report for detailed privacy analysis": "完整安全报告以获取详细隐私分析",
        "has undergone third-party security audits verifying its infrastructure and no-logs claims": "已接受第三方安全审计以验证其基础设施和无日志声明",
        "widely used VPN service": "广泛使用的VPN服务",
        "multiple public sources including package registries, GitHub, NVD, OSV.dev, and OpenSSF Scorecard": "多个公共来源，包括包注册表、GitHub、NVD、OSV.dev和OpenSSF Scorecard",
        "The #1 safest": "最安全的第一名",
        "How are safest": "最安全的如何排名",
        "Are these safest": "这些最安全的",
        "What does a Nerq Trust Score": "Nerq Trust Score意味着什么",
        "The #1": "第一名",
        "According to Nerq": "根据Nerq",
        "How are": "如何",
        "ranked by Nerq Trust Score": "按Nerq Trust Score排名",
        "What are the best": "最好的",
        "Are these rankings updated regularly": "这些排名定期更新吗",
        "What does a Nerq Trust Score measure": "Nerq Trust Score衡量什么",
        "How does Nerq evaluate": "Nerq如何评估",
        "Are these safe to use": "这些安全吗",
        "Security score": "安全分数",
        "Based in": "总部位于",
        "No known data breaches associated with this service": "没有与此服务相关的已知数据泄露",
        "According to independent audit reports": "根据独立审计报告",
        "logging policy": "日志策略",
        "This is a strong positive signal": "这是一个强烈的积极信号",
        "Safety Guide": "安全指南",
        "strong)": "强)",
        "Full analysis": "完整分析",
        "It is recommended": "推荐",
        "Dimension": "维度",
        "Score": "分数",
        "outside all Eyes surveillance alliances": "在所有Eyes监控联盟之外",
        "a privacy advantage": "隐私优势",
        "has been independently audited to verify its privacy claims": "已通过独立审计以验证其隐私声明",
        "Serving": "服务",
        "Related Safety Rankings": "相关安全排名",
        "Complete Your Privacy Setup": "完善您的隐私设置",
        "Add a password manager to your VPN for full protection": "为您的VPN添加密码管理器以获得完整保护",
        "Browse Categories": "浏览分类",
        "Safest VPNs": "最安全的VPN",
        "Most Private Apps": "最私密的应用",
        "Recently Analyzed": "最近分析",
        "What are the best alternatives to": "的最佳替代品是什么",
        "which is safer": "哪个更安全",
        "logging practices": "日志记录实践",
        "ownership transparency": "所有权透明度",
        "Popular in": "热门",
        "Popularity": "人气度",
        "is based in": "总部位于",
        "Not Yet Analyzed": "尚未分析",
        "jurisdiction databases, independent audit reports, protocol analysis, and incident history": "管辖权数据库、独立审计报告、协议分析和事件历史",
        "Panama jurisdiction": "巴拿马管辖权",
        "outside the Five Eyes, Nine Eyes, and Fourteen Eyes surveillance alliances": "在五眼联盟、九眼联盟和十四眼联盟监控联盟之外",
        "jurisdiction": "司法管辖区",
        "Five Eyes": "五眼联盟",
        "Independent": "独立",
        "Audited no-log": "已审计无日志",
        "Claimed no-log": "声称无日志",
        "Check jurisdiction": "检查管辖权",
        "Verify independent audit exists": "验证独立审计",
        "Review logging policy": "审查日志策略",
        "Antivirus": "杀毒软件",
        # ── Vertical-specific strings (auto-generated) ──
        "Privacy Assessment": "隐私评估",
        "Breach History": "泄露历史",
        "Encryption": "加密",
        "Zero-Knowledge Architecture": "零知识架构",
        "Open Source": "开源",
        "Jurisdiction": "管辖权",
        "Infrastructure": "基础设施",
        "Security & Compliance": "安全与合规",
        "Data Location": "数据位置",
        "Security Incidents": "安全事件",
        "Independent Lab Results": "独立实验室结果",
        "Security Track Record": "安全记录",
        "Build Your Security Stack": "构建您的安全套件",
        "Best VPNs": "最佳VPN",
        "Best Password Managers": "最佳密码管理器",
        "Best Antivirus": "最佳杀毒软件",
        "Security Assessment": "安全评估",
        "Ecommerce": "电子商务",
        "Hosting Assessment": "托管评估",
        "Antivirus Assessment": "杀毒软件评估",
        "SaaS Assessment": "SaaS评估",
        "Website Builder Assessment": "网站构建器评估",
        "Exchange Assessment": "交易所评估",
        "Combine these tools for comprehensive protection:": "组合这些工具以获得全面保护:",
        "Proof of Reserves": "储备金证明",
        # Title / H1
        "Independent Trust & Security Analysis": "独立信任与安全分析",
        "Independent Trust &amp; Security Analysis": "独立信任与安全分析",
        # Verdicts
        "Yes, {name} is safe to use.": "是的，{name}可以安全使用。",
        "Use {name} with some caution.": "请谨慎使用{name}。",
        "Exercise caution with {name}.": "请对{name}保持警惕。",
        "{name} has significant trust concerns.": "{name}存在严重的信任问题。",
        "Passes Nerq Verified threshold": "达到 Nerq 验证阈值",
        "Below Nerq Verified threshold": "低于 Nerq 验证阈值",
        "Significant trust gaps detected": "发现重大信任缺口",
        # Section headings
        "Trust Score Breakdown": "信任评分详情",
        "Safety Score Breakdown": "安全评分详情",
        "Key Findings": "主要发现",
        "Key Safety Findings": "主要安全发现",
        "Detailed Score Analysis": "评分详细分析",
        "Frequently Asked Questions": "常见问题",
        "Safer Alternatives": "更安全的替代品",
        "Popular Alternatives": "热门替代品",
        "Community Reviews": "社区评价",
        "Regulatory Compliance": "合规性",
        "How we calculated this score": "我们如何计算此评分",
        "What We Know About": "我们对以下内容的了解",
        # Safety Guide
        "Safety Guide:": "安全指南：",
        "What is": "什么是",
        "How to Verify Safety": "如何验证安全性",
        "Key Safety Concerns for": "以下方面的主要安全问题",
        "Trust Assessment": "信任评估",
        "Key Takeaways": "主要结论",
        "Recommended for use — passes trust threshold.": "推荐使用——达到信任阈值。",
        "Review carefully before use — below trust threshold.": "使用前请仔细审查——低于信任阈值。",
        "Always verify independently using the": "请始终使用以下方式独立验证",
        "When evaluating any": "在评估任何",
        "watch for:": "请注意：",
        # Cross-product
        "Across Platforms": "其他平台",
        "across platforms": "在其他平台",
        "Same developer/company in other registries:": "同一开发者/公司在其他注册表中：",
        # King sections
        "What data does": "收集哪些数据",
        "collect?": "？",
        "Is": "是否",
        "secure?": "安全？",
        "Full analysis:": "完整分析：",
        "Privacy Report": "隐私报告",
        "Privacy review": "隐私审查",
        "Security Report": "安全报告",
        # Dimensions
        "Security": "安全性",
        "Privacy": "隐私",
        "Reliability": "可靠性",
        "Transparency": "透明度",
        "Maintenance": "维护",
        "Overall Trust": "整体信任度",
        "Composite trust score": "综合信任评分",
        "across all available signals": "基于所有可用信号",
        # Methodology
        "Nerq analyzes over 7.5 million entities across 26 registries": "Nerq 在 26 个注册表中分析超过 750 万个实体",
        "using the same methodology, enabling direct cross-entity comparison": "使用相同的方法，实现实体间的直接比较",
        "Scores are updated continuously as new data becomes available": "评分会在新数据可用时持续更新",
        "This page was last reviewed on": "本页面最近审查于",
        "Data version": "数据版本",
        "Full methodology documentation": "完整方法论文档",
        "Machine-readable data (JSON API)": "机器可读数据（JSON API）",
        "Machine-readable data (JSON)": "机器可读数据（JSON）",
        # Meta / small text
        "Last analyzed:": "最近分析：",
        "Last updated": "最后更新",
        "Updated daily": "每日更新",
        "Independent. Data-driven.": "独立。数据驱动。",
        "verified": "已验证",
        "Data sourced from": "数据来源于",
        "Based on": "基于",
        "dimensions": "维度",
        "independent data dimensions": "独立数据维度",
        "strong": "强",
        "moderate": "中等",
        "weak": "弱",
        "actively maintained": "积极维护",
        "moderately maintained": "适度维护",
        "low maintenance activity": "低维护活动",
        "well-documented": "文档完善",
        "partial documentation": "部分文档",
        "limited documentation": "文档有限",
        "community adoption": "社区采用",
        "stars on": "在以下平台的星标",
        # Cross-links
        "Safety": "安全",
        "Legit?": "可靠？",
        "Scam?": "诈骗？",
        "Review": "评论",
        "Alternatives": "替代品",
        "Compare": "比较",
        "Best in Category": "类别最佳",
        "Who Owns?": "谁拥有？",
        "What Is?": "是什么？",
        "Sells Data?": "出售数据？",
        "Hacked?": "曾被黑客攻击？",
        "Safe for Kids?": "对儿童安全？",
        "Pros &amp; Cons": "优缺点",
        # FAQ answers
        "Nerq Verified — meets the 70+ trust threshold.": "Nerq 已验证——达到 70+ 信任阈值。",
        "Below the Nerq Verified threshold of 70.": "低于 Nerq 验证阈值 70。",
        "Has not yet reached the Nerq Verified threshold of 70.": "尚未达到 Nerq 验证阈值 70。",
        "Strongest signal:": "最强信号：",
        "Score based on": "评分基于",
        "security": "安全性",
        "maintenance": "维护",
        "popularity": "人气",
        "documentation": "文档",
        "compliance": "合规性",
        # Verdict box
        "Safe": "安全",
        "Use Caution": "谨慎",
        "Avoid": "避免",
        # Long text patterns
        "is a Node.js package": "是一个 Node.js 包",
        "is a Python package": "是一个 Python 包",
        "is a Rust crate": "是一个 Rust crate",
        "is a Chrome extension": "是一个 Chrome 扩展",
        "is a Firefox extension": "是一个 Firefox 扩展",
        "is a VS Code extension": "是一个 VS Code 扩展",
        "is a WordPress plugin": "是一个 WordPress 插件",
        "is a iOS app": "是一款 iOS 应用",
        "is a Android app": "是一款 Android 应用",
        "is a VPN service": "是一项 VPN 服务",
        "is a game": "是一款游戏",
        "is a website": "是一个网站",
        "is a SaaS platform": "是一个 SaaS 平台",
        "is a dietary supplement": "是一种膳食补充剂",
        "is a cosmetic ingredient": "是一种化妆品成分",
        "is a food": "是一种食品添加剂",
        "is a travel destination": "是一个旅游目的地",
        "is a nonprofit organization": "是一个非营利组织",
        "with a Nerq Trust Score of": "Nerq 信任评分为",
        "with a Nerq Safety Score of": "Nerq 安全评分为",
        "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "在安全性、维护和社区采用方面信号强烈，达到了 Nerq 信任阈值",
        "It has moderate trust signals but shows some areas of concern": "信任信号中等，但存在一些值得关注的方面",
        "It has below-average trust signals with significant gaps": "信任信号低于平均水平，存在重大缺口",
        "review the full report below for specific considerations": "请查看下方完整报告以了解具体注意事项",
        "This score is based on automated analysis of security, maintenance, community, and quality signals.": "此评分基于对安全性、维护、社区和质量信号的自动分析。",
        "You can also check the trust score via API:": "您也可以通过 API 查看信任评分：",
        "dependency vulnerabilities, malicious packages, typosquatting": "依赖漏洞、恶意包、域名抢注",
        "Run your package manager's audit command": "运行您的包管理器审计命令",
        "to check for known vulnerabilities in your dependency tree": "以检查依赖树中的已知漏洞",
        "As a development package": "作为开发包",
        "does not directly collect end-user personal data": "不直接收集最终用户个人数据",
        "However, applications built with it may collect data depending on implementation": "但是，基于其构建的应用程序可能会根据实现方式收集数据",
        "Review the package's dependencies for potential supply chain risks": "检查包的依赖项以评估潜在的供应链风险",
        "License information not available": "许可证信息不可用",
        "Open-source packages allow independent security review of the source code": "开源包允许对源代码进行独立安全审查",
        "to check for vulnerabilities": "以检查漏洞",
        "Review the": "查看",
        "GitHub repository for recent commits": "GitHub 仓库的最新提交",
        "This meets the recommended security threshold for production use": "这满足了生产使用的推荐安全阈值",
        "Nerq monitors this entity against NVD, OSV.dev, and registry-specific vulnerability databases": "Nerq 对照 NVD、OSV.dev 和注册表特定漏洞数据库监控此实体",
        "for ongoing security assessment": "以进行持续安全评估",
        "Yes, it is safe to use.": "是的，可以安全使用。",
        "Use with some caution.": "请谨慎使用。",
        "Exercise caution.": "请保持警惕。",
        "Significant trust concerns.": "存在严重的信任问题。",
        "maintained by": "由...维护",
        "is computed from": "由以下内容计算得出",
        "The score reflects": "该评分反映了",
        "independent dimensions": "独立维度",
        "Each dimension is weighted equally to produce the composite trust score": "每个维度被同等加权以产生综合信任评分",
        "No reviews yet.": "暂无评价。",
        "Be the first to review": "成为第一个评价",
        "Write a review": "撰写评价",
        "Higher-rated": "评分更高的",
        "you may want to consider:": "您可能需要考虑：",
        "under assessment": "正在评估中",
        # Health disclaimers
        "Important Notice:": "重要提示：",
        "educational and informational purposes only": "仅供教育和信息目的",
        "does not constitute medical advice": "不构成医疗建议",
        "Consult a qualified healthcare professional": "请咨询合格的医疗专业人员",
        "Full health disclaimer": "完整健康免责声明",
        "Full disclaimer": "完整免责声明",
    },
    "it": {
        "It is ": "È ",
        "Is NordVPN safe": "NordVPN è sicuro",
        "What is NordVPN": "Cos'è NordVPN",
        "Does NordVPN log my data": "NordVPN registra i miei dati",
        "What are the best alternatives to NordVPN": "Migliori alternative a NordVPN",
        "NordVPN vs alternatives: which is safer": "NordVPN vs alternative: qual è più sicuro",
        "trust score?": "punteggio di fiducia?",
        "Scores update as new data becomes available": "I punteggi si aggiornano quando nuovi dati diventano disponibili",
        "In the vpn category": "Nella categoria VPN",
        "full safety report for detailed privacy analysis": "rapporto di sicurezza completo per un'analisi dettagliata della privacy",
        "jurisdiction databases, independent audit reports, protocol analysis, and incident history": "database giurisdizionali, rapporti di audit indipendenti, analisi dei protocolli e cronologia degli incidenti",
        "has undergone third-party security audits verifying its infrastructure and no-logs claims": "ha superato audit di sicurezza di terze parti che verificano la sua infrastruttura e le affermazioni di no-log",
        "widely used VPN service": "servizio VPN ampiamente utilizzato",
        "multiple public sources including package registries, GitHub, NVD, OSV.dev, and OpenSSF Scorecard": "molteplici fonti pubbliche tra cui registri di pacchetti, GitHub, NVD, OSV.dev e OpenSSF Scorecard",
        "What does a Nerq Trust Score": "Cosa significa un Nerq Trust Score",
        "Are these safest": "Sono questi i più sicuri",
        "How are safest": "Come vengono classificati i più sicuri",
        "The #1 safest": "Il più sicuro #1",
        "The #1": "Il n. 1",
        "According to Nerq": "Secondo Nerq",
        "How are": "Come vengono",
        "What are the best": "Quali sono i migliori",
        "Logging policy": "Politica di registrazione",
        "Safety Guide": "Guida alla Sicurezza",
        "passes trust threshold": "supera la soglia di fiducia",
        "Recommended for use": "Raccomandato per l'uso",
        "This score is based on automated analysis of security, maintenance, community, and quality signals": "Questo punteggio si basa sull'analisi automatizzata di segnali di sicurezza, manutenzione, community e qualità",
        "According to independent audit reports": "Secondo i rapporti di audit indipendenti",
        "No known data breaches associated with this service": "Nessuna violazione di dati nota associata a questo servizio",
        "This is a strong positive signal": "Questo è un forte segnale positivo",
        "logging policy": "politica di registrazione",
        "Full analysis": "Analisi completa",
        "Server infrastructure": "Infrastruttura server",
        "It is recommended": "È raccomandato",
        "most VPN providers have not been independently audited": "la maggior parte dei provider VPN non è stata sottoposta a revisione indipendente",
        "Nerq analyzes over": "Nerq analizza oltre",
        "is based in": "ha sede in",
        "outside all Eyes surveillance alliances": "al di fuori di tutte le alleanze di sorveglianza Eyes",
        "a privacy advantage": "un vantaggio per la privacy",
        "has been independently audited to verify its privacy claims": "è stato sottoposto a revisione indipendente per verificare le sue affermazioni sulla privacy",
        "Serving": "Serve",
        "Related Safety Rankings": "Classifiche di sicurezza correlate",
        "Complete Your Privacy Setup": "Completa la configurazione della privacy",
        "Browse Categories": "Sfoglia le categorie",
        "Safest VPNs": "VPN più sicure",
        "Most Private Apps": "App più private",
        "Recently Analyzed": "Analizzati di recente",
        "What are the best alternatives to": "Quali sono le migliori alternative a",
        "which is safer": "qual è più sicuro",
        "logging practices": "pratiche di registrazione",
        "ownership transparency": "trasparenza proprietaria",
        "Popular in": "Popolare in",
        "Popularity": "Popolarità",
        "Not Yet Analyzed": "Non ancora analizzato",
        # ── Vertical-specific strings ──
        "Privacy Assessment": "Valutazione della Privacy",
        "Breach History": "Cronologia Violazioni",
        "Encryption": "Crittografia",
        "Build Your Security Stack": "Costruisci il Tuo Kit di Sicurezza",
        "Best VPNs": "Migliori VPN",
        "Best Password Managers": "Migliori Gestori di Password",
        "Best Antivirus": "Miglior Antivirus",
        "Security Assessment": "Valutazione di Sicurezza",
        "Security & Compliance": "Sicurezza e Conformità",
        "Combine these tools for comprehensive protection:": "Combina questi strumenti per una protezione completa:",
        # Title / H1
        "Independent Trust & Security Analysis": "Analisi indipendente di fiducia e sicurezza",
        "Independent Trust &amp; Security Analysis": "Analisi indipendente di fiducia e sicurezza",
        # Verdicts
        "Yes, {name} is safe to use.": "Sì, {name} è sicuro da usare.",
        "Use {name} with some caution.": "Usa {name} con cautela.",
        "Exercise caution with {name}.": "Fai attenzione con {name}.",
        "{name} has significant trust concerns.": "{name} presenta problemi significativi di fiducia.",
        "Passes Nerq Verified threshold": "Soddisfa la soglia verificata Nerq",
        "Below Nerq Verified threshold": "Sotto la soglia verificata Nerq",
        "Significant trust gaps detected": "Rilevate lacune significative nella fiducia",
        "Build Your Security Stack": "보안 스택 구축",
        "Best Password Managers": "최고의 비밀번호 관리자",
        "Combine these tools for comprehensive protection:": "이 도구들을 결합하여 종합적으로 보호하세요:",
        # Section headings
        "Trust Score Breakdown": "Dettagli punteggio di fiducia",
        "Safety Score Breakdown": "Dettagli punteggio di sicurezza",
        "Key Findings": "Risultati principali",
        "Key Safety Findings": "Risultati principali sulla sicurezza",
        "Detailed Score Analysis": "Analisi dettagliata del punteggio",
        "Frequently Asked Questions": "Domande frequenti",
        "Safer Alternatives": "Alternative più sicure",
        "Popular Alternatives": "Alternative popolari",
        "Community Reviews": "Recensioni della comunità",
        "Regulatory Compliance": "Conformità normativa",
        "How we calculated this score": "Come abbiamo calcolato questo punteggio",
        "What We Know About": "Cosa sappiamo di",
        # Safety Guide
        "Safety Guide:": "Guida alla sicurezza:",
        "What is": "Cos'è",
        "How to Verify Safety": "Come verificare la sicurezza",
        "Key Safety Concerns for": "Principali problemi di sicurezza per",
        "Trust Assessment": "Valutazione della fiducia",
        "Key Takeaways": "Punti chiave",
        "Recommended for use — passes trust threshold.": "Raccomandato — soddisfa la soglia di fiducia.",
        "Review carefully before use — below trust threshold.": "Verifica attentamente prima dell'uso — sotto la soglia di fiducia.",
        "Always verify independently using the": "Verifica sempre in modo indipendente utilizzando",
        "When evaluating any": "Quando si valuta qualsiasi",
        "watch for:": "prestare attenzione a:",
        # Cross-product
        "Across Platforms": "Su altre piattaforme",
        "across platforms": "su altre piattaforme",
        "Same developer/company in other registries:": "Stesso sviluppatore/azienda in altri registri:",
        # King sections
        "What data does": "Quali dati raccoglie",
        "collect?": "?",
        "Is": "È",
        "secure?": "sicuro?",
        "Full analysis:": "Analisi completa:",
        "Privacy Report": "Report sulla privacy",
        "Privacy review": "Revisione della privacy",
        "Security Report": "Report di sicurezza",
        # Dimensions
        "Security": "Sicurezza",
        "Privacy": "Privacy",
        "Reliability": "Affidabilità",
        "Transparency": "Trasparenza",
        "Maintenance": "Manutenzione",
        "Overall Trust": "Fiducia complessiva",
        "Composite trust score": "Punteggio di fiducia complessivo",
        "across all available signals": "su tutti i segnali disponibili",
        # Methodology
        "Nerq analyzes over 7.5 million entities across 26 registries": "Nerq analizza oltre 7,5 milioni di entità in 26 registri",
        "using the same methodology, enabling direct cross-entity comparison": "utilizzando la stessa metodologia, consentendo il confronto diretto tra entità",
        "Scores are updated continuously as new data becomes available": "I punteggi vengono aggiornati continuamente quando sono disponibili nuovi dati",
        "This page was last reviewed on": "Questa pagina è stata revisionata l'ultima volta il",
        "Data version": "Versione dei dati",
        "Full methodology documentation": "Documentazione completa della metodologia",
        "Machine-readable data (JSON API)": "Dati leggibili dalle macchine (JSON API)",
        "Machine-readable data (JSON)": "Dati leggibili dalle macchine (JSON)",
        # Meta / small text
        "Last analyzed:": "Ultima analisi:",
        "Last updated": "Ultimo aggiornamento",
        "Updated daily": "Aggiornato quotidianamente",
        "Independent. Data-driven.": "Indipendente. Basato sui dati.",
        "verified": "verificato",
        "Data sourced from": "Dati provenienti da",
        "Based on": "Basato su",
        "dimensions": "dimensioni",
        "independent data dimensions": "dimensioni di dati indipendenti",
        "strong": "forte",
        "moderate": "moderato",
        "weak": "debole",
        "actively maintained": "attivamente mantenuto",
        "moderately maintained": "moderatamente mantenuto",
        "low maintenance activity": "bassa attività di manutenzione",
        "well-documented": "ben documentato",
        "partial documentation": "documentazione parziale",
        "limited documentation": "documentazione limitata",
        "community adoption": "adozione della comunità",
        "stars on": "stelle su",
        # Cross-links
        "Safety": "Sicurezza",
        "Legit?": "Affidabile?",
        "Scam?": "Truffa?",
        "Review": "Recensione",
        "Alternatives": "Alternative",
        "Compare": "Confronta",
        "Best in Category": "Il migliore nella categoria",
        "Who Owns?": "Chi è il proprietario?",
        "What Is?": "Cos'è?",
        "Sells Data?": "Vende dati?",
        "Hacked?": "Violato?",
        "Safe for Kids?": "Sicuro per i bambini?",
        "Pros &amp; Cons": "Pro &amp; Contro",
        # FAQ answers
        "Nerq Verified — meets the 70+ trust threshold.": "Nerq verificato — soddisfa la soglia di fiducia 70+.",
        "Below the Nerq Verified threshold of 70.": "Sotto la soglia verificata Nerq di 70.",
        "Has not yet reached the Nerq Verified threshold of 70.": "Non ha ancora raggiunto la soglia verificata Nerq di 70.",
        "Strongest signal:": "Segnale più forte:",
        "Score based on": "Punteggio basato su",
        "security": "sicurezza",
        "maintenance": "manutenzione",
        "popularity": "popolarità",
        "documentation": "documentazione",
        "compliance": "conformità",
        # Verdict box
        "Safe": "Sicuro",
        "Use Caution": "Cautela",
        "Avoid": "Da evitare",
        # Long text patterns
        "is a Node.js package": "è un pacchetto Node.js",
        "is a Python package": "è un pacchetto Python",
        "is a Rust crate": "è una libreria Rust",
        "is a Chrome extension": "è un'estensione Chrome",
        "is a Firefox extension": "è un'estensione Firefox",
        "is a VS Code extension": "è un'estensione VS Code",
        "is a WordPress plugin": "è un plugin WordPress",
        "is a iOS app": "è un'app iOS",
        "is a Android app": "è un'app Android",
        "is a VPN service": "è un servizio VPN",
        "is a game": "è un gioco",
        "is a website": "è un sito web",
        "is a SaaS platform": "è una piattaforma SaaS",
        "is a dietary supplement": "è un integratore alimentare",
        "is a cosmetic ingredient": "è un ingrediente cosmetico",
        "is a food": "è un alimento",
        "is a travel destination": "è una destinazione di viaggio",
        "is a nonprofit organization": "è un'organizzazione non profit",
        "with a Nerq Trust Score of": "con un Punteggio di fiducia Nerq di",
        "with a Nerq Safety Score of": "con un Punteggio di sicurezza Nerq di",
        "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "Soddisfa la soglia di fiducia Nerq con segnali forti in sicurezza, manutenzione e adozione della comunità",
        "It has moderate trust signals but shows some areas of concern": "Ha segnali di fiducia moderati ma mostra alcune aree di preoccupazione",
        "It has below-average trust signals with significant gaps": "Ha segnali di fiducia inferiori alla media con lacune significative",
        "review the full report below for specific considerations": "consulta il report completo di seguito per considerazioni specifiche",
        "This score is based on automated analysis of security, maintenance, community, and quality signals.": "Questo punteggio si basa sull'analisi automatizzata dei segnali di sicurezza, manutenzione, comunità e qualità.",
        "You can also check the trust score via API:": "Puoi anche verificare il punteggio di fiducia tramite API:",
        "As a development package": "Come pacchetto di sviluppo",
        "does not directly collect end-user personal data": "non raccoglie direttamente dati personali degli utenti finali",
        "However, applications built with it may collect data depending on implementation": "Tuttavia, le applicazioni costruite con esso possono raccogliere dati in base all'implementazione",
        "Review the package's dependencies for potential supply chain risks": "Verifica le dipendenze del pacchetto per potenziali rischi della catena di fornitura",
        "License information not available": "Informazioni sulla licenza non disponibili",
        "Open-source packages allow independent security review of the source code": "I pacchetti open source consentono la revisione indipendente della sicurezza del codice sorgente",
        "to check for vulnerabilities": "per verificare le vulnerabilità",
        "Review the": "Controlla",
        "GitHub repository for recent commits": "il repository GitHub per i commit recenti",
        "dependency vulnerabilities, malicious packages, typosquatting": "vulnerabilità delle dipendenze, pacchetti dannosi, typosquatting",
        "Run your package manager's audit command": "Esegui il comando di audit del tuo gestore di pacchetti",
        "to check for known vulnerabilities in your dependency tree": "per verificare le vulnerabilità note nell'albero delle dipendenze",
        "This meets the recommended security threshold for production use": "Soddisfa la soglia di sicurezza raccomandata per l'uso in produzione",
        "Nerq monitors this entity against NVD, OSV.dev, and registry-specific vulnerability databases": "Nerq monitora questa entità rispetto a NVD, OSV.dev e database di vulnerabilità specifici del registro",
        "for ongoing security assessment": "per la valutazione continua della sicurezza",
        "Yes, it is safe to use.": "Sì, è sicuro da usare.",
        "Use with some caution.": "Usa con cautela.",
        "Exercise caution.": "Fai attenzione.",
        "Significant trust concerns.": "Problemi significativi di fiducia.",
        "maintained by": "mantenuto da",
        "is computed from": "è calcolato da",
        "The score reflects": "Il punteggio riflette",
        "independent dimensions": "dimensioni indipendenti",
        "Each dimension is weighted equally to produce the composite trust score": "Ogni dimensione ha lo stesso peso per produrre il punteggio di fiducia complessivo",
        "No reviews yet.": "Ancora nessuna recensione.",
        "Be the first to review": "Sii il primo a recensire",
        "Write a review": "Scrivi una recensione",
        "Higher-rated": "Con punteggio più alto",
        "you may want to consider:": "potresti voler considerare:",
        "under assessment": "in fase di valutazione",
        # Health disclaimers
        "Important Notice:": "Avviso importante:",
        "educational and informational purposes only": "solo a scopo educativo e informativo",
        "does not constitute medical advice": "non costituisce consulenza medica",
        "Consult a qualified healthcare professional": "Consulta un professionista sanitario qualificato",
        "Full health disclaimer": "Dichiarazione completa sulla salute",
        "Full disclaimer": "Dichiarazione completa",
    },
    "ko": {
        "Is NordVPN safe": "NordVPN은 안전한가요",
        "What is NordVPN": "NordVPN이란",
        "Does NordVPN log my data": "NordVPN이 내 데이터를 기록하나요",
        "What are the best alternatives to NordVPN": "NordVPN의 최고 대안은",
        "NordVPN vs alternatives: which is safer": "NordVPN 대 대안: 어느 것이 더 안전한가요",
        "trust score?": "신뢰 점수?",
        "Scores update as new data becomes available": "새로운 데이터가 제공되면 점수가 업데이트됩니다",
        "In the vpn category": "VPN 카테고리에서",
        "full safety report for detailed privacy analysis": "상세한 프라이버시 분석을 위한 ��체 안전 보고서",
        "has undergone third-party security audits verifying its infrastructure and no-logs claims": "인프라와 노로그 주장을 검증하는 제3자 보안 감사를 받았습니다",
        "widely used VPN service": "널리 사용되는 VPN 서비스",
        "multiple public sources including package registries, GitHub, NVD, OSV.dev, and OpenSSF Scorecard": "패키지 레지스트리, GitHub, NVD, OSV.dev, OpenSSF Scorecard를 포함한 여러 공개 소스",
        "The #1 safest": "가장 안전한 1위",
        "How are safest": "가장 안전한 것은 어떻게 순위가 매겨지나요",
        "Are these safest": "이 가장 안전한 것들은",
        "What does a Nerq Trust Score": "Nerq Trust Score란",
        "The #1": "1위",
        "According to Nerq": "Nerq에 따르면",
        "How are": "어떻게",
        "ranked by Nerq Trust Score": "Nerq Trust Score 기준으로 순위가 매겨지나요",
        "What are the best": "최고의",
        "Are these rankings updated regularly": "이 순위는 정기적으로 업데이트되나요",
        "What does a Nerq Trust Score measure": "Nerq Trust Score는 무엇을 측정하나요",
        "How does Nerq evaluate": "Nerq는 어떻게 평가하나요",
        "Are these safe to use": "이것들은 안전하게 사용할 수 있나요",
        "Security score": "보안 점수",
        "Based in": "소재지:",
        "logging policy": "로깅 정책",
        "Server infrastructure": "서버 인프라",
        "most VPN providers have not been independently audited": "대부분의 VPN 제공업체는 독립적으로 감사를 받지 않았습니다",
        "This is a strong positive signal": "이것은 강력한 긍정적 신호입니다",
        "No known data breaches associated with this service": "이 서비스와 관련된 알려진 데이터 침해가 없습니다",
        "According to independent audit reports": "독립 감사 보고서에 따르면",
        "Safety Guide": "안전 가이드",
        "strong)": "강함)",
        "Full analysis": "전체 분석",
        "It is recommended": "권장",
        "Dimension": "차원",
        "Score": "점수",
        "outside all Eyes surveillance alliances": "모든 Eyes 감시 동맹 밖에",
        "a privacy advantage": "프라이버시 이점",
        "has been independently audited to verify its privacy claims": "프라이버시 주장을 검증하기 위해 독립적으로 감사를 받았습니다",
        "Serving": "사용자 수:",
        "Related Safety Rankings": "관련 안전 순위",
        "Complete Your Privacy Setup": "프라이버시 설정을 완성하세요",
        "Add a password manager to your VPN for full protection": "완전한 보호를 위해 VPN에 비밀번호 관리자를 추가하세요",
        "Browse Categories": "카테고리 탐색",
        "Safest VPNs": "가장 안전한 VPN",
        "Most Private Apps": "가장 프라이빗한 앱",
        "Recently Analyzed": "최근 분석",
        "What are the best alternatives to": "의 가장 좋은 대안은",
        "which is safer": "어느 것이 더 안전한가요",
        "logging practices": "로깅 관행",
        "ownership transparency": "소유권 투명성",
        "Popular in": "인기",
        "Popularity": "인기도",
        "is based in": "에 본사를 두고 있습니다",
        "Not Yet Analyzed": "아직 분석되지 않음",
        "Privacy Assessment": "개인정보 보호 평가",
        "Breach History": "침해 이력",
        "Encryption": "암호화",
        "Zero-Knowledge Architecture": "제로 지식 아키텍처",
        "Open Source": "오픈소스",
        "Infrastructure": "인프라",
        "Security & Compliance": "보안 및 컴플라이언스",
        "Data Location": "데이터 위치",
        "Security Incidents": "보안 사고",
        "Independent Lab Results": "독립 연구소 결과",
        "Security Track Record": "보안 실적",
        "Best VPNs": "최고의 VPN",
        "jurisdiction databases, independent audit reports, protocol analysis, and incident history": "관할권 데이터베이스, 독립 감사 보고서, 프로토콜 분석 및 사고 이력",
        "Panama jurisdiction": "파나마 관할권",
        "outside the Five Eyes, Nine Eyes, and Fourteen Eyes surveillance alliances": "파이브아이즈, 나인아이즈, 포틴아이즈 감시 동맹 밖에 위치",
        "jurisdiction": "관할권",
        "Five Eyes": "파이브아이즈",
        "Independent": "독립적",
        "Audited no-log": "감사된 노로그",
        "Claimed no-log": "노로그 주장",
        "Check jurisdiction": "관할권 확인",
        "Verify independent audit exists": "독립 감사 확인",
        "Review logging policy": "로깅 정책 검토",
        "Antivirus": "백신",
        # ── Vertical-specific strings (auto-generated) ──
        "Build Your Security Stack": "보안 스택 구축",
        "Best Password Managers": "최고의 비밀번호 관리자",
        "Combine these tools for comprehensive protection:": "이 도구들을 결합하여 종합적으로 보호하세요:",
        "Best Antivirus": "최고의 백신",
        "Security Assessment": "보안 평가",
        "Ecommerce": "전자상거래",
        "Hosting Assessment": "호스팅 평가",
        "Antivirus Assessment": "백신 평가",
        "SaaS Assessment": "SaaS 평가",
        "Website Builder Assessment": "웹사이트 빌더 평가",
        "Exchange Assessment": "거래소 평가",
        "Combine these tools for comprehensive protection:": "이 도구들을 결합하여 종합적으로 보호하세요:",
        "Proof of Reserves": "준비금 증명",
        # Title / H1
        "Independent Trust & Security Analysis": "독립적인 신뢰 및 보안 분석",
        "Independent Trust &amp; Security Analysis": "독립적인 신뢰 및 보안 분석",
        # Verdicts
        "Yes, {name} is safe to use.": "네, {name}은(는) 사용하기에 안전합니다.",
        "Use {name} with some caution.": "{name}을(를) 주의하며 사용하세요.",
        "Exercise caution with {name}.": "{name}에 대해 주의하세요.",
        "{name} has significant trust concerns.": "{name}에 심각한 신뢰 문제가 있습니다.",
        "Passes Nerq Verified threshold": "Nerq 인증 기준 충족",
        "Below Nerq Verified threshold": "Nerq 인증 기준 미달",
        "Significant trust gaps detected": "심각한 신뢰 격차 발견",
        # Section headings
        "Trust Score Breakdown": "신뢰 점수 세부 정보",
        "Safety Score Breakdown": "보안 점수 세부 정보",
        "Key Findings": "주요 발견",
        "Key Safety Findings": "주요 보안 발견",
        "Detailed Score Analysis": "상세 점수 분석",
        "Frequently Asked Questions": "자주 묻는 질문",
        "Safer Alternatives": "더 안전한 대안",
        "Popular Alternatives": "인기 대안",
        "Community Reviews": "커뮤니티 리뷰",
        "Regulatory Compliance": "규정 준수",
        "How we calculated this score": "이 점수를 어떻게 계산했나요",
        "What We Know About": "알려진 정보:",
        # Safety Guide
        "Safety Guide:": "보안 가이드:",
        "What is": "무엇인가요",
        "How to Verify Safety": "안전성 확인 방법",
        "Key Safety Concerns for": "주요 보안 문제:",
        "Trust Assessment": "신뢰 평가",
        "Key Takeaways": "주요 요점",
        "Recommended for use — passes trust threshold.": "사용 권장 — 신뢰 기준 충족.",
        "Review carefully before use — below trust threshold.": "사용 전 신중히 검토 — 신뢰 기준 미달.",
        "Always verify independently using the": "항상 다음을 사용하여 독립적으로 확인하세요:",
        "When evaluating any": "평가 시 다음을 확인하세요:",
        "watch for:": "주의 사항:",
        # Cross-product
        "Across Platforms": "다른 플랫폼",
        "across platforms": "다른 플랫폼",
        "Same developer/company in other registries:": "다른 레지스트리의 동일 개발자/회사:",
        # King sections
        "What data does": "어떤 데이터를 수집하나요",
        "collect?": "수집하나요?",
        "Is": "안전한가요",
        "secure?": "안전한가요?",
        "Full analysis:": "전체 분석:",
        "Privacy Report": "개인정보 보고서",
        "Privacy review": "개인정보 리뷰",
        "Security Report": "보안 보고서",
        # Dimensions
        "Security": "보안",
        "Privacy": "개인정보",
        "Reliability": "신뢰성",
        "Transparency": "투명성",
        "Maintenance": "유지보수",
        "Overall Trust": "전체 신뢰도",
        "Composite trust score": "종합 신뢰 점수",
        "across all available signals": "모든 가용 신호 기반",
        # Methodology
        "Nerq analyzes over 7.5 million entities across 26 registries": "Nerq는 26개 레지스트리에서 750만 개 이상의 엔터티를 분석합니다",
        "using the same methodology, enabling direct cross-entity comparison": "동일한 방법론을 사용하여 엔터티 간 직접 비교를 가능하게 합니다",
        "Scores are updated continuously as new data becomes available": "새로운 데이터가 제공되면 점수가 지속적으로 업데이트됩니다",
        "This page was last reviewed on": "이 페이지의 마지막 검토일:",
        "Data version": "데이터 버전",
        "Full methodology documentation": "전체 방법론 문서",
        "Machine-readable data (JSON API)": "기계 판독 가능 데이터 (JSON API)",
        "Machine-readable data (JSON)": "기계 판독 가능 데이터 (JSON)",
        # Meta / small text
        "Last analyzed:": "최종 분석:",
        "Last updated": "최종 업데이트",
        "Updated daily": "매일 업데이트",
        "Independent. Data-driven.": "독립적. 데이터 기반.",
        "verified": "인증됨",
        "Data sourced from": "데이터 출처:",
        "Based on": "기반:",
        "dimensions": "차원",
        "independent data dimensions": "독립적인 데이터 차원",
        "strong": "강함",
        "moderate": "보통",
        "weak": "약함",
        "actively maintained": "활발히 유지보수됨",
        "moderately maintained": "보통 수준으로 유지보수됨",
        "low maintenance activity": "유지보수 활동 저조",
        "well-documented": "문서화 잘 됨",
        "partial documentation": "부분적 문서화",
        "limited documentation": "제한된 문서화",
        "community adoption": "커뮤니티 채택",
        "stars on": "스타 수:",
        # Cross-links
        "Safety": "보안",
        "Legit?": "신뢰할 수 있나요?",
        "Scam?": "사기인가요?",
        "Review": "리뷰",
        "Alternatives": "대안",
        "Compare": "비교",
        "Best in Category": "카테고리 최고",
        "Who Owns?": "소유자는 누구?",
        "What Is?": "무엇인가요?",
        "Sells Data?": "데이터를 판매하나요?",
        "Hacked?": "해킹당했나요?",
        "Safe for Kids?": "아이에게 안전한가요?",
        "Pros &amp; Cons": "장점 &amp; 단점",
        # FAQ answers
        "Nerq Verified — meets the 70+ trust threshold.": "Nerq 인증 — 신뢰 기준 70+ 충족.",
        "Below the Nerq Verified threshold of 70.": "Nerq 인증 기준 70 미달.",
        "Has not yet reached the Nerq Verified threshold of 70.": "아직 Nerq 인증 기준 70에 도달하지 못했습니다.",
        "Strongest signal:": "가장 강력한 신호:",
        "Score based on": "점수 기반:",
        "security": "보안",
        "maintenance": "유지보수",
        "popularity": "인기도",
        "documentation": "문서화",
        "compliance": "규정 준수",
        # Verdict box
        "Safe": "안전함",
        "Use Caution": "주의",
        "Avoid": "피하기",
        # Long text patterns
        "is a Node.js package": "Node.js 패키지입니다",
        "is a Python package": "Python 패키지입니다",
        "is a Rust crate": "Rust 크레이트입니다",
        "is a Chrome extension": "Chrome 확장 프로그램입니다",
        "is a Firefox extension": "Firefox 확장 프로그램입니다",
        "is a VS Code extension": "VS Code 확장 프로그램입니다",
        "is a WordPress plugin": "WordPress 플러그인입니다",
        "is a iOS app": "iOS 앱입니다",
        "is a Android app": "Android 앱입니다",
        "is a VPN service": "VPN 서비스입니다",
        "is a game": "게임입니다",
        "is a website": "웹사이트입니다",
        "is a SaaS platform": "SaaS 플랫폼입니다",
        "is a dietary supplement": "식이 보충제입니다",
        "is a cosmetic ingredient": "화장품 성분입니다",
        "is a food": "식품입니다",
        "is a travel destination": "여행지입니다",
        "is a nonprofit organization": "비영리 단체입니다",
        "with a Nerq Trust Score of": "Nerq 신뢰 점수",
        "with a Nerq Safety Score of": "Nerq 보안 점수",
        "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "보안, 유지보수 및 커뮤니티 채택에서 강력한 신호로 Nerq 신뢰 기준을 충족합니다",
        "It has moderate trust signals but shows some areas of concern": "보통 수준의 신뢰 신호가 있지만 일부 우려 사항이 있습니다",
        "It has below-average trust signals with significant gaps": "평균 이하의 신뢰 신호와 심각한 격차가 있습니다",
        "review the full report below for specific considerations": "구체적인 사항은 아래 전체 보고서를 참조하세요",
        "This score is based on automated analysis of security, maintenance, community, and quality signals.": "이 점수는 보안, 유지보수, 커뮤니티 및 품질 신호의 자동 분석을 기반으로 합니다.",
        "You can also check the trust score via API:": "API를 통해 신뢰 점수를 직접 확인할 수도 있습니다:",
        "As a development package": "개발 패키지로서",
        "does not directly collect end-user personal data": "최종 사용자 개인 데이터를 직접 수집하지 않습니다",
        "However, applications built with it may collect data depending on implementation": "그러나 이를 사용하여 구축된 애플리케이션은 구현 방식에 따라 데이터를 수집할 수 있습니다",
        "Review the package's dependencies for potential supply chain risks": "공급망 위험에 대한 패키지 의존성을 검토하세요",
        "License information not available": "라이선스 정보 없음",
        "Open-source packages allow independent security review of the source code": "오픈 소스 패키지는 소스 코드의 독립적인 보안 검토를 허용합니다",
        "to check for vulnerabilities": "취약점을 확인하려면",
        "Review the": "다음을 검토하세요:",
        "GitHub repository for recent commits": "최근 커밋에 대한 GitHub 저장소",
        "dependency vulnerabilities, malicious packages, typosquatting": "의존성 취약점, 악성 패키지, 타이포스쿼팅",
        "Run your package manager's audit command": "패키지 관리자의 감사 명령을 실행하세요",
        "to check for known vulnerabilities in your dependency tree": "의존성 트리의 알려진 취약점을 확인하려면",
        "This meets the recommended security threshold for production use": "프로덕션 사용을 위한 권장 보안 기준을 충족합니다",
        "Nerq monitors this entity against NVD, OSV.dev, and registry-specific vulnerability databases": "Nerq는 NVD, OSV.dev 및 레지스트리별 취약점 데이터베이스를 기준으로 이 엔터티를 모니터링합니다",
        "for ongoing security assessment": "지속적인 보안 평가를 위해",
        "Yes, it is safe to use.": "네, 사용하기에 안전합니다.",
        "Use with some caution.": "주의하며 사용하세요.",
        "Exercise caution.": "주의하세요.",
        "Significant trust concerns.": "심각한 신뢰 문제가 있습니다.",
        "maintained by": "유지보수:",
        "is computed from": "다음에서 계산됩니다:",
        "The score reflects": "점수는 다음을 반영합니다:",
        "independent dimensions": "독립적인 차원",
        "Each dimension is weighted equally to produce the composite trust score": "각 차원은 동등하게 가중되어 종합 신뢰 점수를 산출합니다",
        "No reviews yet.": "아직 리뷰가 없습니다.",
        "Be the first to review": "첫 번째 리뷰를 작성하세요",
        "Write a review": "리뷰 작성",
        "Higher-rated": "더 높은 평가를 받은",
        "you may want to consider:": "다음을 고려해 보세요:",
        "under assessment": "평가 중",
        # Health disclaimers
        "Important Notice:": "중요 안내:",
        "educational and informational purposes only": "교육 및 정보 제공 목적으로만",
        "does not constitute medical advice": "의료 조언이 아닙니다",
        "Consult a qualified healthcare professional": "자격을 갖춘 의료 전문가와 상담하세요",
        "Full health disclaimer": "전체 건강 면책 조항",
        "Full disclaimer": "전체 면책 조항",
    },
    "vi": {
        "What is NordVPN": "NordVPN là gì",
        "What are the best alternatives to NordVPN": "Các lựa chọn thay thế tốt nhất cho NordVPN",
        "NordVPN vs alternatives: which is safer": "NordVPN so với các lựa chọn: cái nào an toàn hơn",
        "Does NordVPN log my data": "NordVPN có ghi dữ liệu của tôi không",
        "trust score?": "điểm tin cậy?",
        "Is NordVPN safe": "NordVPN có an toàn không",
        "Run npm audit": "Chạy npm audit",
        "full safety report for detailed privacy analysis": "báo cáo an toàn đầy đủ để phân tích quyền riêng tư chi tiết",
        "In the npm category": "Trong danh mục npm",
        "In the vpn category": "Trong danh mục VPN",
        "Scores update as new data becomes available": "Điểm được cập nhật khi có dữ liệu mới",
        "multiple public sources including package registries, GitHub, NVD, OSV.dev, and OpenSSF Scorecard": "nhiều nguồn công khai bao gồm registry gói, GitHub, NVD, OSV.dev và OpenSSF Scorecard",
        "The #1 safest": "An toàn nhất số 1",
        "How are safest": "Các VPN an toàn nhất được xếp hạng như thế nào",
        "Are these safest": "Các VPN an toàn nhất này có an toàn không",
        "What does a Nerq Trust Score": "Nerq Trust Score có nghĩa gì",
        "The #1": "Số 1",
        "According to Nerq": "Theo Nerq",
        "How are": "Được xếp hạng như thế nào",
        "ranked by Nerq Trust Score": "theo Nerq Trust Score",
        "What are the best": "Tốt nhất là gì",
        "Are these rankings updated regularly": "Các bảng xếp hạng này có được cập nhật thường xuyên không",
        "What does a Nerq Trust Score measure": "Nerq Trust Score đo lường gì",
        "How does Nerq evaluate": "Nerq đánh giá như thế nào",
        "Are these safe to use": "Có an toàn để sử dụng không",
        "{name} Privacy Report": "Báo cáo quyền riêng tư {name}",
        "has undergone third-party security audits verifying its infrastructure and no-logs claims": "đã trải qua các cuộc kiểm toán bảo mật bên thứ ba xác minh cơ sở hạ tầng và tuyên bố không ghi nhật ký",
        "This is a strong positive signal — most VPN providers have not been independently audited": "Đây là tín hiệu tích cực mạnh — hầu hết các nhà cung cấp VPN chưa được kiểm toán độc lập",
        "has not published results from an independent security audit": "chưa công bố kết quả từ một cuộc kiểm toán bảo mật độc lập",
        "While this does not indicate a security issue, audited VPNs provide higher assurance": "Mặc dù điều này không chỉ ra vấn đề bảo mật, VPN đã được kiểm toán cung cấp đảm bảo cao hơn",
        "Security score": "Điểm bảo mật",
        "Primary encryption protocol": "Giao thức mã hóa chính",
        "which is considered industry-standard for VPN connections": "được coi là tiêu chuẩn ngành cho kết nối VPN",
        "Independent security audit verified": "Kiểm toán bảo mật độc lập đã xác minh",
        "has no known data breaches and has been independently audited": "không có vi phạm dữ liệu đã biết và đã được kiểm toán độc lập",
        "uses AES-256-CBC (industry standard), Argon2id (brute-force resistant key derivation)": "sử dụng AES-256-CBC (tiêu chuẩn ngành), Argon2id (dẫn xuất khóa chống brute-force)",
        "uses a zero-knowledge architecture": "sử dụng kiến trúc zero-knowledge",
        "your master password and vault data are encrypted locally and never sent to the server in plaintext": "mật khẩu chính và dữ liệu vault của bạn được mã hóa cục bộ và không bao giờ được gửi đến máy chủ dưới dạng văn bản thuần",
        "is open source with": "là mã nguồn mở với",
        "GitHub stars": "sao GitHub",
        "Based in": "Có trụ sở tại",
        "Independently audited": "Đã kiểm toán độc lập",
        "No published independent audit": "Không có kiểm toán độc lập được công bố",
        "logging policy": "chính sách ghi nhật ký",
        "Safety Guide": "Hướng dẫn an toàn",
        "You can also check the trust score via API": "Bạn cũng có thể kiểm tra điểm tin cậy qua API",
        "meets Nerq trust threshold": "đạt ngưỡng tin cậy Nerq",
        "passes trust threshold": "vượt ngưỡng tin cậy",
        "Recommended for use": "Được khuyến nghị sử dụng",
        "This score is based on automated analysis of security, maintenance, community, and quality signals": "Điểm này dựa trên phân tích tự động các tín hiệu bảo mật, bảo trì, cộng đồng và chất lượng",
        "widely used": "được sử dụng rộng rãi",
        "No known data breaches associated with this service": "Không có vi phạm dữ liệu đã biết liên quan đến dịch vụ này",
        "This is a strong positive signal": "Đây là tín hiệu tích cực mạnh",
        "most VPN providers have not been independently audited": "hầu hết các nhà cung cấp VPN chưa được kiểm toán độc lập",
        "Full analysis": "Phân tích đầy đủ",
        "Same developer": "Cùng nhà phát triển",
        "It is recommended": "Được khuyến nghị",
        "below the recommended threshold": "dưới ngưỡng khuyến nghị",
        "Dimension": "Chiều",
        "Score": "Điểm",
        "Data from": "Dữ liệu từ",
        "is based in": "có trụ sở tại",
        "outside all Eyes surveillance alliances": "nằm ngoài tất cả các liên minh giám sát Eyes",
        "a privacy advantage": "một lợi thế về quyền riêng tư",
        "has been independently audited to verify its privacy claims": "đã được kiểm toán độc lập để xác minh các tuyên bố về quyền riêng tư",
        "Serving": "Phục vụ",
        "users": "người dùng",
        "Related Safety Rankings": "Xếp hạng an toàn liên quan",
        "Complete Your Privacy Setup": "Hoàn thiện bảo mật của bạn",
        "Add a password manager to your VPN for full protection": "Thêm trình quản lý mật khẩu vào VPN để bảo vệ đầy đủ",
        "Add Antivirus Protection": "Thêm bảo vệ diệt virus",
        "Complete your security with antivirus alongside your VPN": "Hoàn thiện bảo mật với phần mềm diệt virus cùng VPN",
        "servers in": "máy chủ tại",
        "countries": "quốc gia",
        "logging practices": "chính sách ghi nhật ký",
        "audit history": "lịch sử kiểm toán",
        "ownership transparency": "minh bạch quyền sở hữu",
        "are not subject to mandatory data retention laws or intelligence-sharing agreements": "không phải tuân thủ luật lưu giữ dữ liệu bắt buộc hay thỏa thuận chia sẻ tình báo",
        "Server infrastructure": "Hạ tầng máy chủ",
        "servers across": "máy chủ trên",
        "Logging policy": "Chính sách ghi nhật ký",
        "independently audited no-logs policy": "chính sách không ghi nhật ký đã được kiểm toán độc lập",
        "According to independent audit reports": "Theo báo cáo kiểm toán độc lập",
        "does not store connection logs, browsing activity, or DNS queries": "không lưu trữ nhật ký kết nối, hoạt động duyệt web hoặc truy vấn DNS",
        "score:": "điểm:",
        "Nerq analyzes over": "Nerq phân tích hơn",
        "What are the best alternatives to": "Các lựa chọn thay thế tốt nhất cho",
        "log my data": "có ghi dữ liệu của tôi không",
        "vs alternatives: which is safer": "so với các lựa chọn thay thế: cái nào an toàn hơn",
        "Popular in": "Phổ biến trong",
        "Browse Categories": "Duyệt danh mục",
        "Safest VPNs": "VPN an toàn nhất",
        "Most Private Apps": "Ứng dụng riêng tư nhất",
        "Recently Analyzed": "Phân tích gần đây",
        "strong)": "mạnh)",
        "widely used VPN service": "dịch vụ VPN được sử dụng rộng rãi",
        "Popularity": "Độ phổ biến",
        "more VPN services are being analyzed": "thêm nhiều dịch vụ VPN đang được phân tích",
        "check back soon": "hãy quay lại sớm",
        "Nerq assesses": "Nerq đánh giá",
        "data practices as part of its trust score": "thực hành dữ liệu như một phần của điểm tin cậy",
        "Review full safety report for detailed privacy analysis": "Xem báo cáo an toàn đầy đủ để phân tích quyền riêng tư chi tiết",
        "More VPN services are being analyzed for comparison": "Thêm nhiều dịch vụ VPN đang được phân tích để so sánh",
        "This is significant because VPN providers in": "Điều này quan trọng vì các nhà cung cấp VPN tại",
        "jurisdiction databases, independent audit reports, protocol analysis, and incident history": "cơ sở dữ liệu pháp lý, báo cáo kiểm toán độc lập, phân tích giao thức, và lịch sử sự cố",
        "Panama jurisdiction": "thuộc quyền tài phán Panama",
        "logging practices, jurisdiction, audit history, ownership transparency": "chính sách ghi nhật ký, quyền tài phán, lịch sử kiểm toán, minh bạch quyền sở hữu",
        "outside the Five Eyes, Nine Eyes, and Fourteen Eyes surveillance alliances": "nằm ngoài các liên minh giám sát Five Eyes, Nine Eyes và Fourteen Eyes",
        "non-allied jurisdictions are not subject to mandatory data retention laws or intelligence-sharing agreements": "các quốc gia ngoài liên minh không bắt buộc phải tuân thủ luật lưu giữ dữ liệu hay thỏa thuận chia sẻ tình báo",
        "jurisdiction": "quyền tài phán",
        "Five Eyes": "Five Eyes",
        "Independent": "Độc lập",
        "Audited no-log": "Không lưu nhật ký đã kiểm toán",
        "Claimed no-log": "Tuyên bố không lưu nhật ký",
        "Check jurisdiction": "Kiểm tra quyền tài phán",
        "Verify independent audit exists": "Xác minh có kiểm toán độc lập",
        "Review logging policy": "Xem xét chính sách ghi nhật ký",
        "Antivirus": "Diệt Virus",
        # ── Vertical-specific strings (auto-generated) ──
        "Privacy Assessment": "Đánh Giá Quyền Riêng Tư",
        "Breach History": "Lịch Sử Vi Phạm",
        "Encryption": "Mã Hóa",
        "Zero-Knowledge Architecture": "Kiến Trúc Zero-Knowledge",
        "Open Source": "Mã Nguồn Mở",
        "Jurisdiction": "Quyền Tài Phán",
        "Infrastructure": "Hạ Tầng",
        "Security & Compliance": "Bảo Mật & Tuân Thủ",
        "Data Location": "Vị Trí Dữ Liệu",
        "Security Incidents": "Sự Cố Bảo Mật",
        "Independent Lab Results": "Kết Quả Phòng Thí Nghiệm Độc Lập",
        "Security Track Record": "Hồ Sơ Bảo Mật",
        "Build Your Security Stack": "Xây Dựng Bộ Bảo Mật",
        "Best VPNs": "VPN Tốt Nhất",
        "Best Password Managers": "Trình Quản Lý Mật Khẩu Tốt Nhất",
        "Best Antivirus": "Phần Mềm Diệt Virus Tốt Nhất",
        "Security Assessment": "Đánh Giá Bảo Mật",
        "Ecommerce": "Thương Mại Điện Tử",
        "Hosting Assessment": "Đánh Giá Hosting",
        "Antivirus Assessment": "Đánh Giá Phần Mềm Diệt Virus",
        "SaaS Assessment": "Đánh Giá SaaS",
        "Website Builder Assessment": "Đánh Giá Trình Tạo Website",
        "Exchange Assessment": "Đánh Giá Sàn Giao Dịch",
        "Combine these tools for comprehensive protection:": "Kết hợp các công cụ này để bảo vệ toàn diện:",
        "Proof of Reserves": "Bằng Chứng Dự Trữ",
        # Title / H1
        "Independent Trust & Security Analysis": "Phân tích tin cậy và bảo mật độc lập",
        "Independent Trust &amp; Security Analysis": "Phân tích tin cậy và bảo mật độc lập",
        # Verdicts
        "Yes, {name} is safe to use.": "Có, {name} an toàn để sử dụng.",
        "Use {name} with some caution.": "Sử dụng {name} một cách thận trọng.",
        "Exercise caution with {name}.": "Hãy thận trọng với {name}.",
        "{name} has significant trust concerns.": "{name} có vấn đề tin cậy đáng kể.",
        "Passes Nerq Verified threshold": "Đạt ngưỡng xác minh Nerq",
        "Below Nerq Verified threshold": "Dưới ngưỡng xác minh Nerq",
        "Significant trust gaps detected": "Phát hiện khoảng cách tin cậy đáng kể",
        # Section headings
        "Trust Score Breakdown": "Chi tiết điểm tin cậy",
        "Safety Score Breakdown": "Chi tiết điểm bảo mật",
        "Key Findings": "Phát hiện chính",
        "Key Safety Findings": "Phát hiện bảo mật chính",
        "Detailed Score Analysis": "Phân tích điểm chi tiết",
        "Frequently Asked Questions": "Câu hỏi thường gặp",
        "Safer Alternatives": "Lựa chọn an toàn hơn",
        "Popular Alternatives": "Lựa chọn phổ biến",
        "Community Reviews": "Đánh giá cộng đồng",
        "Regulatory Compliance": "Tuân thủ quy định",
        "How we calculated this score": "Cách chúng tôi tính điểm này",
        "What We Know About": "Những gì chúng tôi biết về",
        # Safety Guide
        "Safety Guide:": "Hướng dẫn bảo mật:",
        "What is": "là gì",
        "How to Verify Safety": "Cách xác minh an toàn",
        "Key Safety Concerns for": "Vấn đề bảo mật chính cho",
        "Trust Assessment": "Đánh giá tin cậy",
        "Key Takeaways": "Điểm chính",
        "Recommended for use — passes trust threshold.": "Khuyến nghị sử dụng — đạt ngưỡng tin cậy.",
        "Review carefully before use — below trust threshold.": "Xem xét kỹ trước khi dùng — dưới ngưỡng tin cậy.",
        "Always verify independently using the": "Luôn xác minh độc lập bằng",
        "When evaluating any": "Khi đánh giá bất kỳ",
        "watch for:": "cần chú ý:",
        # Cross-product
        "Across Platforms": "Trên các nền tảng khác",
        "across platforms": "trên các nền tảng khác",
        "Same developer/company in other registries:": "Cùng nhà phát triển/công ty trong các registry khác:",
        # King sections
        "What data does": "thu thập dữ liệu gì",
        "collect?": "không?",
        "Is": "Có",
        "secure?": "an toàn không?",
        "Full analysis:": "Phân tích đầy đủ:",
        "Privacy Report": "Báo cáo quyền riêng tư",
        "Privacy review": "Đánh giá quyền riêng tư",
        "Security Report": "Báo cáo bảo mật",
        # Dimensions
        "Security": "Bảo mật",
        "Privacy": "Quyền riêng tư",
        "Reliability": "Độ tin cậy",
        "Transparency": "Minh bạch",
        "Maintenance": "Bảo trì",
        "Overall Trust": "Tin cậy tổng thể",
        "Composite trust score": "Điểm tin cậy tổng hợp",
        "across all available signals": "dựa trên tất cả tín hiệu có sẵn",
        # Methodology
        "Nerq analyzes over 7.5 million entities across 26 registries": "Nerq phân tích hơn 7,5 triệu thực thể trong 26 registry",
        "using the same methodology, enabling direct cross-entity comparison": "bằng cùng một phương pháp, cho phép so sánh trực tiếp giữa các thực thể",
        "Scores are updated continuously as new data becomes available": "Điểm được cập nhật liên tục khi có dữ liệu mới",
        "This page was last reviewed on": "Trang này được xem xét lần cuối vào",
        "Data version": "Phiên bản dữ liệu",
        "Full methodology documentation": "Tài liệu phương pháp đầy đủ",
        "Machine-readable data (JSON API)": "Dữ liệu máy đọc được (JSON API)",
        "Machine-readable data (JSON)": "Dữ liệu máy đọc được (JSON)",
        # Meta / small text
        "Last analyzed:": "Phân tích gần nhất:",
        "Last updated": "Cập nhật lần cuối",
        "Updated daily": "Cập nhật hàng ngày",
        "Independent. Data-driven.": "Độc lập. Dựa trên dữ liệu.",
        "verified": "đã xác minh",
        "Data sourced from": "Dữ liệu từ",
        "Based on": "Dựa trên",
        "dimensions": "tiêu chí",
        "independent data dimensions": "tiêu chí dữ liệu độc lập",
        "strong": "mạnh",
        "moderate": "trung bình",
        "weak": "yếu",
        "actively maintained": "được bảo trì tích cực",
        "moderately maintained": "được bảo trì vừa phải",
        "low maintenance activity": "hoạt động bảo trì thấp",
        "well-documented": "tài liệu đầy đủ",
        "partial documentation": "tài liệu một phần",
        "limited documentation": "tài liệu hạn chế",
        "community adoption": "sự chấp nhận của cộng đồng",
        "stars on": "sao trên",
        # Cross-links
        "Safety": "Bảo mật",
        "Legit?": "Đáng tin?",
        "Scam?": "Lừa đảo?",
        "Review": "Đánh giá",
        "Alternatives": "Lựa chọn thay thế",
        "Compare": "So sánh",
        "Best in Category": "Tốt nhất trong danh mục",
        "Who Owns?": "Ai sở hữu?",
        "What Is?": "Là gì?",
        "Sells Data?": "Bán dữ liệu?",
        "Hacked?": "Bị tấn công?",
        "Safe for Kids?": "An toàn cho trẻ?",
        "Pros &amp; Cons": "Ưu &amp; Nhược điểm",
        # FAQ answers
        "Nerq Verified — meets the 70+ trust threshold.": "Nerq đã xác minh — đạt ngưỡng tin cậy 70+.",
        "Below the Nerq Verified threshold of 70.": "Dưới ngưỡng xác minh Nerq 70.",
        "Has not yet reached the Nerq Verified threshold of 70.": "Chưa đạt ngưỡng xác minh Nerq 70.",
        "Strongest signal:": "Tín hiệu mạnh nhất:",
        "Score based on": "Điểm dựa trên",
        "security": "bảo mật",
        "maintenance": "bảo trì",
        "popularity": "độ phổ biến",
        "documentation": "tài liệu",
        "compliance": "tuân thủ",
        # Verdict box
        "Safe": "An toàn",
        "Use Caution": "Thận trọng",
        "Avoid": "Tránh",
        # Long text patterns
        "is a Node.js package": "là một gói Node.js",
        "is a Python package": "là một gói Python",
        "is a Rust crate": "là một thư viện Rust",
        "is a Chrome extension": "là một tiện ích mở rộng Chrome",
        "is a Firefox extension": "là một tiện ích mở rộng Firefox",
        "is a VS Code extension": "là một tiện ích mở rộng VS Code",
        "is a WordPress plugin": "là một plugin WordPress",
        "is a iOS app": "là một ứng dụng iOS",
        "is a Android app": "là một ứng dụng Android",
        "is a VPN service": "là một dịch vụ VPN",
        "is a game": "là một trò chơi",
        "is a website": "là một trang web",
        "is a SaaS platform": "là một nền tảng SaaS",
        "is a dietary supplement": "là một thực phẩm bổ sung",
        "is a cosmetic ingredient": "là một thành phần mỹ phẩm",
        "is a food": "là một thực phẩm",
        "is a travel destination": "là một điểm đến du lịch",
        "is a nonprofit organization": "là một tổ chức phi lợi nhuận",
        "with a Nerq Trust Score of": "với Điểm tin cậy Nerq là",
        "with a Nerq Safety Score of": "với Điểm bảo mật Nerq là",
        "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "Đạt ngưỡng tin cậy Nerq với tín hiệu mạnh về bảo mật, bảo trì và sự chấp nhận của cộng đồng",
        "It has moderate trust signals but shows some areas of concern": "Có tín hiệu tin cậy vừa phải nhưng có một số vấn đề cần chú ý",
        "It has below-average trust signals with significant gaps": "Có tín hiệu tin cậy dưới trung bình với khoảng cách đáng kể",
        "review the full report below for specific considerations": "xem báo cáo đầy đủ bên dưới để biết chi tiết",
        "This score is based on automated analysis of security, maintenance, community, and quality signals.": "Điểm này dựa trên phân tích tự động các tín hiệu bảo mật, bảo trì, cộng đồng và chất lượng.",
        "You can also check the trust score via API:": "Bạn cũng có thể kiểm tra điểm tin cậy qua API:",
        "As a development package": "Là một gói phát triển",
        "does not directly collect end-user personal data": "không trực tiếp thu thập dữ liệu cá nhân của người dùng cuối",
        "However, applications built with it may collect data depending on implementation": "Tuy nhiên, các ứng dụng được xây dựng với nó có thể thu thập dữ liệu tùy theo cách triển khai",
        "Review the package's dependencies for potential supply chain risks": "Xem xét các phụ thuộc của gói để phát hiện rủi ro chuỗi cung ứng",
        "License information not available": "Thông tin giấy phép không có sẵn",
        "Open-source packages allow independent security review of the source code": "Các gói mã nguồn mở cho phép xem xét bảo mật độc lập mã nguồn",
        "to check for vulnerabilities": "để kiểm tra lỗ hổng bảo mật",
        "Review the": "Xem xét",
        "GitHub repository for recent commits": "kho GitHub để xem các commit gần đây",
        "dependency vulnerabilities, malicious packages, typosquatting": "lỗ hổng phụ thuộc, gói độc hại, typosquatting",
        "Run your package manager's audit command": "Chạy lệnh kiểm tra của trình quản lý gói",
        "to check for known vulnerabilities in your dependency tree": "để kiểm tra các lỗ hổng đã biết trong cây phụ thuộc",
        "This meets the recommended security threshold for production use": "Đáp ứng ngưỡng bảo mật khuyến nghị cho môi trường sản xuất",
        "Nerq monitors this entity against NVD, OSV.dev, and registry-specific vulnerability databases": "Nerq giám sát thực thể này so với NVD, OSV.dev và cơ sở dữ liệu lỗ hổng của từng registry",
        "for ongoing security assessment": "để đánh giá bảo mật liên tục",
        "Yes, it is safe to use.": "Có, an toàn để sử dụng.",
        "Use with some caution.": "Sử dụng với một chút thận trọng.",
        "Exercise caution.": "Hãy thận trọng.",
        "Significant trust concerns.": "Có vấn đề tin cậy đáng kể.",
        "maintained by": "được duy trì bởi",
        "is computed from": "được tính từ",
        "The score reflects": "Điểm phản ánh",
        "independent dimensions": "tiêu chí độc lập",
        "Each dimension is weighted equally to produce the composite trust score": "Mỗi tiêu chí được tính trọng số bằng nhau để tạo ra điểm tin cậy tổng hợp",
        "No reviews yet.": "Chưa có đánh giá nào.",
        "Be the first to review": "Hãy là người đầu tiên đánh giá",
        "Write a review": "Viết đánh giá",
        "Higher-rated": "Được đánh giá cao hơn",
        "you may want to consider:": "bạn có thể cân nhắc:",
        "under assessment": "đang được đánh giá",
        # Health disclaimers
        "Important Notice:": "Lưu ý quan trọng:",
        "educational and informational purposes only": "chỉ dành cho mục đích giáo dục và thông tin",
        "does not constitute medical advice": "không phải lời khuyên y tế",
        "Consult a qualified healthcare professional": "Hãy tham khảo ý kiến chuyên gia y tế có trình độ",
        "Full health disclaimer": "Tuyên bố từ chối trách nhiệm sức khỏe đầy đủ",
        "Full disclaimer": "Tuyên bố từ chối trách nhiệm đầy đủ",
    },
    "ar": {
        "full safety report for": "تقرير الأمان الكامل لتحليل الخصوصية التفصيلي",
        "Scores update as new data": "يتم تحديث النتائج عند توفر بيانات جديدة",
        "has undergone third-party": "خضع لعمليات تدقيق أمني من طرف ثالث",
        "It is ": "إنه ",
        "It is recommended for production use.": "موصى به للاستخدام في الإنتاج.",
        "Yes, it is safe to use.": "نعم، إنه آمن للاستخدام.",
        "it is safe to use": "إنه آمن للاستخدام",
        "It is below the recommended threshold of 70.": "إنه أقل من العتبة الموصى بها البالغة 70.",
        "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "يستوفي عتبة ثقة Nerq مع إشارات قوية عبر الأمان والصيانة واعتماد المجتمع",
        "It has moderate trust signals but shows some areas of concern that warrant attention": "لديه إشارات ثقة متوسطة لكنه يظهر بعض المجالات المثيرة للقلق التي تستحق الاهتمام",
        "It has below-average trust signals with significant gaps in security, maintenance, or documentation": "لديه إشارات ثقة أقل من المتوسط مع فجوات كبيرة في الأمان أو الصيانة أو التوثيق",
        "The #1 safest": "الأكثر أمانًا رقم 1",
        "How are safest": "كيف يتم تصنيف الأكثر أمانًا",
        "Are these safest": "هل هذه الأكثر أمانًا",
        "What does a Nerq Trust Score": "ماذا يعني Nerq Trust Score",
        "The #1": "رقم 1",
        "According to Nerq": "وفقًا لـ Nerq",
        "How are": "كيف يتم",
        "ranked by Nerq Trust Score": "مصنفة حسب Nerq Trust Score",
        "What are the best": "ما هي أفضل",
        "Are these rankings updated regularly": "هل يتم تحديث هذه التصنيفات بانتظام",
        "What does a Nerq Trust Score measure": "ماذا يقيس Nerq Trust Score",
        "How does Nerq evaluate": "كيف يقيّم Nerq",
        "Are these safe to use": "هل هذه آمنة للاستخدام",
        "{name} Privacy Report": "تقرير خصوصية {name}",
        "Security score": "درجة الأمان",
        "Based in": "مقرها في",
        "Independently audited": "تم التدقيق بشكل مستقل",
        "strong": "قوي",
        "moderate": "متوسط",
        "weak": "ضعيف",
        "logging policy": "سياسة التسجيل",
        "Server infrastructure": "البنية التحتية للخوادم",
        "most VPN providers have not been independently audited": "لم يخضع معظم مزودي VPN لتدقيق مستقل",
        "Nerq analyzes over": "يحلل Nerq أكثر من",
        "Scores are updated continuously as new data becomes available": "يتم تحديث النتائج باستمرار عند توفر بيانات جديدة",
        "community adoption": "اعتماد المجتمع",
        "This is a strong positive signal": "هذه إشارة إيجابية قوية",
        "No known data breaches associated with this service": "لا توجد انتهاكات بيانات معروفة مرتبطة بهذه الخدمة",
        "According to independent audit reports": "وفقًا لتقارير التدقيق المستقلة",
        "Key Safety Concerns for": "مخاوف الأمان الرئيسية لـ",
        "You can also check the trust score via API": "يمكنك أيضًا التحقق من درجة الثقة عبر API",
        "Trust Assessment": "تقييم الثقة",
        "meets Nerq trust threshold": "يستوفي عتبة ثقة Nerq",
        "passes trust threshold": "يجتاز عتبة الثقة",
        "Recommended for use": "موصى به للاستخدام",
        "is computed from": "يُحسب من",
        "strong)": "قوي)",
        "widely used": "واسع الاستخدام",
        "Full analysis": "تحليل كامل",
        "It is recommended": "موصى به",
        "Dimension": "البُعد",
        "Score": "النتيجة",
        "dimensions": "أبعاد",
        "Data from": "البيانات من",
        "is based in": "يقع مقرها في",
        "outside all Eyes surveillance alliances": "خارج جميع تحالفات Eyes للمراقبة",
        "a privacy advantage": "ميزة للخصوصية",
        "Serving": "يخدم",
        "users": "مستخدم",
        "Related Safety Rankings": "تصنيفات الأمان ذات الصلة",
        "countries": "دولة",
        "Browse Categories": "تصفح الفئات",
        "Recently Analyzed": "تم تحليلها مؤخراً",
        "Security": "الأمان",
        "Popularity": "الشعبية",
        "Maintenance": "الصيانة",
        "Community": "المجتمع",
        "Transparency": "الشفافية",
        "Trust Grade": "تقييم الثقة",
        "verified": "موثق",
        "recommended": "موصى به",
        "How to": "كيفية",
        "View all": "عرض الكل",
        "See all": "عرض الكل",
        "Read more": "اقرأ المزيد",
        "Learn more": "تعرف على المزيد",
        "Developer": "المطور",
        "Publisher": "الناشر",
        "Age rating": "تصنيف العمر",
        "Permissions": "الأذونات",
        "Downloads": "التنزيلات",
        "Version": "الإصدار",
        "Updated": "محدّث",
        "Released": "صدر",
        "Reliability": "الموثوقية",
        "Performance": "الأداء",
        "Value": "القيمة",
        "Support": "الدعم",
        "Features": "الميزات",
        "Pricing": "التسعير",
        "Free tier": "الطبقة المجانية",
        "Open source": "مفتوح المصدر",
        "Proprietary": "مملوك",
        "Founded in": "تأسست في",
        "Headquartered in": "مقرها في",
        "employees": "موظفين",
        "customers": "عملاء",
        "Check back soon": "تحقق مرة أخرى قريبًا",
        "No data available": "لا تتوفر بيانات",
        "monthly visitors": "زائر شهري",
        "This score reflects": "تعكس هذه النتيجة",
        "across multiple registries": "عبر سجلات متعددة",
        "Last updated": "آخر تحديث",
        "Yes, {name} is safe to use.": "نعم، {name} آمن للاستخدام.",
        "Use {name} with some caution.": "استخدم {name} بحذر.",
        "Exercise caution with {name}.": "توخَّ الحذر مع {name}.",
        "{name} has significant trust concerns.": "{name} لديه مخاوف كبيرة تتعلق بالثقة.",
        "Passes Nerq Verified threshold": "يجتاز عتبة التحقق من Nerq",
        "Below Nerq Verified threshold": "أقل من عتبة التحقق من Nerq",
        "Significant trust gaps detected": "تم اكتشاف فجوات ثقة كبيرة",
        "What is {name}?": "ما هو {name}؟",
        "More Private Alternatives": "بدائل أكثر خصوصية",
        "License": "الترخيص",
        "Last analyzed:": "آخر تحليل:",
        "How to Verify Safety": "كيفية التحقق من الأمان",
        "Key Takeaways": "النقاط الرئيسية",
        "Based on": "بناءً على",
        "independent data dimensions": "أبعاد بيانات مستقلة",
        "Recommended for privacy-conscious use": "موصى به للاستخدام المراعي للخصوصية",
        "Below the Nerq Verified threshold of 70.": "أقل من عتبة التحقق من Nerq البالغة 70.",
        "Has not yet reached the Nerq Verified threshold of 70.": "لم يصل بعد إلى عتبة التحقق من Nerq البالغة 70.",
        "Composite trust score": "درجة الثقة المركبة",
        "Each dimension is weighted equally to produce the composite trust score.": "يتم ترجيح كل بُعد بالتساوي لإنتاج درجة الثقة المركبة.",
        "weekly downloads": "تنزيلات أسبوعية",
        "active installations": "عمليات تثبيت نشطة",
        "known vulnerabilities": "ثغرات أمنية معروفة",
        "Review": "مراجعة",
        "updated": "محدّث",
        "based on": "بناءً على",
        "recommended for": "موصى به لـ",
        "Below recommended threshold": "أقل من العتبة الموصى بها",
        "Use with caution": "استخدم بحذر",
        "Not recommended": "غير مستحسن",
        "Be the first to review": "كن أول من يقيّم",
        "Data version": "إصدار البيانات",
        "As a development package": "كحزمة تطوير",
        "Always verify independently using the": "تحقق دائمًا بشكل مستقل باستخدام",
        "Not Yet Analyzed": "لم يتم التحليل بعد",
        "jurisdiction databases, independent audit reports, protocol analysis, and incident history": "قواعد بيانات الاختصاص القضائي وتقارير التدقيق المستقل وتحليل البروتوكول وسجل الحوادث",
        "Panama jurisdiction": "الاختصاص القضائي لبنما",
        "outside the Five Eyes, Nine Eyes, and Fourteen Eyes surveillance alliances": "خارج تحالفات المراقبة العيون الخمس والتسع والأربع عشرة",
        "jurisdiction": "ولاية قضائية",
        "Five Eyes": "العيون الخمس",
        "Independent": "مستقل",
        "Audited no-log": "تم تدقيق عدم التسجيل",
        "Claimed no-log": "مُدعى عدم التسجيل",
        "Check jurisdiction": "تحقق من الاختصاص",
        "Verify independent audit exists": "تحقق من وجود تدقيق مستقل",
        "Review logging policy": "مراجعة سياسة التسجيل",
        "Antivirus": "مضاد الفيروسات",
        # ── Vertical-specific strings (auto-generated) ──
        "Privacy Assessment": "تقييم الخصوصية",
        "Breach History": "سجل الاختراقات",
        "Encryption": "التشفير",
        "Zero-Knowledge Architecture": "بنية المعرفة الصفرية",
        "Open Source": "مفتوح المصدر",
        "Jurisdiction": "الاختصاص القضائي",
        "Infrastructure": "البنية التحتية",
        "Security & Compliance": "الأمان والامتثال",
        "Data Location": "موقع البيانات",
        "Security Incidents": "الحوادث الأمنية",
        "Independent Lab Results": "نتائج المختبر المستقل",
        "Security Track Record": "سجل الأمان",
        "Build Your Security Stack": "بناء حزمة الأمان الخاصة بك",
        "Best VPNs": "أفضل VPN",
        "Best Password Managers": "أفضل مديري كلمات المرور",
        "Best Antivirus": "أفضل مضاد فيروسات",
        "Security Assessment": "تقييم الأمان",
        "Ecommerce": "التجارة الإلكترونية",
        "Hosting Assessment": "تقييم الاستضافة",
        "Antivirus Assessment": "تقييم مضاد الفيروسات",
        "SaaS Assessment": "تقييم SaaS",
        "Website Builder Assessment": "تقييم منشئ المواقع",
        "Exchange Assessment": "تقييم البورصة",
        "Compare": "مقارنة",
        "Combine these tools for comprehensive protection:": "اجمع هذه الأدوات للحماية الشاملة:",
        "Proof of Reserves": "إثبات الاحتياطيات",
        "Independent Trust & Security Analysis": "تحليل مستقل للثقة والأمان",
        "Independent Trust &amp; Security Analysis": "تحليل مستقل للثقة والأمان",
        "Trust Score Breakdown": "تفاصيل درجة الثقة",
        "Safety Score Breakdown": "تفاصيل درجة السلامة",
        "Key Findings": "النتائج الرئيسية",
        "Key Safety Findings": "نتائج السلامة الرئيسية",
        "Details": "التفاصيل",
        "Detailed Score Analysis": "تحليل مفصل للدرجة",
        "Frequently Asked Questions": "الأسئلة الشائعة",
        "Community Reviews": "مراجعات المجتمع",
        "Regulatory Compliance": "الامتثال التنظيمي",
        "Popular Alternatives": "بدائل شائعة",
        "Safer Alternatives": "بدائل أكثر أمانًا",
        "Safety Guide": "دليل السلامة",
        "Best in Category": "الأفضل في الفئة",
        "How we calculated this score": "كيف حسبنا هذه الدرجة",
        "Safe": "آمن",
        "Use Caution": "استخدم بحذر",
        "Avoid": "تجنب",
        "Security Analysis": "تحليل الأمان",
        "Privacy Report": "تقرير الخصوصية",
        "Safety Guide:": "دليل الأمان:",
        "Alternatives": "البدائل",
        "What is": "ما هو",
        "Trust Score": "درجة الثقة",
        "has a Nerq Trust Score of": "لديه درجة ثقة Nerq تبلغ",
        "is a": "هو",
        "with a Nerq Trust Score of": "بدرجة ثقة Nerq تبلغ",
        "Author": "المؤلف",
        "Category": "الفئة",
        "Source": "المصدر",
        "Stars": "النجوم",
        "Last analyzed": "آخر تحليل",
        "Data sourced from": "البيانات من",
        "Machine-readable": "قراءة آلية",
        "Across Platforms": "عبر المنصات",
        "explore more": "استكشف المزيد",
        "Discover more": "اكتشف المزيد",
        "Disclaimer": "إخلاء المسؤولية",
        "All rights reserved": "جميع الحقوق محفوظة",
        "About": "حول",
        "Privacy": "الخصوصية",
        "Terms": "الشروط",
        "Blog": "المدونة",
        "API": "واجهة برمجة التطبيقات",
        "Discover": "اكتشف",
        "Search": "بحث",
        "Home": "الرئيسية",
        "Nerq trust scores are automated assessments based on publicly available signals. They are not endorsements or guarantees. Always conduct your own due diligence.": "درجات ثقة Nerq هي تقييمات آلية مبنية على إشارات متاحة للعموم. وهي ليست توصيات أو ضمانات. قم دائمًا بإجراء العناية الواجبة الخاصة بك.",
        "educational and informational purposes only": "لأغراض تعليمية ومعلوماتية فقط",
        "does not constitute medical advice": "لا يشكل نصيحة طبية",
        "Consult a qualified healthcare professional": "استشر أخصائي رعاية صحية مؤهل",
        "Full health disclaimer": "إخلاء المسؤولية الصحية الكامل",
        "Full disclaimer": "إخلاء المسؤولية الكامل",
    },
}


def _translate_html(html, lang, entity_slug=""):
    """Translate all visible English text in rendered HTML to target language."""
    import re as _re_links

    # ── STRUCTURAL: Rewrite internal links to localized versions ──
    # /safe/X → /es/safe/X, /compare → /es/compare, etc.
    # Exclude: /v1/, /static/, /, /#, external URLs
    _skip_prefixes = ('/v1/', '/static/', '/openapi', '/sitemap', '/robots', '/llms', '/feed/', '/badge/', '/mcp/')
    # URL patterns that should NOT be localized (English-only SEO routes)
    _no_localize_patterns = ('/is-', '/does-', '/was-', '/how-to-', '/how-does-', '/where-is-', '/should-i-', '/free-alternative-', '/private-alternative-')
    def _rewrite_link(m):
        path = m.group(1)
        if path == '/' or path.startswith('/#'):
            return m.group(0)
        if any(path.startswith(p) for p in _skip_prefixes):
            return m.group(0)
        if path.startswith(f'/{lang}/'):
            return m.group(0)  # Already localized
        if any(path.startswith(p) for p in _no_localize_patterns):
            return m.group(0)  # English-only SEO URL patterns — do not prefix
        return f'href="/{lang}{path}"'
    html = _re_links.sub(r'href="(/[^"]*)"', _rewrite_link, html)

    # ── RTL: Add dir="rtl" for Arabic ──
    if lang == "ar":
        html = html.replace('<html lang="en">', f'<html lang="ar" dir="rtl">')
        html = html.replace(f'<html lang="{lang}">', f'<html lang="ar" dir="rtl">')
        # Fix inline border-left → border-right for RTL pplx-verdict
        html = html.replace('border-left:4px solid #16a34a', 'border-right:4px solid #16a34a')

    # ── STRUCTURAL: Fix canonical to point to localized version ──
    # Skip if already has lang prefix (native i18n templates set it directly)
    html = _re_links.sub(
        r'<link rel="canonical" href="https://nerq\.ai(/[^"]*)"',
        lambda m: m.group(0) if m.group(1).startswith(f'/{lang}/') else f'<link rel="canonical" href="https://nerq.ai/{lang}{m.group(1)}"',
        html, count=1
    )

    # ── STRUCTURAL: Fix og:url to localized version ──
    html = _re_links.sub(
        r'og:url" content="https://nerq\.ai(/[^"]*)"',
        lambda m: m.group(0) if m.group(1).startswith(f'/{lang}/') else f'og:url" content="https://nerq.ai/{lang}{m.group(1)}"',
        html, count=1
    )

    # ── Language-agnostic structural fixes (JSON-LD, common patterns) ──
    # NOTE: Regex patterns MUST run BEFORE content translations,
    # because content translations replace individual words (e.g. "Is" → "Ist")
    # which breaks regex patterns that match full phrases like "Is X Safe?".
    import re as _re_t

    # Regex patterns keyed by language — applied for ALL translated languages
    _REGEX_PATTERNS = {
        "es": [
            (r'<title>Is (.+?) Safe\?', r'<title>¿Es \1 Seguro?'),
            (r'>Is (.+?) Safe\?<', r'>¿Es \1 Seguro?<'),
            (r'>Is (.+?) safe\?<', r'>¿Es \1 seguro?<'),
            (r'>Is (.+?) Safe to Visit\?', r'>¿Es \1 Seguro para Visitar?'),
            (r'>What data does (.+?) collect\?<', r'>¿Qué datos recopila \1?<'),
            (r'>Is (.+?) secure\?<', r'>¿Es \1 seguro?<'),
            (r'>(.+?) Across Platforms<', r'>\1 en Otras Plataformas<'),
            (r'>(.+?) across platforms<', r'>\1 en otras plataformas<'),
            (r'>Safety Guide: (.+?)<', r'>Guía de Seguridad: \1<'),
            (r'>What is (.+?)\?<', r'>¿Qué es \1?<'),
            (r'>Key Safety Concerns for (.+?)<', r'>Principales Preocupaciones para \1<'),
            (r'>Is (.+?) safe for solo travelers\?<', r'>¿Es \1 seguro para viajeros solos?<'),
            (r'>Is (.+?) safe for women\?<', r'>¿Es \1 seguro para mujeres?<'),
            (r'>Is (.+?) safe for LGBTQ\+ travelers\?<', r'>¿Es \1 seguro para viajeros LGBTQ+?<'),
            (r'>Is (.+?) safe for families\?<', r'>¿Es \1 seguro para familias?<'),
            (r'>Is (.+?) safe to visit right now\?<', r'>¿Es \1 seguro para visitar ahora?<'),
            (r'>Is (.+?) safe for solo female travelers\?<', r'>¿Es \1 seguro para mujeres viajeras solas?<'),
            (r'>Is tap water safe to drink in (.+?)\?<', r'>¿Es seguro beber agua del grifo en \1?<'),
            (r'>Do I need vaccinations for (.+?)\?<', r'>¿Necesito vacunas para \1?<'),
            (r'>What are safer alternatives to (.+?)\?<', r'>¿Cuáles son alternativas más seguras a \1?<'),
            (r'>What are the best alternatives to (.+?)\?<', r'>¿Cuáles son las mejores alternativas a \1?<'),
            (r'>How actively maintained is (.+?)\?<', r'>¿Qué tan activamente se mantiene \1?<'),
            (r'>How does (.+?) compare to similar', r'>¿Cómo se compara \1 con'),
            (r'>Can (.+?) cause skin irritation\?<', r'>¿Puede \1 causar irritación cutánea?<'),
            (r'>Does (.+?) interact with medications\?<', r'>¿Interactúa \1 con medicamentos?<'),
            (r'>What are the safety concerns for (.+?)\?<', r'>¿Cuáles son las preocupaciones de seguridad para \1?<'),
            (r'>What are the side effects of (.+?)\?<', r'>¿Cuáles son los efectos secundarios de \1?<'),
            (r"(.+?)'s trust score of", r'La puntuación de confianza de \1 de'),
            (r"(.+?)'s safety score of", r'La puntuación de seguridad de \1 de'),
            (r'>(.+?) is a Android app — ', r'>\1 es una app de Android — '),
            (r'>(.+?) is a iOS app — ', r'>\1 es una app de iOS — '),
            (r'>(.+?) is a (.+?) maintained by (.+?)\.', r'>\1 es un \2 mantenido por \3.'),
            (r'Nerq of (\d)', r'Nerq de \1'),
            (r'"name": "Is (.+?) Safe\?', r'"name": "¿Es \1 Seguro?'),
            (r'"name": "Is (.+?) Safe to Visit\?', r'"name": "¿Es \1 Seguro para Visitar?'),
            (r'"name": "Is (.+?) Trustworthy\?', r'"name": "¿Es \1 Confiable?'),
            (r'"description": "(.+?) is a travel destination with a Nerq', r'"description": "\1 es un destino de viaje con una'),
            (r'"description": "(.+?) is a nonprofit organization with a Nerq', r'"description": "\1 es una organización sin fines de lucro con una'),
            (r'og:title" content="Is (.+?) Safe\?', r'og:title" content="¿Es \1 Seguro?'),
            (r'og:description" content="(.+?) — (\w[\w+-]*) trust grade', r'og:description" content="\1 — Calificación \2 de confianza'),
            (r'nerq:question" content="Is (.+?) safe', r'nerq:question" content="¿Es \1 seguro'),
            (r'In the (\w+) category, more (.+?) are being analyzed', r'En la categoría \1, se están analizando más \2'),
            (r'Nerq checks (.+?) against NVD', r'Nerq verifica \1 contra NVD'),
        ],
        "de": [
            (r'<title>Is (.+?) Safe\?', r'<title>Ist \1 sicher?'),
            (r'>Is (.+?) Safe\?<', r'>Ist \1 sicher?<'),
            (r'>Is (.+?) safe\?<', r'>Ist \1 sicher?<'),
            (r'>Is (.+?) Safe to Visit\?', r'>Ist \1 sicher zu besuchen?'),
            (r'>What data does (.+?) collect\?<', r'>Welche Daten erhebt \1?<'),
            (r'>Is (.+?) secure\?<', r'>Ist \1 sicher?<'),
            (r'>(.+?) Across Platforms<', r'>\1 auf anderen Plattformen<'),
            (r'>(.+?) across platforms<', r'>\1 auf anderen Plattformen<'),
            (r'>Safety Guide: (.+?)<', r'>Sicherheitsleitfaden: \1<'),
            (r'>What is (.+?)\?<', r'>Was ist \1?<'),
            (r'>Key Safety Concerns for (.+?)<', r'>Wichtige Sicherheitsbedenken für \1<'),
            (r'>Is (.+?) safe for solo travelers\?<', r'>Ist \1 sicher für Alleinreisende?<'),
            (r'>Is (.+?) safe for women\?<', r'>Ist \1 sicher für Frauen?<'),
            (r'>Is (.+?) safe for LGBTQ\+ travelers\?<', r'>Ist \1 sicher für LGBTQ+-Reisende?<'),
            (r'>Is (.+?) safe for families\?<', r'>Ist \1 sicher für Familien?<'),
            (r'>Is (.+?) safe to visit right now\?<', r'>Ist \1 jetzt sicher zu besuchen?<'),
            (r'>Is tap water safe to drink in (.+?)\?<', r'>Ist Leitungswasser in \1 sicher?<'),
            (r'>Do I need vaccinations for (.+?)\?<', r'>Brauche ich Impfungen für \1?<'),
            (r'>What are safer alternatives to (.+?)\?<', r'>Was sind sicherere Alternativen zu \1?<'),
            (r'>How actively maintained is (.+?)\?<', r'>Wie aktiv wird \1 gepflegt?<'),
            (r'>How does (.+?) compare to similar', r'>Wie schneidet \1 im Vergleich zu ähnlichen'),
            (r'>What are the safety concerns for (.+?)\?<', r'>Was sind die Sicherheitsbedenken bei \1?<'),
            (r'>What are the side effects of (.+?)\?<', r'>Was sind die Nebenwirkungen von \1?<'),
            (r'>Does (.+?) interact with medications\?<', r'>Interagiert \1 mit Medikamenten?<'),
            (r"(.+?)'s trust score of", r'Die Vertrauensbewertung von \1 von'),
            (r"(.+?)'s safety score of", r'Die Sicherheitsbewertung von \1 von'),
            (r'>(.+?) is a Android app — ', r'>\1 ist eine Android-App — '),
            (r'>(.+?) is a iOS app — ', r'>\1 ist eine iOS-App — '),
            (r'>(.+?) is a (.+?) maintained by (.+?)\.', r'>\1 ist ein \2, gepflegt von \3.'),
            (r'Nerq of (\d)', r'Nerq von \1'),
            (r'"name": "Is (.+?) Safe\?', r'"name": "Ist \1 sicher?'),
            (r'"name": "Is (.+?) Safe to Visit\?', r'"name": "Ist \1 sicher zu besuchen?'),
            (r'"name": "Is (.+?) Trustworthy\?', r'"name": "Ist \1 vertrauenswürdig?'),
            (r'"description": "(.+?) is a travel destination', r'"description": "\1 ist ein Reiseziel'),
            (r'og:title" content="Is (.+?) Safe\?', r'og:title" content="Ist \1 sicher?'),
            (r'nerq:question" content="Is (.+?) safe', r'nerq:question" content="Ist \1 sicher'),
            (r'Nerq checks (.+?) against NVD', r'Nerq überprüft \1 gegen NVD'),
        ],
        "fr": [
            (r'<title>Is (.+?) Safe\?', r'<title>\1 est-il sûr ?'),
            (r'>Is (.+?) Safe\?<', r'>\1 est-il sûr ?<'),
            (r'>Is (.+?) safe\?<', r'>\1 est-il sûr ?<'),
            (r'>Is (.+?) Safe to Visit\?', r'>\1 est-il sûr à visiter ?'),
            (r'>What data does (.+?) collect\?<', r'>Quelles données \1 collecte-t-il ?<'),
            (r'>Is (.+?) secure\?<', r'>\1 est-il sécurisé ?<'),
            (r'>(.+?) Across Platforms<', r">\1 sur d'autres plateformes<"),
            (r'>(.+?) across platforms<', r">\1 sur d'autres plateformes<"),
            (r'>Safety Guide: (.+?)<', r'>Guide de sécurité : \1<'),
            (r'>What is (.+?)\?<', r">Qu'est-ce que \1 ?<"),
            (r'>Key Safety Concerns for (.+?)<', r'>Préoccupations de sécurité pour \1<'),
            (r'>Is (.+?) safe for solo travelers\?<', r'>\1 est-il sûr pour les voyageurs seuls ?<'),
            (r'>Is (.+?) safe for women\?<', r'>\1 est-il sûr pour les femmes ?<'),
            (r'>Is (.+?) safe for families\?<', r'>\1 est-il sûr pour les familles ?<'),
            (r'>Is (.+?) safe to visit right now\?<', r'>\1 est-il sûr à visiter maintenant ?<'),
            (r'>What are safer alternatives to (.+?)\?<', r'>Quelles sont les alternatives plus sûres à \1 ?<'),
            (r'>How actively maintained is (.+?)\?<', r'>\1 est-il activement maintenu ?<'),
            (r'>How does (.+?) compare to similar', r'>Comment \1 se compare-t-il à des'),
            (r'>What are the side effects of (.+?)\?<', r'>Quels sont les effets secondaires de \1 ?<'),
            (r"(.+?)'s trust score of", r'Le score de confiance de \1 de'),
            (r"(.+?)'s safety score of", r'Le score de sécurité de \1 de'),
            (r'>(.+?) is a Android app — ', r">\1 est une application Android — "),
            (r'>(.+?) is a (.+?) maintained by (.+?)\.', r'>\1 est un \2, maintenu par \3.'),
            (r'Nerq of (\d)', r'Nerq de \1'),
            (r'"name": "Is (.+?) Safe\?', r'"name": "\1 est-il sûr ?'),
            (r'"name": "Is (.+?) Safe to Visit\?', r'"name": "\1 est-il sûr à visiter ?'),
            (r'og:title" content="Is (.+?) Safe\?', r'og:title" content="\1 est-il sûr ?'),
            (r'nerq:question" content="Is (.+?) safe', r'nerq:question" content="\1 est-il sûr'),
            (r'Nerq checks (.+?) against NVD', r'Nerq vérifie \1 contre NVD'),
        ],
        "ja": [
            (r'<title>Is (.+?) Safe\?', r'<title>\1は安全ですか？'),
            (r'>Is (.+?) Safe\?<', r'>\1は安全ですか？<'),
            (r'>Is (.+?) safe\?<', r'>\1は安全ですか？<'),
            (r'>Is (.+?) Safe to Visit\?', r'>\1は訪問しても安全ですか？'),
            (r'>What data does (.+?) collect\?<', r'>\1はどのようなデータを収集しますか？<'),
            (r'>Is (.+?) secure\?<', r'>\1は安全ですか？<'),
            (r'>(.+?) Across Platforms<', r'>\1の他プラットフォーム<'),
            (r'>Safety Guide: (.+?)<', r'>セキュリティガイド: \1<'),
            (r'>What is (.+?)\?<', r'>\1とは？<'),
            (r'>Is (.+?) safe for solo travelers\?<', r'>\1は一人旅に安全ですか？<'),
            (r'>Is (.+?) safe for women\?<', r'>\1は女性にとって安全ですか？<'),
            (r'>Is (.+?) safe for families\?<', r'>\1は家族連れに安全ですか？<'),
            (r'>What are safer alternatives to (.+?)\?<', r'>\1のより安全な代替品は？<'),
            (r'>How actively maintained is (.+?)\?<', r'>\1はどの程度メンテナンスされていますか？<'),
            (r'>What are the side effects of (.+?)\?<', r'>\1の副作用は？<'),
            (r"(.+?)'s trust score of", r'\1の信頼スコア'),
            (r"(.+?)'s safety score of", r'\1の安全スコア'),
            (r'>(.+?) is a Android app — ', r'>\1はAndroidアプリです — '),
            (r'Nerq of (\d)', r'Nerq の \1'),
            (r'"name": "Is (.+?) Safe\?', r'"name": "\1は安全ですか？'),
            (r'"name": "Is (.+?) Safe to Visit\?', r'"name": "\1は訪問しても安全ですか？'),
            (r'og:title" content="Is (.+?) Safe\?', r'og:title" content="\1は安全ですか？'),
            (r'nerq:question" content="Is (.+?) safe', r'nerq:question" content="\1は安全ですか'),
            (r'Nerq checks (.+?) against NVD', r'Nerqは\1をNVDに対してチェック'),
        ],
        "pt": [
            (r'<title>Is (.+?) Safe\?', r'<title>\1 é seguro?'),
            (r'>Is (.+?) Safe\?<', r'>\1 é seguro?<'),
            (r'>Is (.+?) safe\?<', r'>\1 é seguro?<'),
            (r'>Is (.+?) Safe to Visit\?', r'>\1 é seguro para visitar?'),
            (r'>What data does (.+?) collect\?<', r'>Quais dados \1 coleta?<'),
            (r'>Is (.+?) secure\?<', r'>\1 é seguro?<'),
            (r'>(.+?) Across Platforms<', r'>\1 em outras plataformas<'),
            (r'>(.+?) across platforms<', r'>\1 em outras plataformas<'),
            (r'>Safety Guide: (.+?)<', r'>Guia de Segurança: \1<'),
            (r'>What is (.+?)\?<', r'>O que é \1?<'),
            (r'>Key Safety Concerns for (.+?)<', r'>Preocupações de segurança para \1<'),
            (r'>Is (.+?) safe for solo travelers\?<', r'>\1 é seguro para viajantes solo?<'),
            (r'>Is (.+?) safe for women\?<', r'>\1 é seguro para mulheres?<'),
            (r'>Is (.+?) safe for families\?<', r'>\1 é seguro para famílias?<'),
            (r'>Is (.+?) safe to visit right now\?<', r'>\1 é seguro para visitar agora?<'),
            (r'>What are safer alternatives to (.+?)\?<', r'>Quais são alternativas mais seguras a \1?<'),
            (r'>How actively maintained is (.+?)\?<', r'>Quão ativamente \1 é mantido?<'),
            (r'>How does (.+?) compare to similar', r'>Como \1 se compara com'),
            (r'>What are the side effects of (.+?)\?<', r'>Quais são os efeitos colaterais de \1?<'),
            (r"(.+?)'s trust score of", r'A pontuação de confiança de \1 de'),
            (r"(.+?)'s safety score of", r'A pontuação de segurança de \1 de'),
            (r'>(.+?) is a Android app — ', r'>\1 é um app Android — '),
            (r'>(.+?) is a (.+?) maintained by (.+?)\.', r'>\1 é um \2, mantido por \3.'),
            (r'Nerq of (\d)', r'Nerq de \1'),
            (r'"name": "Is (.+?) Safe\?', r'"name": "\1 é seguro?'),
            (r'"name": "Is (.+?) Safe to Visit\?', r'"name": "\1 é seguro para visitar?'),
            (r'og:title" content="Is (.+?) Safe\?', r'og:title" content="\1 é seguro?'),
            (r'nerq:question" content="Is (.+?) safe', r'nerq:question" content="\1 é seguro'),
            (r'Nerq checks (.+?) against NVD', r'Nerq verifica \1 contra NVD'),
        ],
    }

    # Apply regex patterns for current language
    if lang in _REGEX_PATTERNS:
        for pattern, replacement in _REGEX_PATTERNS[lang]:
            html = _re_t.sub(pattern, replacement, html)

    # Common substring replacements (paragraph text) — language-agnostic using dict
    _COMMON_SUBSTRINGS = {
        "es": {
            "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "Cumple con el umbral de confianza de Nerq con señales sólidas en seguridad, mantenimiento y adopción comunitaria",
            "has not yet reached Nerq trust threshold (70+)": "aún no ha alcanzado el umbral de confianza de Nerq (70+)",
            "This score is based on automated analysis of security, maintenance, community, and quality signals.": "Esta puntuación se basa en un análisis automatizado de señales de seguridad, mantenimiento, comunidad y calidad.",
            "As a development package,": "Como paquete de desarrollo,",
            "does not directly collect end-user personal data": "no recopila directamente datos personales del usuario final",
            "License information not available. Open-source packages allow independent security review": "Información de licencia no disponible. Los paquetes de código abierto permiten una revisión de seguridad independiente",
            "using the same methodology, enabling direct cross-entity comparison": "utilizando la misma metodología, lo que permite la comparación directa entre entidades",
            "Scores are updated continuously as new data becomes available": "Las puntuaciones se actualizan continuamente a medida que nuevos datos están disponibles",
            "check back soon": "vuelva pronto",
            "Nerq trust scores are automated assessments based on publicly available signals. They are not endorsements or guarantees. Always conduct your own due diligence.": "Las puntuaciones de confianza de Nerq son evaluaciones automatizadas basadas en señales disponibles públicamente. No son respaldos ni garantías. Siempre realice su propia diligencia debida.",
            "Recommended for production use": "Recomendado para uso en producción",
        },
        "de": {
        # ── Vertical-specific strings (auto-generated) ──
        "Privacy Assessment": "Datenschutzbewertung",
        "Breach History": "Sicherheitsvorfälle",
        "Encryption": "Verschlüsselung",
        "Zero-Knowledge Architecture": "Zero-Knowledge-Architektur",
        "Open Source": "Open Source",
        "Jurisdiction": "Gerichtsbarkeit",
        "Infrastructure": "Infrastruktur",
        "Security & Compliance": "Sicherheit & Compliance",
        "Data Location": "Datenstandort",
        "Security Incidents": "Sicherheitsvorfälle",
        "Independent Lab Results": "Unabhängige Laborergebnisse",
        "Security Track Record": "Sicherheitsbilanz",
        "Build Your Security Stack": "Bauen Sie Ihr Sicherheitspaket",
        "Best VPNs": "Beste VPNs",
        "Best Password Managers": "Beste Passwort-Manager",
        "Best Antivirus": "Bestes Antivirus",
        "Security Assessment": "Sicherheitsbewertung",
        "Ecommerce": "E-Commerce",
        "Hosting Assessment": "Hosting-Bewertung",
        "Antivirus Assessment": "Antivirus-Bewertung",
        "SaaS Assessment": "SaaS-Bewertung",
        "Website Builder Assessment": "Website-Builder-Bewertung",
        "Exchange Assessment": "Börsen-Bewertung",
        "Compare": "Vergleichen",
        "Combine these tools for comprehensive protection:": "Kombinieren Sie diese Tools für umfassenden Schutz:",
        "Proof of Reserves": "Reservenachweis",
            "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "Es erfüllt die Vertrauensschwelle von Nerq mit starken Signalen in Sicherheit, Wartung und Community-Akzeptanz",
            "has not yet reached Nerq trust threshold (70+)": "hat die Nerq-Vertrauensschwelle (70+) noch nicht erreicht",
            "This score is based on automated analysis of security, maintenance, community, and quality signals.": "Diese Bewertung basiert auf automatisierter Analyse von Sicherheits-, Wartungs-, Community- und Qualitätssignalen.",
            "As a development package,": "Als Entwicklungspaket",
            "does not directly collect end-user personal data": "erhebt keine personenbezogenen Daten von Endnutzern direkt",
            "License information not available. Open-source packages allow independent security review of the source code.": "Lizenzinformationen nicht verfügbar. Open-Source-Pakete ermöglichen eine unabhängige Sicherheitsüberprüfung des Quellcodes.",
            "using the same methodology, enabling direct cross-entity comparison": "unter Verwendung derselben Methodik, die einen direkten Vergleich ermöglicht",
            "Scores are updated continuously as new data becomes available": "Bewertungen werden kontinuierlich aktualisiert, wenn neue Daten verfügbar sind",
            "check back soon": "schauen Sie bald wieder vorbei",
            "Nerq trust scores are automated assessments based on publicly available signals. They are not endorsements or guarantees. Always conduct your own due diligence.": "Nerq-Vertrauensbewertungen sind automatisierte Bewertungen basierend auf öffentlich verfügbaren Signalen. Sie sind keine Empfehlungen oder Garantien. Führen Sie immer Ihre eigene Sorgfaltsprüfung durch.",
            "Recommended for production use": "Empfohlen für den Produktionseinsatz",
            "Yes, Express is safe to use.": "Ja, Express ist sicher in der Verwendung.",
            "It is recommended for production use.": "Es wird für den Produktionseinsatz empfohlen.",
            "is a Node.js package": "ist ein Node.js-Paket",
            "with a Nerq Trust Score of": "mit einer Nerq-Vertrauensbewertung von",
            "to check for vulnerabilities. Review the package's GitHub repository for recent commits.": "um auf Schwachstellen zu prüfen. Überprüfen Sie das GitHub-Repository des Pakets auf aktuelle Commits.",
            "However, applications built with it may collect data depending on implementation": "Allerdings können mit ihm erstellte Anwendungen je nach Implementierung Daten erheben",
            "Review the package's dependencies for potential supply chain risks. Run your package manager's audit command regularly.": "Überprüfen Sie die Abhängigkeiten des Pakets auf mögliche Lieferkettenrisiken. Führen Sie regelmäßig den Audit-Befehl Ihres Paketmanagers aus.",
            "Data from npm registry, GitHub repository, NVD, OSV.dev, and OpenSSF Scorecard.": "Daten aus npm-Registry, GitHub-Repository, NVD, OSV.dev und OpenSSF Scorecard.",
            "is computed from": "wird berechnet aus",
            "The score reflects": "Die Bewertung spiegelt",
            "independent dimensions": "unabhängige Dimensionen",
            "Meets Nerq Verified threshold.": "Erfüllt die Nerq-Vertrauensschwelle.",
            "Strongest signal:": "Stärkstes Signal:",
            "safe to use": "sicher in der Verwendung",
            "trust scores for all software": "Vertrauensbewertungen für alle Software",
            "7.5M+ entities": "7,5M+ Entitäten",
            "26 registries": "26 Register",
            "20 languages": "20 Sprachen",
            "Trust scores for software, apps, websites, travel destinations, and charities.": "Vertrauensbewertungen für Software, Apps, Websites, Reiseziele und Wohltätigkeitsorganisationen.",
            "Independent. Data-driven.": "Unabhängig. Datengesteuert.",
            "has a Nerq Trust Score of": "hat eine Nerq-Vertrauensbewertung von",
            "has a Trust Score of": "hat eine Vertrauensbewertung von",
            "has a trust score of": "hat eine Vertrauensbewertung von",
            "Current security score:": "Aktuelle Sicherheitsbewertung:",
            "Run your package manager's audit command for the latest findings.": "Führen Sie den Audit-Befehl Ihres Paketmanagers aus für die neuesten Ergebnisse.",
            "registry-specific vulnerability databases": "registerspezifische Schwachstellendatenbanken",
            "scores": "erzielt",
            "Same developer/company in other registries:": "Gleicher Entwickler/Unternehmen in anderen Registern:",
            "is a nonprofit organization": "ist eine gemeinnützige Organisation",
            "Financial estimates derived from Nerq analysis. Verify with the charity's public filings (IRS Form 990) for exact figures.": "Finanzschätzungen basieren auf der Nerq-Analyse. Überprüfen Sie die öffentlichen Einreichungen (IRS Form 990) für genaue Zahlen.",
            "IRS tax-exempt status on the IRS Tax Exempt Organization Search tool. Most registered 501(c)(3) nonprofits offer tax-deductible donations. Verify directly with the organization.": "IRS-Steuerbefreiungsstatus über das IRS Tax Exempt Organization Search Tool. Die meisten registrierten 501(c)(3)-Organisationen bieten steuerlich absetzbare Spenden an. Überprüfen Sie direkt bei der Organisation.",
            "has an overall trust score of": "hat eine Gesamtvertrauensbewertung von",
            "Compare with similar nonprofits below or browse the full charity index to find top-rated organizations in the same cause area.": "Vergleichen Sie mit ähnlichen gemeinnützigen Organisationen unten oder durchsuchen Sie den vollständigen Wohltätigkeitsindex.",
        },
        "fr": {
            "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "Il atteint le seuil de confiance de Nerq avec des signaux forts en sécurité, maintenance et adoption communautaire",
            "has not yet reached Nerq trust threshold (70+)": "n'a pas encore atteint le seuil de confiance Nerq (70+)",
            "This score is based on automated analysis of security, maintenance, community, and quality signals.": "Ce score est basé sur une analyse automatisée des signaux de sécurité, maintenance, communauté et qualité.",
            "As a development package,": "En tant que paquet de développement,",
            "does not directly collect end-user personal data": "ne collecte pas directement les données personnelles des utilisateurs",
            "License information not available. Open-source packages allow independent security review of the source code.": "Informations de licence non disponibles. Les paquets open source permettent un examen de sécurité indépendant du code source.",
            "using the same methodology, enabling direct cross-entity comparison": "en utilisant la même méthodologie, permettant une comparaison directe entre entités",
            "Scores are updated continuously as new data becomes available": "Les scores sont mis à jour en continu à mesure que de nouvelles données sont disponibles",
            "check back soon": "revenez bientôt",
            "Nerq trust scores are automated assessments based on publicly available signals. They are not endorsements or guarantees. Always conduct your own due diligence.": "Les scores de confiance Nerq sont des évaluations automatisées basées sur des signaux publics. Ce ne sont ni des recommandations ni des garanties. Effectuez toujours votre propre diligence raisonnable.",
            "Recommended for production use": "Recommandé pour une utilisation en production",
            "Yes, Express is safe to use.": "Oui, Express est sûr à utiliser.",
            "It is recommended for production use.": "Il est recommandé pour une utilisation en production.",
            "is a Node.js package": "est un paquet Node.js",
            "with a Nerq Trust Score of": "avec un Score de Confiance Nerq de",
            "to check for vulnerabilities. Review the package's GitHub repository for recent commits.": "pour vérifier les vulnérabilités. Consultez le dépôt GitHub du paquet pour les derniers commits.",
            "However, applications built with it may collect data depending on implementation": "Cependant, les applications construites avec celui-ci peuvent collecter des données selon l'implémentation",
            "Review the package's dependencies for potential supply chain risks. Run your package manager's audit command regularly.": "Examinez les dépendances du paquet pour les risques potentiels de chaîne d'approvisionnement. Exécutez régulièrement la commande d'audit de votre gestionnaire de paquets.",
            "Data from npm registry, GitHub repository, NVD, OSV.dev, and OpenSSF Scorecard.": "Données du registre npm, dépôt GitHub, NVD, OSV.dev et OpenSSF Scorecard.",
            "is computed from": "est calculé à partir de",
            "The score reflects": "Le score reflète",
            "independent dimensions": "dimensions indépendantes",
            "Meets Nerq Verified threshold.": "Atteint le seuil vérifié Nerq.",
            "Strongest signal:": "Signal le plus fort :",
            "safe to use": "sûr à utiliser",
            "trust scores for all software": "scores de confiance pour tous les logiciels",
            "Trust scores for software, apps, websites, travel destinations, and charities.": "Scores de confiance pour logiciels, apps, sites web, destinations et associations.",
            "Independent. Data-driven.": "Indépendant. Basé sur les données.",
            "has a Nerq Trust Score of": "a un Score de Confiance Nerq de",
            "has a Trust Score of": "a un Score de Confiance de",
            "has a trust score of": "a un score de confiance de",
            "Same developer/company in other registries:": "Même développeur/entreprise dans d'autres registres :",
            "is a nonprofit organization": "est une organisation à but non lucratif",
            "Financial estimates derived from Nerq analysis. Verify with the charity's public filings (IRS Form 990) for exact figures.": "Estimations financières basées sur l'analyse Nerq. Vérifiez avec les déclarations publiques (IRS Form 990) pour les chiffres exacts.",
            "IRS tax-exempt status on the IRS Tax Exempt Organization Search tool. Most registered 501(c)(3) nonprofits offer tax-deductible donations. Verify directly with the organization.": "Statut d'exonération fiscale IRS via l'outil de recherche IRS. La plupart des organisations 501(c)(3) offrent des dons déductibles d'impôts. Vérifiez directement auprès de l'organisation.",
            "has an overall trust score of": "a un score de confiance global de",
            "Compare with similar nonprofits below or browse the full charity index to find top-rated organizations in the same cause area.": "Comparez avec des organisations similaires ci-dessous ou parcourez l'index complet des associations.",
        },
        "ja": {
        "jurisdiction databases, independent audit reports, protocol analysis, and incident history": "管轄データベース、独立監査報告書、プロトコル分析、インシデント履歴",
        "Panama jurisdiction": "パナマの管轄",
        "logging practices, jurisdiction, audit history, ownership transparency": "ログ慣行、管轄権、監査履歴、所有権の透明性",
        "non-allied jurisdictions are not subject to mandatory data retention laws or intelligence-sharing agreements": "非同盟管轄区域はデータ保持法や情報共有協定の対象外",
        "jurisdiction": "管轄",
        "Five Eyes": "ファイブアイズ",
        "Independent": "独立",
        "Audited no-log": "監査済みノーログ",
        "Claimed no-log": "ノーログを主張",
        "Check jurisdiction": "管轄権を確認",
        "Verify independent audit exists": "独立監査の存在を確認",
        "Review logging policy": "ロギングポリシーを確認",
        "Antivirus": "アンチウイルス",
        # ── Vertical-specific strings (auto-generated) ──
        "Privacy Assessment": "プライバシー評価",
        "Breach History": "侵害履歴",
        "Encryption": "暗号化",
        "Zero-Knowledge Architecture": "ゼロナレッジ・アーキテクチャ",
        "Open Source": "オープンソース",
        "Jurisdiction": "管轄権",
        "Infrastructure": "インフラストラクチャ",
        "Security & Compliance": "セキュリティとコンプライアンス",
        "Data Location": "データの所在地",
        "Security Incidents": "セキュリティインシデント",
        "Independent Lab Results": "独立ラボテスト結果",
        "Security Track Record": "セキュリティ実績",
        "Build Your Security Stack": "セキュリティスタックを構築",
        "Best VPNs": "ベストVPN",
        "Best Password Managers": "ベストパスワードマネージャー",
        "Best Antivirus": "ベストアンチウイルス",
        "Security Assessment": "セキュリティ評価",
        "Ecommerce": "Eコマース",
        "Hosting Assessment": "ホスティング評価",
        "Antivirus Assessment": "アンチウイルス評価",
        "SaaS Assessment": "SaaS評価",
        "Website Builder Assessment": "ウェブサイトビルダー評価",
        "Exchange Assessment": "取引所評価",
        "Compare": "比較",
        "Combine these tools for comprehensive protection:": "これらのツールを組み合わせて総合的に保護:",
        "Proof of Reserves": "準備金証明",
            "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "Nerqの信頼しきい値を、セキュリティ、メンテナンス、コミュニティの強いシグナルで満たしています",
            "has not yet reached Nerq trust threshold (70+)": "Nerqの信頼しきい値（70+）にまだ達していません",
            "This score is based on automated analysis of security, maintenance, community, and quality signals.": "このスコアは、セキュリティ、メンテナンス、コミュニティ、品質シグナルの自動分析に基づいています。",
            "As a development package,": "開発パッケージとして、",
            "does not directly collect end-user personal data": "エンドユーザーの個人データを直接収集しません",
            "License information not available. Open-source packages allow independent security review of the source code.": "ライセンス情報は利用できません。オープンソースパッケージはソースコードの独立したセキュリティレビューを可能にします。",
            "using the same methodology, enabling direct cross-entity comparison": "同じ方法論を使用し、エンティティ間の直接比較を可能にします",
            "Scores are updated continuously as new data becomes available": "新しいデータが利用可能になるとスコアは継続的に更新されます",
            "check back soon": "近日中にご確認ください",
            "Nerq trust scores are automated assessments based on publicly available signals. They are not endorsements or guarantees. Always conduct your own due diligence.": "Nerqの信頼スコアは、公開されているシグナルに基づく自動評価です。推奨や保証ではありません。常にご自身でデューデリジェンスを行ってください。",
            "Recommended for production use": "本番環境での使用を推奨",
            "is a Node.js package": "はNode.jsパッケージです",
            "with a Nerq Trust Score of": "のNerq信頼スコアは",
            "to check for vulnerabilities. Review the package's GitHub repository for recent commits.": "脆弱性を確認するため。最新のコミットについてパッケージのGitHubリポジトリを確認してください。",
            "However, applications built with it may collect data depending on implementation": "ただし、それを使用して構築されたアプリケーションは実装に応じてデータを収集する場合があります",
            "Review the package's dependencies for potential supply chain risks. Run your package manager's audit command regularly.": "サプライチェーンリスクについてパッケージの依存関係を確認してください。パッケージマネージャーの監査コマンドを定期的に実行してください。",
            "Data from npm registry, GitHub repository, NVD, OSV.dev, and OpenSSF Scorecard.": "データはnpmレジストリ、GitHubリポジトリ、NVD、OSV.dev、OpenSSF Scorecardから。",
            "is computed from": "は以下から計算されます",
            "The score reflects": "スコアは以下を反映しています",
            "independent dimensions": "独立した次元",
            "Meets Nerq Verified threshold.": "Nerq認証しきい値を満たしています。",
            "Strongest signal:": "最も強いシグナル：",
            "safe to use": "安全に使用できます",
            "trust scores for all software": "すべてのソフトウェアの信頼スコア",
            "Trust scores for software, apps, websites, travel destinations, and charities.": "ソフトウェア、アプリ、ウェブサイト、旅行先、慈善団体の信頼スコア。",
            "Independent. Data-driven.": "独立。データ駆動。",
            "has a Nerq Trust Score of": "のNerq信頼スコアは",
            "has a Trust Score of": "の信頼スコアは",
            "has a trust score of": "の信頼スコアは",
            "Same developer/company in other registries:": "他のレジストリの同じ開発者/企業：",
            "is a nonprofit organization": "は非営利組織です",
            "Financial estimates derived from Nerq analysis. Verify with the charity's public filings (IRS Form 990) for exact figures.": "財務見積もりはNerq分析に基づいています。正確な数値はIRS Form 990の公開書類で確認してください。",
            "IRS tax-exempt status on the IRS Tax Exempt Organization Search tool. Most registered 501(c)(3) nonprofits offer tax-deductible donations. Verify directly with the organization.": "IRS免税ステータスはIRS Tax Exempt Organization検索ツールで確認できます。登録済みの501(c)(3)団体の多くは税控除対象の寄付を受け付けています。組織に直接確認してください。",
            "has an overall trust score of": "の総合信頼スコアは",
            "Compare with similar nonprofits below or browse the full charity index to find top-rated organizations in the same cause area.": "以下の類似の非営利団体と比較するか、慈善団体インデックス全体を閲覧してください。",
        },
        "pt": {
        # ── Vertical-specific strings ──
        "Privacy Assessment": "Avaliação de Privacidade",
        "Breach History": "Histórico de Violações",
        "Encryption": "Criptografia",
        "Build Your Security Stack": "Monte Seu Kit de Segurança",
        "Best VPNs": "Melhores VPNs",
        "Best Password Managers": "Melhores Gerenciadores de Senhas",
        "Best Antivirus": "Melhor Antivírus",
        "Security Assessment": "Avaliação de Segurança",
        "Compare": "Comparar",
        "Security & Compliance": "Segurança e Conformidade",
        "Combine these tools for comprehensive protection:": "Combine essas ferramentas para proteção abrangente:",
            "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption": "Atende ao limiar de confiança do Nerq com sinais fortes em segurança, manutenção e adoção pela comunidade",
            "has not yet reached Nerq trust threshold (70+)": "ainda não atingiu o limiar de confiança Nerq (70+)",
            "This score is based on automated analysis of security, maintenance, community, and quality signals.": "Esta pontuação é baseada em análise automatizada de sinais de segurança, manutenção, comunidade e qualidade.",
            "As a development package,": "Como pacote de desenvolvimento,",
            "does not directly collect end-user personal data": "não coleta diretamente dados pessoais do usuário final",
            "License information not available. Open-source packages allow independent security review of the source code.": "Informações de licença não disponíveis. Pacotes de código aberto permitem revisão de segurança independente do código fonte.",
            "using the same methodology, enabling direct cross-entity comparison": "usando a mesma metodologia, permitindo comparação direta entre entidades",
            "Scores are updated continuously as new data becomes available": "As pontuações são atualizadas continuamente à medida que novos dados ficam disponíveis",
            "check back soon": "volte em breve",
            "Nerq trust scores are automated assessments based on publicly available signals. They are not endorsements or guarantees. Always conduct your own due diligence.": "As pontuações de confiança do Nerq são avaliações automatizadas baseadas em sinais publicamente disponíveis. Não são endossos ou garantias. Sempre faça sua própria diligência.",
            "Recommended for production use": "Recomendado para uso em produção",
            "Yes, Express is safe to use.": "Sim, Express é seguro para usar.",
            "It is recommended for production use.": "É recomendado para uso em produção.",
            "is a Node.js package": "é um pacote Node.js",
            "with a Nerq Trust Score of": "com uma Pontuação de Confiança Nerq de",
            "to check for vulnerabilities. Review the package's GitHub repository for recent commits.": "para verificar vulnerabilidades. Revise o repositório GitHub do pacote para commits recentes.",
            "However, applications built with it may collect data depending on implementation": "No entanto, aplicações construídas com ele podem coletar dados dependendo da implementação",
            "Review the package's dependencies for potential supply chain risks. Run your package manager's audit command regularly.": "Revise as dependências do pacote para riscos potenciais na cadeia de suprimentos. Execute regularmente o comando de auditoria do seu gerenciador de pacotes.",
            "Data from npm registry, GitHub repository, NVD, OSV.dev, and OpenSSF Scorecard.": "Dados do registro npm, repositório GitHub, NVD, OSV.dev e OpenSSF Scorecard.",
            "is computed from": "é calculada a partir de",
            "The score reflects": "A pontuação reflete",
            "independent dimensions": "dimensões independentes",
            "Meets Nerq Verified threshold.": "Atinge o limiar verificado Nerq.",
            "Strongest signal:": "Sinal mais forte:",
            "safe to use": "seguro para usar",
            "trust scores for all software": "pontuações de confiança para todos os softwares",
            "Trust scores for software, apps, websites, travel destinations, and charities.": "Pontuações de confiança para software, apps, sites, destinos e instituições.",
            "Independent. Data-driven.": "Independente. Baseado em dados.",
            "has a Nerq Trust Score of": "tem uma Pontuação de Confiança Nerq de",
            "has a Trust Score of": "tem uma Pontuação de Confiança de",
            "has a trust score of": "tem uma pontuação de confiança de",
            "Same developer/company in other registries:": "Mesmo desenvolvedor/empresa em outros registros:",
            "is a nonprofit organization": "é uma organização sem fins lucrativos",
            "Financial estimates derived from Nerq analysis. Verify with the charity's public filings (IRS Form 990) for exact figures.": "Estimativas financeiras baseadas na análise Nerq. Verifique com os registros públicos (IRS Form 990) para números exatos.",
            "IRS tax-exempt status on the IRS Tax Exempt Organization Search tool. Most registered 501(c)(3) nonprofits offer tax-deductible donations. Verify directly with the organization.": "Status de isenção fiscal IRS na ferramenta de busca IRS. A maioria das organizações 501(c)(3) oferece doações dedutíveis de impostos. Verifique diretamente com a organização.",
            "has an overall trust score of": "tem uma pontuação de confiança geral de",
            "Compare with similar nonprofits below or browse the full charity index to find top-rated organizations in the same cause area.": "Compare com organizações similares abaixo ou navegue pelo índice completo de instituições.",
        },
    }
    if lang in _COMMON_SUBSTRINGS:
        for en_str, loc_str in _COMMON_SUBSTRINGS[lang].items():
            html = html.replace(en_str, loc_str)

    if lang in _CONTENT_TRANSLATIONS:
        # JSON-LD inLanguage for ALL translated languages
        html = html.replace('"@type": "WebPage"', f'"@type": "WebPage", "inLanguage": "{lang}"')
        html = html.replace('"@type": "FAQPage"', f'"@type": "FAQPage", "inLanguage": "{lang}"')
        html = html.replace('"@type":"WebPage"', f'"@type":"WebPage","inLanguage":"{lang}"')
        html = html.replace('"@type":"FAQPage"', f'"@type":"FAQPage","inLanguage":"{lang}"')

        # /best/ page translations
        if lang in _BEST_PAGE_TRANSLATIONS:
            for en_str, loc_str in _BEST_PAGE_TRANSLATIONS[lang].items():
                html = html.replace(en_str, loc_str)

        # Common JSON-LD name translations (uses _CONTENT_TRANSLATIONS patterns)
        t = _CONTENT_TRANSLATIONS[lang]
        _trust_score_t = t.get("Trust Score Breakdown", "Trust Score Breakdown")
        _safety_score_t = t.get("Safety Score Breakdown", "Safety Score Breakdown")
        html = html.replace('"name": "Trust Score Breakdown for', f'"name": "{_trust_score_t} for')
        html = html.replace('"name": "Safety Score Breakdown for', f'"name": "{_safety_score_t} for')

        # Common meta fixes using dict
        _safe_t = t.get("Safe", "Safe")
        _caution_t = t.get("Use Caution", "Use Caution")
        _avoid_t = t.get("Avoid", "Avoid")
        # nerq:question pattern
        html = _re_t.sub(r'nerq:question" content="Is (.+?) safe\?"', f'nerq:question" content="{_safe_t}? \\1"', html)

        # og:description
        _ind_safety = t.get("Independent Trust & Security Analysis", "Independent Trust & Security Analysis")
        html = html.replace('Independent safety assessment by Nerq.', f'{_ind_safety} por Nerq.' if lang != "en" else 'Independent safety assessment by Nerq.')

    if lang == "es":
        # Title: "Is X Safe?" or "¿Es X Safe?" → "¿Es X Seguro?"
        html = _re_t.sub(r'<title>Is (.+?) Safe\?', r'<title>¿Es \1 Seguro?', html, count=1)
        html = _re_t.sub(r'<title>¿Es (.+?) Safe\?', r'<title>¿Es \1 Seguro?', html, count=1)
        html = html.replace('Independent Trust &amp; Security Analysis 2026 | Nerq', 'Análisis de Confianza y Seguridad 2026 | Nerq')
        # H1/H2: any remaining "Safe?" → "Seguro?"
        html = _re_t.sub(r'>Is (.+?) Safe\?<', r'>¿Es \1 Seguro?<', html)
        html = _re_t.sub(r'>¿Es (.+?) safe\?<', r'>¿Es \1 seguro?<', html)
        html = _re_t.sub(r'>¿Es (.+?) Safe\?<', r'>¿Es \1 Seguro?<', html)
        html = _re_t.sub(r'>Is (.+?) safe\?<', r'>¿Es \1 seguro?<', html)
        # "What data does X collect?" or partial "¿Qué datos recopila X collect?"
        html = _re_t.sub(r'>What data does (.+?) collect\?<', r'>¿Qué datos recopila \1?<', html)
        html = _re_t.sub(r'>¿Qué datos recopila (.+?) collect\?<', r'>¿Qué datos recopila \1?<', html)
        # "Is X secure?" or "¿Es X secure?"
        html = _re_t.sub(r'>Is (.+?) secure\?<', r'>¿Es \1 seguro?<', html)
        html = _re_t.sub(r'>¿Es (.+?) secure\?<', r'>¿Es \1 seguro?<', html)
        # "X Across Platforms" → "X en Otras Plataformas"
        html = _re_t.sub(r'>(.+?) Across Platforms<', r'>\1 en Otras Plataformas<', html)
        html = _re_t.sub(r'>(.+?) across platforms<', r'>\1 en otras plataformas<', html)
        # "Safety Guide: X" → "Guía de Seguridad: X"
        html = _re_t.sub(r'>Safety Guide: (.+?)<', r'>Guía de Seguridad: \1<', html)
        # "What is X?" → "¿Qué es X?"
        html = _re_t.sub(r'>What is (.+?)\?<', r'>¿Qué es \1?<', html)
        # "Key Safety Concerns for X" → "Principales Preocupaciones de Seguridad para X"
        html = _re_t.sub(r'>Key Safety Concerns for (.+?)<', r'>Principales Preocupaciones para \1<', html)
        # Section title "Details" → "Detalles"
        html = html.replace('>Details<', '>Detalles<')

        # ── Dynamic paragraph translations (regex for f-string patterns) ──

        # 1. Verdict lead: "Yes, X is safe to use. X is a Y with..."
        html = _re_t.sub(
            r'Yes, (.+?) is safe to use\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Sí, \1 es seguro para usar. \1 es un \2 con una Puntuación de Confianza Nerq de \3/100 (\4)', html)
        html = _re_t.sub(
            r'Use (.+?) with some caution\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Usa \1 con precaución. \1 es un \2 con una Puntuación de Confianza Nerq de \3/100 (\4)', html)
        html = _re_t.sub(
            r'Exercise caution with (.+?)\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Ten precaución con \1. \1 es un \2 con una Puntuación de Confianza Nerq de \3/100 (\4)', html)

        # 2. Citation detail: "It meets Nerq's trust threshold..."
        html = html.replace(
            "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption",
            "Cumple con el umbral de confianza de Nerq con señales sólidas en seguridad, mantenimiento y adopción comunitaria")
        html = html.replace("Recommended for production use", "Recomendado para uso en producción")
        html = html.replace("It is recommended for production use.", "Se recomienda para uso en producción.")

        # 3. "X is a Y — description"
        html = _re_t.sub(r'>(.+?) is a (Node\.js package|Python package|Rust crate|Chrome extension|WordPress plugin|VPN service|game|website|SaaS platform) — ',
                         r'>\1 es un \2 — ', html)

        # 4. Safety guide text
        html = html.replace("to check for vulnerabilities. Review the package's GitHub repository for recent commits.",
                           "para verificar vulnerabilidades. Revise el repositorio de GitHub del paquete para confirmaciones recientes.")
        html = html.replace("You can also check the trust score via API:", "También puede verificar la puntuación de confianza vía API:")

        # 5-6. Trust score references
        html = _re_t.sub(r'>(.+?) has a Nerq Trust Score of<', r'>\1 tiene una Puntuación de Confianza Nerq de<', html)
        html = _re_t.sub(r'>(.+?) has a Trust Score of<', r'>\1 tiene una Puntuación de Confianza de<', html)
        html = html.replace("and has not yet reached Nerq trust threshold (70+).",
                           "y aún no ha alcanzado el umbral de confianza de Nerq (70+).")
        html = html.replace("This score is based on automated analysis of security, maintenance, community, and quality signals.",
                           "Esta puntuación se basa en un análisis automatizado de señales de seguridad, mantenimiento, comunidad y calidad.")
        html = html.replace("and meets Nerq trust threshold", "y cumple con el umbral de confianza de Nerq")

        # 8. Data sources
        html = html.replace("Data from npm registry, GitHub repository, NVD, OSV.dev, and OpenSSF Scorecard.",
                           "Datos del registro npm, repositorio de GitHub, NVD, OSV.dev y OpenSSF Scorecard.")
        html = _re_t.sub(r'dimensions\. Data from (.+?)\.', r'dimensiones. Datos de \1.', html)

        # 9. "X is a Y maintained by Z"
        html = _re_t.sub(r'>(.+?) is a (.+?) maintained by (.+?)\.', r'>\1 es un \2 mantenido por \3.', html)

        # 10. Privacy analysis
        html = html.replace("As a development package,", "Como paquete de desarrollo,")
        html = html.replace("does not directly collect end-user personal data",
                           "no recopila directamente datos personales del usuario final")
        html = html.replace("However, applications built with it may collect data depending on implementation",
                           "Sin embargo, las aplicaciones construidas con él pueden recopilar datos según la implementación")
        html = html.replace("Privacy score:", "Puntuación de privacidad:")

        # 11. Dependencies
        html = html.replace("Review the package's dependencies for potential supply chain risks. Run your package manager's audit command regularly.",
                           "Revise las dependencias del paquete para posibles riesgos en la cadena de suministro. Ejecute el comando de auditoría de su gestor de paquetes regularmente.")
        html = html.replace("package's dependencies for potential supply chain risks",
                           "dependencias del paquete para posibles riesgos en la cadena de suministro")

        # 12. License
        html = html.replace("License information not available. Open-source packages allow independent security review of the source code.",
                           "Información de licencia no disponible. Los paquetes de código abierto permiten una revisión de seguridad independiente del código fuente.")

        # 13. Methodology
        html = _re_t.sub(r'is computed from (.+?)\. The score reflects (\d+) independent dimensions:',
                         r'se calcula a partir de \1. La puntuación refleja \2 dimensiones independientes:', html)
        html = html.replace("using the same methodology, enabling direct cross-entity comparison. Scores are updated continuously as new data becomes available.",
                           "utilizando la misma metodología, lo que permite la comparación directa entre entidades. Las puntuaciones se actualizan continuamente a medida que nuevos datos están disponibles.")

        # 15. FAQ alternatives
        html = _re_t.sub(r'>What are safer alternatives to (.+?)\?<', r'>¿Cuáles son alternativas más seguras a \1?<', html)

        # 16. Category text
        html = _re_t.sub(r'In the (\w+) category, more (.+?) are being analyzed', r'En la categoría \1, se están analizando más \2', html)
        html = html.replace("check back soon.", "vuelva pronto.")
        html = _re_t.sub(r'(\w+) scores ([\d.]+)/100', r'\1 tiene una puntuación de \2/100', html)

        # 17. Security checks
        html = _re_t.sub(r'Nerq checks (.+?) against NVD, OSV\.dev, and registry-specific vulnerability databases\. Current security score: (.+?)\.',
                         r'Nerq verifica \1 contra NVD, OSV.dev y bases de datos de vulnerabilidades específicas del registro. Puntuación de seguridad actual: \2.', html)
        html = html.replace("Run your package manager's audit command for the latest findings.",
                           "Ejecute el comando de auditoría de su gestor de paquetes para los hallazgos más recientes.")

        # 18. Maintenance
        html = _re_t.sub(r'>How actively maintained is (.+?)\?<', r'>¿Qué tan activamente se mantiene \1?<', html)

        # 19. Meets threshold
        html = html.replace("Meets Nerq Verified threshold.", "Cumple con el umbral Nerq Verificado.")
        html = _re_t.sub(r'(.+?) has a trust score of ([\d.]+)/100 \((\w[\w+-]*)\)\. Cumple',
                         r'\1 tiene una puntuación de confianza de \2/100 (\3). Cumple', html)

        # 20. Disclaimer
        html = html.replace("Nerq trust scores are automated assessments based on publicly available signals. They are not endorsements or guarantees. Always conduct your own due diligence.",
                           "Las puntuaciones de confianza de Nerq son evaluaciones automatizadas basadas en señales disponibles públicamente. No son respaldos ni garantías. Siempre realice su propia diligencia debida.")

        # 21. Footer
        html = html.replace("nerq.ai &mdash; trust scores for all software &middot; 7.5M+ entities &middot; 26 registries &middot; 20 languages",
                           "nerq.ai &mdash; puntuaciones de confianza para todo el software &middot; 7,5M+ entidades &middot; 26 registros &middot; 20 idiomas")

        # Catch-all: remaining "has a Nerq Trust Score of" / "has a Trust Score of" anywhere
        html = html.replace(" has a Nerq Trust Score of ", " tiene una Puntuación de Confianza Nerq de ")
        html = html.replace(" has a Trust Score of ", " tiene una Puntuación de Confianza de ")
        html = html.replace("review the full report below for specific considerations",
                           "revise el informe completo a continuación para consideraciones específicas")
        html = html.replace("0 known vulnerabilities", "0 vulnerabilidades conocidas")
        html = html.replace("Independent security analysis of", "Análisis de seguridad independiente de")
        html = html.replace("trust signals, vulnerabilities, compliance, and safer alternatives",
                           "señales de confianza, vulnerabilidades, cumplimiento y alternativas más seguras")
        html = html.replace("Is Express safe to use?", "¿Es Express seguro para usar?")
        html = html.replace("Yes, it is safe to use.", "Sí, es seguro para usar.")
        html = html.replace("Strongest signal:", "Señal más fuerte:")
        html = html.replace("Score based on multiple trust dimensions.", "Puntuación basada en múltiples dimensiones de confianza.")
        html = html.replace("Scores update as new data becomes available.", "Las puntuaciones se actualizan con nuevos datos.")
        html = html.replace("Does Express have known vulnerabilities?", "¿Tiene Express vulnerabilidades conocidas?")

        # VPN-specific text
        html = html.replace("outside the Five Eyes, Nine Eyes, and Fourteen Eyes surveillance alliances",
                           "fuera de las alianzas de vigilancia de los Cinco Ojos, Nueve Ojos y Catorce Ojos")
        html = html.replace("This is significant because VPN providers in non-allied jurisdictions are not subject to mandatory data retention laws or intelligence-sharing agreements",
                           "Esto es significativo porque los proveedores de VPN en jurisdicciones no aliadas no están sujetos a leyes obligatorias de retención de datos o acuerdos de intercambio de inteligencia")
        html = html.replace("According to independent audit reports,", "Según informes de auditoría independientes,")
        html = html.replace("has undergone third-party security audits verifying its infrastructure and no-logs claims",
                           "ha sido sometido a auditorías de seguridad de terceros que verifican su infraestructura y su política de no registros")
        html = html.replace("This is a strong positive signal", "Esta es una señal positiva fuerte")
        html = html.replace("most VPN providers have not been independently audited", "la mayoría de los proveedores de VPN no han sido auditados independientemente")
        html = html.replace("No known data breaches associated with this service.", "No se conocen filtraciones de datos asociadas con este servicio.")
        html = _re_t.sub(r'What are the best alternatives to (.+?)\?', r'¿Cuáles son las mejores alternativas a \1?', html)
        html = _re_t.sub(r'(.+?) vs alternatives: which is safer\?', r'\1 vs alternativas: ¿cuál es más seguro?', html)
        html = html.replace("Nerq assesses", "Nerq evalúa")
        html = html.replace("data practices as part of its trust score", "prácticas de datos como parte de su puntuación de confianza")
        html = html.replace("Review the full safety report for detailed privacy analysis", "Revise el informe de seguridad completo para un análisis detallado de privacidad")

        # Travel-specific text
        html = html.replace("Travel advisory:", "Aviso de viaje:")
        html = html.replace("Exercise Normal Precautions", "Ejercer Precauciones Normales")
        html = html.replace("Exercise Increased Caution", "Ejercer Mayor Precaución")
        html = html.replace("Reconsider Travel", "Reconsiderar Viaje")
        html = html.replace("Do Not Travel", "No Viajar")
        html = html.replace("recommended for all types of travelers", "recomendado para todo tipo de viajeros")
        html = html.replace("Overall assessment:", "Evaluación general:")
        html = html.replace("Is it safe to visit?", "¿Es seguro visitar?")
        html = _re_t.sub(r'Is (.+?) safe for solo travelers\?', r'¿Es \1 seguro para viajeros solos?', html)
        html = _re_t.sub(r'Is (.+?) safe for women\?', r'¿Es \1 seguro para mujeres?', html)
        html = _re_t.sub(r'Is (.+?) safe for LGBTQ\+ travelers\?', r'¿Es \1 seguro para viajeros LGBTQ+?', html)
        html = _re_t.sub(r'Is (.+?) safe for families\?', r'¿Es \1 seguro para familias?', html)
        html = html.replace("Key Safety Risks in", "Principales Riesgos de Seguridad en")
        html = html.replace("Practical Travel Information", "Información Práctica de Viaje")
        html = html.replace("Official Travel Advisories", "Avisos Oficiales de Viaje")
        html = html.replace("Similar Safe Destinations", "Destinos Seguros Similares")
        html = html.replace("How We Calculate Country Safety Scores", "Cómo Calculamos las Puntuaciones de Seguridad de Países")
        html = html.replace("Crime &amp; Personal Safety", "Crimen y Seguridad Personal")
        html = html.replace("Political Stability", "Estabilidad Política")
        html = html.replace("Health &amp; Medical", "Salud y Atención Médica")
        html = html.replace("Natural Disaster Risk", "Riesgo de Desastres Naturales")
        html = html.replace("Infrastructure &amp; Transport", "Infraestructura y Transporte")
        html = html.replace("Traveler Rights", "Derechos del Viajero")
        html = html.replace("Very Low Risk", "Riesgo Muy Bajo")
        html = html.replace("Low Risk", "Riesgo Bajo")
        html = html.replace("Medium Risk", "Riesgo Medio")
        html = html.replace("High Risk", "Riesgo Alto")
        html = html.replace("Very High Risk", "Riesgo Muy Alto")
        html = html.replace("Emergency Numbers", "Números de Emergencia")
        html = html.replace("Best Time to Visit", "Mejor Época para Visitar")
        html = html.replace("Entry Requirements", "Requisitos de Entrada")
        html = html.replace("See all safest countries", "Ver todos los países más seguros")
        html = html.replace("Data sources: Global Peace Index, UNODC, WHO, World Bank, US State Dept",
                           "Fuentes de datos: Índice de Paz Global, UNODC, OMS, Banco Mundial, Depto. Estado de EE.UU.")
        html = html.replace("Last updated:", "Última actualización:")
        html = html.replace("Independent travel safety assessment", "Evaluación independiente de seguridad de viaje")

        # Health template text
        html = html.replace("This page is for", "Esta página es para")
        html = html.replace("and does not constitute medical advice, diagnosis, or treatment recommendations",
                           "y no constituye asesoramiento médico, diagnóstico o recomendaciones de tratamiento")
        html = html.replace("Dietary supplements are not evaluated by the FDA to diagnose, treat, cure, or prevent any disease",
                           "Los suplementos dietéticos no son evaluados por la FDA para diagnosticar, tratar, curar o prevenir ninguna enfermedad")
        html = html.replace("Supplements can interact with medications", "Los suplementos pueden interactuar con medicamentos")
        html = html.replace("Always consult a qualified healthcare professional", "Siempre consulte a un profesional de salud calificado")
        html = html.replace("before starting any supplement", "antes de iniciar cualquier suplemento")
        html = _re_t.sub(r'What are the safety concerns for (.+?)\?', r'¿Cuáles son las preocupaciones de seguridad para \1?', html)
        html = html.replace("The primary area of concern is", "El área principal de preocupación es")
        html = html.replace("Consult a healthcare provider for personalized advice", "Consulte a un profesional de salud para asesoramiento personalizado")
        html = _re_t.sub(r'What are the side effects of (.+?)\?', r'¿Cuáles son los efectos secundarios de \1?', html)
        html = _re_t.sub(r'Does (.+?) interact with medications\?', r'¿Interactúa \1 con medicamentos?', html)
        html = html.replace("Dietary supplements are not FDA-approved in the same way as drugs. The FDA regulates supplements under DSHEA.",
                           "Los suplementos dietéticos no están aprobados por la FDA de la misma manera que los medicamentos. La FDA regula los suplementos bajo DSHEA.")
        html = html.replace("Regulatory Status score:", "Puntuación de Estado Regulatorio:")
        html = html.replace("Some jurisdictions may restrict this supplement. Check local regulations.",
                           "Algunas jurisdicciones pueden restringir este suplemento. Verifique las regulaciones locales.")
        html = _re_t.sub(r'the recommended dosage of (.+?)\?', r'la dosis recomendada de \1?', html)
        html = html.replace("Dosage varies by formulation and individual needs. Always follow the manufacturer's label and consult a healthcare provider",
                           "La dosis varía según la formulación y las necesidades individuales. Siempre siga la etiqueta del fabricante y consulte a un profesional de salud")
        html = html.replace("educational and informational purposes only", "fines educativos e informativos únicamente")
        html = html.replace("Consult a dermatologist", "Consulte a un dermatólogo")
        html = html.replace("Individual skin reactions vary", "Las reacciones individuales de la piel varían")
        html = html.replace("Cosmetic ingredient regulations differ by country", "Las regulaciones de ingredientes cosméticos difieren según el país")
        html = html.replace("especially with sensitive skin, skin conditions, or during pregnancy", "especialmente con piel sensible, condiciones cutáneas o durante el embarazo")
        html = html.replace("not nutritional or medical advice", "no es asesoramiento nutricional o médico")
        html = html.replace("Nerq aggregates data from FDA, EFSA, and published research", "Nerq agrega datos de la FDA, EFSA e investigación publicada")
        html = html.replace("Regulatory status varies by country", "El estado regulatorio varía según el país")
        html = html.replace("Consult a healthcare professional or registered dietitian", "Consulte a un profesional de salud o dietista registrado")
        html = html.replace("for dietary decisions", "para decisiones dietéticas")
        html = html.replace("This page is for informational purposes only", "Esta página es solo para fines informativos")
        html = html.replace("Always consult a qualified professional before making health-related decisions",
                           "Siempre consulte a un profesional calificado antes de tomar decisiones relacionadas con la salud")
        html = html.replace("Data sourced from FDA, EFSA, NIH, and peer-reviewed research",
                           "Datos obtenidos de la FDA, EFSA, NIH e investigación revisada por pares")
        html = html.replace("Full health disclaimer", "Descargo de responsabilidad de salud completo")

        # ── TRAVEL template remaining patterns ──
        # Title patterns
        html = _re_t.sub(r'¿Es (.+?) Safe to Visit\?', r'¿Es \1 Seguro para Visitar?', html)
        html = html.replace("2026 Safety Score &amp; Travel Guide | Nerq", "Puntuación de Seguridad 2026 y Guía de Viaje | Nerq")
        html = html.replace("Safety Analysis | Nerq", "Análisis de Seguridad | Nerq")
        html = html.replace("Health &amp; Medical", "Salud y Atención Médica")
        html = html.replace("Health & Medical", "Salud y Atención Médica")
        # Travel advisories
        html = html.replace("Advisory estimated from Nerq Safety Score. Check official sources for current status.",
                           "Aviso estimado a partir de la Puntuación de Seguridad Nerq. Verifique fuentes oficiales para el estado actual.")
        # Traveler type headings
        html = _re_t.sub(r'¿Es (.+?) safe for solo travelers\?', r'¿Es \1 seguro para viajeros solos?', html)
        html = _re_t.sub(r'¿Es (.+?) safe for women\?', r'¿Es \1 seguro para mujeres?', html)
        html = _re_t.sub(r'¿Es (.+?) safe for LGBTQ\+ travelers\?', r'¿Es \1 seguro para viajeros LGBTQ+?', html)
        html = _re_t.sub(r'¿Es (.+?) safe for families\?', r'¿Es \1 seguro para familias?', html)
        html = _re_t.sub(r'¿Es (.+?) safe to visit right now\?', r'¿Es \1 seguro para visitar ahora?', html)
        html = _re_t.sub(r'¿Es (.+?) safe for solo female travelers\?', r'¿Es \1 seguro para mujeres viajeras solas?', html)
        html = _re_t.sub(r'¿Es tap water safe to drink in (.+?)\?', r'¿Es seguro beber agua del grifo en \1?', html)
        html = _re_t.sub(r'¿Qué es the biggest safety risk in (.+?)\?', r'¿Cuál es el mayor riesgo de seguridad en \1?', html)
        html = _re_t.sub(r'Do I need vaccinations for (.+?)\?', r'¿Necesito vacunas para \1?', html)
        # Travel body text
        html = html.replace("Traveler rights score:", "Puntuación de derechos del viajero:")
        html = html.replace("Women travelers generally report positive experiences.", "Las mujeres viajeras generalmente reportan experiencias positivas.")
        html = html.replace("Check current travel advisories for specific guidance on women's safety",
                           "Consulte los avisos de viaje actuales para orientación específica sobre la seguridad de las mujeres")
        html = html.replace("LGBTQ+ travelers generally report few issues.", "Los viajeros LGBTQ+ generalmente reportan pocos problemas.")
        html = html.replace("Generally safe for solo women.", "Generalmente seguro para mujeres solas.")
        html = html.replace("Generally tolerant environment.", "Ambiente generalmente tolerante.")
        html = html.replace("Health score:", "Puntuación de salud:")
        html = html.replace("Check with your doctor and review WHO recommendations for", "Consulte a su médico y revise las recomendaciones de la OMS para")
        html = html.replace("before traveling. Routine vaccinations should be up to date.", "antes de viajar. Las vacunas de rutina deben estar al día.")
        html = html.replace("making it suitable for solo travelers.", "lo que lo hace adecuado para viajeros solos.")
        html = html.replace("making it suitable for family travel.", "lo que lo hace adecuado para viaje familiar.")
        html = html.replace("Solo travelers generally report feeling safe.", "Los viajeros solos generalmente reportan sentirse seguros.")
        html = html.replace("Research specific areas and take standard precautions.", "Investigue áreas específicas y tome precauciones estándar.")
        html = html.replace("Families can travel with confidence.", "Las familias pueden viajar con confianza.")
        html = html.replace("Good healthcare infrastructure available.", "Buena infraestructura sanitaria disponible.")
        html = html.replace("Well-developed transport and communications.", "Transporte y comunicaciones bien desarrollados.")
        html = html.replace("Score:", "Puntuación:")
        html = html.replace("Independent travel safety assessment", "Evaluación independiente de seguridad de viaje")
        html = _re_t.sub(r"(.+?)'s safety score of", r'La puntuación de seguridad de \1 de', html)
        html = html.replace("Nerq indexes over 7.5 million entities across 26 registries including 158 countries, enabling direct cross-destination comparison. Scores are updated as new data becomes available.",
                           "Nerq indexa más de 7,5 millones de entidades en 26 registros, incluyendo 158 países, lo que permite la comparación directa entre destinos. Las puntuaciones se actualizan a medida que hay nuevos datos disponibles.")

        # ── HEALTH template remaining patterns ──
        html = html.replace("Nerq Safety Score:", "Puntuación de Seguridad Nerq:")
        html = html.replace("(Fair)", "(Regular)")
        html = html.replace("(Excellent)", "(Excelente)")
        html = html.replace("(Good)", "(Bueno)")
        html = html.replace("(Poor)", "(Malo)")
        html = html.replace("(Very Poor)", "(Muy Malo)")
        html = html.replace("Independent skincare safety analysis", "Análisis independiente de seguridad para el cuidado de la piel")
        html = html.replace("Independent health & safety analysis", "Análisis independiente de salud y seguridad")
        html = _re_t.sub(r'Updated (March|January|February|April|May|June|July|August|September|October|November|December) (\d+), (\d+)', r'Actualizado \1 \2, \3', html)
        html = html.replace("Pregnancy: Not recommended during pregnancy", "Embarazo: No recomendado durante el embarazo")
        html = html.replace("Irritation: Can cause skin irritation", "Irritación: Puede causar irritación cutánea")
        html = html.replace("Not recommended during pregnancy", "No recomendado durante el embarazo")
        html = html.replace("Can cause skin irritation", "Puede causar irritación cutánea")
        html = html.replace("Perform a patch test before regular use.", "Realice una prueba de parche antes del uso regular.")
        html = _re_t.sub(r'¿Es (.+?) safe in skincare\?', r'¿Es \1 seguro para el cuidado de la piel?', html)
        html = _re_t.sub(r'¿Es (.+?) Safe in Skincare\?', r'¿Es \1 Seguro para el Cuidado de la Piel?', html)
        html = html.replace("Some Safety Concerns.", "Algunas Preocupaciones de Seguridad.")
        html = html.replace("Use with caution — consult a dermatologist.", "Usar con precaución — consulte a un dermatólogo.")
        html = _re_t.sub(r'Can (.+?) cause skin irritation\?', r'¿Puede \1 causar irritación cutánea?', html)
        html = html.replace("Irritation has been reported. Patch test before use.", "Se ha reportado irritación. Pruebe en un parche antes de usar.")
        html = _re_t.sub(r'¿Es (.+?) safe during pregnancy\?', r'¿Es \1 seguro durante el embarazo?', html)
        html = html.replace("Consult your dermatologist or OB-GYN before using products containing", "Consulte a su dermatólogo u obstetra antes de usar productos que contengan")
        html = html.replace("during pregnancy. Safety data may be limited for this use case.", "durante el embarazo. Los datos de seguridad pueden ser limitados para este caso.")
        html = _re_t.sub(r'¿Es (.+?) banned in the EU\?', r'¿Está \1 prohibido en la UE?', html)
        html = html.replace("Comedogenicity depends on concentration and formulation.", "La comedogenicidad depende de la concentración y formulación.")
        html = html.replace("Check the product's full ingredient list and your skin type for the best assessment.",
                           "Verifique la lista completa de ingredientes del producto y su tipo de piel para la mejor evaluación.")
        html = _re_t.sub(r'¿Cuáles son los efectos secundarios de (.+?) on skin\?', r'¿Cuáles son los efectos secundarios de \1 en la piel?', html)
        html = html.replace("Side effects including irritation and sensitivity have been reported.", "Se han reportado efectos secundarios incluyendo irritación y sensibilidad.")
        html = _re_t.sub(r'How does (.+?) compare to similar cosmetic ingredients\?', r'¿Cómo se compara \1 con ingredientes cosméticos similares?', html)
        html = _re_t.sub(r'How does (.+?) compare to similar supplements\?', r'¿Cómo se compara \1 con suplementos similares?', html)
        html = html.replace("Compare with similar ingredients below.", "Compare con ingredientes similares a continuación.")
        html = html.replace("Compare with similar supplements below to find the best option for your needs.", "Compare con suplementos similares a continuación para encontrar la mejor opción.")
        html = html.replace("How does Nerq rate cosmetic ingredients?", "¿Cómo evalúa Nerq los ingredientes cosméticos?")
        html = html.replace("How does Nerq rate supplements?", "¿Cómo evalúa Nerq los suplementos?")
        html = html.replace("is based on analysis of published toxicology data, regulatory filings, clinical studies, and adverse event reports",
                           "se basa en el análisis de datos toxicológicos publicados, expedientes regulatorios, estudios clínicos e informes de eventos adversos")
        html = html.replace("The score reflects 5 health-specific dimensions", "La puntuación refleja 5 dimensiones específicas de salud")
        html = html.replace("Nerq indexes over 7.5 million entities across 26 registries, enabling direct cross-category comparison. Scores are updated as new safety data becomes available.",
                           "Nerq indexa más de 7,5 millones de entidades en 26 registros, permitiendo la comparación directa entre categorías. Las puntuaciones se actualizan a medida que hay nuevos datos de seguridad.")
        html = _re_t.sub(r'¿Es (.+?) safe to take daily\?', r'¿Es seguro tomar \1 diariamente?', html)
        html = html.replace("Significant concerns identified. Consult a healthcare professional before use.", "Preocupaciones significativas identificadas. Consulte a un profesional de salud antes de usar.")
        html = html.replace("Drug Interactions score:", "Puntuación de Interacciones con Medicamentos:")
        html = html.replace("Drug interactions have been documented. Always consult your doctor.", "Se han documentado interacciones con medicamentos. Siempre consulte a su médico.")
        html = html.replace("Sensitization Risk score:", "Puntuación de Riesgo de Sensibilización:")
        html = html.replace("Skin Safety score:", "Puntuación de Seguridad Cutánea:")

        # Travel body text (dynamic)
        html = html.replace("has an overall safety score of", "tiene una puntuación general de seguridad de")
        html = html.replace("so solo travelers should exercise additional caution.", "por lo que los viajeros solos deben tener precaución adicional.")
        html = html.replace("Crime &amp; personal safety score:", "Puntuación de crimen y seguridad personal:")
        html = html.replace("Crime & personal safety score:", "Puntuación de crimen y seguridad personal:")
        html = html.replace("Infrastructure & transport score:", "Puntuación de infraestructura y transporte:")
        html = html.replace("Infrastructure &amp; transport score:", "Puntuación de infraestructura y transporte:")
        html = html.replace("Overall safety:", "Seguridad general:")
        html = html.replace("Health &amp; medical:", "Salud y atención médica:")
        html = html.replace("Health & medical:", "Salud y atención médica:")
        html = html.replace("Infrastructure:", "Infraestructura:")
        html = html.replace("Family travel requires significant preparation", "El viaje familiar requiere preparación significativa")
        html = html.replace("Good health infrastructure suggests safe tap water in urban areas.", "La buena infraestructura sanitaria sugiere agua del grifo segura en áreas urbanas.")
        html = html.replace("Health &amp; medical score:", "Puntuación de salud y atención médica:")
        html = html.replace("the lowest-scoring dimension is", "la dimensión con menor puntuación es")
        html = html.replace("Research this area before traveling.", "Investigue esta área antes de viajar.")
        html = html.replace("is based on data from the Global Peace Index, UNODC crime statistics, World Bank governance indicators, WHO health data",
                           "se basa en datos del Índice de Paz Global, estadísticas de crimen de UNODC, indicadores de gobernanza del Banco Mundial, datos de salud de la OMS")

        # ── CHARITY template ──
        html = _re_t.sub(r'¿Es (.+?) Trustworthy\?', r'¿Es \1 Confiable?', html)
        html = html.replace("Charity Trust Score | Nerq", "Puntuación de Confianza Benéfica | Nerq")
        html = html.replace("Independent charity trust assessment", "Evaluación independiente de confianza benéfica")
        html = html.replace("Actualizado March", "Actualizado marzo")
        html = html.replace("Significant transparency concerns — conduct thorough research before donating",
                           "Preocupaciones significativas de transparencia — investigue a fondo antes de donar")
        html = html.replace("Highly Recommended — strong transparency and effectiveness signals",
                           "Altamente Recomendado — señales sólidas de transparencia y eficacia")
        html = _re_t.sub(r"¿Qué es (.+?)'s Trust Score breakdown\?", r'¿Cuál es el desglose de puntuación de \1?', html)
        html = html.replace("Financial Transparency", "Transparencia Financiera")
        html = html.replace("Program Effectiveness", "Eficacia del Programa")
        html = html.replace("Governance", "Gobernanza")
        html = html.replace("Donor Trust", "Confianza del Donante")
        html = html.replace("Accountability", "Responsabilidad")
        html = _re_t.sub(r'What did Nerq find about (.+?)\?', r'¿Qué encontró Nerq sobre \1?', html)
        html = _re_t.sub(r'How does (.+?) spend its money\?', r'¿Cómo gasta \1 su dinero?', html)
        html = _re_t.sub(r'How does (.+?) spend donations\?', r'¿Cómo gasta \1 las donaciones?', html)
        html = html.replace("Estimated program expense ratio:", "Relación estimada de gastos del programa:")
        html = html.replace("A significant portion of funds may go to administration and fundraising",
                           "Una parte significativa de los fondos puede destinarse a administración y recaudación")
        html = html.replace("Financial estimates derived from Nerq analysis. Verify with the charity's public filings (IRS Form 990) for exact figures.",
                           "Estimaciones financieras derivadas del análisis de Nerq. Verifique con los registros públicos (Formulario IRS 990) para cifras exactas.")
        html = _re_t.sub(r'How is (.+?) governed\?', r'¿Cómo se gobierna \1?', html)
        html = html.replace("Governance score:", "Puntuación de gobernanza:")
        html = html.replace("Accountability score:", "Puntuación de responsabilidad:")
        html = html.replace("Governance practices raise concerns — donors should verify board independence and audit history.",
                           "Las prácticas de gobernanza generan preocupaciones — los donantes deben verificar la independencia de la junta directiva y el historial de auditorías.")
        html = html.replace("Gobernanza practices raise concerns — donors should verify board independence and audit history.",
                           "Las prácticas de gobernanza generan preocupaciones — los donantes deben verificar la independencia de la junta directiva y el historial de auditorías.")
        html = html.replace("Accountability measures are present but could be strengthened.",
                           "Las medidas de responsabilidad están presentes pero podrían fortalecerse.")
        html = _re_t.sub(r'¿Es (.+?) a trustworthy charity\?', r'¿Es \1 una organización benéfica confiable?', html)
        html = html.replace("Review the latest Form 990 for detailed spending breakdown.",
                           "Revise el último Formulario 990 para un desglose detallado de gastos.")
        html = _re_t.sub(r"¿Es my donation to (.+?) tax-deductible\?", r'¿Es mi donación a \1 deducible de impuestos?', html)
        html = _re_t.sub(r"Check (.+?)'s IRS tax-exempt status", r'Verifique el estado de exención fiscal del IRS de \1', html)
        html = html.replace("on the IRS Tax Exempt Organization Search tool. Most registered 501(c)(3) nonprofits offer tax-deductible donations. Verify directly with the organization.",
                           "en la herramienta de búsqueda de organizaciones exentas del IRS. La mayoría de las organizaciones 501(c)(3) registradas ofrecen donaciones deducibles de impuestos. Verifique directamente con la organización.")
        html = _re_t.sub(r'Does (.+?) publish annual reports\?', r'¿Publica \1 informes anuales?', html)
        html = html.replace("Transparency score:", "Puntuación de transparencia:")
        html = html.replace("Organizations with high transparency scores typically publish annual reports and audited financials.",
                           "Las organizaciones con altas puntuaciones de transparencia generalmente publican informes anuales y estados financieros auditados.")
        html = _re_t.sub(r'How effective is (.+?) at achieving its mission\?', r'¿Qué tan eficaz es \1 en lograr su misión?', html)
        html = html.replace("Limited evidence of program effectiveness — request impact data directly.",
                           "Evidencia limitada de eficacia del programa — solicite datos de impacto directamente.")
        html = html.replace("Strong program effectiveness indicates measurable impact toward its stated mission.",
                           "Una fuerte eficacia del programa indica un impacto medible hacia su misión declarada.")
        html = _re_t.sub(r'Who oversees (.+?)\?', r'¿Quién supervisa a \1?', html)
        html = html.replace("Governance information is limited — review IRS Form 990 for board details.",
                           "La información de gobernanza es limitada — revise el formulario IRS 990 para detalles de la junta directiva.")
        html = html.replace("Gobernanza information is limited — review IRS Form 990 for board details.",
                           "La información de gobernanza es limitada — revise el formulario IRS 990 para detalles de la junta directiva.")
        html = html.replace("Indicates strong board oversight and organizational controls.",
                           "Indica una fuerte supervisión de la junta y controles organizacionales.")
        html = _re_t.sub(r'How does (.+?) compare to similar charities\?', r'¿Cómo se compara \1 con organizaciones similares?', html)
        html = html.replace("Compare with similar nonprofits below or browse the full charity index to find top-rated organizations in the same cause area.",
                           "Compare con organizaciones sin fines de lucro similares o explore el índice completo de organizaciones benéficas.")
        html = html.replace("How does Nerq rate charities?", "¿Cómo evalúa Nerq las organizaciones benéficas?")
        html = html.replace("is based on analysis of public financial filings, governance disclosures, program outcomes, and donor feedback signals",
                           "se basa en el análisis de declaraciones financieras públicas, divulgaciones de gobernanza, resultados de programas y señales de retroalimentación de donantes")
        html = html.replace("The score reflects 5 charity-specific dimensions", "La puntuación refleja 5 dimensiones específicas de organizaciones benéficas")
        html = html.replace("enabling direct cross-organization comparison. Scores are updated as new data becomes available.",
                           "permitiendo la comparación directa entre organizaciones. Las puntuaciones se actualizan a medida que hay nuevos datos disponibles.")

        # ── APP / KING specific ──
        html = html.replace("is published by", "es publicado por")
        html = html.replace("on Google Play", "en Google Play")
        html = html.replace("on App Store", "en App Store")
        html = html.replace("with approximately", "con aproximadamente")
        html = html.replace("downloads.", "descargas.")
        html = html.replace("users should review the app's privacy labels", "los usuarios deben revisar las etiquetas de privacidad de la aplicación")
        html = html.replace("Before granting permissions, check whether the app requests access to camera, microphone, contacts, or location",
                           "Antes de otorgar permisos, verifique si la aplicación solicita acceso a cámara, micrófono, contactos o ubicación")
        html = html.replace("and whether each permission is necessary for the app's core functionality",
                           "y si cada permiso es necesario para la funcionalidad principal de la aplicación")
        html = html.replace("Review Data Safety section in Google Play. Check permissions and ad trackers.",
                           "Revise la sección Seguridad de Datos en Google Play. Verifique permisos y rastreadores de anuncios.")
        html = _re_t.sub(r'Al evaluar cualquier (.+?), watch for:', r'Al evaluar cualquier \1, tenga en cuenta:', html)
        html = html.replace("excessive permissions, data collection, ad trackers, background data usage",
                           "permisos excesivos, recopilación de datos, rastreadores de anuncios, uso de datos en segundo plano")
        html = _re_t.sub(r"¿Qué es (.+?)'s trust score\?", r'¿Cuál es la puntuación de confianza de \1?', html)
        html = _re_t.sub(r'¿Es (.+?) safe for kids\?', r'¿Es \1 seguro para niños?', html)
        html = html.replace("Review", "Revisar")  # careful — only at word boundaries
        html = _re_t.sub(r"Revisar (.+?)'s privacy labels and data safety sections", r'Revise las etiquetas de privacidad y secciones de seguridad de datos de \1', html)
        html = html.replace("Privacy Report", "Informe de Privacidad")

        # ── INGREDIENT remaining ──
        html = html.replace("Individuals with sensitivities should exercise caution.", "Las personas con sensibilidades deben tener precaución.")
        html = html.replace("Toxicology score:", "Puntuación de toxicología:")
        html = html.replace("Side effects have been documented. Consult a healthcare provider.", "Se han documentado efectos secundarios. Consulte a un profesional de salud.")
        html = _re_t.sub(r'¿Es (.+?) safe for children\?', r'¿Es \1 seguro para niños?', html)
        html = html.replace("Long-term Safety score:", "Puntuación de seguridad a largo plazo:")
        html = html.replace("Long-term data is limited. Follow recommended guidelines for safe consumption levels.",
                           "Los datos a largo plazo son limitados. Siga las pautas recomendadas para niveles seguros de consumo.")
        html = _re_t.sub(r'¿Es (.+?) safe for people with allergies\?', r'¿Es \1 seguro para personas con alergias?', html)
        html = html.replace("Allergen Risk score:", "Puntuación de riesgo de alérgenos:")
        html = html.replace("Allergen concerns have been noted. Consult an allergist.", "Se han señalado preocupaciones de alérgenos. Consulte a un alergólogo.")
        html = _re_t.sub(r'How does (.+?) compare to similar ingredients\?', r'¿Cómo se compara \1 con ingredientes similares?', html)
        html = html.replace("How does Nerq rate food ingredients?", "¿Cómo evalúa Nerq los ingredientes alimentarios?")
        html = html.replace("(Good)", "(Bueno)")
        html = html.replace("(Fair)", "(Regular)")

        # Footer description
        html = html.replace("Trust scores for software, apps, websites, travel destinations, and charities. 7.5M+ entities from 26 registries. Independent. Data-driven.",
                           "Puntuaciones de confianza para software, apps, sitios web, destinos turísticos y organizaciones benéficas. 7,5M+ entidades de 26 registros. Independiente. Basado en datos.")

        # ── JSON-LD: add inLanguage + translate names ──
        html = html.replace('"@type": "WebPage"', '"@type": "WebPage", "inLanguage": "es"')
        html = html.replace('"@type": "FAQPage"', '"@type": "FAQPage", "inLanguage": "es"')
        html = html.replace('"@type":"WebPage"', '"@type":"WebPage","inLanguage":"es"')
        html = html.replace('"@type":"FAQPage"', '"@type":"FAQPage","inLanguage":"es"')
        # Translate JSON-LD names
        html = _re_t.sub(r'"name": "Is (.+?) Safe\?', r'"name": "¿Es \1 Seguro?', html)
        html = _re_t.sub(r'"name":"Is (.+?) Safe\?', r'"name":"¿Es \1 Seguro?', html)
        html = html.replace('"name": "Trust Score Breakdown for', '"name": "Desglose de Puntuación de Confianza para')
        html = html.replace('"name":"Trust Score Breakdown for', '"name":"Desglose de Puntuación de Confianza para')
        html = html.replace('"name": "Safety Reports"', '"name": "Informes de Seguridad"')
        html = html.replace('"name":"Safety Reports"', '"name":"Informes de Seguridad"')
        # Translate FAQ questions in JSON-LD
        html = _re_t.sub(r'"name": "Is (.+?) safe to use\?"', r'"name": "¿Es \1 seguro para usar?"', html)
        html = _re_t.sub(r'"name":"Is (.+?) safe to use\?"', r'"name":"¿Es \1 seguro para usar?"', html)
        html = _re_t.sub(r'"name": "What is (.+?)\'s trust score\?"', r'"name": "¿Cuál es la puntuación de confianza de \1?"', html)
        html = _re_t.sub(r'"name":"What is (.+?)\'s trust score\?"', r'"name":"¿Cuál es la puntuación de confianza de \1?"', html)
        html = _re_t.sub(r'"name": "Does (.+?) have known vulnerabilities\?"', r'"name": "¿Tiene \1 vulnerabilidades conocidas?"', html)
        html = _re_t.sub(r'"name":"Does (.+?) have known vulnerabilities\?"', r'"name":"¿Tiene \1 vulnerabilidades conocidas?"', html)
        html = _re_t.sub(r'"name": "How actively maintained is (.+?)\?"', r'"name": "¿Qué tan activamente se mantiene \1?"', html)
        html = _re_t.sub(r'"name": "What are safer alternatives to (.+?)\?"', r'"name": "¿Cuáles son alternativas más seguras a \1?"', html)

        # ── OG tags ──
        html = _re_t.sub(r'og:title" content="¿Es (.+?) Safe\?', r'og:title" content="¿Es \1 Seguro?', html)
        html = _re_t.sub(r'og:title" content="Is (.+?) Safe\?', r'og:title" content="¿Es \1 Seguro?', html)
        html = html.replace('Trust Score', 'Puntuación de Confianza')  # in og:title
        html = html.replace('og:description" content="Express — A trust grade', 'og:description" content="Express — Calificación A de confianza')
        html = html.replace('Independent safety assessment by Nerq.', 'Evaluación de seguridad independiente por Nerq.')
        # Fix mixed language in og:description for all entities
        html = _re_t.sub(r'og:description" content="(.+?) — (\w[\w+-]*) trust grade, ([\d.]+)/100\. Independent safety assessment by Nerq\."',
                         r'og:description" content="\1 — Calificación \2 de confianza, \3/100. Evaluación de seguridad independiente por Nerq."', html)

        # ── nerq: tags ──
        html = _re_t.sub(r'nerq:question" content="Is (.+?) safe\?"', r'nerq:question" content="¿Es \1 seguro?"', html)
        html = html.replace('safe to use.', 'seguro para usar.')
        html = html.replace('License: See repository', 'Licencia: Ver repositorio')

        # ── Remaining small fragments ──
        html = html.replace(">safe to use<", ">seguro para usar<")
        html = html.replace("Check the organization website", "Consulte el sitio web de la organización")

        # App-specific remaining
        html = html.replace("Users should review the app's privacy labels (available on the Google Play listing) to understand what data categories are collected, including identifiers, usage data, and location information.",
                           "Los usuarios deben revisar las etiquetas de privacidad de la app (disponibles en la ficha de Google Play) para entender qué categorías de datos se recopilan, incluyendo identificadores, datos de uso e información de ubicación.")
        html = html.replace("This meets the recommended security threshold for production use.", "Esto cumple con el umbral de seguridad recomendado para uso en producción.")
        html = html.replace("Review app permissions carefully before installing.", "Revise los permisos de la app cuidadosamente antes de instalar.")

        # App descriptions: "X is a Android app — ..."
        html = _re_t.sub(r'>(.+?) is a Android app — ', r'>\1 es una app de Android — ', html)
        html = _re_t.sub(r'>(.+?) is a iOS app — ', r'>\1 es una app de iOS — ', html)
        # "Reseña Data Safety section" (partial translation artifact)
        html = html.replace("Reseña Data Safety section in Google Play. Check permissions and ad trackers.",
                           "Revise la sección de Seguridad de Datos en Google Play. Verifique permisos y rastreadores de anuncios.")
        # Data sources for apps
        html = html.replace("Google Play metadata, Data Safety section, Exodus Privacy tracker analysis, and user ratings.",
                           "metadatos de Google Play, sección de Seguridad de Datos, análisis de rastreadores de Exodus Privacy y calificaciones de usuarios.")
        html = html.replace("Privacidad score:", "Puntuación de privacidad:")
        # "X's trust score of" (inside methodology)
        html = _re_t.sub(r"(.+?)'s trust score of", r"La puntuación de confianza de \1 de", html)
        # "Reseña X's privacy labels..." (partial artifact)
        html = _re_t.sub(r"Reseña (.+?)'s privacy labels and data safety sections\.",
                         r"Revise las etiquetas de privacidad y secciones de seguridad de datos de \1.", html)
        html = html.replace("Security score:", "Puntuación de seguridad:")
        html = html.replace("Trust score:", "Puntuación de confianza:")

        # Charity: remaining fragments
        html = html.replace(">Trustworthy?<", ">¿Confiable?<")
        html = html.replace("Trust Intelligence", "Inteligencia de Confianza")

        # ── JSON-LD descriptions (in JSON context) ──
        # Travel
        html = _re_t.sub(r'"name": "Is (.+?) Safe to Visit\? Safety Score', r'"name": "¿Es \1 Seguro para Visitar? Puntuación de Seguridad', html)
        html = _re_t.sub(r'"name":"Is (.+?) Safe to Visit\?', r'"name":"¿Es \1 Seguro para Visitar?', html)
        html = html.replace('"description": "Japan safety score:', '"description": "Puntuación de seguridad de Japón:')
        html = _re_t.sub(r'"description": "(.+?) safety score: ([\d.]+)/100 \((\w[\w+-]*)\)\. Travel advisory:',
                         r'"description": "Puntuación de seguridad de \1: \2/100 (\3). Aviso de viaje:', html)
        html = _re_t.sub(r'"description": "(.+?) is a travel destination with a Nerq Safety Score',
                         r'"description": "\1 es un destino de viaje con una Puntuación de Seguridad Nerq', html)
        # Charity
        html = _re_t.sub(r'"name": "Is (.+?) Trustworthy\? Charity',
                         r'"name": "¿Es \1 Confiable? Organización Benéfica', html)
        html = _re_t.sub(r'"description": "(.+?) is a nonprofit organization with a Nerq',
                         r'"description": "\1 es una organización sin fines de lucro con una', html)
        html = html.replace('"description": "Nerq Trust Score', '"description": "Puntuación de Confianza Nerq')
        # Health
        html = _re_t.sub(r'"name": "Is (.+?) Safe\? Health',
                         r'"name": "¿Es \1 Seguro? Salud', html)
        html = _re_t.sub(r'"name": "Is (.+?) Safe in Skincare\?',
                         r'"name": "¿Es \1 Seguro en el Cuidado de la Piel?', html)
        html = html.replace('"Safety Score Breakdown for', '"Desglose de Puntuación de Seguridad para')
        html = html.replace('Proceed with Caution', 'Proceder con Precaución')
        html = html.replace('Donor recommendation:', 'Recomendación para donantes:')
        html = html.replace('Highly Recommended', 'Altamente Recomendado')

        # ── nerq: meta tags ──
        html = _re_t.sub(r'nerq:question" content="¿Es (.+?) safe to visit\?"', r'nerq:question" content="¿Es \1 seguro para visitar?"', html)
        html = _re_t.sub(r'nerq:question" content="¿Es (.+?) safe\?"', r'nerq:question" content="¿Es \1 seguro?"', html)
        html = _re_t.sub(r'nerq:question" content="Is (.+?) safe', r'nerq:question" content="¿Es \1 seguro', html)
        html = html.replace('has a Nerq Safety Score of', 'tiene una Puntuación de Seguridad Nerq de')
        html = html.replace('meets the 70+ trust threshold', 'cumple con el umbral de confianza de 70+')
        html = html.replace('Crime &amp; Safety:', 'Crimen y Seguridad:')

        # ── JSON-LD description translation (catch-all patterns) ──
        # "X is a Y with a Nerq Trust/Safety Score"
        html = html.replace(' is a Node.js package with a Nerq', ' es un paquete de Node.js con una')
        html = html.replace(' is a Python package with a Nerq', ' es un paquete de Python con una')
        html = html.replace(' is a Android app with a Nerq', ' es una app de Android con una')
        html = html.replace(' is a iOS app with a Nerq', ' es una app de iOS con una')
        html = html.replace(' is a VPN service with a Nerq', ' es un servicio VPN con una')
        html = html.replace(' is a Chrome extension with a Nerq', ' es una extensión de Chrome con una')
        html = html.replace(' is a WordPress plugin with a Nerq', ' es un plugin de WordPress con una')
        html = html.replace(' is a SaaS platform with a Nerq', ' es una plataforma SaaS con una')
        html = html.replace(' is a game with a Nerq', ' es un juego con una')
        html = html.replace(' is a website with a Nerq', ' es un sitio web con una')
        html = html.replace('Trust Score of', 'Puntuación de Confianza de')
        html = html.replace('Safety Score of', 'Puntuación de Seguridad de')
        html = html.replace('trust score:', 'puntuación de confianza:')
        html = html.replace('safety score:', 'puntuación de seguridad:')

        # Meta description patterns
        html = html.replace('Financial transparency, program effectiveness, governance, and donor',
                           'Transparencia financiera, efectividad del programa, gobernanza y donantes')
        html = html.replace('trust grade', 'calificación de confianza')
        html = html.replace('by Nerq.', 'por Nerq.')

        # Citation title + remaining meta
        html = html.replace('Trust Analysis 2026', 'Análisis de Confianza 2026')
        html = html.replace('Safety Analysis 2026', 'Análisis de Seguridad 2026')
        html = html.replace('Puntuación de Confianza of', 'Puntuación de Confianza de')
        html = html.replace('Puntuación de Seguridad of', 'Puntuación de Seguridad de')
        html = html.replace('Seguridad Concerns Noted', 'Preocupaciones de Seguridad Identificadas')
        html = html.replace('Independent nonprofit trust assessment', 'Evaluación independiente de confianza de organizaciones')
        html = html.replace('Independent health safety analysis', 'Análisis independiente de seguridad para la salud')
        html = html.replace('Evidence base, safety profile, drug interactions', 'Base de evidencia, perfil de seguridad, interacciones farmacológicas')
        html = html.replace('regulatory data and scientific evidence', 'datos regulatorios y evidencia científica')
        html = html.replace('Seguridad Guides', 'Guías de Seguridad')
        # Fix "Nerq of X" → "Nerq de X" (leftover from partial translation)
        html = _re_t.sub(r'Nerq of (\d)', r'Nerq de \1', html)
        # og:title "Safety Score" in remaining contexts
        html = html.replace('Safety Score', 'Puntuación de Seguridad')

        # ── og: remaining ──
        html = html.replace('Independent nonprofit trust assessment by Nerq.', 'Evaluación de confianza independiente de organizaciones por Nerq.')
        html = html.replace('safety grade', 'calificación de seguridad')
        html = html.replace('Crime, health, disaster risks, tips for solo, women, LGBTQ+, and family travelers.',
                           'Crimen, salud, riesgos de desastres, consejos para viajeros solos, mujeres, LGBTQ+ y familias.')

        # ── Nav + footer translation ──
        html = html.replace('>Search<', '>Buscar<')
        html = html.replace('>Apps<', '>Aplicaciones<')
        html = html.replace('>Packages<', '>Paquetes<')
        html = html.replace('>Extensions<', '>Extensiones<')
        html = html.replace('>Websites<', '>Sitios Web<')
        html = html.replace('>Travel<', '>Viajes<')
        html = html.replace('>Charities<', '>Organizaciones Benéficas<')
        html = html.replace('>Compare<', '>Comparar<')
        html = html.replace('>API<', '>API<')
        # Footer sections
        html = html.replace('>Check Safety<', '>Verificar Seguridad<')
        html = html.replace('>Mobile Apps<', '>Aplicaciones Móviles<')
        html = html.replace('>VPNs<', '>VPNs<')
        html = html.replace('>Games<', '>Juegos<')
        html = html.replace('>Browser Extensions<', '>Extensiones de Navegador<')
        html = html.replace('>WordPress<', '>WordPress<')
        html = html.replace('>Countries<', '>Países<')
        html = html.replace('>Safety Guides<', '>Guías de Seguridad<')
        html = html.replace('>Check Website<', '>Verificar Sitio Web<')
        html = html.replace('>Trust Badges<', '>Insignias de Confianza<')
        html = html.replace('>About<', '>Acerca de<')
        html = html.replace('>Resources<', '>Recursos<')

    elif lang == "de":
        import re as _re_t
        html = _re_t.sub(r'<title>Is (.+?) Safe\?', r'<title>Ist \1 sicher?', html, count=1)
        html = html.replace('Independent Trust &amp; Security Analysis 2026 | Nerq', 'Unabhängige Vertrauens- und Sicherheitsanalyse 2026 | Nerq')
        html = _re_t.sub(r'>Is (.+?) Safe\?<', r'>Ist \1 sicher?<', html)
        html = _re_t.sub(r'>Is (.+?) safe\?<', r'>Ist \1 sicher?<', html)
        html = _re_t.sub(r'>What data does (.+?) collect\?<', r'>Welche Daten erhebt \1?<', html)
        html = _re_t.sub(r'>Is (.+?) secure\?<', r'>Ist \1 sicher?<', html)
        html = _re_t.sub(r'>(.+?) Across Platforms<', r'>\1 auf anderen Plattformen<', html)
        html = _re_t.sub(r'>Safety Guide: (.+?)<', r'>Sicherheitsleitfaden: \1<', html)
        html = _re_t.sub(r'>What is (.+?)\?<', r'>Was ist \1?<', html)
        html = _re_t.sub(r'>Key Safety Concerns for (.+?)<', r'>Wichtige Sicherheitsbedenken für \1<', html)
        html = html.replace('>Details<', '>Details<')
        html = _re_t.sub(r'>Is (.+?) Safe to Visit\?', r'>Ist \1 sicher zu besuchen?', html)
        html = _re_t.sub(r'>Is (.+?) safe for solo travelers\?<', r'>Ist \1 sicher für Alleinreisende?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for women\?<', r'>Ist \1 sicher für Frauen?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for families\?<', r'>Ist \1 sicher für Familien?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for LGBTQ\+ travelers\?<', r'>Ist \1 sicher für LGBTQ+-Reisende?<', html)
        html = _re_t.sub(r"(.+?)'s trust score of", r'Die Vertrauensbewertung von \1 von', html)
        html = _re_t.sub(r'Nerq of (\d)', r'Nerq von \1', html)
        html = html.replace('Safety Score', 'Sicherheitsbewertung')
        html = html.replace('Trust Analysis 2026', 'Vertrauensanalyse 2026')
        # Nav
        html = html.replace('>Search<', '>Suche<')
        html = html.replace('>Apps<', '>Apps<')
        html = html.replace('>Packages<', '>Pakete<')
        html = html.replace('>Extensions<', '>Erweiterungen<')
        html = html.replace('>Websites<', '>Websites<')
        html = html.replace('>Travel<', '>Reisen<')
        html = html.replace('>Charities<', '>Wohltätigkeit<')
        html = html.replace('>Compare<', '>Vergleichen<')
        html = html.replace('>Check Safety<', '>Sicherheit prüfen<')
        html = html.replace('>Resources<', '>Ressourcen<')
        html = html.replace('>About<', '>Über uns<')

    elif lang == "fr":
        import re as _re_t
        html = _re_t.sub(r'<title>Is (.+?) Safe\?', r'<title>\1 est-il sûr ?', html, count=1)
        html = html.replace('Independent Trust &amp; Security Analysis 2026 | Nerq', 'Analyse Indépendante de Confiance et Sécurité 2026 | Nerq')
        html = _re_t.sub(r'>Is (.+?) Safe\?<', r'>\1 est-il sûr ?<', html)
        html = _re_t.sub(r'>Is (.+?) safe\?<', r'>\1 est-il sûr ?<', html)
        html = _re_t.sub(r'>What data does (.+?) collect\?<', r'>Quelles données \1 collecte-t-il ?<', html)
        html = _re_t.sub(r'>Is (.+?) secure\?<', r'>\1 est-il sécurisé ?<', html)
        html = _re_t.sub(r'>(.+?) Across Platforms<', r'>\1 sur d\'autres plateformes<', html)
        html = _re_t.sub(r'>Safety Guide: (.+?)<', r'>Guide de sécurité : \1<', html)
        html = _re_t.sub(r'>What is (.+?)\?<', r'>Qu\'est-ce que \1 ?<', html)
        html = _re_t.sub(r'>Key Safety Concerns for (.+?)<', r'>Préoccupations de sécurité pour \1<', html)
        html = html.replace('>Details<', '>Détails<')
        html = _re_t.sub(r'>Is (.+?) Safe to Visit\?', r'>\1 est-il sûr à visiter ?', html)
        html = _re_t.sub(r'>Is (.+?) safe for solo travelers\?<', r'>\1 est-il sûr pour les voyageurs seuls ?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for women\?<', r'>\1 est-il sûr pour les femmes ?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for families\?<', r'>\1 est-il sûr pour les familles ?<', html)
        html = _re_t.sub(r"(.+?)'s trust score of", r'Le score de confiance de \1 de', html)
        html = _re_t.sub(r'Nerq of (\d)', r'Nerq de \1', html)
        html = html.replace('Safety Score', 'Score de Sécurité')
        html = html.replace('Trust Analysis 2026', 'Analyse de Confiance 2026')
        html = html.replace('>Search<', '>Recherche<')
        html = html.replace('>Packages<', '>Paquets<')
        html = html.replace('>Extensions<', '>Extensions<')
        html = html.replace('>Websites<', '>Sites Web<')
        html = html.replace('>Travel<', '>Voyage<')
        html = html.replace('>Charities<', '>Associations<')
        html = html.replace('>Compare<', '>Comparer<')
        html = html.replace('>Check Safety<', '>Vérifier la sécurité<')
        html = html.replace('>Resources<', '>Ressources<')
        html = html.replace('>About<', '>À propos<')

    elif lang == "ja":
        import re as _re_t
        html = _re_t.sub(r'<title>Is (.+?) Safe\?', r'<title>\1は安全ですか？', html, count=1)
        html = html.replace('Independent Trust &amp; Security Analysis 2026 | Nerq', '独立した信頼性・セキュリティ分析 2026 | Nerq')
        html = _re_t.sub(r'>Is (.+?) Safe\?<', r'>\1は安全ですか？<', html)
        html = _re_t.sub(r'>Is (.+?) safe\?<', r'>\1は安全ですか？<', html)
        html = _re_t.sub(r'>What data does (.+?) collect\?<', r'>\1はどのようなデータを収集しますか？<', html)
        html = _re_t.sub(r'>Is (.+?) secure\?<', r'>\1は安全ですか？<', html)
        html = _re_t.sub(r'>(.+?) Across Platforms<', r'>\1の他プラットフォーム<', html)
        html = _re_t.sub(r'>Safety Guide: (.+?)<', r'>セキュリティガイド: \1<', html)
        html = _re_t.sub(r'>What is (.+?)\?<', r'>\1とは？<', html)
        html = html.replace('>Details<', '>詳細<')
        html = _re_t.sub(r'>Is (.+?) Safe to Visit\?', r'>\1は訪問しても安全ですか？', html)
        html = _re_t.sub(r"(.+?)'s trust score of", r'\1の信頼スコア', html)
        html = _re_t.sub(r'Nerq of (\d)', r'Nerq の \1', html)
        html = html.replace('Safety Score', 'セキュリティスコア')
        html = html.replace('Trust Analysis 2026', '信頼性分析 2026')
        html = html.replace('>Search<', '>検索<')
        html = html.replace('>Apps<', '>アプリ<')
        html = html.replace('>Packages<', '>パッケージ<')
        html = html.replace('>Extensions<', '>拡張機能<')
        html = html.replace('>Websites<', '>ウェブサイト<')
        html = html.replace('>Travel<', '>旅行<')
        html = html.replace('>Charities<', '>慈善団体<')
        html = html.replace('>Compare<', '>比較<')
        html = html.replace('>Check Safety<', '>安全確認<')
        html = html.replace('>Resources<', '>リソース<')
        html = html.replace('>About<', '>概要<')

    elif lang == "pt":
        import re as _re_t
        html = _re_t.sub(r'<title>Is (.+?) Safe\?', r'<title>\1 é seguro?', html, count=1)
        html = html.replace('Independent Trust &amp; Security Analysis 2026 | Nerq', 'Análise Independente de Confiança e Segurança 2026 | Nerq')
        html = _re_t.sub(r'>Is (.+?) Safe\?<', r'>\1 é seguro?<', html)
        html = _re_t.sub(r'>Is (.+?) safe\?<', r'>\1 é seguro?<', html)
        html = _re_t.sub(r'>What data does (.+?) collect\?<', r'>Quais dados \1 coleta?<', html)
        html = _re_t.sub(r'>Is (.+?) secure\?<', r'>\1 é seguro?<', html)
        html = _re_t.sub(r'>(.+?) Across Platforms<', r'>\1 em outras plataformas<', html)
        html = _re_t.sub(r'>Safety Guide: (.+?)<', r'>Guia de Segurança: \1<', html)
        html = _re_t.sub(r'>What is (.+?)\?<', r'>O que é \1?<', html)
        html = html.replace('>Details<', '>Detalhes<')
        html = _re_t.sub(r'>Is (.+?) Safe to Visit\?', r'>\1 é seguro para visitar?', html)
        html = _re_t.sub(r'>Is (.+?) safe for solo travelers\?<', r'>\1 é seguro para viajantes solo?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for women\?<', r'>\1 é seguro para mulheres?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for families\?<', r'>\1 é seguro para famílias?<', html)
        html = _re_t.sub(r"(.+?)'s trust score of", r'A pontuação de confiança de \1 de', html)
        html = _re_t.sub(r'Nerq of (\d)', r'Nerq de \1', html)
        html = html.replace('Safety Score', 'Pontuação de Segurança')
        html = html.replace('Trust Analysis 2026', 'Análise de Confiança 2026')
        html = html.replace('>Search<', '>Buscar<')
        html = html.replace('>Packages<', '>Pacotes<')
        html = html.replace('>Extensions<', '>Extensões<')
        html = html.replace('>Websites<', '>Sites<')
        html = html.replace('>Travel<', '>Viagem<')
        html = html.replace('>Charities<', '>Instituições<')
        html = html.replace('>Compare<', '>Comparar<')
        html = html.replace('>Check Safety<', '>Verificar Segurança<')
        html = html.replace('>Resources<', '>Recursos<')
        html = html.replace('>About<', '>Sobre<')

    elif lang == "id":
        import re as _re_t
        html = _re_t.sub(r'<title>Is (.+?) Safe\?', r'<title>Apakah \1 Aman?', html, count=1)
        html = html.replace('Independent Trust &amp; Security Analysis 2026 | Nerq', 'Analisis Kepercayaan &amp; Keamanan Independen 2026 | Nerq')
        html = _re_t.sub(r'>Is (.+?) Safe\?<', r'>Apakah \1 Aman?<', html)
        html = _re_t.sub(r'>Is (.+?) safe\?<', r'>Apakah \1 aman?<', html)
        html = _re_t.sub(r'>What data does (.+?) collect\?<', r'>Data apa yang dikumpulkan \1?<', html)
        html = _re_t.sub(r'>Is (.+?) secure\?<', r'>Apakah \1 aman?<', html)
        html = _re_t.sub(r'>(.+?) Across Platforms<', r'>\1 di Platform Lain<', html)
        html = _re_t.sub(r'>Safety Guide: (.+?)<', r'>Panduan Keamanan: \1<', html)
        html = _re_t.sub(r'>What is (.+?)\?<', r'>Apa itu \1?<', html)
        html = html.replace('>Details<', '>Detail<')
        html = _re_t.sub(r'>Is (.+?) Safe to Visit\?', r'>Apakah \1 Aman Dikunjungi?', html)
        html = _re_t.sub(r'>Is (.+?) safe for solo travelers\?<', r'>Apakah \1 aman untuk wisatawan solo?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for women\?<', r'>Apakah \1 aman untuk wanita?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for LGBTQ\+ travelers\?<', r'>Apakah \1 aman untuk wisatawan LGBTQ+?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for families\?<', r'>Apakah \1 aman untuk keluarga?<', html)
        html = _re_t.sub(r'>Is (.+?) safe to visit right now\?<', r'>Apakah \1 aman dikunjungi saat ini?<', html)
        html = _re_t.sub(r'>Is tap water safe to drink in (.+?)\?<', r'>Apakah air keran aman diminum di \1?<', html)
        html = _re_t.sub(r'>Do I need vaccinations for (.+?)\?<', r'>Apakah saya perlu vaksinasi untuk \1?<', html)
        html = _re_t.sub(r'>What are safer alternatives to (.+?)\?<', r'>Apa alternatif yang lebih aman dari \1?<', html)
        html = _re_t.sub(r'>What are the side effects of (.+?)\?<', r'>Apa efek samping \1?<', html)
        html = _re_t.sub(r'>Does (.+?) interact with medications\?<', r'>Apakah \1 berinteraksi dengan obat-obatan?<', html)
        html = _re_t.sub(r"(.+?)'s trust score of", r'Skor kepercayaan \1 sebesar', html)
        html = _re_t.sub(r'Nerq of (\d)', r'Nerq sebesar \1', html)
        html = html.replace('Safety Score', 'Skor Keamanan')
        html = html.replace('Trust Analysis 2026', 'Analisis Kepercayaan 2026')
        # Nav
        html = html.replace('>Search<', '>Cari<')
        html = html.replace('>Apps<', '>Aplikasi<')
        html = html.replace('>Packages<', '>Paket<')
        html = html.replace('>Extensions<', '>Ekstensi<')
        html = html.replace('>Websites<', '>Situs Web<')
        html = html.replace('>Travel<', '>Wisata<')
        html = html.replace('>Charities<', '>Lembaga Amal<')
        html = html.replace('>Compare<', '>Bandingkan<')
        html = html.replace('>Resources<', '>Sumber Daya<')
        html = html.replace('>About<', '>Tentang<')
        html = html.replace('>Check Safety<', '>Periksa Keamanan<')
        html = html.replace('>Games<', '>Permainan<')
        html = html.replace('>Countries<', '>Negara<')
        html = html.replace('>Check Website<', '>Cek Situs Web<')
        html = html.replace('>Safety Guides<', '>Panduan Keamanan<')
        # Footer text
        html = html.replace('Trust scores for software, apps, websites, travel destinations, and charities', 'Skor kepercayaan untuk perangkat lunak, aplikasi, situs web, destinasi wisata, dan lembaga amal')
        html = html.replace('20 languages', '20 bahasa')
        html = html.replace('>Guides<', '>Panduan<')
        html = html.replace('>Mobile Apps<', '>Aplikasi Mobile<')
        html = html.replace('>Trust Badges<', '>Lencana Kepercayaan<')
        html = html.replace('>VPNs<', '>VPN<')
        html = html.replace('7.5M+ entities from 26 registries. Independent. Data-driven.', '7,5 juta+ entitas dari 26 registri. Independen. Berbasis data.')

        # ── Dynamic paragraph translations (verdict lead, definition, FAQ, safety guide) ──

        # 1. Verdict lead: "Yes, X is safe to use. X is a Y with..."
        html = _re_t.sub(
            r'Yes, (.+?) is safe to use\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Ya, \1 aman digunakan. \1 adalah \2 dengan Skor Kepercayaan Nerq sebesar \3/100 (\4)', html)
        html = _re_t.sub(
            r'Use (.+?) with some caution\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Gunakan \1 dengan hati-hati. \1 adalah \2 dengan Skor Kepercayaan Nerq sebesar \3/100 (\4)', html)
        html = _re_t.sub(
            r'Exercise caution with (.+?)\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Berhati-hatilah dengan \1. \1 adalah \2 dengan Skor Kepercayaan Nerq sebesar \3/100 (\4)', html)

        # 2. Short answer box: "YES —" / "CAUTION —" / "NO —"
        html = html.replace('<strong>YES</strong>', '<strong>YA</strong>')
        html = html.replace('<strong>CAUTION</strong>', '<strong>HATI-HATI</strong>')
        html = html.replace('<strong>NO — USE WITH CAUTION</strong>', '<strong>TIDAK — GUNAKAN DENGAN HATI-HATI</strong>')

        # 3. Citation detail / verdict detail
        html = html.replace('It meets Nerq\'s trust threshold with strong signals across security, maintenance, and community adoption', 'Memenuhi ambang batas kepercayaan Nerq dengan sinyal kuat di keamanan, pemeliharaan, dan adopsi komunitas')
        html = html.replace('It has moderate trust signals but shows some areas of concern that warrant attention', 'Memiliki sinyal kepercayaan sedang tetapi menunjukkan beberapa area yang perlu diperhatikan')
        html = html.replace('It has below-average trust signals with significant gaps in security, maintenance, or documentation', 'Memiliki sinyal kepercayaan di bawah rata-rata dengan celah signifikan di keamanan, pemeliharaan, atau dokumentasi')
        html = html.replace('Recommended for production use', 'Direkomendasikan untuk penggunaan produksi')
        html = html.replace('It is recommended for production use.', 'Direkomendasikan untuk penggunaan produksi.')
        html = html.replace('review the full report below for specific considerations', 'tinjau laporan lengkap di bawah untuk pertimbangan spesifik')
        html = html.replace('Suitable for development use', 'Cocok untuk penggunaan pengembangan')
        html = html.replace('review security and maintenance signals before production deployment', 'tinjau sinyal keamanan dan pemeliharaan sebelum penerapan produksi')
        html = html.replace('Not recommended for production use without thorough manual review and additional security measures', 'Tidak direkomendasikan untuk penggunaan produksi tanpa tinjauan manual menyeluruh dan langkah keamanan tambahan')
        html = html.replace('It is below the recommended threshold of 70.', 'Di bawah ambang batas yang direkomendasikan yaitu 70.')

        # 4. "X is a Y — description"
        html = _re_t.sub(r'>(.+?) is a (Node\.js package|Python package|Rust crate|Chrome extension|WordPress plugin|VPN service|game|website|SaaS platform|Firefox extension|VS Code extension|iOS app|Android app) — ',
                         r'>\1 adalah \2 — ', html)

        # 5. Entity type translations in body text
        html = html.replace('is a Node.js package', 'adalah paket Node.js')
        html = html.replace('is a Python package', 'adalah paket Python')
        html = html.replace('is a Rust crate', 'adalah crate Rust')
        html = html.replace('is a Chrome extension', 'adalah ekstensi Chrome')
        html = html.replace('is a WordPress plugin', 'adalah plugin WordPress')
        html = html.replace('is a VPN service', 'adalah layanan VPN')
        html = html.replace('is a iOS app', 'adalah aplikasi iOS')
        html = html.replace('is a Android app', 'adalah aplikasi Android')

        # 6. Safety guide text
        html = html.replace('to check for vulnerabilities. Review the package\'s GitHub repository for recent commits.', 'untuk memeriksa kerentanan. Tinjau repositori GitHub paket untuk commit terbaru.')
        html = html.replace('You can also check the trust score via API:', 'Anda juga dapat memeriksa skor kepercayaan melalui API:')
        html = html.replace('watch for:', 'perhatikan:')
        html = html.replace('dependency vulnerabilities, malicious packages, typosquatting', 'kerentanan dependensi, paket berbahaya, typosquatting')
        html = html.replace('Run your package manager\'s audit command regularly.', 'Jalankan perintah audit package manager Anda secara teratur.')
        html = html.replace('>Run <code>', '>Jalankan <code>')

        # 7. King sections — privacy/security
        html = _re_t.sub(r'(.+?) is a Node\.js package maintained by (.+?)\.', r'\1 adalah paket Node.js yang dipelihara oleh \2.', html)
        html = _re_t.sub(r'(.+?) is a (.+?) maintained by (.+?)\.', r'\1 adalah \2 yang dipelihara oleh \3.', html)
        html = html.replace(' maintained by ', ' yang dipelihara oleh ')
        html = html.replace('As a development package,', 'Sebagai paket pengembangan,')
        html = html.replace('does not directly collect end-user personal data', 'tidak secara langsung mengumpulkan data pribadi pengguna akhir')
        html = html.replace('However, applications built with it may collect data depending on implementation', 'Namun, aplikasi yang dibangun dengannya mungkin mengumpulkan data tergantung implementasi')
        html = html.replace('Review the package\'s dependencies for potential supply chain risks.', 'Tinjau dependensi paket untuk potensi risiko rantai pasokan.')
        html = html.replace('License information not available.', 'Informasi lisensi tidak tersedia.')
        html = html.replace('Open-source packages allow independent security review of the source code.', 'Paket open-source memungkinkan tinjauan keamanan independen terhadap kode sumber.')
        html = html.replace('known vulnerabilities (CVEs) in the National Vulnerability Database', 'kerentanan yang diketahui (CVE) di National Vulnerability Database')
        html = html.replace('This is a clean record.', 'Ini adalah catatan bersih.')
        html = html.replace('Review advisories and update to the latest version.', 'Tinjau advisori dan perbarui ke versi terbaru.')

        html = html.replace('and has not yet reached Nerq trust threshold (70+).', 'dan belum mencapai ambang batas kepercayaan Nerq (70+).')
        html = html.replace('and meets Nerq trust threshold', 'dan memenuhi ambang batas kepercayaan Nerq')
        html = html.replace('This score is based on automated analysis of security, maintenance, community, and quality signals.', 'Skor ini berdasarkan analisis otomatis sinyal keamanan, pemeliharaan, komunitas, dan kualitas.')

        # 8. Methodology
        html = html.replace('using the same methodology, enabling direct cross-entity comparison', 'menggunakan metodologi yang sama, memungkinkan perbandingan langsung antar entitas')
        html = html.replace('Scores are updated continuously as new data becomes available', 'Skor diperbarui secara berkelanjutan saat data baru tersedia')
        html = html.replace('is computed from', 'dihitung dari')
        html = html.replace('The score reflects', 'Skor ini mencerminkan')
        html = html.replace('independent dimensions', 'dimensi independen')
        html = html.replace('Each dimension is weighted equally to produce the composite trust score.', 'Setiap dimensi diberi bobot yang sama untuk menghasilkan skor kepercayaan komposit.')

        # 9. Key findings / signal descriptions
        html = html.replace('Composite trust score:', 'Skor kepercayaan komposit:')
        html = html.replace('across all available signals', 'dari semua sinyal yang tersedia')
        html = html.replace('Code quality, vulnerability exposure, and security practices.', 'Kualitas kode, eksposur kerentanan, dan praktik keamanan.')
        html = html.replace('Update frequency, issue responsiveness, active development.', 'Frekuensi pembaruan, responsivitas terhadap masalah, pengembangan aktif.')
        html = html.replace('README quality, API docs, usage examples.', 'Kualitas README, dokumentasi API, contoh penggunaan.')
        html = html.replace('Community adoption.', 'Adopsi komunitas.')
        html = html.replace('Composite score across all trust dimensions.', 'Skor komposit dari semua dimensi kepercayaan.')

        # 10. FAQ answers
        html = html.replace('Yes, it is safe to use.', 'Ya, aman digunakan.')
        html = html.replace('Use with some caution.', 'Gunakan dengan hati-hati.')
        html = html.replace('Exercise caution.', 'Berhati-hatilah.')
        html = html.replace('Significant trust concerns.', 'Masalah kepercayaan yang signifikan.')
        html = html.replace('Strongest signal:', 'Sinyal terkuat:')
        html = html.replace('Score based on', 'Skor berdasarkan')
        html = html.replace('multiple trust dimensions', 'beberapa dimensi kepercayaan')
        html = html.replace('Scores update as new data becomes available.', 'Skor diperbarui saat data baru tersedia.')
        html = html.replace('check back soon', 'kunjungi kembali segera')
        html = html.replace('higher-rated alternatives include', 'alternatif berperingkat lebih tinggi termasuk')
        html = html.replace('more Node.js packages are being analyzed', 'lebih banyak paket Node.js sedang dianalisis')
        html = html.replace('more Python packages are being analyzed', 'lebih banyak paket Python sedang dianalisis')
        html = html.replace('Meets Nerq Verified threshold.', 'Memenuhi ambang batas terverifikasi Nerq.')

        # 11. Security check FAQ
        html = html.replace('Nerq checks', 'Nerq memeriksa')
        html = html.replace('against NVD, OSV.dev, and registry-specific vulnerability databases', 'terhadap NVD, OSV.dev, dan database kerentanan khusus registry')
        html = html.replace('Current security score:', 'Skor keamanan saat ini:')
        html = html.replace('Run your package manager\'s audit command for the latest findings.', 'Jalankan perintah audit package manager Anda untuk temuan terbaru.')
        html = html.replace('has a trust score of', 'memiliki skor kepercayaan')
        html = html.replace('has a Nerq Trust Score of', 'memiliki Skor Kepercayaan Nerq sebesar')

        # 12. Footer bottom
        html = html.replace('trust scores for all software', 'skor kepercayaan untuk semua perangkat lunak')
        html = html.replace('7.5M+ entities', '7,5 juta+ entitas')
        html = html.replace('26 registries', '26 registry')

        # 13. og:description fix (catches "por Nerq" from Spanish leakage)
        html = html.replace('por Nerq', 'oleh Nerq')
        html = html.replace('Independent safety assessment by Nerq.', 'Penilaian keamanan independen oleh Nerq.')

        # 14. Breadcrumb in JSON-LD
        html = html.replace('"Safety Reports"', '"Laporan Keamanan"')

        # 15. FAQ questions (in <summary> and JSON-LD)
        # NOTE: specific patterns MUST come before generic "What is" replacement
        html = _re_t.sub(r"What is (.+?)'s trust score\?", r'Berapa skor kepercayaan \1?', html)
        html = _re_t.sub(r"Apa itu (.+?)'s trust score\?", r'Berapa skor kepercayaan \1?', html)  # catch post-translated
        html = _re_t.sub(r'Is (.+?) safe to use\?', r'Apakah \1 aman digunakan?', html)
        html = _re_t.sub(r'Is (.+?) safe\?', r'Apakah \1 aman?', html)
        html = _re_t.sub(r'What are safer alternatives to (.+?)\?', r'Apa alternatif yang lebih aman dari \1?', html)
        html = _re_t.sub(r'Does (.+?) have known vulnerabilities\?', r'Apakah \1 memiliki kerentanan yang diketahui?', html)
        html = _re_t.sub(r'How actively maintained is (.+?)\?', r'Seberapa aktif \1 dipelihara?', html)
        html = _re_t.sub(r'How does (.+?) compare to similar', r'Bagaimana \1 dibandingkan dengan', html)
        html = _re_t.sub(r'Can I use (.+?) in a regulated environment\?', r'Bisakah saya menggunakan \1 di lingkungan teregulasi?', html)

        # 16. FAQ answer fragments
        html = html.replace('In the npm category,', 'Dalam kategori npm,')
        html = html.replace('In the pypi category,', 'Dalam kategori pypi,')
        html = html.replace('In the crates category,', 'Dalam kategori crates,')
        html = _re_t.sub(r'In the (\w+) category,', r'Dalam kategori \1,', html)
        html = _re_t.sub(r'(.+?) scores ([\d.]+)/100\.', r'\1 mendapat skor \2/100.', html)

        # 17. "has a Trust Score of" in king sections
        html = _re_t.sub(r'(.+?) has a Trust Score of', r'\1 memiliki Skor Kepercayaan sebesar', html)

        # 18. Security king section fragments
        html = html.replace('Security score:', 'Skor keamanan:')
        html = html.replace('Privacy score:', 'Skor privasi:')
        html = _re_t.sub(r'(.+?) has (\d+) kerentanan', r'\1 memiliki \2 kerentanan', html)
        html = html.replace('to check for known vulnerabilities in your dependency tree', 'untuk memeriksa kerentanan yang diketahui di pohon dependensi Anda')
        html = html.replace('(`npm audit`, `pip audit`, `cargo audit`)', '(`npm audit`, `pip audit`, `cargo audit`)')

        # 19. Meta description
        html = html.replace('0 known vulnerabilities', '0 kerentanan diketahui')
        html = html.replace('License: See repository', 'Lisensi: Lihat repositori')
        html = html.replace('Independent security analysis of', 'Analisis keamanan independen terhadap')
        html = html.replace('trust signals, vulnerabilities, compliance, and safer alternatives', 'sinyal kepercayaan, kerentanan, kepatuhan, dan alternatif lebih aman')

        # 20. og:description
        html = html.replace('Independent safety assessment by Nerq', 'Penilaian keamanan independen oleh Nerq')
        html = html.replace('trust grade,', 'nilai kepercayaan,')

        # 21. Fix Schema.org @type that got wrongly translated by _CONTENT_TRANSLATIONS
        # Schema.org requires English @type values
        html = html.replace('"@type": "Ulasan"', '"@type": "Review"')
        html = html.replace('"@type":"Ulasan"', '"@type":"Review"')
        # reviewBody translation
        html = html.replace('with a Nerq Trust Score of', 'dengan Skor Kepercayaan Nerq sebesar')
        html = html.replace('Proceed with caution.', 'Lanjutkan dengan hati-hati.')
        html = html.replace('Not recommended.', 'Tidak direkomendasikan.')
        # JSON-LD
        html = _re_t.sub(r'"name": "Is (.+?) Safe\?', r'"name": "Apakah \1 Aman?', html)
        html = _re_t.sub(r'"name": "Is (.+?) Safe to Visit\?', r'"name": "Apakah \1 Aman Dikunjungi?', html)
        html = _re_t.sub(r'og:title" content="Is (.+?) Safe\?', r'og:title" content="Apakah \1 Aman?', html)
        html = _re_t.sub(r'nerq:question" content="Is (.+?) safe', r'nerq:question" content="Apakah \1 aman', html)

    elif lang == "cs":
        import re as _re_t
        html = _re_t.sub(r'<title>Is (.+?) Safe\?', r'<title>Je \1 bezpečný?', html, count=1)
        html = html.replace('Independent Trust &amp; Security Analysis 2026 | Nerq', 'Nezávislá analýza důvěryhodnosti a bezpečnosti 2026 | Nerq')
        html = _re_t.sub(r'>Is (.+?) Safe\?<', r'>Je \1 bezpečný?<', html)
        html = _re_t.sub(r'>Is (.+?) safe\?<', r'>Je \1 bezpečný?<', html)
        html = _re_t.sub(r'>What data does (.+?) collect\?<', r'>Jaká data shromažďuje \1?<', html)
        html = _re_t.sub(r'>Is (.+?) secure\?<', r'>Je \1 bezpečný?<', html)
        html = _re_t.sub(r'>(.+?) Across Platforms<', r'>\1 na dalších platformách<', html)
        html = _re_t.sub(r'>Safety Guide: (.+?)<', r'>Bezpečnostní průvodce: \1<', html)
        html = _re_t.sub(r'>What is (.+?)\?<', r'>Co je \1?<', html)
        html = html.replace('>Details<', '>Podrobnosti<')
        html = _re_t.sub(r'>Is (.+?) Safe to Visit\?', r'>Je \1 bezpečné navštívit?', html)
        html = _re_t.sub(r'>Is (.+?) safe for solo travelers\?<', r'>Je \1 bezpečné pro sólo cestovatele?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for women\?<', r'>Je \1 bezpečné pro ženy?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for LGBTQ\+ travelers\?<', r'>Je \1 bezpečné pro LGBTQ+ cestovatele?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for families\?<', r'>Je \1 bezpečné pro rodiny?<', html)
        html = _re_t.sub(r'>Is (.+?) safe to visit right now\?<', r'>Je \1 bezpečné navštívit právě teď?<', html)
        html = _re_t.sub(r'>Is tap water safe to drink in (.+?)\?<', r'>Je voda z kohoutku bezpečná k pití v \1?<', html)
        html = _re_t.sub(r'>Do I need vaccinations for (.+?)\?<', r'>Potřebuji očkování pro \1?<', html)
        html = _re_t.sub(r'>What are safer alternatives to (.+?)\?<', r'>Jaké jsou bezpečnější alternativy k \1?<', html)
        html = _re_t.sub(r'>What are the side effects of (.+?)\?<', r'>Jaké jsou vedlejší účinky \1?<', html)
        html = _re_t.sub(r'>Does (.+?) interact with medications\?<', r'>Interaguje \1 s léky?<', html)
        html = _re_t.sub(r"(.+?)'s trust score of", r'skóre důvěryhodnosti \1', html)
        html = _re_t.sub(r'Nerq of (\d)', r'Nerq \1', html)
        html = html.replace('Safety Score', 'Bezpečnostní skóre')
        html = html.replace('Trust Analysis 2026', 'Analýza důvěryhodnosti 2026')
        # Nav
        html = html.replace('>Search<', '>Hledat<')
        html = html.replace('>Apps<', '>Aplikace<')
        html = html.replace('>Packages<', '>Balíčky<')
        html = html.replace('>Extensions<', '>Rozšíření<')
        html = html.replace('>Websites<', '>Weby<')
        html = html.replace('>Travel<', '>Cestování<')
        html = html.replace('>Charities<', '>Charitativní organizace<')
        html = html.replace('>Compare<', '>Porovnat<')
        html = html.replace('>Resources<', '>Zdroje<')
        html = html.replace('>About<', '>O nás<')
        html = html.replace('>Check Safety<', '>Zkontrolovat bezpečnost<')
        html = html.replace('>Games<', '>Hry<')
        html = html.replace('>Countries<', '>Země<')
        html = html.replace('>Check Website<', '>Zkontrolovat web<')
        html = html.replace('>Safety Guides<', '>Bezpečnostní průvodci<')
        # Footer text
        html = html.replace('Trust scores for software, apps, websites, travel destinations, and charities', 'Skóre důvěryhodnosti pro software, aplikace, weby, cestovní destinace a charitativní organizace')
        html = html.replace('20 languages', '20 jazyků')
        html = html.replace('>Guides<', '>Průvodci<')
        html = html.replace('>Mobile Apps<', '>Mobilní aplikace<')
        html = html.replace('>Trust Badges<', '>Odznaky důvěryhodnosti<')
        html = html.replace('>VPNs<', '>VPN<')
        html = html.replace('7.5M+ entities from 26 registries. Independent. Data-driven.', '7,5M+ entit z 26 registrů. Nezávislé. Založené na datech.')

        # ── Dynamic paragraph translations ──

        # 1. Verdict lead
        html = _re_t.sub(
            r'Yes, (.+?) is safe to use\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Ano, \1 je bezpečný k použití. \1 je \2 se skóre důvěryhodnosti Nerq \3/100 (\4)', html)
        html = _re_t.sub(
            r'Use (.+?) with some caution\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Používejte \1 s opatrností. \1 je \2 se skóre důvěryhodnosti Nerq \3/100 (\4)', html)
        html = _re_t.sub(
            r'Exercise caution with (.+?)\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Buďte opatrní s \1. \1 je \2 se skóre důvěryhodnosti Nerq \3/100 (\4)', html)

        # 2. Short answer box
        html = html.replace('<strong>YES</strong>', '<strong>ANO</strong>')
        html = html.replace('<strong>CAUTION</strong>', '<strong>OPATRNOST</strong>')
        html = html.replace('<strong>NO — USE WITH CAUTION</strong>', '<strong>NE — POUŽÍVEJTE S OPATRNOSTÍ</strong>')

        # 3. Citation detail / verdict detail
        html = html.replace("It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption", 'Splňuje práh důvěryhodnosti Nerq se silnými signály v oblasti bezpečnosti, údržby a přijetí komunitou')
        html = html.replace('It has moderate trust signals but shows some areas of concern that warrant attention', 'Má střední signály důvěryhodnosti, ale vykazuje některé oblasti vyžadující pozornost')
        html = html.replace('It has below-average trust signals with significant gaps in security, maintenance, or documentation', 'Má podprůměrné signály důvěryhodnosti s významnými mezerami v bezpečnosti, údržbě nebo dokumentaci')
        html = html.replace('Recommended for production use', 'Doporučeno pro produkční použití')
        html = html.replace('It is recommended for production use.', 'Doporučeno pro produkční použití.')
        html = html.replace('review the full report below for specific considerations', 'přečtěte si úplnou zprávu níže pro konkrétní úvahy')
        html = html.replace('Suitable for development use', 'Vhodné pro vývojové použití')
        html = html.replace('review security and maintenance signals before production deployment', 'zkontrolujte bezpečnostní signály a signály údržby před nasazením do produkce')
        html = html.replace('Not recommended for production use without thorough manual review and additional security measures', 'Nedoporučeno pro produkční použití bez důkladné ruční kontroly a dalších bezpečnostních opatření')
        html = html.replace('It is below the recommended threshold of 70.', 'Je pod doporučeným prahem 70.')

        # 4. "X is a Y — description"
        html = _re_t.sub(r'>(.+?) is a (Node\.js package|Python package|Rust crate|Chrome extension|WordPress plugin|VPN service|game|website|SaaS platform|Firefox extension|VS Code extension|iOS app|Android app) — ',
                         r'>\1 je \2 — ', html)

        # 5. Entity type translations in body text
        html = html.replace('is a Node.js package', 'je balíček Node.js')
        html = html.replace('is a Python package', 'je balíček Pythonu')
        html = html.replace('is a Rust crate', 'je Rust crate')
        html = html.replace('is a Chrome extension', 'je rozšíření pro Chrome')
        html = html.replace('is a WordPress plugin', 'je plugin pro WordPress')
        html = html.replace('is a VPN service', 'je služba VPN')
        html = html.replace('is a iOS app', 'je aplikace pro iOS')
        html = html.replace('is a Android app', 'je aplikace pro Android')

        # 6. Safety guide text
        html = html.replace("to check for vulnerabilities. Review the package's GitHub repository for recent commits.", 'pro kontrolu zranitelností. Zkontrolujte GitHub repozitář balíčku pro nedávné commity.')
        html = html.replace('You can also check the trust score via API:', 'Skóre důvěryhodnosti můžete zkontrolovat také přes API:')
        html = html.replace('watch for:', 'sledujte:')
        html = html.replace('dependency vulnerabilities, malicious packages, typosquatting', 'zranitelnosti závislostí, škodlivé balíčky, typosquatting')
        html = html.replace("Run your package manager's audit command regularly.", 'Pravidelně spouštějte příkaz auditu vašeho správce balíčků.')
        html = html.replace('>Run <code>', '>Spusťte <code>')

        # 7. King sections — privacy/security
        html = _re_t.sub(r'(.+?) is a Node\.js package maintained by (.+?)\.', r'\1 je balíček Node.js udržovaný \2.', html)
        html = _re_t.sub(r'(.+?) is a (.+?) maintained by (.+?)\.', r'\1 je \2 udržovaný \3.', html)
        html = html.replace(' maintained by ', ' udržováno ')
        html = html.replace('As a development package,', 'Jako vývojový balíček,')
        html = html.replace('does not directly collect end-user personal data', 'přímo neshromažďuje osobní údaje koncových uživatelů')
        html = html.replace('However, applications built with it may collect data depending on implementation', 'Avšak aplikace s ním vytvořené mohou shromažďovat data v závislosti na implementaci')
        html = html.replace("Review the package's dependencies for potential supply chain risks.", 'Zkontrolujte závislosti balíčku pro potenciální rizika dodavatelského řetězce.')
        html = html.replace('License information not available.', 'Informace o licenci nejsou k dispozici.')
        html = html.replace('Open-source packages allow independent security review of the source code.', 'Open-source balíčky umožňují nezávislou bezpečnostní kontrolu zdrojového kódu.')
        html = html.replace('known vulnerabilities (CVEs) in the National Vulnerability Database', 'známé zranitelnosti (CVE) v National Vulnerability Database')
        html = html.replace('This is a clean record.', 'Jedná se o čistý záznam.')
        html = html.replace('Review advisories and update to the latest version.', 'Zkontrolujte bezpečnostní upozornění a aktualizujte na nejnovější verzi.')

        html = html.replace('and has not yet reached Nerq trust threshold (70+).', 'a dosud nedosáhl prahu důvěryhodnosti Nerq (70+).')
        html = html.replace('and meets Nerq trust threshold', 'a splňuje práh důvěryhodnosti Nerq')
        html = html.replace('This score is based on automated analysis of security, maintenance, community, and quality signals.', 'Toto skóre je založeno na automatizované analýze signálů bezpečnosti, údržby, komunity a kvality.')

        # 8. Methodology
        html = html.replace('using the same methodology, enabling direct cross-entity comparison', 'pomocí stejné metodologie, což umožňuje přímé srovnání mezi entitami')
        html = html.replace('Scores are updated continuously as new data becomes available', 'Skóre jsou průběžně aktualizována, jakmile jsou k dispozici nová data')
        html = html.replace('is computed from', 'je vypočítáno z')
        html = html.replace('The score reflects', 'Skóre odráží')
        html = html.replace('independent dimensions', 'nezávislých dimenzí')
        html = html.replace('Each dimension is weighted equally to produce the composite trust score.', 'Každá dimenze má stejnou váhu pro vytvoření souhrnného skóre důvěryhodnosti.')

        # 9. Key findings / signal descriptions
        html = html.replace('Composite trust score:', 'Souhrnné skóre důvěryhodnosti:')
        html = html.replace('across all available signals', 'ze všech dostupných signálů')
        html = html.replace('Code quality, vulnerability exposure, and security practices.', 'Kvalita kódu, expozice zranitelností a bezpečnostní postupy.')
        html = html.replace('Update frequency, issue responsiveness, active development.', 'Frekvence aktualizací, reakce na problémy, aktivní vývoj.')
        html = html.replace('README quality, API docs, usage examples.', 'Kvalita README, dokumentace API, příklady použití.')
        html = html.replace('Community adoption.', 'Přijetí komunitou.')
        html = html.replace('Composite score across all trust dimensions.', 'Souhrnné skóre ze všech dimenzí důvěryhodnosti.')

        # 10. FAQ answers
        html = html.replace('Yes, it is safe to use.', 'Ano, je bezpečný k použití.')
        html = html.replace('Use with some caution.', 'Používejte s opatrností.')
        html = html.replace('Exercise caution.', 'Buďte opatrní.')
        html = html.replace('Significant trust concerns.', 'Významné problémy s důvěryhodností.')
        html = html.replace('Strongest signal:', 'Nejsilnější signál:')
        html = html.replace('Score based on', 'Skóre založeno na')
        html = html.replace('multiple trust dimensions', 'více dimenzích důvěryhodnosti')
        html = html.replace('Scores update as new data becomes available.', 'Skóre se aktualizují, jakmile jsou k dispozici nová data.')
        html = html.replace('check back soon', 'zkuste to znovu brzy')
        html = html.replace('higher-rated alternatives include', 'lépe hodnocené alternativy zahrnují')
        html = html.replace('more Node.js packages are being analyzed', 'více balíčků Node.js je analyzováno')
        html = html.replace('more Python packages are being analyzed', 'více balíčků Pythonu je analyzováno')
        html = html.replace('Meets Nerq Verified threshold.', 'Splňuje ověřený práh Nerq.')

        # 11. Security check FAQ
        html = html.replace('Nerq checks', 'Nerq kontroluje')
        html = html.replace('against NVD, OSV.dev, and registry-specific vulnerability databases', 'oproti NVD, OSV.dev a databázím zranitelností specifickým pro registry')
        html = html.replace('Current security score:', 'Aktuální bezpečnostní skóre:')
        html = html.replace("Run your package manager's audit command for the latest findings.", 'Spusťte příkaz auditu vašeho správce balíčků pro nejnovější zjištění.')
        html = html.replace('has a trust score of', 'má skóre důvěryhodnosti')
        html = html.replace('has a Nerq Trust Score of', 'má skóre důvěryhodnosti Nerq')

        # 12. Footer bottom
        html = html.replace('trust scores for all software', 'skóre důvěryhodnosti pro veškerý software')
        html = html.replace('7.5M+ entities', '7,5M+ entit')
        html = html.replace('26 registries', '26 registrů')

        # 13. og:description
        html = html.replace('Independent safety assessment by Nerq.', 'Nezávislé hodnocení bezpečnosti od Nerq.')

        # 14. Breadcrumb in JSON-LD
        html = html.replace('"Safety Reports"', '"Bezpečnostní zprávy"')

        # 15. FAQ questions (in <summary> and JSON-LD)
        html = _re_t.sub(r"What is (.+?)'s trust score\?", r'Jaké je skóre důvěryhodnosti \1?', html)
        html = _re_t.sub(r"Co je (.+?)'s trust score\?", r'Jaké je skóre důvěryhodnosti \1?', html)
        html = _re_t.sub(r'Is (.+?) safe to use\?', r'Je \1 bezpečný k použití?', html)
        html = _re_t.sub(r'Is (.+?) safe\?', r'Je \1 bezpečný?', html)
        html = _re_t.sub(r'What are safer alternatives to (.+?)\?', r'Jaké jsou bezpečnější alternativy k \1?', html)
        html = _re_t.sub(r'Does (.+?) have known vulnerabilities\?', r'Má \1 známé zranitelnosti?', html)
        html = _re_t.sub(r'How actively maintained is (.+?)\?', r'Jak aktivně je \1 udržováno?', html)
        html = _re_t.sub(r'How does (.+?) compare to similar', r'Jak se \1 srovnává s podobnými', html)
        html = _re_t.sub(r'Can I use (.+?) in a regulated environment\?', r'Mohu použít \1 v regulovaném prostředí?', html)

        # 16. FAQ answer fragments
        html = html.replace('In the npm category,', 'V kategorii npm,')
        html = html.replace('In the pypi category,', 'V kategorii pypi,')
        html = html.replace('In the crates category,', 'V kategorii crates,')
        html = _re_t.sub(r'In the (\w+) category,', r'V kategorii \1,', html)
        html = _re_t.sub(r'(.+?) scores ([\d.]+)/100\.', r'\1 získal skóre \2/100.', html)

        # 17. "has a Trust Score of" in king sections
        html = _re_t.sub(r'(.+?) has a Trust Score of', r'\1 má skóre důvěryhodnosti', html)

        # 18. Security king section fragments
        html = html.replace('Security score:', 'Bezpečnostní skóre:')
        html = html.replace('Privacy score:', 'Skóre soukromí:')
        html = html.replace('to check for known vulnerabilities in your dependency tree', 'pro kontrolu známých zranitelností ve vašem stromu závislostí')

        # 19. Meta description
        html = html.replace('0 known vulnerabilities', '0 známých zranitelností')
        html = html.replace('License: See repository', 'Licence: Viz repozitář')
        html = html.replace('Independent security analysis of', 'Nezávislá bezpečnostní analýza')
        html = html.replace('trust signals, vulnerabilities, compliance, and safer alternatives', 'signály důvěryhodnosti, zranitelnosti, shoda a bezpečnější alternativy')

        # 20. og:description
        html = html.replace('Independent safety assessment by Nerq', 'Nezávislé hodnocení bezpečnosti od Nerq')
        html = html.replace('trust grade,', 'stupeň důvěryhodnosti,')

        # 21. Fix Schema.org @type that got wrongly translated by _CONTENT_TRANSLATIONS
        html = html.replace('"@type": "Recenze"', '"@type": "Review"')
        html = html.replace('"@type":"Recenze"', '"@type":"Review"')
        # reviewBody translation
        html = html.replace('with a Nerq Trust Score of', 'se skóre důvěryhodnosti Nerq')
        html = html.replace('Proceed with caution.', 'Postupujte opatrně.')
        html = html.replace('Not recommended.', 'Nedoporučeno.')
        # JSON-LD
        html = _re_t.sub(r'"name": "Is (.+?) Safe\?', r'"name": "Je \1 bezpečný?', html)
        html = _re_t.sub(r'"name": "Is (.+?) Safe to Visit\?', r'"name": "Je \1 bezpečné navštívit?', html)
        html = _re_t.sub(r'og:title" content="Is (.+?) Safe\?', r'og:title" content="Je \1 bezpečný?', html)
        html = _re_t.sub(r'nerq:question" content="Is (.+?) safe', r'nerq:question" content="Je \1 bezpečné', html)

        # Fix 1: License
        html = html.replace('License: Not specified', 'Licence: Neuvedena')
        html = html.replace('License: See repository', 'Licence: Viz repozitář')
        # Fix 3: og:description
        html = html.replace('por Nerq', 'od Nerq')
        html = html.replace('oleh Nerq', 'od Nerq')
        html = html.replace('Independent safety assessment by Nerq', 'Nezávislé hodnocení bezpečnosti od Nerq')
        # Fix 4: Footer remaining English
        html = html.replace('dimensions. Data from', 'dimenzích. Data z')
        html = html.replace('Data from', 'Data z')

    elif lang == "da":
        import re as _re_t
        html = _re_t.sub(r'<title>Is (.+?) Safe\?', r'<title>Er \1 sikker?', html, count=1)
        html = html.replace('Independent Trust &amp; Security Analysis 2026 | Nerq', 'Uafhængig tillids- og sikkerhedsanalyse 2026 | Nerq')
        html = _re_t.sub(r'>Is (.+?) Safe\?<', r'>Er \1 sikker?<', html)
        html = _re_t.sub(r'>Is (.+?) safe\?<', r'>Er \1 sikker?<', html)
        html = _re_t.sub(r'>What data does (.+?) collect\?<', r'>Hvilke data indsamler \1?<', html)
        html = _re_t.sub(r'>Is (.+?) secure\?<', r'>Er \1 sikker?<', html)
        html = _re_t.sub(r'>(.+?) Across Platforms<', r'>\1 på andre platforme<', html)
        html = _re_t.sub(r'>Safety Guide: (.+?)<', r'>Sikkerhedsguide: \1<', html)
        html = _re_t.sub(r'>What is (.+?)\?<', r'>Hvad er \1?<', html)
        html = html.replace('>Details<', '>Detaljer<')
        html = _re_t.sub(r'>Is (.+?) Safe to Visit\?', r'>Er \1 sikker at besøge?', html)
        html = _re_t.sub(r'>Is (.+?) safe for solo travelers\?<', r'>Er \1 sikkert for solorejsende?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for women\?<', r'>Er \1 sikkert for kvinder?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for LGBTQ\+ travelers\?<', r'>Er \1 sikkert for LGBTQ+-rejsende?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for families\?<', r'>Er \1 sikkert for familier?<', html)
        html = _re_t.sub(r'>Is (.+?) safe to visit right now\?<', r'>Er \1 sikker at besøge lige nu?<', html)
        html = _re_t.sub(r'>Is tap water safe to drink in (.+?)\?<', r'>Er postevandet i \1 sikkert at drikke?<', html)
        html = _re_t.sub(r'>Do I need vaccinations for (.+?)\?<', r'>Har jeg brug for vaccinationer til \1?<', html)
        html = _re_t.sub(r'>What are safer alternatives to (.+?)\?<', r'>Hvad er sikrere alternativer til \1?<', html)
        html = _re_t.sub(r'>What are the side effects of (.+?)\?<', r'>Hvad er bivirkningerne ved \1?<', html)
        html = _re_t.sub(r'>Does (.+?) interact with medications\?<', r'>Interagerer \1 med medicin?<', html)
        html = _re_t.sub(r"(.+?)'s trust score of", r'tillidsscore for \1', html)
        html = _re_t.sub(r'Nerq of (\d)', r'Nerq på \1', html)
        html = html.replace('Trust Score Breakdown', 'Tillidsscore detaljer')
        html = html.replace('Trust Score', 'Tillidsscore')
        html = html.replace('Safety Score Breakdown', 'Sikkerhedsscore detaljer')
        html = html.replace('Safety Score', 'Sikkerhedsscore')
        html = html.replace('trust grade', 'tillidsgrad')
        html = html.replace('Trust Analysis 2026', 'Tillidsanalyse 2026')
        # Nav
        html = html.replace('>Search<', '>Søg<')
        html = html.replace('>Apps<', '>Apps<')
        html = html.replace('>Packages<', '>Pakker<')
        html = html.replace('>Extensions<', '>Udvidelser<')
        html = html.replace('>Websites<', '>Hjemmesider<')
        html = html.replace('>Travel<', '>Rejser<')
        html = html.replace('>Charities<', '>Velgørenhed<')
        html = html.replace('>Compare<', '>Sammenlign<')
        html = html.replace('>Resources<', '>Ressourcer<')
        html = html.replace('>About<', '>Om<')
        html = html.replace('>Check Safety<', '>Tjek sikkerhed<')
        html = html.replace('>Games<', '>Spil<')
        html = html.replace('>Countries<', '>Lande<')
        html = html.replace('>Check Website<', '>Tjek websted<')
        html = html.replace('>Safety Guides<', '>Sikkerhedsguider<')
        # Footer text
        html = html.replace('Trust scores for software, apps, websites, travel destinations, and charities', 'Tillidsscorer for software, apps, websteder, rejsedestinationer og velgørenhedsorganisationer')
        html = html.replace('20 languages', '20 sprog')
        html = html.replace('>Guides<', '>Guider<')
        html = html.replace('>Mobile Apps<', '>Mobilapps<')
        html = html.replace('>Trust Badges<', '>Tillids-badges<')
        html = html.replace('>VPNs<', '>VPN<')
        html = html.replace('7.5M+ entities from 26 registries. Independent. Data-driven.', '7,5 mio.+ enheder fra 26 registre. Uafhængig. Datadriven.')

        # ── Dynamic paragraph translations ──

        # 1. Verdict lead: "Yes, X is safe to use. X is a Y with a Nerq Trust Score of N/100 (G)"
        html = _re_t.sub(
            r'Yes, (.+?) is safe to use\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Ja, \1 er sikker at bruge. \1 er en \2 med en Nerq Tillidsscore på \3/100 (\4)', html)
        html = _re_t.sub(
            r'Use (.+?) with some caution\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Brug \1 med forsigtighed. \1 er en \2 med en Nerq Tillidsscore på \3/100 (\4)', html)
        html = _re_t.sub(
            r'Exercise caution with (.+?)\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Vær forsigtig med \1. \1 er en \2 med en Nerq Tillidsscore på \3/100 (\4)', html)

        # 2. Short answer box
        html = html.replace('<strong>YES</strong>', '<strong>JA</strong>')
        html = html.replace('<strong>CAUTION</strong>', '<strong>FORSIGTIGHED</strong>')
        html = html.replace('<strong>NO — USE WITH CAUTION</strong>', '<strong>NEJ — BRUG MED FORSIGTIGHED</strong>')

        # 3. Citation detail / verdict detail
        html = html.replace("It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption", 'Opfylder Nerqs tillidstærskel med stærke signaler inden for sikkerhed, vedligeholdelse og fællesskabsadoption')
        html = html.replace('It has moderate trust signals but shows some areas of concern that warrant attention', 'Har moderate tillidssignaler, men viser nogle bekymrende områder, der kræver opmærksomhed')
        html = html.replace('It has below-average trust signals with significant gaps in security, maintenance, or documentation', 'Har under gennemsnitlige tillidssignaler med betydelige huller i sikkerhed, vedligeholdelse eller dokumentation')
        html = html.replace('Recommended for production use', 'Anbefalet til produktionsbrug')
        html = html.replace('It is recommended for production use.', 'Anbefalet til produktionsbrug.')
        html = html.replace('review the full report below for specific considerations', 'gennemgå den fulde rapport nedenfor for specifikke overvejelser')
        html = html.replace('Suitable for development use', 'Egnet til udviklingsformål')
        html = html.replace('review security and maintenance signals before production deployment', 'gennemgå sikkerheds- og vedligeholdelsessignaler før produktionsimplementering')
        html = html.replace('Not recommended for production use without thorough manual review and additional security measures', 'Anbefales ikke til produktionsbrug uden grundig manuel gennemgang og yderligere sikkerhedsforanstaltninger')
        html = html.replace('It is below the recommended threshold of 70.', 'Det er under den anbefalede tærskel på 70.')

        # 4. "X is a Y — description"
        html = _re_t.sub(r'>(.+?) is a (Node\.js package|Python package|Rust crate|Chrome extension|WordPress plugin|VPN service|game|website|SaaS platform|Firefox extension|VS Code extension|iOS app|Android app) — ',
                         r'>\1 er en \2 — ', html)

        # 5. Entity type translations in body text
        html = html.replace('is a Node.js package', 'er en Node.js-pakke')
        html = html.replace('is a Python package', 'er en Python-pakke')
        html = html.replace('is a Rust crate', 'er en Rust-crate')
        html = html.replace('is a Chrome extension', 'er en Chrome-udvidelse')
        html = html.replace('is a WordPress plugin', 'er et WordPress-plugin')
        html = html.replace('is a VPN service', 'er en VPN-tjeneste')
        html = html.replace('is a iOS app', 'er en iOS-app')
        html = html.replace('is a Android app', 'er en Android-app')

        # 6. Safety guide text
        html = html.replace("to check for vulnerabilities. Review the package's GitHub repository for recent commits.", 'for at kontrollere for sårbarheder. Gennemgå pakkens GitHub-repositorium for seneste commits.')
        html = html.replace('You can also check the trust score via API:', 'Du kan også tjekke tillidsscoren via API:')
        html = html.replace('watch for:', 'hold øje med:')
        html = html.replace('dependency vulnerabilities, malicious packages, typosquatting', 'afhængighedssårbarheder, ondsindede pakker, typosquatting')
        html = html.replace("Run your package manager's audit command regularly.", 'Kør din pakkehåndterers auditkommando regelmæssigt.')
        html = html.replace('>Run <code>', '>Kør <code>')

        # 7. King sections — privacy/security
        html = _re_t.sub(r'(.+?) is a Node\.js package maintained by (.+?)\.', r'\1 er en Node.js-pakke vedligeholdt af \2.', html)
        html = _re_t.sub(r'(.+?) is a (.+?) maintained by (.+?)\.', r'\1 er en \2 vedligeholdt af \3.', html)
        html = html.replace(' maintained by ', ' vedligeholdt af ')
        html = html.replace('As a development package,', 'Som en udviklingspakke,')
        html = html.replace('does not directly collect end-user personal data', 'indsamler ikke direkte slutbrugerens personlige data')
        html = html.replace('However, applications built with it may collect data depending on implementation', 'Men applikationer bygget med den kan indsamle data afhængigt af implementering')
        html = html.replace("Review the package's dependencies for potential supply chain risks.", 'Gennemgå pakkens afhængigheder for potentielle forsyningskæderisici.')
        html = html.replace('License: Not specified', 'Licens: Ikke angivet')
        html = html.replace('License: See repository', 'Licens: Se repository')
        html = html.replace('License information not available.', 'Licensoplysninger ikke tilgængelige.')
        html = html.replace('Open-source packages allow independent security review of the source code.', 'Open source-pakker muliggør uafhængig sikkerhedsgennemgang af kildekoden.')
        html = html.replace('known vulnerabilities (CVEs) in the National Vulnerability Database', 'kendte sårbarheder (CVE) i National Vulnerability Database')
        html = html.replace('This is a clean record.', 'Dette er en ren journal.')
        html = html.replace('Review advisories and update to the latest version.', 'Gennemgå sikkerhedsadvarsler og opdater til den nyeste version.')

        html = html.replace('and has not yet reached Nerq trust threshold (70+).', 'og har endnu ikke nået Nerqs tillidstærskel (70+).')
        html = html.replace('and meets Nerq trust threshold', 'og opfylder Nerqs tillidstærskel')
        html = html.replace('This score is based on automated analysis of security, maintenance, community, and quality signals.', 'Denne score er baseret på automatiseret analyse af sikkerheds-, vedligeholdelses-, fællesskabs- og kvalitetssignaler.')

        # 8. Methodology
        html = html.replace('using the same methodology, enabling direct cross-entity comparison', 'med samme metodik, hvilket muliggør direkte sammenligning mellem enheder')
        html = html.replace('Scores are updated continuously as new data becomes available', 'Scorer opdateres løbende, efterhånden som nye data bliver tilgængelige')
        html = html.replace('is computed from', 'beregnes ud fra')
        html = html.replace('The score reflects', 'Scoren afspejler')
        html = html.replace('independent dimensions', 'uafhængige dimensioner')
        html = html.replace('Each dimension is weighted equally to produce the composite trust score.', 'Hver dimension vægtes ens for at producere den samlede tillidsscore.')

        # 9. Key findings / signal descriptions
        html = html.replace('Composite trust score:', 'Samlet tillidsscore:')
        html = html.replace('across all available signals', 'på tværs af alle tilgængelige signaler')
        html = html.replace('Code quality, vulnerability exposure, and security practices.', 'Kodekvalitet, sårbarhedseksponering og sikkerhedspraksis.')
        html = html.replace('Update frequency, issue responsiveness, active development.', 'Opdateringsfrekvens, responsivitet over for problemer, aktiv udvikling.')
        html = html.replace('README quality, API docs, usage examples.', 'README-kvalitet, API-dokumentation, eksempler på brug.')
        html = html.replace('Community adoption.', 'Fællesskabsadoption.')
        html = html.replace('Composite score across all trust dimensions.', 'Samlet score på tværs af alle tillidsdimensioner.')

        # 10. FAQ answers — ALL FAQ patterns FIRST
        html = _re_t.sub(r"What is (.+?)'s trust score\?", r'Hvad er tillidsscoren for \1?', html)
        html = _re_t.sub(r"Hvad er (.+?)'s trust score\?", r'Hvad er tillidsscoren for \1?', html)  # catch post-translated
        html = _re_t.sub(r'Is (.+?) safe to use\?', r'Er \1 sikker at bruge?', html)
        html = _re_t.sub(r'Is (.+?) safe\?', r'Er \1 sikker?', html)
        html = _re_t.sub(r'What are safer alternatives to (.+?)\?', r'Hvad er sikrere alternativer til \1?', html)
        html = _re_t.sub(r'Does (.+?) have known vulnerabilities\?', r'Har \1 kendte sårbarheder?', html)
        html = _re_t.sub(r'How actively maintained is (.+?)\?', r'Hvor aktivt vedligeholdes \1?', html)
        html = _re_t.sub(r'How does (.+?) compare to similar', r'Hvordan sammenligner \1 sig med lignende', html)
        html = _re_t.sub(r'Can I use (.+?) in a regulated environment\?', r'Kan jeg bruge \1 i et reguleret miljø?', html)

        # 11. "known vulnerabilities" replacement (AFTER FAQ patterns)
        html = html.replace('0 known vulnerabilities', '0 kendte sårbarheder')

        # 12. FAQ answer text
        html = html.replace('Yes, it is safe to use.', 'Ja, det er sikkert at bruge.')
        html = html.replace('Use with some caution.', 'Brug med forsigtighed.')
        html = html.replace('Exercise caution.', 'Vær forsigtig.')
        html = html.replace('Significant trust concerns.', 'Betydelige tillidsproblemer.')
        html = html.replace('Strongest signal:', 'Stærkeste signal:')
        html = html.replace('Score based on', 'Score baseret på')
        html = html.replace('multiple trust dimensions', 'flere tillidsdimensioner')
        html = html.replace('Scores update as new data becomes available.', 'Scorer opdateres, efterhånden som nye data bliver tilgængelige.')
        html = html.replace('check back soon', 'kom snart tilbage')
        html = html.replace('higher-rated alternatives include', 'højere rangerede alternativer inkluderer')
        html = html.replace('more Node.js packages are being analyzed', 'flere Node.js-pakker analyseres')
        html = html.replace('more Python packages are being analyzed', 'flere Python-pakker analyseres')
        html = html.replace('Meets Nerq Verified threshold.', 'Opfylder Nerqs verificerede tærskel.')

        # 13. Security check FAQ
        html = html.replace('Nerq checks', 'Nerq kontrollerer')
        html = html.replace('against NVD, OSV.dev, and registry-specific vulnerability databases', 'mod NVD, OSV.dev og registrespecifikke sårbarhedsdatabaser')
        html = html.replace('Current security score:', 'Aktuel sikkerhedsscore:')
        html = html.replace("Run your package manager's audit command for the latest findings.", 'Kør din pakkehåndterers auditkommando for de seneste fund.')
        html = html.replace('has a Nerq Trust Score of', 'har en Nerq Tillidsscore på')
        html = html.replace('has a trust score of', 'har en tillidsscore på')

        # 14. Footer bottom
        html = html.replace('trust scores for all software', 'tillidsscorer for al software')
        html = html.replace('7.5M+ entities', '7,5 mio.+ enheder')
        html = html.replace('26 registries', '26 registre')

        # 15. og:description fix — replace other-language suffixes → "af Nerq"
        html = html.replace('por Nerq', 'af Nerq')
        html = html.replace('oleh Nerq', 'af Nerq')
        html = html.replace('od Nerq', 'af Nerq')
        html = html.replace('Independent safety assessment by Nerq.', 'Uafhængig sikkerhedsvurdering af Nerq.')
        html = html.replace('Independent safety assessment by Nerq', 'Uafhængig sikkerhedsvurdering af Nerq')

        # 16. Breadcrumb in JSON-LD
        html = html.replace('"Safety Reports"', '"Sikkerhedsrapporter"')

        # 17. Meta description fragments
        html = html.replace('Independent security analysis of', 'Uafhængig sikkerhedsanalyse af')
        html = html.replace('License: See repository', 'Licens: Se repositorium')
        html = html.replace('trust signals, vulnerabilities, compliance, and safer alternatives', 'tillidssignaler, sårbarheder, overholdelse og sikrere alternativer')

        # 18. "has a Trust Score of" in king sections
        html = _re_t.sub(r'(.+?) has a Trust Score of', r'\1 har en Tillidsscore på', html)

        # 19. Security king section fragments
        html = html.replace('Security score:', 'Sikkerhedsscore:')
        html = html.replace('Privacy score:', 'Privatlivsscore:')
        html = html.replace('to check for known vulnerabilities in your dependency tree', 'for at kontrollere for kendte sårbarheder i dit afhængighedstræ')

        # 20. FAQ answer fragments
        html = html.replace('In the npm category,', 'I npm-kategorien,')
        html = html.replace('In the pypi category,', 'I pypi-kategorien,')
        html = html.replace('In the crates category,', 'I crates-kategorien,')
        html = _re_t.sub(r'In the (\w+) category,', r'I \1-kategorien,', html)
        html = _re_t.sub(r'(.+?) scores ([\d.]+)/100\.', r'\1 scorer \2/100.', html)

        # 21. Fix Schema.org @type that got wrongly translated by _CONTENT_TRANSLATIONS
        # Schema.org requires English @type values
        html = html.replace('"@type": "Anmeldelse"', '"@type": "Review"')
        html = html.replace('"@type":"Anmeldelse"', '"@type":"Review"')
        # reviewBody translation
        html = html.replace('with a Nerq Trust Score of', 'med en Nerq Tillidsscore på')
        html = html.replace('Proceed with caution.', 'Fortsæt med forsigtighed.')
        html = html.replace('Not recommended.', 'Anbefales ikke.')
        # JSON-LD
        html = _re_t.sub(r'"name": "Is (.+?) Safe\?', r'"name": "Er \1 sikker?', html)
        html = _re_t.sub(r'"name": "Is (.+?) Safe to Visit\?', r'"name": "Er \1 sikker at besøge?', html)
        html = _re_t.sub(r'og:title" content="Is (.+?) Safe\?', r'og:title" content="Er \1 sikker?', html)
        html = _re_t.sub(r'nerq:question" content="Is (.+?) safe', r'nerq:question" content="Er \1 sikker', html)

    elif lang == "no":
        import re as _re_t
        html = _re_t.sub(r'<title>Is (.+?) Safe\?', r'<title>Er \1 trygt?', html, count=1)
        html = html.replace('Independent Trust &amp; Security Analysis 2026 | Nerq', 'Uavhengig tillits- og sikkerhetsanalyse 2026 | Nerq')
        # Meta description
        html = html.replace('has a Nerq Trust Score of', 'har en Nerq-tillitspoeng på')
        html = html.replace('known vulnerabilities', 'kjente sårbarheter')
        html = html.replace('License:', 'Lisens:')
        html = html.replace('Not specified', 'Ikke spesifisert')
        html = html.replace('Independent security analysis of', 'Uavhengig sikkerhetsanalyse av')
        html = html.replace('trust signals, vulnerabilities, compliance, and safer alternatives', 'tillitssignaler, sårbarheter, samsvar og tryggere alternativer')
        html = _re_t.sub(r'>Is (.+?) Safe\?<', r'>Er \1 trygt?<', html)
        html = _re_t.sub(r'>Is (.+?) safe\?<', r'>Er \1 trygt?<', html)
        html = _re_t.sub(r'>What data does (.+?) collect\?<', r'>Hvilke data samler \1 inn?<', html)
        html = _re_t.sub(r'>Is (.+?) secure\?<', r'>Er \1 sikkert?<', html)
        html = _re_t.sub(r'>(.+?) Across Platforms<', r'>\1 på andre plattformer<', html)
        html = _re_t.sub(r'>Safety Guide: (.+?)<', r'>Sikkerhetsguide: \1<', html)
        html = _re_t.sub(r'>What is (.+?)\?<', r'>Hva er \1?<', html)
        html = html.replace('>Details<', '>Detaljer<')
        html = _re_t.sub(r'>Is (.+?) Safe to Visit\?', r'>Er \1 trygt å besøke?', html)
        html = _re_t.sub(r'>Is (.+?) safe for solo travelers\?<', r'>Er \1 trygt for soloeinreisende?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for women\?<', r'>Er \1 trygt for kvinner?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for LGBTQ\+ travelers\?<', r'>Er \1 trygt for LGBTQ+-reisende?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for families\?<', r'>Er \1 trygt for familier?<', html)
        html = _re_t.sub(r'>Is (.+?) safe to visit right now\?<', r'>Er \1 trygt å besøke akkurat nå?<', html)
        html = _re_t.sub(r'>Is tap water safe to drink in (.+?)\?<', r'>Er kranvannet i \1 trygt å drikke?<', html)
        html = _re_t.sub(r'>Do I need vaccinations for (.+?)\?<', r'>Trenger jeg vaksiner for \1?<', html)
        html = _re_t.sub(r'>What are safer alternatives to (.+?)\?<', r'>Hva er tryggere alternativer til \1?<', html)
        html = _re_t.sub(r'>What are the side effects of (.+?)\?<', r'>Hva er bivirkningene av \1?<', html)
        html = _re_t.sub(r'>Does (.+?) interact with medications\?<', r'>Interagerer \1 med medisiner?<', html)
        html = _re_t.sub(r"(.+?)'s trust score of", r'tillitspoeng for \1', html)
        html = _re_t.sub(r'Nerq of (\d)', r'Nerq på \1', html)
        html = html.replace('Trust Score Breakdown', 'Tillitspoeng detaljer')
        html = html.replace('Trust Score', 'Tillitspoeng')
        html = html.replace('Safety Score Breakdown', 'Sikkerhetspoeng detaljer')
        html = html.replace('Safety Score', 'Sikkerhetspoeng')
        html = html.replace('trust grade', 'tillitsgrad')
        html = html.replace('Trust Analysis 2026', 'Tillitsanalyse 2026')
        # Nav
        html = html.replace('>Search<', '>Søk<')
        html = html.replace('>Apps<', '>Apper<')
        html = html.replace('>Packages<', '>Pakker<')
        html = html.replace('>Extensions<', '>Utvidelser<')
        html = html.replace('>Websites<', '>Nettsteder<')
        html = html.replace('>Travel<', '>Reise<')
        html = html.replace('>Charities<', '>Veldedighet<')
        html = html.replace('>Compare<', '>Sammenlign<')
        html = html.replace('>Resources<', '>Ressurser<')
        html = html.replace('>About<', '>Om<')
        html = html.replace('>Check Safety<', '>Sjekk sikkerhet<')
        html = html.replace('>Games<', '>Spill<')
        html = html.replace('>Countries<', '>Land<')
        html = html.replace('>Check Website<', '>Sjekk nettsted<')
        html = html.replace('>Safety Guides<', '>Sikkerhetsguider<')
        # Footer text
        html = html.replace('Trust scores for software, apps, websites, travel destinations, and charities', 'Tillitspoeng for programvare, apper, nettsteder, reisemål og veldedighetsorganisasjoner')
        html = html.replace('20 languages', '20 språk')
        html = html.replace('>Guides<', '>Guider<')
        html = html.replace('>Mobile Apps<', '>Mobilapper<')
        html = html.replace('>Trust Badges<', '>Tillitsmerker<')
        html = html.replace('>VPNs<', '>VPN<')
        html = html.replace('7.5M+ entities from 26 registries. Independent. Data-driven.', '7,5 mill.+ enheter fra 26 registre. Uavhengig. Datadrevet.')

        # ── Dynamic paragraph translations ──

        # 1. Verdict lead
        html = _re_t.sub(
            r'Yes, (.+?) is safe to use\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Ja, \1 er trygt å bruke. \1 er en \2 med en Nerq Tillitspoeng på \3/100 (\4)', html)
        html = _re_t.sub(
            r'Use (.+?) with some caution\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Bruk \1 med forsiktighet. \1 er en \2 med en Nerq Tillitspoeng på \3/100 (\4)', html)
        html = _re_t.sub(
            r'Exercise caution with (.+?)\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Vær forsiktig med \1. \1 er en \2 med en Nerq Tillitspoeng på \3/100 (\4)', html)

        # 2. Short answer box
        html = html.replace('<strong>YES</strong>', '<strong>JA</strong>')
        html = html.replace('<strong>CAUTION</strong>', '<strong>FORSIKTIGHET</strong>')
        html = html.replace('<strong>NO — USE WITH CAUTION</strong>', '<strong>NEI — BRUK MED FORSIKTIGHET</strong>')

        # 3. Citation detail / verdict detail
        html = html.replace("It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption", 'Oppfyller Nerqs tillitsterskel med sterke signaler innen sikkerhet, vedlikehold og fellesskapsadopsjon')
        html = html.replace('It has moderate trust signals but shows some areas of concern that warrant attention', 'Har moderate tillitstignaler, men viser noen bekymringsområder som krever oppmerksomhet')
        html = html.replace('It has below-average trust signals with significant gaps in security, maintenance, or documentation', 'Har under gjennomsnittlige tillitstignaler med betydelige hull i sikkerhet, vedlikehold eller dokumentasjon')
        html = html.replace('Recommended for production use', 'Anbefalt for produksjonsbruk')
        html = html.replace('It is recommended for production use.', 'Anbefalt for produksjonsbruk.')
        html = html.replace('review the full report below for specific considerations', 'gjennomgå den fullstendige rapporten nedenfor for spesifikke hensyn')
        html = html.replace('Suitable for development use', 'Egnet for utviklingsformål')
        html = html.replace('review security and maintenance signals before production deployment', 'gjennomgå sikkerhets- og vedlikeholdssignaler før produksjonsimplementering')
        html = html.replace('Not recommended for production use without thorough manual review and additional security measures', 'Anbefales ikke for produksjonsbruk uten grundig manuell gjennomgang og ytterligere sikkerhetstiltak')
        html = html.replace('It is below the recommended threshold of 70.', 'Den er under den anbefalte terskelen på 70.')

        # 4. "X is a Y — description"
        html = _re_t.sub(r'>(.+?) is a (Node\.js package|Python package|Rust crate|Chrome extension|WordPress plugin|VPN service|game|website|SaaS platform|Firefox extension|VS Code extension|iOS app|Android app) — ',
                         r'>\1 er en \2 — ', html)

        # 5. Entity type translations in body text
        html = html.replace('is a Node.js package', 'er en Node.js-pakke')
        html = html.replace('is a Python package', 'er en Python-pakke')
        html = html.replace('is a Rust crate', 'er en Rust-crate')
        html = html.replace('is a Chrome extension', 'er en Chrome-utvidelse')
        html = html.replace('is a WordPress plugin', 'er en WordPress-plugin')
        html = html.replace('is a VPN service', 'er en VPN-tjeneste')
        html = html.replace('is a iOS app', 'er en iOS-app')
        html = html.replace('is a Android app', 'er en Android-app')

        # 6. Safety guide text
        html = html.replace("to check for vulnerabilities. Review the package's GitHub repository for recent commits.", 'for å sjekke for sårbarheter. Gjennomgå pakkens GitHub-repositorium for nylige commits.')
        html = html.replace('You can also check the trust score via API:', 'Du kan også sjekke tillitspoengene via API:')
        html = html.replace('watch for:', 'se opp for:')
        html = html.replace('dependency vulnerabilities, malicious packages, typosquatting', 'avhengighetssårbarheter, ondsinnede pakker, typosquatting')
        html = html.replace("Run your package manager's audit command regularly.", 'Kjør pakkehåndtererens auditkommando jevnlig.')
        html = html.replace('>Run <code>', '>Kjør <code>')

        # 7. King sections — privacy/security
        html = _re_t.sub(r'(.+?) is a Node\.js package maintained by (.+?)\.', r'\1 er en Node.js-pakke vedlikeholdt av \2.', html)
        html = _re_t.sub(r'(.+?) is a (.+?) maintained by (.+?)\.', r'\1 er en \2 vedlikeholdt av \3.', html)
        html = html.replace(' maintained by ', ' vedlikeholdt av ')
        html = html.replace('As a development package,', 'Som en utviklingspakke,')
        html = html.replace('does not directly collect end-user personal data', 'samler ikke inn sluttbrukerens personlige data direkte')
        html = html.replace('However, applications built with it may collect data depending on implementation', 'Men applikasjoner bygget med den kan samle inn data avhengig av implementering')
        html = html.replace("Review the package's dependencies for potential supply chain risks.", 'Gjennomgå pakkens avhengigheter for potensielle forsyningskjederisikoer.')
        html = html.replace('License: Not specified', 'Lisens: Ikke oppgitt')
        html = html.replace('License: See repository', 'Lisens: Se repositorium')
        html = html.replace('License information not available.', 'Lisensinformasjon ikke tilgjengelig.')
        html = html.replace('Open-source packages allow independent security review of the source code.', 'Åpen kildekode-pakker muliggjør uavhengig sikkerhetsgjennomgang av kildekoden.')
        html = html.replace('known vulnerabilities (CVEs) in the National Vulnerability Database', 'kjente sårbarheter (CVE) i National Vulnerability Database')
        html = html.replace('This is a clean record.', 'Dette er en ren journal.')
        html = html.replace('Review advisories and update to the latest version.', 'Gjennomgå sikkerhetsadvarsler og oppdater til nyeste versjon.')

        html = html.replace('and has not yet reached Nerq trust threshold (70+).', 'og har ennå ikke nådd Nerqs tillitsterskel (70+).')
        html = html.replace('and meets Nerq trust threshold', 'og oppfyller Nerqs tillitsterskel')
        html = html.replace('This score is based on automated analysis of security, maintenance, community, and quality signals.', 'Denne poengsummen er basert på automatisert analyse av sikkerhets-, vedlikeholds-, fellesskaps- og kvalitetssignaler.')

        # 8. Methodology
        html = html.replace('using the same methodology, enabling direct cross-entity comparison', 'med samme metodikk, noe som muliggjør direkte sammenligning mellom enheter')
        html = html.replace('Scores are updated continuously as new data becomes available', 'Poeng oppdateres fortløpende etter hvert som nye data blir tilgjengelige')
        html = html.replace('is computed from', 'beregnes ut fra')
        html = html.replace('The score reflects', 'Poengsummen gjenspeiler')
        html = html.replace('independent dimensions', 'uavhengige dimensjoner')
        html = html.replace('Each dimension is weighted equally to produce the composite trust score.', 'Hver dimensjon vektes likt for å produsere den samlede tillitspoengene.')

        # 9. Key findings / signal descriptions
        html = html.replace('Composite trust score:', 'Samlet tillitspoeng:')
        html = html.replace('across all available signals', 'på tvers av alle tilgjengelige signaler')
        html = html.replace('Code quality, vulnerability exposure, and security practices.', 'Kodekvalitet, sårbarhetsseksponering og sikkerhetspraksis.')
        html = html.replace('Update frequency, issue responsiveness, active development.', 'Oppdateringsfrekvens, responsivitet overfor problemer, aktiv utvikling.')
        html = html.replace('README quality, API docs, usage examples.', 'README-kvalitet, API-dokumentasjon, brukseksempler.')
        html = html.replace('Community adoption.', 'Fellesskapsadopsjon.')
        html = html.replace('Composite score across all trust dimensions.', 'Samlet poengsum på tvers av alle tillitsdimensjoner.')

        # 10. FAQ answers
        html = _re_t.sub(r"What is (.+?)'s trust score\?", r'Hva er tillitspoengene for \1?', html)
        html = _re_t.sub(r"Hva er (.+?)'s trust score\?", r'Hva er tillitspoengene for \1?', html)
        html = _re_t.sub(r'Is (.+?) safe to use\?', r'Er \1 trygt å bruke?', html)
        html = _re_t.sub(r'Is (.+?) safe\?', r'Er \1 trygt?', html)
        html = _re_t.sub(r'What are safer alternatives to (.+?)\?', r'Hva er tryggere alternativer til \1?', html)
        html = _re_t.sub(r'Does (.+?) have known vulnerabilities\?', r'Har \1 kjente sårbarheter?', html)
        html = _re_t.sub(r'How actively maintained is (.+?)\?', r'Hvor aktivt vedlikeholdes \1?', html)
        html = _re_t.sub(r'How does (.+?) compare to similar', r'Hvordan sammenligner \1 seg med lignende', html)
        html = _re_t.sub(r'Can I use (.+?) in a regulated environment\?', r'Kan jeg bruke \1 i et regulert miljø?', html)

        # 11. "known vulnerabilities" replacement (AFTER FAQ patterns)
        html = html.replace('0 known vulnerabilities', '0 kjente sårbarheter')

        # 12. FAQ answer text
        html = html.replace('Yes, it is safe to use.', 'Ja, det er trygt å bruke.')
        html = html.replace('Use with some caution.', 'Bruk med forsiktighet.')
        html = html.replace('Exercise caution.', 'Vær forsiktig.')
        html = html.replace('Significant trust concerns.', 'Betydelige tillitsproblemer.')
        html = html.replace('Strongest signal:', 'Sterkeste signal:')
        html = html.replace('Score based on', 'Poengsum basert på')
        html = html.replace('multiple trust dimensions', 'flere tillitsdimensjoner')
        html = html.replace('Scores update as new data becomes available.', 'Poeng oppdateres etter hvert som nye data blir tilgjengelige.')
        html = html.replace('check back soon', 'kom tilbake snart')
        html = html.replace('higher-rated alternatives include', 'høyere rangerte alternativer inkluderer')
        html = html.replace('more Node.js packages are being analyzed', 'flere Node.js-pakker analyseres')
        html = html.replace('more Python packages are being analyzed', 'flere Python-pakker analyseres')
        html = html.replace('Meets Nerq Verified threshold.', 'Oppfyller Nerqs verifiserte terskel.')

        # 13. Security check FAQ
        html = html.replace('Nerq checks', 'Nerq sjekker')
        html = html.replace('against NVD, OSV.dev, and registry-specific vulnerability databases', 'mot NVD, OSV.dev og registerspesifikke sårbarhetsdatabaser')
        html = html.replace('Current security score:', 'Gjeldende sikkerhetspoeng:')
        html = html.replace("Run your package manager's audit command for the latest findings.", 'Kjør pakkehåndtererens auditkommando for de siste funnene.')
        html = html.replace('has a Nerq Trust Score of', 'har en Nerq Tillitspoeng på')
        html = html.replace('has a trust score of', 'har en tillitspoeng på')

        # 14. Footer bottom
        html = html.replace('trust scores for all software', 'tillitspoeng for all programvare')
        html = html.replace('7.5M+ entities', '7,5 mill.+ enheter')
        html = html.replace('26 registries', '26 registre')

        # 15. og:description fix
        html = html.replace('por Nerq', 'av Nerq')
        html = html.replace('oleh Nerq', 'av Nerq')
        html = html.replace('od Nerq', 'av Nerq')
        html = html.replace('Independent safety assessment by Nerq.', 'Uavhengig sikkerhetsvurdering av Nerq.')
        html = html.replace('Independent safety assessment by Nerq', 'Uavhengig sikkerhetsvurdering av Nerq')

        # 16. Breadcrumb in JSON-LD
        html = html.replace('"Safety Reports"', '"Sikkerhetsrapporter"')

        # 17. Meta description fragments
        html = html.replace('Independent security analysis of', 'Uavhengig sikkerhetsanalyse av')
        html = html.replace('License: See repository', 'Lisens: Se repositorium')
        html = html.replace('trust signals, vulnerabilities, compliance, and safer alternatives', 'tillitstignaler, sårbarheter, samsvar og tryggere alternativer')

        # 18. "has a Trust Score of" in king sections
        html = _re_t.sub(r'(.+?) has a Trust Score of', r'\1 har en Tillitspoeng på', html)

        # 19. Security king section fragments
        html = html.replace('Security score:', 'Sikkerhetspoeng:')
        html = html.replace('Privacy score:', 'Personvernpoeng:')
        html = html.replace('to check for known vulnerabilities in your dependency tree', 'for å sjekke for kjente sårbarheter i avhengighetstreet ditt')

        # 20. FAQ answer fragments
        html = html.replace('In the npm category,', 'I npm-kategorien,')
        html = html.replace('In the pypi category,', 'I pypi-kategorien,')
        html = html.replace('In the crates category,', 'I crates-kategorien,')
        html = _re_t.sub(r'In the (\w+) category,', r'I \1-kategorien,', html)
        html = _re_t.sub(r'(.+?) scores ([\d.]+)/100\.', r'\1 scorer \2/100.', html)

        # 21. Fix Schema.org @type
        html = html.replace('"@type": "Anmeldelse"', '"@type": "Review"')
        html = html.replace('"@type":"Anmeldelse"', '"@type":"Review"')
        # reviewBody translation
        html = html.replace('with a Nerq Trust Score of', 'med en Nerq Tillitspoeng på')
        html = html.replace('Proceed with caution.', 'Fortsett med forsiktighet.')
        html = html.replace('Not recommended.', 'Anbefales ikke.')
        # JSON-LD
        html = _re_t.sub(r'"name": "Is (.+?) Safe\?', r'"name": "Er \1 trygt?', html)
        html = _re_t.sub(r'"name": "Is (.+?) Safe to Visit\?', r'"name": "Er \1 trygt å besøke?', html)
        html = _re_t.sub(r'og:title" content="Is (.+?) Safe\?', r'og:title" content="Er \1 trygt?', html)
        html = _re_t.sub(r'nerq:question" content="Is (.+?) safe', r'nerq:question" content="Er \1 trygt', html)

    elif lang == "th":
        import re as _re_t
        html = _re_t.sub(r'<title>Is (.+?) Safe\?', r'<title>\1 ปลอดภัยหรือไม่?', html, count=1)
        html = html.replace('Independent Trust &amp; Security Analysis 2026 | Nerq', 'การวิเคราะห์ความน่าเชื่อถือและความปลอดภัยอิสระ 2026 | Nerq')
        html = _re_t.sub(r'>Is (.+?) Safe\?<', r'>\1 ปลอดภัยหรือไม่?<', html)
        html = _re_t.sub(r'>Is (.+?) safe\?<', r'>\1 ปลอดภัยหรือไม่?<', html)
        html = _re_t.sub(r'>What data does (.+?) collect\?<', r'>\1 เก็บข้อมูลอะไรบ้าง?<', html)
        html = _re_t.sub(r'>Is (.+?) secure\?<', r'>\1 ปลอดภัยหรือไม่?<', html)
        html = _re_t.sub(r'>(.+?) Across Platforms<', r'>\1 บนแพลตฟอร์มอื่น<', html)
        html = _re_t.sub(r'>Safety Guide: (.+?)<', r'>คู่มือความปลอดภัย: \1<', html)
        html = _re_t.sub(r'>What is (.+?)\?<', r'>\1 คืออะไร?<', html)
        html = html.replace('>Details<', '>รายละเอียด<')
        html = _re_t.sub(r'>Is (.+?) Safe to Visit\?', r'>\1 ปลอดภัยที่จะเยี่ยมชมหรือไม่?', html)
        html = _re_t.sub(r'>Is (.+?) safe for solo travelers\?<', r'>\1 ปลอดภัยสำหรับนักท่องเที่ยวเดี่ยวหรือไม่?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for women\?<', r'>\1 ปลอดภัยสำหรับผู้หญิงหรือไม่?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for LGBTQ\+ travelers\?<', r'>\1 ปลอดภัยสำหรับนักท่องเที่ยว LGBTQ+ หรือไม่?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for families\?<', r'>\1 ปลอดภัยสำหรับครอบครัวหรือไม่?<', html)
        html = _re_t.sub(r'>Is (.+?) safe to visit right now\?<', r'>\1 ปลอดภัยที่จะเยี่ยมชมตอนนี้หรือไม่?<', html)
        html = _re_t.sub(r'>Is tap water safe to drink in (.+?)\?<', r'>น้ำประปาใน \1 ปลอดภัยที่จะดื่มหรือไม่?<', html)
        html = _re_t.sub(r'>Do I need vaccinations for (.+?)\?<', r'>ฉันต้องฉีดวัคซีนสำหรับ \1 หรือไม่?<', html)
        html = _re_t.sub(r'>What are safer alternatives to (.+?)\?<', r'>ทางเลือกที่ปลอดภัยกว่า \1 มีอะไรบ้าง?<', html)
        html = _re_t.sub(r'>What are the side effects of (.+?)\?<', r'>ผลข้างเคียงของ \1 มีอะไรบ้าง?<', html)
        html = _re_t.sub(r'>Does (.+?) interact with medications\?<', r'>\1 มีปฏิกิริยากับยาหรือไม่?<', html)
        html = _re_t.sub(r"(.+?)'s trust score of", r'คะแนนความน่าเชื่อถือของ \1', html)
        html = _re_t.sub(r'Nerq of (\d)', r'Nerq \1', html)
        html = html.replace('Safety Score', 'คะแนนความปลอดภัย')
        html = html.replace('Trust Analysis 2026', 'การวิเคราะห์ความน่าเชื่อถือ 2026')
        # Nav
        html = html.replace('>Search<', '>ค้นหา<')
        html = html.replace('>Apps<', '>แอป<')
        html = html.replace('>Packages<', '>แพ็คเกจ<')
        html = html.replace('>Extensions<', '>ส่วนขยาย<')
        html = html.replace('>Websites<', '>เว็บไซต์<')
        html = html.replace('>Travel<', '>ท่องเที่ยว<')
        html = html.replace('>Charities<', '>การกุศล<')
        html = html.replace('>Compare<', '>เปรียบเทียบ<')
        html = html.replace('>Resources<', '>ทรัพยากร<')
        html = html.replace('>About<', '>เกี่ยวกับ<')
        html = html.replace('>Check Safety<', '>ตรวจสอบความปลอดภัย<')
        html = html.replace('>Games<', '>เกม<')
        html = html.replace('>Countries<', '>ประเทศ<')
        html = html.replace('>Check Website<', '>ตรวจสอบเว็บไซต์<')
        html = html.replace('>Safety Guides<', '>คู่มือความปลอดภัย<')
        # Footer text
        html = html.replace('Trust scores for software, apps, websites, travel destinations, and charities', 'คะแนนความน่าเชื่อถือสำหรับซอฟต์แวร์ แอป เว็บไซต์ จุดหมายท่องเที่ยว และองค์กรการกุศล')
        html = html.replace('20 languages', '20 ภาษา')
        html = html.replace('>Guides<', '>คู่มือ<')
        html = html.replace('>Mobile Apps<', '>แอปมือถือ<')
        html = html.replace('>Trust Badges<', '>ตราความน่าเชื่อถือ<')
        html = html.replace('>VPNs<', '>VPN<')
        html = html.replace('7.5M+ entities from 26 registries. Independent. Data-driven.', '7.5 ล้าน+ เอนทิตีจาก 26 registry อิสระ อิงข้อมูล')

        # ── Dynamic paragraph translations ──

        # 1. Verdict lead
        html = _re_t.sub(
            r'Yes, (.+?) is safe to use\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'ใช่ \1 ปลอดภัยที่จะใช้งาน \1 เป็น \2 ด้วยคะแนนความน่าเชื่อถือ Nerq \3/100 (\4)', html)
        html = _re_t.sub(
            r'Use (.+?) with some caution\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'ใช้ \1 ด้วยความระมัดระวัง \1 เป็น \2 ด้วยคะแนนความน่าเชื่อถือ Nerq \3/100 (\4)', html)
        html = _re_t.sub(
            r'Exercise caution with (.+?)\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'ควรระวังกับ \1 \1 เป็น \2 ด้วยคะแนนความน่าเชื่อถือ Nerq \3/100 (\4)', html)

        # 2. Short answer box
        html = html.replace('<strong>YES</strong>', '<strong>ใช่</strong>')
        html = html.replace('<strong>CAUTION</strong>', '<strong>ระวัง</strong>')
        html = html.replace('<strong>NO — USE WITH CAUTION</strong>', '<strong>ไม่ — ใช้ด้วยความระมัดระวัง</strong>')

        # 3. Citation detail / verdict detail
        html = html.replace("It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption", 'ผ่านเกณฑ์ความน่าเชื่อถือของ Nerq ด้วยสัญญาณที่แข็งแกร่งในด้านความปลอดภัย การบำรุงรักษา และการยอมรับจากชุมชน')
        html = html.replace('It has moderate trust signals but shows some areas of concern that warrant attention', 'มีสัญญาณความน่าเชื่อถือปานกลางแต่พบบางประเด็นที่ต้องใส่ใจ')
        html = html.replace('It has below-average trust signals with significant gaps in security, maintenance, or documentation', 'มีสัญญาณความน่าเชื่อถือต่ำกว่าค่าเฉลี่ยและมีช่องว่างที่สำคัญในด้านความปลอดภัย การบำรุงรักษา หรือเอกสาร')
        html = html.replace('Recommended for production use', 'แนะนำสำหรับการใช้งานจริง')
        html = html.replace('It is recommended for production use.', 'แนะนำสำหรับการใช้งานจริง')
        html = html.replace('review the full report below for specific considerations', 'ดูรายงานฉบับเต็มด้านล่างสำหรับข้อพิจารณาเฉพาะ')
        html = html.replace('Suitable for development use', 'เหมาะสำหรับการพัฒนา')
        html = html.replace('review security and maintenance signals before production deployment', 'ตรวจสอบสัญญาณความปลอดภัยและการบำรุงรักษาก่อนนำไปใช้งานจริง')
        html = html.replace('Not recommended for production use without thorough manual review and additional security measures', 'ไม่แนะนำสำหรับการใช้งานจริงโดยไม่มีการตรวจสอบด้วยตนเองอย่างละเอียดและมาตรการความปลอดภัยเพิ่มเติม')
        html = html.replace('It is below the recommended threshold of 70.', 'ต่ำกว่าเกณฑ์ที่แนะนำที่ 70')

        # 4. "X is a Y — description"
        html = _re_t.sub(r'>(.+?) is a (Node\.js package|Python package|Rust crate|Chrome extension|WordPress plugin|VPN service|game|website|SaaS platform|Firefox extension|VS Code extension|iOS app|Android app) — ',
                         r'>\1 เป็น \2 — ', html)

        # 5. Entity type translations in body text
        html = html.replace('is a Node.js package', 'เป็นแพ็คเกจ Node.js')
        html = html.replace('is a Python package', 'เป็นแพ็คเกจ Python')
        html = html.replace('is a Rust crate', 'เป็น Rust crate')
        html = html.replace('is a Chrome extension', 'เป็นส่วนขยาย Chrome')
        html = html.replace('is a WordPress plugin', 'เป็นปลั๊กอิน WordPress')
        html = html.replace('is a VPN service', 'เป็นบริการ VPN')
        html = html.replace('is a iOS app', 'เป็นแอป iOS')
        html = html.replace('is a Android app', 'เป็นแอป Android')

        # 6. Safety guide text
        html = html.replace("to check for vulnerabilities. Review the package's GitHub repository for recent commits.", 'เพื่อตรวจสอบช่องโหว่ ตรวจสอบ GitHub repository ของแพ็คเกจสำหรับ commit ล่าสุด')
        html = html.replace('You can also check the trust score via API:', 'คุณสามารถตรวจสอบคะแนนความน่าเชื่อถือผ่าน API ได้เช่นกัน:')
        html = html.replace('watch for:', 'ควรระวัง:')
        html = html.replace('dependency vulnerabilities, malicious packages, typosquatting', 'ช่องโหว่ dependencies แพ็คเกจอันตราย typosquatting')
        html = html.replace("Run your package manager's audit command regularly.", 'รันคำสั่ง audit ของ package manager เป็นประจำ')
        html = html.replace('>Run <code>', '>รัน <code>')

        # 7. King sections — privacy/security
        html = _re_t.sub(r'(.+?) is a Node\.js package maintained by (.+?)\.', r'\1 เป็นแพ็คเกจ Node.js ที่ดูแลโดย \2', html)
        html = _re_t.sub(r'(.+?) is a (.+?) maintained by (.+?)\.', r'\1 เป็น \2 ที่ดูแลโดย \3', html)
        html = html.replace(' maintained by ', ' ดูแลโดย ')
        html = html.replace('As a development package,', 'ในฐานะแพ็คเกจพัฒนา')
        html = html.replace('does not directly collect end-user personal data', 'ไม่เก็บข้อมูลส่วนตัวของผู้ใช้ปลายทางโดยตรง')
        html = html.replace('However, applications built with it may collect data depending on implementation', 'อย่างไรก็ตาม แอปพลิเคชันที่สร้างด้วยอาจเก็บข้อมูลขึ้นอยู่กับการใช้งาน')
        html = html.replace("Review the package's dependencies for potential supply chain risks.", 'ตรวจสอบ dependencies ของแพ็คเกจสำหรับความเสี่ยงด้านห่วงโซ่อุปทาน')
        html = html.replace('License information not available.', 'ไม่มีข้อมูลใบอนุญาต')
        html = html.replace('Open-source packages allow independent security review of the source code.', 'แพ็คเกจ open-source อนุญาตให้ตรวจสอบความปลอดภัยของซอร์สโค้ดได้อย่างอิสระ')
        html = html.replace('known vulnerabilities (CVEs) in the National Vulnerability Database', 'ช่องโหว่ที่ทราบ (CVE) ใน National Vulnerability Database')
        html = html.replace('This is a clean record.', 'นี่คือบันทึกที่สะอาด')
        html = html.replace('Review advisories and update to the latest version.', 'ตรวจสอบคำแนะนำและอัปเดตเป็นเวอร์ชันล่าสุด')

        html = html.replace('and has not yet reached Nerq trust threshold (70+).', 'และยังไม่ถึงเกณฑ์ความน่าเชื่อถือของ Nerq (70+)')
        html = html.replace('and meets Nerq trust threshold', 'และผ่านเกณฑ์ความน่าเชื่อถือของ Nerq')
        html = html.replace('This score is based on automated analysis of security, maintenance, community, and quality signals.', 'คะแนนนี้อิงจากการวิเคราะห์อัตโนมัติของสัญญาณด้านความปลอดภัย การบำรุงรักษา ชุมชน และคุณภาพ')

        # 8. Methodology
        html = html.replace('using the same methodology, enabling direct cross-entity comparison', 'โดยใช้วิธีการเดียวกัน ทำให้สามารถเปรียบเทียบโดยตรงระหว่างเอนทิตีได้')
        html = html.replace('Scores are updated continuously as new data becomes available', 'คะแนนจะถูกอัปเดตอย่างต่อเนื่องเมื่อมีข้อมูลใหม่')
        html = html.replace('is computed from', 'คำนวณจาก')
        html = html.replace('The score reflects', 'คะแนนสะท้อน')
        html = html.replace('independent dimensions', 'มิติอิสระ')
        html = html.replace('Each dimension is weighted equally to produce the composite trust score.', 'แต่ละมิติมีน้ำหนักเท่ากันเพื่อสร้างคะแนนความน่าเชื่อถือรวม')

        # 9. Key findings / signal descriptions
        html = html.replace('Composite trust score:', 'คะแนนความน่าเชื่อถือรวม:')
        html = html.replace('across all available signals', 'จากสัญญาณทั้งหมดที่มี')
        html = html.replace('Code quality, vulnerability exposure, and security practices.', 'คุณภาพโค้ด การเปิดเผยช่องโหว่ และการปฏิบัติด้านความปลอดภัย')
        html = html.replace('Update frequency, issue responsiveness, active development.', 'ความถี่ในการอัปเดต การตอบสนองต่อปัญหา การพัฒนาที่ยังคงดำเนินอยู่')
        html = html.replace('README quality, API docs, usage examples.', 'คุณภาพ README เอกสาร API ตัวอย่างการใช้งาน')
        html = html.replace('Community adoption.', 'การยอมรับจากชุมชน')
        html = html.replace('Composite score across all trust dimensions.', 'คะแนนรวมจากมิติความน่าเชื่อถือทั้งหมด')

        # 10. FAQ answers
        html = html.replace('Yes, it is safe to use.', 'ใช่ ปลอดภัยที่จะใช้งาน')
        html = html.replace('Use with some caution.', 'ใช้ด้วยความระมัดระวัง')
        html = html.replace('Exercise caution.', 'ควรระวัง')
        html = html.replace('Significant trust concerns.', 'มีปัญหาด้านความน่าเชื่อถือที่สำคัญ')
        html = html.replace('Strongest signal:', 'สัญญาณที่แข็งแกร่งที่สุด:')
        html = html.replace('Score based on', 'คะแนนอิงจาก')
        html = html.replace('multiple trust dimensions', 'มิติความน่าเชื่อถือหลายด้าน')
        html = html.replace('Scores update as new data becomes available.', 'คะแนนจะอัปเดตเมื่อมีข้อมูลใหม่')
        html = html.replace('check back soon', 'กลับมาตรวจสอบเร็วๆ นี้')
        html = html.replace('higher-rated alternatives include', 'ทางเลือกที่มีคะแนนสูงกว่าได้แก่')
        html = html.replace('more Node.js packages are being analyzed', 'แพ็คเกจ Node.js เพิ่มเติมกำลังถูกวิเคราะห์')
        html = html.replace('more Python packages are being analyzed', 'แพ็คเกจ Python เพิ่มเติมกำลังถูกวิเคราะห์')
        html = html.replace('Meets Nerq Verified threshold.', 'ผ่านเกณฑ์ Nerq ที่ยืนยันแล้ว')

        # 11. Security check FAQ
        html = html.replace('Nerq checks', 'Nerq ตรวจสอบ')
        html = html.replace('against NVD, OSV.dev, and registry-specific vulnerability databases', 'กับ NVD, OSV.dev และฐานข้อมูลช่องโหว่เฉพาะ registry')
        html = html.replace('Current security score:', 'คะแนนความปลอดภัยปัจจุบัน:')
        html = html.replace("Run your package manager's audit command for the latest findings.", 'รันคำสั่ง audit ของ package manager เพื่อดูผลล่าสุด')
        html = html.replace('has a trust score of', 'มีคะแนนความน่าเชื่อถือ')
        html = html.replace('has a Nerq Trust Score of', 'มีคะแนนความน่าเชื่อถือ Nerq')

        # 12. Footer bottom
        html = html.replace('trust scores for all software', 'คะแนนความน่าเชื่อถือสำหรับซอฟต์แวร์ทั้งหมด')
        html = html.replace('7.5M+ entities', '7.5 ล้าน+ เอนทิตี')
        html = html.replace('26 registries', '26 registry')

        # 13. og:description
        html = html.replace('Independent safety assessment by Nerq.', 'การประเมินความปลอดภัยอิสระโดย Nerq')
        html = html.replace('Independent safety assessment by Nerq', 'การประเมินความปลอดภัยอิสระโดย Nerq')

        # 14. Breadcrumb in JSON-LD
        html = html.replace('"Safety Reports"', '"รายงานความปลอดภัย"')

        # 15. FAQ questions (in <summary> and JSON-LD)
        html = _re_t.sub(r"What is (.+?)'s trust score\?", r'คะแนนความน่าเชื่อถือของ \1 คือเท่าไร?', html)
        html = _re_t.sub(r"(.+?)'s trust score คืออะไร\?", r'คะแนนความน่าเชื่อถือของ \1 คือเท่าไร?', html)
        html = _re_t.sub(r'Is (.+?) safe to use\?', r'\1 ปลอดภัยที่จะใช้งานหรือไม่?', html)
        html = _re_t.sub(r'Is (.+?) safe\?', r'\1 ปลอดภัยหรือไม่?', html)
        html = _re_t.sub(r'What are safer alternatives to (.+?)\?', r'ทางเลือกที่ปลอดภัยกว่า \1 มีอะไรบ้าง?', html)
        html = _re_t.sub(r'Does (.+?) have known vulnerabilities\?', r'\1 มีช่องโหว่ที่ทราบหรือไม่?', html)
        html = _re_t.sub(r'How actively maintained is (.+?)\?', r'\1 ได้รับการดูแลอย่างต่อเนื่องเพียงใด?', html)
        html = _re_t.sub(r'How does (.+?) compare to similar', r'\1 เปรียบเทียบกับ', html)
        html = _re_t.sub(r'Can I use (.+?) in a regulated environment\?', r'ฉันสามารถใช้ \1 ในสภาพแวดล้อมที่มีการควบคุมหรือไม่?', html)

        # 16. FAQ answer fragments
        html = html.replace('In the npm category,', 'ในหมวดหมู่ npm,')
        html = html.replace('In the pypi category,', 'ในหมวดหมู่ pypi,')
        html = html.replace('In the crates category,', 'ในหมวดหมู่ crates,')
        html = _re_t.sub(r'In the (\w+) category,', r'ในหมวดหมู่ \1,', html)
        html = _re_t.sub(r'(.+?) scores ([\d.]+)/100\.', r'\1 ได้คะแนน \2/100', html)

        # 17. "has a Trust Score of" in king sections
        html = _re_t.sub(r'(.+?) has a Trust Score of', r'\1 มีคะแนนความน่าเชื่อถือ', html)

        # 18. Security king section fragments
        html = html.replace('Security score:', 'คะแนนความปลอดภัย:')
        html = html.replace('Privacy score:', 'คะแนนความเป็นส่วนตัว:')
        html = html.replace('to check for known vulnerabilities in your dependency tree', 'เพื่อตรวจสอบช่องโหว่ที่ทราบใน dependency tree')

        # 19. Meta description
        html = html.replace('0 known vulnerabilities', '0 ช่องโหว่ที่ทราบ')
        html = html.replace('License: See repository', 'ใบอนุญาต: ดูใน repository')
        html = html.replace('Independent security analysis of', 'การวิเคราะห์ความปลอดภัยอิสระของ')
        html = html.replace('trust signals, vulnerabilities, compliance, and safer alternatives', 'สัญญาณความน่าเชื่อถือ ช่องโหว่ การปฏิบัติตามกฎระเบียบ และทางเลือกที่ปลอดภัยกว่า')

        # 20. og:description
        html = html.replace('trust grade,', 'เกรดความน่าเชื่อถือ,')
        html = html.replace('por Nerq', 'โดย Nerq')
        html = html.replace('oleh Nerq', 'โดย Nerq')
        html = html.replace('od Nerq', 'โดย Nerq')

        # 21. Fix Schema.org @type that got wrongly translated by _CONTENT_TRANSLATIONS
        html = html.replace('"@type": "รีวิว"', '"@type": "Review"')
        html = html.replace('"@type":"รีวิว"', '"@type":"Review"')
        # reviewBody translation
        html = html.replace('with a Nerq Trust Score of', 'ด้วยคะแนนความน่าเชื่อถือ Nerq')
        html = html.replace('Proceed with caution.', 'ดำเนินการด้วยความระมัดระวัง')
        html = html.replace('Not recommended.', 'ไม่แนะนำ')
        # JSON-LD
        html = _re_t.sub(r'"name": "Is (.+?) Safe\?', r'"name": "\1 ปลอดภัยหรือไม่?', html)
        html = _re_t.sub(r'"name": "Is (.+?) Safe to Visit\?', r'"name": "\1 ปลอดภัยที่จะเยี่ยมชมหรือไม่?', html)
        html = _re_t.sub(r'og:title" content="Is (.+?) Safe\?', r'og:title" content="\1 ปลอดภัยหรือไม่?', html)
        html = _re_t.sub(r'nerq:question" content="Is (.+?) safe', r'nerq:question" content="\1 ปลอดภัย', html)

        # Fix: License
        html = html.replace('License: Not specified', 'ใบอนุญาต: ไม่ระบุ')
        html = html.replace('License: See repository', 'ใบอนุญาต: ดูใน repository')
        # Fix: og:description suffix
        html = html.replace('โดย Nerq', 'โดย Nerq')
        # Fix: Footer remaining English
        html = html.replace('dimensions. Data from', 'มิติ ข้อมูลจาก')
        html = html.replace('Data from', 'ข้อมูลจาก')

    elif lang == "ro":
        import re as _re_t
        html = _re_t.sub(r'<title>Is (.+?) Safe\?', r'<title>Este \1 sigur?', html, count=1)
        html = html.replace('Independent Trust &amp; Security Analysis 2026 | Nerq', 'Analiză independentă de încredere și securitate 2026 | Nerq')
        html = _re_t.sub(r'>Is (.+?) Safe\?<', r'>Este \1 sigur?<', html)
        html = _re_t.sub(r'>Is (.+?) safe\?<', r'>Este \1 sigur?<', html)
        html = _re_t.sub(r'>What data does (.+?) collect\?<', r'>Ce date colectează \1?<', html)
        html = _re_t.sub(r'>Is (.+?) secure\?<', r'>Este \1 sigur?<', html)
        html = _re_t.sub(r'>(.+?) Across Platforms<', r'>\1 pe alte platforme<', html)
        html = _re_t.sub(r'>Safety Guide: (.+?)<', r'>Ghid de securitate: \1<', html)
        html = _re_t.sub(r'>What is (.+?)\?<', r'>Ce este \1?<', html)
        html = html.replace('>Details<', '>Detalii<')
        html = _re_t.sub(r'>Is (.+?) Safe to Visit\?', r'>Este \1 sigur de vizitat?', html)
        html = _re_t.sub(r'>Is (.+?) safe for solo travelers\?<', r'>Este \1 sigur pentru călătorii singuri?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for women\?<', r'>Este \1 sigur pentru femei?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for LGBTQ\+ travelers\?<', r'>Este \1 sigur pentru călătorii LGBTQ+?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for families\?<', r'>Este \1 sigur pentru familii?<', html)
        html = _re_t.sub(r'>Is (.+?) safe to visit right now\?<', r'>Este \1 sigur de vizitat acum?<', html)
        html = _re_t.sub(r'>Is tap water safe to drink in (.+?)\?<', r'>Este apa de la robinet sigură de băut în \1?<', html)
        html = _re_t.sub(r'>Do I need vaccinations for (.+?)\?<', r'>Am nevoie de vaccinuri pentru \1?<', html)
        html = _re_t.sub(r'>What are safer alternatives to (.+?)\?<', r'>Care sunt alternativele mai sigure la \1?<', html)
        html = _re_t.sub(r'>What are the side effects of (.+?)\?<', r'>Care sunt efectele secundare ale \1?<', html)
        html = _re_t.sub(r'>Does (.+?) interact with medications\?<', r'>Interacționează \1 cu medicamentele?<', html)
        html = _re_t.sub(r"(.+?)'s trust score of", r'scorul de încredere al \1 de', html)
        html = _re_t.sub(r'Nerq of (\d)', r'Nerq de \1', html)
        html = html.replace('Safety Score', 'Scor de securitate')
        html = html.replace('Trust Analysis 2026', 'Analiză de încredere 2026')
        # Nav
        html = html.replace('>Search<', '>Căutare<')
        html = html.replace('>Apps<', '>Aplicații<')
        html = html.replace('>Packages<', '>Pachete<')
        html = html.replace('>Extensions<', '>Extensii<')
        html = html.replace('>Websites<', '>Site-uri web<')
        html = html.replace('>Travel<', '>Călătorii<')
        html = html.replace('>Charities<', '>Organizații caritabile<')
        html = html.replace('>Compare<', '>Comparare<')
        html = html.replace('>Resources<', '>Resurse<')
        html = html.replace('>About<', '>Despre<')
        html = html.replace('>Check Safety<', '>Verifică securitatea<')
        html = html.replace('>Games<', '>Jocuri<')
        html = html.replace('>Countries<', '>Țări<')
        html = html.replace('>Check Website<', '>Verifică site-ul<')
        html = html.replace('>Safety Guides<', '>Ghiduri de securitate<')
        # Footer text
        html = html.replace('Trust scores for software, apps, websites, travel destinations, and charities', 'Scoruri de încredere pentru software, aplicații, site-uri web, destinații de călătorie și organizații caritabile')
        html = html.replace('20 languages', '20 limbi')
        html = html.replace('>Guides<', '>Ghiduri<')
        html = html.replace('>Mobile Apps<', '>Aplicații mobile<')
        html = html.replace('>Trust Badges<', '>Insigne de încredere<')
        html = html.replace('>VPNs<', '>VPN-uri<')
        html = html.replace('7.5M+ entities from 26 registries. Independent. Data-driven.', '7,5M+ entități din 26 registre. Independent. Bazat pe date.')

        # ── Dynamic paragraph translations ──

        # 1. Verdict lead
        html = _re_t.sub(
            r'Yes, (.+?) is safe to use\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Da, \1 este sigur de utilizat. \1 este \2 cu un Scor de Încredere Nerq de \3/100 (\4)', html)
        html = _re_t.sub(
            r'Use (.+?) with some caution\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Folosiți \1 cu precauție. \1 este \2 cu un Scor de Încredere Nerq de \3/100 (\4)', html)
        html = _re_t.sub(
            r'Exercise caution with (.+?)\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Fiți precauți cu \1. \1 este \2 cu un Scor de Încredere Nerq de \3/100 (\4)', html)

        # 2. Short answer box
        html = html.replace('<strong>YES</strong>', '<strong>DA</strong>')
        html = html.replace('<strong>CAUTION</strong>', '<strong>PRECAUȚIE</strong>')
        html = html.replace('<strong>NO — USE WITH CAUTION</strong>', '<strong>NU — UTILIZAȚI CU PRECAUȚIE</strong>')

        # 3. Citation detail / verdict detail
        html = html.replace("It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption", 'Îndeplinește pragul de încredere Nerq cu semnale puternice în securitate, mentenanță și adoptare comunitară')
        html = html.replace('It has moderate trust signals but shows some areas of concern that warrant attention', 'Are semnale de încredere moderate, dar prezintă unele zone care necesită atenție')
        html = html.replace('It has below-average trust signals with significant gaps in security, maintenance, or documentation', 'Are semnale de încredere sub medie cu lacune semnificative în securitate, mentenanță sau documentație')
        html = html.replace('Recommended for production use', 'Recomandat pentru utilizare în producție')
        html = html.replace('It is recommended for production use.', 'Recomandat pentru utilizare în producție.')
        html = html.replace('review the full report below for specific considerations', 'consultați raportul complet de mai jos pentru considerații specifice')
        html = html.replace('Suitable for development use', 'Potrivit pentru utilizare în dezvoltare')
        html = html.replace('review security and maintenance signals before production deployment', 'verificați semnalele de securitate și mentenanță înainte de implementarea în producție')
        html = html.replace('Not recommended for production use without thorough manual review and additional security measures', 'Nu este recomandat pentru producție fără o revizuire manuală amănunțită și măsuri suplimentare de securitate')
        html = html.replace('It is below the recommended threshold of 70.', 'Este sub pragul recomandat de 70.')

        # 4. "X is a Y — description"
        html = _re_t.sub(r'>(.+?) is a (Node\.js package|Python package|Rust crate|Chrome extension|WordPress plugin|VPN service|game|website|SaaS platform|Firefox extension|VS Code extension|iOS app|Android app) — ',
                         r'>\1 este \2 — ', html)

        # 5. Entity type translations in body text
        html = html.replace('is a Node.js package', 'este un pachet Node.js')
        html = html.replace('is a Python package', 'este un pachet Python')
        html = html.replace('is a Rust crate', 'este un Rust crate')
        html = html.replace('is a Chrome extension', 'este o extensie Chrome')
        html = html.replace('is a WordPress plugin', 'este un plugin WordPress')
        html = html.replace('is a VPN service', 'este un serviciu VPN')
        html = html.replace('is a iOS app', 'este o aplicație iOS')
        html = html.replace('is a Android app', 'este o aplicație Android')

        # 6. Safety guide text
        html = html.replace("to check for vulnerabilities. Review the package's GitHub repository for recent commits.", 'pentru a verifica vulnerabilitățile. Verificați depozitul GitHub al pachetului pentru commit-uri recente.')
        html = html.replace('You can also check the trust score via API:', 'Puteți verifica și scorul de încredere prin API:')
        html = html.replace('watch for:', 'urmăriți:')
        html = html.replace('dependency vulnerabilities, malicious packages, typosquatting', 'vulnerabilități de dependențe, pachete malițioase, typosquatting')
        html = html.replace("Run your package manager's audit command regularly.", 'Rulați periodic comanda de audit a managerului de pachete.')
        html = html.replace('>Run <code>', '>Rulați <code>')

        # 7. King sections — privacy/security
        html = _re_t.sub(r'(.+?) is a Node\.js package maintained by (.+?)\.', r'\1 este un pachet Node.js întreținut de \2.', html)
        html = _re_t.sub(r'(.+?) is a (.+?) maintained by (.+?)\.', r'\1 este \2 întreținut de \3.', html)
        html = html.replace(' maintained by ', ' întreținut de ')
        html = html.replace('As a development package,', 'Ca pachet de dezvoltare,')
        html = html.replace('does not directly collect end-user personal data', 'nu colectează direct date personale ale utilizatorilor finali')
        html = html.replace('However, applications built with it may collect data depending on implementation', 'Cu toate acestea, aplicațiile construite cu el pot colecta date în funcție de implementare')
        html = html.replace("Review the package's dependencies for potential supply chain risks.", 'Verificați dependențele pachetului pentru riscuri potențiale în lanțul de aprovizionare.')
        html = html.replace('License information not available.', 'Informații despre licență indisponibile.')
        html = html.replace('Open-source packages allow independent security review of the source code.', 'Pachetele open-source permit revizuirea independentă a securității codului sursă.')
        html = html.replace('known vulnerabilities (CVEs) in the National Vulnerability Database', 'vulnerabilități cunoscute (CVE) în National Vulnerability Database')
        html = html.replace('This is a clean record.', 'Acesta este un record curat.')
        html = html.replace('Review advisories and update to the latest version.', 'Verificați recomandările și actualizați la cea mai recentă versiune.')

        html = html.replace('and has not yet reached Nerq trust threshold (70+).', 'și nu a atins încă pragul de încredere Nerq (70+).')
        html = html.replace('and meets Nerq trust threshold', 'și îndeplinește pragul de încredere Nerq')
        html = html.replace('This score is based on automated analysis of security, maintenance, community, and quality signals.', 'Acest scor se bazează pe analiza automatizată a semnalelor de securitate, mentenanță, comunitate și calitate.')

        # 8. Methodology
        html = html.replace('using the same methodology, enabling direct cross-entity comparison', 'folosind aceeași metodologie, permițând compararea directă între entități')
        html = html.replace('Scores are updated continuously as new data becomes available', 'Scorurile sunt actualizate continuu pe măsură ce devin disponibile date noi')
        html = html.replace('is computed from', 'este calculat din')
        html = html.replace('The score reflects', 'Scorul reflectă')
        html = html.replace('independent dimensions', 'dimensiuni independente')
        html = html.replace('Each dimension is weighted equally to produce the composite trust score.', 'Fiecare dimensiune are pondere egală pentru a produce scorul de încredere compus.')

        # 9. Key findings / signal descriptions
        html = html.replace('Composite trust score:', 'Scor de încredere compus:')
        html = html.replace('across all available signals', 'din toate semnalele disponibile')
        html = html.replace('Code quality, vulnerability exposure, and security practices.', 'Calitatea codului, expunerea la vulnerabilități și practicile de securitate.')
        html = html.replace('Update frequency, issue responsiveness, active development.', 'Frecvența actualizărilor, reactivitatea la probleme, dezvoltarea activă.')
        html = html.replace('README quality, API docs, usage examples.', 'Calitatea README, documentația API, exemple de utilizare.')
        html = html.replace('Community adoption.', 'Adoptare comunitară.')
        html = html.replace('Composite score across all trust dimensions.', 'Scor compus din toate dimensiunile de încredere.')

        # 10. FAQ answers
        html = html.replace('Yes, it is safe to use.', 'Da, este sigur de utilizat.')
        html = html.replace('Use with some caution.', 'Utilizați cu precauție.')
        html = html.replace('Exercise caution.', 'Fiți precauți.')
        html = html.replace('Significant trust concerns.', 'Probleme semnificative de încredere.')
        html = html.replace('Strongest signal:', 'Cel mai puternic semnal:')
        html = html.replace('Score based on', 'Scor bazat pe')
        html = html.replace('multiple trust dimensions', 'multiple dimensiuni de încredere')
        html = html.replace('Scores update as new data becomes available.', 'Scorurile se actualizează pe măsură ce devin disponibile date noi.')
        html = html.replace('check back soon', 'reveniți în curând')
        html = html.replace('higher-rated alternatives include', 'alternativele cu scor mai mare includ')
        html = html.replace('more Node.js packages are being analyzed', 'mai multe pachete Node.js sunt în curs de analiză')
        html = html.replace('more Python packages are being analyzed', 'mai multe pachete Python sunt în curs de analiză')
        html = html.replace('Meets Nerq Verified threshold.', 'Îndeplinește pragul verificat Nerq.')

        # 11. Security check FAQ
        html = html.replace('Nerq checks', 'Nerq verifică')
        html = html.replace('against NVD, OSV.dev, and registry-specific vulnerability databases', 'față de NVD, OSV.dev și bazele de date de vulnerabilități specifice registrului')
        html = html.replace('Current security score:', 'Scorul de securitate curent:')
        html = html.replace("Run your package manager's audit command for the latest findings.", 'Rulați comanda de audit a managerului de pachete pentru cele mai recente rezultate.')
        html = html.replace('has a trust score of', 'are un scor de încredere de')
        html = html.replace('has a Nerq Trust Score of', 'are un Scor de Încredere Nerq de')

        # 12. Footer bottom
        html = html.replace('trust scores for all software', 'scoruri de încredere pentru tot software-ul')
        html = html.replace('7.5M+ entities', '7,5M+ entități')
        html = html.replace('26 registries', '26 registre')

        # 13. og:description
        html = html.replace('Independent safety assessment by Nerq.', 'Evaluare independentă de securitate de către Nerq.')
        html = html.replace('Independent safety assessment by Nerq', 'Evaluare independentă de securitate de către Nerq')

        # 14. Breadcrumb in JSON-LD
        html = html.replace('"Safety Reports"', '"Rapoarte de securitate"')

        # 15. FAQ questions (in <summary> and JSON-LD)
        html = _re_t.sub(r"What is (.+?)'s trust score\?", r'Care este scorul de încredere al \1?', html)
        html = _re_t.sub(r"Care este (.+?)'s trust score\?", r'Care este scorul de încredere al \1?', html)
        html = _re_t.sub(r'Is (.+?) safe to use\?', r'Este \1 sigur de utilizat?', html)
        html = _re_t.sub(r'Is (.+?) safe\?', r'Este \1 sigur?', html)
        html = _re_t.sub(r'What are safer alternatives to (.+?)\?', r'Care sunt alternativele mai sigure la \1?', html)
        html = _re_t.sub(r'Does (.+?) have known vulnerabilities\?', r'Are \1 vulnerabilități cunoscute?', html)
        html = _re_t.sub(r'How actively maintained is (.+?)\?', r'Cât de activ este întreținut \1?', html)
        html = _re_t.sub(r'How does (.+?) compare to similar', r'Cum se compară \1 cu cele similare', html)
        html = _re_t.sub(r'Can I use (.+?) in a regulated environment\?', r'Pot folosi \1 într-un mediu reglementat?', html)

        # 16. FAQ answer fragments
        html = html.replace('In the npm category,', 'În categoria npm,')
        html = html.replace('In the pypi category,', 'În categoria pypi,')
        html = html.replace('In the crates category,', 'În categoria crates,')
        html = _re_t.sub(r'In the (\w+) category,', r'În categoria \1,', html)
        html = _re_t.sub(r'(.+?) scores ([\d.]+)/100\.', r'\1 a obținut scorul \2/100.', html)

        # 17. "has a Trust Score of" in king sections
        html = _re_t.sub(r'(.+?) has a Trust Score of', r'\1 are un Scor de Încredere de', html)

        # 18. Security king section fragments
        html = html.replace('Security score:', 'Scor de securitate:')
        html = html.replace('Privacy score:', 'Scor de confidențialitate:')
        html = html.replace('to check for known vulnerabilities in your dependency tree', 'pentru a verifica vulnerabilitățile cunoscute în arborele de dependențe')

        # 19. Meta description
        html = html.replace('0 known vulnerabilities', '0 vulnerabilități cunoscute')
        html = html.replace('License: See repository', 'Licență: Consultați depozitul')
        html = html.replace('Independent security analysis of', 'Analiză independentă de securitate pentru')
        html = html.replace('trust signals, vulnerabilities, compliance, and safer alternatives', 'semnale de încredere, vulnerabilități, conformitate și alternative mai sigure')

        # 20. og:description
        html = html.replace('trust grade,', 'grad de încredere,')
        html = html.replace('por Nerq', 'de către Nerq')
        html = html.replace('oleh Nerq', 'de către Nerq')
        html = html.replace('od Nerq', 'de către Nerq')

        # 21. Fix Schema.org @type that got wrongly translated by _CONTENT_TRANSLATIONS
        html = html.replace('"@type": "Recenzie"', '"@type": "Review"')
        html = html.replace('"@type":"Recenzie"', '"@type":"Review"')
        # reviewBody translation
        html = html.replace('with a Nerq Trust Score of', 'cu un Scor de Încredere Nerq de')
        html = html.replace('Proceed with caution.', 'Procedați cu precauție.')
        html = html.replace('Not recommended.', 'Nu este recomandat.')
        # JSON-LD
        html = _re_t.sub(r'"name": "Is (.+?) Safe\?', r'"name": "Este \1 sigur?', html)
        html = _re_t.sub(r'"name": "Is (.+?) Safe to Visit\?', r'"name": "Este \1 sigur de vizitat?', html)
        html = _re_t.sub(r'og:title" content="Is (.+?) Safe\?', r'og:title" content="Este \1 sigur?', html)
        html = _re_t.sub(r'nerq:question" content="Is (.+?) safe', r'nerq:question" content="Este \1 sigur', html)

        # Fix: License
        html = html.replace('License: Not specified', 'Licență: Nespecificată')
        html = html.replace('License: See repository', 'Licență: Consultați depozitul')
        # Fix: og:description suffix
        html = html.replace('de către Nerq', 'de către Nerq')
        # Fix: Footer remaining English
        html = html.replace('dimensions. Data from', 'dimensiuni. Date din')
        html = html.replace('Data from', 'Date din')

    elif lang == "tr":
        import re as _re_t
        html = _re_t.sub(r'<title>Is (.+?) Safe\?', r'<title>\1 Güvenli mi?', html, count=1)
        html = html.replace('Independent Trust &amp; Security Analysis 2026 | Nerq', 'Bağımsız Güven ve Güvenlik Analizi 2026 | Nerq')
        html = _re_t.sub(r'>Is (.+?) Safe\?<', r'>\1 Güvenli mi?<', html)
        html = _re_t.sub(r'>Is (.+?) safe\?<', r'>\1 güvenli mi?<', html)
        html = _re_t.sub(r'>What data does (.+?) collect\?<', r'>\1 hangi verileri topluyor?<', html)
        html = _re_t.sub(r'>Is (.+?) secure\?<', r'>\1 güvenli mi?<', html)
        html = _re_t.sub(r'>(.+?) Across Platforms<', r'>\1 Diğer Platformlarda<', html)
        html = _re_t.sub(r'>Safety Guide: (.+?)<', r'>Güvenlik Rehberi: \1<', html)
        html = _re_t.sub(r'>What is (.+?)\?<', r'>\1 Nedir?<', html)
        html = html.replace('>Details<', '>Detaylar<')
        html = _re_t.sub(r'>Is (.+?) Safe to Visit\?', r'>\1 Ziyaret Etmek Güvenli mi?', html)
        html = _re_t.sub(r'>Is (.+?) safe for solo travelers\?<', r'>\1 yalnız gezginler için güvenli mi?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for women\?<', r'>\1 kadınlar için güvenli mi?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for LGBTQ\+ travelers\?<', r'>\1 LGBTQ+ gezginler için güvenli mi?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for families\?<', r'>\1 aileler için güvenli mi?<', html)
        html = _re_t.sub(r'>Is (.+?) safe to visit right now\?<', r'>\1 şu anda ziyaret etmek güvenli mi?<', html)
        html = _re_t.sub(r'>Is tap water safe to drink in (.+?)\?<', r'>\1 bölgesinde musluk suyu içmek güvenli mi?<', html)
        html = _re_t.sub(r'>Do I need vaccinations for (.+?)\?<', r'>\1 için aşı yaptırmam gerekiyor mu?<', html)
        html = _re_t.sub(r'>What are safer alternatives to (.+?)\?<', r'>\1 için daha güvenli alternatifler nelerdir?<', html)
        html = _re_t.sub(r'>What are the side effects of (.+?)\?<', r'>\1 yan etkileri nelerdir?<', html)
        html = _re_t.sub(r'>Does (.+?) interact with medications\?<', r'>\1 ilaçlarla etkileşime girer mi?<', html)
        html = _re_t.sub(r"(.+?)'s trust score of", r'\1 güven puanı', html)
        html = _re_t.sub(r'Nerq of (\d)', r'Nerq \1', html)
        html = html.replace('Safety Score', 'Güvenlik Puanı')
        html = html.replace('Trust Analysis 2026', 'Güven Analizi 2026')
        # Nav
        html = html.replace('>Search<', '>Ara<')
        html = html.replace('>Apps<', '>Uygulamalar<')
        html = html.replace('>Packages<', '>Paketler<')
        html = html.replace('>Extensions<', '>Eklentiler<')
        html = html.replace('>Websites<', '>Web Siteleri<')
        html = html.replace('>Travel<', '>Seyahat<')
        html = html.replace('>Charities<', '>Hayır Kurumları<')
        html = html.replace('>Compare<', '>Karşılaştır<')
        html = html.replace('>Resources<', '>Kaynaklar<')
        html = html.replace('>About<', '>Hakkında<')
        html = html.replace('>Check Safety<', '>Güvenliği Kontrol Et<')
        html = html.replace('>Games<', '>Oyunlar<')
        html = html.replace('>Countries<', '>Ülkeler<')
        html = html.replace('>Check Website<', '>Web Sitesini Kontrol Et<')
        html = html.replace('>Safety Guides<', '>Güvenlik Rehberleri<')
        # Footer text
        html = html.replace('Trust scores for software, apps, websites, travel destinations, and charities', 'Yazılım, uygulama, web sitesi, seyahat destinasyonu ve hayır kurumları için güven puanları')
        html = html.replace('20 languages', '20 dil')
        html = html.replace('>Guides<', '>Rehberler<')
        html = html.replace('>Mobile Apps<', '>Mobil Uygulamalar<')
        html = html.replace('>Trust Badges<', '>Güven Rozetleri<')
        html = html.replace('>VPNs<', '>VPN\'ler<')
        html = html.replace('7.5M+ entities from 26 registries. Independent. Data-driven.', '26 kayıt defterinden 7,5 milyondan fazla varlık. Bağımsız. Veriye dayalı.')

        # ── Dynamic paragraph translations ──

        # 1. Verdict lead
        html = _re_t.sub(
            r'Yes, (.+?) is safe to use\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Evet, \1 kullanımı güvenlidir. \1, \3/100 (\4) Nerq Güven Puanına sahip \2.', html)
        html = _re_t.sub(
            r'Use (.+?) with some caution\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'\1 kullanırken dikkatli olun. \1, \3/100 (\4) Nerq Güven Puanına sahip \2.', html)
        html = _re_t.sub(
            r'Exercise caution with (.+?)\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'\1 konusunda dikkatli olun. \1, \3/100 (\4) Nerq Güven Puanına sahip \2.', html)

        # 2. Short answer box
        html = html.replace('<strong>YES</strong>', '<strong>EVET</strong>')
        html = html.replace('<strong>CAUTION</strong>', '<strong>DİKKAT</strong>')
        html = html.replace('<strong>NO — USE WITH CAUTION</strong>', '<strong>HAYIR — DİKKATLİ KULLANIN</strong>')

        # 3. Citation detail / verdict detail
        html = html.replace("It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption", 'Güvenlik, bakım ve topluluk benimsemesi alanlarında güçlü sinyallerle Nerq güven eşiğini karşılıyor')
        html = html.replace('It has moderate trust signals but shows some areas of concern that warrant attention', 'Orta düzeyde güven sinyallerine sahip olmakla birlikte dikkat gerektiren bazı endişe alanları göstermektedir')
        html = html.replace('It has below-average trust signals with significant gaps in security, maintenance, or documentation', 'Güvenlik, bakım veya dokümantasyonda önemli boşluklarla birlikte ortalamanın altında güven sinyallerine sahiptir')
        html = html.replace('Recommended for production use', 'Üretim kullanımı için önerilir')
        html = html.replace('It is recommended for production use.', 'Üretim kullanımı için önerilir.')
        html = html.replace('review the full report below for specific considerations', 'özel değerlendirmeler için aşağıdaki tam raporu inceleyin')
        html = html.replace('Suitable for development use', 'Geliştirme kullanımı için uygundur')
        html = html.replace('review security and maintenance signals before production deployment', 'üretim dağıtımından önce güvenlik ve bakım sinyallerini inceleyin')
        html = html.replace('Not recommended for production use without thorough manual review and additional security measures', 'Kapsamlı manuel inceleme ve ek güvenlik önlemleri olmadan üretim kullanımı için önerilmez')
        html = html.replace('It is below the recommended threshold of 70.', 'Önerilen 70 eşiğinin altındadır.')

        # 4. "X is a Y — description"
        html = _re_t.sub(r'>(.+?) is a (Node\.js package|Python package|Rust crate|Chrome extension|WordPress plugin|VPN service|game|website|SaaS platform|Firefox extension|VS Code extension|iOS app|Android app) — ',
                         r'>\1 \2 — ', html)

        # 5. Entity type translations in body text
        html = html.replace('is a Node.js package', 'bir Node.js paketidir')
        html = html.replace('is a Python package', 'bir Python paketidir')
        html = html.replace('is a Rust crate', 'bir Rust crate\'idir')
        html = html.replace('is a Chrome extension', 'bir Chrome uzantısıdır')
        html = html.replace('is a WordPress plugin', 'bir WordPress eklentisidir')
        html = html.replace('is a VPN service', 'bir VPN hizmetidir')
        html = html.replace('is a iOS app', 'bir iOS uygulamasıdır')
        html = html.replace('is a Android app', 'bir Android uygulamasıdır')

        # 6. Safety guide text
        html = html.replace("to check for vulnerabilities. Review the package's GitHub repository for recent commits.", 'güvenlik açıklarını kontrol etmek için. Son işlemler için paketin GitHub deposunu inceleyin.')
        html = html.replace('You can also check the trust score via API:', 'Güven puanını API aracılığıyla da kontrol edebilirsiniz:')
        html = html.replace('watch for:', 'dikkat edin:')
        html = html.replace('dependency vulnerabilities, malicious packages, typosquatting', 'bağımlılık açıkları, kötü amaçlı paketler, typosquatting')
        html = html.replace("Run your package manager's audit command regularly.", 'Paket yöneticinizin denetim komutunu düzenli olarak çalıştırın.')
        html = html.replace('>Run <code>', '>Çalıştırın <code>')

        # 7. King sections — privacy/security
        html = _re_t.sub(r'(.+?) is a Node\.js package maintained by (.+?)\.', r'\1, \2 tarafından sürdürülen bir Node.js paketidir.', html)
        html = _re_t.sub(r'(.+?) is a (.+?) maintained by (.+?)\.', r'\1, \3 tarafından sürdürülen \2.', html)
        html = html.replace(' maintained by ', ' tarafından sürdürülmektedir ')
        html = html.replace('As a development package,', 'Bir geliştirme paketi olarak,')
        html = html.replace('does not directly collect end-user personal data', 'son kullanıcı kişisel verilerini doğrudan toplamaz')
        html = html.replace('However, applications built with it may collect data depending on implementation', 'Ancak onunla oluşturulan uygulamalar, uygulamaya bağlı olarak veri toplayabilir')
        html = html.replace("Review the package's dependencies for potential supply chain risks.", 'Olası tedarik zinciri riskleri için paketin bağımlılıklarını inceleyin.')
        html = html.replace('License information not available.', 'Lisans bilgisi mevcut değil.')
        html = html.replace('Open-source packages allow independent security review of the source code.', 'Açık kaynaklı paketler, kaynak kodunun bağımsız güvenlik incelemesine olanak tanır.')
        html = html.replace('known vulnerabilities (CVEs) in the National Vulnerability Database', 'Ulusal Güvenlik Açığı Veritabanı\'nda bilinen güvenlik açıkları (CVE)')
        html = html.replace('This is a clean record.', 'Bu temiz bir sicildir.')
        html = html.replace('Review advisories and update to the latest version.', 'Güvenlik uyarılarını inceleyin ve en son sürüme güncelleyin.')

        html = html.replace('and has not yet reached Nerq trust threshold (70+).', 've henüz Nerq güven eşiğine (70+) ulaşamamıştır.')
        html = html.replace('and meets Nerq trust threshold', 've Nerq güven eşiğini karşılıyor')
        html = html.replace('This score is based on automated analysis of security, maintenance, community, and quality signals.', 'Bu puan, güvenlik, bakım, topluluk ve kalite sinyallerinin otomatik analizine dayanmaktadır.')

        # 8. Methodology
        html = html.replace('using the same methodology, enabling direct cross-entity comparison', 'aynı metodolojiyi kullanarak, varlıklar arasında doğrudan karşılaştırma yapılmasını sağlar')
        html = html.replace('Scores are updated continuously as new data becomes available', 'Puanlar, yeni veriler kullanılabilir hale geldikçe sürekli güncellenir')
        html = html.replace('is computed from', 'şundan hesaplanmıştır:')
        html = html.replace('The score reflects', 'Puan şunu yansıtmaktadır:')
        html = html.replace('independent dimensions', 'bağımsız boyut')
        html = html.replace('Each dimension is weighted equally to produce the composite trust score.', 'Her boyut, bileşik güven puanını oluşturmak için eşit ağırlıklandırılmıştır.')

        # 9. Key findings / signal descriptions
        html = html.replace('Composite trust score:', 'Bileşik güven puanı:')
        html = html.replace('across all available signals', 'tüm mevcut sinyaller genelinde')
        html = html.replace('Code quality, vulnerability exposure, and security practices.', 'Kod kalitesi, güvenlik açığı maruziyeti ve güvenlik uygulamaları.')
        html = html.replace('Update frequency, issue responsiveness, active development.', 'Güncelleme sıklığı, sorun yanıt verme süresi, aktif geliştirme.')
        html = html.replace('README quality, API docs, usage examples.', 'README kalitesi, API belgeleri, kullanım örnekleri.')
        html = html.replace('Community adoption.', 'Topluluk benimsemesi.')
        html = html.replace('Composite score across all trust dimensions.', 'Tüm güven boyutlarında bileşik puan.')

        # 10. FAQ answers
        html = html.replace('Yes, it is safe to use.', 'Evet, kullanımı güvenlidir.')
        html = html.replace('Use with some caution.', 'Dikkatli kullanın.')
        html = html.replace('Exercise caution.', 'Dikkatli olun.')
        html = html.replace('Significant trust concerns.', 'Önemli güven sorunları.')
        html = html.replace('Strongest signal:', 'En güçlü sinyal:')
        html = html.replace('Score based on', 'Puan şuna dayalı:')
        html = html.replace('multiple trust dimensions', 'birden fazla güven boyutu')
        html = html.replace('Scores update as new data becomes available.', 'Puanlar, yeni veriler kullanılabilir hale geldikçe güncellenir.')
        html = html.replace('check back soon', 'yakında tekrar kontrol edin')
        html = html.replace('higher-rated alternatives include', 'daha yüksek puanlı alternatifler şunlardır:')
        html = html.replace('more Node.js packages are being analyzed', 'daha fazla Node.js paketi analiz ediliyor')
        html = html.replace('more Python packages are being analyzed', 'daha fazla Python paketi analiz ediliyor')
        html = html.replace('Meets Nerq Verified threshold.', 'Nerq Doğrulanmış eşiğini karşılıyor.')

        # 11. Security check FAQ
        html = html.replace('Nerq checks', 'Nerq kontrol eder')
        html = html.replace('against NVD, OSV.dev, and registry-specific vulnerability databases', 'NVD, OSV.dev ve kayıt defterine özgü güvenlik açığı veritabanlarına karşı')
        html = html.replace('Current security score:', 'Mevcut güvenlik puanı:')
        html = html.replace("Run your package manager's audit command for the latest findings.", 'En son bulgular için paket yöneticinizin denetim komutunu çalıştırın.')
        html = html.replace('has a trust score of', 'güven puanına sahip')
        html = html.replace('has a Nerq Trust Score of', 'Nerq Güven Puanına sahip')

        # 12. Footer bottom
        html = html.replace('trust scores for all software', 'tüm yazılımlar için güven puanları')
        html = html.replace('7.5M+ entities', '7,5 milyondan fazla varlık')
        html = html.replace('26 registries', '26 kayıt defteri')

        # 13. og:description
        html = html.replace('Independent safety assessment by Nerq.', 'Nerq tarafından bağımsız güvenlik değerlendirmesi.')
        html = html.replace('Independent safety assessment by Nerq', 'Nerq tarafından bağımsız güvenlik değerlendirmesi')

        # 14. Breadcrumb in JSON-LD
        html = html.replace('"Safety Reports"', '"Güvenlik Raporları"')

        # 15. FAQ questions (in <summary> and JSON-LD)
        html = _re_t.sub(r"What is (.+?)'s trust score\?", r'\1 güven puanı nedir?', html)
        html = _re_t.sub(r"Nedir: (.+?)'s trust score\?", r'\1 güven puanı nedir?', html)  # catch post-translated
        html = _re_t.sub(r'Is (.+?) safe to use\?', r'\1 kullanımı güvenli mi?', html)
        html = _re_t.sub(r'Is (.+?) safe\?', r'\1 güvenli mi?', html)
        html = _re_t.sub(r'What are safer alternatives to (.+?)\?', r'\1 için daha güvenli alternatifler nelerdir?', html)
        html = _re_t.sub(r'Does (.+?) have known vulnerabilities\?', r'\1 bilinen güvenlik açıklarına sahip mi?', html)
        html = _re_t.sub(r'How actively maintained is (.+?)\?', r'\1 ne kadar aktif sürdürülüyor?', html)
        html = _re_t.sub(r'How does (.+?) compare to similar', r'\1 benzerleriyle nasıl karşılaştırılır', html)
        html = _re_t.sub(r'Can I use (.+?) in a regulated environment\?', r'\1 düzenlenmiş bir ortamda kullanabilir miyim?', html)

        # 16. FAQ answer fragments
        html = html.replace('In the npm category,', 'npm kategorisinde,')
        html = html.replace('In the pypi category,', 'pypi kategorisinde,')
        html = html.replace('In the crates category,', 'crates kategorisinde,')
        html = _re_t.sub(r'In the (\w+) category,', r'\1 kategorisinde,', html)
        html = _re_t.sub(r'(.+?) scores ([\d.]+)/100\.', r'\1, \2/100 puan aldı.', html)

        # 17. "has a Trust Score of" in king sections
        html = _re_t.sub(r'(.+?) has a Trust Score of', r'\1 Güven Puanına sahip', html)

        # 18. Security king section fragments
        html = html.replace('Security score:', 'Güvenlik puanı:')
        html = html.replace('Privacy score:', 'Gizlilik puanı:')
        html = html.replace('to check for known vulnerabilities in your dependency tree', 'bağımlılık ağacınızdaki bilinen güvenlik açıklarını kontrol etmek için')

        # 19. Meta description
        html = html.replace('0 known vulnerabilities', '0 bilinen güvenlik açığı')
        html = html.replace('License: See repository', 'Lisans: Depoya bakın')
        html = html.replace('Independent security analysis of', 'Bağımsız güvenlik analizi:')
        html = html.replace('trust signals, vulnerabilities, compliance, and safer alternatives', 'güven sinyalleri, güvenlik açıkları, uyumluluk ve daha güvenli alternatifler')

        # 20. og:description
        html = html.replace('trust grade,', 'güven derecesi,')
        html = html.replace('por Nerq', 'Nerq tarafından')
        html = html.replace('oleh Nerq', 'Nerq tarafından')
        html = html.replace('od Nerq', 'Nerq tarafından')
        html = html.replace('by Nerq', 'Nerq tarafından')

        # 21. Fix Schema.org @type that got wrongly translated by _CONTENT_TRANSLATIONS
        html = html.replace('"@type": "İnceleme"', '"@type": "Review"')
        html = html.replace('"@type":"İnceleme"', '"@type":"Review"')
        # reviewBody translation
        html = html.replace('with a Nerq Trust Score of', 'Nerq Güven Puanı ile')
        html = html.replace('Proceed with caution.', 'Dikkatli ilerleyin.')
        html = html.replace('Not recommended.', 'Önerilmez.')
        # JSON-LD
        html = _re_t.sub(r'"name": "Is (.+?) Safe\?', r'"name": "\1 Güvenli mi?', html)
        html = _re_t.sub(r'"name": "Is (.+?) Safe to Visit\?', r'"name": "\1 Ziyaret Etmek Güvenli mi?', html)
        html = _re_t.sub(r'og:title" content="Is (.+?) Safe\?', r'og:title" content="\1 Güvenli mi?', html)
        html = _re_t.sub(r'nerq:question" content="Is (.+?) safe', r'nerq:question" content="\1 güvenli', html)

        # Fix: License
        html = html.replace('License: Not specified', 'Lisans: Belirtilmemiş')
        html = html.replace('License: See repository', 'Lisans: Depoya bakın')
        # Fix: og:description suffix — ensure "Nerq tarafından" is consistent
        html = html.replace('tarafından Nerq', 'Nerq tarafından')
        # Fix: Footer remaining English
        html = html.replace('dimensions. Data from', 'boyut. Veriler:')
        html = html.replace('Data from', 'Veriler:')

    elif lang == "hi":
        import re as _re_t
        html = _re_t.sub(r'<title>Is (.+?) Safe\?', r'<title>क्या \1 सुरक्षित है?', html, count=1)
        html = html.replace('Independent Trust &amp; Security Analysis 2026 | Nerq', 'स्वतंत्र विश्वास एवं सुरक्षा विश्लेषण 2026 | Nerq')
        html = _re_t.sub(r'>Is (.+?) Safe\?<', r'>क्या \1 सुरक्षित है?<', html)
        html = _re_t.sub(r'>Is (.+?) safe\?<', r'>क्या \1 सुरक्षित है?<', html)
        html = _re_t.sub(r'>What data does (.+?) collect\?<', r'>\1 कौन सा डेटा एकत्र करता है?<', html)
        html = _re_t.sub(r'>Is (.+?) secure\?<', r'>क्या \1 सुरक्षित है?<', html)
        html = _re_t.sub(r'>(.+?) Across Platforms<', r'>\1 अन्य प्लेटफॉर्म पर<', html)
        html = _re_t.sub(r'>Safety Guide: (.+?)<', r'>सुरक्षा गाइड: \1<', html)
        html = _re_t.sub(r'>What is (.+?)\?<', r'>\1 क्या है?<', html)
        html = html.replace('>Details<', '>विवरण<')
        html = _re_t.sub(r'>Is (.+?) Safe to Visit\?', r'>क्या \1 पर जाना सुरक्षित है?', html)
        html = _re_t.sub(r'>Is (.+?) safe for solo travelers\?<', r'>क्या \1 अकेले यात्रियों के लिए सुरक्षित है?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for women\?<', r'>क्या \1 महिलाओं के लिए सुरक्षित है?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for LGBTQ\+ travelers\?<', r'>क्या \1 LGBTQ+ यात्रियों के लिए सुरक्षित है?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for families\?<', r'>क्या \1 परिवारों के लिए सुरक्षित है?<', html)
        html = _re_t.sub(r'>Is (.+?) safe to visit right now\?<', r'>क्या \1 अभी जाना सुरक्षित है?<', html)
        html = _re_t.sub(r'>Is tap water safe to drink in (.+?)\?<', r'>क्या \1 में नल का पानी पीना सुरक्षित है?<', html)
        html = _re_t.sub(r'>Do I need vaccinations for (.+?)\?<', r'>क्या मुझे \1 के लिए टीकाकरण की आवश्यकता है?<', html)
        html = _re_t.sub(r'>What are safer alternatives to (.+?)\?<', r'>\1 के अधिक सुरक्षित विकल्प क्या हैं?<', html)
        html = _re_t.sub(r'>What are the side effects of (.+?)\?<', r'>\1 के दुष्प्रभाव क्या हैं?<', html)
        html = _re_t.sub(r'>Does (.+?) interact with medications\?<', r'>क्या \1 दवाओं के साथ प्रतिक्रिया करता है?<', html)
        html = _re_t.sub(r"(.+?)'s trust score of", r'\1 का विश्वास स्कोर', html)
        html = _re_t.sub(r'Nerq of (\d)', r'Nerq \1', html)
        html = html.replace('Safety Score', 'सुरक्षा स्कोर')
        html = html.replace('Trust Analysis 2026', 'विश्वास विश्लेषण 2026')
        # Nav
        html = html.replace('>Search<', '>खोजें<')
        html = html.replace('>Apps<', '>ऐप्स<')
        html = html.replace('>Packages<', '>पैकेज<')
        html = html.replace('>Extensions<', '>एक्सटेंशन<')
        html = html.replace('>Websites<', '>वेबसाइट<')
        html = html.replace('>Travel<', '>यात्रा<')
        html = html.replace('>Charities<', '>चैरिटी<')
        html = html.replace('>Compare<', '>तुलना करें<')
        html = html.replace('>Resources<', '>संसाधन<')
        html = html.replace('>About<', '>परिचय<')
        html = html.replace('>Check Safety<', '>सुरक्षा जांचें<')
        html = html.replace('>Games<', '>गेम्स<')
        html = html.replace('>Countries<', '>देश<')
        html = html.replace('>Check Website<', '>वेबसाइट जांचें<')
        html = html.replace('>Safety Guides<', '>सुरक्षा गाइड<')
        # Footer text
        html = html.replace('Trust scores for software, apps, websites, travel destinations, and charities', 'सॉफ्टवेयर, ऐप्स, वेबसाइट, यात्रा गंतव्य और चैरिटी के लिए विश्वास स्कोर')
        html = html.replace('20 languages', '20 भाषाएं')
        html = html.replace('>Guides<', '>गाइड<')
        html = html.replace('>Mobile Apps<', '>मोबाइल ऐप्स<')
        html = html.replace('>Trust Badges<', '>विश्वास बैज<')
        html = html.replace('>VPNs<', '>VPN<')
        html = html.replace('7.5M+ entities from 26 registries. Independent. Data-driven.', '26 रजिस्ट्री से 7.5 मिलियन+ इकाइयां। स्वतंत्र। डेटा-आधारित।')

        # ── Dynamic paragraph translations ──

        # 1. Verdict lead
        html = _re_t.sub(
            r'Yes, (.+?) is safe to use\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'हां, \1 उपयोग के लिए सुरक्षित है। \1 एक \2 है जिसका Nerq विश्वास स्कोर \3/100 (\4) है।', html)
        html = _re_t.sub(
            r'Use (.+?) with some caution\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'\1 का उपयोग सावधानी से करें। \1 एक \2 है जिसका Nerq विश्वास स्कोर \3/100 (\4) है।', html)
        html = _re_t.sub(
            r'Exercise caution with (.+?)\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'\1 के साथ सावधानी बरतें। \1 एक \2 है जिसका Nerq विश्वास स्कोर \3/100 (\4) है।', html)

        # 2. Short answer box
        html = html.replace('<strong>YES</strong>', '<strong>हां</strong>')
        html = html.replace('<strong>CAUTION</strong>', '<strong>सावधानी</strong>')
        html = html.replace('<strong>NO — USE WITH CAUTION</strong>', '<strong>नहीं — सावधानी से उपयोग करें</strong>')

        # 3. Citation detail / verdict detail
        html = html.replace("It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption", 'सुरक्षा, रखरखाव और सामुदायिक स्वीकृति में मजबूत संकेतों के साथ Nerq विश्वास सीमा को पूरा करता है')
        html = html.replace('It has moderate trust signals but shows some areas of concern that warrant attention', 'मध्यम विश्वास संकेत हैं, लेकिन ध्यान देने योग्य कुछ चिंताजनक क्षेत्र भी हैं')
        html = html.replace('It has below-average trust signals with significant gaps in security, maintenance, or documentation', 'सुरक्षा, रखरखाव या दस्तावेज़ीकरण में महत्वपूर्ण अंतराल के साथ औसत से कम विश्वास संकेत हैं')
        html = html.replace('Recommended for production use', 'प्रोडक्शन उपयोग के लिए अनुशंसित')
        html = html.replace('It is recommended for production use.', 'प्रोडक्शन उपयोग के लिए अनुशंसित है।')
        html = html.replace('review the full report below for specific considerations', 'विशिष्ट विचारों के लिए नीचे पूरी रिपोर्ट देखें')
        html = html.replace('Suitable for development use', 'डेवलपमेंट उपयोग के लिए उपयुक्त')
        html = html.replace('review security and maintenance signals before production deployment', 'प्रोडक्शन तैनाती से पहले सुरक्षा और रखरखाव संकेतों की जांच करें')
        html = html.replace('Not recommended for production use without thorough manual review and additional security measures', 'पूरी मैनुअल समीक्षा और अतिरिक्त सुरक्षा उपायों के बिना प्रोडक्शन उपयोग के लिए अनुशंसित नहीं')
        html = html.replace('It is below the recommended threshold of 70.', 'यह अनुशंसित सीमा 70 से नीचे है।')

        # 4. "X is a Y — description"
        html = _re_t.sub(r'>(.+?) is a (Node\.js package|Python package|Rust crate|Chrome extension|WordPress plugin|VPN service|game|website|SaaS platform|Firefox extension|VS Code extension|iOS app|Android app) — ',
                         r'>\1 \2 — ', html)

        # 5. Entity type translations in body text
        html = html.replace('is a Node.js package', 'एक Node.js पैकेज है')
        html = html.replace('is a Python package', 'एक Python पैकेज है')
        html = html.replace('is a Rust crate', 'एक Rust crate है')
        html = html.replace('is a Chrome extension', 'एक Chrome एक्सटेंशन है')
        html = html.replace('is a WordPress plugin', 'एक WordPress प्लगइन है')
        html = html.replace('is a VPN service', 'एक VPN सेवा है')
        html = html.replace('is a iOS app', 'एक iOS ऐप है')
        html = html.replace('is a Android app', 'एक Android ऐप है')

        # 6. Safety guide text
        html = html.replace("to check for vulnerabilities. Review the package's GitHub repository for recent commits.", 'कमजोरियों की जांच के लिए। हालिया कमिट के लिए पैकेज का GitHub रिपॉजिटरी देखें।')
        html = html.replace('You can also check the trust score via API:', 'आप API के माध्यम से भी विश्वास स्कोर जांच सकते हैं:')
        html = html.replace('watch for:', 'ध्यान रखें:')
        html = html.replace('dependency vulnerabilities, malicious packages, typosquatting', 'निर्भरता कमजोरियां, दुर्भावनापूर्ण पैकेज, typosquatting')
        html = html.replace("Run your package manager's audit command regularly.", 'अपने पैकेज मैनेजर का audit कमांड नियमित रूप से चलाएं।')
        html = html.replace('>Run <code>', '>चलाएं <code>')

        # 7. King sections — privacy/security
        html = _re_t.sub(r'(.+?) is a Node\.js package maintained by (.+?)\.', r'\1, \2 द्वारा अनुरक्षित एक Node.js पैकेज है।', html)
        html = _re_t.sub(r'(.+?) is a (.+?) maintained by (.+?)\.', r'\1, \3 द्वारा अनुरक्षित \2 है।', html)
        html = html.replace(' maintained by ', ' द्वारा अनुरक्षित ')
        html = html.replace('As a development package,', 'एक डेवलपमेंट पैकेज के रूप में,')
        html = html.replace('does not directly collect end-user personal data', 'अंतिम-उपयोगकर्ता का व्यक्तिगत डेटा सीधे एकत्र नहीं करता')
        html = html.replace('However, applications built with it may collect data depending on implementation', 'हालांकि, इससे बनाए गए एप्लिकेशन कार्यान्वयन के आधार पर डेटा एकत्र कर सकते हैं')
        html = html.replace("Review the package's dependencies for potential supply chain risks.", 'संभावित आपूर्ति श्रृंखला जोखिमों के लिए पैकेज की निर्भरताओं की जांच करें।')
        html = html.replace('License information not available.', 'लाइसेंस जानकारी उपलब्ध नहीं।')
        html = html.replace('Open-source packages allow independent security review of the source code.', 'ओपन-सोर्स पैकेज स्रोत कोड की स्वतंत्र सुरक्षा समीक्षा की अनुमति देते हैं।')
        html = html.replace('known vulnerabilities (CVEs) in the National Vulnerability Database', 'राष्ट्रीय कमजोरी डेटाबेस में ज्ञात कमजोरियां (CVEs)')
        html = html.replace('This is a clean record.', 'यह एक स्वच्छ रिकॉर्ड है।')
        html = html.replace('Review advisories and update to the latest version.', 'सलाह की समीक्षा करें और नवीनतम संस्करण में अपडेट करें।')

        html = html.replace('and has not yet reached Nerq trust threshold (70+).', 'और अभी तक Nerq विश्वास सीमा (70+) तक नहीं पहुंचा है।')
        html = html.replace('and meets Nerq trust threshold', 'और Nerq विश्वास सीमा को पूरा करता है')
        html = html.replace('This score is based on automated analysis of security, maintenance, community, and quality signals.', 'यह स्कोर सुरक्षा, रखरखाव, समुदाय और गुणवत्ता संकेतों के स्वचालित विश्लेषण पर आधारित है।')

        # 8. Methodology
        html = html.replace('using the same methodology, enabling direct cross-entity comparison', 'एक ही कार्यप्रणाली का उपयोग करके, इकाइयों के बीच सीधी तुलना संभव बनाता है')
        html = html.replace('Scores are updated continuously as new data becomes available', 'नया डेटा उपलब्ध होने पर स्कोर लगातार अपडेट किए जाते हैं')
        html = html.replace('is computed from', 'से गणना की गई है:')
        html = html.replace('The score reflects', 'स्कोर प्रतिबिंबित करता है:')
        html = html.replace('independent dimensions', 'स्वतंत्र आयाम')
        html = html.replace('Each dimension is weighted equally to produce the composite trust score.', 'समग्र विश्वास स्कोर बनाने के लिए प्रत्येक आयाम को समान भार दिया गया है।')

        # 9. Key findings / signal descriptions
        html = html.replace('Composite trust score:', 'समग्र विश्वास स्कोर:')
        html = html.replace('across all available signals', 'सभी उपलब्ध संकेतों में')
        html = html.replace('Code quality, vulnerability exposure, and security practices.', 'कोड गुणवत्ता, कमजोरी एक्सपोजर और सुरक्षा प्रथाएं।')
        html = html.replace('Update frequency, issue responsiveness, active development.', 'अपडेट आवृत्ति, समस्या प्रतिक्रिया, सक्रिय विकास।')
        html = html.replace('README quality, API docs, usage examples.', 'README गुणवत्ता, API दस्तावेज़, उपयोग उदाहरण।')
        html = html.replace('Community adoption.', 'सामुदायिक स्वीकृति।')
        html = html.replace('Composite score across all trust dimensions.', 'सभी विश्वास आयामों में समग्र स्कोर।')

        # 10. FAQ answers
        html = html.replace('Yes, it is safe to use.', 'हां, यह उपयोग के लिए सुरक्षित है।')
        html = html.replace('Use with some caution.', 'सावधानी से उपयोग करें।')
        html = html.replace('Exercise caution.', 'सावधानी बरतें।')
        html = html.replace('Significant trust concerns.', 'महत्वपूर्ण विश्वास संबंधी चिंताएं।')
        html = html.replace('Strongest signal:', 'सबसे मजबूत संकेत:')
        html = html.replace('Score based on', 'स्कोर आधारित')
        html = html.replace('multiple trust dimensions', 'कई विश्वास आयाम')
        html = html.replace('Scores update as new data becomes available.', 'नया डेटा उपलब्ध होने पर स्कोर अपडेट होते हैं।')
        html = html.replace('check back soon', 'जल्द ही वापस देखें')
        html = html.replace('higher-rated alternatives include', 'उच्च-रेटेड विकल्पों में शामिल हैं:')
        html = html.replace('more Node.js packages are being analyzed', 'अधिक Node.js पैकेज का विश्लेषण किया जा रहा है')
        html = html.replace('more Python packages are being analyzed', 'अधिक Python पैकेज का विश्लेषण किया जा रहा है')
        html = html.replace('Meets Nerq Verified threshold.', 'Nerq सत्यापित सीमा को पूरा करता है।')

        # 11. Security check FAQ
        html = html.replace('Nerq checks', 'Nerq जांच करता है')
        html = html.replace('against NVD, OSV.dev, and registry-specific vulnerability databases', 'NVD, OSV.dev और रजिस्ट्री-विशिष्ट कमजोरी डेटाबेस के विरुद्ध')
        html = html.replace('Current security score:', 'वर्तमान सुरक्षा स्कोर:')
        html = html.replace("Run your package manager's audit command for the latest findings.", 'नवीनतम निष्कर्षों के लिए अपने पैकेज मैनेजर का audit कमांड चलाएं।')
        html = html.replace('has a trust score of', 'का विश्वास स्कोर है')
        html = html.replace('has a Nerq Trust Score of', 'का Nerq विश्वास स्कोर है')

        # 12. Footer bottom
        html = html.replace('trust scores for all software', 'सभी सॉफ्टवेयर के लिए विश्वास स्कोर')
        html = html.replace('7.5M+ entities', '7.5 मिलियन+ इकाइयां')
        html = html.replace('26 registries', '26 रजिस्ट्री')

        # 13. og:description
        html = html.replace('Independent safety assessment by Nerq.', 'Nerq द्वारा स्वतंत्र सुरक्षा मूल्यांकन।')
        html = html.replace('Independent safety assessment by Nerq', 'Nerq द्वारा स्वतंत्र सुरक्षा मूल्यांकन')

        # 14. Breadcrumb in JSON-LD
        html = html.replace('"Safety Reports"', '"सुरक्षा रिपोर्ट"')

        # 15. FAQ questions (in <summary> and JSON-LD)
        html = _re_t.sub(r"What is (.+?)'s trust score\?", r'\1 का विश्वास स्कोर क्या है?', html)
        html = _re_t.sub(r'Is (.+?) safe to use\?', r'क्या \1 उपयोग के लिए सुरक्षित है?', html)
        html = _re_t.sub(r'Is (.+?) safe\?', r'क्या \1 सुरक्षित है?', html)
        html = _re_t.sub(r'What are safer alternatives to (.+?)\?', r'\1 के अधिक सुरक्षित विकल्प क्या हैं?', html)
        html = _re_t.sub(r'Does (.+?) have known vulnerabilities\?', r'क्या \1 में ज्ञात कमजोरियां हैं?', html)
        html = _re_t.sub(r'How actively maintained is (.+?)\?', r'\1 को कितनी सक्रियता से अनुरक्षित किया जाता है?', html)
        html = _re_t.sub(r'How does (.+?) compare to similar', r'\1 की समान से तुलना कैसे होती है', html)
        html = _re_t.sub(r'Can I use (.+?) in a regulated environment\?', r'क्या मैं \1 को विनियमित वातावरण में उपयोग कर सकता हूं?', html)

        # 16. FAQ answer fragments
        html = html.replace('In the npm category,', 'npm श्रेणी में,')
        html = html.replace('In the pypi category,', 'pypi श्रेणी में,')
        html = html.replace('In the crates category,', 'crates श्रेणी में,')
        html = _re_t.sub(r'In the (\w+) category,', r'\1 श्रेणी में,', html)
        html = _re_t.sub(r'(.+?) scores ([\d.]+)/100\.', r'\1 का स्कोर \2/100 है।', html)

        # 17. "has a Trust Score of" in king sections
        html = _re_t.sub(r'(.+?) has a Trust Score of', r'\1 का विश्वास स्कोर है', html)

        # 18. Security king section fragments
        html = html.replace('Security score:', 'सुरक्षा स्कोर:')
        html = html.replace('Privacy score:', 'गोपनीयता स्कोर:')
        html = html.replace('to check for known vulnerabilities in your dependency tree', 'अपनी निर्भरता वृक्ष में ज्ञात कमजोरियों की जांच के लिए')

        # 19. Meta description
        html = html.replace('0 known vulnerabilities', '0 ज्ञात कमजोरियां')
        html = html.replace('License: See repository', 'लाइसेंस: रिपॉजिटरी देखें')
        html = html.replace('Independent security analysis of', 'स्वतंत्र सुरक्षा विश्लेषण:')
        html = html.replace('trust signals, vulnerabilities, compliance, and safer alternatives', 'विश्वास संकेत, कमजोरियां, अनुपालन और अधिक सुरक्षित विकल्प')

        # 20. og:description
        html = html.replace('trust grade,', 'विश्वास ग्रेड,')
        html = html.replace('por Nerq', 'Nerq द्वारा')
        html = html.replace('oleh Nerq', 'Nerq द्वारा')
        html = html.replace('od Nerq', 'Nerq द्वारा')
        html = html.replace('Nerq tarafından', 'Nerq द्वारा')
        html = html.replace('by Nerq', 'Nerq द्वारा')

        # 21. Fix Schema.org @type that got wrongly translated by _CONTENT_TRANSLATIONS
        html = html.replace('"@type": "समीक्षा"', '"@type": "Review"')
        html = html.replace('"@type":"समीक्षा"', '"@type":"Review"')
        # reviewBody translation
        html = html.replace('with a Nerq Trust Score of', 'Nerq विश्वास स्कोर के साथ')
        html = html.replace('Proceed with caution.', 'सावधानी से आगे बढ़ें।')
        html = html.replace('Not recommended.', 'अनुशंसित नहीं।')
        # JSON-LD
        html = _re_t.sub(r'"name": "Is (.+?) Safe\?', r'"name": "क्या \1 सुरक्षित है?', html)
        html = _re_t.sub(r'"name": "Is (.+?) Safe to Visit\?', r'"name": "क्या \1 पर जाना सुरक्षित है?', html)
        html = _re_t.sub(r'og:title" content="Is (.+?) Safe\?', r'og:title" content="क्या \1 सुरक्षित है?', html)
        html = _re_t.sub(r'nerq:question" content="Is (.+?) safe', r'nerq:question" content="क्या \1 सुरक्षित', html)

        # Fix: License
        html = html.replace('License: Not specified', 'लाइसेंस: निर्दिष्ट नहीं')
        html = html.replace('License: See repository', 'लाइसेंस: रिपॉजिटरी देखें')
        # Fix: FAQ Q2 — trust score question
        html = _re_t.sub(r"What is (.+?)'s trust score\?", r'\1 का विश्वास स्कोर क्या है?', html)
        # Fix: Footer remaining English
        html = html.replace('dimensions. Data from', 'आयाम। डेटा:')
        html = html.replace('Data from', 'डेटा:')

    elif lang == "ru":
        import re as _re_t
        html = _re_t.sub(r'<title>Is (.+?) Safe\?', r'<title>Безопасен ли \1?', html, count=1)
        html = html.replace('Independent Trust &amp; Security Analysis 2026 | Nerq', 'Независимый анализ доверия и безопасности 2026 | Nerq')
        html = _re_t.sub(r'>Is (.+?) Safe\?<', r'>Безопасен ли \1?<', html)
        html = _re_t.sub(r'>Is (.+?) safe\?<', r'>Безопасен ли \1?<', html)
        html = _re_t.sub(r'>What data does (.+?) collect\?<', r'>Какие данные собирает \1?<', html)
        html = _re_t.sub(r'>Is (.+?) secure\?<', r'>Безопасен ли \1?<', html)
        html = _re_t.sub(r'>(.+?) Across Platforms<', r'>\1 на других платформах<', html)
        html = _re_t.sub(r'>Safety Guide: (.+?)<', r'>Руководство по безопасности: \1<', html)
        html = _re_t.sub(r'>What is (.+?)\?<', r'>Что такое \1?<', html)
        html = html.replace('>Details<', '>Подробности<')
        html = _re_t.sub(r'>Is (.+?) Safe to Visit\?', r'>Безопасно ли посещать \1?', html)
        html = _re_t.sub(r'>Is (.+?) safe for solo travelers\?<', r'>Безопасен ли \1 для одиночных путешественников?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for women\?<', r'>Безопасен ли \1 для женщин?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for LGBTQ\+ travelers\?<', r'>Безопасен ли \1 для LGBTQ+ путешественников?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for families\?<', r'>Безопасен ли \1 для семей?<', html)
        html = _re_t.sub(r'>Is (.+?) safe to visit right now\?<', r'>Безопасно ли посещать \1 прямо сейчас?<', html)
        html = _re_t.sub(r'>Is tap water safe to drink in (.+?)\?<', r'>Безопасна ли водопроводная вода в \1?<', html)
        html = _re_t.sub(r'>Do I need vaccinations for (.+?)\?<', r'>Нужны ли прививки для \1?<', html)
        html = _re_t.sub(r'>What are safer alternatives to (.+?)\?<', r'>Какие более безопасные альтернативы \1?<', html)
        html = _re_t.sub(r'>What are the side effects of (.+?)\?<', r'>Какие побочные эффекты у \1?<', html)
        html = _re_t.sub(r'>Does (.+?) interact with medications\?<', r'>Взаимодействует ли \1 с лекарствами?<', html)
        html = _re_t.sub(r"(.+?)'s trust score of", r'рейтинг доверия \1', html)
        html = _re_t.sub(r'Nerq of (\d)', r'Nerq \1', html)
        html = html.replace('Safety Score', 'Рейтинг безопасности')
        html = html.replace('Trust Analysis 2026', 'Анализ доверия 2026')
        # Nav
        html = html.replace('>Search<', '>Поиск<')
        html = html.replace('>Apps<', '>Приложения<')
        html = html.replace('>Packages<', '>Пакеты<')
        html = html.replace('>Extensions<', '>Расширения<')
        html = html.replace('>Websites<', '>Сайты<')
        html = html.replace('>Travel<', '>Путешествия<')
        html = html.replace('>Charities<', '>Благотворительность<')
        html = html.replace('>Compare<', '>Сравнить<')
        html = html.replace('>Resources<', '>Ресурсы<')
        html = html.replace('>About<', '>О сервисе<')
        html = html.replace('>Check Safety<', '>Проверить безопасность<')
        html = html.replace('>Games<', '>Игры<')
        html = html.replace('>Countries<', '>Страны<')
        html = html.replace('>Check Website<', '>Проверить сайт<')
        html = html.replace('>Safety Guides<', '>Руководства по безопасности<')
        # Footer text
        html = html.replace('Trust scores for software, apps, websites, travel destinations, and charities', 'Рейтинги доверия для программного обеспечения, приложений, сайтов, туристических направлений и благотворительных организаций')
        html = html.replace('20 languages', '20 языков')
        html = html.replace('>Guides<', '>Руководства<')
        html = html.replace('>Mobile Apps<', '>Мобильные приложения<')
        html = html.replace('>Trust Badges<', '>Знаки доверия<')
        html = html.replace('>VPNs<', '>VPN<')
        html = html.replace('7.5M+ entities from 26 registries. Independent. Data-driven.', '7,5 млн+ сущностей из 26 реестров. Независимо. На основе данных.')

        # ── Dynamic paragraph translations ──

        # 1. Verdict lead
        html = _re_t.sub(
            r'Yes, (.+?) is safe to use\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Да, \1 безопасен для использования. \1 — это \2 с рейтингом доверия Nerq \3/100 (\4).', html)
        html = _re_t.sub(
            r'Use (.+?) with some caution\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Используйте \1 с осторожностью. \1 — это \2 с рейтингом доверия Nerq \3/100 (\4).', html)
        html = _re_t.sub(
            r'Exercise caution with (.+?)\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Будьте осторожны с \1. \1 — это \2 с рейтингом доверия Nerq \3/100 (\4).', html)

        # 2. Short answer box
        html = html.replace('<strong>YES</strong>', '<strong>ДА</strong>')
        html = html.replace('<strong>CAUTION</strong>', '<strong>ОСТОРОЖНО</strong>')
        html = html.replace('<strong>NO — USE WITH CAUTION</strong>', '<strong>НЕТ — ИСПОЛЬЗУЙТЕ С ОСТОРОЖНОСТЬЮ</strong>')

        # 3. Citation detail / verdict detail
        html = html.replace("It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption", 'Соответствует порогу доверия Nerq с сильными сигналами в области безопасности, обслуживания и принятия сообществом')
        html = html.replace('It has moderate trust signals but shows some areas of concern that warrant attention', 'Умеренные сигналы доверия, но есть отдельные области, требующие внимания')
        html = html.replace('It has below-average trust signals with significant gaps in security, maintenance, or documentation', 'Сигналы доверия ниже среднего со значительными пробелами в безопасности, обслуживании или документации')
        html = html.replace('Recommended for production use', 'Рекомендуется для использования в продакшене')
        html = html.replace('It is recommended for production use.', 'Рекомендуется для использования в продакшене.')
        html = html.replace('review the full report below for specific considerations', 'ознакомьтесь с полным отчётом ниже для уточнения')
        html = html.replace('Suitable for development use', 'Подходит для разработки')
        html = html.replace('review security and maintenance signals before production deployment', 'проверьте сигналы безопасности и обслуживания перед развёртыванием в продакшене')
        html = html.replace('Not recommended for production use without thorough manual review and additional security measures', 'Не рекомендуется для продакшена без тщательной ручной проверки и дополнительных мер безопасности')
        html = html.replace('It is below the recommended threshold of 70.', 'Ниже рекомендуемого порога в 70.')

        # 4. "X is a Y — description"
        html = _re_t.sub(r'>(.+?) is a (Node\.js package|Python package|Rust crate|Chrome extension|WordPress plugin|VPN service|game|website|SaaS platform|Firefox extension|VS Code extension|iOS app|Android app) — ',
                         r'>\1 \2 — ', html)

        # 5. Entity type translations in body text
        html = html.replace('is a Node.js package', '— это пакет Node.js')
        html = html.replace('is a Python package', '— это пакет Python')
        html = html.replace('is a Rust crate', '— это Rust crate')
        html = html.replace('is a Chrome extension', '— это расширение Chrome')
        html = html.replace('is a WordPress plugin', '— это плагин WordPress')
        html = html.replace('is a VPN service', '— это VPN-сервис')
        html = html.replace('is a iOS app', '— это приложение для iOS')
        html = html.replace('is a Android app', '— это приложение для Android')

        # 6. Safety guide text
        html = html.replace("to check for vulnerabilities. Review the package's GitHub repository for recent commits.", 'для проверки уязвимостей. Проверьте репозиторий GitHub пакета на наличие последних коммитов.')
        html = html.replace('You can also check the trust score via API:', 'Вы также можете проверить рейтинг доверия через API:')
        html = html.replace('watch for:', 'обратите внимание на:')
        html = html.replace('dependency vulnerabilities, malicious packages, typosquatting', 'уязвимости зависимостей, вредоносные пакеты, тайпосквоттинг')
        html = html.replace("Run your package manager's audit command regularly.", 'Регулярно запускайте команду аудита вашего менеджера пакетов.')
        html = html.replace('>Run <code>', '>Запустите <code>')

        # 7. King sections — privacy/security
        html = _re_t.sub(r'(.+?) is a Node\.js package maintained by (.+?)\.', r'\1 — это пакет Node.js, поддерживаемый \2.', html)
        html = _re_t.sub(r'(.+?) is a (.+?) maintained by (.+?)\.', r'\1 — это \2, поддерживаемый \3.', html)
        html = html.replace(' maintained by ', ' поддерживается ')
        html = html.replace('As a development package,', 'Как пакет для разработки,')
        html = html.replace('does not directly collect end-user personal data', 'не собирает напрямую персональные данные конечных пользователей')
        html = html.replace('However, applications built with it may collect data depending on implementation', 'Однако приложения, созданные с его помощью, могут собирать данные в зависимости от реализации')
        html = html.replace("Review the package's dependencies for potential supply chain risks.", 'Проверьте зависимости пакета на возможные риски цепочки поставок.')
        html = html.replace('License information not available.', 'Информация о лицензии недоступна.')
        html = html.replace('Open-source packages allow independent security review of the source code.', 'Пакеты с открытым исходным кодом позволяют проводить независимую проверку безопасности кода.')
        html = html.replace('known vulnerabilities (CVEs) in the National Vulnerability Database', 'известные уязвимости (CVEs) в Национальной базе данных уязвимостей')
        html = html.replace('This is a clean record.', 'Нарушений не выявлено.')
        html = html.replace('Review advisories and update to the latest version.', 'Ознакомьтесь с предупреждениями и обновитесь до последней версии.')

        html = html.replace('and has not yet reached Nerq trust threshold (70+).', 'и ещё не достиг порога доверия Nerq (70+).')
        html = html.replace('and meets Nerq trust threshold', 'и соответствует порогу доверия Nerq')
        html = html.replace('This score is based on automated analysis of security, maintenance, community, and quality signals.', 'Этот рейтинг основан на автоматическом анализе сигналов безопасности, обслуживания, сообщества и качества.')

        # 8. Methodology
        html = html.replace('using the same methodology, enabling direct cross-entity comparison', 'используя единую методологию, что позволяет проводить прямое сравнение между сущностями')
        html = html.replace('Scores are updated continuously as new data becomes available', 'Рейтинги обновляются непрерывно по мере поступления новых данных')
        html = html.replace('is computed from', 'вычисляется из:')
        html = html.replace('The score reflects', 'Рейтинг отражает:')
        html = html.replace('independent dimensions', 'независимых показателей')
        html = html.replace('Each dimension is weighted equally to produce the composite trust score.', 'Каждый показатель имеет равный вес в сводном рейтинге доверия.')

        # 9. Key findings / signal descriptions
        html = html.replace('Composite trust score:', 'Сводный рейтинг доверия:')
        html = html.replace('across all available signals', 'по всем доступным сигналам')
        html = html.replace('Code quality, vulnerability exposure, and security practices.', 'Качество кода, уязвимости и практики безопасности.')
        html = html.replace('Update frequency, issue responsiveness, active development.', 'Частота обновлений, реагирование на проблемы, активная разработка.')
        html = html.replace('README quality, API docs, usage examples.', 'Качество README, документация API, примеры использования.')
        html = html.replace('Community adoption.', 'Принятие сообществом.')
        html = html.replace('Composite score across all trust dimensions.', 'Сводный рейтинг по всем показателям доверия.')

        # 10. FAQ answers
        html = html.replace('Yes, it is safe to use.', 'Да, безопасно использовать.')
        html = html.replace('Use with some caution.', 'Используйте с осторожностью.')
        html = html.replace('Exercise caution.', 'Будьте осторожны.')
        html = html.replace('Significant trust concerns.', 'Серьёзные проблемы с доверием.')
        html = html.replace('Strongest signal:', 'Самый сильный сигнал:')
        html = html.replace('Score based on', 'Рейтинг основан на')
        html = html.replace('multiple trust dimensions', 'нескольких показателях доверия')
        html = html.replace('Scores update as new data becomes available.', 'Рейтинги обновляются по мере поступления новых данных.')
        html = html.replace('check back soon', 'проверьте позже')
        html = html.replace('higher-rated alternatives include', 'альтернативы с более высоким рейтингом:')
        html = html.replace('more Node.js packages are being analyzed', 'больше пакетов Node.js анализируется')
        html = html.replace('more Python packages are being analyzed', 'больше пакетов Python анализируется')
        html = html.replace('Meets Nerq Verified threshold.', 'Соответствует верифицированному порогу Nerq.')

        # 11. Security check FAQ
        html = html.replace('Nerq checks', 'Nerq проверяет')
        html = html.replace('against NVD, OSV.dev, and registry-specific vulnerability databases', 'по базам NVD, OSV.dev и реестровым базам уязвимостей')
        html = html.replace('Current security score:', 'Текущий рейтинг безопасности:')
        html = html.replace("Run your package manager's audit command for the latest findings.", 'Запустите команду аудита вашего менеджера пакетов для получения последних данных.')
        html = html.replace('has a trust score of', 'имеет рейтинг доверия')
        html = html.replace('has a Nerq Trust Score of', 'имеет рейтинг доверия Nerq')

        # 12. Footer bottom
        html = html.replace('trust scores for all software', 'рейтинги доверия для всего программного обеспечения')
        html = html.replace('7.5M+ entities', '7,5 млн+ сущностей')
        html = html.replace('26 registries', '26 реестров')

        # 13. og:description
        html = html.replace('Independent safety assessment by Nerq.', 'Независимая оценка безопасности от Nerq.')
        html = html.replace('Independent safety assessment by Nerq', 'Независимая оценка безопасности от Nerq')

        # 14. Breadcrumb in JSON-LD
        html = html.replace('"Safety Reports"', '"Отчёты о безопасности"')

        # 15. FAQ questions (in <summary> and JSON-LD)
        html = _re_t.sub(r"What is (.+?)'s trust score\?", r'Каков рейтинг доверия \1?', html)
        html = _re_t.sub(r'Is (.+?) safe to use\?', r'Безопасен ли \1 для использования?', html)
        html = _re_t.sub(r'Is (.+?) safe\?', r'Безопасен ли \1?', html)
        html = _re_t.sub(r'What are safer alternatives to (.+?)\?', r'Какие более безопасные альтернативы \1?', html)
        html = _re_t.sub(r'Does (.+?) have known vulnerabilities\?', r'Есть ли у \1 известные уязвимости?', html)
        html = _re_t.sub(r'How actively maintained is (.+?)\?', r'Насколько активно поддерживается \1?', html)
        html = _re_t.sub(r'How does (.+?) compare to similar', r'Как \1 сравнивается с аналогичными', html)
        html = _re_t.sub(r'Can I use (.+?) in a regulated environment\?', r'Можно ли использовать \1 в регулируемой среде?', html)

        # 16. FAQ answer fragments
        html = html.replace('In the npm category,', 'В категории npm,')
        html = html.replace('In the pypi category,', 'В категории pypi,')
        html = html.replace('In the crates category,', 'В категории crates,')
        html = _re_t.sub(r'In the (\w+) category,', r'В категории \1,', html)
        html = _re_t.sub(r'(.+?) scores ([\d.]+)/100\.', r'\1 получает \2/100.', html)

        # 17. "has a Trust Score of" in king sections
        html = _re_t.sub(r'(.+?) has a Trust Score of', r'\1 имеет рейтинг доверия', html)

        # 18. Security king section fragments
        html = html.replace('Security score:', 'Рейтинг безопасности:')
        html = html.replace('Privacy score:', 'Рейтинг конфиденциальности:')
        html = html.replace('to check for known vulnerabilities in your dependency tree', 'для проверки известных уязвимостей в вашем дереве зависимостей')

        # 19. Meta description
        html = html.replace('0 known vulnerabilities', '0 известных уязвимостей')
        html = html.replace('License: See repository', 'Лицензия: см. репозиторий')
        html = html.replace('Independent security analysis of', 'Независимый анализ безопасности:')
        html = html.replace('trust signals, vulnerabilities, compliance, and safer alternatives', 'сигналы доверия, уязвимости, соответствие и более безопасные альтернативы')

        # 20. og:description
        html = html.replace('trust grade,', 'рейтинг доверия,')
        html = html.replace('por Nerq', 'от Nerq')
        html = html.replace('oleh Nerq', 'от Nerq')
        html = html.replace('od Nerq', 'от Nerq')
        html = html.replace('Nerq tarafından', 'от Nerq')
        html = html.replace('द्वारा Nerq', 'от Nerq')
        html = html.replace('by Nerq', 'от Nerq')

        # 21. Fix Schema.org @type that got wrongly translated by _CONTENT_TRANSLATIONS
        html = html.replace('"@type": "Отзыв"', '"@type": "Review"')
        html = html.replace('"@type":"Отзыв"', '"@type":"Review"')
        # reviewBody translation
        html = html.replace('with a Nerq Trust Score of', 'с рейтингом доверия Nerq')
        html = html.replace('Proceed with caution.', 'Действуйте с осторожностью.')
        html = html.replace('Not recommended.', 'Не рекомендуется.')
        # JSON-LD
        html = _re_t.sub(r'"name": "Is (.+?) Safe\?', r'"name": "Безопасен ли \1?', html)
        html = _re_t.sub(r'"name": "Is (.+?) Safe to Visit\?', r'"name": "Безопасно ли посещать \1?', html)
        html = _re_t.sub(r'og:title" content="Is (.+?) Safe\?', r'og:title" content="Безопасен ли \1?', html)
        html = _re_t.sub(r'nerq:question" content="Is (.+?) safe', r'nerq:question" content="Безопасен ли \1', html)

        # Fix: License
        html = html.replace('License: Not specified', 'Лицензия: не указана')
        html = html.replace('License: See repository', 'Лицензия: см. репозиторий')
        # Fix: FAQ Q2 — trust score question
        html = _re_t.sub(r"What is (.+?)'s trust score\?", r'Каков рейтинг доверия \1?', html)
        # Fix: Footer remaining English
        html = html.replace('dimensions. Data from', 'показателей. Данные из')
        html = html.replace('Data from', 'Данные из')

    elif lang == "pl":
        import re as _re_t
        html = _re_t.sub(r'<title>Is (.+?) Safe\?', r'<title>Czy \1 jest bezpieczny?', html, count=1)
        html = html.replace('Independent Trust &amp; Security Analysis 2026 | Nerq', 'Niezależna analiza zaufania i bezpieczeństwa 2026 | Nerq')
        html = _re_t.sub(r'>Is (.+?) Safe\?<', r'>Czy \1 jest bezpieczny?<', html)
        html = _re_t.sub(r'>Is (.+?) safe\?<', r'>Czy \1 jest bezpieczny?<', html)
        html = _re_t.sub(r'>What data does (.+?) collect\?<', r'>Jakie dane zbiera \1?<', html)
        html = _re_t.sub(r'>Is (.+?) secure\?<', r'>Czy \1 jest bezpieczny?<', html)
        html = _re_t.sub(r'>(.+?) Across Platforms<', r'>\1 na innych platformach<', html)
        html = _re_t.sub(r'>Safety Guide: (.+?)<', r'>Przewodnik bezpieczeństwa: \1<', html)
        html = _re_t.sub(r'>What is (.+?)\?<', r'>Czym jest \1?<', html)
        html = html.replace('>Details<', '>Szczegóły<')
        html = _re_t.sub(r'>Is (.+?) Safe to Visit\?', r'>Czy \1 jest bezpieczne do odwiedzenia?', html)
        html = _re_t.sub(r'>Is (.+?) safe for solo travelers\?<', r'>Czy \1 jest bezpieczne dla podróżników indywidualnych?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for women\?<', r'>Czy \1 jest bezpieczne dla kobiet?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for LGBTQ\+ travelers\?<', r'>Czy \1 jest bezpieczne dla podróżników LGBTQ+?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for families\?<', r'>Czy \1 jest bezpieczne dla rodzin?<', html)
        html = _re_t.sub(r'>Is (.+?) safe to visit right now\?<', r'>Czy \1 jest teraz bezpieczne do odwiedzenia?<', html)
        html = _re_t.sub(r'>Is tap water safe to drink in (.+?)\?<', r'>Czy woda z kranu w \1 jest bezpieczna do picia?<', html)
        html = _re_t.sub(r'>Do I need vaccinations for (.+?)\?<', r'>Czy potrzebuję szczepień na \1?<', html)
        html = _re_t.sub(r'>What are safer alternatives to (.+?)\?<', r'>Jakie są bezpieczniejsze alternatywy dla \1?<', html)
        html = _re_t.sub(r'>What are the side effects of (.+?)\?<', r'>Jakie są skutki uboczne \1?<', html)
        html = _re_t.sub(r'>Does (.+?) interact with medications\?<', r'>Czy \1 wchodzi w interakcje z lekami?<', html)
        html = _re_t.sub(r"(.+?)'s trust score of", r'wynik zaufania \1', html)
        html = _re_t.sub(r'Nerq of (\d)', r'Nerq \1', html)
        html = html.replace('Trust Score Breakdown', 'Szczegóły wyniku zaufania')
        html = html.replace('Trust Score', 'Wynik zaufania')
        html = html.replace('Safety Score Breakdown', 'Szczegóły wyniku bezpieczeństwa')
        html = html.replace('Safety Score', 'Wynik bezpieczeństwa')
        html = html.replace('Trust Analysis 2026', 'Analiza zaufania 2026')
        # Nav
        html = html.replace('>Search<', '>Szukaj<')
        html = html.replace('>Apps<', '>Aplikacje<')
        html = html.replace('>Packages<', '>Pakiety<')
        html = html.replace('>Extensions<', '>Rozszerzenia<')
        html = html.replace('>Websites<', '>Strony<')
        html = html.replace('>Travel<', '>Podróże<')
        html = html.replace('>Charities<', '>Organizacje charytatywne<')
        html = html.replace('>Compare<', '>Porównaj<')
        html = html.replace('>Resources<', '>Zasoby<')
        html = html.replace('>About<', '>O serwisie<')
        html = html.replace('>Check Safety<', '>Sprawdź bezpieczeństwo<')
        html = html.replace('>Games<', '>Gry<')
        html = html.replace('>Countries<', '>Kraje<')
        html = html.replace('>Check Website<', '>Sprawdź stronę<')
        html = html.replace('>Safety Guides<', '>Przewodniki bezpieczeństwa<')
        # Footer text
        html = html.replace('Trust scores for software, apps, websites, travel destinations, and charities', 'Wyniki zaufania dla oprogramowania, aplikacji, stron internetowych, miejsc podróży i organizacji charytatywnych')
        html = html.replace('20 languages', '20 języków')
        html = html.replace('>Guides<', '>Przewodniki<')
        html = html.replace('>Mobile Apps<', '>Aplikacje mobilne<')
        html = html.replace('>Trust Badges<', '>Znaki zaufania<')
        html = html.replace('>VPNs<', '>VPN<')
        html = html.replace('7.5M+ entities from 26 registries. Independent. Data-driven.', 'Ponad 7,5 mln podmiotów z 26 rejestrów. Niezależne. Oparte na danych.')

        # ── Dynamic paragraph translations ──

        # 1. Verdict lead
        html = _re_t.sub(
            r'Yes, (.+?) is safe to use\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Tak, \1 jest bezpieczny w użyciu. \1 to \2 z wynikiem zaufania Nerq \3/100 (\4).', html)
        html = _re_t.sub(
            r'Use (.+?) with some caution\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Używaj \1 z ostrożnością. \1 to \2 z wynikiem zaufania Nerq \3/100 (\4).', html)
        html = _re_t.sub(
            r'Exercise caution with (.+?)\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Zachowaj ostrożność z \1. \1 to \2 z wynikiem zaufania Nerq \3/100 (\4).', html)

        # 2. Short answer box
        html = html.replace('<strong>YES</strong>', '<strong>TAK</strong>')
        html = html.replace('<strong>CAUTION</strong>', '<strong>OSTROŻNOŚĆ</strong>')
        html = html.replace('<strong>NO — USE WITH CAUTION</strong>', '<strong>NIE — UŻYWAJ Z OSTROŻNOŚCIĄ</strong>')

        # 3. Citation detail / verdict detail
        html = html.replace("It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption", 'Spełnia próg zaufania Nerq z silnymi sygnałami w zakresie bezpieczeństwa, konserwacji i przyjęcia przez społeczność')
        html = html.replace('It has moderate trust signals but shows some areas of concern that warrant attention', 'Ma umiarkowane sygnały zaufania, ale wykazuje pewne obszary budzące uwagę')
        html = html.replace('It has below-average trust signals with significant gaps in security, maintenance, or documentation', 'Ma poniżej przeciętne sygnały zaufania ze znaczącymi lukami w zakresie bezpieczeństwa, konserwacji lub dokumentacji')
        html = html.replace('Recommended for production use', 'Zalecany do użytku produkcyjnego')
        html = html.replace('It is recommended for production use.', 'Zalecany do użytku produkcyjnego.')
        html = html.replace('review the full report below for specific considerations', 'zapoznaj się z pełnym raportem poniżej, aby uzyskać szczegółowe informacje')
        html = html.replace('Suitable for development use', 'Nadaje się do użytku deweloperskiego')
        html = html.replace('review security and maintenance signals before production deployment', 'sprawdź sygnały bezpieczeństwa i konserwacji przed wdrożeniem produkcyjnym')
        html = html.replace('Not recommended for production use without thorough manual review and additional security measures', 'Niezalecany do użytku produkcyjnego bez dokładnego ręcznego przeglądu i dodatkowych środków bezpieczeństwa')
        html = html.replace('It is below the recommended threshold of 70.', 'Jest poniżej zalecanego progu wynoszącego 70.')

        # 4. "X is a Y — description"
        html = _re_t.sub(r'>(.+?) is a (Node\.js package|Python package|Rust crate|Chrome extension|WordPress plugin|VPN service|game|website|SaaS platform|Firefox extension|VS Code extension|iOS app|Android app) — ',
                         r'>\1 \2 — ', html)

        # 5. Entity type translations in body text
        html = html.replace('is a Node.js package', 'to pakiet Node.js')
        html = html.replace('is a Python package', 'to pakiet Python')
        html = html.replace('is a Rust crate', 'to biblioteka Rust')
        html = html.replace('is a Chrome extension', 'to rozszerzenie Chrome')
        html = html.replace('is a WordPress plugin', 'to wtyczka WordPress')
        html = html.replace('is a VPN service', 'to usługa VPN')
        html = html.replace('is a iOS app', 'to aplikacja iOS')
        html = html.replace('is a Android app', 'to aplikacja Android')

        # 6. Safety guide text
        html = html.replace("to check for vulnerabilities. Review the package's GitHub repository for recent commits.", 'aby sprawdzić podatności. Sprawdź repozytorium GitHub pakietu pod kątem ostatnich zatwierdzeń.')
        html = html.replace('You can also check the trust score via API:', 'Możesz również sprawdzić wynik zaufania przez API:')
        html = html.replace('watch for:', 'zwróć uwagę na:')
        html = html.replace('dependency vulnerabilities, malicious packages, typosquatting', 'podatności zależności, złośliwe pakiety, typosquatting')
        html = html.replace("Run your package manager's audit command regularly.", 'Regularnie uruchamiaj polecenie audytu menedżera pakietów.')
        html = html.replace('>Run <code>', '>Uruchom <code>')

        # 7. King sections — privacy/security
        html = _re_t.sub(r'(.+?) is a Node\.js package maintained by (.+?)\.', r'\1 to pakiet Node.js utrzymywany przez \2.', html)
        html = _re_t.sub(r'(.+?) is a (.+?) maintained by (.+?)\.', r'\1 to \2 utrzymywany przez \3.', html)
        html = html.replace(' maintained by ', ' utrzymywany przez ')
        html = html.replace('As a development package,', 'Jako pakiet deweloperski,')
        html = html.replace('does not directly collect end-user personal data', 'nie zbiera bezpośrednio danych osobowych użytkowników końcowych')
        html = html.replace('However, applications built with it may collect data depending on implementation', 'Jednak aplikacje zbudowane przy jego użyciu mogą zbierać dane w zależności od implementacji')
        html = html.replace("Review the package's dependencies for potential supply chain risks.", 'Sprawdź zależności pakietu pod kątem potencjalnych zagrożeń w łańcuchu dostaw.')
        html = html.replace('License information not available.', 'Informacje o licencji niedostępne.')
        html = html.replace('Open-source packages allow independent security review of the source code.', 'Pakiety open-source umożliwiają niezależny przegląd bezpieczeństwa kodu źródłowego.')
        html = html.replace('known vulnerabilities (CVEs) in the National Vulnerability Database', 'znane podatności (CVE) w Krajowej Bazie Danych Podatności')
        html = html.replace('This is a clean record.', 'Brak stwierdzonych naruszeń.')
        html = html.replace('Review advisories and update to the latest version.', 'Zapoznaj się z ostrzeżeniami i zaktualizuj do najnowszej wersji.')

        html = html.replace('and has not yet reached Nerq trust threshold (70+).', 'i nie osiągnął jeszcze progu zaufania Nerq (70+).')
        html = html.replace('and meets Nerq trust threshold', 'i spełnia próg zaufania Nerq')
        html = html.replace('This score is based on automated analysis of security, maintenance, community, and quality signals.', 'Ten wynik jest oparty na zautomatyzowanej analizie sygnałów bezpieczeństwa, konserwacji, społeczności i jakości.')

        # 8. Methodology
        html = html.replace('using the same methodology, enabling direct cross-entity comparison', 'przy użyciu tej samej metodologii, umożliwiając bezpośrednie porównanie między podmiotami')
        html = html.replace('Scores are updated continuously as new data becomes available', 'Wyniki są na bieżąco aktualizowane w miarę dostępności nowych danych')
        html = html.replace('is computed from', 'jest obliczany z:')
        html = html.replace('The score reflects', 'Wynik odzwierciedla:')
        html = html.replace('independent dimensions', 'niezależnych wymiarów')
        html = html.replace('Each dimension is weighted equally to produce the composite trust score.', 'Każdy wymiar ma równą wagę w łącznym wyniku zaufania.')

        # 9. Key findings / signal descriptions
        html = html.replace('Composite trust score:', 'Łączny wynik zaufania:')
        html = html.replace('across all available signals', 'ze wszystkich dostępnych sygnałów')
        html = html.replace('Code quality, vulnerability exposure, and security practices.', 'Jakość kodu, podatności i praktyki bezpieczeństwa.')
        html = html.replace('Update frequency, issue responsiveness, active development.', 'Częstotliwość aktualizacji, reagowanie na zgłoszenia, aktywny rozwój.')
        html = html.replace('README quality, API docs, usage examples.', 'Jakość README, dokumentacja API, przykłady użycia.')
        html = html.replace('Community adoption.', 'Przyjęcie przez społeczność.')
        html = html.replace('Composite score across all trust dimensions.', 'Łączny wynik we wszystkich wymiarach zaufania.')

        # 10. FAQ answers
        html = html.replace('Yes, it is safe to use.', 'Tak, jest bezpieczny w użyciu.')
        html = html.replace('Use with some caution.', 'Używaj z ostrożnością.')
        html = html.replace('Exercise caution.', 'Zachowaj ostrożność.')
        html = html.replace('Significant trust concerns.', 'Poważne problemy z zaufaniem.')
        html = html.replace('Strongest signal:', 'Najsilniejszy sygnał:')
        html = html.replace('Score based on', 'Wynik oparty na')
        html = html.replace('multiple trust dimensions', 'wielu wymiarach zaufania')
        html = html.replace('Scores update as new data becomes available.', 'Wyniki są aktualizowane wraz z pojawianiem się nowych danych.')
        html = html.replace('check back soon', 'sprawdź ponownie wkrótce')
        html = html.replace('higher-rated alternatives include', 'alternatywy z wyższym wynikiem to:')
        html = html.replace('more Node.js packages are being analyzed', 'więcej pakietów Node.js jest analizowanych')
        html = html.replace('more Python packages are being analyzed', 'więcej pakietów Python jest analizowanych')
        html = html.replace('Meets Nerq Verified threshold.', 'Spełnia zweryfikowany próg Nerq.')

        # 11. Security check FAQ
        html = html.replace('Nerq checks', 'Nerq sprawdza')
        html = html.replace('against NVD, OSV.dev, and registry-specific vulnerability databases', 'względem NVD, OSV.dev i rejestrowych baz danych podatności')
        html = html.replace('Current security score:', 'Aktualny wynik bezpieczeństwa:')
        html = html.replace("Run your package manager's audit command for the latest findings.", 'Uruchom polecenie audytu menedżera pakietów, aby uzyskać najnowsze wyniki.')
        html = html.replace('has a trust score of', 'ma wynik zaufania')
        html = html.replace('has a Nerq Trust Score of', 'ma wynik zaufania Nerq')

        # 12. Footer bottom
        html = html.replace('trust scores for all software', 'wyniki zaufania dla całego oprogramowania')
        html = html.replace('7.5M+ entities', 'Ponad 7,5 mln podmiotów')
        html = html.replace('26 registries', '26 rejestrów')

        # 13. og:description
        html = html.replace('Independent safety assessment by Nerq.', 'Niezależna ocena bezpieczeństwa przez Nerq.')
        html = html.replace('Independent safety assessment by Nerq', 'Niezależna ocena bezpieczeństwa przez Nerq')

        # 14. Breadcrumb in JSON-LD
        html = html.replace('"Safety Reports"', '"Raporty bezpieczeństwa"')

        # 15. FAQ questions (in <summary> and JSON-LD)
        html = _re_t.sub(r"What is (.+?)'s trust score\?", r'Jaki jest wynik zaufania \1?', html)
        html = _re_t.sub(r'Is (.+?) safe to use\?', r'Czy \1 jest bezpieczny w użyciu?', html)
        html = _re_t.sub(r'Is (.+?) safe\?', r'Czy \1 jest bezpieczny?', html)
        html = _re_t.sub(r'What are safer alternatives to (.+?)\?', r'Jakie są bezpieczniejsze alternatywy dla \1?', html)
        html = _re_t.sub(r'Does (.+?) have known vulnerabilities\?', r'Czy \1 ma znane podatności?', html)
        html = _re_t.sub(r'How actively maintained is (.+?)\?', r'Jak aktywnie utrzymywany jest \1?', html)
        html = _re_t.sub(r'How does (.+?) compare to similar', r'Jak \1 wypada w porównaniu z podobnymi', html)
        html = _re_t.sub(r'Can I use (.+?) in a regulated environment\?', r'Czy mogę używać \1 w środowisku regulowanym?', html)

        # 16. FAQ answer fragments
        html = html.replace('In the npm category,', 'W kategorii npm,')
        html = html.replace('In the pypi category,', 'W kategorii pypi,')
        html = html.replace('In the crates category,', 'W kategorii crates,')
        html = _re_t.sub(r'In the (\w+) category,', r'W kategorii \1,', html)
        html = _re_t.sub(r'(.+?) scores ([\d.]+)/100\.', r'\1 uzyskuje \2/100.', html)

        # 17. "has a Trust Score of" in king sections
        html = _re_t.sub(r'(.+?) has a Trust Score of', r'\1 ma wynik zaufania', html)

        # 18. Security king section fragments
        html = html.replace('Security score:', 'Wynik bezpieczeństwa:')
        html = html.replace('Privacy score:', 'Wynik prywatności:')
        html = html.replace('to check for known vulnerabilities in your dependency tree', 'aby sprawdzić znane podatności w drzewie zależności')

        # 19. Meta description
        html = html.replace('0 known vulnerabilities', '0 znanych podatności')
        html = html.replace('License: See repository', 'Licencja: patrz repozytorium')
        html = html.replace('Independent security analysis of', 'Niezależna analiza bezpieczeństwa:')
        html = html.replace('trust signals, vulnerabilities, compliance, and safer alternatives', 'sygnały zaufania, podatności, zgodność i bezpieczniejsze alternatywy')

        # 20. og:description
        html = html.replace('trust grade,', 'wynik zaufania,')
        html = html.replace('por Nerq', 'przez Nerq')
        html = html.replace('oleh Nerq', 'przez Nerq')
        html = html.replace('od Nerq', 'przez Nerq')
        html = html.replace('Nerq tarafından', 'przez Nerq')
        html = html.replace('द्वारा Nerq', 'przez Nerq')
        html = html.replace('by Nerq', 'przez Nerq')

        # 21. Fix Schema.org @type that got wrongly translated by _CONTENT_TRANSLATIONS
        html = html.replace('"@type": "Opinia"', '"@type": "Review"')
        html = html.replace('"@type":"Opinia"', '"@type":"Review"')
        # reviewBody translation
        html = html.replace('with a Nerq Trust Score of', 'z wynikiem zaufania Nerq')
        html = html.replace('Proceed with caution.', 'Postępuj z ostrożnością.')
        html = html.replace('Not recommended.', 'Niezalecany.')
        # JSON-LD
        html = _re_t.sub(r'"name": "Is (.+?) Safe\?', r'"name": "Czy \1 jest bezpieczny?', html)
        html = _re_t.sub(r'"name": "Is (.+?) Safe to Visit\?', r'"name": "Czy \1 jest bezpieczne do odwiedzenia?', html)
        html = _re_t.sub(r'og:title" content="Is (.+?) Safe\?', r'og:title" content="Czy \1 jest bezpieczny?', html)
        html = _re_t.sub(r'nerq:question" content="Is (.+?) safe', r'nerq:question" content="Czy \1 jest bezpieczny', html)

        # Fix: License
        html = html.replace('License: Not specified', 'Licencja: nie określono')
        html = html.replace('License: See repository', 'Licencja: patrz repozytorium')
        # Fix: FAQ Q2 — trust score question
        html = _re_t.sub(r"What is (.+?)'s trust score\?", r'Jaki jest wynik zaufania \1?', html)
        # Fix: Footer remaining English
        html = html.replace('dimensions. Data from', 'wymiarów. Dane z')
        html = html.replace('Data from', 'Dane z')

    elif lang == "it":
        import re as _re_t
        html = _re_t.sub(r'<title>Is (.+?) Safe\?', r'<title>\1 è sicuro?', html, count=1)
        html = html.replace('Independent Trust &amp; Security Analysis 2026 | Nerq', 'Analisi indipendente di fiducia e sicurezza 2026 | Nerq')
        html = _re_t.sub(r'>Is (.+?) Safe\?<', r'>\1 è sicuro?<', html)
        html = _re_t.sub(r'>Is (.+?) safe\?<', r'>\1 è sicuro?<', html)
        html = _re_t.sub(r'>What data does (.+?) collect\?<', r'>Quali dati raccoglie \1?<', html)
        html = _re_t.sub(r'>Is (.+?) secure\?<', r'>\1 è sicuro?<', html)
        html = _re_t.sub(r'>(.+?) Across Platforms<', r'>\1 su altre piattaforme<', html)
        html = _re_t.sub(r'>Safety Guide: (.+?)<', r'>Guida alla sicurezza: \1<', html)
        html = _re_t.sub(r">What is (.+?)\?<", r">Cos'è \1?<", html)
        html = html.replace('>Details<', '>Dettagli<')
        html = _re_t.sub(r'>Is (.+?) Safe to Visit\?', r'>È sicuro visitare \1?', html)
        html = _re_t.sub(r'>Is (.+?) safe for solo travelers\?<', r'>\1 è sicuro per viaggiatori singoli?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for women\?<', r'>\1 è sicuro per le donne?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for LGBTQ\+ travelers\?<', r'>\1 è sicuro per viaggiatori LGBTQ+?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for families\?<', r'>\1 è sicuro per le famiglie?<', html)
        html = _re_t.sub(r'>Is (.+?) safe to visit right now\?<', r'>È sicuro visitare \1 adesso?<', html)
        html = _re_t.sub(r'>Is tap water safe to drink in (.+?)\?<', r">L'acqua del rubinetto a \1 è sicura da bere?<", html)
        html = _re_t.sub(r'>Do I need vaccinations for (.+?)\?<', r'>Ho bisogno di vaccinazioni per \1?<', html)
        html = _re_t.sub(r'>What are safer alternatives to (.+?)\?<', r'>Quali sono le alternative più sicure a \1?<', html)
        html = _re_t.sub(r'>What are the side effects of (.+?)\?<', r'>Quali sono gli effetti collaterali di \1?<', html)
        html = _re_t.sub(r'>Does (.+?) interact with medications\?<', r'>\1 interagisce con i farmaci?<', html)
        html = _re_t.sub(r"(.+?)'s trust score of", r'punteggio di fiducia di \1 pari a', html)
        html = _re_t.sub(r'Nerq of (\d)', r'Nerq di \1', html)
        html = html.replace('has a Nerq Trust Score of', 'ha un Punteggio di fiducia Nerq di')
        html = html.replace('with a Nerq Trust Score of', 'con un Punteggio di fiducia Nerq di')
        html = html.replace('Trust Score Breakdown', 'Dettagli punteggio di fiducia')
        html = html.replace('Trust Score', 'Punteggio di fiducia')
        html = html.replace('Safety Score Breakdown', 'Dettagli punteggio di sicurezza')
        html = html.replace('Safety Score', 'Punteggio di sicurezza')
        html = html.replace('Trust Analysis 2026', 'Analisi di fiducia 2026')
        # Nav
        html = html.replace('>Search<', '>Cerca<')
        html = html.replace('>Apps<', '>App<')
        html = html.replace('>Packages<', '>Pacchetti<')
        html = html.replace('>Extensions<', '>Estensioni<')
        html = html.replace('>Websites<', '>Siti web<')
        html = html.replace('>Travel<', '>Viaggi<')
        html = html.replace('>Charities<', '>Beneficenza<')
        html = html.replace('>Compare<', '>Confronta<')
        html = html.replace('>Resources<', '>Risorse<')
        html = html.replace('>About<', '>Chi siamo<')
        html = html.replace('>Check Safety<', '>Verifica sicurezza<')
        html = html.replace('>Games<', '>Giochi<')
        html = html.replace('>Countries<', '>Paesi<')
        html = html.replace('>Check Website<', '>Verifica sito web<')
        html = html.replace('>Safety Guides<', '>Guide alla sicurezza<')
        # Footer text
        html = html.replace('Trust scores for software, apps, websites, travel destinations, and charities', 'Punteggi di fiducia per software, app, siti web, destinazioni di viaggio e organizzazioni di beneficenza')
        html = html.replace('20 languages', '20 lingue')
        html = html.replace('>Guides<', '>Guide<')
        html = html.replace('>Mobile Apps<', '>App mobile<')
        html = html.replace('>Trust Badges<', '>Badge di fiducia<')
        html = html.replace('>VPNs<', '>VPN<')
        html = html.replace('7.5M+ entities from 26 registries. Independent. Data-driven.', 'Oltre 7,5 milioni di entità da 26 registri. Indipendente. Basato sui dati.')

        # ── Dynamic paragraph translations ──

        # 1. Verdict lead
        html = _re_t.sub(
            r'Yes, (.+?) is safe to use\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Sì, \1 è sicuro da usare. \1 è \2 con un Punteggio di fiducia Nerq di \3/100 (\4).', html)
        html = _re_t.sub(
            r'Use (.+?) with some caution\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Usa \1 con cautela. \1 è \2 con un Punteggio di fiducia Nerq di \3/100 (\4).', html)
        html = _re_t.sub(
            r'Exercise caution with (.+?)\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Fai attenzione con \1. \1 è \2 con un Punteggio di fiducia Nerq di \3/100 (\4).', html)

        # 2. Short answer box
        html = html.replace('<strong>YES</strong>', '<strong>SÌ</strong>')
        html = html.replace('<strong>CAUTION</strong>', '<strong>CAUTELA</strong>')
        html = html.replace('<strong>NO — USE WITH CAUTION</strong>', '<strong>NO — USA CON CAUTELA</strong>')

        # 3. Citation detail / verdict detail
        html = html.replace("It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption", 'Soddisfa la soglia di fiducia Nerq con segnali forti in sicurezza, manutenzione e adozione della comunità')
        html = html.replace('It has moderate trust signals but shows some areas of concern that warrant attention', 'Ha segnali di fiducia moderati ma mostra alcune aree di preoccupazione che meritano attenzione')
        html = html.replace('It has below-average trust signals with significant gaps in security, maintenance, or documentation', 'Ha segnali di fiducia inferiori alla media con lacune significative in sicurezza, manutenzione o documentazione')
        html = html.replace('Recommended for production use', "Raccomandato per l'uso in produzione")
        html = html.replace('It is recommended for production use.', "È raccomandato per l'uso in produzione.")
        html = html.replace('review the full report below for specific considerations', 'consulta il report completo di seguito per considerazioni specifiche')
        html = html.replace('Suitable for development use', "Adatto per l'uso in sviluppo")
        html = html.replace('review security and maintenance signals before production deployment', 'verifica i segnali di sicurezza e manutenzione prima del deployment in produzione')
        html = html.replace('Not recommended for production use without thorough manual review and additional security measures', 'Non raccomandato per uso in produzione senza una revisione manuale accurata e misure di sicurezza aggiuntive')
        html = html.replace('It is below the recommended threshold of 70.', 'È al di sotto della soglia raccomandata di 70.')

        # 4. "X is a Y — description"
        html = _re_t.sub(r'>(.+?) is a (Node\.js package|Python package|Rust crate|Chrome extension|WordPress plugin|VPN service|game|website|SaaS platform|Firefox extension|VS Code extension|iOS app|Android app) — ',
                         r'>\1 è \2 — ', html)

        # 5. Entity type translations in body text
        html = html.replace('is a Node.js package', 'è un pacchetto Node.js')
        html = html.replace('is a Python package', 'è un pacchetto Python')
        html = html.replace('is a Rust crate', 'è una libreria Rust')
        html = html.replace('is a Chrome extension', "è un'estensione Chrome")
        html = html.replace('is a WordPress plugin', 'è un plugin WordPress')
        html = html.replace('is a VPN service', 'è un servizio VPN')
        html = html.replace('is a iOS app', "è un'app iOS")
        html = html.replace('is a Android app', "è un'app Android")

        # 6. Safety guide text
        html = html.replace("to check for vulnerabilities. Review the package's GitHub repository for recent commits.", 'per verificare le vulnerabilità. Controlla il repository GitHub del pacchetto per i commit recenti.')
        html = html.replace('You can also check the trust score via API:', 'Puoi anche verificare il punteggio di fiducia tramite API:')
        html = html.replace('watch for:', 'prestare attenzione a:')
        html = html.replace('dependency vulnerabilities, malicious packages, typosquatting', 'vulnerabilità delle dipendenze, pacchetti dannosi, typosquatting')
        html = html.replace("Run your package manager's audit command regularly.", 'Esegui regolarmente il comando di audit del tuo gestore di pacchetti.')
        html = html.replace('>Run <code>', '>Esegui <code>')

        # 7. King sections — privacy/security
        html = _re_t.sub(r'(.+?) is a Node\.js package maintained by (.+?)\.', r'\1 è un pacchetto Node.js mantenuto da \2.', html)
        html = _re_t.sub(r'(.+?) is a (.+?) maintained by (.+?)\.', r'\1 è \2 mantenuto da \3.', html)
        html = html.replace(' maintained by ', ' mantenuto da ')
        html = html.replace('As a development package,', 'Come pacchetto di sviluppo,')
        html = html.replace('does not directly collect end-user personal data', 'non raccoglie direttamente dati personali degli utenti finali')
        html = html.replace('However, applications built with it may collect data depending on implementation', "Tuttavia, le applicazioni costruite con esso possono raccogliere dati in base all'implementazione")
        html = html.replace("Review the package's dependencies for potential supply chain risks.", 'Verifica le dipendenze del pacchetto per potenziali rischi della catena di fornitura.')
        html = html.replace('License information not available.', 'Informazioni sulla licenza non disponibili.')
        html = html.replace('Open-source packages allow independent security review of the source code.', 'I pacchetti open source consentono la revisione indipendente della sicurezza del codice sorgente.')
        html = html.replace('known vulnerabilities (CVEs) in the National Vulnerability Database', 'vulnerabilità note (CVE) nel National Vulnerability Database')
        html = html.replace('This is a clean record.', 'Nessuna vulnerabilità rilevata.')
        html = html.replace('Review advisories and update to the latest version.', 'Consulta gli avvisi e aggiorna alla versione più recente.')

        html = html.replace('and has not yet reached Nerq trust threshold (70+).', 'e non ha ancora raggiunto la soglia di fiducia Nerq (70+).')
        html = html.replace('and meets Nerq trust threshold', 'e soddisfa la soglia di fiducia Nerq')
        html = html.replace('This score is based on automated analysis of security, maintenance, community, and quality signals.', "Questo punteggio si basa sull'analisi automatizzata dei segnali di sicurezza, manutenzione, comunità e qualità.")

        # 8. Methodology
        html = html.replace('using the same methodology, enabling direct cross-entity comparison', 'utilizzando la stessa metodologia, consentendo il confronto diretto tra entità')
        html = html.replace('Scores are updated continuously as new data becomes available', 'I punteggi vengono aggiornati continuamente quando sono disponibili nuovi dati')
        html = html.replace('is computed from', 'è calcolato da')
        html = html.replace('The score reflects', 'Il punteggio riflette')
        html = html.replace('independent dimensions', 'dimensioni indipendenti')
        html = html.replace('Each dimension is weighted equally to produce the composite trust score.', 'Ogni dimensione ha lo stesso peso per produrre il punteggio di fiducia complessivo.')

        # 9. Key findings / signal descriptions
        html = html.replace('Composite trust score:', 'Punteggio di fiducia complessivo:')
        html = html.replace('across all available signals', 'su tutti i segnali disponibili')
        html = html.replace('Code quality, vulnerability exposure, and security practices.', 'Qualità del codice, esposizione alle vulnerabilità e pratiche di sicurezza.')
        html = html.replace('Update frequency, issue responsiveness, active development.', 'Frequenza di aggiornamento, reattività ai problemi, sviluppo attivo.')
        html = html.replace('README quality, API docs, usage examples.', 'Qualità del README, documentazione API, esempi di utilizzo.')
        html = html.replace('Community adoption.', 'Adozione della comunità.')
        html = html.replace('Composite score across all trust dimensions.', 'Punteggio complessivo su tutte le dimensioni di fiducia.')

        # 10. FAQ answers
        html = html.replace('Yes, it is safe to use.', 'Sì, è sicuro da usare.')
        html = html.replace('Use with some caution.', 'Usa con cautela.')
        html = html.replace('Exercise caution.', 'Fai attenzione.')
        html = html.replace('Significant trust concerns.', 'Problemi significativi di fiducia.')
        html = html.replace('Strongest signal:', 'Segnale più forte:')
        html = html.replace('Score based on', 'Punteggio basato su')
        html = html.replace('multiple trust dimensions', 'più dimensioni di fiducia')
        html = html.replace('Scores update as new data becomes available.', 'I punteggi vengono aggiornati quando sono disponibili nuovi dati.')
        html = html.replace('check back soon', 'torna a controllare presto')
        html = html.replace('higher-rated alternatives include', 'le alternative con punteggio più alto includono')
        html = html.replace('more Node.js packages are being analyzed', 'altri pacchetti Node.js sono in fase di analisi')
        html = html.replace('more Python packages are being analyzed', 'altri pacchetti Python sono in fase di analisi')
        html = html.replace('Meets Nerq Verified threshold.', 'Soddisfa la soglia verificata Nerq.')

        # 11. Security check FAQ
        html = html.replace('Nerq checks', 'Nerq verifica')
        html = html.replace('against NVD, OSV.dev, and registry-specific vulnerability databases', 'rispetto a NVD, OSV.dev e database di vulnerabilità specifici del registro')
        html = html.replace('Current security score:', 'Punteggio di sicurezza attuale:')
        html = html.replace("Run your package manager's audit command for the latest findings.", 'Esegui il comando di audit del tuo gestore di pacchetti per i risultati più recenti.')
        html = html.replace('has a trust score of', 'ha un punteggio di fiducia di')
        html = html.replace('has a Nerq Trust Score of', 'ha un Punteggio di fiducia Nerq di')

        # 12. Footer bottom
        html = html.replace('trust scores for all software', 'punteggi di fiducia per tutto il software')
        html = html.replace('7.5M+ entities', 'Oltre 7,5 milioni di entità')
        html = html.replace('26 registries', '26 registri')

        # 13. og:description
        html = html.replace('Independent safety assessment by Nerq.', 'Valutazione indipendente della sicurezza di Nerq.')
        html = html.replace('Independent safety assessment by Nerq', 'Valutazione indipendente della sicurezza di Nerq')

        # 14. Breadcrumb in JSON-LD
        html = html.replace('"Safety Reports"', '"Report di sicurezza"')

        # 15. FAQ questions (in <summary> and JSON-LD)
        html = _re_t.sub(r"What is (.+?)'s trust score\?", r'Qual è il punteggio di fiducia di \1?', html)
        html = _re_t.sub(r"Qual è il punteggio di fiducia di (.+?)'s trust score\?", r'Qual è il punteggio di fiducia di \1?', html)  # catch post-translated
        html = _re_t.sub(r'Is (.+?) safe to use\?', r'\1 è sicuro da usare?', html)
        html = _re_t.sub(r'Is (.+?) safe\?', r'\1 è sicuro?', html)
        html = _re_t.sub(r'What are safer alternatives to (.+?)\?', r'Quali sono le alternative più sicure a \1?', html)
        html = _re_t.sub(r'Does (.+?) have known vulnerabilities\?', r'\1 ha vulnerabilità note?', html)
        html = _re_t.sub(r'How actively maintained is (.+?)\?', r'Quanto è attivamente mantenuto \1?', html)
        html = _re_t.sub(r'How does (.+?) compare to similar', r'Come si confronta \1 con simili', html)
        html = _re_t.sub(r'Can I use (.+?) in a regulated environment\?', r'Posso usare \1 in un ambiente regolamentato?', html)

        # 16. FAQ answer fragments
        html = html.replace('In the npm category,', 'Nella categoria npm,')
        html = html.replace('In the pypi category,', 'Nella categoria pypi,')
        html = html.replace('In the crates category,', 'Nella categoria crates,')
        html = _re_t.sub(r'In the (\w+) category,', r'Nella categoria \1,', html)
        html = _re_t.sub(r'(.+?) scores ([\d.]+)/100\.', r'\1 ottiene \2/100.', html)

        # 17. "has a Trust Score of" in king sections
        html = _re_t.sub(r'(.+?) has a Trust Score of', r'\1 ha un Punteggio di fiducia di', html)

        # 18. Security king section fragments
        html = html.replace('Security score:', 'Punteggio di sicurezza:')
        html = html.replace('Privacy score:', 'Punteggio di privacy:')
        html = html.replace('to check for known vulnerabilities in your dependency tree', "per verificare le vulnerabilità note nell'albero delle dipendenze")

        # 19. Meta description
        html = html.replace('0 known vulnerabilities', '0 vulnerabilità note')
        html = html.replace('License: See repository', 'Licenza: vedi repository')
        html = html.replace('Independent security analysis of', 'Analisi indipendente della sicurezza di')
        html = html.replace('trust signals, vulnerabilities, compliance, and safer alternatives', 'segnali di fiducia, vulnerabilità, conformità e alternative più sicure')

        # 20. og:description — "di Nerq" + fix all other language suffixes
        html = html.replace('trust grade,', 'grado di fiducia,')
        html = html.replace('por Nerq', 'di Nerq')
        html = html.replace('oleh Nerq', 'di Nerq')
        html = html.replace('od Nerq', 'di Nerq')
        html = html.replace('Nerq tarafından', 'di Nerq')
        html = html.replace('द्वारा Nerq', 'di Nerq')
        html = html.replace('от Nerq', 'di Nerq')
        html = html.replace('przez Nerq', 'di Nerq')
        html = html.replace('by Nerq', 'di Nerq')

        # 21. Fix Schema.org @type that got wrongly translated by _CONTENT_TRANSLATIONS
        html = html.replace('"@type": "Recensione"', '"@type": "Review"')
        html = html.replace('"@type":"Recensione"', '"@type":"Review"')
        # reviewBody translation
        html = html.replace('with a Nerq Trust Score of', 'con un Punteggio di fiducia Nerq di')
        html = html.replace('Proceed with caution.', 'Procedi con cautela.')
        html = html.replace('Not recommended.', 'Non raccomandato.')
        # JSON-LD
        html = _re_t.sub(r'"name": "Is (.+?) Safe\?', r'"name": "\1 è sicuro?', html)
        html = _re_t.sub(r'"name": "Is (.+?) Safe to Visit\?', r'"name": "È sicuro visitare \1?', html)
        html = _re_t.sub(r'og:title" content="Is (.+?) Safe\?', r'og:title" content="\1 è sicuro?', html)
        html = _re_t.sub(r'nerq:question" content="Is (.+?) safe', r'nerq:question" content="\1 è sicuro', html)

        # Fix: License
        html = html.replace('License: Not specified', 'Licenza: non specificata')
        html = html.replace('License: See repository', 'Licenza: vedi repository')
        # Fix: FAQ Q2 — trust score question (catch partial-translated)
        html = _re_t.sub(r"What is (.+?)'s trust score\?", r'Qual è il punteggio di fiducia di \1?', html)
        html = _re_t.sub(r"Qual è il punteggio di fiducia di (.+?)'s trust score\?", r'Qual è il punteggio di fiducia di \1?', html)
        # Fix: Footer remaining English
        html = html.replace('dimensions. Data from', 'dimensioni. Dati da')
        html = html.replace('Data from', 'Dati da')

    elif lang == "ko":
        import re as _re_t
        html = _re_t.sub(r'<title>Is (.+?) Safe\?', r'<title>\1은(는) 안전한가요?', html, count=1)
        html = html.replace('Independent Trust &amp; Security Analysis 2026 | Nerq', '독립적인 신뢰 및 보안 분석 2026 | Nerq')
        html = _re_t.sub(r'>Is (.+?) Safe\?<', r'>\1은(는) 안전한가요?<', html)
        html = _re_t.sub(r'>Is (.+?) safe\?<', r'>\1은(는) 안전한가요?<', html)
        html = _re_t.sub(r'>What data does (.+?) collect\?<', r'>\1은(는) 어떤 데이터를 수집하나요?<', html)
        html = _re_t.sub(r'>Is (.+?) secure\?<', r'>\1은(는) 안전한가요?<', html)
        html = _re_t.sub(r'>(.+?) Across Platforms<', r'>다른 플랫폼의 \1<', html)
        html = _re_t.sub(r'>Safety Guide: (.+?)<', r'>보안 가이드: \1<', html)
        html = _re_t.sub(r">What is (.+?)\?<", r">\1이(가) 무엇인가요?<", html)
        html = html.replace('>Details<', '>세부 정보<')
        html = _re_t.sub(r'>Is (.+?) Safe to Visit\?', r'>\1은(는) 방문하기 안전한가요?', html)
        html = _re_t.sub(r'>Is (.+?) safe for solo travelers\?<', r'>\1은(는) 혼자 여행하기에 안전한가요?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for women\?<', r'>\1은(는) 여성에게 안전한가요?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for LGBTQ\+ travelers\?<', r'>\1은(는) LGBTQ+ 여행자에게 안전한가요?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for families\?<', r'>\1은(는) 가족에게 안전한가요?<', html)
        html = _re_t.sub(r'>Is (.+?) safe to visit right now\?<', r'>\1은(는) 지금 방문하기 안전한가요?<', html)
        html = _re_t.sub(r'>Is tap water safe to drink in (.+?)\?<', r'>\1에서 수돗물을 마셔도 안전한가요?<', html)
        html = _re_t.sub(r'>Do I need vaccinations for (.+?)\?<', r'>\1을(를) 위해 예방접종이 필요한가요?<', html)
        html = _re_t.sub(r'>What are safer alternatives to (.+?)\?<', r'>\1의 더 안전한 대안은 무엇인가요?<', html)
        html = _re_t.sub(r'>What are the side effects of (.+?)\?<', r'>\1의 부작용은 무엇인가요?<', html)
        html = _re_t.sub(r'>Does (.+?) interact with medications\?<', r'>\1은(는) 약물과 상호작용하나요?<', html)
        html = _re_t.sub(r"(.+?)'s trust score of", r'\1의 신뢰 점수', html)
        html = _re_t.sub(r'Nerq of (\d)', r'Nerq \1', html)
        # CRITICAL ORDER: replace longer phrases before standalone 'Trust Score'
        html = html.replace('has a Nerq Trust Score of', '의 Nerq 신뢰 점수는')
        html = html.replace('with a Nerq Trust Score of', 'Nerq 신뢰 점수')
        html = html.replace('Trust Score Breakdown', '신뢰 점수 세부 정보')
        html = html.replace('Trust Score', '신뢰 점수')
        html = html.replace('Safety Score Breakdown', '보안 점수 세부 정보')
        html = html.replace('Safety Score', '보안 점수')
        html = html.replace('Trust Analysis 2026', '신뢰 분석 2026')
        # Nav
        html = html.replace('>Search<', '>검색<')
        html = html.replace('>Apps<', '>앱<')
        html = html.replace('>Packages<', '>패키지<')
        html = html.replace('>Extensions<', '>확장<')
        html = html.replace('>Websites<', '>웹사이트<')
        html = html.replace('>Travel<', '>여행<')
        html = html.replace('>Charities<', '>자선단체<')
        html = html.replace('>Compare<', '>비교<')
        html = html.replace('>Resources<', '>리소스<')
        html = html.replace('>About<', '>소개<')
        html = html.replace('>Check Safety<', '>안전 확인<')
        html = html.replace('>Games<', '>게임<')
        html = html.replace('>Countries<', '>국가<')
        html = html.replace('>Check Website<', '>웹사이트 확인<')
        html = html.replace('>Safety Guides<', '>보안 가이드<')
        # Footer text
        html = html.replace('Trust scores for software, apps, websites, travel destinations, and charities', '소프트웨어, 앱, 웹사이트, 여행지 및 자선단체를 위한 신뢰 점수')
        html = html.replace('20 languages', '20개 언어')
        html = html.replace('>Guides<', '>가이드<')
        html = html.replace('>Mobile Apps<', '>모바일 앱<')
        html = html.replace('>Trust Badges<', '>신뢰 배지<')
        html = html.replace('>VPNs<', '>VPN<')
        html = html.replace('7.5M+ entities from 26 registries. Independent. Data-driven.', '26개 레지스트리의 750만 개 이상 엔터티. 독립적. 데이터 기반.')

        # ── Dynamic paragraph translations ──

        # 1. Verdict lead
        html = _re_t.sub(
            r'Yes, (.+?) is safe to use\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'네, \1은(는) 사용하기에 안전합니다. \1은(는) \2이며 Nerq 신뢰 점수는 \3/100 (\4)입니다.', html)
        html = _re_t.sub(
            r'Use (.+?) with some caution\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'\1을(를) 주의하며 사용하세요. \1은(는) \2이며 Nerq 신뢰 점수는 \3/100 (\4)입니다.', html)
        html = _re_t.sub(
            r'Exercise caution with (.+?)\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'\1에 대해 주의하세요. \1은(는) \2이며 Nerq 신뢰 점수는 \3/100 (\4)입니다.', html)

        # 2. Short answer box
        html = html.replace('<strong>YES</strong>', '<strong>예</strong>')
        html = html.replace('<strong>CAUTION</strong>', '<strong>주의</strong>')
        html = html.replace('<strong>NO — USE WITH CAUTION</strong>', '<strong>아니오 — 주의하며 사용</strong>')

        # 3. Citation detail / verdict detail
        html = html.replace("It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption", '보안, 유지보수 및 커뮤니티 채택에서 강력한 신호로 Nerq 신뢰 기준을 충족합니다')
        html = html.replace('It has moderate trust signals but shows some areas of concern that warrant attention', '보통 수준의 신뢰 신호가 있지만 주의가 필요한 일부 우려 사항이 있습니다')
        html = html.replace('It has below-average trust signals with significant gaps in security, maintenance, or documentation', '보안, 유지보수 또는 문서화에서 심각한 격차와 함께 평균 이하의 신뢰 신호가 있습니다')
        html = html.replace('Recommended for production use', '프로덕션 사용 권장')
        html = html.replace('It is recommended for production use.', '프로덕션 사용이 권장됩니다.')
        html = html.replace('review the full report below for specific considerations', '구체적인 사항은 아래 전체 보고서를 참조하세요')
        html = html.replace('Suitable for development use', '개발 사용에 적합')
        html = html.replace('review security and maintenance signals before production deployment', '프로덕션 배포 전 보안 및 유지보수 신호를 검토하세요')
        html = html.replace('Not recommended for production use without thorough manual review and additional security measures', '철저한 수동 검토 및 추가 보안 조치 없이는 프로덕션 사용이 권장되지 않습니다')
        html = html.replace('It is below the recommended threshold of 70.', '권장 기준인 70 미만입니다.')

        # 4. "X is a Y — description"
        html = _re_t.sub(r'>(.+?) is a (Node\.js package|Python package|Rust crate|Chrome extension|WordPress plugin|VPN service|game|website|SaaS platform|Firefox extension|VS Code extension|iOS app|Android app) — ',
                         r'>\1은(는) \2이며 — ', html)

        # 5. Entity type translations in body text
        html = html.replace('is a Node.js package', 'Node.js 패키지입니다')
        html = html.replace('is a Python package', 'Python 패키지입니다')
        html = html.replace('is a Rust crate', 'Rust 크레이트입니다')
        html = html.replace('is a Chrome extension', 'Chrome 확장 프로그램입니다')
        html = html.replace('is a WordPress plugin', 'WordPress 플러그인입니다')
        html = html.replace('is a VPN service', 'VPN 서비스입니다')
        html = html.replace('is a iOS app', 'iOS 앱입니다')
        html = html.replace('is a Android app', 'Android 앱입니다')

        # 6. Safety guide text
        html = html.replace("to check for vulnerabilities. Review the package's GitHub repository for recent commits.", '취약점을 확인하려면. 최근 커밋에 대한 패키지의 GitHub 저장소를 검토하세요.')
        html = html.replace('You can also check the trust score via API:', 'API를 통해 신뢰 점수를 직접 확인할 수도 있습니다:')
        html = html.replace('watch for:', '주의 사항:')
        html = html.replace('dependency vulnerabilities, malicious packages, typosquatting', '의존성 취약점, 악성 패키지, 타이포스쿼팅')
        html = html.replace("Run your package manager's audit command regularly.", '패키지 관리자의 감사 명령을 정기적으로 실행하세요.')
        html = html.replace('>Run <code>', '>실행 <code>')

        # 7. King sections — privacy/security
        html = _re_t.sub(r'(.+?) is a Node\.js package maintained by (.+?)\.', r'\1은(는) \2이(가) 유지보수하는 Node.js 패키지입니다.', html)
        html = _re_t.sub(r'(.+?) is a (.+?) maintained by (.+?)\.', r'\1은(는) \2이며 \3이(가) 유지보수합니다.', html)
        html = html.replace(' maintained by ', ' 유지보수: ')
        html = html.replace('As a development package,', '개발 패키지로서,')
        html = html.replace('does not directly collect end-user personal data', '최종 사용자 개인 데이터를 직접 수집하지 않습니다')
        html = html.replace('However, applications built with it may collect data depending on implementation', '그러나 이를 사용하여 구축된 애플리케이션은 구현 방식에 따라 데이터를 수집할 수 있습니다')
        html = html.replace("Review the package's dependencies for potential supply chain risks.", '공급망 위험에 대한 패키지 의존성을 검토하세요.')
        html = html.replace('License information not available.', '라이선스 정보 없음.')
        html = html.replace('Open-source packages allow independent security review of the source code.', '오픈 소스 패키지는 소스 코드의 독립적인 보안 검토를 허용합니다.')
        html = html.replace('known vulnerabilities (CVEs) in the National Vulnerability Database', '국가 취약점 데이터베이스(NVD)의 알려진 취약점(CVE)')
        html = html.replace('This is a clean record.', '취약점이 발견되지 않았습니다.')
        html = html.replace('Review advisories and update to the latest version.', '권고 사항을 검토하고 최신 버전으로 업데이트하세요.')

        html = html.replace('and has not yet reached Nerq trust threshold (70+).', '아직 Nerq 신뢰 기준(70+)에 도달하지 못했습니다.')
        html = html.replace('and meets Nerq trust threshold', 'Nerq 신뢰 기준 충족')
        html = html.replace('This score is based on automated analysis of security, maintenance, community, and quality signals.', '이 점수는 보안, 유지보수, 커뮤니티 및 품질 신호의 자동 분석을 기반으로 합니다.')

        # 8. Methodology
        html = html.replace('using the same methodology, enabling direct cross-entity comparison', '동일한 방법론을 사용하여 엔터티 간 직접 비교를 가능하게 합니다')
        html = html.replace('Scores are updated continuously as new data becomes available', '새로운 데이터가 제공되면 점수가 지속적으로 업데이트됩니다')
        html = html.replace('is computed from', '다음에서 계산됩니다:')
        html = html.replace('The score reflects', '점수는 다음을 반영합니다:')
        html = html.replace('independent dimensions', '독립적인 차원')
        html = html.replace('Each dimension is weighted equally to produce the composite trust score.', '각 차원은 동등하게 가중되어 종합 신뢰 점수를 산출합니다.')

        # 9. Key findings / signal descriptions
        html = html.replace('Composite trust score:', '종합 신뢰 점수:')
        html = html.replace('across all available signals', '모든 가용 신호 기반')
        html = html.replace('Code quality, vulnerability exposure, and security practices.', '코드 품질, 취약점 노출 및 보안 관행.')
        html = html.replace('Update frequency, issue responsiveness, active development.', '업데이트 빈도, 이슈 대응성, 활발한 개발.')
        html = html.replace('README quality, API docs, usage examples.', 'README 품질, API 문서, 사용 예제.')
        html = html.replace('Community adoption.', '커뮤니티 채택.')
        html = html.replace('Composite score across all trust dimensions.', '모든 신뢰 차원의 종합 점수.')

        # 10. FAQ answers
        html = html.replace('Yes, it is safe to use.', '네, 사용하기에 안전합니다.')
        html = html.replace('Use with some caution.', '주의하며 사용하세요.')
        html = html.replace('Exercise caution.', '주의하세요.')
        html = html.replace('Significant trust concerns.', '심각한 신뢰 문제가 있습니다.')
        html = html.replace('Strongest signal:', '가장 강력한 신호:')
        html = html.replace('Score based on', '점수 기반:')
        html = html.replace('multiple trust dimensions', '여러 신뢰 차원')
        html = html.replace('Scores update as new data becomes available.', '새로운 데이터가 제공되면 점수가 업데이트됩니다.')
        html = html.replace('check back soon', '곧 다시 확인해 주세요')
        html = html.replace('higher-rated alternatives include', '더 높은 평가를 받은 대안으로는')
        html = html.replace('more Node.js packages are being analyzed', '더 많은 Node.js 패키지를 분석 중입니다')
        html = html.replace('more Python packages are being analyzed', '더 많은 Python 패키지를 분석 중입니다')
        html = html.replace('Meets Nerq Verified threshold.', 'Nerq 인증 기준 충족.')

        # 11. Security check FAQ
        html = html.replace('Nerq checks', 'Nerq 검사:')
        html = html.replace('against NVD, OSV.dev, and registry-specific vulnerability databases', 'NVD, OSV.dev 및 레지스트리별 취약점 데이터베이스 대조')
        html = html.replace('Current security score:', '현재 보안 점수:')
        html = html.replace("Run your package manager's audit command for the latest findings.", '패키지 관리자의 감사 명령을 실행하여 최신 결과를 확인하세요.')
        html = html.replace('has a trust score of', '의 신뢰 점수는')
        html = html.replace('has a Nerq Trust Score of', '의 Nerq 신뢰 점수는')

        # 12. Footer bottom
        html = html.replace('trust scores for all software', '모든 소프트웨어의 신뢰 점수')
        html = html.replace('7.5M+ entities', '750만 개 이상의 엔터티')
        html = html.replace('26 registries', '26개 레지스트리')

        # 13. og:description
        html = html.replace('Independent safety assessment by Nerq.', 'Nerq 제공 독립적 안전 평가.')
        html = html.replace('Independent safety assessment by Nerq', 'Nerq 제공 독립적 안전 평가')

        # 14. Breadcrumb in JSON-LD
        html = html.replace('"Safety Reports"', '"보안 보고서"')

        # 15. FAQ questions (in <summary> and JSON-LD)
        html = _re_t.sub(r"What is (.+?)'s trust score\?", r'\1의 신뢰 점수는 얼마인가요?', html)
        html = _re_t.sub(r'Is (.+?) safe to use\?', r'\1은(는) 사용하기에 안전한가요?', html)
        html = _re_t.sub(r'Is (.+?) safe\?', r'\1은(는) 안전한가요?', html)
        html = _re_t.sub(r'What are safer alternatives to (.+?)\?', r'\1의 더 안전한 대안은 무엇인가요?', html)
        html = _re_t.sub(r'Does (.+?) have known vulnerabilities\?', r'\1에 알려진 취약점이 있나요?', html)
        html = _re_t.sub(r'How actively maintained is (.+?)\?', r'\1은(는) 얼마나 활발히 유지보수되나요?', html)
        html = _re_t.sub(r'How does (.+?) compare to similar', r'\1은(는) 유사한 항목과 어떻게 비교되나요', html)
        html = _re_t.sub(r'Can I use (.+?) in a regulated environment\?', r'\1을(를) 규제 환경에서 사용할 수 있나요?', html)

        # 16. FAQ answer fragments
        html = html.replace('In the npm category,', 'npm 카테고리에서,')
        html = html.replace('In the pypi category,', 'pypi 카테고리에서,')
        html = html.replace('In the crates category,', 'crates 카테고리에서,')
        html = _re_t.sub(r'In the (\w+) category,', r'\1 카테고리에서,', html)
        html = _re_t.sub(r'(.+?) scores ([\d.]+)/100\.', r'\1의 점수는 \2/100입니다.', html)

        # 17. "has a Trust Score of" in king sections
        html = _re_t.sub(r'(.+?) has a Trust Score of', r'\1의 신뢰 점수는', html)

        # 18. Security king section fragments
        html = html.replace('Security score:', '보안 점수:')
        html = html.replace('Privacy score:', '개인정보 점수:')
        html = html.replace('to check for known vulnerabilities in your dependency tree', '의존성 트리의 알려진 취약점을 확인하려면')

        # 19. Meta description
        html = html.replace('0 known vulnerabilities', '알려진 취약점 0건')
        html = html.replace('License: See repository', '라이선스: 저장소 참조')
        html = html.replace('Independent security analysis of', '독립적 보안 분석:')
        html = html.replace('trust signals, vulnerabilities, compliance, and safer alternatives', '신뢰 신호, 취약점, 규정 준수 및 더 안전한 대안')

        # 20. og:description — "Nerq 제공" + fix all other language suffixes
        html = html.replace('trust grade,', '신뢰 등급,')
        html = html.replace('por Nerq', 'Nerq 제공')
        html = html.replace('oleh Nerq', 'Nerq 제공')
        html = html.replace('od Nerq', 'Nerq 제공')
        html = html.replace('Nerq tarafından', 'Nerq 제공')
        html = html.replace('द्वारा Nerq', 'Nerq 제공')
        html = html.replace('от Nerq', 'Nerq 제공')
        html = html.replace('przez Nerq', 'Nerq 제공')
        html = html.replace('di Nerq', 'Nerq 제공')
        html = html.replace('by Nerq', 'Nerq 제공')

        # 21. Fix Schema.org @type that got wrongly translated by _CONTENT_TRANSLATIONS
        html = html.replace('"@type": "리뷰"', '"@type": "Review"')
        html = html.replace('"@type":"리뷰"', '"@type":"Review"')
        # reviewBody translation
        html = html.replace('with a Nerq Trust Score of', 'Nerq 신뢰 점수')
        html = html.replace('Proceed with caution.', '주의하여 진행하세요.')
        html = html.replace('Not recommended.', '권장하지 않습니다.')
        # JSON-LD
        html = _re_t.sub(r'"name": "Is (.+?) Safe\?', r'"name": "\1은(는) 안전한가요?', html)
        html = _re_t.sub(r'"name": "Is (.+?) Safe to Visit\?', r'"name": "\1은(는) 방문하기 안전한가요?', html)
        html = _re_t.sub(r'og:title" content="Is (.+?) Safe\?', r'og:title" content="\1은(는) 안전한가요?', html)
        html = _re_t.sub(r'nerq:question" content="Is (.+?) safe', r'nerq:question" content="\1은(는) 안전', html)

        # Fix: License
        html = html.replace('License: Not specified', '라이선스: 지정되지 않음')
        html = html.replace('License: See repository', '라이선스: 저장소 참조')
        # Fix: FAQ Q2 — trust score question
        html = _re_t.sub(r"What is (.+?)'s trust score\?", r'\1의 신뢰 점수는 얼마인가요?', html)
        # Fix: Footer remaining English
        html = html.replace('dimensions. Data from', '차원. 데이터 출처:')
        html = html.replace('Data from', '데이터 출처:')

    elif lang == "vi":
        import re as _re_t
        html = _re_t.sub(r'<title>Is (.+?) Safe\?', r'<title>\1 có an toàn không?', html, count=1)
        html = html.replace('Independent Trust &amp; Security Analysis 2026 | Nerq', 'Phân tích tin cậy và bảo mật độc lập 2026 | Nerq')
        html = _re_t.sub(r'>Is (.+?) Safe\?<', r'>\1 có an toàn không?<', html)
        html = _re_t.sub(r'>Is (.+?) safe\?<', r'>\1 có an toàn không?<', html)
        html = _re_t.sub(r'>What data does (.+?) collect\?<', r'>\1 thu thập dữ liệu gì?<', html)
        html = _re_t.sub(r'>Is (.+?) secure\?<', r'>\1 có an toàn không?<', html)
        html = _re_t.sub(r'>(.+?) Across Platforms<', r'>\1 trên các nền tảng khác<', html)
        html = _re_t.sub(r'>Safety Guide: (.+?)<', r'>Hướng dẫn bảo mật: \1<', html)
        html = _re_t.sub(r">What is (.+?)\?<", r">\1 là gì?<", html)
        html = html.replace('>Details<', '>Chi tiết<')
        html = _re_t.sub(r'>Is (.+?) Safe to Visit\?', r'>\1 có an toàn để ghé thăm không?', html)
        html = _re_t.sub(r'>Is (.+?) safe for solo travelers\?<', r'>\1 có an toàn cho du khách đi một mình không?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for women\?<', r'>\1 có an toàn cho phụ nữ không?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for LGBTQ\+ travelers\?<', r'>\1 có an toàn cho du khách LGBTQ+ không?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for families\?<', r'>\1 có an toàn cho gia đình không?<', html)
        html = _re_t.sub(r'>Is (.+?) safe to visit right now\?<', r'>\1 có an toàn để ghé thăm ngay bây giờ không?<', html)
        html = _re_t.sub(r'>Is tap water safe to drink in (.+?)\?<', r'>Nước máy ở \1 có an toàn để uống không?<', html)
        html = _re_t.sub(r'>Do I need vaccinations for (.+?)\?<', r'>Tôi có cần tiêm phòng cho \1 không?<', html)
        html = _re_t.sub(r'>What are safer alternatives to (.+?)\?<', r'>Các lựa chọn an toàn hơn \1 là gì?<', html)
        html = _re_t.sub(r'>What are the side effects of (.+?)\?<', r'>Tác dụng phụ của \1 là gì?<', html)
        html = _re_t.sub(r'>Does (.+?) interact with medications\?<', r'>\1 có tương tác với thuốc không?<', html)
        html = _re_t.sub(r"(.+?)'s trust score of", r'điểm tin cậy của \1 là', html)
        html = _re_t.sub(r'Nerq of (\d)', r'Nerq \1', html)
        # CRITICAL ORDER: replace longer phrases before standalone 'Trust Score'
        html = html.replace('has a Nerq Trust Score of', 'có Điểm tin cậy Nerq là')
        html = html.replace('with a Nerq Trust Score of', 'với Điểm tin cậy Nerq là')
        html = html.replace('Trust Score Breakdown', 'Chi tiết điểm tin cậy')
        html = html.replace('Trust Score', 'Điểm tin cậy')
        html = html.replace('Safety Score Breakdown', 'Chi tiết điểm bảo mật')
        html = html.replace('Safety Score', 'Điểm bảo mật')
        html = html.replace('Trust Analysis 2026', 'Phân tích tin cậy 2026')
        # Nav
        html = html.replace('>Search<', '>Tìm kiếm<')
        html = html.replace('>Apps<', '>Ứng dụng<')
        html = html.replace('>Packages<', '>Gói<')
        html = html.replace('>Extensions<', '>Tiện ích<')
        html = html.replace('>Websites<', '>Trang web<')
        html = html.replace('>Travel<', '>Du lịch<')
        html = html.replace('>Charities<', '>Từ thiện<')
        html = html.replace('>Compare<', '>So sánh<')
        html = html.replace('>Resources<', '>Tài nguyên<')
        html = html.replace('>About<', '>Giới thiệu<')
        html = html.replace('>Check Safety<', '>Kiểm tra bảo mật<')
        html = html.replace('>Games<', '>Trò chơi<')
        html = html.replace('>Countries<', '>Quốc gia<')
        html = html.replace('>Check Website<', '>Kiểm tra trang web<')
        html = html.replace('>Safety Guides<', '>Hướng dẫn bảo mật<')
        # Footer text
        html = html.replace('Trust scores for software, apps, websites, travel destinations, and charities', 'Điểm tin cậy cho phần mềm, ứng dụng, trang web, điểm đến du lịch và tổ chức từ thiện')
        html = html.replace('20 languages', '20 ngôn ngữ')
        html = html.replace('>Guides<', '>Hướng dẫn<')
        html = html.replace('>Mobile Apps<', '>Ứng dụng di động<')
        html = html.replace('>Trust Badges<', '>Huy hiệu tin cậy<')
        html = html.replace('>VPNs<', '>VPN<')
        html = html.replace('7.5M+ entities from 26 registries. Independent. Data-driven.', 'Hơn 7,5 triệu thực thể từ 26 registry. Độc lập. Dựa trên dữ liệu.')

        # ── Dynamic paragraph translations ──

        # 1. Verdict lead
        html = _re_t.sub(
            r'Yes, (.+?) is safe to use\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Có, \1 an toàn để sử dụng. \1 là \2 với Điểm tin cậy Nerq là \3/100 (\4).', html)
        html = _re_t.sub(
            r'Use (.+?) with some caution\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Sử dụng \1 một cách thận trọng. \1 là \2 với Điểm tin cậy Nerq là \3/100 (\4).', html)
        html = _re_t.sub(
            r'Exercise caution with (.+?)\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Hãy thận trọng với \1. \1 là \2 với Điểm tin cậy Nerq là \3/100 (\4).', html)

        # 2. Short answer box
        html = html.replace('<strong>YES</strong>', '<strong>CÓ</strong>')
        html = html.replace('<strong>CAUTION</strong>', '<strong>THẬN TRỌNG</strong>')
        html = html.replace('<strong>NO — USE WITH CAUTION</strong>', '<strong>KHÔNG — SỬ DỤNG THẬN TRỌNG</strong>')

        # 3. Citation detail / verdict detail
        html = html.replace("It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption", 'Đạt ngưỡng tin cậy Nerq với tín hiệu mạnh về bảo mật, bảo trì và sự chấp nhận của cộng đồng')
        html = html.replace('It has moderate trust signals but shows some areas of concern that warrant attention', 'Có tín hiệu tin cậy vừa phải nhưng có một số vấn đề cần chú ý')
        html = html.replace('It has below-average trust signals with significant gaps in security, maintenance, or documentation', 'Có tín hiệu tin cậy dưới trung bình với khoảng cách đáng kể về bảo mật, bảo trì hoặc tài liệu')
        html = html.replace('Recommended for production use', 'Khuyến nghị sử dụng trong sản xuất')
        html = html.replace('It is recommended for production use.', 'Được khuyến nghị sử dụng trong sản xuất.')
        html = html.replace('review the full report below for specific considerations', 'xem báo cáo đầy đủ bên dưới để biết chi tiết')
        html = html.replace('Suitable for development use', 'Phù hợp để sử dụng trong phát triển')
        html = html.replace('review security and maintenance signals before production deployment', 'xem xét tín hiệu bảo mật và bảo trì trước khi triển khai sản xuất')
        html = html.replace('Not recommended for production use without thorough manual review and additional security measures', 'Không khuyến nghị sử dụng trong sản xuất mà không có kiểm tra thủ công kỹ lưỡng và các biện pháp bảo mật bổ sung')
        html = html.replace('It is below the recommended threshold of 70.', 'Dưới ngưỡng khuyến nghị là 70.')

        # 4. "X is a Y — description"
        html = _re_t.sub(r'>(.+?) is a (Node\.js package|Python package|Rust crate|Chrome extension|WordPress plugin|VPN service|game|website|SaaS platform|Firefox extension|VS Code extension|iOS app|Android app) — ',
                         r'>\1 là \2 — ', html)

        # 5. Entity type translations in body text
        html = html.replace('is a Node.js package', 'là một gói Node.js')
        html = html.replace('is a Python package', 'là một gói Python')
        html = html.replace('is a Rust crate', 'là một thư viện Rust')
        html = html.replace('is a Chrome extension', 'là một tiện ích mở rộng Chrome')
        html = html.replace('is a WordPress plugin', 'là một plugin WordPress')
        html = html.replace('is a VPN service', 'là một dịch vụ VPN')
        html = html.replace('is a iOS app', 'là một ứng dụng iOS')
        html = html.replace('is a Android app', 'là một ứng dụng Android')

        # 6. Safety guide text
        html = html.replace("to check for vulnerabilities. Review the package's GitHub repository for recent commits.", 'để kiểm tra lỗ hổng bảo mật. Xem kho GitHub của gói để xem các commit gần đây.')
        html = html.replace('You can also check the trust score via API:', 'Bạn cũng có thể kiểm tra điểm tin cậy qua API:')
        html = html.replace('watch for:', 'cần chú ý:')
        html = html.replace('dependency vulnerabilities, malicious packages, typosquatting', 'lỗ hổng phụ thuộc, gói độc hại, typosquatting')
        html = html.replace("Run your package manager's audit command regularly.", 'Chạy lệnh kiểm tra của trình quản lý gói thường xuyên.')
        html = html.replace('>Run <code>', '>Chạy <code>')

        # 7. King sections — privacy/security
        html = _re_t.sub(r'(.+?) is a Node\.js package maintained by (.+?)\.', r'\1 là gói Node.js được duy trì bởi \2.', html)
        html = _re_t.sub(r'(.+?) is a (.+?) maintained by (.+?)\.', r'\1 là \2 được duy trì bởi \3.', html)
        html = html.replace(' maintained by ', ' được duy trì bởi ')
        html = html.replace('As a development package,', 'Là một gói phát triển,')
        html = html.replace('does not directly collect end-user personal data', 'không trực tiếp thu thập dữ liệu cá nhân của người dùng cuối')
        html = html.replace('However, applications built with it may collect data depending on implementation', 'Tuy nhiên, các ứng dụng được xây dựng với nó có thể thu thập dữ liệu tùy theo cách triển khai')
        html = html.replace("Review the package's dependencies for potential supply chain risks.", 'Xem xét các phụ thuộc của gói để phát hiện rủi ro chuỗi cung ứng.')
        html = html.replace('License information not available.', 'Thông tin giấy phép không có sẵn.')
        html = html.replace('Open-source packages allow independent security review of the source code.', 'Các gói mã nguồn mở cho phép xem xét bảo mật độc lập mã nguồn.')
        html = html.replace('known vulnerabilities (CVEs) in the National Vulnerability Database', 'lỗ hổng đã biết (CVE) trong Cơ sở dữ liệu lỗ hổng quốc gia')
        html = html.replace('This is a clean record.', 'Không có lỗ hổng được ghi nhận.')
        html = html.replace('Review advisories and update to the latest version.', 'Xem xét cảnh báo và cập nhật lên phiên bản mới nhất.')

        html = html.replace('and has not yet reached Nerq trust threshold (70+).', 'và chưa đạt ngưỡng tin cậy Nerq (70+).')
        html = html.replace('and meets Nerq trust threshold', 'và đạt ngưỡng tin cậy Nerq')
        html = html.replace('This score is based on automated analysis of security, maintenance, community, and quality signals.', 'Điểm này dựa trên phân tích tự động các tín hiệu bảo mật, bảo trì, cộng đồng và chất lượng.')

        # 8. Methodology
        html = html.replace('using the same methodology, enabling direct cross-entity comparison', 'bằng cùng một phương pháp, cho phép so sánh trực tiếp giữa các thực thể')
        html = html.replace('Scores are updated continuously as new data becomes available', 'Điểm được cập nhật liên tục khi có dữ liệu mới')
        html = html.replace('is computed from', 'được tính từ')
        html = html.replace('The score reflects', 'Điểm phản ánh')
        html = html.replace('independent dimensions', 'tiêu chí độc lập')
        html = html.replace('Each dimension is weighted equally to produce the composite trust score.', 'Mỗi tiêu chí được tính trọng số bằng nhau để tạo ra điểm tin cậy tổng hợp.')

        # 9. Key findings / signal descriptions
        html = html.replace('Composite trust score:', 'Điểm tin cậy tổng hợp:')
        html = html.replace('across all available signals', 'dựa trên tất cả tín hiệu có sẵn')
        html = html.replace('Code quality, vulnerability exposure, and security practices.', 'Chất lượng mã, mức độ lộ lỗ hổng và thực hành bảo mật.')
        html = html.replace('Update frequency, issue responsiveness, active development.', 'Tần suất cập nhật, phản hồi vấn đề, phát triển tích cực.')
        html = html.replace('README quality, API docs, usage examples.', 'Chất lượng README, tài liệu API, ví dụ sử dụng.')
        html = html.replace('Community adoption.', 'Sự chấp nhận của cộng đồng.')
        html = html.replace('Composite score across all trust dimensions.', 'Điểm tổng hợp trên tất cả tiêu chí tin cậy.')

        # 10. FAQ answers
        html = html.replace('Yes, it is safe to use.', 'Có, an toàn để sử dụng.')
        html = html.replace('Use with some caution.', 'Sử dụng với một chút thận trọng.')
        html = html.replace('Exercise caution.', 'Hãy thận trọng.')
        html = html.replace('Significant trust concerns.', 'Có vấn đề tin cậy đáng kể.')
        html = html.replace('Strongest signal:', 'Tín hiệu mạnh nhất:')
        html = html.replace('Score based on', 'Điểm dựa trên')
        html = html.replace('multiple trust dimensions', 'nhiều tiêu chí tin cậy')
        html = html.replace('Scores update as new data becomes available.', 'Điểm được cập nhật khi có dữ liệu mới.')
        html = html.replace('check back soon', 'hãy kiểm tra lại sớm')
        html = html.replace('higher-rated alternatives include', 'các lựa chọn thay thế được đánh giá cao hơn bao gồm')
        html = html.replace('more Node.js packages are being analyzed', 'đang phân tích thêm gói Node.js')
        html = html.replace('more Python packages are being analyzed', 'đang phân tích thêm gói Python')
        html = html.replace('Meets Nerq Verified threshold.', 'Đạt ngưỡng xác minh Nerq.')

        # 11. Security check FAQ
        html = html.replace('Nerq checks', 'Nerq kiểm tra')
        html = html.replace('against NVD, OSV.dev, and registry-specific vulnerability databases', 'so với NVD, OSV.dev và cơ sở dữ liệu lỗ hổng của từng registry')
        html = html.replace('Current security score:', 'Điểm bảo mật hiện tại:')
        html = html.replace("Run your package manager's audit command for the latest findings.", 'Chạy lệnh kiểm tra của trình quản lý gói để có kết quả mới nhất.')
        html = html.replace('has a trust score of', 'có điểm tin cậy là')
        html = html.replace('has a Nerq Trust Score of', 'có Điểm tin cậy Nerq là')

        # 12. Footer bottom
        html = html.replace('trust scores for all software', 'điểm tin cậy cho tất cả phần mềm')
        html = html.replace('7.5M+ entities', 'Hơn 7,5 triệu thực thể')
        html = html.replace('26 registries', '26 registry')

        # 13. og:description — "bởi Nerq" + fix all other language suffixes
        html = html.replace('Independent safety assessment by Nerq.', 'Đánh giá bảo mật độc lập bởi Nerq.')
        html = html.replace('Independent safety assessment by Nerq', 'Đánh giá bảo mật độc lập bởi Nerq')
        html = html.replace('trust grade,', 'hạng tin cậy,')
        html = html.replace('por Nerq', 'bởi Nerq')
        html = html.replace('oleh Nerq', 'bởi Nerq')
        html = html.replace('od Nerq', 'bởi Nerq')
        html = html.replace('Nerq tarafından', 'bởi Nerq')
        html = html.replace('द्वारा Nerq', 'bởi Nerq')
        html = html.replace('от Nerq', 'bởi Nerq')
        html = html.replace('przez Nerq', 'bởi Nerq')
        html = html.replace('di Nerq', 'bởi Nerq')
        html = html.replace('by Nerq', 'bởi Nerq')

        # 14. Breadcrumb in JSON-LD
        html = html.replace('"Safety Reports"', '"Báo cáo bảo mật"')

        # 15. Fix Schema.org @type that got wrongly translated by _CONTENT_TRANSLATIONS
        html = html.replace('"@type": "Đánh giá"', '"@type": "Review"')
        html = html.replace('"@type":"Đánh giá"', '"@type":"Review"')
        # reviewBody translation
        html = html.replace('Proceed with caution.', 'Tiến hành thận trọng.')
        html = html.replace('Not recommended.', 'Không khuyến nghị.')
        # JSON-LD
        html = _re_t.sub(r'"name": "Is (.+?) Safe\?', r'"name": "\1 có an toàn không?', html)
        html = _re_t.sub(r'"name": "Is (.+?) Safe to Visit\?', r'"name": "\1 có an toàn để ghé thăm không?', html)
        html = _re_t.sub(r'og:title" content="Is (.+?) Safe\?', r'og:title" content="\1 có an toàn không?', html)
        html = _re_t.sub(r'nerq:question" content="Is (.+?) safe', r'nerq:question" content="\1 có an toàn', html)

        # Fix: Meta description English fragments
        html = html.replace('0 known vulnerabilities', '0 lỗ hổng đã biết')
        html = html.replace('known vulnerabilities', 'lỗ hổng đã biết')
        html = html.replace('Independent security analysis of', 'Phân tích bảo mật độc lập của')
        html = html.replace('trust signals, vulnerabilities, compliance, and safer alternatives', 'tín hiệu tin cậy, lỗ hổng, tuân thủ và các lựa chọn an toàn hơn')
        # Fix: License
        html = html.replace('License: Not specified', 'Giấy phép: Chưa xác định')
        html = html.replace('License: See repository', 'Giấy phép: Xem repository')
        # Fix: ALL FAQ questions
        html = _re_t.sub(r"What is (.+?)'s trust score\?", r'Điểm tin cậy của \1 là bao nhiêu?', html)
        html = _re_t.sub(r"(.+?) là gì\?'s trust score\?", r'Điểm tin cậy của \1 là bao nhiêu?', html)
        html = _re_t.sub(r'Is (.+?) safe to use\?', r'\1 có an toàn để sử dụng không?', html)
        html = _re_t.sub(r'Is (.+?) safe\?', r'\1 có an toàn không?', html)
        html = _re_t.sub(r'What are safer alternatives to (.+?)\?', r'Các lựa chọn an toàn hơn cho \1 là gì?', html)
        html = _re_t.sub(r'Does (.+?) have known vulnerabilities\?', r'\1 có lỗ hổng đã biết không?', html)
        html = _re_t.sub(r'Does (.+?) have lỗ hổng đã biết\?', r'\1 có lỗ hổng đã biết không?', html)
        html = _re_t.sub(r'How actively maintained is (.+?)\?', r'\1 được bảo trì tích cực như thế nào?', html)
        html = _re_t.sub(r'How does (.+?) compare to similar', r'\1 so với các', html)
        html = _re_t.sub(r'Can I use (.+?) in a regulated environment\?', r'Tôi có thể sử dụng \1 trong môi trường quy định không?', html)
        # Fix: Footer remaining English
        html = html.replace('dimensions. Data from', 'tiêu chí. Dữ liệu từ')
        html = html.replace('Data from', 'Dữ liệu từ')

    elif lang == "nl":
        import re as _re_t
        html = _re_t.sub(r'<title>Is (.+?) Safe\?', r'<title>Is \1 veilig?', html, count=1)
        html = html.replace('Independent Trust &amp; Security Analysis 2026 | Nerq', 'Onafhankelijke vertrouwens- en beveiligingsanalyse 2026 | Nerq')
        html = _re_t.sub(r'>Is (.+?) Safe\?<', r'>Is \1 veilig?<', html)
        html = _re_t.sub(r'>Is (.+?) safe\?<', r'>Is \1 veilig?<', html)
        html = _re_t.sub(r'>What data does (.+?) collect\?<', r'>Welke gegevens verzamelt \1?<', html)
        html = _re_t.sub(r'>Is (.+?) secure\?<', r'>Is \1 veilig?<', html)
        html = _re_t.sub(r'>(.+?) Across Platforms<', r'>\1 op andere platforms<', html)
        html = _re_t.sub(r'>Safety Guide: (.+?)<', r'>Beveiligingsgids: \1<', html)
        html = _re_t.sub(r">What is (.+?)\?<", r">Wat is \1?<", html)
        html = html.replace('>Details<', '>Details<')
        html = _re_t.sub(r'>Is (.+?) Safe to Visit\?', r'>Is \1 veilig om te bezoeken?', html)
        html = _re_t.sub(r'>Is (.+?) safe for solo travelers\?<', r'>Is \1 veilig voor soloreiziger?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for women\?<', r'>Is \1 veilig voor vrouwen?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for LGBTQ\+ travelers\?<', r'>Is \1 veilig voor LGBTQ+-reizigers?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for families\?<', r'>Is \1 veilig voor gezinnen?<', html)
        html = _re_t.sub(r'>Is (.+?) safe to visit right now\?<', r'>Is \1 nu veilig om te bezoeken?<', html)
        html = _re_t.sub(r'>Is tap water safe to drink in (.+?)\?<', r'>Is kraanwater veilig om te drinken in \1?<', html)
        html = _re_t.sub(r'>Do I need vaccinations for (.+?)\?<', r'>Heb ik vaccinaties nodig voor \1?<', html)
        html = _re_t.sub(r'>What are safer alternatives to (.+?)\?<', r'>Wat zijn veiligere alternatieven voor \1?<', html)
        html = _re_t.sub(r'>What are the side effects of (.+?)\?<', r'>Wat zijn de bijwerkingen van \1?<', html)
        html = _re_t.sub(r'>Does (.+?) interact with medications\?<', r'>Heeft \1 interacties met medicijnen?<', html)
        html = _re_t.sub(r"(.+?)'s trust score of", r'de vertrouwensscore van \1 is', html)
        html = _re_t.sub(r'Nerq of (\d)', r'Nerq \1', html)
        # CRITICAL ORDER: replace longer phrases before standalone 'Trust Score'
        html = html.replace('has a Nerq Trust Score of', 'heeft een Nerq Vertrouwensscore van')
        html = html.replace('with a Nerq Trust Score of', 'met een Nerq Vertrouwensscore van')
        html = html.replace('Trust Score Breakdown', 'Vertrouwensscore uitsplitsing')
        html = html.replace('Trust Score', 'Vertrouwensscore')
        html = html.replace('Safety Score Breakdown', 'Beveiligingsscore uitsplitsing')
        html = html.replace('Safety Score', 'Beveiligingsscore')
        html = html.replace('Trust Analysis 2026', 'Vertrouwensanalyse 2026')
        # Nav
        html = html.replace('>Search<', '>Zoeken<')
        html = html.replace('>Apps<', '>Apps<')
        html = html.replace('>Packages<', '>Pakketten<')
        html = html.replace('>Extensions<', '>Extensies<')
        html = html.replace('>Websites<', '>Websites<')
        html = html.replace('>Travel<', '>Reizen<')
        html = html.replace('>Charities<', '>Liefdadigheid<')
        html = html.replace('>Compare<', '>Vergelijken<')
        html = html.replace('>Resources<', '>Bronnen<')
        html = html.replace('>About<', '>Over<')
        html = html.replace('>Check Safety<', '>Beveiliging controleren<')
        html = html.replace('>Games<', '>Spellen<')
        html = html.replace('>Countries<', '>Landen<')
        html = html.replace('>Check Website<', '>Website controleren<')
        html = html.replace('>Safety Guides<', '>Beveiligingsgidsen<')
        # Footer text
        html = html.replace('Trust scores for software, apps, websites, travel destinations, and charities', 'Vertrouwensscores voor software, apps, websites, reisbestemmingen en goede doelen')
        html = html.replace('20 languages', '20 talen')
        html = html.replace('>Guides<', '>Gidsen<')
        html = html.replace('>Mobile Apps<', '>Mobiele apps<')
        html = html.replace('>Trust Badges<', '>Vertrouwensbadges<')
        html = html.replace('>VPNs<', '>VPN\'s<')
        html = html.replace('7.5M+ entities from 26 registries. Independent. Data-driven.', '7,5M+ entiteiten uit 26 registers. Onafhankelijk. Datagedreven.')

        # ── Dynamic paragraph translations ──

        # 1. Verdict lead
        html = _re_t.sub(
            r'Yes, (.+?) is safe to use\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Ja, \1 is veilig om te gebruiken. \1 is een \2 met een Nerq Vertrouwensscore van \3/100 (\4).', html)
        html = _re_t.sub(
            r'Use (.+?) with some caution\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Gebruik \1 met enige voorzichtigheid. \1 is een \2 met een Nerq Vertrouwensscore van \3/100 (\4).', html)
        html = _re_t.sub(
            r'Exercise caution with (.+?)\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Wees voorzichtig met \1. \1 is een \2 met een Nerq Vertrouwensscore van \3/100 (\4).', html)

        # 2. Short answer box
        html = html.replace('<strong>YES</strong>', '<strong>JA</strong>')
        html = html.replace('<strong>CAUTION</strong>', '<strong>VOORZICHTIGHEID</strong>')
        html = html.replace('<strong>NO — USE WITH CAUTION</strong>', '<strong>NEE — GEBRUIK MET VOORZICHTIGHEID</strong>')

        # 3. Citation detail / verdict detail
        html = html.replace("It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption", 'Het voldoet aan de Nerq vertrouwensdrempel met sterke signalen voor beveiliging, onderhoud en acceptatie door de gemeenschap')
        html = html.replace('It has moderate trust signals but shows some areas of concern that warrant attention', 'Het heeft gematigde vertrouwenssignalen maar toont enkele aandachtspunten')
        html = html.replace('It has below-average trust signals with significant gaps in security, maintenance, or documentation', 'Het heeft benedengemiddelde vertrouwenssignalen met aanzienlijke lacunes in beveiliging, onderhoud of documentatie')
        html = html.replace('Recommended for production use', 'Aanbevolen voor productiegebruik')
        html = html.replace('It is recommended for production use.', 'Het wordt aanbevolen voor productiegebruik.')
        html = html.replace('review the full report below for specific considerations', 'bekijk het volledige rapport hieronder voor specifieke overwegingen')
        html = html.replace('Suitable for development use', 'Geschikt voor ontwikkelingsgebruik')
        html = html.replace('review security and maintenance signals before production deployment', 'controleer beveiligings- en onderhoudssignalen vóór productie-implementatie')
        html = html.replace('Not recommended for production use without thorough manual review and additional security measures', 'Niet aanbevolen voor productiegebruik zonder grondige handmatige controle en aanvullende beveiligingsmaatregelen')
        html = html.replace('It is below the recommended threshold of 70.', 'Het ligt onder de aanbevolen drempel van 70.')

        # 4. "X is a Y — description"
        html = _re_t.sub(r'>(.+?) is a (Node\.js package|Python package|Rust crate|Chrome extension|WordPress plugin|VPN service|game|website|SaaS platform|Firefox extension|VS Code extension|iOS app|Android app) — ',
                         r'>\1 is een \2 — ', html)

        # 5. Entity type translations in body text
        html = html.replace('is a Node.js package', 'is een Node.js-pakket')
        html = html.replace('is a Python package', 'is een Python-pakket')
        html = html.replace('is a Rust crate', 'is een Rust-crate')
        html = html.replace('is a Chrome extension', 'is een Chrome-extensie')
        html = html.replace('is a WordPress plugin', 'is een WordPress-plugin')
        html = html.replace('is a VPN service', 'is een VPN-dienst')
        html = html.replace('is a iOS app', 'is een iOS-app')
        html = html.replace('is a Android app', 'is een Android-app')

        # 6. Safety guide text
        html = html.replace("to check for vulnerabilities. Review the package's GitHub repository for recent commits.", 'om te controleren op kwetsbaarheden. Bekijk de GitHub-repository van het pakket voor recente commits.')
        html = html.replace('You can also check the trust score via API:', 'U kunt de vertrouwensscore ook via API controleren:')
        html = html.replace('watch for:', 'let op:')
        html = html.replace('dependency vulnerabilities, malicious packages, typosquatting', 'kwetsbaarheden in afhankelijkheden, kwaadaardige pakketten, typosquatting')
        html = html.replace("Run your package manager's audit command regularly.", 'Voer regelmatig de auditcommando van uw pakketbeheerder uit.')
        html = html.replace('>Run <code>', '>Uitvoeren <code>')

        # 7. King sections — privacy/security
        html = _re_t.sub(r'(.+?) is a Node\.js package maintained by (.+?)\.', r'\1 is een Node.js-pakket onderhouden door \2.', html)
        html = _re_t.sub(r'(.+?) is a (.+?) maintained by (.+?)\.', r'\1 is een \2 onderhouden door \3.', html)
        html = html.replace(' maintained by ', ' onderhouden door ')
        html = html.replace('As a development package,', 'Als een ontwikkelingspakket,')
        html = html.replace('does not directly collect end-user personal data', 'verzamelt geen persoonlijke gegevens van eindgebruikers direct')
        html = html.replace('However, applications built with it may collect data depending on implementation', 'Toepassingen gebouwd met dit pakket kunnen echter gegevens verzamelen afhankelijk van de implementatie')
        html = html.replace("Review the package's dependencies for potential supply chain risks.", 'Controleer de afhankelijkheden van het pakket op mogelijke supply chain-risico\'s.')
        html = html.replace('License information not available.', 'Licentie-informatie niet beschikbaar.')
        html = html.replace('Open-source packages allow independent security review of the source code.', 'Open-source pakketten maken onafhankelijke beveiligingsbeoordeling van de broncode mogelijk.')
        html = html.replace('known vulnerabilities (CVEs) in the National Vulnerability Database', 'bekende kwetsbaarheden (CVE\'s) in de National Vulnerability Database')
        html = html.replace('This is a clean record.', 'Dit is een schone staat van dienst.')
        html = html.replace('Review advisories and update to the latest version.', 'Bekijk de adviezen en update naar de nieuwste versie.')

        html = html.replace('and has not yet reached Nerq trust threshold (70+).', 'en heeft de Nerq vertrouwensdrempel (70+) nog niet bereikt.')
        html = html.replace('and meets Nerq trust threshold', 'en voldoet aan de Nerq vertrouwensdrempel')
        html = html.replace('This score is based on automated analysis of security, maintenance, community, and quality signals.', 'Deze score is gebaseerd op geautomatiseerde analyse van beveiligings-, onderhouds-, gemeenschaps- en kwaliteitssignalen.')

        # 8. Methodology
        html = html.replace('using the same methodology, enabling direct cross-entity comparison', 'met behulp van dezelfde methodologie, waardoor directe vergelijking tussen entiteiten mogelijk is')
        html = html.replace('Scores are updated continuously as new data becomes available', 'Scores worden continu bijgewerkt naarmate nieuwe gegevens beschikbaar komen')
        html = html.replace('is computed from', 'wordt berekend uit')
        html = html.replace('The score reflects', 'De score weerspiegelt')
        html = html.replace('independent dimensions', 'onafhankelijke dimensies')
        html = html.replace('Each dimension is weighted equally to produce the composite trust score.', 'Elke dimensie wordt gelijk gewogen om de samengestelde vertrouwensscore te produceren.')

        # 9. Key findings / signal descriptions
        html = html.replace('Composite trust score:', 'Samengestelde vertrouwensscore:')
        html = html.replace('across all available signals', 'over alle beschikbare signalen')
        html = html.replace('Code quality, vulnerability exposure, and security practices.', 'Codekwaliteit, kwetsbaarheidsblootstelling en beveiligingspraktijken.')
        html = html.replace('Update frequency, issue responsiveness, active development.', 'Updatefrequentie, responsiviteit op problemen, actieve ontwikkeling.')
        html = html.replace('README quality, API docs, usage examples.', 'README-kwaliteit, API-documentatie, gebruiksvoorbeelden.')
        html = html.replace('Community adoption.', 'Acceptatie door de gemeenschap.')
        html = html.replace('Composite score across all trust dimensions.', 'Samengestelde score over alle vertrouwensdimensies.')

        # 10. FAQ answers
        html = html.replace('Yes, it is safe to use.', 'Ja, het is veilig om te gebruiken.')
        html = html.replace('Use with some caution.', 'Gebruik met enige voorzichtigheid.')
        html = html.replace('Exercise caution.', 'Wees voorzichtig.')
        html = html.replace('Significant trust concerns.', 'Aanzienlijke vertrouwensproblemen.')
        html = html.replace('Strongest signal:', 'Sterkste signaal:')
        html = html.replace('Score based on', 'Score gebaseerd op')
        html = html.replace('multiple trust dimensions', 'meerdere vertrouwensdimensies')
        html = html.replace('Scores update as new data becomes available.', 'Scores worden bijgewerkt naarmate nieuwe gegevens beschikbaar komen.')
        html = html.replace('check back soon', 'kom snel terug')
        html = html.replace('higher-rated alternatives include', 'hoger beoordeelde alternatieven zijn onder meer')
        html = html.replace('more Node.js packages are being analyzed', 'meer Node.js-pakketten worden geanalyseerd')
        html = html.replace('more Python packages are being analyzed', 'meer Python-pakketten worden geanalyseerd')
        html = html.replace('Meets Nerq Verified threshold.', 'Voldoet aan de Nerq Verified drempel.')

        # 11. Security check FAQ
        html = html.replace('Nerq checks', 'Nerq controleert')
        html = html.replace('against NVD, OSV.dev, and registry-specific vulnerability databases', 'tegen NVD, OSV.dev en registerspecifieke kwetsbaarheidsdatabases')
        html = html.replace('Current security score:', 'Huidige beveiligingsscore:')
        html = html.replace("Run your package manager's audit command for the latest findings.", 'Voer de auditcommando van uw pakketbeheerder uit voor de nieuwste bevindingen.')
        html = html.replace('has a trust score of', 'heeft een vertrouwensscore van')
        html = html.replace('has a Nerq Trust Score of', 'heeft een Nerq Vertrouwensscore van')

        # 12. Footer bottom
        html = html.replace('trust scores for all software', 'vertrouwensscores voor alle software')
        html = html.replace('7.5M+ entities', '7,5M+ entiteiten')
        html = html.replace('26 registries', '26 registers')

        # 13. og:description — "door Nerq" + fix all other language suffixes
        html = html.replace('Independent safety assessment by Nerq.', 'Onafhankelijke veiligheidsbeoordeling door Nerq.')
        html = html.replace('Independent safety assessment by Nerq', 'Onafhankelijke veiligheidsbeoordeling door Nerq')
        html = html.replace('trust grade,', 'vertrouwensrang,')
        html = html.replace('por Nerq', 'door Nerq')
        html = html.replace('oleh Nerq', 'door Nerq')
        html = html.replace('od Nerq', 'door Nerq')
        html = html.replace('Nerq tarafından', 'door Nerq')
        html = html.replace('द्वारा Nerq', 'door Nerq')
        html = html.replace('от Nerq', 'door Nerq')
        html = html.replace('przez Nerq', 'door Nerq')
        html = html.replace('di Nerq', 'door Nerq')
        html = html.replace('bởi Nerq', 'door Nerq')
        html = html.replace('by Nerq', 'door Nerq')

        # 14. Breadcrumb in JSON-LD
        html = html.replace('"Safety Reports"', '"Veiligheidsrapporten"')

        # 15. Fix Schema.org @type that got wrongly translated by _CONTENT_TRANSLATIONS
        html = html.replace('"@type": "Beoordeling"', '"@type": "Review"')
        html = html.replace('"@type":"Beoordeling"', '"@type":"Review"')
        # reviewBody translation
        html = html.replace('Proceed with caution.', 'Ga voorzichtig te werk.')
        html = html.replace('Not recommended.', 'Niet aanbevolen.')
        # JSON-LD
        html = _re_t.sub(r'"name": "Is (.+?) Safe\?', r'"name": "Is \1 veilig?', html)
        html = _re_t.sub(r'"name": "Is (.+?) Safe to Visit\?', r'"name": "Is \1 veilig om te bezoeken?', html)
        html = _re_t.sub(r'og:title" content="Is (.+?) Safe\?', r'og:title" content="Is \1 veilig?', html)
        html = _re_t.sub(r'nerq:question" content="Is (.+?) safe', r'nerq:question" content="Is \1 veilig', html)

        # Fix: ALL FAQ questions (MUST come BEFORE generic "known vulnerabilities" replacement)
        html = _re_t.sub(r"What is (.+?)'s trust score\?", r'Wat is de vertrouwensscore van \1?', html)
        html = _re_t.sub(r'Is (.+?) safe to use\?', r'Is \1 veilig om te gebruiken?', html)
        html = _re_t.sub(r'Is (.+?) safe\?', r'Is \1 veilig?', html)
        html = _re_t.sub(r'What are safer alternatives to (.+?)\?', r'Wat zijn veiligere alternatieven voor \1?', html)
        html = _re_t.sub(r'Does (.+?) have known vulnerabilities\?', r'Heeft \1 bekende kwetsbaarheden?', html)
        html = _re_t.sub(r'How actively maintained is (.+?)\?', r'Hoe actief wordt \1 onderhouden?', html)
        html = _re_t.sub(r'How does (.+?) compare to similar', r'Hoe verhoudt \1 zich tot vergelijkbare', html)
        html = _re_t.sub(r'Can I use (.+?) in a regulated environment\?', r'Kan ik \1 gebruiken in een gereguleerde omgeving?', html)
        # Fix: Meta description English fragments (AFTER FAQ to avoid breaking FAQ patterns)
        html = html.replace('0 known vulnerabilities', '0 bekende kwetsbaarheden')
        html = html.replace('known vulnerabilities', 'bekende kwetsbaarheden')
        html = html.replace('Independent security analysis of', 'Onafhankelijke beveiligingsanalyse van')
        html = html.replace('trust signals, vulnerabilities, compliance, and safer alternatives', 'vertrouwenssignalen, kwetsbaarheden, naleving en veiligere alternatieven')
        # Fix: License
        html = html.replace('License: Not specified', 'Licentie: Niet opgegeven')
        html = html.replace('License: See repository', 'Licentie: Zie repository')
        # Fallback: FAQ Q4 if "known vulnerabilities" was already replaced
        html = _re_t.sub(r'Does (.+?) have bekende kwetsbaarheden\?', r'Heeft \1 bekende kwetsbaarheden?', html)
        # Fix: Footer remaining English
        html = html.replace('dimensions. Data from', 'dimensies. Gegevens van')
        html = html.replace('Data from', 'Gegevens van')

    elif lang == "sv":
        import re as _re_t
        html = _re_t.sub(r'<title>Is (.+?) Safe\?', r'<title>Är \1 säker?', html, count=1)
        html = html.replace('Independent Trust &amp; Security Analysis 2026 | Nerq', 'Oberoende förtroende- och säkerhetsanalys 2026 | Nerq')
        html = _re_t.sub(r'>Is (.+?) Safe\?<', r'>Är \1 säker?<', html)
        html = _re_t.sub(r'>Is (.+?) safe\?<', r'>Är \1 säker?<', html)
        html = _re_t.sub(r'>What data does (.+?) collect\?<', r'>Vilka data samlar \1 in?<', html)
        html = _re_t.sub(r'>Is (.+?) secure\?<', r'>Är \1 säker?<', html)
        html = _re_t.sub(r'>(.+?) Across Platforms<', r'>\1 på andra plattformar<', html)
        html = _re_t.sub(r'>Safety Guide: (.+?)<', r'>Säkerhetsguide: \1<', html)
        html = _re_t.sub(r">What is (.+?)\?<", r">Vad är \1?<", html)
        html = html.replace('>Details<', '>Detaljer<')
        html = _re_t.sub(r'>Is (.+?) Safe to Visit\?', r'>Är \1 säkert att besöka?', html)
        html = _re_t.sub(r'>Is (.+?) safe for solo travelers\?<', r'>Är \1 säkert för ensamma resenärer?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for women\?<', r'>Är \1 säkert för kvinnor?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for LGBTQ\+ travelers\?<', r'>Är \1 säkert för LGBTQ+-resenärer?<', html)
        html = _re_t.sub(r'>Is (.+?) safe for families\?<', r'>Är \1 säkert för familjer?<', html)
        html = _re_t.sub(r'>Is (.+?) safe to visit right now\?<', r'>Är \1 säkert att besöka just nu?<', html)
        html = _re_t.sub(r'>Is tap water safe to drink in (.+?)\?<', r'>Är kranvattnet i \1 säkert att dricka?<', html)
        html = _re_t.sub(r'>Do I need vaccinations for (.+?)\?<', r'>Behöver jag vaccinationer för \1?<', html)
        html = _re_t.sub(r'>What are safer alternatives to (.+?)\?<', r'>Vilka säkrare alternativ finns till \1?<', html)
        html = _re_t.sub(r'>What are the side effects of (.+?)\?<', r'>Vilka biverkningar har \1?<', html)
        html = _re_t.sub(r'>Does (.+?) interact with medications\?<', r'>Interagerar \1 med läkemedel?<', html)
        html = _re_t.sub(r"(.+?)'s trust score of", r'förtroendepoängen för \1 är', html)
        html = _re_t.sub(r'Nerq of (\d)', r'Nerq \1', html)
        # CRITICAL ORDER: replace longer phrases before standalone 'Trust Score'
        html = html.replace('has a Nerq Trust Score of', 'har ett Nerq-förtroendepoäng på')
        html = html.replace('with a Nerq Trust Score of', 'med ett Nerq-förtroendepoäng på')
        html = html.replace('Trust Score Breakdown', 'Förtroendepoäng i detalj')
        html = html.replace('Trust Score', 'Förtroendepoäng')
        html = html.replace('Safety Score Breakdown', 'Säkerhetspoäng i detalj')
        html = html.replace('Safety Score', 'Säkerhetspoäng')
        html = html.replace('Trust Analysis 2026', 'Förtroendeanalys 2026')
        # Nav
        html = html.replace('>Search<', '>Sök<')
        html = html.replace('>Apps<', '>Appar<')
        html = html.replace('>Packages<', '>Paket<')
        html = html.replace('>Extensions<', '>Tillägg<')
        html = html.replace('>Websites<', '>Webbplatser<')
        html = html.replace('>Travel<', '>Resor<')
        html = html.replace('>Charities<', '>Välgörenhet<')
        html = html.replace('>Compare<', '>Jämför<')
        html = html.replace('>Resources<', '>Resurser<')
        html = html.replace('>About<', '>Om<')
        html = html.replace('>Check Safety<', '>Kontrollera säkerhet<')
        html = html.replace('>Games<', '>Spel<')
        html = html.replace('>Countries<', '>Länder<')
        html = html.replace('>Check Website<', '>Kontrollera webbplats<')
        html = html.replace('>Safety Guides<', '>Säkerhetsguider<')
        # Footer text
        html = html.replace('Trust scores for software, apps, websites, travel destinations, and charities', 'Förtroendepoäng för mjukvara, appar, webbplatser, resmål och välgörenhetsorganisationer')
        html = html.replace('20 languages', '20 språk')
        html = html.replace('>Guides<', '>Guider<')
        html = html.replace('>Mobile Apps<', '>Mobilappar<')
        html = html.replace('>Trust Badges<', '>Förtroendemärken<')
        html = html.replace('>VPNs<', '>VPN:er<')
        html = html.replace('7.5M+ entities from 26 registries. Independent. Data-driven.', '7,5M+ entiteter från 26 register. Oberoende. Datadriven.')

        # ── Dynamic paragraph translations ──

        # 1. Verdict lead
        html = _re_t.sub(
            r'Yes, (.+?) is safe to use\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Ja, \1 är säker att använda. \1 är ett \2 med ett Nerq-förtroendepoäng på \3/100 (\4).', html)
        html = _re_t.sub(
            r'Use (.+?) with some caution\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Använd \1 med försiktighet. \1 är ett \2 med ett Nerq-förtroendepoäng på \3/100 (\4).', html)
        html = _re_t.sub(
            r'Exercise caution with (.+?)\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'Var försiktig med \1. \1 är ett \2 med ett Nerq-förtroendepoäng på \3/100 (\4).', html)

        # 2. Short answer box
        html = html.replace('<strong>YES</strong>', '<strong>JA</strong>')
        html = html.replace('<strong>CAUTION</strong>', '<strong>VAR FÖRSIKTIG</strong>')
        html = html.replace('<strong>NO — USE WITH CAUTION</strong>', '<strong>NEJ — ANVÄND MED FÖRSIKTIGHET</strong>')

        # 3. Citation detail / verdict detail
        html = html.replace("It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption", 'Uppfyller Nerqs förtroendetröskel med starka signaler inom säkerhet, underhåll och communityanvändning')
        html = html.replace('It has moderate trust signals but shows some areas of concern that warrant attention', 'Har måttliga förtroendesignaler men uppvisar vissa oroande områden')
        html = html.replace('It has below-average trust signals with significant gaps in security, maintenance, or documentation', 'Har lägre än genomsnittliga förtroendesignaler med betydande luckor i säkerhet, underhåll eller dokumentation')
        html = html.replace('Recommended for production use', 'Rekommenderas för produktionsanvändning')
        html = html.replace('It is recommended for production use.', 'Rekommenderas för produktionsanvändning.')
        html = html.replace('review the full report below for specific considerations', 'se hela rapporten nedan för specifika överväganden')
        html = html.replace('Suitable for development use', 'Lämplig för utvecklingsanvändning')
        html = html.replace('review security and maintenance signals before production deployment', 'granska säkerhets- och underhållssignaler innan produktionsdriftsättning')
        html = html.replace('Not recommended for production use without thorough manual review and additional security measures', 'Rekommenderas inte för produktionsanvändning utan noggrann manuell granskning och ytterligare säkerhetsåtgärder')
        html = html.replace('It is below the recommended threshold of 70.', 'Ligger under den rekommenderade gränsen på 70.')

        # 4. "X is a Y — description"
        html = _re_t.sub(r'>(.+?) is a (Node\.js package|Python package|Rust crate|Chrome extension|WordPress plugin|VPN service|game|website|SaaS platform|Firefox extension|VS Code extension|iOS app|Android app) — ',
                         r'>\1 är ett \2 — ', html)

        # 5. Entity type translations in body text
        html = html.replace('is a Node.js package', 'är ett Node.js-paket')
        html = html.replace('is a Python package', 'är ett Python-paket')
        html = html.replace('is a Rust crate', 'är en Rust-crate')
        html = html.replace('is a Chrome extension', 'är ett Chrome-tillägg')
        html = html.replace('is a WordPress plugin', 'är ett WordPress-tillägg')
        html = html.replace('is a VPN service', 'är en VPN-tjänst')
        html = html.replace('is a iOS app', 'är en iOS-app')
        html = html.replace('is a Android app', 'är en Android-app')

        # 6. Safety guide text
        html = html.replace("to check for vulnerabilities. Review the package's GitHub repository for recent commits.", 'för att söka efter sårbarheter. Granska paketets GitHub-repositorium för senaste incheckningar.')
        html = html.replace('You can also check the trust score via API:', 'Du kan också kontrollera förtroendepoängen via API:')
        html = html.replace('watch for:', 'håll utkik efter:')
        html = html.replace('dependency vulnerabilities, malicious packages, typosquatting', 'sårbarheter i beroenden, skadliga paket, typosquatting')
        html = html.replace("Run your package manager's audit command regularly.", 'Kör pakethanterarens granskningskommando regelbundet.')
        html = html.replace('>Run <code>', '>Kör <code>')

        # 7. King sections — privacy/security
        html = _re_t.sub(r'(.+?) is a Node\.js package maintained by (.+?)\.', r'\1 är ett Node.js-paket som underhålls av \2.', html)
        html = _re_t.sub(r'(.+?) is a (.+?) maintained by (.+?)\.', r'\1 är ett \2 som underhålls av \3.', html)
        html = html.replace(' maintained by ', ' underhålls av ')
        html = html.replace('As a development package,', 'Som ett utvecklingspaket,')
        html = html.replace('does not directly collect end-user personal data', 'samlar inte direkt in slutanvändares personuppgifter')
        html = html.replace('However, applications built with it may collect data depending on implementation', 'Applikationer byggda med det kan dock samla in data beroende på implementationen')
        html = html.replace("Review the package's dependencies for potential supply chain risks.", 'Granska paketets beroenden för potentiella risker i leveranskedjan.')
        html = html.replace('License information not available.', 'Licensinformation saknas.')
        html = html.replace('Open-source packages allow independent security review of the source code.', 'Öppen källkod möjliggör oberoende säkerhetsgranskning av källkoden.')
        html = html.replace('known vulnerabilities (CVEs) in the National Vulnerability Database', 'kända sårbarheter (CVE:er) i National Vulnerability Database')
        html = html.replace('This is a clean record.', 'Detta är ett rent register.')
        html = html.replace('Review advisories and update to the latest version.', 'Granska säkerhetsrådgivningar och uppdatera till den senaste versionen.')

        html = html.replace('and has not yet reached Nerq trust threshold (70+).', 'och har ännu inte nått Nerqs förtroendetröskel (70+).')
        html = html.replace('and meets Nerq trust threshold', 'och uppfyller Nerqs förtroendetröskel')
        html = html.replace('This score is based on automated analysis of security, maintenance, community, and quality signals.', 'Denna poäng baseras på automatiserad analys av signaler för säkerhet, underhåll, community och kvalitet.')

        # 8. Methodology
        html = html.replace('using the same methodology, enabling direct cross-entity comparison', 'med samma metodik, vilket möjliggör direkt jämförelse mellan entiteter')
        html = html.replace('Scores are updated continuously as new data becomes available', 'Poäng uppdateras löpande när ny data finns tillgänglig')
        html = html.replace('is computed from', 'beräknas utifrån')
        html = html.replace('The score reflects', 'Poängen speglar')
        html = html.replace('independent dimensions', 'oberoende dimensioner')
        html = html.replace('Each dimension is weighted equally to produce the composite trust score.', 'Varje dimension ges lika vikt för att producera den sammansatta förtroendepoängen.')

        # 9. Key findings / signal descriptions
        html = html.replace('Composite trust score:', 'Sammansatt förtroendepoäng:')
        html = html.replace('across all available signals', 'utifrån alla tillgängliga signaler')
        html = html.replace('Code quality, vulnerability exposure, and security practices.', 'Kodkvalitet, sårbarhetsutsatthet och säkerhetspraxis.')
        html = html.replace('Update frequency, issue responsiveness, active development.', 'Uppdateringsfrekvens, responsivitet på ärenden, aktiv utveckling.')
        html = html.replace('README quality, API docs, usage examples.', 'README-kvalitet, API-dokumentation, användningsexempel.')
        html = html.replace('Community adoption.', 'Communityanvändning.')
        html = html.replace('Composite score across all trust dimensions.', 'Sammansatt poäng över alla förtroendedimensioner.')

        # 10. FAQ answers — CRITICAL: ALL FAQ question patterns FIRST
        html = _re_t.sub(r"What is (.+?)'s trust score\?", r'Vad är förtroendepoängen för \1?', html)
        html = _re_t.sub(r'Is (.+?) safe to use\?', r'Är \1 säker att använda?', html)
        html = _re_t.sub(r'Is (.+?) safe\?', r'Är \1 säker?', html)
        html = _re_t.sub(r'What are safer alternatives to (.+?)\?', r'Vilka säkrare alternativ finns till \1?', html)
        html = _re_t.sub(r'Does (.+?) have known vulnerabilities\?', r'Har \1 kända sårbarheter?', html)
        html = _re_t.sub(r'How actively maintained is (.+?)\?', r'Hur aktivt underhålls \1?', html)
        html = _re_t.sub(r'How does (.+?) compare to similar', r'Hur jämförs \1 med liknande', html)
        html = _re_t.sub(r'Can I use (.+?) in a regulated environment\?', r'Kan jag använda \1 i en reglerad miljö?', html)
        # Fix: Meta description English fragments (AFTER FAQ to avoid breaking FAQ patterns)
        html = html.replace('0 known vulnerabilities', '0 kända sårbarheter')
        html = html.replace('known vulnerabilities', 'kända sårbarheter')
        html = html.replace('Independent security analysis of', 'Oberoende säkerhetsanalys av')
        html = html.replace('trust signals, vulnerabilities, compliance, and safer alternatives', 'förtroendesignaler, sårbarheter, regelefterlevnad och säkrare alternativ')
        html = html.replace('Yes, it is safe to use.', 'Ja, det är säkert att använda.')
        html = html.replace('Use with some caution.', 'Använd med viss försiktighet.')
        html = html.replace('Exercise caution.', 'Var försiktig.')
        html = html.replace('Significant trust concerns.', 'Betydande förtroendeproblem.')
        html = html.replace('Strongest signal:', 'Starkaste signalen:')
        html = html.replace('Score based on', 'Poäng baserad på')
        html = html.replace('multiple trust dimensions', 'flera förtroendedimensioner')
        html = html.replace('Scores update as new data becomes available.', 'Poäng uppdateras när ny data finns tillgänglig.')
        html = html.replace('check back soon', 'kom tillbaka snart')
        html = html.replace('higher-rated alternatives include', 'högre betygsatta alternativ inkluderar')
        html = html.replace('more Node.js packages are being analyzed', 'fler Node.js-paket analyseras')
        html = html.replace('more Python packages are being analyzed', 'fler Python-paket analyseras')
        html = html.replace('Meets Nerq Verified threshold.', 'Uppfyller Nerqs verifierade tröskel.')

        # 11. Security check FAQ
        html = html.replace('Nerq checks', 'Nerq kontrollerar')
        html = html.replace('against NVD, OSV.dev, and registry-specific vulnerability databases', 'mot NVD, OSV.dev och registerspecifika sårbarhetsdatabaser')
        html = html.replace('Current security score:', 'Aktuellt säkerhetspoäng:')
        html = html.replace("Run your package manager's audit command for the latest findings.", 'Kör pakethanterarens granskningskommando för de senaste resultaten.')
        html = html.replace('has a trust score of', 'har ett förtroendepoäng på')
        html = html.replace('has a Nerq Trust Score of', 'har ett Nerq-förtroendepoäng på')

        # 12. Footer bottom
        html = html.replace('trust scores for all software', 'förtroendepoäng för all mjukvara')
        html = html.replace('7.5M+ entities', '7,5M+ entiteter')
        html = html.replace('26 registries', '26 register')

        # 13. og:description — "av Nerq" + fix all other language suffixes
        html = html.replace('Independent safety assessment by Nerq.', 'Oberoende säkerhetsbedömning av Nerq.')
        html = html.replace('Independent safety assessment by Nerq', 'Oberoende säkerhetsbedömning av Nerq')
        html = html.replace('trust grade,', 'förtroendebetyg,')
        html = html.replace('por Nerq', 'av Nerq')
        html = html.replace('oleh Nerq', 'av Nerq')
        html = html.replace('od Nerq', 'av Nerq')
        html = html.replace('Nerq tarafından', 'av Nerq')
        html = html.replace('द्वारा Nerq', 'av Nerq')
        html = html.replace('от Nerq', 'av Nerq')
        html = html.replace('przez Nerq', 'av Nerq')
        html = html.replace('di Nerq', 'av Nerq')
        html = html.replace('Nerq 제공', 'av Nerq')
        html = html.replace('bởi Nerq', 'av Nerq')
        html = html.replace('door Nerq', 'av Nerq')
        html = html.replace('by Nerq', 'av Nerq')

        # 14. Breadcrumb in JSON-LD
        html = html.replace('"Safety Reports"', '"Säkerhetsrapporter"')

        # 15. Fix Schema.org @type that got wrongly translated by _CONTENT_TRANSLATIONS
        html = html.replace('"@type": "Recension"', '"@type": "Review"')
        html = html.replace('"@type":"Recension"', '"@type":"Review"')
        # reviewBody translation
        html = html.replace('Proceed with caution.', 'Fortsätt med försiktighet.')
        html = html.replace('Not recommended.', 'Rekommenderas inte.')
        # JSON-LD
        html = _re_t.sub(r'"name": "Is (.+?) Safe\?', r'"name": "Är \1 säker?', html)
        html = _re_t.sub(r'"name": "Is (.+?) Safe to Visit\?', r'"name": "Är \1 säkert att besöka?', html)
        html = _re_t.sub(r'og:title" content="Is (.+?) Safe\?', r'og:title" content="Är \1 säker?', html)
        html = _re_t.sub(r'nerq:question" content="Is (.+?) safe', r'nerq:question" content="Är \1 säker', html)
        # Fallback: FAQ Q4 if "known vulnerabilities" was already replaced
        html = _re_t.sub(r'Har (.+?) kända sårbarheter\?', r'Har \1 kända sårbarheter?', html)
        # Fix: Footer remaining English
        html = html.replace('dimensions. Data from', 'dimensioner. Data från')
        html = html.replace('Data from', 'Data från')
        # Fix: License
        html = html.replace('License: Not specified', 'Licens: Ej angiven')
        html = html.replace('License: See repository', 'Licens: Se repositoriet')

    elif lang == "zh":
        import re as _re_t
        html = _re_t.sub(r'<title>Is (.+?) Safe\?', r'<title>\1安全吗？', html, count=1)
        html = html.replace('Independent Trust &amp; Security Analysis 2026 | Nerq', '独立信任与安全分析 2026 | Nerq')
        html = _re_t.sub(r'>Is (.+?) Safe\?<', r'>\1安全吗？<', html)
        html = _re_t.sub(r'>Is (.+?) safe\?<', r'>\1安全吗？<', html)
        html = _re_t.sub(r'>What data does (.+?) collect\?<', r'>\1收集哪些数据？<', html)
        html = _re_t.sub(r'>Is (.+?) secure\?<', r'>\1安全吗？<', html)
        html = _re_t.sub(r'>(.+?) Across Platforms<', r'>\1在其他平台<', html)
        html = _re_t.sub(r'>Safety Guide: (.+?)<', r'>安全指南：\1<', html)
        html = _re_t.sub(r">What is (.+?)\?<", r">\1是什么？<", html)
        html = html.replace('>Details<', '>详情<')
        html = _re_t.sub(r'>Is (.+?) Safe to Visit\?', r'>访问\1安全吗？', html)
        html = _re_t.sub(r'>Is (.+?) safe for solo travelers\?<', r'>\1对独自旅行者安全吗？<', html)
        html = _re_t.sub(r'>Is (.+?) safe for women\?<', r'>\1对女性安全吗？<', html)
        html = _re_t.sub(r'>Is (.+?) safe for LGBTQ\+ travelers\?<', r'>\1对 LGBTQ+ 旅行者安全吗？<', html)
        html = _re_t.sub(r'>Is (.+?) safe for families\?<', r'>\1对家庭安全吗？<', html)
        html = _re_t.sub(r'>Is (.+?) safe to visit right now\?<', r'>现在访问\1安全吗？<', html)
        html = _re_t.sub(r'>Is tap water safe to drink in (.+?)\?<', r'>\1的自来水可以安全饮用吗？<', html)
        html = _re_t.sub(r'>Do I need vaccinations for (.+?)\?<', r'>我去\1需要接种疫苗吗？<', html)
        html = _re_t.sub(r'>What are safer alternatives to (.+?)\?<', r'>\1有哪些更安全的替代品？<', html)
        html = _re_t.sub(r'>What are the side effects of (.+?)\?<', r'>\1的副作用有哪些？<', html)
        html = _re_t.sub(r'>Does (.+?) interact with medications\?<', r'>\1会与药物产生相互作用吗？<', html)
        html = _re_t.sub(r"(.+?)'s trust score of", r'\1的信任评分为', html)
        html = _re_t.sub(r'Nerq of (\d)', r'Nerq \1', html)
        # CRITICAL ORDER: replace longer phrases before standalone 'Trust Score'
        html = html.replace('has a Nerq Trust Score of', 'Nerq 信任评分为')
        html = html.replace('with a Nerq Trust Score of', 'Nerq 信任评分为')
        html = html.replace('Trust Score Breakdown', '信任评分详情')
        html = html.replace('Trust Score', '信任评分')
        html = html.replace('Safety Score Breakdown', '安全评分详情')
        html = html.replace('Safety Score', '安全评分')
        html = html.replace('Trust Analysis 2026', '信任分析 2026')
        # Nav
        html = html.replace('>Search<', '>搜索<')
        html = html.replace('>Apps<', '>应用<')
        html = html.replace('>Packages<', '>软件包<')
        html = html.replace('>Extensions<', '>扩展<')
        html = html.replace('>Websites<', '>网站<')
        html = html.replace('>Travel<', '>旅行<')
        html = html.replace('>Charities<', '>慈善<')
        html = html.replace('>Compare<', '>比较<')
        html = html.replace('>Resources<', '>资源<')
        html = html.replace('>About<', '>关于<')
        html = html.replace('>Check Safety<', '>检查安全性<')
        html = html.replace('>Games<', '>游戏<')
        html = html.replace('>Countries<', '>国家<')
        html = html.replace('>Check Website<', '>检查网站<')
        html = html.replace('>Safety Guides<', '>安全指南<')
        # Footer text
        html = html.replace('Trust scores for software, apps, websites, travel destinations, and charities', '软件、应用、网站、旅行目的地和慈善机构的信任评分')
        html = html.replace('20 languages', '20 种语言')
        html = html.replace('>Guides<', '>指南<')
        html = html.replace('>Mobile Apps<', '>移动应用<')
        html = html.replace('>Trust Badges<', '>信任徽章<')
        html = html.replace('>VPNs<', '>VPN<')
        html = html.replace('7.5M+ entities from 26 registries. Independent. Data-driven.', '来自 26 个注册表的 750 万+ 实体。独立。数据驱动。')

        # ── Dynamic paragraph translations ──

        # 1. Verdict lead
        html = _re_t.sub(
            r'Yes, (.+?) is safe to use\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'是的，\1可以安全使用。\1是一个\2，Nerq 信任评分为 \3/100（\4）。', html)
        html = _re_t.sub(
            r'Use (.+?) with some caution\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'请谨慎使用\1。\1是一个\2，Nerq 信任评分为 \3/100（\4）。', html)
        html = _re_t.sub(
            r'Exercise caution with (.+?)\. \1 is a (.+?) with a Nerq Trust Score of ([\d.]+)/100 \((\w[\w+-]*)\)',
            r'请对\1保持警惕。\1是一个\2，Nerq 信任评分为 \3/100（\4）。', html)

        # 2. Short answer box
        html = html.replace('<strong>YES</strong>', '<strong>是</strong>')
        html = html.replace('<strong>CAUTION</strong>', '<strong>谨慎</strong>')
        html = html.replace('<strong>NO — USE WITH CAUTION</strong>', '<strong>否——请谨慎使用</strong>')

        # 3. Citation detail / verdict detail
        html = html.replace("It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption", '在安全性、维护和社区采用方面信号强烈，达到了 Nerq 信任阈值')
        html = html.replace('It has moderate trust signals but shows some areas of concern that warrant attention', '信任信号中等，但存在一些值得关注的方面')
        html = html.replace('It has below-average trust signals with significant gaps in security, maintenance, or documentation', '信任信号低于平均水平，在安全性、维护或文档方面存在重大缺口')
        html = html.replace('Recommended for production use', '推荐用于生产环境')
        html = html.replace('It is recommended for production use.', '推荐用于生产环境。')
        html = html.replace('review the full report below for specific considerations', '请查看下方完整报告以了解具体注意事项')
        html = html.replace('Suitable for development use', '适合用于开发环境')
        html = html.replace('review security and maintenance signals before production deployment', '在生产部署前请查看安全性和维护信号')
        html = html.replace('Not recommended for production use without thorough manual review and additional security measures', '未经彻底手动审查和额外安全措施，不建议用于生产环境')
        html = html.replace('It is below the recommended threshold of 70.', '低于推荐阈值 70。')

        # 4. "X is a Y — description"
        html = _re_t.sub(r'>(.+?) is a (Node\.js package|Python package|Rust crate|Chrome extension|WordPress plugin|VPN service|game|website|SaaS platform|Firefox extension|VS Code extension|iOS app|Android app) — ',
                         r'>\1 是一个 \2 — ', html)

        # 5. Entity type translations in body text
        html = html.replace('is a Node.js package', '是一个 Node.js 包')
        html = html.replace('is a Python package', '是一个 Python 包')
        html = html.replace('is a Rust crate', '是一个 Rust crate')
        html = html.replace('is a Chrome extension', '是一个 Chrome 扩展')
        html = html.replace('is a WordPress plugin', '是一个 WordPress 插件')
        html = html.replace('is a VPN service', '是一项 VPN 服务')
        html = html.replace('is a iOS app', '是一款 iOS 应用')
        html = html.replace('is a Android app', '是一款 Android 应用')

        # 6. Safety guide text
        html = html.replace("to check for vulnerabilities. Review the package's GitHub repository for recent commits.", '以检查漏洞。请查看该包的 GitHub 仓库以获取最新提交记录。')
        html = html.replace('You can also check the trust score via API:', '您也可以通过 API 查看信任评分：')
        html = html.replace('watch for:', '请注意：')
        html = html.replace('dependency vulnerabilities, malicious packages, typosquatting', '依赖漏洞、恶意包、域名抢注')
        html = html.replace("Run your package manager's audit command regularly.", '请定期运行您的包管理器审计命令。')
        html = html.replace('>Run <code>', '>运行 <code>')

        # 7. King sections — privacy/security
        html = _re_t.sub(r'(.+?) is a Node\.js package maintained by (.+?)\.', r'\1 是一个由 \2 维护的 Node.js 包。', html)
        html = _re_t.sub(r'(.+?) is a (.+?) maintained by (.+?)\.', r'\1 是一个由 \3 维护的 \2。', html)
        html = html.replace(' maintained by ', ' 由...维护 ')
        html = html.replace('As a development package,', '作为开发包，')
        html = html.replace('does not directly collect end-user personal data', '不直接收集最终用户个人数据')
        html = html.replace('However, applications built with it may collect data depending on implementation', '但是，基于其构建的应用程序可能会根据实现方式收集数据')
        html = html.replace("Review the package's dependencies for potential supply chain risks.", '请检查包的依赖项以评估潜在的供应链风险。')
        html = html.replace('License information not available.', '许可证信息不可用。')
        html = html.replace('Open-source packages allow independent security review of the source code.', '开源包允许对源代码进行独立安全审查。')
        html = html.replace('known vulnerabilities (CVEs) in the National Vulnerability Database', '国家漏洞数据库中的已知漏洞（CVE）')
        html = html.replace('This is a clean record.', '这是一份清白记录。')
        html = html.replace('Review advisories and update to the latest version.', '请查看安全公告并更新至最新版本。')

        html = html.replace('and has not yet reached Nerq trust threshold (70+).', '且尚未达到 Nerq 信任阈值（70+）。')
        html = html.replace('and meets Nerq trust threshold', '且已达到 Nerq 信任阈值')
        html = html.replace('This score is based on automated analysis of security, maintenance, community, and quality signals.', '此评分基于对安全性、维护、社区和质量信号的自动分析。')

        # 8. Methodology
        html = html.replace('using the same methodology, enabling direct cross-entity comparison', '使用相同的方法，实现实体间的直接比较')
        html = html.replace('Scores are updated continuously as new data becomes available', '评分会在新数据可用时持续更新')
        html = html.replace('is computed from', '由以下内容计算得出')
        html = html.replace('The score reflects', '该评分反映了')
        html = html.replace('independent dimensions', '独立维度')
        html = html.replace('Each dimension is weighted equally to produce the composite trust score.', '每个维度被同等加权以产生综合信任评分。')

        # 9. Key findings / signal descriptions
        html = html.replace('Composite trust score:', '综合信任评分：')
        html = html.replace('across all available signals', '基于所有可用信号')
        html = html.replace('Code quality, vulnerability exposure, and security practices.', '代码质量、漏洞暴露和安全实践。')
        html = html.replace('Update frequency, issue responsiveness, active development.', '更新频率、问题响应速度、积极开发。')
        html = html.replace('README quality, API docs, usage examples.', 'README 质量、API 文档、使用示例。')
        html = html.replace('Community adoption.', '社区采用。')
        html = html.replace('Composite score across all trust dimensions.', '跨所有信任维度的综合评分。')

        # 10. FAQ answers — CRITICAL: ALL FAQ question patterns FIRST
        html = _re_t.sub(r"What is (.+?)'s trust score\?", r'\1的信任评分是多少？', html)
        html = _re_t.sub(r'Is (.+?) safe to use\?', r'\1可以安全使用吗？', html)
        html = _re_t.sub(r'Is (.+?) safe\?', r'\1安全吗？', html)
        html = _re_t.sub(r'What are safer alternatives to (.+?)\?', r'\1有哪些更安全的替代品？', html)
        html = _re_t.sub(r'Does (.+?) have known vulnerabilities\?', r'\1存在已知漏洞吗？', html)
        html = _re_t.sub(r'How actively maintained is (.+?)\?', r'\1的维护活跃度如何？', html)
        html = _re_t.sub(r'How does (.+?) compare to similar', r'\1与类似', html)
        html = _re_t.sub(r'Can I use (.+?) in a regulated environment\?', r'我可以在受监管环境中使用\1吗？', html)
        # Fix: Meta description English fragments (AFTER FAQ to avoid breaking FAQ patterns)
        html = html.replace('0 known vulnerabilities', '0 个已知漏洞')
        html = html.replace('known vulnerabilities', '已知漏洞')
        html = html.replace('Independent security analysis of', '以下内容的独立安全分析')
        html = html.replace('trust signals, vulnerabilities, compliance, and safer alternatives', '信任信号、漏洞、合规性和更安全的替代品')
        html = html.replace('Yes, it is safe to use.', '是的，可以安全使用。')
        html = html.replace('Use with some caution.', '请谨慎使用。')
        html = html.replace('Exercise caution.', '请保持警惕。')
        html = html.replace('Significant trust concerns.', '存在严重的信任问题。')
        html = html.replace('Strongest signal:', '最强信号：')
        html = html.replace('Score based on', '评分基于')
        html = html.replace('multiple trust dimensions', '多个信任维度')
        html = html.replace('Scores update as new data becomes available.', '评分会在新数据可用时更新。')
        html = html.replace('check back soon', '请稍后再查看')
        html = html.replace('higher-rated alternatives include', '评分更高的替代品包括')
        html = html.replace('more Node.js packages are being analyzed', '正在分析更多 Node.js 包')
        html = html.replace('more Python packages are being analyzed', '正在分析更多 Python 包')
        html = html.replace('Meets Nerq Verified threshold.', '达到 Nerq 验证阈值。')

        # 11. Security check FAQ
        html = html.replace('Nerq checks', 'Nerq 对照')
        html = html.replace('against NVD, OSV.dev, and registry-specific vulnerability databases', 'NVD、OSV.dev 和注册表特定漏洞数据库进行检查')
        html = html.replace('Current security score:', '当前安全评分：')
        html = html.replace("Run your package manager's audit command for the latest findings.", '请运行您的包管理器审计命令以获取最新结果。')
        html = html.replace('has a trust score of', '信任评分为')
        html = html.replace('has a Nerq Trust Score of', 'Nerq 信任评分为')

        # 12. Footer bottom
        html = html.replace('trust scores for all software', '所有软件的信任评分')
        html = html.replace('7.5M+ entities', '750 万+ 实体')
        html = html.replace('26 registries', '26 个注册表')

        # 13. og:description — "由 Nerq 提供" + fix all other language suffixes
        html = html.replace('Independent safety assessment by Nerq.', '由 Nerq 提供的独立安全评估。')
        html = html.replace('Independent safety assessment by Nerq', '由 Nerq 提供的独立安全评估')
        html = html.replace('trust grade,', '信任等级，')
        html = html.replace('por Nerq', '由 Nerq 提供')
        html = html.replace('oleh Nerq', '由 Nerq 提供')
        html = html.replace('od Nerq', '由 Nerq 提供')
        html = html.replace('Nerq tarafından', '由 Nerq 提供')
        html = html.replace('द्वारा Nerq', '由 Nerq 提供')
        html = html.replace('от Nerq', '由 Nerq 提供')
        html = html.replace('przez Nerq', '由 Nerq 提供')
        html = html.replace('di Nerq', '由 Nerq 提供')
        html = html.replace('Nerq 제공', '由 Nerq 提供')
        html = html.replace('bởi Nerq', '由 Nerq 提供')
        html = html.replace('door Nerq', '由 Nerq 提供')
        html = html.replace('av Nerq', '由 Nerq 提供')
        html = html.replace('by Nerq', '由 Nerq 提供')

        # 14. Breadcrumb in JSON-LD
        html = html.replace('"Safety Reports"', '"安全报告"')

        # 15. Fix Schema.org @type that got wrongly translated by _CONTENT_TRANSLATIONS
        html = html.replace('"@type": "评论"', '"@type": "Review"')
        html = html.replace('"@type":"评论"', '"@type":"Review"')
        # reviewBody translation
        html = html.replace('Proceed with caution.', '请谨慎操作。')
        html = html.replace('Not recommended.', '不推荐。')
        # JSON-LD
        html = _re_t.sub(r'"name": "Is (.+?) Safe\?', r'"name": "\1安全吗？', html)
        html = _re_t.sub(r'"name": "Is (.+?) Safe to Visit\?', r'"name": "访问\1安全吗？', html)
        html = _re_t.sub(r'og:title" content="Is (.+?) Safe\?', r'og:title" content="\1安全吗？', html)
        html = _re_t.sub(r'nerq:question" content="Is (.+?) safe', r'nerq:question" content="\1安全', html)
        # Fix: Footer remaining English
        html = html.replace('dimensions. Data from', '维度。数据来源于')
        html = html.replace('Data from', '数据来源于')
        # Fix: License
        html = html.replace('License: Not specified', '许可证：未指定')
        html = html.replace('License: See repository', '许可证：请查看仓库')

    # ── CONTENT TRANSLATIONS: Simple string replacements (run LAST as catch-all) ──
    translations = _CONTENT_TRANSLATIONS.get(lang)
    if translations:
        # Sort by length descending to prevent partial replacements
        sorted_pairs = sorted(translations.items(), key=lambda x: len(x[0]), reverse=True)
        for en, loc in sorted_pairs:
            if not en or not loc:
                continue
            # Tag-boundary replacements (safe, won't break HTML attributes)
            html = html.replace(f'>{en}<', f'>{loc}<')
            html = html.replace(f'>{en} ', f'>{loc} ')
            html = html.replace(f'"{en}"', f'"{loc}"')
            html = html.replace(f'content="{en}', f'content="{loc}')
            # Mid-text replacement for multi-word domain terms (compound phrases)
            # Only for strings 8+ chars — short strings risk false matches
            if len(en) >= 8:
                html = html.replace(en, loc)

    # ── POST-FIX: Restore Schema.org @type values that got wrongly translated ──
    # _CONTENT_TRANSLATIONS may replace "Review"→"Ulasan" etc. inside JSON-LD @type
    _schema_fixes = {
        "Ulasan": "Review", "Reseña": "Review", "Bewertung": "Review",
        "Avis": "Review", "レビュー": "Review", "Avaliação": "Review",
        "Recenze": "Review", "รีวิว": "Review", "Recenzie": "Review",
        "İnceleme": "Review", "समीक्षा": "Review", "Отзыв": "Review",
        "Opinia": "Review", "Recensione": "Review", "리뷰": "Review",
        "Đánh giá": "Review", "Beoordeling": "Review", "Recension": "Review",
        "评论": "Review", "Anmeldelse": "Review",
        "Pregunta": "Question", "Frage": "Question", "Pertanyaan": "Question",
        "Respuesta": "Answer", "Antwort": "Answer", "Jawaban": "Answer",
    }
    for wrong, right in _schema_fixes.items():
        html = html.replace(f'"@type": "{wrong}"', f'"@type": "{right}"')
        html = html.replace(f'"@type":"{wrong}"', f'"@type":"{right}"')

    # ── POST-FIX: Translate FAQ JSON-LD questions ──
    # FAQ questions are inside <script> tags — word-map replacements using >text<
    # patterns don't reach them. Do targeted replacement on common FAQ patterns.
    _FAQ_Q_TRANSLATIONS = {
        "es": {"Is {n} safe": "¿Es {n} seguro", "What is {n}": "¿Qué es {n}", "trust score": "puntuación de confianza"},
        "fr": {"Is {n} safe": "{n} est-il sûr", "What is {n}": "Qu'est-ce que {n}", "trust score": "score de confiance"},
        "de": {"Is {n} safe": "Ist {n} sicher", "What is {n}": "Was ist {n}", "trust score": "Vertrauenswert"},
        "ja": {"Is {n} safe": "{n}は安全ですか", "What is {n}": "{n}とは", "trust score": "トラストスコア"},
        "ko": {"Is {n} safe": "{n}은(는) 안전한가요", "What is {n}": "{n}이란", "trust score": "신뢰 점수"},
        "zh": {"Is {n} safe": "{n}安全吗", "What is {n}": "什么是{n}", "trust score": "信任分数"},
        "ar": {"Is {n} safe": "هل {n} آمن", "What is {n}": "ما هو {n}", "trust score": "درجة الثقة"},
        "pt": {"Is {n} safe": "{n} é seguro", "What is {n}": "O que é {n}", "trust score": "pontuação de confiança"},
        "nl": {"Is {n} safe": "Is {n} veilig", "What is {n}": "Wat is {n}", "trust score": "vertrouwensscore"},
        "id": {"Is {n} safe": "Apakah {n} aman", "What is {n}": "Apa itu {n}", "trust score": "skor kepercayaan"},
        "cs": {"Is {n} safe": "Je {n} bezpečný", "What is {n}": "Co je {n}", "trust score": "skóre důvěry"},
        "th": {"Is {n} safe": "{n} ปลอดภัยหรือไม่", "What is {n}": "{n} คืออะไร", "trust score": "คะแนนความเชื่อถือ"},
        "ro": {"Is {n} safe": "Este {n} sigur", "What is {n}": "Ce este {n}", "trust score": "scor de încredere"},
        "tr": {"Is {n} safe": "{n} güvenli mi", "What is {n}": "{n} nedir", "trust score": "güven puanı"},
        "hi": {"Is {n} safe": "क्या {n} सुरक्षित है", "What is {n}": "{n} क्या है", "trust score": "विश्वास स्कोर"},
        "ru": {"Is {n} safe": "Безопасен ли {n}", "What is {n}": "Что такое {n}", "trust score": "оценка доверия"},
        "pl": {"Is {n} safe": "Czy {n} jest bezpieczny", "What is {n}": "Czym jest {n}", "trust score": "wynik zaufania"},
        "it": {"Is {n} safe": "{n} è sicuro", "What is {n}": "Cos'è {n}", "trust score": "punteggio di fiducia"},
        "da": {"Is {n} safe": "Er {n} sikker", "What is {n}": "Hvad er {n}", "trust score": "tillidsscore"},
    }
    _fqt = _FAQ_Q_TRANSLATIONS.get(lang)
    if _fqt:
        # Extract entity name from page (appears in <h1>)
        import re as _re_faq
        _h1_match = _re_faq.search(r'<h1[^>]*>([^<]+)</h1>', html)
        if _h1_match:
            # The h1 is already translated, extract the entity name from the English FAQ
            # Find entity name from the FAQ question pattern "Is X safe"
            _faq_name_match = _re_faq.search(r'"name":"Is ([^"]+) safe', html)
            if _faq_name_match:
                _ename = _faq_name_match.group(1)
                for _en_pat, _loc_pat in _fqt.items():
                    if "{n}" in _en_pat:
                        _en_full = _en_pat.replace("{n}", _ename)
                        _loc_full = _loc_pat.replace("{n}", _ename)
                        html = html.replace(f'"name":"{_en_full}', f'"name":"{_loc_full}')
                    else:
                        html = html.replace(_en_pat, _loc_pat)

    return html


def _render_localized_page_minimal(entity_slug, pattern, lang):
    """Minimal localized page fallback (old approach)."""
    ck_min = f"l10n_min:{lang}:{pattern}:{entity_slug}"

    t = TRANSLATIONS.get(lang, TRANSLATIONS.get("en", {}))
    a = _resolve(entity_slug)
    if not a:
        return None

    nm = a["name"].split("/")[-1] if "/" in a.get("name", "") else a.get("name", "")
    score = a.get("score") or 0
    grade = a.get("grade") or "D"
    desc = a.get("desc") or ""

    # Title
    title_key = f"title_{pattern.replace('-', '_').replace('a_scam', 'scam')}"
    title = t.get(title_key, t.get("title_safe", "Is {name} Safe? 2026 | Nerq")).format(name=_esc(nm), a=_esc(nm), b="")

    # Canonical
    pat_slug = URL_PATTERNS.get(lang, {}).get(f"is_{pattern.replace('-', '_')}", f"is-{entity_slug}-safe")
    canonical = f"{SITE}/{lang}/{pat_slug.format(slug=entity_slug)}"

    # Citable paragraph
    citable_key = f"citable_{pattern.replace('-', '_').replace('a_scam', 'scam')}"
    verdict_text = t.get("safe") if score >= 70 else t.get("use_caution") if score >= 40 else t.get("avoid")
    citable = t.get(citable_key, t.get("citable_safe", "")).format(
        name=_esc(nm), score=f"{score:.0f}", grade=grade, verdict=verdict_text,
        key_point=_esc(desc[:100]), entity=_esc(a.get("author", "")),
        conclusion=f"{t.get('last_updated', 'Updated')} {MY}",
        **{k: "" for k in ["privacy_score", "collection_level", "data_point", "red_flag_count",
                            "scam_verdict", "kids_verdict", "age_range", "key_concern", "rating",
                            "spyware_verdict", "perm_count", "tracker_count", "founded"]})

    # Alternatives
    alts = _find_alts(a.get("name", ""), a.get("cat"), 3)
    alts_html = ""
    for alt in alts:
        alts_html += f'<tr><td><a href="/{lang}/{URL_PATTERNS.get(lang, {}).get("is_safe", "is-{{slug}}-safe").format(slug=alt["name"].lower().replace(" ", "-"))}" style="color:#0d9488">{_esc(alt["name"])}</a></td><td>{alt["score"]:.0f}/100</td><td>{alt["grade"]}</td></tr>'

    # FAQ JSON-LD
    import json as _json_l10n
    _faq_q1 = t.get('faq_is_safe', 'Is {name} safe?').format(name=nm)
    _faq_a1 = f"{nm}: {score:.0f}/100 ({grade}). {verdict_text}."
    _faq_q2 = t.get('faq_alternatives', 'What are safer alternatives to {name}?').format(name=nm)
    _faq_a2 = ', '.join(f"{alt['name']} ({alt['score']:.0f})" for alt in alts[:3]) if alts else "More being analyzed."
    faq_ld = '<script type="application/ld+json">' + _json_l10n.dumps({
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": _faq_q1, "acceptedAnswer": {"@type": "Answer", "text": _faq_a1}},
            {"@type": "Question", "name": _faq_q2, "acceptedAnswer": {"@type": "Answer", "text": _faq_a2}},
        ]
    }) + '</script>'

    # Direction for Arabic
    dir_attr = ' dir="rtl"' if lang == "ar" else ""

    hreflang = _render_hreflang(entity_slug, f"is_{pattern.replace('-', '_')}")

    meta_desc = t.get("meta_safe", "").format(name=_esc(nm), score=f"{score:.0f}", grade=grade, verdict=verdict_text, date=MY)

    page = f"""<!DOCTYPE html><html lang="{lang}"{dir_attr}><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title[:60])}</title>
<meta name="description" content="{_esc(meta_desc[:160])}">
<link rel="canonical" href="{canonical}">
{hreflang}
<meta property="og:title" content="{_esc(title[:60])}">
<meta property="og:description" content="{_esc(meta_desc[:160])}">
<meta property="og:locale" content="{lang}">
<meta name="nerq:type" content="{pattern}"><meta name="nerq:entity" content="{_esc(nm)}">
<meta name="nerq:score" content="{score:.0f}"><meta name="nerq:updated" content="{TODAY}">
<meta name="citation_title" content="{_esc(title)}"><meta name="citation_author" content="Nerq">
<meta name="nerq:answer" content="{_esc(nm)} {score:.0f}/100 ({grade}). {_esc(verdict_text)}. {_esc(desc[:120])}">
<meta name="robots" content="max-snippet:-1">
{faq_ld}
{NERQ_CSS}
<style>.verdict-box{{border-radius:12px;padding:24px;margin:20px 0}}table{{width:100%;border-collapse:collapse;font-size:13px;margin:12px 0}}th{{text-align:left;padding:8px;border-bottom:2px solid #e5e7eb;color:#6b7280}}td{{padding:8px;border-bottom:1px solid #e5e7eb}}</style>
</head><body>
{NERQ_NAV}
<main class="container" style="max-width:900px;margin:0 auto;padding:24px">

<h1>{_esc(title.replace(' | Nerq', ''))}</h1>

{_render_verdict_box(a, pattern, t)}

<p style="font-size:15px;color:#374151;margin:8px 0 20px">{citable}</p>

{_render_dimensions(a, t, lang)}

{"<h2>" + t.get('safer_alternatives', 'Safer Alternatives') + "</h2><table><tr><th>" + t.get('alternative', 'Alternative') + "</th><th>" + t.get('score', 'Score') + "</th><th>" + t.get('grade', 'Grade') + "</th></tr>" + alts_html + "</table>" if alts_html else ""}

<h2>{t.get('about', 'About {name}').format(name=_esc(nm))}</h2>
<p style="font-size:14px;color:#374151">{_esc(desc[:500])}</p>

<h2>{t.get('faq', 'FAQ')}</h2>
<details style="margin:8px 0;border:1px solid #e5e7eb;padding:12px;border-radius:6px">
<summary style="cursor:pointer;font-weight:600">{t.get('faq_is_safe', 'Is {name} safe?').format(name=_esc(nm))}</summary>
<p style="margin-top:8px;color:#4b5563">{_esc(nm)}: {score:.0f}/100 ({grade}). {verdict_text}.</p>
</details>
<details style="margin:8px 0;border:1px solid #e5e7eb;padding:12px;border-radius:6px">
<summary style="cursor:pointer;font-weight:600">{t.get('faq_alternatives', 'What are safer alternatives to {name}?').format(name=_esc(nm))}</summary>
<p style="margin-top:8px;color:#4b5563">{', '.join(_esc(alt['name']) + ' (' + str(alt.get('score',0)) + ')' for alt in alts[:3]) if alts else t.get('unknown', 'Checking...')}</p>
</details>

<div style="display:flex;flex-wrap:wrap;gap:6px;margin:20px 0">
<a href="/is-{entity_slug}-safe" style="display:inline-block;padding:4px 12px;border:1px solid #e2e8f0;border-radius:99px;font-size:12px;color:#64748b;text-decoration:none">English</a>
<a href="/safe/{entity_slug}" style="display:inline-block;padding:4px 12px;border:1px solid #e2e8f0;border-radius:99px;font-size:12px;color:#64748b;text-decoration:none">{t.get('trust_score', 'Trust Score')}</a>
<a href="/alternatives/{entity_slug}" style="display:inline-block;padding:4px 12px;border:1px solid #e2e8f0;border-radius:99px;font-size:12px;color:#64748b;text-decoration:none">{t.get('safer_alternatives', 'Alternatives')}</a>
<a href="/review/{entity_slug}" style="display:inline-block;padding:4px 12px;border:1px solid #e2e8f0;border-radius:99px;font-size:12px;color:#64748b;text-decoration:none">Review</a>
</div>

<div style="margin-top:24px;font-size:12px;color:#6b7280">
{t.get('last_updated', 'Last updated')}: {MY} &middot; <a href="/is-{entity_slug}-safe" style="color:#0d9488">English version</a>
</div>
</main>{NERQ_FOOTER}</body></html>"""

    # Localize internal links via the i18n module (same fix as _render_localized_page).
    # Ensures fallback minimal-pages also get prefixed hrefs on non-English languages.
    from agentindex.i18n.html_rewrite import localize_internal_links as _localize_links
    page = _localize_links(page, lang)

    return _sc(ck_min, page)


def mount_localized_routes(app):
    """Mount localized routes for all 21 non-English languages."""

    # ── Localized static page routes (BEFORE catch-all) ──
    from agentindex.homepage_i18n import render_localized_homepage as _render_hp
    from agentindex.pages_i18n import render_about as _render_about, render_privacy as _render_privacy, render_terms as _render_terms, render_discover as _render_discover

    for _hl in SUPPORTED_LANGS:
        def _make_about(l=_hl):
            async def h():
                html = _render_about(l)
                return HTMLResponse(html)
            return h
        def _make_privacy(l=_hl):
            async def h():
                html = _render_privacy(l)
                return HTMLResponse(html)
            return h
        def _make_terms(l=_hl):
            async def h():
                html = _render_terms(l)
                return HTMLResponse(html)
            return h
        def _make_discover(l=_hl):
            async def h():
                html = _render_discover(l)
                return HTMLResponse(html)
            return h
        app.get(f"/{_hl}/about", response_class=HTMLResponse)(_make_about())
        app.get(f"/{_hl}/privacy", response_class=HTMLResponse)(_make_privacy())
        app.get(f"/{_hl}/terms", response_class=HTMLResponse)(_make_terms())
        app.get(f"/{_hl}/discover", response_class=HTMLResponse)(_make_discover())

    for _hl in SUPPORTED_LANGS:
        def _make_home_handler(l=_hl):
            async def home_handler():
                html = _render_hp(l)
                # All strings rendered via _ht() + render_nav(lang) + render_footer(lang)
                return HTMLResponse(html)
            return home_handler
        app.get(f"/{_hl}/", response_class=HTMLResponse)(_make_home_handler())
        app.get(f"/{_hl}", response_class=HTMLResponse)(_make_home_handler())

    # Reserved slugs that should NOT be treated as entities
    _RESERVED_SLUGS = {"blog", "docs", "guides",
                        "comply", "checker", "contact", "help"}

    # Single catch-all route per language
    for lang in SUPPORTED_LANGS:
        def _make_handler(l=lang):
            async def handler(pattern_slug: str):
                # 0. Reserved slugs — delegate to English version, NOT entity lookup
                if pattern_slug in _RESERVED_SLUGS:
                    from starlette.responses import RedirectResponse
                    return RedirectResponse(f"/{pattern_slug}", status_code=302)

                # 1. Try English URL patterns first (/{lang}/is-{slug}-safe etc.)
                english_patterns = [
                    (r"^is-([a-z0-9-]+)-safe$", "safe"),
                    (r"^is-([a-z0-9-]+)-legit$", "legit"),
                    (r"^is-([a-z0-9-]+)-a-scam$", "scam"),
                    (r"^is-([a-z0-9-]+)-safe-for-kids$", "kids"),
                    (r"^is-([a-z0-9-]+)-spyware$", "spyware"),
                    (r"^is-([a-z0-9-]+)-a-virus$", "virus"),
                    (r"^is-([a-z0-9-]+)-safe-to-download$", "download"),
                    (r"^is-([a-z0-9-]+)-safe-to-buy-from$", "buy"),
                    (r"^is-([a-z0-9-]+)-fake$", "fake"),
                    (r"^is-([a-z0-9-]+)-encrypted$", "encrypted"),
                    (r"^is-([a-z0-9-]+)-down$", "down"),
                    (r"^is-([a-z0-9-]+)-worth-it$", "worth"),
                    (r"^privacy/([a-z0-9-]+)$", "privacy"),
                    (r"^review/([a-z0-9-]+)$", "review"),
                    (r"^pros-cons/([a-z0-9-]+)$", "pros-cons"),
                    (r"^what-is/([a-z0-9-]+)$", "what-is"),
                    (r"^who-owns/([a-z0-9-]+)$", "who-owns"),
                    (r"^alternatives/([a-z0-9-]+)$", "alternatives"),
                    (r"^does-([a-z0-9-]+)-sell-your-data$", "sell-data"),
                    (r"^does-([a-z0-9-]+)-track-you$", "track"),
                    (r"^was-([a-z0-9-]+)-hacked$", "hacked"),
                    (r"^free-alternative-to-([a-z0-9-]+)$", "free-alt"),
                ]
                for regex, pattern in english_patterns:
                    m = re.match(regex, pattern_slug)
                    if m:
                        entity_slug = m.group(1)
                        html = _render_localized_page(entity_slug, pattern, l)
                        if html:
                            return HTMLResponse(html)

                # 2. Try localized URL patterns
                patterns = URL_PATTERNS.get(l, {})
                for pat_key, pat_template in patterns.items():
                    regex_pat = pat_template.replace("{slug}", r"([a-z0-9-]+)")
                    m = re.match(f"^{regex_pat}$", pattern_slug)
                    if m:
                        entity_slug = m.group(1)
                        pattern = pat_key.replace("is_", "").replace("_", "-")
                        html = _render_localized_page(entity_slug, pattern, l)
                        if html:
                            return HTMLResponse(html)

                # 2b. Handle /{lang}/categories — render categories hub, not entity page
                if pattern_slug == "categories":
                    try:
                        from agentindex.api.discovery import categories_page
                        resp = await categories_page()
                        html = resp.body.decode("utf-8")
                        html = html.replace('lang="en"', f'lang="{l}"')
                        html = re.sub(r'<link rel="canonical" href="https://nerq\.ai(/[^"]*)"',
                                      f'<link rel="canonical" href="https://nerq.ai/{l}\\1"', html, count=1)
                        _no_loc_cat = ('/is-', '/does-', '/was-', '/how-to-', '/how-does-', '/where-is-', '/should-i-', '/free-alternative-', '/private-alternative-', '/feed/', '/badge/', '/mcp/')
                        def _rw_cat(m2):
                            p = m2.group(1)
                            if p == '/' or p.startswith(f'/{l}/') or p.startswith('/v1/') or p.startswith('/static/'):
                                return m2.group(0)
                            if any(p.startswith(x) for x in _no_loc_cat):
                                return m2.group(0)
                            return f'href="/{l}{p}"'
                        html = re.sub(r'href="(/[^"]*)"', _rw_cat, html)
                        return HTMLResponse(html)
                    except Exception:
                        pass

                # 3. Handle /{lang}/{pattern}/{slug} — safe, alternatives, review, etc.
                _entity_patterns = {"safe", "alternatives", "review", "privacy",
                                    "pros-cons", "what-is", "who-owns", "guide"}
                m = re.match(r"^([a-z-]+)/([a-z0-9._-]+)$", pattern_slug)
                if m and m.group(1) in _entity_patterns:
                    html = _render_localized_page(m.group(2), "safe", l)
                    if html:
                        return HTMLResponse(html)

                # 4. Handle /{lang}/best/{category} — delegate to seo_programmatic
                # Lightweight localization: link rewriting + title/UI translation.
                # Does NOT use _translate_html (causes ReDoS on large table pages).
                m = re.match(r"^best/([a-z0-9-]+)$", pattern_slug)
                if m:
                    try:
                        from agentindex.seo_programmatic import _render_best_page
                        resp = await _render_best_page(m.group(1))
                        if resp.status_code == 200:
                            html = resp.body.decode("utf-8")
                            html = html.replace('lang="en"', f'lang="{l}"')
                            html = re.sub(
                                r'<link rel="canonical" href="https://nerq\.ai(/[^"]*)"',
                                f'<link rel="canonical" href="https://nerq.ai/{l}\\1"',
                                html, count=1)
                            _no_loc = ('/is-', '/does-', '/was-', '/how-to-', '/how-does-', '/where-is-', '/should-i-', '/free-alternative-', '/private-alternative-', '/feed/', '/badge/', '/mcp/')
                            def _rw(m2):
                                p = m2.group(1)
                                if p == '/' or p.startswith(f'/{l}/') or p.startswith('/v1/') or p.startswith('/static/'):
                                    return m2.group(0)
                                if any(p.startswith(x) for x in _no_loc):
                                    return m2.group(0)
                                return f'href="/{l}{p}"'
                            html = re.sub(r'href="(/[^"]*)"', _rw, html)
                            # Title + UI translation (safe string replacements, no regex on body)
                            _bt = _BEST_UI_STRINGS.get(l, {})
                            if _bt:
                                for _en, _loc in sorted(_bt.items(), key=lambda x: -len(x[0])):
                                    html = html.replace(f'>{_en}<', f'>{_loc}<')
                                    html = html.replace(f'>{_en} ', f'>{_loc} ')
                                    html = html.replace(f'"{_en}"', f'"{_loc}"')
                                    if len(_en) >= 12:
                                        html = html.replace(_en, _loc)
                            # Replace EN nav/footer with localized versions
                            from agentindex.nerq_design import render_nav, render_footer
                            _nav_start = html.find('<nav')
                            _nav_end = html.find('</script>', _nav_start) + len('</script>') if _nav_start >= 0 else -1
                            if _nav_start >= 0 and _nav_end > _nav_start:
                                html = html[:_nav_start] + render_nav(lang=l) + html[_nav_end:]
                            _foot_start = html.find('<div class="cross-links"')
                            if _foot_start >= 0:
                                html = html[:_foot_start] + render_footer(lang=l)
                            # ── Replace FAQ with fully localized templates ──
                            _bfaq = _BEST_FAQ_I18N.get(l)
                            if _bfaq:
                                # Extract category name from <h1>
                                _h1m = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
                                _cat_name = _h1m.group(1) if _h1m else m.group(1).replace("-", " ").title()
                                # Strip year suffix to avoid "2026 2026" duplication
                                _cat_name = re.sub(r'\s*\d{4}\s*$', '', _cat_name).strip()
                                # Find FAQ section: <h2>FAQ</h2><details>...(last)</details>
                                _faq_h2 = html.find('<h2>FAQ</h2>')
                                if _faq_h2 >= 0:
                                    _last_details_end = html.rfind('</details>', _faq_h2, html.find('<h2', _faq_h2 + 12) if html.find('<h2', _faq_h2 + 12) >= 0 else len(html))
                                    if _last_details_end >= 0:
                                        _last_details_end += len('</details>')
                                        _new_faq = f'<h2>{_bfaq[0]}</h2>'
                                        for _qi in range(1, len(_bfaq), 2):
                                            _q = _bfaq[_qi].replace("{category}", _cat_name).replace("{year}", str(2026))
                                            _a = _bfaq[_qi+1].replace("{category}", _cat_name) if _qi+1 < len(_bfaq) else ""
                                            _new_faq += f'<details style="margin:8px 0;border:1px solid #e5e7eb;padding:12px"><summary style="cursor:pointer;font-weight:600">{_q}</summary><p style="margin-top:8px;color:#4b5563">{_a}</p></details>'
                                        html = html[:_faq_h2] + _new_faq + html[_last_details_end:]
                                # Also fix FAQ in JSON-LD
                                import json as _jmod
                                _jfaq_start = html.find('"@type": "FAQPage"')
                                if _jfaq_start >= 0:
                                    _jblock_start = html.rfind('{', 0, _jfaq_start)
                                    _jblock_end = html.find('}]}', _jfaq_start)
                                    if _jblock_start >= 0 and _jblock_end >= 0:
                                        _jblock_end += 3
                                        _faq_ld_items = []
                                        for _qi in range(1, len(_bfaq), 2):
                                            _q = _bfaq[_qi].replace("{category}", _cat_name).replace("{year}", str(2026))
                                            _a = _bfaq[_qi+1].replace("{category}", _cat_name) if _qi+1 < len(_bfaq) else ""
                                            _faq_ld_items.append({"@type": "Question", "name": _q, "acceptedAnswer": {"@type": "Answer", "text": _a}})
                                        _new_jblock = _jmod.dumps({"@type": "FAQPage", "mainEntity": _faq_ld_items})
                                        html = html[:_jblock_start] + _new_jblock + html[_jblock_end:]
                            # Fast phrase replacement for FAQ/methodology/security stack
                            _ct = _CONTENT_TRANSLATIONS.get(l)
                            if _ct:
                                for _en, _loc in sorted(_ct.items(), key=lambda x: -len(x[0])):
                                    if not _en or not _loc: continue
                                    if len(_en) >= 8:
                                        html = html.replace(_en, _loc)
                            return HTMLResponse(html)
                        return resp
                    except Exception:
                        pass

                # 5. Handle /{lang}/{registry}/{slug} (old URL pattern from crawlers)
                _registries = {"npm", "pypi", "crates", "nuget", "go", "gems", "packagist",
                               "homebrew", "wordpress", "vscode", "chrome", "firefox",
                               "steam", "ios", "android", "vpn"}
                m = re.match(r"^([a-z]+)/([a-z0-9._-]+)$", pattern_slug)
                if m and m.group(1) in _registries:
                    html = _render_localized_page(m.group(2), "safe", l)
                    if html:
                        return HTMLResponse(html)

                # 6. Fallback: treat entire slug as entity with "safe" pattern
                html = _render_localized_page(pattern_slug, "safe", l)
                if html:
                    return HTMLResponse(html)

                # Return 410 Gone for known dead patterns to stop bots retrying
                return HTMLResponse(status_code=404, content="<h1>Not Found</h1><p>This page does not exist. <a href='/'>nerq.ai</a></p>", headers={"X-Robots-Tag": "noindex"})
            return handler

        app.get(f"/{lang}/{{pattern_slug:path}}", response_class=HTMLResponse)(_make_handler())

    # Sitemap for each language (2 URLs per entity: /safe/ + localized slug)
    _lang_sitemap_total = [0]  # mutable for closure
    _URLS_PER_ENTITY = 2  # /{lang}/safe/{slug} + /{lang}/{localized-slug}
    _LANG_CHUNK = 5000  # entities per chunk (× 2 = 10K URLs per file)

    @app.get("/sitemap-localized.xml", response_class=Response)
    async def sitemap_localized():
        """Sitemap index for all language sitemaps — 2 URLs per entity, 10K URLs per file."""
        if not _lang_sitemap_total[0]:
            session = get_session()
            try:
                # Only count entities from published registries (quality gate)
                _pub_regs = None
                try:
                    from agentindex.quality_gate import get_publishable_registries
                    _pub_regs = get_publishable_registries()
                except Exception:
                    pass
                _reg_filter = ""
                if _pub_regs:
                    _reg_list = ",".join(f"'{r}'" for r in _pub_regs)
                    _reg_filter = f"AND registry IN ({_reg_list})"
                _lang_sitemap_total[0] = session.execute(text(
                    f"SELECT COUNT(*) FROM software_registry "
                    f"WHERE trust_score IS NOT NULL AND trust_score > 0 "
                    f"AND description IS NOT NULL AND description != '' "
                    f"AND LENGTH(description) > 20 {_reg_filter}"
                )).scalar() or 0
            finally:
                session.close()
        total = _lang_sitemap_total[0]
        chunks = max(1, -(-total // _LANG_CHUNK))  # ceil division
        now = date.today().isoformat()
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        _SITEMAP_EXCLUDE = set()  # All languages now translated
        for lang in SUPPORTED_LANGS:
            if lang in _SITEMAP_EXCLUDE:
                continue
            for c in range(chunks):
                xml += f'  <sitemap><loc>{SITE}/sitemap-lang-{lang}-{c}.xml</loc><lastmod>{now}</lastmod></sitemap>\n'
        xml += '</sitemapindex>'
        return Response(xml, media_type="application/xml")

    @app.get("/sitemap-lang-{lang}-{chunk}.xml", response_class=Response)
    async def sitemap_lang_chunk(lang: str, chunk: int):
        """Per-language chunked sitemap. 2 URLs per entity (/{lang}/safe/ + localized slug), ~10K URLs per file."""
        if lang not in SUPPORTED_LANGS:
            return Response("Not found", status_code=404)
        offset = chunk * _LANG_CHUNK
        # Quality gate: only include published registries
        _pub_regs = None
        try:
            from agentindex.quality_gate import get_publishable_registries
            _pub_regs = get_publishable_registries()
        except Exception:
            pass
        _reg_filter = ""
        if _pub_regs:
            _reg_list = ",".join(f"'{r}'" for r in _pub_regs)
            _reg_filter = f"AND registry IN ({_reg_list})"
        session = get_session()
        try:
            rows = session.execute(text(f"""
                SELECT slug FROM software_registry
                WHERE trust_score IS NOT NULL AND trust_score > 0
                  AND description IS NOT NULL AND description != ''
                  AND LENGTH(description) > 20 {_reg_filter}
                ORDER BY is_king DESC NULLS LAST, trust_score DESC NULLS LAST
                OFFSET :off LIMIT :lim
            """), {"off": offset, "lim": _LANG_CHUNK}).fetchall()
        finally:
            session.close()
        if not rows:
            return Response('<?xml version="1.0"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>', media_type="application/xml")

        now = date.today().isoformat()
        pat = URL_PATTERNS.get(lang, {}).get("is_safe", "is-{slug}-safe")
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        for r in rows:
            slug = r[0]
            # URL 1: /{lang}/safe/{slug} (high priority — direct safety page)
            safe_url = f"{SITE}/{lang}/safe/{_esc(slug)}"
            en_safe = f"{SITE}/safe/{_esc(slug)}"
            xml += (f'<url><loc>{safe_url}</loc><lastmod>{now}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority>'
                    f'\n  <xhtml:link rel="alternate" hreflang="en" href="{en_safe}"/>'
                    f'\n  <xhtml:link rel="alternate" hreflang="{lang}" href="{safe_url}"/>'
                    f'</url>\n')
            # URL 2: /{lang}/{localized-slug} (localized pattern URL)
            loc_url = f"{SITE}/{lang}/{pat.format(slug=slug)}"
            en_url = f"{SITE}/is-{_esc(slug)}-safe"
            xml += (f'<url><loc>{_esc(loc_url)}</loc><lastmod>{now}</lastmod><changefreq>weekly</changefreq><priority>0.6</priority>'
                    f'\n  <xhtml:link rel="alternate" hreflang="en" href="{en_url}"/>'
                    f'\n  <xhtml:link rel="alternate" hreflang="{lang}" href="{_esc(loc_url)}"/>'
                    f'</url>\n')
        xml += '</urlset>'
        return Response(xml, media_type="application/xml")

    # Keep old route as redirect for backwards compatibility
    @app.get("/sitemap-lang-{lang}.xml", response_class=Response)
    async def sitemap_lang_redirect(lang: str):
        """Redirect old single-file URLs to chunk 0."""
        if lang not in SUPPORTED_LANGS:
            return Response("Not found", status_code=404)
        from starlette.responses import RedirectResponse
        return RedirectResponse(f"/sitemap-lang-{lang}-0.xml", status_code=301)

    logger.info(f"Mounted localized routes for {len(SUPPORTED_LANGS)} languages")
