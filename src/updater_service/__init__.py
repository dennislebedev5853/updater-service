"""updater-service: resolve IANA service names to canonical ports and protocols."""

from updater_service.core import (
    ResolutionError,
    ServiceRecord,
    resolve,
    resolve_tcp,
    resolve_udp,
)

__all__ = [
    "ResolutionError",
    "ServiceRecord",
    "resolve",
    "resolve_tcp",
    "resolve_udp",
]
