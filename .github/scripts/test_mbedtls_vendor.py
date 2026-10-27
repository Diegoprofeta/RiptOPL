"""mbedTLS is vendored from its 3.6.7 release archive under Apache-2.0, for RA builds only.

The RA edition looks games up on retroachievements.org over HTTPS (ORBIT parity). TLS comes from
mbedTLS, taken under Apache-2.0 so RiptOPL keeps no GPL code. Only RA builds may compile or link it,
and only five pinned roots are trusted. The expected root fingerprints are written here, checked
against the Mozilla root store when vendored, so a wrong DER can't pass with a matching README. Ported from the original with this refresh; the
Makefile check became a check of tools/build_edition.py's edition definitions and tools/assets.py.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MBED = ROOT / "third_party/mbedtls"
ROOTS = ROOT / "third_party/ca-roots"

# Issuer roots (Google Trust Services, ISRG), SHA-256 of the DER.
PINNED = {
    "gtsr1.der": "d947432abde7b7fa90fc2e6b59101b1280e0e1c7e4e40fa3c6887fff57a7f4cf",
    "gtsr3.der": "34d8a73ee208d9bcdb0d956520934b4e40e69482596e8b6f73c8426b010a6f48",
    "gtsr4.der": "349dfa4058c5e263123b398ae795573c4e1313c83fe68f93556cd5e8031b3c7d",
    "isrgrootx1.der": "96bcec06264976f37460779acf28c5a7cfe8a3c0aae11a8ffcee05c0bddf08c6",
    "isrg-root-x2.der": "69729b8e15a86efc177a57afb7171dfc64add28c2fca8cf1507e34453ccb1470",
}

readme = (MBED / "README.md").read_text(encoding="utf-8") if (MBED / "README.md").exists() else None
assert readme is not None, "third_party/mbedtls/README.md missing"
assert "3.6.7" in readme and re.search(r"\b[0-9a-f]{64}\b", readme), "README must name 3.6.7 and the archive SHA-256"
assert "Used under the Apache-2.0 licence." in readme
assert (MBED / "LICENSE").is_file()
# Generated sources only the release archive carries (not the git tag).
assert (MBED / "library/psa_crypto_driver_wrappers_no_static.c").is_file()
assert (MBED / "library/error.c").is_file()
for source in sorted((MBED / "library").glob("*.c")):
    head = source.read_text(encoding="utf-8", errors="replace")[:2000]
    assert re.search(r"SPDX-License-Identifier:.*Apache-2\.0", head), f"{source.name}: no Apache-2.0 SPDX line"

# Only the RA edition compiles or links mbedTLS, the TLS client or the roots.
sys.path.insert(0, str(ROOT / "tools"))
import build_edition  # noqa: E402

pattern = re.compile(r"mbedtls|ratls", re.I)
for edition in build_edition.EDITIONS:
    for configuration in build_edition.CONFIGURATIONS:
        try:
            config = build_edition.definition(edition, configuration)
        except ValueError:
            continue  # a combination build_configuration.py refuses
        text = json.dumps(config)
        if build_edition.EDITIONS[edition]["ra"]:
            targets = {t["name"]: t for t in config["targets"]}
            assert targets["mbedtls"]["type"] == "ee_lib"
            assert targets["mbedtls"]["sources"] == ["third_party/mbedtls/library/*.c"]
            main = targets["riptopl"]
            assert "mbedtls" in main["libs"]
            assert {"src/platform/ratls.c", "src/sources/ratls_ps2.cpp"} <= set(main["sources"])
            assert targets["mbedtls"]["defines"] == [r'MBEDTLS_CONFIG_FILE=\"riptopl_mbedtls_config.h\"']
            assert {"third_party/mbedtls/include", "third_party/mbedtls"} <= set(main["include_dirs"])
            assert '#define MBEDTLS_CONFIG_FILE "riptopl_mbedtls_config.h"' in (ROOT / "include/ratls.h").read_text()
        else:
            assert not pattern.search(text), f"{edition}/{configuration} names mbedTLS or ratls"
# The roots are embedded by tools/assets.py for RA alone.
assets = (ROOT / "tools/assets.py").read_text(encoding="utf-8")
ra_branch = assets[assets.index('    if os.environ.get("RIPTOPL_RA") == "1":'):]
ra_branch = ra_branch[:ra_branch.index("\n    for a in pngs:")]
assert "third_party/ca-roots" in ra_branch and assets.count("ca-roots") == 1
assert '"ratls_root_" + der.stem.replace("-", "")' in ra_branch

# Five pinned roots, nothing else. GTS Root R2 is gone: Mozilla's store dropped it (certifi
# 2026.10.18), so it is not trusted here.
assert sorted(p.name for p in ROOTS.glob("*.der")) == sorted(PINNED)
roots_readme = (ROOTS / "README.md").read_text(encoding="utf-8")
for name, expected in PINNED.items():
    assert hashlib.sha256((ROOTS / name).read_bytes()).hexdigest() == expected, name
    assert expected in roots_readme.replace(":", "").lower(), f"{name}: README lists another fingerprint"

config = (MBED / "riptopl_mbedtls_config.h").read_text(encoding="utf-8")
for wanted in ("MBEDTLS_SSL_PROTO_TLS1_3", "MBEDTLS_SSL_PROTO_TLS1_2", "MBEDTLS_ENTROPY_HARDWARE_ALT",
               "MBEDTLS_PLATFORM_TIME_ALT", "MBEDTLS_SSL_CLI_C", "MBEDTLS_X509_CRT_PARSE_C"):
    assert re.search(rf"^#define {wanted}\b", config, re.M), wanted
for unwanted in ("MBEDTLS_SSL_SRV_C", "MBEDTLS_FS_IO", "MBEDTLS_SSL_RENEGOTIATION", "MBEDTLS_NET_C",
                 "MBEDTLS_TIMING_C", "MBEDTLS_DEBUG_C"):
    assert not re.search(rf"^#define {unwanted}\b", config, re.M), unwanted

print("PASS: mbedTLS 3.6.7 vendored (Apache-2.0), RA-only, five pinned roots")
