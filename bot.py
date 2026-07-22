import asyncio
import re
import sqlite3
import io
import matplotlib.pyplot as plt
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from datetime import datetime

# --- Заглушка для Render ---
from aiohttp import web
import threading
async def handle(request):
    return web.Response(text="Bot is running!")
def run_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    web.run_app(app, host='0.0.0.0', port=10000)
threading.Thread(target=run_web_server, daemon=True).start()
# ---------------------------

BOT_TOKEN = "8856832421:AAEWvsUoVd5XTpOsnRcSfWSrCsM8jlvp-mw"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- КНОПКИ ---
def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💰 Баланс"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="⚙️ Мой лимит"), KeyboardButton(text="🎯 Цель")]
        ],
        resize_keyboard=True
    )

# --- БАЗА ДАННЫХ ---
conn = sqlite3.connect('finance.db')
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        type TEXT,
        amount INTEGER,
        category TEXT,
        date TEXT,
        comment TEXT
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_limits (
        user_id INTEGER PRIMARY KEY,
        daily_limit INTEGER
    )
''')
conn.commit()

def save_transaction(user_id, t_type, amount, category, comment):
    today = datetime.now().strftime("%d.%m.%Y")
    cursor.execute('''
        INSERT INTO transactions (user_id, type, amount, category, date, comment)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, t_type, amount, category, today, comment))
    conn.commit()

def get_user_limit(user_id):
    cursor.execute("SELECT daily_limit FROM user_limits WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    return res[0] if res else 1500

def set_user_limit(user_id, new_limit):
    cursor.execute("INSERT OR REPLACE INTO user_limits (user_id, daily_limit) VALUES (?, ?)", (user_id, new_limit))
    conn.commit()

def get_balance(user_id):
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = 'Доход'", (user_id,))
    income = cursor.fetchone()[0] or 0
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = 'Расход'", (user_id,))
    expense = cursor.fetchone()[0] or 0
    return income - expense

def get_category_expenses(user_id):
    cursor.execute("SELECT category, SUM(amount) FROM transactions WHERE user_id = ? AND type = 'Расход' AND category != 'Не указана' GROUP BY category", (user_id,))
    return cursor.fetchall()

def get_today_expenses(user_id):
    today = datetime.now().strftime("%d.%m.%Y")
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = 'Расход' AND date = ?", (user_id, today))
    return cursor.fetchone()[0] or 0

def get_avg_daily_expense(user_id):
    # Считаем средние траты за последние 7 дней
    cursor.execute("SELECT AVG(amount) FROM (SELECT SUM(amount) as amount FROM transactions WHERE user_id = ? AND type = 'Расход' GROUP BY date ORDER BY date DESC LIMIT 7)", (user_id,))
    res = cursor.fetchone()[0]
    return int(res) if res else 0

# --- ПАРСЕР ---
def parse_money(text):
    amounts = re.findall(r'\b\d+\b', text)
    if not amounts:
        return None, None, None, "Я не нашел сумму. Напиши число."
    amount = int(amounts[0])
    t_lower = text.lower()
    
    income_keywords = ['получил', 'зарплата', 'заработал', 'доход', 'пришло', 'перевели', 'аванс', 'продал', 'премия', 'выплата', 'подработка', 'халтура', 'нашел', 'вернули', 'расчет', 'гонорар', 'кешбэк', 'выиграл', 'дивиденды']
    if any(word in t_lower for word in income_keywords):
        return "Доход", amount, "Доход", None
        
    transport_keywords = ['такси', 'метро', 'автобус', 'заправка', 'бензин', 'парковка', 'машина', 'авто', 'заправил', 'топливо', 'газ', 'электричка', 'самолет', 'билет']
    if any(word in t_lower for word in transport_keywords):
        return "Расход", amount, "Транспорт", None
        
    food_keywords = ['кафе', 'ресторан', 'поужинал', 'обед', 'шаурма', 'кофе', 'пицца', 'продукты', 'магазин', 'суши', 'бургер', 'еда', 'завтрак', 'ужин', 'фастфуд', 'доставка', 'лавка', 'рынок']
    if any(word in t_lower for word in food_keywords):
        return "Расход", amount, "Еда", None
        
    home_keywords = ['квартира', 'аренда', 'коммуналка', 'свет', 'вода', 'газ', 'интернет', 'телефон', 'связь', 'хозяева', 'жкх', 'ремонт', 'дом', 'ипотека']
    if any(word in t_lower for word in home_keywords):
        return "Расход", amount, "Жилье", None
        
    fun_keywords = ['кино', 'бар', 'клуб', 'концерт', 'игры', 'плейстейшн', 'развлечения', 'караоке', 'вечеринка', 'боулинг', 'квест']
    if any(word in t_lower for word in fun_keywords):
        return "Расход", amount, "Развлечения", None
        
    shopping_keywords = ['купил', 'телефон', 'ноутбук', 'одёжда', 'штаны', 'куртка', 'кроссовки', 'ботинки', 'джинсы', 'техника', 'наушники', 'планшет', 'часы', 'сумка']
    if any(word in t_lower for word in shopping_keywords):
        return "Расход", amount, "Покупки", None
        
    health_keywords = ['врач', 'лекарство', 'аптека', 'больница', 'таблетки', 'зубы', 'стоматолог', 'анализы', 'массаж', 'косметолог']
    if any(word in t_lower for word in health_keywords):
        return "Расход", amount, "Здоровье", None
    
    if any(word in t_lower for word in ['потратил', 'расход', 'оплатил', 'отдал', 'снял', 'сходил']):
        return "Расход", amount, "Прочее", None
        
    return "Расход", amount, "Прочее", None

# --- ПРОДВИНУТЫЙ ГЕНЕРАТОР ГРАФИКОВ ---
def create_stats_chart(user_id):
    categories = get_category_expenses(user_id)
    if not categories:
        return None
        
    labels = [cat[0] for cat in categories]
    sizes = [cat[1] for cat in categories]
    
    # Стиль как в банковских приложениях (светлая тема с тенями)
    fig, ax = plt.subplots(figsize=(8, 8), facecolor='#f8f9fa')
    colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c', '#e67e22']
    
    wedges, texts, autotexts = ax.pie(
        sizes, 
        labels=labels, 
        autopct='%1.0f%%', 
        startangle=90,
        colors=colors,
        wedgeprops={'edgecolor': 'white', 'linewidth': 3, 'antialiased': True}
    )
    
    # Крупный шрифт для процентов
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontsize(12)
        autotext.set_fontweight('bold')
        
    for text in texts:
        text.set_fontsize(14)
        text.set_fontweight('bold')
        text.set_color('#2c3e50')
        
    ax.set_title("📊 Распределение расходов", fontsize=20, color='#2c3e50', pad=20, fontweight='bold')
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='#f8f9fa')
    buf.seek(0)
    plt.close()
    return buf

# --- ОБРАБОТЧИК ---
@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    text = message.text
    
    # --- КНОПКИ ---
    if text == "💰 Баланс":
        balance = get_balance(user_id)
        await message.answer(f"💰 Твой текущий баланс: **{balance} ₽**", reply_markup=get_main_keyboard())
        return
        
    elif text == "📊 Статистика":
        chart = create_stats_chart(user_id)
        if chart:
            await message.answer_photo(photo=types.BufferedInputFile(chart.read(), filename="stats.png"), caption="📊 Вот куда уходят твои деньги", reply_markup=get_main_keyboard())
        else:
            await message.answer("📭 Пока нет расходов для статистики.", reply_markup=get_main_keyboard())
        return
        
    elif text == "🎯 Цель":
        await message.answer("📝 Отправь цель в формате:\n`/цель 100000 6`\n(100000 - сумма, 6 - месяцев)", reply_markup=get_main_keyboard())
        return

    elif text == "⚙️ Мой лимит":
        curr_limit = get_user_limit(user_id)
        await message.answer(f"⚙️ Твой текущий лимит: **{curr_limit} ₽/день**\n\nЧтобы изменить, просто напиши новую сумму цифрами (например, `2500`).", reply_markup=get_main_keyboard())
        return

    text_lower = text.lower()
    
    # --- КОМАНДЫ ---
    if text_lower == "/start":
        await message.answer(
            "🤖 **Finbro PRO** — твой личный ИИ-коуч!\n\n"
            "📝 Просто пиши: *'Такси 350'* или *'Зарплата 45000'*\n"
            "⚙️ Настрой лимит дня.\n"
            "🎯 Ставь цели и получай советы.\n\n"
            "👇 Жми на кнопки!",
            reply_markup=get_main_keyboard()
        )
    
    elif text_lower.startswith("/цель"):
        parts = text_lower.split()
        if len(parts) < 3:
            await message.answer("❌ Формат: /цель [сумма] [месяцев].", reply_markup=get_main_keyboard())
            return
        try:
            target = int(parts[1])
            months = int(parts[2])
        except:
            await message.answer("❌ Укажи цифры.", reply_markup=get_main_keyboard())
            return
            
        current_balance = get_balance(user_id)
        avg_daily_spend = get_avg_daily_expense(user_id)
        needed_per_month = target / months
        
        reply = f"🎯 **Цель:** {target} ₽ за {months} мес.\n"
        reply += f"📆 Нужно откладывать: **{needed_per_month:,.0f} ₽/мес**.\n\n"
        
        if current_balance >= target:
            reply += "✅ У тебя уже есть эта сумма! Можешь покупать прямо сейчас!"
        else:
            reply += f"📊 Твои средние траты в день: **{avg_daily_spend} ₽**\n"
            safe_to_save = max(0, (avg_daily_spend * 30) - needed_per_month)
            
            if safe_to_save > 0:
                reply += f"💡 *Совет:* Сократив ненужные траты на {safe_to_save} ₽ в месяц, ты достигнешь цели без стресса."
            else:
                reply += "💡 *Совет:* Чтобы достичь цели, попробуй найти дополнительный источник дохода или увеличить срок накопления."
                
        await message.answer(reply, reply_markup=get_main_keyboard())

    # --- СМЕНА ЛИМИТА ---
    elif text.isdigit():
        new_limit = int(text)
        set_user_limit(user_id, new_limit)
        await message.answer(f"✅ Дневной лимит обновлен до **{new_limit} ₽**!", reply_markup=get_main_keyboard())

    # --- ЗАПИСЬ ТРАТ ---
    else:
        t_type, amount, category, error = parse_money(text)
        if error:
            await message.answer(f"❌ {error}", reply_markup=get_main_keyboard())
        else:
            save_transaction(user_id, t_type, amount, category, text)
            sign = "+" if t_type == "Доход" else "-"
            
            category_emoji = {"Еда": "🍔", "Транспорт": "🚗", "Жилье": "🏠", "Развлечения": "🎮", "Покупки": "🛍️", "Здоровье": "💊", "Доход": "💰", "Прочее": "📌"}
            emoji = category_emoji.get(category, "📌")
            
            today_spent = get_today_expenses(user_id)
            daily_limit = get_user_limit(user_id)
            remaining = daily_limit - today_spent
            
            response = f"✅ Записал {t_type}!\nСумма: {sign}{amount} ₽\nКатегория: {emoji} {category}\n📅 {datetime.now().strftime('%d.%m.%Y')}\n\n"
            
            if t_type == "Расход":
                if remaining < 0:
                    response += f"❌ Превышение лимита! Перерасход: **{abs(remaining)} ₽**"
                else:
                    response += f"💸 Сегодня потрачено: **{today_spent} ₽**\n📉 Остаток лимита: **{remaining} ₽**"
            
            await message.answer(response, reply_markup=get_main_keyboard())

# --- ЗАПУСК ---
if __name__ == "__main__":
    print("🚀 FINBRO PRO ЗАПУЩЕН!")
    asyncio.run(dp.start_polling(bot))
