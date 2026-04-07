#!/usr/bin/env python3
"""Food & Cosmetics Seeds — seed ~460 entities across ingredient, supplement, and cosmetic_ingredient registries."""
import logging
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agentindex.db.models import get_session
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
log = logging.getLogger("food_cosmetics_seeds")


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


def _slug(name: str) -> str:
    """Generate a URL-safe slug from a name."""
    import re
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


# ─── E-NUMBER OVERRIDES ────────────────────────────────────────────────────────
# (e_number, name, score, is_king, category, function, status, extra)
E_NUMBER_OVERRIDES = {
    "E100": ("Curcumin", 85, False, "color", "a yellow food coloring derived from turmeric", "Approved (EU/US)", "Natural colorant with antioxidant properties."),
    "E102": ("Tartrazine", 45, True, "color", "a synthetic lemon-yellow azo dye", "Approved but controversial", "Linked to hyperactivity in children. Requires warning label in EU."),
    "E104": ("Quinoline Yellow", 50, False, "color", "a synthetic yellow food dye", "Approved EU, not approved US", "Southampton study linked to hyperactivity."),
    "E110": ("Sunset Yellow FCF", 40, True, "color", "a synthetic orange-red azo dye", "Approved but controversial", "Linked to hyperactivity. Requires warning label in EU."),
    "E120": ("Carmine", 60, True, "color", "a natural red pigment derived from cochineal insects", "Approved (EU/US)", "Not suitable for vegans/vegetarians. Allergen risk."),
    "E122": ("Azorubine", 45, False, "color", "a synthetic red azo dye", "Approved EU, banned US", "Hyperactivity concerns."),
    "E123": ("Amaranth", 25, False, "color", "a synthetic dark red azo dye", "Banned in US since 1976", "Suspected carcinogen. Restricted in many countries."),
    "E124": ("Ponceau 4R", 40, False, "color", "a synthetic red azo dye", "Approved EU, not approved US", "Hyperactivity concerns."),
    "E127": ("Erythrosine", 35, True, "color", "a synthetic cherry-pink dye", "Approved, under FDA review", "Being reviewed by FDA. Thyroid concerns at high doses."),
    "E129": ("Allura Red", 40, True, "color", "a synthetic red azo dye (Red 40)", "Approved but controversial", "Most widely used red dye. Red 40 controversy. Hyperactivity concerns."),
    "E131": ("Patent Blue V", 50, False, "color", "a synthetic blue dye", "Approved EU, not approved US", "Used mainly in confectionery."),
    "E132": ("Indigotine", 55, False, "color", "a synthetic blue dye (Indigo Carmine)", "Approved (EU/US)", "One of the oldest synthetic dyes."),
    "E133": ("Brilliant Blue FCF", 55, False, "color", "a synthetic blue dye", "Approved (EU/US)", "Used in beverages and confectionery."),
    "E140": ("Chlorophyll", 80, False, "color", "a natural green pigment from plants", "Approved (EU/US)", "Natural and generally considered safe."),
    "E141": ("Copper complexes of chlorophyll", 75, False, "color", "a modified natural green pigment", "Approved (EU/US)", "More stable than plain chlorophyll."),
    "E142": ("Green S", 45, False, "color", "a synthetic green dye", "Approved EU, banned US", "Limited safety data."),
    "E150a": ("Plain caramel", 75, False, "color", "a natural brown coloring from heated sugar", "Approved (EU/US)", "Simple caramel with no chemical treatment."),
    "E150b": ("Caustic sulphite caramel", 60, False, "color", "a processed brown coloring", "Approved (EU/US)", "Produced with sulphite compounds."),
    "E150c": ("Ammonia caramel", 55, False, "color", "a processed brown coloring", "Approved (EU/US)", "Contains 2-MEI and 4-MEI byproducts."),
    "E150d": ("Sulphite ammonia caramel", 55, False, "color", "a processed brown coloring used in cola drinks", "Approved (EU/US)", "Most common caramel color. Contains 4-MEI (potential carcinogen)."),
    "E151": ("Brilliant Black BN", 45, False, "color", "a synthetic black dye", "Approved EU, not approved US", "Azo dye with hyperactivity concerns."),
    "E153": ("Vegetable carbon", 70, False, "color", "a natural black pigment from charred plant material", "Approved (EU/US)", "Natural but may contain PAHs if impure."),
    "E155": ("Brown HT", 45, False, "color", "a synthetic brown dye", "Approved EU, not approved US", "Azo dye."),
    "E160a": ("Beta-carotene", 85, False, "color", "a natural orange pigment (provitamin A)", "Approved (EU/US)", "Natural colorant and nutrient. Found in carrots."),
    "E160b": ("Annatto", 70, False, "color", "a natural orange-red pigment from annatto seeds", "Approved (EU/US)", "Natural but can cause allergic reactions."),
    "E160c": ("Paprika extract", 80, False, "color", "a natural red pigment from paprika", "Approved (EU/US)", "Natural colorant from capsicum peppers."),
    "E160d": ("Lycopene", 85, False, "color", "a natural red pigment from tomatoes", "Approved (EU/US)", "Natural antioxidant."),
    "E160e": ("Beta-apo-8-carotenal", 70, False, "color", "a carotenoid pigment", "Approved (EU/US)", "Related to beta-carotene."),
    "E161b": ("Lutein", 80, False, "color", "a natural yellow-orange pigment", "Approved (EU/US)", "Found in egg yolks. Eye health benefits."),
    "E162": ("Beetroot Red", 80, False, "color", "a natural red pigment from beetroot", "Approved (EU/US)", "Natural colorant with no safety concerns."),
    "E163": ("Anthocyanins", 82, False, "color", "natural purple-red pigments from fruits", "Approved (EU/US)", "Natural colorant with antioxidant properties."),
    "E170": ("Calcium carbonate", 85, False, "color", "a white mineral pigment (chalk)", "Approved (EU/US)", "Also used as calcium supplement and antacid."),
    "E171": ("Titanium dioxide", 15, True, "color", "a white pigment used in confectionery and sauces", "BANNED in EU since August 2022", "EFSA concluded it can no longer be considered safe. Genotoxicity concerns with nanoparticles. Still permitted in US."),
    "E172": ("Iron oxides", 70, False, "color", "mineral-derived pigments (red, yellow, black)", "Approved (EU/US)", "Used in confectionery and meat products."),
    "E173": ("Aluminium", 40, False, "color", "a metallic silver colorant", "Approved EU (restricted), limited US use", "Only for external decoration of sugar confectionery."),
    "E174": ("Silver", 50, False, "color", "a metallic silver colorant", "Approved EU (restricted)", "Only for external decoration of confectionery."),
    "E175": ("Gold", 55, False, "color", "a metallic gold colorant", "Approved EU (restricted)", "Only for external decoration of confectionery and liqueurs."),
    "E180": ("Litholrubine BK", 35, False, "color", "a synthetic red dye for cheese rind only", "Approved EU for cheese rind only", "Very restricted use."),
    "E200": ("Sorbic acid", 85, False, "preservative", "an antimicrobial preservative", "Approved (EU/US)", "One of the safest preservatives. Natural origin (rowan berries)."),
    "E201": ("Sodium sorbate", 80, False, "preservative", "a salt of sorbic acid preservative", "Approved (EU/US)", "Well-tolerated preservative."),
    "E202": ("Potassium sorbate", 80, False, "preservative", "a widely-used antimicrobial preservative", "Approved (EU/US)", "Most common sorbic acid salt. Used in cheese, wine, baked goods."),
    "E203": ("Calcium sorbate", 78, False, "preservative", "a salt of sorbic acid preservative", "Approved (EU/US)", "Similar safety profile to potassium sorbate."),
    "E210": ("Benzoic acid", 65, False, "preservative", "an antimicrobial preservative", "Approved (EU/US)", "Can form benzene when combined with ascorbic acid under certain conditions."),
    "E211": ("Sodium benzoate", 55, True, "preservative", "a widely-used antimicrobial preservative in acidic foods", "Approved (EU/US) with limits", "Can form benzene with ascorbic acid. Hyperactivity concerns. Widely used in soft drinks."),
    "E212": ("Potassium benzoate", 60, False, "preservative", "a salt of benzoic acid preservative", "Approved (EU/US)", "Similar concerns to sodium benzoate."),
    "E213": ("Calcium benzoate", 60, False, "preservative", "a salt of benzoic acid preservative", "Approved (EU/US)", "Similar concerns to sodium benzoate."),
    "E214": ("Ethylparaben", 55, False, "preservative", "a paraben preservative", "Approved EU with limits", "Paraben family — endocrine disruption debate."),
    "E215": ("Sodium ethylparaben", 55, False, "preservative", "a paraben preservative", "Approved EU with limits", "Paraben family."),
    "E218": ("Methylparaben", 55, False, "preservative", "a paraben preservative", "Approved EU with limits", "Most common paraben preservative."),
    "E219": ("Sodium methylparaben", 55, False, "preservative", "a paraben preservative", "Approved EU with limits", "Paraben family."),
    "E220": ("Sulphur dioxide", 60, True, "preservative", "an antioxidant and antimicrobial preservative", "Approved (EU/US), allergen labeling required", "Major allergen. Must be declared above 10mg/kg. Used in wine, dried fruit."),
    "E221": ("Sodium sulphite", 60, False, "preservative", "a sulphite preservative", "Approved (EU/US)", "Allergen — must be declared."),
    "E222": ("Sodium bisulphite", 58, False, "preservative", "a sulphite preservative", "Approved (EU/US)", "Allergen — must be declared."),
    "E223": ("Sodium metabisulphite", 58, False, "preservative", "a sulphite preservative and antioxidant", "Approved (EU/US)", "Allergen — must be declared."),
    "E224": ("Potassium metabisulphite", 58, False, "preservative", "a sulphite preservative used in wine", "Approved (EU/US)", "Allergen — must be declared."),
    "E226": ("Calcium sulphite", 55, False, "preservative", "a sulphite preservative", "Approved EU", "Allergen — must be declared."),
    "E227": ("Calcium bisulphite", 55, False, "preservative", "a sulphite preservative", "Approved EU", "Allergen — must be declared."),
    "E228": ("Potassium bisulphite", 55, False, "preservative", "a sulphite preservative", "Approved (EU/US)", "Allergen — must be declared."),
    "E230": ("Biphenyl", 25, False, "preservative", "a fungicide for citrus fruit peels", "Banned in EU", "No longer permitted in EU."),
    "E231": ("Orthophenyl phenol", 30, False, "preservative", "a fungicide for citrus fruit peels", "Restricted EU", "Limited use, restricted to surface treatment."),
    "E232": ("Sodium orthophenyl phenol", 30, False, "preservative", "a fungicide for citrus fruit peels", "Restricted EU", "Limited use."),
    "E234": ("Nisin", 78, False, "preservative", "a natural antimicrobial peptide", "Approved (EU/US)", "Natural preservative produced by bacteria. Used in cheese."),
    "E235": ("Natamycin", 75, False, "preservative", "a natural antifungal preservative", "Approved (EU/US)", "Used on cheese rind and sausage casings."),
    "E239": ("Hexamethylenetetramine", 30, False, "preservative", "a formaldehyde-releasing preservative", "Limited EU use (Provolone cheese only)", "Releases formaldehyde. Very restricted."),
    "E242": ("Dimethyl dicarbonate", 65, False, "preservative", "a cold sterilization agent for beverages", "Approved (EU/US)", "Decomposes rapidly in the beverage."),
    "E249": ("Potassium nitrite", 40, False, "preservative", "a curing agent for processed meats", "Approved with strict limits", "Nitrosamine formation concern. Cancer risk at high levels."),
    "E250": ("Sodium nitrite", 35, True, "preservative", "a curing agent for processed meats", "Approved with strict limits", "Essential for preventing botulism in cured meats. IARC Group 2A carcinogen when forming nitrosamines. Central to processed-meat cancer debate."),
    "E251": ("Sodium nitrate", 40, True, "preservative", "a curing agent that converts to nitrite in meat", "Approved with limits", "Converts to nitrite during curing. Same cancer risk concerns."),
    "E252": ("Potassium nitrate", 42, False, "preservative", "a curing salt (saltpeter) for processed meats", "Approved with limits", "Traditional curing agent. Converts to nitrite."),
    "E260": ("Acetic acid", 88, False, "preservative", "the main component of vinegar", "Approved (EU/US)", "Vinegar. GRAS (Generally Recognized as Safe)."),
    "E261": ("Potassium acetate", 80, False, "preservative", "a buffering agent and preservative", "Approved (EU/US)", "Well-tolerated."),
    "E262": ("Sodium acetate", 80, False, "preservative", "a seasoning and preservative (salt and vinegar flavor)", "Approved (EU/US)", "Used in salt and vinegar chips."),
    "E263": ("Calcium acetate", 78, False, "preservative", "a stabilizer and preservative", "Approved (EU/US)", "Also used as calcium supplement."),
    "E270": ("Lactic acid", 85, False, "preservative", "a natural preservative and acidulant", "Approved (EU/US)", "Naturally produced by fermentation."),
    "E280": ("Propionic acid", 70, False, "preservative", "an antimicrobial preservative for bread", "Approved (EU/US)", "Naturally occurring in Swiss cheese."),
    "E281": ("Sodium propionate", 68, False, "preservative", "a bread preservative", "Approved (EU/US)", "Common bread mold inhibitor."),
    "E282": ("Calcium propionate", 68, False, "preservative", "the most common bread preservative", "Approved (EU/US)", "Most widely used bread preservative worldwide."),
    "E283": ("Potassium propionate", 68, False, "preservative", "a bread preservative", "Approved (EU/US)", "Similar to calcium propionate."),
    "E284": ("Boric acid", 25, False, "preservative", "a preservative for caviar only", "EU: caviar only. Toxic in quantity", "Very restricted use."),
    "E285": ("Sodium tetraborate", 25, False, "preservative", "a preservative for caviar only", "EU: caviar only", "Very restricted use. Borax."),
    "E290": ("Carbon dioxide", 90, False, "preservative", "a carbonation and packaging gas", "Approved (EU/US)", "Used for carbonation of beverages."),
    "E296": ("Malic acid", 85, False, "preservative", "a natural acidulant found in apples", "Approved (EU/US)", "Natural — found in many fruits."),
    "E297": ("Fumaric acid", 80, False, "preservative", "an acidulant and flavor enhancer", "Approved (EU/US)", "Naturally occurs in fumitory plant."),
    "E300": ("Ascorbic acid", 95, True, "antioxidant", "Vitamin C — an antioxidant and flour treatment agent", "Approved (EU/US). Essential nutrient", "The most well-known vitamin. Essential nutrient. Also used as preservative in meats."),
    "E301": ("Sodium ascorbate", 90, False, "antioxidant", "a salt of Vitamin C", "Approved (EU/US)", "Sodium salt of ascorbic acid."),
    "E302": ("Calcium ascorbate", 88, False, "antioxidant", "a salt of Vitamin C", "Approved (EU/US)", "Calcium salt of ascorbic acid."),
    "E304": ("Ascorbyl palmitate", 82, False, "antioxidant", "a fat-soluble form of Vitamin C", "Approved (EU/US)", "Oil-soluble antioxidant."),
    "E306": ("Tocopherols", 92, False, "antioxidant", "Vitamin E — a natural antioxidant", "Approved (EU/US). Essential nutrient", "Natural vitamin E extract. Essential nutrient and antioxidant."),
    "E307": ("Alpha-tocopherol", 90, False, "antioxidant", "synthetic Vitamin E", "Approved (EU/US)", "Most active form of Vitamin E."),
    "E308": ("Gamma-tocopherol", 85, False, "antioxidant", "a form of Vitamin E", "Approved (EU/US)", "Antioxidant form of Vitamin E."),
    "E309": ("Delta-tocopherol", 85, False, "antioxidant", "a form of Vitamin E", "Approved (EU/US)", "Antioxidant form of Vitamin E."),
    "E310": ("Propyl gallate", 55, False, "antioxidant", "a synthetic antioxidant for fats and oils", "Approved (EU/US) with limits", "Some allergy concerns. Restricted in baby food."),
    "E311": ("Octyl gallate", 50, False, "antioxidant", "a synthetic antioxidant", "Approved EU with limits", "Less common than propyl gallate."),
    "E312": ("Dodecyl gallate", 50, False, "antioxidant", "a synthetic antioxidant", "Approved EU with limits", "Rarely used."),
    "E315": ("Erythorbic acid", 78, False, "antioxidant", "a stereoisomer of Vitamin C used as antioxidant", "Approved (EU/US)", "Cheaper alternative to ascorbic acid. Not a vitamin."),
    "E316": ("Sodium erythorbate", 78, False, "antioxidant", "the sodium salt of erythorbic acid", "Approved (EU/US)", "Common meat-curing antioxidant."),
    "E319": ("TBHQ", 40, True, "antioxidant", "a synthetic antioxidant (tertiary butylhydroquinone)", "Approved (EU/US) with strict limits", "Controversial. Used in fast food frying oils. Some studies show immune effects."),
    "E320": ("BHA", 30, True, "antioxidant", "butylated hydroxyanisole — a synthetic antioxidant", "Approved with limits. IARC Group 2B", "Possible carcinogen (IARC). Endocrine disruption concerns. Banned in some countries for baby food."),
    "E321": ("BHT", 35, True, "antioxidant", "butylated hydroxytoluene — a synthetic antioxidant", "Approved with limits", "Controversial. Some studies show tumor promotion. Banned in some countries."),
    "E322": ("Lecithin", 88, True, "antioxidant", "a natural emulsifier from soy or sunflower", "Approved (EU/US). GRAS", "One of the most common food additives. Natural emulsifier. Soy allergen concern."),
    "E325": ("Sodium lactate", 80, False, "antioxidant", "a natural humectant and preservative", "Approved (EU/US)", "Sodium salt of lactic acid."),
    "E326": ("Potassium lactate", 80, False, "antioxidant", "a natural preservative", "Approved (EU/US)", "Potassium salt of lactic acid."),
    "E327": ("Calcium lactate", 82, False, "antioxidant", "a calcium salt of lactic acid", "Approved (EU/US)", "Also a calcium supplement."),
    "E330": ("Citric acid", 92, True, "antioxidant", "the most widely used food additive — an acidulant and antioxidant", "Approved (EU/US). GRAS", "Found in citrus fruits. The most common food additive globally. Used in virtually all processed food."),
    "E331": ("Sodium citrate", 88, False, "antioxidant", "a buffering agent and emulsifier", "Approved (EU/US)", "Used in beverages and cheese."),
    "E332": ("Potassium citrate", 85, False, "antioxidant", "a buffering agent", "Approved (EU/US)", "Also used as potassium supplement."),
    "E333": ("Calcium citrate", 85, False, "antioxidant", "a calcium salt of citric acid", "Approved (EU/US)", "Also a calcium supplement."),
    "E334": ("Tartaric acid", 82, False, "antioxidant", "a natural acidulant from grapes", "Approved (EU/US)", "Key acid in winemaking."),
    "E335": ("Sodium tartrate", 80, False, "antioxidant", "a salt of tartaric acid", "Approved (EU/US)", "Used as emulsifier."),
    "E336": ("Potassium tartrate", 82, False, "antioxidant", "cream of tartar", "Approved (EU/US)", "Cream of tartar — common baking ingredient."),
    "E337": ("Sodium potassium tartrate", 78, False, "antioxidant", "Rochelle salt", "Approved (EU/US)", "Used as emulsifier."),
    "E338": ("Phosphoric acid", 55, True, "antioxidant", "an acidulant in cola drinks", "Approved (EU/US) with limits", "Gives cola drinks their tangy taste. Concerns about bone health at high intake."),
    "E339": ("Sodium phosphate", 60, False, "antioxidant", "an emulsifier and buffering agent", "Approved (EU/US) with limits", "Phosphate additive — excess phosphate intake concern."),
    "E340": ("Potassium phosphate", 62, False, "antioxidant", "a buffering agent and emulsifier", "Approved (EU/US) with limits", "Phosphate additive."),
    "E341": ("Calcium phosphate", 70, False, "antioxidant", "a mineral supplement and anti-caking agent", "Approved (EU/US)", "Also a calcium supplement."),
    "E343": ("Magnesium phosphate", 70, False, "antioxidant", "a mineral supplement and anti-caking agent", "Approved (EU/US)", "Also a magnesium supplement."),
    "E350": ("Sodium malate", 78, False, "antioxidant", "a salt of malic acid", "Approved (EU/US)", "Buffering agent."),
    "E351": ("Potassium malate", 78, False, "antioxidant", "a salt of malic acid", "Approved (EU/US)", "Buffering agent."),
    "E352": ("Calcium malate", 78, False, "antioxidant", "a salt of malic acid", "Approved (EU/US)", "Buffering agent and calcium source."),
    "E353": ("Metatartaric acid", 75, False, "antioxidant", "a stabilizer for wine", "Approved EU", "Used to prevent tartrate crystals in wine."),
    "E354": ("Calcium tartrate", 78, False, "antioxidant", "a salt of tartaric acid", "Approved (EU/US)", "Used in baking."),
    "E355": ("Adipic acid", 75, False, "antioxidant", "an acidulant", "Approved (EU/US)", "Used in gelatin desserts."),
    "E356": ("Sodium adipate", 75, False, "antioxidant", "a salt of adipic acid", "Approved EU", "Buffering agent."),
    "E357": ("Potassium adipate", 75, False, "antioxidant", "a salt of adipic acid", "Approved EU", "Buffering agent."),
    "E363": ("Succinic acid", 78, False, "antioxidant", "an acidulant and flavor enhancer", "Approved (EU/US)", "Naturally found in many foods."),
    "E380": ("Triammonium citrate", 72, False, "antioxidant", "an ammonium salt of citric acid", "Approved EU", "Buffering agent."),
    "E385": ("EDTA", 55, False, "antioxidant", "a chelating agent to prevent metal-catalyzed oxidation", "Approved (EU/US) with limits", "Binds metal ions. Controversial — some concerns about mineral depletion."),
    "E392": ("Rosemary extract", 85, False, "antioxidant", "a natural antioxidant from rosemary", "Approved (EU/US)", "Natural antioxidant. Increasingly popular as clean-label alternative."),
    "E399": ("Calcium lactobionate", 75, False, "antioxidant", "a calcium salt stabilizer", "Approved EU", "Used in some dairy products."),
    "E400": ("Alginic acid", 80, False, "thickener", "a natural thickener from seaweed", "Approved (EU/US)", "Extracted from brown seaweed."),
    "E401": ("Sodium alginate", 80, False, "thickener", "a thickener and gelling agent from seaweed", "Approved (EU/US)", "Used in molecular gastronomy."),
    "E402": ("Potassium alginate", 78, False, "thickener", "a thickener from seaweed", "Approved (EU/US)", "Similar to sodium alginate."),
    "E403": ("Ammonium alginate", 75, False, "thickener", "a thickener from seaweed", "Approved (EU/US)", "Similar to sodium alginate."),
    "E404": ("Calcium alginate", 78, False, "thickener", "a gelling agent from seaweed", "Approved (EU/US)", "Used in restructured foods."),
    "E405": ("Propylene glycol alginate", 65, False, "thickener", "a modified alginate emulsifier", "Approved (EU/US)", "Used in salad dressings and beer foam."),
    "E406": ("Agar", 85, False, "thickener", "a natural gelling agent from red seaweed", "Approved (EU/US)", "Vegan gelatin alternative. Used in microbiology."),
    "E407": ("Carrageenan", 45, True, "thickener", "a gelling and thickening agent from red seaweed", "Approved but highly controversial", "Major gut health controversy. Some studies show intestinal inflammation. Organic food lobby has pushed for removal. Widely debated."),
    "E407a": ("Processed eucheuma seaweed", 50, False, "thickener", "a semi-refined carrageenan", "Approved EU", "Less processed form of carrageenan."),
    "E410": ("Locust bean gum", 80, False, "thickener", "a natural thickener from carob seeds", "Approved (EU/US)", "Natural gum. Combined with xanthan or carrageenan."),
    "E412": ("Guar gum", 80, False, "thickener", "a natural thickener from guar beans", "Approved (EU/US)", "Widely used thickener. Can cause digestive issues in large amounts."),
    "E413": ("Tragacanth gum", 72, False, "thickener", "a natural gum from thorny shrubs", "Approved (EU/US)", "Ancient thickener. Some allergy risk."),
    "E414": ("Gum arabic", 82, False, "thickener", "a natural gum from acacia trees", "Approved (EU/US). GRAS", "One of the oldest food additives. Used in soft drinks and confectionery."),
    "E415": ("Xanthan gum", 82, True, "thickener", "a microbial polysaccharide thickener", "Approved (EU/US). GRAS", "Produced by fermentation. Essential in gluten-free baking. One of the most versatile food thickeners."),
    "E416": ("Karaya gum", 70, False, "thickener", "a natural gum from Indian trees", "Approved (EU/US)", "Used in ice cream and sauces."),
    "E417": ("Tara gum", 75, False, "thickener", "a natural gum from tara seeds", "Approved (EU/US)", "Growing in popularity."),
    "E418": ("Gellan gum", 78, False, "thickener", "a microbial polysaccharide gelling agent", "Approved (EU/US)", "Modern thickener produced by fermentation."),
    "E420": ("Sorbitol", 78, False, "thickener", "a sugar alcohol sweetener and humectant", "Approved (EU/US)", "Naturally found in fruits. Can cause digestive issues in large amounts."),
    "E421": ("Mannitol", 75, False, "thickener", "a sugar alcohol sweetener", "Approved (EU/US)", "Can cause digestive issues."),
    "E422": ("Glycerol", 82, False, "thickener", "a humectant and sweetener", "Approved (EU/US). GRAS", "Very common food additive and pharmaceutical ingredient."),
    "E425": ("Konjac", 72, False, "thickener", "a gelling agent from konjac root (glucomannan)", "Approved EU with restrictions", "Choking hazard in jelly candies — banned in some forms."),
    "E426": ("Soybean hemicellulose", 70, False, "thickener", "a stabilizer from soybeans", "Approved EU", "Soy allergen concern."),
    "E427": ("Cassia gum", 68, False, "thickener", "a natural gum from cassia seeds", "Approved EU", "Used in pet food and dairy."),
    "E431": ("Polyoxyethylene stearate", 55, False, "thickener", "a synthetic emulsifier", "Approved EU with limits", "Limited use."),
    "E432": ("Polysorbate 20", 60, False, "thickener", "a synthetic emulsifier (Tween 20)", "Approved (EU/US)", "Used in baked goods."),
    "E433": ("Polysorbate 80", 58, False, "thickener", "a synthetic emulsifier (Tween 80)", "Approved (EU/US)", "Some studies show gut microbiome effects."),
    "E434": ("Polysorbate 40", 58, False, "thickener", "a synthetic emulsifier", "Approved (EU/US)", "Similar to polysorbate 80."),
    "E435": ("Polysorbate 60", 58, False, "thickener", "a synthetic emulsifier", "Approved (EU/US)", "Similar to polysorbate 80."),
    "E436": ("Polysorbate 65", 58, False, "thickener", "a synthetic emulsifier", "Approved (EU/US)", "Similar to polysorbate 80."),
    "E440": ("Pectin", 90, False, "thickener", "a natural gelling agent from fruit", "Approved (EU/US). GRAS", "Natural — found in all fruit. Key ingredient in jam-making."),
    "E442": ("Ammonium phosphatide", 65, False, "thickener", "a synthetic emulsifier for chocolate", "Approved EU", "Used mainly in chocolate."),
    "E444": ("Sucrose acetate isobutyrate", 60, False, "thickener", "a weighting agent for beverages", "Approved (EU/US)", "Used to keep oils suspended in drinks."),
    "E445": ("Glycerol esters of wood rosins", 55, False, "thickener", "a weighting agent for beverages", "Approved (EU/US)", "Used in citrus-flavored drinks."),
    "E450": ("Diphosphates", 60, False, "thickener", "phosphate-based leavening agents", "Approved (EU/US)", "Common in baking powder. Excess phosphate concern."),
    "E451": ("Triphosphates", 58, False, "thickener", "phosphate-based emulsifiers", "Approved (EU/US)", "Used in processed meats. Excess phosphate concern."),
    "E452": ("Polyphosphates", 55, False, "thickener", "phosphate-based water-binding agents", "Approved (EU/US) with limits", "Used in processed meats to retain water. Excess phosphate concern."),
    "E459": ("Beta-cyclodextrin", 70, False, "thickener", "a starch derivative encapsulant", "Approved EU", "Used to encapsulate flavors."),
    "E460": ("Cellulose", 75, False, "thickener", "a plant-derived bulking agent and fiber", "Approved (EU/US)", "Wood pulp or cotton-derived. Used as anti-caking agent in shredded cheese."),
    "E461": ("Methyl cellulose", 72, False, "thickener", "a modified cellulose thickener", "Approved (EU/US)", "Used in gluten-free baking."),
    "E462": ("Ethyl cellulose", 70, False, "thickener", "a modified cellulose film-former", "Approved (EU/US)", "Used for coatings and encapsulation."),
    "E463": ("Hydroxypropyl cellulose", 70, False, "thickener", "a modified cellulose thickener", "Approved (EU/US)", "Used in pharmaceuticals."),
    "E464": ("Hydroxypropyl methyl cellulose", 72, False, "thickener", "a modified cellulose thickener (HPMC)", "Approved (EU/US)", "Common in vegan capsules and gluten-free baking."),
    "E465": ("Ethyl methyl cellulose", 68, False, "thickener", "a modified cellulose emulsifier", "Approved EU", "Rare use."),
    "E466": ("CMC", 72, False, "thickener", "carboxymethyl cellulose — a synthetic thickener", "Approved (EU/US)", "Common thickener in ice cream. Recent studies suggest gut microbiome effects."),
    "E468": ("Crosslinked CMC", 68, False, "thickener", "a modified cellulose stabilizer", "Approved EU", "Used in tablets."),
    "E469": ("Enzymatically hydrolysed CMC", 68, False, "thickener", "a modified cellulose thickener", "Approved EU", "Modified version of CMC."),
    "E470a": ("Sodium/potassium/calcium salts of fatty acids", 72, False, "thickener", "fatty acid salt emulsifiers", "Approved (EU/US)", "Common anti-caking agent."),
    "E470b": ("Magnesium salts of fatty acids", 72, False, "thickener", "a fatty acid salt anti-caking agent", "Approved (EU/US)", "Common in supplements and confectionery."),
    "E471": ("Mono- and diglycerides of fatty acids", 65, True, "thickener", "the most widely used emulsifier in processed food", "Approved (EU/US). GRAS", "Found in almost all processed food. Bread, ice cream, margarine. Can be from animal or plant sources."),
    "E472a": ("Acetic acid esters of mono/diglycerides", 65, False, "thickener", "a modified fat emulsifier", "Approved (EU/US)", "Used in baked goods."),
    "E472b": ("Lactic acid esters of mono/diglycerides", 65, False, "thickener", "a modified fat emulsifier", "Approved (EU/US)", "Used in baked goods."),
    "E472c": ("Citric acid esters of mono/diglycerides", 65, False, "thickener", "a modified fat emulsifier", "Approved (EU/US)", "Used in baked goods."),
    "E472d": ("Tartaric acid esters of mono/diglycerides", 65, False, "thickener", "a modified fat emulsifier", "Approved EU", "Used in baked goods."),
    "E472e": ("DATEM", 65, False, "thickener", "diacetyl tartaric acid esters — a dough conditioner", "Approved (EU/US)", "Common bread improver."),
    "E472f": ("Mixed tartaric/acetic esters of mono/diglycerides", 62, False, "thickener", "a modified fat emulsifier", "Approved EU", "Used in baked goods."),
    "E473": ("Sucrose esters", 62, False, "thickener", "sugar-based emulsifiers", "Approved (EU/US)", "Modern emulsifier."),
    "E474": ("Sucroglycerides", 62, False, "thickener", "sugar-fat hybrid emulsifiers", "Approved EU", "Similar to sucrose esters."),
    "E475": ("Polyglycerol esters of fatty acids", 62, False, "thickener", "a synthetic emulsifier", "Approved (EU/US)", "Used in chocolate and baked goods."),
    "E476": ("PGPR", 60, False, "thickener", "polyglycerol polyricinoleate — a chocolate emulsifier", "Approved (EU/US)", "Reduces cocoa butter needed in chocolate. Cost-saving additive."),
    "E477": ("Propylene glycol esters of fatty acids", 58, False, "thickener", "a synthetic emulsifier", "Approved (EU/US)", "Used in whipped toppings."),
    "E479b": ("Thermally oxidized soya bean oil", 50, False, "thickener", "a soybean-derived emulsifier", "Approved EU", "Used in frying fats."),
    "E481": ("Sodium stearoyl lactylate", 72, False, "thickener", "an emulsifier and dough strengthener", "Approved (EU/US)", "Common bread improver."),
    "E482": ("Calcium stearoyl lactylate", 72, False, "thickener", "an emulsifier", "Approved (EU/US)", "Used in baked goods."),
    "E483": ("Stearyl tartrate", 68, False, "thickener", "a flour treatment agent", "Approved EU", "Used in baked goods."),
    "E491": ("Sorbitan monostearate", 65, False, "thickener", "a synthetic emulsifier", "Approved (EU/US)", "Used in chocolate and confectionery."),
    "E492": ("Sorbitan tristearate", 65, False, "thickener", "a synthetic emulsifier", "Approved (EU/US)", "Used in chocolate."),
    "E493": ("Sorbitan monolaurate", 65, False, "thickener", "a synthetic emulsifier", "Approved (EU/US)", "Used in confectionery."),
    "E494": ("Sorbitan monooleate", 65, False, "thickener", "a synthetic emulsifier", "Approved (EU/US)", "Used in confectionery."),
    "E495": ("Sorbitan monopalmitate", 65, False, "thickener", "a synthetic emulsifier", "Approved (EU/US)", "Used in confectionery."),
    "E500": ("Sodium carbonate", 95, False, "anti-caking", "baking soda/washing soda — a leavening agent", "Approved (EU/US). GRAS", "Baking soda — one of the oldest and safest food additives."),
    "E501": ("Potassium carbonate", 88, False, "anti-caking", "a leavening and buffering agent", "Approved (EU/US)", "Used in Dutch-process cocoa."),
    "E503": ("Ammonium carbonate", 82, False, "anti-caking", "a leavening agent (baker's ammonia)", "Approved (EU/US)", "Traditional leavening for cookies and crackers."),
    "E504": ("Magnesium carbonate", 85, False, "anti-caking", "an anti-caking agent and color retention agent", "Approved (EU/US)", "Also used as magnesium supplement."),
    "E507": ("Hydrochloric acid", 72, False, "anti-caking", "an acid used in food processing", "Approved (EU/US)", "Used in gelatin production and corn syrup."),
    "E508": ("Potassium chloride", 78, False, "anti-caking", "a salt substitute and gelling agent", "Approved (EU/US)", "Low-sodium salt alternative. Can have bitter taste."),
    "E509": ("Calcium chloride", 80, False, "anti-caking", "a firming agent for fruits and vegetables", "Approved (EU/US)", "Used to keep pickles crisp and in cheese-making."),
    "E510": ("Ammonium chloride", 68, False, "anti-caking", "a yeast nutrient and flavoring (salmiak)", "Approved (EU/US)", "Used in licorice in Nordic countries."),
    "E511": ("Magnesium chloride", 78, False, "anti-caking", "a coagulant for tofu (nigari)", "Approved (EU/US)", "Essential in tofu production."),
    "E512": ("Stannous chloride", 55, False, "anti-caking", "a tin-based antioxidant for canned food", "Approved with limits", "Used in canned asparagus and other white vegetables."),
    "E513": ("Sulphuric acid", 65, False, "anti-caking", "an acid used in food processing", "Approved (EU/US)", "Used in modified starch production."),
    "E514": ("Sodium sulphate", 72, False, "anti-caking", "a diluent in food colors", "Approved (EU/US)", "Glauber's salt."),
    "E515": ("Potassium sulphate", 75, False, "anti-caking", "a salt substitute", "Approved (EU/US)", "Used in some salt alternatives."),
    "E516": ("Calcium sulphate", 80, False, "anti-caking", "a coagulant for tofu (gypsum)", "Approved (EU/US)", "Traditional tofu coagulant."),
    "E517": ("Ammonium sulphate", 68, False, "anti-caking", "a yeast nutrient for bread", "Approved (EU/US)", "Used as yeast food in bread."),
    "E520": ("Aluminium sulphate", 45, False, "anti-caking", "a firming agent", "Approved with limits", "Aluminium concerns at high intake."),
    "E521": ("Aluminium sodium sulphate", 45, False, "anti-caking", "a leavening acid", "Approved with limits", "Aluminium concerns."),
    "E522": ("Aluminium potassium sulphate", 48, False, "anti-caking", "alum — a firming agent and leavening acid", "Approved with limits", "Traditional pickling ingredient."),
    "E523": ("Aluminium ammonium sulphate", 45, False, "anti-caking", "a leavening acid", "Approved with limits", "Aluminium concerns."),
    "E524": ("Sodium hydroxide", 75, False, "anti-caking", "an alkali (lye) used in food processing", "Approved (EU/US)", "Used in pretzel making, olives, and lutefisk."),
    "E525": ("Potassium hydroxide", 75, False, "anti-caking", "an alkali used in food processing", "Approved (EU/US)", "Used in cocoa processing."),
    "E526": ("Calcium hydroxide", 78, False, "anti-caking", "slaked lime — used in food processing", "Approved (EU/US)", "Used in corn nixtamalization and pickling."),
    "E527": ("Ammonium hydroxide", 70, False, "anti-caking", "an alkali used in food processing", "Approved (EU/US)", "Used in baked goods. \"Pink slime\" controversy."),
    "E528": ("Magnesium hydroxide", 82, False, "anti-caking", "an alkali and antacid", "Approved (EU/US)", "Milk of magnesia."),
    "E529": ("Calcium oxide", 75, False, "anti-caking", "quicklime — used in food processing", "Approved (EU/US)", "Used in corn processing."),
    "E530": ("Magnesium oxide", 80, False, "anti-caking", "an anti-caking agent", "Approved (EU/US)", "Also magnesium supplement."),
    "E535": ("Sodium ferrocyanide", 65, False, "anti-caking", "an anti-caking agent for salt", "Approved (EU/US) with limits", "Sounds alarming but safe at permitted levels."),
    "E536": ("Potassium ferrocyanide", 65, False, "anti-caking", "an anti-caking agent for salt", "Approved (EU/US) with limits", "Safe at permitted levels despite name."),
    "E538": ("Calcium ferrocyanide", 65, False, "anti-caking", "an anti-caking agent for salt", "Approved EU with limits", "Safe at permitted levels."),
    "E541": ("Sodium aluminium phosphate", 45, False, "anti-caking", "a leavening acid for self-rising flour", "Approved (EU/US)", "Aluminium concerns."),
    "E551": ("Silicon dioxide", 78, False, "anti-caking", "a natural anti-caking agent (silica)", "Approved (EU/US)", "Found naturally in many foods. Used in powdered foods."),
    "E552": ("Calcium silicate", 75, False, "anti-caking", "an anti-caking agent", "Approved (EU/US)", "Used in salt and baking powder."),
    "E553a": ("Magnesium silicate", 72, False, "anti-caking", "an anti-caking agent (talc)", "Approved (EU/US) with limits", "Talc — asbestos contamination concerns in some sources."),
    "E553b": ("Talc", 68, False, "anti-caking", "a mineral anti-caking agent", "Approved (EU/US) with limits", "Must be asbestos-free."),
    "E554": ("Sodium aluminium silicate", 48, False, "anti-caking", "an anti-caking agent", "Approved (EU/US)", "Aluminium concerns."),
    "E555": ("Potassium aluminium silicate", 48, False, "anti-caking", "an anti-caking agent", "Approved EU", "Aluminium concerns."),
    "E556": ("Calcium aluminium silicate", 48, False, "anti-caking", "an anti-caking agent", "Approved EU", "Aluminium concerns."),
    "E558": ("Bentonite", 70, False, "anti-caking", "a clay used for fining wines", "Approved EU", "Used in winemaking."),
    "E559": ("Aluminium silicate (Kaolin)", 55, False, "anti-caking", "a clay anti-caking agent", "Approved EU", "Kaolin clay."),
    "E570": ("Fatty acids", 75, False, "anti-caking", "natural fatty acid anti-caking agents", "Approved (EU/US)", "Stearic acid etc."),
    "E574": ("Gluconic acid", 80, False, "anti-caking", "a natural acid", "Approved (EU/US)", "Produced by fermentation."),
    "E575": ("Glucono delta-lactone", 80, False, "anti-caking", "a slow-acting acidulant for tofu", "Approved (EU/US)", "Used in tofu and salami."),
    "E576": ("Sodium gluconate", 78, False, "anti-caking", "a sequestrant", "Approved (EU/US)", "Used in metal cleaning."),
    "E577": ("Potassium gluconate", 78, False, "anti-caking", "a potassium supplement", "Approved (EU/US)", "Also used as potassium supplement."),
    "E578": ("Calcium gluconate", 80, False, "anti-caking", "a calcium supplement and firming agent", "Approved (EU/US)", "Also used as calcium supplement."),
    "E579": ("Ferrous gluconate", 72, False, "anti-caking", "an iron supplement and olive colorant", "Approved (EU/US)", "Used to darken ripe olives."),
    "E585": ("Ferrous lactate", 72, False, "anti-caking", "an iron supplement and olive colorant", "Approved EU", "Iron supplement."),
    "E586": ("4-Hexylresorcinol", 60, False, "anti-caking", "an anti-browning agent for shrimp", "Approved (EU/US)", "Prevents melanosis in crustaceans."),
    "E620": ("Glutamic acid", 65, False, "flavour_enhancer", "the amino acid that gives umami taste", "Approved (EU/US)", "Naturally present in many foods. Parent compound of MSG."),
    "E621": ("MSG", 50, True, "flavour_enhancer", "monosodium glutamate — the most famous flavor enhancer", "Approved (EU/US). GRAS but controversial", "The most debated food additive. Chinese Restaurant Syndrome (debunked). EFSA set ADI at 30mg/kg. Umami taste."),
    "E622": ("Monopotassium glutamate", 55, False, "flavour_enhancer", "a potassium salt of glutamic acid", "Approved (EU/US)", "Similar to MSG."),
    "E623": ("Calcium glutamate", 55, False, "flavour_enhancer", "a calcium salt of glutamic acid", "Approved (EU/US)", "Similar to MSG."),
    "E624": ("Monoammonium glutamate", 55, False, "flavour_enhancer", "an ammonium salt of glutamic acid", "Approved (EU/US)", "Similar to MSG."),
    "E625": ("Magnesium glutamate", 55, False, "flavour_enhancer", "a magnesium salt of glutamic acid", "Approved (EU/US)", "Similar to MSG."),
    "E626": ("Guanylic acid", 65, False, "flavour_enhancer", "a nucleotide flavor enhancer", "Approved (EU/US)", "Often combined with MSG for synergistic effect."),
    "E627": ("Disodium guanylate", 65, False, "flavour_enhancer", "a nucleotide flavor enhancer", "Approved (EU/US)", "Used with MSG in instant noodles and chips."),
    "E628": ("Dipotassium guanylate", 65, False, "flavour_enhancer", "a nucleotide flavor enhancer", "Approved (EU/US)", "Similar to disodium guanylate."),
    "E629": ("Calcium guanylate", 65, False, "flavour_enhancer", "a nucleotide flavor enhancer", "Approved (EU/US)", "Similar to disodium guanylate."),
    "E630": ("Inosinic acid", 65, False, "flavour_enhancer", "a nucleotide flavor enhancer", "Approved (EU/US)", "Found naturally in meat."),
    "E631": ("Disodium inosinate", 65, False, "flavour_enhancer", "a nucleotide flavor enhancer", "Approved (EU/US)", "Often combined with MSG and disodium guanylate."),
    "E632": ("Dipotassium inosinate", 65, False, "flavour_enhancer", "a nucleotide flavor enhancer", "Approved (EU/US)", "Similar to disodium inosinate."),
    "E633": ("Calcium inosinate", 65, False, "flavour_enhancer", "a nucleotide flavor enhancer", "Approved (EU/US)", "Similar to disodium inosinate."),
    "E634": ("Calcium 5-ribonucleotides", 65, False, "flavour_enhancer", "a combination flavor enhancer", "Approved (EU/US)", "Blend of guanylate and inosinate."),
    "E635": ("Disodium 5-ribonucleotides", 65, False, "flavour_enhancer", "a combination flavor enhancer (I+G)", "Approved (EU/US)", "Synergistic with MSG. Very common in Asian cuisine."),
    "E640": ("Glycine", 78, False, "flavour_enhancer", "a natural amino acid flavor modifier", "Approved (EU/US)", "Naturally occurring amino acid."),
    "E650": ("Zinc acetate", 60, False, "flavour_enhancer", "a zinc supplement and flavor modifier", "Approved EU", "Also used as zinc supplement."),
    "E900": ("Dimethylpolysiloxane", 60, False, "sweetener", "an anti-foaming agent (silicone)", "Approved (EU/US)", "Used in frying oils at McDonald's and other fast food."),
    "E901": ("Beeswax", 80, False, "sweetener", "a natural glazing agent from bees", "Approved (EU/US)", "Natural coating for confectionery and fruit."),
    "E902": ("Candelilla wax", 78, False, "sweetener", "a plant-based glazing agent", "Approved (EU/US)", "Vegan alternative to beeswax."),
    "E903": ("Carnauba wax", 80, False, "sweetener", "a plant-based glazing agent from palm leaves", "Approved (EU/US)", "Used in confectionery, car wax, and dental floss."),
    "E904": ("Shellac", 65, False, "sweetener", "a natural resin glazing agent from lac bugs", "Approved (EU/US)", "Used to coat pills and candy. Not vegan."),
    "E905": ("Microcrystalline wax", 60, False, "sweetener", "a petroleum-derived glazing agent", "Approved (EU/US) with limits", "Petroleum-based. Used in chewing gum."),
    "E907": ("Hydrogenated poly-1-decene", 55, False, "sweetener", "a synthetic glazing agent", "Approved EU", "Used in confectionery."),
    "E912": ("Montan acid esters", 60, False, "sweetener", "a mineral-based glazing agent", "Approved EU", "Surface treatment for fruit."),
    "E914": ("Oxidized polyethylene wax", 50, False, "sweetener", "a synthetic glazing agent", "Approved EU", "Surface treatment for citrus fruit."),
    "E920": ("L-Cysteine", 65, False, "sweetener", "a flour treatment agent (amino acid)", "Approved (EU/US)", "Often derived from human hair or duck feathers. Used in bread."),
    "E927b": ("Carbamide", 60, False, "sweetener", "urea — used in chewing gum", "Approved EU", "Used in sugar-free chewing gum."),
    "E938": ("Argon", 90, False, "sweetener", "a packaging gas", "Approved (EU/US)", "Inert gas. Completely safe."),
    "E939": ("Helium", 90, False, "sweetener", "a packaging gas", "Approved (EU/US)", "Inert gas. Completely safe."),
    "E941": ("Nitrogen", 92, False, "sweetener", "a packaging and freezing gas", "Approved (EU/US)", "Makes up 78% of air. Used in nitro coffee."),
    "E942": ("Nitrous oxide", 70, False, "sweetener", "a propellant for whipped cream", "Approved (EU/US)", "Laughing gas. Safe in food use."),
    "E943a": ("Butane", 60, False, "sweetener", "a propellant gas", "Approved EU", "Used in cooking spray."),
    "E943b": ("Isobutane", 60, False, "sweetener", "a propellant gas", "Approved EU", "Used in cooking spray."),
    "E944": ("Propane", 60, False, "sweetener", "a propellant gas", "Approved EU", "Used in cooking spray."),
    "E948": ("Oxygen", 92, False, "sweetener", "a packaging gas", "Approved (EU/US)", "Used in modified atmosphere packaging."),
    "E949": ("Hydrogen", 90, False, "sweetener", "a packaging gas", "Approved EU", "Used in modified atmosphere packaging."),
    "E950": ("Acesulfame K", 55, True, "sweetener", "a high-intensity artificial sweetener", "Approved (EU/US)", "200x sweeter than sugar. Often combined with aspartame. Some studies question long-term safety."),
    "E951": ("Aspartame", 40, True, "sweetener", "a high-intensity artificial sweetener", "Approved (EU/US). IARC Group 2B (2023)", "WHO IARC classified as \"possibly carcinogenic\" (Group 2B) in July 2023. Most studied food additive. 200x sweeter than sugar."),
    "E952": ("Cyclamate", 35, True, "sweetener", "a high-intensity artificial sweetener", "Banned in US since 1969. Approved in EU", "30x sweeter than sugar. Banned in US due to bladder cancer concerns in rats."),
    "E953": ("Isomalt", 72, False, "sweetener", "a sugar alcohol from sucrose", "Approved (EU/US)", "Low glycemic. Used in sugar-free candy."),
    "E954": ("Saccharin", 50, True, "sweetener", "the oldest artificial sweetener", "Approved (EU/US). Warning label removed 2000", "300x sweeter than sugar. Was labeled as carcinogenic, later cleared. Sweet'N Low."),
    "E955": ("Sucralose", 55, True, "sweetener", "an artificial sweetener (Splenda)", "Approved (EU/US)", "600x sweeter than sugar. Made from sugar. Recent studies question gut microbiome effects."),
    "E957": ("Thaumatin", 82, False, "sweetener", "a natural protein sweetener from katemfe fruit", "Approved (EU/US)", "2000x sweeter than sugar. Natural origin."),
    "E959": ("Neohesperidin DC", 70, False, "sweetener", "a semi-synthetic sweetener from citrus", "Approved EU", "1500x sweeter than sugar."),
    "E960": ("Stevia", 78, True, "sweetener", "a natural high-intensity sweetener from stevia plant", "Approved (EU/US)", "200-300x sweeter than sugar. Natural origin. Driving the natural sweetener trend. Coca-Cola and PepsiCo use."),
    "E961": ("Neotame", 60, False, "sweetener", "an artificial sweetener related to aspartame", "Approved (EU/US)", "8000x sweeter than sugar."),
    "E962": ("Aspartame-acesulfame salt", 48, False, "sweetener", "a combined artificial sweetener", "Approved (EU/US)", "Combination of two sweeteners."),
    "E965": ("Maltitol", 72, False, "sweetener", "a sugar alcohol from maltose", "Approved (EU/US)", "90% sweetness of sugar. Used in sugar-free chocolate."),
    "E966": ("Lactitol", 70, False, "sweetener", "a sugar alcohol from lactose", "Approved (EU/US)", "Low calorie sweetener."),
    "E967": ("Xylitol", 75, True, "sweetener", "a sugar alcohol from birch wood", "Approved (EU/US)", "Dental health benefits. Toxic to dogs. Common in sugar-free gum."),
    "E968": ("Erythritol", 65, True, "sweetener", "a zero-calorie sugar alcohol", "Approved (EU/US)", "Zero calories. 2023 Cleveland Clinic study linked to increased cardiovascular risk."),
    "E999": ("Quillaia extract", 65, False, "sweetener", "a natural foaming agent from tree bark", "Approved (EU/US)", "Used in soft drinks for foam."),
    "E1103": ("Invertase", 78, False, "modified_starch", "an enzyme that converts sucrose", "Approved (EU/US)", "Used in confectionery for soft centers."),
    "E1105": ("Lysozyme", 80, False, "modified_starch", "a natural antimicrobial enzyme from egg white", "Approved (EU/US)", "Used in cheese and wine. Egg allergen."),
    "E1200": ("Polydextrose", 72, False, "modified_starch", "a synthetic fiber and bulking agent", "Approved (EU/US)", "Low-calorie bulking agent for sugar-free products."),
    "E1201": ("Polyvinylpyrrolidone", 60, False, "modified_starch", "a clarifying agent for wine and beer", "Approved (EU/US)", "Also used in pharmaceuticals."),
    "E1202": ("Polyvinylpolypyrrolidone", 60, False, "modified_starch", "a clarifying agent for beverages", "Approved (EU/US)", "Used in beer and wine clarification."),
    "E1404": ("Oxidized starch", 75, False, "modified_starch", "a chemically modified starch", "Approved (EU/US)", "Used as thickener and binder."),
    "E1410": ("Monostarch phosphate", 75, False, "modified_starch", "a modified starch thickener", "Approved (EU/US)", "Improved freeze-thaw stability."),
    "E1412": ("Distarch phosphate", 75, False, "modified_starch", "a cross-linked modified starch", "Approved (EU/US)", "Acid and heat stable."),
    "E1413": ("Phosphated distarch phosphate", 75, False, "modified_starch", "a modified starch", "Approved (EU/US)", "Combined modification."),
    "E1414": ("Acetylated distarch phosphate", 75, False, "modified_starch", "a modified starch", "Approved (EU/US)", "Most versatile modified starch."),
    "E1420": ("Acetylated starch", 75, False, "modified_starch", "a modified starch with improved properties", "Approved (EU/US)", "Better stability and texture."),
    "E1422": ("Acetylated distarch adipate", 75, False, "modified_starch", "a modified starch", "Approved (EU/US)", "Good freeze-thaw stability."),
    "E1440": ("Hydroxypropyl starch", 75, False, "modified_starch", "a modified starch", "Approved (EU/US)", "Cold-water swelling starch."),
    "E1442": ("Hydroxypropyl distarch phosphate", 75, False, "modified_starch", "a modified starch", "Approved (EU/US)", "Very common in sauces and dressings."),
    "E1450": ("Starch sodium octenyl succinate", 72, False, "modified_starch", "a modified starch emulsifier", "Approved (EU/US)", "Used in beverage emulsions."),
    "E1451": ("Acetylated oxidized starch", 72, False, "modified_starch", "a modified starch", "Approved EU", "Multi-modified starch."),
    "E1452": ("Starch aluminium octenyl succinate", 65, False, "modified_starch", "a modified starch with aluminium", "Approved EU", "Contains aluminium."),
    "E1505": ("Triethyl citrate", 72, False, "modified_starch", "a plasticizer and stabilizer", "Approved (EU/US)", "Used in coatings and pharmaceuticals."),
    "E1510": ("Ethanol", 82, False, "modified_starch", "ethyl alcohol — a solvent and carrier", "Approved (EU/US)", "Used as extraction solvent and in flavors."),
    "E1517": ("Glyceryl diacetate", 68, False, "modified_starch", "a solvent and humectant", "Approved EU", "Used in flavors."),
    "E1518": ("Glyceryl triacetate", 70, False, "modified_starch", "a solvent and humectant (triacetin)", "Approved (EU/US)", "Used in flavors and chewing gum."),
    "E1519": ("Benzyl alcohol", 60, False, "modified_starch", "a solvent and flavoring", "Approved (EU/US)", "Natural in many fruits."),
    "E1520": ("Propylene glycol", 65, False, "modified_starch", "a solvent and humectant", "Approved (EU/US) with limits", "Used in food and e-cigarette liquid. GRAS."),
    "E1521": ("Polyethylene glycol", 55, False, "modified_starch", "a solvent and tablet coating", "Approved EU with limits", "Used in pharmaceuticals."),
}


# ─── NON-E-NUMBER INGREDIENTS ──────────────────────────────────────────────────
# (name, slug, score, is_king, description)
NON_E_INGREDIENTS = [
    ("High-Fructose Corn Syrup", "high-fructose-corn-syrup", 30, True,
     "High-Fructose Corn Syrup is a sweetener commonly found in soft drinks, processed foods, and condiments. Linked to obesity, diabetes, and metabolic syndrome. Dominant sweetener in US food supply."),
    ("Maltodextrin", "maltodextrin", 45, True,
     "Maltodextrin is a processed starch commonly found in powdered foods, snacks, and sports drinks. High glycemic index. Can spike blood sugar. Often used as cheap filler."),
    ("Gluten", "gluten", 70, True,
     "Gluten is a protein complex commonly found in wheat, barley, and rye products. Safe for most people. Harmful for celiac disease (1% of population) and gluten sensitivity."),
    ("Caffeine", "caffeine", 72, True,
     "Caffeine is a stimulant commonly found in coffee, tea, energy drinks, and chocolate. The most widely consumed psychoactive substance. Safe up to 400mg/day for adults (FDA)."),
    ("Taurine", "taurine", 70, False,
     "Taurine is an amino acid commonly found in energy drinks and supplements. Naturally produced by the body. Key ingredient in Red Bull."),
    ("Palm Oil", "palm-oil", 40, True,
     "Palm Oil is a vegetable oil commonly found in processed foods, chocolate, and cosmetics. Major deforestation driver. Contains saturated fat. WHO recommends limiting intake."),
    ("Trans Fats", "trans-fats", 10, True,
     "Trans Fats is an artificial fat commonly found in partially hydrogenated oils, margarine, and fried food. BANNED by FDA in US (2018) and restricted in EU. Increases heart disease risk dramatically."),
    ("Gelatin", "gelatin", 75, False,
     "Gelatin is a protein commonly found in gummy candy, marshmallows, and desserts. Derived from animal collagen. Not vegetarian/vegan."),
    ("Sodium (Salt)", "sodium-salt", 65, True,
     "Sodium (Salt) is a mineral commonly found in virtually all processed foods. Essential nutrient but excess causes hypertension. WHO recommends <5g/day."),
    ("Lactose", "lactose", 72, False,
     "Lactose is a milk sugar commonly found in dairy products. 65% of adults have reduced ability to digest lactose after infancy."),
    ("Peanut Protein", "peanut-protein", 70, False,
     "Peanut Protein is an allergen commonly found in peanut butter, snacks, and Asian cuisine. One of the 'Big 8' allergens. Can cause anaphylaxis."),
    ("Soy Protein", "soy-protein", 72, False,
     "Soy Protein is a plant protein and allergen commonly found in tofu, soy sauce, and processed foods. Phytoestrogen debate. Major allergen."),
    ("Tree Nut Protein", "tree-nut-protein", 70, False,
     "Tree Nut Protein is an allergen commonly found in almonds, walnuts, cashews, and baked goods. Major allergen group. Can cause anaphylaxis."),
    ("Shellfish Protein", "shellfish-protein", 70, False,
     "Shellfish Protein is an allergen commonly found in shrimp, crab, lobster, and seafood dishes. Major allergen. Can cause severe reactions."),
    ("Egg Protein", "egg-protein", 75, False,
     "Egg Protein is an allergen commonly found in baked goods, mayonnaise, and pasta. Major allergen. Most children outgrow egg allergy."),
    ("Wheat Protein", "wheat-protein", 72, False,
     "Wheat Protein is an allergen commonly found in bread, pasta, cereals, and baked goods. Major allergen. Different from celiac disease."),
    ("Sesame", "sesame-allergen", 70, False,
     "Sesame is an allergen commonly found in tahini, hummus, bread, and Asian cuisine. Added to US major allergen list in 2023 (FASTER Act)."),
    ("Mustard", "mustard-allergen", 72, False,
     "Mustard is an allergen commonly found in condiments, sauces, and processed meats. Major allergen in EU. Hidden in many processed foods."),
    ("Celery", "celery-allergen", 75, False,
     "Celery is an allergen commonly found in soups, stocks, and seasoning blends. Major allergen in EU. Less recognized in US."),
    ("Lupin", "lupin-allergen", 72, False,
     "Lupin is an allergen commonly found in gluten-free flour, pasta, and baked goods. Major allergen in EU. Cross-reactivity with peanut."),
]


# ─── SUPPLEMENTS ────────────────────────────────────────────────────────────────
# (name, slug, score, is_king, description)
SUPPLEMENTS = [
    ("Vitamin D", "vitamin-d-supplement", 90, True,
     "Vitamin D is a dietary supplement. Regulates calcium absorption and immune function. Strong evidence for bone health; emerging evidence for immunity. Deficiency common in northern latitudes."),
    ("Vitamin C", "vitamin-c-supplement", 92, True,
     "Vitamin C is a dietary supplement. Essential antioxidant and cofactor for collagen synthesis. Strong evidence for immune support and scurvy prevention. Very safe at recommended doses."),
    ("Vitamin B12", "vitamin-b12-supplement", 88, True,
     "Vitamin B12 is a dietary supplement. Essential for nerve function and DNA synthesis. Strong evidence for deficiency treatment. Critical for vegans and elderly."),
    ("Vitamin A", "vitamin-a-supplement", 82, True,
     "Vitamin A is a dietary supplement. Essential for vision, immune function, and skin health. Strong evidence but toxicity risk at high doses. Teratogenic in pregnancy."),
    ("Vitamin E", "vitamin-e-supplement", 85, True,
     "Vitamin E is a dietary supplement. Fat-soluble antioxidant. Mixed evidence for disease prevention. High doses may increase mortality risk (meta-analyses)."),
    ("Vitamin K", "vitamin-k-supplement", 84, True,
     "Vitamin K is a dietary supplement. Essential for blood clotting and bone health. Strong evidence for K2 and cardiovascular health. Interacts with warfarin."),
    ("Omega-3 Fatty Acids", "omega-3-supplement", 88, True,
     "Omega-3 Fatty Acids is a dietary supplement. EPA and DHA support cardiovascular and brain health. Strong evidence from multiple RCTs. Anti-inflammatory properties."),
    ("Fish Oil", "fish-oil-supplement", 85, True,
     "Fish Oil is a dietary supplement. Rich source of EPA and DHA omega-3 fatty acids. Strong evidence for triglyceride reduction. Mercury contamination concern in low-quality products."),
    ("Krill Oil", "krill-oil-supplement", 78, True,
     "Krill Oil is a dietary supplement. Phospholipid-bound omega-3 source with astaxanthin. Moderate evidence suggests better absorption than fish oil. Sustainability concerns."),
    ("Probiotics", "probiotics-supplement", 82, True,
     "Probiotics is a dietary supplement. Live microorganisms that confer health benefits. Moderate-to-strong evidence for gut health and antibiotic-associated diarrhea. Strain-specific effects."),
    ("Prebiotics", "prebiotics-supplement", 80, True,
     "Prebiotics is a dietary supplement. Non-digestible fibers that feed beneficial gut bacteria. Moderate evidence for gut health. Includes inulin, FOS, and GOS."),
    ("Magnesium", "magnesium-supplement", 87, True,
     "Magnesium is a dietary supplement. Essential mineral for 300+ enzymatic reactions. Strong evidence for muscle function and sleep. Deficiency is very common (up to 50% of population)."),
    ("Zinc", "zinc-supplement", 85, True,
     "Zinc is a dietary supplement. Essential trace mineral for immune function and wound healing. Strong evidence for reducing cold duration. Can cause nausea if taken on empty stomach."),
    ("Iron", "iron-supplement", 80, True,
     "Iron is a dietary supplement. Essential for hemoglobin and oxygen transport. Strong evidence for anemia treatment. Can be toxic in excess. GI side effects common."),
    ("Calcium", "calcium-supplement", 84, True,
     "Calcium is a dietary supplement. Essential mineral for bones and teeth. Strong evidence for bone health. Recent concerns about cardiovascular calcification with supplements vs food sources."),
    ("Potassium", "potassium-supplement", 82, True,
     "Potassium is a dietary supplement. Essential electrolyte for heart and muscle function. Strong evidence for blood pressure reduction. Dangerous in excess (hyperkalemia)."),
    ("Creatine", "creatine-supplement", 85, True,
     "Creatine is a dietary supplement. Enhances ATP regeneration for high-intensity exercise. One of the most researched supplements. Strong evidence for strength and power gains. Very safe."),
    ("Protein Powder", "protein-powder-supplement", 80, True,
     "Protein Powder is a dietary supplement. Concentrated protein source for muscle recovery. Strong evidence for muscle protein synthesis. Various sources: whey, casein, plant."),
    ("Whey Protein", "whey-protein-supplement", 82, True,
     "Whey Protein is a dietary supplement. Fast-absorbing dairy protein rich in BCAAs. Strong evidence for muscle recovery. Gold standard for sports nutrition."),
    ("Collagen", "collagen-supplement", 75, True,
     "Collagen is a dietary supplement. Structural protein for skin, joints, and connective tissue. Moderate evidence for skin elasticity and joint health. Trending supplement."),
    ("Melatonin", "melatonin-supplement", 72, True,
     "Melatonin is a dietary supplement. Hormone regulating circadian rhythm. Moderate evidence for jet lag and sleep onset. OTC in US, prescription in EU. Long-term safety unclear."),
    ("Ashwagandha", "ashwagandha-supplement", 65, True,
     "Ashwagandha is a dietary supplement. Adaptogenic herb (Withania somnifera). Moderate evidence for stress reduction and cortisol levels. Traditional Ayurvedic medicine. Thyroid interaction concern."),
    ("Turmeric Curcumin", "turmeric-curcumin-supplement", 70, True,
     "Turmeric Curcumin is a dietary supplement. Anti-inflammatory compound from turmeric root. Moderate evidence but poor bioavailability without piperine. Trending for joint health."),
    ("CoQ10", "coq10-supplement", 78, True,
     "CoQ10 is a dietary supplement. Coenzyme Q10 supports mitochondrial energy production. Moderate evidence for statin-related muscle pain and heart failure. Levels decline with age."),
    ("L-Theanine", "l-theanine-supplement", 75, True,
     "L-Theanine is a dietary supplement. Amino acid from tea leaves that promotes relaxation without drowsiness. Moderate evidence for anxiety reduction. Synergistic with caffeine."),
    ("Biotin", "biotin-supplement", 80, True,
     "Biotin is a dietary supplement. B vitamin (B7) for hair, skin, and nail health. Limited evidence for hair growth in non-deficient individuals. Can interfere with lab tests."),
    ("Folic Acid", "folic-acid-supplement", 85, True,
     "Folic Acid is a dietary supplement. Synthetic B9 vitamin critical for fetal development. Very strong evidence for neural tube defect prevention. Mandatory fortification in many countries."),
    ("Glucosamine", "glucosamine-supplement", 70, True,
     "Glucosamine is a dietary supplement. Amino sugar for joint cartilage support. Mixed evidence — some large studies show no benefit. Popular for osteoarthritis."),
    ("Chondroitin", "chondroitin-supplement", 68, True,
     "Chondroitin is a dietary supplement. Cartilage component often paired with glucosamine. Mixed evidence for joint health. May slow cartilage loss."),
    ("MSM", "msm-supplement", 65, True,
     "MSM is a dietary supplement. Methylsulfonylmethane — organic sulfur compound. Limited evidence for joint pain and inflammation. Generally well-tolerated."),
    ("St. Johns Wort", "st-johns-wort-supplement", 55, True,
     "St. Johns Wort is a dietary supplement. Hypericum perforatum for mild-to-moderate depression. Moderate evidence but DANGEROUS drug interactions (SSRIs, birth control, warfarin, HIV drugs)."),
    ("Ginkgo Biloba", "ginkgo-biloba-supplement", 58, True,
     "Ginkgo Biloba is a dietary supplement. Ancient tree extract for cognitive function. Mixed evidence — large GEM study showed no dementia prevention. Blood-thinning effect."),
    ("CBD Oil", "cbd-oil-supplement", 50, True,
     "CBD Oil is a dietary supplement. Cannabidiol extract from hemp. Moderate evidence for epilepsy (Epidiolex). Legal complexity varies by jurisdiction. FDA has not approved as supplement."),
    ("Kratom", "kratom-supplement", 25, True,
     "Kratom is a dietary supplement. Mitragyna speciosa — opioid-like plant. FDA WARNING: risk of addiction, abuse, and death. Banned in several countries. NOT recommended by any medical authority."),
    ("Apple Cider Vinegar", "apple-cider-vinegar-supplement", 60, True,
     "Apple Cider Vinegar is a dietary supplement. Acetic acid fermented from apples. Limited evidence for blood sugar control. Can damage tooth enamel. Trendy but overhyped."),
    ("Elderberry", "elderberry-supplement", 68, True,
     "Elderberry is a dietary supplement. Sambucus nigra berry extract for immune support. Moderate evidence for reducing cold duration and severity. Raw berries are toxic."),
    ("Echinacea", "echinacea-supplement", 62, True,
     "Echinacea is a dietary supplement. Flowering plant extract for immune support. Mixed evidence for cold prevention. May reduce cold duration slightly. Autoimmune disease caution."),
    ("5-HTP", "5-htp-supplement", 55, True,
     "5-HTP is a dietary supplement. 5-Hydroxytryptophan — serotonin precursor. Moderate evidence for depression and sleep. DANGEROUS with SSRIs (serotonin syndrome risk)."),
    ("GABA Supplement", "gaba-supplement", 60, True,
     "GABA Supplement is a dietary supplement. Gamma-aminobutyric acid — inhibitory neurotransmitter. Limited evidence — uncertain if oral GABA crosses blood-brain barrier."),
    ("SAMe", "same-supplement", 65, True,
     "SAMe is a dietary supplement. S-Adenosyl methionine — methyl donor for brain chemistry. Moderate evidence for depression and osteoarthritis. Expensive. Bipolar caution."),
    ("Spirulina", "spirulina-supplement", 72, True,
     "Spirulina is a dietary supplement. Blue-green algae superfood rich in protein and nutrients. Moderate evidence for cholesterol reduction. Heavy metal contamination risk in poor-quality products."),
    ("Chlorella", "chlorella-supplement", 70, True,
     "Chlorella is a dietary supplement. Green algae rich in chlorophyll and nutrients. Limited evidence for detoxification claims. May support immune function."),
    ("Activated Charcoal", "activated-charcoal-supplement", 45, True,
     "Activated Charcoal is a dietary supplement. Porous carbon that adsorbs toxins. Strong evidence for acute poisoning treatment. No evidence for detox trends. Can block medication absorption."),
    ("Berberine", "berberine-supplement", 60, True,
     "Berberine is a dietary supplement. Plant alkaloid with blood-sugar-lowering properties. Moderate evidence comparable to metformin in some studies. Trending as 'nature's Ozempic'. GI side effects."),
    ("Vitamin B Complex", "vitamin-b-complex-supplement", 86, True,
     "Vitamin B Complex is a dietary supplement. Contains all 8 B vitamins for energy metabolism. Strong evidence for deficiency prevention. Water-soluble — low toxicity risk."),
    ("Selenium", "selenium-supplement", 78, True,
     "Selenium is a dietary supplement. Essential trace mineral and antioxidant. Strong evidence for thyroid function. Narrow therapeutic window — toxic in excess (selenosis)."),
    ("Chromium", "chromium-supplement", 62, True,
     "Chromium is a dietary supplement. Trace mineral marketed for blood sugar control and weight loss. Mixed evidence. Chromium picolinate is most studied form."),
    ("Milk Thistle", "milk-thistle-supplement", 65, True,
     "Milk Thistle is a dietary supplement. Silymarin extract for liver support. Moderate evidence for liver protection. Used after mushroom poisoning in Europe. Generally safe."),
]


# ─── COSMETIC INGREDIENTS ──────────────────────────────────────────────────────
# (name, slug, score, is_king, description)
COSMETICS = [
    ("Retinol", "retinol-cosmetic", 82, True,
     "Retinol is a cosmetic ingredient used as an anti-aging and skin renewal active. Gold standard for anti-aging with strong evidence for wrinkle reduction. Can cause irritation and photosensitivity. Not recommended during pregnancy."),
    ("Retinaldehyde", "retinaldehyde-cosmetic", 80, False,
     "Retinaldehyde is a cosmetic ingredient used as an anti-aging retinoid. One step closer to retinoic acid than retinol. Better tolerated than tretinoin. Good evidence for anti-aging."),
    ("Tretinoin", "tretinoin-cosmetic", 75, True,
     "Tretinoin is a cosmetic ingredient used as a prescription-strength retinoid. Most potent topical retinoid. Prescription only. Strong evidence for acne and photoaging. Significant irritation and sun sensitivity."),
    ("Niacinamide", "niacinamide-cosmetic", 88, True,
     "Niacinamide is a cosmetic ingredient used as a multi-functional active (B3 vitamin). Reduces pores, brightens, strengthens skin barrier. Well-tolerated. Strong evidence. Works at 2-5%."),
    ("Hyaluronic Acid", "hyaluronic-acid-cosmetic", 90, True,
     "Hyaluronic Acid is a cosmetic ingredient used as a humectant moisturizer. Holds 1000x its weight in water. Naturally present in skin. Very safe. Different molecular weights for different depths. Trendy hero ingredient."),
    ("Salicylic Acid", "salicylic-acid-cosmetic", 82, True,
     "Salicylic Acid is a cosmetic ingredient used as a BHA exfoliant and acne treatment. Oil-soluble — penetrates pores. Strong evidence for acne. Anti-inflammatory. Max 2% OTC."),
    ("Glycolic Acid", "glycolic-acid-cosmetic", 78, True,
     "Glycolic Acid is a cosmetic ingredient used as an AHA exfoliant. Smallest AHA molecule — deepest penetration. Strong evidence for skin texture improvement. Can cause irritation and sun sensitivity."),
    ("Lactic Acid Skincare", "lactic-acid-skincare", 80, False,
     "Lactic Acid Skincare is a cosmetic ingredient used as a gentle AHA exfoliant. Larger molecule than glycolic — gentler. Also a humectant. Good for sensitive skin. Found in sour milk."),
    ("Mandelic Acid", "mandelic-acid-cosmetic", 76, False,
     "Mandelic Acid is a cosmetic ingredient used as a gentle AHA exfoliant. Largest common AHA molecule. Gentlest AHA. Good for hyperpigmentation and acne-prone skin."),
    ("Vitamin C Serum", "vitamin-c-serum-cosmetic", 85, True,
     "Vitamin C Serum is a cosmetic ingredient used as an antioxidant and brightening active. L-ascorbic acid is gold standard form. Strong evidence for UV protection support and collagen synthesis. Unstable — degrades quickly."),
    ("Ascorbic Acid Skincare", "ascorbic-acid-skincare", 83, False,
     "Ascorbic Acid Skincare is a cosmetic ingredient used as the pure form of Vitamin C. Most effective but least stable form. Must be at pH <3.5. 10-20% concentration optimal."),
    ("Ceramides", "ceramides-cosmetic", 85, False,
     "Ceramides is a cosmetic ingredient used as a skin barrier repair agent. Natural component of skin barrier (50% of lipids). Strong evidence for barrier repair. Safe for all skin types."),
    ("Peptides Skincare", "peptides-skincare", 78, False,
     "Peptides Skincare is a cosmetic ingredient used as anti-aging signaling molecules. Short chains of amino acids. Various types (copper, matrixyl). Moderate evidence for collagen stimulation."),
    ("Squalane", "squalane-cosmetic", 82, False,
     "Squalane is a cosmetic ingredient used as a lightweight moisturizing oil. Hydrogenated version of squalene. Non-comedogenic. Plant-derived (olive, sugarcane). Mimics skin's natural oils."),
    ("Zinc Oxide Sunscreen", "zinc-oxide-sunscreen", 88, False,
     "Zinc Oxide Sunscreen is a cosmetic ingredient used as a physical/mineral UV filter. Broad-spectrum UVA+UVB protection. Reef-safe. Can leave white cast. Safe for sensitive skin and pregnancy."),
    ("Titanium Dioxide Sunscreen", "titanium-dioxide-sunscreen", 70, True,
     "Titanium Dioxide Sunscreen is a cosmetic ingredient used as a physical/mineral UV filter. Primarily UVB protection. Nano-particle controversy — inhalation concerns in spray sunscreens. Reef-safe. Banned as food additive in EU but still allowed in cosmetics."),
    ("Avobenzone", "avobenzone-cosmetic", 72, False,
     "Avobenzone is a cosmetic ingredient used as a chemical UVA filter. Most common UVA filter in US sunscreens. Photounstable — needs stabilizers (octocrylene). Enters bloodstream (FDA study 2019). Reef concerns."),
    ("Octinoxate", "octinoxate-cosmetic", 45, True,
     "Octinoxate is a cosmetic ingredient used as a chemical UVB filter. Potential endocrine disruptor (estrogen-like). Banned in Hawaii, Palau, and Key West for coral reef damage. Enters bloodstream."),
    ("Oxybenzone", "oxybenzone-cosmetic", 35, True,
     "Oxybenzone is a cosmetic ingredient used as a chemical UV filter. Banned in Hawaii, Palau, US Virgin Islands for reef damage. Endocrine disruption concerns. Enters bloodstream rapidly. Photoallergic reactions."),
    ("Parabens", "parabens-cosmetic", 40, True,
     "Parabens is a cosmetic ingredient used as a preservative. Weak estrogen-mimicking activity. 2004 Darbre study (methodological issues) sparked controversy. Still considered safe by FDA and EU at permitted levels. Consumer backlash drove 'paraben-free' trend."),
    ("Methylparaben", "methylparaben-cosmetic", 42, False,
     "Methylparaben is a cosmetic ingredient used as a preservative. Most common paraben. Lowest estrogenic activity of parabens. EU limit: 0.4% alone, 0.8% mixed. Generally safe."),
    ("Propylparaben", "propylparaben-cosmetic", 38, False,
     "Propylparaben is a cosmetic ingredient used as a preservative. Higher estrogenic activity than methylparaben. EU has lowered permitted concentration. Banned in leave-on products for children under 3 in EU."),
    ("Sodium Lauryl Sulfate", "sodium-lauryl-sulfate-cosmetic", 50, True,
     "Sodium Lauryl Sulfate is a cosmetic ingredient used as a surfactant and cleansing agent. Strong detergent. Can be irritating to skin and eyes. Different from SLES. Used in clinical studies as standard irritant."),
    ("SLES", "sles-cosmetic", 55, False,
     "SLES is a cosmetic ingredient used as a gentler surfactant (Sodium Laureth Sulfate). Milder than SLS. 1,4-dioxane contamination concern (byproduct of ethoxylation). Most common shampoo surfactant. Generally safe."),
    ("Phthalates", "phthalates-cosmetic", 25, True,
     "Phthalates is a cosmetic ingredient used as a plasticizer and fragrance fixative. Endocrine disruptors linked to reproductive harm. Several types banned in EU cosmetics. Hidden in 'fragrance' ingredient. DEHP most concerning."),
    ("PFAS in Cosmetics", "pfas-cosmetics", 15, True,
     "PFAS in Cosmetics is a cosmetic ingredient used as a water/oil repellent and texture enhancer. 'Forever chemicals' — bioaccumulative and persistent. Linked to cancer and immune suppression. Being phased out globally. Found in waterproof makeup."),
    ("Formaldehyde Releasers", "formaldehyde-releasers-cosmetic", 20, True,
     "Formaldehyde Releasers is a cosmetic ingredient used as a preservative (DMDM hydantoin, quaternium-15, etc). Release formaldehyde over time. Formaldehyde is a known carcinogen (IARC Group 1). Banned or restricted in many jurisdictions. Keratin treatment controversy."),
    ("Triclosan", "triclosan-cosmetic", 25, True,
     "Triclosan is a cosmetic ingredient used as an antibacterial agent. FDA banned in OTC antiseptic soaps (2016). Endocrine disruption and antibiotic resistance concerns. Still in some toothpastes. Environmental persistence."),
    ("Dimethicone", "dimethicone-cosmetic", 78, False,
     "Dimethicone is a cosmetic ingredient used as a silicone-based emollient and skin protectant. Creates smooth, silky feel. Non-comedogenic. Very safe. Concerns about environmental persistence are debated. FDA approved."),
    ("Silicones", "silicones-cosmetic", 72, False,
     "Silicones is a cosmetic ingredient used as hair smoothing and skin conditioning agents. Cyclomethicone, dimethicone, etc. Provide slip and shine. D4 and D5 restricted in EU for environmental reasons."),
    ("Mineral Oil", "mineral-oil-cosmetic", 60, True,
     "Mineral Oil is a cosmetic ingredient used as an occlusive moisturizer. Petroleum-derived. Highly refined cosmetic grade is non-comedogenic and safe. Unrefined grades are carcinogenic. 'Natural beauty' movement avoids it."),
    ("Fragrance (Parfum)", "fragrance-parfum-cosmetic", 45, True,
     "Fragrance (Parfum) is a cosmetic ingredient used as a scent component. Umbrella term for 3,000+ potential chemicals. Top allergen. No disclosure requirement for individual chemicals (trade secret). Leading cause of cosmetic contact dermatitis."),
    ("Essential Oils Skincare", "essential-oils-skincare", 55, False,
     "Essential Oils Skincare is a cosmetic ingredient used as a natural fragrance and active. Can be highly irritating and sensitizing. Phototoxic (bergamot, citrus). Marketed as 'natural' but not inherently safer."),
    ("Benzoyl Peroxide", "benzoyl-peroxide-cosmetic", 75, True,
     "Benzoyl Peroxide is a cosmetic ingredient used as an acne treatment. Kills acne bacteria. Strong evidence as first-line acne treatment. FDA OTC monograph. Can bleach fabrics. 2.5-10% concentrations. FDA investigating benzene formation concern (2024)."),
    ("Azelaic Acid", "azelaic-acid-cosmetic", 80, False,
     "Azelaic Acid is a cosmetic ingredient used as an anti-acne and brightening active. Naturally produced by yeast on skin. Anti-inflammatory. Good for rosacea and hyperpigmentation. Safe in pregnancy."),
    ("Alpha Arbutin", "alpha-arbutin-cosmetic", 76, False,
     "Alpha Arbutin is a cosmetic ingredient used as a skin brightening agent. Inhibits tyrosinase to reduce melanin production. Safer alternative to hydroquinone. Well-tolerated. Effective at 1-2%."),
    ("Bakuchiol", "bakuchiol-cosmetic", 72, False,
     "Bakuchiol is a cosmetic ingredient used as a plant-based retinol alternative. From Psoralea corylifolia seeds. Moderate evidence for anti-aging. Safe in pregnancy. No photosensitivity."),
    ("Centella Asiatica", "centella-asiatica-cosmetic", 78, False,
     "Centella Asiatica is a cosmetic ingredient used as a soothing and healing agent (Cica). Traditional Asian medicine. Madecassoside and asiaticoside are key actives. Good evidence for wound healing. K-beauty staple."),
    ("Snail Mucin", "snail-mucin-cosmetic", 70, True,
     "Snail Mucin is a cosmetic ingredient used as a hydrating and healing agent. Contains glycoproteins, hyaluronic acid, glycolic acid. K-beauty phenomenon. Moderate evidence for skin repair. Ethical concerns about snail farming."),
    ("Hydroquinone", "hydroquinone-cosmetic", 35, True,
     "Hydroquinone is a cosmetic ingredient used as a skin lightening agent. Most effective depigmenting agent. BANNED in EU and many countries for OTC use. Prescription only in US since 2020. Ochronosis risk with prolonged use."),
    ("Kojic Acid", "kojic-acid-cosmetic", 65, False,
     "Kojic Acid is a cosmetic ingredient used as a skin brightening agent. Derived from fungi (sake production byproduct). Weaker than hydroquinone but safer. Can cause sensitization. Unstable."),
    ("Sunscreen SPF", "sunscreen-spf-cosmetic", 92, True,
     "Sunscreen SPF is a cosmetic ingredient used as UV radiation protection. The most important skincare product for preventing skin cancer and aging. SPF 30 blocks 97% of UVB. Regular use reduces melanoma risk by 50%."),
    ("AHA Blend", "aha-blend-cosmetic", 77, False,
     "AHA Blend is a cosmetic ingredient used as a chemical exfoliant combination. Alpha hydroxy acids (glycolic, lactic, mandelic). Improve texture and tone. pH-dependent efficacy. Sun sensitivity increase."),
    ("BHA (Beta Hydroxy Acid)", "bha-cosmetic", 80, False,
     "BHA (Beta Hydroxy Acid) is a cosmetic ingredient used as an oil-soluble exfoliant. Salicylic acid is the primary BHA. Penetrates pores. Anti-inflammatory. Best for oily and acne-prone skin."),
    ("Ferulic Acid", "ferulic-acid-cosmetic", 79, False,
     "Ferulic Acid is a cosmetic ingredient used as an antioxidant booster. Doubles the photoprotection of vitamins C and E (Pinnell 2005). Plant-derived. Stabilizes L-ascorbic acid."),
    ("Copper Peptides", "copper-peptides-cosmetic", 74, False,
     "Copper Peptides is a cosmetic ingredient used as a wound healing and anti-aging active. GHK-Cu is best studied. Moderate evidence for skin regeneration. Can increase skin sensitivity initially."),
    ("Tranexamic Acid Skincare", "tranexamic-acid-skincare", 77, False,
     "Tranexamic Acid Skincare is a cosmetic ingredient used as a brightening and anti-melasma active. Originally a blood-clotting medication. Emerging evidence for hyperpigmentation. Safe topically. Growing K-beauty and J-beauty trend."),
]


# ─── SEEDING FUNCTION ───────────────────────────────────────────────────────────

SQL_UPSERT = text("""
    INSERT INTO software_registry
        (id, name, slug, registry, description, trust_score, trust_grade,
         enriched_at, created_at, is_king)
    VALUES
        (:id, :name, :slug, :registry, :desc, :score, :grade,
         NOW(), NOW(), :is_king)
    ON CONFLICT (registry, slug) DO UPDATE SET
        name = EXCLUDED.name,
        description = EXCLUDED.description,
        trust_score = EXCLUDED.trust_score,
        trust_grade = EXCLUDED.trust_grade,
        enriched_at = NOW(),
        is_king = EXCLUDED.is_king
""")


def _build_e_number_description(e_num, name, category, function, status, extra):
    return f"{name} ({e_num}) is a food {category} used as {function}. EU status: {status}. {extra}"


def seed():
    """Upsert all ingredient, supplement, and cosmetic_ingredient entities."""
    session = get_session()
    total = 0
    batch = 0

    # ── 1. E-number ingredients ─────────────────────────────────────────────
    log.info("Seeding E-number ingredients...")
    for e_num, (name, score, is_king, category, function, status, extra) in E_NUMBER_OVERRIDES.items():
        slug = _slug(f"{e_num}-{name}")
        grade = _grade(score)
        desc = _build_e_number_description(e_num, name, category, function, status, extra)
        session.execute(SQL_UPSERT, {
            "id": str(uuid4()), "name": f"{e_num} {name}", "slug": slug,
            "registry": "ingredient", "desc": desc, "score": score,
            "grade": grade, "is_king": is_king,
        })
        total += 1
        batch += 1
        if batch >= 200:
            session.commit()
            log.info(f"  Committed batch ({total} so far)")
            batch = 0

    log.info(f"  E-numbers done: {total}")

    # ── 2. Non-E-number ingredients ─────────────────────────────────────────
    log.info("Seeding non-E-number ingredients...")
    for name, slug, score, is_king, desc in NON_E_INGREDIENTS:
        grade = _grade(score)
        session.execute(SQL_UPSERT, {
            "id": str(uuid4()), "name": name, "slug": slug,
            "registry": "ingredient", "desc": desc, "score": score,
            "grade": grade, "is_king": is_king,
        })
        total += 1
        batch += 1
        if batch >= 200:
            session.commit()
            log.info(f"  Committed batch ({total} so far)")
            batch = 0

    log.info(f"  Non-E ingredients done (total: {total})")

    # ── 3. Supplements ──────────────────────────────────────────────────────
    log.info("Seeding supplements...")
    for name, slug, score, is_king, desc in SUPPLEMENTS:
        grade = _grade(score)
        session.execute(SQL_UPSERT, {
            "id": str(uuid4()), "name": name, "slug": slug,
            "registry": "supplement", "desc": desc, "score": score,
            "grade": grade, "is_king": is_king,
        })
        total += 1
        batch += 1
        if batch >= 200:
            session.commit()
            log.info(f"  Committed batch ({total} so far)")
            batch = 0

    log.info(f"  Supplements done (total: {total})")

    # ── 4. Cosmetic ingredients ─────────────────────────────────────────────
    log.info("Seeding cosmetic ingredients...")
    for name, slug, score, is_king, desc in COSMETICS:
        grade = _grade(score)
        session.execute(SQL_UPSERT, {
            "id": str(uuid4()), "name": name, "slug": slug,
            "registry": "cosmetic_ingredient", "desc": desc, "score": score,
            "grade": grade, "is_king": is_king,
        })
        total += 1
        batch += 1
        if batch >= 200:
            session.commit()
            log.info(f"  Committed batch ({total} so far)")
            batch = 0

    # Final commit
    if batch > 0:
        session.commit()

    session.close()
    log.info(f"Seeding complete. Total entities upserted: {total}")
    log.info(f"  - E-number ingredients: {len(E_NUMBER_OVERRIDES)}")
    log.info(f"  - Non-E ingredients: {len(NON_E_INGREDIENTS)}")
    log.info(f"  - Supplements: {len(SUPPLEMENTS)}")
    log.info(f"  - Cosmetic ingredients: {len(COSMETICS)}")


if __name__ == "__main__":
    seed()
