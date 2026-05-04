#!/usr/bin/env python3
"""
Quick smoke test for POST /api/orders endpoint after .env recreation
"""
import requests
import json
from pymongo import MongoClient
import os

# Backend URL - using internal URL since we're in the same container
BACKEND_URL = "http://localhost:8001"

# Test payload from review request
test_payload = {
    "customer": {
        "fullName": "Teste Cliente",
        "email": "kawemacielbrito4@gmail.com",
        "phone": "+351 912 345 678",
        "address": "Rua Teste",
        "addressNumber": "10",
        "addressComplement": "",
        "city": "Lisboa",
        "country": "PORTUGAL"
    },
    "items": [
        {
            "id": "syna-graffiti-hoodie",
            "slug": "syna-graffiti-hoodie",
            "name": "SYNA GRAFFITI HOODIE",
            "size": "M",
            "color": "VERDE",
            "qty": 1,
            "price": 155
        }
    ],
    "subtotal": 155
}

print("=" * 80)
print("SONDER E-COMMERCE - POST /api/orders SMOKE TEST")
print("=" * 80)
print()

# Test 1: POST /api/orders with valid payload
print("Test 1: POST /api/orders with valid payload")
print("-" * 80)
try:
    response = requests.post(
        f"{BACKEND_URL}/api/orders",
        json=test_payload,
        headers={"Content-Type": "application/json"},
        timeout=10
    )
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    if response.status_code == 200:
        data = response.json()
        order_id = data.get("orderId")
        email_sent = data.get("emailSent")
        created_at = data.get("createdAt")
        
        print()
        print("✅ Response validation:")
        print(f"   - orderId: {order_id} {'✅' if order_id and order_id.startswith('SND-') else '❌'}")
        print(f"   - createdAt: {created_at} {'✅' if created_at else '❌'}")
        print(f"   - emailSent: {email_sent} {'✅' if email_sent == True else '❌'}")
        
        # Test 2: Verify order in MongoDB
        print()
        print("Test 2: Verify order in MongoDB")
        print("-" * 80)
        try:
            mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
            db_name = os.environ.get('DB_NAME', 'test_database')
            
            client = MongoClient(mongo_url)
            db = client[db_name]
            orders_collection = db['orders']
            
            order = orders_collection.find_one({"orderId": order_id})
            
            if order:
                print(f"✅ Order found in MongoDB")
                print(f"   - orderId: {order.get('orderId')}")
                print(f"   - customer email: {order.get('customer', {}).get('email')}")
                print(f"   - items count: {len(order.get('items', []))}")
                print(f"   - subtotal: {order.get('subtotal')}")
                print(f"   - emailSent: {order.get('emailSent')}")
            else:
                print(f"❌ Order NOT found in MongoDB")
                
            client.close()
            
        except Exception as e:
            print(f"❌ MongoDB verification failed: {str(e)}")
        
        # Test 3: Check backend logs for email confirmation
        print()
        print("Test 3: Check backend logs for email confirmation")
        print("-" * 80)
        try:
            import subprocess
            result = subprocess.run(
                ["tail", "-n", "20", "/var/log/supervisor/backend.out.log"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            log_lines = result.stdout.split('\n')
            email_log_found = False
            
            for line in log_lines:
                if "Order email sent" in line and order_id in line:
                    print(f"✅ Email log found: {line.strip()}")
                    email_log_found = True
                    break
            
            if not email_log_found:
                print(f"⚠️  Email log not found for {order_id}")
                print("Recent logs:")
                for line in log_lines[-5:]:
                    if line.strip():
                        print(f"   {line.strip()}")
                        
        except Exception as e:
            print(f"❌ Log check failed: {str(e)}")
            
    else:
        print(f"❌ Expected 200, got {response.status_code}")
        
except requests.exceptions.RequestException as e:
    print(f"❌ Request failed: {str(e)}")
except Exception as e:
    print(f"❌ Test failed: {str(e)}")

print()
print("=" * 80)
print("SMOKE TEST COMPLETE")
print("=" * 80)
