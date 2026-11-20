"""
Transaction categorisation: rule-based keywords + a per-user ML model.

* ML  : TF-IDF (char n-grams) + Logistic Regression, trained ONLY on records whose
        category was chosen by the user (category_source 'manual' or 'user').
        Predictions below CONF_THRESHOLD are not used.
* Rule: keyword fallback (used when ML is not trained or not confident).
* If neither applies: 'Other' (expense) / 'Other Income' (earning), source='default'.

Nothing is pre-trained or bundled: if a user has too few labelled records the model
simply reports "not trained" and rules are used.
"""
import re
import warnings

CONF_THRESHOLD = 0.55
MIN_LABELED = 30          # minimum labelled records (with text) before ML is trained
MIN_PER_CLASS = 2         # classes with fewer labelled examples are left to the rules

DEFAULT_EXPENSE = "Other"
DEFAULT_INCOME = "Other Income"

# (category, keywords) -- matched against the upper-cased text; first matching category wins, so order matters.
# Short keywords (<= 4 letters) are matched as whole words (so "ATM" does not match "SATMAN"); longer ones as substrings.
EXPENSE_RULES = [
    ("Rent", ["RENT", "LANDLORD", "NOBROKER", "HOUSING.COM", "MAINTENANCE CHARGE", "SOCIETY MAINT"]),
    ("Insurance", ["LIC PREMIUM", "LIC OF INDIA", "INSURANCE", "HDFC LIFE", "ICICI PRU", "SBI LIFE", "MAX LIFE",
                   "STAR HEALTH", "CARE HEALTH", "NIVA BUPA", "ACKO", "DIGIT INS", "POLICYBAZAAR", "BAJAJ ALLIANZ",
                   "NEW INDIA ASSUR", "PREMIUM PAID"]),
    ("Investments", ["SIP", "MUTUAL FUND", "ZERODHA", "GROWW", "UPSTOX", "NPS", "PPF", "LIC ", "KUVERA", "COIN BY",
                     "ANGEL ONE", "ANGELONE", "5PAISA", "ICICI DIRECT", "HDFC SEC", "KOTAK SEC", "SMALLCASE",
                     "INDMONEY", "PAYTM MONEY", "NSE CLEARING", "BSE STAR", "FIXED DEPOSIT", "RECURRING DEPOSIT",
                     "SGB", "GOLD BOND", "ELSS", "CDSL", "NSDL", "AMC"]),
    ("EMI & Loans", ["EMI", "LOAN", "BAJAJ FIN", "HOME CREDIT", "HDFC LTD", "TATA CAPITAL", "FULLERTON", "MUTHOOT",
                     "MANAPPURAM", "KREDITBEE", "MONEYVIEW", "LAZYPAY", "SLICE", "ZESTMONEY", "FIBE", "EARLYSALARY",
                     "NACH", "ECS", "ACH D", "ACH-D", "HOME FIN", "LENDINGKART", "PIRAMAL", "CHOLAMANDALAM"]),
    ("Fees & Charges", ["CHARGES", "PENALTY", "SMS CHRG", "ANNUAL FEE", "LATE FEE", "LATE PAYMENT", "MIN BAL",
                        "MINIMUM BALANCE", "AMB CHRG", "DEBIT CARD FEE", "CARD FEE", "PROCESSING FEE", "GST ON",
                        "SERVICE CHARGE", "FOREX MARKUP", "CHEQUE BOOK", "CHQ BOOK", "CONVENIENCE FEE", "STAMP DUTY"]),
    ("Transfers", ["CREDIT CARD BILL", "CC PAYMENT", "CREDIT CARD PAYMENT", "CARD BILL", "SELF TRANSFER",
                   "OWN ACCOUNT", "OWN A/C", "SELF-TRANSFER", "CRED CLUB", "CRED.CLUB", "CREDCLUB"]),
    ("Food", ["SWIGGY", "ZOMATO", "RESTAURANT", "CAFE", "DOMINO", "MCDONALD", "KFC", "STARBUCKS",
              "BIGBASKET", "BLINKIT", "ZEPTO", "INSTAMART", "GROCER", "DMART", "BAKERY", "PIZZA",
              "BURGER", "SUBWAY", "HALDIRAM", "BARBEQUE", "BARISTA", "CHAI POINT", "CHAAYOS", "THIRD WAVE",
              "FAASOS", "BEHROUZ", "EATSURE", "EATFIT", "MAGICPIN", "DUNZO", "JIOMART", "NATURES BASKET",
              "FRESHTOHOME", "LICIOUS", "MILKBASKET", "COUNTRY DELIGHT", "AMUL", "KIRANA", "SUPERMARKET",
              "HOTEL", "DHABA", "BIRYANI", "CANTEEN", "MESS", "TIFFIN", "SWEETS", "DAIRY", "VEGETABLE",
              "FRUIT", "TEA ", "JUICE", "ICE CREAM", "BASKIN", "NAUGHTY", "WAREHOUSE", "RELIANCE FRESH",
              "STAR BAZAAR", "SPENCER", "MORE RETAIL", "RATNADEEP"]),
    ("Travel", ["UBER", "OLA ", "RAPIDO", "IRCTC", "REDBUS", "MAKEMYTRIP", "INDIGO", "AIRLINE",
                "PETROL", "FUEL", "HPCL", "BPCL", "IOCL", "FASTAG", "METRO",
                "OLACABS", "OLA CABS", "MERU", "BLUSMART", "NAMMA YATRI", "YULU", "BOUNCE", "AIR INDIA", "VISTARA",
                "SPICEJET", "AKASA", "GOIBIBO", "YATRA", "CLEARTRIP", "EASEMYTRIP", "ABHIBUS", "MSRTC", "KSRTC",
                "RAILWAY", "SHELL", "RELIANCE BP", "NAYARA", "INDIAN OIL", "PARKING", "TOLL", "AIRBNB", "OYO",
                "TREEBO", "FABHOTEL", "AGODA", "BOOKING.COM", "TAXI", "CAB ", "RAIL", "AIRPORT"]),
    ("Shopping", ["AMAZON", "FLIPKART", "MYNTRA", "AJIO", "NYKAA", "MEESHO", "RETAIL", "MART",
                  "TATA CLIQ", "SNAPDEAL", "LENSKART", "DECATHLON", "IKEA", "CROMA", "RELIANCE DIGITAL",
                  "VIJAY SALES", "PEPPERFRY", "URBAN LADDER", "FIRSTCRY", "BEWAKOOF", "H&M", "ZARA", "WESTSIDE",
                  "PANTALOONS", "LIFESTYLE", "SHOPPERS STOP", "MAX FASHION", "TRENDS", "BATA", "PUMA", "NIKE",
                  "ADIDAS", "UNIQLO", "APPLE", "SAMSUNG", "ONEPLUS", "BOAT LIFESTYLE", "TANISHQ", "CARATLANE",
                  "BLUESTONE", "LEROY", "HOMETOWN", "FASHION", "ELECTRONICS", "BOOKSTORE", "CROSSWORD", "STATIONERY"]),
    ("Bills & Utilities", ["ELECTRIC", "AIRTEL", "JIO", "VODAFONE", "BSNL", "BROADBAND", "RECHARGE",
                           "WATER BILL", "GAS BILL", "TATA POWER", "MSEB", "DTH", "BILLDESK",
                           "MAHANAGAR GAS", "MGL", "INDRAPRASTHA GAS", "ADANI GAS", "ADANI ELECTRICITY", "BESCOM",
                           "TORRENT POWER", "MSEDCL", "BSES", "ACT FIBERNET", "HATHWAY", "TATA PLAY", "TATASKY",
                           "DISH TV", "D2H", "VI ", "VI PREPAID", "VI POSTPAID", "POSTPAID", "PREPAID", "ELECTRICITY",
                           "PIPED GAS", "LPG", "INDANE", "BHARATGAS", "HP GAS", "MUNICIPAL", "PROPERTY TAX",
                           "BBPS", "CABLE", "WIFI", "INTERNET", "FASTWAY", "EXCITEL", "NETBANKING BILL"]),
    ("Entertainment", ["NETFLIX", "SPOTIFY", "HOTSTAR", "PRIME VIDEO", "BOOKMYSHOW", "YOUTUBE",
                       "PVR", "INOX", "TICKET", "DISNEY", "SONYLIV", "ZEE5", "JIOCINEMA", "JIOSAAVN", "GAANA",
                       "APPLE MUSIC", "APPLE.COM/BILL", "GOOGLE PLAY", "PLAYSTATION", "STEAM", "XBOX", "DREAM11",
                       "MPL", "NOVI", "AMAZON PRIME", "AUDIBLE", "KINDLE", "CINEMA", "MULTIPLEX", "CONCERT",
                       "DISTRICT BY ZOMATO", "PAYTM INSIDER", "TIMEZONE", "SMAAASH", "BOWLING", "GAMING"]),
    ("Health", ["PHARMA", "APOLLO", "HOSPITAL", "MEDPLUS", "1MG", "CLINIC", "DIAGNOSTIC", "MEDICAL",
                "NETMEDS", "PHARMEASY", "TATA 1MG", "PRACTO", "LAL PATH", "METROPOLIS", "THYROCARE", "DR ",
                "DENTAL", "DENTIST", "OPTICAL", "EYE CARE", "FORTIS", "MANIPAL", "MAX HEALTH", "CHEMIST",
                "PATHOLOGY", "PHYSIO", "CULT.FIT", "CULTFIT", "CULT FIT", "GYM", "FITNESS", "HEALTHIFYME",
                "SCAN CENTRE", "DRUG"]),
    ("Education", ["TUITION", "COLLEGE", "UDEMY", "COURSERA", "SCHOOL", "EXAM FEE",
                   "UNIVERSITY", "UNACADEMY", "BYJU", "VEDANTU", "PHYSICSWALLAH", "UPGRAD", "SIMPLILEARN",
                   "EDX", "SKILLSHARE", "LINKEDIN LEARN", "COACHING", "ACADEMY", "INSTITUTE", "ADMISSION",
                   "EXAMINATION", "NPTEL", "LIBRARY", "CLASS FEE", "COURSE FEE", "HOSTEL FEE", "SEMESTER"]),
    ("Personal Care", ["SALON", "SPA ", "BARBER", "URBAN COMPANY", "URBANCLAP", "LAKME", "JAWED HABIB", "GREEN TRENDS",
                       "NATURALS", "BEAUTY", "PARLOUR", "PARLOR", "GROOMING", "BODY SHOP", "MAMAEARTH", "WELLNESS"]),
    ("Taxes", ["INCOME TAX", "ADVANCE TAX", "GST PAYMENT", "TDS", "CBDT", "TIN NSDL", "PROFESSIONAL TAX", "NSDL TAX"]),
    ("Cash", ["ATM", "CASH WDL", "CASH WITHDRAWAL", "NWD", "EAW", "CASH WITHDRAW", "ATM WDL"]),
]
INCOME_RULES = [
    ("Salary", ["SALARY", "PAYROLL", "SAL CREDIT", "STIPEND", "SAL FOR", "WAGES", "PAY CREDIT", "BONUS", "INCENTIVE"]),
    ("Interest", ["INTEREST", "INT.PD", "INT PD", "INT CR", "INT.CR", "SB INT", "INT PAID", "CREDIT INT"]),
    ("Refund", ["REFUND", "REVERSAL", "CASHBACK", "REVERSED", "CHARGEBACK", "REFUND OF", "RFND", "CASH BACK",
                "TAX REFUND", "ITR REFUND", "REWARD"]),
    ("Investment Income", ["DIVIDEND", "MATURITY", "REDEMPTION", "DIV CR", "MF REDEMPTION", "SELL SETTLEMENT",
                           "UNIT REDEEM", "SGB INTEREST", "COUPON"]),
]

_SHORT_KW = re.compile(r"^[A-Z0-9]{1,4}$")      # whole-word match for these; everything else is a substring match


def _kw_hit(keyword, text):
    if _SHORT_KW.match(keyword):
        return re.search(r"(?<![A-Z0-9])" + re.escape(keyword) + r"(?![A-Z0-9])", text) is not None
    return keyword in text


def rule_categorize(text, txn_type):
    """Returns the matched category or None."""
    t = " " + re.sub(r"[^A-Z0-9&.@/ ]+", " ", (text or "").upper()) + " "
    rules = EXPENSE_RULES if txn_type == "expense" else INCOME_RULES
    for category, keywords in rules:
        if any(_kw_hit(k, t) for k in keywords):
            return category
    return None


def record_text(r):
    """Text the model sees for a stored record or an import row."""
    parts = [r.get("raw_narration") or "", r.get("receiver_payer") or "",
             r.get("subcategory") or "", r.get("notes") or ""]
    text = " ".join(p for p in parts if p).strip()
    return re.sub(r"\d{5,}", " ", text)   # long reference numbers carry no signal


def _x(text, txn_type):
    return f"{'__exp__' if txn_type == 'expense' else '__inc__'} {text}"


class MLCategorizer:
    def __init__(self):
        self.model = None
        self.info = {"trained": False, "reason": "not trained", "n_labeled": 0,
                     "n_train": 0, "classes": [], "cv_accuracy": None, "cv_folds": None,
                     "min_required": MIN_LABELED, "threshold": CONF_THRESHOLD}

    def train(self, labeled_records):
        from collections import Counter
        data = [(_x(record_text(r), r["type"]), r["category"]) for r in labeled_records
                if record_text(r).strip()]
        self.info["n_labeled"] = len(data)
        counts = Counter(c for _, c in data)
        data = [(x, c) for x, c in data if counts[c] >= MIN_PER_CLASS]
        self.info["n_train"] = len(data)
        classes = sorted({c for _, c in data})
        self.info["classes"] = classes
        if len(data) < MIN_LABELED:
            self.info["reason"] = (f"needs at least {MIN_LABELED} labelled transactions with "
                                   f"text; has {len(data)}")
            return self
        if len(classes) < 2:
            self.info["reason"] = "needs at least 2 categories in the labelled data"
            return self

        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        X = [x for x, _ in data]
        y = [c for _, c in data]

        def build():
            return make_pipeline(
                TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), lowercase=True,
                                sublinear_tf=True),
                LogisticRegression(max_iter=1000, C=10.0))

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.model = build().fit(X, y)
            # honest, measured accuracy (cross-validation on the user's own labels)
            folds = min(5, min(Counter(y).values()))
            if folds >= 2:
                from sklearn.model_selection import cross_val_score, StratifiedKFold
                scores = cross_val_score(build(), X, y, cv=StratifiedKFold(folds, shuffle=True,
                                                                           random_state=0))
                self.info["cv_accuracy"] = round(float(scores.mean()), 3)
                self.info["cv_folds"] = folds
        self.info.update(trained=True, reason="")
        return self

    def predict(self, text, txn_type):
        """Returns (category, confidence) or (None, None) if untrained."""
        if self.model is None:
            return None, None
        proba = self.model.predict_proba([_x(text, txn_type)])[0]
        i = int(proba.argmax())
        return self.model.classes_[i], float(proba[i])


def train_for_user(labeled_records):
    return MLCategorizer().train(labeled_records)


def categorize(ml, text, txn_type):
    """Returns (category, source, confidence). ML first (if confident), then rules."""
    if ml is not None:
        cat, conf = ml.predict(text, txn_type)
        if cat is not None and conf >= CONF_THRESHOLD:
            return cat, "ml", round(conf, 3)
    cat = rule_categorize(text, txn_type)
    if cat:
        return cat, "rule", None
    return (DEFAULT_EXPENSE if txn_type == "expense" else DEFAULT_INCOME), "default", None


def match_existing_name(category, existing):
    """Reuse the user's own spelling/case if the category already exists in their masters."""
    for c in existing:
        if c.lower() == category.lower():
            return c
    return category
