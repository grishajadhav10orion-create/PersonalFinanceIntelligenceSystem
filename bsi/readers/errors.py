"""Shared error for statements the app refuses to open because they are password-protected."""


class PasswordProtectedError(ValueError):
    """The file is encrypted / password-protected. Such files are rejected for safety (no password is ever requested)."""

    def __init__(self, kind: str = "file"):
        self.kind = kind
        super().__init__(f"This {kind} is password-protected. Password-protected statements are not accepted: "
                         "remove the protection (or export an unprotected copy from your bank) and upload it again.")
