import sqlite3
import os
import csv
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'expenses.db')

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')
    
    conn.commit()
    conn.close()

def set_setting(key, value):
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, str(value)))
    conn.commit()
    conn.close()

def get_setting(key):
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = cursor.fetchone()
    conn.close()
    return row['value'] if row else None

def format_money(amount):
    return f"${int(round(amount)):,}".replace(",", ".")

def add_transaction(description, amount, pct=0.5, trans_type='gasto', user_id=None):
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
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
    
    cursor.execute("SELECT SUM(debt_amount) as total_gastos FROM transactions WHERE type IN ('gasto', 'saldo_inicial')")
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

def get_detailed_balance():
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    owner_id_str = get_setting('owner_id')
    owner_id = int(owner_id_str) if owner_id_str else None

    # Deuda Angel: Sum of (amount * pct) for purchases paid by Angela (type = 'gasto_angela')
    cursor.execute("SELECT SUM(ABS(debt_amount)) as val FROM transactions WHERE type = 'gasto_angela'")
    r = cursor.fetchone()
    deuda_angel = r['val'] if r and r['val'] is not None else 0.0

    # Abonos Angel: Sum of abonos made by Angel (type = 'abono' AND user_id == owner_id)
    if owner_id:
        cursor.execute("SELECT SUM(ABS(debt_amount)) as val FROM transactions WHERE type = 'abono' AND user_id = ?", (owner_id,))
    else:
        cursor.execute("SELECT 0.0 as val")
    r = cursor.fetchone()
    abonos_angel = r['val'] if r and r['val'] is not None else 0.0

    # Deuda Angela: Sum of debt_amount for purchases paid by Angel (type IN ('gasto', 'saldo_inicial'))
    cursor.execute("SELECT SUM(debt_amount) as val FROM transactions WHERE type IN ('gasto', 'saldo_inicial')")
    r = cursor.fetchone()
    deuda_angela = r['val'] if r and r['val'] is not None else 0.0

    # Abonos Angela: Sum of abonos made by Angela (type = 'abono' AND (user_id != owner_id OR user_id IS NULL))
    if owner_id:
        cursor.execute("SELECT SUM(ABS(debt_amount)) as val FROM transactions WHERE type = 'abono' AND (user_id != ? OR user_id IS NULL)", (owner_id,))
    else:
        cursor.execute("SELECT SUM(ABS(debt_amount)) as val FROM transactions WHERE type = 'abono'")
    r = cursor.fetchone()
    abonos_angela = r['val'] if r and r['val'] is not None else 0.0

    total_angel_num = abonos_angel - deuda_angel
    total_angela_num = abonos_angela - deuda_angela

    conn.close()

    return {
        'deuda_angel': deuda_angel,
        'abonos_angel': abonos_angel,
        'total_angel_num': total_angel_num,
        'deuda_angela': deuda_angela,
        'abonos_angela': abonos_angela,
        'total_angela_num': total_angela_num
    }

def get_recent_transactions(limit=10):
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM transactions ORDER BY id DESC LIMIT ?', (limit,))
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def get_all_transactions():
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM transactions ORDER BY id ASC')
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

def reset_all_data():
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM transactions')
    cursor.execute('DELETE FROM sqlite_sequence WHERE name="transactions"')
    conn.commit()
    conn.close()

def export_to_csv():
    txs = get_all_transactions()
    filepath = os.path.join(os.path.dirname(__file__), 'Reporte_Gastos_Angela.csv')
    
    with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(['ID', 'Fecha y Hora', 'Concepto', 'Monto Pagado', 'Porcentaje Angela', 'Monto Deuda Angela', 'Tipo de Registro'])
        
        for t in txs:
            t_type = t['type']
            if t_type == 'gasto':
                tag = "Pagado por ti"
            elif t_type == 'gasto_angela':
                tag = "Pagado por Angela"
            elif t_type == 'abono':
                tag = "Abono / Transferencia Angela"
            else:
                tag = "Saldo Inicial"
                
            writer.writerow([
                t['id'],
                t['timestamp'],
                t['description'],
                int(round(t['amount'])),
                f"{int(t['pct']*100)}%",
                int(round(t['debt_amount'])),
                tag
            ])
            
    return filepath

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully.")
