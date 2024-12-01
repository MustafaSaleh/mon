import sqlite3
import os

DB_PATH = '/app/data/monitor.db'

def set_database_path(path):
    global DB_PATH 
    DB_PATH = path
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path=None):
    if db_path:
        set_database_path(db_path)
    
    conn = get_db()
    c = conn.cursor()
    
    try:
        c.execute('''CREATE TABLE IF NOT EXISTS services
            (id INTEGER PRIMARY KEY,
             name TEXT,
             type TEXT,
             target TEXT,
             check_frequency INTEGER,
             retry_threshold INTEGER,
             grace_period INTEGER,
             alert_email TEXT)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS checks
            (id INTEGER PRIMARY KEY,
             service_id INTEGER,
             timestamp TEXT,
             status TEXT,
             response_time REAL,
             details TEXT,
             FOREIGN KEY(service_id) REFERENCES services(id))''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS alerts
            (id INTEGER PRIMARY KEY,
             service_id INTEGER,
             timestamp TEXT,
             type TEXT,
             details TEXT,
             FOREIGN KEY(service_id) REFERENCES services(id))''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS errors
            (id INTEGER PRIMARY KEY,
             timestamp TEXT,
             error TEXT)''')

        c.execute('''CREATE TABLE IF NOT EXISTS smtp_config
            (id INTEGER PRIMARY KEY,
             host TEXT,
             port INTEGER,
             username TEXT,
             password TEXT,
             from_email TEXT,
             use_tls BOOLEAN)''')
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()