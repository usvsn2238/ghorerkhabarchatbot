import os
import requests
from flask import Flask, request
import google.generativeai as genai
from dotenv import load_dotenv
import urllib.parse
from datetime import datetime, timedelta
from pymongo import MongoClient # ডেটাবেসের জন্য নতুন ইম্পোর্ট

# .env ফাইল থেকে Environment Variables লোড করার জন্য
load_dotenv()

# Flask অ্যাপ ইনিশিয়ালাইজ করা
app = Flask(__name__)

# Environment Variables থেকে Key এবং Token গুলো নেওয়া
FACEBOOK_PAGE_ACCESS_TOKEN = os.getenv('FACEBOOK_PAGE_ACCESS_TOKEN')
VERIFY_TOKEN = os.getenv('VERIFY_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
WHATSAPP_PHONE_NO = os.getenv('WHATSAPP_PHONE_NO')
CALLMEBOT_API_KEY = os.getenv('CALLMEBOT_API_KEY')
MONGO_URI = os.getenv('MONGO_URI') # নতুন: MongoDB কানেকশন স্ট্রিং

# --- ডেটাবেস কানেকশন ---
try:
    client = MongoClient(MONGO_URI)
    db = client.chatbot_db # ডেটাবেসের নাম
    chat_history_collection = db.chat_history # কথোপকথন সেভ করার কালেকশন
    otn_tokens_collection = db.otn_tokens # OTN টোকেন সেভ করার কালেকশন
    print("MongoDB ডেটাবেসের সাথে সফলভাবে সংযুক্ত।")
except Exception as e:
    print(f"MongoDB সংযোগে সমস্যা: {e}")
    client = None
# -------------------------

KNOWLEDGE_BASE = """
# --- আমার রেস্টুরেন্টের তথ্য ---

## আমাদের সম্পর্কে
আমরা "ফুড ফিউশন" ক্যাফে, ঢাকার উত্তরাতে অবস্থিত। আমরা প্রতিদিন সকাল ১০টা থেকে রাত ১১টা পর্যন্ত খোলা থাকি।

## মেন্যু লিস্ট
### বার্গার
- স্পাইসি চিকেন বার্গার: ৳২০০
- বিফ চিজ ডিলাইট: ৳২৫০
- ভেজি ক্লাসিক: ৳১৮০
### ড্রিংকস
- কোক: ৳৩০, স্প্রাইট: ৳৩০, মিনারেল ওয়াটার: ৳২০

## পলিসি এবং প্রায়শই জিজ্ঞাসিত প্রশ্ন (FAQ)
- **ডেলিভারি চার্জ:** উত্তরার ভেতরে ৫০ টাকা। উত্তরার বাইরে ১০০ টাকা।
- **অর্ডার করার নিয়ম:** মেন্যু থেকে আপনার পছন্দের আইটেম জানান। অর্ডার কনফার্ম করার জন্য আপনার পুরো নাম, ডেলিভারি ঠিকানা, এবং একটি সচল ফোন নম্বর দিন।
- **পেমেন্ট:** আমরা বর্তমানে শুধুমাত্র ক্যাশ অন ডেলিভারি গ্রহণ করি।
- **যোগাযোগ:** যেকোনো প্রয়োজনে আমাদের পেজে মেসেজ দিন অথবা 01700000000 নম্বরে কল করুন।
"""

# Gemini AI মডেল কনফিগার করা
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    print("Gemini AI মডেল সফলভাবে লোড হয়েছে।")
except Exception as e:
    print(f"Gemini AI কনফিগারেশনে সমস্যা হয়েছে: {e}")
    model = None

# Facebook Graph API-এর URL
GRAPH_API_URL = 'https://graph.facebook.com/v18.0/me/messages'

@app.route('/')
def home():
    return 'সার্ভারটি সফলভাবে চলছে!', 200

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        # Webhook ভেরিফিকেশন
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
                    
                    # --- নতুন: OTN অনুমতি হ্যান্ডেল করা ---
                    if messaging_event.get('optin'):
                        if messaging_event['optin'].get('type') == 'one_time_notif_req':
                            otn_token = messaging_event['optin']['one_time_notif_token']
                            save_otn_token(sender_id, otn_token)
                            send_facebook_message(sender_id, "ধন্যবাদ! আমরা পরবর্তী অফার এলে আপনাকে জানাবো।")
                        continue # লুপের পরবর্তী ধাপে চলে যাবে

                    if messaging_event.get('message'):
                        message_text = messaging_event['message'].get('text')
                        if message_text:
                            save_message_to_db(sender_id, 'user', message_text)
                            if model:
                                try:
                                    bot_response = get_gemini_response(sender_id, message_text)
                                    save_message_to_db(sender_id, 'bot', bot_response)
                                    
                                    if "[ORDER_CONFIRMED]" in bot_response:
                                        send_whatsapp_notification(bot_response)
                                        apply_date_label(sender_id)
                                        user_facing_response = bot_response.replace("[ORDER_CONFIRMED]", "").strip()
                                        send_facebook_message(sender_id, user_facing_response)
                                        # অর্ডার কনফার্ম করার পর OTN রিকুয়েস্ট পাঠানো
                                        send_otn_request(sender_id)
                                    else:
                                        send_facebook_message(sender_id, bot_response)

                                except Exception as e:
                                    print(f"Gemini থেকে উত্তর আনতে সমস্যা হয়েছে: {e}")
                                    send_facebook_message(sender_id, "দুঃখিত, এই মুহূর্তে উত্তর দিতে পারছি না।")
        return 'Event received', 200

def get_gemini_response(sender_id, message):
    # --- নতুন: ডেটাবেস থেকে হিস্টোরি নেওয়া ---
    history = get_chat_history(sender_id)
    formatted_history = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history])

    prompt = f"""
    আপনি "ফুড ফিউশন" ক্যাফের একজন হেল্পফুল অ্যাসিস্ট্যান্ট। আপনার কাজ হলো নিচে দেওয়া তথ্য এবং পূর্বের কথোপকথনের উপর ভিত্তি করে উত্তর দেওয়া।

    --- এখানে আমাদের তথ্য ---
    {KNOWLEDGE_BASE}
    --- তথ্য শেষ ---

    --- পূর্বের কথোপকথন ---
    {formatted_history}
    --- কথোপকথন শেষ ---

    গুরুত্বপূর্ণ নির্দেশনা:
    1. অর্ডার নিশ্চিত হলে, আপনার উত্তরের শুরুতে অবশ্যই "[ORDER_CONFIRMED]" ট্যাগটি যোগ করবেন।

    এখন, এই তথ্যের উপর ভিত্তি করে নিচের নতুন প্রশ্নের উত্তর দিন:
    user: "{message}"
    bot: 
    """
    response = model.generate_content(prompt)
    return response.text

# --- নতুন ফাংশন: ডেটাবেসে মেসেজ সেভ করার জন্য ---
def save_message_to_db(sender_id, role, content):
    if client:
        chat_history_collection.insert_one({
            'sender_id': sender_id,
            'role': role,
            'content': content,
            'timestamp': datetime.utcnow()
        })

# --- নতুন ফাংশন: ডেটাবেস থেকে হিস্টোরি আনার জন্য ---
def get_chat_history(sender_id, limit=5):
    if client:
        # শেষ ৫টি মেসেজ আনা হচ্ছে
        history_cursor = chat_history_collection.find({'sender_id': sender_id}).sort('timestamp', -1).limit(limit)
        return list(history_cursor)[::-1] # পুরাতন থেকে নতুন 순서
    return []

# --- নতুন ফাংশন: OTN রিকুয়েস্ট পাঠানোর জন্য ---
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
        requests.post(GRAPH_API_URL, params=params, headers=headers, json=data, timeout=10)
    except requests.exceptions.RequestException as e:
        print(f"OTN রিকুয়েস্ট পাঠাতে সমস্যা হয়েছে: {e}")

# --- নতুন ফাংশন: OTN টোকেন সেভ করার জন্য ---
def save_otn_token(sender_id, token):
    if client:
        otn_tokens_collection.insert_one({
            'sender_id': sender_id,
            'token': token,
            'used': False,
            'created_at': datetime.utcnow()
        })
        print(f"ব্যবহারকারী {sender_id}-এর জন্য OTN টোকেন সেভ করা হয়েছে।")

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
    except requests.exceptions.RequestException as e:
        print(f"ফেসবুকে মেসেজ পাঠাতে সমস্যা হয়েছে: {e}")

def send_whatsapp_notification(order_details):
    if not WHATSAPP_PHONE_NO or not CALLMEBOT_API_KEY:
        print("WhatsApp নোটিফিকেশনের জন্য প্রয়োজনীয় তথ্য সেট করা নেই।")
        return
    
    message_body = f"*নতুন অর্ডার এসেছে!*\n\n{order_details.replace('[ORDER_CONFIRMED]', '').strip()}"
    encoded_message = urllib.parse.quote_plus(message_body)
    
    api_url = f"https://api.callmebot.com/whatsapp.php?phone={WHATSAPP_PHONE_NO}&text={encoded_message}&apikey={CALLMEBOT_API_KEY}"
    
    try:
        response = requests.get(api_url, timeout=10)
        if response.status_code == 200:
            print("সফলভাবে WhatsApp নোটিফিকেশন পাঠানো হয়েছে।")
        else:
            print(f"WhatsApp নোটিফিকেশন পাঠাতে সমস্যা হয়েছে: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"CallMeBot API-তে কল করতে সমস্যা হয়েছে: {e}")

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

    except requests.exceptions.RequestException as e:
        print(f"লেবেল তৈরি বা খুঁজতে সমস্যা হয়েছে: {e}")
        return None

def apply_date_label(user_psid):
    today_label_name = datetime.now().strftime("%d-%m-%Y")
    label_id = get_or_create_label_id(today_label_name)
    
    if not label_id:
        print("লেবেল আইডি পাওয়া যায়নি।")
        return

    apply_label_url = f"https://graph.facebook.com/v18.0/{label_id}/label"
    params = {'user': user_psid, 'access_token': FACEBOOK_PAGE_ACCESS_TOKEN}
    
    try:
        response = requests.post(apply_label_url, params=params, timeout=10)
        response.raise_for_status()
        if response.json().get('success'):
            print(f"ব্যবহারকারীকে সফলভাবে '{today_label_name}' লেবেল দেওয়া হয়েছে।")
    except requests.exceptions.RequestException as e:
        print(f"ফেসবুক লেবেল API-তে কল করতে সমস্যা হয়েছে: {e}")

