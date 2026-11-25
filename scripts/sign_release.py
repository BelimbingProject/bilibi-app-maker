#!/usr/bin/env python3
"""Sign Bilibi's installable release assets with the Platform proof signer."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

import publish


SECRET = 'BILIBI_RELEASE_SIGNING_KEY'


def checksum(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def platform_signer(root):
    sources = Path(os.environ.get('BILIBI_SOURCE_DIR', root / 'sources'))
    return sources / 'platform/scripts/lib/release-proof.py'


def write_sums(folder):
    sums = folder / 'SHA256SUMS'
    contents = ''.join(
        f'{checksum(path)}  {path.name}\n'
        for path in sorted(folder.iterdir())
        if path.name != sums.name
    )
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=folder, delete=False) as opened:
        pending = Path(opened.name)
        opened.write(contents)
        opened.flush()
        os.fsync(opened.fileno())
    try:
        pending.chmod(0o644)
        pending.replace(sums)
    finally:
        pending.unlink(missing_ok=True)


def sign(args):
    root = Path(os.environ.get('BILIBI_TOOL_APPLICATION_ROOT', Path(__file__).resolve().parent.parent)).resolve()
    signer = platform_signer(root)
    if not signer.is_file():
        raise ValueError(
            f'{signer} is missing. Upgrade the saved Bilibi Platform to a release with ADR 35 operator proofs.'
        )
    key = os.environ.pop(SECRET, '')
    if not key.strip():
        raise ValueError(f'{SECRET} is empty; configure the release-signing environment secret before signing a release')
    if not hasattr(os, 'memfd_create'):
        raise ValueError('release signing needs Linux anonymous memory files')

    expected = publish.verify_files(args.directory)
    record = json.loads((args.directory / 'recipe.json').read_text())
    if record.get('setup', {}).get('tag') != args.tag or record.get('setup', {}).get('repository') != args.repository:
        raise ValueError('The release recipe must name the repository and tag being signed')
    target = record['built_for']['target']
    unsigned = publish.release_assets(args.tag, target)
    if set(expected) != unsigned:
        raise ValueError('Sign only the complete unsigned release produced by package.py')
    assets = publish.installable_assets(args.tag, target)

    key_fd = os.memfd_create('bilibi-release-signing-key', flags=0)
    try:
        os.write(key_fd, key.encode('utf-8'))
        sanitized = dict(os.environ)
        for name, kind, proof_target in assets:
            artifact = args.directory / name
            os.lseek(key_fd, 0, os.SEEK_SET)
            output = artifact.with_name(artifact.name + '.proof.json')
            subprocess.run(
                [
                    'python3', str(signer), 'sign',
                    '--artifact', str(artifact),
                    '--private-key', '/proc/self/fd/0',
                    '--repository', args.repository,
                    '--repository-id', str(args.repository_id),
                    '--workflow', args.workflow,
                    '--tag', args.tag,
                    '--kind', kind,
                    '--target', proof_target,
                    '--output', str(output),
                ],
                stdin=key_fd,
                env=sanitized,
                check=True,
            )
    finally:
        os.close(key_fd)

    write_sums(args.directory)
    signed = publish.verify_files(args.directory)
    wanted = publish.release_assets(args.tag, target, operator_proof=True)
    if set(signed) != wanted:
        raise ValueError('The signed release does not contain the complete operator proof set')
    print(f'Signed {len(assets)} installable assets with the Platform ADR 35 proof format.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--repository-id', type=int, required=True)
    parser.add_argument('--workflow', required=True)
    args = parser.parse_args()
    try:
        sign(args)
    except ValueError as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
