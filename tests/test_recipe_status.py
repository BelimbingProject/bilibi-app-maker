"""The built program's composition is compared with the saved record."""
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import recipe  # noqa: E402

RECORD = {
    'platform_version': '0.2.1', 'platform': 'a' * 40,
    'containers': {
        'domains/factory': {'head': 'b' * 40},
        'extensions/shop_rules': {'head': 'c' * 40, 'code': 'reviewed'},
    },
}
HEAD = f'Bilibi 0.2.1, unreleased, commit {"a" * 40}\nPin: .local/composition, compiled in at build time\n'


def status(extension):
    return (HEAD + 'Domains:\n' + f'  factory untagged, commit {"b" * 40}, modules: factory/inventory\n'
            + 'Extensions:\n' + extension + '\n')


class CheckedStatus(unittest.TestCase):
    def checked(self, text):
        with mock.patch.object(recipe, 'check_record', return_value=RECORD), \
                mock.patch.object(recipe, 'run', return_value=text):
            return recipe.checked_status(Path('bilibi-web'))

    def test_accepts_an_extension_with_its_code_declaration(self):
        text = status(f'  shop_rules untagged, commit {"c" * 40}, code: reviewed, modules: shop_rules/rules')
        self.assertEqual(self.checked(text), text)

    def test_refuses_another_code_declaration(self):
        with self.assertRaisesRegex(ValueError, 'differ from the saved recipe'):
            self.checked(status(f'  shop_rules untagged, commit {"c" * 40}, code: customer, modules: shop_rules/rules'))

    def test_refuses_another_commit(self):
        with self.assertRaisesRegex(ValueError, 'differ from the saved recipe'):
            self.checked(status(f'  shop_rules untagged, commit {"d" * 40}, code: reviewed, modules: shop_rules/rules'))


if __name__ == '__main__':
    unittest.main()
