from unittest import TestCase

from airspeed import Template, TemplateExecutionError


class RepeatedMacroTests(TestCase):
    def test_macro_definition_inside_a_repeated_loop_body(self):
        template = Template(
            '#foreach($item in [1,2,3])'
            '#macro(show)$item#end#show()#end'
        )
        self.assertEqual(template.merge({}), '123')

    def test_reusing_a_compiled_template_and_namespace(self):
        template = Template('#macro(greet)Hello $name!#end#greet()')
        namespace = {'name': 'Ada'}
        self.assertEqual(template.merge(namespace), 'Hello Ada!')
        namespace['name'] = 'Grace'
        self.assertEqual(template.merge(namespace), 'Hello Grace!')

    def test_parsing_the_same_cached_template_twice(self):
        class Loader:
            child = Template('#macro(show)Hello#end#show()')

            def load_template(self, name):
                return self.child

        template = Template('#parse("child.vm")#parse("child.vm")')
        self.assertEqual(template.merge({}, Loader()), 'HelloHello')

    def test_distinct_definitions_are_still_redefinitions(self):
        template = Template('#macro(show)first#end#macro(show)second#end')
        with self.assertRaises(TemplateExecutionError):
            template.merge({})
