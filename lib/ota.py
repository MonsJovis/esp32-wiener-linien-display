"""
Over-the-air update of the app: main.py, config.json and lib/*.py.

The MicroPython firmware itself stays as flashed; this replaces the Python
files it runs. Same shape as esp-flight-monitor's OTA:

- A release is a git tag. .github/workflows/release.yml publishes all files as
  one bundle plus manifest.json (version, size and SHA-256 per file) and
  manifest.sig, signed with the release key. lib/ota_key.py is its public half.
- Off unless config.json sets ota.manifest_url.
- Checked once a day (an hour after a failed check), installed only inside
  ota.install_hours, local time.
- TLS certificates are not verified (MicroPython has no CA bundle), so trust
  comes from the signature, not the connection: a manifest that does not
  verify, or a file that does not match its hash, is never installed.
- The new build boots on trial (boot.py) and keeps itself only after
  CONFIRM_AFTER_FETCHES good departure fetches. Otherwise boot.py restores the
  previous build and remembers the version as bad.

ota/state.json and the ota/new, ota/old layout are a contract with boot.py,
which is not part of the update. Changing them needs a USB deploy.
"""

import gc
import os
import binascii
import hashlib
import machine
import ujson
import utime

from lib.config import get_ota_config
from lib.init_wifi import get_timezone_offset
from lib.version import VERSION

STATE = 'ota/state.json'
NEW = 'ota/new/'
OLD = 'ota/old/'

FIRST_CHECK_DELAY_SEC = 5 * 60    # departures first, then the update check
CHECK_INTERVAL_SEC = 24 * 3600
RETRY_INTERVAL_SEC = 3600         # after a check or download that failed
CONFIRM_AFTER_FETCHES = 3         # ~2 minutes at the default update interval

HTTP_TIMEOUT_SEC = 15
MAX_REDIRECTS = 5                 # GitHub: latest -> tag -> release-assets host
MANIFEST_MAX = 8192
SIG_MAX = 1024
CHUNK = 1024
FREE_MARGIN = 32 * 1024


class Updater:
    """Call poll() once per fetch cycle and fetch_ok() after each good fetch."""

    def __init__(self):
        cfg = get_ota_config()
        self.manifest_url = cfg.get('manifest_url') or ''
        self.install_hours = cfg.get('install_hours', [3, 5])
        state = _load_state()
        self.trial = state.get('phase') == 'trial'
        self.bad = state.get('bad')
        self.pending = None
        self.next_check = utime.time() + FIRST_CHECK_DELAY_SEC
        self.good_fetches = 0
        print('ota: running {}{}{}'.format(
            VERSION, ' (trial)' if self.trial else '', '' if self.manifest_url else ', updates off'))

    def fetch_ok(self):
        """A departure fetch worked. Confirms a trial build after a few of them."""
        if not self.trial:
            return
        self.good_fetches += 1
        if self.good_fetches >= CONFIRM_AFTER_FETCHES:
            confirm()
            self.trial = False

    def poll(self, online, wdt=None):
        """
        Check for and install updates when due. Resets the device after an install.

        Call right after clear_cached_departures(): TLS needs that memory.
        """
        if not self.manifest_url or self.trial or not online:
            return
        now = utime.time()
        try:
            if self.pending is None and now >= self.next_check:
                ok = self._check(wdt)
                self.next_check = now + (CHECK_INTERVAL_SEC if ok else RETRY_INTERVAL_SEC)
            if self.pending is not None and self._in_install_window():
                self._install(wdt)
        except Exception as e:
            print('ota: {} {}'.format(type(e).__name__, e))
            self.pending = None
            self.next_check = now + RETRY_INTERVAL_SEC

    def _in_install_window(self):
        from lib.ota_policy import hour_in_window
        # Before NTP has answered the clock says 2000, and its hour means nothing.
        if utime.localtime()[0] < 2025:
            return False
        hour = utime.localtime(utime.time() + get_timezone_offset())[3]
        return hour_in_window(hour, self.install_hours[0], self.install_hours[1])

    def _check(self, wdt):
        """Fetch and verify the manifest. False when the check itself failed."""
        from lib.ota_key import N, E, K
        from lib.ota_policy import verify_signature, parse_manifest, version_cmp
        try:
            body = _get(self.manifest_url, MANIFEST_MAX, wdt)
            sig = _get(self.manifest_url.rsplit('/', 1)[0] + '/manifest.sig', SIG_MAX, wdt)
            if not verify_signature(body, sig, N, E, K):
                print('ota: manifest signature does not verify, ignoring it')
                return False
            manifest = parse_manifest(body)
        except Exception as e:
            print('ota: check failed: {} {}'.format(type(e).__name__, e))
            return False
        version = manifest['version']
        if version_cmp(version, VERSION) <= 0:
            print('ota: up to date ({}, latest {})'.format(VERSION, version))
        elif version == self.bad:
            print('ota: {} was rolled back before, skipping it'.format(version))
        else:
            print('ota: {} available, installing between {}:00 and {}:00'.format(
                version, self.install_hours[0], self.install_hours[1]))
            self.pending = manifest
        return True

    def _install(self, wdt):
        manifest = self.pending
        self.pending = None
        print('ota: downloading', manifest['version'])
        try:
            stage(manifest, wdt)
        except Exception as e:
            print('ota: download failed: {} {}'.format(type(e).__name__, e))
            _rmtree(NEW[:-1])
            self.next_check = utime.time() + RETRY_INTERVAL_SEC
            return
        print('ota: staged {}, restarting to install'.format(manifest['version']))
        machine.reset()


def stage(manifest, wdt=None):
    """
    Download the bundle into ota/new/, verify every file, write the journal.

    boot.py moves the files into place on the next boot.
    """
    _rmtree(NEW[:-1])
    _rmtree(OLD[:-1])
    total = sum(f['size'] for f in manifest['files'])
    free = _free_bytes()
    if free is not None and free < total + FREE_MARGIN:
        raise OSError('only {} bytes free for {}'.format(free, total))

    s, length = _open(manifest['bundle'], wdt)
    try:
        if length is not None and length != total:
            raise ValueError('bundle is {} bytes, manifest says {}'.format(length, total))
        for f in manifest['files']:
            path = NEW + f['path']
            _mkdirs(path)
            h = hashlib.sha256()
            left = f['size']
            with open(path, 'wb') as out:
                while left:
                    chunk = s.read(min(CHUNK, left))
                    if not chunk:
                        raise OSError('bundle ends early')
                    h.update(chunk)
                    out.write(chunk)
                    left -= len(chunk)
                    if wdt:
                        wdt.feed()
            if binascii.hexlify(h.digest()).decode() != f['sha256']:
                raise ValueError('hash mismatch: ' + f['path'])
    finally:
        s.close()

    # existed: tells boot.py whether a rollback restores the file or deletes it.
    files = [[f['path'], _exists(f['path'])] for f in manifest['files']]
    _save_state({'phase': 'staged', 'version': manifest['version'], 'files': files})


def confirm():
    """The trial build works: keep it and drop the backup."""
    _remove(STATE)
    _rmtree(OLD[:-1])
    print('ota: confirmed', VERSION)


# --- HTTPS --------------------------------------------------------------
#
# Not lib requests: in MicroPython 1.24 it keeps the first Host header across
# redirects, and GitHub redirects every release download to another host.

def _open(url, wdt=None):
    """GET over HTTPS, following redirects. Returns (socket, content_length or None)."""
    import socket
    for _ in range(MAX_REDIRECTS + 1):
        if not url.startswith('https://'):
            raise ValueError('not https: ' + url[:60])
        host, _, path = url[8:].partition('/')
        if wdt:
            wdt.feed()  # each hop can take a few 15 s timeouts
        gc.collect()
        ai = socket.getaddrinfo(host, 443, 0, socket.SOCK_STREAM)[0]
        s = socket.socket(ai[0], socket.SOCK_STREAM, ai[2])
        try:
            s.settimeout(HTTP_TIMEOUT_SEC)
            s.connect(ai[-1])
            s = _wrap_tls(s, host)
            s.write(('GET /{} HTTP/1.0\r\nHost: {}\r\nUser-Agent: esp-public-transport-screen\r\n'
                     'Connection: close\r\n\r\n').format(path, host).encode())
            status = int(s.readline().split(None, 2)[1])
            location = None
            length = None
            while True:
                line = s.readline()
                if not line or line == b'\r\n':
                    break
                lower = line.lower()
                if lower.startswith(b'location:'):
                    location = line[9:].strip().decode()
                elif lower.startswith(b'content-length:'):
                    length = int(line[15:].strip())
                elif lower.startswith(b'transfer-encoding:') and b'chunked' in lower:
                    raise OSError('chunked response')
        except BaseException:
            s.close()
            raise
        if status in (301, 302, 303, 307, 308) and location:
            s.close()
            url = location if location.startswith('https://') else 'https://' + host + location
            continue
        if status != 200:
            s.close()
            raise OSError('HTTP {} from {}'.format(status, host))
        return s, length
    raise OSError('too many redirects')


def _wrap_tls(sock, host):
    # Same as lib requests: no certificate check, see the module docstring.
    try:
        import tls
    except ImportError:  # MicroPython before 1.23
        import ssl
        return ssl.wrap_socket(sock, server_hostname=host)
    ctx = tls.SSLContext(tls.PROTOCOL_TLS_CLIENT)
    ctx.verify_mode = tls.CERT_NONE
    return ctx.wrap_socket(sock, server_hostname=host)


def _get(url, limit, wdt=None):
    """Whole body of a small file, at most `limit` bytes."""
    s, length = _open(url, wdt)
    try:
        if length is not None and length > limit:
            raise ValueError('{} bytes, limit {}'.format(length, limit))
        body = b''
        while True:
            chunk = s.read(CHUNK)
            if not chunk:
                break
            body += chunk
            if len(body) > limit:
                raise ValueError('more than {} bytes'.format(limit))
    finally:
        s.close()
    return body


# --- files ----------------------------------------------------------------

def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def _remove(path):
    if _exists(path):
        os.remove(path)


def _mkdirs(path):
    """Create the parent directories of a file path."""
    parts = path.split('/')[:-1]
    for i in range(1, len(parts) + 1):
        d = '/'.join(parts[:i])
        if not _exists(d):
            os.mkdir(d)


def _rmtree(path):
    if not _exists(path):
        return
    for name in os.listdir(path):
        child = path + '/' + name
        if os.stat(child)[0] & 0x4000:
            _rmtree(child)
        else:
            os.remove(child)
    os.rmdir(path)


def _free_bytes():
    try:
        st = os.statvfs('/')
        return st[1] * st[4]  # f_frsize * f_bavail
    except (AttributeError, OSError):
        return None


def _load_state():
    try:
        with open(STATE) as f:
            return ujson.load(f)
    except (OSError, ValueError):
        return {}


def _save_state(state):
    _mkdirs(STATE)
    with open(STATE + '.tmp', 'w') as f:
        ujson.dump(state, f)
    os.rename(STATE + '.tmp', STATE)
