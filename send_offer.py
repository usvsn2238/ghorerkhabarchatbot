import os
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

# .env ফাইল থেকে Environment Variables লোড করার জন্য
load_dotenv()

# Environment Variables থেকে Key এবং Token গুলো নেওয়া
FACEBOOK_PAGE_ACCESS_TOKEN = os.getenv('FACEBOOK_PAGE_ACCESS_TOKEN')
MONGO_URI = os.getenv('MONGO_URI')

# ডেটাবেস কানেকশন
try:
    client = MongoClient(MONGO_URI)
    db = client.chatbot_db
    otn_tokens_collection = db.otn_tokens
    print("MongoDB ডেটাবেসের সাথে সফলভাবে সংযুক্ত।")
except Exception as e:
    print(f"MongoDB সংযোগে সমস্যা: {e}")
    exit()

def send_offer_message(offer_text):
    # ডেটাবেস থেকে সব অব্যবহৃত টোকেন খুঁজে বের করা
    tokens_to_use = otn_tokens_collection.find({'used': False})
    
    success_count = 0
    failure_count = 0

    for record in tokens_to_use:
        recipient_id = record['sender_id']
        otn_token = record['token']
        
        # Facebook Graph API-তে মেসেজ পাঠানোর জন্য রিকোয়েস্ট তৈরি
        params = {'access_token': FACEBOOK_PAGE_ACCESS_TOKEN}
        headers = {'Content-Type': 'application/json'}
        data = {
            'recipient': {'one_time_notif_token': otn_token},
            'message': {'text': offer_text}
        }
        
        try:
            response = requests.post('https://graph.facebook.com/v18.0/me/messages', params=params, headers=headers, json=data)
            
            if response.status_code == 200:
                print(f"সফলভাবে {recipient_id}-কে অফার পাঠানো হয়েছে।")
                # টোকেনটিকে 'used' হিসেবে মার্ক করা
                otn_tokens_collection.update_one({'_id': record['_id']}, {'$set': {'used': True}})
                success_count += 1
            else:
                print(f"ব্যর্থতা: {recipient_id}-কে মেসেজ পাঠানো যায়নি। Response: {response.json()}")
                # যদি টোকেনটি inválido হয়, তবে সেটিকেও used হিসেবে মার্ক করা যেতে পারে
                otn_tokens_collection.update_one({'_id': record['_id']}, {'$set': {'used': True}})
                failure_count += 1

        except Exception as e:
            print(f"একটি ত্রুটি ঘটেছে: {e}")
            failure_count += 1
            
    print(f"\nপ্রক্রিয়া সম্পন্ন।")
    print(f"সফলভাবে পাঠানো হয়েছে: {success_count} জনকে।")
    print(f"ব্যর্থ হয়েছে: {failure_count} জনের ক্ষেত্রে।")


if __name__ == '__main__':
    # এই স্ক্রিপ্টটি টার্মিনাল থেকে চালানোর সময় অফারের মেসেজটি দিতে হবে
    import sys
    if len(sys.argv) > 1:
        message = sys.argv[1]
        send_offer_message(message)
    else:
        print("ব্যবহার: python send_offer.py \"আপনার অফারের মেসেজ এখানে লিখুন\"")

