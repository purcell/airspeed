from unittest import TestCase

from airspeed import Template


class NullMappingEntryTestCase(TestCase):
    def test_null_entries_do_not_expose_methods(self):
        for name in ('items', 'get', 'isEmpty', 'toString'):
            with self.subTest(name=name):
                template = Template('$!record.' + name)
                self.assertEqual('', template.merge({'record': {name: None}}))

    def test_null_entry_uses_the_reference_default(self):
        template = Template('${record.items|"no items"}')
        self.assertEqual('no items', template.merge({'record': {'items': None}}))

    def test_null_entry_is_false_in_a_condition(self):
        template = Template('#if($record.items)present#else missing#end')
        self.assertEqual(' missing', template.merge({'record': {'items': None}}))

    def test_null_method_entry_cannot_mutate_the_mapping(self):
        record = {'put': None}
        template = Template('$!record.put("added", 1)')
        self.assertEqual('', template.merge({'record': record}))
        self.assertEqual({'put': None}, record)

    def test_null_mapping_entry_shadows_an_attribute(self):
        class Row:
            items = 'attribute value'

            def __getitem__(self, name):
                return {'items': None}[name]

        self.assertEqual('', Template('$!row.items').merge({'row': Row()}))

    def test_absent_entries_still_resolve_methods(self):
        template = Template('$record.get("value")/$record.isEmpty()')
        self.assertEqual('kept/False', template.merge({'record': {'value': 'kept'}}))

    def test_non_null_entries_keep_precedence(self):
        for value, expected in ((0, '0'), (False, 'False'), ('', ''), ('data', 'data')):
            with self.subTest(value=value):
                self.assertEqual(expected, Template('$record.items').merge({
                    'record': {'items': value}}))

    def test_callable_mapping_entries_still_run(self):
        template = Template('$record.items()')
        self.assertEqual('custom', template.merge({
            'record': {'items': lambda: 'custom'}}))
