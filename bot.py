import os
import re
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from dotenv import load_dotenv
import database as db

load_dotenv()

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '8616750364:AAEOr-8exqfgoAX5-dMmP2Kp7ZZOB4P9ZmE')

bot = telebot.TeleBot(TOKEN, parse_mode='Markdown')

# Initialize DB
db.init_db()

# Lightweight HTTP Health Check Server for Render Free Tier ($0/month)
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"OK - Bot Telegram Yiyipipo is running 24/7!")
    
    def log_message(self, format, *args):
        pass # Silence HTTP logs

def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    try:
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        print(f"Health check server listening on port {port}")
        server.serve_forever()
    except Exception as e:
        print(f"Health server error: {e}")

# Run health server in background thread for Render
threading.Thread(target=start_health_server, daemon=True).start()

def format_money(val):
    return f"${int(round(val)):,}".replace(",", ".")

def ensure_owner(user_id):
    owner = db.get_setting('owner_id')
    if not owner:
        db.set_setting('owner_id', user_id)
        return user_id
    return int(owner)

@bot.message_handler(commands=['start', 'help', 'ayuda'])
@bot.message_handler(func=lambda msg: msg.text and msg.text.strip().lower() in ['ayuda', '/ayuda', 'help', '/help'])
def send_welcome(message):
    ensure_owner(message.from_user.id)
    welcome_text = (
        "👋 *¡Hola! Soy tu Asistente de Gastos Compartidos con Angela.*\n\n"
        "Identifico automáticamente quién escribe en el chat para registrar el gasto correctamente.\n\n"
        "📌 *¿Cómo registrar un gasto?*\n"
        "• Escribe el concepto y el monto: `super 45000` o `luz 30000` (por defecto 50%).\n"
        "• El bot detecta si escribes tú o Angela y asigna a quién le corresponde.\n"
        "• Si es 100% de la otra persona: `plancha 40000 100%`.\n\n"
        "📌 *¿Cómo registrar un abono / transferencia?*\n"
        "• Escribe: `abono 50000` o `me pagó 30000`.\n\n"
        "⚙️ *Comandos disponibles:*\n"
        "• /saldo (o /balance) - Ver el saldo acumulado en tiempo real.\n"
        "• /historial - Lista los últimos movimientos.\n"
        "• /wsp - Genera el texto limpio para copiar y enviar por WhatsApp.\n"
        "• /excel - Exporta y descarga el reporte en formato Excel/CSV.\n"
        "• /borrar - Elimina el último movimiento (o `/borrar ID` para uno específico).\n"
        "• /reiniciar - Borra todas las transacciones y vuelve la cuenta a $0.\n"
        "• /saldo_inicial - Ajusta el saldo inicial acumulado (ejemplo: `/saldo_inicial 659308`).\n"
        "• /ayuda - Muestra este menú de instrucciones."
    )
    bot.send_message(message.chat.id, welcome_text)

@bot.message_handler(commands=['balance', 'saldo'])
def show_balance(message):
    ensure_owner(message.from_user.id)
    b = db.get_balance()
    total = b['total_debt']
    
    if total >= 0:
        status_line = f"💰 *Angela te debe actualmente:* `{format_money(total)}`"
    else:
        status_line = f"🔴 *Tú le debes a Angela:* `{format_money(abs(total))}`"

    msg = (
        "📊 *RESUMEN DE CUENTAS ACTUAL*\n"
        "────────────────────\n"
        f"{status_line}\n"
        "────────────────────\n"
        f"• Deuda acumulada por tus compras: `{format_money(b['total_gastos_deuda'])}`\n"
        f"• Deuda tuya por compras de Angela: `{format_money(b['total_angela_deuda'])}`\n"
        f"• Abonos recibidos de Angela: `{format_money(b['total_abonos'])}`"
    )
    bot.send_message(message.chat.id, msg)

@bot.message_handler(commands=['historial'])
def show_history(message):
    ensure_owner(message.from_user.id)
    txs = db.get_recent_transactions(10)
    if not txs:
        bot.send_message(message.chat.id, "📜 No hay movimientos registrados aún.")
        return
    
    lines = ["📜 *ÚLTIMOS 10 MOVIMIENTOS:*\n"]
    for t in txs:
        t_type = t['type']
        t_id = t['id']
        pct_str = f" ({int(t['pct']*100)}%)" if t_type in ['gasto', 'gasto_angela'] else ""
        
        if t_type == 'gasto':
            tag = "🟢 Pagaste tú"
        elif t_type == 'gasto_angela':
            tag = "🔴 Pagó Angela"
        elif t_type == 'abono':
            tag = "💵 Abono Angela"
        else:
            tag = "⚙️ Saldo inicial"
            
        lines.append(f"• *#{t_id}* | {tag}: *{t['description']}* - `{format_money(t['amount'])}`{pct_str} -> Impacto saldo: `{format_money(t['debt_amount'])}`")
    
    lines.append("\n💡 _Para borrar el último gasto escribe `/borrar` (o `/borrar ID` para uno específico)_")
    bot.send_message(message.chat.id, "\n".join(lines))

@bot.message_handler(commands=['borrar', 'undo'])
def delete_handler(message):
    ensure_owner(message.from_user.id)
    parts = message.text.split()
    
    if len(parts) == 1:
        deleted = db.delete_last_transaction()
        if deleted:
            b = db.get_balance()
            bot.send_message(message.chat.id, f"🗑️ *Última transacción (#{deleted['id']}) borrada:* '{deleted['description']}' por `{format_money(deleted['amount'])}`.\n\n💰 *Nuevo saldo:* `{format_money(b['total_debt'])}`")
        else:
            bot.send_message(message.chat.id, "❌ No hay transacciones para borrar.")
        return

    if len(parts) >= 2 and parts[1].isdigit():
        t_id = int(parts[1])
        deleted = db.delete_transaction(t_id)
        if deleted:
            b = db.get_balance()
            bot.send_message(message.chat.id, f"🗑️ *Transacción #{deleted['id']} borrada:* '{deleted['description']}'.\n\n💰 *Nuevo saldo:* `{format_money(b['total_debt'])}`")
        else:
            bot.send_message(message.chat.id, f"❌ No se encontró ninguna transacción con el ID #{t_id}.")
    else:
        bot.send_message(message.chat.id, "⚠️ Usa `/borrar` para borrar el último registro, o `/borrar ID` (ejemplo: `/borrar 5`).")

@bot.message_handler(commands=['reiniciar', 'reset'])
def reset_handler(message):
    ensure_owner(message.from_user.id)
    db.reset_all_data()
    bot.send_message(message.chat.id, "🧹 *¡Todos los datos han sido reiniciados a $0 con éxito!* La cuenta está limpia para comenzar de nuevo.")

@bot.message_handler(commands=['excel', 'exportar', 'csv'])
def export_excel_handler(message):
    ensure_owner(message.from_user.id)
    filepath = db.export_to_csv()
    if os.path.exists(filepath):
        bot.send_message(message.chat.id, "📊 *Aquí tienes la planilla Excel con todos los movimientos ordenados:*")
        with open(filepath, 'rb') as f:
            bot.send_document(message.chat.id, f)
    else:
        bot.send_message(message.chat.id, "❌ No hay datos para exportar.")

@bot.message_handler(commands=['saldo_inicial'])
def set_initial_balance(message):
    ensure_owner(message.from_user.id)
    text = message.text.replace('/saldo_inicial', '').strip()
    match = re.search(r'\d+', text.replace('.', '').replace('$', ''))
    if match:
        amount = float(match.group(0))
        tx = db.add_transaction("Saldo Inicial Acumulado", amount, pct=1.0, trans_type='saldo_inicial', user_id=message.from_user.id)
        b = db.get_balance()
        bot.send_message(message.chat.id, f"✅ *Saldo inicial registrado:* `{format_money(amount)}`.\n\n💰 *Saldo actual:* `{format_money(b['total_debt'])}`")
    else:
        bot.send_message(message.chat.id, "⚠️ Indica el monto. Ejemplo: `/saldo_inicial 659308`")

@bot.message_handler(commands=['wsp', 'whatsapp'])
def send_whatsapp_summary(message):
    ensure_owner(message.from_user.id)
    b = db.get_balance()
    total = b['total_debt']
    
    if total >= 0:
        wsp_text = (
            f"Hola Angela! Te comparto el resumen actualizado de cuentas:\n\n"
            f"• Gastos tuyos / compartidos acumulados: {format_money(b['total_gastos_deuda'])}\n"
            f"• Descuento por gastos pagados por ti: -{format_money(b['total_angela_deuda'])}\n"
            f"• Abonos realizados: -{format_money(b['total_abonos'])}\n\n"
            f"👉 TOTAL PENDIENTE A TRANSFERIR: {format_money(total)}"
        )
    else:
        wsp_text = (
            f"Hola Angela! Revisé las cuentas acumuladas:\n\n"
            f"👉 Saldo a tu favor: {format_money(abs(total))}"
        )

    msg = f"```\n{wsp_text}\n```"
    bot.send_message(message.chat.id, msg)

@bot.message_handler(func=lambda msg: True)
def process_text_message(message):
    text = message.text.strip().lower()
    user_id = message.from_user.id
    owner_id = ensure_owner(user_id)
    
    is_owner = (user_id == owner_id)
    
    if text.startswith('/'):
        return

    # Check for abono
    if text.startswith('abono') or text.startswith('pago') or 'me pago' in text or 'me pagó' in text:
        match = re.search(r'(\d[\d\.\,]*)', text)
        if match:
            raw_amt = match.group(1).replace('.', '').replace(',', '')
            amount = float(raw_amt)
            tx = db.add_transaction("Abono de Angela", amount, pct=1.0, trans_type='abono', user_id=user_id)
            b = db.get_balance()
            bot.send_message(message.chat.id, f"💵 *Abono registrado:* `{format_money(amount)}`.\n\n💰 *Nuevo saldo que Angela te debe:* `{format_money(b['total_debt'])}`")
            return

    # Force Angela paid if explicitly specified by keyword 'ange' or 'angela'
    explicit_angela = text.startswith('ange') or text.startswith('angela')
    
    # Check for numbers
    match = re.search(r'(\d[\d\.\,]*)', text)
    if match:
        raw_amt = match.group(1).replace('.', '').replace(',', '')
        amount = float(raw_amt)
        clean_desc = text.replace('ange', '').replace('angela', '').replace(match.group(1), '').replace('100%', '').replace('100', '').strip() or "Gasto variado"
        pct = 1.0 if ('100%' in text or ' 100' in text or text.endswith('100')) else 0.5
        
        # If message is NOT from owner OR explicitly starts with 'ange' -> Paid by Angela
        if not is_owner or explicit_angela:
            tx = db.add_transaction(clean_desc.capitalize(), amount, pct=pct, trans_type='gasto_angela', user_id=user_id)
            b = db.get_balance()
            pct_str = " (100% tu deuda)" if pct == 1.0 else " (50% tu parte)"
            bot.send_message(message.chat.id, f"🔴 *Gasto de Angela registrado:* '{clean_desc.capitalize()}' por `{format_money(amount)}`{pct_str}.\n\n💰 *Nuevo saldo que Angela te debe:* `{format_money(b['total_debt'])}`")
        else:
            # Paid by Owner (Angel)
            tx = db.add_transaction(clean_desc.capitalize(), amount, pct=pct, trans_type='gasto', user_id=user_id)
            b = db.get_balance()
            pct_str = " (100% Angela)" if pct == 1.0 else " (50% Angela)"
            bot.send_message(message.chat.id, f"🟢 *Gasto registrado:* '{clean_desc.capitalize()}' por `{format_money(amount)}`{pct_str}.\n💡 *Angela aporta:* `{format_money(tx['debt_amount'])}`.\n\n💰 *Nuevo saldo que Angela te debe:* `{format_money(b['total_debt'])}`")
        return

    bot.send_message(message.chat.id, "💡 *No entendí la cifra.* Para registrar un gasto escribe el nombre y el monto (ejemplo: `super 45000` o `abono 20000`).\n\nUsa /ayuda para ver las instrucciones.")

if __name__ == '__main__':
    print("Bot de Cuentas Iniciado y Escuchando en Telegram...")
    bot.infinity_polling()
