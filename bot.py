from __future__ import annotations

import logging
import os
from datetime import datetime, time
from pathlib import Path
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update, WebAppInfo
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import storage

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://footballistika-web.vercel.app/web/index.html")
ADMIN_IDS = {
    int(item.strip())
    for item in os.environ.get("ADMIN_IDS", "").split(",")
    if item.strip()
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

MAKE_PREDICTION_BTN = "Зробити прогноз"
PROFILE_BTN = "Профіль"
TABLE_BTN = "Таблиця"
USER_RESULT_ACCURACY_BTN = "Влучність прогнозів"
USER_GOAL_ACCURACY_BTN = "Влучність по голам"
USER_ALL_PREDICTIONS_BTN = "Всі прогнози"
USER_AVG_PREDICTION_BTN = "Середній прогноз"
ADMIN_MENU_BTN = "Адмінка"
ADMIN_ADD_MATCH_BTN = "➕ Додати матч"
ADMIN_ENTER_RESULT_BTN = "📋 Ввести результат"
ADMIN_AVG_PREDICTION_BTN = "📊 Середній прогноз"
ADMIN_ALL_PREDICTIONS_BTN = "📜 Всі прогнози"
ADMIN_RESULT_ACCURACY_BTN = "🎯 Влучність результату"
ADMIN_GOAL_ACCURACY_BTN = "🥅 Точність по голах"
BACK_BTN = "⬅️ Назад"

YES_WORDS = {"так", "ок", "окей", "ok", "yes", "y", "+", "ага"}
NO_WORDS = {"ні", "no", "n", "не", "-"}
CANCEL_WORDS = {"відміна", "скасувати", "cancel", "назад", "back", "stop"}
ADD_MATCH_CANCEL_BTN = "❌ Скасувати"
ADD_MATCH_CONFIRM_BTN = "✅ Підтвердити"
ADD_MATCH_REENTER_BTN = "↩️ Змінити"
PREDICTION_CANCEL_BTN = "❌ Скасувати прогноз"
RESULT_INPUT_PLACEHOLDER = "Введи рахунок у форматі 2:1"
KYIV_TZ = ZoneInfo("Europe/Kyiv")
PREDICTION_DEADLINE = time(17, 59)


def is_admin(user_id: Optional[int]) -> bool:
    return bool(user_id and user_id in ADMIN_IDS)


def main_keyboard(is_admin_user: bool) -> ReplyKeyboardMarkup:
    buttons = [
        [MAKE_PREDICTION_BTN],
        [TABLE_BTN],
        [USER_AVG_PREDICTION_BTN, USER_ALL_PREDICTIONS_BTN],
        [USER_RESULT_ACCURACY_BTN, USER_GOAL_ACCURACY_BTN],
    ]
    if is_admin_user:
        buttons.append([ADMIN_MENU_BTN])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def admin_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [ADMIN_ADD_MATCH_BTN],
            [ADMIN_ENTER_RESULT_BTN],
            [BACK_BTN],
        ],
        resize_keyboard=True,
    )


def add_match_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[ADD_MATCH_CANCEL_BTN]], resize_keyboard=True)


def add_match_confirmation_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[ADD_MATCH_CONFIRM_BTN], [ADD_MATCH_REENTER_BTN], [ADD_MATCH_CANCEL_BTN]],
        resize_keyboard=True,
    )


def prediction_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[PREDICTION_CANCEL_BTN]], resize_keyboard=True)


def default_reply_markup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> ReplyKeyboardMarkup:
    user = update.effective_user
    user_id = user.id if user else None
    if user_id and context.user_data.get("admin_menu_open") and is_admin(user_id):
        return admin_keyboard()
    return main_keyboard(is_admin_user=is_admin(user_id))


def result_entry_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[BACK_BTN]],
        resize_keyboard=True,
        input_field_placeholder=RESULT_INPUT_PLACEHOLDER,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    username = user.username or user.full_name or str(user.id)
    storage.ensure_user_record(user.id, username)
    context.user_data.clear()
    greeting_name = user.full_name or user.first_name or username
    await update.message.reply_text(
        f"Привіт, {greeting_name}!\nВикористовуй кнопки нижче, щоб зробити прогноз або переглянути таблицю.",
        reply_markup=main_keyboard(is_admin(user.id)),
    )
    await send_webapp_button(update, context)


async def send_webapp_button(update: Update, context: ContextTypes.DEFAULT_TYPE | None = None) -> None:
    keyboard = [
        [InlineKeyboardButton("Відкрити Footballistika", web_app=WebAppInfo(url=WEBAPP_URL))]
    ]
    await update.message.reply_text(
        "Тисни кнопку, щоб зайти у застосунок:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def debug_webapp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    url = "https://footballistika-web.vercel.app/index-debug.html"
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(text="Відкрити debug WebApp", web_app=WebAppInfo(url=url))]
        ]
    )
    await update.message.reply_text("Тест Telegram WebApp:", reply_markup=kb)


async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message:
        return
    user = update.effective_user
    user_id = user.id
    username = user.username or user.full_name or str(user.id)
    storage.ensure_user_record(user_id, username)
    text = message.text.strip()

    # Ongoing workflows first
    if context.user_data.get("awaiting_prediction_match"):
        return await handle_prediction_input(update, context)
    if context.user_data.get("admin_mode") == "adding_match":
        return await handle_admin_add_match_input(update, context)
    if context.user_data.get("admin_mode") == "entering_result":
        return await handle_admin_result_input(update, context)

    if text == PROFILE_BTN:
        return await send_webapp_button(update, context)
    if text == MAKE_PREDICTION_BTN:
        return await start_prediction_flow(update, context)
    if text == TABLE_BTN:
        return await show_leaderboard(update, context)
    if text == ADMIN_MENU_BTN and is_admin(user_id):
        context.user_data["admin_menu_open"] = True
        return await message.reply_text(
            "Адмін-режим активовано.",
            reply_markup=admin_keyboard(),
        )
    if text == BACK_BTN and context.user_data.get("admin_menu_open"):
        context.user_data["admin_menu_open"] = False
        context.user_data.pop("admin_mode", None)
        context.user_data.pop("admin_result_match", None)
        context.user_data.pop("add_match_state", None)
        context.user_data.pop("candidate_team1", None)
        context.user_data.pop("candidate_team2", None)
        return await message.reply_text(
            "Повертаю стандартне меню.",
            reply_markup=main_keyboard(is_admin(user_id)),
        )
    if text == ADMIN_ADD_MATCH_BTN and is_admin(user_id):
        context.user_data["admin_mode"] = "adding_match"
        context.user_data["add_match_state"] = "await_team1"
        context.user_data.pop("candidate_team1", None)
        context.user_data.pop("candidate_team2", None)
        return await message.reply_text(
            "Введи назву першої команди (або натисни Скасувати).",
            reply_markup=add_match_cancel_keyboard(),
        )
    if text == ADMIN_ENTER_RESULT_BTN and is_admin(user_id):
        return await prompt_next_result(update, context)
    if text == ADMIN_AVG_PREDICTION_BTN and is_admin(user_id):
        return await show_average_predictions(update, context)
    if text == ADMIN_ALL_PREDICTIONS_BTN and is_admin(user_id):
        return await show_all_predictions(update, context)
    if text == ADMIN_RESULT_ACCURACY_BTN and is_admin(user_id):
        return await show_result_accuracy(update, context)
    if text == ADMIN_GOAL_ACCURACY_BTN and is_admin(user_id):
        return await show_goal_accuracy(update, context)
    if text == USER_AVG_PREDICTION_BTN:
        return await show_average_predictions(update, context)
    if text == USER_ALL_PREDICTIONS_BTN:
        return await show_all_predictions(update, context)
    if text == USER_RESULT_ACCURACY_BTN:
        return await show_result_accuracy(update, context)
    if text == USER_GOAL_ACCURACY_BTN:
        return await show_goal_accuracy(update, context)

    await message.reply_text(
        "Не розпізнав команду. Натисни одну з кнопок нижче.",
        reply_markup=default_reply_markup(update, context),
    )


async def start_prediction_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_prediction_window_open():
        await update.message.reply_text(
            "Прогнози приймаємо до 17:59 за київським часом. Спробуй завтра.",
            reply_markup=main_keyboard(is_admin(user.id)),
        )
        return
    match = storage.get_next_match_for_prediction(user.id)
    if not match:
        context.user_data.pop("awaiting_prediction_match", None)
        await update.message.reply_text(
            "Ти зробив усі прогнози на актуальні матчі 🎉",
            reply_markup=main_keyboard(is_admin(user.id)),
        )
        return
    context.user_data["awaiting_prediction_match"] = match["id"]
    await update.message.reply_text(
        format_match_prompt(match)
        + "\nВведи рахунок у форматі 2:1",
        reply_markup=prediction_cancel_keyboard(),
    )


def format_match_prompt(match: dict) -> str:
    return f"Матч #{match['id']}: {match['team1']} vs {match['team2']}"


async def handle_prediction_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    user = update.effective_user
    match_id = context.user_data.get("awaiting_prediction_match")
    if not match_id:
        return
    if not is_prediction_window_open():
        context.user_data.pop("awaiting_prediction_match", None)
        await message.reply_text(
            "Прогнози приймаємо до 17:59 за київським часом. Спробуй завтра.",
            reply_markup=main_keyboard(is_admin(user.id)),
        )
        return
    text = (message.text or "").strip()
    text_lower = text.lower()
    if text == PREDICTION_CANCEL_BTN or text_lower in CANCEL_WORDS:
        context.user_data.pop("awaiting_prediction_match", None)
        await message.reply_text(
            "Скасував введення прогнозу.",
            reply_markup=main_keyboard(is_admin(user.id)),
        )
        return
    parsed = parse_score(text)
    if parsed is None:
        await message.reply_text(
            "Спробуй ще раз у форматі 2:1 (цілі числа).",
            reply_markup=prediction_cancel_keyboard(),
        )
        return
    score1, score2 = parsed
    existing = storage.get_user_prediction(match_id, user.id)
    if existing:
        await message.reply_text("Ти вже робив прогноз на цей матч.")
    else:
        storage.append_prediction(match_id, user.id, user.username or user.full_name, score1, score2)
        await message.reply_text(
            f"Зберіг прогноз {score1}:{score2}.",
        )
    context.user_data.pop("awaiting_prediction_match", None)
    await start_prediction_flow(update, context)


def parse_score(text: str) -> Optional[tuple[int, int]]:
    cleaned = text.replace(" ", "")
    if ":" not in cleaned:
        return None
    left, right = cleaned.split(":", 1)
    if not (left.isdigit() and right.isdigit()):
        return None
    return int(left), int(right)


async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    rows = storage.leaderboard_rows()
    if not rows:
        await update.message.reply_text(
            "Поки що ніхто не отримав балів.",
            reply_markup=main_keyboard(is_admin(user.id)),
        )
        return
    message_lines = ["Таблиця прогнозистів:"]
    for idx, (user_id, username, points) in enumerate(rows[:10], start=1):
        label = username if username != "None" else str(user_id)
        message_lines.append(f"{idx}. {label}: {points} балів")
    # Add current user position if outside top-10
    for position, (row_user_id, username, points) in enumerate(rows, start=1):
        if row_user_id == user.id and position > 10:
            message_lines.append(
                f"Твоє місце: {position} з {len(rows)} ( {points} балів )"
            )
            break
    await update.message.reply_text(
        "\n".join(message_lines),
        reply_markup=main_keyboard(is_admin(user.id)),
    )


async def handle_admin_add_match_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    text = (message.text or "").strip()
    text_lower = text.lower()
    if text == ADD_MATCH_CANCEL_BTN or text_lower in CANCEL_WORDS:
        await exit_admin_add_mode(update, context, "Створення матчу скасовано.")
        return
    state = context.user_data.get("add_match_state", "await_team1")

    if state == "await_team1":
        if not text:
            await message.reply_text(
                "Введи назву першої команди (текст не може бути порожнім).",
                reply_markup=add_match_cancel_keyboard(),
            )
            return
        context.user_data["candidate_team1"] = text
        context.user_data["add_match_state"] = "confirm_team1"
        await message.reply_text(
            f"Перша команда: {text}\nПідтвердити?",
            reply_markup=add_match_confirmation_keyboard(),
        )
        return

    if state == "confirm_team1":
        if text == ADD_MATCH_CONFIRM_BTN or is_yes(text_lower):
            context.user_data["add_match_state"] = "await_team2"
            await message.reply_text(
                "Добре. Введи назву другої команди.",
                reply_markup=add_match_cancel_keyboard(),
            )
            return
        if text == ADD_MATCH_REENTER_BTN or is_no(text_lower):
            context.user_data["add_match_state"] = "await_team1"
            context.user_data.pop("candidate_team1", None)
            await message.reply_text(
                "Ок, введи назву першої команди ще раз.",
                reply_markup=add_match_cancel_keyboard(),
            )
            return
        await message.reply_text(
            "Натисни одну з кнопок нижче.",
            reply_markup=add_match_confirmation_keyboard(),
        )
        return

    if state == "await_team2":
        if not text:
            await message.reply_text(
                "Назва другої команди не може бути порожньою.",
                reply_markup=add_match_cancel_keyboard(),
            )
            return
        context.user_data["candidate_team2"] = text
        context.user_data["add_match_state"] = "confirm_team2"
        await message.reply_text(
            f"Друга команда: {text}\nПідтвердити?",
            reply_markup=add_match_confirmation_keyboard(),
        )
        return

    if state == "confirm_team2":
        if text == ADD_MATCH_CONFIRM_BTN or is_yes(text_lower):
            context.user_data["add_match_state"] = "confirm_final"
            team1 = context.user_data.get("candidate_team1", "")
            team2 = context.user_data.get("candidate_team2", "")
            await message.reply_text(
                f"Створити матч {team1} vs {team2}?",
                reply_markup=add_match_confirmation_keyboard(),
            )
            return
        if text == ADD_MATCH_REENTER_BTN or is_no(text_lower):
            context.user_data["add_match_state"] = "await_team2"
            context.user_data.pop("candidate_team2", None)
            await message.reply_text(
                "Ок, введи назву другої команди ще раз.",
                reply_markup=add_match_cancel_keyboard(),
            )
            return
        await message.reply_text(
            "Натисни одну з кнопок нижче.",
            reply_markup=add_match_confirmation_keyboard(),
        )
        return

    if state == "confirm_final":
        if text == ADD_MATCH_CONFIRM_BTN or is_yes(text_lower):
            team1 = context.user_data.get("candidate_team1")
            team2 = context.user_data.get("candidate_team2")
            if not team1 or not team2:
                await message.reply_text(
                    "Не вистачає даних. Почнемо спочатку.",
                    reply_markup=add_match_cancel_keyboard(),
                )
                await restart_add_match_flow(update, context)
                return
            match = storage.add_match(team1, team2)
            await exit_admin_add_mode(
                update,
                context,
                f"Створив матч #{match['id']}: {team1} vs {team2}.",
            )
            return
        if text == ADD_MATCH_REENTER_BTN or is_no(text_lower):
            await message.reply_text(
                "Добре, почнемо спочатку. Введи назву першої команди.",
                reply_markup=add_match_cancel_keyboard(),
            )
            await restart_add_match_flow(update, context)
            return
        await message.reply_text(
            "Натисни одну з кнопок нижче.",
            reply_markup=add_match_confirmation_keyboard(),
        )
        return

    # fallback
    await restart_add_match_flow(update, context)
    await message.reply_text(
        "Сталася помилка стану. Почнемо знову: введи назву першої команди.",
        reply_markup=add_match_cancel_keyboard(),
    )


async def prompt_next_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    match = storage.get_next_pending_match_for_result()
    if not match:
        context.user_data.pop("admin_mode", None)
        context.user_data.pop("admin_result_match", None)
        await update.message.reply_text(
            "Немає матчів без результату.",
            reply_markup=admin_keyboard(),
        )
        return
    context.user_data["admin_mode"] = "entering_result"
    context.user_data["admin_result_match"] = match
    await update.message.reply_text(
        format_match_prompt(match) + "\nВведи фінальний рахунок у форматі 2:1",
        reply_markup=result_entry_keyboard(),
    )


async def handle_admin_result_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    match = context.user_data.get("admin_result_match")
    if not match:
        context.user_data.pop("admin_mode", None)
        await message.reply_text(
            "Не зміг знайти матч. Спробуй ще раз.",
            reply_markup=admin_keyboard(),
        )
        return
    text = (message.text or "").strip()
    text_lower = text.lower()
    if text == BACK_BTN or text_lower in CANCEL_WORDS:
        await exit_admin_result_mode(update, context, "Повертаю стандартні кнопки.")
        return
    parsed = parse_score(text)
    if parsed is None:
        await message.reply_text(
            "Спробуй ще раз у форматі 2:1 (тільки цифри).",
            reply_markup=result_entry_keyboard(),
        )
        return
    score1, score2 = parsed
    updated_match = storage.update_match_result(match["id"], score1, score2)
    if not updated_match:
        await message.reply_text(
            "Не вдалося оновити матч. Спробуй ще раз.",
            reply_markup=result_entry_keyboard(),
        )
        return
    awarded = storage.settle_match_points(match["id"], score1, score2)
    summary = f"Матч #{match['id']} оновлено: {score1}:{score2}."
    if awarded:
        summary += "\nНараховано бали:"
        for _, username, points in awarded:
            label = username if username != "None" else "користувач"
            summary += f"\n- {label}: {points}"
    else:
        summary += "\nНіхто не отримав балів."
    await message.reply_text(summary)
    # Prompt next pending match automatically
    await prompt_next_result(update, context)


async def show_average_predictions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = storage.average_predictions_per_match(include_finished=False)
    if not rows:
        await update.message.reply_text(
            "Ще немає прогнозів для розрахунку.",
            reply_markup=default_reply_markup(update, context),
        )
        return
    lines: List[str] = []
    for row in rows:
        match = row["match"]
        avg1 = row["avg1"]
        avg2 = row["avg2"]
        formatted = format_table(
            [[match["team1"], f"{avg1:.1f} : {avg2:.1f}", match["team2"]]]
        )
        lines.append(f"<pre>{formatted}    </pre>")
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=default_reply_markup(update, context),
        parse_mode=ParseMode.HTML,
    )


async def show_all_predictions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    matches = {match["id"]: match for match in storage.read_matches()}
    grouped: Dict[int, List[Dict]] = {}
    for entry in storage.read_predictions():
        match = matches.get(entry["match_id"])
        if not match or match.get("status") == "finished":
            continue
        grouped.setdefault(entry["match_id"], []).append(entry)
    if not grouped:
        await update.message.reply_text(
            "Немає прогнозів на матчі без результату.",
            reply_markup=default_reply_markup(update, context),
        )
        return
    lines: List[str] = []
    for match_id in sorted(grouped):
        records = sorted(grouped[match_id], key=lambda entry: entry["timestamp"])
        match = matches.get(match_id)
        if match:
            title = f"{match['team1']} vs {match['team2']}"
        else:
            title = f"Матч {match_id}"
        rows: List[List[str]] = [["Користувач", "Рахунок"]]
        for entry in records:
            username = entry["username"] or str(entry["user_id"])
            rows.append([username, f"{entry['pred_score1']}:{entry['pred_score2']}"])
        lines.append(title)
        lines.append(f"<pre>{format_table(rows)}</pre>")
    await update.message.reply_text(
        "\n\n".join(lines),
        reply_markup=default_reply_markup(update, context),
        parse_mode=ParseMode.HTML,
    )


async def show_result_accuracy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage.recalculate_prediction_quality()
    rows = storage.read_prediction_result_accuracy()
    if not rows:
        await update.message.reply_text(
            "Ще немає завершених матчів для статистики.",
            reply_markup=default_reply_markup(update, context),
        )
        return
    sorted_rows = sorted(rows, key=lambda row: row["result_accuracy_percent"], reverse=True)
    table: List[List[str]] = [["#", "Користувач", "Прогнози", "Точність"]]
    for idx, row in enumerate(sorted_rows, start=1):
        username = row["username"] or str(row["user_id"])
        table.append(
            [
                str(idx),
                username,
                str(row["predictions"]),
                f"{row['result_accuracy_percent']:.0f}%",
            ]
        )
    formatted = format_table(table)
    await update.message.reply_text(
        f"<pre>{formatted}</pre>",
        reply_markup=default_reply_markup(update, context),
        parse_mode=ParseMode.HTML,
    )


async def show_goal_accuracy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage.recalculate_prediction_quality()
    rows = storage.read_prediction_goal_accuracy()
    if not rows:
        await update.message.reply_text(
            "Ще немає завершених матчів для статистики.",
            reply_markup=default_reply_markup(update, context),
        )
        return
    sorted_rows = sorted(rows, key=lambda row: row["goal_accuracy_percent"], reverse=True)
    table: List[List[str]] = [["#", "Користувач", "Прогнози", "Точність"]]
    for idx, row in enumerate(sorted_rows, start=1):
        username = row["username"] or str(row["user_id"])
        table.append(
            [
                str(idx),
                username,
                str(row["predictions"]),
                f"{row['goal_accuracy_percent']:.0f}%",
            ]
        )
    formatted = format_table(table)
    await update.message.reply_text(
        f"<pre>{formatted}</pre>",
        reply_markup=default_reply_markup(update, context),
        parse_mode=ParseMode.HTML,
    )


def is_yes(text_lower: str) -> bool:
    return text_lower in YES_WORDS


def is_no(text_lower: str) -> bool:
    return text_lower in NO_WORDS


async def exit_admin_add_mode(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str) -> None:
    context.user_data.pop("admin_mode", None)
    context.user_data.pop("add_match_state", None)
    context.user_data.pop("candidate_team1", None)
    context.user_data.pop("candidate_team2", None)
    await update.message.reply_text(
        message,
        reply_markup=admin_keyboard(),
    )


async def restart_add_match_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["admin_mode"] = "adding_match"
    context.user_data["add_match_state"] = "await_team1"
    context.user_data.pop("candidate_team1", None)
    context.user_data.pop("candidate_team2", None)


async def exit_admin_result_mode(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str) -> None:
    context.user_data.pop("admin_mode", None)
    context.user_data.pop("admin_result_match", None)
    await update.message.reply_text(
        message,
        reply_markup=admin_keyboard(),
    )


def is_prediction_window_open(current_time: Optional[datetime] = None) -> bool:
    now_kyiv = current_time or datetime.now(KYIV_TZ)
    if now_kyiv.tzinfo is None:
        now_kyiv = now_kyiv.replace(tzinfo=KYIV_TZ)
    else:
        now_kyiv = now_kyiv.astimezone(KYIV_TZ)
    deadline = datetime.combine(now_kyiv.date(), PREDICTION_DEADLINE, KYIV_TZ)
    return now_kyiv <= deadline


def format_table(rows: List[List[str]]) -> str:
    if not rows:
        return ""
    col_count = len(rows[0])
    widths = [0] * col_count
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))
    formatted_rows = []
    for row in rows:
        padded = [cell.ljust(widths[idx]) for idx, cell in enumerate(row)]
        formatted_rows.append("  ".join(padded).rstrip())
    return "\n".join(formatted_rows)


def build_app() -> Application:
    if not TOKEN:
        raise RuntimeError("Не вказано TELEGRAM_BOT_TOKEN у середовищі або .env файлі.")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler(["app", "profile"], send_webapp_button))
    app.add_handler(CommandHandler("debug", debug_webapp))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
    return app


def main() -> None:
    app = build_app()
    logging.getLogger(__name__).info("Бот запущено.")
    app.run_polling()


if __name__ == "__main__":
    main()
