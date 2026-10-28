"""Resolve IANA service names to ports and protocols from /etc/services.

This module reads the operating system's built-in services file and provides a
typed lookup for service names. A single static registry is built lazily on
first use, then cached for the life of the process.
"""

from __future__ import annotations

import dataclasses
from typing import Dict, Tuple

DEFAULT_SERVICES_PATH = "/etc/services"


class ResolutionError(KeyError):
    """Raised when a service name (and optional protocol) cannot be resolved.

    Subclassing KeyError keeps dict-style ``port = services[name]`` ergonomics
    without hiding the cause when callers ask for something the file does not
    define.
    """


@dataclasses.dataclass(frozen=True)
class ServiceRecord:
    """A single resolved entry from /etc/services.

    Attributes:
        name: Canonical service name as listed.
        port: Numeric port assigned by IANA.
        protocol: Transport protocol (typically "tcp" or "udp").
        aliases: Alternative names that also map to this record.
    """

    name: str
    port: int
    protocol: str
    aliases: Tuple[str, ...] = ()

    def __str__(self) -> str:
        return f"{self.name}/{self.protocol}"


def _parse_line(line: str) -> Tuple[Tuple[str, ...], int, str]:
    """Parse one logical /etc/services line.

    Format per the file's own comment header:
        service-name  port/protocol  [aliases ...]

    Comments (``#``) and blank lines are stripped by the caller, but inline
    comments are handled here defensively in case a file has them.
    Returns a tuple of (names_tuple, port, protocol).
    """
    hash_pos = line.find("#")
    if hash_pos != -1:
        line = line[:hash_pos]
    parts = line.split()
    if len(parts) < 2:
        raise ValueError("line too short")
    name = parts[0]
    port_proto = parts[1]
    # The "/" splits port from protocol; the standard mandates the slash but
    # some files omit the protocol on a few entries. We require it because
    # the entire purpose of this library is protocol-aware resolution.
    if "/" not in port_proto:
        raise ValueError(f"missing protocol separator in {port_proto!r}")
    port_str, proto = port_proto.split("/", 1)
    try:
        port = int(port_str)
    except ValueError as exc:
        raise ValueError(f"invalid port {port_str!r}") from exc
    if not (0 <= port <= 65535):
        raise ValueError(f"port out of range: {port}")
    proto = proto.lower()
    aliases = tuple(parts[2:])
    names = (name,) + aliases
    return names, port, proto


def _build_registry(path: str = DEFAULT_SERVICES_PATH) -> Dict[Tuple[str, str], ServiceRecord]:
    """Read the services file and build a lookup keyed by (name, protocol).

    Both the canonical name and every alias are inserted as keys, each pointing
    to the same ServiceRecord. If a name/protocol pair appears twice, the first
    entry wins -- IANA's canonical listing is first in the standard file, so
    shadowing it would be surprising.
    """
    registry: Dict[Tuple[str, str], ServiceRecord] = {}
    with open(path, "r", encoding="ascii", errors="replace") as handle:
        for raw_line in handle:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                names, port, proto = _parse_line(stripped)
            except ValueError:
                continue
            key = (names[0], proto)
            if key in registry:
                continue
            record = ServiceRecord(
                name=names[0],
                port=port,
                protocol=proto,
                aliases=names[1:],
            )
            for n in names:
                registry[(n, proto)] = record
    return registry


# Lazily populated on first lookup so that importing the module never touches
# the filesystem. A plain module-level dict with a None sentinel avoids the
# overhead of threading.Lock for the overwhelmingly common case where the
# lookup is called after import time has already completed.
_REGISTRY: Dict[Tuple[str, str], ServiceRecord] | None = None


def _get_registry() -> Dict[Tuple[str, str], ServiceRecord]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    return _REGISTRY


def resolve(service: str, protocol: str) -> ServiceRecord:
    """Look up ``service`` for the given ``protocol``.

    The name match is case-insensitive; the protocol match is also
    case-insensitive. Raises :class:`ResolutionError` if no entry exists.
    """
    key = (service.lower(), protocol.lower())
    record = _get_registry().get(key)
    if record is None:
        raise ResolutionError(
            f"no service named {service!r} for protocol {protocol!r}"
        )
    return record


def resolve_tcp(service: str) -> ServiceRecord:
    """Shorthand for ``resolve(service, 'tcp')``."""
    return resolve(service, "tcp")


def resolve_udp(service: str) -> ServiceRecord:
    """Shorthand for ``resolve(service, 'udp')``."""
    return resolve(service, "udp")
