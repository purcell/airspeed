from unittest import TestCase

from airspeed import Template, TemplateExecutionError


class FailingLookup:
    def __init__(self, error):
        self.error = error

    def __getitem__(self, key):
        raise self.error


class IndexErrorTests(TestCase):
    def test_lookup_failures_report_the_original_error_and_template(self):
        for text in ('$record["name"]', '$!record["name"]'):
            for error in (RuntimeError('lookup failed'), OSError('backend unavailable')):
                with self.subTest(text=text, error=type(error).__name__):
                    template = Template(text, filename='profile.vm')
                    with self.assertRaises(TemplateExecutionError) as raised:
                        template.merge({'record': FailingLookup(error)})
                    self.assertIs(raised.exception.__cause__, error)
                    self.assertEqual(raised.exception.filename, 'profile.vm')

    def test_indexed_lookup_does_not_swallow_cancellation(self):
        for error in (KeyboardInterrupt(), SystemExit(7)):
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(type(error)) as raised:
                    Template('$record["name"]').merge({'record': FailingLookup(error)})
                self.assertIs(raised.exception, error)

    def test_nonindexable_values_report_a_type_error(self):
        with self.assertRaises(TemplateExecutionError) as raised:
            Template('$value[0]').merge({'value': 42})
        self.assertIsInstance(raised.exception.__cause__, TypeError)

    def test_missing_keys_and_out_of_range_indexes_remain_optional(self):
        for text, namespace in (
                ('$record["missing"]', {'record': {}}),
                ('$values[4]', {'values': ['one']})):
            with self.subTest(text=text):
                self.assertEqual(Template(text).merge(namespace), text)
                self.assertEqual(Template('$!' + text[1:]).merge(namespace), '')
        self.assertEqual(Template('$record["name"] $values[0]').merge(
            {'record': {'name': 'Ada'}, 'values': ['one']}), 'Ada one')
