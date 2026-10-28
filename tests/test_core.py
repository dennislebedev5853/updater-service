"""Tests for updater-service.core.

A tiny services file is written to a temp path and the private registry builder
is pointed at it, so tests are independent of the host OS's /etc/services.
"""

import dataclasses
import os
import tempfile
import unittest

from updater_service import core
from updater_service.core import (
    ResolutionError,
    ServiceRecord,
    resolve,
    resolve_tcp,
    resolve_udp,
)

SAMPLE = """# Network services, Internet style
# Note that it is presently the policy of IANA to assign a single well-known
# port number for both tcp and udp; hence, officially there are no separate
# entries for udp.

echo            7/tcp
echo            7/udp
discard         9/tcp           sink null
ftp            21/tcp           fsp fspd
ssh            22/tcp           ssh
telnet         23/tcp
smtp           25/tcp           mail
http           80/tcp           www www-http
ntp            123/tcp          ntpd
ntp            123/udp
bogus          -1/tcp
weird          70000/udp
noproto        80
"""


class _RegistryStub:
    """Swaps core._REGISTRY for a controlled one and restores it on teardown."""

    def __init__(self, registry):
        self._saved = core._REGISTRY
        core._REGISTRY = registry

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        core._REGISTRY = self._saved


def _stub_from_file(text):
    with tempfile.NamedTemporaryFile(
        mode="w", suffix="_services", delete=False, encoding="ascii"
    ) as handle:
        handle.write(text)
        path = handle.name
    registry = core._build_registry(path)
    os.unlink(path)
    return registry


class TestParseLine(unittest.TestCase):
    def test_basic(self):
        names, port, proto = core._parse_line("http 80/tcp www")
        self.assertEqual(names, ("http", "www"))
        self.assertEqual(port, 80)
        self.assertEqual(proto, "tcp")

    def test_no_aliases(self):
        names, port, proto = core._parse_line("ssh 22/tcp")
        self.assertEqual(names, ("ssh",))
        self.assertEqual(port, 22)

    def test_inline_comment(self):
        names, port, proto = core._parse_line("http 80/tcp www # HTTP")
        self.assertEqual(names, ("http", "www"))

    def test_missing_protocol_raises(self):
        with self.assertRaises(ValueError):
            core._parse_line("bad 80")

    def test_non_numeric_port_raises(self):
        with self.assertRaises(ValueError):
            core._parse_line("bad x/tcp")


class TestBuildRegistry(unittest.TestCase):
    def setUp(self):
        self.reg = _stub_from_file(SAMPLE)

    def test_first_wins_on_duplicate(self):
        record = self.reg[("echo", "tcp")]
        self.assertEqual(record.name, "echo")
        self.assertEqual(record.port, 7)

    def test_alias_points_to_same_record(self):
        primary = self.reg[("http", "tcp")]
        alias = self.reg[("www", "tcp")]
        self.assertIs(primary, alias)

    def test_protocol_separated(self):
        self.assertEqual(self.reg[("echo", "tcp")].port, 7)
        self.assertEqual(self.reg[("echo", "udp")].port, 7)

    def test_aliases_propagate(self):
        record = self.reg[("discard", "tcp")]
        self.assertEqual(record.aliases, ("sink", "null"))

    def test_skips_negative_port(self):
        self.assertNotIn(("bogus", "tcp"), self.reg)

    def test_skips_out_of_range_port(self):
        self.assertNotIn(("weird", "udp"), self.reg)

    def test_skips_missing_protocol(self):
        self.assertNotIn(("noproto", "tcp"), self.reg)


class TestResolve(unittest.TestCase):
    def setUp(self):
        self._stub = _RegistryStub(_stub_from_file(SAMPLE))
        self._stub.__enter__()

    def tearDown(self):
        self._stub.__exit__(None, None, None)

    def test_basic_lookup(self):
        r = resolve("http", "tcp")
        self.assertEqual(r.name, "http")
        self.assertEqual(r.port, 80)
        self.assertEqual(r.protocol, "tcp")

    def test_case_insensitive(self):
        upper = resolve("HTTP", "TCP")
        lower = resolve("http", "tcp")
        self.assertEqual(upper.port, lower.port)

    def test_alias_lookup(self):
        r = resolve("www", "tcp")
        self.assertEqual(r.name, "http")
        self.assertEqual(r.port, 80)

    def test_missing_raises(self):
        with self.assertRaises(ResolutionError):
            resolve("nope", "tcp")

    def test_wrong_protocol_raises(self):
        with self.assertRaises(ResolutionError):
            resolve("http", "udp")


class TestShorthands(unittest.TestCase):
    def setUp(self):
        self._stub = _RegistryStub(_stub_from_file(SAMPLE))
        self._stub.__enter__()

    def tearDown(self):
        self._stub.__exit__(None, None, None)

    def test_tcp_shorthand(self):
        self.assertEqual(resolve_tcp("ftp").port, 21)

    def test_udp_shorthand(self):
        self.assertEqual(resolve_udp("echo").port, 7)

    def test_shorthand_raises_on_wrong_protocol(self):
        with self.assertRaises(ResolutionError):
            resolve_udp("ftp")


class TestServiceRecord(unittest.TestCase):
    def test_str_format(self):
        record = ServiceRecord(name="ssh", port=22, protocol="tcp")
        self.assertEqual(str(record), "ssh/tcp")

    def test_frozen(self):
        record = ServiceRecord(name="ssh", port=22, protocol="tcp")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            record.port = 23


class TestLazyLoading(unittest.TestCase):
    def test_get_registry_populates_once(self):
        core._REGISTRY = None
        reg = core._get_registry()
        self.assertIsNotNone(core._REGISTRY)
        self.assertIs(reg, core._REGISTRY)


class TestUnknownServiceFile(unittest.TestCase):
    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            core._build_registry("/nonexistent/path/services")


if __name__ == "__main__":
    unittest.main()
