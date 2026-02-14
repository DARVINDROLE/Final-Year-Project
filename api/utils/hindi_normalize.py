"""
Hindi/Devanagari → Romanized keyword normalization for STT transcripts.

When Groq Whisper transcribes Hindi speech, it outputs Devanagari script (e.g. "ओटीपी")
instead of romanized text ("otp"). This module provides a normalization function that
appends romanized equivalents of detected Devanagari keywords so that downstream
keyword matching works regardless of script.

Used by:  PerceptionAgent (context flags, emotion), IntelligenceAgent (intent, risk)
"""

from __future__ import annotations

# ──────────────────────────────────────────────────────────────
# Devanagari → Romanized mapping for security-critical keywords
# Grouped by domain for maintainability
# ──────────────────────────────────────────────────────────────

_DEVANAGARI_TO_ROMAN: dict[str, str] = {
    # --- Scam / Financial ---
    "ओटीपी": "otp",
    "ओ टी पी": "otp",
    "वेरिफिकेशन कोड": "verification code",
    "वेरिफिकेशन": "verification",
    "वेरीफिकेशन": "verification",
    "वेरिफाई": "verify",
    "यूपीआई": "upi",
    "यू पी आई": "upi",
    "क्यूआर": "qr",
    "क्यू आर": "qr",
    "स्कैन": "scan",
    "अकाउंट नंबर": "account number",
    "अकाउंट": "account",
    "बैंक": "bank",
    "आधार": "aadhaar",
    "केवाईसी": "kyc",
    "के वाई सी": "kyc",
    "पैन कार्ड": "pan card",
    "रिफंड": "refund",
    "लॉटरी": "lottery",
    "प्राइज": "prize",
    "विनर": "winner",
    "पेमेंट": "payment",
    "ट्रांसफर": "transfer",
    "पैसा": "paisa",
    "पैसे": "paise",
    "रुपये": "rupees",
    "कैश": "cash",

    # --- Delivery ---
    "डिलिवरी": "delivery",
    "डिलीवरी": "delivery",
    "कूरियर": "courier",
    "पार्सल": "parcel",
    "पैकेज": "package",
    "अमेज़न": "amazon",
    "अमेज़ॉन": "amazon",
    "फ्लिपकार्ट": "flipkart",
    "स्विगी": "swiggy",
    "ज़ोमैटो": "zomato",
    "ऑर्डर": "order",
    "कम्प्लीट": "complete",

    # --- Aggression / Threat ---
    "देख लेना": "dekh lena",
    "मार": "maar",
    "मारूंगा": "maarunga",
    "मार दूंगा": "maar dunga",
    "तोड़ेंगे": "todenge",
    "तोड़ दूंगा": "tod dunga",
    "वरना": "warna",
    "धमकी": "dhamki",
    "चाकू": "chaku",
    "गोली": "goli",
    "जान से": "jaan se",
    "दरवाज़ा तोड़": "darwaza tod",
    "दरवाजा तोड़": "darwaza tod",
    "खोल वरना": "khol warna",
    "बर्बाद": "barbad",
    "ख़तम": "khatam",
    "खतम": "khatam",

    # --- Distress / Emergency ---
    "बचाओ": "bachao",
    "मदद": "madad",
    "आग": "aag",
    "लगी": "lagi",
    "खो गई": "kho gayi",
    "खो गया": "kho gaya",
    "दर्द": "dard",
    "चोट": "chot",
    "खून": "khoon",
    "हॉस्पिटल": "hospital",
    "एम्बुलेंस": "ambulance",
    "पुलिस": "police",

    # --- Occupancy probe ---
    "कोई घर पे": "koi ghar pe",
    "कोई घर पर": "koi ghar pe",
    "कोई है": "koi hai",
    "घर पे है": "ghar pe hai",
    "घर पर है": "ghar pe hai",
    "कौन है घर": "kaun hai ghar",
    "ओनर है क्या": "owner hai kya",
    "घर खाली": "ghar khali",

    # --- Entry request ---
    "अंदर आना": "andar aana",
    "अंदर आने": "andar aane",
    "दरवाज़ा खोल": "darwaza khol",
    "दरवाजा खोल": "darwaza khol",
    "दरवाज़ा खोलो": "darwaza khol",
    "गेट खोल": "gate khol",

    # --- Identity / Staff / Authority claims ---
    "ओनर ने बोला": "owner ne bola",
    "ओनर": "owner",
    "रिलेटिव": "relative",
    "रिलेटिव हूं": "relative hoon",
    "चाचा हूं": "chacha hoon",
    "मामा हूं": "mama hoon",
    "फ्रेंड हूं": "friend hoon",
    "फैमिली मेंबर": "family member",
    "घर वाले": "ghar wale",
    "काम करूंगी": "kaam karungi",
    "काम करता": "kaam karta",
    "बाई": "bai",
    "मेड": "maid",
    "पुरानी बाई": "purani bai",
    "सफ़ाई": "safai",
    "सफाई": "safai",
    "ड्राइवर": "driver",
    "चाबी": "chaabi",

    # --- Government / Authority ---
    "सरकारी": "sarkari",
    "गवर्नमेंट": "government",
    "कोर्ट": "court",
    "लीगल नोटिस": "legal notice",
    "टैक्स": "tax",
    "इंस्पेक्शन": "inspection",
    "बिजली": "bijli",
    "इलेक्ट्रिसिटी": "electricity",
    "गैस": "gas",
    "गैस लीक": "gas leak",
    "वॉटर बोर्ड": "water board",
    "मीटर रीडिंग": "meter reading",
    "सेंसस": "census",
    "सर्वे": "survey",

    # --- Religious / Donation ---
    "चंदा": "chanda",
    "डोनेशन": "donation",
    "मंदिर": "mandir",
    "टेम्पल": "temple",
    "मस्जिद": "masjid",
    "चर्च": "church",
    "गुरुद्वारा": "gurudwara",
    "हवन": "havan",
    "पूजा": "puja",
    "भगवान": "bhagwan",
    "गणपति": "ganpati",
    "दुर्गा": "durga",

    # --- Sales ---
    "फ्री डेमो": "free demo",
    "ऑफर": "offer",
    "डिस्काउंट": "discount",
    "इंश्योरेंस": "insurance",
    "पॉलिसी": "policy",
    "वाटर प्यूरिफायर": "water purifier",
    "प्यूरिफायर": "purifier",
    "ब्रॉडबैंड": "broadband",
    "लोन": "loan",

    # --- Child / Elderly ---
    "मम्मी खो गई": "mummy kho gayi",
    "मम्मी": "mummy",
    "पापा खो गए": "papa kho gaye",
    "बच्चा": "bachcha",
    "पानी मिलेगा": "paani milega",
    "भाई साहब": "bhai sahab",
    "घर नहीं मिल रहा": "ghar nahi mil raha",

    # --- Common verbs/phrases ---
    "बता दीजिए": "bata dijiye",
    "बता दीजे": "bata dijiye",
    "पता दीजे": "bata dijiye",
    "पता दीजिए": "bata dijiye",
    "बताओ": "batao",
    "बता दो": "bata do",
    "कर दीजिए": "kar dijiye",
    "कर दो": "kar do",
    "खोलो": "kholo",
    "खोल दो": "khol do",
    "आने दो": "aane do",
    "ज़रूरी": "zaroori",
    "जरूरी": "zaroori",
    "बहुत ज़रूरी": "bahut zaroori",
}


def normalize_hindi_transcript(text: str) -> str:
    """Normalize a transcript that may contain Devanagari script.

    Returns a string that contains both the original text AND romanized
    equivalents of any detected Devanagari keywords, separated by spaces.
    This allows downstream keyword matching to work regardless of script.

    Example:
        Input:  "सर्व ओटीपी पता दीजे डिलिवरी कम्प्लीट करना है"
        Output: "सर्व ओटीपी पता दीजे डिलिवरी कम्प्लीट करना है otp bata dijiye delivery complete"
    """
    if not text:
        return text

    # Check if any Devanagari characters present (Unicode block: U+0900–U+097F)
    has_devanagari = any("\u0900" <= ch <= "\u097F" for ch in text)
    if not has_devanagari:
        return text  # already romanized, no normalization needed

    # Build romanized additions
    text_lower = text.lower()
    roman_additions: list[str] = []

    # Sort by length descending so longer phrases match first
    sorted_mappings = sorted(_DEVANAGARI_TO_ROMAN.items(), key=lambda x: len(x[0]), reverse=True)

    for devanagari, roman in sorted_mappings:
        if devanagari in text_lower:
            roman_additions.append(roman)

    if roman_additions:
        # Append romanized keywords to original transcript
        return text + " " + " ".join(roman_additions)

    return text
