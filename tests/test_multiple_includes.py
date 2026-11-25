from io import StringIO
from unittest import TestCase

from airspeed import Template, TemplateExecutionError, TemplateSyntaxError


class TextLoader:
    def __init__(self):
        self.names = []

    def load_text(self, name):
        self.names.append(name)
        if name == 'missing.txt':
            raise IOError(name)
        return {'first.txt': '$value', 'second.txt': '#set($value = 1)'}[name]


class MultipleIncludeTests(TestCase):
    def test_includes_each_file_in_order_without_evaluating_its_contents(self):
        for separator in (',', ',\n ', ' ', '\n'):
            with self.subTest(separator=separator):
                loader = TextLoader()
                template = Template('#include("first.txt"' + separator + '"second.txt")')
                self.assertEqual(template.merge({'value': 'expanded'}, loader=loader),
                                 '$value#set($value = 1)')
                self.assertEqual(loader.names, ['first.txt', 'second.txt'])

    def test_accepts_references_and_interpolated_filenames(self):
        loader = TextLoader()
        template = Template('#include($first, "${stem}.txt")')
        result = template.merge({'first': 'first.txt', 'stem': 'second'}, loader=loader)
        self.assertEqual(result, '$value#set($value = 1)')

    def test_retains_single_filename_and_surrounding_whitespace(self):
        loader = TextLoader()
        self.assertEqual(Template("#include( 'first.txt' \n )").merge({}, loader=loader),
                         '$value')

    def test_reports_a_later_loader_error_without_loading_following_files(self):
        loader = TextLoader()
        output = StringIO()
        template = Template('#include("first.txt", "missing.txt", "second.txt")')
        with self.assertRaises(TemplateExecutionError) as caught:
            template.merge_to({}, output, loader=loader)
        self.assertIsInstance(caught.exception.__cause__, IOError)
        self.assertEqual(loader.names, ['first.txt', 'missing.txt'])
        self.assertEqual(output.getvalue(), '$value')

    def test_requires_a_filename_and_rejects_missing_arguments(self):
        for source in ('#include()', '#include("first.txt",)',
                       '#include("first.txt", , "second.txt")',
                       '#include("first.txt""second.txt")'):
            with self.subTest(source=source):
                with self.assertRaises(TemplateSyntaxError):
                    Template(source).merge({}, loader=TextLoader())
