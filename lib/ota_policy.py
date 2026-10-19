"""
Decisions for the over-the-air update: is the manifest genuine and well-formed,
is the release newer, may it be installed at this hour.

No network, no files, no machine module: tools/release.py and tests/ run this
exact code on the host, so the release is checked by the same rules the
device applies. The plumbing (HTTPS, flash writes, trial boot) is lib/ota.py
and boot.py.
"""

import hashlib
import json

# DER prefix of a SHA-256 DigestInfo (RFC 8017, section 9.2, note 1).
_SHA256_DIGEST_INFO = (
    b'\x30\x31\x30\x0d\x06\x09\x60\x86\x48\x01\x65\x03\x04\x02\x01\x05\x00\x04\x20'
)


def verify_signature(data, sig, n, e, k):
    """
    Check an RSA PKCS#1 v1.5 SHA-256 signature, as `openssl dgst -sha256 -sign` writes it.

    n, e: public key. k: key length in bytes (MicroPython ints have no
    bit_length(), so lib/ota_key.py stores it).
    """
    if len(sig) != k:
        return False
    s = int.from_bytes(sig, 'big')
    if s >= n:
        return False
    t = _SHA256_DIGEST_INFO + hashlib.sha256(data).digest()
    em = b'\x00\x01' + b'\xff' * (k - len(t) - 3) + b'\x00' + t
    return pow(s, e, n) == int.from_bytes(em, 'big')


def _version_parts(version):
    """'v1.2.3-4-gabc-dirty' -> [1, 2, 3]. Stops at the first non-numeric part."""
    if version.startswith('v'):
        version = version[1:]
    parts = []
    for part in version.split('.'):
        digits = ''
        for c in part:
            if not '0' <= c <= '9':
                break
            digits += c
        if not digits:
            break
        parts.append(int(digits))
        if len(digits) < len(part):
            break
    return parts


def version_cmp(a, b):
    """
    Compare two version strings like strcmp: <0, 0 or >0.

    Numeric per component, so 1.10.0 is newer than 1.9.0. A leading "v" and a
    git describe suffix are ignored: "v1.2.0-3-gabc" compares as 1.2.0, so a
    USB deploy made after the v1.2.0 tag is replaced by v1.2.1, not by v1.2.0.
    """
    pa = _version_parts(a)
    pb = _version_parts(b)
    while len(pa) < len(pb):
        pa.append(0)
    while len(pb) < len(pa):
        pb.append(0)
    return (pa > pb) - (pa < pb)


def path_allowed(path):
    """
    What an update may write: main.py and lib/*.py.

    Never boot.py (the rollback lives there and must survive any update),
    never config.json or secrets.json (the device's own, see lib/config.py),
    never anything under ota/.
    """
    if path == 'main.py':
        return True
    return (isinstance(path, str) and path.startswith('lib/') and path.endswith('.py')
            and len(path) > 7 and '/' not in path[4:])


def parse_manifest(body):
    """
    Parse and validate manifest.json. Raises ValueError on anything malformed.

        {"version": "1.2.0",
         "bundle": "https://.../app-1.2.0.bin",
         "files": [{"path": "main.py", "size": 6438, "sha256": "<64 hex>"}, ...]}

    The bundle is every file concatenated in this order; the sizes split it.
    """
    manifest = json.loads(body)
    if not isinstance(manifest, dict):
        raise ValueError('manifest is not an object')
    version = manifest.get('version')
    if not isinstance(version, str) or not _version_parts(version):
        raise ValueError('bad version')
    bundle = manifest.get('bundle')
    if not isinstance(bundle, str) or not bundle.startswith('https://'):
        raise ValueError('bundle must be an https URL')
    files = manifest.get('files')
    if not isinstance(files, list) or not files:
        raise ValueError('no files')
    seen = []
    for f in files:
        if not isinstance(f, dict):
            raise ValueError('bad file entry')
        path = f.get('path')
        size = f.get('size')
        sha = f.get('sha256')
        if not path_allowed(path) or path in seen:
            raise ValueError('path not allowed: {}'.format(path))
        if not isinstance(size, int) or size < 0:
            raise ValueError('bad size: {}'.format(path))
        if not isinstance(sha, str) or len(sha) != 64:
            raise ValueError('bad sha256: {}'.format(path))
        seen.append(path)
    return manifest


def hour_in_window(hour, start, end):
    """Is hour in [start, end)? Wraps midnight: (23, 2) covers 23, 0 and 1."""
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end
