from unittest import TestCase

from airspeed import Template, TemplateExecutionError


class StringAdditionTests(TestCase):
    def render(self, expression):
        return Template('#set($result = ' + expression + ')$result').merge({})

    def test_strings_concatenate_with_numbers_in_either_order(self):
        for expression, expected in (
            ('"item-" + 2', 'item-2'),
            ('2 + " items"', '2 items'),
            ('"value=" + 2.5', 'value=2.5'),
            ('-3 + " C"', '-3 C'),
        ):
            with self.subTest(expression=expression):
                self.assertEqual(self.render(expression), expected)

    def test_concatenation_preserves_precedence_and_associativity(self):
        for expression, expected in (
            ('1 + 2 + " items"', '3 items'),
            ('"item-" + 1 + 2', 'item-12'),
            ('"value=" + 2 * 3', 'value=6'),
            ('"value=" + (2 + 3)', 'value=5'),
        ):
            with self.subTest(expression=expression):
                self.assertEqual(self.render(expression), expected)

    def test_numeric_and_string_addition_keep_their_results(self):
        self.assertEqual(self.render('2 + 3'), '5')
        self.assertEqual(self.render('2 + 3.5'), '5.5')
        self.assertEqual(self.render('"a" + "b"'), 'ab')
        with self.assertRaises(TemplateExecutionError):
            self.render('"a" - 1')
