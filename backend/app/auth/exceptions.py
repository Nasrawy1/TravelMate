from starlette.exceptions import HTTPException as StarletteHTTPException


class AuthenticationError(StarletteHTTPException):
    """Raised when a request does not contain a valid access token."""

    def __init__(self) -> None:
        super().__init__(status_code=401, detail="Authentication required.")
