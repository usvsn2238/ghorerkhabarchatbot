import os
import requests
from flask import Flask, request
from dotenv import load_dotenv
import urllib.parse
from datetime import datetime
from pymongo import MongoClient
import re
import google.generativeai as genai
import certifi
import time

# .env ফাইল থেকে Environment Variables লোড করার জন্য
load_dotenv()

# Flask অ্যাপ ইনিশিয়ালাইজ করা
app = Flask(__name__)

# Environment Variables থেকে Key এবং Token গুলো নেওয়া
FACEBOOK_PAGE_ACCESS_TOKEN = os.getenv('FACEBOOK_PAGE_ACCESS_TOKEN')
VERIFY_TOKEN = os.getenv('VERIFY_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
MONGO_URI = os.getenv('MONGO_URI')
TELEGRAM_USERNAME = os.getenv('TELEGRAM_USERNAME')
CALLMEBOT_API_KEY = os.getenv('CALLMEBOT_API_KEY')

# --- ডেটাবেস কানেকশন ---
try:
    ca = certifi.where()
    client = MongoClient(MONGO_URI, tlsCAFile=ca)
    db = client.chatbot_db
    chat_history_collection = db.chat_history
    otn_tokens_collection = db.otn_tokens
    customer_details_collection = db.customer_details
    knowledge_collection = db.knowledge_base
    print("MongoDB ডেটাবেসের সাথে সফলভাবে সংযুক্ত।")
except Exception as e:
    print(f"MongoDB সংযোগে সমস্যা: {e}")
    client = None
# -------------------------

# --- নতুন: স্বয়ংক্রিয় প্রথম উত্তরের জন্য কীওয়ার্ড এবং মেসেজ ---
WELCOME_KEYWORDS = ("hi", "hello", "هاي", "هلو", "আসসালামু আলাইকুম", "দাম", "price", "মেন্যু", "menu", "list", "talika")

WELCOME_MESSAGE_1 = """
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

WELCOME_MESSAGE_2 = """
অর্ডার কনফার্ম করতে,
পণ্যের নাম, আপনার নাম, ঠিকানা, এবং মোবাইল নাম্বার দিয়ে আমাদের সহযোগিতা করুন।
"""

ORDER_CONFIRMATION_TEMPLATE = """
ধন্যবাদ, আপনার মোট চার্জ {} টাকা।
আপনি ১ থেকে ৩ দিনের মধ্যে প্রোডাক্টস পেয়ে যাবেন।
দয়া করে কনফার্ম করার পর ক্যানসেল করিয়েন না, কারণ আমরা অর্ডার দেয়ার পর তৈরি করি।
"""
# ----------------------------------------------------

# --- Gemini AI মডেল কনফিগার করা ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash-lite') 
    print("Gemini AI মডেল (2.5 Flash-Lite) সফলভাবে লোড হয়েছে।")
except Exception as e:
    print(f"Gemini AI কনফিগারেশনে সমস্যা হয়েছে: {e}")
    model = None

GRAPH_API_URL = 'https://graph.facebook.com/v19.0/me/messages'

def get_full_knowledge_base():
    if not client:
        return "কোনো তথ্য পাওয়া যায়নি।"
    try:
        all_docs = knowledge_collection.find({})
        knowledge_text = "\n".join([doc.get("information", "") for doc in all_docs])
        return knowledge_text if knowledge_text else "কোনো তথ্য পাওয়া যায়নি।"
    except Exception as e:
        print(f"সম্পূর্ণ জ্ঞানভান্ডার আনতে সমস্যা: {e}")
        return "কোনো তথ্য পাওয়া যায়নি।"

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
                        # ... (OTN কোড আগের মতোই থাকবে)
                        continue

                    if messaging_event.get('message'):
                        message_text = messaging_event['message'].get('text')
                        if message_text:
                            # --- নতুন কার্যপ্রণালী ---
                            history_count = get_chat_history_count(sender_id)
                            contains_welcome_keyword = any(keyword in message_text.lower() for keyword in WELCOME_KEYWORDS)

                            # ধাপ ১: প্রথম মেসেজ বা ওয়েলকাম কীওয়ার্ড পরীক্ষা
                            if history_count <= 1 or (contains_welcome_keyword and len(message_text.split()) < 4):
                                save_message_to_db(sender_id, 'user', message_text)
                                send_facebook_message(sender_id, WELCOME_MESSAGE_1)
                                time.sleep(1) # দুটি মেসেজের মধ্যে সামান্য বিরতি
                                send_facebook_message(sender_id, WELCOME_MESSAGE_2)
                                save_message_to_db(sender_id, 'model', "Sent welcome messages.")
                                continue
                            
                            # ধাপ ২: যদি উপরের কোনোটিই কাজ না করে, তবেই AI ব্যবহার করা
                            save_message_to_db(sender_id, 'user', message_text)
                            if model:
                                try:
                                    bot_response = get_gemini_response(sender_id, message_text)
                                    save_message_to_db(sender_id, 'model', bot_response)
                                    
                                    user_facing_response = bot_response
                                    
                                    if "[ORDER_CONFIRMATION]" in bot_response:
                                        bill_match = re.search(r'\[BILL:(\d+\.?\d*)\]', bot_response)
                                        total_bill = bill_match.group(1) if bill_match else "মোট বিল"
                                        
                                        confirmation_message = ORDER_CONFIRMATION_TEMPLATE.format(total_bill)
                                        send_facebook_message(sender_id, confirmation_message)
                                        
                                        details_match = re.search(r'\[DETAILS:(.*?)\]', bot_response)
                                        if details_match:
                                            details_str = details_match.group(1)
                                            save_customer_details(sender_id, details_str)
                                        
                                        send_otn_request(sender_id)
                                    else:
                                        send_facebook_message(sender_id, user_facing_response)

                                except Exception as e:
                                    print(f"Gemini থেকে উত্তর আনতে সমস্যা হয়েছে: {e}")
                                    send_facebook_message(sender_id, "দুঃখিত, এই মুহূর্তে উত্তর দিতে পারছি না।")
        return 'Event received', 200

def get_gemini_response(sender_id, message):
    history = get_chat_history(sender_id, limit=6)
    formatted_history = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history])

    customer_details = get_saved_customer_details(sender_id)
    details_context = "এই গ্রাহকের কোনো তথ্য আমাদের কাছে সেভ করা নেই।"
    saved_address = ""
    if customer_details and customer_details.get('address'):
        saved_address = customer_details.get('address')
        details_context = f"এই গ্রাহকের একটি ঠিকানা আমাদের কাছে সেভ করা আছে: {saved_address}"
    
    knowledge_base_for_prompt = get_full_knowledge_base()

    prompt = f"""
    ### আপনার ব্যক্তিত্ব (Persona) ###
    আপনি "ঘরের খাবার" এর একজন দক্ষ এবং পেশাদার সহকারী। আপনার উত্তর হবে সংক্ষিপ্ত, নির্ভুল এবং সাহায্যকারী।

    ### আপনার জ্ঞান (Knowledge Base) ###
    {knowledge_base_for_prompt}
    
    ### গ্রাহকের সেভ করা তথ্য (Saved Customer Details) ###
    {details_context}

    ### কঠোর নির্দেশনা (Strict Instructions) ###
    1.  সর্বদা এবং শুধুমাত্র "আপনার জ্ঞান" এবং "পূর্বের কথোপকথন" এর উপর ভিত্তি করে উত্তর দিন।
    2.  **প্রসঙ্গ বোঝার নিয়ম:** যদি আপনার আগের প্রশ্নে আপনি কোনো কনফার্মেশন চেয়ে থাকেন (যেমন: "আপনি কি অর্ডার করতে চান?") এবং গ্রাহক "জ্বি", "হ্যাঁ", "hmm", "ok", "কনফার্ম" এই ধরনের কোনো ইতিবাচক উত্তর দেয়, তাহলে প্রশ্নটি পুনরাবৃত্তি না করে অর্ডারের পরবর্তী ধাপে চলে যাবেন।
    3.  **হিসাব করার নিয়ম:** যদি গ্রাহক একাধিক আইটেমের মোট দাম জানতে চায়, তাহলে "পূর্বের কথোপকথন" এবং "আপনার জ্ঞান" থেকে আইটেম ও দাম নিয়ে সঠিকভাবে হিসাব করে একটি ব্রেকডাউন সহ মোট বিল দেখাবেন।
    4.  **অর্ডার কনফার্ম করার নিয়ম:** গ্রাহক যখন স্পষ্টভাবে অর্ডার নিশ্চিত করবে, তখন আপনার উত্তরের শুরুতে অবশ্যই "[ORDER_CONFIRMATION]" ট্যাগটি যোগ করবেন। এরপর "[BILL:মোট_টাকা]" এবং "[DETAILS:নাম=..., ঠিকানা=..., ফোন=...]" ট্যাগগুলো যোগ করবেন। যদি কোনো তথ্য না জানেন, তাহলে 'N/A' লিখবেন।
    
    ### কথোপকথনের উদাহরণ ###
    user: আমার এক প্যাকেট চিকেন রোল আর এক প্যাকেট পরোটা লাগবে।
    model: আপনি কোন পরোটা নিতে আগ্রহী? আমাদের কাছে আলু পরোটা এবং বিভিন্ন সাইজের চারকোনা পরোটা আছে।
    user: চারকোনা পরোটা ১২০০ গ্রাম।
    model: ঠিক আছে, স্যার/ম্যাম। আপনার দুটি আইটেম হলো: ১ প্যাকেট চিকেন রোল এবং ১ প্যাকেট চারকোনা পরোটা (১২০০gm)। আপনি কি অর্ডারটি কনফার্ম করতে চান?
    user: জ্বি
    model: অবশ্যই! আপনার দুটি আইটেমের মোট দাম আসছে:\n- চিকেন রোল (১ প্যাকেট): ২২৫ টাকা\n- চারকোনা পরোটা (১২০০gm): ২২০ টাকা\n- ডেলিভারি চার্জ: ৬০ টাকা\n\nসর্বমোট: ২২৫ + ২২০ + ৬০ = ৫০৫ টাকা। আপনার ঠিকানা কি আগেরটিই থাকবে?
    user: হ্যাঁ, কনফার্ম।
    model: [ORDER_CONFIRMATION]\n[BILL:505]\n[DETAILS:নাম=N/A, ঠিকানা={saved_address}, ফোন=N/A]

    ### পূর্বের কথোপকথন ###
    {formatted_history}

    ### নতুন মেসেজ ###
    user: "{message}"
    model: 
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return "দুঃখিত, একটি প্রযুক্তিগত সমস্যা হয়েছে। আমরা বিষয়টি দেখছি।"

def get_chat_history_count(sender_id):
    if client:
        return chat_history_collection.count_documents({'sender_id': sender_id})
    return 0

# (বাকি সব ফাংশন আগের মতোই থাকবে)
def save_message_to_db(sender_id, role, content):
    if client:
        chat_history_collection.insert_one({'sender_id': sender_id,'role': role,'content': content,'timestamp': datetime.utcnow()})

def get_chat_history(sender_id, limit=6):
    if client:
        history_cursor = chat_history_collection.find({'sender_id': sender_id}).sort('timestamp', -1).limit(limit)
        history = []
        for doc in history_cursor:
            role = doc.get('role')
            if role == 'assistant':
                role = 'model'
            history.append({'role': role, 'content': doc.get('content')})
        return history
    return []
    
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
                upsert=True)
    except Exception as e:
        print(f"গ্রাহকের তথ্য পার্স করতে সমস্যা: {e}")

def get_saved_customer_details(sender_id):
    if client:
        return customer_details_collection.find_one({'sender_id': sender_id})
    return None

def send_otn_request(recipient_id):
    params = {'access_token': FACEBOOK_PAGE_ACCESS_TOKEN}
    headers = {'Content-Type': 'application/json'}
    data = {'recipient': {'id': recipient_id},'message': {"attachment": {"type": "template","payload": {"template_type": "one_time_notif_req","title": "আমাদের পরবর্তী অফার সম্পর্কে জানতে চান?","payload": "notify_me_payload" }}}}
    try:
        requests.post(GRAPH_API_URL, params=params, headers=headers, json=data)
    except Exception:
        pass

def send_telegram_notification(order_details):
    if not TELEGRAM_USERNAME or not CALLMEBOT_API_KEY:
        return
    message_body = f"*নতুন অর্ডার এসেছে!*\n\n{order_details.replace('[ORDER_CONFIRMATION]', '').strip()}"
    encoded_message = urllib.parse.quote_plus(message_body)
    api_url = f"https://api.callmebot.com/text.php?user={TELEGRAM_USERNAME}&text={encoded_message}&apikey={CALLMEBOT_API_KEY}"
    try:
        requests.get(api_url, timeout=10)
    except Exception:
        pass

def get_or_create_label_id(label_name):
    get_labels_url = f"https://graph.facebook.com/v19.0/me/custom_labels"
    params = {'fields': 'name', 'access_token': FACEBOOK_PAGE_ACCESS_TOKEN}
    try:
        response = requests.get(get_labels_url, params=params, timeout=10)
        response.raise_for_status()
        existing_labels = response.json().get('data', [])
        for label in existing_labels:
            if label.get('name') == label_name:
                return label.get('id')
        create_label_url = f"https://graph.facebook.com/v19.0/me/custom_labels"
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
    apply_label_url = f"https://graph.facebook.com/v19.0/{label_id}/label"
    params = {'user': user_psid, 'access_token': FACEBOOK_PAGE_ACCESS_TOKEN}
    try:
        response = requests.post(apply_label_url, params=params, timeout=10)
        response.raise_for_status()
    except Exception:
        pass

def send_facebook_message(recipient_id, message_text):
    params = {'access_token': FACEBOOK_PAGE_ACCESS_TOKEN}
    headers = {'Content-Type': 'application/json'}
    data = {'recipient': {'id': recipient_id},'message': {'text': message_text},'messaging_type': 'RESPONSE'}
    try:
        requests.post(GRAPH_API_URL, params=params, headers=headers, json=data, timeout=10)
    except Exception:
        pass

