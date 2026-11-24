from io import StringIO
from unittest import TestCase

from airspeed import Template, TemplateSyntaxError


class BreakTestCase(TestCase):
    def test_break_exits_loop_without_running_remaining_statements(self):
        visited = []
        template = Template(
            '#foreach($i in [1..4])'
            '#if($i == 3)#break#end'
            '#set($ignored = $record($i))$i#end done')
        self.assertEqual('12 done', template.merge({'record': visited.append}))
        self.assertEqual([1, 2], visited)

    def test_break_only_exits_innermost_loop(self):
        template = Template(
            '#foreach($i in [1..2])$i:'
            '#foreach($j in [1..3])$j#break#end'
            '|#end done')
        self.assertEqual('1:1|2:1| done', template.merge({}))

    def test_break_in_unentered_branch_does_not_exit_loop(self):
        template = Template(
            '#foreach($i in [1..3])#if(false)#break#end$i#end')
        self.assertEqual('123', template.merge({}))

    def test_break_in_else_exits_loop(self):
        template = Template(
            '#foreach($i in [1..3])#if($i == 1)$i#else#break#end#end done')
        self.assertEqual('1 done', template.merge({}))

    def test_top_level_break_stops_template(self):
        visited = []
        template = Template('before#break#set($ignored = $record())after')
        self.assertEqual('before', template.merge({'record': lambda: visited.append(1)}))
        self.assertEqual([], visited)

    def test_break_works_with_external_output_stream(self):
        output = StringIO()
        Template('#foreach($i in [1..3])$i#break#end done').merge_to({}, output)
        self.assertEqual('1 done', output.getvalue())

    def test_break_in_macro_only_stops_macro(self):
        template = Template(
            '#macro(short)before#break after#end'
            '#foreach($i in [1..2])#short()|#end done')
        self.assertEqual('before|before| done', template.merge({}))

    def test_break_in_defined_block_only_stops_block(self):
        template = Template('#define($short)before#break after#end$short done')
        self.assertEqual('before done', template.merge({}))

    def test_break_in_parsed_template_only_stops_parsed_template(self):
        class Loader:
            def load_template(self, name):
                return Template('before#break after', filename=name)

        template = Template('#foreach($i in [1..2])#parse("short")|#end done')
        self.assertEqual('before|before| done', template.merge({}, loader=Loader()))

    def test_break_in_evaluated_template_only_stops_evaluation(self):
        template = Template(
            '#foreach($i in [1..2])#evaluate(\'before#break after\')|#end done')
        self.assertEqual('before|before| done', template.merge({}))

    def test_break_spellings_and_repeated_merge(self):
        for directive in ('#break', '#BREAK', '#{break}', '#break()'):
            with self.subTest(directive=directive):
                template = Template('#foreach($i in [1..3])$i' + directive + '#end done')
                self.assertEqual('1 done', template.merge({}))
                self.assertEqual('1 done', template.merge({}))

    def test_break_does_not_match_longer_names_or_escaped_text(self):
        self.assertEqual('#breakpoint #break', Template(r'#breakpoint \#break').merge({}))

    def test_break_is_reserved_macro_name(self):
        with self.assertRaises(TemplateSyntaxError):
            Template('#macro(break)ignored#end').merge({})

    def test_unsupported_scope_argument_is_rejected(self):
        with self.assertRaises(TemplateSyntaxError):
            Template('#break($foreach)').merge({})
