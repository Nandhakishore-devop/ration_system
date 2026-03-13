from flask import Flask, request, render_template, redirect, url_for
import sqlite3
import datetime
import os
import requests
from dotenv import load_dotenv

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
    """Sends real SMS via Fast2SMS to all registered users."""
    message = translate_to_tamil(status, items)
    
    # --- FAST2SMS CONFIGURATION ---
    # We prioritize the environment variable if present, otherwise use the hardcoded fallback
    hardcoded_key = "rmJEDw3Ub6ZkfvpbmgK8zn0R6myVJjKbbH36pdmhRlF49W3bXpGSD62e512B"
    API_KEY = os.environ.get("FAST2SMS_API_KEY", hardcoded_key).strip()
    
    # If the environment variable gives us the old 'disabled' key, manually override it
    if API_KEY.startswith("ENIs"):
        API_KEY = hardcoded_key
        
    URL = "https://www.fast2sms.com/dev/bulkV2"
    # ------------------------------

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT phone_number FROM users")
    users = cursor.fetchall()
    conn.close()

    # Clean numbers: Remove '+' and spaces. Fast2SMS likes 10-digit or 91-prefix numbers.
    cleaned_numbers = []
    for (phone,) in users:
        clean = "".join(filter(str.isdigit, phone)) # Keep only digits
        if len(clean) >= 10:
            cleaned_numbers.append(clean)
    
    phone_numbers = ",".join(cleaned_numbers)
    
    if not phone_numbers:
        return 0

    # Fast2SMS Payload
    payload = {
        "route": "q",
        "message": message,
        "language": "unicode",
        "numbers": phone_numbers,
    }
    
    headers = {
        "authorization": API_KEY,
        "Content-Type": "application/x-www-form-urlencoded",
    }

    # Logging for verification
    with open("sms_logs.txt", "a", encoding="utf-8") as f:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"\n--- Fast2SMS Attempt at {timestamp} ---\n")
        f.write(f"Message: {message}\n")
        f.write(f"Numbers: {phone_numbers}\n")
        
        try:
            if API_KEY == "YOUR_API_KEY_HERE":
                f.write("STATUS: SKIPPED (Placeholder API Key used)\n")
                print("⚠️ SMS skipped: Please provide a real Fast2SMS API Key in the .env file.")
            else:
                # Log first 4 chars of key for debug (SAFE)
                debug_key = f"{API_KEY[:4]}...{API_KEY[-4:]}" if len(API_KEY) > 8 else "too short"
                f.write(f"DEBUG_KEY_MASKED: {debug_key}\n")
                
                response = requests.post(URL, data=payload, headers=headers)
                f.write(f"STATUS: {response.status_code} - {response.text}\n")
                print(f"Fast2SMS Response: {response.status_code} - {response.text}")
        except Exception as e:
            f.write(f"ERROR: {str(e)}\n")
            
        f.write("-" * 30 + "\n")
    
    return len(users)

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
    
    # Diagnostic check for Internet/DNS
    print("\n--- Starting Diagnostics ---")
    try:
        requests.get("https://www.google.com", timeout=3)
        print("✅ Internet Connection: OK")
        requests.get("https://www.fast2sms.com", timeout=3)
        print("✅ Fast2SMS Server: REACHABLE")
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        print("Please check your internet connection or DNS settings.")
    print("--- Diagnostics End ---\n")

    app.run(debug=True)