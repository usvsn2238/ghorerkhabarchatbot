import os
import requests
from flask import Flask, request
from dotenv import load_dotenv
import urllib.parse
from datetime import datetime
from pymongo import MongoClient
import re
from groq import Groq

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

# --- ডেটাবেস কানেকশন ---
try:
    client = MongoClient(MONGO_URI)
    db = client.chatbot_db
    chat_history_collection = db.chat_history
    otn_tokens_collection = db.otn_tokens
    customer_details_collection = db.customer_details
    print("MongoDB ডেটাবেসের সাথে সফলভাবে সংযুক্ত।")
except Exception as e:
    print(f"MongoDB সংযোগে সমস্যা: {e}")
    client = None
# -------------------------

KNOWLEDGE_BASE = """
# --- আমার হোমমেড ফ্রোজেন ফুড এর তথ্য ---
 
## আমাদের সম্পর্কে
আমরা "ঘরের খাবার" সম্পুর্ন বাসায় অত্যন্ত পরচ্ছন্নভাবে ফ্রোজেন ফুড তৈরি করে থাকি। আমারা অনলাইন অর্ডার এবং ডেলিভারি সেবা দিয়ে থাকি। আমাদের প্রধান লক্ষ্য হলো গ্রাহকদের সুস্বাদু এবং স্বাস্থ্যকর খাবার সরবরাহ করা।
## মেন্যু লিস্ট
### আসসালামু আলাইকুম 
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

## পলিসি এবং প্রায়শই জিজ্ঞাসিত প্রশ্ন (FAQ)
- **অর্ডার প্রসেসিং সময়:** অর্ডার কনফার্ম হওয়ার পর ২৪ থেকে ৭২ ঘণ্টার মধ্যে ডেলিভারি করা হয়। এটি আমাদের কাজের চাপ এবং ডেলিভারি লোকেশনের উপর নির্ভর করে।
- **ডেলিভারি এলাকা:মিরপুর, উত্তরা, বসুন্ধরা, গুলশান, তেজগাঁও, বনশ্রী , রামপুরা, ধানমন্ডি, মোহাম্মদপুর, আজিমপুর, পল্টন, মালিবাগ, শ্যামলী, কুড়িল, কলাবাগান, মগবাজার, নিকুঞ্জ, বনানী, বাড্ডা,  এলাকায় ডেলিভারি করা হয়। অন্যান্য এলাকার জন্য আলাদা আলোচনা প্রয়োজন হতে পারে।
- **ডেলিভারি চার্জ:** ৬০ টাকা।  
- **অর্ডার করার নিয়ম:** মেন্যু থেকে আপনার পছন্দের আইটেম জানান। অর্ডার কনফার্ম করার জন্য আপনার পুরো নাম, ডেলিভারি ঠিকানা, এবং একটি সচল ফোন নম্বর দিন।
- **পেমেন্ট:** আমরা বর্তমানে শুধুমাত্র ক্যাশ অন ডেলিভারি গ্রহণ করি।
- **যোগাযোগ:** যেকোনো প্রয়োজনে আমাদের পেজে মেসেজ দিন অথবা whats app নাম্বার 0১৭১৫৯৪৬৫৫৯ নম্বরে কল করুন।
"""

# Groq ক্লায়েন্ট কনফিগার করা
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    print("Groq AI ক্লায়েন্ট সফলভাবে লোড হয়েছে।")
except Exception as e:
    print(f"Groq AI কনফিগারেশনে সমস্যা হয়েছে: {e}")
    groq_client = None

GRAPH_API_URL = 'https://graph.facebook.com/v18.0/me/messages'

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
                            save_message_to_db(sender_id, 'user', message_text)
                            if groq_client:
                                try:
                                    bot_response = get_groq_response(sender_id, message_text)
                                    save_message_to_db(sender_id, 'bot', bot_response)
                                    
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
    history = get_chat_history(sender_id)
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

    system_prompt = f"""
    ### আপনার ব্যক্তিত্ব (Persona) ###
    আপনি "ঘরের খাবার" হোমমেড ফ্রোজেন ফুড এর একজন খুবই হাসিখুশি, বন্ধুসুলভ এবং হেল্পফুল মডারেটর। আপনার কথার ধরণ হবে কিছুটা ঘরোয়া এবং আন্তরিক। আপনি সবসময় গ্রাহককে স্যার/ম্যাম বলে সম্বোধন করবেন।

    ### আপনার জ্ঞান (Knowledge Base) ###
    {KNOWLEDGE_BASE}
    
    ### গ্রাহকের সেভ করা তথ্য (Saved Customer Details) ###
    {details_context}

    ### গুরুত্বপূর্ণ নির্দেশনা (Strict Instructions) ###
    1.  কথোপকথন শুরুতেই ঠিকানা চাইবেন না। প্রথমে গ্রাহকের উদ্দেশ্য বোঝার চেষ্টা করুন।
    2.  গ্রাহক যখন স্পষ্টভাবে অর্ডার করার ইচ্ছা প্রকাশ করবে, শুধুমাত্র তখনই অর্ডারের প্রক্রিয়া শুরু করবেন।
    3.  অর্ডারের প্রক্রিয়া শুরু করার সময়, প্রথমে "গ্রাহকের সেভ করা তথ্য" অংশটি দেখুন।
    4.  যদি সেখানে কোনো ঠিকানা সেভ করা থাকে, তাহলে গ্রাহককে জিজ্ঞেস করুন ওই ঠিকানায় অর্ডারটি পাঠাতে হবে কিনা। যেমন: "স্যার/ম্যাম, আপনার অর্ডারটি কি আপনার সেভ করা ঠিকানা '{saved_address}' এইখানে পাঠিয়ে দেবো?"
    5.  যদি কোনো ঠিকানা সেভ করা না থাকে, তবেই শুধুমাত্র গ্রাহকের কাছে তার পুরো নাম, ডেলিভারি ঠিকানা, এবং একটি সচল ফোন নম্বর চাইবেন।
    6.  অর্ডার চূড়ান্তভাবে নিশ্চিত হলে, আপনার উত্তরের শুরুতে অবশ্যই "[ORDER_CONFIRMED]" ট্যাগটি যোগ করবেন। এরপর একটি নতুন লাইনে "[DETAILS:নাম=..., ঠিকানা=..., ফোন=...]" এই ফরম্যাটে গ্রাহকের সম্পূর্ণ তথ্য যোগ করবেন।
    
    ### কথোপকথনের উদাহরণ (Conversation Examples) ###
    ---
    **স্যাম্পল ১: প্রথমবার অর্ডার**
    user: "একটা চিকেন নাগেট আর ফ্রেঞ্চ ফ্রাই অর্ডার করতে চাই।"
    (বট দেখবে কোনো ঠিকানা সেভ করা নেই)
    bot: "অবশ্যই, স্যার/ম্যাম! আপনার অর্ডারটি ডেলিভারি করার জন্য দয়া করে আপনার পুরো নাম, ডেলিভারি ঠিকানা, এবং একটি সচল ফোন নম্বর দিন।"
    user: "নাম: আকাশ, ঠিকানা: মিরপুর ডিওএইচএস, রোড-১, বাড়ি-৫, ঢাকা। ফোন: ০১৬xxxxxxxx"
    bot: "[ORDER_CONFIRMED] [DETAILS:নাম=আকাশ, ঠিকানা=মিরপুর ডিওএইচএস, রোড-১, বাড়ি-৫, ঢাকা, ফোন=০১৬xxxxxxxx] ধন্যবাদ, স্যার! আপনার অর্ডারটি কনফার্ম করা হয়েছে। 🎉 আমরা দ্রুত আপনার সাথে যোগাযোগ করব।"
    ---
    **স্যাম্পল ২: রিপিট কাস্টমার**
    user: "হাই, আমি কিছু ফ্রোজেন আইটেম অর্ডার করতে চাই।"
    (বট দেখবে ঠিকানা সেভ করা আছে)
    bot: "আপনাকে আবার স্বাগত, স্যার/ম্যাম! 😊 অবশ্যই অর্ডার করতে পারবেন। আপনার অর্ডারটি কি আপনার সেভ করা ঠিকানা 'মিরপুর ডিওএইচএস, রোড-১, বাড়ি-৫, ঢাকা' এইখানে পাঠিয়ে দেবো?"
    user: "হ্যাঁ, ওই ঠিকানাতেই পাঠান।"
    bot: "[ORDER_CONFIRMED] [DETAILS:নাম=আকাশ, ঠিকানা=মিরপুর ডিওএইচএস, রোড-১, বাড়ি-৫, ঢাকা, ফোন=০১৬xxxxxxxx] ধন্যবাদ, স্যার! আপনার অর্ডারটি আপনার সেভ করা ঠিকানার জন্য কনফার্ম করা হয়েছে। আর কিছু কি লাগবে আপনার?"
    ---
    """
    
    messages_for_api = [
        {"role": "system", "content": system_prompt}
    ]
    messages_for_api.extend(formatted_history)
    messages_for_api.append({"role": "user", "content": message})

    try:
        chat_completion = groq_client.chat.completions.create(
            messages=messages_for_api,
            model="llama3-70b-8192", # <-- পরিবর্তন: নতুন এবং শক্তিশালী মডেল
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        print(f"Groq API Error: {e}")
        return "দুঃখিত, একটি প্রযুক্তিগত সমস্যা হয়েছে। আমরা বিষয়টি দেখছি।"

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
            print(f"গ্রাহক {sender_id}-এর তথ্য সেভ/আপডেট করা হয়েছে।")
    except Exception as e:
        print(f"গ্রাহকের তথ্য পার্স বা সেভ করতে সমস্যা: {e}")

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

def get_chat_history(sender_id, limit=5):
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
    requests.post(GRAPH_API_URL, params=params, headers=headers, json=data)

def send_telegram_notification(order_details):
    if not TELEGRAM_USERNAME or not CALLMEBOT_API_KEY:
        print("Telegram নোটিফিকেশনের জন্য প্রয়োজনীয় তথ্য সেট করা নেই।")
        return
    message_body = f"*নতুন অর্ডার এসেছে!*\n\n{order_details.replace('[ORDER_CONFIRMED]', '').strip()}"
    encoded_message = urllib.parse.quote_plus(message_body)
    api_url = f"https://api.callmebot.com/text.php?user={TELEGRAM_USERNAME}&text={encoded_message}&apikey={CALLMEBOT_API_KEY}"
    try:
        response = requests.get(api_url, timeout=10)
        if response.status_code == 200:
            print("সফলভাবে Telegram নোটিফিকেশন পাঠানো হয়েছে।")
        else:
            print(f"Telegram নোটিফিকেশন পাঠাতে সমস্যা হয়েছে: {response.text}")
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
        return
    apply_label_url = f"https://graph.facebook.com/v18.0/{label_id}/label"
    params = {'user': user_psid, 'access_token': FACEBOOK_PAGE_ACCESS_TOKEN}
    try:
        response = requests.post(apply_label_url, params=params, timeout=10)
        response.raise_for_status()
        if response.json().get('success'):
            print(f"ব্যবহারকারী {user_psid}-কে সফলভাবে '{today_label_name}' লেবেল দেওয়া হয়েছে।")
    except requests.exceptions.RequestException as e:
        print(f"ফেসবুক লেবেল API-তে কল করতে সমস্যা হয়েছে: {e}")

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

