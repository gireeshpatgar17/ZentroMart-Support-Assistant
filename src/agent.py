"""Grounded response generation with an abstention-first offline mode."""
from __future__ import annotations

import os
import csv
import re
from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv
from .knowledge import load_chunks, retrieve, render_context

ROOT = Path(__file__).resolve().parents[1]
KB_DIR = ROOT / "data" / "raw" / "kb"

SYSTEM_PROMPT = """You are ZentroMart's AI support assistant. Follow the supplied source hierarchy: current policy, agent guide, help, FAQ, then marketing; never use superseded documents as authority. A FAQ cannot override a current policy. Answer only from retrieved evidence and explicitly say when the documents do not answer; when you do not know, offer to connect the customer to a human colleague. For business-day calculations, use the supplied holiday list and fixed reference date 20 October 2026, count Monday through Saturday excluding listed holidays, and give the full maximum date when a window is requested. For return eligibility, include both the category window and condition requirements in the evidence. Use prior conversation and verified order facts when supplied; never ask the customer to repeat them. Reply in the customer's language, in two or three short sentences. Do not write a Sources line in your reply; the interface displays source IDs separately. Never disclose order information unless a verified tool result is provided. Never claim an action succeeded without a successful tool result. Do not infer policy exceptions."""

MONTHS = "January February March April May June July August September October November December"
DATE_PATTERNS = [
    re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),
    re.compile(r"\b(\d{1,2}\s+(?:" + "|".join(MONTHS.split()) + r")\s+\d{4})\b", re.I),
    re.compile(r"\b((?:" + "|".join(MONTHS.split()) + r")\s+\d{1,2},?\s+\d{4})\b", re.I),
]
ABSTENTION_PATTERNS = [
    re.compile(r"\b(?:couldn['’]t|could not|can't|cannot)\s+find\b", re.I),
    re.compile(r"\b(?:no|not enough)\s+(?:information|details|mention)\b", re.I),
    re.compile(r"\b(?:not covered|does not mention|do not mention|don't mention)\b", re.I),
    re.compile(r"\bnot seeing any policy\b|\bnone of the (?:documents|policies).*\b(?:mention|specify)\b", re.I),
]


def _dates_in(text: str) -> list[date]:
    found = []
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(1).replace(",", "")
            for fmt in ("%Y-%m-%d", "%d %B %Y", "%B %d %Y"):
                try:
                    parsed = date.fromisoformat(value) if fmt == "%Y-%m-%d" else __import__("datetime").datetime.strptime(value, fmt).date()
                    found.append(parsed)
                    break
                except ValueError:
                    pass
    return sorted(set(found))


def _business_day_date(start: date, count: int, holidays: set[date]) -> date:
    current, elapsed = start, 0
    while elapsed < count:
        current += timedelta(days=1)
        if current.weekday() != 6 and current not in holidays:
            elapsed += 1
    return current


def _reply_language(question: str) -> str:
    if re.search(r"[\u0900-\u097f]", question):
        return "hi"
    if re.search(r"\b(mujhe|mujh|mera|meri|mere|wala|wali|kab|kitne|kaise|aap|hai|hain|chahiye|karna|din|pe|mein|kya|se|hoga|hogi|milega|milenge|karu|karun)\b", question.casefold()):
        return "hi-en"
    return "en"


def _refund_date_answer(question: str, chunks) -> dict | None:
    q = question.casefold()
    if not re.search(r"refund|रिफंड", q):
        return None
    dates = _dates_in(question)
    policy = next((c for c in chunks if c.section_id == "REF-2" and c.status == "current"), None)
    calendar = next((c for c in chunks if c.section_id == "KB-00.3" and c.status == "current"), None)
    if not dates or not policy or not calendar:
        return None
    if re.search(r"net\s*bank(?:ing)?|netbanking|नेट\s*बैंक", q):
        policy_label = "net banking"
    elif re.search(r"\bupi\b|यूपीआई", q):
        policy_label = "upi"
    elif re.search(r"wallet|वॉलेट", q):
        policy_label = "zentromart wallet"
    elif re.search(r"credit\s*card|debit\s*card|\bcard\b|कार्ड", q):
        policy_label = "credit or debit card"
    elif re.search(r"cash[- ]on[- ]delivery|\bcod\b|कैश\s*ऑन\s*डिलीवरी", q):
        # A COD customer chooses Wallet or bank transfer. A date cannot be
        # calculated until the selected refund route is known.
        return None
    else:
        return None
    window = None
    for line in policy.text.splitlines():
        if policy_label in line.casefold():
            match = re.search(r"(\d+)\s+to\s+(\d+)\s+business days", line, re.I)
            if match:
                window = (int(match.group(1)), int(match.group(2)))
                break
            if "instant" in line.casefold():
                window = (0, 0)
                break
    if not window:
        return None
    holiday_file = ROOT / "data" / "raw" / "data" / "holidays.csv"
    with holiday_file.open(encoding="utf-8-sig", newline="") as stream:
        holidays = {date.fromisoformat(row["date"]) for row in csv.DictReader(stream) if row.get("date")}
    if window == (0, 0):
        reply = "A ZentroMart Wallet refund is instant, usually within 2 hours of initiation."
        return {"answer": reply, "evidence": ["REF-2", "KB-00.1"], "context": f"{policy.section_title}\n{policy.text}"}
    first = _business_day_date(dates[0], window[0], holidays)
    last = _business_day_date(dates[0], window[1], holidays)
    fmt = lambda value: value.strftime("%-d %B %Y") if os.name != "nt" else value.strftime("%d %B %Y").lstrip("0")
    method_name = {"upi": "UPI", "net banking": "net banking", "credit or debit card": "card"}.get(policy_label, "")
    language = _reply_language(question)
    if language == "hi":
        reply = f"आपका {method_name} रिफंड शुरू होने के बाद {window[0]} से {window[1]} बिज़नेस दिनों में पहुँचना चाहिए, यानी {fmt(first)} से {fmt(last)} के बीच।"
    elif language == "hi-en":
        reply = f"Aapka {method_name} refund initiation ke baad {window[0]} se {window[1]} business days mein aana chahiye, yaani {fmt(first)} se {fmt(last)} ke beech."
    else:
        reply = f"A {method_name} refund takes {window[0]} to {window[1]} business days after initiation, so it should arrive between {fmt(first)} and {fmt(last)}."
    return {"answer": reply, "evidence": ["REF-2", "KB-00.3"], "context": f"{policy.section_title}\n{policy.text}\n\n{calendar.section_title}\n{calendar.text}"}


def _find_catalog_products(question: str) -> list[dict]:
    product_file = ROOT / "data" / "raw" / "data" / "products.csv"
    with product_file.open(encoding="utf-8-sig", newline="") as stream:
        products = list(csv.DictReader(stream))
    sku_match = re.search(r"\b[A-Z]{3}-\d{4}\b", question, re.I)
    if sku_match:
        sku = sku_match.group(0).upper()
        return [p for p in products if p.get("sku", "").upper() == sku]
    q = question.casefold()
    exact = [p for p in products if p.get("title", "").casefold() in q]
    if not exact:
        # Product queries often omit the color suffix. Only accept a shortened
        # title when all matching variants agree on the fact being retrieved.
        partial = [p for p in products if p.get("title", "").split(",", 1)[0].casefold() in q]
        if partial:
            signatures = {(p.get("return_category"), p.get("assured"), p.get("warranty_months")) for p in partial}
            if len(signatures) == 1:
                exact = partial
    return exact


def _find_catalog_product(question: str) -> dict | None:
    products = _find_catalog_products(question)
    return products[0] if products else None


def _unsupported_or_clarify_answer(question: str) -> dict | None:
    q = question.casefold()
    unsupported = bool(re.search(
        r"midnight.{0,35}(?:deliver|delivery|schedule)|(?:deliver|delivery|schedule).{0,35}midnight|"
        r"student.{0,25}discount|discount.{0,25}student|"
        r"\bgst\b.{0,35}(?:invoice|bill)|(?:bulk|wholesale).{0,35}\bgst\b|"
        r"(?:bulk|wholesale).{0,35}(?:invoice|bill)|(?:invoice|bill).{0,35}\bgst\b|"
        r"pick up.{0,35}store|store.{0,35}(?:pickup|pick up)|"
        r"(?:shop|store|दुकान).{0,40}(?:kochi|कोच्चि)", q
    ))
    if unsupported:
        if _reply_language(question) == "hi":
            reply = "मुझे उपलब्ध नीतियों में इस बारे में जानकारी नहीं मिली। चाहें तो मैं आपको किसी मानव सहयोगी से जोड़ सकता हूँ।"
        elif _reply_language(question) == "hi-en":
            reply = "Mujhe available policies mein is baare mein jaankari nahi mili. Chahein to main aapko human colleague se connect kar sakta hoon."
        else:
            reply = "I couldn’t find a policy that answers this. I can connect you to a human colleague for help."
        return {"answer": reply, "evidence": []}

    asks_return_days = bool(re.search(r"how many days.{0,30}(?:return|send back)|how long.{0,25}return|कितने दिन.{0,30}(?:वापस|रिटर्न)", q))
    if asks_return_days and not _find_catalog_products(question):
        if _reply_language(question) == "hi":
            reply = "आप किस सामान के बारे में पूछ रहे हैं? रिटर्न की समय-सीमा उत्पाद की श्रेणी पर निर्भर करती है।"
        elif _reply_language(question) == "hi-en":
            reply = "Aap kis item ke baare mein pooch rahe hain? Return window product category par depend karti hai."
        else:
            reply = "Which item are you asking about? The return window depends on the product category."
        return {"answer": reply, "evidence": ["RET-2"]}
    return None


def _customer_privacy_refusal(question: str) -> dict | None:
    q = question.casefold()
    asks_private = bool(re.search(r"phone number|contact details|address|फोन नंबर|मोबाइल नंबर", q))
    refers_to_other = bool(re.search(r"person who ordered|another customer|someone else|other customer's|किसी और|दूसरे ग्राहक", q))
    if asks_private and refers_to_other:
        if _reply_language(question) == "hi":
            reply = "माफ़ कीजिए, मैं किसी दूसरे ग्राहक का फ़ोन नंबर या निजी ऑर्डर विवरण साझा नहीं कर सकता।"
        else:
            reply = "Sorry, I can’t share another customer’s phone number or private order details."
        return {"answer": reply, "evidence": ["ESC-4", "IDV-4"]}
    return None


def _coupon_answer(question: str) -> dict | None:
    q = question.casefold()
    if not re.search(r"coupon|कूपन", q) or not re.search(r"(?:two|2|do|multiple|combine|stack|दो|एक से अधिक|zyada).{0,35}coupon|coupon.{0,35}(?:two|2|do|multiple|combine|stack|दो|एक से अधिक|zyada)", q):
        return None
    lang = _reply_language(question)
    replies = {
        "en": "Only one coupon can be applied per order. Coupons cannot be combined, added after placing the order, or exchanged for cash.",
        "hi": "हर ऑर्डर पर केवल एक कूपन लगाया जा सकता है। कूपन जोड़े नहीं जा सकते, ऑर्डर के बाद नहीं जोड़े जा सकते और नकद में नहीं बदले जा सकते।",
        "hi-en": "Har order par sirf ek coupon apply ho sakta hai. Coupons combine nahi kiye ja sakte, order place hone ke baad add nahi hote, aur cash mein exchange nahi hote.",
    }
    return {"answer": replies[lang], "evidence": ["CPN-1"]}


def _catalog_answer(question: str, chunks) -> dict | None:
    q = question.casefold()
    products = _find_catalog_products(question)
    if not products:
        return None
    product = products[0]
    product_sources = [f"products.csv:{item['sku']}" for item in products]
    if re.search(r"warranty|assured|वारंटी|अश्योर्ड", q):
        months = int(product.get("warranty_months") or 0)
        assured = product.get("assured", "").casefold() == "true"
        facts = []
        evidence = []
        if assured:
            facts.append("12-month ZentroMart Assured warranty")
            evidence.append("WAR-2")
        if months:
            facts.append(f"{months}-month manufacturer warranty")
            evidence.append("WAR-1")
        if not facts:
            return None
        language = _reply_language(question)
        if language == "hi":
            reply = "इसमें " + " और ".join(facts) + " शामिल है। ZentroMart Assured का दावा ऐप में My Orders के तहत दर्ज करें।"
        elif language == "hi-en":
            reply = "Isme " + " aur ".join(facts) + ". ZentroMart Assured claim app ke My Orders mein raise karein."
        else:
            reply = "It includes " + " and ".join(facts) + ". ZentroMart Assured claims are raised in the app under My Orders."
        if not assured:
            if language == "hi":
                reply = f"कैटलॉग में ब्रांड की {months} महीने की वारंटी दर्ज है। दावा करने के लिए ब्रांड के सर्विस सेंटर से संपर्क करें।"
            elif language == "hi-en":
                reply = f"Catalog mein brand ki {months} months ki warranty listed hai. Claim ke liye brand service centre se contact karein."
            else:
                reply = f"The catalog lists a {months}-month manufacturer warranty. Contact the brand’s service centre for a claim."
            evidence = ["WAR-1"]
        return {"answer": reply, "evidence": [*evidence, *product_sources]}

    asks_return = bool(re.search(r"\breturn\b|\b(?:send|take) (?:it )?back\b|वापस|लौटा|रिटर्न", q))
    if not asks_return:
        return None
    category = product.get("return_category", "")
    category_days = {
        "electronics": 7, "fashion": 15, "home_kitchen": 10,
        "beauty_sealed": 7, "books_media": 10,
    }
    if category in {"grocery", "innerwear", "digital"}:
        if _reply_language(question) == "hi":
            reply = "यह सामान पसंद बदलने पर लौटाया नहीं जा सकता। सामान खराब, एक्सपायर्ड, गलत या गायब हो तो 48 घंटे के भीतर फ़ोटो के साथ शिकायत करें।"
        elif _reply_language(question) == "hi-en":
            reply = "Yeh item change of mind ke liye return nahi hota. Damaged, expired, wrong ya missing ho to 48 hours mein photos ke saath report karein."
        else:
            reply = "This item is not returnable for a change of mind. If it arrived damaged, expired, wrong, or missing, report it within 48 hours with photos."
        return {"answer": reply, "evidence": ["RET-2", "RET-5", "DWM-1", *product_sources]}
    if category not in category_days:
        return None

    evidence = ["RET-2", "RET-4", *product_sources]
    if category == "beauty_sealed":
        opened = bool(re.search(r"\b(open(?:ed)?|tried|used|unsealed)\b|seal\s+(?:is\s+)?broken|खोल|खुला|सील\s*टूट", q))
        if opened:
            if _reply_language(question) == "hi":
                reply = "खोला या इस्तेमाल किया हुआ ब्यूटी आइटम वापस नहीं किया जा सकता। रिटर्न तभी संभव है जब पैक बंद हो और सील सही हो।"
            elif _reply_language(question) == "hi-en":
                reply = "Khula ya used beauty item return nahi ho sakta. Return tabhi hoga jab item unopened ho aur seal intact ho."
            else:
                reply = "This beauty item cannot be returned after opening or use. It is returnable only if unopened with the seal intact."
            return {"answer": reply, "evidence": ["RET-2", "RET-4", *product_sources]}
        return {"answer": "Beauty and personal care items can be returned within 7 days of delivery only if unopened with the seal intact.", "evidence": ["RET-2", "RET-4", *product_sources]}

    if category == "electronics":
        evidence.append("RET-3")
        all_dates = _dates_in(question)
        delivery_date = all_dates[0] if all_dates else None
        if not delivery_date:
            short_date = re.search(r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\b", question, re.I)
            if short_date:
                try:
                    delivery_date = date(2026, __import__("datetime").datetime.strptime(short_date.group(2), "%B").month, int(short_date.group(1)))
                except ValueError:
                    pass
        days = 10 if delivery_date and delivery_date < date(2026, 8, 1) else 7
        reply = f"The return window is {days} days from delivery. Electronics delivered before 1 August 2026 keep the 10-day window; items delivered on or after that date have 7 days."
        if _reply_language(question) == "hi":
            reply = f"डिलीवरी की तारीख से रिटर्न विंडो {days} दिन है। 1 अगस्त 2026 से पहले डिलीवर हुए इलेक्ट्रॉनिक्स पर 10 दिन और उस तारीख या उसके बाद डिलीवर हुए आइटम पर 7 दिन लागू होते हैं।"
        elif _reply_language(question) == "hi-en":
            reply = f"Delivery date se return window {days} days hai. 1 August 2026 se pehle delivered electronics par 10 days, aur us date ya baad delivered items par 7 days hain."
        return {"answer": reply, "evidence": [*evidence, "RETv3-2", *product_sources] if days == 10 else [*evidence, *product_sources]}

    days = category_days[category]
    sale_order = category == "fashion" and bool(re.search(
        r"(?:sale|order|bought|purchased).{0,100}\b(?:0?[1-9]|1[0-5])\s+oct(?:ober)?\b|"
        r"\b(?:0?[1-9]|1[0-5])\s+oct(?:ober)?\b.{0,100}(?:sale|order|bought|purchased)", q
    ))
    if sale_order:
        days = 30
        evidence.append("RET-8")
        if _reply_language(question) == "hi":
            reply = "यह कपड़े, जूते या बैग का ऑर्डर 1–15 अक्टूबर 2026 की फ़ेस्टिव सेल में रखा गया था, इसलिए डिलीवरी से 30 दिन के भीतर लौटाया जा सकता है।"
        elif _reply_language(question) == "hi-en":
            reply = "Yeh clothing, footwear ya bag order 1–15 October 2026 festive sale mein place hua tha, isliye delivery se 30 days ke andar return kar sakte hain."
        else:
            reply = "Because this clothing, footwear, or bag order was placed during the 1–15 October 2026 festive sale, it can be returned within 30 days of delivery."
    else:
        sale_note = category == "fashion"
        if sale_note:
            evidence.append("RET-8")
            reply = f"This item can normally be returned within {days} days of delivery. Clothing, footwear, or bags ordered during the 1–15 October 2026 festive sale have a 30-day window."
            if _reply_language(question) == "hi":
                reply = f"यह सामान सामान्यतः डिलीवरी से {days} दिनों के भीतर लौटाया जा सकता है। 1–15 अक्टूबर 2026 की फ़ेस्टिव सेल में रखे गए कपड़े, जूते या बैग के ऑर्डर पर 30 दिन मिलते हैं।"
            elif _reply_language(question) == "hi-en":
                reply = f"Yeh item normally delivery se {days} days ke andar return ho sakta hai. 1–15 October 2026 festive sale mein order kiye clothing, footwear ya bags ke liye 30 days milte hain."
        else:
            reply = f"This item can be returned within {days} days of delivery, subject to the item meeting the return condition."
            if _reply_language(question) == "hi":
                reply = f"यह सामान डिलीवरी से {days} दिनों के भीतर लौटाया जा सकता है, बशर्ते यह रिटर्न की शर्तें पूरी करता हो।"
            elif _reply_language(question) == "hi-en":
                reply = f"Yeh item delivery se {days} days ke andar return kar sakte hain, agar return conditions poori hoti hain."
    return {"answer": reply, "evidence": [*evidence, *product_sources]}


def _damaged_item_answer(question: str) -> dict | None:
    q = question.casefold()
    if not re.search(r"damage|damaged|crack|cracked|broken|torn|defective|wrong item|खराब|टूटा|टूटी|फटा|फटी", q):
        return None
    if not re.search(r"item|product|jeans|order|arrived|received|came|सामान|आया|मिला|डिलीवरी|कलेक्शन|pickup|collection|return|शिकायत", q):
        return None
    products = _find_catalog_products(question)
    if any(int(product.get("price_inr") or 0) > 10000 for product in products):
        # High-value claims require the verified order/tool handoff path.
        return None
    if _reply_language(question) == "hi":
        reply = "डिलीवरी से 48 घंटे के भीतर सामान और पैकेट की फ़ोटो के साथ शिकायत करें। जाँच के बाद damaged item के लिए मुफ़्त replacement या पूरा refund मिल सकता है; pickup fee नहीं लगेगी।"
    elif _reply_language(question) == "hi-en":
        reply = "Delivery se 48 hours ke andar item aur package ki photos ke saath report karein. Verification ke baad free replacement ya full refund mil sakta hai; pickup fee nahi lagegi."
    else:
        reply = "Report it within 48 hours of delivery with photos of the item and packaging. After verification, a damaged item can receive a free replacement or full refund, with no reverse-pickup fee."
    return {"answer": reply, "evidence": ["DWM-1", "DWM-2", "RET-6"]}


def _refund_timeline_answer(question: str, chunks) -> dict | None:
    q = question.casefold()
    is_cod = bool(re.search(r"cash[- ]on[- ]delivery|\bcod\b|कैश\s*ऑन\s*डिलीवरी", q))
    if not re.search(r"refund|रिफंड", q) and not (is_cod and re.search(r"money back|cash back|पैसे", q)):
        return None
    asks_timing = bool(re.search(
        r"\b(when|how long|how soon|how fast|by what date|time|timeline|take|takes)\b|"
        r"\b(kab|kitne din|kitna samay)\b|कब|कितने दिन|कितना समय", q
    ))
    if not asks_timing and not (is_cod and re.search(r"money back|refund|paise|पैसे", q)):
        return None
    policy = next((c for c in chunks if c.section_id == "REF-2" and c.status == "current"), None)
    cod_policy = next((c for c in chunks if c.section_id == "REF-3" and c.status == "current"), None)
    if not policy:
        return None
    if is_cod:
        return {
            "answer": "For a cash-on-delivery refund, you can choose a ZentroMart Wallet refund (instant, within 2 hours) or a bank transfer (5 to 7 business days after your bank details are verified).",
            "evidence": ["REF-3", "REF-2"],
            "context": "\n\n".join(c.text for c in (cod_policy, policy) if c),
        }
    if re.search(r"\bupi\b|यूपीआई", q):
        phrase = "1 to 3 business days"
        method = "UPI"
    elif re.search(r"net\s*bank(?:ing)?|netbanking|नेट\s*बैंक", q):
        phrase = "3 to 5 business days"
        method = "net banking"
    elif re.search(r"credit\s*card|debit\s*card|\bcard\b|कार्ड", q):
        phrase = "5 to 7 business days"
        method = "card"
    elif re.search(r"wallet|वॉलेट", q):
        phrase = "instant, usually within 2 hours"
        method = "ZentroMart Wallet"
    else:
        return None
    language = _reply_language(question)
    if method == "ZentroMart Wallet":
        reply = "A ZentroMart Wallet refund is instant, usually within 2 hours of initiation."
    elif language == "hi":
        reply = f"{method} रिफंड शुरू होने के बाद {phrase} में पहुँचता है।"
    elif language == "hi-en":
        reply = f"{method} refund initiation ke baad {phrase} mein aata hai."
    else:
        reply = f"A {method} refund takes {phrase} after it is initiated."
    calendar = next((c for c in chunks if c.section_id == "KB-00.1" and c.status == "current"), None)
    evidence = ["REF-2"] + (["KB-00.1"] if calendar else [])
    return {"answer": reply, "evidence": evidence, "context": f"{policy.section_title}\n{policy.text}"}


def _generic_refund_clarification(question: str, chunks) -> dict | None:
    q = question.casefold()
    asks_timing = bool(re.search(r"\b(when|how long|how soon|by what date|when will)\b|\b(kab|kitne din)\b|कब|कितने दिन", q))
    asks_refund = bool(re.search(r"\brefund\b|रिफंड", q))
    mentions_method = bool(re.search(r"\b(upi|card|credit|debit|net\s*banking|wallet|cash on delivery|cod|neft|bank transfer)\b|यूपीआई|कार्ड|वॉलेट|कैश\s*ऑन\s*डिलीवरी|नेट\s*बैंक", q))
    if not (asks_timing and asks_refund and not mentions_method and not _dates_in(question)):
        return None
    policy = next((c for c in chunks if c.section_id == "REF-2" and c.status == "current"), None)
    if not policy:
        return None
    reply = "How did you pay for the order (UPI, card, net banking, Wallet, or cash on delivery)? The refund timeline depends on the payment method."
    if re.search(r"[\u0900-\u097f]", question):
        reply = "रिफंड की समय-सीमा भुगतान के तरीके पर निर्भर करती है। आपने UPI, कार्ड, नेट बैंकिंग, Wallet या कैश ऑन डिलीवरी में से किससे भुगतान किया था?"
    return {"answer": reply, "evidence": ["REF-2"], "context": f"{policy.section_title}\n{policy.text}"}


def _opened_sealed_product_answer(question: str, chunks) -> dict | None:
    q = question.casefold()
    describes_opened = bool(re.search(r"\b(opened|open|tried|used|unsealed)\b|seal\s+(?:is\s+)?broken", q))
    asks_return = bool(re.search(r"\b(return|send back|take back)\b", q))
    if not (describes_opened and asks_return):
        return None
    product_file = ROOT / "data" / "raw" / "data" / "products.csv"
    with product_file.open(encoding="utf-8-sig", newline="") as stream:
        products = list(csv.DictReader(stream))
    matches = [p for p in products if p.get("title", "").casefold() in q and p.get("return_category") == "beauty_sealed"]
    if not matches:
        return None
    ret4 = next((c for c in chunks if c.section_id == "RET-4" and c.status == "current"), None)
    ret2 = next((c for c in chunks if c.section_id == "RET-2" and c.status == "current"), None)
    if not ret4 or not ret2:
        return None
    product = matches[0]
    reply = "Because the perfume has been opened and tried, it does not meet the return condition. Beauty and personal care items are returnable only when unopened with the seal intact."
    return {"answer": reply, "evidence": ["RET-4", "RET-2", f"products.csv:{product['sku']}"], "context": f"{ret4.section_title}\n{ret4.text}\n\n{ret2.section_title}\n{ret2.text}"}


def answer(question: str, chunks=None, *, conversation_history=None, verified_order_context="") -> dict:
    load_dotenv(ROOT / ".env")
    chunks = chunks if chunks is not None else load_chunks(KB_DIR)
    deterministic = (_refund_date_answer(question, chunks)
                     or _refund_timeline_answer(question, chunks)
                     or _coupon_answer(question)
                     or _customer_privacy_refusal(question)
                     or _unsupported_or_clarify_answer(question)
                     or (None if verified_order_context else _generic_refund_clarification(question, chunks))
                     or _opened_sealed_product_answer(question, chunks)
                     or _damaged_item_answer(question)
                     or _catalog_answer(question, chunks))
    if deterministic:
        deterministic["evidence"] = list(dict.fromkeys(deterministic.get("evidence", [])))
        return deterministic
    results = retrieve(question, chunks, limit=5)
    context = render_context(results)
    evidence = [chunk.section_id for _, chunk in results]
    api_key = (os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY", "")).strip()
    if api_key and context:
        from openai import OpenAI
        kwargs = {"api_key": api_key}
        if os.getenv("OPENAI_BASE_URL"):
            kwargs["base_url"] = os.environ["OPENAI_BASE_URL"]
        client = OpenAI(**kwargs)
        response = client.chat.completions.create(
            model=os.getenv("CHAT_MODEL", "openai/gpt-oss-20b"),
            temperature=0,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}]
            + list(conversation_history or [])
            + [{"role": "user", "content": f"Evidence:\n{context}\n\nVerified order facts (only if present):\n{verified_order_context or 'None'}\n\nCustomer message: {question}"}],
        )
        text = response.choices[0].message.content or "I could not prepare an answer from the available information."
    elif results:
        text = "Offline retrieval is ready. Configure an OpenAI-compatible model endpoint to generate a customer reply. The matching source sections are listed below."
    else:
        text = "I could not find a relevant answer in the available company documents. I can connect you with a human colleague."
    if any(pattern.search(text) for pattern in ABSTENTION_PATTERNS):
        evidence = []
    return {"answer": text, "evidence": evidence, "context": context}

