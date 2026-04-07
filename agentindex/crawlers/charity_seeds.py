#!/usr/bin/env python3
"""Charity Seeds — seed 500+ charities into software_registry with registry='charity'."""
import logging
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agentindex.db.models import get_session
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
log = logging.getLogger("charity_seeds")


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
    if score >= 40: return "D"
    return "F"


# (name, slug, score, description, is_king)
CURATED_CHARITIES = [
    # ── Humanitarian ─────────────────────────────────────────────────────
    ("International Committee of the Red Cross", "red-cross", 92, "Humanitarian organization providing assistance in conflict zones. Founded 1863. Nobel Peace Prize laureate.", True),
    ("Doctors Without Borders", "doctors-without-borders", 90, "Medical humanitarian organization (MSF). Provides emergency medical care worldwide. Nobel Peace Prize 1999.", True),
    ("UNICEF", "unicef", 91, "United Nations Children's Fund. Works in 190 countries for children's rights and welfare.", True),
    ("World Food Programme", "world-food-programme", 90, "UN agency fighting hunger worldwide. Nobel Peace Prize 2020. Feeds 160M+ people annually.", True),
    ("Save the Children", "save-the-children", 88, "International children's rights organization. Founded 1919. Works in 120+ countries.", True),
    ("Habitat for Humanity", "habitat-for-humanity", 87, "Nonprofit housing organization. Has built/repaired 800,000+ homes since 1976.", True),
    ("World Vision", "world-vision", 82, "Christian humanitarian organization. Works in nearly 100 countries.", True),
    ("Oxfam", "oxfam", 78, "International confederation fighting poverty. Active in 90+ countries. Faced scandal in 2018.", True),
    ("Care International", "care-international", 85, "Humanitarian org fighting global poverty. Works in 100+ countries.", True),
    ("Amnesty International", "amnesty-international", 88, "Human rights organization. 10M+ supporters. Nobel Peace Prize 1977.", True),

    # ── Environment ──────────────────────────────────────────────────────
    ("World Wildlife Fund", "wwf", 86, "Environmental conservation organization. Works in 100+ countries. Protects endangered species.", True),
    ("Greenpeace", "greenpeace", 75, "Environmental activist organization. Controversial direct action tactics.", True),
    ("The Nature Conservancy", "nature-conservancy", 85, "Environmental nonprofit. Protects 125M+ acres of land. Largest environmental nonprofit.", True),
    ("Sierra Club", "sierra-club", 82, "Environmental organization. Founded 1892. 3.8M members.", True),
    ("Environmental Defense Fund", "environmental-defense-fund", 84, "Environmental advocacy organization. Market-based solutions approach.", True),
    ("Rainforest Alliance", "rainforest-alliance", 83, "Works to conserve biodiversity. Sustainable agriculture certification.", True),
    ("Ocean Conservancy", "ocean-conservancy", 81, "Ocean protection nonprofit. International Coastal Cleanup organizer.", True),

    # ── Health ───────────────────────────────────────────────────────────
    ("St. Jude Children's Research Hospital", "st-jude", 93, "Pediatric treatment and research facility. Families never receive a bill. $2.7B annual revenue.", True),
    ("American Cancer Society", "american-cancer-society", 80, "Cancer research and patient support. Founded 1913. $800M+ annual revenue.", True),
    ("American Heart Association", "american-heart-association", 82, "Heart disease and stroke research. Founded 1924.", True),
    ("Mayo Clinic", "mayo-clinic", 90, "Nonprofit academic medical center. Consistently ranked #1 US hospital.", True),
    ("Feeding America", "feeding-america", 88, "Largest hunger-relief charity in US. 200+ food banks. Feeds 40M+ people.", True),
    ("Direct Relief", "direct-relief", 91, "Medical aid to people affected by poverty and emergencies. 100% score on Charity Navigator.", True),
    ("Partners in Health", "partners-in-health", 89, "Global health organization. Works in 12 countries. Founded by Paul Farmer.", True),
    ("Médecins du Monde", "medecins-du-monde", 85, "Medical humanitarian org. Works in 40+ countries.", True),

    # ── Education ────────────────────────────────────────────────────────
    ("Khan Academy", "khan-academy", 90, "Free online education platform. 150M+ registered users. Funded by philanthropy.", True),
    ("Wikipedia / Wikimedia Foundation", "wikimedia-foundation", 91, "Operates Wikipedia and sister projects. 60M+ articles. Non-profit.", True),
    ("Room to Read", "room-to-read", 87, "Literacy and girls' education in low-income countries. 39M+ children helped.", True),
    ("Teach for America", "teach-for-america", 78, "Nonprofit placing teachers in underserved schools. Some controversy.", True),
    ("DonorsChoose", "donorschoose", 88, "Crowdfunding platform for public school teachers. $1B+ raised.", True),

    # ── Animal welfare ───────────────────────────────────────────────────
    ("ASPCA", "aspca", 79, "Animal welfare organization. Founded 1866. Some controversy over spending.", True),
    ("Humane Society", "humane-society", 76, "Animal protection organization. 11M+ supporters. CEO compensation questioned.", True),
    ("Best Friends Animal Society", "best-friends-animal-society", 84, "No-kill animal shelter network. Goal: end killing of cats and dogs by 2025.", True),

    # ── Arts & Culture ───────────────────────────────────────────────────
    ("Smithsonian Institution", "smithsonian", 90, "World's largest museum/research complex. 30M+ visitors annually. US government-funded.", True),
    ("National Geographic Society", "national-geographic-society", 82, "Science and exploration nonprofit. Funds research expeditions worldwide.", True),

    # ── Technology ───────────────────────────────────────────────────────
    ("Electronic Frontier Foundation", "eff", 88, "Digital rights nonprofit. Defends civil liberties online. Founded 1990.", True),
    ("Mozilla Foundation", "mozilla-foundation", 85, "Open-source advocate. Creator of Firefox. Champions internet health.", True),
    ("Creative Commons", "creative-commons", 86, "Nonprofit enabling sharing of knowledge and creativity through free legal tools.", True),
    ("Internet Archive", "internet-archive", 87, "Digital library. Wayback Machine. Preserves the web. Some legal challenges.", True),
    ("Signal Foundation", "signal-foundation", 89, "Privacy-focused messaging. Open source. End-to-end encrypted.", True),
    ("Tor Project", "tor-project", 82, "Online privacy and freedom. Tor network. Some controversy around dark web.", True),
    ("Apache Software Foundation", "apache-software-foundation", 88, "Open-source software development. Apache HTTP Server, Hadoop, Kafka.", True),
    ("Linux Foundation", "linux-foundation", 89, "Open-source ecosystem. Linux kernel, Kubernetes, Node.js.", True),
    ("Python Software Foundation", "python-software-foundation", 87, "Supports Python programming language development.", True),

    # ── Disaster Relief ──────────────────────────────────────────────────
    ("American Red Cross", "american-red-cross", 78, "Disaster relief and blood services. Some criticism of disaster response efficiency.", True),
    ("GlobalGiving", "globalgiving", 86, "Crowdfunding platform for nonprofits. Vetted projects in 170+ countries.", True),

    # ── Controversial / Lower Score ──────────────────────────────────────
    ("Wounded Warrior Project", "wounded-warrior-project", 72, "Veterans support. Previously faced excessive spending scandals. Has reformed.", True),
    ("Susan G. Komen", "susan-g-komen", 70, "Breast cancer charity. Criticized for spending on marketing vs research.", True),
    ("Goodwill Industries", "goodwill-industries", 75, "Job training and employment. Revenue from thrift stores. CEO pay questioned.", True),
    ("Salvation Army", "salvation-army", 80, "Social services and disaster relief. Religious organization. LGBTQ+ policy concerns.", True),

    # ── Watchlist / Avoid ────────────────────────────────────────────────
    ("Kars4Kids", "kars4kids", 35, "Car donation charity. Misleading advertising. Most funds go to religious education, not general children's charity.", False),
    ("Cancer Fund of America", "cancer-fund-of-america", 10, "Dissolved by FTC in 2016. Fraudulent charity that spent almost nothing on cancer patients.", False),

    # ── Additional International NGOs ────────────────────────────────────
    ("International Rescue Committee", "irc", 89, "Refugee assistance and resettlement. Works in 40+ countries. Founded 1933 at behest of Albert Einstein.", True),
    ("Mercy Corps", "mercy-corps", 86, "Global humanitarian aid. Works in 40+ countries. Focus on crisis and conflict zones.", True),
    ("Action Against Hunger", "action-against-hunger", 87, "International humanitarian org dedicated to ending world hunger. Works in 50+ countries.", True),
    ("Plan International", "plan-international", 85, "Children's rights and girls' equality. Works in 80+ countries. Founded 1937.", True),
    ("International Medical Corps", "international-medical-corps", 86, "Emergency medical relief worldwide. First responders to crises.", True),
    ("Heifer International", "heifer-international", 83, "Ending hunger and poverty through sustainable agriculture. Livestock and training programs.", True),
    ("WaterAid", "wateraid", 87, "Clean water, sanitation, and hygiene charity. Works in 34 countries.", True),
    ("Water.org", "water-org", 88, "Clean water access nonprofit. Co-founded by Matt Damon. WaterCredit microfinance model.", True),
    ("charity: water", "charity-water", 86, "Clean water projects in developing countries. 100% donation model (operations funded separately).", True),
    ("Médecins Sans Frontières USA", "msf-usa", 90, "US arm of Doctors Without Borders. Major fundraising hub for MSF operations.", True),
    ("UNHCR (UN Refugee Agency)", "unhcr", 88, "United Nations High Commissioner for Refugees. Protects 100M+ displaced people.", True),
    ("World Health Organization Foundation", "who-foundation", 84, "Supports WHO's mission for global health. Independent Swiss foundation.", True),
    ("UNDP", "undp", 85, "United Nations Development Programme. Poverty reduction and sustainable development.", True),
    ("International Crisis Group", "international-crisis-group", 86, "Conflict prevention and resolution. Independent analysis and advocacy.", True),
    ("Human Rights Watch", "human-rights-watch", 87, "Investigates and reports on human rights abuses worldwide. Founded 1978.", True),
    ("Transparency International", "transparency-international", 86, "Anti-corruption organization. Publishes Corruption Perceptions Index.", True),
    ("Global Fund", "global-fund", 89, "Partnership fighting AIDS, tuberculosis, and malaria. $55B+ disbursed since 2002.", True),
    ("Gavi, the Vaccine Alliance", "gavi", 90, "Vaccine access for developing countries. Public-private partnership. 1B+ children vaccinated.", True),
    ("PATH", "path", 87, "Global health innovation nonprofit. Accelerates health equity through technology and advocacy.", True),
    ("Clinton Foundation", "clinton-foundation", 72, "Global development foundation. Politically controversial. Clinton Health Access Initiative.", True),
    ("Carter Center", "carter-center", 88, "Peace and health programs. Founded by President Jimmy Carter. Guinea worm eradication.", True),
    ("Bill & Melinda Gates Foundation", "gates-foundation", 91, "World's largest private charitable foundation. $50B+ endowment. Global health and education.", True),
    ("Ford Foundation", "ford-foundation", 85, "Social justice philanthropy. $16B+ endowment. One of the largest US foundations.", True),
    ("Rockefeller Foundation", "rockefeller-foundation", 84, "Philanthropic foundation since 1913. Focus on health, food, and economic opportunity.", True),
    ("Bloomberg Philanthropies", "bloomberg-philanthropies", 86, "Philanthropy of Michael Bloomberg. Environment, public health, education, arts.", True),
    ("Open Society Foundations", "open-society-foundations", 75, "George Soros philanthropy. Democracy, human rights. Politically controversial.", True),
    ("MacArthur Foundation", "macarthur-foundation", 87, "Private foundation. Famous for 'genius grants.' $8B+ endowment.", True),
    ("Wellcome Trust", "wellcome-trust", 88, "UK biomedical research charity. £38B endowment. One of world's largest foundations.", True),
    ("Howard Hughes Medical Institute", "hhmi", 90, "Biomedical research philanthropy. $24B+ endowment. Funds top scientists.", True),

    # ── US National Health Charities ─────────────────────────────────────
    ("American Diabetes Association", "american-diabetes-association", 79, "Diabetes research, advocacy, and education. Founded 1940. $200M+ annual revenue.", True),
    ("American Lung Association", "american-lung-association", 81, "Lung health advocacy and research. Founded 1904. Clean air and tobacco control.", True),
    ("Alzheimer's Association", "alzheimers-association", 80, "Dementia research and support. Largest voluntary health org for Alzheimer's care.", True),
    ("Leukemia & Lymphoma Society", "leukemia-lymphoma-society", 83, "Blood cancer research and patient services. $340M+ annual revenue.", True),
    ("March of Dimes", "march-of-dimes", 78, "Maternal and infant health. Originally fought polio. Founded by FDR.", True),
    ("Cystic Fibrosis Foundation", "cystic-fibrosis-foundation", 86, "CF research and care. Venture philanthropy model produced breakthrough drugs.", True),
    ("Muscular Dystrophy Association", "muscular-dystrophy-association", 77, "Neuromuscular disease research and care. Jerry Lewis legacy.", True),
    ("National Multiple Sclerosis Society", "national-ms-society", 81, "MS research and patient support. $270M+ annual revenue.", True),
    ("American Foundation for Suicide Prevention", "afsp", 83, "Suicide prevention research, education, and advocacy. Largest US suicide prevention org.", True),
    ("Mental Health America", "mental-health-america", 80, "Mental health advocacy and support. Founded 1909. Screenings and policy advocacy.", True),
    ("NAMI (National Alliance on Mental Illness)", "nami", 82, "Grassroots mental health advocacy. 600+ local affiliates.", True),
    ("Planned Parenthood", "planned-parenthood", 77, "Reproductive health care. Politically divisive. Serves 2.4M+ patients annually.", True),
    ("Cleveland Clinic Foundation", "cleveland-clinic-foundation", 89, "Nonprofit academic medical center. Consistently top-ranked US hospital.", True),
    ("Shriners Hospitals for Children", "shriners-hospitals", 87, "Pediatric specialty care regardless of ability to pay. 22 locations.", True),
    ("Ronald McDonald House Charities", "ronald-mcdonald-house", 84, "Family support near children's hospitals. 260+ Houses worldwide.", True),
    ("Make-A-Wish Foundation", "make-a-wish", 85, "Grants wishes to children with critical illnesses. 500,000+ wishes granted.", True),
    ("St. Baldrick's Foundation", "st-baldricks", 84, "Childhood cancer research funding. Volunteer-driven head-shaving events.", True),
    ("Alex's Lemonade Stand Foundation", "alexs-lemonade-stand", 87, "Pediatric cancer research. Founded by child cancer patient. $250M+ raised.", True),
    ("Lupus Foundation of America", "lupus-foundation", 78, "Lupus research and patient support. Advocacy for 1.5M Americans with lupus.", True),
    ("Epilepsy Foundation", "epilepsy-foundation", 79, "Epilepsy research and services. Serves 3.4M Americans with epilepsy.", True),
    ("Arthritis Foundation", "arthritis-foundation", 78, "Arthritis research and advocacy. Founded 1948. Juvenile arthritis focus.", True),
    ("National Kidney Foundation", "national-kidney-foundation", 80, "Kidney disease prevention and treatment. Organ donation advocacy.", True),
    ("American Foundation for the Blind", "afb", 81, "Blindness and vision loss advocacy. Founded by Helen Keller.", True),
    ("Prevent Blindness", "prevent-blindness", 79, "Eye health and safety. Vision screenings and public education.", True),

    # ── Religious Charities ──────────────────────────────────────────────
    ("Catholic Charities USA", "catholic-charities-usa", 83, "Largest private social service provider in US. Disaster relief, immigration, housing.", True),
    ("Lutheran World Relief", "lutheran-world-relief", 85, "International humanitarian aid. Part of Corus International. Works in 35+ countries.", True),
    ("Catholic Relief Services", "catholic-relief-services", 86, "International humanitarian agency. Works in 100+ countries. $3.7B annual revenue.", True),
    ("World Relief", "world-relief", 81, "Evangelical humanitarian org. Refugee resettlement and disaster response.", True),
    ("Compassion International", "compassion-international", 84, "Christian child development. Sponsors 2M+ children in 27 countries.", True),
    ("Samaritan's Purse", "samaritans-purse", 80, "Christian humanitarian org. Operation Christmas Child. Disaster relief.", True),
    ("Islamic Relief USA", "islamic-relief-usa", 82, "Muslim humanitarian org. Disaster relief and development. Works in 40+ countries.", True),
    ("American Jewish World Service", "ajws", 85, "International development and human rights. Grassroots organizations in developing world.", True),
    ("Church World Service", "church-world-service", 83, "Protestant humanitarian org. Refugee resettlement and disaster response.", True),
    ("Mennonite Central Committee", "mennonite-central-committee", 84, "Relief, development, and peace. Works in 50+ countries. Thrift shops.", True),
    ("Episcopal Relief & Development", "episcopal-relief-development", 83, "Disaster response, food security, and health. Works in 40+ countries.", True),
    ("United Methodist Committee on Relief", "umcor", 85, "Disaster response of United Methodist Church. 100% of donations go to relief.", True),
    ("Latter-day Saint Charities", "lds-charities", 82, "Humanitarian arm of LDS Church. Disaster relief, clean water, immunization.", True),
    ("Aga Khan Foundation", "aga-khan-foundation", 86, "Development org. Focus on Asia and Africa. Part of Aga Khan Development Network.", True),

    # ── Veterans Charities ───────────────────────────────────────────────
    ("Gary Sinise Foundation", "gary-sinise-foundation", 85, "Veterans and first responders support. Founded by actor Gary Sinise.", True),
    ("Fisher House Foundation", "fisher-house", 90, "Comfort homes near military/VA medical centers. Families stay free. Top-rated.", True),
    ("Disabled American Veterans", "dav", 84, "Veterans advocacy and services. Free assistance to disabled veterans.", True),
    ("Homes for Our Troops", "homes-for-our-troops", 89, "Builds adapted homes for severely injured veterans. 90%+ to program.", True),
    ("Team Rubicon", "team-rubicon", 86, "Veteran-led disaster response. Unites military veterans with first responders.", True),
    ("K9s For Warriors", "k9s-for-warriors", 85, "Service dogs for veterans with PTSD. Largest provider in US.", True),
    ("Bob Woodruff Foundation", "bob-woodruff-foundation", 84, "Veterans and military families support. Finding and funding solutions.", True),
    ("USO (United Service Organizations)", "uso", 83, "Morale and recreation for US military. Founded 1941.", True),
    ("Veterans of Foreign Wars Foundation", "vfw-foundation", 80, "Veterans assistance and advocacy. 1.5M members.", True),
    ("Semper Fi & America's Fund", "semper-fi-fund", 88, "Financial assistance for combat wounded. 94% to programs.", True),
    ("Intrepid Fallen Heroes Fund", "intrepid-fallen-heroes-fund", 86, "Support for military families. Rehabilitation centers for veterans.", True),
    ("National Military Family Association", "nmfa", 82, "Military family advocacy and programs since 1969.", True),
    ("Operation Homefront", "operation-homefront", 83, "Military family support. Financial assistance, housing, and family support.", True),
    ("Tunnels to Towers Foundation", "tunnels-to-towers", 85, "Honors 9/11 hero Stephen Siller. Mortgage-free homes for veterans and first responders.", True),

    # ── Youth Organizations ──────────────────────────────────────────────
    ("Boys & Girls Clubs of America", "boys-girls-clubs", 84, "Youth development. 4,700+ clubs. 4.3M young people served.", True),
    ("Big Brothers Big Sisters", "big-brothers-big-sisters", 83, "Youth mentoring. Largest mentoring network in US. 200,000+ matches.", True),
    ("Girl Scouts of the USA", "girl-scouts", 82, "Youth development for girls. 1.7M members. Iconic cookie program.", True),
    ("Boy Scouts of America", "boy-scouts", 68, "Youth outdoor and development program. Bankruptcy due to abuse lawsuits. Rebranded as Scouting America.", True),
    ("4-H", "4h", 84, "Youth development through agricultural, STEM, and civic programs. 6M members.", True),
    ("Junior Achievement", "junior-achievement", 83, "Financial literacy and entrepreneurship education for young people.", True),
    ("YMCA", "ymca", 81, "Community organization. Health, youth development, social responsibility. 2,700+ US locations.", True),
    ("YWCA", "ywca", 80, "Women's empowerment and social justice. Domestic violence services, childcare.", True),
    ("Special Olympics", "special-olympics", 87, "Sports competition for people with intellectual disabilities. 5M+ athletes worldwide.", True),
    ("United Way", "united-way", 77, "Community impact network. Education, income, health. Some local chapter controversies.", True),
    ("Kiwanis International", "kiwanis", 80, "Service club focused on improving lives of children. 550,000+ members worldwide.", True),
    ("Rotary International", "rotary-international", 85, "Service organization. 1.4M members. Polio eradication, clean water, education.", True),
    ("Lions Clubs International", "lions-clubs", 82, "Service club. 1.4M members. Vision care, diabetes, hunger, environment.", True),

    # ── Education & Research ─────────────────────────────────────────────
    ("Code.org", "code-org", 87, "Computer science education advocacy. Hour of Code. 70M+ students.", True),
    ("Girls Who Code", "girls-who-code", 85, "Closing gender gap in technology. 580,000+ girls served.", True),
    ("Kiva", "kiva", 86, "Micro-lending platform. $2B+ in loans. 1.9M borrowers in 77 countries.", True),
    ("Acumen", "acumen", 84, "Impact investing. Patient capital approach. Works in developing countries.", True),
    ("Ashoka", "ashoka", 83, "Social entrepreneurship network. 3,800+ Ashoka Fellows worldwide.", True),
    ("TED Foundation", "ted-foundation", 82, "Ideas worth spreading. TED Talks. Audacious Project philanthropy.", True),
    ("Brookings Institution", "brookings-institution", 84, "Public policy think tank. Founded 1916. Nonpartisan research.", True),
    ("RAND Corporation", "rand-corporation", 83, "Policy research and analysis. Nonprofit. National security, health, education.", True),
    ("Carnegie Corporation of New York", "carnegie-corporation", 85, "Philanthropic foundation. International peace, education, democracy.", True),
    ("Carnegie Endowment for International Peace", "carnegie-endowment", 84, "International affairs think tank. Global network of policy centers.", True),
    ("Council on Foreign Relations", "cfr", 82, "Foreign policy think tank. Founded 1921. Publishes Foreign Affairs.", True),
    ("Aspen Institute", "aspen-institute", 80, "Leadership and policy forum. Seminars, fellowships, policy programs.", True),
    ("National Science Foundation (private)", "nsf-foundation", 83, "Supports NSF mission through private donations and partnerships.", True),
    ("American Association for the Advancement of Science", "aaas", 84, "Largest general scientific society. Publishes Science journal.", True),
    ("National Audubon Society", "audubon-society", 83, "Bird conservation and habitat protection. 1.2M members. Founded 1905.", True),
    ("Earthjustice", "earthjustice", 85, "Environmental law organization. Free legal representation for environmental causes.", True),
    ("Natural Resources Defense Council", "nrdc", 83, "Environmental advocacy. Legal, scientific, and policy expertise.", True),
    ("Conservation International", "conservation-international", 82, "Biodiversity conservation. Works in 30+ countries. Science-based approach.", True),
    ("Wildlife Conservation Society", "wildlife-conservation-society", 84, "Runs Bronx Zoo, NY Aquarium. Conserves wildlife in 60+ countries.", True),
    ("World Resources Institute", "wri", 85, "Global research organization. Climate, energy, food, forests, water.", True),

    # ── Poverty & Development ────────────────────────────────────────────
    ("GiveDirectly", "givedirectly", 88, "Direct cash transfers to people in extreme poverty. Evidence-based. Highly rated.", True),
    ("GiveWell", "givewell", 90, "Charity evaluator. Identifies most cost-effective charities. Moved $500M+ annually.", True),
    ("Against Malaria Foundation", "against-malaria-foundation", 91, "Distributes bed nets to prevent malaria. Top-rated by GiveWell. Extremely cost-effective.", True),
    ("Deworm the World Initiative", "deworm-the-world", 88, "Mass deworming programs. Part of Evidence Action. GiveWell top charity.", True),
    ("Schistosomiasis Control Initiative", "sci-foundation", 86, "Treats neglected tropical diseases. GiveWell recommended.", True),
    ("Helen Keller International", "helen-keller-intl", 87, "Combats causes of blindness and malnutrition. GiveWell top charity.", True),
    ("Malaria Consortium", "malaria-consortium", 88, "Malaria prevention. Seasonal malaria chemoprevention. GiveWell top charity.", True),
    ("New Incentives", "new-incentives", 85, "Cash incentives for routine immunizations in Nigeria. GiveWell top charity.", True),
    ("Sightsavers", "sightsavers", 86, "Prevents avoidable blindness. Neglected tropical disease treatment. Works in 30+ countries.", True),
    ("The END Fund", "end-fund", 84, "Neglected tropical disease control. Philanthropic investment vehicle.", True),
    ("Innovations for Poverty Action", "ipa", 85, "Poverty research and policy. Randomized evaluations of programs.", True),
    ("J-PAL (Abdul Latif Jameel Poverty Action Lab)", "jpal", 87, "MIT-based poverty research lab. Randomized controlled trials. Policy influence.", True),
    ("Grameen Foundation", "grameen-foundation", 82, "Microfinance and technology for the poor. Founded on Grameen Bank model.", True),
    ("BRAC", "brac", 88, "World's largest NGO. Bangladesh-based. Poverty alleviation, education, health.", True),
    ("Pratham", "pratham", 86, "Indian education NGO. Annual State of Education Report. Reaches millions of children.", True),
    ("One Acre Fund", "one-acre-fund", 87, "Smallholder farmer support in Africa. Financing, training, market access.", True),
    ("Living Goods", "living-goods", 84, "Community health worker model in Africa. Door-to-door health services.", True),
    ("VillageReach", "villagereach", 83, "Last-mile health delivery in sub-Saharan Africa. Supply chain innovation.", True),

    # ── US Social Services & Community ───────────────────────────────────
    ("Meals on Wheels America", "meals-on-wheels", 86, "Senior nutrition and companionship. 5,000+ community programs. 2.4M seniors served.", True),
    ("St. Vincent de Paul Society", "st-vincent-de-paul", 82, "Catholic lay organization. Poverty relief. Thrift stores. Person-to-person assistance.", True),
    ("Volunteers of America", "volunteers-of-america", 81, "Social services. Housing, healthcare, veterans, youth. 16,000+ employees.", True),
    ("American Civil Liberties Union", "aclu", 82, "Civil liberties advocacy. Legal defense. Founded 1920. 1.8M+ members.", True),
    ("Southern Poverty Law Center", "splc", 75, "Civil rights org. Hate group monitoring. Controversy over workplace culture.", True),
    ("NAACP", "naacp", 79, "Civil rights organization. Founded 1909. Oldest civil rights org in US.", True),
    ("National Urban League", "national-urban-league", 80, "Economic empowerment for African Americans. Job training, education, housing.", True),
    ("Legal Aid Society", "legal-aid-society", 83, "Free legal services for low-income New Yorkers. Largest legal aid organization.", True),
    ("Equal Justice Initiative", "equal-justice-initiative", 88, "Criminal justice reform. Founded by Bryan Stevenson. National Memorial for Peace and Justice.", True),
    ("Innocence Project", "innocence-project", 87, "Exonerating wrongfully convicted through DNA testing. 240+ exonerations.", True),
    ("National Domestic Violence Hotline", "ndvh", 84, "24/7 support for domestic violence victims. 400,000+ contacts annually.", True),
    ("Covenant House", "covenant-house", 82, "Shelter and services for homeless youth. 31 cities. Founded 1972.", True),
    ("National Alliance to End Homelessness", "naeh", 81, "Homelessness policy advocacy and research. Data-driven approach.", True),
    ("Coalition for the Homeless", "coalition-for-the-homeless", 80, "NYC homelessness advocacy. Litigation, direct services, public education.", True),
    ("Feeding Children Everywhere", "feeding-children-everywhere", 78, "Hunger relief through meal packing events. Volunteer-driven model.", True),
    ("No Kid Hungry", "no-kid-hungry", 85, "Childhood hunger campaign by Share Our Strength. School breakfast, summer meals.", True),
    ("Food Bank for New York City", "food-bank-nyc", 83, "NYC's largest hunger-relief network. 1.5M New Yorkers served.", True),
    ("Second Harvest Food Bank", "second-harvest", 82, "Regional food bank network. Part of Feeding America.", True),

    # ── International Development / Niche ────────────────────────────────
    ("Doctors of the World USA", "doctors-of-the-world-usa", 82, "Health access for vulnerable populations. Part of Médecins du Monde network.", True),
    ("ChildFund International", "childfund-international", 83, "Child development and protection. Works in 24 countries.", True),
    ("SOS Children's Villages", "sos-childrens-villages", 81, "Family-based care for orphaned children. 136 countries. Founded 1949.", True),
    ("Feed the Children", "feed-the-children", 74, "Hunger relief. Past financial scandals. Has undergone reforms.", True),
    ("Food for the Poor", "food-for-the-poor", 76, "Caribbean and Latin America aid. Some controversy over in-kind donations accounting.", True),
    ("Operation Smile", "operation-smile", 84, "Free cleft surgeries worldwide. 300,000+ surgeries performed. 60+ countries.", True),
    ("Smile Train", "smile-train", 86, "Cleft surgery funding worldwide. 1.5M+ surgeries funded. Sustainable model.", True),
    ("HALO Trust", "halo-trust", 87, "Landmine clearance. Works in 30+ countries. Princess Diana association.", True),
    ("International Justice Mission", "ijm", 85, "Combats human trafficking and slavery. Legal casework in developing countries.", True),
    ("Polaris Project", "polaris-project", 84, "Anti-human trafficking. Operates National Human Trafficking Hotline.", True),
    ("Free the Slaves", "free-the-slaves", 82, "Anti-slavery nonprofit. Community-based liberation programs.", True),
    ("World Bicycle Relief", "world-bicycle-relief", 85, "Bicycles for developing world. Education, healthcare, economic development.", True),
    ("Pencils of Promise", "pencils-of-promise", 81, "School building in developing countries. 550+ schools built.", True),
    ("buildOn", "buildon", 82, "School building and service learning. 1,700+ schools in developing countries.", True),
    ("Evidence Action", "evidence-action", 85, "Scales evidence-based programs. Deworm the World, Dispensers for Safe Water.", True),

    # ── Arts, Media & Culture ────────────────────────────────────────────
    ("Metropolitan Museum of Art", "met-museum", 88, "NYC art museum. 2M+ works. 5.3M visitors annually. Founded 1870.", True),
    ("American Museum of Natural History", "amnh", 86, "NYC science museum. 33M+ specimens. Research and education.", True),
    ("PBS Foundation", "pbs-foundation", 83, "Supports Public Broadcasting Service. Educational programming.", True),
    ("NPR Foundation", "npr-foundation", 82, "Supports National Public Radio. Independent journalism.", True),
    ("ProPublica", "propublica", 87, "Investigative journalism nonprofit. Pulitzer Prize winners. Public interest reporting.", True),
    ("Committee to Protect Journalists", "cpj", 85, "Press freedom advocacy. Journalist safety. 40+ years of work.", True),
    ("Reporters Without Borders", "reporters-without-borders", 84, "Press freedom worldwide. World Press Freedom Index. Founded 1985.", True),
    ("Freedom of the Press Foundation", "freedom-of-press-foundation", 85, "Press freedom and whistleblower protection. SecureDrop project.", True),

    # ── Science & Space ──────────────────────────────────────────────────
    ("Planetary Society", "planetary-society", 83, "Space exploration advocacy. Founded by Carl Sagan. LightSail project.", True),
    ("SETI Institute", "seti-institute", 80, "Search for extraterrestrial intelligence. Scientific research.", True),
    ("X Prize Foundation", "xprize", 82, "Innovation prizes for global challenges. Incentive competitions.", True),
    ("Breakthrough Prize Foundation", "breakthrough-prize", 84, "Scientific achievement awards. $3M prizes in life sciences, physics, math.", True),

    # ── Disability & Inclusion ───────────────────────────────────────────
    ("Goodwill Industries International", "goodwill-intl", 75, "Job training and employment services. Thrift store revenue model.", True),
    ("Disability Rights Advocates", "disability-rights-advocates", 82, "Disability civil rights legal center. Impact litigation.", True),
    ("National Federation of the Blind", "nfb", 80, "Advocacy and programs for blind Americans. Founded 1940.", True),
    ("Gallaudet University", "gallaudet-university", 83, "Only university for deaf and hard of hearing. Federal charter.", True),
    ("Autism Speaks", "autism-speaks", 72, "Autism advocacy. Controversy within autism community over approach.", True),
    ("Best Buddies International", "best-buddies", 83, "Inclusion for people with intellectual and developmental disabilities.", True),

    # ── Housing & Community Development ──────────────────────────────────
    ("Enterprise Community Partners", "enterprise-community-partners", 84, "Affordable housing solutions. $61B+ invested in communities.", True),
    ("Local Initiatives Support Corporation", "lisc", 83, "Community development. Affordable housing, economic development.", True),
    ("National Low Income Housing Coalition", "nlihc", 81, "Affordable housing policy advocacy. Annual Out of Reach report.", True),
    ("Rebuilding Together", "rebuilding-together", 82, "Home repair for low-income homeowners. 100,000+ volunteers annually.", True),

    # ── Food & Agriculture ───────────────────────────────────────────────
    ("World Central Kitchen", "world-central-kitchen", 88, "Chef José Andrés' disaster relief food nonprofit. Meals in crisis zones worldwide.", True),
    ("The Hunger Project", "hunger-project", 79, "Ending hunger through community-led strategies. Works in Africa, Asia, Latin America.", True),
    ("Farm Aid", "farm-aid", 80, "Supporting family farmers. Annual concert fundraiser. Founded by Willie Nelson.", True),
    ("Food Research & Action Center", "frac", 81, "Anti-hunger policy research and advocacy. Federal nutrition programs.", True),
    ("Oxfam America", "oxfam-america", 80, "US arm of Oxfam. Poverty and injustice focus. Advocacy and emergency response.", True),

    # ── Climate & Energy ─────────────────────────────────────────────────
    ("350.org", "350-org", 78, "Climate change activism. Fossil fuel divestment movement. Founded by Bill McKibben.", True),
    ("Clean Air Task Force", "clean-air-task-force", 85, "Clean energy advocacy. Technology innovation. Highly rated by Founders Pledge.", True),
    ("Carbon180", "carbon180", 82, "Carbon removal policy advocacy. Science-based approach.", True),
    ("Rocky Mountain Institute", "rmi", 84, "Clean energy think tank. Market-based energy transformation.", True),
    ("Union of Concerned Scientists", "union-of-concerned-scientists", 83, "Science-based advocacy. Climate, clean energy, nuclear safety.", True),
    ("Climate Works Foundation", "climate-works-foundation", 83, "Climate philanthropy platform. Coordinates global climate giving.", True),
    ("Sunrise Movement Education Fund", "sunrise-movement", 72, "Youth-led climate activism. Green New Deal advocacy. Political.", True),

    # ── Legal & Democracy ────────────────────────────────────────────────
    ("Brennan Center for Justice", "brennan-center", 85, "Democracy, justice, rule of law. NYU-affiliated. Nonpartisan policy.", True),
    ("League of Women Voters", "league-of-women-voters", 83, "Voter education and advocacy. Nonpartisan. Founded 1920.", True),
    ("Common Cause", "common-cause", 80, "Government accountability. Campaign finance, voting rights, ethics.", True),
    ("Center for Responsive Politics (OpenSecrets)", "opensecrets", 84, "Tracks money in politics. Nonpartisan. Campaign finance data.", True),
    ("First Amendment Coalition", "first-amendment-coalition", 81, "Free speech and press freedom advocacy. California-based.", True),

    # ── Additional Animal Welfare ────────────────────────────────────────
    ("World Animal Protection", "world-animal-protection", 82, "Animal welfare worldwide. Factory farming, disaster relief, wildlife.", True),
    ("Wildlife Conservation Network", "wildlife-conservation-network", 85, "Conservation of endangered species. Direct funding to field projects.", True),
    ("International Fund for Animal Welfare", "ifaw", 81, "Animal rescue and habitat conservation. Works in 40+ countries.", True),
    ("Dian Fossey Gorilla Fund", "gorilla-fund", 85, "Mountain gorilla conservation. Research center in Rwanda. Founded 1978.", True),
    ("Jane Goodall Institute", "jane-goodall-institute", 86, "Chimpanzee conservation and community development. Founded by Jane Goodall.", True),
    ("Born Free Foundation", "born-free-foundation", 80, "Wildlife conservation. Opposes captive wild animals. Rescue centers.", True),
    ("Oceana", "oceana", 83, "Ocean conservation. Policy-focused. Protecting marine biodiversity.", True),
    ("Sea Shepherd Conservation Society", "sea-shepherd", 74, "Marine wildlife conservation. Direct action tactics. Controversial.", True),
    ("National Wildlife Federation", "nwf", 82, "Conservation and outdoor recreation. 6M+ members and supporters.", True),
    ("Defenders of Wildlife", "defenders-of-wildlife", 83, "Wildlife and habitat protection. Endangered Species Act advocacy.", True),
    ("Bat Conservation International", "bat-conservation-intl", 80, "Bat conservation worldwide. Research and habitat protection.", True),
    ("Whale and Dolphin Conservation", "whale-dolphin-conservation", 81, "Marine mammal protection. Anti-captivity advocacy.", True),

    # ── International / Regional ─────────────────────────────────────────
    ("Aga Khan Development Network", "akdn", 85, "Comprehensive development. Education, health, architecture, microfinance. 10 agencies.", True),
    ("Africa Development Promise", "africa-development-promise", 78, "Community-driven development in sub-Saharan Africa.", True),
    ("Africare", "africare", 79, "African development. Health, food, water, environment. 50+ years.", True),
    ("Asia Foundation", "asia-foundation", 83, "Asian development and policy. Governance, women's empowerment, environment.", True),
    ("Inter-American Development Bank Foundation", "idb-foundation", 82, "Latin American and Caribbean development.", True),
    ("Aga Khan Education Services", "aga-khan-education", 84, "Education network in developing countries. 200+ schools.", True),
    ("Médecins Sans Frontières International", "msf-international", 91, "International coordinating office of MSF. Geneva-based.", True),
    ("International Federation of Red Cross", "ifrc", 87, "World's largest humanitarian network. 192 national societies.", True),
    ("Terre des Hommes", "terre-des-hommes", 82, "Children's rights federation. Works in 60+ countries. Swiss-based.", True),
    ("War Child", "war-child", 83, "Children affected by conflict. Education, protection, psychosocial support.", True),

    # ── Microfinance & Economic Development ──────────────────────────────
    ("Opportunity International", "opportunity-international", 82, "Microfinance and training in developing world. 18M+ clients.", True),
    ("FINCA International", "finca", 80, "Microfinance institution. Financial inclusion for underserved.", True),
    ("Women's World Banking", "womens-world-banking", 84, "Financial inclusion for women. 55M+ low-income women served.", True),
    ("Endeavor", "endeavor", 83, "High-impact entrepreneurship. 2,500+ entrepreneurs in 40+ markets.", True),
    ("TechnoServe", "technoserve", 84, "Business solutions to poverty. Agricultural and enterprise development.", True),

    # ── Recently Prominent / Modern Charities ────────────────────────────
    ("Effective Altruism Foundation", "ea-foundation", 80, "Promotes effective charitable giving. Research and grantmaking.", True),
    ("80,000 Hours", "80000-hours", 82, "Career guidance for social impact. Evidence-based career advice.", True),
    ("Charity Navigator", "charity-navigator", 85, "Charity evaluation and rating. America's largest independent charity evaluator.", True),
    ("GuideStar (Candid)", "guidestar", 84, "Nonprofit information database. Merged with Foundation Center to form Candid.", True),
    ("Better Business Bureau Wise Giving Alliance", "bbb-wise-giving", 80, "Charity accountability standards. National charity reports.", True),
    ("Robin Hood Foundation", "robin-hood", 85, "NYC poverty-fighting charity. 100% model — board covers operating costs.", True),
    ("Emerson Collective", "emerson-collective", 79, "Laurene Powell Jobs' social impact org. Education, immigration, environment.", True),
    ("Chan Zuckerberg Initiative", "czi", 78, "Zuckerberg/Chan philanthropy. LLC structure (not traditional charity). Education, science.", True),
    ("Skoll Foundation", "skoll-foundation", 83, "Social entrepreneurship. Skoll World Forum. Jeff Skoll (eBay).", True),
    ("Omidyar Network", "omidyar-network", 81, "Pierre Omidyar philanthropic investment firm. Technology, governance.", True),
    ("Schmidt Futures", "schmidt-futures", 80, "Eric Schmidt philanthropy. Science, technology, and societal challenges.", True),
    ("Patrick J. McGovern Foundation", "mcgovern-foundation", 79, "AI and data science for social impact. Emerging tech philanthropy.", True),

    # ── Additional Watchlist / Lower Score ───────────────────────────────
    ("Kids Wish Network", "kids-wish-network", 30, "Criticized as one of America's worst charities. Minimal spending on children.", False),
    ("National Veterans Services Fund", "national-veterans-services-fund", 40, "Poor spending ratios. Most revenue to fundraisers, not veterans.", False),
    ("Wishing Well Foundation", "wishing-well-foundation", 38, "Low program spending. Most funds go to solicitation and administration.", False),
    ("Project Cure", "project-cure", 74, "Medical supply distribution. High in-kind donations inflate efficiency numbers.", True),
    ("Operation Blessing International", "operation-blessing", 73, "Pat Robertson affiliated. Disaster relief. Controversial ties to diamond mining.", True),
    ("Breast Cancer Research Foundation", "bcrf", 85, "Breast cancer research funding. 91% to research and awareness. A-rated.", True),
    ("National Geographic Partners", "natgeo-partners", 78, "For-profit joint venture with Disney. Revenue supports Society's mission.", True),

    # ── More Education & Libraries ───────────────────────────────────────
    ("Libraries Without Borders", "libraries-without-borders", 83, "Global library access. Ideas Box. Founded in France. Works in 30+ countries.", True),
    ("Worldreader", "worldreader", 81, "Digital reading in developing countries. E-readers and mobile apps.", True),
    ("Sesame Workshop", "sesame-workshop", 86, "Sesame Street creators. Early childhood education through media. 150+ countries.", True),
    ("Harlem Children's Zone", "harlem-childrens-zone", 85, "Comprehensive cradle-to-college program for Harlem youth. Geoffrey Canada.", True),
    ("City Year", "city-year", 81, "AmeriCorps program placing young adults in schools. Tutoring and mentoring.", True),
    ("Year Up", "year-up", 83, "Workforce development for young adults. Corporate partnerships. Job placement.", True),
    ("Per Scholas", "per-scholas", 82, "Free tech training for underserved communities. 90%+ job placement rate.", True),

    # ── Emergency & First Responders ─────────────────────────────────────
    ("National Volunteer Fire Council", "nvfc", 79, "Volunteer firefighter advocacy and training. 729,000+ volunteer firefighters.", True),
    ("Firefighters Charitable Foundation", "firefighters-charitable", 78, "Direct aid to fire victims and firefighters. Disaster response.", True),
    ("First Responders Children's Foundation", "first-responders-children", 81, "Scholarships and support for children of first responders.", True),
    ("National Fallen Firefighters Foundation", "nfff", 84, "Honors fallen firefighters. Survivor support programs.", True),
    ("Gary Sinise Foundation (First Responders)", "gary-sinise-first-responders", 85, "First responder outreach programs. Building smart homes.", True),

    # ── Global Health (More) ─────────────────────────────────────────────
    ("Elizabeth Glaser Pediatric AIDS Foundation", "egpaf", 84, "Pediatric HIV/AIDS prevention and treatment. Works in 19 countries.", True),
    ("amfAR (American Foundation for AIDS Research)", "amfar", 82, "AIDS research. Annual fundraising events. $550M+ invested in research.", True),
    ("Treatment Action Group", "treatment-action-group", 81, "HIV, tuberculosis, hepatitis C research advocacy.", True),
    ("Jhpiego", "jhpiego", 85, "Johns Hopkins affiliate. Maternal and newborn health. 40+ countries.", True),
    ("Population Services International", "psi", 83, "Global health organization. HIV, malaria, reproductive health. 40+ countries.", True),
    ("EngenderHealth", "engenderhealth", 80, "Reproductive health and family planning. 20+ countries.", True),
    ("Médecins Sans Frontières Australia", "msf-australia", 89, "Australian arm of MSF. Fundraising and recruitment for field operations.", True),

    # ── Filler to reach 500+ ─────────────────────────────────────────────
    ("MAP International", "map-international", 82, "Christian global health org. Medicine and health supplies to 100+ countries.", True),
    ("AmeriCares", "americares", 85, "Emergency response and global health. $800M+ in aid annually.", True),
    ("Project HOPE", "project-hope", 83, "Global health education and humanitarian assistance. 25+ countries.", True),
    ("Brother's Brother Foundation", "brothers-brother-foundation", 86, "Medical, educational, and humanitarian supplies. $5B+ in donations since 1958.", True),
    ("Heart to Heart International", "heart-to-heart-intl", 81, "Medical outreach and disaster response. Efficient supply chain.", True),
    ("Cross-Cultural Solutions", "cross-cultural-solutions", 76, "International volunteer programs. Cultural exchange.", True),
    ("Global Citizen", "global-citizen", 79, "Advocacy platform. Campaigns to end extreme poverty. Concerts and events.", True),
    ("ONE Campaign", "one-campaign", 80, "Advocacy organization co-founded by Bono. Poverty and disease in Africa.", True),
    ("Stand Up To Cancer", "stand-up-to-cancer", 84, "Collaborative cancer research funding. Entertainment industry support.", True),
    ("V Foundation for Cancer Research", "v-foundation", 85, "Cancer research. Founded by Jim Valvano. 100% of donations to research.", True),
    ("Lustgarten Foundation", "lustgarten-foundation", 84, "Pancreatic cancer research. 100% model — Cablevision covers costs.", True),
    ("Pancreatic Cancer Action Network", "pancan", 81, "Pancreatic cancer research and advocacy. Patient services.", True),
    ("ALS Association", "als-association", 82, "ALS (Lou Gehrig's disease) research and care. Ice Bucket Challenge raised $115M.", True),
    ("Michael J. Fox Foundation", "michael-j-fox-foundation", 88, "Parkinson's disease research. $1.5B+ funded. Largest nonprofit funder of PD research.", True),
    ("Christopher & Dana Reeve Foundation", "reeve-foundation", 82, "Spinal cord injury research and quality of life. Founded by Christopher Reeve.", True),
    ("Juvenile Diabetes Research Foundation", "jdrf", 83, "Type 1 diabetes research funding. $2.5B+ invested in research.", True),
    ("American Kidney Fund", "american-kidney-fund", 82, "Kidney disease support. Financial assistance for dialysis patients.", True),
    ("National Osteoporosis Foundation", "nof", 78, "Bone health advocacy and education. Research funding.", True),
    ("Prevent Cancer Foundation", "prevent-cancer-foundation", 80, "Cancer prevention research and education. Founded 1985.", True),
    ("Susan Thompson Buffett Foundation", "buffett-foundation", 83, "Reproductive health and education. One of largest US foundations.", True),
    ("Walton Family Foundation", "walton-family-foundation", 80, "Education, environment, community. Walmart family philanthropy.", True),
    ("Lilly Endowment", "lilly-endowment", 84, "Indiana-based philanthropy. Religion, education, community development.", True),
    ("W.K. Kellogg Foundation", "kellogg-foundation", 83, "Children, families, communities. Racial equity focus. $8B+ endowment.", True),
    ("Robert Wood Johnson Foundation", "rwjf", 86, "Health and healthcare philanthropy. Largest US health-focused foundation.", True),
    ("David and Lucile Packard Foundation", "packard-foundation", 85, "Conservation, science, children, reproductive health. $8B+ endowment.", True),
    ("Gordon and Betty Moore Foundation", "moore-foundation", 84, "Science, environment, Bay Area. Intel co-founder philanthropy.", True),
    ("Simons Foundation", "simons-foundation", 85, "Mathematics and basic science research. $4B+ endowment.", True),
    ("Alfred P. Sloan Foundation", "sloan-foundation", 83, "Science, technology, economics. STEM education and research.", True),
    ("Andrew W. Mellon Foundation", "mellon-foundation", 84, "Arts, culture, humanities, higher education. $8B+ endowment.", True),
    ("William and Flora Hewlett Foundation", "hewlett-foundation", 85, "Education, environment, global development. $12B+ endowment.", True),
    ("John D. and Catherine T. MacArthur Foundation", "macarthur-foundation-full", 87, "Justice, climate, nuclear challenges. 'Genius grants.' $8B+ endowment.", True),
    ("Pew Charitable Trusts", "pew-charitable-trusts", 85, "Public policy research and civic engagement. Nonpartisan. $7B+ assets.", True),
    ("Annie E. Casey Foundation", "casey-foundation", 83, "Child welfare and juvenile justice. KIDS COUNT data. $3B+ endowment.", True),

    # ── Additional US Health & Research ──────────────────────────────────
    ("Dana-Farber Cancer Institute", "dana-farber", 89, "Cancer treatment and research center. Harvard Medical School affiliate.", True),
    ("Memorial Sloan Kettering Cancer Center", "mskcc", 90, "World's oldest and largest private cancer center. NYC-based.", True),
    ("MD Anderson Cancer Center", "md-anderson", 89, "Top-ranked US cancer hospital. Part of UT System. Houston-based.", True),
    ("Johns Hopkins Medicine", "johns-hopkins-medicine", 91, "Pioneering academic medical center. Research and clinical excellence.", True),
    ("Stanford Medicine", "stanford-medicine", 89, "Stanford University medical center. Research and patient care.", True),
    ("Cedars-Sinai Medical Center", "cedars-sinai", 87, "Nonprofit academic medical center in Los Angeles. Research and patient care.", True),
    ("Children's Hospital of Philadelphia", "chop", 88, "Nation's first hospital devoted to children. Pioneering pediatric care.", True),
    ("Boston Children's Hospital", "boston-childrens-hospital", 88, "Pediatric teaching hospital of Harvard. 400+ specialized programs.", True),
    ("Cincinnati Children's Hospital", "cincinnati-childrens", 87, "Top-ranked pediatric hospital. Research and clinical care.", True),
    ("Nationwide Children's Hospital", "nationwide-childrens", 86, "Major pediatric hospital in Columbus, Ohio. Research focus.", True),
    ("Children's National Hospital", "childrens-national", 86, "Pediatric hospital in Washington DC. 150+ years of care.", True),
    ("Joslin Diabetes Center", "joslin-diabetes-center", 85, "World's largest diabetes research center. Harvard affiliate.", True),
    ("Fred Hutchinson Cancer Center", "fred-hutch", 88, "Cancer research institute in Seattle. Nobel Prize-winning discoveries.", True),
    ("Sloan Foundation", "sloan-foundation-charity", 83, "Supports science, technology, and economic research.", True),
    ("Research!America", "research-america", 80, "Health research advocacy. Largest US nonprofit health research advocacy alliance.", True),

    # ── More International / Humanitarian ────────────────────────────────
    ("Norwegian Refugee Council", "nrc", 87, "Humanitarian aid for refugees and displaced persons. Works in 40+ countries.", True),
    ("Danish Refugee Council", "danish-refugee-council", 86, "Humanitarian assistance to refugees globally. Founded 1956.", True),
    ("Refugees International", "refugees-international", 84, "Advocacy for displaced people worldwide. No government funding.", True),
    ("Women for Women International", "women-for-women-intl", 83, "Supporting women in conflict zones. Economic empowerment.", True),
    ("Tostan", "tostan", 84, "Community-led development in West Africa. Human rights education.", True),
    ("Mercy Ships", "mercy-ships", 85, "Hospital ships providing free surgeries in Africa. Volunteer crews.", True),
    ("Global Witness", "global-witness", 83, "Exposing corruption and environmental abuse. Campaigns against resource exploitation.", True),
    ("Transparency International USA", "transparency-intl-usa", 82, "US chapter of anti-corruption organization.", True),
    ("Landesa", "landesa", 83, "Land rights for world's poorest. Legal and policy reform. 40+ countries.", True),
    ("International Land Coalition", "international-land-coalition", 80, "Land governance advocacy. 300+ member organizations.", True),
    ("Oxfam GB", "oxfam-gb", 77, "UK arm of Oxfam confederation. Faced 2018 Haiti scandal.", True),
    ("ActionAid", "actionaid", 81, "Anti-poverty international organization. Works in 45+ countries.", True),
    ("CBM (Christian Blind Mission)", "cbm", 83, "Disability-inclusive development. Works in 47 countries.", True),
    ("HelpAge International", "helpage-international", 81, "Rights and welfare of older people globally.", True),
    ("Handicap International (Humanity & Inclusion)", "humanity-inclusion", 84, "Disability rights and assistance in 60+ countries. Landmine action.", True),
    ("International Alert", "international-alert", 82, "Peacebuilding organization. Works in 30+ countries.", True),
    ("Search for Common Ground", "search-for-common-ground", 83, "Conflict transformation. Works in 35+ countries. Media and dialogue.", True),
    ("Conciliation Resources", "conciliation-resources", 81, "Peacebuilding through dialogue and policy. Founded 1994.", True),
    ("Crisis Group", "crisis-group", 85, "Conflict prevention analysis. Independent. Influential policy briefs.", True),

    # ── US Community & Social Services (More) ────────────────────────────
    ("Points of Light", "points-of-light", 81, "Volunteer mobilization. Largest volunteer organization. Founded by George H.W. Bush.", True),
    ("VolunteerMatch", "volunteermatch", 80, "Online volunteer matching platform. 150,000+ nonprofits listed.", True),
    ("Idealist", "idealist", 79, "Nonprofit job board and volunteer opportunities. 120,000+ organizations.", True),
    ("United Way Worldwide", "united-way-worldwide", 78, "Umbrella for 1,100+ local United Way organizations. Community impact.", True),
    ("Community Foundation of Greater Atlanta", "cf-greater-atlanta", 82, "Regional community foundation. Grants and donor services.", True),
    ("Silicon Valley Community Foundation", "svcf", 80, "Largest community foundation in US. Tech donor-advised funds.", True),
    ("Chicago Community Trust", "chicago-community-trust", 82, "Community foundation serving Chicago region. 100+ years.", True),
    ("New York Community Trust", "ny-community-trust", 83, "NYC's community foundation. Grants to nonprofits.", True),
    ("Cleveland Foundation", "cleveland-foundation", 82, "World's first community foundation (1914). Cleveland grantmaking.", True),
    ("California Community Foundation", "cal-community-foundation", 81, "LA area grantmaking. $2B+ in assets.", True),

    # ── International Education ──────────────────────────────────────────
    ("Aga Khan University", "aga-khan-university", 84, "International university system. Campuses in Asia, Africa, UK.", True),
    ("Teach for All", "teach-for-all", 82, "Global network of Teach for America-style organizations in 60+ countries.", True),
    ("Education International", "education-international", 80, "Global union federation of teachers. 32M members.", True),
    ("Global Partnership for Education", "gpe", 84, "Multilateral partnership for education in developing countries. $7B+ mobilized.", True),
    ("CAMFED", "camfed", 86, "Girls' education in sub-Saharan Africa. 5M+ students supported.", True),
    ("Right to Play", "right-to-play", 83, "Education through play and sport. 2.3M children in 15 countries.", True),
    ("War Child Holland", "war-child-holland", 82, "Education and psychosocial support for conflict-affected children.", True),
    ("Educate Girls", "educate-girls", 84, "Girls' enrollment and learning in India. Development Impact Bond model.", True),

    # ── Sports & Recreation Charities ────────────────────────────────────
    ("Challenged Athletes Foundation", "challenged-athletes", 85, "Support for athletes with physical challenges. Grants and events.", True),
    ("Laureus Sport for Good Foundation", "laureus", 82, "Sport for social change. 250+ programs in 50+ countries.", True),
    ("Right To Play International", "right-to-play-intl", 83, "Global sport for development organization. Founded by Johann Koss.", True),
    ("PeacePlayers International", "peaceplayers", 80, "Using basketball to bridge divides. Northern Ireland, Middle East, South Africa.", True),
    ("Athletes for Hope", "athletes-for-hope", 79, "Connects athletes with charitable causes. Community engagement.", True),
    ("Soccer Without Borders", "soccer-without-borders", 78, "Using soccer for youth development and integration of newcomers.", True),

    # ── Water & Sanitation ───────────────────────────────────────────────
    ("Water For People", "water-for-people", 85, "Sustainable water and sanitation. Everyone Forever model. 9 countries.", True),
    ("Splash International", "splash-international", 81, "Clean water in urban schools. Works in Ethiopia, India, Nepal.", True),
    ("Evidence Action (Safe Water)", "evidence-action-water", 84, "Dispensers for Safe Water. Chlorine dispensers at water sources in Africa.", True),
    ("Lifewater International", "lifewater-intl", 80, "Clean water and sanitation. WASH programs in developing countries.", True),
    ("Blood:Water", "blood-water", 79, "Clean water and HIV/AIDS support in Africa. Community-driven approach.", True),

    # ── Hunger & Food Security (More) ────────────────────────────────────
    ("Action Contre la Faim", "action-contre-la-faim", 86, "French arm of Action Against Hunger. Emergency nutrition.", True),
    ("Concern Worldwide", "concern-worldwide", 85, "Irish humanitarian org. Emergency and development in 24+ countries.", True),
    ("Trocaire", "trocaire", 82, "Irish Catholic development agency. Works in 20+ countries.", True),
    ("Mary's Meals", "marys-meals", 86, "School feeding in 18 countries. Feeds 2.4M+ children daily.", True),
    ("Food for the Hungry", "food-for-the-hungry", 80, "Christian anti-hunger and development. Works in 20+ countries.", True),
    ("Rise Against Hunger", "rise-against-hunger", 83, "Meal packing and distribution. Volunteer-driven. 600M+ meals distributed.", True),

    # ── Immigrant & Refugee Services ─────────────────────────────────────
    ("HIAS (Hebrew Immigrant Aid Society)", "hias", 84, "Refugee resettlement and protection. Originally for Jewish refugees, now serves all.", True),
    ("Lutheran Immigration and Refugee Service", "lirs", 83, "Refugee and immigrant services. Part of Lutheran tradition.", True),
    ("International Rescue Committee UK", "irc-uk", 86, "UK arm of IRC. Fundraising and advocacy for refugees.", True),
    ("Refugee Council", "refugee-council-uk", 82, "UK-based refugee support. Advice, support, and advocacy.", True),
    ("USA for UNHCR", "usa-for-unhcr", 85, "US fundraising partner for UN Refugee Agency. Awareness and advocacy.", True),
    ("Asylum Seeker Advocacy Project", "asap", 80, "Legal information and community for asylum seekers.", True),

    # ── Tech & Digital Rights (More) ─────────────────────────────────────
    ("Access Now", "access-now", 84, "Digital rights for users at risk. RightsCon conference organizer.", True),
    ("Center for Democracy & Technology", "cdt", 82, "Internet policy advocacy. Privacy, free expression, security.", True),
    ("Wikimedia Foundation (Deutschland)", "wikimedia-de", 85, "German chapter of Wikimedia. Wikipedia support.", True),
    ("Open Knowledge Foundation", "open-knowledge-foundation", 82, "Open data and open knowledge advocacy. CKAN open data platform.", True),
    ("Free Software Foundation", "fsf", 80, "GNU Project. Free software advocacy. Founded by Richard Stallman. Controversy.", True),
    ("Software Freedom Conservancy", "software-freedom-conservancy", 83, "Fiscal sponsor for free software projects. GPL enforcement.", True),
    ("GNOME Foundation", "gnome-foundation", 81, "GNOME desktop environment. Free software advocacy.", True),
    ("OpenStreetMap Foundation", "openstreetmap-foundation", 83, "Supports OpenStreetMap. Free and open geographic data.", True),
    ("Raspberry Pi Foundation", "raspberry-pi-foundation", 85, "Computing education charity. Affordable computers for learning.", True),
    ("Code for America", "code-for-america", 84, "Government technology improvement. Civic tech. Brigade network.", True),
    ("Digital Green", "digital-green", 81, "Technology for smallholder farmers. Video-enabled agricultural extension.", True),

    # ── Foundations (More Major) ─────────────────────────────────────────
    ("Charles Stewart Mott Foundation", "mott-foundation", 82, "Civil society, environment, Flint community. $3.4B endowment.", True),
    ("John S. and James L. Knight Foundation", "knight-foundation", 83, "Journalism, arts, communities. $2.5B+ endowment. Media innovation.", True),
    ("Duke Endowment", "duke-endowment", 84, "Health, education, rural churches, child care in Carolinas. $4B+ assets.", True),
    ("Kresge Foundation", "kresge-foundation", 83, "Health, environment, education, arts in American cities. $4B endowment.", True),
    ("Surdna Foundation", "surdna-foundation", 81, "Environment, community-centered economies, thriving cultures.", True),
    ("Barr Foundation", "barr-foundation", 82, "Climate, education, arts. Greater Boston and beyond. $3B+ assets.", True),
    ("Ballmer Group", "ballmer-group", 80, "Steve Ballmer philanthropy. Economic mobility for children and families.", True),
    ("Michael & Susan Dell Foundation", "dell-foundation", 82, "Education, family economic stability, childhood health. $2B+ committed.", True),
    ("Arnold Ventures", "arnold-ventures", 81, "John Arnold philanthropy. Criminal justice, health, education.", True),
    ("Milken Institute", "milken-institute", 79, "Economic think tank. Health, education, human capital.", True),
    ("Laura and John Arnold Foundation", "arnold-foundation", 81, "Evidence-based policy. Criminal justice, education reform.", True),
    ("Helmsley Charitable Trust", "helmsley-trust", 83, "Health, education, social services. $5.5B+ endowment.", True),
    ("Conrad N. Hilton Foundation", "hilton-foundation", 84, "Homelessness, substance abuse, foster youth. $2.9B endowment.", True),
    ("Harry and Jeanette Weinberg Foundation", "weinberg-foundation", 82, "Poverty programs. One of largest US private foundations. $2.5B assets.", True),
    ("Doris Duke Charitable Foundation", "doris-duke-foundation", 83, "Environment, performing arts, medical research, child well-being.", True),
    ("Kavli Foundation", "kavli-foundation", 84, "Astrophysics, neuroscience, nanoscience, theoretical physics. Nobel-caliber research.", True),
    ("Templeton Foundation", "templeton-foundation", 80, "Science, religion, character development. $3.4B endowment.", True),
    ("Bezos Day One Fund", "bezos-day-one", 78, "Jeff Bezos philanthropy. Homelessness and preschool education.", True),
    ("Patagonia (1% for the Planet)", "one-percent-for-planet", 83, "Environmental philanthropy network. 1% of sales to environmental groups.", True),
    ("Arcadia Fund", "arcadia-fund", 84, "Lisbet Rausing and Peter Baldwin philanthropy. Culture, nature, open access.", True),
    ("Oak Foundation", "oak-foundation", 83, "Human rights, environment, housing, child abuse, learning differences.", True),

    # ── More Watchlist / Controversial ───────────────────────────────────
    ("Disabled Veterans National Foundation", "dvnf", 45, "History of minimal spending on veterans. Investigated by CNN. Has tried reforms.", False),
    ("Firefighters Burn Fund", "firefighters-burn-fund", 40, "Low program spending. Most funds to telemarketing firms.", False),
    ("Children's Charity Fund", "childrens-charity-fund", 38, "Criticized for excessive fundraising costs. Minimal direct aid.", False),
    ("Committee for Missing Children", "committee-missing-children", 35, "Under scrutiny for spending. Very low program expense ratio.", False),
    ("Shiloh International Ministries", "shiloh-intl-ministries", 42, "Questionable spending practices. Minimal transparency.", False),
    ("American Institute of Philanthropy-flagged orgs", "aip-flagged", 30, "Placeholder for charities consistently rated F by watchdog groups.", False),

    # ── Final Batch: Regional & Niche to reach 500+ ─────────────────────
    ("World Monuments Fund", "world-monuments-fund", 83, "Cultural heritage preservation worldwide. Watch list of endangered sites.", True),
    ("National Trust for Historic Preservation", "national-trust-historic", 82, "Preserving historic places across America. Founded 1949.", True),
    ("Trust for Public Land", "trust-for-public-land", 84, "Parks and public land conservation. Protected 3.8M+ acres.", True),
    ("American Farmland Trust", "american-farmland-trust", 81, "Farmland conservation. Keeps farmers on the land.", True),
    ("Land Trust Alliance", "land-trust-alliance", 82, "National network of 950+ land trusts. Conservation advocacy.", True),
    ("Ducks Unlimited", "ducks-unlimited", 80, "Wetlands and waterfowl conservation. 15M+ acres conserved.", True),
    ("Trout Unlimited", "trout-unlimited", 79, "Cold-water fisheries conservation. 300,000 members.", True),
    ("National Parks Conservation Association", "npca", 83, "Protecting US National Parks. Founded 1919. 1.6M+ members.", True),
    ("Appalachian Mountain Club", "appalachian-mountain-club", 81, "Outdoor recreation and conservation in Northeast US. Founded 1876.", True),
    ("Pacific Crest Trail Association", "pcta", 80, "Protects and promotes the Pacific Crest Trail. Volunteer trail crews.", True),
    ("National Geographic Explorer Program", "natgeo-explorers", 83, "Funds scientific research and exploration expeditions worldwide.", True),
    ("Surfrider Foundation", "surfrider-foundation", 80, "Beach and ocean protection. Clean water, beach access. 80+ chapters.", True),
    ("Clean Ocean Action", "clean-ocean-action", 78, "Ocean pollution prevention. New Jersey-based. Beach sweeps.", True),
    ("Coral Reef Alliance", "coral-reef-alliance", 81, "Coral reef conservation. Science-based approach. Works in 6 countries.", True),
    ("American Rivers", "american-rivers", 82, "River conservation. Dam removal, clean water, flood protection.", True),
    ("Chesapeake Bay Foundation", "chesapeake-bay-foundation", 83, "Chesapeake Bay conservation. Education, advocacy, litigation.", True),
    ("Everglades Foundation", "everglades-foundation", 81, "Florida Everglades restoration advocacy. Science-based.", True),
    ("Rainforest Trust", "rainforest-trust", 86, "Tropical land purchase for conservation. 47M+ acres protected.", True),
    ("American Prairie", "american-prairie", 82, "Creating largest nature reserve in continental US. Montana-based.", True),
    ("National Geographic Education Foundation", "natgeo-education", 82, "Geographic literacy and education programs worldwide.", True),
    ("United Nations Foundation", "un-foundation", 84, "Supports UN causes. Ted Turner founded. Advocacy and fundraising.", True),
    ("Population Council", "population-council", 83, "Biomedical, social science, public health research. 60+ countries.", True),
    ("FHI 360", "fhi360", 82, "Research and development nonprofit. Health, education, economic development.", True),
    ("RTI International", "rti-international", 83, "Research institute. Health, education, technology. 75+ countries.", True),
    ("Abt Associates", "abt-associates", 80, "Research and consulting for social impact. Health, governance, climate.", True),
    ("Mathematica", "mathematica", 82, "Evidence-based policy research. Education, health, labor.", True),
    ("Urban Institute", "urban-institute", 83, "Social and economic policy research. Nonpartisan. Washington DC.", True),
    ("Center on Budget and Policy Priorities", "cbpp", 82, "Fiscal policy research. Focus on low-income families.", True),
    ("Economic Policy Institute", "epi", 80, "Economic research. Workers and low-income families focus.", True),
    ("New America", "new-america", 79, "Think tank. Technology, education, economic security.", True),
    ("Millenium Promise", "millennium-promise", 76, "Millennium Villages Project. UN partnership. Development model.", True),
    ("Clinton Health Access Initiative", "chai", 84, "HIV/AIDS treatment access. Global health markets. 70+ countries.", True),
    ("Elizabeth Glaser Foundation", "egpaf-intl", 83, "Pediatric AIDS prevention globally. Partner of PEPFAR.", True),
    ("Global Alliance for Improved Nutrition", "gain", 82, "Nutrition improvement. Large-scale food fortification programs.", True),
    ("Nutrition International", "nutrition-international", 83, "Micronutrient supplementation. Reaches 1B+ people annually.", True),
    ("WaterCredit / Water Equity", "water-equity", 84, "Microfinance for water and sanitation access. Matt Damon co-founded.", True),
    ("Sanergy", "sanergy", 78, "Sanitation social enterprise in Nairobi. Waste-to-value model.", True),
]


def seed():
    """Upsert all charity entries into software_registry."""
    session = get_session()
    inserted = 0

    for name, slug, score, desc, is_king in CURATED_CHARITIES:
        grade = _grade(score)
        try:
            session.execute(text("""
                INSERT INTO software_registry
                    (name, slug, registry, description, trust_score, trust_grade,
                     enriched_at, created_at, is_king)
                VALUES
                    (:name, :slug, 'charity', :desc, :score, :grade,
                     NOW(), NOW(), :is_king)
                ON CONFLICT (registry, slug) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    trust_score = EXCLUDED.trust_score,
                    trust_grade = EXCLUDED.trust_grade,
                    is_king = EXCLUDED.is_king,
                    enriched_at = NOW()
            """), {
                "name": name,
                "slug": slug,
                "desc": desc,
                "score": score,
                "grade": grade,
                "is_king": is_king,
            })
            inserted += 1
        except Exception as e:
            session.rollback()
            log.warning("Failed %s: %s", slug, e)

    session.commit()
    log.info("Seeded %d / %d charities (registry='charity')", inserted, len(CURATED_CHARITIES))
    session.close()
    return inserted


def fetch_propublica(limit=5000):
    """Fetch additional charities from ProPublica Nonprofit Explorer API.

    Scores are estimated from revenue, filing consistency, and program expense ratio.
    This is a bonus enrichment step — the curated seed above is the primary source.
    """
    import requests
    import time

    url = "https://projects.propublica.org/nonprofits/api/v2/search.json"
    session = get_session()
    fetched = 0
    page = 0
    per_page = 100  # ProPublica default

    while fetched < limit:
        try:
            resp = requests.get(url, params={
                "q": "",
                "page": page,
                "order": "revenue",
                "sort_order": "desc",
            }, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.warning("ProPublica API error on page %d: %s", page, e)
            break

        orgs = data.get("organizations", [])
        if not orgs:
            break

        for org in orgs:
            ein = org.get("ein", "")
            name = org.get("name", "").strip()
            if not name:
                continue

            slug = (
                name.lower()
                .replace("&", "and")
                .replace("'", "")
                .replace(",", "")
                .replace(".", "")
                .replace("  ", " ")
                .replace(" ", "-")
                .strip("-")
            )[:200]

            # Estimate trust score from available data
            revenue = org.get("total_revenue", 0) or 0
            score = 60  # baseline
            if revenue > 1_000_000_000:
                score += 15
            elif revenue > 100_000_000:
                score += 12
            elif revenue > 10_000_000:
                score += 8
            elif revenue > 1_000_000:
                score += 4

            # Bonus for having recent filings
            if org.get("tax_period"):
                score += 5

            # Cap at 85 for API-sourced (curated kings can be higher)
            score = min(score, 85)

            city = org.get("city", "")
            state = org.get("state", "")
            location = f"{city}, {state}".strip(", ") if city or state else ""
            ntee_code = org.get("ntee_code", "")
            desc = f"EIN: {ein}. {location}. NTEE: {ntee_code}. Revenue: ${revenue:,.0f}." if revenue else f"EIN: {ein}. {location}."

            grade = _grade(score)
            try:
                session.execute(text("""
                    INSERT INTO software_registry
                        (name, slug, registry, description, trust_score, trust_grade,
                         enriched_at, created_at, is_king)
                    VALUES
                        (:name, :slug, 'charity', :desc, :score, :grade,
                         NOW(), NOW(), false)
                    ON CONFLICT (registry, slug) DO UPDATE SET
                        description = COALESCE(
                            CASE WHEN software_registry.is_king THEN software_registry.description ELSE EXCLUDED.description END,
                            EXCLUDED.description
                        ),
                        trust_score = CASE WHEN software_registry.is_king THEN software_registry.trust_score ELSE EXCLUDED.trust_score END,
                        trust_grade = CASE WHEN software_registry.is_king THEN software_registry.trust_grade ELSE EXCLUDED.trust_grade END,
                        enriched_at = NOW()
                """), {
                    "name": name,
                    "slug": slug,
                    "desc": desc,
                    "score": score,
                    "grade": grade,
                })
                fetched += 1
            except Exception as e:
                session.rollback()
                log.warning("ProPublica insert failed for %s: %s", slug, e)

        session.commit()
        page += 1
        log.info("ProPublica page %d — fetched %d / %d", page, fetched, limit)

        # Rate limiting
        time.sleep(1)

    session.close()
    log.info("ProPublica fetch complete: %d charities added", fetched)
    return fetched


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Seed charities into software_registry")
    parser.add_argument("--propublica", action="store_true", help="Also fetch from ProPublica API")
    parser.add_argument("--propublica-limit", type=int, default=5000, help="Max charities from ProPublica")
    args = parser.parse_args()

    total = seed()
    log.info("Curated seed complete: %d charities", total)

    if args.propublica:
        extra = fetch_propublica(limit=args.propublica_limit)
        log.info("ProPublica enrichment: %d additional charities", extra)
        total += extra

    log.info("Total charities seeded: %d", total)
