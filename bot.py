import os
import logging
import asyncio
import random
from datetime import datetime, timedelta
from typing import List, Dict

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)

from openai import OpenAI
from openai import RateLimitError

# =========================
# ENV
# =========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_BOT_TOKEN or not OPENAI_API_KEY:
    raise RuntimeError("ENV variables TELEGRAM_BOT_TOKEN / OPENAI_API_KEY not set")

client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# LOGGING
# =========================
logging.basicConfig(level=logging.INFO)

# =========================
# STORAGE (IN-MEMORY)
# =========================
USER_MEALS: Dict[int, List[dict]] = {}

# =========================
# COMMENTS
# =========================
SPECIAL_COMMENTS = [
    "Кайфани как следует, роднулька ❤️ 🎉",
    "Сегодня можно 😌 🎉",
    "Живём один раз — кайфуй ❤️ 🎉",
    "Вот ради этого и старались 🎉",
    "Да и правильно, иногда надо 🎉",
    "Чистый кайф, без оправданий 🎉",
    "Вот за это мы и любим еду 🎉",
    "Чистое гастрономическое счастье 🎉",
    "Такое надо уважать 🎉",
]

NORMAL_COMMENTS = [
    "Хороший приём пищи",
    "Выглядит сбалансированно",
    "Нормальный, спокойный вариант",
    "Всё на месте",
    "Хорошая еда без лишнего",
    "По-домашнему",
    "Приятный вариант",
    "Сытно, но без перебора",
    "Еда как еда — и это хорошо",
]

# =========================
# HELPERS
# =========================
def get_user_storage(user_id: int) -> List[dict]:
    return USER_MEALS.setdefault(user_id, [])

def choose_comment(total_kcal: int, is_special_food: bool) -> str:
    if total_kcal >= 1000 or is_special_food:
        return random.choice(SPECIAL_COMMENTS)
    return random.choice(NORMAL_COMMENTS)

def is_special_food_by_name(name: str) -> bool:
    keywords = ["пиво", "алкоголь", "торт", "шоколад", "конфеты", "фастфуд"]
    name = name.lower()
    return any(k in name for k in keywords)

# =========================
# OPENAI ANALYSIS
# =========================
def analyze_food(prompt: str) -> dict:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты считаешь калории еды.\n"
                    "Если несколько блюд — перечисли их.\n"
                    "Для каждого блюда: название, вес (г), калории.\n"
                    "Верни JSON:\n"
                    "{ items: [{name, weight_g, kcal}], total_kcal }"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )

    return eval(response.choices[0].message.content)

# =========================
# HANDLERS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет 👋\n\n"
        "Я считаю калории по фото и тексту.\n\n"
        "Команды:\n"
        "/today — калории за сегодня\n"
        "/week — за 7 дней\n"
        "/reset — сброс дня\n"
        "/delete — удалить последний приём пищи\n"
        "/stop — остановить бота\n\n"
        "Можешь:\n"
        "• отправить фото еды\n"
        "• написать текстом: «2 сосиски и 5 яиц»"
    )

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Останавливаюсь 👋")
    await context.application.stop()

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meals = get_user_storage(update.effective_user.id)
    today_sum = sum(m["total_kcal"] for m in meals if m["date"].date() == datetime.now().date())
    await update.message.reply_text(f"Сегодня: {today_sum} ккал")

async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meals = get_user_storage(update.effective_user.id)
    week_ago = datetime.now() - timedelta(days=7)
    total = sum(m["total_kcal"] for m in meals if m["date"] >= week_ago)
    await update.message.reply_text(f"За 7 дней: {total} ккал")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    USER_MEALS[update.effective_user.id] = []
    await update.message.reply_text("Счётчик сброшен")

async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meals = get_user_storage(update.effective_user.id)
    if meals:
        meals.pop()
        await update.message.reply_text("Последний приём пищи удалён")
    else:
        await update.message.reply_text("Нечего удалять")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        result = analyze_food(update.message.text)
    except RateLimitError:
        await update.message.reply_text("Лимит API, попробуй позже")
        return

    items = result["items"]
    total_kcal = result["total_kcal"]

    is_special = any(is_special_food_by_name(i["name"]) for i in items)
    comment = choose_comment(total_kcal, is_special)

    lines = ["Блюда:"]
    for i in items:
        lines.append(f"• {i['name']} — {i['weight_g']} г — {i['kcal']} ккал")

    lines.append(f"\nИтого: {total_kcal} ккал")
    lines.append(comment)

    get_user_storage(update.effective_user.id).append({
        "date": datetime.now(),
        "total_kcal": total_kcal,
    })

    await update.message.reply_text("\n".join(lines))

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await photo.get_file()
    photo_url = file.file_path

    caption = update.message.caption or ""

    prompt = (
        "На фото еда.\n"
        f"{'Комментарий пользователя: ' + caption if caption else ''}\n"
        f"URL изображения: {photo_url}"
    )

    try:
        result = analyze_food(prompt)
    except RateLimitError:
        await update.message.reply_text("Лимит API, попробуй позже")
        return

    items = result["items"]
    total_kcal = result["total_kcal"]

    is_special = any(is_special_food_by_name(i["name"]) for i in items)
    comment = choose_comment(total_kcal, is_special)

    lines = ["Блюда:"]
    for i in items:
        lines.append(f"• {i['name']} — {i['weight_g']} г — {i['kcal']} ккал")

    lines.append(f"\nИтого: {total_kcal} ккал")
    lines.append(comment)

    get_user_storage(update.effective_user.id).append({
        "date": datetime.now(),
        "total_kcal": total_kcal,
    })

    await update.message.reply_text("\n".join(lines))

# =========================
# MAIN
# =========================
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # ВАЖНО: ПОРЯДОК
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("week", week))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("delete", delete))
    app.add_handler(CommandHandler("stop", stop))

    app.run_polling()

if __name__ == "__main__":
    main()
