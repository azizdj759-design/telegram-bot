import sqlite3

def create_db():
    # إنشاء قاعدة بيانات باسم leaks.db
    conn = sqlite3.connect('leaks.db')
    cursor = conn.cursor()
    
    # إنشاء الجدول
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leaked_users (
            username TEXT PRIMARY KEY,
            email TEXT,
            phone TEXT
        )
    ''')
    
    # إضافة بيانات تجريبية (أمثلة لتجربة البحث)
    dummy_data = [
        ('olivia', 'olivia.private@gmail.com', '+1 555-0199'),
        ('user123', 'user123@yahoo.com', '+44 7700 900077'),
        ('test', 'test@test.com', '+966 50 123 4567')
    ]
    
    cursor.executemany('INSERT OR IGNORE INTO leaked_users VALUES (?, ?, ?)', dummy_data)
    conn.commit()
    conn.close()
    print("✅ Database created successfully as 'leaks.db'")

if __name__ == "__main__":
    create_db()
