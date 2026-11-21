"""Shared request identity for published browser resource capabilities."""

from urllib.parse import urlsplit, urlunsplit


def normalize_request_url(url: str) -> str:
    """Normalize case, default ports and fragments without merging targets.

    IPv6 brackets delimit the hostname from a non-default port. Removing them
    would make one address/port pair collide with a different IPv6 address.
    Paths and queries remain exact parts of the authorization identity.
    """
    split = urlsplit(url)
    scheme = split.scheme.lower()
    host = (split.hostname or "").lower()
    if ":" in host:
        host = f"[{host}]"
    default_port = {"http": 80, "https": 443}.get(scheme)
    port = split.port
    netloc = host if port is None or port == default_port else f"{host}:{port}"
    return urlunsplit((scheme, netloc, split.path, split.query, ""))
