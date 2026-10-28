# updater-service

Resolves IANA service names to their canonical port numbers and protocols using the operating system's built-in services file.

```python
from updater_service import resolve, resolve_tcp, resolve_udp, ResolutionError

try:
    record = resolve_tcp("https")
    print(record.name, record.port, record.protocol)
except ResolutionError:
    print("not found")
```

`ServiceRecord` is a frozen dataclass with `name`, `port`, `protocol`, and `aliases` fields.

## Why this exists

Reading `/etc/services` directly every time you need a port is easy to get wrong: the file has comments, inline comments, aliases, duplicate entries, and the occasional malformed line. This library parses that file once, builds a lookup keyed by `(name, protocol)`, and returns typed records. It touches no network, depends on nothing outside the standard library, and works in containers with `/etc/services` present.

The trade-off: the library trusts whatever the host operating system shipped in `/etc/services`. If an entry is missing from the file, `resolve` raises `ResolutionError` — there is no bundled fallback table. This keeps the library tiny and avoids shipping a second source of truth that drifts from IANA.

## Edge cases

- **Case-insensitive:** both the service name and protocol are matched case-insensitively.
- **Aliases:** every alias in the services file is inserted as a key pointing at the same record, so `resolve("www", "tcp")` returns the record whose canonical name is `http`.
- **Duplicates:** the first occurrence of a name/protocol pair wins, matching IANA's convention of listing the canonical entry first.
- **Malformed lines** (negative ports, out-of-range ports, missing protocol separator) are skipped silently rather than raising, so a broken line in the file does not take down lookups for everything else.
