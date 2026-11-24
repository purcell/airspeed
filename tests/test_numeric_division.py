import unittest

import airspeed


class NumericDivisionTest(unittest.TestCase):
    def calculate(self, expression, **namespace):
        values = []
        namespace['capture'] = values.append
        airspeed.Template('#set($result = (' + expression + '))$!capture($result)').merge(namespace)
        return values[0]

    def test_division_preserves_fractions_when_either_operand_is_float(self):
        for left, right, expected in [(5.0, 2, 2.5), (5, 2.0, 2.5), (5.0, 2.0, 2.5), (-5.0, 2, -2.5)]:
            with self.subTest(left=left, right=right):
                self.assertEqual(self.calculate('$left / $right', left=left, right=right), expected)

    def test_integer_division_truncates_towards_zero_without_float_rounding(self):
        for left, right, expected in [(-5, 2, -2), (5, -2, -2), (-5, -2, 2), (5, 2, 2), (-(10 ** 100 + 1), 3, -((10 ** 100 + 1) // 3))]:
            with self.subTest(left=left, right=right):
                result = self.calculate('$left / $right', left=left, right=right)
                self.assertEqual(result, expected)
                self.assertIsInstance(result, int)

    def test_division_by_zero_still_reports_the_template_error(self):
        with self.assertRaises(airspeed.TemplateExecutionError) as caught:
            self.calculate('1 / 0')
        self.assertIsInstance(caught.exception.__cause__, ZeroDivisionError)

