"""Helpers for keeping credentials out of logs."""

from urllib.parse import urlsplit, urlunsplit


def redact_url(url: str) -> str:
    """Hide the password/token in a connection URL.

    ``rediss://default:TOKEN@host:6379`` -> ``rediss://default:***@host:6379``.
    Anything that isn't a parseable URL with credentials is returned unchanged.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<unparseable url>"
    if "@" not in parts.netloc:
        return url
    userinfo, _, host = parts.netloc.rpartition("@")
    user = userinfo.split(":", 1)[0]
    return urlunsplit(parts._replace(netloc=f"{user}:***@{host}"))
