"""Small shared localization helpers for the current Persian RTL UI foundation."""

DEFAULT_LOCALE = "fa-IR"
DEFAULT_LANGUAGE = "fa"
DEFAULT_DIRECTION = "rtl"

MESSAGES = {
    "auth.invalid_credentials": "نام کاربری یا گذرواژه نادرست است.",
}


def t(message_key, default=None):
    """Return a localized message for a stable message key."""
    return MESSAGES.get(message_key, default if default is not None else message_key)
