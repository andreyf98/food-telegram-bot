import os
import json
import logging
import asyncio
import base64
import random
from datetime import date, timedelta
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)
from openai import OpenAI, RateLimitError

# ========================
# ENV
# ========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_BOT_TOKEN or not OPENAI_API_KEY:
    raise RuntimeError("Env variables not set")

client = OpenAI(api_key=OPENAI_API_KEY)
DATA_FILE = "data.json"

logging.basicConfig(level=logging.INFO)

# ========================
# COMMENTS
# ========================
SPECIAL_COMMENTS = [
    "Кайфани как следует, роднулька ❤️ 🎉",
    "Сегодня можно 😌 💎",
    "Живём один раз — кайфуй ❤️ 🥇",
    "Вот ради этого и старались 🎉",
    "Да и правильно, иногда надо 💎",
    "Чистый кайф, без оправданий 🥇",
    "Вот за это мы и любим еду 🎉",
    "Чистое гастрономическое счастье 💎",
    "Такое надо уважать 🥇",
]

NORMAL_COMMENTS = [
    "Хороший приём пищи.",
    "Выглядит сбалансированно.",
    "Нормальный, спокойный вариант.",
    "Всё на месте.",
    "Хорошая еда без лишнего.",
    "Выглядит по-человечески.",
    "Похоже на сытный приём пищи.",
    "Выглядит разумно.",
    "Всё выглядит вполне ок.",
    "По-домашнему.",
    "Выглядит уютно.",
    "Спокойная еда.",
    "Приятный вариант.",
    "Такое обычно заходит.",
    "Простая и понятная еда.",
    "Ничего лишнего.",
    "Еда как еда — и это хорошо.",
    "Сытно, но без перебора.",
    "Хорошо вписывается в день.",
]

# ========================
# DATA
# ========================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def is_stopped(user_id):
    return load_data().get("stopped", {}).get(str(user_id), False)

def set_stopped(user_id, value):
    data = load_data()
    data.setdefault("stopped", {})
    data["stopped"][str(user_id)] = value
    save_data(data)

def add_meal(user_id, meal):
    data = load_data()
    today = str(date.today())
    uid = str(user_id)
    data.setdefault(uid, {})
    data[uid].setdefault(today, [])
    data[uid][today].append(meal)
    save_data(data)

def get_last_meal(user_id):
    data = load_data()
    today = str(date.today())
    return data.get(str(user_id), {}).get(today, [])[-1]

def replace_last_meal(user_id, meal):
    data = load_data()
    today = str(date.today())
    data[str(user_id)][today][-1] = meal
    save_data(data)

def delete_last_meal(user_id):
    data = load_data()
    today = str(date.today())
    meals = data.get(str(user_id), {}).get(today, [])
    if not meals:
        return False
    meals.pop()
    save_data(data)
    return True

def reset_today(user_id):
    data = load_data()
    today = str(date.today())
    uid = str(user_id)
    if uid in data and today in data[uid]:
        del data[uid][today]
        save_data(data)
        return True
    return False

# ========================
# LOGIC (FIXED)
# ========================
def is_special(calories: int, text: str) -> bool:
    text = text.lower()

    # строго: только очень калорийное
    if calories > 1000:
        return True

    # явно вредная / кайфовая еда
    tasty_words = {
        "пицца", "бургер", "фастфуд", "шаурма",
        "пиво", "алкоголь", "чипсы"
    }

    if any(w in text for w in tasty_words):
        return True

    return False

def choose_comment(calories, text):
    return random.choice(
        SPECIAL_COMMENTS if is_special(calories, text) else NORMAL_COMMENTS
    )

def extract_calories(text):
    """
    Берём ТОЛЬКО строку 'Итого'
    """
    for line in text.splitlines():
        if line.lower().startswith("итого"):
            digits = "".join(c for c in line if c.isdigit())
            return int(digits) if digits else 0
    return 0

# ========================
# GPT
# ========================
async def analyze(prompt, image_base64=None):
    content = [{"type": "text", "text": prompt}]
    if image_base64:
        content.append({
            "type": "image_url",
            "image_url": {"url": "data:image/jpeg;base64," + image_base64}
        })

    response = await asyncio.to_thread(
        client.chat.completions.create,
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": content}],
        max_tokens=400,
    )
    return response.choices[0].message.content.strip()

# ========================
# COMMANDS (НЕ ТРОГАЛ)
# ========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_stopped(update.effective_user.id, False)
    await update.message.reply_text(
        "Бот активен.\n\n"
        "Команды:\n"
        "/today — калории за сегодня\n"
        "/week — статистика за 7 дней\n"
        "/delete — удалить последний приём пищи\n"
        "/fix — исправить последний приём пищи\n"
        "/reset — сбросить сегодняшний день\n"
        "/stop — временно отключить бота"
    )

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_stopped(update.effective_user.id, True)
    await update.message.reply_text("Бот остановлен. Напиши /start, чтобы включить снова.")

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    today = str(date.today())
    meals = data.get(str(update.effective_user.id), {}).get(today, [])
    await update.message.reply_text(
        f"Сегодня: {sum(m['calories'] for m in meals)} ккал"
        if meals else "Сегодня пока ничего не записано."
    )

async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = str(update.effective_user.id)
    total = 0
    lines = []

    for i in range(6, -1, -1):
        d = date.today() - timedelta(days=i)
        cals = sum(m["calories"] for m in data.get(uid, {}).get(str(d), []))
        total += cals
        lines.append(f"{d.strftime('%a')}: {cals} ккал")

    await update.message.reply_text(
        "Последние 7 дней:\n\n" + "\n".join(lines) + f"\n\nИтого: {total} ккал"
    )

async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if delete_last_meal(update.effective_user.id):
        await update.message.reply_text("Последний приём пищи удалён.")
    else:
        await update.message.reply_text("Удалять нечего.")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if reset_today(update.effective_user.id):
        await update.message.reply_text("Сегодняшний день сброшен.")
    else:
        await update.message.reply_text("Сегодня пока нечего сбрасывать.")

async def fix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["fixing"] = True
    await update.message.reply_text(
        "Опиши, что нужно исправить.\n"
        "Например: добавить помидор, сосисок было 2."
    )

# ========================
# HANDLERS (НЕ ТРОГАЛ)
# ========================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_stopped(update.effective_user.id):
        return

    file = await update.message.photo[-1].get_file()
    image = base64.b64encode(await file.download_as_bytearray()).decode()

    prompt = (
        "Определи блюда на фото и их калорийность.\n"
        "Формат:\n"
        "Блюда:\n"
        "• название — вес — ккал\n\n"
        "Итого: ккал"
    )

    try:
        answer = await analyze(prompt, image)
        calories = extract_calories(answer)
        comment = choose_comment(calories, answer)

        add_meal(update.effective_user.id, {
            "calories": calories,
            "raw": answer
        })

        await update.message.reply_text(answer + "\n\n" + comment)

    except RateLimitError:
        await update.message.reply_text("⏳ Я сейчас перегружен. Попробуй позже.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_stopped(update.effective_user.id):
        return

    text = update.message.text

    if context.user_data.get("fixing"):
        context.user_data["fixing"] = False
        last = get_last_meal(update.effective_user.id)

        prompt = (
            "Исходное описание:\n" + last["raw"] +
            "\n\nИсправь согласно инструкции:\n" + text
        )

        answer = await analyze(prompt)
        calories = extract_calories(answer)
        comment = choose_comment(calories, answer)

        replace_last_meal(update.effective_user.id, {
            "calories": calories,
            "raw": answer
        })

        await update.message.reply_text(answer + "\n\n" + comment)
        return

    prompt = (
        "Пользователь съел: " + text +
        "\nЕсли количество не указано — возьми среднюю порцию.\n"
        "Формат:\n"
        "Блюда:\n"
        "• название — вес — ккал\n\n"
        "Итого: ккал"
    )

    try:
        answer = await analyze(prompt)
        calories = extract_calories(answer)
        comment = choose_comment(calories, answer)

        add_meal(update.effective_user.id, {
            "calories": calories,
            "raw": answer
        })

        await update.message.reply_text(answer + "\n\n" + comment)

    except RateLimitError:
        await update.message.reply_text("⏳ Я сейчас перегружен. Попробуй позже.")

# ========================
# MAIN
# ========================
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("week", week))
    app.add_handler(CommandHandler("delete", delete))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("fix", fix))

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
