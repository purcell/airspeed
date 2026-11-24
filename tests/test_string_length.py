import unittest

import airspeed


class StringLengthTest(unittest.TestCase):
    def test_length_counts_java_utf16_code_units(self):
        for text, expected in [('', 0), ('hello', 5), ('\u4e2d\u6587', 2),
                               ('\U0001f600', 2), ('a\U0001f600b', 4),
                               ('\ud800', 1), ('\ud83d\ude00', 2)]:
            with self.subTest(text=ascii(text)):
                self.assertEqual(airspeed.Template('$text.length()').merge(
                    {'text': text}), str(expected))
