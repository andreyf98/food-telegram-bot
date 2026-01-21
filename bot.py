import os
import logging
import re
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

# ======================
# ENV
# ======================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_BOT_TOKEN or not OPENAI_API_KEY:
    raise RuntimeError("ENV variables not set")

client = OpenAI(api_key=OPENAI_API_KEY)

logging.basicConfig(level=logging.INFO)

# ======================
# STORAGE
# ======================
MEALS: Dict[int, List[dict]] = {}

# ======================
# COMMENTS
# ======================
SPECIAL_COMMENTS = [
    "Кайфани как следует, роднулька ❤️ 🎉",
    "Сегодня можно 😌 🎉",
    "Живём один раз — кайфуй ❤️ 🎉",
    "Вот ради этого и старались 🎉",
    "Да и правильно, иногда надо 🎉",
]

NORMAL_COMMENTS = [
    "Хороший приём пищи",
    "Выглядит сбалансированно",
    "Нормальный вариант",
    "Всё ок",
    "Еда как еда — и это хорошо",
]

ALCOHOL_WORDS = ["пиво", "алкоголь", "вино", "сидр"]
SWEET_WORDS = ["торт", "шоколад", "конфет", "десерт"]

# ======================
# HELPERS
# ======================
def extract_calories(text: str) -> int:
    numbers = re.findall(r"\d{2,5}", text)
    nums = [int(n) for n in numbers if 10 <= int(n) <= 5000]
    return max(nums) if nums else 0


def is_special(total_kcal: int, text: str) -> bool:
    t = text.lower()
    if total_kcal >= 1000:
        return True
    if any(w in t for w in ALCOHOL_WORDS):
        return True
    if total_kcal >= 600 and any(w in t for w in SWEET_WORDS):
        return True
    return False


def choose_comment(total_kcal: int, text: str) -> str:
    if is_special(total_kcal, text):
        return random.choice(SPECIAL_COMMENTS)
    return random.choice(NORMAL_COMMENTS)


def save_meal(user_id: int, kcal: int):
    MEALS.setdefault(user_id, []).append({
        "time": datetime.now(),
        "kcal": kcal,
    })


def meals_today(user_id: int):
    today = datetime.now().date()
    return [m for m in MEALS.get(user_id, []) if m["time"].date() == today]


def meals_week(user_id: int):
    week_ago = datetime.now() - timedelta(days=7)
    return [m for m in MEALS.get(user_id, []) if m["time"] >= week_ago]


# ======================
# OPENAI
# ======================
def ask_openai(prompt: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Определи блюдо и калорийность."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
    )
    return response.choices[0].message.content


# ======================
# COMMANDS
# ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Я считаю калории по фото и тексту.\n\n"
        "Команды:\n"
        "/today — за сегодня\n"
        "/week — за 7 дней\n"
        "/delete — удалить последний приём\n"
        "/reset — сбросить день"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    MEALS[update.effective_user.id] = []
    await update.message.reply_text("День сброшен.")


async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meals = MEALS.get(update.effective_user.id, [])
    if meals:
        meals.pop()
        await update.message.reply_text("Последний приём удалён.")
    else:
        await update.message.reply_text("Нечего удалять.")


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = sum(m["kcal"] for m in meals_today(update.effective_user.id))
    await update.message.reply_text(f"Сегодня: {total} ккал")


async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = sum(m["kcal"] for m in meals_week(update.effective_user.id))
    await update.message.reply_text(f"За 7 дней: {total} ккал")


# ======================
# HANDLERS
# ======================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    answer = ask_openai(text)
    kcal = extract_calories(answer)

    save_meal(update.effective_user.id, kcal)
    comment = choose_comment(kcal, text)

    await update.message.reply_text(
        f"{answer}\n\nИтого: {kcal} ккал\n{comment}"
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caption = update.message.caption or "Еда на фото"

    answer = ask_openai(f"На фото еда. {caption}")
    kcal = extract_calories(answer)

    save_meal(update.effective_user.id, kcal)
    comment = choose_comment(kcal, caption)

    await update.message.reply_text(
        f"{answer}\n\nИтого: {kcal} ккал\n{comment}"
    )


# ======================
# MAIN
# ======================
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("week", week))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("delete", delete))

    app.run_polling()


if __name__ == "__main__":
    main()
