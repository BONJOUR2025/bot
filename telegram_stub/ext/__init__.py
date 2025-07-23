class Filter:
    def __init__(self, name=None):
        self.name = name
    def __and__(self, other):
        return self

class Filters:
    TEXT = Filter('TEXT')
    @staticmethod
    def Regex(pattern):
        return Filter(f'Regex({pattern})')

filters = Filters()

class MessageHandler:
    def __init__(self, filters, callback):
        self.filters = filters
        self.callback = callback

class CallbackQueryHandler(MessageHandler):
    def __init__(self, callback, pattern=None):
        super().__init__(None, callback)
        self.pattern = pattern

class ConversationHandler:
    END = -1
    def __init__(self, *args, **kwargs):
        pass

class ContextTypes:
    DEFAULT_TYPE = object()
