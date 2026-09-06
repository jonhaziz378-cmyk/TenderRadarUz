import asyncio, json, os, re, logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, executor, types
import aiohttp
from bs4 import BeautifulSoup
from threading import Thread

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_TOKEN")
DB_FILE = "users.json"

VILOYATLAR = ["Toshkent sh", "Toshkent vil", "Samarqand", "Buxoro", "Andijon", "Farg'ona", "Namangan", "Qashqadaryo", "Surxondaryo", "Xorazm", "Navoiy", "Jizzax", "Sirdaryo", "Qoraqalpog'iston"]
KATEGORIYALAR = ["Qurilish", "IT kompyuter", "Tibbiyot dori", "Oziq-ovqat", "Mebel jihoz", "Transport", "Kantselyariya"]

bot = Bot(BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

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

# Kuchli headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "uz-UZ,uz;q=0.9",
    "Referer": "https://xt-xarid.uz/",
    "Connection": "keep-alive"
}

async def fetch_all_tenders(filters=None):
    """xt-xarid.uz saytidan tenderlarni olib kelish"""
    tenders = []
    
    try:
        logger.info("📍 Tenderlar qidirilmoqda...")
        
        proxy_url = os.environ.get("PROXY_URL", "")
        
        async with aiohttp.ClientSession(headers=HEADERS, connector=aiohttp.TCPConnector(ssl=False)) as session:
            try:
                async with session.get(
                    "https://xt-xarid.uz/oz/tenders", 
                    timeout=aiohttp.ClientTimeout(total=15),
                    proxy=proxy_url if proxy_url else None
                ) as r:
                    if r.status == 200:
                        html = await r.text()
                        logger.info(f"✅ Sahifa yuklab olindi: {len(html)} baitlar")
                        
                        soup = BeautifulSoup(html, 'html.parser')
                        tender_rows = soup.select('tr')
                        logger.info(f"📊 Topilgan qatorlar: {len(tender_rows)}")
                        
                        for row in tender_rows[:50]:
                            try:
                                cells = row.find_all('td')
                                if len(cells) < 5: continue
                                
                                lot_num = cells[0].get_text(strip=True)
                                tender_name = cells[1].get_text(strip=True)
                                region = cells[2].get_text(strip=True) if len(cells) > 2 else "Noma'lum"
                                budget_text = cells[3].get_text(strip=True) if len(cells) > 3 else "0"
                                deadline_text = cells[4].get_text(strip=True) if len(cells) > 4 else ""
                                
                                # Budget
                                budget = 0
                                try:
                                    budget_num = ''.join(filter(str.isdigit, budget_text.split()[0] if budget_text else "0"))
                                    budget = int(budget_num) if budget_num else 0
                                except: 
                                    budget = 0
                                
                                # Deadline
                                deadline_days = 0
                                deadline_date = (datetime.now() + timedelta(days=7)).strftime("%d.%m.%Y")
                                
                                try:
                                    if "kun" in deadline_text.lower():
                                        days_match = re.search(r'(\d+)', deadline_text)
                                        if days_match:
                                            deadline_days = int(days_match.group(1))
                                            deadline_date = (datetime.now() + timedelta(days=deadline_days)).strftime("%d.%m.%Y")
                                except:
                                    pass
                                
                                # Link
                                link_elem = row.find('a')
                                link = link_elem['href'] if link_elem and link_elem.get('href') else f"https://xt-xarid.uz/oz/tenders?lot={lot_num}"
                                if not link.startswith('http'):
                                    link = f"https://xt-xarid.uz{link}"
                                
                                # Filter - sham tenderlar
                                if not tender_name or budget == 0 or not lot_num:
                                    continue
                                
                                tender_id = f"lot_{lot_num}_{datetime.now().timestamp()}"
                                
                                tender = {
                                    "id": tender_id,
                                    "lot_number": lot_num,
                                    "name": tender_name,
                                    "budget": budget,
                                    "region": region,
                                    "deadline": deadline_days if deadline_days > 0 else 7,
                                    "deadline_date": deadline_date,
                                    "link": link,
                                    "fetched_at": datetime.now().isoformat()
                                }
                                
                                tenders.append(tender)
                                logger.info(f"✓ {tender_name[:50]} - {budget:,} so'm")
                                
                            except Exception as e:
                                logger.error(f"Row error: {e}")
                                continue
                    else:
                        logger.error(f"❌ Status: {r.status}")
                        
            except asyncio.TimeoutError:
                logger.error("⏱ Timeout")
            except Exception as e:
                logger.error(f"Request error: {e}")
        
        logger.info(f"✅ Jami: {len(tenders)} ta tender")
        
    except Exception as e:
        logger.error(f"Error: {e}")
    
    return tenders

def filter_tenders(tenders, f):
    """Filtrlash"""
    res = tenders
    res = [t for t in res if t.get("budget", 0) > 100000]
    res = [t for t in res if t.get("name", "").strip()]
    
    if f.get("regions"):
        res = [t for t in res if any(r.lower() in t["region"].lower() for r in f["regions"])]
    
    if f.get("categories"):
        res = [t for t in res if any(c.lower() in t["name"].lower() for c in f["categories"])]
    
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
        left_txt="Cheksiz" if left==999 else f"{left} kun"
        await m.answer(f"👋 Salom!\n📊 {left_txt}\n📍 {vil}\n💼 {kat}", reply_markup=types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))
    else:
        await m.answer("7 kun tugadi!")

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
        save_users(users); await c.message.edit_text(f"✅ Saqlandi!"); await c.answer(); return
    sel=users[uid]["filters"][key]
    if val in sel: sel.remove(val)
    else: sel.append(val)
    users[uid]["filters"][key]=sel; save_users(users)
    kb=make_kb(VILOYATLAR if pref=="REG" else KATEGORIYALAR, sel, pref)
    try: await c.message.edit_reply_markup(reply_markup=kb)
    except: pass
    await c.answer()

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
    sent_ids = set(users[str(m.from_user.id)].get("sent_ids", []))
    
    await m.answer("⏳ Qidirilmoqda...")
    
    all_t = await fetch_all_tenders(f)
    filtered = filter_tenders(all_t, f)
    
    if not filtered:
        await m.answer("❌ Tender yo'q")
        return
    
    new_tenders = [t for t in filtered if t["id"] not in sent_ids]
    
    if not new_tenders:
        await m.answer(f"📋 Siz {len(filtered)} ta tenderni ko'rgan ekansiz")
        return
    
    text = f"🔥 YA'NI: {len(new_tenders)} ta tender\n\n"
    
    for t in new_tenders[:10]:
        budget_formatted = f"{t['budget']:,}".replace(",", " ")
        text += f"📦 {t['name'][:60]}\n"
        text += f"🔢 {t['lot_number']} | 💰 {budget_formatted} so'm\n"
        text += f"📍 {t['region']} | ⏰ {t['deadline_date']}\n"
        text += f"🔗 {t['link']}\n\n"
    
    new_sent_ids = sent_ids | {t["id"] for t in new_tenders}
    users[str(m.from_user.id)]["sent_ids"] = list(new_sent_ids)[-200:]
    save_users(users)
    
    await m.answer(text, disable_web_page_preview=True)

if __name__=="__main__":
    print("🤖 Bot ishga tushdi - Polling mode")
    executor.start_polling(dp, skip_updates=True)
