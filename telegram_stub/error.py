class TelegramError(Exception):
    pass


class BadRequest(TelegramError):
    pass


class Forbidden(TelegramError):
    pass


class NetworkError(TelegramError):
    pass


# Иерархия повторяет настоящую: в python-telegram-bot TimedOut — наследник
# NetworkError. Раньше в стабе он наследовал TelegramError напрямую, и код,
# который ловит NetworkError, в тестах выглядел сломанным, хотя в бою работал.
class TimedOut(NetworkError):
    pass


class RetryAfter(TelegramError):
    def __init__(self, retry_after=0):
        super().__init__(f"Flood control exceeded. Retry in {retry_after} seconds")
        self.retry_after = retry_after
