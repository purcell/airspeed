from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from airspeed import CachingFileLoader, Template


class HyphenatedIdentifierTests(TestCase):
    def render(self, content, namespace=None):
        return Template(content, allow_hyphen_in_identifiers=True).merge(namespace or {})

    def test_default_is_unchanged_and_templates_do_not_share_the_option(self):
        namespace = {'first': 'old', 'first-name': 'new', 'n': 5}
        self.assertEqual('old-name', Template('$first-name').merge(namespace))
        self.assertEqual('new', self.render('$first-name', namespace))
        self.assertEqual('old-name', Template('$first-name').merge(namespace))
        self.assertEqual('4', Template('#set($x=$n-1)$x').merge(namespace))

    def test_references_properties_and_methods(self):
        self.assertEqual('a b c', self.render(
            '$first-name ${person.full-name} $get-name()',
            {'first-name': 'a', 'person': {'full-name': 'b'}, 'get-name': lambda: 'c'}))

    def test_assignment_and_loop_variables(self):
        self.assertEqual('12 ok', self.render(
            '#set($item-list=[1,2])#foreach($one-item in $item-list)$one-item#end'
            ' #set($person.full-name="ok")$person.full-name', {'person': {}}))

    def test_macro_and_define_parameters(self):
        self.assertEqual('x y', self.render(
            '#macro(show-name $first-name)$first-name#end#show-name("x") '
            '#define($last-name $given-name)$given-name#end$last-name("y")'))

    def test_interpolation_and_evaluate_inherit_the_option(self):
        self.assertEqual('hello Ada Ada', self.render(
            '#set($greeting="hello $first-name")$greeting #evaluate(\'$first-name\')',
            {'first-name': 'Ada'}))

    def test_subtraction_with_whitespace(self):
        self.assertEqual('3', self.render('#set($result=$item-count - 1)$result', {'item-count': 4}))

    def test_file_loader_applies_the_option_to_parsed_templates(self):
        with TemporaryDirectory() as directory:
            Path(directory, 'main.vm').write_text('#parse("child.vm")', encoding='utf-8')
            Path(directory, 'child.vm').write_text('$first-name', encoding='utf-8')
            loader = CachingFileLoader(directory, allow_hyphen_in_identifiers=True)
            template = loader.load_template('main.vm')
            self.assertEqual('Ada', template.merge({'first-name': 'Ada'}, loader))
            self.assertIs(template, loader.load_template('main.vm'))
