from unittest import TestCase

from airspeed import Template


class AlternateValueTestCase(TestCase):
    def test_alternate_in_assignment_retains_its_numeric_type(self):
        template = Template('#set($total = ${missing|41} + 1)$total')
        self.assertEqual('42', template.merge({}))

    def test_alternate_in_condition(self):
        template = Template('#if(${missing|true})yes#else no#end')
        self.assertEqual('yes', template.merge({}))

    def test_alternates_in_list_and_macro_arguments(self):
        template = Template(
            '#macro(show $value)$value;#end'
            '#set($values = [${missing|1}, ${present|2}])'
            '#foreach($value in $values)#show($value)#end'
            '#show(${missing|3})')
        self.assertEqual('1;4;3;', template.merge({'present': 4}))

    def test_alternate_in_method_argument_uses_calling_namespace(self):
        template = Template('$format(${missing|$fallback})')
        self.assertEqual('<guest>', template.merge({
            'format': lambda value: '<' + value + '>',
            'fallback': 'guest',
        }))

    def test_false_and_empty_references_use_the_alternate(self):
        template = Template('${value|"guest"}')
        for value in (None, False, 0, 0.0, '', [], {}):
            with self.subTest(value=value):
                self.assertEqual('guest', template.merge({'value': value}))

    def test_alternate_is_evaluated_only_when_needed(self):
        calls = []

        def fallback():
            calls.append('fallback')
            return 'guest'

        template = Template('#set($name = ${value|$fallback()})$name')
        self.assertEqual('member', template.merge({
            'value': 'member', 'fallback': fallback}))
        self.assertEqual([], calls)
        self.assertEqual('guest', template.merge({'fallback': fallback}))
        self.assertEqual(['fallback'], calls)

    def test_false_values_without_an_alternate_are_preserved(self):
        template = Template('${value}')
        for value, expected in ((False, 'False'), (0, '0'), ('', '')):
            with self.subTest(value=value):
                self.assertEqual(expected, template.merge({'value': value}))

    def test_silent_missing_references_are_unchanged(self):
        template = Template('$!missing|$!{missing}|$missing')
        self.assertEqual('||$missing', template.merge({}))
