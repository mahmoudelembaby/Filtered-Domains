"""SSRF protection: block private/internal targets before any outbound fetch."""
import ipaddress
import socket
import asyncio

BLOCKED_SUFFIXES = (".internal", ".local", ".lan", ".corp", ".home", ".localhost")
BLOCKED_EXACT = {"localhost"}

# Explicit cloud-metadata + link-local that must never be fetched
BLOCKED_IPS = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("169.254.169.253"),
    ipaddress.ip_address("0.0.0.0"),
}


class SSRFError(ValueError):
    pass


def _ip_is_blocked(ip: ipaddress._BaseAddress) -> bool:
    if ip in BLOCKED_IPS:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def check_hostname_syntax(host: str) -> None:
    h = (host or "").strip().lower().rstrip(".")
    if not h or h in BLOCKED_EXACT:
        raise SSRFError(f"blocked host: {host!r}")
    if " " in h or "/" in h:
        raise SSRFError(f"blocked host: {host!r}")
    if h.endswith(BLOCKED_SUFFIXES):
        raise SSRFError(f"blocked internal name: {host!r}")
    if "." not in h:  # single-label => internal/mDNS
        raise SSRFError(f"blocked single-label host: {host!r}")


async def resolve_and_validate(host: str) -> list[str]:
    """Resolve host and reject if ANY resolved IP is non-public. Mitigates DNS rebinding."""
    check_hostname_syntax(host)
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, None)
    except socket.gaierror as e:
        raise SSRFError(f"dns resolution failed for {host!r}: {e}")
    ips: list[str] = []
    for _fam, _type, _proto, _canon, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            raise SSRFError(f"bad resolved IP {ip_str!r}")
        if _ip_is_blocked(ip):
            raise SSRFError(f"blocked resolved IP {ip_str} for {host!r}")
        ips.append(ip_str)
    if not ips:
        raise SSRFError(f"no addresses for {host!r}")
    return ips
