import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'expenses.db')

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Table for transactions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            pct REAL NOT NULL,
            debt_amount REAL NOT NULL,
            type TEXT NOT NULL, -- 'gasto', 'gasto_angela', 'abono', 'saldo_inicial'
            user_id INTEGER
        )
    ''')
    
    conn.commit()
    conn.close()

def format_money(amount):
    return f"${int(round(amount)):,}".replace(",", ".")

def add_transaction(description, amount, pct=0.5, trans_type='gasto', user_id=None):
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # debt_amount is how much this transaction changes Angela's debt to user
    # 'gasto': paid by user for shared/Angela -> Angela owes +(amount * pct)
    # 'gasto_angela': paid by Angela for shared/user -> user owes Angela, so Angela's debt to user decreases by -(amount * pct)
    # 'abono': Angela pays user -> Angela's debt to user decreases by -amount
    # 'saldo_inicial': sets or adds initial debt balance
    
    if trans_type == 'gasto':
        debt_amount = amount * pct
    elif trans_type == 'gasto_angela':
        debt_amount = -(amount * pct)
    elif trans_type == 'abono':
        debt_amount = -amount
    elif trans_type == 'saldo_inicial':
        debt_amount = amount
    else:
        debt_amount = amount * pct

    cursor.execute('''
        INSERT INTO transactions (timestamp, description, amount, pct, debt_amount, type, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (timestamp, description, amount, pct, debt_amount, trans_type, user_id))
    
    conn.commit()
    trans_id = cursor.lastrowid
    conn.close()
    
    return {
        'id': trans_id,
        'description': description,
        'amount': amount,
        'pct': pct,
        'debt_amount': debt_amount,
        'type': trans_type,
        'timestamp': timestamp
    }

def get_balance():
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT SUM(debt_amount) as total_debt FROM transactions')
    row = cursor.fetchone()
    total_debt = row['total_debt'] if row and row['total_debt'] is not None else 0.0
    
    cursor.execute("SELECT SUM(debt_amount) as total_gastos FROM transactions WHERE type = 'gasto'")
    g_row = cursor.fetchone()
    total_gastos = g_row['total_gastos'] if g_row and g_row['total_gastos'] is not None else 0.0

    cursor.execute("SELECT SUM(debt_amount) as total_angela FROM transactions WHERE type = 'gasto_angela'")
    ga_row = cursor.fetchone()
    total_angela = ga_row['total_angela'] if ga_row and ga_row['total_angela'] is not None else 0.0

    cursor.execute("SELECT SUM(-debt_amount) as total_abonos FROM transactions WHERE type = 'abono'")
    a_row = cursor.fetchone()
    total_abonos = a_row['total_abonos'] if a_row and a_row['total_abonos'] is not None else 0.0
    
    conn.close()
    
    return {
        'total_debt': total_debt,
        'total_gastos_deuda': total_gastos,
        'total_angela_deuda': abs(total_angela),
        'total_abonos': total_abonos
    }

def get_recent_transactions(limit=10):
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM transactions ORDER BY id DESC LIMIT ?', (limit,))
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def delete_transaction(trans_id):
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM transactions WHERE id = ?', (trans_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    
    cursor.execute('DELETE FROM transactions WHERE id = ?', (trans_id,))
    conn.commit()
    conn.close()
    return dict(row)

def delete_last_transaction():
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM transactions ORDER BY id DESC LIMIT 1')
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    
    cursor.execute('DELETE FROM transactions WHERE id = ?', (row['id'],))
    conn.commit()
    conn.close()
    return dict(row)

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully.")
