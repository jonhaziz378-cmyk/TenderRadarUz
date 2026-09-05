import os, json, requests
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask
import telebot
from telebot.types import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8776730597:AAFF8PMTN_qvUdf-b-7Js4s8uGm_7B8PoME")
DB_FILE = "users.json"
VILOYATLAR = ["Toshkent sh", "Toshkent vil", "Samarqand", "Buxoro", "Andijon", "Farg'ona", "Namangan", "Qashqadaryo", "Surxondaryo", "Xorazm", "Navoiy", "Jizzax", "Sirdaryo", "Qoraqalpog'iston"]
KATEGORIYALAR = ["Qurilish", "IT kompyuter", "Tibbiyot dori", "Oziq-ovqat", "Mebel jihoz", "Transport", "Kantselyariya"]

bot = telebot.TeleBot(BOT_TOKEN)

flask_app = Flask(__name__)
@flask_app.route('/')
def home(): return f"Bot alive {datetime.now()}"
@flask_app.route('/health')
def health(): return "OK"
def run_flask():
    port=int(os.environ.get('PORT',10000))
    flask_app.run(host='0.0.0.0',port=port)
Thread(target=run_flask,daemon=True).start()

def load_users():
    if not os.path.exists(DB_FILE): return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return {}
def save_users(u):
    with open(DB_FILE, "w", encoding="utf-8") as f: json.dump(u, f, ensure_ascii=False, indent=2)
def get_or_create(uid, username=""):
    users=load_users(); suid=str(uid)
    if suid not in users:
        users[suid]={"id":uid,"username":username,"start_date":datetime.now().isoformat(),"is_paid":False,"filters":{"regions":[],"categories":[]},"sent_ids":[]}
        save_users(users)
    return users[suid]

@bot.message_handler(commands=['start'])
def start(m):
    get_or_create(m.from_user.id, m.from_user.username or "")
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📍 Viloyat"), KeyboardButton("💼 Kategoriya"))
    kb.add(KeyboardButton("🔎 Mening tenderlarim"))
    kb.add(KeyboardButton("⚙️ Filtrim"))
    bot.send_message(m.chat.id, f"👋 Salom, {m.from_user.first_name}!\n\nTender bot ishga tushdi ✅\nViloyat va kategoriyani tanlang.", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text=="📍 Viloyat")
def ask_reg(m):
    users=load_users(); sel=users.get(str(m.from_user.id), {}).get("filters",{}).get("regions",[])
    kb=InlineKeyboardMarkup(row_width=2)
    for it in VILOYATLAR:
        mark="✅" if it in sel else "⬜"
        kb.add(InlineKeyboardButton(f"{mark} {it}", callback_data=f"REG:{it}"))
    kb.add(InlineKeyboardButton("💾 Saqlash", callback_data="REG:SAVE"))
    bot.send_message(m.chat.id, "Viloyat tanlang:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text=="💼 Kategoriya")
def ask_cat(m):
    users=load_users(); sel=users.get(str(m.from_user.id), {}).get("filters",{}).get("categories",[])
    kb=InlineKeyboardMarkup(row_width=2)
    for it in KATEGORIYALAR:
        mark="✅" if it in sel else "⬜"
        kb.add(InlineKeyboardButton(f"{mark} {it}", callback_data=f"CAT:{it}"))
    kb.add(InlineKeyboardButton("💾 Saqlash", callback_data="CAT:SAVE"))
    bot.send_message(m.chat.id, "Kategoriya tanlang:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: True)
def toggle(c):
    users=load_users(); uid=str(c.from_user.id); pref,val=c.data.split(":",1); key="regions" if pref=="REG" else "categories"
    if uid not in users: get_or_create(c.from_user.id); users=load_users()
    if val=="SAVE":
        bot.edit_message_text(f"Saqlandi: {', '.join(users[uid]['filters'][key]) or 'Hammasi'}", c.message.chat.id, c.message.message_id)
        bot.answer_callback_query(c.id, "Saqlandi!")
        return
    sel=users[uid]["filters"][key]
    if val in sel: sel.remove(val)
    else: sel.append(val)
    users[uid]["filters"][key]=sel; save_users(users)
    kb=InlineKeyboardMarkup(row_width=2)
    items=VILOYATLAR if pref=="REG" else KATEGORIYALAR
    for it in items:
        mark="✅" if it in sel else "⬜"
        kb.add(InlineKeyboardButton(f"{mark} {it}", callback_data=f"{pref}:{it}"))
    kb.add(InlineKeyboardButton("💾 Saqlash", callback_data=f"{pref}:SAVE"))
    try: bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=kb)
    except: pass
    bot.answer_callback_query(c.id, f"{len(sel)} ta")

@bot.message_handler(func=lambda m: m.text=="⚙️ Filtrim")
def show_f(m):
    f=load_users()[str(m.from_user.id)]["filters"]
    bot.send_message(m.chat.id, f"📍 {', '.join(f['regions']) or 'Hammasi'}\n💼 {', '.join(f['categories']) or 'Hammasi'}")

@bot.message_handler(func=lambda m: m.text=="🔎 Mening tenderlarim")
def my_tenders(m):
    bot.send_message(m.chat.id, "🔥 1 ta tender topildi:\n\n📦 Kompyuter jihozlari xaridi\n🔢 Lot: 12345\n📍 Toshkent sh | 💰 50,000,000 so'm\n⏰ Tugash: 10.09.2026 | 5 kun qoldi\n🔗 https://xarid.uzex.uz/lot/12345")

print("Tender bot ishga tushdi - telebot")
bot.infinity_polling()
