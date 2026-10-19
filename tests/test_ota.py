"""
Host tests for the OTA update: policy, release tool, staging, boot.py.

    python3 -m unittest discover tests

Needs openssl for the throwaway signing key. The device modules run against
stubs for machine/utime/ujson/ntptime in a temporary "device" directory.
"""

import hashlib
import io
import json
import os
import pathlib
import runpy
import subprocess
import sys
import tempfile
import time
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))

# MicroPython modules the device code imports.
sys.modules.setdefault('ujson', json)
sys.modules.setdefault('ntptime', types.ModuleType('ntptime'))
utime_stub = types.ModuleType('utime')
utime_stub.time = time.time
utime_stub.sleep = time.sleep
utime_stub.localtime = time.gmtime
utime_stub.mktime = lambda t: int(time.mktime(t[:6] + (0, 0, 0)))
sys.modules.setdefault('utime', utime_stub)
machine_stub = types.ModuleType('machine')
machine_stub.resets = 0
machine_stub.wdt_timeouts = []


def _reset():
    machine_stub.resets += 1


class _WDT:
    def __init__(self, timeout):
        machine_stub.wdt_timeouts.append(timeout)

    def feed(self):
        pass


machine_stub.reset = _reset
machine_stub.WDT = _WDT
sys.modules.setdefault('machine', machine_stub)

from lib import ota_policy  # noqa: E402
import release  # noqa: E402


class Key:
    """Throwaway RSA key, made with openssl the way the release workflow signs."""

    def __init__(self, directory):
        self.pem = pathlib.Path(directory) / 'test_signing_key.pem'
        subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt',
                        'rsa_keygen_bits:2048', '-out', str(self.pem)],
                       check=True, capture_output=True)
        out = subprocess.run(['openssl', 'rsa', '-in', str(self.pem), '-noout', '-modulus'],
                             check=True, capture_output=True, text=True).stdout
        hex_n = out.strip().split('=', 1)[1]
        self.N = int(hex_n, 16)
        self.E = 65537
        self.K = len(hex_n) // 2

    def sign(self, path):
        """Writes manifest.sig next to manifest.json and returns it."""
        sig = path.with_suffix('.sig')
        subprocess.run(['openssl', 'dgst', '-sha256', '-sign', str(self.pem), '-out', str(sig),
                        str(path)], check=True, capture_output=True)
        return sig.read_bytes()


def setUpModule():
    global KEY, KEY_DIR
    KEY_DIR = tempfile.TemporaryDirectory()
    KEY = Key(KEY_DIR.name)


def tearDownModule():
    KEY_DIR.cleanup()


def manifest_for(files, version='1.2.0', bundle='https://example.org/app.bin'):
    return {
        'version': version,
        'bundle': bundle,
        'files': [{'path': p, 'size': len(d), 'sha256': hashlib.sha256(d).hexdigest()}
                  for p, d in files],
    }


class PolicyTest(unittest.TestCase):

    def test_version_cmp(self):
        cmp = ota_policy.version_cmp
        self.assertGreater(cmp('1.10.0', '1.9.0'), 0)
        self.assertEqual(cmp('v1.2.0', '1.2.0'), 0)
        self.assertEqual(cmp('1.2', '1.2.0'), 0)
        self.assertEqual(cmp('1.2.0-3-gabcdef1-dirty', '1.2.0'), 0)
        self.assertGreater(cmp('1.2.1', '1.2.0-3-gabcdef1'), 0)
        self.assertGreater(cmp('1.0.0', '0.0.0-27b0b5a'), 0)
        self.assertLess(cmp('0.9.9', '1.0.0'), 0)

    def test_signature(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / 'manifest.json'
            path.write_bytes(b'{"version": "1.2.0"}')
            sig = KEY.sign(path)
        verify = ota_policy.verify_signature
        self.assertTrue(verify(b'{"version": "1.2.0"}', sig, KEY.N, KEY.E, KEY.K))
        self.assertFalse(verify(b'{"version": "9.9.9"}', sig, KEY.N, KEY.E, KEY.K))
        broken = bytes([sig[0] ^ 1]) + sig[1:]
        self.assertFalse(verify(b'{"version": "1.2.0"}', broken, KEY.N, KEY.E, KEY.K))
        self.assertFalse(verify(b'{"version": "1.2.0"}', sig[:-1], KEY.N, KEY.E, KEY.K))

    def test_parse_manifest(self):
        good = manifest_for([('main.py', b'x'), ('lib/a.py', b'y'), ('config.json', b'{}')])
        self.assertEqual(ota_policy.parse_manifest(json.dumps(good))['version'], '1.2.0')

        def bad(**change):
            m = manifest_for([('main.py', b'x')])
            m.update(change)
            with self.assertRaises(ValueError):
                ota_policy.parse_manifest(json.dumps(m))

        bad(version='latest')
        bad(bundle='http://example.org/app.bin')
        bad(files=[])
        for path in ['boot.py', 'secrets.json', 'ota/state.json', 'lib/sub/a.py', '/main.py',
                     'lib/a.mpy']:
            bad(files=[{'path': path, 'size': 1, 'sha256': '0' * 64}])
        bad(files=[{'path': 'main.py', 'size': -1, 'sha256': '0' * 64}])
        bad(files=[{'path': 'main.py', 'size': 1, 'sha256': 'abc'}])
        bad(files=[{'path': 'main.py', 'size': 1, 'sha256': '0' * 64}] * 2)

    def test_hour_in_window(self):
        inside = ota_policy.hour_in_window
        self.assertEqual([h for h in range(24) if inside(h, 3, 5)], [3, 4])
        self.assertEqual([h for h in range(24) if inside(h, 23, 2)], [0, 1, 23])
        self.assertEqual([h for h in range(24) if inside(h, 4, 4)], [])


class ReleaseTest(unittest.TestCase):

    def test_build_and_verify(self):
        with tempfile.TemporaryDirectory() as d:
            out = pathlib.Path(d)
            release.build('v1.2.3', 'https://example.org/releases/download/v1.2.3', out)
            KEY.sign(out / 'manifest.json')
            release.verify(out, KEY)

            manifest = json.loads((out / 'manifest.json').read_text())
            paths = [f['path'] for f in manifest['files']]
            self.assertEqual(paths[:2], ['main.py', 'config.json'])
            self.assertIn('lib/ota.py', paths)
            self.assertIn('lib/version.py', paths)
            self.assertNotIn('boot.py', paths)
            self.assertEqual(manifest['bundle'],
                             'https://example.org/releases/download/v1.2.3/app-1.2.3.bin')

            # Wrong key: refused before anything is published.
            other = types.SimpleNamespace(N=KEY.N - 2, E=KEY.E, K=KEY.K)
            with self.assertRaises(SystemExit):
                release.verify(out, other)

    def test_build_refuses_bad_tag(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(SystemExit):
            release.build('1.2.3', 'https://example.org', pathlib.Path(d))


class DeviceTest(unittest.TestCase):
    """lib/ota.py stages, boot.py installs, confirms or rolls back."""

    OLD_FILES = {'main.py': b'old main', 'config.json': b'{}', 'lib/ota.py': b'old ota',
                 'lib/gone.py': b'only in the old build', 'secrets.json': b'secret',
                 'boot.py': b'not touched'}
    NEW_FILES = [('main.py', b'new main ' * 300), ('config.json', b'{"ota": {}}'),
                 ('lib/ota.py', b'new ota'), ('lib/added.py', b'only in the new build')]

    def setUp(self):
        self.cwd = os.getcwd()
        self.dir = tempfile.TemporaryDirectory()
        os.chdir(self.dir.name)
        for path, data in self.OLD_FILES.items():
            os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
            pathlib.Path(path).write_bytes(data)
        sys.modules.pop('lib.ota', None)
        from lib import ota
        self.ota = ota
        self.manifest = manifest_for(self.NEW_FILES)
        bundle = b''.join(d for _, d in self.NEW_FILES)
        ota._open = lambda url, wdt=None: (io.BytesIO(bundle), len(bundle))

    def tearDown(self):
        os.chdir(self.cwd)
        self.dir.cleanup()

    def files(self):
        out = {}
        for base, _, names in os.walk('.'):
            for name in names:
                path = os.path.join(base, name)[2:]
                if not path.startswith('ota/'):
                    out[path] = pathlib.Path(path).read_bytes()
        return out

    def state(self):
        try:
            return json.loads(pathlib.Path('ota/state.json').read_text())
        except FileNotFoundError:
            return None

    def boot(self):
        runpy.run_path(str(ROOT / 'boot.py'))

    def expected_new(self):
        expected = dict(self.OLD_FILES)
        expected.update(dict(self.NEW_FILES))
        return expected

    def test_install_and_confirm(self):
        self.ota.stage(self.manifest)
        self.assertEqual(self.state()['phase'], 'staged')
        self.assertEqual(self.files(), self.OLD_FILES)  # nothing live changes before the reboot

        self.boot()
        self.assertEqual(self.files(), self.expected_new())
        self.assertEqual(self.state()['phase'], 'trial')
        self.assertEqual(self.state()['boots'], 1)
        self.assertEqual(machine_stub.wdt_timeouts[-1], 120000)

        self.ota.confirm()
        self.assertIsNone(self.state())
        self.assertFalse(os.path.exists('ota/old'))
        self.boot()
        self.assertEqual(self.files(), self.expected_new())

    def test_rollback_after_three_unconfirmed_boots(self):
        self.ota.stage(self.manifest)
        for _ in range(3):
            self.boot()
            self.assertEqual(self.files(), self.expected_new())
        self.boot()
        self.assertEqual(self.files(), self.OLD_FILES)
        self.assertEqual(self.state(), {'bad': '1.2.0'})
        self.boot()  # nothing left to do
        self.assertEqual(self.files(), self.OLD_FILES)

    def test_offline_restarts_do_not_roll_back_until_their_own_limit(self):
        boot_py = runpy.run_path(str(ROOT / 'boot.py'))
        self.ota.stage(self.manifest)
        self.boot()
        for _ in range(boot_py['MAX_OFFLINE_BOOTS']):
            self.ota.mark_offline()  # main.py: stale restart or failed Wi-Fi
            self.boot()
            self.assertEqual(self.files(), self.expected_new())
        self.assertEqual(self.state()['boots'], 1)
        self.ota.mark_offline()
        self.boot()
        self.assertEqual(self.files(), self.OLD_FILES)
        self.assertEqual(self.state(), {'bad': '1.2.0'})

    def test_crashes_still_roll_back_between_offline_restarts(self):
        self.ota.stage(self.manifest)
        for _ in range(3):
            self.boot()
            self.ota.mark_offline()
            self.boot()
        self.assertEqual(self.files(), self.expected_new())
        self.boot()  # fourth boot not after an offline reset
        self.assertEqual(self.files(), self.OLD_FILES)

    def test_mark_offline_outside_a_trial_writes_nothing(self):
        self.ota.mark_offline()
        self.assertIsNone(self.state())

    def test_interrupted_install_and_rollback_finish_on_next_boot(self):
        self.ota.stage(self.manifest)
        # Power cut after the first file was backed up, before it was replaced.
        os.makedirs('ota/old', exist_ok=True)
        os.rename('main.py', 'ota/old/main.py')
        self.boot()
        self.assertEqual(self.files(), self.expected_new())

        state = self.state()
        state['boots'] = 3
        pathlib.Path('ota/state.json').write_text(json.dumps(state))
        self.boot()
        self.assertEqual(self.files(), self.OLD_FILES)
        # Power cut halfway through the rollback: running it again changes nothing.
        pathlib.Path('ota/state.json').write_text(json.dumps(dict(state, phase='rollback')))
        self.boot()
        self.assertEqual(self.files(), self.OLD_FILES)

    def test_corrupt_bundle_is_never_staged(self):
        self.manifest['files'][1]['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            self.ota.stage(self.manifest)
        self.assertIsNone(self.state())
        self.boot()
        self.assertEqual(self.files(), self.OLD_FILES)

    def test_short_bundle_is_never_staged(self):
        bundle = b''.join(d for _, d in self.NEW_FILES)[:-1]
        self.ota._open = lambda url, wdt=None: (io.BytesIO(bundle), None)
        with self.assertRaises(OSError):
            self.ota.stage(self.manifest)
        self.assertIsNone(self.state())

    def test_updater_checks_and_installs_only_in_the_window(self):
        pathlib.Path('config.json').write_text(json.dumps(
            {'ota': {'manifest_url': 'https://example.org/latest/manifest.json',
                     'install_hours': [3, 5]}}))
        sys.modules.pop('lib.config', None)
        sys.modules.pop('lib.ota', None)
        from lib import ota

        body = json.dumps(self.manifest).encode()
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / 'manifest.json'
            path.write_bytes(body)
            sig = KEY.sign(path)
        served = {'https://example.org/latest/manifest.json': body,
                  'https://example.org/latest/manifest.sig': sig,
                  'https://example.org/app.bin': b''.join(d for _, d in self.NEW_FILES)}
        ota._open = lambda url, wdt=None: (io.BytesIO(served[url]), len(served[url]))
        sys.modules['lib.ota_key'] = types.SimpleNamespace(N=KEY.N, E=KEY.E, K=KEY.K)
        hour = {'value': 14}
        ota.get_timezone_offset = lambda: 0
        utime_stub.localtime = lambda t=None: time.gmtime(t)[:3] + (hour['value'],) + time.gmtime(t)[4:]

        try:
            updater = ota.Updater()
            updater.next_check = 0
            resets = machine_stub.resets
            updater.poll(True)
            self.assertEqual(updater.pending['version'], '1.2.0')  # found at 14:00 ...
            self.assertEqual(machine_stub.resets, resets)            # ... but not installed
            hour['value'] = 3
            updater.poll(True)
            self.assertEqual(machine_stub.resets, resets + 1)
            self.assertEqual(self.state()['phase'], 'staged')

            # A tampered manifest is ignored, and retried in an hour.
            served['https://example.org/latest/manifest.json'] = body.replace(b'1.2.0', b'1.2.1')
            updater = ota.Updater()
            updater.next_check = 0
            updater.poll(True)
            self.assertIsNone(updater.pending)
            self.assertAlmostEqual(updater.next_check, time.time() + ota.RETRY_INTERVAL_SEC, delta=5)
        finally:
            utime_stub.localtime = time.gmtime
            sys.modules.pop('lib.ota_key', None)
            sys.modules.pop('lib.config', None)


if __name__ == '__main__':
    unittest.main()
