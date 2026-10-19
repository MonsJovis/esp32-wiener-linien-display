#!/usr/bin/env python3
"""
Build and check an OTA release: the bundle the device downloads and the
manifest it trusts.

    python3 tools/release.py build v1.2.0 --url-base URL --out dist
    openssl dgst -sha256 -sign ota_signing_key.pem -out dist/manifest.sig dist/manifest.json
    python3 tools/release.py verify dist
    python3 tools/release.py pubkey ota_signing_key.pem    # writes lib/ota_key.py

`verify` runs the device's own rules (lib/ota_policy.py) against the finished
files: the signature against the committed lib/ota_key.py, the manifest, every
file's hash inside the bundle, and the version stamped into lib/version.py.
A release signed with the wrong key would be refused by every device, so it is
refused here first.
"""

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import ota_policy  # noqa: E402

# boot.py, config.json and secrets.json are never part of an update (see
# lib/ota_policy.path_allowed); new settings get defaults in lib/config.py.
TOP_LEVEL = ['main.py']


def payload(version):
    """[(path, bytes)] in bundle order, with lib/version.py stamped."""
    paths = TOP_LEVEL + sorted('lib/' + p.name for p in (ROOT / 'lib').glob('*.py'))
    files = []
    for path in paths:
        if not ota_policy.path_allowed(path):
            sys.exit('not allowed in an update: ' + path)
        data = (ROOT / path).read_bytes()
        if path == 'lib/version.py':
            data = version_file(version)
        files.append((path, data))
    return files


def version_file(version):
    return "VERSION = '{}'\n".format(version).encode()


def build(tag, url_base, out):
    m = re.fullmatch(r'v(\d+\.\d+\.\d+)', tag)
    if not m:
        sys.exit('tag must look like v1.2.3, got ' + tag)
    version = m.group(1)
    files = payload(version)
    bundle_name = 'app-{}.bin'.format(version)

    out.mkdir(parents=True, exist_ok=True)
    (out / bundle_name).write_bytes(b''.join(data for _, data in files))
    manifest = {
        'version': version,
        'bundle': url_base.rstrip('/') + '/' + bundle_name,
        'files': [
            {'path': path, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
            for path, data in files
        ],
    }
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1) + '\n')
    print('built {}: {} files, {} bytes'.format(version, len(files), sum(len(d) for _, d in files)))


def verify(out, key=None):
    if key is None:
        from lib import ota_key as key
    body = (out / 'manifest.json').read_bytes()
    sig = (out / 'manifest.sig').read_bytes()
    if not ota_policy.verify_signature(body, sig, key.N, key.E, key.K):
        sys.exit('manifest.sig does not verify against lib/ota_key.py')
    manifest = ota_policy.parse_manifest(body)
    bundle = (out / manifest['bundle'].rsplit('/', 1)[1]).read_bytes()

    offset = 0
    for f in manifest['files']:
        data = bundle[offset:offset + f['size']]
        offset += f['size']
        if hashlib.sha256(data).hexdigest() != f['sha256']:
            sys.exit('hash mismatch: ' + f['path'])
        if f['path'] == 'lib/version.py' and data != version_file(manifest['version']):
            sys.exit('lib/version.py does not say ' + manifest['version'])
    if offset != len(bundle):
        sys.exit('bundle is {} bytes, manifest covers {}'.format(len(bundle), offset))
    if 'lib/version.py' not in [f['path'] for f in manifest['files']]:
        sys.exit('lib/version.py missing')
    print('verified {}: signature, {} files, version'.format(manifest['version'], len(manifest['files'])))


def pubkey(pem, dest):
    text = subprocess.run(['openssl', 'pkey', '-in', str(pem), '-noout', '-text'],
                          check=True, capture_output=True, text=True).stdout
    if 'publicExponent: 65537' not in text:
        sys.exit('expected an RSA key with exponent 65537')
    modulus = subprocess.run(['openssl', 'rsa', '-in', str(pem), '-noout', '-modulus'],
                             check=True, capture_output=True, text=True).stdout
    hex_n = modulus.strip().split('=', 1)[1].lower()
    lines = '\n'.join("    '{}'".format(hex_n[i:i + 64]) for i in range(0, len(hex_n), 64))
    dest.write_text(
        '# Public half of the OTA release key, written by tools/release.py pubkey.\n'
        '# The private half is the OTA_SIGNING_KEY secret of the release workflow.\n'
        'N = int(\n{}, 16)\nE = 65537\nK = {}\n'.format(lines, len(hex_n) // 2))
    print('wrote {} ({}-bit key)'.format(dest.relative_to(ROOT), len(hex_n) * 4))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('build')
    p.add_argument('tag')
    p.add_argument('--url-base', required=True)
    p.add_argument('--out', type=pathlib.Path, default=ROOT / 'dist')
    p = sub.add_parser('verify')
    p.add_argument('out', type=pathlib.Path)
    p = sub.add_parser('pubkey')
    p.add_argument('pem', type=pathlib.Path)
    args = parser.parse_args()

    if args.cmd == 'build':
        build(args.tag, args.url_base, args.out)
    elif args.cmd == 'verify':
        verify(args.out)
    else:
        pubkey(args.pem, ROOT / 'lib' / 'ota_key.py')


if __name__ == '__main__':
    main()
