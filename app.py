import os
import requests
from flask import Flask, request
from dotenv import load_dotenv
import urllib.parse
from datetime import datetime
from pymongo import MongoClient
import re
from groq import Groq
import certifi

# .env ফাইল থেকে Environment Variables লোড করার জন্য
load_dotenv()

# Flask অ্যাপ ইনিশিয়ালাইজ করা
app = Flask(__name__)

# Environment Variables থেকে Key এবং Token গুলো নেওয়া
FACEBOOK_PAGE_ACCESS_TOKEN = os.getenv('FACEBOOK_PAGE_ACCESS_TOKEN')
VERIFY_TOKEN = os.getenv('VERIFY_TOKEN')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
MONGO_URI = os.getenv('MONGO_URI')
TELEGRAM_USERNAME = os.getenv('TELEGRAM_USERNAME')
CALLMEBOT_API_KEY = os.getenv('CALLMEBOT_API_KEY')
GROQ_MODEL_NAME = os.getenv('GROQ_MODEL_NAME', 'llama-3.1-8b-instant')


# --- ডেটাবেস কানেকশন ---
try:
    ca = certifi.where()
    client = MongoClient(MONGO_URI, tlsCAFile=ca)
    db = client.chatbot_db
    chat_history_collection = db.chat_history
    otn_tokens_collection = db.otn_tokens
    customer_details_collection = db.customer_details
    print("MongoDB ডেটাবেসের সাথে সফলভাবে সংযুক্ত।")
except Exception as e:
    print(f"MongoDB সংযোগে সমস্যা: {e}")
    client = None
# -------------------------

# --- ধাপ ১: সাধারণ প্রশ্নের জন্য নির্দিষ্ট উত্তর (FAQ) ---
FAQ_RESPONSES = {
    ("hi", "hello", "هاي", "هلو", "আসসালামু আলাইকুম"): "আসসালামু আলাইকুম, স্যার/ম্যাম! 😊 আপনাকে কিভাবে সাহায্য করতে পারি?",
    ("thanks", "thank you", "شكرا", "ধন্যবাদ"): "আপনাকে সাহায্য করতে পেরে আমরা আনন্দিত!",
}

# --- নতুন: সম্পূর্ণ মেন্যু একটি ভ্যারিয়েবলে রাখা ---
FULL_MENU_TEXT = """
আসসালামু আলাইকুম 
আপনাদের জন্য নিয়ে এসেছি সুস্বাদু এবং স্বাস্থ্যকর ফ্রোজেন ফুডের মেন্যু। নিচে আমাদের মেন্যু লিস্ট দেওয়া হলো:
১) চিকেন রোল ১৫ পিসের প্যাক    ২২৫ টাকা
২) ভেজিটেবল রোল ১৫ পিসের প্যাক ১৫০ টাকা
৩) বিফ রোল ১০ পিসের প্যাক ২৫০ টাকা 
৪) চিকেন সমুচা ১৫ পিসের প্যাক ২২৫ টাকা 
৫) ভেজিটেবল সমুচা ১৫ পিসের প্যাক ১৫০ টাকা 
৬) বিফ সমুচা ১০ পিসের প্যাক ২৫০ টাকা 
৭) চিকেন সিঙ্গারা ১০ পিসের  প্যাক ১৫০ টাকা 
৮) আলু সিঙ্গারা ১০ পিসের প্যাক ১০০ টাকা 
৯) চিকেন কলিজা সিঙ্গারা ১০ পিসের প্যাক ১৬০ টাকা ।
১০) আলু পুরি  ২০ পিসের প্যাক ১৬০ টাকা 
১১) ডাল পুরি ২০ পিসের প্যাক ১৬০ টাকা 
১২) চিকেন নাগেটস ১২ পিসের প্যাক ২৪০ টাকা 
১৩) চিকেন টিকিয়া কাবাব ১২ পিসের প্যাক ২৪০ টাকা
১৪) চিকেন ঝাল ডোনাট  ১২ পিসের প্যাক ২৪০ টাকা
১৫) চিকেন কাটলেট ১২ পিসের প্যাক ২৪০ টাকা । 
১৬) চারকোনা পরোটা  
      ক)২০ পিসের প্যাক(১২০০gm )220টাকা ।
      খ)২০ পিসের প্যাক (১৫০০ gm) 260টাকা।
      গ) ১০ পিস আলু পরোটা ২৫০ টাকা
১৭) আটা রুটি ২০ পিসের প্যাক ১৬০ টাকা 
১৮) ময়দা রুটি ২০ পিসের প্যাক ১৮০ টাকা 
১৯) লাল আটা রুটি  ২০ পিসের প্যাক ১৮০ টাকা 
২০) চাউলের রুটি ২০ পিসের প্যাক 200 টাকা 
২১) পাটি সাপটা ১০ পিসের প্যাক ২০০ টাকা
২২) অন্থন ১০ পিসের প্যাক ১৫০ টাকা 
২৩) সুজির হালুয়া ৪০০ টাকা কেজি 
২৪) গাজরের হালুয়া ৮০০ টাকা কেজি 
২৫) বুটের হালুয়া ৭০০ টাকা কেজি 
(বি: দ্রঃ কমপক্ষে যে কোন ২ প্যাক অর্ডার করতে হবে)
"""

# --- ধাপ ২: নির্দিষ্ট আইটেম সম্পর্কে প্রশ্নের জন্য কাঠামোবদ্ধ জ্ঞান (AI ছাড়া উত্তর) ---
STRUCTURED_KNOWLEDGE = [
    # মেন্যু আইটেম
    {"name": "চিকেন রোল", "price": 225, "keywords": ["chicken roll", "চিকেন রোল"]},
    {"name": "ভেজিটেবল রোল", "price": 150, "keywords": ["vegetable roll", "ভেজিটেবল রোল", "সবজি রোল"]},
    {"name": "বিফ রোল", "price": 250, "keywords": ["beef roll", "বিফ রোল"]},
    {"name": "চিকেন সমুচা", "price": 225, "keywords": ["chicken somusa", "চিকেন সমুচা"]},
    {"name": "ভেজিটেবল সমুচা", "price": 150, "keywords": ["vegetable somusa", "ভেজিটেবল সমুচা", "সবজি সমুচা"]},
    {"name": "বিফ সমুচা", "price": 250, "keywords": ["beef somusa", "বিফ সমুচা"]},
    {"name": "চিকেন সিঙ্গারা", "price": 150, "keywords": ["chicken singara", "চিকেন সিঙ্গারা"]},
    {"name": "আলু সিঙ্গারা", "price": 100, "keywords": ["alu singara", "আলু সিঙ্গারা"]},
    {"name": "চিকেন কলিজা সিঙ্গারা", "price": 160, "keywords": ["chicken kolija singara", "চিকেন কলিজা সিঙ্গারা"]},
    {"name": "আলু পুরি", "price": 160, "keywords": ["alu puri", "আলু পুরি"]},
    {"name": "ডাল পুরি", "price": 160, "keywords": ["dal puri", "ডাল পুরি"]},
    {"name": "চিকেন নাগেটস", "price": 240, "keywords": ["chicken nuggets", "চিকেন নাগেটস"]},
    {"name": "চিকেন টিকিয়া কাবাব", "price": 240, "keywords": ["chicken tikia kabab", "টিকিয়া কাবাব"]},
    {"name": "চিকেন ঝাল ডোনাট", "price": 240, "keywords": ["chicken jhal donut", "ঝাল ডোনাট"]},
    {"name": "চিকেন কাটলেট", "price": 240, "keywords": ["chicken cutlet", "চিকেন কাটলেট"]},
    {"name": "চারকোনা পরোটা (১২০০gm)", "price": 220, "keywords": ["porota", "পরোটা", "1200gm"]},
    {"name": "চারকোনা পরোটা (১৫০০gm)", "price": 260, "keywords": ["porota", "পরোটা", "1500gm"]},
    {"name": "আলু পরোটা", "price": 250, "keywords": ["alu porota", "আলু পরোটা"]},
    {"name": "আটা রুটি", "price": 160, "keywords": ["ata ruti", "আটা রুটি"]},
    {"name": "ময়দা রুটি", "price": 180, "keywords": ["moyda ruti", "ময়দা রুটি"]},
    {"name": "লাল আটা রুটি", "price": 180, "keywords": ["lal ata ruti", "লাল আটা রুটি"]},
    {"name": "চাউলের রুটি", "price": 200, "keywords": ["chaler ruti", "চাউলের রুটি"]},
    {"name": "পাটি সাপটা", "price": 200, "keywords": ["pati shapta", "পাটি সাপটা"]},
    {"name": "অন্থন", "price": 150, "keywords": ["onthon", "অন্থন"]},
    {"name": "সুজির হালুয়া", "price": 400, "keywords": ["sujir halua", "সুজির হালুয়া"]},
    {"name": "গাজরের হালুয়া", "price": 800, "keywords": ["gajorer halua", "গাজরের হালুয়া"]},
    {"name": "বুটের হালুয়া", "price": 700, "keywords": ["buter halua", "বুটের হালুয়া"]},
    
    # পলিসি এবং অন্যান্য তথ্য
    {"name": "ডেলিভারি চার্জ", "price": 60, "keywords": ["delivery", "charge", "cost", "ডেলিভারি", "চার্জ", "খরচ"]},
    # আপনি এখানে আরও তথ্য যোগ করতে পারেন, যেমন:
    # {"name": "ডেলিভারি এলাকা", "info": "আমরা মিরপুর, উত্তরা...", "keywords": ["area", "location", "এলাকা"]}
]
INTENT_KEYWORDS = {
    "get_price": ["price", "dam", "দাম", "খরচ", "কত", "প্রাইস"],
    "get_menu": ["menu", "list", "items", "মেন্যু", "তালিকা", "খাবার"]
}
# -----------------------------------------------------------------

# Groq ক্লায়েন্ট কনফিগার করা
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    print("Groq AI ক্লায়েন্ট সফলভাবে লোড হয়েছে।")
except Exception as e:
    print(f"Groq AI কনফিগারেশনে সমস্যা হয়েছে: {e}")
    groq_client = None

GRAPH_API_URL = 'https://graph.facebook.com/v18.0/me/messages'

def find_faq_response(message):
    lower_message = message.lower()
    for keywords, response in FAQ_RESPONSES.items():
        for keyword in keywords:
            if re.search(r'\b' + re.escape(keyword) + r'\b', lower_message):
                return response
    return None

def handle_structured_query(message):
    lower_message = message.lower()
    
    is_price_query = any(re.search(r'\b' + kw + r'\b', lower_message) for kw in INTENT_KEYWORDS["get_price"])
    is_menu_query = any(re.search(r'\b' + kw + r'\b', lower_message) for kw in INTENT_KEYWORDS["get_menu"])

    # যদি কেউ মেন্যু চায়
    if is_menu_query:
        return FULL_MENU_TEXT

    # যদি কেউ দাম জানতে চায়
    if is_price_query:
        found_items = []
        for item in STRUCTURED_KNOWLEDGE:
            for keyword in item["keywords"]:
                if re.search(r'\b' + keyword + r'\b', lower_message):
                    found_items.append(f"{item['name']}-এর দাম {item['price']} টাকা।")
        
        # যদি নির্দিষ্ট কোনো আইটেমের নাম পাওয়া যায়
        if found_items:
            return "\n".join(found_items)
        # যদি শুধু "দাম কত" বা "প্রাইস লিস্ট" বলে, তাহলে পুরো মেন্যু দেওয়া হবে
        else:
            return FULL_MENU_TEXT

    # আপনি এখানে অন্যান্য উদ্দেশ্য যোগ করতে পারেন
    return None


@app.route('/')
def home():
    return 'সার্ভারটি সফলভাবে চলছে!', 200

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return request.args.get('hub.challenge'), 200
        else:
            return 'ভেরিফিকেশন টোকেন ভুল', 403
    
    if request.method == 'POST':
        data = request.get_json()
        if data and data.get('object') == 'page':
            for entry in data.get('entry', []):
                for messaging_event in entry.get('messaging', []):
                    sender_id = messaging_event['sender']['id']
                    
                    if messaging_event.get('optin'):
                        # ... (OTN কোড)
                        continue

                    if messaging_event.get('message'):
                        message_text = messaging_event['message'].get('text')
                        if message_text:
                            # --- নতুন কার্যপ্রণালী ---
                            # ধাপ ১: সাধারণ FAQ পরীক্ষা
                            faq_answer = find_faq_response(message_text)
                            if faq_answer:
                                send_facebook_message(sender_id, faq_answer)
                                continue

                            # ধাপ ২: নির্দিষ্ট প্রশ্নের (দাম, মেন্যু ইত্যাদি) উত্তর দেওয়া
                            structured_answer = handle_structured_query(message_text)
                            if structured_answer:
                                send_facebook_message(sender_id, structured_answer)
                                continue
                            
                            # ধাপ ৩: যদি উপরের কোনোটিই কাজ না করে, তবেই AI ব্যবহার করা
                            save_message_to_db(sender_id, 'user', message_text)
                            if groq_client:
                                try:
                                    bot_response = get_groq_response(sender_id, message_text)
                                    save_message_to_db(sender_id, 'assistant', bot_response)
                                    
                                    user_facing_response = bot_response
                                    if "[ORDER_CONFIRMED]" in bot_response:
                                        send_telegram_notification(bot_response)
                                        apply_date_label(sender_id)
                                        details_match = re.search(r'\[DETAILS:(.*?)\]', bot_response)
                                        if details_match:
                                            details_str = details_match.group(1)
                                            save_customer_details(sender_id, details_str)
                                        user_facing_response = re.sub(r'\[.*?\]', '', bot_response).strip()
                                        send_otn_request(sender_id)
                                    send_facebook_message(sender_id, user_facing_response)

                                except Exception as e:
                                    print(f"Groq থেকে উত্তর আনতে সমস্যা হয়েছে: {e}")
                                    send_facebook_message(sender_id, "দুঃখিত, এই মুহূর্তে উত্তর দিতে পারছি না।")
        return 'Event received', 200

def get_groq_response(sender_id, message):
    history = get_chat_history(sender_id, limit=3)
    formatted_history = []
    for msg in history:
        if msg.get('role') and msg.get('content'):
            formatted_history.append({"role": msg.get('role'), "content": msg.get('content')})

    customer_details = get_saved_customer_details(sender_id)
    details_context = "এই গ্রাহকের কোনো তথ্য আমাদের কাছে সেভ করা নেই।"
    saved_address = ""
    if customer_details and customer_details.get('address'):
        saved_address = customer_details.get('address')
        details_context = f"এই গ্রাহকের একটি ঠিকানা আমাদের কাছে সেভ করা আছে: {saved_address}"

    # AI-কে এখন শুধু পলিসি এবং সাধারণ নির্দেশনা দেওয়া হচ্ছে
    KNOWLEDGE_BASE_FOR_AI = """
    ## পলিসি এবং প্রায়শই জিজ্ঞাসিত প্রশ্ন (FAQ)
    - **অর্ডার প্রসেসিং সময়:** অর্ডার কনফার্ম হওয়ার পর ২৪ থেকে ৭২ ঘণ্টার মধ্যে ডেলিভারি করা হয়।
    - **পেমেন্ট:** আমরা বর্তমানে শুধুমাত্র ক্যাশ অন ডেলিভারি গ্রহণ করি।
    - **যোগাযোগ:** যেকোনো প্রয়োজনে আমাদের পেজে মেসেজ দিন।
    """

    system_prompt = f"""
    ### আপনার ব্যক্তিত্ব (Persona) ###
    আপনি "ঘরের খাবার" এর একজন হেল্পফুল মডারেটর। আপনার কথার ধরণ হবে ঘরোয়া এবং আন্তরিক।

    ### আপনার জ্ঞান (Knowledge Base) ###
    {KNOWLEDGE_BASE_FOR_AI}
    
    ### গ্রাহকের সেভ করা তথ্য (Saved Customer Details) ###
    {details_context}

    ### গুরুত্বপূর্ণ নির্দেশনা (Strict Instructions) ###
    (এখানে আপনার আগের নির্দেশনাগুলো থাকবে, যেমন: অর্ডার কনফার্মেশন)
    
    ### আপনার কাজ ###
    আপনার কাছে এমন একটি প্রশ্ন এসেছে যার উত্তর আপনার নির্দিষ্ট জ্ঞানে নেই। সাধারণ জ্ঞান এবং আপনার ব্যক্তিত্ব ব্যবহার করে একটি সাহায্যকারী উত্তর দিন।

    ### পূর্বের কথোপকথন ###
    {formatted_history}

    ### নতুন মেসেজ ###
    user: "{message}"
    """
    
    messages_for_api = [
        {"role": "system", "content": system_prompt},
        *formatted_history,
        {"role": "user", "content": message}
    ]

    try:
        chat_completion = groq_client.chat.completions.create(
            messages=messages_for_api,
            model=GROQ_MODEL_NAME,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        print(f"Groq API Error: {e}")
        return "দুঃখিত, একটি প্রযুক্তিগত সমস্যা হয়েছে। আমরা বিষয়টি দেখছি।"

# (বাকি সব ফাংশন আগের মতোই থাকবে)
def save_customer_details(sender_id, details_str):
    try:
        details = dict(item.split("=") for item in details_str.strip().split(", "))
        if client:
            customer_details_collection.update_one(
                {'sender_id': sender_id},
                {'$set': {
                    'name': details.get('নাম'),
                    'address': details.get('ঠিকানা'),
                    'phone': details.get('ফোন'),
                    'last_updated': datetime.utcnow()
                }},
                upsert=True
            )
    except Exception as e:
        print(f"গ্রাহকের তথ্য পার্স করতে সমস্যা: {e}")

def get_saved_customer_details(sender_id):
    if client:
        details = customer_details_collection.find_one({'sender_id': sender_id})
        if details:
             return details
    return None

def save_message_to_db(sender_id, role, content):
    if client:
        chat_history_collection.insert_one({
            'sender_id': sender_id,
            'role': role,
            'content': content,
            'timestamp': datetime.utcnow()
        })

def get_chat_history(sender_id, limit=3):
    if client:
        history_cursor = chat_history_collection.find({'sender_id': sender_id}).sort('timestamp', -1).limit(limit)
        return list(history_cursor)[::-1]
    return []

def send_otn_request(recipient_id):
    params = {'access_token': FACEBOOK_PAGE_ACCESS_TOKEN}
    headers = {'Content-Type': 'application/json'}
    data = {
        'recipient': {'id': recipient_id},
        'message': {
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "one_time_notif_req",
                    "title": "আমাদের পরবর্তী অফার সম্পর্কে জানতে চান?",
                    "payload": "notify_me_payload" 
                }
            }
        }
    }
    try:
        requests.post(GRAPH_API_URL, params=params, headers=headers, json=data)
    except Exception:
        pass

def send_telegram_notification(order_details):
    if not TELEGRAM_USERNAME or not CALLMEBOT_API_KEY:
        return
    message_body = f"*নতুন অর্ডার এসেছে!*\n\n{order_details.replace('[ORDER_CONFIRMED]', '').strip()}"
    encoded_message = urllib.parse.quote_plus(message_body)
    api_url = f"https://api.callmebot.com/text.php?user={TELEGRAM_USERNAME}&text={encoded_message}&apikey={CALLMEBOT_API_KEY}"
    try:
        requests.get(api_url, timeout=10)
    except Exception:
        pass

def get_or_create_label_id(label_name):
    get_labels_url = f"https://graph.facebook.com/v18.0/me/custom_labels"
    params = {'fields': 'name', 'access_token': FACEBOOK_PAGE_ACCESS_TOKEN}
    try:
        response = requests.get(get_labels_url, params=params, timeout=10)
        response.raise_for_status()
        existing_labels = response.json().get('data', [])
        for label in existing_labels:
            if label.get('name') == label_name:
                return label.get('id')
        create_label_url = f"https://graph.facebook.com/v18.0/me/custom_labels"
        data = {'name': label_name}
        response = requests.post(create_label_url, params={'access_token': FACEBOOK_PAGE_ACCESS_TOKEN}, json=data, timeout=10)
        response.raise_for_status()
        new_label = response.json()
        return new_label.get('id')
    except requests.exceptions.RequestException:
        return None

def apply_date_label(user_psid):
    today_label_name = datetime.now().strftime("%d-%m-%Y")
    label_id = get_or_create_label_id(today_label_name)
    if not label_id:
        return
    apply_label_url = f"https://graph.facebook.com/v18.0/{label_id}/label"
    params = {'user': user_psid, 'access_token': FACEBOOK_PAGE_ACCESS_TOKEN}
    try:
        response = requests.post(apply_label_url, params=params, timeout=10)
        response.raise_for_status()
    except Exception:
        pass

def send_facebook_message(recipient_id, message_text):
    params = {'access_token': FACEBOOK_PAGE_ACCESS_TOKEN}
    headers = {'Content-Type': 'application/json'}
    data = {
        'recipient': {'id': recipient_id},
        'message': {'text': message_text},
        'messaging_type': 'RESPONSE'
    }
    try:
        requests.post(GRAPH_API_URL, params=params, headers=headers, json=data, timeout=10)
    except Exception:
        pass

