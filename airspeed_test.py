#!/usr/bin/env python

from unittest import TestCase, main
import airspeed


class TemplateTestCase(TestCase):

    def test_parser_returns_input_when_there_is_nothing_to_substitute(self):
        template = airspeed.Template("<html></html>")
        self.assertEquals("<html></html>", template.merge({}))

    def test_parser_substitutes_string_added_to_the_context(self):
        template = airspeed.Template("Hello $name")
        self.assertEquals("Hello Chris", template.merge({"name": "Chris"}))

    def test_dollar_left_untouched(self):
        template = airspeed.Template("Hello $ ")
        self.assertEquals("Hello $ ", template.merge({}))
        template = airspeed.Template("Hello $")
        self.assertEquals("Hello $", template.merge({}))

    def test_unmatched_name_does_not_get_substituted(self):
        template = airspeed.Template("Hello $name")
        self.assertEquals("Hello $name", template.merge({}))

    def test_silent_substitution_for_unmatched_values(self):
        template = airspeed.Template("Hello $!name")
        self.assertEquals("Hello world", template.merge({"name": "world"}))
        self.assertEquals("Hello ", template.merge({}))

    def test_embed_substitution_value_in_braces_gets_handled(self):
        template = airspeed.Template("Hello ${name}.")
        self.assertEquals("Hello World.", template.merge({"name": "World"}))

    def test_unmatched_braces_raises_exception(self):
        template = airspeed.Template("Hello ${name.")
        self.assertRaises(airspeed.TemplateSyntaxError, template.merge, {})

    def test_unmatched_trailing_brace_preserved(self):
        template = airspeed.Template("Hello $name}.")
        self.assertEquals("Hello World}.", template.merge({"name": "World"}))

    def test_can_return_value_from_an_attribute_of_a_context_object(self):
        template = airspeed.Template("Hello $name.first_name")
        class MyObj: pass
        o = MyObj()
        o.first_name = 'Chris'
        self.assertEquals("Hello Chris", template.merge({"name": o}))

    def test_can_return_value_from_an_attribute_of_a_context_object(self):
        template = airspeed.Template("Hello $name.first_name")
        class MyObj: pass
        o = MyObj()
        o.first_name = 'Chris'
        self.assertEquals("Hello Chris", template.merge({"name": o}))

    def test_can_return_value_from_a_method_of_a_context_object(self):
        template = airspeed.Template("Hello $name.first_name()")
        class MyObj:
            def first_name(self): return "Chris"
        self.assertEquals("Hello Chris", template.merge({"name": MyObj()}))

    def test_when_if_statement_resolves_to_true_the_content_is_returned(self):
        template = airspeed.Template("Hello #if ($name)your name is ${name}#end Good to see you")
        self.assertEquals("Hello your name is Steve Good to see you", template.merge({"name": "Steve"}))

    def test_when_if_statement_resolves_to_false_the_content_is_skipped(self):
        template = airspeed.Template("Hello #if ($show_greeting)your name is ${name}#end Good to see you")
        self.assertEquals("Hello  Good to see you", template.merge({"name": "Steve", "show_greeting": False}))

    def test_when_if_statement_is_nested_inside_a_successful_enclosing_if_it_gets_evaluated(self):
        template = airspeed.Template("Hello #if ($show_greeting)your name is ${name}.#if ($is_birthday) Happy Birthday.#end#end Good to see you")
        namespace = {"name": "Steve", "show_greeting": False}
        self.assertEquals("Hello  Good to see you", template.merge(namespace))
        namespace["show_greeting"] = True
        self.assertEquals("Hello your name is Steve. Good to see you", template.merge(namespace))
        namespace["is_birthday"] = True
        self.assertEquals("Hello your name is Steve. Happy Birthday. Good to see you", template.merge(namespace))

    def test_new_lines_in_templates_are_permitted(self):
        template = airspeed.Template("hello #if ($show_greeting)${name}.\n#if($is_birthday)Happy Birthday\n#end.\n#endOff out later?")
        namespace = {"name": "Steve", "show_greeting": True, "is_birthday": True}
        self.assertEquals("hello Steve.\nHappy Birthday\n.\nOff out later?", template.merge(namespace))

    def test_foreach_with_plain_content_loops_correctly(self):
        template = airspeed.Template("#foreach ($name in $names)Hello you. #end")
        self.assertEquals("Hello you. Hello you. ", template.merge({"names": ["Chris", "Steve"]}))

    def test_foreach_skipped_when_nested_in_a_failing_if(self):
        template = airspeed.Template("#if ($false_value)#foreach ($name in $names)Hello you. #end#end")
        self.assertEquals("", template.merge({"false_value": False, "names": ["Chris", "Steve"]}))

    def test_foreach_with_expression_content_loops_correctly(self):
        template = airspeed.Template("#foreach ($name in $names)Hello $you. #end")
        self.assertEquals("Hello You. Hello You. ", template.merge({"you": "You", "names": ["Chris", "Steve"]}))

    def test_foreach_makes_loop_variable_accessible(self):
        template = airspeed.Template("#foreach ($name in $names)Hello $name. #end")
        self.assertEquals("Hello Chris. Hello Steve. ", template.merge({"names": ["Chris", "Steve"]}))

    def test_loop_variable_not_accessible_after_loop(self):
        template = airspeed.Template("#foreach ($name in $names)Hello $name. #end$name")
        self.assertEquals("Hello Chris. Hello Steve. $name", template.merge({"names": ["Chris", "Steve"]}))

    def test_loop_variables_do_not_clash_in_nested_loops(self):
        template = airspeed.Template("#foreach ($word in $greetings)$word to#foreach ($word in $names) $word#end. #end")
        namespace = {"greetings": ["Hello", "Goodbye"], "names": ["Chris", "Steve"]}
        self.assertEquals("Hello to Chris Steve. Goodbye to Chris Steve. ", template.merge(namespace))

    def test_loop_counter_variable_available_in_loops(self):
        template = airspeed.Template("#foreach ($word in $greetings)$velocityCount,#end")
        namespace = {"greetings": ["Hello", "Goodbye"]}
        self.assertEquals("1,2,", template.merge(namespace))

    def test_loop_counter_variables_do_not_clash_in_nested_loops(self):
        template = airspeed.Template("#foreach ($word in $greetings)Outer $velocityCount#foreach ($word in $names), inner $velocityCount#end. #end")
        namespace = {"greetings": ["Hello", "Goodbye"], "names": ["Chris", "Steve"]}
        self.assertEquals("Outer 1, inner 1, inner 2. Outer 2, inner 1, inner 2. ", template.merge(namespace))

    def test_can_use_an_integer_variable_defined_in_template(self):
        template = airspeed.Template("#set ($value = 10)$value")
        self.assertEquals("10", template.merge({}))

    def test_passed_in_namespace_not_modified_by_set(self):
        template = airspeed.Template("#set ($value = 10)$value")
        namespace = {}
        template.merge(namespace)
        self.assertEquals({}, namespace)

    def test_can_use_a_string_variable_defined_in_template(self):
        template = airspeed.Template('#set ($value = "Steve")$value')
        self.assertEquals("Steve", template.merge({}))

    def test_can_use_a_single_quoted_string_variable_defined_in_template(self):
        template = airspeed.Template("#set ($value = 'Steve')$value")
        self.assertEquals("Steve", template.merge({}))

    def test_single_line_comments_skipped(self):
        template = airspeed.Template('## comment\nStuff\nMore stuff## more comments $blah')
        self.assertEquals("Stuff\nMore stuff", template.merge({}))

    def test_multi_line_comments_skipped(self):
        template = airspeed.Template('Stuff#*\n more comments *#\n and more stuff')
        self.assertEquals("Stuff and more stuff", template.merge({}))

    def test_merge_to_stream(self):
        template = airspeed.Template('Hello $name!')
        from cStringIO import StringIO
        output = StringIO()
        template.merge_to({"name": "Chris"}, output)
        self.assertEquals('Hello Chris!', output.getvalue())

    def test_string_literal_can_contain_embedded_escaped_quotes(self):
        template = airspeed.Template('#set ($name = "\\"batman\\"")$name')
        self.assertEquals('"batman"', template.merge({}))

    def test_string_literal_can_contain_embedded_escaped_newlines(self):
        template = airspeed.Template('#set ($name = "\\\\batman\\nand robin")$name')
        self.assertEquals('\\batman\nand robin', template.merge({}))

    def test_else_block_evaluated_when_if_expression_false(self):
        template = airspeed.Template('#if ($value) true #else false #end')
        self.assertEquals(" false ", template.merge({}))

    def test_too_many_end_clauses_trigger_error(self):
        template = airspeed.Template('#if (1)true!#end #end ')
        self.assertRaises(airspeed.TemplateSyntaxError, template.merge, {})

    def test_can_call_function_with_one_parameter(self):
        def squared(number):
            return number * number
        template = airspeed.Template('$squared(8)')
        self.assertEquals("64", template.merge(locals()))
        some_var = 6
        template = airspeed.Template('$squared($some_var)')
        self.assertEquals("36", template.merge(locals()))
        template = airspeed.Template('$squared($squared($some_var))')
        self.assertEquals("1296", template.merge(locals()))

    def test_can_call_function_with_one_parameter(self):
        def multiply(number1, number2):
            return number1 * number2
        template = airspeed.Template('$multiply(2, 4)')
        self.assertEquals("8", template.merge(locals()))
        template = airspeed.Template('$multiply( 2 , 4 )')
        self.assertEquals("8", template.merge(locals()))
        value1, value2 = 4, 12
        template = airspeed.Template('$multiply($value1,$value2)')
        self.assertEquals("48", template.merge(locals()))

    def test_velocity_style_escaping(self): # example from Velocity docs
        template = airspeed.Template('''\
#set( $email = "foo" )
$email
\\$email
\\\\$email
\\\\\\$email''')
        self.assertEquals('''\
foo
$email
\\foo
\\$email''', template.merge({}))

#    def test_velocity_style_escaping_when_var_unset(self): # example from Velocity docs
#        template = airspeed.Template('''\
#$email
#\$email
#\\$email
#\\\$email''')
#        self.assertEquals('''\
#$email
#\$email
#\\$email
#\\\$email''', template.merge({}))

    def test_true_elseif_evaluated_when_if_is_false(self):
        template = airspeed.Template('#if ($value1) one #elseif ($value2) two #end')
        value1, value2 = False, True
        self.assertEquals(' two ', template.merge(locals()))

    def test_false_elseif_skipped_when_if_is_true(self):
        template = airspeed.Template('#if ($value1) one #elseif ($value2) two #end')
        value1, value2 = True, False
        self.assertEquals(' one ', template.merge(locals()))

    def test_first_true_elseif_evaluated_when_if_is_false(self):
        template = airspeed.Template('#if ($value1) one #elseif ($value2) two #elseif($value3) three #end')
        value1, value2, value3 = False, True, True
        self.assertEquals(' two ', template.merge(locals()))

    def test_illegal_to_have_elseif_after_else(self):
        template = airspeed.Template('#if ($value1) one #else two #elseif($value3) three #end')
        self.assertRaises(airspeed.TemplateSyntaxError, template.merge, {})

    def test_else_evaluated_when_if_and_elseif_are_false(self):
        template = airspeed.Template('#if ($value1) one #elseif ($value2) two #else three #end')
        value1, value2 = False, False
        self.assertEquals(' three ', template.merge(locals()))

    def test_syntax_error_contains_line_and_column_pos(self):
        try: airspeed.Template('#if ( $hello )\n\n#elseif blah').merge({})
        except airspeed.TemplateSyntaxError, e:
            self.assertEquals((3, 9), (e.line, e.column))
        else: self.fail('expected error')
        try: airspeed.Template('#else blah').merge({})
        except airspeed.TemplateSyntaxError, e:
            self.assertEquals((1, 1), (e.line, e.column))
        else: self.fail('expected error')

    def test_get_position_strings_in_syntax_error(self):
        try: airspeed.Template('#else whatever').merge({})
        except airspeed.TemplateSyntaxError, e:
            self.assertEquals(['#else whatever',
                               '^'], e.get_position_strings())
        else: self.fail('expected error')

    def test_get_position_strings_in_syntax_error_when_newline_after_error(self):
        try: airspeed.Template('#else whatever\n').merge({})
        except airspeed.TemplateSyntaxError, e:
            self.assertEquals(['#else whatever',
                               '^'], e.get_position_strings())
        else: self.fail('expected error')

    def test_get_position_strings_in_syntax_error_when_newline_before_error(self):
        try: airspeed.Template('foobar\n  #else whatever\n').merge({})
        except airspeed.TemplateSyntaxError, e:
            self.assertEquals(['  #else whatever',
                               '  ^'], e.get_position_strings())
        else: self.fail('expected error')

    def test_compare_greater_than_operator(self):
        template = airspeed.Template('#if ( $value > 1 )yes#end')
        self.assertEquals('', template.merge({'value': 0}))
        self.assertEquals('', template.merge({'value': 1}))
        self.assertEquals('yes', template.merge({'value': 2}))

    def test_compare_greater_than_or_equal_operator(self):
        template = airspeed.Template('#if ( $value >= 1 )yes#end')
        self.assertEquals('', template.merge({'value': 0}))
        self.assertEquals('yes', template.merge({'value': 1}))
        self.assertEquals('yes', template.merge({'value': 2}))

    def test_compare_less_than_operator(self):
        template = airspeed.Template('#if ( $value < 1 )yes#end')
        self.assertEquals('yes', template.merge({'value': 0}))
        self.assertEquals('', template.merge({'value': 1}))
        self.assertEquals('', template.merge({'value': 2}))

    def test_compare_less_than_or_equal_operator(self):
        template = airspeed.Template('#if ( $value <= 1 )yes#end')
        self.assertEquals('yes', template.merge({'value': 0}))
        self.assertEquals('yes', template.merge({'value': 1}))
        self.assertEquals('', template.merge({'value': 2}))

    def test_compare_equality_operator(self):
        template = airspeed.Template('#if ( $value == 1 )yes#end')
        self.assertEquals('', template.merge({'value': 0}))
        self.assertEquals('yes', template.merge({'value': 1}))
        self.assertEquals('', template.merge({'value': 2}))

    def test_cannot_define_macro_to_override_reserved_statements(self):
        for reserved in ('if', 'else', 'elseif', 'set', 'macro', 'foreach', 'parse', 'include', 'stop', 'end'):
            template = airspeed.Template('#macro ( %s $value) $value #end' % reserved)
            self.assertRaises(airspeed.TemplateSyntaxError, template.merge, {})

    def test_cannot_call_undefined_macro(self):
        template = airspeed.Template('#undefined()')
        self.assertRaises(Exception, template.merge, {})

    def test_define_and_use_macro_with_no_parameters(self):
        template = airspeed.Template('#macro ( hello)hi#end#hello ()#hello()')
        self.assertEquals('hihi', template.merge({'text': 'hello'}))

    def test_define_and_use_macro_with_one_parameter(self):
        template = airspeed.Template('#macro ( bold $value)<strong>$value</strong>#end#bold ($text)')
        self.assertEquals('<strong>hello</strong>', template.merge({'text': 'hello'}))

    def test_use_of_macro_name_is_case_insensitive(self):
        template = airspeed.Template('#macro ( bold $value)<strong>$value</strong>#end#BoLd ($text)')
        self.assertEquals('<strong>hello</strong>', template.merge({'text': 'hello'}))

    def test_define_and_use_macro_with_two_parameter(self):
        template = airspeed.Template('#macro (addition $value1 $value2 )$value1+$value2#end#addition (1 2)')
        self.assertEquals('1+2', template.merge({}))
        template = airspeed.Template('#macro (addition $value1 $value2 )$value1+$value2#end#addition( $one   $two )')
        self.assertEquals('ONE+TWO', template.merge({'one': 'ONE', 'two': 'TWO'}))

    def test_cannot_redefine_macro(self):
        template = airspeed.Template('#macro ( hello)hi#end#macro(hello)again#end')
        self.assertRaises(Exception, template.merge, {}) ## Should this be TemplateSyntaxError?

    def test_include_directive_gives_error_if_no_loader_provided(self):
        template = airspeed.Template('#include ("foo.tmpl")')
        self.assertRaises(airspeed.TemplateError, template.merge, {})

    def test_include_directive_yields_loader_error_if_included_content_not_found(self):
        class BrokenLoader:
            def load_text(self, name):
                raise IOError(name)
        template = airspeed.Template('#include ("foo.tmpl")')
        self.assertRaises(IOError, template.merge, {}, loader=BrokenLoader())

    def test_valid_include_directive_include_content(self):
        class WorkingLoader:
            def load_text(self, name):
                if name == 'foo.tmpl':
                    return "howdy"
        template = airspeed.Template('Message is: #include ("foo.tmpl")!')
        self.assertEquals('Message is: howdy!', template.merge({}, loader=WorkingLoader()))

    def test_parse_directive_gives_error_if_no_loader_provided(self):
        template = airspeed.Template('#parse ("foo.tmpl")')
        self.assertRaises(airspeed.TemplateError, template.merge, {})

    def test_parse_directive_yields_loader_error_if_parsed_content_not_found(self):
        class BrokenLoader:
            def load_template(self, name):
                raise IOError(name)
        template = airspeed.Template('#parse ("foo.tmpl")')
        self.assertRaises(IOError, template.merge, {}, loader=BrokenLoader())

    def test_valid_parse_directive_outputs_parsed_content(self):
        class WorkingLoader:
            def load_template(self, name):
                if name == 'foo.tmpl':
                    return airspeed.Template("$message")
        template = airspeed.Template('Message is: #parse ("foo.tmpl")!')
        self.assertEquals('Message is: hola!', template.merge({'message': 'hola'}, loader=WorkingLoader()))
        template = airspeed.Template('Message is: #parse ($foo)!')
        self.assertEquals('Message is: hola!', template.merge({'foo': 'foo.tmpl', 'message': 'hola'}, loader=WorkingLoader()))

#
# TODO:
#
#  Math expressions
#  Gobbling up whitespace (tricky!)
#  range literals
#  list literals
#  Bind #macro calls at compile time?
#  Interpolated strings
#  Directives inside string literals
#  map literals
#  Sub-object assignment:  #set( $customer.Behavior = $primate )
#  Q. What is scope of #set ($customer.Name = 'john')  ???
#  Scope of #set across if/elseif/else?
#  Scope of namespace for #include etc
#


if __name__ == '__main__':
    reload(airspeed)
    try: main()
    except SystemExit: pass
