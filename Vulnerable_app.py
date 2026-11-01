import os
import sqlite3
from flask import Flask, request

app = Flask(__name__)

def init_db():
    conn = sqlite3.connect('vuln.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, password TEXT, role TEXT)''')
    cursor.execute("INSERT OR IGNORE INTO users VALUES (1, 'admin', 'SuperSecretPassword123!', 'Administrator')")
    conn.commit()
    conn.close()

init_db()

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    
    conn = sqlite3.connect('vuln.db')
    cursor = conn.cursor()
    # الثغرة هنا: دمج المدخلات مباشرة بدون حماية
    query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
    
    try:
        cursor.execute(query)
        user = cursor.fetchone()
        if user:
            return f"Login Success! Welcome {user[1]}. Your role is {user[3]}.", 200
        else:
            return "Login Failed: Invalid credentials.", 401
    except Exception as e:
        return f"Database Error: {str(e)}", 500
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
