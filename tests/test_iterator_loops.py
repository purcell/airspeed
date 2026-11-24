from unittest import TestCase

from airspeed import Template, TemplateExecutionError


class IteratorLoopTestCase(TestCase):
    def test_loop_accepts_an_iterator(self):
        template = Template('#foreach($value in $values)$value;#end')
        self.assertEqual('1;2;3;', template.merge({'values': iter([1, 2, 3])}))

    def test_generator_loop_metadata(self):
        template = Template(
            '#foreach($value in $values)'
            '$foreach.count/$foreach.index/$foreach.first/$foreach.last/'
            '$foreach.hasNext/$velocityCount/$velocityHasNext:$value;#end')
        self.assertEqual(
            '1/0/True/False/True/1/True:a;'
            '2/1/False/True/False/2/False:b;',
            template.merge({'values': (value for value in ('a', 'b'))}))

    def test_empty_and_single_item_iterators(self):
        template = Template(
            'before#foreach($value in $values)'
            '$value:$foreach.first:$foreach.last:$foreach.hasNext;#end after')
        self.assertEqual('before after', template.merge({'values': iter(())}))
        self.assertEqual('before7:True:True:False; after',
                         template.merge({'values': iter((7,))}))

    def test_none_is_a_valid_item(self):
        template = Template(
            '#foreach($value in $values)'
            '#if($value == null)empty#else$value#end;#end')
        self.assertEqual('empty;2;', template.merge({'values': iter((None, 2))}))

    def test_generator_is_not_materialized_before_rendering(self):
        yielded = []
        rendered = []

        def values():
            for value in range(100):
                yielded.append(value)
                yield value

        def render(value):
            # Retain only enough lookahead to provide hasNext/last metadata.
            self.assertLessEqual(len(yielded) - len(rendered), 2)
            rendered.append(value)
            return ''

        template = Template('#foreach($value in $values)$render($value)#end')
        self.assertEqual('', template.merge({'values': values(), 'render': render}))
        self.assertEqual(list(range(100)), rendered)

    def test_nested_iterators_preserve_outer_loop_metadata(self):
        template = Template(
            '#foreach($outer in $values)$outer:${foreach.index}['
            '#foreach($inner in $children())$inner:$foreach.index;#end'
            ']$foreach.index;#end')
        self.assertEqual('a:0[x:0;y:1;]0;b:1[x:0;y:1;]1;', template.merge({
            'values': iter(('a', 'b')),
            'children': lambda: iter(('x', 'y')),
        }))

    def test_iterator_errors_remain_execution_errors(self):
        def values():
            yield 1
            raise RuntimeError('data source failed')

        template = Template('#foreach($value in $values)$value#end')
        with self.assertRaises(TemplateExecutionError) as caught:
            template.merge({'values': values()})
        self.assertIsInstance(caught.exception.__cause__, RuntimeError)
        self.assertEqual('data source failed', str(caught.exception.__cause__))
