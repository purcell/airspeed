import unittest

from airspeed import Template, TemplateExecutionError


class ReplaceAllTests(unittest.TestCase):
    def replace(self, source, pattern, replacement):
        return Template('$text.replaceAll($pattern, $replacement)').merge({
            'text': source, 'pattern': pattern, 'replacement': replacement,
        })

    def test_java_replacement_groups_and_escapes(self):
        cases = [
            ('ab ab', '(a)(b)', '$2$1', 'ba ba'),
            ('ab', '(a)(b)', '$0/$1/$2', 'ab/a/b'),
            ('a', '(a)', '$12', 'a2'),
            ('a', '(a)', '$01', 'a'),
            ('abcdefghijkl', '(a)(b)(c)(d)(e)(f)(g)(h)(i)(j)(k)(l)', '$12', 'l'),
            ('b', '(a)?b', '<$1>', '<>'),
            ('a', '(a)', r'\$1', '$1'),
            ('a', '(a)', r'\\$1', '\\a'),
            ('a', '(a)', r'\n', 'n'),
            ('a', '(?P<word>a)', '${word}', 'a'),
            ('x', '(a)', '$99', 'x'),
            ('abc', 'b', 'x', 'axc'),
        ]
        for source, pattern, replacement, expected in cases:
            with self.subTest(replacement=replacement, pattern=pattern):
                self.assertEqual(self.replace(source, pattern, replacement), expected)

    def test_invalid_replacement_references(self):
        for replacement in ['$', '$x', '$2', '${missing}', '${word', '\\']:
            with self.subTest(replacement=replacement):
                with self.assertRaises(TemplateExecutionError):
                    self.replace('a', '(a)', replacement)


if __name__ == '__main__':
    unittest.main()
