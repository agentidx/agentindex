"""
Localized About, Privacy, and Terms pages for Nerq.
Each function generates full HTML for the given language.
"""
from agentindex.nerq_design import NERQ_NAV, NERQ_FOOTER, NERQ_CSS, render_hreflang

_SITE = "https://nerq.ai"

# ── Translations ──
_T = {
    "about_title": {
        "en": "About Nerq — Independent Trust Scores for Everything",
        "es": "Acerca de Nerq — Puntuaciones de confianza independientes",
        "de": "Über Nerq — Unabhängige Vertrauensbewertungen",
        "fr": "À propos de Nerq — Scores de confiance indépendants",
        "ja": "Nerqについて — 独立した信頼スコア",
        "pt": "Sobre o Nerq — Pontuações de confiança independentes",
        "id": "Tentang Nerq — Skor kepercayaan independen",
        "cs": "O Nerq — Nezávislé skóre důvěryhodnosti",
        "th": "เกี่ยวกับ Nerq — คะแนนความน่าเชื่อถือแบบอิสระ",
        "ro": "Despre Nerq — Scoruri de încredere independente",
        "tr": "Nerq Hakkında — Bağımsız güven puanları",
        "hi": "Nerq के बारे में — स्वतंत्र विश्वास स्कोर",
        "ru": "О Nerq — Независимые рейтинги доверия",
        "pl": "O Nerq — Niezależne wyniki zaufania",
        "it": "Informazioni su Nerq — Punteggi di fiducia indipendenti",
        "ko": "Nerq 소개 — 독립적인 신뢰 점수",
        "vi": "Về Nerq — Điểm tin cậy độc lập",
        "nl": "Over Nerq — Onafhankelijke vertrouwensscores",
        "sv": "Om Nerq — Oberoende förtroendepoäng",
        "zh": "关于 Nerq — 独立信任评分",
        "da": "Om Nerq — Uafhængige tillidsscorer",
    },
    "about_h1": {
        "en": "About Nerq", "es": "Acerca de Nerq", "de": "Über Nerq", "fr": "À propos de Nerq",
        "ja": "Nerqについて", "pt": "Sobre o Nerq", "id": "Tentang Nerq", "cs": "O Nerq",
        "th": "เกี่ยวกับ Nerq", "ro": "Despre Nerq", "tr": "Nerq Hakkında", "hi": "Nerq के बारे में",
        "ru": "О Nerq", "pl": "O Nerq", "it": "Informazioni su Nerq", "ko": "Nerq 소개",
        "vi": "Về Nerq", "nl": "Over Nerq", "sv": "Om Nerq", "zh": "关于 Nerq", "da": "Om Nerq",
    },
    "about_desc": {
        "en": "Nerq provides independent trust scores for 7.5M+ digital entities — software, apps, websites, travel destinations, food ingredients, supplements, and skincare products. We analyze data from 26 registries across 5 dimensions: security, maintenance, community, quality, and compliance. Free, no auth required, updated daily.",
        "es": "Nerq proporciona puntuaciones de confianza independientes para más de 7,5 millones de entidades digitales: software, aplicaciones, sitios web, destinos de viaje, ingredientes alimentarios, suplementos y productos para el cuidado de la piel. Analizamos datos de 26 registros en 5 dimensiones: seguridad, mantenimiento, comunidad, calidad y cumplimiento. Gratis, sin autenticación, actualizado diariamente.",
        "de": "Nerq bietet unabhängige Vertrauensbewertungen für über 7,5 Millionen digitale Entitäten — Software, Apps, Websites, Reiseziele, Lebensmittelzutaten, Nahrungsergänzungsmittel und Hautpflegeprodukte. Wir analysieren Daten aus 26 Registern in 5 Dimensionen: Sicherheit, Wartung, Community, Qualität und Compliance. Kostenlos, ohne Authentifizierung, täglich aktualisiert.",
        "fr": "Nerq fournit des scores de confiance indépendants pour plus de 7,5 millions d'entités numériques : logiciels, applications, sites web, destinations de voyage, ingrédients alimentaires, compléments et produits de soin. Nous analysons des données provenant de 26 registres selon 5 dimensions : sécurité, maintenance, communauté, qualité et conformité. Gratuit, sans authentification, mis à jour quotidiennement.",
        "ja": "Nerqは750万以上のデジタルエンティティ（ソフトウェア、アプリ、ウェブサイト、旅行先、食品成分、サプリメント、スキンケア製品）に対して独立した信頼スコアを提供します。26のレジストリから5つの次元（セキュリティ、メンテナンス、コミュニティ、品質、コンプライアンス）でデータを分析します。無料、認証不要、毎日更新。",
        "pt": "O Nerq fornece pontuações de confiança independentes para mais de 7,5 milhões de entidades digitais — software, aplicativos, sites, destinos de viagem, ingredientes alimentares, suplementos e produtos para a pele. Analisamos dados de 26 registros em 5 dimensões: segurança, manutenção, comunidade, qualidade e conformidade. Gratuito, sem autenticação, atualizado diariamente.",
        "sv": "Nerq tillhandahåller oberoende förtroendepoäng för över 7,5 miljoner digitala entiteter — programvara, appar, webbplatser, resmål, livsmedelsingredienser, kosttillskott och hudvårdsprodukter. Vi analyserar data från 26 register över 5 dimensioner: säkerhet, underhåll, community, kvalitet och regelefterlevnad. Gratis, ingen inloggning krävs, uppdateras dagligen.",
        "id": "Nerq menyediakan skor kepercayaan independen untuk 7,5 juta+ entitas digital — perangkat lunak, aplikasi, situs web, destinasi wisata, bahan makanan, suplemen, dan produk perawatan kulit. Kami menganalisis data dari 26 registry di 5 dimensi: keamanan, pemeliharaan, komunitas, kualitas, dan kepatuhan. Gratis, tanpa autentikasi, diperbarui setiap hari.",
        "cs": "Nerq poskytuje nezávislé skóre důvěryhodnosti pro více než 7,5 milionu digitálních entit — software, aplikace, webové stránky, cestovní destinace, potravinové přísady, doplňky stravy a kosmetické produkty. Analyzujeme data z 26 registrů v 5 dimenzích: bezpečnost, údržba, komunita, kvalita a shoda. Zdarma, bez autentizace, aktualizováno denně.",
        "th": "Nerq ให้คะแนนความน่าเชื่อถือแบบอิสระสำหรับ 7.5 ล้านเอนทิตีดิจิทัล — ซอฟต์แวร์ แอป เว็บไซต์ จุดหมายปลายทาง ส่วนผสมอาหาร อาหารเสริม และผลิตภัณฑ์ดูแลผิว เราวิเคราะห์ข้อมูลจาก 26 registry ใน 5 มิติ: ความปลอดภัย การบำรุงรักษา ชุมชน คุณภาพ และการปฏิบัติตามกฎระเบียบ ฟรี ไม่ต้องยืนยันตัวตน อัปเดตทุกวัน",
        "ro": "Nerq oferă scoruri de încredere independente pentru peste 7,5 milioane de entități digitale — software, aplicații, site-uri web, destinații de călătorie, ingrediente alimentare, suplimente și produse de îngrijire a pielii. Analizăm date din 26 de registre în 5 dimensiuni: securitate, mentenanță, comunitate, calitate și conformitate. Gratuit, fără autentificare, actualizat zilnic.",
        "tr": "Nerq, 7,5 milyondan fazla dijital varlık için bağımsız güven puanları sağlar — yazılım, uygulamalar, web siteleri, seyahat destinasyonları, gıda katkıları, takviyeler ve cilt bakım ürünleri. 26 kayıt defterinden 5 boyutta veri analiz ediyoruz: güvenlik, bakım, topluluk, kalite ve uyumluluk. Ücretsiz, kimlik doğrulama gerektirmez, günlük güncellenir.",
        "hi": "Nerq 7.5 मिलियन से अधिक डिजिटल इकाइयों के लिए स्वतंत्र विश्वास स्कोर प्रदान करता है — सॉफ्टवेयर, ऐप्स, वेबसाइट, यात्रा गंतव्य, खाद्य सामग्री, पूरक और त्वचा देखभाल उत्पाद। हम 26 रजिस्ट्री से 5 आयामों में डेटा का विश्लेषण करते हैं: सुरक्षा, रखरखाव, समुदाय, गुणवत्ता और अनुपालन। मुफ्त, प्रमाणीकरण की आवश्यकता नहीं, दैनिक अपडेट।",
        "ru": "Nerq предоставляет независимые рейтинги доверия для 7,5+ миллионов цифровых сущностей — программного обеспечения, приложений, веб-сайтов, туристических направлений, пищевых добавок, БАДов и средств по уходу за кожей. Мы анализируем данные из 26 реестров по 5 направлениям: безопасность, обслуживание, сообщество, качество и соответствие. Бесплатно, без регистрации, обновляется ежедневно.",
        "pl": "Nerq zapewnia niezależne wyniki zaufania dla ponad 7,5 miliona cyfrowych podmiotów — oprogramowania, aplikacji, stron internetowych, miejsc podróży, składników spożywczych, suplementów i produktów do pielęgnacji skóry. Analizujemy dane z 26 rejestrów w 5 wymiarach: bezpieczeństwo, konserwacja, społeczność, jakość i zgodność. Bezpłatne, bez uwierzytelniania, aktualizowane codziennie.",
        "it": "Nerq fornisce punteggi di fiducia indipendenti per oltre 7,5 milioni di entità digitali — software, app, siti web, destinazioni di viaggio, ingredienti alimentari, integratori e prodotti per la cura della pelle. Analizziamo dati da 26 registri in 5 dimensioni: sicurezza, manutenzione, comunità, qualità e conformità. Gratuito, senza autenticazione, aggiornato quotidianamente.",
        "ko": "Nerq는 750만 개 이상의 디지털 엔터티(소프트웨어, 앱, 웹사이트, 여행지, 식품 성분, 보충제, 스킨케어 제품)에 대한 독립적인 신뢰 점수를 제공합니다. 26개 레지스트리에서 5가지 차원(보안, 유지보수, 커뮤니티, 품질, 규정 준수)으로 데이터를 분석합니다. 무료, 인증 불필요, 매일 업데이트.",
        "vi": "Nerq cung cấp điểm tin cậy độc lập cho hơn 7,5 triệu thực thể số — phần mềm, ứng dụng, trang web, điểm đến du lịch, thành phần thực phẩm, thực phẩm bổ sung và sản phẩm chăm sóc da. Chúng tôi phân tích dữ liệu từ 26 registry trên 5 chiều: bảo mật, bảo trì, cộng đồng, chất lượng và tuân thủ. Miễn phí, không cần xác thực, cập nhật hàng ngày.",
        "nl": "Nerq biedt onafhankelijke vertrouwensscores voor meer dan 7,5 miljoen digitale entiteiten — software, apps, websites, reisbestemmingen, voedselingrediënten, supplementen en huidverzorgingsproducten. We analyseren gegevens uit 26 registers over 5 dimensies: beveiliging, onderhoud, gemeenschap, kwaliteit en naleving. Gratis, geen authenticatie vereist, dagelijks bijgewerkt.",
        "zh": "Nerq 为 750 万+ 数字实体提供独立信任评分——软件、应用、网站、旅行目的地、食品成分、营养补充剂和护肤产品。我们从 26 个注册表中分析 5 个维度的数据：安全性、维护、社区、质量和合规性。免费、无需认证、每日更新。",
        "da": "Nerq leverer uafhængige tillidsscorer for 7,5+ millioner digitale enheder — software, apps, hjemmesider, rejsedestinationer, fødevareingredienser, kosttilskud og hudplejeprodukter. Vi analyserer data fra 26 registre på tværs af 5 dimensioner: sikkerhed, vedligeholdelse, fællesskab, kvalitet og overholdelse. Gratis, ingen godkendelse påkrævet, opdateret dagligt.",
    },
    "what_we_do": {
        "en": "What We Do", "es": "Lo que hacemos", "de": "Was wir tun", "fr": "Ce que nous faisons",
        "ja": "Nerqの仕組み", "pt": "O que fazemos", "id": "Apa yang kami lakukan", "cs": "Co děláme",
        "th": "สิ่งที่เราทำ", "ro": "Ce facem", "tr": "Ne yapıyoruz", "hi": "हम क्या करते हैं",
        "ru": "Что мы делаем", "pl": "Co robimy", "it": "Cosa facciamo", "ko": "우리가 하는 일",
        "vi": "Chúng tôi làm gì", "nl": "Wat we doen", "sv": "Vad vi gör", "zh": "我们做什么", "da": "Hvad vi gør",
    },
    "key_numbers": {
        "en": "Key Numbers", "es": "Cifras clave", "de": "Wichtige Zahlen", "fr": "Chiffres clés",
        "ja": "主要数値", "pt": "Números-chave", "id": "Angka utama", "cs": "Klíčová čísla",
        "th": "ตัวเลขสำคัญ", "ro": "Cifre cheie", "tr": "Önemli rakamlar", "hi": "प्रमुख संख्याएं",
        "ru": "Ключевые цифры", "pl": "Kluczowe liczby", "it": "Numeri chiave", "ko": "핵심 수치",
        "vi": "Số liệu chính", "nl": "Belangrijke cijfers", "sv": "Nyckeltal", "zh": "关键数据", "da": "Nøgletal",
    },
    "links": {
        "en": "Links", "es": "Enlaces", "de": "Links", "fr": "Liens", "ja": "リンク", "pt": "Links",
        "id": "Tautan", "cs": "Odkazy", "th": "ลิงก์", "ro": "Linkuri", "tr": "Bağlantılar",
        "hi": "लिंक", "ru": "Ссылки", "pl": "Linki", "it": "Link", "ko": "링크", "vi": "Liên kết",
        "nl": "Links", "sv": "Länkar", "zh": "链接", "da": "Links",
    },
    "contact": {
        "en": "Contact", "es": "Contacto", "de": "Kontakt", "fr": "Contact", "ja": "連絡先",
        "pt": "Contato", "id": "Kontak", "cs": "Kontakt", "th": "ติดต่อ", "ro": "Contact",
        "tr": "İletişim", "hi": "संपर्क", "ru": "Контакт", "pl": "Kontakt", "it": "Contatti",
        "ko": "연락처", "vi": "Liên hệ", "nl": "Contact", "sv": "Kontakt", "zh": "联系方式", "da": "Kontakt",
    },
    "last_updated": {
        "en": "Last updated: March 2026", "es": "Última actualización: marzo 2026", "de": "Zuletzt aktualisiert: März 2026",
        "fr": "Dernière mise à jour : mars 2026", "ja": "最終更新：2026年3月", "pt": "Última atualização: março 2026",
        "id": "Terakhir diperbarui: Maret 2026", "cs": "Naposledy aktualizováno: březen 2026",
        "th": "อัปเดตล่าสุด: มีนาคม 2026", "ro": "Ultima actualizare: martie 2026",
        "tr": "Son güncelleme: Mart 2026", "hi": "अंतिम अपडेट: मार्च 2026",
        "ru": "Последнее обновление: март 2026", "pl": "Ostatnia aktualizacja: marzec 2026",
        "it": "Ultimo aggiornamento: marzo 2026", "ko": "최종 업데이트: 2026년 3월",
        "vi": "Cập nhật lần cuối: Tháng 3/2026", "nl": "Laatst bijgewerkt: maart 2026",
        "sv": "Senast uppdaterad: mars 2026", "zh": "最后更新：2026年3月", "da": "Sidst opdateret: marts 2026",
    },
    "effective": {
        "en": "Effective: March 2026", "es": "Vigente desde: marzo 2026", "de": "Gültig ab: März 2026",
        "fr": "En vigueur : mars 2026", "ja": "施行日：2026年3月", "pt": "Vigente desde: março 2026",
        "id": "Berlaku: Maret 2026", "cs": "Účinné od: březen 2026",
        "th": "มีผลบังคับใช้: มีนาคม 2026", "ro": "În vigoare din: martie 2026",
        "tr": "Yürürlük: Mart 2026", "hi": "प्रभावी: मार्च 2026",
        "ru": "Действует с: март 2026", "pl": "Obowiązuje od: marzec 2026",
        "it": "In vigore da: marzo 2026", "ko": "시행일: 2026년 3월",
        "vi": "Có hiệu lực: Tháng 3/2026", "nl": "Geldig vanaf: maart 2026",
        "sv": "Gäller från: mars 2026", "zh": "生效日期：2026年3月", "da": "Gældende fra: marts 2026",
    },
    "privacy_title": {
        "en": "Privacy Policy — Nerq", "es": "Política de privacidad — Nerq", "de": "Datenschutzrichtlinie — Nerq",
        "fr": "Politique de confidentialité — Nerq", "ja": "プライバシーポリシー — Nerq",
        "pt": "Política de privacidade — Nerq", "id": "Kebijakan Privasi — Nerq",
        "cs": "Zásady ochrany osobních údajů — Nerq", "th": "นโยบายความเป็นส่วนตัว — Nerq",
        "ro": "Politica de confidențialitate — Nerq", "tr": "Gizlilik Politikası — Nerq",
        "hi": "गोपनीयता नीति — Nerq", "ru": "Политика конфиденциальности — Nerq",
        "pl": "Polityka prywatności — Nerq", "it": "Informativa sulla privacy — Nerq",
        "ko": "개인정보 처리방침 — Nerq", "vi": "Chính sách quyền riêng tư — Nerq",
        "nl": "Privacybeleid — Nerq", "sv": "Integritetspolicy — Nerq",
        "zh": "隐私政策 — Nerq", "da": "Privatlivspolitik — Nerq",
    },
    "privacy_h1": {
        "en": "Nerq Privacy Policy", "es": "Política de privacidad de Nerq", "de": "Nerq Datenschutzrichtlinie",
        "fr": "Politique de confidentialité de Nerq", "ja": "Nerq プライバシーポリシー",
        "pt": "Política de privacidade do Nerq", "id": "Kebijakan Privasi Nerq",
        "cs": "Zásady ochrany osobních údajů Nerq", "th": "นโยบายความเป็นส่วนตัวของ Nerq",
        "ro": "Politica de confidențialitate Nerq", "tr": "Nerq Gizlilik Politikası",
        "hi": "Nerq गोपनीयता नीति", "ru": "Политика конфиденциальности Nerq",
        "pl": "Polityka prywatności Nerq", "it": "Informativa sulla privacy di Nerq",
        "ko": "Nerq 개인정보 처리방침", "vi": "Chính sách quyền riêng tư Nerq",
        "nl": "Nerq Privacybeleid", "sv": "Nerq Integritetspolicy",
        "zh": "Nerq 隐私政策", "da": "Nerq Privatlivspolitik",
    },
    "terms_title": {
        "en": "Terms of Service — Nerq", "es": "Términos de servicio — Nerq", "de": "Nutzungsbedingungen — Nerq",
        "fr": "Conditions d'utilisation — Nerq", "ja": "利用規約 — Nerq", "pt": "Termos de serviço — Nerq",
        "id": "Ketentuan Layanan — Nerq", "cs": "Podmínky služby — Nerq", "th": "ข้อกำหนดการใช้งาน — Nerq",
        "ro": "Termeni și condiții — Nerq", "tr": "Hizmet Şartları — Nerq", "hi": "सेवा की शर्तें — Nerq",
        "ru": "Условия использования — Nerq", "pl": "Regulamin — Nerq", "it": "Termini di servizio — Nerq",
        "ko": "서비스 약관 — Nerq", "vi": "Điều khoản dịch vụ — Nerq", "nl": "Gebruiksvoorwaarden — Nerq",
        "sv": "Användarvillkor — Nerq", "zh": "服务条款 — Nerq", "da": "Servicevilkår — Nerq",
    },
    "discover_title": {
        "en": "Discover — Nerq", "es": "Descubrir — Nerq", "de": "Entdecken — Nerq", "fr": "Découvrir — Nerq",
        "ja": "探索 — Nerq", "pt": "Descobrir — Nerq", "id": "Temukan — Nerq", "cs": "Objevit — Nerq",
        "th": "ค้นหา — Nerq", "ro": "Descoperă — Nerq", "tr": "Keşfet — Nerq", "hi": "खोजें — Nerq",
        "ru": "Обзор — Nerq", "pl": "Odkryj — Nerq", "it": "Scopri — Nerq", "ko": "탐색 — Nerq",
        "vi": "Khám phá — Nerq", "nl": "Ontdekken — Nerq", "sv": "Utforska — Nerq",
        "zh": "探索 — Nerq", "da": "Udforsk — Nerq",
    },
    "discover_h1": {
        "en": "Search", "es": "Buscar", "de": "Suchen", "fr": "Rechercher", "ja": "検索",
        "pt": "Pesquisar", "id": "Cari", "cs": "Hledat", "th": "ค้นหา", "ro": "Căutare",
        "tr": "Ara", "hi": "खोजें", "ru": "Поиск", "pl": "Szukaj", "it": "Cerca",
        "ko": "검색", "vi": "Tìm kiếm", "nl": "Zoeken", "sv": "Sök", "zh": "搜索", "da": "Søg",
    },
    "discover_placeholder": {
        "en": "Search agents, tools, models…", "es": "Buscar agentes, herramientas, modelos…",
        "de": "Agenten, Tools, Modelle suchen…", "fr": "Rechercher agents, outils, modèles…",
        "ja": "エージェント、ツール、モデルを検索…", "pt": "Pesquisar agentes, ferramentas, modelos…",
        "id": "Cari agen, alat, model…", "cs": "Hledat agenty, nástroje, modely…",
        "th": "ค้นหา agent เครื่องมือ โมเดล…", "ro": "Caută agenți, instrumente, modele…",
        "tr": "Ajan, araç, model ara…", "hi": "एजेंट, टूल, मॉडल खोजें…",
        "ru": "Поиск агентов, инструментов, моделей…", "pl": "Szukaj agentów, narzędzi, modeli…",
        "it": "Cerca agenti, strumenti, modelli…", "ko": "에이전트, 도구, 모델 검색…",
        "vi": "Tìm agent, công cụ, mô hình…", "nl": "Zoek agenten, tools, modellen…",
        "sv": "Sök agenter, verktyg, modeller…", "zh": "搜索 agent、工具、模型…", "da": "Søg agenter, værktøjer, modeller…",
    },
    "discover_categories": {
        "en": "Browse by category", "es": "Explorar por categoría", "de": "Nach Kategorie durchsuchen",
        "fr": "Parcourir par catégorie", "ja": "カテゴリで閲覧", "pt": "Navegar por categoria",
        "id": "Jelajahi berdasarkan kategori", "cs": "Procházet podle kategorie",
        "th": "เรียกดูตามหมวดหมู่", "ro": "Răsfoiți după categorie", "tr": "Kategoriye göre gözat",
        "hi": "श्रेणी के अनुसार ब्राउज़ करें", "ru": "Обзор по категориям", "pl": "Przeglądaj według kategorii",
        "it": "Sfoglia per categoria", "ko": "카테고리별 탐색", "vi": "Duyệt theo danh mục",
        "nl": "Bladeren op categorie", "sv": "Bläddra efter kategori", "zh": "按类别浏览", "da": "Gennemse efter kategori",
    },
}

# ── Privacy sections: 4 per language ──
_PRIVACY_SECTIONS = {
    "en": [
        ("What we collect", "Nerq does not collect personal data. The API returns trust scores based on entity names only. No other information is transmitted."),
        ("Cookies and tracking", "Nerq does not use cookies, tracking pixels, or analytics scripts. No login or account is required."),
        ("Third parties", "Your data is not shared with third parties."),
        ("Contact", "Questions? Visit <a href='https://nerq.ai'>nerq.ai</a>."),
    ],
    "es": [
        ("Qué recopilamos", "Nerq no recopila datos personales. La API devuelve puntuaciones de confianza basadas únicamente en nombres de entidades. No se transmite ninguna otra información."),
        ("Cookies y rastreo", "Nerq no utiliza cookies, píxeles de seguimiento ni scripts de análisis. No se requiere inicio de sesión ni cuenta."),
        ("Terceros", "Sus datos no se comparten con terceros."),
        ("Contacto", "¿Preguntas? Visita <a href='https://nerq.ai'>nerq.ai</a>."),
    ],
    "de": [
        ("Was wir sammeln", "Nerq sammelt keine persönlichen Daten. Die API gibt Vertrauensbewertungen nur basierend auf Entitätsnamen zurück. Es werden keine anderen Informationen übertragen."),
        ("Cookies und Tracking", "Nerq verwendet keine Cookies, Tracking-Pixel oder Analyseskripte. Kein Login oder Konto erforderlich."),
        ("Dritte", "Ihre Daten werden nicht an Dritte weitergegeben."),
        ("Kontakt", "Fragen? Besuche <a href='https://nerq.ai'>nerq.ai</a>."),
    ],
    "fr": [
        ("Ce que nous collectons", "Nerq ne collecte pas de données personnelles. L'API renvoie des scores de confiance basés uniquement sur les noms d'entités. Aucune autre information n'est transmise."),
        ("Cookies et suivi", "Nerq n'utilise pas de cookies, de pixels de suivi ni de scripts d'analyse. Aucune connexion ou compte requis."),
        ("Tiers", "Vos données ne sont pas partagées avec des tiers."),
        ("Contact", "Des questions ? Visitez <a href='https://nerq.ai'>nerq.ai</a>."),
    ],
    "ja": [
        ("収集する情報", "Nerqは個人データを収集しません。APIはエンティティ名のみに基づいて信頼スコアを返します。他の情報は送信されません。"),
        ("Cookieとトラッキング", "Nerqはクッキー、トラッキングピクセル、分析スクリプトを使用しません。ログインやアカウントは不要です。"),
        ("第三者", "あなたのデータは第三者と共有されません。"),
        ("連絡先", "ご質問は <a href='https://nerq.ai'>nerq.ai</a> をご覧ください。"),
    ],
    "pt": [
        ("O que coletamos", "O Nerq não coleta dados pessoais. A API retorna pontuações de confiança com base apenas em nomes de entidades. Nenhuma outra informação é transmitida."),
        ("Cookies e rastreamento", "O Nerq não usa cookies, pixels de rastreamento ou scripts de análise. Nenhum login ou conta é necessário."),
        ("Terceiros", "Seus dados não são compartilhados com terceiros."),
        ("Contato", "Dúvidas? Acesse <a href='https://nerq.ai'>nerq.ai</a>."),
    ],
    "id": [
        ("Apa yang kami kumpulkan", "Nerq tidak mengumpulkan data pribadi. API mengembalikan skor kepercayaan berdasarkan nama entitas saja. Tidak ada informasi lain yang dikirimkan."),
        ("Cookie dan pelacakan", "Nerq tidak menggunakan cookie, piksel pelacakan, atau skrip analitik. Tidak perlu login atau akun."),
        ("Pihak ketiga", "Data Anda tidak dibagikan kepada pihak ketiga."),
        ("Kontak", "Pertanyaan? Kunjungi <a href='https://nerq.ai'>nerq.ai</a>."),
    ],
    "cs": [
        ("Co sbíráme", "Nerq neshromažďuje osobní údaje. API vrací skóre důvěryhodnosti pouze na základě názvů entit. Žádné jiné informace nejsou přenášeny."),
        ("Cookies a sledování", "Nerq nepoužívá cookies, sledovací pixely ani analytické skripty. Není vyžadováno přihlášení ani účet."),
        ("Třetí strany", "Vaše data nejsou sdílena s třetími stranami."),
        ("Kontakt", "Otázky? Navštivte <a href='https://nerq.ai'>nerq.ai</a>."),
    ],
    "th": [
        ("สิ่งที่เราเก็บรวบรวม", "Nerq ไม่เก็บรวบรวมข้อมูลส่วนบุคคล API ส่งคืนคะแนนความน่าเชื่อถือตามชื่อเอนทิตีเท่านั้น ไม่มีข้อมูลอื่นถูกส่ง"),
        ("คุกกี้และการติดตาม", "Nerq ไม่ใช้คุกกี้ พิกเซลติดตาม หรือสคริปต์วิเคราะห์ ไม่ต้องเข้าสู่ระบบหรือสร้างบัญชี"),
        ("บุคคลที่สาม", "ข้อมูลของคุณจะไม่ถูกแชร์กับบุคคลที่สาม"),
        ("ติดต่อ", "มีคำถาม? เยี่ยมชม <a href='https://nerq.ai'>nerq.ai</a>"),
    ],
    "ro": [
        ("Ce colectăm", "Nerq nu colectează date personale. API-ul returnează scoruri de încredere bazate doar pe numele entităților. Nu sunt transmise alte informații."),
        ("Cookie-uri și urmărire", "Nerq nu folosește cookie-uri, pixeli de urmărire sau scripturi de analiză. Nu este necesară autentificarea sau un cont."),
        ("Terți", "Datele dvs. nu sunt partajate cu terți."),
        ("Contact", "Întrebări? Vizitați <a href='https://nerq.ai'>nerq.ai</a>."),
    ],
    "tr": [
        ("Ne topluyoruz", "Nerq kişisel veri toplamaz. API yalnızca varlık adlarına dayalı güven puanları döndürür. Başka hiçbir bilgi iletilmez."),
        ("Çerezler ve izleme", "Nerq çerez, izleme pikseli veya analiz betiği kullanmaz. Giriş veya hesap gerekmez."),
        ("Üçüncü taraflar", "Verileriniz üçüncü taraflarla paylaşılmaz."),
        ("İletişim", "Sorularınız mı var? <a href='https://nerq.ai'>nerq.ai</a> adresini ziyaret edin."),
    ],
    "hi": [
        ("हम क्या एकत्र करते हैं", "Nerq व्यक्तिगत डेटा एकत्र नहीं करता। API केवल इकाई नामों के आधार पर विश्वास स्कोर लौटाता है। कोई अन्य जानकारी प्रसारित नहीं की जाती।"),
        ("कुकीज़ और ट्रैकिंग", "Nerq कुकीज़, ट्रैकिंग पिक्सेल या एनालिटिक्स स्क्रिप्ट का उपयोग नहीं करता। लॉगिन या खाते की आवश्यकता नहीं।"),
        ("तृतीय पक्ष", "आपका डेटा तृतीय पक्षों के साथ साझा नहीं किया जाता।"),
        ("संपर्क", "प्रश्न? <a href='https://nerq.ai'>nerq.ai</a> पर जाएं।"),
    ],
    "ru": [
        ("Что мы собираем", "Nerq не собирает личные данные. API возвращает рейтинги доверия только на основе названий сущностей. Никакая другая информация не передаётся."),
        ("Файлы cookie и отслеживание", "Nerq не использует файлы cookie, пиксели отслеживания или аналитические скрипты. Вход или учётная запись не требуются."),
        ("Третьи стороны", "Ваши данные не передаются третьим сторонам."),
        ("Контакт", "Вопросы? Посетите <a href='https://nerq.ai'>nerq.ai</a>."),
    ],
    "pl": [
        ("Co zbieramy", "Nerq nie zbiera danych osobowych. API zwraca wyniki zaufania wyłącznie na podstawie nazw podmiotów. Żadne inne informacje nie są przesyłane."),
        ("Pliki cookie i śledzenie", "Nerq nie używa plików cookie, pikseli śledzących ani skryptów analitycznych. Nie wymagamy logowania ani konta."),
        ("Strony trzecie", "Twoje dane nie są udostępniane stronom trzecim."),
        ("Kontakt", "Pytania? Odwiedź <a href='https://nerq.ai'>nerq.ai</a>."),
    ],
    "it": [
        ("Cosa raccogliamo", "Nerq non raccoglie dati personali. L'API restituisce punteggi di fiducia basati solo sui nomi delle entità. Nessun'altra informazione viene trasmessa."),
        ("Cookie e tracciamento", "Nerq non utilizza cookie, pixel di tracciamento o script di analisi. Nessun login o account richiesto."),
        ("Terze parti", "I tuoi dati non sono condivisi con terze parti."),
        ("Contatti", "Domande? Visita <a href='https://nerq.ai'>nerq.ai</a>."),
    ],
    "ko": [
        ("수집하는 정보", "Nerq는 개인 데이터를 수집하지 않습니다. API는 엔터티 이름만을 기반으로 신뢰 점수를 반환합니다. 다른 정보는 전송되지 않습니다."),
        ("쿠키 및 추적", "Nerq는 쿠키, 추적 픽셀 또는 분석 스크립트를 사용하지 않습니다. 로그인이나 계정이 필요하지 않습니다."),
        ("제3자", "귀하의 데이터는 제3자와 공유되지 않습니다."),
        ("연락처", "질문이 있으신가요? <a href='https://nerq.ai'>nerq.ai</a>를 방문하세요."),
    ],
    "vi": [
        ("Chúng tôi thu thập gì", "Nerq không thu thập dữ liệu cá nhân. API chỉ trả về điểm tin cậy dựa trên tên thực thể. Không có thông tin nào khác được truyền đi."),
        ("Cookie và theo dõi", "Nerq không sử dụng cookie, pixel theo dõi hoặc script phân tích. Không cần đăng nhập hoặc tài khoản."),
        ("Bên thứ ba", "Dữ liệu của bạn không được chia sẻ với bên thứ ba."),
        ("Liên hệ", "Câu hỏi? Truy cập <a href='https://nerq.ai'>nerq.ai</a>."),
    ],
    "nl": [
        ("Wat we verzamelen", "Nerq verzamelt geen persoonlijke gegevens. De API retourneert vertrouwensscores uitsluitend op basis van entiteitsnamen. Er wordt geen andere informatie verzonden."),
        ("Cookies en tracking", "Nerq gebruikt geen cookies, tracking pixels of analytics scripts. Geen login of account vereist."),
        ("Derden", "Uw gegevens worden niet gedeeld met derden."),
        ("Contact", "Vragen? Bezoek <a href='https://nerq.ai'>nerq.ai</a>."),
    ],
    "sv": [
        ("Vad vi samlar in", "Nerq samlar inte in personuppgifter. API:et returnerar förtroendepoäng baserat enbart på entitetsnamn. Ingen annan information överförs."),
        ("Cookies och spårning", "Nerq använder inga cookies, spårningspixlar eller analysskript. Ingen inloggning eller konto krävs."),
        ("Tredje parter", "Dina uppgifter delas inte med tredje part."),
        ("Kontakt", "Frågor? Besök <a href='https://nerq.ai'>nerq.ai</a>."),
    ],
    "zh": [
        ("我们收集什么", "Nerq 不收集个人数据。API 仅根据实体名称返回信任评分。不传输其他任何信息。"),
        ("Cookie 和跟踪", "Nerq 不使用 cookie、跟踪像素或分析脚本。无需登录或账户。"),
        ("第三方", "您的数据不会与第三方共享。"),
        ("联系方式", "有问题？请访问 <a href='https://nerq.ai'>nerq.ai</a>。"),
    ],
    "da": [
        ("Hvad vi indsamler", "Nerq indsamler ikke personlige data. API'et returnerer tillidsscorer udelukkende baseret på enhedsnavne. Ingen anden information transmitteres."),
        ("Cookies og sporing", "Nerq bruger ikke cookies, sporingspixels eller analysescripts. Ingen login eller konto påkrævet."),
        ("Tredjeparter", "Dine data deles ikke med tredjeparter."),
        ("Kontakt", "Spørgsmål? Besøg <a href='https://nerq.ai'>nerq.ai</a>."),
    ],
}

# ── Terms sections: 15 per language ──
_TERMS_SECTIONS = {
    "en": [
        ("1. Acceptance of Terms", "By using Nerq, you agree to these Terms. If you disagree, do not use the Service."),
        ("2. Description of Service", "Nerq provides trust scoring and safety assessments for digital entities."),
        ("3. Informational Purposes Only", "Trust assessments are for informational purposes only and do not constitute legal or professional advice. You are responsible for your own compliance decisions."),
        ("4. Your Responsibilities", "You are responsible for the accuracy of information you provide and your own decisions."),
        ("5. Intellectual Property", "Nerq retains all rights in the Service. You retain ownership of data you submit."),
        ("6. Acceptable Use", "Do not use the Service for unlawful purposes or misrepresent trust scores as official certifications."),
        ("7. Warranty Disclaimer", "THE SERVICE IS PROVIDED 'AS IS' WITHOUT WARRANTIES. Nerq does not guarantee accuracy of assessments."),
        ("8. Limitation of Liability", "Nerq is not liable for indirect or consequential damages. Maximum liability: €100."),
        ("9. Indemnification", "You agree to indemnify Nerq from claims arising from your use of the Service."),
        ("10. Compliance Badges", "Badges reflect automated assessments at a point in time and do not constitute certification."),
        ("11. AI Transparency", "Assessments use AI and may contain errors. Outputs are probabilistic."),
        ("12. Modifications", "Nerq may modify these Terms. Continued use constitutes acceptance."),
        ("13. Termination", "Nerq may suspend access at any time. You may stop using the Service at any time."),
        ("14. Governing Law", "These Terms are governed by Swedish law. Disputes resolved by Stockholm courts."),
        ("15. Contact", "Questions: <a href='mailto:hello@nerq.ai'>hello@nerq.ai</a>"),
    ],
    "es": [
        ("1. Aceptación de los términos", "Al usar Nerq, aceptas estos Términos. Si no estás de acuerdo, no uses el Servicio."),
        ("2. Descripción del servicio", "Nerq proporciona puntuaciones de confianza y evaluaciones de seguridad para entidades digitales."),
        ("3. Solo fines informativos", "Las evaluaciones de confianza son solo para fines informativos y no constituyen asesoramiento legal o profesional. Eres responsable de tus propias decisiones de cumplimiento."),
        ("4. Tus responsabilidades", "Eres responsable de la exactitud de la información que proporcionas y de tus propias decisiones."),
        ("5. Propiedad intelectual", "Nerq conserva todos los derechos sobre el Servicio. Conservas la propiedad de los datos que envíes."),
        ("6. Uso aceptable", "No uses el Servicio para fines ilegales ni presentes las puntuaciones de confianza como certificaciones oficiales."),
        ("7. Descargo de garantías", "EL SERVICIO SE PROPORCIONA 'TAL CUAL' SIN GARANTÍAS. Nerq no garantiza la exactitud de las evaluaciones."),
        ("8. Limitación de responsabilidad", "Nerq no es responsable de daños indirectos o consecuentes. Responsabilidad máxima: 100 €."),
        ("9. Indemnización", "Aceptas indemnizar a Nerq por reclamaciones derivadas de tu uso del Servicio."),
        ("10. Insignias de cumplimiento", "Las insignias reflejan evaluaciones automatizadas en un momento dado y no constituyen certificación."),
        ("11. Transparencia de IA", "Las evaluaciones usan IA y pueden contener errores. Los resultados son probabilísticos."),
        ("12. Modificaciones", "Nerq puede modificar estos Términos. El uso continuado constituye aceptación."),
        ("13. Terminación", "Nerq puede suspender el acceso en cualquier momento. Puedes dejar de usar el Servicio en cualquier momento."),
        ("14. Ley aplicable", "Estos Términos se rigen por la legislación sueca. Las disputas se resuelven en los tribunales de Estocolmo."),
        ("15. Contacto", "Preguntas: <a href='mailto:hello@nerq.ai'>hello@nerq.ai</a>"),
    ],
    "de": [
        ("1. Annahme der Bedingungen", "Durch die Nutzung von Nerq stimmen Sie diesen Bedingungen zu. Wenn Sie nicht einverstanden sind, nutzen Sie den Dienst nicht."),
        ("2. Beschreibung des Dienstes", "Nerq bietet Vertrauensbewertungen und Sicherheitsbeurteilungen für digitale Entitäten."),
        ("3. Nur zu Informationszwecken", "Vertrauensbewertungen dienen nur zu Informationszwecken und stellen keine Rechts- oder Fachberatung dar. Sie sind für Ihre eigenen Compliance-Entscheidungen verantwortlich."),
        ("4. Ihre Verantwortlichkeiten", "Sie sind für die Richtigkeit der von Ihnen bereitgestellten Informationen und Ihre eigenen Entscheidungen verantwortlich."),
        ("5. Geistiges Eigentum", "Nerq behält alle Rechte am Dienst. Sie behalten das Eigentum an den von Ihnen übermittelten Daten."),
        ("6. Zulässige Nutzung", "Nutzen Sie den Dienst nicht für rechtswidrige Zwecke oder stellen Sie Vertrauensbewertungen nicht als offizielle Zertifizierungen dar."),
        ("7. Gewährleistungsausschluss", "DER DIENST WIRD 'WIE BESEHEN' OHNE GARANTIEN BEREITGESTELLT. Nerq übernimmt keine Garantie für die Genauigkeit der Bewertungen."),
        ("8. Haftungsbeschränkung", "Nerq haftet nicht für indirekte oder Folgeschäden. Maximale Haftung: 100 €."),
        ("9. Freistellung", "Sie erklären sich damit einverstanden, Nerq von Ansprüchen freizustellen, die aus Ihrer Nutzung des Dienstes entstehen."),
        ("10. Compliance-Abzeichen", "Abzeichen spiegeln automatisierte Bewertungen zu einem bestimmten Zeitpunkt wider und stellen keine Zertifizierung dar."),
        ("11. KI-Transparenz", "Bewertungen nutzen KI und können Fehler enthalten. Ergebnisse sind probabilistisch."),
        ("12. Änderungen", "Nerq kann diese Bedingungen ändern. Die weitere Nutzung gilt als Annahme."),
        ("13. Kündigung", "Nerq kann den Zugang jederzeit sperren. Sie können den Dienst jederzeit nicht mehr nutzen."),
        ("14. Anwendbares Recht", "Diese Bedingungen unterliegen schwedischem Recht. Streitigkeiten werden von Stockholmer Gerichten gelöst."),
        ("15. Kontakt", "Fragen: <a href='mailto:hello@nerq.ai'>hello@nerq.ai</a>"),
    ],
    "fr": [
        ("1. Acceptation des conditions", "En utilisant Nerq, vous acceptez ces Conditions. Si vous n'êtes pas d'accord, n'utilisez pas le Service."),
        ("2. Description du service", "Nerq fournit des scores de confiance et des évaluations de sécurité pour les entités numériques."),
        ("3. À titre informatif uniquement", "Les évaluations de confiance sont à titre informatif uniquement et ne constituent pas un avis juridique ou professionnel. Vous êtes responsable de vos propres décisions de conformité."),
        ("4. Vos responsabilités", "Vous êtes responsable de l'exactitude des informations que vous fournissez et de vos propres décisions."),
        ("5. Propriété intellectuelle", "Nerq conserve tous les droits sur le Service. Vous conservez la propriété des données que vous soumettez."),
        ("6. Utilisation acceptable", "N'utilisez pas le Service à des fins illégales et ne présentez pas les scores de confiance comme des certifications officielles."),
        ("7. Exclusion de garantie", "LE SERVICE EST FOURNI 'TEL QUEL' SANS GARANTIES. Nerq ne garantit pas l'exactitude des évaluations."),
        ("8. Limitation de responsabilité", "Nerq n'est pas responsable des dommages indirects ou consécutifs. Responsabilité maximale : 100 €."),
        ("9. Indemnisation", "Vous acceptez d'indemniser Nerq contre les réclamations découlant de votre utilisation du Service."),
        ("10. Badges de conformité", "Les badges reflètent des évaluations automatisées à un moment donné et ne constituent pas une certification."),
        ("11. Transparence IA", "Les évaluations utilisent l'IA et peuvent contenir des erreurs. Les résultats sont probabilistes."),
        ("12. Modifications", "Nerq peut modifier ces Conditions. L'utilisation continue vaut acceptation."),
        ("13. Résiliation", "Nerq peut suspendre l'accès à tout moment. Vous pouvez cesser d'utiliser le Service à tout moment."),
        ("14. Droit applicable", "Ces Conditions sont régies par le droit suédois. Les litiges sont résolus par les tribunaux de Stockholm."),
        ("15. Contact", "Questions : <a href='mailto:hello@nerq.ai'>hello@nerq.ai</a>"),
    ],
    "ja": [
        ("1. 利用規約の同意", "Nerqを使用することで、これらの規約に同意したものとみなします。同意しない場合は、サービスを使用しないでください。"),
        ("2. サービスの説明", "Nerqはデジタルエンティティの信頼スコアリングと安全性評価を提供します。"),
        ("3. 情報提供のみ", "信頼評価は情報提供のみを目的としており、法的または専門的なアドバイスを構成するものではありません。コンプライアンスに関する決定はお客様自身の責任で行ってください。"),
        ("4. お客様の責任", "提供する情報の正確性および自身の決定についての責任はお客様にあります。"),
        ("5. 知的財産", "Nerqはサービスに関するすべての権利を保持します。お客様が提出したデータの所有権はお客様が保持します。"),
        ("6. 許容される使用", "違法な目的でサービスを使用したり、信頼スコアを公式認証として誤って表示したりしないでください。"),
        ("7. 保証の否認", "サービスは「現状のまま」保証なしで提供されます。Nerqは評価の正確性を保証しません。"),
        ("8. 責任の制限", "Nerqは間接的または結果的損害について責任を負いません。最大責任額：€100。"),
        ("9. 補償", "サービスの使用から生じる請求からNerqを補償することに同意します。"),
        ("10. コンプライアンスバッジ", "バッジはある時点での自動評価を反映しており、認証を構成するものではありません。"),
        ("11. AIの透明性", "評価にはAIを使用しており、エラーが含まれる場合があります。出力は確率的なものです。"),
        ("12. 変更", "Nerqはこれらの規約を変更する場合があります。継続的な使用は承諾とみなされます。"),
        ("13. 終了", "Nerqはいつでもアクセスを停止することができます。お客様もいつでもサービスの使用を停止できます。"),
        ("14. 準拠法", "本規約はスウェーデン法に準拠します。紛争はストックホルムの裁判所で解決されます。"),
        ("15. 連絡先", "ご質問: <a href='mailto:hello@nerq.ai'>hello@nerq.ai</a>"),
    ],
    "pt": [
        ("1. Aceitação dos termos", "Ao usar o Nerq, você concorda com estes Termos. Se não concordar, não use o Serviço."),
        ("2. Descrição do serviço", "O Nerq fornece pontuações de confiança e avaliações de segurança para entidades digitais."),
        ("3. Apenas para fins informativos", "As avaliações de confiança são apenas para fins informativos e não constituem aconselhamento jurídico ou profissional. Você é responsável pelas suas próprias decisões de conformidade."),
        ("4. Suas responsabilidades", "Você é responsável pela precisão das informações que fornece e pelas suas próprias decisões."),
        ("5. Propriedade intelectual", "O Nerq retém todos os direitos sobre o Serviço. Você retém a propriedade dos dados que enviar."),
        ("6. Uso aceitável", "Não use o Serviço para fins ilegais nem represente incorretamente as pontuações de confiança como certificações oficiais."),
        ("7. Isenção de garantia", "O SERVIÇO É FORNECIDO 'NO ESTADO EM QUE SE ENCONTRA' SEM GARANTIAS. O Nerq não garante a precisão das avaliações."),
        ("8. Limitação de responsabilidade", "O Nerq não é responsável por danos indiretos ou consequentes. Responsabilidade máxima: €100."),
        ("9. Indenização", "Você concorda em indenizar o Nerq de reclamações decorrentes do seu uso do Serviço."),
        ("10. Selos de conformidade", "Os selos refletem avaliações automatizadas em um ponto no tempo e não constituem certificação."),
        ("11. Transparência de IA", "As avaliações usam IA e podem conter erros. Os resultados são probabilísticos."),
        ("12. Modificações", "O Nerq pode modificar estes Termos. O uso continuado constitui aceitação."),
        ("13. Rescisão", "O Nerq pode suspender o acesso a qualquer momento. Você pode parar de usar o Serviço a qualquer momento."),
        ("14. Lei aplicável", "Estes Termos são regidos pela lei sueca. As disputas são resolvidas pelos tribunais de Estocolmo."),
        ("15. Contato", "Dúvidas: <a href='mailto:hello@nerq.ai'>hello@nerq.ai</a>"),
    ],
    "id": [
        ("1. Penerimaan Ketentuan", "Dengan menggunakan Nerq, Anda menyetujui Ketentuan ini. Jika tidak setuju, jangan gunakan Layanan."),
        ("2. Deskripsi Layanan", "Nerq menyediakan penilaian kepercayaan dan evaluasi keamanan untuk entitas digital."),
        ("3. Hanya untuk Tujuan Informasi", "Penilaian kepercayaan hanya untuk tujuan informasi dan bukan merupakan saran hukum atau profesional. Anda bertanggung jawab atas keputusan kepatuhan Anda sendiri."),
        ("4. Tanggung Jawab Anda", "Anda bertanggung jawab atas keakuratan informasi yang Anda berikan dan keputusan Anda sendiri."),
        ("5. Kekayaan Intelektual", "Nerq mempertahankan semua hak atas Layanan. Anda mempertahankan kepemilikan data yang Anda kirimkan."),
        ("6. Penggunaan yang Dapat Diterima", "Jangan gunakan Layanan untuk tujuan melanggar hukum atau salah menggambarkan skor kepercayaan sebagai sertifikasi resmi."),
        ("7. Penafian Garansi", "LAYANAN DISEDIAKAN 'APA ADANYA' TANPA GARANSI. Nerq tidak menjamin keakuratan penilaian."),
        ("8. Batasan Tanggung Jawab", "Nerq tidak bertanggung jawab atas kerusakan tidak langsung atau konsekuensial. Tanggung jawab maksimum: €100."),
        ("9. Ganti Rugi", "Anda setuju untuk mengganti rugi Nerq dari klaim yang timbul dari penggunaan Layanan Anda."),
        ("10. Lencana Kepatuhan", "Lencana mencerminkan penilaian otomatis pada suatu titik waktu dan bukan merupakan sertifikasi."),
        ("11. Transparansi AI", "Penilaian menggunakan AI dan mungkin mengandung kesalahan. Output bersifat probabilistik."),
        ("12. Modifikasi", "Nerq dapat memodifikasi Ketentuan ini. Penggunaan berkelanjutan merupakan penerimaan."),
        ("13. Penghentian", "Nerq dapat menangguhkan akses kapan saja. Anda dapat berhenti menggunakan Layanan kapan saja."),
        ("14. Hukum yang Berlaku", "Ketentuan ini diatur oleh hukum Swedia. Sengketa diselesaikan oleh pengadilan Stockholm."),
        ("15. Kontak", "Pertanyaan: <a href='mailto:hello@nerq.ai'>hello@nerq.ai</a>"),
    ],
    "cs": [
        ("1. Přijetí podmínek", "Používáním Nerq souhlasíte s těmito Podmínkami. Pokud nesouhlasíte, Službu nepoužívejte."),
        ("2. Popis služby", "Nerq poskytuje hodnocení důvěryhodnosti a bezpečnostní posouzení digitálních entit."),
        ("3. Pouze pro informační účely", "Hodnocení důvěryhodnosti jsou pouze pro informační účely a nepředstavují právní ani odborné poradenství. Jste odpovědní za vlastní rozhodnutí o dodržování předpisů."),
        ("4. Vaše odpovědnosti", "Jste odpovědní za přesnost vámi poskytnutých informací a za vlastní rozhodnutí."),
        ("5. Duševní vlastnictví", "Nerq si ponechává veškerá práva ke Službě. Zachováváte vlastnictví dat, která odesíláte."),
        ("6. Přijatelné použití", "Nepoužívejte Službu k nezákonným účelům ani neprezentujte skóre důvěryhodnosti jako oficiální certifikace."),
        ("7. Odmítnutí záruky", "SLUŽBA JE POSKYTOVÁNA 'JAK JE' BEZ ZÁRUK. Nerq nezaručuje přesnost hodnocení."),
        ("8. Omezení odpovědnosti", "Nerq nenese odpovědnost za nepřímé nebo následné škody. Maximální odpovědnost: €100."),
        ("9. Odškodnění", "Souhlasíte s tím, že odškodníte Nerq od nároků vzniklých z vašeho používání Služby."),
        ("10. Odznaky shody", "Odznaky odrážejí automatizovaná hodnocení v daném čase a nepředstavují certifikaci."),
        ("11. Transparentnost AI", "Hodnocení využívají AI a mohou obsahovat chyby. Výstupy jsou pravděpodobnostní."),
        ("12. Změny", "Nerq může tyto Podmínky měnit. Pokračující používání představuje přijetí."),
        ("13. Ukončení", "Nerq může kdykoli pozastavit přístup. Používání Služby můžete kdykoli ukončit."),
        ("14. Rozhodné právo", "Tyto Podmínky se řídí švédským právem. Spory řeší stockholmské soudy."),
        ("15. Kontakt", "Otázky: <a href='mailto:hello@nerq.ai'>hello@nerq.ai</a>"),
    ],
    "th": [
        ("1. การยอมรับข้อกำหนด", "การใช้ Nerq ถือว่าคุณยอมรับข้อกำหนดเหล่านี้ หากไม่เห็นด้วย กรุณาอย่าใช้บริการ"),
        ("2. คำอธิบายบริการ", "Nerq ให้บริการคะแนนความน่าเชื่อถือและการประเมินความปลอดภัยสำหรับเอนทิตีดิจิทัล"),
        ("3. เพื่อวัตถุประสงค์ข้อมูลเท่านั้น", "การประเมินความน่าเชื่อถือมีไว้เพื่อวัตถุประสงค์ข้อมูลเท่านั้น และไม่ถือเป็นคำแนะนำทางกฎหมายหรือวิชาชีพ คุณรับผิดชอบต่อการตัดสินใจด้านการปฏิบัติตามกฎระเบียบของคุณเอง"),
        ("4. ความรับผิดชอบของคุณ", "คุณรับผิดชอบต่อความถูกต้องของข้อมูลที่คุณให้และการตัดสินใจของคุณเอง"),
        ("5. ทรัพย์สินทางปัญญา", "Nerq สงวนสิทธิ์ทั้งหมดในบริการ คุณยังคงเป็นเจ้าของข้อมูลที่คุณส่ง"),
        ("6. การใช้งานที่ยอมรับได้", "ห้ามใช้บริการเพื่อวัตถุประสงค์ที่ผิดกฎหมาย หรือแสดงคะแนนความน่าเชื่อถือเป็นการรับรองอย่างเป็นทางการ"),
        ("7. การปฏิเสธการรับประกัน", "บริการนี้มีให้ 'ตามสภาพ' โดยไม่มีการรับประกัน Nerq ไม่รับประกันความถูกต้องของการประเมิน"),
        ("8. การจำกัดความรับผิด", "Nerq ไม่รับผิดชอบต่อความเสียหายทางอ้อมหรือผลที่ตามมา ความรับผิดสูงสุด: €100"),
        ("9. การชดใช้ค่าเสียหาย", "คุณตกลงที่จะชดใช้ค่าเสียหายให้ Nerq จากการเรียกร้องที่เกิดจากการใช้บริการของคุณ"),
        ("10. ป้ายการปฏิบัติตามกฎระเบียบ", "ป้ายสะท้อนการประเมินอัตโนมัติ ณ จุดหนึ่งในเวลา และไม่ถือเป็นการรับรอง"),
        ("11. ความโปร่งใสของ AI", "การประเมินใช้ AI และอาจมีข้อผิดพลาด ผลลัพธ์เป็นความน่าจะเป็น"),
        ("12. การปรับปรุง", "Nerq อาจแก้ไขข้อกำหนดเหล่านี้ การใช้งานต่อเนื่องถือเป็นการยอมรับ"),
        ("13. การยกเลิก", "Nerq อาจระงับการเข้าถึงได้ทุกเมื่อ คุณอาจหยุดใช้บริการได้ทุกเมื่อ"),
        ("14. กฎหมายที่ใช้บังคับ", "ข้อกำหนดเหล่านี้อยู่ภายใต้กฎหมายสวีเดน ข้อพิพาทได้รับการแก้ไขโดยศาลสตอกโฮล์ม"),
        ("15. ติดต่อ", "คำถาม: <a href='mailto:hello@nerq.ai'>hello@nerq.ai</a>"),
    ],
    "ro": [
        ("1. Acceptarea termenilor", "Prin utilizarea Nerq, acceptați acești Termeni. Dacă nu sunteți de acord, nu utilizați Serviciul."),
        ("2. Descrierea serviciului", "Nerq oferă scoruri de încredere și evaluări de siguranță pentru entitățile digitale."),
        ("3. Doar în scop informativ", "Evaluările de încredere sunt doar în scop informativ și nu constituie consultanță juridică sau profesională. Sunteți responsabili pentru propriile decizii de conformitate."),
        ("4. Responsabilitățile dvs.", "Sunteți responsabili pentru acuratețea informațiilor pe care le furnizați și pentru propriile decizii."),
        ("5. Proprietate intelectuală", "Nerq păstrează toate drepturile asupra Serviciului. Păstrați dreptul de proprietate asupra datelor pe care le trimiteți."),
        ("6. Utilizare acceptabilă", "Nu utilizați Serviciul în scopuri ilegale și nu prezentați scorurile de încredere drept certificări oficiale."),
        ("7. Excluderea garanțiilor", "SERVICIUL ESTE FURNIZAT 'CA ATARE' FĂRĂ GARANȚII. Nerq nu garantează acuratețea evaluărilor."),
        ("8. Limitarea răspunderii", "Nerq nu este răspunzătoare pentru daune indirecte sau consecvente. Răspundere maximă: €100."),
        ("9. Despăgubire", "Sunteți de acord să despăgubiți Nerq pentru reclamațiile care decurg din utilizarea Serviciului."),
        ("10. Insigne de conformitate", "Insignele reflectă evaluări automate la un moment dat și nu constituie certificare."),
        ("11. Transparența AI", "Evaluările utilizează AI și pot conține erori. Rezultatele sunt probabilistice."),
        ("12. Modificări", "Nerq poate modifica acești Termeni. Utilizarea continuă constituie acceptare."),
        ("13. Reziliere", "Nerq poate suspenda accesul în orice moment. Puteți înceta utilizarea Serviciului în orice moment."),
        ("14. Legea aplicabilă", "Acești Termeni sunt guvernați de legea suedeză. Litigiile sunt soluționate de instanțele din Stockholm."),
        ("15. Contact", "Întrebări: <a href='mailto:hello@nerq.ai'>hello@nerq.ai</a>"),
    ],
    "tr": [
        ("1. Koşulların Kabulü", "Nerq'i kullanarak bu Koşulları kabul etmiş olursunuz. Kabul etmiyorsanız Hizmeti kullanmayın."),
        ("2. Hizmetin Tanımı", "Nerq, dijital varlıklar için güven puanlama ve güvenlik değerlendirmeleri sağlar."),
        ("3. Yalnızca Bilgilendirme Amaçlı", "Güven değerlendirmeleri yalnızca bilgilendirme amaçlıdır ve hukuki veya profesyonel tavsiye niteliği taşımaz. Kendi uyum kararlarınızdan siz sorumlusunuz."),
        ("4. Sorumluluklarınız", "Sağladığınız bilgilerin doğruluğundan ve kendi kararlarınızdan siz sorumlusunuz."),
        ("5. Fikri Mülkiyet", "Nerq, Hizmet üzerindeki tüm hakları saklı tutar. Gönderdiğiniz verilerin mülkiyetini siz elinde tutarsınız."),
        ("6. Kabul Edilebilir Kullanım", "Hizmeti yasadışı amaçlarla kullanmayın veya güven puanlarını resmi sertifikalar olarak yanlış beyan etmeyin."),
        ("7. Garanti Reddi", "HİZMET GARANTİ OLMAKSIZIN 'OLDUĞU GİBİ' SUNULMAKTADIR. Nerq, değerlendirmelerin doğruluğunu garanti etmez."),
        ("8. Sorumluluğun Sınırlandırılması", "Nerq, dolaylı veya sonuç olarak ortaya çıkan zararlardan sorumlu değildir. Azami sorumluluk: €100."),
        ("9. Tazminat", "Hizmeti kullanımınızdan kaynaklanan taleplerden Nerq'i korumayı kabul edersiniz."),
        ("10. Uyum Rozetleri", "Rozetler, belirli bir zamandaki otomatik değerlendirmeleri yansıtır ve sertifikasyon niteliği taşımaz."),
        ("11. Yapay Zeka Şeffaflığı", "Değerlendirmeler yapay zeka kullanır ve hata içerebilir. Çıktılar olasılıksaldır."),
        ("12. Değişiklikler", "Nerq bu Koşulları değiştirebilir. Kullanmaya devam etmek kabulü oluşturur."),
        ("13. Fesih", "Nerq istediği zaman erişimi askıya alabilir. İstediğiniz zaman Hizmeti kullanmayı bırakabilirsiniz."),
        ("14. Geçerli Hukuk", "Bu Koşullar İsveç hukukuna tabidir. Anlaşmazlıklar Stockholm mahkemelerinde çözümlenir."),
        ("15. İletişim", "Sorularınız: <a href='mailto:hello@nerq.ai'>hello@nerq.ai</a>"),
    ],
    "hi": [
        ("1. शर्तों की स्वीकृति", "Nerq का उपयोग करके, आप इन शर्तों से सहमत होते हैं। यदि असहमत हैं, तो सेवा का उपयोग न करें।"),
        ("2. सेवा का विवरण", "Nerq डिजिटल इकाइयों के लिए विश्वास स्कोरिंग और सुरक्षा मूल्यांकन प्रदान करता है।"),
        ("3. केवल सूचनात्मक उद्देश्यों के लिए", "विश्वास मूल्यांकन केवल सूचनात्मक उद्देश्यों के लिए हैं और कानूनी या पेशेवर सलाह नहीं हैं। आप अपने अनुपालन निर्णयों के लिए जिम्मेदार हैं।"),
        ("4. आपकी जिम्मेदारियां", "आप द्वारा प्रदान की गई जानकारी की सटीकता और अपने निर्णयों के लिए आप जिम्मेदार हैं।"),
        ("5. बौद्धिक संपदा", "Nerq सेवा में सभी अधिकार बनाए रखता है। आप जो डेटा सबमिट करते हैं उसका स्वामित्व आपके पास रहता है।"),
        ("6. स्वीकार्य उपयोग", "सेवा का उपयोग गैरकानूनी उद्देश्यों के लिए न करें और विश्वास स्कोर को आधिकारिक प्रमाणन के रूप में गलत तरीके से प्रस्तुत न करें।"),
        ("7. वारंटी अस्वीकरण", "सेवा 'जैसी है' बिना किसी वारंटी के प्रदान की जाती है। Nerq मूल्यांकन की सटीकता की गारंटी नहीं देता।"),
        ("8. देयता की सीमा", "Nerq अप्रत्यक्ष या परिणामी नुकसान के लिए उत्तरदायी नहीं है। अधिकतम देयता: €100।"),
        ("9. क्षतिपूर्ति", "आप सेवा के उपयोग से उत्पन्न दावों से Nerq को क्षतिपूर्ति करने के लिए सहमत हैं।"),
        ("10. अनुपालन बैज", "बैज किसी समय पर स्वचालित मूल्यांकन को दर्शाते हैं और प्रमाणन नहीं हैं।"),
        ("11. AI पारदर्शिता", "मूल्यांकन AI का उपयोग करते हैं और त्रुटियां हो सकती हैं। आउटपुट संभाव्य हैं।"),
        ("12. संशोधन", "Nerq इन शर्तों को संशोधित कर सकता है। निरंतर उपयोग स्वीकृति मानी जाती है।"),
        ("13. समाप्ति", "Nerq किसी भी समय पहुंच निलंबित कर सकता है। आप किसी भी समय सेवा का उपयोग बंद कर सकते हैं।"),
        ("14. शासी कानून", "ये शर्तें स्वीडिश कानून द्वारा नियंत्रित हैं। विवादों का समाधान स्टॉकहोम न्यायालयों द्वारा किया जाता है।"),
        ("15. संपर्क", "प्रश्न: <a href='mailto:hello@nerq.ai'>hello@nerq.ai</a>"),
    ],
    "ru": [
        ("1. Принятие условий", "Используя Nerq, вы соглашаетесь с настоящими Условиями. Если вы не согласны, не используйте Сервис."),
        ("2. Описание сервиса", "Nerq предоставляет оценки доверия и оценки безопасности для цифровых сущностей."),
        ("3. Только в информационных целях", "Оценки доверия носят исключительно информационный характер и не являются юридическими или профессиональными рекомендациями. Вы несёте ответственность за свои решения в области соответствия."),
        ("4. Ваши обязанности", "Вы несёте ответственность за точность предоставляемой информации и за собственные решения."),
        ("5. Интеллектуальная собственность", "Nerq сохраняет все права на Сервис. Вы сохраняете право собственности на данные, которые отправляете."),
        ("6. Допустимое использование", "Не используйте Сервис в незаконных целях и не представляйте оценки доверия как официальные сертификаты."),
        ("7. Отказ от гарантий", "СЕРВИС ПРЕДОСТАВЛЯЕТСЯ «КАК ЕСТЬ» БЕЗ КАКИХ-ЛИБО ГАРАНТИЙ. Nerq не гарантирует точность оценок."),
        ("8. Ограничение ответственности", "Nerq не несёт ответственности за косвенный или последующий ущерб. Максимальная ответственность: €100."),
        ("9. Возмещение ущерба", "Вы соглашаетесь возместить Nerq ущерб от претензий, возникших в результате использования вами Сервиса."),
        ("10. Знаки соответствия", "Знаки отражают автоматизированные оценки на определённый момент времени и не являются сертификацией."),
        ("11. Прозрачность ИИ", "Оценки используют ИИ и могут содержать ошибки. Результаты носят вероятностный характер."),
        ("12. Изменения", "Nerq может изменять настоящие Условия. Продолжение использования означает согласие."),
        ("13. Прекращение", "Nerq может в любое время приостановить доступ. Вы можете в любое время прекратить использование Сервиса."),
        ("14. Применимое право", "Настоящие Условия регулируются законодательством Швеции. Споры разрешаются судами Стокгольма."),
        ("15. Контакт", "Вопросы: <a href='mailto:hello@nerq.ai'>hello@nerq.ai</a>"),
    ],
    "pl": [
        ("1. Akceptacja warunków", "Korzystając z Nerq, akceptujesz niniejsze Warunki. Jeśli się nie zgadzasz, nie korzystaj z Usługi."),
        ("2. Opis usługi", "Nerq zapewnia oceny zaufania i oceny bezpieczeństwa dla podmiotów cyfrowych."),
        ("3. Wyłącznie w celach informacyjnych", "Oceny zaufania mają wyłącznie charakter informacyjny i nie stanowią porady prawnej ani profesjonalnej. Jesteś odpowiedzialny za własne decyzje dotyczące zgodności."),
        ("4. Twoje odpowiedzialności", "Jesteś odpowiedzialny za dokładność podanych informacji i własne decyzje."),
        ("5. Własność intelektualna", "Nerq zachowuje wszystkie prawa do Usługi. Zachowujesz własność danych, które przesyłasz."),
        ("6. Dopuszczalne użytkowanie", "Nie używaj Usługi do celów niezgodnych z prawem ani nie przedstawiaj wyników zaufania jako oficjalnych certyfikacji."),
        ("7. Wyłączenie gwarancji", "USŁUGA JEST ŚWIADCZONA 'W STANIE, W JAKIM JEST' BEZ GWARANCJI. Nerq nie gwarantuje dokładności ocen."),
        ("8. Ograniczenie odpowiedzialności", "Nerq nie ponosi odpowiedzialności za pośrednie lub wynikowe szkody. Maksymalna odpowiedzialność: €100."),
        ("9. Odszkodowanie", "Zgadzasz się zabezpieczyć Nerq przed roszczeniami wynikającymi z korzystania przez Ciebie z Usługi."),
        ("10. Odznaki zgodności", "Odznaki odzwierciedlają automatyczne oceny w danym momencie i nie stanowią certyfikacji."),
        ("11. Przejrzystość AI", "Oceny korzystają z AI i mogą zawierać błędy. Wyniki mają charakter probabilistyczny."),
        ("12. Modyfikacje", "Nerq może modyfikować niniejsze Warunki. Dalsze korzystanie oznacza akceptację."),
        ("13. Zakończenie", "Nerq może w dowolnym momencie zawiesić dostęp. Możesz w dowolnym momencie zaprzestać korzystania z Usługi."),
        ("14. Prawo właściwe", "Niniejsze Warunki podlegają prawu szwedzkiemu. Spory rozstrzygają sądy w Sztokholmie."),
        ("15. Kontakt", "Pytania: <a href='mailto:hello@nerq.ai'>hello@nerq.ai</a>"),
    ],
    "it": [
        ("1. Accettazione dei termini", "Utilizzando Nerq, accetti questi Termini. Se non sei d'accordo, non utilizzare il Servizio."),
        ("2. Descrizione del servizio", "Nerq fornisce punteggi di fiducia e valutazioni di sicurezza per entità digitali."),
        ("3. Solo a scopo informativo", "Le valutazioni di fiducia sono solo a scopo informativo e non costituiscono consulenza legale o professionale. Sei responsabile delle tue decisioni di conformità."),
        ("4. Le tue responsabilità", "Sei responsabile dell'accuratezza delle informazioni che fornisci e delle tue decisioni."),
        ("5. Proprietà intellettuale", "Nerq conserva tutti i diritti sul Servizio. Conservi la proprietà dei dati che invii."),
        ("6. Uso accettabile", "Non utilizzare il Servizio per scopi illegali né presentare erroneamente i punteggi di fiducia come certificazioni ufficiali."),
        ("7. Esclusione di garanzia", "IL SERVIZIO È FORNITO 'COSÌ COM'È' SENZA GARANZIE. Nerq non garantisce l'accuratezza delle valutazioni."),
        ("8. Limitazione di responsabilità", "Nerq non è responsabile per danni indiretti o consequenziali. Responsabilità massima: €100."),
        ("9. Indennizzo", "Accetti di manlevare Nerq da reclami derivanti dal tuo utilizzo del Servizio."),
        ("10. Badge di conformità", "I badge riflettono valutazioni automatizzate in un momento specifico e non costituiscono certificazione."),
        ("11. Trasparenza AI", "Le valutazioni utilizzano l'AI e possono contenere errori. I risultati sono probabilistici."),
        ("12. Modifiche", "Nerq può modificare questi Termini. L'uso continuato costituisce accettazione."),
        ("13. Cessazione", "Nerq può sospendere l'accesso in qualsiasi momento. Puoi smettere di utilizzare il Servizio in qualsiasi momento."),
        ("14. Legge applicabile", "Questi Termini sono disciplinati dalla legge svedese. Le controversie sono risolte dai tribunali di Stoccolma."),
        ("15. Contatti", "Domande: <a href='mailto:hello@nerq.ai'>hello@nerq.ai</a>"),
    ],
    "ko": [
        ("1. 약관 동의", "Nerq를 사용함으로써 본 약관에 동의하는 것으로 간주됩니다. 동의하지 않는 경우 서비스를 이용하지 마십시오."),
        ("2. 서비스 설명", "Nerq는 디지털 엔터티에 대한 신뢰 점수 산정 및 안전성 평가를 제공합니다."),
        ("3. 정보 제공 목적만", "신뢰 평가는 정보 제공 목적으로만 제공되며, 법적 또는 전문적인 조언을 구성하지 않습니다. 규정 준수 결정은 귀하의 책임입니다."),
        ("4. 귀하의 책임", "귀하가 제공하는 정보의 정확성 및 귀하의 결정에 대한 책임은 귀하에게 있습니다."),
        ("5. 지적 재산권", "Nerq는 서비스에 대한 모든 권리를 보유합니다. 귀하가 제출한 데이터의 소유권은 귀하에게 있습니다."),
        ("6. 허용 가능한 사용", "불법적인 목적으로 서비스를 사용하거나 신뢰 점수를 공식 인증으로 허위 표시하지 마십시오."),
        ("7. 보증 부인", "서비스는 어떠한 보증도 없이 '있는 그대로' 제공됩니다. Nerq는 평가의 정확성을 보장하지 않습니다."),
        ("8. 책임 제한", "Nerq는 간접적 또는 결과적 손해에 대해 책임을 지지 않습니다. 최대 책임: €100."),
        ("9. 면책", "귀하는 서비스 이용으로 인해 발생하는 청구로부터 Nerq를 면책하는 데 동의합니다."),
        ("10. 규정 준수 배지", "배지는 특정 시점의 자동화된 평가를 반영하며 인증을 구성하지 않습니다."),
        ("11. AI 투명성", "평가는 AI를 사용하며 오류가 포함될 수 있습니다. 출력은 확률적입니다."),
        ("12. 수정", "Nerq는 본 약관을 수정할 수 있습니다. 계속 사용하면 동의한 것으로 간주됩니다."),
        ("13. 종료", "Nerq는 언제든지 접근을 정지할 수 있습니다. 귀하는 언제든지 서비스 이용을 중단할 수 있습니다."),
        ("14. 준거법", "본 약관은 스웨덴 법에 의해 규율됩니다. 분쟁은 스톡홀름 법원에서 해결됩니다."),
        ("15. 연락처", "문의: <a href='mailto:hello@nerq.ai'>hello@nerq.ai</a>"),
    ],
    "vi": [
        ("1. Chấp nhận Điều khoản", "Bằng cách sử dụng Nerq, bạn đồng ý với các Điều khoản này. Nếu không đồng ý, vui lòng không sử dụng Dịch vụ."),
        ("2. Mô tả Dịch vụ", "Nerq cung cấp điểm tin cậy và đánh giá an toàn cho các thực thể số."),
        ("3. Chỉ để cung cấp thông tin", "Các đánh giá tin cậy chỉ dành cho mục đích thông tin và không cấu thành lời khuyên pháp lý hoặc chuyên nghiệp. Bạn chịu trách nhiệm về các quyết định tuân thủ của riêng mình."),
        ("4. Trách nhiệm của bạn", "Bạn chịu trách nhiệm về độ chính xác của thông tin bạn cung cấp và các quyết định của chính mình."),
        ("5. Sở hữu trí tuệ", "Nerq giữ lại tất cả các quyền đối với Dịch vụ. Bạn giữ quyền sở hữu dữ liệu bạn gửi."),
        ("6. Sử dụng chấp nhận được", "Không sử dụng Dịch vụ cho mục đích bất hợp pháp hoặc trình bày sai điểm tin cậy như các chứng nhận chính thức."),
        ("7. Tuyên bố từ chối bảo hành", "DỊCH VỤ ĐƯỢC CUNG CẤP 'NGUYÊN TRẠNG' MÀ KHÔNG CÓ BẢO HÀNH. Nerq không đảm bảo độ chính xác của các đánh giá."),
        ("8. Giới hạn trách nhiệm", "Nerq không chịu trách nhiệm về các thiệt hại gián tiếp hoặc hậu quả. Trách nhiệm tối đa: €100."),
        ("9. Bồi thường", "Bạn đồng ý bồi thường cho Nerq khỏi các khiếu nại phát sinh từ việc bạn sử dụng Dịch vụ."),
        ("10. Huy hiệu tuân thủ", "Huy hiệu phản ánh các đánh giá tự động tại một thời điểm và không cấu thành chứng nhận."),
        ("11. Minh bạch AI", "Các đánh giá sử dụng AI và có thể chứa lỗi. Đầu ra mang tính xác suất."),
        ("12. Sửa đổi", "Nerq có thể sửa đổi các Điều khoản này. Tiếp tục sử dụng là chấp nhận."),
        ("13. Chấm dứt", "Nerq có thể đình chỉ quyền truy cập bất cứ lúc nào. Bạn có thể ngừng sử dụng Dịch vụ bất cứ lúc nào."),
        ("14. Luật điều chỉnh", "Các Điều khoản này được điều chỉnh bởi luật pháp Thụy Điển. Tranh chấp được giải quyết bởi tòa án Stockholm."),
        ("15. Liên hệ", "Câu hỏi: <a href='mailto:hello@nerq.ai'>hello@nerq.ai</a>"),
    ],
    "nl": [
        ("1. Acceptatie van voorwaarden", "Door Nerq te gebruiken, gaat u akkoord met deze Voorwaarden. Als u het er niet mee eens bent, gebruik de Service dan niet."),
        ("2. Beschrijving van de service", "Nerq biedt vertrouwensscores en veiligheidsbeoordelingen voor digitale entiteiten."),
        ("3. Uitsluitend voor informatieve doeleinden", "Vertrouwensbeoordelingen zijn uitsluitend voor informatieve doeleinden en vormen geen juridisch of professioneel advies. U bent verantwoordelijk voor uw eigen nalevingsbeslissingen."),
        ("4. Uw verantwoordelijkheden", "U bent verantwoordelijk voor de nauwkeurigheid van de informatie die u verstrekt en uw eigen beslissingen."),
        ("5. Intellectueel eigendom", "Nerq behoudt alle rechten op de Service. U behoudt de eigendom van gegevens die u indient."),
        ("6. Acceptabel gebruik", "Gebruik de Service niet voor onwettige doeleinden en stel vertrouwensscores niet voor als officiële certificeringen."),
        ("7. Garantiedisclaimer", "DE SERVICE WORDT GELEVERD 'ZOALS IS' ZONDER GARANTIES. Nerq garandeert de nauwkeurigheid van beoordelingen niet."),
        ("8. Beperking van aansprakelijkheid", "Nerq is niet aansprakelijk voor indirecte of gevolgschade. Maximale aansprakelijkheid: €100."),
        ("9. Vrijwaring", "U stemt ermee in Nerq te vrijwaren van claims die voortvloeien uit uw gebruik van de Service."),
        ("10. Compliancebadges", "Badges weerspiegelen geautomatiseerde beoordelingen op een bepaald moment en vormen geen certificering."),
        ("11. AI-transparantie", "Beoordelingen maken gebruik van AI en kunnen fouten bevatten. Uitvoer is probabilistisch."),
        ("12. Wijzigingen", "Nerq kan deze Voorwaarden wijzigen. Voortgezet gebruik geldt als acceptatie."),
        ("13. Beëindiging", "Nerq kan de toegang op elk moment opschorten. U kunt de Service op elk moment niet meer gebruiken."),
        ("14. Toepasselijk recht", "Deze Voorwaarden worden beheerst door Zweeds recht. Geschillen worden beslecht door Stockholmse rechtbanken."),
        ("15. Contact", "Vragen: <a href='mailto:hello@nerq.ai'>hello@nerq.ai</a>"),
    ],
    "sv": [
        ("1. Acceptans av villkor", "Genom att använda Nerq accepterar du dessa Villkor. Om du inte håller med, använd inte Tjänsten."),
        ("2. Beskrivning av tjänsten", "Nerq tillhandahåller förtroendepoäng och säkerhetsbedömningar för digitala entiteter."),
        ("3. Endast för informationsändamål", "Förtroendebedömningar är enbart för informationsändamål och utgör inte juridisk eller professionell rådgivning. Du ansvarar för dina egna efterlevnadsbeslut."),
        ("4. Ditt ansvar", "Du ansvarar för noggrannheten i den information du tillhandahåller och dina egna beslut."),
        ("5. Immateriella rättigheter", "Nerq behåller alla rättigheter till Tjänsten. Du behåller äganderätten till data du skickar in."),
        ("6. Acceptabel användning", "Använd inte Tjänsten för olagliga ändamål eller missrepresentera förtroendepoäng som officiella certifieringar."),
        ("7. Garantifriskrivning", "TJÄNSTEN TILLHANDAHÅLLS 'I BEFINTLIGT SKICK' UTAN GARANTIER. Nerq garanterar inte noggrannheten i bedömningarna."),
        ("8. Ansvarsbegränsning", "Nerq är inte ansvarigt för indirekta eller följdskador. Maximal ansvar: €100."),
        ("9. Skadeersättning", "Du samtycker till att hålla Nerq skadelöst från anspråk som uppstår från din användning av Tjänsten."),
        ("10. Efterlevnadsmärken", "Märken återspeglar automatiserade bedömningar vid en tidpunkt och utgör inte certifiering."),
        ("11. AI-transparens", "Bedömningar använder AI och kan innehålla fel. Utdata är probabilistiska."),
        ("12. Ändringar", "Nerq kan ändra dessa Villkor. Fortsatt användning utgör acceptans."),
        ("13. Uppsägning", "Nerq kan när som helst stänga av åtkomst. Du kan när som helst sluta använda Tjänsten."),
        ("14. Tillämplig lag", "Dessa Villkor regleras av svensk lag. Tvister avgörs av Stockholms domstolar."),
        ("15. Kontakt", "Frågor: <a href='mailto:hello@nerq.ai'>hello@nerq.ai</a>"),
    ],
    "zh": [
        ("1. 接受条款", "使用 Nerq 即表示您同意这些条款。如果不同意，请勿使用本服务。"),
        ("2. 服务描述", "Nerq 为数字实体提供信任评分和安全评估。"),
        ("3. 仅供参考", "信任评估仅供参考，不构成法律或专业建议。您对自己的合规决策负责。"),
        ("4. 您的责任", "您对提供的信息准确性及自己的决策负责。"),
        ("5. 知识产权", "Nerq 保留服务的所有权利。您保留提交数据的所有权。"),
        ("6. 可接受的使用", "不得将服务用于非法目的，也不得将信任评分误述为官方认证。"),
        ("7. 免责声明", "服务按「原样」提供，不提供任何保证。Nerq 不保证评估的准确性。"),
        ("8. 责任限制", "Nerq 对间接或结果性损害不承担责任。最大责任：€100。"),
        ("9. 赔偿", "您同意就您使用服务产生的索赔向 Nerq 进行赔偿。"),
        ("10. 合规徽章", "徽章反映某一时间点的自动评估，不构成认证。"),
        ("11. AI 透明度", "评估使用 AI，可能包含错误。输出具有概率性。"),
        ("12. 修改", "Nerq 可能修改这些条款。继续使用即视为接受。"),
        ("13. 终止", "Nerq 可随时暂停访问。您可随时停止使用服务。"),
        ("14. 适用法律", "本条款受瑞典法律管辖。争议由斯德哥尔摩法院解决。"),
        ("15. 联系方式", "问题：<a href='mailto:hello@nerq.ai'>hello@nerq.ai</a>"),
    ],
    "da": [
        ("1. Acceptering af vilkår", "Ved at bruge Nerq accepterer du disse Vilkår. Hvis du er uenig, må du ikke bruge Tjenesten."),
        ("2. Beskrivelse af tjenesten", "Nerq leverer tillidsscorer og sikkerhedsvurderinger for digitale enheder."),
        ("3. Kun til informationsformål", "Tillidssvurderinger er kun til informationsformål og udgør ikke juridisk eller professionel rådgivning. Du er ansvarlig for dine egne overholdelsesafgørelser."),
        ("4. Dine ansvarsområder", "Du er ansvarlig for nøjagtigheden af de oplysninger, du giver, og dine egne beslutninger."),
        ("5. Intellektuel ejendomsret", "Nerq beholder alle rettigheder til Tjenesten. Du beholder ejerskabet af de data, du indsender."),
        ("6. Acceptabel brug", "Brug ikke Tjenesten til ulovlige formål eller fremstil tillidsscorer som officielle certificeringer."),
        ("7. Garantifraskrivelse", "TJENESTEN LEVERES 'SOM DEN ER' UDEN GARANTIER. Nerq garanterer ikke nøjagtigheden af vurderinger."),
        ("8. Ansvarsbegrænsning", "Nerq er ikke ansvarlig for indirekte eller følgeskader. Maksimalt ansvar: €100."),
        ("9. Skadesløsholdelse", "Du accepterer at holde Nerq skadesløs fra krav, der opstår fra din brug af Tjenesten."),
        ("10. Overholdelsesbadges", "Badges afspejler automatiserede vurderinger på et tidspunkt og udgør ikke certificering."),
        ("11. AI-gennemsigtighed", "Vurderinger bruger AI og kan indeholde fejl. Output er probabilistiske."),
        ("12. Ændringer", "Nerq kan ændre disse Vilkår. Fortsat brug udgør accept."),
        ("13. Opsigelse", "Nerq kan til enhver tid suspendere adgang. Du kan til enhver tid stoppe med at bruge Tjenesten."),
        ("14. Gældende ret", "Disse Vilkår er underlagt svensk ret. Tvister afgøres af Stockholms domstole."),
        ("15. Kontakt", "Spørgsmål: <a href='mailto:hello@nerq.ai'>hello@nerq.ai</a>"),
    ],
}


def _gt(key, lang):
    d = _T.get(key, {})
    return d.get(lang, d.get("en", key))


def _page_head(lang, title, desc, page_path):
    hreflang = render_hreflang(f"/{page_path}")
    canonical = f"{_SITE}/{lang}/{page_path}" if lang != "en" else f"{_SITE}/{page_path}"
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc[:160]}">
<link rel="canonical" href="{canonical}">
{hreflang}
<meta property="og:title" content="{title}">
<meta property="og:url" content="{canonical}">
<meta name="robots" content="index, follow, max-snippet:-1">
<link rel="stylesheet" href="/static/nerq.css?v=13">
{NERQ_CSS}
</head>
<body>
{NERQ_NAV}
<main class="container" style="padding-top:20px;padding-bottom:40px">"""


def render_about(lang="en"):
    t = lambda k: _gt(k, lang)
    return f"""{_page_head(lang, t('about_title'), t('about_desc')[:160], 'about')}
<h1>{t('about_h1')}</h1>
<div style="margin:20px 0;font-size:16px;line-height:1.8;color:#374151"><p>{t('about_desc')}</p></div>
<h2>{t('what_we_do')}</h2>
<p style="font-size:15px;line-height:1.7;color:#374151;margin-bottom:16px">Trust Score (0–100):</p>
<table>
<tr><td style="font-weight:600;width:180px">Security (25%)</td><td>CVEs, vulnerability exposure</td></tr>
<tr><td style="font-weight:600">Community (25%)</td><td>Stars, downloads, contributors</td></tr>
<tr><td style="font-weight:600">Compliance (20%)</td><td>License, EU AI Act mapping</td></tr>
<tr><td style="font-weight:600">Maintenance (15%)</td><td>Update recency, release cadence</td></tr>
<tr><td style="font-weight:600">Quality (15%)</td><td>Documentation, description quality</td></tr>
</table>
<h2>{t('key_numbers')}</h2>
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:12px 0">
<div style="border:1px solid #e5e7eb;padding:16px;text-align:center"><div style="font-family:ui-monospace,monospace;font-size:1.5rem;font-weight:700;color:#0d9488">7.5M+</div><div style="font-size:12px;color:#6b7280">Entities</div></div>
<div style="border:1px solid #e5e7eb;padding:16px;text-align:center"><div style="font-family:ui-monospace,monospace;font-size:1.5rem;font-weight:700;color:#0d9488">26</div><div style="font-size:12px;color:#6b7280">Registries</div></div>
<div style="border:1px solid #e5e7eb;padding:16px;text-align:center"><div style="font-family:ui-monospace,monospace;font-size:1.5rem;font-weight:700;color:#0d9488">21</div><div style="font-size:12px;color:#6b7280">Languages</div></div>
<div style="border:1px solid #e5e7eb;padding:16px;text-align:center"><div style="font-family:ui-monospace,monospace;font-size:1.5rem;font-weight:700;color:#0d9488">Daily</div><div style="font-size:12px;color:#6b7280">Updates</div></div>
</div>
<h2>{t('links')}</h2>
<table>
<tr><td style="width:180px"><a href="/nerq/docs">API Documentation</a></td><td>Full endpoint reference</td></tr>
<tr><td><a href="/safe">Safety Reports</a></td><td>Browse 7.5M+ entity assessments</td></tr>
<tr><td><a href="/blog">Blog</a></td><td>Research and reports</td></tr>
</table>
<h2>{t('contact')}</h2>
<table>
<tr><td style="color:#6b7280;width:180px">Founded by</td><td>Anders Nilsson</td></tr>
<tr><td style="color:#6b7280">Email</td><td><a href="mailto:anders@nerq.ai">anders@nerq.ai</a></td></tr>
</table>
</main>
{NERQ_FOOTER}
</body></html>"""


def render_privacy(lang="en"):
    t = lambda k: _gt(k, lang)
    sections = _PRIVACY_SECTIONS.get(lang, _PRIVACY_SECTIONS["en"])
    body = "\n".join(
        f"<h2>{h}</h2>\n<p style=\"font-size:15px;line-height:1.8;color:#374151\">{b}</p>"
        for h, b in sections
    )
    desc = sections[0][1][:160]
    return f"""{_page_head(lang, t('privacy_title'), desc, 'privacy')}
<h1>{t('privacy_h1')}</h1>
<p><strong>{t('last_updated')}</strong></p>
{body}
</main>
{NERQ_FOOTER}
</body></html>"""


def render_terms(lang="en"):
    t = lambda k: _gt(k, lang)
    sections = _TERMS_SECTIONS.get(lang, _TERMS_SECTIONS["en"])
    body = "\n".join(
        f"<h2 style=\"font-size:1rem;font-weight:600;color:#111827;margin-top:24px\">{h}</h2>\n<p style=\"font-size:15px;line-height:1.8;color:#374151\">{b}</p>"
        for h, b in sections
    )
    _terms_desc = sections[0][1][:160] if sections else "Terms of Service"
    return f"""{_page_head(lang, t('terms_title'), _terms_desc, 'terms')}
<h1>{t('terms_title').replace(' — Nerq', '')}</h1>
<p><strong>{t('effective')}</strong></p>
{body}
</main>
{NERQ_FOOTER}
</body></html>"""


def render_discover(lang="en"):
    t = lambda k: _gt(k, lang)
    title = t("discover_title")
    h1 = t("discover_h1")
    placeholder = t("discover_placeholder")
    categories_label = t("discover_categories")
    categories = [
        ("AI Agents", "/search?q=agent"),
        ("MCP Servers", "/search?q=mcp"),
        ("LLM Tools", "/search?q=llm"),
        ("Safety", "/safe"),
        ("Models", "/search?q=model"),
        ("Frameworks", "/search?q=framework"),
    ]
    cat_links = " ".join(
        f'<a href="{url}" style="display:inline-block;padding:6px 14px;margin:4px;border:1px solid #e5e7eb;border-radius:20px;font-size:13px;color:#374151;text-decoration:none">{label}</a>'
        for label, url in categories
    )
    return f"""{_page_head(lang, title, placeholder, 'discover')}
<h1 style="font-size:2rem;font-weight:700;margin-bottom:24px">{h1}</h1>
<form action="/search" method="get" style="margin-bottom:32px">
<input name="q" type="search" placeholder="{placeholder}"
  style="width:100%;max-width:600px;padding:12px 16px;font-size:16px;border:2px solid #e5e7eb;border-radius:8px;outline:none">
<button type="submit" style="margin-left:8px;padding:12px 20px;background:#0d9488;color:#fff;border:none;border-radius:8px;font-size:15px;cursor:pointer">{h1}</button>
</form>
<h2 style="font-size:1rem;font-weight:600;color:#6b7280;margin-bottom:12px">{categories_label}</h2>
<div>{cat_links}</div>
</main>
{NERQ_FOOTER}
</body></html>"""
