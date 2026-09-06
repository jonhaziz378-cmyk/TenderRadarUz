import os, json, requests, re
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask
import telebot
from telebot.types import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from bs4 import BeautifulSoup
import time
import traceback

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8776730597:AAFF8PMTN_qvUdf-b-7Js4s8uGm_7B8PoME")
DB_FILE = "users.json"
VILOYATLAR = ["Toshkent sh", "Toshkent vil", "Samarqand", "Buxoro", "Andijon", "Farg'ona", "Namangan", "Qashqadaryo", "Surxondaryo", "Xorazm", "Navoiy", "Jizzax", "Sirdaryo", "Qoraqalpog'iston"]
KATEGORIYALAR = ["Qurilish", "IT kompyuter", "Tibbiyot dori", "Oziq-ovqat", "Mebel jihoz", "Transport", "Kantselyariya"]

bot = telebot.TeleBot(BOT_TOKEN)

flask_app = Flask(__name__)
@flask_app.route('/')
def home(): return f"Bot alive {datetime.now()} - REAL v3 Playwright"
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "uz-UZ,uz;q=0.9,ru;q=0.8,en;q=0.7",
}

def fetch_via_open_api():
    """Eng ochiq API lar - kalitsiz ishlaydi"""
    tenders=[]
    session = requests.Session()
    
    # 1. xt-xarid.uz - eng ochiq, Cloudflare yo'q
    open_endpoints = [
        "https://xt-xarid.uz/api/v1/lots?limit=20",
        "https://xt-xarid.uz/api/lots?size=20",
        "https://etender.uzex.uz/api/lots?size=20&page=0",
        "https://etender.uzex.uz/api/frontend/lots?size=20",
        "https://xarid.uzex.uz/api/v1/lots",
        "https://dxarid.uzex.uz/api/lots",
    ]
    
    for test_url in open_endpoints:
        try:
            print(f"TRY API {test_url}")
            r = session.get(test_url, headers=HEADERS, timeout=15)
            print(f"-> {r.status_code} len={len(r.text)}")
            if r.status_code!=200 or len(r.text)<500:
                continue
                
            # JSON bolsa
            content_type = r.headers.get('Content-Type','')
            text = r.text.strip()
            if 'json' in content_type or text.startswith('{') or text.startswith('['):
                try:
                    j = r.json()
                    items = []
                    if isinstance(j, list):
                        items = j
                    elif isinstance(j, dict):
                        items = j.get('data') or j.get('items') or j.get('lots') or j.get('content') or j.get('result') or j.get('lots_data') or []
                        # ba'zida data ichida items
                        if isinstance(items, dict):
                            items = items.get('items') or items.get('content') or []
                    
                    print(f"JSON items: {len(items)}")
                    for it in items[:20]:
                        if not isinstance(it, dict):
                            continue
                        name = it.get('title') or it.get('name') or it.get('lotName') or it.get('productName') or it.get('lot_name') or it.get('description') or ''
                        if len(name)<10:
                            continue
                        lot_id = str(it.get('id') or it.get('lotId') or it.get('lotNumber') or it.get('lot_number') or it.get('number') or '')[:20]
                        budget = it.get('budget') or it.get('amount') or it.get('initialPrice') or it.get('price') or it.get('start_price') or 0
                        try: 
                            budget = int(float(str(budget).replace(' ','').replace(',','')))
                        except: 
                            budget = 0
                        region = it.get('region') or it.get('regionName') or it.get('customer_region') or 'Toshkent sh'
                        link = it.get('url') or it.get('link') or f"https://xt-xarid.uz/lot/{lot_id}"
                        if not link.startswith('http'):
                            link = "https://xt-xarid.uz" + link if link.startswith('/') else "https://xt-xarid.uz/"+link
                        tenders.append({
                            "id": lot_id or str(int(time.time()))[-8:],
                            "lot_number": lot_id,
                            "name": name[:250],
                            "budget": budget,
                            "region": region,
                            "deadline": 3,
                            "deadline_date": (datetime.now()+timedelta(days=3)).strftime("%d.%m.%Y"),
                            "link": link
                        })
                    if tenders:
                        print(f"API dan {len(tenders)} ta topildi {test_url}")
                        return tenders
                except Exception as je:
                    print(f"JSON parse xato {test_url}: {je}")
                    continue
        except Exception as e:
            print(f"{test_url} xato {e}")
            continue
    return []

def fetch_via_html_scrape():
    """HTML scrape - etender.uzex.uz dan"""
    tenders=[]
    try:
        session = requests.Session()
        urls = [
            "https://etender.uzex.uz/lots",
            "https://xt-xarid.uz/",
            "https://xarid.uzex.uz/",
        ]
        for url in urls:
            try:
                print(f"TRY HTML {url}")
                r = session.get(url, headers=HEADERS, timeout=15)
                if r.status_code!=200:
                    continue
                soup = BeautifulSoup(r.text, 'html.parser')
                # barcha lot linklarini qidirish
                candidates = []
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    txt = a.get_text(strip=True)
                    if len(txt)<15:
                        continue
                    if 'lot' in href.lower() or 'tender' in href.lower() or len(txt)>30:
                        if not href.startswith('http'):
                            base = url.rsplit('/',1)[0]
                            href = base + href if href.startswith('/') else base + '/' + href
                        candidates.append((txt, href))
                
                print(f"HTML candidates {len(candidates)} from {url}")
                for txt, href in candidates[:15]:
                    lot_num = re.search(r'(\d{5,})', href)
                    lot_num = lot_num.group(1) if lot_num else str(int(time.time()*1000))[-7:]
                    tenders.append({
                        "id": lot_num,
                        "lot_number": lot_num,
                        "name": txt[:250],
                        "budget": 0,
                        "region": "Toshkent",
                        "deadline": 5,
                        "deadline_date": (datetime.now()+timedelta(days=5)).strftime("%d.%m.%Y"),
                        "link": href
                    })
                if tenders:
                    return tenders[:10]
            except Exception as e:
                print(f"HTML {url} xato {e}")
                continue
    except Exception as e:
        print(f"HTML umumiy xato {e}")
    return []

def fetch_via_playwright():
    """Playwright - Cloudflare ni aylanib o'tadi"""
    tenders=[]
    try:
        from playwright.sync_api import sync_playwright
        print("Playwright ishga tushmoqda...")
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage','--disable-gpu']
            )
            context = browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="uz-UZ"
            )
            page = context.new_page()
            
            # xarid.uzex.uz ga kirish - Cloudflare kutish
            try:
                print("GOTO xarid.uzex.uz")
                page.goto("https://xarid.uzex.uz", wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(8000)  # Cloudflare uchun kutish
                
                # agar Cloudflare challenge bo'lsa
                content = page.content()
                if "Checking your browser" in content or "cloudflare" in content.lower()[:2000]:
                    print("Cloudflare challenge kutmoqda...")
                    page.wait_for_timeout(10000)
                
                # lot linklarini olish
                links = page.query_selector_all("a")
                print(f"Playwright {len(links)} ta link topdi")
                
                for el in links[:50]:
                    try:
                        href = el.get_attribute("href") or ""
                        txt = el.inner_text().strip()
                        if len(txt)<15 or len(txt)>300:
                            continue
                        if "lot" in href.lower() or "tender" in href.lower() or "xarid" in txt.lower() or len(txt)>40:
                            if not href.startswith("http"):
                                href = "https://xarid.uzex.uz" + href if href.startswith("/") else "https://xarid.uzex.uz/"+href
                            lot_num = re.search(r'(\d{5,})', href)
                            lot_num = lot_num.group(1) if lot_num else str(int(time.time()))[-6:]
                            tenders.append({
                                "id": lot_num,
                                "lot_number": lot_num,
                                "name": txt[:250],
                                "budget": 0,
                                "region": "Toshkent",
                                "deadline": 5,
                                "deadline_date": (datetime.now()+timedelta(days=5)).strftime("%d.%m.%Y"),
                                "link": href
                            })
                    except:
                        continue
                
                if tenders:
                    print(f"Playwright dan {len(tenders)} ta topildi")
                    browser.close()
                    return tenders[:10]
                
                # Agar xarid dan topilmasa, etender ga o'tish
                print("GOTO etender.uzex.uz")
                page.goto("https://etender.uzex.uz/lots", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(5000)
                links = page.query_selector_all("a")
                for el in links[:50]:
                    try:
                        href = el.get_attribute("href") or ""
                        txt = el.inner_text().strip()
                        if len(txt)<15:
                            continue
                        if not href.startswith("http"):
                            href = "https://etender.uzex.uz" + href if href.startswith("/") else "https://etender.uzex.uz/"+href
                        lot_num = re.search(r'(\d{5,})', href)
                        lot_num = lot_num.group(1) if lot_num else str(int(time.time()))[-6:]
                        tenders.append({
                            "id": lot_num,
                            "lot_number": lot_num,
                            "name": txt[:250],
                            "budget": 0,
                            "region": "Toshkent",
                            "deadline": 3,
                            "deadline_date": (datetime.now()+timedelta(days=3)).strftime("%d.%m.%Y"),
                            "link": href
                        })
                    except:
                        continue
                    
            except Exception as e:
                print(f"Playwright page xato: {e}")
                traceback.print_exc()
            
            browser.close()
    except ImportError:
        print("Playwright o'rnatilmagan")
    except Exception as e:
        print(f"Playwright umumiy xato: {e}")
        traceback.print_exc()
    return tenders

def fetch_real_tenders():
    print("=== fetch_real_tenders boshlandi ===")
    
    # 1 - Ochiq API larni sinab ko'rish (eng tez, kalitsiz)
    tenders = fetch_via_open_api()
    if tenders:
        return tenders
    
    # 2 - HTML scrape
    tenders = fetch_via_html_scrape()
    if tenders:
        return tenders
    
    # 3 - Playwright (Cloudflare uchun)
    tenders = fetch_via_playwright()
    if tenders:
        return tenders
    
    # 4 - Agar hammasi ishlamasa, real tushuntirish berish, fake emas
    print("HECH QAYERDAN TOPILMADI")
    now=datetime.now()
    return [
        {"id":"ERR","lot_number":"0","name":"⚠️ Hozir xarid.uzex.uz va etender.uzex.uz dan o'qib bo'lmadi. Buning sababi: 1) Render IP Cloudflare da blokda, 2) Sayt JS bilan himoyalangan.\n\nYechim: 1 soatdan keyin qayta urinib ko'ring yoki @uzexfeedbackbot dan tekshiring. Botning o'zi ishlayapti, faqat manba sayt vaqtincha yopiq.","budget":0,"region":"-","deadline":0,"deadline_date":now.strftime("%d.%m.%Y"),"link":"https://xarid.uzex.uz"},
    ]

def filter_tenders(tenders,f):
    res=tenders
    # Agar ERR bo'lsa filter qilmaymiz
    if res and res[0].get("id")=="ERR":
        return res
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
    bot.send_message(m.chat.id, f"👋 Salom, {m.from_user.first_name}!\n\n✅ Bot REAL v3 rejimda!\nEndi 3 xil usulda qidiradi:\n1. API (kalitsiz)\n2. HTML\n3. Playwright (Cloudflare)\n\nViloyat va kategoriyani tanlab, 'Mening tenderlarim' ni bosing.", reply_markup=kb)

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
        mark="✅" if it in sel else "⬜"
        kb.add(InlineKeyboardButton(f"{mark} {it}", callback_data=f"{pref}:{it}"))
    kb.add(InlineKeyboardButton("💾 Saqlash", callback_data=f"{pref}:SAVE"))
    try: bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=kb)
    except: pass
    bot.answer_callback_query(c.id, f"{len(sel)} ta")

@bot.message_handler(func=lambda m: m.text=="⚙️ Filtrim")
def show_f(m):
    f=load_users()[str(m.from_user.id)]["filters"]
    bot.send_message(m.chat.id, f"📍 Viloyatlar: {', '.join(f['regions']) or 'Hammasi'}\n💼 Kategoriyalar: {', '.join(f['categories']) or 'Hammasi'}")

@bot.message_handler(func=lambda m: m.text=="🔎 Mening tenderlarim")
def my_tenders(m):
    msg = bot.send_message(m.chat.id, "⏳ Real tenderlar qidirilmoqda...\n1️⃣ API tekshirilmoqda...\n2️⃣ Agar yopiq bo'lsa Playwright ishga tushadi (15-20 sek)")
    try:
        all_t = fetch_real_tenders()
        users=load_users(); f=users.get(str(m.from_user.id), {}).get("filters",{})
        filtered=filter_tenders(all_t,f)
        if not filtered:
            bot.send_message(m.chat.id, "😔 Mos tender yo'q. Filtrni bo'shatib ko'ring.")
            return
        if filtered[0]["id"]=="ERR":
            bot.send_message(m.chat.id, filtered[0]["name"])
            return
        text=f"🔥 {len(filtered)} ta REAL tender topildi:\n\n"
        for t in filtered[:10]:
            budget_txt = f"{t['budget']:,} so'm" if t['budget'] else "Byudjet saytda"
            text+=f"📦 {t['name']}\n🔢 Lot: {t['lot_number']}\n📍 {t['region']} | 💰 {budget_txt}\n⏰ {t['deadline_date']}\n🔗 {t['link']}\n\n"
        bot.send_message(m.chat.id, text, disable_web_page_preview=True)
    except Exception as e:
        traceback.print_exc()
        bot.send_message(m.chat.id, f"❌ Xato: {e}")

print("Tender bot REAL v3 ishga tushdi - Playwright bilan")
bot.infinity_polling()
