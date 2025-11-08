"""
ShopBot - E-commerce Chatbot Backend
Dialogflow CX Webhook Fulfillment with PostgreSQL
"""

from flask import Flask, request, jsonify
# import psycopg
import psycopg2
# from psycopg.rows import dict_row
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime, timedelta
import random
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Database Configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'dbname': os.getenv('DB_NAME', 'shopbot_db'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'your_password'),
    'port': os.getenv('DB_PORT', '5432')
}

def get_db_connection():
    """Create database connection"""
    try:
        # conn = psycopg.connect(**DB_CONFIG)
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

def track_order(order_id):
    """Track order status by order ID"""
    conn = get_db_connection()
    if not conn:
        return {"error": "Database connection failed"}
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT o.order_id, o.status, o.order_date, o.estimated_delivery,
                   c.name, c.email, c.phone
            FROM orders o
            JOIN customers c ON o.customer_id = c.customer_id
            WHERE o.order_id = %s
        """, (order_id,))
        
        order = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if order:
            return dict(order)
        else:
            return {"error": "Order not found"}
    except Exception as e:
        print(f"Error tracking order: {e}")
        return {"error": str(e)}

def process_return(order_id, reason):
    """Process return request"""
    conn = get_db_connection()
    if not conn:
        return {"error": "Database connection failed"}
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Check if order exists and is eligible for return
        cursor.execute("""
            SELECT order_id, status, order_date
            FROM orders
            WHERE order_id = %s
        """, (order_id,))
        
        order = cursor.fetchone()
        
        if not order:
            return {"error": "Order not found"}
        
        # Check if order is within return window (30 days)
        days_since_order = (datetime.now() - order['order_date']).days
        
        if days_since_order > 30:
            return {
                "eligible": False,
                "message": "Return window (30 days) has expired"
            }
        
        if order['status'] not in ['delivered', 'completed']:
            return {
                "eligible": False,
                "message": "Order must be delivered before initiating return"
            }
        
        # Create return request
        return_id = f"RET{random.randint(10000, 99999)}"
        cursor.execute("""
            INSERT INTO returns (return_id, order_id, reason, status, request_date)
            VALUES (%s, %s, %s, 'pending', %s)
        """, (return_id, order_id, reason, datetime.now()))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return {
            "eligible": True,
            "return_id": return_id,
            "message": "Return request created successfully"
        }
    except Exception as e:
        print(f"Error processing return: {e}")
        return {"error": str(e)}

def search_product(product_name):
    """Search for products"""
    conn = get_db_connection()
    if not conn:
        return {"error": "Database connection failed"}
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT product_id, name, price, stock_quantity, category
            FROM products
            WHERE LOWER(name) LIKE LOWER(%s)
            LIMIT 5
        """, (f"%{product_name}%",))
        
        products = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return [dict(p) for p in products]
    except Exception as e:
        print(f"Error searching products: {e}")
        return {"error": str(e)}

def get_customer_orders(email):
    """Get all orders for a customer"""
    conn = get_db_connection()
    if not conn:
        return {"error": "Database connection failed"}
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT o.order_id, o.status, o.order_date, o.total_amount
            FROM orders o
            JOIN customers c ON o.customer_id = c.customer_id
            WHERE c.email = %s
            ORDER BY o.order_date DESC
        """, (email,))
        
        orders = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return [dict(o) for o in orders]
    except Exception as e:
        print(f"Error fetching customer orders: {e}")
        return {"error": str(e)}

@app.route('/webhook', methods=['POST'])
def webhook():
    """Dialogflow CX webhook handler"""
    req = request.get_json()
    
    # Extract intent and parameters
    tag = req.get('fulfillmentInfo', {}).get('tag', '')
    parameters = req.get('sessionInfo', {}).get('parameters', {})
    
    response_text = "I'm here to help!"
    
    # Route to appropriate handler based on tag
    if tag == 'track-order':
        order_id = parameters.get('order_id', '')
        if order_id:
            result = track_order(order_id)
            if 'error' in result:
                response_text = f"Sorry, I couldn't find order {order_id}. Please check the order ID and try again."
            else:
                status = result['status']
                delivery = result.get('estimated_delivery', 'N/A')
                response_text = f"Your order {order_id} is currently {status}. "
                if status == 'shipped':
                    response_text += f"Estimated delivery: {delivery}"
                elif status == 'delivered':
                    response_text += "Your order has been delivered!"
                else:
                    response_text += f"Expected delivery: {delivery}"
        else:
            response_text = "Please provide your order ID to track your order."
    
    elif tag == 'process-return':
        order_id = parameters.get('order_id', '')
        reason = parameters.get('return_reason', 'Not specified')
        
        if order_id:
            result = process_return(order_id, reason)
            if 'error' in result:
                response_text = f"Error: {result['error']}"
            elif not result.get('eligible', False):
                response_text = result['message']
            else:
                response_text = f"Return request created! Your return ID is {result['return_id']}. We'll send you a prepaid shipping label within 24 hours."
        else:
            response_text = "Please provide your order ID to process the return."
    
    elif tag == 'search-product':
        product_name = parameters.get('product_name', '')
        if product_name:
            products = search_product(product_name)
            if isinstance(products, dict) and 'error' in products:
                response_text = "Sorry, I couldn't search for products right now."
            elif not products:
                response_text = f"Sorry, I couldn't find any products matching '{product_name}'."
            else:
                response_text = f"Found {len(products)} product(s):\n"
                for p in products[:3]:
                    stock_status = "In stock" if p['stock_quantity'] > 0 else "Out of stock"
                    response_text += f"\n• {p['name']} - ${p['price']} ({stock_status})"
        else:
            response_text = "What product are you looking for?"
    
    elif tag == 'get-customer-orders':
        email = parameters.get('email', '')
        if email:
            orders = get_customer_orders(email)
            if isinstance(orders, dict) and 'error' in orders:
                response_text = "Sorry, I couldn't retrieve your orders."
            elif not orders:
                response_text = "No orders found for this email."
            else:
                response_text = f"You have {len(orders)} order(s):\n"
                for o in orders[:5]:
                    response_text += f"\n• Order {o['order_id']}: {o['status']} (${o['total_amount']})"
        else:
            response_text = "Please provide your email address."
    
    # Build Dialogflow CX response
    response = {
        "fulfillment_response": {
            "messages": [
                {
                    "text": {
                        "text": [response_text]
                    }
                }
            ]
        }
    }
    
    return jsonify(response)

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)