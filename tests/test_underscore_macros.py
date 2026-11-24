from unittest import TestCase

from airspeed import Template, TemplateExecutionError


class UnderscoreMacroTests(TestCase):
    def test_call_a_macro_whose_name_starts_with_an_underscore(self):
        template = Template('#macro(_hello $name)Hi $name#end#_hello("Ada")')
        self.assertEqual(template.merge({}), 'Hi Ada')

    def test_macro_parameters_accept_leading_underscores(self):
        template = Template('#macro(show $_name)$_name#end#show("Ada")')
        self.assertEqual(template.merge({}), 'Ada')

    def test_define_names_and_parameters_accept_leading_underscores(self):
        template = Template('#define($_greet $_person)Hi $_person#end$_greet("Ada")')
        self.assertEqual(template.merge({}), 'Hi Ada')

    def test_non_calls_remain_literal_and_undefined_calls_still_fail(self):
        self.assertEqual(Template('#_literal').merge({}), '#_literal')
        with self.assertRaises(TemplateExecutionError):
            Template('#_missing()').merge({})
