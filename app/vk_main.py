"""Entrypoint for running the (future) VK bot — a third process alongside
app.main (Telegram) and uvicorn (API/admin), same idea as the "app"/"main"
commands the project already runs.

This is intentionally a placeholder, not a full duplicate of the Telegram
scenarios: it only registers everyone who messages the community into
vk_bot_users.json (mirrors app/handlers/user/start.py's touch() call for
Telegram) so an admin can already link VK contacts to employee profiles on
the "Доступы" page (see app/api/vk_bot_users.py) before any real dialogue
flow is built. Actual scenarios (shift check-in, salary, etc.) come later.

Requires VK_API_TOKEN in .env — a community (group) access token with the
`messages` scope, from VK's group management → API usage → Access tokens.
Uses VK's Bot Long Poll API (vkbottle), which needs no public webhook URL,
matching how the Telegram bot runs via long polling.
"""

from vkbottle.bot import Bot, Message

from .config import VK_API_TOKEN
from .data.vk_bot_user_repository import get_vk_bot_user_repository
from .utils.logger import log, log_connection

bot = Bot(token=VK_API_TOKEN)


async def _register_contact(message: Message) -> None:
    screen_name = first_name = last_name = None
    try:
        users = await bot.api.users.get(user_ids=[message.from_id], fields=["screen_name"])
        if users:
            user = users[0]
            screen_name = getattr(user, "screen_name", None)
            first_name = getattr(user, "first_name", None)
            last_name = getattr(user, "last_name", None)
    except Exception as exc:
        # A failed profile lookup shouldn't stop the contact from being
        # recorded — link it with just the id, same as Telegram's touch()
        # tolerates a missing username.
        log(f"⚠️ [vk_bot] Не удалось получить профиль {message.from_id}: {exc}")
    get_vk_bot_user_repository().touch(
        message.from_id, screen_name=screen_name, first_name=first_name, last_name=last_name,
    )


@bot.on.message()
async def handle_any_message(message: Message) -> None:
    await _register_contact(message)
    await message.answer("Здравствуйте! Этот бот пока в разработке — сценарии появятся позже.")


def main() -> None:
    if not VK_API_TOKEN:
        log("⚠️ VK_API_TOKEN не задан в .env — VK-бот не запущен")
        return
    log("🚀 VK bot started and waiting for messages...")
    log_connection("VK bot process started (long poll)")
    bot.run_forever()


if __name__ == "__main__":
    main()
