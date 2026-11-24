from unittest import TestCase

from airspeed import Template, TemplateSyntaxError


class BlockTerminatorTests(TestCase):
    def test_block_endings_accept_the_same_case_as_directive_parsers(self):
        cases = (
            ('#IF(true)yes#ELSE no#END', 'yes'),
            ('#if(false)no#ElseIf(true)yes#eLsE no#EnD', 'yes'),
            ('#if(false)no#{ELSE}yes#{END}', 'yes'),
            ('#foreach($i in [1,2])$i#END', '12'),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(Template(source).merge({}), expected)

    def test_adjacent_text_after_end_remains_supported(self):
        for ending in ('#end', '#END'):
            with self.subTest(ending=ending):
                self.assertEqual(
                    Template('#if(true)yes' + ending + 'Tail').merge({}), 'yesTail'
                )

    def test_unmatched_endings_are_rejected_in_every_case(self):
        for source in ('#end', '#END', '#Else', '#{END}'):
            with self.subTest(source=source):
                with self.assertRaises(TemplateSyntaxError):
                    Template(source).merge({})
