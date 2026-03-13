from flask import Flask, request, render_template, redirect, url_for
import sqlite3
import datetime
import os
import requests
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv() # Load variables from .env file

app = Flask(__name__)

def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            queue_status TEXT,
            items TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT UNIQUE NOT NULL,
            name TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            stock_kg REAL,
            max_stock_kg REAL,
            icon TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS queue_stats (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            waiting_count INTEGER DEFAULT 0,
            avg_wait TEXT DEFAULT '0m'
        )
    ''')

    # Seed inventory if empty
    cursor.execute("SELECT COUNT(*) FROM inventory")
    if cursor.fetchone()[0] == 0:
        items = [
            ('Premium Rice(அரிசி)', 1240, 1500, '🌾'),
            ('Refined Oil(எண்ணெய்)', 480, 1000, '💧'),
            ('Whole Wheat(கோதுமை)', 950, 1200, '🌾'),
            ('Fine Sugar(சர்க்கரை)', 120, 500, '🍦')
        ]
        cursor.executemany("INSERT INTO inventory (name, stock_kg, max_stock_kg, icon) VALUES (?, ?, ?, ?)", items)
    else:
        # Migration: Add Tamil to existing items if not present
        mapping = {
            'Premium Rice': 'Premium Rice(அரிசி)',
            'Refined Oil': 'Refined Oil(எண்ணெய்)',
            'Whole Wheat': 'Whole Wheat(கோதுமை)',
            'Fine Sugar': 'Fine Sugar(சர்க்கரை)'
        }
        for old, new in mapping.items():
            cursor.execute("UPDATE inventory SET name = ? WHERE name = ?", (new, old))

    # Seed queue_stats if empty
    cursor.execute("SELECT COUNT(*) FROM queue_stats")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO queue_stats (id, waiting_count, avg_wait) VALUES (1, 42, '8m')")

    conn.commit()
    conn.close()

def translate_to_tamil(status, items):
    """Simple translation logic for the SMS notification."""
    status_map = {
        "Empty": "காலியாக உள்ளது (Empty)",
        "Manageable": "மிதமான கூட்டம் (Manageable)",
        "Crowded": "அதிக கூட்டம் (Crowded)"
    }
    tamil_status = status_map.get(status, status)
    
    msg = f"ரேஷன் கடை அப்டேட்:\nவரிசை: {tamil_status}\nகிடைக்கும் பொருட்கள்: {items}\nஇப்போது வரலாம்."
    return msg

def simulate_sms_sending(status, items):
    """Sends real SMS via Twilio to all registered users."""
    message = translate_to_tamil(status, items)
    
    # --- TWILIO CONFIGURATION ---
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    twilio_number = os.environ.get("TWILIO_PHONE_NUMBER")
    
    if not all([account_sid, auth_token, twilio_number]) or "your_" in (account_sid + auth_token + twilio_number):
        print("⚠️ Twilio credentials missing or using placeholders. SMS skipped.")
        with open("sms_logs.txt", "a", encoding="utf-8") as f:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"\n--- Twilio Attempt SKIPPED at {timestamp} ---\n")
            f.write("REASON: Missing or placeholder credentials in .env\n")
            f.write("-" * 30 + "\n")
        return 0

    try:
        client = Client(account_sid, auth_token)
    except Exception as e:
        print(f"❌ Error initializing Twilio Client: {e}")
        return 0
    # ------------------------------

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT phone_number FROM users")
    users = cursor.fetchall()
    conn.close()

    if not users:
        return 0

    # Twilio sends messages individually
    success_count = 0
    error_count = 0

    with open("sms_logs.txt", "a", encoding="utf-8") as f:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"\n--- Twilio SMS Batch at {timestamp} ---\n")
        f.write(f"Message: {message}\n")
        
        for (phone,) in users:
            try:
                # Basic formatting: Twilio prefers E.164 (e.g., +919876543210)
                # If number doesn't start with +, we assume +91 (India) as per previous context
                formatted_phone = phone.strip()
                if not formatted_phone.startswith('+'):
                    # Strip non-digits and add +91
                    clean = "".join(filter(str.isdigit, formatted_phone))
                    formatted_phone = f"+91{clean}" if len(clean) == 10 else f"+{clean}"

                message_sent = client.messages.create(
                    body=message,
                    from_=twilio_number,
                    to=formatted_phone
                )
                f.write(f"SENT to {formatted_phone}: {message_sent.sid}\n")
                success_count += 1
            except Exception as e:
                f.write(f"ERROR to {phone}: {str(e)}\n")
                error_count += 1
                
        f.write(f"SUMMARY: {success_count} success, {error_count} failed\n")
        f.write("-" * 30 + "\n")
    
    print(f"Twilio Batch Complete: {success_count} sent, {error_count} failed.")
    return success_count

def analyze_best_time():
    """Simple data analysis to find the hour with most 'Empty' or 'Manageable' reports."""
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    # We look for hours where status was NOT Crowded
    cursor.execute("""
        SELECT strftime('%H', timestamp) as hour, COUNT(*) as count 
        FROM updates 
        WHERE queue_status IN ('Empty', 'Manageable')
        GROUP BY hour 
        ORDER BY count DESC 
        LIMIT 1
    """)
    result = cursor.fetchone()
    conn.close()
    
    if result:
        hour = int(result[0])
        period = "AM" if hour < 12 else "PM"
        display_hour = hour if hour <= 12 else hour - 12
        if display_hour == 0: display_hour = 12
        return f"{display_hour}:00 {period} to {display_hour + 1}:00 {period}"
    return "Not enough data yet"

@app.route('/', methods=['GET', 'POST'])
def home():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    if request.method == 'POST':
        queue_status = request.form.get('queue_status')
        items = request.form.getlist('items')
        items_string = ", ".join(items)

        cursor.execute(
            "INSERT INTO updates (queue_status, items) VALUES (?, ?)",
            (queue_status, items_string)
        )
        conn.commit()

        # Trigger SMS simulation
        count = simulate_sms_sending(queue_status, items_string)
        
        # After update, we could also decrement stock here if we want, 
        # but for now we just log it.
        
        return f"<h2>Data Saved & {count} SMS Simulants Logged ✅</h2><a href='/'>Go Back</a>"

    # Fetch recommendation
    recommendation = analyze_best_time()
    
    # Fetch inventory
    cursor.execute("SELECT * FROM inventory")
    inventory = cursor.fetchall()
    
    # Fetch recent updates (optional missed feature)
    cursor.execute("SELECT * FROM updates ORDER BY timestamp DESC LIMIT 5")
    recent_updates = cursor.fetchall()
    
    # Fetch user count
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]

    # Fetch queue stats
    cursor.execute("SELECT waiting_count, avg_wait FROM queue_stats WHERE id = 1")
    q_stats = cursor.fetchone()
    waiting_count = q_stats[0] if q_stats else 42
    avg_wait = q_stats[1] if q_stats else '8m'

    conn.close()
    return render_template('dashboard.html', 
                           recommendation=recommendation, 
                           inventory=inventory,
                           recent_updates=recent_updates,
                           user_count=user_count,
                           waiting_count=waiting_count,
                           avg_wait=avg_wait)

@app.route('/update_stats', methods=['POST'])
def update_stats():
    waiting_count = request.form.get('waiting_count')
    avg_wait = request.form.get('avg_wait')
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE queue_stats SET waiting_count = ?, avg_wait = ? WHERE id = 1", 
                   (waiting_count, avg_wait))
    conn.commit()
    conn.close()
    return redirect(url_for('home'))

@app.route('/customers')
def customers():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    conn.close()
    return render_template('customers.html', users=users)

@app.route('/edit_customer/<int:id>', methods=['POST'])
def edit_customer(id):
    name = request.form.get('name')
    phone = request.form.get('phone')
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET name = ?, phone_number = ? WHERE id = ?", (name, phone, id))
    conn.commit()
    conn.close()
    return redirect(url_for('customers'))

@app.route('/delete_customer/<int:id>', methods=['POST'])
def delete_customer(id):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('customers'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        phone = request.form.get('phone')
        name = request.form.get('name')

        try:
            conn = sqlite3.connect('database.db')
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (phone_number, name) VALUES (?, ?)", (phone, name))
            conn.commit()
            conn.close()
            return "<h2>Registration Successful! ✅</h2><a href='/'>Go to Dashboard</a>"
        except sqlite3.IntegrityError:
            return "<h2>Phone number already registered! ❌</h2><a href='/register'>Try Again</a>"

    return render_template('register.html')

if __name__ == '__main__':
    init_db()
    
    # Diagnostic check for Internet/DNS and Twilio
    print("\n--- Starting Diagnostics ---")
    try:
        requests.get("https://www.google.com", timeout=3)
        print("✅ Internet Connection: OK")
        requests.get("https://api.twilio.com", timeout=3)
        print("✅ Twilio Server: REACHABLE")
        
        # Check for credentials
        if all([os.environ.get("TWILIO_ACCOUNT_SID"), os.environ.get("TWILIO_AUTH_TOKEN"), os.environ.get("TWILIO_PHONE_NUMBER")]):
            if "your_" not in os.environ.get("TWILIO_ACCOUNT_SID", ""):
                 print("✅ Twilio Credentials: FOUND")
            else:
                 print("⚠️ Twilio Credentials: PLACEHOLDERS DETECTED")
        else:
            print("❌ Twilio Credentials: MISSING")
    except Exception as e:
        print(f"❌ Connection Error: {e}")
    print("--- Diagnostics End ---\n")

    app.run(debug=True)