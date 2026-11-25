"""Operator release signing keeps the key in memory and emits the complete sidecar set."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import publish  # noqa: E402


FAKE_PLATFORM_SIGNER = r'''#!/usr/bin/env python3
import argparse, json, os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('command')
for name in ('artifact', 'private-key', 'repository', 'repository-id', 'workflow', 'tag', 'kind', 'target', 'output'):
    parser.add_argument('--' + name, required=True)
args = parser.parse_args()
assert args.command == 'sign'
assert args.private_key == '/proc/self/fd/0'
assert 'BILIBI_RELEASE_SIGNING_KEY' not in os.environ
with open(args.private_key, 'rb') as first, open(args.private_key, 'rb') as second:
    assert first.read() == b'test private key in memory\n'
    assert second.read() == b'test private key in memory\n'
Path(args.output).write_text(json.dumps({
    'artifact': Path(args.artifact).name,
    'repository': args.repository,
    'repository_id': int(args.repository_id),
    'workflow': args.workflow,
    'tag': args.tag,
    'kind': args.kind,
    'target': args.target,
}) + '\n')
'''


class SignReleaseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dist = self.root / 'dist'
        self.dist.mkdir()
        self.tag = 'setup-v1.2.3'
        self.target = 'x86_64-unknown-linux-gnu'
        files = {
            f'bilibi-{self.tag}-{self.target}.tar.gz': b'application archive\n',
            f'bilibi-installer-{self.target}': b'installer\n',
            'bilibi-server-tools.tar.gz': b'server tools\n',
            'builder-packages.txt': b'packages\n',
            'publication.json': b'{}\n',
            'recipe.json': json.dumps({
                'setup': {'repository': 'acme/shop', 'tag': self.tag},
                'built_for': {'target': self.target},
            }).encode(),
        }
        for name, contents in files.items():
            (self.dist / name).write_bytes(contents)
        (self.dist / 'SHA256SUMS').write_text(''.join(
            f'{hashlib.sha256(contents).hexdigest()}  {name}\n' for name, contents in sorted(files.items())
        ))
        self.signer = self.root / 'release-proof.py'
        self.signer.write_text(FAKE_PLATFORM_SIGNER)

    def test_signs_every_installable_asset_without_exporting_the_key(self):
        env = dict(os.environ)
        env.update(
            BILIBI_RELEASE_SIGNING_KEY='test private key in memory\n',
            BILIBI_TOOL_APPLICATION_ROOT=str(self.root),
        )
        subprocess.run([
            'python3', str(ROOT / 'scripts/sign_release.py'),
            '--directory', str(self.dist),
            '--tag', self.tag,
            '--repository', 'acme/shop',
            '--repository-id', '123456789',
            '--workflow', 'acme/shop/.github/workflows/release.yml',
            '--signer', str(self.signer),
        ], env=env, check=True, capture_output=True, text=True)

        expected = publish.release_assets(self.tag, self.target, operator_proof=True)
        self.assertEqual(set(publish.verify_files(self.dist)), expected)
        proofs = sorted(self.dist.glob('*.proof.json'))
        self.assertEqual(len(proofs), 3)
        self.assertEqual(
            {(json.loads(path.read_text())['kind'], json.loads(path.read_text())['target']) for path in proofs},
            {('setup', self.target), ('installer', self.target), ('server-tools', 'server-tools')},
        )
        for path in self.dist.iterdir():
            self.assertNotIn(b'test private key in memory', path.read_bytes())

    def test_refuses_an_empty_signing_secret(self):
        result = subprocess.run([
            'python3', str(ROOT / 'scripts/sign_release.py'),
            '--directory', str(self.dist),
            '--tag', self.tag,
            '--repository', 'acme/shop',
            '--repository-id', '123456789',
            '--workflow', 'acme/shop/.github/workflows/release.yml',
            '--signer', str(self.signer),
        ], env={**os.environ, 'BILIBI_RELEASE_SIGNING_KEY': ''}, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('BILIBI_RELEASE_SIGNING_KEY is empty', result.stderr)


if __name__ == '__main__':
    unittest.main()
