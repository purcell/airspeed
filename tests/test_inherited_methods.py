import unittest

import airspeed


class ListSubclass(list):
    pass


class DictSubclass(dict):
    pass


class StringSubclass(str):
    pass


class InheritedMethodsTest(unittest.TestCase):
    def test_list_subclass_inherits_velocity_helpers(self):
        values = ListSubclass(["a", "b"])
        output = airspeed.Template('$values.size()/$values.get(1)/$values.add("c")/$values.set(0, "z")').merge({'values': values})
        self.assertEqual(output, '2/b/True/a')
        self.assertEqual(values, ['z', 'b', 'c'])

    def test_dict_subclass_inherits_velocity_helpers(self):
        values = DictSubclass()
        output = airspeed.Template('$values.isEmpty()$!values.put("a", 1)/$values.toString()').merge({'values': values})
        self.assertEqual(output, 'True/{a=1}')
        self.assertEqual(values, {'a': 1})

    def test_string_subclass_inherits_velocity_helpers(self):
        output = airspeed.Template('$value.length()/$value.trim()/$value.startsWith(" ")').merge({'value': StringSubclass(' hi ')})
        self.assertEqual(output, '4/hi/True')

    def test_real_methods_and_dictionary_entries_keep_precedence(self):
        class Override(ListSubclass):
            def size(self):
                return 42
        output = airspeed.Template('$values.size()/$mapping.isEmpty()').merge({'values': Override(), 'mapping': DictSubclass(isEmpty=lambda: 'custom')})
        self.assertEqual(output, '42/custom')

    def test_unrelated_objects_do_not_gain_list_methods(self):
        self.assertEqual(airspeed.Template('$!value.size()').merge({'value': object()}), '')
