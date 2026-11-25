import unittest

from airspeed import Template


class EvaluateCaseTest(unittest.TestCase):
    def test_evaluate_accepts_the_same_letter_cases_as_other_directives(self):
        for directive in ('evaluate', 'EVALUATE', 'Evaluate', 'eVaLuAtE'):
            with self.subTest(directive=directive):
                template = Template('#' + directive + '($fragment)')
                self.assertEqual(template.merge({'fragment': 'Hello $name', 'name': 'Ada'}), 'Hello Ada')

    def test_mixed_case_evaluate_uses_the_enclosing_namespace(self):
        template = Template('#set($name="Ada")#Evaluate($fragment)')
        self.assertEqual(template.merge({'fragment': '$name'}), 'Ada')


if __name__ == '__main__':
    unittest.main()
