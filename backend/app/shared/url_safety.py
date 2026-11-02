from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlsplit, urlunsplit

ALLOWED_SCHEMES = frozenset({"http", "https"})

# Written to a response header or a JSON log line; anything else is attacker
# noise that survives JSON escaping and reaches a terminal.
CORRELATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

_TAG_LIKE = re.compile(r"</?[a-zA-Z][^>]{0,512}>")

# Cloud provider metadata endpoints. Reaching one of these from a server-side
# fetch is the single most common SSRF payoff, so it is named rather than left
# to the general private-range rule.
_BLOCKED_EXPLICITLY = frozenset(
    {
        "169.254.169.254",  # AWS/GCP/Azure/IMDS
        "169.254.170.2",  # ECS task role
        "metadata.google.internal",
        "metadata",
        "100.100.100.100",  # Alibaba Cloud metadata
    }
)


class UnsafeUrlError(ValueError):
    """Raised when a URL must not be fetched. Never silently skipped."""


def validate_service_base_url(raw: str, *, field: str = "base_url") -> str:
    """Pin a configured service endpoint to scheme + host, nothing else.

    Adapters append a fixed path (``/search``, ``/interpreter``). A configured
    value that smuggles a path, query or credentials would change which resource
    we actually request, and userinfo in a URL ends up in logs.

    Private hosts and ``http`` are allowed here on purpose: this application is
    local-first and SearXNG is expected to run at ``http://searxng:8080``. The
    untrusted-input rule is :func:`validate_discovered_target`, not this one.
    """
    if not raw or not isinstance(raw, str):
        raise UnsafeUrlError(f"{field} must be a non-empty string")

    parts = urlsplit(raw.strip())
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"{field} must use http or https")
    if not parts.hostname:
        raise UnsafeUrlError(f"{field} must include a host")
    if parts.username or parts.password:
        raise UnsafeUrlError(f"{field} must not embed credentials")

    path = parts.path.rstrip("/")
    if path or parts.query or parts.fragment:
        raise UnsafeUrlError(
            f"{field} must be a service origin without a path or query; "
            "the adapter appends its own endpoint"
        )

    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"


def _classify_ip(literal: str) -> bool:
    """True when the address itself is safe to fetch as a public target."""
    try:
        ip = ipaddress.ip_address(literal)
    except ValueError:
        return False
    if ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
        return False
    if ip.is_private:  # covers 10/8, 172.16/12, 192.168/16, 100.64/10 CGNAT
        return False
    return ip.is_global


def validate_discovered_target(
    raw: str | None, *, allow_private_networks: bool = False, timeout: float = 3.0
) -> str:
    """Approve or refuse a URL that came from outside content.

    This is the SSRF gate for the website crawler. Discovered URLs are attacker
    chosen, and the server fetching them is the classic path to cloud metadata,
    internal admin panels and localhost services — including a Redis or
    PostgreSQL that was never meant to be reachable over HTTP.

    Enforcement, in order: scheme must be http(s); no embedded credentials; the
    host must resolve to public addresses unless the operator explicitly opts
    out; every resolved address is checked, not just the first, so a host with
    one public and one loopback record cannot pass.

    ``allow_private_networks`` exists because a self-hosted crawler may
    legitimately crawl a LAN lab. It defaults to **False** — deny by default —
    and must be a deliberate configuration choice.
    """
    if not raw or not isinstance(raw, str):
        raise UnsafeUrlError("discovered target must be a non-empty string")

    candidate = raw.strip()
    parts = urlsplit(candidate)
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"scheme '{parts.scheme or 'none'}' is not fetchable")
    if not parts.hostname:
        raise UnsafeUrlError("target has no host")
    if parts.username or parts.password:
        raise UnsafeUrlError("target must not embed credentials")

    host = parts.hostname.lower()
    if host in _BLOCKED_EXPLICITLY:
        raise UnsafeUrlError(f"refusing to fetch metadata endpoint {host}")

    if allow_private_networks:
        return urlunsplit((parts.scheme.lower(), parts.netloc, parts.path, parts.query, ""))

    try:
        resolved = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"host {host!r} did not resolve") from exc

    literals = {str(entry[4][0]) for entry in resolved}
    if not literals:
        raise UnsafeUrlError(f"host {host!r} resolved to no addresses")

    for literal in literals:
        if literal in _BLOCKED_EXPLICITLY:
            raise UnsafeUrlError(f"host {host!r} resolves to a blocked address")
        if not _classify_ip(literal):
            raise UnsafeUrlError(
                f"host {host!r} resolves to a non-public address ({literal}); refusing the fetch"
            )

    return urlunsplit((parts.scheme.lower(), parts.netloc, parts.path, parts.query, ""))


def strip_markup(value: str | None) -> str | None:
    """Remove tag-shaped markup from text collected from pages.

    Not a sanitizer substitute for rendering — React escapes text already. This
    exists so stored records hold data rather than fragments of someone else's
    HTML, which would otherwise reappear in CSV exports and any future renderer
    that forgets to escape.
    """
    if value is None:
        return None
    cleaned = _TAG_LIKE.sub(" ", value)
    return cleaned if cleaned.strip() else None
