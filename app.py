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
POSITIVE_CONFIRMATIONS = ("ji", "jee", "yes", "হ্যাঁ", "জ্বি", "ok", "okay", "hmm", "কনফার্ম", "confirm", "chai", "চাই")

# --- ধাপ ১: কীওয়ার্ড এবং নির্দিষ্ট বাক্যের জন্য উত্তর (বিনা খরচে) ---
# আপনি এখানে আপনার পছন্দ অনুযায়ী যত খুশি তত কীওয়ার্ড এবং উত্তর যোগ করতে পারেন।
FAQ_RESPONSES = {
    # --- কীওয়ার্ডের গ্রুপ ---       # --- নির্দিষ্ট উত্তর ---
    ("hi", "hello", "هاي", "هلو", "আসসালামু আলাইকুম"): "আসসালামু আলাইকুম, স্যার/ম্যাম! 😊 আপনাকে কিভাবে সাহায্য করতে পারি?",
    ("thanks", "thank you", "شكرا", "ধন্যবাদ"): "আপনাকে সাহায্য করতে পেরে আমরা আনন্দিত!",
    
    # --- আপনি এখানে নতুন নিয়ম যোগ করুন ---
    ("কেমন আছেন", "কেমন আছো"): "আমি ভালো আছি, ধন্যবাদ! আপনাকে কিভাবে সাহায্য করতে পারি?",
    ("আপনারা কখন খোলা থাকেন", "কখন খোলা", "কখন বন্ধ"): "আমাদের অনলাইন সেবা ২৪ ঘন্টাই খোলা থাকে। আপনি যেকোনো সময় অর্ডার করতে পারেন।",
    ("আপনাদের দোকান কোথায়", "আউটলেট, কোথায়","ঠিকানা","address","শো রুম" "ঠিকানা কি"): "আমাদের ঠিকানা: 1107 কাঁঠালতলা, পূর্ব মনিপুর, মিরপুর ২। তবে আমরা মূলত অনলাইন ডেলিভারি সেবা দিয়ে থাকি।"
    ("অর্ডার করতে চাই","অর্ডার কিভাবে করব", "order korte chai", "order korbo","ordar korbo"):"অর্ডার করতে পন্যের তালিকা, আপনার নাম,বাসার ঠিকানা এবং মোবাইল নাম্বার দিন প্লিজ।"
    
}
# --------------------------------------------------------------------


WELCOME_MESSAGE_1 = """
আসসালামু আলাইকুম 
আপনাদের জন্য নিয়ে এসেছি সুস্বাদু এবং স্বাস্থ্যকর ফ্রোজেন ফুডের মেন্যু। নিচে আমাদের মেন্যু লিস্ট দেওয়া হলো:
১) চিকেন রোল ১৫ পিসের প্যাক    ২২৫ টাকা
২) ভেজিটেবল রোল ১৫ পিসের প্যাক ১৫০ টাকা
... (আপনার সম্পূর্ণ মেন্যু এখানে থাকবে)
"""

WELCOME_MESSAGE_2 = "অর্ডার কনফার্ম করতে, পণ্যের নাম, আপনার নাম, ঠিকানা, এবং মোবাইল নাম্বার দিয়ে আমাদের সহযোগিতা করুন।"
ORDER_CONFIRMATION_TEMPLATE = "ধন্যবাদ, আপনার মোট চার্জ {} টাকা।\nআপনি ১ থেকে ৩ দিনের মধ্যে প্রোডাক্টস পেয়ে যাবেন।\nদয়া করে কনফার্ম করার পর ক্যানসেল করিয়েন না, কারণ আমরা অর্ডার দেয়ার পর তৈরি করি।"
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
    if not client: return "কোনো তথ্য পাওয়া যায়নি।"
    try:
        all_docs = knowledge_collection.find({})
        knowledge_text = "\n".join([doc.get("information", "") for doc in all_docs])
        return knowledge_text if knowledge_text else "কোনো তথ্য পাওয়া যায়নি।"
    except Exception as e:
        print(f"সম্পূর্ণ জ্ঞানভান্ডার আনতে সমস্যা: {e}")
        return "কোনো তথ্য পাওয়া যায়নি।"

def find_faq_response(message):
    lower_message = message.lower()
    for keywords, response in FAQ_RESPONSES.items():
        for keyword in keywords:
            # কীওয়ার্ডটি একটি সম্পূর্ণ শব্দ হিসেবে বাক্যের মধ্যে আছে কিনা তা পরীক্ষা করা হচ্ছে
            if re.search(r'\b' + re.escape(keyword) + r'\b', lower_message):
                return response
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
                            user_state, _ = get_or_create_user_state(sender_id)
                            lower_message = message_text.lower()
                            
                            # ধাপ ১: সাধারণ FAQ পরীক্ষা
                            faq_answer = find_faq_response(message_text)
                            if faq_answer:
                                send_facebook_message(sender_id, faq_answer)
                                continue

                            # ধাপ ২: যদি ব্যবহারকারী কনফার্মেশনের অপেক্ষায় থাকে
                            if user_state == "awaiting_confirmation" and any(word in lower_message for word in POSITIVE_CONFIRMATIONS):
                                save_message_to_db(sender_id, 'user', message_text)
                                call_ai_for_final_order(sender_id, message_text)
                                continue

                            # ধাপ ৩: প্রথম মেসেজ বা ওয়েলকাম কীওয়ার্ড
                            history_count = get_chat_history_count(sender_id)
                            contains_welcome_keyword = any(keyword in lower_message for keyword in WELCOME_KEYWORDS)
                            if history_count <= 1 or (contains_welcome_keyword and len(message_text.split()) < 4):
                                save_message_to_db(sender_id, 'user', message_text)
                                send_facebook_message(sender_id, WELCOME_MESSAGE_1)
                                time.sleep(1)
                                send_facebook_message(sender_id, WELCOME_MESSAGE_2)
                                save_message_to_db(sender_id, 'model', "Sent welcome messages.")
                                set_user_state(sender_id, "ordering")
                                continue
                            
                            # ধাপ ৪: সাধারণ AI কল
                            call_ai_for_general_chat(sender_id, message_text)
        return 'Event received', 200

def call_ai_for_general_chat(sender_id, message_text):
    """সাধারণ কথোপকথন এবং আইটেম শনাক্ত করার জন্য AI-কে কল করে"""
    save_message_to_db(sender_id, 'user', message_text)
    if model:
        try:
            bot_response = get_gemini_response(sender_id, message_text, "general_chat")
            save_message_to_db(sender_id, 'model', bot_response)
            
            if "আপনি কি অর্ডার করতে চান" in bot_response or "কনফার্ম করতে চান" in bot_response:
                set_user_state(sender_id, "awaiting_confirmation")
            else:
                set_user_state(sender_id, "ordering")
            
            send_facebook_message(sender_id, bot_response)
        except Exception as e:
            print(f"Gemini থেকে সাধারণ উত্তর আনতে সমস্যা: {e}")
            send_facebook_message(sender_id, "দুঃখিত, আমি বুঝতে পারিনি।")

def call_ai_for_final_order(sender_id, message_text):
    """ চূড়াnt অর্ডার এবং বিল হিসাবের জন্য AI-কে কল করে"""
    if model:
        try:
            bot_response = get_gemini_response(sender_id, message_text, "confirm_order")
            save_message_to_db(sender_id, 'model', bot_response)
            
            if "[ORDER_CONFIRMATION]" in bot_response:
                bill_match = re.search(r'\[BILL:(\d+\.?\d*)\]', bot_response)
                total_bill = bill_match.group(1) if bill_match else "মোট বিল"
                
                confirmation_message = ORDER_CONFIRMATION_TEMPLATE.format(total_bill)
                send_facebook_message(sender_id, confirmation_message)
                
                details_match = re.search(r'\[DETAILS:(.*?)\]', bot_response)
                if details_match:
                    details_str = details_match.group(1)
                    save_customer_details(sender_id, details_str, "completed")
                
                send_otn_request(sender_id)
            else:
                set_user_state(sender_id, "awaiting_address")
                send_facebook_message(sender_id, bot_response)
        except Exception as e:
            print(f"Gemini থেকে চূড়ান্ত অর্ডার আনতে সমস্যা: {e}")
            send_facebook_message(sender_id, "দুঃখিত, একটি সমস্যা হয়েছে।")


def get_gemini_response(sender_id, message, task):
    history = get_chat_history(sender_id, limit=6)
    formatted_history = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history])

    customer_details = get_saved_customer_details(sender_id)
    details_context = "এই গ্রাহকের কোনো তথ্য আমাদের কাছে সেভ করা নেই।"
    saved_address = ""
    if customer_details and customer_details.get('address'):
        saved_address = customer_details.get('address')
        details_context = f"এই গ্রাহকের একটি ঠিকানা আমাদের কাছে সেভ করা আছে: {saved_address}"
    
    knowledge_base_for_prompt = get_full_knowledge_base()

    if task == "confirm_order":
        task_prompt = "গ্রাহক তার অর্ডারটি কনফার্ম করেছে। পূর্বের কথোপকথন এবং আপনার জ্ঞান ব্যবহার করে মোট বিল হিসাব করুন এবং একটি চূড়ান্ত কনফার্মেশন তৈরি করুন।"
    else: # general_chat
        task_prompt = "পূর্বের কথোপকথন এবং আপনার জ্ঞান ব্যবহার করে গ্রাহকের নতুন মেসেজের একটি সাহায্যকারী উত্তর দিন।"

    prompt = f"""
    ### আপনার জ্ঞান (Knowledge Base) ###
    {knowledge_base_for_prompt}
    
    ### গ্রাহকের সেভ করা তথ্য ###
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
    model: অবশ্যই! আপনার দুটি আইটেমের মোট দাম আসছে:\n- চিকেন রোল (১ প্যাকেট): ২২৫ টাকা\n- চারকোনা পরোটা (১২০০gm): ২২০ টাকা\n- ডেলিভারি চার্জ: ৬০ টাকা\n\nসর্বমোট: ২২৫ + ২২০ + ৬০ = ৫০৫ টাকা। আপনার ডেলিভারি ঠিকানা কি প্রয়োজন?
    user: হ্যাঁ, কনফার্ম।
    model: [ORDER_CONFIRMATION]\n[BILL:505]\n[DETAILS:নাম=N/A, ঠিকানা={saved_address}, ফোন=N/A]

    ### আপনার বর্তমান কাজ ###
    {task_prompt}

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
        return "দুঃখিত, একটি প্রযুক্তিগত সমস্যা হয়েছে।"

# --- নতুন State Management ফাংশন ---
def get_or_create_user_state(sender_id):
    user_data = customer_details_collection.find_one({'sender_id': sender_id})
    if user_data:
        return user_data.get("state", "greeting"), user_data
    else:
        # নতুন ব্যবহারকারীর জন্য state 'greeting' হিসেবে শুরু হবে
        customer_details_collection.insert_one({'sender_id': sender_id, 'state': 'greeting'})
        return 'greeting', None

def set_user_state(sender_id, state):
    customer_details_collection.update_one(
        {'sender_id': sender_id},
        {'$set': {'state': state}},
        upsert=True
    )
# ------------------------------------

# (বাকি সব ফাংশন আগের মতোই থাকবে)
def get_chat_history_count(sender_id):
    if client:
        return chat_history_collection.count_documents({'sender_id': sender_id})
    return 0

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
    
def save_customer_details(sender_id, details_str, state="completed"):
    try:
        details = dict(item.split("=") for item in details_str.strip().split(", "))
        if client:
            customer_details_collection.update_one(
                {'sender_id': sender_id},
                {'$set': {
                    'name': details.get('নাম'),
                    'address': details.get('ঠিকানা'),
                    'phone': details.get('ফোন'),
                    'last_updated': datetime.utcnow(),
                    'state': state
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

