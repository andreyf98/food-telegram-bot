import os
import logging
import random
from datetime import datetime, timedelta
from typing import Dict, List

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

from openai import OpenAI
from openai.error import RateLimitError


# ========================
# ENV
# ========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_BOT_TOKEN or not OPENAI_API_KEY:
    raise RuntimeError("ENV variables not set")

client = OpenAI(api_key=OPENAI_API_KEY)

# ========================
# LOGGING
# ========================
logging.basicConfig(level=logging.INFO)

# ========================
# STORAGE
# ========================
MEALS: Dict[int, List[dict]] = {}

# ========================
# COMMENTS
# ========================

SPECIAL_COMMENTS = [
    "Кайфани как следует, роднулька ❤️ 🎉",
    "Сегодня можно 😌 🎉",
    "Живём один раз — кайфуй ❤️ 🥇",
    "Вот ради этого и старались 💎",
    "Да и правильно, иногда надо 🎉",
    "Чистый кайф, без оправданий 🥇",
    "Вот за это мы и любим еду 💎",
    "Чистое гастрономическое счастье 🎉",
    "Такое надо уважать 🥇",
]

NORMAL_COMMENTS = [
    "Хороший приём пищи",
    "Выглядит сбалансированно",
    "Нормальный, спокойный вариант",
    "Всё на месте",
    "Хорошая еда без лишнего",
    "По-домашнему",
    "Сытно и без перебора",
    "Простая и понятная еда",
    "Выглядит разумно",
    "Еда как еда — и это хорошо",
]

ALCOHOL_KEYWORDS = ["пиво", "вино", "алкоголь", "шампанское", "сидр"]
SWEET_KEYWORDS = ["торт", "пирож", "конфет", "шоколад", "десерт"]


# ========================
# UTILS
# ========================

def is_special_meal(meal: dict) -> bool:
    text = meal["description"].lower()
    calories = meal["total_calories"]

    if calories >= 1000:
        return True

    if any(word in text for word in ALCOHOL_KEYWORDS):
        return True

    if any(word in text for word in SWEET_KEYWORDS) and calories >= 600:
        return True

    return False


def choose_comment(meal: dict) -> str:
    return random.choice(
        SPECIAL_COMMENTS if is_special_meal(meal) else NORMAL_COMMENTS
    )


def ask_openai(prompt: str) -> int:
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Определи калорийность еды. Ответь ТОЛЬКО числом в ккал.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        text = response.choices[0].message.content
        digits = "".join(c for c in text if c.isdigit())
        return int(digits) if digits else 0
    except RateLimitError:
        return 0


def add_meal(user_id: int, description: str):
    calories = ask_openai(description)
    meal = {
        "description": description,
        "total_calories": calories,
        "time": datetime.now(),
    }
    MEALS.setdefault(user_id, []).append(meal)
    return meal


def meals_today(user_id: int) -> List[dict]:
    today = datetime.now().date()
    return [
        m for m in MEALS.get(user_id, [])
        if m["time"].date() == today
    ]


def meals_last_week(user_id: int) -> List[dict]:
    week_ago = datetime.now() - timedelta(days=7)
    return [
        m for m in MEALS.get(user_id, [])
        if m["time"] >= week_ago
    ]


# ========================
# COMMANDS
# ========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Я считаю калории по фото и тексту.\n\n"
        "Команды:\n"
        "/today — калории за сегодня\n"
        "/week — калории за неделю\n"
        "/delete — удалить последний приём\n"
        "/fix новое описание — исправить последний приём\n"
        "/reset — сбросить день\n"
        "/stop — остановить бота"
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Останавливаюсь 👋")
    await context.application.stop()


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    MEALS[user_id] = []
    await update.message.reply_text("Счётчик за день сброшен.")


async def delete_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meals = MEALS.get(update.effective_user.id, [])
    if meals:
        meals.pop()
        await update.message.reply_text("Последний приём пищи удалён.")
    else:
        await update.message.reply_text("Удалять нечего.")


async def fix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    meals = MEALS.get(user_id, [])

    if not meals:
        await update.message.reply_text("Нечего исправлять.")
        return

    new_text = update.message.text.replace("/fix", "").strip()
    if not new_text:
        await update.message.reply_text("Напиши новое описание после /fix")
        return

    meals.pop()
    meal = add_meal(user_id, new_text)
    comment = choose_comment(meal)

    await update.message.reply_text(
        f"{meal['description']}\n"
        f"{meal['total_calories']} ккал\n\n{comment}"
    )


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meals = meals_today(update.effective_user.id)
    total = sum(m["total_calories"] for m in meals)
    await update.message.reply_text(f"Сегодня: {total} ккал")


async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meals = meals_last_week(update.effective_user.id)
    total = sum(m["total_calories"] for m in meals)
    await update.message.reply_text(f"За 7 дней: {total} ккал")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    meal = add_meal(update.effective_user.id, text)
    comment = choose_comment(meal)

    await update.message.reply_text(
        f"{meal['description']}\n"
        f"{meal['total_calories']} ккал\n\n{comment}"
    )


# ========================
# MAIN
# ========================

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("delete", delete_last))
    app.add_handler(CommandHandler("fix", fix))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("week", week))

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )

    print("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
