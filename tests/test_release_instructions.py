"""What ./bilibi release tells the owner to do on each server."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import github_release  # noqa: E402


class InstallSteps(unittest.TestCase):
    def steps(self, limit):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / 'bilibi-setup-v1.0.0-x86_64-unknown-linux-gnu.tar.gz'
            archive.write_bytes(b'application archive\n')
            with mock.patch.object(github_release, 'UPLOAD_LIMIT', limit):
                return github_release.install_steps('acme/shop', 'setup-v1.0.0', archive, 'abc123'), archive

    def test_a_file_within_the_upload_limit_is_uploaded(self):
        text, archive = self.steps(1024)
        self.assertIn(f'Open Software -> Releases and upload this file:\n       {archive}', text)
        self.assertIn('SHA-256 abc123', text)

    def test_a_file_over_the_upload_limit_is_reviewed_from_github(self):
        text, archive = self.steps(4)
        self.assertIn('choose Refresh, then Review on setup-v1.0.0', text)
        self.assertIn('over the 64 MiB an upload accepts', text)
        self.assertIn(str(archive), text)
        self.assertNotIn('upload this file', text)


if __name__ == '__main__':
    unittest.main()
