#!/usr/bin/env python

from unittest import TestCase, main
import airspeed


class ParserTestCase(TestCase):

    def test_parser_returns_input_when_there_is_nothing_to_substitute(self):
        parser = airspeed.Parser()
        template = airspeed.Template("<html></html>")
        parsedContent = parser.merge(template)
        self.assertEquals("<html></html>", parsedContent)

    def test_parser_substitutes_string_added_to_the_context(self):
        parser = airspeed.Parser()
        template = airspeed.Template("Hello $name")
        parser["name"] = "Chris"
        parsedContent = parser.merge(template)
        self.assertEquals("Hello Chris", parsedContent)

    def test_unmatched_name_does_not_get_substituted(self):
        parser = airspeed.Parser()
        template = airspeed.Template("Hello $name")
        parsedContent = parser.merge(template)
        self.assertEquals("Hello $name", parsedContent)

    def test_silent_substitution_for_unmatched_values(self):
        parser = airspeed.Parser()
        template = airspeed.Template("Hello $!name")
        parsedContent = parser.merge(template)
        self.assertEquals("Hello ", parsedContent)
        parser["name"] = "world"
        self.assertEquals("Hello world", parser.merge(template))

    def test_embed_substitution_value_in_braces_gets_handled(self):
        parser = airspeed.Parser()
        template = airspeed.Template("Hello ${name}.")
        parser["name"] = "World"
        self.assertEquals("Hello World.", parser.merge(template))

    def test_unmatched_braces_raises_exception(self):
        parser = airspeed.Parser()
        template = airspeed.Template("Hello ${name.")
        parser["name"] = "World"
        self.assertRaises(airspeed.TemplateSyntaxError, parser.merge, template)

    def test_unmatched_trailing_brace_preserved(self):
        parser = airspeed.Parser()
        template = airspeed.Template("Hello $name}.")
        parser["name"] = "World"
        self.assertEquals("Hello World}.", parser.merge(template))

    def test_can_return_value_from_an_attribute_of_a_context_object(self):
        parser = airspeed.Parser()
        template = airspeed.Template("Hello $name.first_name")
        class MyObj: pass
        o = MyObj()
        o.first_name = 'Chris'
        parser["name"] = o
        self.assertEquals("Hello Chris", parser.merge(template))

    def test_can_return_value_from_an_attribute_of_a_context_object(self):
        parser = airspeed.Parser()
        template = airspeed.Template("Hello $name.first_name")
        class MyObj: pass
        o = MyObj()
        o.first_name = 'Chris'
        parser["name"] = o
        self.assertEquals("Hello Chris", parser.merge(template))

    def test_can_return_value_from_a_method_of_a_context_object(self):
        parser = airspeed.Parser()
        template = airspeed.Template("Hello $name.first_name()")
        class MyObj:
            def first_name(self): return "Chris"
        parser["name"] = MyObj()
        self.assertEquals("Hello Chris", parser.merge(template))

    def test_when_if_statement_resolves_to_true_the_content_is_returned(self):
        parser = airspeed.Parser()
        template = airspeed.Template("Hello #if ($name)your name is ${name}#end Good to see you")
        parser["name"] = "Steve"
        self.assertEquals("Hello your name is Steve Good to see you", parser.merge(template))

    def test_when_if_statement_resolves_to_false_the_content_is_skipped(self):
        parser = airspeed.Parser()
        template = airspeed.Template("Hello #if ($show_greeting)your name is ${name}#end Good to see you")
        parser["name"] = "Steve"
        parser["show_greeting"] = False
        self.assertEquals("Hello  Good to see you", parser.merge(template))

    def test_when_if_statement_is_nested_inside_a_successful_enclosing_if_it_gets_evaluated(self):
        parser = airspeed.Parser()
        template = airspeed.Template("Hello #if ($show_greeting)your name is ${name}.#if ($is_birthday) Happy Birthday.#end#end Good to see you")
        parser["name"] = "Steve"
        parser["show_greeting"] = False
        self.assertEquals("Hello  Good to see you", parser.merge(template))
        parser["show_greeting"] = True
        self.assertEquals("Hello your name is Steve. Good to see you", parser.merge(template))
        parser["is_birthday"] = True
        self.assertEquals("Hello your name is Steve. Happy Birthday. Good to see you", parser.merge(template))

    def test_new_lines_in_templates_are_permitted(self):
        parser = airspeed.Parser()
        template = airspeed.Template("hello #if ($show_greeting)${name}.\n#if($is_birthday)Happy Birthday\n#end.\n#endOff out later?")
        parser["name"] = "Steve"
        parser["show_greeting"] = True
        parser["is_birthday"] = True
        self.assertEquals("hello Steve.\nHappy Birthday\n.\nOff out later?", parser.merge(template))

    def test_foreach_with_plain_content_loops_correctly(self):
        parser = airspeed.Parser()
        template = airspeed.Template("#foreach ($name in $names)Hello you. #end")
        parser["names"] = ["Chris", "Steve"]
        self.assertEquals("Hello you. Hello you. ", parser.merge(template))

    def test_foreach_skipped_when_nested_in_a_failing_if(self):
        parser = airspeed.Parser()
        template = airspeed.Template("#if ($false_value)#foreach ($name in $names)Hello you. #end#end")
        parser["false_value"] = False
        parser["names"] = ["Chris", "Steve"]
        self.assertEquals("", parser.merge(template))

    def test_foreach_with_expression_content_loops_correctly(self):
        parser = airspeed.Parser()
        template = airspeed.Template("#foreach ($name in $names)Hello $you. #end")
        parser["you"] = "You"
        parser["names"] = ["Chris", "Steve"]
        self.assertEquals("Hello You. Hello You. ", parser.merge(template))

    def test_foreach_makes_loop_variable_accessible(self):
        parser = airspeed.Parser()
        template = airspeed.Template("#foreach ($name in $names)Hello $name. #end")
        parser["names"] = ["Chris", "Steve"]
        self.assertEquals("Hello Chris. Hello Steve. ", parser.merge(template))

    def test_loop_variable_not_accessible_after_loop(self):
        parser = airspeed.Parser()
        template = airspeed.Template("#foreach ($name in $names)Hello $name. #end$name")
        parser["names"] = ["Chris", "Steve"]
        self.assertEquals("Hello Chris. Hello Steve. $name", parser.merge(template))

    def test_loop_variables_do_not_clash_in_nested_loops(self):
        parser = airspeed.Parser()
        template = airspeed.Template("#foreach ($word in $greetings)$word to#foreach ($word in $names) $word#end. #end")
        parser["greetings"] = ["Hello", "Goodbye"]
        parser["names"] = ["Chris", "Steve"]
        self.assertEquals("Hello to Chris Steve. Goodbye to Chris Steve. ", parser.merge(template))



if __name__ == '__main__':
    reload(airspeed)
    try: main()
    except SystemExit: pass
