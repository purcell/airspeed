from unittest import TestCase

from airspeed import Template


class DirectiveWhitespaceTestCase(TestCase):
    def test_foreach_consumes_one_directive_line_ending(self):
        for newline in ('\n', '\r\n'):
            for trailing in ('', '  \t'):
                with self.subTest(newline=newline, trailing=trailing):
                    source = (
                        '#foreach($i in [1..2])' + trailing + newline
                        + '  $i' + newline + '#end' + newline + 'tail'
                    )
                    self.assertEqual(
                        '  1' + newline + '  2' + newline + 'tail',
                        Template(source).merge({}),
                    )

    def test_else_consumes_one_directive_line_ending(self):
        for directive in ('#else', '#{else}'):
            for newline in ('\n', '\r\n'):
                with self.subTest(directive=directive, newline=newline):
                    source = (
                        '#if(false)' + newline + 'unused' + newline
                        + directive + ' \t' + newline + '  body' + newline
                        + '#end' + newline + 'tail'
                    )
                    self.assertEqual(
                        '  body' + newline + 'tail', Template(source).merge({})
                    )

    def test_intentional_blank_lines_are_preserved(self):
        self.assertEqual(
            '\n1\n\n2\ntail',
            Template('#foreach($i in [1..2])\n\n$i\n#end\ntail').merge({}),
        )
        self.assertEqual(
            '\nbody\ntail',
            Template('#if(false)bad#else\n\nbody\n#end\ntail').merge({}),
        )

    def test_inline_whitespace_is_preserved(self):
        self.assertEqual(
            ' \t1  \t2 ',
            Template('#foreach($i in [1..2]) \t$i #end').merge({}),
        )
        self.assertEqual(
            ' \tbody', Template('#if(false)bad#else \tbody#end').merge({})
        )

    def test_nested_directives_do_not_add_blank_lines(self):
        source = (
            '#foreach($i in [1..2])\n'
            '#if($i == 1)\nfirst\n#else\nsecond\n#end\n#end'
        )
        self.assertEqual('first\nsecond\n', Template(source).merge({}))
