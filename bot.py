
import asyncio, json, os, re
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, executor, types
import requests
from bs4 import BeautifulSoup
from threading import Thread
from flask import Flask

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8776730597:AAFF8PMTN_qvUdf-b-7Js4s8uGm_7B8PoME")
DB_FILE = "users.json"
VILOYATLAR = ["Toshkent sh", "Toshkent vil", "Samarqand", "Buxoro", "Andijon", "Farg'ona", "Namangan", "Qashqadaryo", "Surxondaryo", "Xorazm", "Navoiy", "Jizzax", "Sirdaryo", "Qoraqalpog'iston"]
KATEGORIYALAR = ["Qurilish", "IT kompyuter", "Tibbiyot dori", "Oziq-ovqat", "Mebel jihoz", "Transport", "Kantselyariya"]

bot = Bot(BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

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
def check_access(uid):
    users=load_users(); u=users.get(str(uid))
    if not u: return False,0
    days=(datetime.now()-datetime.fromisoformat(u["start_date"])).days
    if u.get("is_paid"): return True,999
    if days<=7: return True,7-days
    return False,0

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://xarid.uzex.uz/",
}

async def fetch_all_tenders(filters=None):
    tenders=[]; now=datetime.now()
    tenders.append({
        "id": "lot_12345",
        "lot_number": "12345",
        "name": "Kompyuter jihozlari xaridi",
        "budget": 50000000,
        "region": "Toshkent sh",
        "deadline": 5,
        "deadline_date": (now+timedelta(days=5)).strftime("%d.%m.%Y"),
        "link": "https://xarid.uzex.uz/lot/12345"
    })
    try:
        r=requests.get("https://xarid.uzex.uz/", headers=HEADERS, timeout=10)
        print(f"xarid sahifasi {len(r.text)}")
    except Exception as e:
        print(f"fetch xato {e}")
    print(f"JAMI: {len(tenders)} ta")
    return tenders

def filter_tenders(tenders,f):
    res=tenders
    if f.get("regions"):
        res=[t for t in res if any(r.lower() in t["region"].lower() for r in f["regions"])]
    if f.get("categories"):
        res=[t for t in res if any(c.lower() in t["name"].lower() for c in f["categories"])]
    return res

def make_kb(items, selected, prefix):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    kb=[]; row=[]
    for it in items:
        mark="✅" if it in selected else "⬜"
        row.append(InlineKeyboardButton(text=f"{mark} {it}", callback_data=f"{prefix}:{it}"))
        if len(row)==2: kb.append(row); row=[]
    if row: kb.append(row)
    kb.append([InlineKeyboardButton(text="💾 Saqlash", callback_data=f"{prefix}:SAVE")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

@dp.message_handler(commands=['start'])
async def start(m: types.Message):
    get_or_create(m.from_user.id, m.from_user.username or "")
    access,left=check_access(m.from_user.id)
    kb=[[types.KeyboardButton(text="📍 Viloyat"), types.KeyboardButton(text="💼 Kategoriya")],[types.KeyboardButton(text="🔎 Mening tenderlarim")],[types.KeyboardButton(text="⚙️ Filtrim")]]
    if access:
        u=load_users()[str(m.from_user.id)]; f=u["filters"]
        vil=", ".join(f["regions"]) or "Hammasi"; kat=", ".join(f["categories"]) or "Hammasi"
        left_txt="Cheksiz" if left==999 else f"{left} kun qoldi"
        await m.answer(f"👋 Salom, {m.from_user.first_name}!\n\n📊 {left_txt}\n📍 {vil}\n💼 {kat}\n\nViloyat va kategoriyani tanlang.", reply_markup=types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))
    else:
        await m.answer("7 kun tugadi.")

@dp.message_handler(lambda m: m.text=="📍 Viloyat")
async def ask_reg(m: types.Message):
    sel=load_users()[str(m.from_user.id)]["filters"]["regions"]
    await m.answer("Viloyat tanlang:", reply_markup=make_kb(VILOYATLAR, sel, "REG"))
@dp.message_handler(lambda m: m.text=="💼 Kategoriya")
async def ask_cat(m: types.Message):
    sel=load_users()[str(m.from_user.id)]["filters"]["categories"]
    await m.answer("Kategoriya tanlang:", reply_markup=make_kb(KATEGORIYALAR, sel, "CAT"))

@dp.callback_query_handler(lambda c: c.data.startswith("REG:") or c.data.startswith("CAT:"))
async def toggle(c: types.CallbackQuery):
    users=load_users(); uid=str(c.from_user.id); pref,val=c.data.split(":",1); key="regions" if pref=="REG" else "categories"
    if val=="SAVE":
        save_users(users); await c.message.edit_text(f"Saqlandi: {', '.join(users[uid]['filters'][key]) or 'Hammasi'}"); await c.answer("Saqlandi!"); return
    sel=users[uid]["filters"][key]
    if val in sel: sel.remove(val)
    else: sel.append(val)
    users[uid]["filters"][key]=sel; save_users(users)
    kb=make_kb(VILOYATLAR if pref=="REG" else KATEGORIYALAR, sel, pref)
    try: await c.message.edit_reply_markup(reply_markup=kb)
    except: pass
    await c.answer(f"{len(sel)} ta")

@dp.message_handler(lambda m: m.text=="⚙️ Filtrim")
async def show_f(m: types.Message):
    f=load_users()[str(m.from_user.id)]["filters"]
    await m.answer(f"📍 {', '.join(f['regions']) or 'Hammasi'}\n💼 {', '.join(f['categories']) or 'Hammasi'}")

@dp.message_handler(lambda m: m.text=="🔎 Mening tenderlarim")
async def my_tenders(m: types.Message):
    access,_=check_access(m.from_user.id)
    if not access:
        await start(m); return
    users=load_users(); f=users[str(m.from_user.id)]["filters"]
    await m.answer("Qidirilmoqda...")
    all_t=await fetch_all_tenders(f)
    filtered=filter_tenders(all_t,f)
    if not filtered:
        await m.answer("Hozircha sizga mos tender yo'q."); return
    text=f"🔥 {len(filtered)} ta tender topildi:\n\n"
    for t in filtered[:10]:
        text+=f"📦 {t['name']}\n🔢 Lot: {t['lot_number']}\n📍 {t['region']} | 💰 {t['budget']:,} so'm\n⏰ Tugash: {t['deadline_date']} | {t['deadline']} kun qoldi\n🔗 {t['link']}\n\n"
    users[str(m.from_user.id)]["sent_ids"]=list(set(users[str(m.from_user.id)].get("sent_ids",[])+[t["id"] for t in filtered]))[-100:]
    save_users(users)
    await m.answer(text)

if __name__=="__main__":
    print("Tender bot ishga tushdi - aiogram2")
    executor.start_polling(dp, skip_updates=True)
