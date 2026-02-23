from flask import Flask, request, render_template
import sqlite3

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

    conn.commit()
    conn.close()

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        queue_status = request.form.get('queue_status')
        items = request.form.getlist('items')
        items_string = ", ".join(items)

        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO updates (queue_status, items) VALUES (?, ?)",
            (queue_status, items_string)
        )

        conn.commit()
        conn.close()

        return "<h2>Data Saved Successfully ✅</h2><a href='/'>Go Back</a>"

    return render_template('dashboard.html')

if __name__ == '__main__':
    init_db()
    app.run(debug=True)