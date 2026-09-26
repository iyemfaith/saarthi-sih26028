"""Display names for trains and cities, in English and Hindi.

The dataset's train names are raw NTES abbreviations ("Pnbe Anvt Sf Special",
"Kolkata Rajdhni"). Boards and SMS need clean names: code-style names are
rebuilt as "Origin-Destination <type>", proper names are spelling-fixed, and
both are rendered in Devanagari from a curated dictionary (no machine
transliteration, so no mangled names on a public board).
"""
import re

CITY = {  # dataset station name -> (clean English, Hindi)
    "Kanpur Central": ("Kanpur", "कानपुर"), "Ahmedabad": ("Ahmedabad", "अहमदाबाद"), "Patna": ("Patna", "पटना"),
    "Delhi": ("Delhi", "दिल्ली"), "Anand Vihar Terminal": ("Anand Vihar", "आनंद विहार"),
    "Rajendra Nagar": ("Rajendra Nagar", "राजेंद्र नगर"), "New Delhi": ("New Delhi", "नई दिल्ली"),
    "Gaya": ("Gaya", "गया"), "Kamakhya": ("Kamakhya", "कामाख्या"), "Barauni": ("Barauni", "बरौनी"),
    "Darbhanga": ("Darbhanga", "दरभंगा"), "Howrah": ("Howrah", "हावड़ा"), "Khatipura": ("Khatipura", "खातीपुरा"),
    "Sealdah": ("Sealdah", "सियालदह"), "Vadodara": ("Vadodara", "वडोदरा"), "Danapur": ("Danapur", "दानापुर"),
    "Malda Town": ("Malda Town", "मालदा टाउन"), "Bhagalpur": ("Bhagalpur", "भागलपुर"),
    "Asansol": ("Asansol", "आसनसोल"), "Ballia": ("Ballia", "बलिया"), "Subedarganj": ("Subedarganj", "सूबेदारगंज"),
    "Lokmanyatilak": ("Mumbai LTT", "मुंबई एलटीटी"), "Secunderabad": ("Secunderabad", "सिकंदराबाद"),
    "Bandra Terminus": ("Bandra Terminus", "बांद्रा टर्मिनस"), "Tundla": ("Tundla", "टूंडला"),
    "Gorakhpur": ("Gorakhpur", "गोरखपुर"), "Muzaffarpur": ("Muzaffarpur", "मुज़फ़्फ़रपुर"), "Kota": ("Kota", "कोटा"),
    "Samastipur": ("Samastipur", "समस्तीपुर"), "Amritsar": ("Amritsar", "अमृतसर"), "Katihar": ("Katihar", "कटिहार"),
    "Udhna": ("Udhna", "उधना"), "Ghazipur City": ("Ghazipur City", "गाज़ीपुर सिटी"), "Surat": ("Surat", "सूरत"),
    "Mumbai Central": ("Mumbai Central", "मुंबई सेंट्रल"), "Banaras": ("Banaras", "बनारस"), "Mau": ("Mau", "मऊ"),
    "Sabarmati Bg": ("Sabarmati", "साबरमती"), "Hapa": ("Hapa", "हापा"), "Naharlagun": ("Naharlagun", "नाहरलागुन"),
    "Rajkot": ("Rajkot", "राजकोट"), "Lucknow": ("Lucknow", "लखनऊ"), "Dehradoon": ("Dehradun", "देहरादून"),
    "Kathgodam": ("Kathgodam", "काठगोदाम"), "Agra Fort": ("Agra Fort", "आगरा फोर्ट"),
    "Azamgarh": ("Azamgarh", "आज़मगढ़"), "Madhupur": ("Madhupur", "मधुपुर"), "Bikaner": ("Bikaner", "बीकानेर"),
    "Bhubaneswar": ("Bhubaneswar", "भुवनेश्वर"), "Jodhpur": ("Jodhpur", "जोधपुर"), "Kalka": ("Kalka", "कालका"),
    "Kolkatta Terminal": ("Kolkata", "कोलकाता"), "Udaipur City": ("Udaipur City", "उदयपुर सिटी"),
    "Gwalior": ("Gwalior", "ग्वालियर"), "Barmer": ("Barmer", "बाड़मेर"), "Godda": ("Godda", "गोड्डा"),
    "Rajgir": ("Rajgir", "राजगीर"), "Ajmer": ("Ajmer", "अजमेर"), "Lalgarh": ("Lalgarh", "लालगढ़"),
    "Prayagraj": ("Prayagraj", "प्रयागराज"), "Dibrugarh": ("Dibrugarh", "डिब्रूगढ़"), "Rewa": ("Rewa", "रीवा"),
    "Jaynagar": ("Jaynagar", "जयनगर"), "Haldia": ("Haldia", "हल्दिया"), "Ranchi": ("Ranchi", "रांची"),
    "Jogbani": ("Jogbani", "जोगबनी"), "New Jalpaiguri": ("New Jalpaiguri", "न्यू जलपाईगुड़ी"),
    "Saharsa": ("Saharsa", "सहरसा"), "Bathinda": ("Bathinda", "बठिंडा"), "Puri": ("Puri", "पुरी"),
    "Hatia": ("Hatia", "हटिया"), "Gandhidham Bg": ("Gandhidham", "गांधीधाम"),
    "Bhavnagar Terminus": ("Bhavnagar", "भावनगर"), "Veraval": ("Veraval", "वेरावल"),
    "Balurghat": ("Balurghat", "बालुरघाट"), "Sitamarhi": ("Sitamarhi", "सीतामढ़ी"),
    "Meerut Cant": ("Meerut Cantt", "मेरठ कैंट"), "Shri Ganganagar": ("Sri Ganganagar", "श्रीगंगानगर"),
    "Shri Mata Vaishno Devi Katra": ("Katra", "कटरा"), "Silchar": ("Silchar", "सिलचर"),
    "Bhiwani": ("Bhiwani", "भिवानी"), "Meerut City": ("Meerut City", "मेरठ सिटी"),
    "Prayagraj Sangam": ("Prayagraj Sangam", "प्रयागराज संगम"), "Chandigarh": ("Chandigarh", "चंडीगढ़"),
    "Bareilly(nr)": ("Bareilly", "बरेली"), "Agartala": ("Agartala", "अगरतला"),
    "Firozpur Cant": ("Firozpur Cantt", "फ़िरोज़पुर कैंट"), "Jalandhar City": ("Jalandhar City", "जालंधर सिटी"),
    "Varanasi City": ("Varanasi City", "वाराणसी सिटी"), "Okha": ("Okha", "ओखा"),
    "Alipur Duar": ("Alipurduar", "अलीपुरद्वार"), "Guwahati": ("Guwahati", "गुवाहाटी"),
    "Jammutavi": ("Jammu Tawi", "जम्मू तवी"), "Tatanagar": ("Tatanagar", "टाटानगर"),
    "Sambalpur": ("Sambalpur", "संबलपुर"), "Agra Cantt": ("Agra Cantt", "आगरा कैंट"),
    "Varanasi": ("Varanasi", "वाराणसी"), "Indore": ("Indore", "इंदौर"), "Islampur": ("Islampur", "इस्लामपुर"),
    "Ayodhya Cantt": ("Ayodhya Cantt", "अयोध्या कैंट"), "Martyr Captain Tushar Mahajan": ("Udhampur", "उधमपुर"),
    "Chitrakot": ("Chitrakoot", "चित्रकूट"), "Santragachi": ("Santragachi", "संतरागाछी"),
    "Kanpur Anwrganj": ("Kanpur Anwarganj", "कानपुर अनवरगंज"),
}

# Spelling fixes / expansions for proper-name tokens, then their Hindi.
FIX = {"rajdhni": "Rajdhani", "shtbdi": "Shatabdi", "shatabadi": "Shatabdi", "shatabdii": "Shatabdi",
       "sht": "Shatabdi", "janshatabdii": "Jan Shatabdi", "janshatabdi": "Jan Shatabdi", "humsfr": "Humsafar",
       "hmsfr": "Humsafar", "humsafr": "Humsafar", "krnti": "Kranti", "porvotr": "Purvottar",
       "shkti": "Shakti", "lichchvi": "Lichchavi", "lichchivi": "Lichchavi", "neelanchal": "Neelachal",
       "farkka": "Farakka", "brahmputra": "Brahmaputra", "garbha": "Garba", "swtantrta": "Swatantrata",
       "swatantra": "Swatantrata", "sikkimmahananda": "Sikkim Mahananda", "chaurichaura": "Chauri Chaura",
       "shramjivi": "Shramjeevi", "sampooran": "Sampoorna", "sf": "SF", "sup": "SF", "suf": "SF",
       "sfast": "SF", "sfexp": "SF Express", "raj": "Rajdhani", "ac": "AC", "memu": "MEMU", "irctc": "",
       "festval": "Festival", "hspecial": "Special", "wkly": "Weekly", "bi": "Bi-weekly", "northeast": "North East"}
PHRASE = [(r"\bS Kranti\b", "Sampark Kranti"), (r"\bSampoorna K\b", "Sampoorna Kranti"),
          (r"\bSwatantrata S\b", "Swatantrata Senani"), (r"\bKashi V Nath\b", "Kashi Vishwanath"),
          (r"\bBaba [BV] Dham\b", "Baba Baidyanath Dham"), (r"\bBv Dham\b", "Baba Baidyanath Dham")]
HI = {
    "Express": "एक्सप्रेस", "Mail": "मेल", "Special": "स्पेशल", "SF": "सुपरफ़ास्ट", "Rajdhani": "राजधानी",
    "Shatabdi": "शताब्दी", "Jan": "जन", "Duronto": "दुरंतो", "Humsafar": "हमसफ़र", "Garib": "गरीब", "Rath": "रथ",
    "Tejas": "तेजस", "Vande": "वंदे", "Bharat": "भारत", "Amrit": "अमृत", "Intercity": "इंटरसिटी", "AC": "एसी",
    "MEMU": "मेमू", "Swaran": "स्वर्ण", "Kaifiyat": "कैफ़ियत", "Poorva": "पूर्वा", "Netaji": "नेताजी",
    "Ananya": "अनन्या", "Shramjeevi": "श्रमजीवी", "Sampoorna": "संपूर्ण", "Kranti": "क्रांति", "Sampark": "संपर्क",
    "Ziyarat": "ज़ियारत", "Mahabodhi": "महाबोधि", "Prayagraj": "प्रयागराज", "Gomti": "गोमती", "Haldiya": "हल्दिया",
    "Shram": "श्रम", "Shakti": "शक्ति", "Seemanchal": "सीमांचल", "Pratap": "प्रताप", "North": "नॉर्थ", "East": "ईस्ट",
    "Vaishali": "वैशाली", "Gorakhdham": "गोरखधाम", "Shiv": "शिव", "Ganga": "गंगा", "Swatantrata": "स्वतंत्रता",
    "Senani": "सेनानी", "Bihar": "बिहार", "Purushottam": "पुरुषोत्तम", "Nandankanan": "नंदनकानन",
    "Swarnjayanti": "स्वर्ण जयंती", "Jharkhand": "झारखंड", "Neelachal": "नीलांचल", "Garba": "गरबा",
    "Parasnath": "पारसनाथ", "Banaras": "बनारस", "Azimabad": "अज़ीमाबाद", "Farakka": "फरक्का",
    "Lichchavi": "लिच्छवी", "Jammu": "जम्मू", "Purvottar": "पूर्वोत्तर", "Kalindi": "कालिंदी", "Sangam": "संगम",
    "Unchahar": "ऊंचाहार", "Tripura": "त्रिपुरा", "Sundari": "सुंदरी", "Marudhar": "मरुधर", "Chauri": "चौरी",
    "Chaura": "चौरा", "Kashi": "काशी", "Vishwanath": "विश्वनाथ", "Jansadharan": "जनसाधारण", "Sikkim": "सिक्किम",
    "Mahananda": "महानंदा", "Brahmaputra": "ब्रह्मपुत्र", "Kamakhya": "कामाख्या", "Champaran": "चंपारण",
    "Avadh": "अवध", "Uttaranchal": "उत्तरांचल", "Mahakal": "महाकाल", "Magadh": "मगध", "Mahamana": "महामना",
    "Bhrigu": "भृगु", "Suhaldev": "सुहेलदेव", "Baba": "बाबा", "Baidyanath": "बैद्यनाथ", "Dham": "धाम",
    "Lucknow": "लखनऊ", "Guwahati": "गुवाहाटी", "Kathgodam": "काठगोदाम", "Kolkata": "कोलकाता",
    "Madhupur": "मधुपुर", "Rewa": "रीवा", "Festival": "फ़ेस्टिवल", "Summer": "समर", "Weekly": "साप्ताहिक",
    "Bi-weekly": "द्वि-साप्ताहिक", "Clone": "क्लोन", "One": "वन", "Way": "वे", "Sealdah": "सियालदह",
    "Haldia": "हल्दिया",
}
TYPE_WORDS = ["Rajdhani", "Duronto", "Humsafar", "Garib Rath", "Jan Shatabdi", "Shatabdi", "Intercity", "MEMU",
              "Tejas", "Vande Bharat", "Amrit Bharat"]


def _tokens(name):
    out = []
    for w in re.findall(r"[A-Za-z]+", name):
        f = FIX.get(w.lower(), w.capitalize() if w.islower() else w)
        if f:
            out.append(f)
    s = " ".join(out)
    for pat, rep in PHRASE:
        s = re.sub(pat, rep, s)
    return s


def hi_words(s):
    return " ".join(HI.get(w, w) for w in s.split())


def display(train, name, origin_name, dest_name, codes):
    """-> (English, Hindi) display name."""
    raw = [w for w in re.findall(r"[A-Za-z]+", name)]
    has_code = any(w.upper() in codes and w.upper() not in ("SF", "ONE", "WAY") for w in raw)
    clean = _tokens(name)
    if has_code or not clean:
        o_en, o_hi = CITY.get(origin_name, (origin_name, origin_name))
        d_en, d_hi = CITY.get(dest_name, (dest_name, dest_name))
        kind = next((t for t in TYPE_WORDS if t in clean), None)
        if kind == "Tejas" and "Rajdhani" in clean:
            kind = "Tejas Rajdhani"
        if kind is None:
            kind = "Special" if "Special" in clean else "Express"
            if "SF" in clean.split():
                kind = "SF " + kind
        en = f"{o_en}–{d_en} {kind}"
        hi = f"{o_hi}–{d_hi} {hi_words(kind)}"
        return en, hi
    if not any(k in clean for k in ("Express", "Mail", "Special", "Rajdhani", "Shatabdi", "Duronto",
                                     "Humsafar", "Rath", "Intercity", "Kranti", "Sundari")):
        clean += " Express"
    clean = clean.replace("SF Express", "SF Express").replace("  ", " ").strip()
    return clean, hi_words(clean)


def short(en, n=18):
    """Board-width abbreviation in the style Indian boards use."""
    s = en.replace("Express", "Exp").replace("Special", "Spl").replace("Superfast", "SF")
    s = s.replace("Rajdhani", "Rajdhani").replace("Humsafar", "Humsafar")
    return s if len(s) <= n else s[:n - 1] + "."
