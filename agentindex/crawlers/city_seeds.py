#!/usr/bin/env python3
"""City Seeds — seed ~5000 cities into software_registry with registry='city'.

Uses parent country trust_scores from DB, adjusts per-city.
Idempotent via ON CONFLICT (registry, slug) DO UPDATE.
"""
import logging
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agentindex.db.models import get_session
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
log = logging.getLogger("city_seeds")

random.seed(42)  # reproducible


def _grade(score: int) -> str:
    if score >= 90: return "A+"
    if score >= 85: return "A"
    if score >= 80: return "A-"
    if score >= 75: return "B+"
    if score >= 70: return "B"
    if score >= 65: return "B-"
    if score >= 60: return "C+"
    if score >= 55: return "C"
    if score >= 50: return "C-"
    if score >= 45: return "D+"
    if score >= 40: return "D"
    if score >= 35: return "D-"
    return "F"


def _slugify(name: str) -> str:
    """Simple slug: lowercase, replace spaces/special chars with hyphens."""
    import re
    s = name.lower().strip()
    # Handle unicode chars
    replacements = {
        "á": "a", "à": "a", "â": "a", "ã": "a", "ä": "a", "å": "a",
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "í": "i", "ì": "i", "î": "i", "ï": "i",
        "ó": "o", "ò": "o", "ô": "o", "õ": "o", "ö": "o", "ø": "o",
        "ú": "u", "ù": "u", "û": "u", "ü": "u",
        "ý": "y", "ÿ": "y", "ñ": "n", "ç": "c",
        "ß": "ss", "ð": "d", "þ": "th", "æ": "ae",
        "'": "", "'": "", "`": "", "\"": "",
    }
    for old, new in replacements.items():
        s = s.replace(old, new)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


# ─── TOURIST CITIES (is_king=True) ────────────────────────────────────────────
# (city_name, country_slug, score_adjustment, description, is_king)
TOURIST_CITIES = {
    "tokyo": ("Tokyo", "japan", 0, "Capital of Japan. Population 13.9M. One of the safest major cities globally.", True),
    "paris": ("Paris", "france", -3, "Capital of France. Population 2.1M (12M metro). Tourist pickpocketing common near landmarks.", True),
    "bangkok": ("Bangkok", "thailand", -5, "Capital of Thailand. Population 10.5M. Major tourist hub with vibrant street life.", True),
    "london": ("London", "united-kingdom", 0, "Capital of the UK. Population 8.8M. Diverse and well-policed.", True),
    "new-york": ("New York", "united-states", -5, "Largest US city. Population 8.3M. Safe in tourist areas, varies by neighborhood.", True),
    "dubai": ("Dubai", "united-arab-emirates", +3, "Largest city in UAE. Population 3.5M. Very low crime, strict laws.", True),
    "singapore-city": ("Singapore City", "singapore", 0, "City-state. Population 5.9M. Among safest cities globally.", True),
    "rome": ("Rome", "italy", -2, "Capital of Italy. Population 2.8M. Petty theft common near tourist sites.", True),
    "istanbul": ("Istanbul", "turkey", -3, "Largest city in Turkey. Population 15.8M. Busy and vibrant.", True),
    "barcelona": ("Barcelona", "spain", -3, "Major Spanish city. Population 1.6M. Pickpocketing hotspot for tourists.", True),
    "amsterdam": ("Amsterdam", "netherlands", -2, "Capital of the Netherlands. Population 900K. Liberal city, watch for bike lanes.", True),
    "sydney": ("Sydney", "australia", 0, "Largest Australian city. Population 5.3M. Generally very safe.", True),
    "kyoto": ("Kyoto", "japan", +2, "Ancient capital of Japan. Population 1.5M. Extremely safe and traditional.", True),
    "osaka": ("Osaka", "japan", 0, "Third largest Japanese city. Population 2.8M. Safe with vibrant nightlife.", True),
    "seoul": ("Seoul", "south-korea", 0, "Capital of South Korea. Population 9.7M. Very safe, excellent transit.", True),
    "berlin": ("Berlin", "germany", -2, "Capital of Germany. Population 3.6M. Safe overall, some areas rougher at night.", True),
    "lisbon": ("Lisbon", "portugal", 0, "Capital of Portugal. Population 500K. Safe and walkable.", True),
    "prague": ("Prague", "czech-republic", -2, "Capital of Czech Republic. Population 1.3M. Tourist scams common.", True),
    "vienna": ("Vienna", "austria", +2, "Capital of Austria. Population 1.9M. Consistently ranked among safest cities.", True),
    "copenhagen": ("Copenhagen", "denmark", 0, "Capital of Denmark. Population 800K. Very safe, bike-friendly.", True),
    "taipei": ("Taipei", "taiwan", 0, "Capital of Taiwan. Population 2.6M. Very safe with low crime.", True),
    "hong-kong": ("Hong Kong", "china", -5, "Special Administrative Region. Population 7.5M. Low crime, political tensions.", True),
    "bali": ("Bali", "indonesia", +5, "Indonesian island. Popular resort destination. Safe for tourists with precautions.", True),
    "phuket": ("Phuket", "thailand", -3, "Thai resort island. Population 400K. Tourist-oriented, scams possible.", True),
    "cancun": ("Cancún", "mexico", -8, "Mexican resort city. Population 900K. Resort zone safe, caution elsewhere.", True),
    "marrakech": ("Marrakech", "morocco", -3, "Major Moroccan city. Population 1M. Vibrant souks, persistent vendors.", True),
    "cairo": ("Cairo", "egypt", -5, "Capital of Egypt. Population 10M. Busy, chaotic traffic, petty crime.", True),
    "rio-de-janeiro": ("Rio de Janeiro", "brazil", -10, "Major Brazilian city. Population 6.7M. Beautiful but higher crime in favelas.", True),
    "buenos-aires": ("Buenos Aires", "argentina", -5, "Capital of Argentina. Population 3M. Petty theft in tourist areas.", True),
    "mexico-city": ("Mexico City", "mexico", -5, "Capital of Mexico. Population 9.2M. Rich culture, varies by neighborhood.", True),
    "hanoi": ("Hanoi", "vietnam", 0, "Capital of Vietnam. Population 8.4M. Low violent crime, traffic chaotic.", True),
    "ho-chi-minh-city": ("Ho Chi Minh City", "vietnam", -2, "Largest Vietnamese city. Population 9M. Bag snatching common.", True),
    "kuala-lumpur": ("Kuala Lumpur", "malaysia", 0, "Capital of Malaysia. Population 1.8M. Modern and generally safe.", True),
    "mumbai": ("Mumbai", "india", -5, "Largest Indian city. Population 20.7M. Crowded, petty crime common.", True),
    "delhi": ("Delhi", "india", -8, "Capital of India. Population 32M metro. Higher crime rates, air pollution.", True),
    "moscow": ("Moscow", "russia", -3, "Capital of Russia. Population 12.6M. Generally safe for tourists.", True),
    "nairobi": ("Nairobi", "kenya", -5, "Capital of Kenya. Population 4.4M. Avoid certain areas at night.", True),
    "cape-town": ("Cape Town", "south-africa", -5, "Major South African city. Population 4.6M. Beautiful but high crime.", True),
    "bogota": ("Bogotá", "colombia", -5, "Capital of Colombia. Population 7.4M. Improving safety, still caution needed.", True),
    "lima": ("Lima", "peru", -3, "Capital of Peru. Population 10.7M. Petty theft in tourist areas.", True),
    "santiago": ("Santiago", "chile", 0, "Capital of Chile. Population 6.2M. Relatively safe by SA standards.", True),
    "athens": ("Athens", "greece", -2, "Capital of Greece. Population 660K. Safe, watch for pickpockets.", True),
    "budapest": ("Budapest", "hungary", -2, "Capital of Hungary. Population 1.7M. Safe, tourist scams exist.", True),
    "warsaw": ("Warsaw", "poland", 0, "Capital of Poland. Population 1.8M. Safe and modern.", True),
    "stockholm": ("Stockholm", "sweden", 0, "Capital of Sweden. Population 1M. Very safe.", True),
    "oslo": ("Oslo", "norway", 0, "Capital of Norway. Population 700K. Very safe but expensive.", True),
    "helsinki": ("Helsinki", "finland", 0, "Capital of Finland. Population 650K. Very safe.", True),
    "reykjavik": ("Reykjavík", "iceland", 0, "Capital of Iceland. Population 130K. Extremely safe.", True),
    "zurich": ("Zurich", "switzerland", +2, "Largest Swiss city. Population 420K. Extremely safe and clean.", True),
    "geneva": ("Geneva", "switzerland", +2, "Swiss city. Population 200K. Very safe, international hub.", True),
    "milan": ("Milan", "italy", -2, "Major Italian city. Population 1.4M. Fashion capital, pickpockets near Duomo.", True),
    "florence": ("Florence", "italy", -1, "Tuscan city. Population 380K. Tourist-heavy, petty theft.", True),
    "venice": ("Venice", "italy", 0, "Unique canal city. Population 260K. Very safe, expensive.", True),
    "munich": ("Munich", "germany", +2, "Bavarian capital. Population 1.5M. Very safe, Oktoberfest city.", True),
    "dublin": ("Dublin", "ireland", 0, "Capital of Ireland. Population 1.4M. Generally safe.", True),
    "edinburgh": ("Edinburgh", "united-kingdom", +2, "Scottish capital. Population 540K. Very safe, beautiful.", True),
    "melbourne": ("Melbourne", "australia", 0, "Australian city. Population 5M. Very safe and livable.", True),
    "auckland": ("Auckland", "new-zealand", 0, "Largest NZ city. Population 1.7M. Very safe.", True),
    "doha": ("Doha", "qatar", +3, "Capital of Qatar. Population 2.4M. Very low crime.", True),
    "tel-aviv": ("Tel Aviv", "israel", -5, "Israeli city. Population 450K. Vibrant but regional tensions.", True),
    "havana": ("Havana", "cuba", 0, "Capital of Cuba. Population 2.1M. Low violent crime, petty theft.", True),
    "cartagena": ("Cartagena", "colombia", +3, "Colombian coastal city. Population 1M. Safer than other Colombian cities.", True),
    "medellin": ("Medellín", "colombia", 0, "Colombian city. Population 2.5M. Transformed, still some areas to avoid.", True),
    # ── Additional top tourist cities ──────────────────────────────────────
    "san-francisco": ("San Francisco", "united-states", -3, "US city. Population 870K. Tech hub, homelessness issues downtown.", True),
    "los-angeles": ("Los Angeles", "united-states", -5, "US city. Population 3.9M. Sprawling, safe in tourist areas.", True),
    "chicago": ("Chicago", "united-states", -8, "US city. Population 2.7M. Great architecture, higher crime in some areas.", True),
    "miami": ("Miami", "united-states", -3, "US city. Population 440K. Beach city, vibrant nightlife.", True),
    "las-vegas": ("Las Vegas", "united-states", -5, "US city. Population 650K. Tourist-oriented, stay on the Strip.", True),
    "washington-dc": ("Washington DC", "united-states", -2, "US capital. Population 690K. Safe in tourist areas, monuments.", True),
    "boston": ("Boston", "united-states", 0, "US city. Population 690K. Historic, safe, walkable.", True),
    "honolulu": ("Honolulu", "united-states", +2, "US city. Population 350K. Hawaiian paradise, very safe.", True),
    "toronto": ("Toronto", "canada", 0, "Largest Canadian city. Population 2.8M. Multicultural and safe.", True),
    "vancouver": ("Vancouver", "canada", 0, "Canadian city. Population 680K. Beautiful, safe, mild climate.", True),
    "montreal": ("Montreal", "canada", 0, "Canadian city. Population 1.8M. French-speaking, vibrant culture.", True),
    "nice": ("Nice", "france", -2, "French Riviera city. Population 350K. Beautiful coast, petty theft.", True),
    "lyon": ("Lyon", "france", 0, "French city. Population 520K. Culinary capital, safe.", True),
    "marseille": ("Marseille", "france", -5, "French port city. Population 870K. Rougher than other French cities.", True),
    "seville": ("Seville", "spain", -2, "Spanish city. Population 690K. Beautiful, petty theft possible.", True),
    "madrid": ("Madrid", "spain", -2, "Capital of Spain. Population 3.3M. Generally safe, watch for pickpockets.", True),
    "malaga": ("Málaga", "spain", -1, "Spanish coastal city. Population 580K. Safe resort destination.", True),
    "porto": ("Porto", "portugal", 0, "Portuguese city. Population 240K. Safe, great wine region.", True),
    "naples": ("Naples", "italy", -5, "Italian city. Population 920K. Chaotic but authentic, higher crime.", True),
    "krakow": ("Kraków", "poland", 0, "Polish city. Population 780K. Safe, historic, popular with tourists.", True),
    "dubrovnik": ("Dubrovnik", "croatia", +2, "Croatian coastal city. Population 40K. Very safe, Game of Thrones filming.", True),
    "split": ("Split", "croatia", 0, "Croatian coastal city. Population 180K. Safe, Roman ruins.", True),
    "bruges": ("Bruges", "belgium", +2, "Belgian city. Population 120K. Very safe, medieval charm.", True),
    "brussels": ("Brussels", "belgium", -2, "Capital of Belgium. Population 1.2M. EU capital, some rough areas.", True),
    "salzburg": ("Salzburg", "austria", +2, "Austrian city. Population 155K. Very safe, Sound of Music city.", True),
    "santorini": ("Santorini", "greece", +3, "Greek island. Population 15K. Very safe, iconic sunsets.", True),
    "mykonos": ("Mykonos", "greece", +2, "Greek island. Population 10K. Safe party island.", True),
    "crete": ("Crete", "greece", +2, "Greek island. Population 620K. Safe, beautiful beaches.", True),
    "rhodes": ("Rhodes", "greece", +1, "Greek island. Population 120K. Safe, medieval old town.", True),
    "edinburgh": ("Edinburgh", "united-kingdom", +2, "Scottish capital. Very safe, beautiful architecture.", True),
    "bath": ("Bath", "united-kingdom", +3, "English city. Population 90K. Very safe, Roman baths.", True),
    "oxford": ("Oxford", "united-kingdom", +2, "English city. Population 150K. Safe, prestigious university.", True),
    "cambridge": ("Cambridge", "united-kingdom", +2, "English city. Population 145K. Very safe, university town.", True),
    "manchester": ("Manchester", "united-kingdom", -2, "English city. Population 550K. Vibrant, some rougher areas.", True),
    "lucerne": ("Lucerne", "switzerland", +3, "Swiss city. Population 82K. Extremely safe, beautiful lakeside.", True),
    "interlaken": ("Interlaken", "switzerland", +3, "Swiss town. Population 6K. Extremely safe, adventure sports hub.", True),
    "hamburg": ("Hamburg", "germany", 0, "German city. Population 1.9M. Safe, major port city.", True),
    "frankfurt": ("Frankfurt", "germany", -2, "German city. Population 760K. Financial hub, some areas less safe at night.", True),
    "dresden": ("Dresden", "germany", 0, "German city. Population 560K. Safe, baroque architecture.", True),
    "tallinn": ("Tallinn", "estonia", 0, "Capital of Estonia. Population 450K. Safe, medieval old town.", True),
    "riga": ("Riga", "latvia", -2, "Capital of Latvia. Population 615K. Historic, generally safe.", True),
    "vilnius": ("Vilnius", "lithuania", 0, "Capital of Lithuania. Population 590K. Safe, baroque old town.", True),
    "bratislava": ("Bratislava", "slovakia", -2, "Capital of Slovakia. Population 440K. Safe, compact old town.", True),
    "ljubljana": ("Ljubljana", "slovenia", +2, "Capital of Slovenia. Population 290K. Very safe, green city.", True),
    "zagreb": ("Zagreb", "croatia", 0, "Capital of Croatia. Population 800K. Safe, pleasant capital.", True),
    "bucharest": ("Bucharest", "romania", -3, "Capital of Romania. Population 1.8M. Improving, stray dogs issue.", True),
    "sofia": ("Sofia", "bulgaria", -3, "Capital of Bulgaria. Population 1.3M. Affordable, some petty crime.", True),
    "belgrade": ("Belgrade", "serbia", -2, "Capital of Serbia. Population 1.7M. Vibrant nightlife, generally safe.", True),
    "tbilisi": ("Tbilisi", "georgia", 0, "Capital of Georgia. Population 1.1M. Very safe, rising tourist destination.", True),
    "batumi": ("Batumi", "georgia", +2, "Georgian Black Sea resort. Population 170K. Safe, modern resort city.", True),
    "petra": ("Petra", "jordan", +2, "Ancient Jordanian city. Major tourist site, very safe for visitors.", True),
    "amman": ("Amman", "jordan", 0, "Capital of Jordan. Population 4.4M. Safe, friendly locals.", True),
    "muscat": ("Muscat", "oman", +3, "Capital of Oman. Population 1.5M. Very safe, hospitable culture.", True),
    "jaipur": ("Jaipur", "india", -3, "Indian city. Population 3.1M. Pink City, tourist-friendly.", True),
    "goa": ("Goa", "india", 0, "Indian state. Population 1.5M. Beach destination, relatively safe.", True),
    "agra": ("Agra", "india", -5, "Indian city. Population 1.6M. Taj Mahal city, touts and scams.", True),
    "varanasi": ("Varanasi", "india", -5, "Indian city. Population 1.2M. Sacred city on the Ganges, chaotic.", True),
    "chiang-mai": ("Chiang Mai", "thailand", +2, "Thai city. Population 130K. Very safe, digital nomad hub.", True),
    "siem-reap": ("Siem Reap", "cambodia", 0, "Cambodian city. Population 250K. Gateway to Angkor Wat, safe.", True),
    "luang-prabang": ("Luang Prabang", "laos", +2, "Laotian town. Population 55K. UNESCO site, very safe.", True),
    "yangon": ("Yangon", "myanmar", -3, "Largest Myanmar city. Population 5.3M. Political instability.", True),
    "kathmandu": ("Kathmandu", "nepal", -2, "Capital of Nepal. Population 1.4M. Safe, chaotic traffic.", True),
    "colombo": ("Colombo", "sri-lanka", -2, "Capital of Sri Lanka. Population 750K. Improving safety, friendly.", True),
    "male": ("Malé", "maldives", +5, "Capital of Maldives. Population 250K. Very safe island capital.", True),
    "zanzibar": ("Zanzibar", "tanzania", 0, "Tanzanian island. Population 1.3M. Safe resort island.", True),
    "marrakech": ("Marrakech", "morocco", -3, "Moroccan city. Vibrant souks, persistent vendors.", True),
    "fez": ("Fez", "morocco", -2, "Moroccan city. Population 1.2M. Ancient medina, fewer tourists.", True),
    "casablanca": ("Casablanca", "morocco", -3, "Largest Moroccan city. Population 3.7M. Urban, some petty crime.", True),
    "accra": ("Accra", "ghana", -2, "Capital of Ghana. Population 2.5M. Relatively safe in West Africa.", True),
    "dakar": ("Dakar", "senegal", -2, "Capital of Senegal. Population 1.1M. Vibrant, relatively safe.", True),
    "addis-ababa": ("Addis Ababa", "ethiopia", -3, "Capital of Ethiopia. Population 5.2M. Generally safe, petty crime.", True),
    "victoria-falls": ("Victoria Falls", "zimbabwe", +5, "Zimbabwean town. Population 35K. Tourist town, very safe.", True),
    "livingstone": ("Livingstone", "zambia", +3, "Zambian town. Population 180K. Tourist town near Victoria Falls.", True),
    "windhoek": ("Windhoek", "namibia", 0, "Capital of Namibia. Population 430K. Relatively safe.", True),
    "cusco": ("Cusco", "peru", +2, "Peruvian city. Population 430K. Gateway to Machu Picchu, safe.", True),
    "quito": ("Quito", "ecuador", -3, "Capital of Ecuador. Population 2.8M. Historic, watch belongings.", True),
    "la-paz": ("La Paz", "bolivia", -3, "Seat of government, Bolivia. Population 900K. Altitude sickness, safe.", True),
    "montevideo": ("Montevideo", "uruguay", 0, "Capital of Uruguay. Population 1.4M. Safe by South American standards.", True),
    "panama-city": ("Panama City", "panama", -3, "Capital of Panama. Population 880K. Modern, some areas unsafe.", True),
    "san-jose-costa-rica": ("San José", "costa-rica", -2, "Capital of Costa Rica. Population 350K. Petty theft common.", True),
    "antigua-guatemala": ("Antigua Guatemala", "guatemala", +3, "Guatemalan town. Population 45K. Safe tourist town, colonial.", True),
    "playa-del-carmen": ("Playa del Carmen", "mexico", -5, "Mexican resort town. Population 300K. Tourist zone safe.", True),
    "tulum": ("Tulum", "mexico", -3, "Mexican beach town. Population 35K. Boho-chic, relatively safe.", True),
    "oaxaca": ("Oaxaca", "mexico", -2, "Mexican city. Population 260K. Safe, great food and culture.", True),
    "san-miguel-de-allende": ("San Miguel de Allende", "mexico", +3, "Mexican colonial town. Population 170K. Very safe, expat haven.", True),
    "puerto-vallarta": ("Puerto Vallarta", "mexico", -2, "Mexican resort city. Population 290K. Safe tourist area.", True),
    "queenstown": ("Queenstown", "new-zealand", +3, "NZ adventure town. Population 16K. Very safe, adventure capital.", True),
    "wellington": ("Wellington", "new-zealand", 0, "Capital of New Zealand. Population 215K. Very safe, windy.", True),
    "fiji-nadi": ("Nadi", "fiji", 0, "Fijian town. Population 70K. Gateway to Fiji resorts, safe.", True),
    "maui": ("Maui", "united-states", +3, "Hawaiian island. Population 160K. Very safe, beautiful beaches.", True),
    "key-west": ("Key West", "united-states", +2, "Florida Keys city. Population 25K. Safe, laid-back island life.", True),
    "savannah": ("Savannah", "united-states", 0, "US city. Population 150K. Charming southern city, generally safe.", True),
    "charleston": ("Charleston", "united-states", 0, "US city. Population 150K. Historic, safe, great food.", True),
    "sedona": ("Sedona", "united-states", +3, "US town. Population 10K. Very safe, red rock scenery.", True),
    "aspen": ("Aspen", "united-states", +5, "US ski town. Population 7K. Very safe, wealthy resort.", True),
    "st-petersburg-russia": ("Saint Petersburg", "russia", -2, "Russian city. Population 5.4M. Beautiful, generally safe for tourists.", True),
    "st-petersburg-florida": ("St. Petersburg", "united-states", 0, "US city, Florida. Population 260K. Safe beach city.", True),
    "nice": ("Nice", "france", -2, "French Riviera city. Beautiful coast, petty theft.", True),
    "bruges": ("Bruges", "belgium", +2, "Medieval Belgian city. Very safe.", True),
    "cinque-terre": ("Cinque Terre", "italy", +2, "Italian coastal villages. Very safe, beautiful hiking.", True),
    "amalfi": ("Amalfi", "italy", +2, "Italian coastal town. Population 5K. Very safe, stunning coast.", True),
    "sorrento": ("Sorrento", "italy", +2, "Italian coastal town. Population 16K. Safe, beautiful views.", True),
    "positano": ("Positano", "italy", +3, "Italian cliffside village. Population 4K. Very safe, glamorous.", True),
    "taormina": ("Taormina", "italy", +2, "Sicilian town. Population 11K. Safe, beautiful Greek theatre.", True),
    "hallstatt": ("Hallstatt", "austria", +3, "Austrian lakeside village. Population 750. Extremely safe, iconic.", True),
    "bergen": ("Bergen", "norway", +2, "Norwegian city. Population 285K. Very safe, fjord gateway.", True),
    "tromso": ("Tromsø", "norway", +2, "Norwegian city. Population 77K. Very safe, northern lights.", True),
    "rovaniemi": ("Rovaniemi", "finland", +2, "Finnish city. Population 64K. Very safe, Santa Claus village.", True),
    "lapland": ("Lapland", "finland", +3, "Finnish region. Very safe, northern lights and reindeer.", True),
    "gothenburg": ("Gothenburg", "sweden", 0, "Swedish city. Population 580K. Safe, friendly.", True),
    "malmo": ("Malmö", "sweden", -3, "Swedish city. Population 350K. Some suburban crime issues.", True),
    "nara": ("Nara", "japan", +3, "Japanese city. Population 360K. Very safe, friendly deer.", True),
    "hiroshima": ("Hiroshima", "japan", +2, "Japanese city. Population 1.2M. Very safe, peace memorial.", True),
    "fukuoka": ("Fukuoka", "japan", +1, "Japanese city. Population 1.6M. Safe, great food scene.", True),
    "sapporo": ("Sapporo", "japan", +1, "Japanese city. Population 2M. Safe, winter sports and beer.", True),
    "busan": ("Busan", "south-korea", 0, "South Korean city. Population 3.4M. Safe, great seafood.", True),
    "jeju": ("Jeju", "south-korea", +2, "South Korean island. Population 680K. Very safe, volcanic island.", True),
    "penang": ("Penang", "malaysia", 0, "Malaysian island. Population 1.8M. Safe, great street food.", True),
    "langkawi": ("Langkawi", "malaysia", +2, "Malaysian island. Population 100K. Safe resort island.", True),
    "ubud": ("Ubud", "indonesia", +3, "Balinese town. Cultural center, safe for tourists.", True),
    "yogyakarta": ("Yogyakarta", "indonesia", 0, "Indonesian city. Population 420K. Cultural center, safe.", True),
    "manila": ("Manila", "philippines", -8, "Capital of Philippines. Population 1.8M. Crowded, higher crime.", True),
    "cebu": ("Cebu", "philippines", -3, "Philippine city. Population 960K. Resort gateway, moderate safety.", True),
    "boracay": ("Boracay", "philippines", +2, "Philippine island. Population 40K. Safe resort island.", True),
    "phnom-penh": ("Phnom Penh", "cambodia", -5, "Capital of Cambodia. Population 2.3M. Improving but petty crime.", True),
    "vientiane": ("Vientiane", "laos", -2, "Capital of Laos. Population 950K. Sleepy capital, safe.", True),
}

# ─── CAPITALS ────────────────────────────────────────────────────────────────
# country_slug -> (capital_name, capital_slug)
CAPITALS = {
    "afghanistan": ("Kabul", "kabul"),
    "albania": ("Tirana", "tirana"),
    "algeria": ("Algiers", "algiers"),
    "andorra": ("Andorra la Vella", "andorra-la-vella"),
    "angola": ("Luanda", "luanda"),
    "antigua-and-barbuda": ("St. John's", "st-johns-antigua"),
    "argentina": ("Buenos Aires", "buenos-aires"),
    "armenia": ("Yerevan", "yerevan"),
    "australia": ("Canberra", "canberra"),
    "austria": ("Vienna", "vienna"),
    "azerbaijan": ("Baku", "baku"),
    "bahamas": ("Nassau", "nassau"),
    "bahrain": ("Manama", "manama"),
    "bangladesh": ("Dhaka", "dhaka"),
    "barbados": ("Bridgetown", "bridgetown"),
    "belarus": ("Minsk", "minsk"),
    "belgium": ("Brussels", "brussels"),
    "belize": ("Belmopan", "belmopan"),
    "benin": ("Porto-Novo", "porto-novo"),
    "bhutan": ("Thimphu", "thimphu"),
    "bolivia": ("La Paz", "la-paz"),
    "bosnia-and-herzegovina": ("Sarajevo", "sarajevo"),
    "botswana": ("Gaborone", "gaborone"),
    "brazil": ("Brasília", "brasilia"),
    "brunei": ("Bandar Seri Begawan", "bandar-seri-begawan"),
    "bulgaria": ("Sofia", "sofia"),
    "burkina-faso": ("Ouagadougou", "ouagadougou"),
    "burundi": ("Gitega", "gitega"),
    "cambodia": ("Phnom Penh", "phnom-penh"),
    "cameroon": ("Yaoundé", "yaounde"),
    "canada": ("Ottawa", "ottawa"),
    "cape-verde": ("Praia", "praia"),
    "central-african-republic": ("Bangui", "bangui"),
    "chad": ("N'Djamena", "ndjamena"),
    "chile": ("Santiago", "santiago"),
    "china": ("Beijing", "beijing"),
    "colombia": ("Bogotá", "bogota"),
    "comoros": ("Moroni", "moroni"),
    "congo": ("Brazzaville", "brazzaville"),
    "congo-drc": ("Kinshasa", "kinshasa"),
    "costa-rica": ("San José", "san-jose-costa-rica"),
    "croatia": ("Zagreb", "zagreb"),
    "cuba": ("Havana", "havana"),
    "cyprus": ("Nicosia", "nicosia"),
    "czech-republic": ("Prague", "prague"),
    "denmark": ("Copenhagen", "copenhagen"),
    "djibouti": ("Djibouti", "djibouti-city"),
    "dominica": ("Roseau", "roseau"),
    "dominican-republic": ("Santo Domingo", "santo-domingo"),
    "east-timor": ("Dili", "dili"),
    "ecuador": ("Quito", "quito"),
    "egypt": ("Cairo", "cairo"),
    "el-salvador": ("San Salvador", "san-salvador"),
    "equatorial-guinea": ("Malabo", "malabo"),
    "eritrea": ("Asmara", "asmara"),
    "estonia": ("Tallinn", "tallinn"),
    "eswatini": ("Mbabane", "mbabane"),
    "ethiopia": ("Addis Ababa", "addis-ababa"),
    "fiji": ("Suva", "suva"),
    "finland": ("Helsinki", "helsinki"),
    "france": ("Paris", "paris"),
    "gabon": ("Libreville", "libreville"),
    "gambia": ("Banjul", "banjul"),
    "georgia": ("Tbilisi", "tbilisi"),
    "germany": ("Berlin", "berlin"),
    "ghana": ("Accra", "accra"),
    "greece": ("Athens", "athens"),
    "grenada": ("St. George's", "st-georges-grenada"),
    "guatemala": ("Guatemala City", "guatemala-city"),
    "guinea": ("Conakry", "conakry"),
    "guinea-bissau": ("Bissau", "bissau"),
    "guyana": ("Georgetown", "georgetown-guyana"),
    "haiti": ("Port-au-Prince", "port-au-prince"),
    "honduras": ("Tegucigalpa", "tegucigalpa"),
    "hungary": ("Budapest", "budapest"),
    "iceland": ("Reykjavík", "reykjavik"),
    "india": ("New Delhi", "new-delhi"),
    "indonesia": ("Jakarta", "jakarta"),
    "iran": ("Tehran", "tehran"),
    "iraq": ("Baghdad", "baghdad"),
    "ireland": ("Dublin", "dublin"),
    "israel": ("Jerusalem", "jerusalem"),
    "italy": ("Rome", "rome"),
    "ivory-coast": ("Yamoussoukro", "yamoussoukro"),
    "jamaica": ("Kingston", "kingston-jamaica"),
    "japan": ("Tokyo", "tokyo"),
    "jordan": ("Amman", "amman"),
    "kazakhstan": ("Astana", "astana"),
    "kenya": ("Nairobi", "nairobi"),
    "kiribati": ("Tarawa", "tarawa"),
    "kuwait": ("Kuwait City", "kuwait-city"),
    "kyrgyzstan": ("Bishkek", "bishkek"),
    "laos": ("Vientiane", "vientiane"),
    "latvia": ("Riga", "riga"),
    "lebanon": ("Beirut", "beirut"),
    "lesotho": ("Maseru", "maseru"),
    "liberia": ("Monrovia", "monrovia"),
    "libya": ("Tripoli", "tripoli"),
    "liechtenstein": ("Vaduz", "vaduz"),
    "lithuania": ("Vilnius", "vilnius"),
    "luxembourg": ("Luxembourg City", "luxembourg-city"),
    "madagascar": ("Antananarivo", "antananarivo"),
    "malawi": ("Lilongwe", "lilongwe"),
    "malaysia": ("Kuala Lumpur", "kuala-lumpur"),
    "maldives": ("Malé", "male"),
    "mali": ("Bamako", "bamako"),
    "malta": ("Valletta", "valletta"),
    "marshall-islands": ("Majuro", "majuro"),
    "mauritania": ("Nouakchott", "nouakchott"),
    "mauritius": ("Port Louis", "port-louis"),
    "mexico": ("Mexico City", "mexico-city"),
    "micronesia": ("Palikir", "palikir"),
    "moldova": ("Chișinău", "chisinau"),
    "monaco": ("Monaco", "monaco-city"),
    "mongolia": ("Ulaanbaatar", "ulaanbaatar"),
    "montenegro": ("Podgorica", "podgorica"),
    "morocco": ("Rabat", "rabat"),
    "mozambique": ("Maputo", "maputo"),
    "myanmar": ("Naypyidaw", "naypyidaw"),
    "namibia": ("Windhoek", "windhoek"),
    "nauru": ("Yaren", "yaren"),
    "nepal": ("Kathmandu", "kathmandu"),
    "netherlands": ("Amsterdam", "amsterdam"),
    "new-zealand": ("Wellington", "wellington"),
    "nicaragua": ("Managua", "managua"),
    "niger": ("Niamey", "niamey"),
    "nigeria": ("Abuja", "abuja"),
    "north-korea": ("Pyongyang", "pyongyang"),
    "north-macedonia": ("Skopje", "skopje"),
    "norway": ("Oslo", "oslo"),
    "oman": ("Muscat", "muscat"),
    "pakistan": ("Islamabad", "islamabad"),
    "palau": ("Ngerulmud", "ngerulmud"),
    "panama": ("Panama City", "panama-city"),
    "papua-new-guinea": ("Port Moresby", "port-moresby"),
    "paraguay": ("Asunción", "asuncion"),
    "peru": ("Lima", "lima"),
    "philippines": ("Manila", "manila"),
    "poland": ("Warsaw", "warsaw"),
    "portugal": ("Lisbon", "lisbon"),
    "qatar": ("Doha", "doha"),
    "romania": ("Bucharest", "bucharest"),
    "russia": ("Moscow", "moscow"),
    "rwanda": ("Kigali", "kigali"),
    "saint-kitts-and-nevis": ("Basseterre", "basseterre"),
    "saint-lucia": ("Castries", "castries"),
    "saint-vincent": ("Kingstown", "kingstown"),
    "samoa": ("Apia", "apia"),
    "san-marino": ("San Marino", "san-marino-city"),
    "sao-tome-and-principe": ("São Tomé", "sao-tome"),
    "saudi-arabia": ("Riyadh", "riyadh"),
    "senegal": ("Dakar", "dakar"),
    "serbia": ("Belgrade", "belgrade"),
    "seychelles": ("Victoria", "victoria-seychelles"),
    "sierra-leone": ("Freetown", "freetown"),
    "singapore": ("Singapore City", "singapore-city"),
    "slovakia": ("Bratislava", "bratislava"),
    "slovenia": ("Ljubljana", "ljubljana"),
    "solomon-islands": ("Honiara", "honiara"),
    "somalia": ("Mogadishu", "mogadishu"),
    "south-africa": ("Pretoria", "pretoria"),
    "south-korea": ("Seoul", "seoul"),
    "south-sudan": ("Juba", "juba"),
    "spain": ("Madrid", "madrid"),
    "sri-lanka": ("Colombo", "colombo"),
    "sudan": ("Khartoum", "khartoum"),
    "suriname": ("Paramaribo", "paramaribo"),
    "sweden": ("Stockholm", "stockholm"),
    "switzerland": ("Bern", "bern"),
    "syria": ("Damascus", "damascus"),
    "taiwan": ("Taipei", "taipei"),
    "tajikistan": ("Dushanbe", "dushanbe"),
    "tanzania": ("Dodoma", "dodoma"),
    "thailand": ("Bangkok", "bangkok"),
    "togo": ("Lomé", "lome"),
    "tonga": ("Nukuʻalofa", "nukualofa"),
    "trinidad-and-tobago": ("Port of Spain", "port-of-spain"),
    "tunisia": ("Tunis", "tunis"),
    "turkey": ("Ankara", "ankara"),
    "turkmenistan": ("Ashgabat", "ashgabat"),
    "tuvalu": ("Funafuti", "funafuti"),
    "uganda": ("Kampala", "kampala"),
    "ukraine": ("Kyiv", "kyiv"),
    "united-arab-emirates": ("Abu Dhabi", "abu-dhabi"),
    "united-kingdom": ("London", "london"),
    "united-states": ("Washington DC", "washington-dc"),
    "uruguay": ("Montevideo", "montevideo"),
    "uzbekistan": ("Tashkent", "tashkent"),
    "vanuatu": ("Port Vila", "port-vila"),
    "vatican": ("Vatican City", "vatican-city"),
    "venezuela": ("Caracas", "caracas"),
    "vietnam": ("Hanoi", "hanoi"),
    "yemen": ("Sana'a", "sanaa"),
    "zambia": ("Lusaka", "lusaka"),
    "zimbabwe": ("Harare", "harare"),
}

# ─── SECONDARY CITIES ────────────────────────────────────────────────────────
# country_slug -> list of city names
SECONDARY_CITIES = {
    "united-states": [
        "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia",
        "San Antonio", "San Diego", "Dallas", "San Jose", "Austin",
        "Jacksonville", "Fort Worth", "Columbus", "Charlotte", "Indianapolis",
        "San Francisco", "Seattle", "Denver", "Nashville", "Oklahoma City",
        "Las Vegas", "Portland", "Memphis", "Louisville", "Baltimore",
        "Milwaukee", "Albuquerque", "Tucson", "Fresno", "Sacramento",
        "Mesa", "Kansas City", "Atlanta", "Omaha", "Colorado Springs",
        "Raleigh", "Long Beach", "Virginia Beach", "Miami", "Oakland",
        "Minneapolis", "Tampa", "Tulsa", "Arlington", "New Orleans",
        "Honolulu", "Boston", "Anchorage", "Pittsburgh", "Cincinnati",
        "St. Louis", "Orlando", "Buffalo", "Salt Lake City", "Scottsdale",
        "Boise", "Richmond", "Des Moines", "Spokane", "El Paso",
        "Corpus Christi", "Lexington", "Bakersfield", "Durham", "Chandler",
        "Irvine", "Santa Ana", "Riverside", "Stockton", "Laredo",
        "Gilbert", "Madison", "Norfolk", "Chesapeake", "Hialeah",
        "Tallahassee", "Palm Springs", "Santa Barbara", "Palm Beach", "Fort Lauderdale",
        "Sarasota", "Naples Florida", "Pensacola", "Daytona Beach", "Key Largo",
        "Park City", "Jackson Hole", "Sun Valley", "Vail", "Telluride",
        "Steamboat Springs", "Lake Tahoe", "Napa Valley", "Sonoma", "Carmel",
        "Monterey", "Santa Cruz", "Big Sur", "Malibu", "Laguna Beach",
        "Coronado", "La Jolla", "Galveston", "South Padre Island", "Myrtle Beach",
        "Hilton Head", "Kiawah Island", "Outer Banks", "Cape Cod", "Martha's Vineyard",
        "Nantucket", "Bar Harbor", "Kennebunkport", "Newport Rhode Island", "Annapolis",
        "Williamsburg", "Asheville", "Gatlinburg", "Branson", "Hot Springs",
        "Sedona", "Scottsdale", "Flagstaff", "Moab", "Santa Fe",
        "Taos", "Durango", "Bend Oregon", "Cannon Beach", "Leavenworth",
        "Whitefish Montana", "Missoula", "Rapid City", "Deadwood", "Grand Junction",
        "Chattanooga", "Knoxville", "Greenville", "Athens Georgia", "Wilmington",
        "Rehoboth Beach", "Ocean City Maryland", "Cape May", "Traverse City", "Mackinac Island",
        "Door County", "Duluth", "Fargo", "Sioux Falls", "Lincoln",
        "Wichita", "Little Rock", "Jackson Mississippi", "Birmingham Alabama", "Mobile",
        "Shreveport", "Baton Rouge", "Lafayette Louisiana", "Beaumont", "Amarillo",
        "Lubbock", "Midland", "Abilene", "Waco", "Tyler",
        "Springfield Missouri", "Columbia Missouri", "Cedar Rapids", "Iowa City", "Davenport",
        "Peoria", "Rockford", "Green Bay", "Appleton", "Eau Claire",
        "Rochester Minnesota", "Bloomington", "Grand Rapids", "Ann Arbor", "Lansing",
        "Kalamazoo", "Flint", "South Bend", "Fort Wayne", "Evansville",
        "Akron", "Toledo", "Dayton", "Youngstown", "Canton",
        "Harrisburg", "Scranton", "Allentown", "Erie", "State College",
        "Rochester New York", "Syracuse", "Albany", "Ithaca", "Saratoga Springs",
        "Hartford", "New Haven", "Providence", "Burlington Vermont", "Portland Maine",
        "Manchester New Hampshire", "Concord New Hampshire", "Bangor", "Augusta Maine",
    ],
    "china": [
        "Shanghai", "Beijing", "Guangzhou", "Shenzhen", "Chengdu",
        "Wuhan", "Hangzhou", "Nanjing", "Chongqing", "Tianjin",
        "Xi'an", "Suzhou", "Harbin", "Dalian", "Qingdao",
        "Kunming", "Zhengzhou", "Changsha", "Fuzhou", "Xiamen",
        "Shenyang", "Jinan", "Guiyang", "Ürümqi", "Lhasa",
        "Hefei", "Nanchang", "Changchun", "Lanzhou", "Taiyuan",
        "Nanning", "Haikou", "Hohhot", "Yinchuan", "Xining",
        "Wenzhou", "Dongguan", "Foshan", "Ningbo", "Wuxi",
        "Zhuhai", "Guilin", "Lijiang", "Luoyang", "Kaifeng",
        "Macau", "Dali", "Yangshuo", "Zhangjiajie", "Chengde",
        "Dunhuang", "Turpan", "Kashgar", "Pingyao", "Datong",
        "Huangshan", "Emeishan", "Leshan", "Diqing", "Shangri-La",
        "Sanya", "Beihai", "Wuxi", "Yantai", "Weifang",
        "Zibo", "Jining", "Linyi", "Xuzhou", "Changzhou",
        "Nantong", "Yancheng", "Taizhou Jiangsu", "Yangzhou", "Zhenjiang",
        "Huai'an", "Lianyungang", "Quanzhou", "Putian", "Zhangzhou",
        "Shantou", "Jiangmen", "Zhongshan", "Huizhou", "Meizhou",
        "Baotou", "Ordos", "Wuhai", "Zunyi", "Qujing",
        "Yichang", "Xiangyang", "Jingzhou", "Huangshi", "Mianyang",
        "Deyang", "Nanchong", "Zigong", "Luzhou", "Yibin",
    ],
    "india": [
        "Mumbai", "Delhi", "Bangalore", "Hyderabad", "Ahmedabad",
        "Chennai", "Kolkata", "Pune", "Jaipur", "Lucknow",
        "Kanpur", "Nagpur", "Visakhapatnam", "Indore", "Thane",
        "Bhopal", "Patna", "Vadodara", "Ghaziabad", "Ludhiana",
        "Agra", "Nashik", "Faridabad", "Meerut", "Rajkot",
        "Varanasi", "Srinagar", "Aurangabad", "Dhanbad", "Amritsar",
        "Allahabad", "Ranchi", "Coimbatore", "Jabalpur", "Gwalior",
        "Vijayawada", "Jodhpur", "Madurai", "Raipur", "Kochi",
        "Chandigarh", "Mysore", "Tiruchirappalli", "Dehradun", "Shimla",
        "Goa", "Pondicherry", "Udaipur", "Darjeeling", "Rishikesh",
        "Manali", "Leh", "Ladakh", "McLeod Ganj", "Dharamshala",
        "Munnar", "Ooty", "Kodaikanal", "Hampi", "Gokarna",
        "Varkala", "Alleppey", "Trivandrum", "Mangalore", "Udupi",
        "Tirupati", "Warangal", "Nellore", "Guntur", "Rajahmundry",
        "Khajuraho", "Orchha", "Ujjain", "Sanchi", "Pachmarhi",
        "Gangtok", "Pelling", "Kalimpong", "Shillong", "Guwahati",
        "Tezpur", "Kaziranga", "Imphal", "Aizawl", "Kohima",
        "Jaisalmer", "Pushkar", "Mount Abu", "Bikaner", "Ajmer",
        "Mathura", "Haridwar", "Nainital", "Mussoorie", "Almora",
        "Jim Corbett", "Lakshadweep", "Andaman Islands", "Diu", "Daman",
    ],
    "brazil": [
        "São Paulo", "Rio de Janeiro", "Brasília", "Salvador", "Fortaleza",
        "Belo Horizonte", "Manaus", "Curitiba", "Recife", "Porto Alegre",
        "Belém", "Goiânia", "Guarulhos", "Campinas", "São Luís",
        "Maceió", "Natal", "Campo Grande", "Teresina", "João Pessoa",
        "Florianópolis", "Vitória", "Cuiabá", "Aracaju", "Uberlândia",
        "Ribeirão Preto", "Santos", "Niterói", "Foz do Iguaçu", "Búzios",
        "Paraty", "Ouro Preto", "Petrópolis", "Gramado", "Canela",
        "Bonito", "Lençóis", "Chapada Diamantina", "Jericoacoara", "Fernando de Noronha",
        "Ilhabela", "Ubatuba", "Angra dos Reis", "Arraial do Cabo", "Trancoso",
        "Porto Seguro", "Praia do Forte", "Olinda", "São José dos Campos", "Londrina",
        "Maringá", "Blumenau", "Joinville", "Caxias do Sul", "Pelotas",
        "Piracicaba", "Sorocaba", "Juiz de Fora", "Montes Claros", "Feira de Santana",
    ],
    "japan": [
        "Yokohama", "Nagoya", "Kobe", "Kawasaki", "Kitakyushu",
        "Sendai", "Chiba", "Sakai", "Niigata", "Hamamatsu",
        "Kumamoto", "Sagamihara", "Okayama", "Shizuoka", "Kagoshima",
        "Funabashi", "Hachioji", "Matsuyama", "Kanazawa", "Okinawa",
        "Nagasaki", "Takayama", "Hakone", "Kamakura", "Nikko",
        "Naoshima", "Onomichi", "Beppu", "Miyajima", "Yakushima",
        "Shirakawa-go", "Matsumoto", "Tsumago", "Magome", "Ise",
        "Koyasan", "Yoshino", "Aomori", "Akita", "Morioka",
        "Hakodate", "Otaru", "Furano", "Niseko", "Noboribetsu",
    ],
    "germany": [
        "Hamburg", "Munich", "Cologne", "Frankfurt", "Stuttgart",
        "Düsseldorf", "Leipzig", "Dortmund", "Essen", "Bremen",
        "Dresden", "Hanover", "Nuremberg", "Duisburg", "Bochum",
        "Wuppertal", "Bielefeld", "Bonn", "Mannheim", "Karlsruhe",
        "Augsburg", "Wiesbaden", "Heidelberg", "Freiburg", "Potsdam",
        "Rothenburg ob der Tauber", "Baden-Baden", "Bamberg", "Trier", "Lübeck",
    ],
    "united-kingdom": [
        "Birmingham", "Manchester", "Leeds", "Glasgow", "Liverpool",
        "Bristol", "Sheffield", "Newcastle", "Nottingham", "Leicester",
        "Coventry", "Belfast", "Cardiff", "Brighton", "Plymouth",
        "Southampton", "Reading", "Aberdeen", "Derby", "York",
        "Canterbury", "Bath", "Oxford", "Cambridge", "Stratford-upon-Avon",
        "Inverness", "Swansea", "Exeter", "Norwich", "Chester",
    ],
    "france": [
        "Lyon", "Marseille", "Toulouse", "Nice", "Nantes",
        "Strasbourg", "Montpellier", "Bordeaux", "Lille", "Rennes",
        "Reims", "Saint-Étienne", "Toulon", "Le Havre", "Grenoble",
        "Dijon", "Angers", "Nîmes", "Aix-en-Provence", "Cannes",
        "Avignon", "Tours", "Rouen", "Perpignan", "Clermont-Ferrand",
        "Biarritz", "Chamonix", "Colmar", "Carcassonne", "La Rochelle",
    ],
    "italy": [
        "Milan", "Naples", "Turin", "Palermo", "Genoa",
        "Bologna", "Florence", "Catania", "Bari", "Verona",
        "Venice", "Messina", "Padua", "Trieste", "Brescia",
        "Parma", "Modena", "Perugia", "Cagliari", "Siena",
        "Pisa", "Bergamo", "Ravenna", "Lecce", "Como",
        "Sorrento", "Amalfi", "Positano", "Taormina", "Cinque Terre",
    ],
    "spain": [
        "Barcelona", "Valencia", "Seville", "Zaragoza", "Málaga",
        "Murcia", "Palma de Mallorca", "Las Palmas", "Bilbao", "Alicante",
        "Córdoba", "Valladolid", "Vigo", "Gijón", "Granada",
        "A Coruña", "Vitoria-Gasteiz", "Santa Cruz de Tenerife", "Pamplona", "Santander",
        "San Sebastián", "Toledo", "Salamanca", "Ibiza", "Marbella",
        "Cádiz", "Segovia", "Tarragona", "Girona", "Ronda",
    ],
    "russia": [
        "Saint Petersburg", "Novosibirsk", "Yekaterinburg", "Kazan", "Nizhny Novgorod",
        "Chelyabinsk", "Samara", "Omsk", "Rostov-on-Don", "Ufa",
        "Krasnoyarsk", "Voronezh", "Perm", "Volgograd", "Krasnodar",
        "Irkutsk", "Vladivostok", "Murmansk", "Sochi", "Kaliningrad",
        "Saratov", "Tyumen", "Barnaul", "Togliatti", "Izhevsk",
        "Ulyanovsk", "Khabarovsk", "Yaroslavl", "Vladikavkaz", "Makhachkala",
        "Tomsk", "Orenburg", "Kemerovo", "Novokuznetsk", "Ryazan",
        "Astrakhan", "Penza", "Lipetsk", "Tula", "Kirov",
        "Cheboksary", "Kursk", "Stavropol", "Suzdal", "Velikiy Novgorod",
    ],
    "indonesia": [
        "Jakarta", "Surabaya", "Bandung", "Medan", "Semarang",
        "Makassar", "Palembang", "Denpasar", "Yogyakarta", "Malang",
        "Balikpapan", "Manado", "Padang", "Batam", "Solo",
        "Lombok", "Ubud", "Komodo", "Raja Ampat", "Flores",
        "Bogor", "Depok", "Tangerang", "Bekasi", "Cirebon",
        "Pekanbaru", "Pontianak", "Samarinda", "Banjarmasin", "Mataram",
        "Kupang", "Ambon", "Jayapura", "Ternate", "Gorontalo",
        "Kendari", "Palu", "Bengkulu", "Jambi", "Pangkal Pinang",
        "Labuan Bajo", "Gili Islands", "Bunaken", "Toraja", "Belitung",
    ],
    "mexico": [
        "Guadalajara", "Monterrey", "Puebla", "Tijuana", "León",
        "Ciudad Juárez", "Zapopan", "Mérida", "Querétaro", "Chihuahua",
        "Aguascalientes", "Morelia", "Saltillo", "Hermosillo", "Durango",
        "Villahermosa", "Toluca", "Mazatlán", "Cabo San Lucas", "San Cristóbal de las Casas",
        "Guanajuato", "Taxco", "Campeche", "Cozumel", "Acapulco",
        "Ixtapa", "Huatulco", "Copper Canyon", "Todos Santos", "La Paz Baja",
        "Sayulita", "Zihuatanejo", "Bacalar", "Holbox", "Isla Mujeres",
        "Veracruz", "Xalapa", "San Luis Potosí", "Tampico", "Zacatecas",
        "Colima", "Tepic", "Pachuca", "Tlaxcala", "Tuxtla Gutiérrez",
        "Ciudad Obregón", "Los Mochis", "La Paz", "Ensenada", "Rosarito",
    ],
    "turkey": [
        "Ankara", "İzmir", "Bursa", "Antalya", "Adana",
        "Gaziantep", "Konya", "Mersin", "Diyarbakır", "Kayseri",
        "Eskişehir", "Trabzon", "Samsun", "Bodrum", "Fethiye",
        "Cappadocia", "Pamukkale", "Ephesus", "Kaş", "Alanya",
        "Marmaris", "Kuşadası", "Side", "Cesme", "Alaçatı",
        "Dalyan", "Ölüdeniz", "Göreme", "Safranbolu", "Sinop",
        "Amasya", "Mardin", "Şanlıurfa", "Van", "Rize",
        "Artvin", "Çanakkale", "Gallipoli", "Troy", "Edirne",
    ],
    "south-korea": [
        "Busan", "Incheon", "Daegu", "Daejeon", "Gwangju",
        "Suwon", "Ulsan", "Changwon", "Seongnam", "Goyang",
        "Yongin", "Cheongju", "Jeonju", "Chuncheon", "Jeju",
        "Gyeongju", "Andong", "Sokcho", "Gangneung", "Pohang",
    ],
    "thailand": [
        "Chiang Mai", "Phuket", "Pattaya", "Hua Hin", "Krabi",
        "Koh Samui", "Koh Phangan", "Koh Lipe", "Koh Chang", "Chiang Rai",
        "Ayutthaya", "Sukhothai", "Pai", "Kanchanaburi", "Nakhon Ratchasima",
        "Khon Kaen", "Udon Thani", "Hat Yai", "Lampang", "Nan",
    ],
    "vietnam": [
        "Ho Chi Minh City", "Da Nang", "Hai Phong", "Can Tho", "Nha Trang",
        "Hue", "Hoi An", "Da Lat", "Vung Tau", "Quy Nhon",
        "Sapa", "Ha Long", "Ninh Binh", "Phu Quoc", "Mekong Delta",
    ],
    "egypt": [
        "Alexandria", "Giza", "Luxor", "Aswan", "Sharm el-Sheikh",
        "Hurghada", "Port Said", "Suez", "Dahab", "Marsa Alam",
        "Siwa Oasis", "Fayoum", "Tanta", "Mansoura", "Ismailia",
    ],
    "south-africa": [
        "Johannesburg", "Cape Town", "Durban", "Pretoria", "Port Elizabeth",
        "Bloemfontein", "East London", "Pietermaritzburg", "Stellenbosch", "Knysna",
        "Franschhoek", "Hermanus", "Kruger Park", "Garden Route", "Soweto",
    ],
    "canada": [
        "Toronto", "Montreal", "Vancouver", "Calgary", "Edmonton",
        "Ottawa", "Winnipeg", "Quebec City", "Hamilton", "Victoria",
        "Halifax", "Saskatoon", "Regina", "St. John's", "Kelowna",
        "Whistler", "Banff", "Niagara Falls", "Charlottetown", "Yellowknife",
    ],
    "australia": [
        "Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide",
        "Gold Coast", "Canberra", "Hobart", "Darwin", "Cairns",
        "Newcastle", "Sunshine Coast", "Wollongong", "Geelong", "Townsville",
        "Alice Springs", "Byron Bay", "Great Barrier Reef", "Uluru", "Blue Mountains",
    ],
    "nigeria": [
        "Lagos", "Kano", "Ibadan", "Abuja", "Port Harcourt",
        "Benin City", "Kaduna", "Maiduguri", "Zaria", "Aba",
        "Jos", "Ilorin", "Oyo", "Enugu", "Abeokuta",
        "Sokoto", "Calabar", "Warri", "Uyo", "Owerri",
    ],
    "pakistan": [
        "Karachi", "Lahore", "Faisalabad", "Rawalpindi", "Multan",
        "Hyderabad", "Gujranwala", "Peshawar", "Quetta", "Sialkot",
        "Bahawalpur", "Sargodha", "Sukkur", "Larkana", "Islamabad",
        "Abbottabad", "Gilgit", "Hunza", "Swat", "Murree",
    ],
    "bangladesh": [
        "Dhaka", "Chittagong", "Khulna", "Rajshahi", "Sylhet",
        "Rangpur", "Comilla", "Gazipur", "Narayanganj", "Cox's Bazar",
        "Mymensingh", "Jessore", "Bogra", "Barisal", "Dinajpur",
    ],
    "philippines": [
        "Manila", "Quezon City", "Davao", "Cebu", "Zamboanga",
        "Antipolo", "Taguig", "Pasig", "Cagayan de Oro", "Parañaque",
        "Makati", "Bacolod", "General Santos", "Iloilo", "Baguio",
        "Boracay", "Palawan", "Siargao", "El Nido", "Coron",
    ],
    "colombia": [
        "Bogotá", "Medellín", "Cali", "Barranquilla", "Cartagena",
        "Bucaramanga", "Pereira", "Santa Marta", "Manizales", "Ibagué",
        "Cúcuta", "Villavicencio", "Pasto", "Armenia", "Leticia",
    ],
    "argentina": [
        "Buenos Aires", "Córdoba", "Rosario", "Mendoza", "La Plata",
        "San Miguel de Tucumán", "Mar del Plata", "Salta", "Santa Fe", "San Juan",
        "Bariloche", "Ushuaia", "Iguazú", "El Calafate", "Puerto Madryn",
    ],
    "peru": [
        "Lima", "Arequipa", "Trujillo", "Chiclayo", "Cusco",
        "Piura", "Iquitos", "Huancayo", "Tacna", "Pucallpa",
        "Ayacucho", "Cajamarca", "Puno", "Huaraz", "Nazca",
    ],
    "poland": [
        "Kraków", "Łódź", "Wrocław", "Poznań", "Gdańsk",
        "Szczecin", "Bydgoszcz", "Lublin", "Białystok", "Katowice",
        "Toruń", "Rzeszów", "Olsztyn", "Opole", "Zakopane",
    ],
    "netherlands": [
        "Rotterdam", "The Hague", "Utrecht", "Eindhoven", "Tilburg",
        "Groningen", "Almere", "Breda", "Nijmegen", "Maastricht",
        "Haarlem", "Leiden", "Delft", "Arnhem", "Enschede",
    ],
    "belgium": [
        "Brussels", "Antwerp", "Ghent", "Bruges", "Liège",
        "Namur", "Leuven", "Mechelen", "Charleroi", "Mons",
    ],
    "switzerland": [
        "Zurich", "Geneva", "Basel", "Lausanne", "Bern",
        "Winterthur", "Lucerne", "St. Gallen", "Lugano", "Interlaken",
        "Zermatt", "Grindelwald", "Davos", "Montreux", "Thun",
    ],
    "portugal": [
        "Porto", "Vila Nova de Gaia", "Amadora", "Braga", "Setúbal",
        "Coimbra", "Funchal", "Évora", "Aveiro", "Faro",
        "Sintra", "Lagos", "Albufeira", "Cascais", "Óbidos",
    ],
    "czech-republic": [
        "Brno", "Ostrava", "Plzeň", "Liberec", "Olomouc",
        "České Budějovice", "Hradec Králové", "Ústí nad Labem", "Pardubice", "Karlovy Vary",
        "Český Krumlov", "Kutná Hora", "Telč", "Mariánské Lázně", "Znojmo",
    ],
    "austria": [
        "Graz", "Linz", "Salzburg", "Innsbruck", "Klagenfurt",
        "Hallstatt", "St. Anton", "Kitzbühel", "Bad Gastein", "Zell am See",
    ],
    "greece": [
        "Thessaloniki", "Patras", "Heraklion", "Larissa", "Volos",
        "Rhodes", "Corfu", "Santorini", "Mykonos", "Crete",
        "Zakynthos", "Kalamata", "Kavala", "Nafplio", "Delphi",
    ],
    "hungary": [
        "Debrecen", "Szeged", "Miskolc", "Pécs", "Győr",
        "Nyíregyháza", "Kecskemét", "Székesfehérvár", "Eger", "Sopron",
    ],
    "romania": [
        "Cluj-Napoca", "Timișoara", "Iași", "Constanța", "Craiova",
        "Brașov", "Galați", "Ploiești", "Oradea", "Sibiu",
        "Sighișoara", "Alba Iulia", "Bran", "Sinaia", "Suceava",
    ],
    "croatia": [
        "Zagreb", "Split", "Rijeka", "Osijek", "Zadar",
        "Dubrovnik", "Pula", "Šibenik", "Rovinj", "Hvar",
    ],
    "morocco": [
        "Casablanca", "Fez", "Tangier", "Agadir", "Meknes",
        "Oujda", "Kenitra", "Tétouan", "Chefchaouen", "Essaouira",
    ],
    "kenya": [
        "Mombasa", "Kisumu", "Nakuru", "Eldoret", "Thika",
        "Malindi", "Lamu", "Nanyuki", "Diani Beach", "Maasai Mara",
    ],
    "tanzania": [
        "Dar es Salaam", "Mwanza", "Arusha", "Mbeya", "Morogoro",
        "Tanga", "Zanzibar", "Bagamoyo", "Iringa", "Serengeti",
    ],
    "ethiopia": [
        "Addis Ababa", "Dire Dawa", "Mekelle", "Gondar", "Adama",
        "Bahir Dar", "Hawassa", "Jimma", "Dessie", "Lalibela",
    ],
    "ghana": [
        "Accra", "Kumasi", "Tamale", "Takoradi", "Cape Coast",
        "Sunyani", "Koforidua", "Ho", "Tema", "Elmina",
    ],
    "senegal": [
        "Dakar", "Saint-Louis", "Thiès", "Kaolack", "Ziguinchor",
        "Touba", "Mbour", "Louga", "Richard-Toll", "Gorée Island",
    ],
    "malaysia": [
        "Kuala Lumpur", "George Town", "Johor Bahru", "Ipoh", "Kuching",
        "Kota Kinabalu", "Shah Alam", "Malacca", "Alor Setar", "Langkawi",
        "Cameron Highlands", "Taman Negara", "Perhentian Islands", "Tioman", "Putrajaya",
    ],
    "singapore": [
        "Singapore City", "Sentosa", "Marina Bay", "Changi", "Jurong",
    ],
    "new-zealand": [
        "Auckland", "Wellington", "Christchurch", "Hamilton", "Tauranga",
        "Dunedin", "Napier", "Nelson", "Queenstown", "Rotorua",
        "Wanaka", "Hobbiton", "Milford Sound", "Te Anau", "Kaikoura",
    ],
    "ireland": [
        "Cork", "Galway", "Limerick", "Waterford", "Kilkenny",
        "Killarney", "Dingle", "Sligo", "Westport", "Doolin",
    ],
    "denmark": [
        "Aarhus", "Odense", "Aalborg", "Esbjerg", "Randers",
        "Kolding", "Horsens", "Roskilde", "Helsingør", "Billund",
    ],
    "sweden": [
        "Gothenburg", "Malmö", "Uppsala", "Västerås", "Örebro",
        "Linköping", "Norrköping", "Helsingborg", "Jönköping", "Kiruna",
        "Visby", "Lund", "Umeå", "Gävle", "Kalmar",
    ],
    "norway": [
        "Bergen", "Trondheim", "Stavanger", "Tromsø", "Drammen",
        "Kristiansand", "Fredrikstad", "Sandnes", "Ålesund", "Lofoten",
        "Flåm", "Geiranger", "Svalbard", "Bodø", "Narvik",
    ],
    "finland": [
        "Espoo", "Tampere", "Vantaa", "Oulu", "Turku",
        "Jyväskylä", "Kuopio", "Lahti", "Rovaniemi", "Lappeenranta",
    ],
    "iceland": [
        "Akureyri", "Vik", "Húsavík", "Selfoss", "Blue Lagoon",
    ],
    "saudi-arabia": [
        "Jeddah", "Mecca", "Medina", "Dammam", "Khobar",
        "Tabuk", "Taif", "Abha", "NEOM", "AlUla",
    ],
    "united-arab-emirates": [
        "Abu Dhabi", "Sharjah", "Ajman", "Ras Al Khaimah", "Fujairah",
        "Al Ain", "Umm Al Quwain",
    ],
    "israel": [
        "Tel Aviv", "Jerusalem", "Haifa", "Eilat", "Be'er Sheva",
        "Nazareth", "Tiberias", "Acre", "Caesarea", "Dead Sea",
    ],
    "jordan": [
        "Amman", "Aqaba", "Irbid", "Zarqa", "Petra",
        "Jerash", "Madaba", "Dead Sea", "Wadi Rum", "Salt",
    ],
    "qatar": [
        "Al Wakrah", "Al Khor", "Dukhan", "Lusail", "The Pearl",
    ],
    "oman": [
        "Salalah", "Sohar", "Nizwa", "Sur", "Musandam",
    ],
    "iran": [
        "Isfahan", "Shiraz", "Tabriz", "Mashhad", "Yazd",
        "Kerman", "Kashan", "Hamadan", "Ahvaz", "Rasht",
    ],
    "cuba": [
        "Santiago de Cuba", "Camagüey", "Holguín", "Santa Clara", "Trinidad",
        "Cienfuegos", "Viñales", "Varadero", "Baracoa", "Pinar del Río",
    ],
    "costa-rica": [
        "San José", "Limón", "Heredia", "Alajuela", "La Fortuna",
        "Monteverde", "Manuel Antonio", "Tamarindo", "Puerto Viejo", "Jacó",
    ],
    "guatemala": [
        "Guatemala City", "Antigua Guatemala", "Quetzaltenango", "Flores", "Panajachel",
        "Livingston", "Chichicastenango", "Cobán", "Tikal", "Semuc Champey",
    ],
    "chile": [
        "Santiago", "Valparaíso", "Concepción", "Viña del Mar", "Antofagasta",
        "Temuco", "Rancagua", "Talca", "Arica", "Iquique",
        "Puerto Montt", "Punta Arenas", "San Pedro de Atacama", "Torres del Paine", "Easter Island",
    ],
    "uruguay": [
        "Punta del Este", "Colonia del Sacramento", "Salto", "Paysandú", "Rivera",
    ],
    "ecuador": [
        "Guayaquil", "Cuenca", "Ambato", "Manta", "Portoviejo",
        "Galápagos", "Baños", "Otavalo", "Riobamba", "Loja",
    ],
    "bolivia": [
        "Santa Cruz", "Cochabamba", "Sucre", "Oruro", "Tarija",
        "Potosí", "Uyuni", "Copacabana", "Rurrenabaque", "Samaipata",
    ],
    "panama": [
        "Colón", "David", "Bocas del Toro", "Boquete", "Pedasí",
    ],
    "cambodia": [
        "Siem Reap", "Sihanoukville", "Battambang", "Kampot", "Kep",
    ],
    "laos": [
        "Luang Prabang", "Vang Vieng", "Pakse", "Savannakhet", "4000 Islands",
    ],
    "myanmar": [
        "Mandalay", "Bagan", "Inle Lake", "Mawlamyine", "Ngapali Beach",
    ],
    "nepal": [
        "Pokhara", "Lalitpur", "Bhaktapur", "Chitwan", "Lumbini",
        "Nagarkot", "Bandipur", "Janakpur", "Biratnagar", "Birgunj",
    ],
    "sri-lanka": [
        "Kandy", "Galle", "Negombo", "Ella", "Trincomalee",
        "Sigiriya", "Anuradhapura", "Jaffna", "Nuwara Eliya", "Mirissa",
    ],
    "maldives": [
        "Addu City", "Hulhumalé", "Maafushi", "Fuvahmulah", "Thulusdhoo",
    ],
    "georgia": [
        "Kutaisi", "Batumi", "Rustavi", "Zugdidi", "Gori",
        "Kazbegi", "Mestia", "Sighnaghi", "Telavi", "Borjomi",
    ],
    "ukraine": [
        "Kyiv", "Kharkiv", "Odessa", "Dnipro", "Lviv",
        "Zaporizhzhia", "Vinnytsia", "Mykolaiv", "Chernivtsi", "Poltava",
    ],
    "bulgaria": [
        "Plovdiv", "Varna", "Burgas", "Ruse", "Stara Zagora",
        "Pleven", "Bansko", "Sozopol", "Nessebar", "Veliko Tarnovo",
    ],
    "serbia": [
        "Novi Sad", "Niš", "Kragujevac", "Subotica", "Zlatibor",
    ],
    "slovenia": [
        "Maribor", "Celje", "Kranj", "Koper", "Bled",
        "Piran", "Portorož", "Bovec", "Ptuj", "Nova Gorica",
    ],
    "slovakia": [
        "Košice", "Prešov", "Žilina", "Banská Bystrica", "Nitra",
        "Trenčín", "High Tatras", "Bardejov", "Bojnice", "Levoča",
    ],
    "lithuania": [
        "Kaunas", "Klaipėda", "Šiauliai", "Panevėžys", "Trakai",
    ],
    "latvia": [
        "Daugavpils", "Liepāja", "Jelgava", "Jūrmala", "Ventspils",
    ],
    "estonia": [
        "Tartu", "Narva", "Pärnu", "Kohtla-Järve", "Haapsalu",
    ],
    "north-macedonia": [
        "Skopje", "Ohrid", "Bitola", "Kumanovo", "Tetovo",
    ],
    "albania": [
        "Tirana", "Durrës", "Vlorë", "Shkodër", "Elbasan",
        "Sarandë", "Berat", "Gjirokastër", "Korçë", "Pogradec",
    ],
    "montenegro": [
        "Podgorica", "Budva", "Kotor", "Herceg Novi", "Tivat",
        "Bar", "Ulcinj", "Cetinje", "Žabljak", "Sveti Stefan",
    ],
    "bosnia-and-herzegovina": [
        "Sarajevo", "Banja Luka", "Mostar", "Tuzla", "Zenica",
        "Trebinje", "Jajce", "Višegrad", "Bihać", "Neum",
    ],
    "tunisia": [
        "Tunis", "Sfax", "Sousse", "Hammamet", "Djerba",
        "Monastir", "Kairouan", "Tozeur", "Sidi Bou Said", "Carthage",
    ],
    "namibia": [
        "Windhoek", "Walvis Bay", "Swakopmund", "Oshakati", "Rundu",
        "Sossusvlei", "Etosha", "Fish River Canyon", "Skeleton Coast", "Lüderitz",
    ],
    "zimbabwe": [
        "Harare", "Bulawayo", "Chitungwiza", "Mutare", "Victoria Falls",
        "Masvingo", "Gweru", "Kariba", "Nyanga", "Hwange",
    ],
    "zambia": [
        "Lusaka", "Kitwe", "Ndola", "Kabwe", "Livingstone",
        "Chipata", "Kasama", "Solwezi", "Mfuwe", "Siavonga",
    ],
    "botswana": [
        "Gaborone", "Francistown", "Maun", "Kasane", "Nata",
        "Okavango Delta", "Chobe", "Makgadikgadi", "Tsodilo", "Palapye",
    ],
    "madagascar": [
        "Antananarivo", "Toamasina", "Antsirabe", "Mahajanga", "Nosy Be",
        "Morondava", "Ranomafana", "Isalo", "Andasibe", "Diego Suarez",
    ],
    "rwanda": [
        "Kigali", "Butare", "Gisenyi", "Ruhengeri", "Volcanoes NP",
    ],
    "uganda": [
        "Kampala", "Entebbe", "Jinja", "Fort Portal", "Mbarara",
        "Bwindi", "Murchison Falls", "Queen Elizabeth NP", "Kabale", "Gulu",
    ],
    "algeria": [
        "Oran", "Constantine", "Annaba", "Batna", "Blida",
        "Sétif", "Djelfa", "Sidi Bel Abbès", "Tlemcen", "Ghardaïa",
    ],
    "libya": [
        "Benghazi", "Misrata", "Sabha", "Zliten", "Tobruk",
    ],
    "iraq": [
        "Baghdad", "Basra", "Erbil", "Mosul", "Sulaymaniyah",
        "Karbala", "Najaf", "Kirkuk", "Duhok", "Samawah",
    ],
    "lebanon": [
        "Beirut", "Tripoli", "Sidon", "Byblos", "Baalbek",
        "Jounieh", "Tyre", "Zahle", "Harissa", "Beiteddine",
    ],
    "kazakhstan": [
        "Almaty", "Astana", "Shymkent", "Aktobe", "Karaganda",
        "Turkestan", "Aktau", "Semey", "Atyrau", "Kostanay",
    ],
    "uzbekistan": [
        "Samarkand", "Bukhara", "Khiva", "Namangan", "Andijan",
        "Nukus", "Fergana", "Qarshi", "Termez", "Navoi",
    ],
    "mongolia": [
        "Ulaanbaatar", "Erdenet", "Darkhan", "Khovd", "Terelj",
        "Gobi Desert", "Kharkhorin", "Olgii", "Murun", "Dalanzadgad",
    ],
    "fiji": [
        "Suva", "Nadi", "Lautoka", "Labasa", "Savusavu",
        "Denarau", "Coral Coast", "Taveuni", "Yasawa Islands", "Mamanuca Islands",
    ],
}

# ─── Additional smaller countries with a few cities each ──────────────────────
SMALL_COUNTRY_CITIES = {
    "andorra": ["Andorra la Vella", "Escaldes-Engordany", "Encamp"],
    "bahamas": ["Nassau", "Freeport", "Paradise Island"],
    "bahrain": ["Manama", "Muharraq", "Riffa"],
    "barbados": ["Bridgetown", "Holetown", "Speightstown"],
    "belize": ["Belmopan", "Belize City", "San Ignacio", "Placencia", "Caye Caulker"],
    "bhutan": ["Thimphu", "Paro", "Punakha", "Bumthang", "Trongsa"],
    "brunei": ["Bandar Seri Begawan", "Seria", "Tutong"],
    "burkina-faso": ["Ouagadougou", "Bobo-Dioulasso", "Koudougou"],
    "burundi": ["Gitega", "Bujumbura", "Muyinga"],
    "cameroon": ["Yaoundé", "Douala", "Bamenda", "Bafoussam", "Garoua"],
    "cape-verde": ["Praia", "Mindelo", "Sal", "Boa Vista"],
    "central-african-republic": ["Bangui", "Bimbo", "Berbérati"],
    "chad": ["N'Djamena", "Moundou", "Abéché"],
    "comoros": ["Moroni", "Mutsamudu", "Fomboni"],
    "congo": ["Brazzaville", "Pointe-Noire", "Dolisie"],
    "congo-drc": ["Kinshasa", "Lubumbashi", "Mbuji-Mayi", "Kananga", "Kisangani"],
    "cyprus": ["Nicosia", "Limassol", "Larnaca", "Paphos", "Ayia Napa"],
    "djibouti": ["Djibouti City", "Ali Sabieh", "Tadjoura"],
    "dominica": ["Roseau", "Portsmouth", "Marigot"],
    "dominican-republic": ["Santo Domingo", "Santiago", "Punta Cana", "Puerto Plata", "La Romana"],
    "east-timor": ["Dili", "Baucau", "Maliana"],
    "el-salvador": ["San Salvador", "Santa Ana", "San Miguel", "Suchitoto", "El Tunco"],
    "equatorial-guinea": ["Malabo", "Bata", "Ebebiyin"],
    "eritrea": ["Asmara", "Keren", "Massawa"],
    "eswatini": ["Mbabane", "Manzini", "Lobamba"],
    "gabon": ["Libreville", "Port-Gentil", "Franceville"],
    "gambia": ["Banjul", "Serekunda", "Brikama"],
    "grenada": ["St. George's", "Gouyave", "Grenville"],
    "guinea": ["Conakry", "Nzérékoré", "Kankan"],
    "guinea-bissau": ["Bissau", "Bafatá", "Gabú"],
    "guyana": ["Georgetown", "Linden", "New Amsterdam", "Kaieteur Falls"],
    "haiti": ["Port-au-Prince", "Cap-Haïtien", "Gonaïves", "Jacmel"],
    "honduras": ["Tegucigalpa", "San Pedro Sula", "La Ceiba", "Roatán", "Utila"],
    "jamaica": ["Kingston", "Montego Bay", "Ocho Rios", "Negril", "Port Antonio"],
    "kiribati": ["Tarawa", "Kiritimati"],
    "kuwait": ["Kuwait City", "Hawalli", "Salmiya", "Fahaheel"],
    "kyrgyzstan": ["Bishkek", "Osh", "Karakol", "Issyk-Kul", "Cholpon-Ata"],
    "lesotho": ["Maseru", "Teyateyaneng", "Mafeteng"],
    "liberia": ["Monrovia", "Gbarnga", "Buchanan"],
    "liechtenstein": ["Vaduz", "Schaan", "Balzers"],
    "luxembourg": ["Luxembourg City", "Esch-sur-Alzette", "Differdange"],
    "malawi": ["Lilongwe", "Blantyre", "Mzuzu", "Zomba", "Lake Malawi"],
    "mali": ["Bamako", "Sikasso", "Timbuktu", "Mopti", "Djenné"],
    "malta": ["Valletta", "Sliema", "St. Julian's", "Mdina", "Gozo"],
    "marshall-islands": ["Majuro", "Ebeye"],
    "mauritania": ["Nouakchott", "Nouadhibou", "Atar"],
    "mauritius": ["Port Louis", "Curepipe", "Vacoas", "Grand Baie", "Flic en Flac"],
    "micronesia": ["Palikir", "Weno", "Kolonia"],
    "moldova": ["Chișinău", "Tiraspol", "Bălți"],
    "monaco": ["Monaco City", "Monte Carlo", "La Condamine"],
    "mozambique": ["Maputo", "Matola", "Beira", "Nampula", "Inhambane"],
    "nauru": ["Yaren"],
    "nicaragua": ["Managua", "León", "Granada", "San Juan del Sur", "Ometepe"],
    "niger": ["Niamey", "Zinder", "Maradi", "Agadez"],
    "north-korea": ["Pyongyang", "Hamhung", "Chongjin"],
    "palau": ["Ngerulmud", "Koror"],
    "papua-new-guinea": ["Port Moresby", "Lae", "Madang", "Mount Hagen"],
    "paraguay": ["Asunción", "Ciudad del Este", "Encarnación", "San Bernardino"],
    "saint-kitts-and-nevis": ["Basseterre", "Charlestown"],
    "saint-lucia": ["Castries", "Soufrière", "Gros Islet", "Vieux Fort"],
    "saint-vincent": ["Kingstown", "Bequia", "Mustique"],
    "samoa": ["Apia", "Lalomanu"],
    "san-marino": ["San Marino City"],
    "sao-tome-and-principe": ["São Tomé", "Santo Amaro"],
    "seychelles": ["Victoria", "Beau Vallon", "Praslin", "La Digue"],
    "sierra-leone": ["Freetown", "Bo", "Kenema"],
    "solomon-islands": ["Honiara", "Gizo"],
    "somalia": ["Mogadishu", "Hargeisa", "Berbera"],
    "south-sudan": ["Juba", "Malakal", "Wau"],
    "sudan": ["Khartoum", "Omdurman", "Port Sudan"],
    "suriname": ["Paramaribo", "Lelydorp"],
    "syria": ["Damascus", "Aleppo", "Homs", "Latakia", "Palmyra"],
    "tajikistan": ["Dushanbe", "Khujand", "Khorog"],
    "togo": ["Lomé", "Sokodé", "Kara"],
    "tonga": ["Nukuʻalofa", "Vavaʻu"],
    "trinidad-and-tobago": ["Port of Spain", "San Fernando", "Tobago", "Chaguanas"],
    "turkmenistan": ["Ashgabat", "Türkmenabat", "Daşoguz"],
    "tuvalu": ["Funafuti"],
    "vanuatu": ["Port Vila", "Luganville"],
    "vatican": ["Vatican City"],
    "venezuela": ["Caracas", "Maracaibo", "Valencia", "Barquisimeto", "Ciudad Bolívar",
                   "Mérida", "Margarita Island"],
    "yemen": ["Sana'a", "Aden", "Taiz", "Socotra"],
}


# ─── POPULAR "IS X SAFE" SEARCH DESTINATIONS ─────────────────────────────────
# Additional cities commonly searched for safety, not already listed above
IS_X_SAFE_CITIES = {
    "mexico": ["Tijuana", "Juárez", "Nogales", "Reynosa", "Matamoros", "Nuevo Laredo",
               "Guadalajara", "Monterrey", "Chiapas"],
    "brazil": ["São Paulo", "Manaus", "Belém", "Recife", "Salvador", "Fortaleza"],
    "colombia": ["Cali", "Barranquilla", "Santa Marta", "San Andrés"],
    "south-africa": ["Johannesburg", "Durban", "Pretoria", "Port Elizabeth", "Bloemfontein"],
    "india": ["Mumbai", "Delhi", "Kolkata", "Chennai", "Bangalore", "Hyderabad",
              "Jaipur", "Agra", "Varanasi", "Goa", "Kerala", "Rajasthan"],
    "thailand": ["Bangkok", "Phuket", "Chiang Mai", "Koh Samui", "Pattaya", "Krabi"],
    "philippines": ["Manila", "Cebu", "Davao", "Boracay", "Palawan"],
    "egypt": ["Cairo", "Luxor", "Sharm el-Sheikh", "Hurghada", "Dahab", "Alexandria"],
    "turkey": ["Istanbul", "Ankara", "Antalya", "Bodrum", "Izmir", "Cappadocia"],
    "morocco": ["Marrakech", "Fez", "Casablanca", "Tangier", "Chefchaouen"],
    "kenya": ["Nairobi", "Mombasa", "Kisumu", "Nakuru", "Lamu"],
    "peru": ["Lima", "Cusco", "Arequipa", "Iquitos", "Puno"],
    "argentina": ["Buenos Aires", "Mendoza", "Córdoba", "Bariloche", "Ushuaia"],
    "guatemala": ["Guatemala City", "Antigua", "Flores", "Lake Atitlán", "Tikal"],
    "honduras": ["Tegucigalpa", "San Pedro Sula", "Roatán", "La Ceiba", "Copán"],
    "el-salvador": ["San Salvador", "Santa Ana", "San Miguel", "El Tunco"],
    "nicaragua": ["Managua", "Granada", "León", "San Juan del Sur"],
    "venezuela": ["Caracas", "Mérida", "Maracaibo", "Los Roques"],
    "haiti": ["Port-au-Prince", "Cap-Haïtien", "Jacmel"],
    "jamaica": ["Kingston", "Montego Bay", "Ocho Rios", "Negril"],
    "dominican-republic": ["Santo Domingo", "Punta Cana", "Puerto Plata"],
    "pakistan": ["Karachi", "Lahore", "Islamabad", "Peshawar", "Quetta"],
    "iraq": ["Baghdad", "Erbil", "Basra", "Sulaymaniyah"],
    "lebanon": ["Beirut", "Byblos", "Baalbek", "Tripoli Lebanon"],
    "iran": ["Tehran", "Isfahan", "Shiraz", "Yazd", "Tabriz"],
    "nigeria": ["Lagos", "Abuja", "Kano", "Port Harcourt", "Ibadan"],
    "myanmar": ["Yangon", "Mandalay", "Bagan", "Inle Lake"],
    "cambodia": ["Phnom Penh", "Siem Reap", "Sihanoukville", "Kampot"],
    "sri-lanka": ["Colombo", "Kandy", "Galle", "Ella", "Sigiriya"],
    "nepal": ["Kathmandu", "Pokhara", "Lumbini", "Chitwan"],
    "tanzania": ["Dar es Salaam", "Zanzibar", "Arusha", "Serengeti", "Ngorongoro"],
    "ethiopia": ["Addis Ababa", "Lalibela", "Gondar", "Bahir Dar"],
    "congo-drc": ["Kinshasa", "Lubumbashi", "Goma", "Bukavu"],
    "somalia": ["Mogadishu", "Hargeisa"],
    "ukraine": ["Kyiv", "Lviv", "Odessa", "Kharkiv"],
    "russia": ["Moscow", "Saint Petersburg", "Sochi", "Vladivostok", "Kazan"],
    "china": ["Beijing", "Shanghai", "Hong Kong", "Shenzhen", "Guangzhou", "Xi'an"],
}

# ─── ADDITIONAL POPULAR WORLD CITIES ─────────────────────────────────────────
# More cities for countries that have many searchable destinations
EXTRA_WORLD_CITIES = {
    "germany": [
        "Aachen", "Kiel", "Rostock", "Mainz", "Erfurt",
        "Jena", "Weimar", "Regensburg", "Würzburg", "Passau",
        "Konstanz", "Ulm", "Ingolstadt", "Darmstadt", "Kassel",
        "Halle", "Magdeburg", "Schwerin", "Braunschweig", "Göttingen",
    ],
    "france": [
        "Versailles", "Metz", "Nancy", "Limoges", "Poitiers",
        "Pau", "Bayonne", "Ajaccio", "Bastia", "Lourdes",
        "Saint-Malo", "Honfleur", "Étretat", "Mont Saint-Michel", "Annecy",
        "Chambéry", "Valence", "Arles", "Carcassonne", "Sète",
    ],
    "italy": [
        "Rimini", "Ancona", "Pescara", "Sassari", "Oristano",
        "Trani", "Matera", "Alberobello", "Polignano a Mare", "Vieste",
        "San Gimignano", "Volterra", "Cortona", "Assisi", "Orvieto",
        "Spoleto", "Lucca", "Livorno", "La Spezia", "Portofino",
    ],
    "spain": [
        "Cuenca", "Ávila", "Cáceres", "Badajoz", "León Spain",
        "Burgos", "Logroño", "Huesca", "Teruel", "Almería",
        "Huelva", "Jaén", "Jerez de la Frontera", "Pontevedra", "Lugo",
        "Ourense", "Palencia", "Soria", "Zamora", "Ciudad Real",
    ],
    "united-kingdom": [
        "Stratford-upon-Avon", "Cotswolds", "Lake District", "Cornwall", "Devon",
        "Bournemouth", "Winchester", "Canterbury", "Windsor", "Stonehenge Area",
        "Snowdonia", "Highlands Scotland", "Isle of Skye", "Orkney", "Shetland",
        "Jersey", "Guernsey", "Isle of Man", "Isle of Wight", "St Andrews",
    ],
    "canada": [
        "Quebec City", "Halifax", "Charlottetown", "Moncton", "Fredericton",
        "Thunder Bay", "Sudbury", "Kingston Ontario", "London Ontario", "Waterloo Ontario",
        "Jasper", "Lake Louise", "Tofino", "Prince Edward Island", "Churchill",
        "Dawson City", "Iqaluit", "Inuvik", "Whitehorse", "Prince George",
    ],
    "australia": [
        "Broome", "Kalgoorlie", "Margaret River", "Esperance", "Geraldton",
        "Bundaberg", "Mackay", "Rockhampton", "Gladstone", "Hervey Bay",
        "Coffs Harbour", "Port Macquarie", "Albury", "Wagga Wagga", "Dubbo",
        "Bathurst", "Orange", "Tamworth", "Armidale", "Launceston",
    ],
    "south-korea": [
        "Yeosu", "Tongyeong", "Gapyeong", "Damyang", "Boseong",
        "Namhae", "Haenam", "Jinju", "Gimhae", "Cheonan",
    ],
    "thailand": [
        "Nakhon Si Thammarat", "Surat Thani", "Trang", "Ranong", "Chumphon",
        "Mae Hong Son", "Phitsanulok", "Nong Khai", "Loei", "Buriram",
    ],
    "vietnam": [
        "Buon Ma Thuot", "Kon Tum", "Pleiku", "Dong Hoi", "Vinh",
        "Thanh Hoa", "Nam Dinh", "Thai Nguyen", "Lao Cai", "Dien Bien Phu",
    ],
    "egypt": [
        "Asyut", "Faiyum", "Beni Suef", "Minya", "Sohag",
        "Qena", "Edfu", "Kom Ombo", "Abu Simbel", "Rosetta",
    ],
    "south-africa": [
        "Pietermaritzburg", "Nelspruit", "Polokwane", "Kimberley", "Upington",
        "George", "Mossel Bay", "Oudtshoorn", "Graaff-Reinet", "Grahamstown",
    ],
    "nigeria": [
        "Ogbomosho", "Akure", "Ondo", "Ile-Ife", "Oshogbo",
        "Ekiti", "Bauchi", "Gombe", "Yola", "Lafia",
    ],
    "pakistan": [
        "Larkana", "Gujrat", "Sahiwal", "Mirpur", "Mardan",
        "Mingora", "Chitral", "Skardu", "Naran", "Kaghan",
    ],
    "bangladesh": [
        "Dinajpur", "Tangail", "Faridpur", "Noakhali", "Brahmanbaria",
        "Habiganj", "Moulvibazar", "Chapainawabganj", "Kushtia", "Jamalpur",
    ],
    "philippines": [
        "Tacloban", "Dumaguete", "Vigan", "Sagada", "Batangas",
        "Angeles City", "Olongapo", "Legazpi", "Naga City", "Ormoc",
    ],
    "colombia": [
        "Neiva", "Popayán", "Tunja", "Riohacha", "Valledupar",
        "Montería", "Sincelejo", "Quibdó", "Yopal", "San Gil",
    ],
    "argentina": [
        "San Carlos de Bariloche", "El Chaltén", "Puerto Iguazú", "Tigre", "Pilar",
        "San Rafael", "Villa La Angostura", "San Martín de los Andes", "Villa General Belgrano", "Tandil",
    ],
    "peru": [
        "Máncora", "Chachapoyas", "Tarapoto", "Moyobamba", "Tambopata",
        "Colca Canyon", "Paracas", "Ica", "Chincha", "Huaraz",
    ],
    "poland": [
        "Sopot", "Gdynia", "Kołobrzeg", "Świnoujście", "Jelenia Góra",
        "Karpacz", "Malbork", "Zamość", "Kazimierz Dolny", "Sandomierz",
    ],
    "netherlands": [
        "Dordrecht", "Gouda", "Amersfoort", "Den Bosch", "Middelburg",
        "Vlissingen", "Leeuwarden", "Zwolle", "Apeldoorn", "Deventer",
    ],
    "czech-republic": [
        "Tábor", "Třebíč", "Kroměříž", "Liberec", "Harrachov",
        "Špindlerův Mlýn", "Mikulov", "Lednice", "Litomyšl", "Loket",
    ],
    "iran": [
        "Kermanshah", "Zanjan", "Arak", "Sanandaj", "Qom",
        "Gorgan", "Sari", "Bandar Abbas", "Chabahar", "Kish Island",
    ],
    "morocco": [
        "Rabat", "Ouarzazate", "Merzouga", "Asilah", "Moulay Idriss",
        "Volubilis", "Ifrane", "Midelt", "Tinghir", "Todra Gorge",
    ],
    "kenya": [
        "Watamu", "Malindi", "Lamu", "Amboseli", "Tsavo",
        "Lake Naivasha", "Lake Nakuru", "Samburu", "Laikipia", "Nanyuki",
    ],
    "tanzania": [
        "Moshi", "Karatu", "Lake Manyara", "Kilimanjaro", "Pemba Island",
        "Mafia Island", "Mikumi", "Ruaha", "Selous", "Kondoa",
    ],
    "cuba": [
        "Matanzas", "Remedios", "Camagüey", "Bayamo", "Guantánamo",
        "Cayo Coco", "Cayo Largo", "Isla de la Juventud", "Topes de Collantes", "María la Gorda",
    ],
    "costa-rica": [
        "Tortuguero", "Drake Bay", "Corcovado", "Nosara", "Santa Teresa",
        "Montezuma", "Arenal", "Rincón de la Vieja", "Cahuita", "Dominical",
    ],
    "greece": [
        "Meteora", "Olympia", "Thessaloniki", "Ioannina", "Alexandroupolis",
        "Lefkada", "Kefalonia", "Paros", "Naxos", "Milos",
        "Skiathos", "Skopelos", "Samos", "Lesbos", "Chios",
    ],
    "croatia": [
        "Korčula", "Brač", "Vis", "Mljet", "Trogir",
        "Makarska", "Opatija", "Cres", "Lošinj", "Motovun",
    ],
    "hungary": [
        "Hévíz", "Balatonfüred", "Tihany", "Villány", "Tokaj",
        "Visegrád", "Szentendre", "Esztergom", "Keszthely", "Hollókő",
    ],
    "romania": [
        "Turda", "Baia Mare", "Târgu Mureș", "Piatra Neamț", "Rădăuți",
        "Câmpulung", "Curtea de Argeș", "Hunedoara", "Deva", "Horezu",
    ],
    "bulgaria": [
        "Koprivshtitsa", "Belogradchik", "Melnik", "Tryavna", "Kovachevtsi",
        "Smolyan", "Shiroka Laka", "Devin", "Sandanski", "Kazanlak",
    ],
    "georgia": [
        "Stepantsminda", "Mtskheta", "Vardzia", "Uplistsikhe", "Tusheti",
        "Svaneti", "Kakheti", "Ananuri", "Gudauri", "Bakuriani",
    ],
    "japan": [
        "Kanazawa", "Matsue", "Tottori", "Wakayama", "Mie",
        "Gifu", "Toyama", "Fukui", "Saga", "Oita",
        "Miyazaki", "Tokushima", "Kochi", "Ehime", "Iwate",
    ],
    "south-korea": [
        "Suncheon", "Mokpo", "Gunsan", "Iksan", "Gongju",
        "Buyeo", "Hapcheon", "Miryang", "Gimje", "Wanju",
    ],
    "india": [
        "Thanjavur", "Kumbakonam", "Mahabalipuram", "Chidambaram", "Karaikal",
        "Hampi", "Badami", "Pattadakal", "Bijapur", "Aihole",
        "Ellora", "Ajanta", "Aurangabad Maharashtra", "Nashik", "Lonavala",
        "Matheran", "Alibaug", "Mahabaleshwar", "Panchgani", "Bhandardara",
        "Kasol", "Tirthan Valley", "Spiti Valley", "Chitkul", "Kalpa",
        "Bir Billing", "Barog", "Chail", "Kufri", "Auli",
        "Chopta", "Mukteshwar", "Bhimtal", "Ranikhet", "Lansdowne",
        "Binsar", "Jageshwar", "Chaukori", "Munsiyari", "Pithoragarh",
    ],
    "china": [
        "Pingyao", "Fenghuang", "Zhoushan", "Putuoshan", "Wuzhen",
        "Nanxun", "Xitang", "Zhouzhuang", "Tongli", "Luzhi",
        "Moganshan", "Anji", "Wuyishan", "Lushan", "Jingdezhen",
        "Zhangye", "Jiayuguan", "Turfan", "Kanas", "Altay",
        "Dali", "Tengchong", "Ruili", "Jianshui", "Yuanyang",
        "Chishui", "Fanjingshan", "Zhenyuan", "Kaili", "Rongjiang",
    ],
    "united-states": [
        "Glacier National Park", "Yellowstone", "Grand Canyon Village",
        "Zion", "Bryce Canyon", "Arches", "Canyonlands", "Capitol Reef",
        "Olympic Peninsula", "San Juan Islands", "Whidbey Island",
        "Orcas Island", "Bainbridge Island", "Astoria Oregon", "Hood River",
        "Crater Lake", "Joseph Oregon", "McCall Idaho", "Sun Valley Idaho",
        "Coeur d'Alene", "Sandpoint Idaho", "Flathead Lake", "Helena",
        "Livingston Montana", "Red Lodge", "Cody Wyoming", "Sheridan Wyoming",
        "Deadwood South Dakota", "Badlands", "Theodore Roosevelt",
        "Duluth Minnesota", "Bayfield Wisconsin", "Minocqua",
        "Petoskey Michigan", "Sleeping Bear Dunes", "Pictured Rocks",
        "Put-in-Bay Ohio", "Hocking Hills", "Brown County Indiana",
        "Eureka Springs", "Mountain View Arkansas", "Natchez Mississippi",
        "Oxford Mississippi", "Beaufort South Carolina", "Bluffton",
        "Amelia Island", "Cedar Key", "Apalachicola", "Destin",
        "Rosemary Beach", "Seaside Florida", "Anna Maria Island",
        "Sanibel Island", "Captiva Island", "Marco Island", "Islamorada",
        "Marathon Florida", "St. Augustine", "Fernandina Beach",
        "Jekyll Island", "Cumberland Island", "Tybee Island",
    ],
    "brazil": [
        "Arraial d'Ajuda", "Morro de São Paulo", "Itacaré", "Chapada dos Veadeiros",
        "Alto Paraíso", "Pirenópolis", "Brotas", "São Thomé das Letras",
        "Monte Verde", "Visconde de Mauá", "Penedo", "Tiradentes",
        "São João del-Rei", "Diamantina", "Conceição do Mato Dentro",
        "Alter do Chão", "Jalapão", "São Miguel dos Milagres",
        "Praia do Gunga", "Praia dos Carneiros",
    ],
    "mexico": [
        "Real de Catorce", "Bernal", "Tepoztlán", "Tlacotalpan", "Pátzcuaro",
        "Isla Holbox", "Tulum", "Valladolid", "Izamal", "Celestún",
        "Palenque", "Bonampak", "Hierve el Agua", "Monte Albán", "Mitla",
        "El Rosario", "Creel", "Batopilas", "El Fuerte", "Alamos",
    ],
    "russia": [
        "Sergiev Posad", "Pskov", "Petrozavodsk", "Vologda", "Kostroma",
        "Pereslavl-Zalessky", "Rostov Veliky", "Uglich", "Myshkin", "Plyos",
    ],
    "turkey": [
        "Amasya", "Malatya", "Bitlis", "Siirt", "Batman Turkey",
        "Antakya", "Tarsus", "Selçuk", "Pergamon", "Aphrodisias",
    ],
    "indonesia": [
        "Sumba", "Wakatobi", "Derawan", "Togean Islands", "Weh Island",
        "Tana Toraja", "Ende", "Maumere", "Ruteng", "Bajawa",
    ],
    "thailand": [
        "Trat", "Ubon Ratchathani", "Surin", "Nakhon Phanom", "Mukdahan",
        "Phetchaburi", "Prachuap Khiri Khan", "Rayong", "Samet Island", "Koh Kood",
    ],
    "vietnam": [
        "Ha Giang", "Cao Bang", "Ban Gioc", "Tam Coc", "Cat Ba Island",
        "Con Dao", "Ly Son Island", "Phong Nha", "Bach Ma", "A Luoi",
    ],
    "malaysia": [
        "Taiping", "Kuala Terengganu", "Kota Bharu", "Taman Negara",
        "Miri", "Sibu", "Sandakan", "Semporna", "Sipadan",
    ],
    "philippines": [
        "Siquijor", "Apo Island", "Bantayan Island", "Malapascua", "Camiguin",
        "Surigao", "Bucas Grande", "Kalanggaman Island", "Batanes", "Caramoan",
    ],
    "colombia": [
        "Salento", "Jardín", "Guatapé", "Barichara", "Villa de Leyva",
        "Mompox", "Providencia", "Capurganá", "Tatacoa Desert", "Desierto de la Tatacoa",
    ],
    "peru": [
        "Ollantaytambo", "Pisac", "Moray", "Maras", "Chinchero",
        "Colca Valley", "Puno", "Taquile Island", "Amantani", "Huacachina",
    ],
    "new-zealand": [
        "Franz Josef", "Fox Glacier", "Abel Tasman", "Coromandel", "Raglan",
        "New Plymouth", "Waitomo", "Tongariro", "Gisborne", "Napier",
    ],
    "australia": [
        "Noosa", "Airlie Beach", "Whitsundays", "Port Douglas", "Mission Beach",
        "Kangaroo Island", "Barossa Valley", "McLaren Vale", "Victor Harbor", "Port Augusta",
        "Coober Pedy", "Kakadu", "Litchfield", "Arnhem Land", "Katherine",
    ],
    "canada": [
        "Mont Tremblant", "Tadoussac", "Baie-Saint-Paul", "Percé", "Gaspé",
        "Lunenburg", "Mahone Bay", "Peggy's Cove", "Cabot Trail", "Bay of Fundy",
    ],
    "switzerland": [
        "Appenzell", "Engelberg", "Lauterbrunnen", "Wengen", "Mürren",
        "Gimmelwald", "Brienz", "Spiez", "Ascona", "Locarno",
    ],
    "austria": [
        "Bregenz", "Feldkirch", "Wörthersee", "Villach", "Lienz",
        "Schladming", "Leoben", "Steyr", "Wels", "St. Pölten",
    ],
    "portugal": [
        "Tavira", "Olhão", "Loulé", "Silves", "Sagres",
        "Nazaré", "Peniche", "Ericeira", "Tomar", "Batalha",
    ],
    "norway": [
        "Reine", "Henningsvær", "Kabelvåg", "Andenes", "Sortland",
        "Harstad", "Finnsnes", "Alta", "Hammerfest", "Honningsvåg",
    ],
    "sweden": [
        "Abisko", "Jokkmokk", "Östersund", "Mora", "Falun",
        "Borlänge", "Sundsvall", "Kramfors", "Örnsköldsvik", "Skellefteå",
    ],
    "finland": [
        "Savonlinna", "Porvoo", "Rauma", "Naantali", "Hanko",
        "Mariehamn", "Kuusamo", "Levi", "Saariselkä", "Inari",
    ],
    "denmark": [
        "Skagen", "Ribe", "Sønderborg", "Nyborg", "Svendborg",
        "Maribo", "Bornholm", "Faroe Islands", "Tórshavn", "Klaksvík",
    ],
    "ireland": [
        "Clifden", "Connemara", "Aran Islands", "Dingle Peninsula", "Ring of Kerry",
        "Kenmare", "Cobh", "Kinsale", "Blarney", "Cashel",
    ],
    "iceland": [
        "Seyðisfjörður", "Ísafjörður", "Egilsstaðir", "Stykkishólmur", "Snæfellsnes",
        "Landmannalaugar", "Skógar", "Höfn", "Djúpivogur", "Borgarfjörður",
    ],
    "saudi-arabia": [
        "Yanbu", "Jizan", "Al Baha", "Hail", "Najran",
        "Diriyah", "King Abdullah Economic City", "Umluj", "Farasan Islands", "Al Ahsa",
    ],
    "united-arab-emirates": [
        "Hatta", "Khorfakkan", "Dibba", "Jebel Jais", "Liwa Oasis",
    ],
    "jordan": [
        "Ajloun", "Umm Qais", "Dana Nature Reserve", "Shobak", "Aqaba Marine Park",
    ],
    "oman": [
        "Wahiba Sands", "Jebel Akhdar", "Jebel Shams", "Ras al Jinz", "Dhofar",
    ],
    "lebanon": [
        "Deir el Qamar", "Bcharre", "The Cedars", "Aanjar", "Batroun",
    ],
    "nepal": [
        "Tansen", "Gorkha", "Manang", "Mustang", "Ilam",
        "Dhankuta", "Lukla", "Namche Bazaar", "Dhulikhel", "Panauti",
    ],
    "sri-lanka": [
        "Polonnaruwa", "Dambulla", "Habarana", "Unawatuna", "Tangalle",
        "Arugam Bay", "Batticaloa", "Bentota", "Hikkaduwa", "Matara",
    ],
    "cambodia": [
        "Koh Rong", "Koh Rong Samloem", "Mondulkiri", "Ratanakiri", "Koh Kong",
    ],
    "laos": [
        "Thakhek", "Phonsavan", "Plain of Jars", "Nong Khiaw", "Muang Ngoi",
    ],
    "myanmar": [
        "Hsipaw", "Kalaw", "Pyin Oo Lwin", "Mrauk U", "Hpa-An",
    ],
    "cuba": [
        "Playa Girón", "Soroa", "Las Terrazas", "Cayo Santa María", "Gibara",
    ],
    "costa-rica": [
        "Uvita", "Ojochal", "Bahía Drake", "Carate", "Montezuma",
    ],
    "ecuador": [
        "Mindo", "Cotopaxi", "Tena", "Misahuallí", "Vilcabamba",
        "Montañita", "Puerto López", "Isla de la Plata", "Ingapirca", "Cajas",
    ],
    "bolivia": [
        "Tiwanaku", "Coroico", "Sorata", "Torotoro", "Noel Kempff",
    ],
    "chile": [
        "Pucón", "Frutillar", "Puerto Varas", "Chiloé", "Coyhaique",
        "Villa O'Higgins", "Humberstone", "Arica", "Valle de Elqui", "La Serena",
    ],
    "argentina": [
        "Cafayate", "Quebrada de Humahuaca", "Tilcara", "Purmamarca", "Cachi",
        "El Bolsón", "Esquel", "Los Glaciares", "Perito Moreno", "Peninsula Valdés",
    ],
    "kenya": [
        "Ol Pejeta", "Solio Ranch", "Lake Baringo", "Lake Bogoria", "Marsabit",
    ],
    "tanzania": [
        "Lake Natron", "Ol Doinyo Lengai", "Mahale", "Gombe", "Saadani",
    ],
    "south-africa": [
        "Drakensberg", "Wild Coast", "Cederberg", "West Coast", "Namaqualand",
        "Langebaan", "Paternoster", "Prince Albert", "Montagu", "Swellendam",
    ],
    "namibia": [
        "Kolmanskop", "Spitzkoppe", "Damaraland", "Caprivi Strip", "Waterberg",
    ],
    "botswana": [
        "Savuti", "Moremi", "Central Kalahari", "Kubu Island", "Linyanti",
    ],
    "ethiopia": [
        "Harar", "Axum", "Tigray", "Simien Mountains", "Omo Valley",
    ],
    "morocco": [
        "Dades Valley", "Skoura", "Aït Benhaddou", "Tafraoute", "Legzira",
    ],
    "tunisia": [
        "Sidi Bou Said", "El Jem", "Matmata", "Chott el Jerid", "Tabarka",
    ],
    "egypt": [
        "White Desert", "Black Desert", "Bahariya Oasis", "Kharga Oasis", "Dakhla Oasis",
    ],
    "pakistan": [
        "Fairy Meadows", "Deosai Plains", "Attabad Lake", "Phander Valley", "Naltar Valley",
    ],
    "bangladesh": [
        "Sundarbans", "Rangamati", "Bandarban", "Sajek Valley", "Saint Martin Island",
    ],
    "iran": [
        "Persepolis", "Pasargadae", "Naqsh-e Jahan Square", "Abyaneh", "Meybod",
    ],
    "uzbekistan": [
        "Shakhrisabz", "Nurata", "Aydarkul", "Muynak", "Chimgan",
    ],
    "kazakhstan": [
        "Charyn Canyon", "Kolsai Lakes", "Big Almaty Lake", "Baikonur", "Mangystau",
    ],
    "mongolia": [
        "Tsenkher Hot Springs", "Orkhon Valley", "Amarbayasgalant", "Hustai", "Khovsgol Lake",
    ],
}


def _clamp(v: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, v))


def seed():
    """Seed ~5000 cities into software_registry with registry='city'."""
    session = get_session()

    # ── Step 1: Load country trust_scores from DB ────────────────────────────
    log.info("Loading country trust_scores from DB...")
    rows = session.execute(text(
        "SELECT slug, trust_score FROM software_registry WHERE registry = 'country' AND trust_score IS NOT NULL"
    )).fetchall()
    country_scores = {r[0]: r[1] for r in rows}
    log.info(f"Found {len(country_scores)} countries with trust_scores in DB")

    if not country_scores:
        log.error("No countries found in DB! Seed countries first.")
        return

    # Fallback score for countries not in DB
    DEFAULT_COUNTRY_SCORE = 55

    inserted = 0
    skipped = 0
    batch = 0
    BATCH_SIZE = 500

    def _do_insert(name, slug, country_slug, score_adj, description, is_king):
        nonlocal inserted, skipped, batch
        country_score = country_scores.get(country_slug, DEFAULT_COUNTRY_SCORE)
        score = _clamp(int(round(country_score + score_adj)))
        grade = _grade(score)

        try:
            session.execute(text("""
                INSERT INTO software_registry
                    (name, slug, registry, description, trust_score, trust_grade,
                     is_king, enriched_at, created_at)
                VALUES
                    (:name, :slug, 'city', :desc, :score, :grade,
                     :is_king, NOW(), NOW())
                ON CONFLICT (registry, slug) DO UPDATE SET
                    trust_score = EXCLUDED.trust_score,
                    trust_grade = EXCLUDED.trust_grade,
                    description = EXCLUDED.description,
                    is_king = EXCLUDED.is_king,
                    enriched_at = NOW()
            """), {
                "name": name,
                "slug": slug,
                "desc": description,
                "score": score,
                "grade": grade,
                "is_king": is_king,
            })
            inserted += 1
            batch += 1
        except Exception as e:
            log.warning(f"  SKIP {slug}: {e}")
            session.rollback()
            skipped += 1
            return

        if batch >= BATCH_SIZE:
            session.commit()
            log.info(f"  Committed batch — {inserted} total inserts so far")
            batch = 0

    # ── Step 2: Insert tourist cities (is_king=True) ─────────────────────────
    log.info("Inserting tourist cities (~200 is_king=True)...")
    seen_slugs = set()
    for slug, (name, country_slug, adj, desc, is_king) in TOURIST_CITIES.items():
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        _do_insert(name, slug, country_slug, adj, desc, is_king)

    tourist_count = inserted
    log.info(f"Tourist cities done: {tourist_count} inserted")

    # ── Step 3: Insert capitals ──────────────────────────────────────────────
    log.info("Inserting capitals...")
    for country_slug, (cap_name, cap_slug) in CAPITALS.items():
        if cap_slug in seen_slugs:
            continue
        seen_slugs.add(cap_slug)
        # Auto-generate description and small random adjustment
        adj = random.randint(-3, 3)
        desc = f"{cap_name} is the capital of {country_slug.replace('-', ' ').title()}."
        _do_insert(cap_name, cap_slug, country_slug, adj, desc, False)

    capital_count = inserted - tourist_count
    log.info(f"Capitals done: {capital_count} inserted (non-tourist)")

    # ── Step 4: Insert secondary cities ──────────────────────────────────────
    log.info("Inserting secondary cities...")
    secondary_start = inserted

    all_secondary = {}
    all_secondary.update(SECONDARY_CITIES)
    all_secondary.update(SMALL_COUNTRY_CITIES)
    # Merge IS_X_SAFE_CITIES and EXTRA_WORLD_CITIES (append, don't overwrite)
    for extra_dict in [IS_X_SAFE_CITIES, EXTRA_WORLD_CITIES]:
        for k, v in extra_dict.items():
            if k in all_secondary:
                all_secondary[k] = all_secondary[k] + v
            else:
                all_secondary[k] = v

    for country_slug, cities in all_secondary.items():
        for city_name in cities:
            slug = _slugify(city_name)
            # Avoid duplicates if city already appeared as tourist or capital
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            adj = random.randint(-5, 3)
            country_display = country_slug.replace("-", " ").title()
            desc = f"{city_name} is a city in {country_display}."
            _do_insert(city_name, slug, country_slug, adj, desc, False)

    secondary_count = inserted - secondary_start
    log.info(f"Secondary cities done: {secondary_count} inserted")

    # ── Step 5: Final commit ─────────────────────────────────────────────────
    if batch > 0:
        session.commit()

    log.info(f"=== DONE ===")
    log.info(f"Total inserted/updated: {inserted}")
    log.info(f"  Tourist (is_king): {tourist_count}")
    log.info(f"  Capitals: {capital_count}")
    log.info(f"  Secondary: {secondary_count}")
    log.info(f"  Skipped: {skipped}")

    # Verify total
    total = session.execute(text(
        "SELECT COUNT(*) FROM software_registry WHERE registry = 'city'"
    )).scalar()
    log.info(f"Total cities in DB: {total}")

    session.close()


if __name__ == "__main__":
    seed()
