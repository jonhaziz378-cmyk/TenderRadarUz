import asyncio, json, os, re
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import aiohttp
from bs4 import BeautifulSoup

BOT_TOKEN = "8776730597:AAFF8PMTN_qvUdf-b-7Js4s8uGm_7B8PoME"
DB_FILE = "users.json"
VILOYATLAR = ["Toshkent sh", "Toshkent vil", "Samarqand", "Buxoro", "Andijon", "Farg'ona", "Namangan", "Qashqadaryo", "Surxondaryo", "Xorazm", "Navoiy", "Jizzax", "Sirdaryo", "Qoraqalpog'iston"]
KATEGORIYALAR = ["Qurilish", "IT kompyuter", "Tibbiyot dori", "Oziq-ovqat", "Mebel jihoz", "Transport", "Kantselyariya"]

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# --- RENDER keep-alive ---
from threading import Thread
try:
    from flask import Flask
    flask_app = Flask(__name__)
    @flask_app.route('/')
    def home(): return f"Bot alive {datetime.now()}"
    @flask_app.route('/health')
    def health(): return "OK"
    def run_flask():
        port=int(os.environ.get('PORT',10000))
        flask_app.run(host='0.0.0.0',port=port)
    Thread(target=run_flask,daemon=True).start()
    print("Flask keep-alive started")
except Exception as e:
    print(f"Flask error: {e}")


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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "uz-UZ,uz;q=0.9,ru;q=0.8,en;q=0.7",
    "Referer": "https://xarid.uzex.uz/",
}

async def fetch_xarid_html():
    """xarid.uzex.uz asosiy sahifasidan lotlarni olish - HTML orqali, JSON xato bo'lsa"""
    tenders=[]; now=datetime.now()
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            # xarid lotlar sahifasi - ko'p hollarda ochiq
            urls = [
                "https://xarid.uzex.uz/lots",
                "https://xarid.uzex.uz/",
            ]
            for url in urls:
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                        if r.status!=200: continue
                        html = await r.text()
                        if len(html)<1000: continue
                        soup = BeautifulSoup(html, 'html.parser')
                        # lot linklarni qidirish
                        for a in soup.find_all("a", href=True):
                            href=a["href"]
                            if "/lot/" in href:
                                m=re.search(r"/lot/(\d+)", href)
                                if not m: continue
                                lot_id=m.group(1)
                                # nomini topish - a text yoki yaqin tr
                                name=a.get_text(strip=True) or "Tender"
                                if len(name)<5: 
                                    parent=a.find_parent("tr")
                                    if parent: name=parent.get_text(" ", strip=True)[:150]
                                if len(name)<10: continue
                                # sana qidirish
                                parent_text=a.find_parent("tr").get_text(" ", strip=True) if a.find_parent("tr") else html
                                date_match=re.search(r"(\d{2}\.\d{2}\.\d{4})", parent_text)
                                deadline_date=date_match.group(1) if date_match else (now+timedelta(days=5)).strftime("%d.%m.%Y")
                                try:
                                    dt=datetime.strptime(deadline_date, "%d.%m.%Y")
                                    days_left=(dt-now).days
                                except: days_left=5
                                tenders.append({
                                    "id": f"lot_{lot_id}",
                                    "lot_number": lot_id,
                                    "name": name[:150],
                                    "budget": 10000000,
                                    "region": "Toshkent sh",
                                    "deadline": max(days_left,0),
                                    "deadline_date": deadline_date,
                                    "link": f"https://xarid.uzex.uz/lot/{lot_id}" if href.startswith("/") else href
                                })
                                if len(tenders)>=20: break
                        if tenders:
                            print(f"xarid html dan {len(tenders)} ta topildi")
                            return tenders
                except Exception as e:
                    print(f"html xato {url}: {e}")
                    continue
    except Exception as e:
        print(f"html umumiy xato: {e}")
    return tenders

async def fetch_xarid_api():
    """JSON API - xato bo'lsa ham urinadi"""
    tenders=[]; now=datetime.now()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # 1. To'g'ridan-to'g'ri lotlar API - turli variantlar
        apis = [
            "https://xarid.uzex.uz/api/Common/GetLots?page=1&pageSize=30",
            "https://xarid.uzex.uz/api/Lots/GetActiveLots?page=1&pageSize=30",
            "https://xarid.uzex.uz/api/Lots/GetLots?page=1&pageSize=30",
            "https://xarid.uzex.uz/api/Common/GetActiveLots?page=1&pageSize=30",
        ]
        for url in apis:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status!=200: continue
                    ctype = r.headers.get("Content-Type","")
                    text = await r.text()
                    if "text/html" in ctype or "<html" in text.lower()[:500]:
                        # HTML qaytgan - JSON emas, o'tkazib yuboramiz, html parser ishlaydi
                        continue
                    try:
                        data = json.loads(text)
                    except:
                        continue
                    lots=[]
                    if isinstance(data, dict):
                        lots=data.get("data") or data.get("lots") or data.get("items") or data.get("result") or []
                        if isinstance(lots, dict): lots=lots.get("data") or []
                    elif isinstance(data, list): lots=data
                    if not lots: continue
                    for lot in lots[:30]:
                        if not isinstance(lot, dict): continue
                        lot_id=str(lot.get("id") or lot.get("lot_id") or lot.get("lotId") or lot.get("code") or "")
                        if not lot_id: continue
                        name=(lot.get("name") or lot.get("title") or lot.get("product_name") or "Tender")[:150]
                        budget=lot.get("budget") or lot.get("start_price") or 10000000
                        try: budget=int(float(budget))
                        except: budget=10000000
                        end_str=lot.get("end_date") or lot.get("deadline") or ""
                        deadline_date=""; days_left=5
                        if end_str:
                            try:
                                dt=None
                                for fmt in ("%Y-%m-%dT%H:%M:%S","%Y-%m-%d %H:%M:%S","%d.%m.%Y","%Y-%m-%d"):
                                    try:
                                        dt=datetime.strptime(end_str[:19], fmt) if "T" in end_str else datetime.strptime(end_str[:10], fmt)
                                        break
                                    except: continue
                                if dt:
                                    deadline_date=dt.strftime("%d.%m.%Y")
                                    days_left=(dt-now).days
                            except: pass
                        if not deadline_date: deadline_date=(now+timedelta(days=5)).strftime("%d.%m.%Y")
                        region=lot.get("region") or "Toshkent sh"
                        tenders.append({
                            "id": f"lot_{lot_id}",
                            "lot_number": lot_id,
                            "name": name,
                            "budget": budget,
                            "region": region,
                            "deadline": max(days_left,0),
                            "deadline_date": deadline_date,
                            "link": f"https://xarid.uzex.uz/lot/{lot_id}"
                        })
                    if tenders:
                        print(f"API {url} dan {len(tenders)} ta")
                        return tenders
            except Exception as e:
                print(f"API xato {url}: {e}")
                continue
    return tenders

async def fetch_all_tenders(filters=None):
    # Avval API, keyin HTML
    t = await fetch_xarid_api()
    if not t:
        t = await fetch_xarid_html()
    print(f"JAMI: {len(t)} ta")
    return t

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

@dp.message(Command("start"))
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

@dp.message(lambda m: m.text=="📍 Viloyat")
async def ask_reg(m: types.Message):
    sel=load_users()[str(m.from_user.id)]["filters"]["regions"]
    await m.answer("Viloyat tanlang:", reply_markup=make_kb(VILOYATLAR, sel, "REG"))
@dp.message(lambda m: m.text=="💼 Kategoriya")
async def ask_cat(m: types.Message):
    sel=load_users()[str(m.from_user.id)]["filters"]["categories"]
    await m.answer("Kategoriya tanlang:", reply_markup=make_kb(KATEGORIYALAR, sel, "CAT"))

@dp.callback_query(lambda c: c.data.startswith("REG:") or c.data.startswith("CAT:"))
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

@dp.message(lambda m: m.text=="⚙️ Filtrim")
async def show_f(m: types.Message):
    f=load_users()[str(m.from_user.id)]["filters"]
    await m.answer(f"📍 {', '.join(f['regions']) or 'Hammasi'}\n💼 {', '.join(f['categories']) or 'Hammasi'}")

@dp.message(lambda m: m.text=="🔎 Mening tenderlarim")
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

async def auto_loop():
    while True:
        try:
            users=load_users(); all_t=await fetch_all_tenders({})
            for uid,u in users.items():
                acc,_=check_access(int(uid))
                if not acc: continue
                filt=u["filters"]
                if not filt["regions"] and not filt["categories"]: continue
                filtered=filter_tenders(all_t,filt)
                new=[t for t in filtered if t["id"] not in u.get("sent_ids",[])]
                if new:
                    try:
                        txt=f"🔔 Yangi {len(new)} ta tender!\n\n"
                        for t in new[:3]:
                            txt+=f"📦 {t['name'][:60]}\n🔢 Lot: {t['lot_number']} | ⏰ {t['deadline_date']}\n🔗 {t['link']}\n\n"
                        await bot.send_message(int(uid), txt)
                        users[uid]["sent_ids"]=(users[uid].get("sent_ids",[])+[t["id"] for t in new])[-100:]
                        save_users(users)
                    except: pass
        except Exception as e: print(f"auto xato: {e}")
        await asyncio.sleep(15*60)

async def main():
    asyncio.create_task(auto_loop())
    print("Tender bot ishga tushdi")
    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())
