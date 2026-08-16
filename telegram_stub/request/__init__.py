class HTTPXRequest:
    """Stub of telegram.request.HTTPXRequest.

    app/services/telegram_service.py imports this at module level, so without
    it any test that (even transitively) imports the API package failed to
    collect. It is only ever constructed and handed to the Application
    builder in tests, never used to make a request.
    """

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    async def do_request(self, url, method, *args, **kwargs):
        """Точка, которую переопределяет RetryingHTTPXRequest.

        В боевом PTB здесь живёт сам HTTP-вызов; тесты подменяют этот метод,
        чтобы проверить логику повторов, не выходя в сеть.
        """
        raise NotImplementedError("подмените do_request в тесте")
