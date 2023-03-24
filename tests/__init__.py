# -*- coding: utf-8 -*-

import re
import sys

if sys.version_info >= (3, 0) and sys.version_info <= (3, 3):
    import imp
elif sys.version_info >= (3, 4):
    import importlib

from unittest import TestCase

# Make these tests runnable without needing 'nose' installed
try:
    import airspeed
except ImportError:
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    import airspeed

import six


class TemplateTestCase(TestCase):
    def assertRaisesExecutionError(self, exctype, func, *args, **kwargs):
        try:
            func(*args, **kwargs)
            self.fail("Expected TemplateExecutionError wrapping %s" % (exctype,))
        except airspeed.TemplateExecutionError as e:
            self.assertEqual(exctype, type(e.__cause__))

    def test_parser_returns_input_when_there_is_nothing_to_substitute(self):
        template = airspeed.Template("<html></html>")
        self.assertEqual("<html></html>", template.merge({}))

    def test_parser_substitutes_string_added_to_the_context(self):
        template = airspeed.Template("Hello $name")
        self.assertEqual("Hello Chris", template.merge({"name": "Chris"}))

    def test_dollar_left_untouched(self):
        template = airspeed.Template("Hello $ ")
        self.assertEqual("Hello $ ", template.merge({}))
        template = airspeed.Template("Hello $")
        self.assertEqual("Hello $", template.merge({}))

    def test_unmatched_name_does_not_get_substituted(self):
        template = airspeed.Template("Hello $name")
        self.assertEqual("Hello $name", template.merge({}))

    def test_silent_substitution_for_unmatched_values(self):
        template = airspeed.Template("Hello $!name")
        self.assertEqual("Hello world", template.merge({"name": "world"}))
        self.assertEqual("Hello ", template.merge({}))

    def test_formal_reference_in_an_if_condition(self):
        template = airspeed.Template("#if(${a.b.c})yes!#end")
        # reference in an if statement used to be a problem
        self.assertEqual("yes!", template.merge({"a": {"b": {"c": "d"}}}))
        self.assertEqual("", template.merge({}))

    def test_silent_formal_reference_in_an_if_condition(self):
        # the silent modifier shouldn't make a difference here
        template = airspeed.Template("#if($!{a.b.c})yes!#end")
        self.assertEqual("yes!", template.merge({"a": {"b": {"c": "d"}}}))
        self.assertEqual("", template.merge({}))
        # with or without curly braces
        template = airspeed.Template("#if($!a.b.c)yes!#end")
        self.assertEqual("yes!", template.merge({"a": {"b": {"c": "d"}}}))
        self.assertEqual("", template.merge({}))

    def test_reference_function_calls_in_if_conditions(self):
        template = airspeed.Template("#if(${a.b.c('cheese')})yes!#end")
        self.assertEqual(
            "yes!", template.merge({"a": {"b": {"c": lambda x: "hello %s" % x}}})
        )
        self.assertEqual("", template.merge({"a": {"b": {"c": lambda x: None}}}))
        self.assertEqual("", template.merge({}))

    def test_silent_reference_function_calls_in_if_conditions(self):
        # again, this shouldn't make any difference
        template = airspeed.Template("#if($!{a.b.c('cheese')})yes!#end")
        self.assertEqual(
            "yes!", template.merge({"a": {"b": {"c": lambda x: "hello %s" % x}}})
        )
        self.assertEqual("", template.merge({"a": {"b": {"c": lambda x: None}}}))
        self.assertEqual("", template.merge({}))
        # with or without braces
        template = airspeed.Template("#if($!a.b.c('cheese'))yes!#end")
        self.assertEqual(
            "yes!", template.merge({"a": {"b": {"c": lambda x: "hello %s" % x}}})
        )
        self.assertEqual("", template.merge({"a": {"b": {"c": lambda x: None}}}))
        self.assertEqual("", template.merge({}))

    def test_embed_substitution_value_in_braces_gets_handled(self):
        template = airspeed.Template("Hello ${name}.")
        self.assertEqual("Hello World.", template.merge({"name": "World"}))

    def test_unmatched_braces_raises_exception(self):
        template = airspeed.Template("Hello ${name.")
        self.assertRaises(airspeed.TemplateSyntaxError, template.merge, {})

    def test_unmatched_trailing_brace_preserved(self):
        template = airspeed.Template("Hello $name}.")
        self.assertEqual("Hello World}.", template.merge({"name": "World"}))

    def test_formal_reference_with_alternate_literal_value(self):
        template = airspeed.Template("${a|'hello'}")
        self.assertEqual("foo", template.merge({"a": "foo"}))
        self.assertEqual("hello", template.merge({}))

    def test_formal_reference_with_alternate_expression_value(self):
        template = airspeed.Template("${a|$b}")
        self.assertEqual("hello", template.merge({"b": "hello"}))

    def test_can_return_value_from_an_attribute_of_a_context_object(self):
        template = airspeed.Template("Hello $name.first_name")

        class MyObj:
            pass

        o = MyObj()
        o.first_name = "Chris"
        self.assertEqual("Hello Chris", template.merge({"name": o}))

    def test_can_return_value_from_a_method_of_a_context_object(self):
        template = airspeed.Template("Hello $name.first_name()")

        class MyObj:
            def first_name(self):
                return "Chris"

        self.assertEqual("Hello Chris", template.merge({"name": MyObj()}))

    def test_when_if_statement_resolves_to_true_the_content_is_returned(self):
        template = airspeed.Template(
            "Hello #if ($name)your name is ${name}#end Good to see you"
        )
        self.assertEqual(
            "Hello your name is Steve Good to see you",
            template.merge({"name": "Steve"}),
        )

    def test_when_if_statement_resolves_to_false_the_content_is_skipped(self):
        template = airspeed.Template(
            "Hello #if ($show_greeting)your name is ${name}#end Good to see you"
        )
        self.assertEqual(
            "Hello  Good to see you",
            template.merge({"name": "Steve", "show_greeting": False}),
        )

    def test_when_if_statement_is_nested_inside_a_successful_enclosing_if_it_gets_evaluated(
        self,
    ):
        template = airspeed.Template(
            "Hello #if ($show_greeting)your name is ${name}.#if ($is_birthday) Happy Birthday.#end#end Good to see you"
        )
        namespace = {"name": "Steve", "show_greeting": False}
        self.assertEqual("Hello  Good to see you", template.merge(namespace))
        namespace["show_greeting"] = True
        self.assertEqual(
            "Hello your name is Steve. Good to see you", template.merge(namespace)
        )
        namespace["is_birthday"] = True
        self.assertEqual(
            "Hello your name is Steve. Happy Birthday. Good to see you",
            template.merge(namespace),
        )

    def test_if_statement_considers_None_to_be_false(self):
        template = airspeed.Template("#if ($some_value)hide me#end")
        self.assertEqual("", template.merge({}))
        self.assertEqual("", template.merge({"some_value": None}))

    def test_if_statement_honours_custom_truth_value_of_objects(self):
        class BooleanValue(object):
            def __init__(self, value):
                self.value = value

            def __bool__(self):
                return self.value

            def __nonzero__(self):
                return self.__bool__()

        template = airspeed.Template("#if ($v)yes#end")
        self.assertEqual("", template.merge({"v": BooleanValue(False)}))
        self.assertEqual("yes", template.merge({"v": BooleanValue(True)}))

    def test_understands_boolean_literal_true(self):
        template = airspeed.Template("#set ($v = true)$v")
        self.assertEqual("True", template.merge({}))

    def test_understands_boolean_literal_false(self):
        template = airspeed.Template("#set ($v = false)$v")
        self.assertEqual("False", template.merge({}))

    def test_new_lines_in_templates_are_permitted(self):
        template = airspeed.Template(
            "hello #if ($show_greeting)${name}.\n#if($is_birthday)Happy Birthday\n#end.\n#endOff out later?"
        )
        namespace = {"name": "Steve", "show_greeting": True, "is_birthday": True}
        self.assertEqual(
            "hello Steve.\nHappy Birthday\n.\nOff out later?", template.merge(namespace)
        )

    def test_foreach_with_plain_content_loops_correctly(self):
        template = airspeed.Template("#foreach ($name in $names)Hello you. #end")
        self.assertEqual(
            "Hello you. Hello you. ", template.merge({"names": ["Chris", "Steve"]})
        )

    def test_foreach_skipped_when_nested_in_a_failing_if(self):
        template = airspeed.Template(
            "#if ($false_value)#foreach ($name in $names)Hello you. #end#end"
        )
        self.assertEqual(
            "", template.merge({"false_value": False, "names": ["Chris", "Steve"]})
        )

    def test_foreach_with_expression_content_loops_correctly(self):
        template = airspeed.Template("#foreach ($name in $names)Hello $you. #end")
        self.assertEqual(
            "Hello You. Hello You. ",
            template.merge({"you": "You", "names": ["Chris", "Steve"]}),
        )

    def test_foreach_makes_loop_variable_accessible(self):
        template = airspeed.Template("#foreach ($name in $names)Hello $name. #end")
        self.assertEqual(
            "Hello Chris. Hello Steve. ", template.merge({"names": ["Chris", "Steve"]})
        )

    def test_loop_variable_not_accessible_after_loop(self):
        template = airspeed.Template("#foreach ($name in $names)Hello $name. #end$name")
        self.assertEqual(
            "Hello Chris. Hello Steve. $name",
            template.merge({"names": ["Chris", "Steve"]}),
        )

    def test_loop_variables_do_not_clash_in_nested_loops(self):
        template = airspeed.Template(
            "#foreach ($word in $greetings)$word to#foreach ($word in $names) $word#end. #end"
        )
        namespace = {"greetings": ["Hello", "Goodbye"], "names": ["Chris", "Steve"]}
        self.assertEqual(
            "Hello to Chris Steve. Goodbye to Chris Steve. ", template.merge(namespace)
        )

    def test_loop_counter_variable_available_in_loops(self):
        template = airspeed.Template(
            "#foreach ($word in $greetings)$velocityCount,#end"
        )
        namespace = {"greetings": ["Hello", "Goodbye"]}
        self.assertEqual("1,2,", template.merge(namespace))

    def test_loop_counter_variable_available_in_loops_new(self):
        template = airspeed.Template(
            "#foreach ($word in $greetings)$foreach.count,#end"
        )
        namespace = {"greetings": ["Hello", "Goodbye"]}
        self.assertEqual("1,2,", template.merge(namespace))

    def test_loop_index_variable_available_in_loops_new(self):
        template = airspeed.Template(
            "#foreach ($word in $greetings)$foreach.index,#end"
        )
        namespace = {"greetings": ["Hello", "Goodbye"]}
        self.assertEqual("0,1,", template.merge(namespace))

    def test_loop_counter_variables_do_not_clash_in_nested_loops(self):
        template = airspeed.Template(
            "#foreach ($word in $greetings)Outer $velocityCount#foreach ($word in $names), inner $velocityCount#end. #end"
        )
        namespace = {"greetings": ["Hello", "Goodbye"], "names": ["Chris", "Steve"]}
        self.assertEqual(
            "Outer 1, inner 1, inner 2. Outer 2, inner 1, inner 2. ",
            template.merge(namespace),
        )

    def test_loop_counter_variables_do_not_clash_in_nested_loops_new(self):
        template = airspeed.Template(
            "#foreach ($word in $greetings)Outer $foreach.count#foreach ($word in $names), inner $foreach.count#end. #end"
        )
        namespace = {"greetings": ["Hello", "Goodbye"], "names": ["Chris", "Steve"]}
        self.assertEqual(
            "Outer 1, inner 1, inner 2. Outer 2, inner 1, inner 2. ",
            template.merge(namespace),
        )

    def test_loop_index_variables_do_not_clash_in_nested_loops_new(self):
        template = airspeed.Template(
            "#foreach ($word in $greetings)Outer $foreach.index#foreach ($word in $names), inner $foreach.index#end. #end"
        )
        namespace = {"greetings": ["Hello", "Goodbye"], "names": ["Chris", "Steve"]}
        self.assertEqual(
            "Outer 0, inner 0, inner 1. Outer 1, inner 0, inner 1. ",
            template.merge(namespace),
        )

    def test_has_next(self):
        template = airspeed.Template(
            "#foreach ($i in [1, 2, 3])$i. #if ($velocityHasNext)yes#end, #end"
        )
        self.assertEqual("1. yes, 2. yes, 3. , ", template.merge({}))

    def test_has_next_new(self):
        template = airspeed.Template(
            "#foreach ($i in [1, 2, 3])$i. #if ($foreach.hasNext)yes#end, #end"
        )
        self.assertEqual("1. yes, 2. yes, 3. , ", template.merge({}))

    def test_first(self):
        template = airspeed.Template(
            "#foreach ($i in [1, 2, 3])$i. #if ($foreach.first)yes#end, #end"
        )
        self.assertEqual("1. yes, 2. , 3. , ", template.merge({}))

    def test_last(self):
        template = airspeed.Template(
            "#foreach ($i in [1, 2, 3])$i. #if ($foreach.last)yes#end, #end"
        )
        self.assertEqual("1. , 2. , 3. yes, ", template.merge({}))

    def test_can_use_an_integer_variable_defined_in_template(self):
        template = airspeed.Template("#set ($value = 10)$value")
        self.assertEqual("10", template.merge({}))

    def test_passed_in_namespace_not_modified_by_set(self):
        template = airspeed.Template("#set ($value = 10)$value")
        namespace = {}
        template.merge(namespace)
        self.assertEqual({}, namespace)

    def test_can_use_a_string_variable_defined_in_template(self):
        template = airspeed.Template('#set ($value = "Steve")$value')
        self.assertEqual("Steve", template.merge({}))

    def test_can_use_a_single_quoted_string_variable_defined_in_template(self):
        template = airspeed.Template("#set ($value = 'Steve')$value")
        self.assertEqual("Steve", template.merge({}))

    def test_single_line_comments_skipped(self):
        template = airspeed.Template(
            "## comment\nStuff\nMore stuff## more comments $blah"
        )
        self.assertEqual("Stuff\nMore stuff", template.merge({}))

    def test_multi_line_comments_skipped(self):
        template = airspeed.Template("Stuff#*\n more comments *#\n and more stuff")
        self.assertEqual("Stuff and more stuff", template.merge({}))

    def test_merge_to_stream(self):
        template = airspeed.Template("Hello $name!")
        output = six.StringIO()
        template.merge_to({"name": "Chris"}, output)
        self.assertEqual("Hello Chris!", output.getvalue())

    # TODO: this VTL string is invalid in AWS API Gateway (results in 500 error)
    # def test_string_literal_can_contain_embedded_escaped_quotes(self):
    #     template = airspeed.Template('#set ($name = "\\"batman\\"")$name')
    #     self.assertEqual('"batman"', template.merge({}))

    def test_string_literal_can_contain_embedded_escaped_newlines(self):
        template = airspeed.Template('#set ($name = "\\\\batman\\nand robin")$name')
        self.assertEqual("\\batman\nand robin", template.merge({}))

    def test_string_literal_with_inner_double_quotes(self):
        template = airspeed.Template("#set($d = '{\"a\": 2}')$d")
        self.assertEqual('{"a": 2}', template.merge({}))

    def test_string_interpolation_with_inner_double_double_quotes(self):
        template = airspeed.Template('#set($d = "{""a"": 2}")$d')
        self.assertEqual('{"a": 2}', template.merge({}))

    def test_string_interpolation_with_multiple_double_quotes(self):
        template = airspeed.Template(r'#set($d = "1\\""2""3")$d')
        # Note: in AWS this would yield r'1\\"2"3', as backslashes are not escaped
        self.assertEqual(r'1\"2"3', template.merge({}))

    def test_else_block_evaluated_when_if_expression_false(self):
        template = airspeed.Template("#if ($value) true #else false #end")
        self.assertEqual(" false ", template.merge({}))

    def test_curly_else(self):
        template = airspeed.Template("#if($value)true#{else}false#end")
        self.assertEqual("false", template.merge({}))

    def test_curly_end(self):
        template = airspeed.Template("#if($value)true#{end}monkey")
        self.assertEqual("monkey", template.merge({}))

    def test_too_many_end_clauses_trigger_error(self):
        template = airspeed.Template("#if (1)true!#end #end ")
        self.assertRaises(airspeed.TemplateSyntaxError, template.merge, {})

    def test_can_call_function_with_one_parameter(self):
        def squared(number):
            return number * number

        template = airspeed.Template("$squared(8)")
        self.assertEqual("64", template.merge(locals()))
        some_var = 6
        template = airspeed.Template("$squared($some_var)")
        self.assertEqual("36", template.merge(locals()))
        template = airspeed.Template("$squared($squared($some_var))")
        self.assertEqual("1296", template.merge(locals()))

    def test_can_call_function_with_two_parameters(self):
        def multiply(number1, number2):
            return number1 * number2

        template = airspeed.Template("$multiply(2, 4)")
        self.assertEqual("8", template.merge(locals()))
        template = airspeed.Template("$multiply( 2 , 4 )")
        self.assertEqual("8", template.merge(locals()))
        value1, value2 = 4, 12
        template = airspeed.Template("$multiply($value1,$value2)")
        self.assertEqual("48", template.merge(locals()))

    def test_extract_array_index_from_function_result(self):
        def get_array():
            return ["p1", ["p2", "p3"]]

        template = airspeed.Template("$get_array()[0]")
        self.assertEqual("p1", template.merge(locals()))
        template = airspeed.Template("$get_array()[1][1]")
        self.assertEqual("p3", template.merge(locals()))

    def test_velocity_style_escaping(self):  # example from Velocity docs
        template = airspeed.Template(
            r"""
#set( $email = "foo" )
$email
\$email
\\$email
\
\\ \# \$
\#end
\# end
\#set( $email = "foo" )
"""
        )
        self.assertEqual(
            r"""
foo
$email
\\foo
\
\\ \# \$
#end
\# end
#set( foo = "foo" )
""",
            template.merge({}),
        )

    # def test_velocity_style_escaping_when_var_unset(self): # example from Velocity docs
    #        template = airspeed.Template('''\
    # $email
    # \$email
    # \\$email
    # \\\$email''')
    #        self.assertEquals('''\
    # $email
    # \$email
    # \\$email
    # \\\$email''', template.merge({}))

    def test_true_elseif_evaluated_when_if_is_false(self):
        template = airspeed.Template("#if ($value1) one #elseif ($value2) two #end")
        value1, value2 = False, True
        self.assertEqual(" two ", template.merge(locals()))

    def test_false_elseif_skipped_when_if_is_true(self):
        template = airspeed.Template("#if ($value1) one #elseif ($value2) two #end")
        value1, value2 = True, False
        self.assertEqual(" one ", template.merge(locals()))

    def test_first_true_elseif_evaluated_when_if_is_false(self):
        template = airspeed.Template(
            "#if ($value1) one #elseif ($value2) two #elseif($value3) three #end"
        )
        value1, value2, value3 = False, True, True
        self.assertEqual(" two ", template.merge(locals()))

    def test_illegal_to_have_elseif_after_else(self):
        template = airspeed.Template(
            "#if ($value1) one #else two #elseif($value3) three #end"
        )
        self.assertRaises(airspeed.TemplateSyntaxError, template.merge, {})

    def test_else_evaluated_when_if_and_elseif_are_false(self):
        template = airspeed.Template(
            "#if ($value1) one #elseif ($value2) two #else three #end"
        )
        value1, value2 = False, False
        self.assertEqual(" three ", template.merge(locals()))

    def test_syntax_error_contains_line_and_column_pos(self):
        try:
            airspeed.Template("#if ( $hello )\n\n#elseif blah").merge({})
        except airspeed.TemplateSyntaxError as e:
            self.assertEqual((3, 9), (e.line, e.column))
        else:
            self.fail("expected error")
        try:
            airspeed.Template("#else blah").merge({})
        except airspeed.TemplateSyntaxError as e:
            self.assertEqual((1, 1), (e.line, e.column))
        else:
            self.fail("expected error")

    def test_get_position_strings_in_syntax_error(self):
        try:
            airspeed.Template("#else whatever").merge({})
        except airspeed.TemplateSyntaxError as e:
            self.assertEqual(["#else whatever", "^"], e.get_position_strings())
        else:
            self.fail("expected error")

    def test_get_position_strings_in_syntax_error_when_newline_after_error(self):
        try:
            airspeed.Template("#else whatever\n").merge({})
        except airspeed.TemplateSyntaxError as e:
            self.assertEqual(["#else whatever", "^"], e.get_position_strings())
        else:
            self.fail("expected error")

    def test_get_position_strings_in_syntax_error_when_newline_before_error(self):
        try:
            airspeed.Template("foobar\n  #else whatever\n").merge({})
        except airspeed.TemplateSyntaxError as e:
            self.assertEqual(["  #else whatever", "  ^"], e.get_position_strings())
        else:
            self.fail("expected error")

    def test_compare_greater_than_operator(self):
        for operator in [">", "gt"]:
            template = airspeed.Template("#if ( $value %s 1 )yes#end" % operator)
            self.assertEqual("", template.merge({"value": 0}))
            self.assertEqual("", template.merge({"value": 1}))
            self.assertEqual("yes", template.merge({"value": 2}))

    def test_compare_greater_than_or_equal_operator(self):
        for operator in [">=", "ge"]:
            template = airspeed.Template("#if ( $value %s 1 )yes#end" % operator)
            self.assertEqual("", template.merge({"value": 0}))
            self.assertEqual("yes", template.merge({"value": 1}))
            self.assertEqual("yes", template.merge({"value": 2}))

    def test_compare_less_than_operator(self):
        for operator in ["<", "lt"]:
            template = airspeed.Template("#if ( $value %s 1 )yes#end" % operator)
            self.assertEqual("yes", template.merge({"value": 0}))
            self.assertEqual("", template.merge({"value": 1}))
            self.assertEqual("", template.merge({"value": 2}))

    def test_compare_less_than_or_equal_operator(self):
        for operator in ["<=", "le"]:
            template = airspeed.Template("#if ( $value %s 1 )yes#end" % operator)
            self.assertEqual("yes", template.merge({"value": 0}))
            self.assertEqual("yes", template.merge({"value": 1}))
            self.assertEqual("", template.merge({"value": 2}))

    def test_compare_equality_operator(self):
        for operator in ["==", "eq"]:
            template = airspeed.Template("#if ( $value %s 1 )yes#end" % operator)
            self.assertEqual("", template.merge({"value": 0}))
            self.assertEqual("yes", template.merge({"value": 1}))
            self.assertEqual("", template.merge({"value": 2}))

    def test_or_operator(self):
        template = airspeed.Template("#if ( $value1 || $value2 )yes#end")
        self.assertEqual("", template.merge({"value1": False, "value2": False}))
        self.assertEqual("yes", template.merge({"value1": True, "value2": False}))
        self.assertEqual("yes", template.merge({"value1": False, "value2": True}))

    def test_or_operator_otherform(self):
        template = airspeed.Template("#if ( $value1 or $value2 )yes#end")
        self.assertEqual("", template.merge({"value1": False, "value2": False}))
        self.assertEqual("yes", template.merge({"value1": True, "value2": False}))
        self.assertEqual("yes", template.merge({"value1": False, "value2": True}))

    def test_or_operator_considers_not_None_values_true(self):
        class SomeClass:
            pass

        template = airspeed.Template("#if ( $value1 || $value2 )yes#end")
        self.assertEqual("", template.merge({"value1": None, "value2": None}))
        self.assertEqual(
            "yes", template.merge({"value1": SomeClass(), "value2": False})
        )
        self.assertEqual(
            "yes", template.merge({"value1": False, "value2": SomeClass()})
        )

    def test_and_operator(self):
        template = airspeed.Template("#if ( $value1 && $value2 )yes#end")
        self.assertEqual("", template.merge({"value1": False, "value2": False}))
        self.assertEqual("", template.merge({"value1": True, "value2": False}))
        self.assertEqual("", template.merge({"value1": False, "value2": True}))
        self.assertEqual("yes", template.merge({"value1": True, "value2": True}))

    def test_and_operator_otherform(self):
        template = airspeed.Template("#if ( $value1 and $value2 )yes#end")
        self.assertEqual("", template.merge({"value1": False, "value2": False}))
        self.assertEqual("", template.merge({"value1": True, "value2": False}))
        self.assertEqual("", template.merge({"value1": False, "value2": True}))
        self.assertEqual("yes", template.merge({"value1": True, "value2": True}))

    def test_and_operator_considers_not_None_values_true(self):
        class SomeClass:
            pass

        template = airspeed.Template("#if ( $value1 && $value2 )yes#end")
        self.assertEqual("", template.merge({"value1": None, "value2": None}))
        self.assertEqual("yes", template.merge({"value1": SomeClass(), "value2": True}))
        self.assertEqual("yes", template.merge({"value1": True, "value2": SomeClass()}))

    def test_parenthesised_value(self):
        template = airspeed.Template("#if ( ($value1 == 1) && ($value2 == 2) )yes#end")
        self.assertEqual("", template.merge({"value1": 0, "value2": 1}))
        self.assertEqual("", template.merge({"value1": 1, "value2": 1}))
        self.assertEqual("", template.merge({"value1": 0, "value2": 2}))
        self.assertEqual("yes", template.merge({"value1": 1, "value2": 2}))

    def test_multiterm_expression(self):
        template = airspeed.Template("#if ( $value1 == 1 && $value2 == 2 )yes#end")
        self.assertEqual("", template.merge({"value1": 0, "value2": 1}))
        self.assertEqual("", template.merge({"value1": 1, "value2": 1}))
        self.assertEqual("", template.merge({"value1": 0, "value2": 2}))
        self.assertEqual("yes", template.merge({"value1": 1, "value2": 2}))

    def test_compound_condition(self):
        template = airspeed.Template("#if ( ($value) )yes#end")
        self.assertEqual("", template.merge({"value": False}))
        self.assertEqual("yes", template.merge({"value": True}))

    def test_logical_negation_operator(self):
        template = airspeed.Template("#if ( !$value )yes#end")
        self.assertEqual("yes", template.merge({"value": False}))
        self.assertEqual("", template.merge({"value": True}))

    def test_logical_alt_negation_operator(self):
        template = airspeed.Template("#if ( not $value )yes#end")
        self.assertEqual("yes", template.merge({"value": False}))
        self.assertEqual("", template.merge({"value": True}))

    def test_logical_negation_operator_yields_true_for_None(self):
        template = airspeed.Template("#if ( !$value )yes#end")
        self.assertEqual("yes", template.merge({"value": None}))

    def test_logical_negation_operator_honours_custom_truth_values(self):
        class BooleanValue(object):
            def __init__(self, value):
                self.value = value

            def __bool__(self):
                return self.value

            def __nonzero__(self):
                return self.__bool__()

        template = airspeed.Template("#if ( !$v)yes#end")
        self.assertEqual("yes", template.merge({"v": BooleanValue(False)}))
        self.assertEqual("", template.merge({"v": BooleanValue(True)}))

    def test_compound_binary_and_unary_operators(self):
        template = airspeed.Template("#if ( !$value1 && !$value2 )yes#end")
        self.assertEqual("", template.merge({"value1": False, "value2": True}))
        self.assertEqual("", template.merge({"value1": True, "value2": False}))
        self.assertEqual("", template.merge({"value1": True, "value2": True}))
        self.assertEqual("yes", template.merge({"value1": False, "value2": False}))

    def test_cannot_define_macro_to_override_reserved_statements(self):
        for reserved in (
            "if",
            "else",
            "elseif",
            "set",
            "macro",
            "foreach",
            "parse",
            "include",
            "stop",
            "end",
            "define",
        ):
            template = airspeed.Template("#macro ( %s $value) $value #end" % reserved)
            self.assertRaises(airspeed.TemplateSyntaxError, template.merge, {})

    def test_cannot_call_undefined_macro(self):
        template = airspeed.Template("#undefined()")
        self.assertRaises(airspeed.TemplateExecutionError, template.merge, {})

    def test_define_and_use_macro_with_no_parameters(self):
        template = airspeed.Template("#macro ( hello)hi#end#hello ()#hello()")
        self.assertEqual("hihi", template.merge({"text": "hello"}))

    def test_define_and_use_macro_with_one_parameter(self):
        template = airspeed.Template(
            "#macro ( bold $value)<strong>$value</strong>#end#bold ($text)"
        )
        self.assertEqual("<strong>hello</strong>", template.merge({"text": "hello"}))

    def test_define_and_use_macro_with_two_parameters_no_comma(self):
        template = airspeed.Template(
            "#macro ( bold $value $other)<strong>$value</strong>$other#end#bold ($text $monkey)"
        )
        self.assertEqual(
            "<strong>hello</strong>cheese",
            template.merge({"text": "hello", "monkey": "cheese"}),
        )

    # We use commas with our macros and it seems to work
    # so it's correct behavior by definition; the real
    # question is whether using them without a comma is a legal variant
    # or not.  This should affect the above test; the following test
    # should be legal by definition

    def test_define_and_use_macro_with_two_parameters_with_comma(self):
        template = airspeed.Template(
            "#macro ( bold $value, $other)<strong>$value</strong>$other#end#bold ($text, $monkey)"
        )
        self.assertEqual(
            "<strong>hello</strong>cheese",
            template.merge({"text": "hello", "monkey": "cheese"}),
        )

    def test_use_of_macro_name_is_case_insensitive(self):
        template = airspeed.Template(
            "#macro ( bold $value)<strong>$value</strong>#end#BoLd ($text)"
        )
        self.assertEqual("<strong>hello</strong>", template.merge({"text": "hello"}))

    def test_define_and_use_macro_with_two_parameter(self):
        template = airspeed.Template(
            "#macro (addition $value1 $value2 )$value1+$value2#end#addition (1 2)"
        )
        self.assertEqual("1+2", template.merge({}))
        template = airspeed.Template(
            "#macro (addition $value1 $value2 )$value1+$value2#end#addition( $one   $two )"
        )
        self.assertEqual("ONE+TWO", template.merge({"one": "ONE", "two": "TWO"}))

    def test_cannot_redefine_macro(self):
        template = airspeed.Template("#macro ( hello)hi#end#macro(hello)again#end")
        self.assertRaises(
            airspeed.TemplateExecutionError, template.merge, {}
        )  # Should this be TemplateSyntaxError?

    def test_can_call_macro_with_newline_between_args(self):
        template = airspeed.Template(
            "#macro (hello $value1 $value2 )hello $value1 and $value2#end\n#hello (1,\n 2)"
        )
        self.assertEqual("hello 1 and 2", template.merge({}))

    def test_use_define_with_no_parameters(self):
        template = airspeed.Template("#define ( $hello)hi#end$hello()$hello()")
        self.assertEqual("hihi", template.merge({}))

    def test_use_define_with_parameters(self):
        template = airspeed.Template(
            '#define ( $echo $v1 $v2)$v1$v2#end$echo(1,"a")$echo("b",2)'
        )
        self.assertEqual("1ab2", template.merge({"text": "hello"}))
        template = airspeed.Template(
            '#define ( $echo $v1 $v2)$v1$v2#end$echo(1,"a")$echo($echo(2,"b"),"c")'
        )
        self.assertEqual("1a2bc", template.merge({}))
        template = airspeed.Template(
            '#define ( $echo $v1 $v2)$v1$v2#end$echo(1,"a")$echo("b",$echo(3,"c"))'
        )
        self.assertEqual("1ab3c", template.merge({}))

    def test_define_with_local_namespace(self):
        template = airspeed.Template(
            "#define ( $showindex )$foreach.index#end#foreach($x in [1,2,3])$showindex#end"
        )
        self.assertEqual("012", template.merge({}))

    def test_use_defined_func_multiple_times(self):
        template = airspeed.Template(
            """
            #define( $myfunc )$ctx#end
            #set( $ctx = 'foo' )
            $myfunc
            #set( $ctx = 'bar' )
            $myfunc
        """
        )
        result = template.merge({}).replace("\n", "").replace(" ", "")
        self.assertEqual("foobar", result)

    def test_use_defined_func_create_json_loop(self):
        template = airspeed.Template(
            """
        #define( $loop ) {
            #foreach($e in $map.keySet())
                #set( $k = $e )
                #set( $v = $map.get($k))
                "$k": "$v"
                #if( $foreach.hasNext ) , #end
            #end
        }
        #end
        $loop
        #set( $map = {'foo':'bar'} )
        $loop
        """
        )
        context = {"map": {"test": 123, "test2": "abc"}}
        result = re.sub(r"\s", "", template.merge(context), flags=re.MULTILINE)
        self.assertEqual('{"test":"123","test2":"abc"}{"foo":"bar"}', result)

    def test_include_directive_gives_error_if_no_loader_provided(self):
        template = airspeed.Template('#include ("foo.tmpl")')
        self.assertRaises(airspeed.TemplateError, template.merge, {})

    def test_include_directive_yields_loader_error_if_included_content_not_found(self):
        class BrokenLoader:
            def load_text(self, name):
                raise IOError(name)

        template = airspeed.Template('#include ("foo.tmpl")')
        self.assertRaisesExecutionError(
            IOError, template.merge, {}, loader=BrokenLoader()
        )

    def test_valid_include_directive_include_content(self):
        class WorkingLoader:
            def load_text(self, name):
                if name == "foo.tmpl":
                    return "howdy"

        template = airspeed.Template('Message is: #include ("foo.tmpl")!')
        self.assertEqual(
            "Message is: howdy!", template.merge({}, loader=WorkingLoader())
        )

    def test_parse_directive_gives_error_if_no_loader_provided(self):
        template = airspeed.Template('#parse ("foo.tmpl")')
        self.assertRaises(airspeed.TemplateExecutionError, template.merge, {})

    def test_parse_directive_yields_loader_error_if_parsed_content_not_found(self):
        class BrokenLoader:
            def load_template(self, name):
                raise IOError(name)

        template = airspeed.Template('#parse ("foo.tmpl")')
        self.assertRaisesExecutionError(
            IOError, template.merge, {}, loader=BrokenLoader()
        )

    def test_valid_parse_directive_outputs_parsed_content(self):
        class WorkingLoader:
            def load_template(self, name):
                if name == "foo.tmpl":
                    return airspeed.Template("$message", name)

        template = airspeed.Template('Message is: #parse ("foo.tmpl")!')
        self.assertEqual(
            "Message is: hola!",
            template.merge({"message": "hola"}, loader=WorkingLoader()),
        )
        template = airspeed.Template("Message is: #parse ($foo)!")
        self.assertEqual(
            "Message is: hola!",
            template.merge(
                {"foo": "foo.tmpl", "message": "hola"}, loader=WorkingLoader()
            ),
        )

    def test_valid_parse_directive_merge_namespace(self):
        class WorkingLoader:
            def load_template(self, name):
                if name == "foo.tmpl":
                    return airspeed.Template("#set($message = 'hola')")

        template = airspeed.Template('#parse("foo.tmpl")Message is: $message!')
        self.assertEqual(
            "Message is: hola!", template.merge({}, loader=WorkingLoader())
        )

    def test_assign_range_literal(self):
        template = airspeed.Template(
            "#set($values = [1..5])#foreach($value in $values)$value,#end"
        )
        self.assertEqual("1,2,3,4,5,", template.merge({}))
        template = airspeed.Template(
            "#set($values = [2..-2])#foreach($value in $values)$value,#end"
        )
        self.assertEqual("2,1,0,-1,-2,", template.merge({}))

    def test_local_namespace_methods_are_not_available_in_context(self):
        template = airspeed.Template("#macro(tryme)$values#end#tryme()")
        self.assertEqual("$values", template.merge({}))

    def test_array_literal(self):
        template = airspeed.Template(
            'blah\n#set($valuesInList = ["Hello ", $person, ", your lucky number is ", 7])\n#foreach($value in $valuesInList)$value#end\n\nblah'
        )
        self.assertEqual(
            "blah\nHello Chris, your lucky number is 7\nblah",
            template.merge({"person": "Chris"}),
        )
        # NOTE: the original version of this test incorrectly preserved
        # the newline at the end of the #end line

    def test_dictionary_literal(self):
        template = airspeed.Template('#set($a = {"dog": "cat" , "horse":15})$a.dog')
        self.assertEqual("cat", template.merge({}))
        template = airspeed.Template('#set($a = {"dog": "$horse"})$a.dog')
        self.assertEqual("cow", template.merge({"horse": "cow"}))

    def test_dictionary_literal_as_parameter(self):
        template = airspeed.Template('$a({"color":"blue"})')
        ns = {"a": lambda x: x["color"] + " food"}
        self.assertEqual("blue food", template.merge(ns))

    def test_nested_array_literals(self):
        template = airspeed.Template(
            '#set($values = [["Hello ", "Steve"], ["Hello", " Chris"]])#foreach($pair in $values)#foreach($word in $pair)$word#end. #end'
        )
        self.assertEqual("Hello Steve. Hello Chris. ", template.merge({}))

    def test_when_dictionary_does_not_contain_referenced_attribute_no_substitution_occurs(
        self,
    ):
        template = airspeed.Template(" $user.name ")
        self.assertEqual(" $user.name ", template.merge({"user": self}))

    def test_when_dictionary_has_same_key_as_built_in_method(self):
        template = airspeed.Template(" $user.items ")
        self.assertEqual(" 1;2;3 ", template.merge({"user": {"items": "1;2;3"}}))

    def test_when_non_dictionary_object_does_not_contain_referenced_attribute_no_substitution_occurs(
        self,
    ):
        class MyObject:
            pass

        template = airspeed.Template(" $user.name ")
        self.assertEqual(" $user.name ", template.merge({"user": MyObject()}))

    def test_variables_expanded_in_double_quoted_strings(self):
        template = airspeed.Template('#set($hello="hello, $name is my name")$hello')
        self.assertEqual("hello, Steve is my name", template.merge({"name": "Steve"}))

    def test_escaped_variable_references_not_expanded_in_double_quoted_strings(self):
        template = airspeed.Template('#set($hello="hello, \\$name is my name")$hello')
        self.assertEqual("hello, $name is my name", template.merge({"name": "Steve"}))

    def test_macros_expanded_in_double_quoted_strings(self):
        template = airspeed.Template(
            '#macro(hi $person)$person says hello#end#set($hello="#hi($name)")$hello'
        )
        self.assertEqual("Steve says hello", template.merge({"name": "Steve"}))

    def test_color_spec(self):
        template = airspeed.Template('<span style="color: #13ff93">')
        self.assertEqual('<span style="color: #13ff93">', template.merge({}))

    # check for a plain hash outside of a context where it could be
    # confused with a directive or macro call.
    # this is useful for cases where someone put a hash in the target
    # of a link, which is typical when javascript is associated with the link

    def test_standalone_hashes(self):
        template = airspeed.Template("#")
        self.assertEqual("#", template.merge({}))
        template = airspeed.Template('"#"')
        self.assertEqual('"#"', template.merge({}))
        template = airspeed.Template('<a href="#">bob</a>')
        self.assertEqual('<a href="#">bob</a>', template.merge({}))

    def test_large_areas_of_text_handled_without_error(self):
        text = "qwerty uiop asdfgh jkl zxcvbnm. 1234" * 300
        template = airspeed.Template(text)
        self.assertEqual(text, template.merge({}))

    def test_foreach_with_unset_variable_expands_to_nothing(self):
        template = airspeed.Template("#foreach($value in $values)foo#end")
        self.assertEqual("", template.merge({}))

    def test_foreach_with_non_iterable_variable_raises_error(self):
        template = airspeed.Template("#foreach($value in $values)foo#end")
        self.assertRaises(
            airspeed.TemplateExecutionError, template.merge, {"values": 1}
        )

    def test_correct_scope_for_parameters_of_method_calls(self):
        template = airspeed.Template("$obj.get_self().method($param)")

        class C:
            def get_self(self):
                return self

            def method(self, p):
                if p == "bat":
                    return "monkey"

        value = template.merge({"obj": C(), "param": "bat"})
        self.assertEqual("monkey", value)

    def test_preserves_unicode_strings(self):
        template = airspeed.Template("$value")
        value = "Grüße"
        self.assertEqual(value, template.merge(locals()))

    def test_preserves_unicode_strings_objects(self):
        template = airspeed.Template("$value")

        class Clazz:
            def __init__(self, value):
                self.value = value

            def __str__(self):
                return self.value

        value = Clazz("£12,000")
        self.assertEqual(six.text_type(value), template.merge(locals()))

    def test_can_define_macros_in_parsed_files(self):
        class Loader:
            def load_template(self, name):
                if name == "foo.tmpl":
                    return airspeed.Template("#macro(themacro)works#end")

        template = airspeed.Template('#parse("foo.tmpl")#themacro()')
        self.assertEqual("works", template.merge({}, loader=Loader()))

    def test_modulus_operator(self):
        template = airspeed.Template("#set( $modulus = ($value % 2) )$modulus")
        self.assertEqual("1", template.merge({"value": 3}))

    def test_can_assign_empty_string(self):
        template = airspeed.Template("#set( $v = \"\" )#set( $y = '' ).$v.$y.")
        self.assertEqual("...", template.merge({}))

    def test_can_loop_over_numeric_ranges(self):
        # Test for bug #15
        template = airspeed.Template("#foreach( $v in [1..5] )$v\n#end")
        self.assertEqual("1\n2\n3\n4\n5\n", template.merge({}))

    def test_can_loop_over_numeric_ranges_backwards(self):
        template = airspeed.Template("#foreach( $v in [5..-2] )$v,#end")
        self.assertEqual("5,4,3,2,1,0,-1,-2,", template.merge({}))

    def test_ranges_over_references(self):
        template = airspeed.Template(
            "#set($start = 1)#set($end = 5)#foreach($i in [$start .. $end])$i-#end"
        )
        self.assertEqual("1-2-3-4-5-", template.merge({}))

    def test_user_defined_directive(self):
        class DummyDirective(airspeed._Element):
            PLAIN = re.compile(r"#(monkey)man(.*)$", re.S + re.I)

            def parse(self):
                (self.text,) = self.identity_match(self.PLAIN)

            def evaluate(self, stream, namespace, loader):
                stream.write(self.text)

        airspeed.UserDefinedDirective.DIRECTIVES.append(DummyDirective)
        template = airspeed.Template("hello #monkeyman")
        self.assertEqual("hello monkey", template.merge({}))
        airspeed.UserDefinedDirective.DIRECTIVES.remove(DummyDirective)

    def test_stop_directive(self):
        template = airspeed.Template("hello #stop world")
        self.assertEqual("hello ", template.merge({}))

    def test_assignment_of_parenthesized_math_expression(self):
        template = airspeed.Template("#set($a = (5 + 4))$a")
        self.assertEqual("9", template.merge({}))

    def test_assignment_of_parenthesized_math_expression_with_reference(self):
        template = airspeed.Template("#set($b = 5)#set($a = ($b + 4))$a")
        self.assertEqual("9", template.merge({}))

    def test_recursive_macro(self):
        template = airspeed.Template(
            "#macro ( recur $number)#if ($number > 0)#set($number = $number - 1)#recur($number)X#end#end#recur(5)"
        )
        self.assertEqual("XXXXX", template.merge({}))

    def test_addition_has_higher_precedence_than_comparison(self):
        template = airspeed.Template("#set($a = 4 > 2 + 5)$a")
        self.assertEqual("False", template.merge({}))

    def test_parentheses_work(self):
        template = airspeed.Template("#set($a = (5 + 4) > 2)$a")
        self.assertEqual("True", template.merge({}))

    def test_addition_has_higher_precedence_than_comparison_other_direction(self):
        template = airspeed.Template("#set($a = 5 + 4 > 2)$a")
        self.assertEqual("True", template.merge({}))

    # Note: this template:
    # template = airspeed.Template('#set($a = (4 > 2) + 5)$a')
    # prints 6.  That's because Python automatically promotes True to 1
    # and False to 0.
    # This is weird, but I can't say it's wrong.

    def test_multiplication_has_higher_precedence_than_subtraction(self):
        template = airspeed.Template("#set($a = 5 * 4 - 2)$a")
        self.assertEqual("18", template.merge({}))

    def test_multiplication_has_higher_precedence_than_addition_reverse(self):
        template = airspeed.Template("#set($a = 2 + 5 * 4)$a")
        self.assertEqual("22", template.merge({}))

    def test_parse_empty_dictionary(self):
        template = airspeed.Template("#set($a = {})$a")
        self.assertEqual("{}", template.merge({}))

    def test_macro_whitespace_and_newlines_ignored(self):
        template = airspeed.Template(
            """#macro ( blah )
hello##
#end
#blah()"""
        )
        self.assertEqual("hello", template.merge({}))

    def test_if_whitespace_and_newlines_ignored(self):
        template = airspeed.Template(
            """#if(true)
hello##
#end"""
        )
        self.assertEqual("hello", template.merge({}))

    def test_subobject_assignment(self):
        template = airspeed.Template("#set($outer.inner = 'monkey')")
        x = {"outer": {}}
        template.merge(x)
        self.assertEqual("monkey", x["outer"]["inner"])

    def test_expressions_with_numbers_with_fractions(self):
        template = airspeed.Template("#set($a = 100.0 / 50)$a")
        self.assertEqual("2.0", template.merge({}))
        # TODO: is that how Velocity would format a floating point?

    def test_multiline_arguments_to_function_calls(self):
        class Thing:
            def func(self, arg):
                return "y"

        template = airspeed.Template(
            """$x.func("multi
line")"""
        )
        self.assertEqual("y", template.merge({"x": Thing()}))

    def test_does_not_accept_dollar_digit_identifiers(self):
        template = airspeed.Template("$Something$0")
        self.assertEqual("$Something$0", template.merge({"0": "bar"}))

    def test_valid_vtl_identifiers(self):
        template = airspeed.Template("$_x $a $A")
        self.assertEqual("bar z Z", template.merge({"_x": "bar", "a": "z", "A": "Z"}))

    def test_invalid_vtl_identifier(self):
        template = airspeed.Template("$0")
        self.assertEqual("$0", template.merge({"0": "bar"}))

    def test_array_notation_int_index(self):
        template = airspeed.Template("$a[1]")
        self.assertEqual("bar", template.merge({"a": ["foo", "bar"]}))

    def test_array_notation_nested_indexes(self):
        template = airspeed.Template("$a[1][1]")
        self.assertEqual("bar2", template.merge({"a": ["foo", ["bar1", "bar2"]]}))

    def test_array_notation_dot(self):
        template = airspeed.Template("$a[1].bar1")
        self.assertEqual("bar2", template.merge({"a": ["foo", {"bar1": "bar2"}]}))

    def test_array_notation_dict_index(self):
        template = airspeed.Template('$a["foo"]')
        self.assertEqual("bar", template.merge({"a": {"foo": "bar"}}))

    def test_array_notation_empty_array_variable(self):
        template = airspeed.Template("$!a[1]")
        self.assertEqual("", template.merge({"a": []}))

    def test_array_notation_variable_index(self):
        template = airspeed.Template("#set($i = 1)$a[ $i ]")
        self.assertEqual("bar", template.merge({"a": ["foo", "bar"]}))

    def test_array_notation_invalid_index(self):
        template = airspeed.Template('#set($i = "baz")$a[$i]')
        self.assertRaises(
            airspeed.TemplateExecutionError, template.merge, {"a": ["foo", "bar"]}
        )

    def test_provides_helpful_error_location(self):
        template = airspeed.Template(
            """
          #set($flag = $country.lower())
          #set($url = "$host_url/images/flags/")
          #set($flagUrl = $url + ${flag} + ".png")
           <img src="${flagUrl}" />
        """,
            filename="mytemplate",
        )
        data = {"model": {"host_url": "http://whatever.com", "country": None}}
        try:
            template.merge(data)
            self.fail("expected exception")
        except airspeed.TemplateExecutionError as e:
            self.assertEqual("mytemplate", e.filename)
            self.assertEqual(105, e.start)
            self.assertEqual(142, e.end)
            self.assertTrue(isinstance(e.__cause__, TypeError))

    def test_outer_variable_assignable_from_foreach_block(self):
        template = airspeed.Template(
            "#set($var = 1)#foreach ($i in $items)" "$var,#set($var = $i)" "#end$var"
        )
        self.assertEqual("1,2,3,4", template.merge({"items": [2, 3, 4]}))

    def test_no_assignment_to_outer_var_if_same_varname_in_block(self):
        template = airspeed.Template(
            "#set($i = 1)$i," "#foreach ($i in [2, 3, 4])$i,#set($i = $i)#end" "$i"
        )
        self.assertEqual("1,2,3,4,1", template.merge({}))

    def test_nested_foreach_vars_are_scoped(self):
        template = airspeed.Template(
            "#foreach ($j in [1,2])"
            "#foreach ($i in [3, 4])$foreach.count,#end"
            "$foreach.count|#end"
        )
        self.assertEqual("1,2,1|1,2,2|", template.merge({}))

    def test_template_cannot_modify_its_args(self):
        template = airspeed.Template("#set($foo = 1)")
        ns = {"foo": 2}
        template.merge(ns)
        self.assertEqual(2, ns["foo"])

    def test_doesnt_blow_stack(self):
        template = airspeed.Template(
            """
#foreach($i in [1..$end])
    $assembly##
#end
"""
        )
        ns = {"end": 400}
        template.merge(ns)

    def test_array_size(self):
        template = airspeed.Template("#set($foo = [1,2,3]) $foo.size()")
        output = template.merge({})
        self.assertEqual(output, " 3")

    def test_array_contains_true(self):
        template = airspeed.Template(
            "#set($foo = [1,2,3]) #if($foo.contains(1))found#end"
        )
        output = template.merge({})
        self.assertEqual(output, " found")

    def test_array_contains_false(self):
        template = airspeed.Template(
            "#set($foo = [1,2,3]) #if($foo.contains(10))found#end"
        )
        output = template.merge({})
        self.assertEqual(output, " ")

    def test_array_get_item(self):
        template = airspeed.Template("#set($foo = [1,2,3]) $foo.get(1)")
        output = template.merge({})
        self.assertEqual(output, " 2")

    def test_array_add_item(self):
        template = airspeed.Template(
            "#set($foo = [1,2,3])"
            "#set( $ignore = $foo.add('string value') )"
            "#foreach($item in $foo)$item,#end"
        )
        output = template.merge({})
        self.assertEqual(output, "1,2,3,string value,")

    def test_string_length(self):
        template = airspeed.Template("#set($foo = 'foobar123') $foo.length()")
        output = template.merge({})
        self.assertEqual(output, " 9")

    def test_string_replace_all(self):
        template = airspeed.Template(
            "#set($foo = 'foobar123bab') $foo.replaceAll('ba.', 'foo')"
        )
        output = template.merge({})
        self.assertEqual(output, " foofoo123foo")

    def test_string_starts_with_true(self):
        template = airspeed.Template(
            "#set($foo = 'foobar123') #if($foo.startsWith('foo'))yes!#end"
        )
        output = template.merge({})
        self.assertEqual(output, " yes!")

    def test_string_starts_with_false(self):
        template = airspeed.Template(
            "#set($foo = 'nofoobar123') #if($foo.startsWith('foo'))yes!#end"
        )
        output = template.merge({})
        self.assertEqual(output, " ")

    def test_dict_put_item(self):
        template = airspeed.Template(
            "#set( $ignore = $test_dict.put('k', 'new value') )"
            "$ignore - $test_dict.k"
        )
        output = template.merge({"test_dict": {"k": "initial value"}})
        self.assertEqual(output, "initial value - new value")

    def test_dict_putall_items(self):
        template = airspeed.Template(
            "#set( $ignore = $test_dict.putAll({'k1': 'v3', 'k2': 'v2'}))"
            "$test_dict.k1 - $test_dict.k2"
        )
        output = template.merge({"test_dict": {"k1": "v1"}})
        self.assertEqual(output, "v3 - v2")

    def test_evaluate(self):
        template = airspeed.Template(
            """#set($source1 = "abc")
#set($select = "1")
#set($dynamicsource = "$source$select")
## $dynamicsource is now the string '$source1'
#evaluate($dynamicsource)"""
        )
        output = template.merge({})
        self.assertEqual(output, "abc")

    def test_return_macro(self):
        template = "#set($v1 = {})#set($ignore = $v1.put('foo', 'bar'))#return($v1)"
        template = airspeed.Template(template)
        output = template.merge({})
        self.assertEqual(output, '{"foo": "bar"}')


# TODO:
#
#  Report locations for template errors in files included via loaders
#  Gobbling up whitespace (see WHITESPACE_TO_END_OF_LINE above, but need to apply in more places)
# Bind #macro calls at compile time?
# Scope of #set across if/elseif/else?
# there seems to be some confusion about the semantics of parameter
# passing to macros; an assignment in a macro body should persist past the
# macro call.  Confirm against Velocity.

if __name__ == "__main__":
    if sys.version_info >= (3, 0) and sys.version_info <= (3, 3):
        imp.reload(airspeed)
    elif sys.version_info >= (3, 4):
        importlib.reload(airspeed)
    import unittest

    try:
        unittest.main()
    except SystemExit:
        pass
