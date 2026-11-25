"""Verify maker sidecars with the Platform's installation-pinned ADR 35 verifier."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
TAG = 'setup-v1.2.3'
REPOSITORY = 'acme/shop'
WORKFLOW = 'acme/shop/.github/workflows/release.yml'
TARGET = 'x86_64-unknown-linux-gnu'
ASSETS = {
    'bilibi-setup-v1.2.3-x86_64-unknown-linux-gnu.tar.gz': ('setup', TARGET),
    'bilibi-installer-x86_64-unknown-linux-gnu': ('installer', TARGET),
    'bilibi-server-tools.tar.gz': ('server-tools', 'server-tools'),
}


class SignReleaseTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.dist = self.root / 'dist'
        self.dist.mkdir()
        self.signer = self.root / 'sources/platform/scripts/lib/release-proof.py'
        self.signer.parent.mkdir(parents=True)
        self.files = {
            **{name: f'{kind} bytes\n'.encode() for name, (kind, _) in ASSETS.items()},
            'builder-packages.txt': b'packages\n',
            'publication.json': b'{}\n',
            'recipe.json': json.dumps({
                'setup': {'repository': REPOSITORY, 'tag': TAG},
                'built_for': {'target': TARGET},
            }).encode(),
        }
        for name, contents in self.files.items():
            (self.dist / name).write_bytes(contents)
        (self.dist / 'SHA256SUMS').write_text(''.join(
            f'{hashlib.sha256(contents).hexdigest()}  {name}\n'
            for name, contents in sorted(self.files.items())
        ))

    def sign(self, key):
        env = dict(os.environ)
        env.pop('BILIBI_SOURCE_DIR', None)
        env.update(BILIBI_RELEASE_SIGNING_KEY=key, BILIBI_TOOL_APPLICATION_ROOT=str(self.root))
        return subprocess.run([
            'python3', str(ROOT / 'scripts/sign_release.py'),
            '--directory', str(self.dist), '--tag', TAG, '--repository', REPOSITORY,
            '--repository-id', '123456789', '--workflow', WORKFLOW,
        ], env=env, capture_output=True, text=True)

    def test_platform_accepts_every_sidecar_for_its_bound_artifact(self):
        source = os.environ.get('BILIBI_TEST_PLATFORM_SIGNER')
        if not source:
            self.skipTest('Set BILIBI_TEST_PLATFORM_SIGNER to the materialized Platform signer')
        self.signer.symlink_to(Path(source).resolve(strict=True))
        key = subprocess.check_output(['openssl', 'genpkey', '-algorithm', 'Ed25519'], text=True)
        public_key = self.root / 'operator.pub'
        public_key.write_bytes(subprocess.run(
            ['openssl', 'pkey', '-pubout'], input=key.encode(), capture_output=True, check=True,
        ).stdout)
        trust = self.root / 'trust.json'
        subprocess.run([
            'python3', str(self.signer), 'make-trust', '--kind', 'operator',
            '--repository', REPOSITORY, '--repository-id', '123456789', '--workflow', WORKFLOW,
            '--minimum-tag', 'setup-v1.0.0', '--changed-by', 'test', '--public-key', str(public_key),
            '--output', str(trust),
        ], capture_output=True, check=True)
        signed = self.sign(key)
        self.assertEqual(signed.returncode, 0, signed.stderr)

        expected = set(self.files) | {f'{name}.proof.json' for name in ASSETS}
        self.assertEqual({path.name for path in self.dist.iterdir()}, expected | {'SHA256SUMS'})
        self.assertEqual((self.dist / 'SHA256SUMS').read_text(), ''.join(
            f'{hashlib.sha256((self.dist / name).read_bytes()).hexdigest()}  {name}\n'
            for name in sorted(expected)
        ))
        for name, (kind, target) in ASSETS.items():
            with self.subTest(asset=name):
                artifact = self.dist / name
                self.assertEqual(artifact.read_bytes(), self.files[name])
                verified = subprocess.run([
                    'python3', str(self.signer), 'verify-operator', '--artifact', str(artifact),
                    '--proof', str(self.dist / f'{name}.proof.json'), '--trust', str(trust),
                    '--tag', TAG, '--kind', kind, '--target', target,
                ], capture_output=True, text=True)
                self.assertEqual(verified.returncode, 0, verified.stderr)
        for path in self.dist.iterdir():
            self.assertNotIn(key.strip().encode(), path.read_bytes())

    def test_refuses_an_empty_signing_secret(self):
        self.signer.touch()
        result = self.sign('')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('BILIBI_RELEASE_SIGNING_KEY is empty', result.stderr)


if __name__ == '__main__':
    unittest.main()
