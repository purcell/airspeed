import unittest
import math

import airspeed


class NumericRemainderTest(unittest.TestCase):
    def calculate(self, left, right):
        values = []
        airspeed.Template('#set($value = $left % $right)$!capture($value)').merge(
            {'left': left, 'right': right, 'capture': values.append})
        return values[0]

    def test_integer_remainder_has_the_dividend_sign(self):
        for left, right, expected in [(5, 2, 1), (-5, 2, -1),
                                      (5, -2, 1), (-5, -2, -1),
                                      (-(10 ** 100 + 1), 3, -2)]:
            with self.subTest(left=left, right=right):
                result = self.calculate(left, right)
                self.assertEqual(result, expected)
                self.assertIsInstance(result, int)

    def test_float_remainder_has_the_dividend_sign(self):
        for left, right, expected in [(-5.5, 2, -1.5), (5.5, -2, 1.5),
                                      (-5, 2.0, -1.0), (-4.0, 2, -0.0)]:
            with self.subTest(left=left, right=right):
                result = self.calculate(left, right)
                self.assertEqual(result, expected)
                self.assertIsInstance(result, float)
                self.assertEqual(math.copysign(1, result), math.copysign(1, expected))

    def test_zero_divisor_reports_a_template_error(self):
        with self.assertRaises(airspeed.TemplateExecutionError):
            self.calculate(5, 0)
