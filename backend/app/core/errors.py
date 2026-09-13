class AppError(Exception):
    """Error que el cliente puede corregir o entender; `code` es estable para traducirlo en la web.

    La API lo responde como `{"detail": {"code", "message"}}` con `status_code`.
    """

    status_code = 422

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
