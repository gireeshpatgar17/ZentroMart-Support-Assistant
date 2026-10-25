"""Ephemeral, identity-gated conversation flow for the Streamlit prototype."""
from __future__ import annotations

import re
import sys
import unicodedata
import csv
from datetime import date, datetime, timedelta
from pathlib import Path

from .agent import ROOT, answer, _business_day_date
from .knowledge import load_chunks

RAW_DIR = ROOT / "data" / "raw"
if str(RAW_DIR) not in sys.path:
    sys.path.insert(0, str(RAW_DIR))

from tools import lookup_order, create_ticket  # noqa: E402


def new_state() -> dict:
    return {
        "history": [],
        "pending_order_id": None,
        "verification_attempts": 0,
        "verified_order": None,
        "pending_question": "",
        "last_issue": "",
        "language": "en",
    }


def _ascii_digits(text: str) -> str:
    out = []
    for char in text:
        try:
            out.append(str(unicodedata.digit(char)))
        except (TypeError, ValueError):
            out.append(char)
    return "".join(out)


def _order_id(text: str) -> str | None:
    normalized = _ascii_digits(text)
    match = re.search(r"(?<!\d)(?:\d\s*){7}\d(?!\d)", normalized)
    return re.sub(r"\D", "", match.group(0)) if match else None


def _third_party_order_request(text: str) -> bool:
    """Catch requests to look up an order belonging to someone else."""
    normalized = text.casefold()
    return bool(re.search(
        r"\b(?:roommate|room-mate|friend|someone else|somebody else|another person|"
        r"my (?:brother|sister|parent|mother|father|husband|wife|partner|colleague)'s)\b|"
        r"\b(?:their|his|her) order\b|किसी और के ऑर्डर|दोस्त के ऑर्डर|रूममेट के ऑर्डर",
        normalized,
    ))


def _verification_value(text: str) -> str | None:
    normalized = _ascii_digits(text)
    if re.search(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b", normalized):
        return None
    runs = re.findall(r"(?<!\d)\d{4}(?:\d{2})?(?!\d)", normalized)
    return runs[0] if runs else None


def _language(text: str, previous: str = "en") -> str:
    if re.search(r"[\u0900-\u097F]", text):
        return "hi"
    if re.search(r"\b(mujhe|hain|hai|kya|mera|meri|kar|aap|pe|mein|kaise|chahiye|hoon|hain)\b", text.casefold()):
        return "hi-en"
    return previous


def _safe_order_context(order: dict) -> str:
    allowed = (
        "order_id", "status", "payment_method", "delivery_type", "promised_date",
        "shipped_on", "delivered_on", "delivery_attempts", "total_inr", "subtotal_inr",
        "return_sku", "return_reason", "return_status", "return_requested_on",
        "return_pickup_on", "return_qc_passed_on", "return_refund_initiated_on",
        "return_refund_method", "return_refund_amount_inr", "return_refund_completed_on",
        "return_rrn", "cancellation_refund_initiated_on", "cancellation_refund_method",
        "cancellation_refund_amount_inr", "cancellation_rrn", "rto_refund_initiated_on",
        "rto_refund_method", "rto_refund_amount_inr", "rto_rrn", "express_late_credit_inr",
        "express_late_credit_on", "damage_sku", "damage_issue", "damage_reported_at",
        "damage_status", "contacts_last_7_days", "timeline", "is_plus",
    )
    facts = [f"{key}: {order[key]}" for key in allowed if order.get(key) not in (None, "", False)]
    items = order.get("items", [])
    for item in items:
        facts.append("item: " + ", ".join(f"{k}={item.get(k)}" for k in ("sku", "title", "qty", "unit_price_inr") if item.get(k) not in (None, "")))
    # Explicitly never pass phone suffixes or pincode verification secrets.
    return "\n".join(facts)


def _refund_overdue(order: dict) -> bool:
    candidates = [
        ("return_refund_initiated_on", "return_refund_method", "return_refund_completed_on"),
        ("cancellation_refund_initiated_on", "cancellation_refund_method", None),
        ("rto_refund_initiated_on", "rto_refund_method", None),
    ]
    refund = next(((order.get(start), order.get(method), order.get(completed) if completed else None)
                   for start, method, completed in candidates
                   if order.get(start) and (not completed or not order.get(completed))), None)
    if not refund:
        return False
    initiated, method, _ = refund
    method = str(method or "").casefold()
    policy_label = {
        "upi": "upi", "card": "credit or debit card", "debit": "credit or debit card",
        "credit": "credit or debit card", "netbanking": "net banking",
        "wallet": "zentromart wallet", "cod_wallet": "zentromart wallet for cash-on-delivery orders",
        "cod_bank": "bank transfer (neft) for cash-on-delivery orders",
    }.get(method)
    if not policy_label:
        return False
    chunks = load_chunks(ROOT / "data" / "raw" / "kb")
    refunds = next((c for c in chunks if c.section_id == "REF-2" and c.status == "current"), None)
    calendar = next((c for c in chunks if c.section_id == "KB-00.2" and c.status == "current"), None)
    if not refunds or not calendar:
        return False
    window = None
    for line in refunds.text.splitlines():
        cells = [cell.strip().casefold() for cell in line.strip().strip("|").split("|")]
        if cells and policy_label in cells[0]:
            match = re.search(r"(\d+)\s+to\s+(\d+)\s+business days", line, re.I)
            if match:
                window = int(match.group(2))
                break
            if "instant" in line.casefold():
                window = 0
                break
    today_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", calendar.text)
    if today_match:
        today = date.fromisoformat(today_match.group(1))
    else:
        spelled_date = re.search(r"\b(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b", calendar.text)
        try:
            today = datetime.strptime(spelled_date.group(1), "%d %B %Y").date() if spelled_date else None
        except ValueError:
            today = None
    if window is None or today is None:
        return False
    with (ROOT / "data" / "raw" / "data" / "holidays.csv").open(encoding="utf-8-sig", newline="") as stream:
        holidays = {date.fromisoformat(row["date"]) for row in csv.DictReader(stream) if row.get("date")}
    due = _business_day_date(date.fromisoformat(initiated), window, holidays)
    grace_end = _business_day_date(due, 3, holidays)
    return today > grace_end


def _escalation_reason(message: str, order: dict | None) -> str | None:
    text = message.casefold()
    if re.search(r"\b(human|person|agent|representative)\b|इंसान|मानव|सहयोगी", text):
        return "customer_requested_human"
    if re.search(r"\b(lawyer|legal action|consumer court|police complaint|police)\b|वकील|पुलिस|अदालत", text):
        return "legal_or_police_contact"
    if re.search(r"\b(burning smell|smoke|sparks|swollen battery|injury|caught fire)\b|आग|धुआँ|चिंगारी", text):
        return "product_safety_risk"
    if re.search(r"\b(not mine|didn.t (?:place|order|make)|never (?:placed|ordered|made)|unauthori[sz]ed|fraud)\b", text) or re.search(r"\border\b.{0,35}\bnever\s+(?:placed|ordered|made)\b", text):
        return "unrecognized_account_activity"
    if order and int(order.get("contacts_last_7_days") or 0) >= 2:
        return "repeat_contact_within_7_days"
    if order and "refund" in text and _refund_overdue(order):
        return "refund_overdue_beyond_grace"
    if order and re.search(r"\b(damage|damaged|defective|cracked|broken|wrong item)\b", text):
        damage_sku = order.get("damage_sku")
        if damage_sku:
            for item in order.get("items", []):
                if item.get("sku") == damage_sku and int(item.get("unit_price_inr") or 0) > 10000:
                    return "high_value_damage_over_10000"
    return None


def _ticket_response(message: str, state: dict, reason: str) -> dict:
    order = state.get("verified_order") or {}
    order_id = order.get("order_id") or state.get("pending_order_id")
    prior = state.get("last_issue", "")
    status = order.get("status") or "not checked"
    summary = (
        f"Customer issue: {message}. Intent: {reason}. Order ID: {order_id or 'not provided'}. "
        f"Customer previously reported: {prior or message}. Checks made: identity status {('verified' if order else 'not required')}; order status {status}. "
        f"Escalation reason: {reason}."
    )
    result = create_ticket(summary=summary, order_id=order_id, reason=reason, intent=reason)
    if result.get("created") is True:
        if state.get("language") == "hi":
            text = f"मैंने सहायता टिकट ({result['ticket_id']}) बना दिया है। एक मानव सहयोगी आपसे संपर्क करेगा; मैं किसी निश्चित नतीजे या समय का वादा नहीं कर सकता।"
        elif state.get("language") == "hi-en":
            text = f"Maine support ticket ({result['ticket_id']}) bana diya hai. Ek human colleague follow up karega; main outcome ya timing ka promise nahi kar sakta."
        else:
            text = f"I’ve created a support ticket ({result['ticket_id']}). A human colleague will follow up; I can’t promise a particular outcome or timing."
        evidence = ["ESC-1", "ESC-2", "ESC-3"]
        if reason == "refund_overdue_beyond_grace":
            rrn = order.get("return_rrn") or order.get("cancellation_rrn") or order.get("rto_rrn")
            if rrn:
                text += f" Refund reference number (RRN): {rrn}."
                evidence.append("REF-6")
        if reason == "high_value_damage_over_10000":
            evidence.append("DWM-3")
    else:
        text = "I’m sorry, I couldn’t create the handoff ticket just now. Please try again or contact support directly."
        evidence = ["ESC-2"]
    return {"answer": text, "evidence": evidence, "user_display": message}


def _date_label(value: date, language: str) -> str:
    if language == "hi":
        months = ("जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर")
        return f"{value.day} {months[value.month - 1]} {value.year}"
    return f"{value.day} {value.strftime('%B')} {value.year}"


def _verified_order_answer(message: str, order: dict, state: dict) -> dict | None:
    """Answer common order-specific intents from verified tool facts and current policy."""
    q, lang = message.casefold(), state.get("language", "en")
    items = order.get("items", [])
    if re.search(r"\bwhen (?:was|did)|\bshipped\b|kab ship|ship hua|कब.*(भेज|शिप)|कहाँ.*ऑर्डर|where.*order|where is it|hasn't arrived|has not arrived|track", q):
        shipped = order.get("shipped_on")
        promised = order.get("promised_date")
        if shipped and re.search(r"\bwhen (?:was|did)|kab ship|ship hua|कब.*(भेज|शिप)", q):
            d = date.fromisoformat(str(shipped)[:10])
            label = _date_label(d, lang)
            text = (f"आपका ऑर्डर {label} को शिप हुआ था।" if lang == "hi" else
                    f"Aapka order {label} ko ship hua tha." if lang == "hi-en" else
                    f"Your order was shipped on {label}.")
            return {"answer": text, "evidence": ["TRK-1"]}
        if shipped and promised:
            d_ship, d_due = date.fromisoformat(str(shipped)[:10]), date.fromisoformat(str(promised)[:10])
            if lang == "hi":
                text = f"आपका ऑर्डर { _date_label(d_ship, lang)} को शिप हुआ था और { _date_label(d_due, lang)} तक पहुँचने की उम्मीद है।"
            elif lang == "hi-en":
                text = f"Aapka order {_date_label(d_ship, lang)} ko ship hua tha aur {_date_label(d_due, lang)} tak expected hai."
            else:
                text = f"Your order was shipped on {_date_label(d_ship, lang)} and is expected to arrive by {_date_label(d_due, lang)}."
            return {"answer": text, "evidence": ["TRK-1"]}

    if re.search(r"not at home|not home|ghar par nahi|घर पर नहीं|उपलब्ध नहीं", q):
        if lang == "hi":
            text = "कूरियर अधिकतम 3 डिलीवरी प्रयास करेगा। हर असफल प्रयास के बाद SMS से रीशेड्यूल कर सकते हैं; तीसरा प्रयास भी असफल होने पर पार्सल वेयरहाउस लौट जाएगा।"
        elif lang == "hi-en":
            text = "Courier maximum 3 delivery attempts karega. Failed attempt ke baad SMS se reschedule kar sakte hain; third attempt bhi fail hua to parcel warehouse return hoga."
        else:
            text = "The courier will make up to 3 delivery attempts. After a failed attempt, use the SMS to reschedule; if the third attempt fails, the parcel returns to the warehouse."
        return {"answer": text, "evidence": ["DEL-3"]}

    if re.search(r"\bcancel|cancel kar|रद्द|कैंसिल", q) and not order.get("shipped_on"):
        if lang == "hi":
            text = "जब तक ऑर्डर शिप नहीं हुआ है, आप ऐप के My Orders सेक्शन से इसे बिना शुल्क रद्द कर सकते हैं। रद्द करने पर रिफ़ंड तुरंत शुरू होगा; मैं स्वयं ऑर्डर रद्द नहीं कर सकता।"
        elif lang == "hi-en":
            text = "Order ship hone se pehle aap app ke My Orders section se ise free cancel kar sakte hain. Cancellation par refund turant initiate hoga; main khud order cancel nahi kar sakta."
        else:
            text = "You can cancel the order free from My Orders while it is still unshipped. The refund is initiated immediately; I can’t cancel it for you."
        return {"answer": text, "evidence": ["CAN-1"]}

    if re.search(r"\bcancel|cancel kar|रद्द|कैंसिल", q) and order.get("shipped_on"):
        method = str(order.get("payment_method") or "").casefold()
        refund_time = {"upi": "1 to 3 business days", "card": "5 to 7 business days", "credit": "5 to 7 business days", "debit": "5 to 7 business days", "netbanking": "3 to 5 business days", "wallet": "instant, within about 2 hours"}.get(method, "the timeline for your payment method")
        if lang == "hi":
            text = f"माफ़ कीजिए, शिप हो चुका ऑर्डर रद्द नहीं किया जा सकता। आप पार्सल लेने से मना कर सकते हैं; प्रीपेड रिफ़ंड आमतौर पर आख़िरी असफल प्रयास के 7–10 कैलेंडर दिनों बाद पार्सल वेयरहाउस पहुँचने पर शुरू होगा। {method.upper()} में शुरू होने के बाद {refund_time} लगते हैं। या डिलीवरी लेकर लागू रिटर्न अवधि में सामान लौटा सकते हैं।"
        elif lang == "hi-en":
            text = f"Maaf kijiye, shipped order cancel nahi ho sakta. Aap parcel refuse kar sakte hain; prepaid refund usually last failed attempt ke 7–10 calendar days baad, parcel warehouse pahunchne par start hota hai. {method.upper()} mein initiate hone ke baad {refund_time} lagte hain. Ya delivery accept karke applicable return window mein item return kar sakte hain."
        else:
            text = f"Sorry, a shipped order cannot be cancelled. You can refuse the parcel; a prepaid refund starts when it reaches the warehouse, usually 7–10 calendar days after the last delivery attempt. Once initiated, {method.upper()} refunds take {refund_time}. Or accept delivery and return eligible items within their return window."
        return {"answer": text, "evidence": ["CAN-2", "REF-1", "REF-2", "RET-2"]}

    if re.search(r"voucher|compensation|रुपये|रुपए|मुआवज़ा", q) and order.get("delivery_type") == "standard":
        if lang == "hi":
            text = "माफ़ कीजिए, स्टैंडर्ड डिलीवरी में देर के लिए कोई मुआवज़ा या वाउचर नहीं दिया जाता।"
        elif lang == "hi-en":
            text = "Maaf kijiye, standard delivery late hone par compensation ya voucher nahi diya jata."
        else:
            text = "I’m sorry, standard-delivery delays are not eligible for compensation or a voucher."
        return {"answer": text, "evidence": ["DEL-4"]}

    if re.search(r"express|credit|wallet|वॉलेट|क्रेडिट", q) and order.get("delivery_type") == "express":
        promised, delivered = order.get("promised_date"), order.get("delivered_on")
        late = bool(promised and delivered and date.fromisoformat(str(delivered)[:10]) > date.fromisoformat(str(promised)[:10]))
        amount, credited_on = order.get("express_late_credit_inr"), order.get("express_late_credit_on")
        if amount and credited_on:
            credited = _date_label(date.fromisoformat(str(credited_on)[:10]), lang)
            text = f"The ₹{amount} express fee credit was added to your ZentroMart Wallet on {credited}." if lang == "en" else f"₹{amount} express fee credit {credited} ko aapke ZentroMart Wallet mein add hua."
            return {"answer": text, "evidence": ["DEL-4"]}
        if late and not order.get("is_plus"):
            text = "Your express delivery arrived after its promised date. The ₹79 express fee is credited automatically to your ZentroMart Wallet within 48 hours." if lang == "en" else "Aapki express delivery promised date ke baad aayi. ₹79 express fee 48 hours ke andar automatically ZentroMart Wallet mein credit hoti hai."
            return {"answer": text, "evidence": ["DEL-4"]}

    if re.search(r"\breturn|\bwapas|\bvaapas|वापस|लौटा", q) and not re.search(r"refund|रिफ़ंड|रिफंड", q) and items:
        def base_title(item: dict) -> str:
            return str(item.get("title", "")).split(",")[0].casefold()
        matches = [item for item in items if base_title(item) and all(token in q for token in re.findall(r"[a-z0-9]+", base_title(item)) if len(token) > 2)]
        item = matches[0] if len(matches) == 1 else (items[0] if len(items) == 1 else None)
        if item and order.get("delivered_on"):
            category = str(item.get("return_category") or "")
            windows = {"electronics": 7, "fashion": 15, "home_kitchen": 10, "beauty_sealed": 7, "books_media": 10}
            window = windows.get(category)
            evidence = ["RET-2", "RET-4", f"products.csv:{item.get('sku')}"]
            if category == "fashion" and order.get("placed_at"):
                placed = date.fromisoformat(str(order["placed_at"])[:10])
                if date(2026, 10, 1) <= placed <= date(2026, 10, 15):
                    window = 30
                    evidence.append("RET-8")
            if category == "fashion" and not order.get("is_plus"):
                evidence.append("RET-6")
            if not window:
                text = "This product category is not returnable under the listed policy."
                return {"answer": text, "evidence": ["RET-2", f"products.csv:{item.get('sku')}"]}
            if category == "beauty_sealed" and re.search(r"\b(open|opened|used|tried)\b|खोल|खुला|इस्तेमाल", q):
                return {"answer": "Beauty and personal care items are returnable only when unopened with the seal intact.", "evidence": ["RET-4", "RET-2", f"products.csv:{item.get('sku')}"]}
            deadline = date.fromisoformat(str(order["delivered_on"])[:10]) + timedelta(days=window)
            if lang == "hi":
                text = f"आप {item.get('title')} को डिलीवरी के {window} दिनों के भीतर, यानी {_date_label(deadline, lang)} तक लौटा सकते हैं। सामान अप्रयुक्त और मूल पैकेजिंग सहित होना चाहिए।" + (" बदलाव के कारण लौटाने पर ₹49 रिवर्स-पिकअप शुल्क लागू हो सकता है।" if category == "fashion" and not order.get("is_plus") else "")
            elif lang == "hi-en":
                text = f"Aap {item.get('title')} ko delivery ke {window} days ke andar, yaani {_date_label(deadline, lang)} tak return kar sakte hain, agar item unused ho aur original packaging ho." + (" Change-of-mind return par ₹49 reverse-pickup fee lag sakti hai." if category == "fashion" and not order.get("is_plus") else "")
            else:
                text = f"You can return {item.get('title')} within {window} days of delivery, by {_date_label(deadline, lang)}, provided it is unused and in its original packaging." + (" A ₹49 reverse-pickup fee may apply to change-of-mind returns." if category == "fashion" and not order.get("is_plus") else "")
            return {"answer": text, "evidence": evidence}

    if re.search(r"refund|रिफ़ंड|रिफंड", q):
        pickup = order.get("return_pickup_on")
        qc = order.get("return_qc_passed_on")
        initiated = order.get("return_refund_initiated_on")
        method = str(order.get("return_refund_method") or order.get("payment_method") or "").casefold()
        if pickup and not qc and not initiated:
            picked = _date_label(date.fromisoformat(str(pickup)[:10]), lang)
            if order.get("is_plus"):
                text = f"Your return was picked up on {picked}. As a ZentroMart Plus member, the refund is initiated at pickup; then the {method.upper()} timeline applies."
            elif lang == "hi":
                text = f"आपका रिटर्न {picked} को पिक-अप हुआ। अब वेयरहाउस क्वालिटी चेक का इंतज़ार है; पास होने पर 2 कामकाजी दिनों के भीतर रिफ़ंड शुरू होगा। उसके बाद भुगतान विधि की समय-सीमा लागू होगी।"
            elif lang == "hi-en":
                text = f"Aapka return {picked} ko pickup hua. Warehouse QC pending hai; pass hone par 2 business days ke andar refund initiate hoga. Uske baad payment method ka timeline lagega."
            else:
                text = f"Your return was picked up on {picked} and is awaiting warehouse quality check. If it passes, the refund is initiated within 2 business days; the payment-method timeline starts after that."
            return {"answer": text, "evidence": ["RET-7", "REF-1"]}
        if not initiated:
            duration = {"upi": "1 to 3 business days", "card": "5 to 7 business days", "credit": "5 to 7 business days", "debit": "5 to 7 business days", "netbanking": "3 to 5 business days", "wallet": "instant, within about 2 hours"}.get(method)
            if duration:
                if lang == "hi":
                    text = f"रिटर्न पिक-अप और क्वालिटी चेक पास होने के बाद 2 कामकाजी दिनों के भीतर रिफ़ंड शुरू होगा। {method.upper()} में शुरू होने के बाद आमतौर पर {duration} लगते हैं।"
                elif lang == "hi-en":
                    text = f"Return pickup aur QC pass hone ke baad 2 business days ke andar refund initiate hoga. {method.upper()} mein initiate hone ke baad {duration} lagte hain."
                else:
                    text = f"The refund is initiated within 2 business days after pickup and a passed quality check. Once initiated, {method.upper()} refunds usually take {duration}."
                return {"answer": text, "evidence": ["RET-7", "REF-1", "REF-2"]}
    return None


def respond(message: str, state: dict) -> dict:
    """Handle one user turn and return a safe display string plus source IDs."""
    raw_message = message
    state["language"] = _language(message, state.get("language", "en"))
    lang = state["language"]
    if _third_party_order_request(message):
        prompts = {
            "en": "For privacy, I can help with orders placed from your own account only. Please ask the account holder to contact us from their account, or I can connect you to a human colleague.",
            "hi": "गोपनीयता के लिए, मैं केवल आपके अपने अकाउंट से किए गए ऑर्डर में मदद कर सकता हूँ। कृपया अकाउंट धारक से उनके अकाउंट से संपर्क करने को कहें, या मैं आपको किसी मानव सहयोगी से जोड़ सकता हूँ।",
            "hi-en": "Privacy ke liye, main sirf aapke apne account se kiye gaye orders mein help kar sakta hoon. Account holder se unke account se contact karne ko kahein, ya main aapko human colleague se connect kar sakta hoon.",
        }
        text = prompts[lang]
        state["history"].append({"role": "user", "content": message})
        state["history"].append({"role": "assistant", "content": text})
        return {"answer": text, "evidence": ["IDV-2"], "user_display": raw_message}
    handoff_without_order_check = _escalation_reason(message, None)
    if handoff_without_order_check in {"customer_requested_human", "legal_or_police_contact", "product_safety_risk", "unrecognized_account_activity"}:
        result = _ticket_response(message, state, handoff_without_order_check)
        state["history"].append({"role": "assistant", "content": result["answer"]})
        return result
    pending = state.get("pending_order_id")
    if pending:
        proof = _verification_value(message)
        if not proof:
            prompts = {
                "en": "Please provide either the last four digits of the registered phone number or the delivery pincode. I’ll use one verification detail only.",
                "hi": "कृपया रजिस्टर्ड फ़ोन नंबर के आख़िरी चार अंक या डिलीवरी पिनकोड में से एक दें।",
                "hi-en": "Registered phone ke last 4 digits ya delivery pincode mein se ek share karein.",
            }
            return {"answer": prompts[lang], "evidence": ["IDV-2"], "user_display": message}
        lookup = lookup_order(pending, verification_value=proof)
        # Never retain or echo the submitted verification value.
        state["history"].append({"role": "assistant", "content": "I asked the customer to verify their identity."})
        if lookup.get("verified") is True:
            # Drop the verification pincode from the session copy immediately;
            # the agent only needs the verification result and order facts.
            lookup.pop("delivery_pincode", None)
            lookup.pop("customer_id", None)
            state["verified_order"] = lookup
            state["pending_order_id"] = None
            state["verification_attempts"] = 0
            issue = state.get("pending_question", "")
            if issue:
                result = (_verified_order_answer(issue, lookup, state)
                          or answer(issue, conversation_history=state["history"], verified_order_context=_safe_order_context(lookup)))
                text = "Your order is verified. " + result["answer"]
                evidence = list(dict.fromkeys(["IDV-2", *result["evidence"]]))
            else:
                prompts = {"en": "Thanks, your order is verified. What would you like help with?", "hi": "धन्यवाद, आपका ऑर्डर सत्यापित हो गया है। आपको किस बात में मदद चाहिए?", "hi-en": "Thanks, order verify ho gaya. Aapko kis cheez mein help chahiye?"}
                text, evidence = prompts[lang], ["IDV-2"]
            state["pending_question"] = ""
            state["history"].append({"role": "assistant", "content": text})
            return {"answer": text, "evidence": evidence, "user_display": "Verification details provided."}
        state["verification_attempts"] += 1
        if state["verification_attempts"] >= 2:
            state["pending_order_id"] = None
            state["pending_question"] = ""
            state["verified_order"] = None
            prompts = {"en": "I couldn’t verify those details, so I can’t share order information. Please contact a human colleague for help.", "hi": "मैं इन विवरणों से सत्यापन नहीं कर पाया, इसलिए ऑर्डर की जानकारी साझा नहीं कर सकता। कृपया सहायता के लिए किसी मानव सहयोगी से संपर्क करें।", "hi-en": "Details verify nahi ho paaye, isliye main order info share nahi kar sakta. Help ke liye human colleague se contact karein."}
            text = prompts[lang]
            evidence = ["IDV-3", "IDV-4"]
        else:
            prompts = {"en": "That detail didn’t match. Please try once more with either the last four registered phone digits or the delivery pincode.", "hi": "यह विवरण मेल नहीं खाया। रजिस्टर्ड फ़ोन के आख़िरी चार अंक या डिलीवरी पिनकोड से एक बार और कोशिश करें।", "hi-en": "Yeh detail match nahi hui. Registered phone ke last 4 digits ya delivery pincode se ek baar aur try karein."}
            text = prompts[lang]
            evidence = ["IDV-3"]
        state["history"].append({"role": "assistant", "content": text})
        return {"answer": text, "evidence": evidence, "user_display": "Verification details provided."}

    order_id = _order_id(message)
    if order_id:
        state["verified_order"] = None
        state["pending_order_id"] = order_id
        state["verification_attempts"] = 0
        stripped = re.sub(r"(?<!\d)(?:\d\s*){7}\d(?!\d)", " ", _ascii_digits(message))
        is_id_only = bool(re.search(r"\border\s*(?:number|id|no\.?|#)?\b", stripped, re.I)) and not re.search(r"\b(where|status|track|refund|return|cancel|late|delivery|arrived|item|product)\b", stripped, re.I)
        if not is_id_only:
            state["pending_question"] = message
        lookup_order(order_id)  # unverified response is only the verification gate
        prompts = {"en": "Please verify your identity before I look up order details. Share either the last four digits of the registered phone number or the delivery pincode.", "hi": "ऑर्डर की जानकारी देखने से पहले कृपया अपनी पहचान सत्यापित करें। रजिस्टर्ड फ़ोन के आख़िरी चार अंक या डिलीवरी पिनकोड में से एक साझा करें।", "hi-en": "Order details dekhne se pehle identity verify karni hogi. Registered phone ke last 4 digits ya delivery pincode mein se ek share karein."}
        text = prompts[lang]
        if not is_id_only:
            state["last_issue"] = message
        state["history"].append({"role": "user", "content": message})
        state["history"].append({"role": "assistant", "content": text})
        return {"answer": text, "evidence": ["IDV-2"], "user_display": message}

    order = state.get("verified_order")
    reason = _escalation_reason(message, order)
    if reason:
        result = _ticket_response(message, state, reason)
        state["history"].append({"role": "assistant", "content": result["answer"]})
        return result

    if order:
        result = _verified_order_answer(message, order, state)
        if result:
            state["history"].append({"role": "user", "content": message})
            state["history"].append({"role": "assistant", "content": result["answer"]})
            state["last_issue"] = message
            return {**result, "user_display": raw_message}

    if not order and re.search(r"\b(order|my order|ऑर्डर)\b", message.casefold()):
        state["pending_question"] = message
        state["last_issue"] = message
        prompts = {"en": "I’m ZentroMart’s AI support assistant. Please share your order ID so I can help.", "hi": "मैं ZentroMart का AI सहायता सहायक हूँ। कृपया अपना ऑर्डर ID साझा करें।", "hi-en": "Main ZentroMart ka AI support assistant hoon. Please apna order ID share karein."}
        text = prompts[lang]
        state["history"].append({"role": "user", "content": message})
        state["history"].append({"role": "assistant", "content": text})
        return {"answer": text, "evidence": ["STY-1", "IDV-2"], "user_display": message}

    chunks = None
    if order:
        issue = message
        state["last_issue"] = issue
        result = (_verified_order_answer(issue, order, state)
                  or answer(issue, conversation_history=state["history"], verified_order_context=_safe_order_context(order)))
    else:
        result = answer(message, conversation_history=state["history"])
    state["history"].append({"role": "user", "content": message})
    state["history"].append({"role": "assistant", "content": result["answer"]})
    return {"answer": result["answer"], "evidence": result["evidence"], "user_display": raw_message}

