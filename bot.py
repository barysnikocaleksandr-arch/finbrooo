import asyncio
import re
import sqlite3
import io
import matplotlib.pyplot as plt
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from datetime import datetime

# --- Заглушка для Render (чтобы не убивал бота) ---
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

# --- КНОПКИ МЕНЮ ---
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
# Таблица для транзакций
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
# Таблица для лимитов пользователей
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
    if res:
        return res[0]
    return 1500 # Дефолтный лимит, если пользователь его не менял

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

def get_avg_monthly_expense(user_id):
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = 'Расход' AND date >= date('now', '-30 days')", (user_id,))
    return cursor.fetchone()[0] or 0

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

# --- КРАСИВЫЙ ГЕНЕРАТОР ГРАФИКОВ ---
def create_stats_chart(user_id):
    categories = get_category_expenses(user_id)
    if not categories:
        return None
        
    labels = [cat[0] for cat in categories]
    sizes = [cat[1] for cat in categories]
    
    # Красивые цвета и настройка
    plt.figure(figsize=(8, 6))
    colors = plt.get_cmap('Set3')(range(len(labels)))
    
    # Рисуем круг с четкими границами и процентами
    wedges, texts, autotexts = plt.pie(
        sizes, 
        labels=labels, 
        autopct='%1.0f%%', 
        startangle=140, 
        colors=colors,
        wedgeprops={'edgecolor': 'white', 'linewidth': 2}
    )
    
    # Делаем шрифты жирными и крупными
    plt.setp(autotexts, size=12, weight="bold", color="white")
    plt.setp(texts, size=12, weight="bold")
    plt.title("Ваши расходы", fontsize=16, weight='bold', color='#333333')
    
    # Сохраняем в память
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
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
            await message.answer_photo(photo=types.BufferedInputFile(chart.read(), filename="stats.png"), caption="📊 Красивый график твоих трат", reply_markup=get_main_keyboard())
        else:
            await message.answer("📭 Пока нет расходов.", reply_markup=get_main_keyboard())
        return
        
    elif text == "🎯 Цель":
        await message.answer("📝 Напиши цель в формате:\n`/цель 100000 6`\n(где 100000 - сумма, 6 - месяцев)", reply_markup=get_main_keyboard())
        return

    elif text == "⚙️ Мой лимит":
        curr_limit = get_user_limit(user_id)
        await message.answer(f"⚙️ Твой текущий лимит на день: **{curr_limit} ₽**\n\nЧтобы изменить, просто напиши новую сумму цифрами (например: `3000`)", reply_markup=get_main_keyboard())
        return

    text_lower = text.lower()
    
    # --- КОМАНДЫ ---
    if text_lower == "/start":
        await message.answer(
            "🤖 Я Finbro MAX. Могу всё!\n\n"
            "📝 Пиши о деньгах любой фразой.\n"
            "⚙️ Нажми 'Мой лимит' чтобы настроить бюджет на день.\n"
            "📊 Смотри красивые графики!\n\n"
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
        avg_spend = get_avg_monthly_expense(user_id)
        needed_per_month = target / months
        
        reply = f"🎯 **Цель:** {target} ₽ за {months} мес.\n"
        reply += f"📆 Нужно: **{needed_per_month:,.0f} ₽/мес**.\n\n"
        
        if current_balance >= target:
            reply += "✅ У тебя уже есть эта сумма!"
        else:
            diff = max(0, needed_per_month - (current_balance / months))
            if diff > 0:
                reply += f"💡 *Совет:* Твои средние траты: {avg_spend:,.0f} ₽. Откладывай сразу после получения денег."
            else:
                reply += "📊 Ты справляешься!"
                
        await message.answer(reply, reply_markup=get_main_keyboard())

    # --- ЕСЛИ ПОЛЬЗОВАТЕЛЬ ПЫТАЕТСЯ ИЗМЕНИТЬ ЛИМИТ (Цифры в ответ на кнопку) ---
    elif text.isdigit():
        # Если пользователь отправил просто число, считаем это новым лимитом
        new_limit = int(text)
        set_user_limit(user_id, new_limit)
        await message.answer(f"✅ Новый дневной лимит установлен: **{new_limit} ₽**!", reply_markup=get_main_keyboard())

    # --- ЗАПИСЬ ТРАТ ---
    else:
        t_type, amount, category, error = parse_money(text)
        if error:
            await message.answer(f"❌ {error}", reply_markup=get_main_keyboard())
        else:
            save_transaction(user_id, t_type, amount, category, text)
            sign = "+" if t_type == "Доход" else "-"
            
            category_emoji = {
                "Еда": "🍔", "Транспорт": "🚗", "Жилье": "🏠", 
                "Развлечения": "🎮", "Покупки": "🛍️", "Здоровье": "💊", 
                "Доход": "💰", "Прочее": "📌"
            }
            emoji = category_emoji.get(category, "📌")
            
            today_spent = get_today_expenses(user_id)
            daily_limit = get_user_limit(user_id)
            remaining = max(0, daily_limit - today_spent)
            
            response = (
                f"✅ Записал {t_type}!\n"
                f"Сумма: {sign}{amount} ₽\n"
                f"Категория: {emoji} {category}\n"
                f"📅 {datetime.now().strftime('%d.%m.%Y')}\n\n"
            )
            
            if t_type == "Расход":
                response += f"💸 Сегодня потрачено: {today_spent} ₽\n"
                response += f"📉 Остаток лимита: **{remaining} ₽**"
            
            await message.answer(response, reply_markup=get_main_keyboard())

# --- ЗАПУСК ---
if __name__ == "__main__":
    print("🚀 FINBRO MAX ЗАПУЩЕН!")
    asyncio.run(dp.start_polling(bot))
