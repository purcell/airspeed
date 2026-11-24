import unittest

import airspeed


class NestedIndexScopeTest(unittest.TestCase):
    def test_nested_list_indexes_resolve_in_the_template_namespace(self):
        template = airspeed.Template('$matrix[$row][$column]')
        self.assertEqual(template.merge({'matrix': [[10, 11], [20, 21]], 'row': 1, 'column': 0}), '20')

    def test_nested_map_must_not_shadow_the_template_index(self):
        template = airspeed.Template('$data["record"][$key]')
        self.assertEqual(template.merge({'data': {'record': {'key': 'wrong', 'wanted': 'right', 'wrong': 'bad'}}, 'key': 'wanted'}), 'right')

    def test_every_chained_index_uses_the_template_namespace(self):
        template = airspeed.Template('$cube[0][$row][$column]')
        self.assertEqual(template.merge({'cube': [[[1, 2], [3, 4]]], 'row': 1, 'column': 1}), '4')

    def test_index_expressions_and_methods_use_the_template_namespace(self):
        template = airspeed.Template('$matrix[0][($offset + 1)]/$matrix[0][$index()]')
        self.assertEqual(template.merge({'matrix': [[10, 20, 30]], 'offset': 0, 'index': lambda: 2}), '20/30')

    def test_literal_indexes_and_native_negative_indexes_still_work(self):
        template = airspeed.Template('$matrix[0][1]/$matrix[0][-1]')
        self.assertEqual(template.merge({'matrix': [[10, 20, 30]]}), '20/30')
