import os, json, requests, re, time
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask
import telebot
from telebot.types import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from bs4 import BeautifulSoup
import traceback

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8776730597:AAGr9XbnyixajCnSa_AlyTQDHUjodyQmdto")
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

BYPASS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "uz-UZ,uz;q=0.9,ru-RU;q=0.8,ru;q=0.7,en-US;q=0.6,en;q=0.5",
    "Referer": "https://etender.uzex.uz/",
    "Upgrade-Insecure-Requests": "1",
}

def fetch_with_curl_cffi(url):
    try:
        from curl_cffi import requests as c_requests
        r = c_requests.get(url, impersonate="chrome122", headers=BYPASS_HEADERS, timeout=20)
        if r.status_code == 200 and len(r.text) > 1000:
            if "Attention Required" in r.text or "cf-challenge" in r.text or "Checking your browser" in r.text:
                return None
            return r.text
    except Exception:
        pass
    return None

def fetch_with_requests(url, is_json=False):
    try:
        headers = BYPASS_HEADERS.copy()
        if is_json:
            headers["Accept"] = "application/json"
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200 and len(r.text) > 500:
            if "Attention Required" in r.text[:2000] or "cf-challenge" in r.text[:2000]:
                return None
            return r.text
    except Exception:
        pass
    return None

def parse_tenders_from_json(text):
    tenders=[]
    try:
        j = json.loads(text) if isinstance(text, str) else text
        items = []
        if isinstance(j, list):
            items = j
        elif isinstance(j, dict):
            items = j.get('content') or j.get('data') or j.get('items') or j.get('result') or j.get('lots') or []
            if isinstance(items, dict):
                items = items.get('content') or items.get('items') or []
        for it in items[:20]:
            if not isinstance(it, dict):
                continue
            name = it.get('title') or it.get('name') or it.get('lotName') or it.get('productName') or it.get('subject') or it.get('description') or ''
            if len(name.strip()) < 15:
                continue
            lot_id = str(it.get('id') or it.get('lotId') or it.get('lotNumber') or it.get('number') or '')[:20]
            budget = it.get('budget') or it.get('amount') or it.get('price') or it.get('startPrice') or 0
            try:
                budget = int(float(str(budget).replace(' ','').replace(',','')))
            except:
                budget = 0
            region = it.get('region') or it.get('regionName') or it.get('customerRegion') or 'Toshkent sh'
            link = it.get('url') or f"https://etender.uzex.uz/lot/{lot_id}"
            if not link.startswith('http'):
                link = f"https://etender.uzex.uz{link}"
            tenders.append({
                "id": lot_id or f"{int(time.time())%100000}",
                "lot_number": lot_id,
                "name": name[:280],
                "budget": budget,
                "region": str(region)[:50],
                "deadline_date": (datetime.now()+timedelta(days=3)).strftime("%d.%m.%Y"),
                "link": link
            })
    except Exception:
        pass
    return tenders

def parse_tenders_from_html(html):
    tenders=[]
    try:
        soup = BeautifulSoup(html, 'html.parser')
        for a in soup.find_all('a', href=True):
            txt = a.get_text(strip=True)
            href = a['href']
            if 30 < len(txt) < 300 and ('lot' in href.lower() or len(txt) > 60):
                if not href.startswith('http'):
                    href = f"https://etender.uzex.uz{href}" if href.startswith('/') else f"https://etender.uzex.uz/{href}"
                lot_num = re.search(r'(\d{4,})', href)
                lot_num = lot_num.group(1) if lot_num else str(int(time.time())%1000000)
                tenders.append({
                    "id": lot_num,
                    "lot_number": lot_num,
                    "name": txt[:280],
                    "budget": 0,
                    "region": "Toshkent sh",
                    "deadline_date": (datetime.now()+timedelta(days=3)).strftime("%d.%m.%Y"),
                    "link": href
                })
                if len(tenders) >= 12:
                    break
    except Exception:
        pass
    return tenders

def fetch_real_tenders():
    open_apis = [
        "https://etender.uzex.uz/api/frontend/lots?size=30&page=0&sort=id,desc",
        "https://etender.uzex.uz/api/lots?size=30&page=0",
        "https://exarid.uzex.uz/api/lots?size=20",
    ]
    for url in open_apis:
        html = fetch_with_curl_cffi(url)
        if not html:
            html = fetch_with_requests(url, is_json=True)
        if html:
            tenders = parse_tenders_from_json(html)
            if tenders:
                return tenders
    html_pages = [
        "https://etender.uzex.uz/lots",
        "https://exarid.uzex.uz/",
    ]
    for url in html_pages:
        html = fetch_with_curl_cffi(url)
        if not html:
            html = fetch_with_requests(url)
        if html:
            tenders = parse_tenders_from_html(html)
            if tenders:
                return tenders
    return []

def filter_tenders(tenders,f):
    if not tenders:
        return tenders
    res=tenders
    if f.get("regions"):
        res=[t for t in res if any(r.lower() in t["region"].lower() or r.lower() in t["name"].lower() for r in f["regions"])]
    if f.get("categories"):
        res=[t for t in res if any(c.lower() in t["name"].lower() for c in f["categories"])]
    return res

@bot.message_handler(commands=['start'])
def start(m):
    get_or_create(m.from_user.id, m.from_user.username or "")
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📍 Viloyat"), KeyboardButton("💼 Kategoriya"))
    kb.add(KeyboardButton("🔎 Mening tenderlarim"))
    kb.add(KeyboardButton("⚙️ Filtrim"))
    bot.send_message(m.chat.id, 
        f"👋 Salom, {m.from_user.first_name}!\n\n"
        f"Men tender botman. Sizga O'zbekiston bo'yicha eng yangi tenderlarni topib beraman.\n\n"
        f"📍 Viloyatingizni va 💼 kategoriyani tanlang, so'ng 🔎 Mening tenderlarim ni bosing.\n\n"
        f"Har kuni yangi imkoniyatlarni o'tkazib yubormang!",
        reply_markup=kb)

@bot.message_handler(func=lambda m: m.text=="📍 Viloyat")
def ask_reg(m):
    users=load_users(); sel=users.get(str(m.from_user.id), {}).get("filters",{}).get("regions",[])
    kb=InlineKeyboardMarkup(row_width=2)
    for it in VILOYATLAR:
        kb.add(InlineKeyboardButton(f"{'✅' if it in sel else '⬜'} {it}", callback_data=f"REG:{it}"))
    kb.add(InlineKeyboardButton("💾 Saqlash", callback_data="REG:SAVE"))
    bot.send_message(m.chat.id, "Viloyat tanlang:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text=="💼 Kategoriya")
def ask_cat(m):
    users=load_users(); sel=users.get(str(m.from_user.id), {}).get("filters",{}).get("categories",[])
    kb=InlineKeyboardMarkup(row_width=2)
    for it in KATEGORIYALAR:
        kb.add(InlineKeyboardButton(f"{'✅' if it in sel else '⬜'} {it}", callback_data=f"CAT:{it}"))
    kb.add(InlineKeyboardButton("💾 Saqlash", callback_data="CAT:SAVE"))
    bot.send_message(m.chat.id, "Kategoriya tanlang:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: True)
def toggle(c):
    users=load_users(); uid=str(c.from_user.id); pref,val=c.data.split(":",1); key="regions" if pref=="REG" else "categories"
    if uid not in users: get_or_create(c.from_user.id); users=load_users()
    if val=="SAVE":
        bot.edit_message_text(f"✅ Saqlandi: {', '.join(users[uid]['filters'][key]) or 'Hammasi'}", c.message.chat.id, c.message.message_id)
        bot.answer_callback_query(c.id, "Saqlandi!")
        return
    sel=users[uid]["filters"][key]
    if val in sel: sel.remove(val)
    else: sel.append(val)
    users[uid]["filters"][key]=sel; save_users(users)
    kb=InlineKeyboardMarkup(row_width=2)
    items=VILOYATLAR if pref=="REG" else KATEGORIYALAR
    for it in items:
        kb.add(InlineKeyboardButton(f"{'✅' if it in sel else '⬜'} {it}", callback_data=f"{pref}:{it}"))
    kb.add(InlineKeyboardButton("💾 Saqlash", callback_data=f"{pref}:SAVE"))
    try: bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=kb)
    except: pass
    bot.answer_callback_query(c.id, f"{len(sel)} ta")

@bot.message_handler(func=lambda m: m.text=="⚙️ Filtrim")
def show_f(m):
    f=load_users().get(str(m.from_user.id), {}).get("filters",{})
    bot.send_message(m.chat.id, f"📍 Viloyatlar: {', '.join(f.get('regions',[])) or 'Hammasi'}\n💼 Kategoriyalar: {', '.join(f.get('categories',[])) or 'Hammasi'}")

@bot.message_handler(func=lambda m: m.text=="🔎 Mening tenderlarim")
def my_tenders(m):
    bot.send_message(m.chat.id, "⏳ Tenderlar qidirilmoqda...")
    try:
        all_t = fetch_real_tenders()
        f=load_users().get(str(m.from_user.id), {}).get("filters",{})
        filtered=filter_tenders(all_t,f)
        if not filtered:
            bot.send_message(m.chat.id, "😔 Hozircha sizning filtr bo'yicha mos tenderlar topilmadi. Filtrni o'zgartirib ko'ring yoki keyinroq qayta urinib ko'ring.")
            return
        text=f"🔥 {len(filtered)} ta yangi tender:\n\n"
        for t in filtered[:10]:
            budget_txt = f"{t['budget']:,} so'm" if t['budget'] else "Byudjet saytda ko'rsatilgan"
            text+=f"📦 {t['name']}\n🔢 {t['lot_number']}\n📍 {t['region']} | 💰 {budget_txt}\n⏰ {t['deadline_date']}\n🔗 {t['link']}\n\n"
        bot.send_message(m.chat.id, text, disable_web_page_preview=True)
    except Exception as e:
        traceback.print_exc()
        bot.send_message(m.chat.id, f"❌ Hozircha ma'lumotlarni olib bo'lmadi, birozdan so'ng qayta urinib ko'ring.")

print("Tender bot ishga tushdi")
bot.infinity_polling()
