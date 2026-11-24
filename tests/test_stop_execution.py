from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Barrier
from unittest import TestCase

from airspeed import Template, TemplateExecutionError


class StopExecutionTestCase(TestCase):
    def test_stop_works_with_an_external_stream(self):
        output = StringIO()
        Template('before#stop after').merge_to({}, output)
        output.write(' appended by caller')
        self.assertEqual('before appended by caller', output.getvalue())

    def test_stop_skips_later_function_calls(self):
        calls = []
        template = Template('before#stop$touch()')
        self.assertEqual('before', template.merge({'touch': lambda: calls.append(1)}))
        self.assertEqual([], calls)

    def test_stop_ends_all_enclosing_loops(self):
        calls = []

        def touch(outer, inner):
            calls.append((outer, inner))
            return f'{outer}{inner};'

        template = Template(
            '#foreach($outer in [1..3])#foreach($inner in [1..3])'
            '$touch($outer, $inner)#if($inner == 2)#stop#end#end#end'
            '$touch(9, 9)')
        self.assertEqual('11;12;', template.merge({'touch': touch}))
        self.assertEqual([(1, 1), (1, 2)], calls)

    def test_stop_in_macro_ends_the_calling_template(self):
        calls = []
        template = Template(
            '#macro(halt)inside#stop ignored#end'
            'before#halt() after$touch()')
        self.assertEqual('beforeinside', template.merge({'touch': lambda: calls.append(1)}))
        self.assertEqual([], calls)

    def test_stop_in_parsed_template_ends_the_calling_template(self):
        calls = []
        class Loader:
            def load_template(self, name):
                return Template('inside#stop ignored', filename=name)

        template = Template('before#parse("child") after$touch()')
        self.assertEqual('beforeinside', template.merge(
            {'touch': lambda: calls.append(1)}, loader=Loader()))
        self.assertEqual([], calls)

    def test_stop_in_evaluated_template_ends_the_calling_template(self):
        calls = []
        template = Template('before#evaluate($content) after$touch()')
        self.assertEqual('beforeinside', template.merge({
            'content': 'inside#stop ignored',
            'touch': lambda: calls.append(1),
        }))
        self.assertEqual([], calls)

    def test_stop_in_defined_block_aborts_the_calling_expression(self):
        calls = []
        template = Template(
            '#define($halt)#stop$touch()#end'
            'before$touch($halt()) after')
        self.assertEqual('before', template.merge({
            'touch': lambda *args: calls.append(args)}))
        self.assertEqual([], calls)

    def test_stop_in_interpolated_string_aborts_the_assignment(self):
        calls = []
        template = Template('before#set($x = "value#stop$touch()")$touch() after')
        self.assertEqual('before', template.merge({'touch': lambda: calls.append(1)}))
        self.assertEqual([], calls)

    def test_template_can_be_merged_again_after_stopping(self):
        template = Template('$name#stop ignored')
        self.assertEqual('first', template.merge({'name': 'first'}))
        self.assertEqual('second', template.merge({'name': 'second'}))

    def test_stopping_concurrent_renders_is_independent(self):
        barrier = Barrier(2)

        def wait():
            barrier.wait(timeout=5)
            return ''

        def render(label):
            return Template('$label$wait()#stop ignored').merge({
                'label': label, 'wait': wait})

        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(['one', 'two'], list(executor.map(render, ('one', 'two'))))

    def test_stop_does_not_hide_an_earlier_execution_error(self):
        def fail():
            raise ValueError('failure')

        with self.assertRaises(TemplateExecutionError) as caught:
            Template('$fail()#stop').merge({'fail': fail})
        self.assertIsInstance(caught.exception.__cause__, ValueError)
