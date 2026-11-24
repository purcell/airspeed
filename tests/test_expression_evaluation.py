import unittest

import airspeed


class ExpressionEvaluationTest(unittest.TestCase):
    def render(self, expression, namespace=None):
        return airspeed.Template('#set($result = (' + expression + '))$result').merge(namespace or {})

    def test_logical_operators_skip_the_unneeded_operand(self):
        def forbidden():
            raise AssertionError('short-circuited operand was evaluated')
        for expression, expected in [('false && $fail()', 'False'), ('false and $fail()', 'False'), ('true || $fail()', 'True'), ('true or $fail()', 'True'), ('true || $fail() && false', 'True')]:
            with self.subTest(expression=expression):
                self.assertEqual(self.render(expression, {'fail': forbidden}), expected)

    def test_logical_guard_prevents_division_by_zero(self):
        self.assertEqual(self.render('$denominator != 0 && 10 / $denominator > 1', {'denominator': 0}), 'False')

    def test_operands_run_left_to_right_once(self):
        calls = []
        def take(value):
            calls.append(value)
            return value
        self.assertEqual(self.render('$take(1) + $take(2) * $take(3)', {'take': take}), '7')
        self.assertEqual(calls, [1, 2, 3])

    def test_needed_logical_operand_runs_once(self):
        calls = []
        def take(value):
            calls.append(value)
            return value
        self.assertEqual(self.render('$take(true) && $take(false) || $take(true)', {'take': take}), 'True')
        self.assertEqual(calls, [True, False, True])

    def test_equality_and_inequality_have_equal_precedence(self):
        for expression in ['1 != 2 == 3', '1 ne 2 eq 3', '1 ne 2 == 3', '1 != 2 eq 3']:
            with self.subTest(expression=expression):
                self.assertEqual(self.render(expression), 'False')

    def test_parentheses_and_arithmetic_associativity_remain_intact(self):
        for expression, expected in [('10 - 3 - 2', '5'), ('10 - (3 - 2)', '9'), ('2 + 3 * 4', '14'), ('(2 + 3) * 4', '20'), ('1 != (2 == 3)', 'True')]:
            with self.subTest(expression=expression):
                self.assertEqual(self.render(expression), expected)

    def test_long_flat_expression_does_not_require_recursive_evaluation(self):
        self.assertEqual(self.render(' + '.join(['1'] * 1500)), '1500')
