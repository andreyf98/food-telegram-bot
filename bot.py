import os
import logging
import random
import json
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

from openai import OpenAI, RateLimitError


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
    "Сытно, но без перебора",
    "Еда как еда — и это хорошо",
]

ALCOHOL_WORDS = ["пиво", "алкоголь", "вино", "сидр", "шампанское"]
SWEET_WORDS = ["торт", "пирож", "шоколад", "конфет", "десерт"]


# ======================
# HELPERS
# ======================
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
    return random.choice(
        SPECIAL_COMMENTS if is_special(total_kcal, text) else NORMAL_COMMENTS
    )


def save_meal(user_id: int, total_kcal: int):
    MEALS.setdefault(user_id, []).append({
        "time": datetime.now(),
        "kcal": total_kcal,
    })


def meals_today(user_id: int) -> List[dict]:
    today = datetime.now().date()
    return [m for m in MEALS.get(user_id, []) if m["time"].date() == today]


def meals_week(user_id: int) -> List[dict]:
    week_ago = datetime.now() - timedelta(days=7)
    return [m for m in MEALS.get(user_id, []) if m["time"] >= week_ago]


# ======================
# OPENAI
# ======================
def analyze_food(prompt: str) -> dict:
    """
    Возвращает СТРОГО JSON.
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты анализируешь еду.\n"
                    "Верни СТРОГО JSON без текста.\n"
                    "Формат:\n"
                    "{\n"
                    "  \"items\": [\n"
                    "    {\"name\": \"...\", \"weight_g\": 123, \"kcal\": 456}\n"
                    "  ],\n"
                    "  \"total_kcal\": 789\n"
                    "}"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )

    content = response.choices[0].message.content
    return json.loads(content)


# ======================
# COMMANDS
# ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Я считаю калории по фото и тексту.\n\n"
        "Команды:\n"
        "/today — калории за сегодня\n"
        "/week — за 7 дней\n"
        "/delete — удалить последний приём\n"
        "/fix новый текст — исправить последний приём\n"
        "/reset — сбросить день\n"
        "/stop — остановить бота"
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Останавливаюсь 👋")
    await context.application.stop()


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    MEALS[update.effective_user.id] = []
    await update.message.reply_text("День сброшен.")


async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await update.message.reply_text("Напиши новое описание после /fix.")
        return

    meals.pop()
    result = analyze_food(new_text)
    save_meal(user_id, result["total_kcal"])

    comment = choose_comment(result["total_kcal"], new_text)

    await update.message.reply_text(
        f"Итого: {result['total_kcal']} ккал\n\n{comment}"
    )


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
    try:
        result = analyze_food(text)
    except RateLimitError:
        await update.message.reply_text("Лимит API, попробуй позже.")
        return
    except Exception:
        await update.message.reply_text("Не смог разобрать еду.")
        return

    save_meal(update.effective_user.id, result["total_kcal"])
    comment = choose_comment(result["total_kcal"], text)

    lines = []
    for i in result["items"]:
        lines.append(f"{i['name']} — {i['weight_g']} г — {i['kcal']} ккал")
    lines.append(f"\nИтого: {result['total_kcal']} ккал")
    lines.append(comment)

    await update.message.reply_text("\n".join(lines))


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await photo.get_file()
    caption = update.message.caption or ""

    prompt = f"Фото еды. Комментарий пользователя: {caption}"

    try:
        result = analyze_food(prompt)
    except RateLimitError:
        await update.message.reply_text("Лимит API, попробуй позже.")
        return
    except Exception:
        await update.message.reply_text("Не смог разобрать фото.")
        return

    save_meal(update.effective_user.id, result["total_kcal"])
    comment = choose_comment(result["total_kcal"], caption)

    lines = []
    for i in result["items"]:
        lines.append(f"{i['name']} — {i['weight_g']} г — {i['kcal']} ккал")
    lines.append(f"\nИтого: {result['total_kcal']} ккал")
    lines.append(comment)

    await update.message.reply_text("\n".join(lines))


# ======================
# MAIN
# ======================
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # ВАЖНО: СНАЧАЛА ФОТО
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("week", week))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("delete", delete))
    app.add_handler(CommandHandler("fix", fix))
    app.add_handler(CommandHandler("stop", stop))

    app.run_polling()


if __name__ == "__main__":
    main()
