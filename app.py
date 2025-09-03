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

# --- শুধুমাত্র সাধারণ অভিবাদনের জন্য নির্দিষ্ট উত্তর ---
FAQ_RESPONSES = {
    ("hi", "hello", "هاي", "هلو", "আসসালামু আলাইকুম"): "আসসালামু আলাইকুম, স্যার/ম্যাম! 😊 আপনাকে কিভাবে সাহায্য করতে পারি?",
    ("thanks", "thank you", "شكرا", "ধন্যবাদ"): "আপনাকে সাহায্য করতে পেরে আমরা আনন্দিত!",
}
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
        knowledge_text = "\n".join([f"- {doc.get('information', '')}" for doc in all_docs])
        # সম্পূর্ণ মেন্যুটিও যোগ করা হচ্ছে
        full_menu = """
        সম্পূর্ণ মেন্যু লিস্ট:
        ১) চিকেন রোল ১৫ পিসের প্যাক    ২২৫ টাকা
        ২) ভেজিটেবল রোল ১৫ পিসের প্যাক ১৫০ টাকা
        ৩) বিফ রোল ১০ পিসের প্যাক ২৫০ টাকা 
        ... (আপনার সম্পূর্ণ মেন্যু এখানে থাকবে)
        """
        return full_menu + "\n\nঅন্যান্য তথ্য:\n" + knowledge_text
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
                        # ... (OTN কোড)
                        continue

                    if messaging_event.get('message'):
                        message_text = messaging_event['message'].get('text')
                        if message_text:
                            # --- নতুন এবং সরলীকৃত কার্যপ্রণালী ---
                            lower_message = message_text.lower()
                            is_faq = False
                            for keywords, response in FAQ_RESPONSES.items():
                                for keyword in keywords:
                                    if re.search(r'\b' + re.escape(keyword) + r'\b', lower_message):
                                        send_facebook_message(sender_id, response)
                                        is_faq = True
                                        break
                                if is_faq: break
                            
                            if is_faq:
                                continue

                            # যদি FAQ না হয়, তবেই AI ব্যবহার করা
                            save_message_to_db(sender_id, 'user', message_text)
                            if model:
                                try:
                                    bot_response = get_gemini_response(sender_id, message_text)
                                    save_message_to_db(sender_id, 'model', bot_response)
                                    
                                    user_facing_response = bot_response
                                    
                                    if "[ORDER_CONFIRMATION]" in bot_response:
                                        bill_match = re.search(r'\[BILL:(\d+\.?\d*)\]', bot_response)
                                        total_bill = bill_match.group(1) if bill_match else "মোট বিল"
                                        
                                        confirmation_message = f"ধন্যবাদ, আপনার মোট চার্জ {total_bill} টাকা।\nআপনি ১ থেকে ৩ দিনের মধ্যে প্রোডাক্টস পেয়ে যাবেন।\nদয়া করে কনফার্ম করার পর ক্যানসেল করিয়েন না, কারণ আমরা অর্ডার দেয়ার পর তৈরি করি।"
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
    
    ### গ্রাহকের সেভ করা তথ্য ###
    {details_context}

    ### কঠোর নির্দেশনা (Strict Instructions) ###
    1.  **সীমানা:** সর্বদা এবং শুধুমাত্র "আপনার জ্ঞান" এবং "পূর্বের কথোপকথন" এর উপর ভিত্তি করে উত্তর দিন। এর বাইরে একটি শব্দও বলা যাবে না।
    2.  **অজানা প্রশ্ন:** যদি গ্রাহকের প্রশ্নের উত্তর "আপনার জ্ঞান"-এর মধ্যে না থাকে, তাহলে বলুন: "দুঃখিত, এই বিষয়ে আমি নিশ্চিত নই। আপনাকে সাহায্য করার জন্য আমাদের একজন প্রতিনিধি শীঘ্রই আপনার সাথে যোগাযোগ করবে।"
    3.  **ক্রমিক নম্বর বোঝা:** "আপনার জ্ঞান"-এর মধ্যে দেওয়া মেন্যুটি একটি numerised তালিকা। যদি গ্রাহক "১ নম্বর" বা "১ ও ২ নম্বর" বলে, তাহলে আপনাকে অবশ্যই তালিকা থেকে সঠিক আইটেমগুলো শনাক্ত করতে হবে।
    4.  **প্রসঙ্গ বোঝা (সবচেয়ে গুরুত্বপূর্ণ):** যদি আপনার আগের প্রশ্নে আপনি কোনো কনফার্মেশন চেয়ে থাকেন (যেমন: "আপনি কি অর্ডার করতে চান?") এবং গ্রাহক "জ্বি", "হ্যাঁ", "hmm", "ok", "কনফার্ম", "নিতে চাই", "চাই" এই ধরনের কোনো ইতিবাচক উত্তর দেয়, তাহলে প্রশ্নটি পুনরাবৃত্তি না করে অর্ডারের পরবর্তী ধাপে চলে যাবেন (যেমন: বিল হিসাব করা বা ঠিকানা চাওয়া)।
    5.  **হিসাব করা:** যদি গ্রাহক একাধিক আইটেমের মোট দাম জানতে চায়, তাহলে "পূর্বের কথোপকথন" এবং "আপনার জ্ঞান" থেকে আইটেম ও দাম নিয়ে সঠিকভাবে হিসাব করে একটি ব্রেকডাউন সহ মোট বিল দেখাবেন।
    6.  **অর্ডার কনফার্ম করা:** গ্রাহক যখন তার নাম, ঠিকানা এবং ফোন নম্বর দেবে, তখনই অর্ডারটি চূড়ান্তভাবে নিশ্চিত হবে। তখন আপনার উত্তরের শুরুতে অবশ্যই "[ORDER_CONFIRMATION]" ট্যাগটি যোগ করবেন। এরপর "[BILL:মোট_টাকা]" এবং "[DETAILS:নাম=..., ঠিকানা=..., ফোন=...]" ট্যাগগুলো যোগ করবেন।
    
    ### কথোপকথনের উদাহরণ ###
    user: আমার ১ ও ২ নম্বর আইটেম লাগবে।
    model: আপনি কি মেন্যুর ১ নম্বর (চিকেন রোল) এবং ২ নম্বর (ভেজিটেবল রোল) আইটেমগুলো অর্ডার করতে চান?
    user: জ্বি
    model: অবশ্যই! আপনার দুটি আইটেমের মোট দাম আসছে:\n- চিকেন রোল (১ প্যাকেট): ২২৫ টাকা\n- ভেজিটেবল রোল (১ প্যাকেট): ১৫০ টাকা\n- ডেলিভারি চার্জ: ৬০ টাকা\n\nসর্বমোট: ২২৫ + ১৫০ + ৬০ = ৪৩৫ টাকা। আপনার অর্ডারটি কনফার্ম করার জন্য আপনার নাম, ঠিকানা ও ফোন নম্বর দিন।
    user: নাম: Rahim, ঠিকানা: Dhaka, ফোন: 123
    model: [ORDER_CONFIRMATION]\n[BILL:435]\n[DETAILS:নাম=Rahim, ঠিকানা=Dhaka, ফোন=123]

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
    
def save_customer_details(sender_id, details_str):
    try:
        details = dict(item.split("=") for item in details_str.strip().split(", "))
        if client:
            update_data = {
                'name': details.get('নাম'),
                'address': details.get('ঠিকানা'),
                'phone': details.get('ফোন'),
                'last_updated': datetime.utcnow(),
            }
            update_data = {k: v for k, v in update_data.items() if v is not None}
            customer_details_collection.update_one(
                {'sender_id': sender_id},
                {'$set': update_data},
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

