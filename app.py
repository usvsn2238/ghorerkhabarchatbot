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
    knowledge_collection = db.knowledge_base # জ্ঞানভান্ডার এখন পুরোপুরি ডেটাবেসে
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
# ----------------------------------------------------

# Groq ক্লায়েন্ট কনফিগার করা
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    print("Groq AI ক্লায়েন্ট সফলভাবে লোড হয়েছে।")
except Exception as e:
    print(f"Groq AI কনফিগারেশনে সমস্যা হয়েছে: {e}")
    groq_client = None

GRAPH_API_URL = 'https://graph.facebook.com/v19.0/me/messages'

def find_faq_response(message):
    lower_message = message.lower()
    for keywords, response in FAQ_RESPONSES.items():
        for keyword in keywords:
            if re.search(r'\b' + re.escape(keyword) + r'\b', lower_message):
                return response
    return None

# RAG: ডেটাবেস থেকে প্রাসঙ্গিক তথ্য খোঁজার ফাংশন
def find_relevant_knowledge(message):
    if not client:
        return None
    try:
        words = set(re.split(r'\s|[,.?]', message.lower()))
        knowledge_cursor = knowledge_collection.find({"keywords": {"$in": list(words)}})
        
        information_list = [doc.get("information") for doc in knowledge_cursor if doc.get("information")]
        
        if information_list:
            print(f"ডেটাবেস থেকে {len(information_list)} টি প্রাসঙ্গিক তথ্য পাওয়া গেছে (RAG)।")
            return "\n".join(information_list)
            
    except Exception as e:
        print(f"ডেটাবেস থেকে জ্ঞান খুঁজতে সমস্যা: {e}")
        
    print("ডেটাবেসে কোনো প্রাসঙ্গিক তথ্য পাওয়া যায়নি। সাধারণ AI ব্যবহার করা হচ্ছে।")
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
                        if messaging_event['optin'].get('type') == 'one_time_notif_req':
                            otn_token = messaging_event['optin']['one_time_notif_token']
                            save_otn_token(sender_id, otn_token)
                            send_facebook_message(sender_id, "ধন্যবাদ! আমরা পরবর্তী অফার এলে আপনাকে জানাবো।")
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
                            
                            # ধাপ ২: যদি FAQ-তে উত্তর না পাওয়া যায়, তবেই Guided AI ব্যবহার করা
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
    
    # RAG: ডেটাবেস থেকে শুধুমাত্র প্রাসঙ্গিক তথ্য খোঁজা
    relevant_knowledge = find_relevant_knowledge(message)
    knowledge_base_for_prompt = relevant_knowledge if relevant_knowledge else "প্রাসঙ্গিক কোনো তথ্য পাওয়া যায়নি।"

    system_prompt = f"""
    ### আপনার ব্যক্তিত্ব (Persona) ###
    আপনি "ঘরের খাবার" এর একজন হেল্পফুল এবং পেশাদার মডারেটর। আপনার কথার ধরণ হবে মার্জিত এবং আন্তরিক।

    ### আপনার জ্ঞান (Knowledge Base) ###
    {knowledge_base_for_prompt}
    
    ### গ্রাহকের সেভ করা তথ্য (Saved Customer Details) ###
    {details_context}

    ### কঠোর নির্দেশনা (Strict Instructions) ###
    1.  সর্বদা এবং শুধুমাত্র "আপনার জ্ঞান" সেকশনে দেওয়া তথ্যের উপর ভিত্তি করে উত্তর দিন। এর বাইরে কোনো উত্তর দেওয়া যাবে না।
    2.  যদি "আপনার জ্ঞান" সেকশনে "প্রাসঙ্গিক কোনো তথ্য পাওয়া যায়নি" লেখা থাকে, তাহলে বলুন: "দুঃখিত, এই বিষয়ে আমি নিশ্চিত নই। আপনাকে সাহায্য করার জন্য আমাদের একজন প্রতিনিধি শীঘ্রই আপনার সাথে যোগাযোগ করবে।"
    3.  যদি গ্রাহক একাধিক আইটেমের দাম হিসাব করতে বলে, তাহলে "আপনার জ্ঞান" সেকশনে দেওয়া তথ্য ব্যবহার করে গণিত করুন।
    4.  অর্ডার চূড়ান্তভাবে নিশ্চিত হলে, আপনার উত্তরের শুরুতে অবশ্যই "[ORDER_CONFIRMED]" ট্যাগটি যোগ করবেন।
    
    ### আপনার কাজ ###
    এখন, উপরে দেওয়া ব্যক্তিত্ব, জ্ঞান এবং কঠোর নির্দেশনাগুলো অনুসরণ করে নিচের নতুন মেসেজটির উত্তর দিন।

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
    data = {
        'recipient': {'id': recipient_id},
        'message': {'text': message_text},
        'messaging_type': 'RESPONSE'
    }
    try:
        requests.post(GRAPH_API_URL, params=params, headers=headers, json=data, timeout=10)
    except Exception:
        pass

