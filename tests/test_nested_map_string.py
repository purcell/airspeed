from unittest import TestCase

from airspeed import Template


class NestedMapStringTests(TestCase):
    def render(self, value):
        return Template('$value.toString()').merge({'value': value})

    def test_nested_maps_and_lists_use_java_style_contents(self):
        value = {'user': {'name': 'Ada', 'roles': ['reader', 'writer']}, 'count': 2}
        self.assertEqual(
            self.render(value), '{user={name=Ada, roles=[reader, writer]}, count=2}'
        )

    def test_null_and_boolean_keys_and_values_use_java_spellings(self):
        self.assertEqual(
            self.render({None: True, 'disabled': False, 'missing': None}),
            '{null=true, disabled=false, missing=null}',
        )

    def test_self_references_do_not_recurse_forever(self):
        mapping = {}
        mapping['self'] = mapping
        self.assertEqual(self.render(mapping), '{self=(this Map)}')
        values = []
        values.append(values)
        self.assertEqual(self.render({'items': values}), '{items=[(this Collection)]}')

    def test_empty_and_plain_maps_keep_their_output(self):
        self.assertEqual(self.render({}), '{}')
        self.assertEqual(self.render({'key': 'value', 'n': 3}), '{key=value, n=3}')
