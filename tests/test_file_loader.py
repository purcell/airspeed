import os
from pathlib import Path
import tempfile
import unittest

from airspeed import CachingFileLoader, Template


class CachingFileLoaderTestCase(unittest.TestCase):
    def test_replaced_template_with_older_timestamp_is_reloaded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'child.vm'
            path.write_text('first $name', encoding='utf-8')
            os.utime(path, (200, 200))
            loader = CachingFileLoader(directory)
            parent = Template('#parse("child.vm")')
            self.assertEqual(parent.merge({'name': 'one'}, loader), 'first one')
            original = loader.load_template('child.vm')
            self.assertIs(loader.load_template('child.vm'), original)

            path.write_text('second $name', encoding='utf-8')
            os.utime(path, (100, 100))
            self.assertEqual(parent.merge({'name': 'two'}, loader), 'second two')
            replacement = loader.load_template('child.vm')
            self.assertIsNot(replacement, original)
            self.assertIs(loader.load_template('child.vm'), replacement)

    def test_newer_template_is_reloaded_and_unchanged_template_is_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'child.vm'
            path.write_text('before', encoding='utf-8')
            os.utime(path, (100, 100))
            loader = CachingFileLoader(directory)
            original = loader.load_template('child.vm')
            self.assertIs(loader.load_template('child.vm'), original)
            path.write_text('after', encoding='utf-8')
            os.utime(path, (200, 200))
            replacement = loader.load_template('child.vm')
            self.assertIsNot(replacement, original)
            self.assertEqual(replacement.merge({}), 'after')
            self.assertIs(loader.load_template('child.vm'), replacement)
