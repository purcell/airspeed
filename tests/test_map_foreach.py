from collections import OrderedDict, UserDict
import unittest

from airspeed import Template


class MapForeachTests(unittest.TestCase):
    def test_literal_map_iterates_values(self):
        template = Template('#set($map = {"left":"L", "right":"R"})'
                            '#foreach($value in $map)$value|#end')
        self.assertEqual(template.merge({}), 'L|R|')

    def test_injected_mappings_iterate_values_in_mapping_order(self):
        for mapping in (dict, OrderedDict, UserDict):
            with self.subTest(mapping=mapping):
                users = mapping([('alice', 'Alice'), ('bob', 'Bob')])
                result = Template('#foreach($user in $users)$user|#end').merge({'users': users})
                self.assertEqual(result, 'Alice|Bob|')

    def test_mapping_values_can_be_objects(self):
        template = Template('#foreach($user in $users)$user.name|#end')
        self.assertEqual(template.merge({'users': {'alice': {'name': 'Alice'}}}), 'Alice|')

    def test_loop_metadata_counts_values(self):
        template = Template('#foreach($v in $users)'
                            '$foreach.index:$v#if($foreach.hasNext),#end#end')
        self.assertEqual(template.merge({'users': {'alice': 'Alice', 'bob': 'Bob'}}),
                         '0:Alice,1:Bob')

    def test_explicit_key_set_still_iterates_keys(self):
        template = Template('#foreach($key in $users.keySet())$key|#end')
        self.assertEqual(template.merge({'users': {'alice': 'Alice', 'bob': 'Bob'}}),
                         'alice|bob|')

    def test_empty_mapping_has_no_iterations(self):
        self.assertEqual(Template('before#foreach($v in $users)$v#end-after').merge({'users': {}}),
                         'before-after')


if __name__ == '__main__':
    unittest.main()
