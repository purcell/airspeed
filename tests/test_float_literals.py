from unittest import TestCase

from airspeed import Template, TemplateSyntaxError


class FloatingLiteralTests(TestCase):
    def test_velocity_floating_literal_forms_are_valid_in_assignments(self):
        for literal, expected in (
                ('1e3', 1000.0), ('-2E-2', -0.02), ('2.5e+2', 250.0),
                ('.5E2', 50.0), ('-.5e-1', -0.05), ('1.', 1.0),
                ('-2.', -2.0), ('1.e2', 100.0)):
            with self.subTest(literal=literal):
                values = []
                template = Template('#set($value = ' + literal + ')$capture($value)')
                template.merge({'capture': lambda value: values.append(value) or ''})
                self.assertEqual(values, [expected])
                self.assertIsInstance(values[0], float)

    def test_exponents_work_in_call_arguments_containers_and_arithmetic(self):
        self.assertEqual(Template('$echo(2E3)').merge({'echo': str}), '2000.0')
        self.assertEqual(Template('#set($x = 1.e2 + .5e1)$x').merge({}), '105.0')
        self.assertEqual(Template('#set($xs = [1., 2e1, -.5E2])'
                                 '$xs[0],$xs[1],$xs[2]').merge({}), '1.0,20.0,-50.0')
        self.assertEqual(Template('#set($xs = {"small": 1e-2})$xs.small').merge({}), '0.01')

    def test_integer_ranges_and_existing_decimal_forms_are_unchanged(self):
        self.assertEqual(Template('#foreach($x in [1..3])$x#end').merge({}), '123')
        self.assertEqual(Template('#foreach($x in [3..1])$x#end').merge({}), '321')
        self.assertEqual(Template('#set($x = 7)$x').merge({}), '7')
        self.assertEqual(Template('#set($x = -.25)$x').merge({}), '-0.25')

    def test_incomplete_exponents_are_syntax_errors(self):
        for literal in ('1e', '1e+', '1.0E-', '.e2'):
            with self.subTest(literal=literal):
                with self.assertRaises(TemplateSyntaxError):
                    Template('#set($x = ' + literal + ')').ensure_compiled()
