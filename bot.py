import asyncio
import re
import sqlite3
import io
import matplotlib.pyplot as plt
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from datetime import datetime

BOT_TOKEN = "8856832421:AAEWvsUoVd5XTpOsnRcSfWSrCsM8jlvp-mw"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- КНОПКИ МЕНЮ ---
def get_main_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("💰 Баланс"), KeyboardButton("📊 Статистика"))
    keyboard.add(KeyboardButton("🎯 Цель"))
    return keyboard

conn = sqlite3.connect('finance.db')
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT,
        amount INTEGER,
        category TEXT,
        date TEXT,
        comment TEXT
    )
''')
conn.commit()

def save_transaction(t_type, amount, category, comment):
    today = datetime.now().strftime("%d.%m.%Y")
    cursor.execute('''
        INSERT INTO transactions (type, amount, category, date, comment)
        VALUES (?, ?, ?, ?, ?)
    ''', (t_type, amount, category, today, comment))
    conn.commit()

def get_balance():
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE type = 'Доход'")
    income = cursor.fetchone()[0] or 0
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE type = 'Расход'")
    expense = cursor.fetchone()[0] or 0
    return income - expense

def get_category_expenses():
    cursor.execute("SELECT category, SUM(amount) FROM transactions WHERE type = 'Расход' AND category != 'Не указана' GROUP BY category")
    return cursor.fetchall()

def parse_money(text):
    amounts = re.findall(r'\b\d+\b', text)
    if not amounts:
        return None, None, None, "Я не нашел сумму. Напиши, например: 'Потратил 500'"
    
    amount = int(amounts[0])
    text_lower = text.lower()
    
    if any(word in text_lower for word in ['получил', 'зарплата', 'заработал', 'доход', 'пришло', 'перевели', 'аванс', 'продал', 'премия', 'выплата']):
        return "Доход", amount, "Доход", None
        
    if any(word in text_lower for word in ['такси', 'метро', 'автобус', 'заправка', 'бензин', 'парковка', 'машина', 'авто', 'заправил', 'топливо', 'газ']):
        return "Расход", amount, "Транспорт", None
        
    if any(word in text_lower for word in ['кафе', 'ресторан', 'поужинал', 'обед', 'шаурма', 'кофе', 'пицца', 'продукты', 'магазин', 'суши', 'бургер', 'еда', 'завтрак', 'ужин']):
        return "Расход", amount, "Еда", None
        
    if any(word in text_lower for word in ['квартира', 'аренда', 'коммуналка', 'свет', 'вода', 'газ', 'интернет', 'телефон', 'связь', 'хозяева']):
        return "Расход", amount, "Жилье", None
        
    if any(word in text_lower for word in ['кино', 'бар', 'клуб', 'концерт', 'игры', 'плейстейшн', 'развлечения', 'караоке']):
        return "Расход", amount, "Развлечения", None
        
    if any(word in text_lower for word in ['купил', 'телефон', 'ноутбук', 'одёжда', 'штаны', 'куртка', 'кроссовки', 'ботинки', 'джинсы', 'техника']):
        return "Расход", amount, "Покупки", None
        
    if any(word in text_lower for word in ['врач', 'лекарство', 'аптека', 'больница', 'таблетки', 'зубы', 'стоматолог']):
        return "Расход", amount, "Здоровье", None
        
    if any(word in text_lower for word in ['потратил', 'расход', 'оплатил', 'отдал', 'снял']):
        return "Расход", amount, "Прочее", None
        
    return "Расход", amount, "Прочее", None

def create_stats_chart():
    categories = get_category_expenses()
    if not categories:
        return None
        
    labels = [cat[0] for cat in categories]
    sizes = [cat[1] for cat in categories]
    
    plt.figure(figsize=(6, 6))
    plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140)
    plt.title("Твои расходы")
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return buf

@dp.message()
async def handle_message(message: types.Message):
    text = message.text
    
    # Обработка кнопок
    if text == "💰 Баланс":
        balance = get_balance()
        await message.answer(f"💰 Твой текущий баланс: **{balance} ₽**", reply_markup=get_main_keyboard())
        return
        
    elif text == "📊 Статистика":
        chart = create_stats_chart()
        if chart:
            await message.answer_photo(photo=types.BufferedInputFile(chart.read(), filename="stats.png"), caption="📊 Вот как распределяются твои траты", reply_markup=get_main_keyboard())
        else:
            await message.answer("📭 У тебя пока нет записанных расходов.", reply_markup=get_main_keyboard())
        return
        
    elif text == "🎯 Цель":
        await message.answer("📝 Напиши цель в формате:\n`/цель 100000 6`\n(где 100000 - сумма, 6 - месяцев)", reply_markup=get_main_keyboard())
        return

    text_lower = text.lower()
    
    if text_lower == "/start":
        await message.answer(
            "🤖 Я Finbro. Без нейросетей, но с отличной логикой!\n\n"
            "📝 Просто пиши о тратах текстом:\n"
            "- Заправил машину 1500\n"
            "- Поужинал в ресторане 2000\n"
            "- Зарплата 45000\n\n"
            "👇 Пользуйся кнопками снизу для быстрых команд!",
            reply_markup=get_main_keyboard()
        )
    
    elif text_lower.startswith("/цель"):
        parts = text_lower.split()
        if len(parts) < 3:
            await message.answer("❌ Формат: /цель [сумма] [месяцев]. Например: /цель 300000 6", reply_markup=get_main_keyboard())
            return
        try:
            target = int(parts[1])
            months = int(parts[2])
        except:
            await message.answer("❌ Укажи цифры.", reply_markup=get_main_keyboard())
            return
        needed_per_month = target / months
        await message.answer(f"🎯 **Цель:** {target} ₽ за {months} мес.\n📆 Нужно откладывать: **{needed_per_month:,.0f} ₽/мес**.", reply_markup=get_main_keyboard())

    else:
        t_type, amount, category, error = parse_money(text)
        if error:
            await message.answer(f"❌ {error}", reply_markup=get_main_keyboard())
        else:
            save_transaction(t_type, amount, category, text)
            sign = "+" if t_type == "Доход" else "-"
            
            category_emoji = {
                "Еда": "🍔", "Транспорт": "🚗", "Жилье": "🏠", 
                "Развлечения": "🎮", "Покупки": "🛍️", "Здоровье": "💊", 
                "Доход": "💰", "Прочее": "📌"
            }
            emoji = category_emoji.get(category, "📌")
            
            await message.answer(
                f"✅ Записал {t_type}!\n"
                f"Сумма: {sign}{amount} ₽\n"
                f"Категория: {emoji} {category}\n"
                f"📅 {datetime.now().strftime('%d.%m.%Y')}",
                reply_markup=get_main_keyboard()
            )

if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))
