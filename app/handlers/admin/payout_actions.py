"""Admin payout actions.

This module handles approving and denying payout requests. It logs each
decision to ``logs/payout_actions.log`` and warns if a matching request
cannot be found or updated.
"""

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.ext import ContextTypes, ConversationHandler
from telegram.error import BadRequest, Forbidden
import logging
from pathlib import Path

from ...constants import UserStates
from ...core.enums import PAYOUT_STATUSES
from ...config import (
    ADMIN_ID,
    ADMIN_CHAT_ID,
    CARD_DISPATCH_CHAT_ID,
    CARD_DISPATCH_CHATS,
    DEFAULT_CARD_DISPATCH_CHAT_KEY,
)
from ...services.users import load_users_map
from ...keyboards.reply_admin import get_admin_menu
from ...services.advance_requests import (
    load_advance_requests,
    save_advance_requests,
    update_request_status,
)
from ...utils.logger import log
from ...utils import is_valid_user_id

logger = logging.getLogger(__name__)


audit_logger = logging.getLogger("payout_actions")
if not audit_logger.handlers:
    Path("logs").mkdir(exist_ok=True)
    handler = logging.FileHandler("logs/payout_actions.log", encoding="utf-8")
    formatter = logging.Formatter("[%(asctime)s] %(message)s")
    handler.setFormatter(formatter)
    audit_logger.addHandler(handler)
    audit_logger.setLevel(logging.INFO)

PENDING_STATUSES = {PAYOUT_STATUSES[0]}


def _resolve_cashier_chat(
    user_id: str, users: dict[str, dict] | None
) -> tuple[int | None, str, str | None]:
    """Return target cashier chat id, display name and key for the user."""
    user_info = users.get(str(user_id), {}) if isinstance(users, dict) else {}
    key = user_info.get("payout_chat_key") if isinstance(user_info, dict) else None

    if key:
        for chat in CARD_DISPATCH_CHATS:
            if str(chat.get("key")) == str(key):
                name = chat.get("name") or str(key)
                try:
                    chat_id = int(chat.get("chat_id"))
                except (TypeError, ValueError):
                    continue
                return chat_id, str(name), str(key)

    if CARD_DISPATCH_CHATS:
        default_chat = CARD_DISPATCH_CHATS[0]
        name = default_chat.get("name") or str(default_chat.get("key"))
        try:
            chat_id = int(default_chat.get("chat_id"))
        except (TypeError, ValueError):
            chat_id = None
        return chat_id, str(name), str(default_chat.get("key"))

    if CARD_DISPATCH_CHAT_ID:
        return CARD_DISPATCH_CHAT_ID, "Основной кассир", DEFAULT_CARD_DISPATCH_CHAT_KEY

    return None, "", None


async def allow_payout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    payout_id = int(query.data.split("_")[-1])
    log(f"✅ [allow_payout] Одобрение выплаты для payout_id: {payout_id}")

    payouts = load_advance_requests()
    logger.debug(f"[allow_payout] Все ID в базе: {[p['id'] for p in payouts]}")

    request_to_approve = next(
        (p for p in payouts if int(p.get("id", 0)) == payout_id),
        None,
    )
    if not request_to_approve:
        logger.warning(f"Не найден запрос на одобрение {payout_id}")
        await query.edit_message_text("❌ Нет активного запроса для одобрения.")
        return
    status = request_to_approve.get("status")
    if status != PAYOUT_STATUSES[0]:
        logger.warning(
            f"[allow_payout] Запрос {payout_id} имеет статус '{status}', ожидался 'Ожидает'"
        )
        await query.edit_message_text("❌ Запрос уже обработан.")
        return

    user_id = request_to_approve["user_id"]
    log(
        f"📋 [allow_payout] Найден запрос {request_to_approve['id']} для user_id {user_id}"
    )

    try:
        updated = update_request_status(payout_id, "approved")
    except Exception as e:
        log(f"❌ Ошибка обновления статуса выплаты: {e}")
        updated = False

    if updated:
        log(f"✅ [allow_payout] Статус запроса {request_to_approve['id']} обновлён")
        audit_logger.info(
            f"✏️ Выплата {request_to_approve['id']} обновлена — статус: Одобрено"
        )
    else:
        log(f"⚠️ [allow_payout] Не удалось обновить запрос {request_to_approve['id']}")
        audit_logger.warning(
            f"Не удалось обновить запрос {request_to_approve['id']} пользователя {user_id}"
        )

    payout_type = request_to_approve.get("payout_type") or "Не указано"
    method = request_to_approve.get("method") or ""
    force_notify_cashier = bool(request_to_approve.get("force_notify_cashier"))
    should_notify_cashier = method in {"💳 На карту", "🤝 Наличными"} or force_notify_cashier
    cashier_chat_id: int | None = None
    cashier_chat_name = ""
    cashier_chat_key: str | None = None
    users_map = load_users_map()
    if should_notify_cashier:
        cashier_chat_id, cashier_chat_name, cashier_chat_key = _resolve_cashier_chat(
            user_id, users_map
        )
    is_bot_user = bool(users_map.get(str(user_id), {}).get("bot_user"))

    user_message = (
        f"✅ Ваш запрос на выплату одобрен!\n"
        f"Тип: {payout_type}\n"
        f"Сумма: {request_to_approve['amount']} ₽\n"
        f"Метод: {method or 'Не указан'}"
    )
    if is_valid_user_id(user_id) and is_bot_user:
        log(
            f"[Telegram] sending approval notice to {user_id} — text: '{user_message[:50]}'"
        )
        try:
            await context.bot.send_message(chat_id=user_id, text=user_message)
        except (BadRequest, Forbidden) as e:
            log(f"❌ Failed to send message to chat {user_id} — {e}")
            # Do not interrupt the payout process if user notification fails
    else:
        log(
            f"⚠️ Skipping approval notice — user {user_id} is not marked as a bot user"
        )

    current_text = query.message.text
    updated_text = f"{current_text}\n\n✅ Одобрено"
    if should_notify_cashier:
        if cashier_chat_name:
            display_name = cashier_chat_name
            if cashier_chat_key and cashier_chat_key != cashier_chat_name:
                display_name = f"{cashier_chat_name} ({cashier_chat_key})"
            updated_text += f"\n📬 Чат кассира: {display_name}"
        elif cashier_chat_key:
            updated_text += f"\n📬 Чат кассира: {cashier_chat_key}"
        elif not cashier_chat_id:
            updated_text += "\n⚠️ Чат кассира не настроен"
    log(
        f"[Telegram] editing message {query.message.message_id} in {query.message.chat.id}"
    )
    try:
        await query.edit_message_text(text=updated_text)
    except BadRequest as e:
        log(
            f"❌ Failed to edit message {query.message.message_id} in chat {query.message.chat.id} — {e}"
        )
        # Editing message is optional; continue without raising

    if should_notify_cashier:
        contact_value = (
            request_to_approve.get("card_number")
            or request_to_approve.get("phone")
            or ""
        )
        bank_value = request_to_approve.get("bank") or ""
        header = "📤 Запрос на перевод"
        if cashier_chat_name:
            header += f" — {cashier_chat_name}"
        elif cashier_chat_key:
            header += f" — {cashier_chat_key}"
        lines = [
            f"{header}:",
            "",
            f"👤 {request_to_approve['name']}",
        ]
        if contact_value:
            contact_label = "💳" if method == "💳 На карту" else "📞"
            lines.append(f"{contact_label} {contact_value}")
        if bank_value:
            lines.append(f"🏦 {bank_value}")
        lines.append(f"💰 {request_to_approve['amount']} ₽")
        lines.append(f"📂 {payout_type}")
        if method:
            lines.append(f"🔄 Способ: {method}")
        cashier_text = "\n".join(lines)
        if (
            request_to_approve.get("note")
            and request_to_approve.get("show_note_in_bot")
        ):
            cashier_text += f"\n\n📝 {request_to_approve['note']}"
        cashier_buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📤 Отправлено", callback_data=f"mark_sent_{request_to_approve['id']}_{user_id}"
                    )
                ]
            ]
        )
        target_label = cashier_chat_name or cashier_chat_key or str(cashier_chat_id)
        if not cashier_chat_id:
            log(
                f"⚠️ [allow_payout] Не указан чат кассира для пользователя {user_id}; уведомление не отправлено"
            )
        else:
            log(
                f"[Telegram] sending cashier notice to {target_label} — text: '{cashier_text[:50]}'"
            )
            try:
                await context.bot.send_message(
                    chat_id=cashier_chat_id,
                    text=cashier_text,
                    reply_markup=cashier_buttons,
                )
                log(
                    f"📨 [allow_payout] Сообщение кассиру отправлено для user_id: {user_id}"
                )
            except BadRequest as e:
                log(
                    f"❌ Failed to send message to chat {cashier_chat_id} — {e}"
                )
                # Continue even if the cashier chat is missing
            except Exception as e:
                log(f"❌ [allow_payout] Ошибка отправки кассиру: {e}")


async def deny_payout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    payout_id = query.data.split("_")[-1]
    log(f"❌ [deny_payout] Отклонение выплаты для payout_id: {payout_id}")

    payout_requests = load_advance_requests()
    request_to_deny = next(
        (
            r
            for r in payout_requests
            if str(r.get("id")) == str(payout_id)
            and r.get("status") in PENDING_STATUSES
        ),
        None,
    )
    if not request_to_deny:
        log(f"⚠️ [deny_payout] Запрос {payout_id} не найден")
        audit_logger.warning(f"Не найден запрос на отклонение {payout_id}")
        await query.edit_message_text("❌ Нет активного запроса для отклонения.")
        return

    log(
        f"📋 [deny_payout] Найден запрос {request_to_deny['id']} для user_id {request_to_deny['user_id']}"
    )

    user_id = request_to_deny["user_id"]

    try:
        updated = update_request_status(payout_id, "rejected")
    except Exception as e:
        log(f"❌ Ошибка обновления статуса выплаты: {e}")
        updated = False

    if updated:
        log(f"✅ [deny_payout] Статус запроса {request_to_deny['id']} обновлён")
        audit_logger.info(
            f"✏️ Выплата {request_to_deny['id']} обновлена — статус: Отклонено"
        )
    else:
        log(f"⚠️ [deny_payout] Не удалось обновить запрос {request_to_deny['id']}")
        audit_logger.warning(
            f"Не удалось обновить запрос {request_to_deny['id']} пользователя {user_id}"
        )

    payout_type = request_to_deny.get("payout_type") or "Не указано"
    user_message = (
        f"❌ Ваш запрос на выплату отклонён.\n"
        f"Тип: {payout_type}\n"
        f"Сумма: {request_to_deny['amount']} ₽\n"
        f"Метод: {request_to_deny['method']}"
    )
    users_map = load_users_map()
    is_bot_user = bool(users_map.get(str(user_id), {}).get("bot_user"))
    if is_valid_user_id(user_id) and is_bot_user:
        log(f"[Telegram] sending denial notice to {user_id} — text: '{user_message[:50]}'")
        try:
            await context.bot.send_message(chat_id=user_id, text=user_message)
        except (BadRequest, Forbidden) as e:
            log(f"❌ Failed to send message to chat {user_id} — {e}")
            # Do not interrupt the payout process if user notification fails
    else:
        log(
            f"⚠️ Skipping denial notice — user {user_id} is not marked as a bot user"
        )

    current_text = query.message.text
    updated_text = f"{current_text}\n\n❌ Отклонено"
    log(
        f"[Telegram] editing message {query.message.message_id} in {query.message.chat.id}"
    )
    try:
        await query.edit_message_text(text=updated_text, reply_markup=None)
    except BadRequest as e:
        log(
            f"❌ Failed to edit message {query.message.message_id} in chat {query.message.chat.id} — {e}"
        )
        raise


async def reset_payout_request(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    chat_id = update.effective_chat.id
    state = context.application.chat_data.get(chat_id, {}).get("conversation")
    log(f"[FSM] state before entry: {state}")
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text(
            "❌ У вас нет прав для выполнения этой команды."
        )
        return

    payout_requests = load_advance_requests()
    if not payout_requests:
        await update.message.reply_text(
            "📭 Нет запросов в файле для сброса.",
            reply_markup=get_admin_menu(),
        )
        return

    pending_requests = [
        req for req in payout_requests if req.get("status") in PENDING_STATUSES
    ]
    reset_details = []

    if pending_requests:
        for req in pending_requests:
            req["status"] = "Отменено"
            update_request_status(req["id"], "cancelled")
            reset_details.append(
                f"👤 {req['name']} (ID: {req['user_id']})\n"
                f"Сумма: {req['amount']} ₽\n"
                f"Метод: {req['method']}\n"
                f"Тип: {req.get('payout_type', 'Не указано')}"
            )
        save_advance_requests(payout_requests)
        log(
            f"✅ [reset_payout_request] Сброшено {len(pending_requests)} запросов из файла: {reset_details}"
        )
    else:
        log("⚠️ [reset_payout_request] Нет активных запросов в файле.")

    users = load_users_map()
    reset_users = []
    persistence = getattr(context.application, "persistence", None)
    for uid in users.keys():
        user_data = persistence.get_user_data().get(int(uid), {}) if persistence else {}
        if user_data and "payout_in_progress" in user_data:
            reset_users.append(f"👤 {users[uid].get('name', 'Неизвестно')} (ID: {uid})")
            user_data.pop("payout_in_progress", None)
            user_data.pop("payout_data", None)
            if persistence:
                persistence.update_user_data(int(uid), user_data)

    message_lines = []
    if pending_requests:
        message_lines.append(f"✅ Сброшено {len(pending_requests)} запросов из файла:")
        message_lines.extend(
            [f"Запрос #{i+1}:\n{detail}" for i, detail in enumerate(reset_details)]
        )
    else:
        message_lines.append("📭 Нет активных запросов в файле.")

    if reset_users:
        message_lines.append(f"\n✅ Очищено {len(reset_users)} зависших состояний:")
        message_lines.extend(
            [f"Пользователь #{i+1}: {user}" for i, user in enumerate(reset_users)]
        )
    else:
        message_lines.append("\n📭 Нет зависших состояний у пользователей.")

    reset_message = "\n\n".join(message_lines)
    await update.message.reply_text(reset_message, reply_markup=get_admin_menu())
    log(f"✅ [reset_payout_request] Завершён сброс: {reset_message}")


async def mark_sent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    payout_id = parts[2] if len(parts) >= 4 else None
    user_id = parts[-1]

    if payout_id:
        from app.data.payout_repository import PayoutRepository
        try:
            PayoutRepository().update(payout_id, {"status": "Выплачено"})
            log(f"✅ [mark_sent] Выплата {payout_id} → Выплачено")
        except Exception as e:
            log(f"❌ [mark_sent] Не удалось обновить статус выплаты {payout_id}: {e}")

    current_text = query.message.text
    updated_text = f"{current_text}\n\n📤 Отправлено"
    log(
        f"[Telegram] editing message {query.message.message_id} in {query.message.chat.id}"
    )
    try:
        await query.edit_message_text(updated_text)
    except BadRequest as e:
        log(
            f"❌ Failed to edit message {query.message.message_id} in chat {query.message.chat.id} — {e}"
        )
        raise
