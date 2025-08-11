class Bot:
    def __init__(self, token, request=None):
        self.token = token
        self.request = request

    async def edit_message_text(self, *args, **kwargs):
        pass

    async def send_message(self, *args, **kwargs):
        pass

class Chat:
    def __init__(self, id=None, type=None):
        self.id = id
        self.type = type


class User:
    def __init__(self, id=None, is_bot=False, first_name=None):
        self.id = id
        self.is_bot = is_bot
        self.first_name = first_name


class Message:
    def __init__(self, message_id=None, chat=None, date=None, text=None, from_user=None):
        self.message_id = message_id
        self.chat = chat
        self.date = date
        self.text = text
        self.from_user = from_user

    @classmethod
    def de_json(cls, data, bot):
        chat_data = data.get("chat") or {}
        from_data = data.get("from") or {}
        return cls(
            message_id=data.get("message_id"),
            chat=Chat(chat_data.get("id"), chat_data.get("type")),
            date=data.get("date"),
            text=data.get("text"),
            from_user=User(from_data.get("id"), from_data.get("is_bot"), from_data.get("first_name")),
        )

    async def reply_text(self, *args, **kwargs):
        pass

class CallbackQuery:
    def __init__(self, id=None, from_user=None, chat_instance=None, data=None, message=None):
        self.id = id
        self.from_user = from_user
        self.chat_instance = chat_instance
        self.data = data
        self.message = Message.de_json(message or {}, None)

    @classmethod
    def de_json(cls, payload, bot):
        return cls(
            id=payload.get("id"),
            from_user=payload.get("from"),
            chat_instance=payload.get("chat_instance"),
            data=payload.get("data"),
            message=payload.get("message"),
        )

    async def answer(self, *args, **kwargs):
        pass

    async def edit_message_text(self, *args, **kwargs):
        pass

class Update:
    def __init__(self, update_id=None, message=None, callback_query=None):
        self.update_id = update_id
        self.message = message
        self.callback_query = callback_query

    @classmethod
    def de_json(cls, data, bot):
        message = data.get("message")
        return cls(update_id=data.get("update_id"), message=Message.de_json(message, bot) if message else None)

    @property
    def effective_chat(self):
        if self.message:
            return self.message.chat
        if self.callback_query:
            return self.callback_query.message.chat
        return None

    @property
    def effective_user(self):
        if self.message:
            return self.message.from_user
        if self.callback_query:
            return self.callback_query.from_user
        return None


class ReplyKeyboardMarkup:
    def __init__(self, keyboard, resize_keyboard=False, one_time_keyboard=False):
        self.keyboard = keyboard


class ReplyKeyboardRemove:
    pass


class InlineKeyboardButton:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


class InlineKeyboardMarkup:
    def __init__(self, keyboard):
        self.inline_keyboard = keyboard


class BadRequest(Exception):
    pass
