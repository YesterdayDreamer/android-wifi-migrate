class MigrationError(ValueError):
    """User-facing message; never include credentials or raw device output."""


class PasswordRequired(MigrationError):
    pass
