import os.path
import re
import tempfile
import textwrap

import pytest
import requests
import six
from localstack.constants import TEST_AWS_ACCOUNT_ID
from localstack.testing.aws.util import is_aws_cloud
from localstack.testing.pytest import fixtures
from localstack.utils.archives import unzip
from localstack.utils.files import save_file
from localstack.utils.http import download
from localstack.utils.run import run
from localstack.utils.strings import short_uid, to_str
from localstack.utils.sync import retry

import airspeed

# URL to download velocity CLI (using the official Velocity Java implementation)
VELOCITY_CLI_URL = "https://repo1.maven.org/maven2/com/github/heuermh/velocity/velocity-cli/2.1.4/velocity-cli-2.1.4-bin.zip"


@pytest.fixture(scope="session")
def account_id(aws_client):
    if not is_aws_cloud():
        return TEST_AWS_ACCOUNT_ID
    return aws_client.sts.get_caller_identity()["Account"]


# patch required to enable importing of `snapshot` fixture, without having LS running locally
fixtures.account_id = account_id


@pytest.fixture
def test_render_on_aws(aws_client, create_rest_apigw, snapshot):
    def _run_test(template, context=None, snapshot_key=None):
        context = context or {}
        snapshot_key = snapshot_key or "render-result"

        # construct response template with VTL template and input variables
        variable_defs = " ".join(f"#set(${var} = $bodyJSON.{var})" for var in context)
        response_template = textwrap.dedent(
            """
        #set($body = $context.requestOverride.path.body)
        #set($bodyJSON = $util.parseJson($body)) %s
        %s"""
        ).lstrip("\n")
        response_template = response_template % (variable_defs, template)

        # create API Gateway API, method, integration response
        api_id, api_name, root_resource = create_rest_apigw(
            name=f"test-gw-{short_uid()}"
        )
        aws_client.apigateway.put_method(
            restApiId=api_id,
            resourceId=root_resource,
            httpMethod="POST",
            authorizationType="NONE",
        )
        aws_client.apigateway.put_method_response(
            restApiId=api_id,
            resourceId=root_resource,
            httpMethod="POST",
            statusCode="200",
        )
        aws_client.apigateway.put_integration(
            restApiId=api_id,
            resourceId=root_resource,
            httpMethod="POST",
            integrationHttpMethod="POST",
            type="MOCK",
            requestTemplates={
                "application/json": """
            #set($context.requestOverride.path.body = $input.body)
            {
              "statusCode": 200,
            }
            """
            },
        )
        aws_client.apigateway.put_integration_response(
            restApiId=api_id,
            resourceId=root_resource,
            httpMethod="POST",
            statusCode="200",
            responseTemplates={"application/json": response_template},
        )
        deploymeny_id = aws_client.apigateway.create_deployment(restApiId=api_id)["id"]
        aws_client.apigateway.create_stage(
            restApiId=api_id, stageName="test", deploymentId=deploymeny_id
        )

        def get_response():
            response = requests.post(url, json=context)
            content = to_str(response.content)
            assert response.ok
            return content

        url = f"https://{api_id}.execute-api.{aws_client.apigateway.meta.region_name}.amazonaws.com/test"
        content = retry(get_response, retries=20, sleep=1)
        snapshot.match(snapshot_key, content)

    return _run_test


@pytest.fixture
def test_render(test_render_on_aws, test_render_locally, snapshot):
    snapshot_count = 1

    def _run_test(template, context=None):
        nonlocal snapshot_count
        snapshot_key = f"render-result-{snapshot_count}"
        snapshot_count += 1

        # snapshot result of official VTL Java library (there may be discrepancies with AWS)
        cli_result = run_velocity_cli(template, context=context)
        snapshot.match(f"{snapshot_key}-cli", cli_result)

        if is_aws_cloud():
            test_render_on_aws(template, context=context, snapshot_key=snapshot_key)
            return

        result = test_render_locally(template, context=context)
        snapshot.match(snapshot_key, result)

    return _run_test


@pytest.fixture
def test_render_locally(test_render_on_aws, snapshot):
    def _render(template: str, context: dict = None, expected=None):
        context = {} if context is None else context
        template = airspeed.Template(template)
        result = template.merge(context)
        if expected is not None:
            assert result == expected
        return result

    return _render


def run_velocity_cli(template: str, context: dict) -> str:
    # install CLI
    target_dir = os.path.join(tempfile.gettempdir(), "velocity-cli-2.1.4")
    bin_path = os.path.join(target_dir, "bin", "velocity")
    if not os.path.exists(bin_path):
        cli_file = os.path.join(tempfile.gettempdir(), "vlt-cli.tmp.zip")
        download(VELOCITY_CLI_URL, cli_file)
        unzip(cli_file, tempfile.gettempdir())

    # run template rendering via CLI
    context = context or {}
    template_file = os.path.join(target_dir, "template.tmp")
    save_file(template_file, template)
    context_str = ",".join(f"{key}={value}" for key, value in context.items())
    cmd = [bin_path, "-t", "template.tmp"]
    if context_str:
        cmd += ["-c", context_str]
    result = run(cmd, cwd=target_dir)
    return result


class TestTemplating:
    def test_parser_returns_input_when_there_is_nothing_to_substitute(
        self, test_render
    ):
        test_render("<html></html>")

    def test_parser_substitutes_string_added_to_the_context(self, test_render):
        test_render("Hello $name", context={"name": "Chris"})

    def test_dollar_left_untouched(self, test_render):
        test_render("Hello $ ")
        # TODO: raises 500 on AWS
        # test_render("Hello $")

    @pytest.mark.xfail(reason="Discrepancy with AWS")
    def test_unmatched_name_does_not_get_substituted(self, test_render):
        test_render("Hello $name")

    def test_silent_substitution_for_unmatched_values(self, test_render):
        test_render("Hello $!name", context={"name": "world"})
        test_render("Hello $!name")

    @pytest.mark.xfail(reason="Discrepancy with AWS for case #2")
    def test_formal_reference_in_an_if_condition(self, test_render):
        # reference in an if statement used to be a problem
        test_render("#if(${a.b.c})yes!#end", context={"a": {"b": {"c": "d"}}})
        test_render("#if(${a.b.c})yes!#end", context={})

    @pytest.mark.xfail(reason="Discrepancy with AWS for cases #2 and #4")
    def test_silent_formal_reference_in_an_if_condition(self, test_render):
        # the silent modifier shouldn't make a difference here
        test_render("#if($!{a.b.c})yes!#end", context={"a": {"b": {"c": "d"}}})
        test_render("#if($!{a.b.c})yes!#end")
        # with or without curly braces
        test_render("#if($!a.b.c)yes!#end", context={"a": {"b": {"c": "d"}}})
        test_render("#if($!a.b.c)yes!#end")

    def test_embed_substitution_value_in_braces_gets_handled(self, test_render):
        test_render("Hello ${name}.", context={"name": "World"})

    def test_unmatched_trailing_brace_preserved(self, test_render):
        test_render("Hello $name}.", context={"name": "World"})

    @pytest.mark.xfail(reason="Raises an error on AWS")
    def test_formal_reference_with_alternate_literal_value(self, test_render):
        # TODO: raises an error on AWS
        test_render("${a|'hello'}", context={"a": "foo"})
        test_render("${a|'hello'}")

    @pytest.mark.xfail(reason="Raises an error on AWS")
    def test_formal_reference_with_alternate_expression_value(self, test_render):
        test_render("${a|$b}", context={"b": "hello"})

    def test_when_if_statement_resolves_to_true_the_content_is_returned(
        self, test_render
    ):
        test_render(
            "Hello #if ($name)your name is ${name}#end Good to see you",
            context={"name": "Steve"},
        )

    def test_when_if_statement_resolves_to_false_the_content_is_skipped(
        self, test_render
    ):
        test_render(
            "Hello #if ($show_greeting)your name is ${name}#end Good to see you",
            context={"name": "Steve", "show_greeting": False},
        )

    @pytest.mark.xfail(reason="Discrepancy with AWS for test case #2")
    def test_when_if_statement_is_nested_inside_a_successful_enclosing_if_it_gets_evaluated(
        self, test_render
    ):
        template = "Hello #if ($show_greeting)your name is ${name}.#if ($is_birthday) Happy Birthday.#end#end Good to see you"
        test_render(
            template,
            context={"name": "Steve", "show_greeting": False},
        )
        test_render(
            template,
            context={"name": "Steve", "show_greeting": True},
        )
        test_render(
            template,
            context={"name": "Steve", "show_greeting": True, "is_birthday": True},
        )

    @pytest.mark.xfail(reason="Discrepancy with AWS")
    def test_if_statement_considers_None_to_be_false(self, test_render):
        test_render("#if ($some_value)hide me#end", "")
        test_render(
            "#if ($some_value)hide me#end",
            context={"some_value": None},
        )

    @pytest.mark.xfail(reason="Discrepancy with AWS - True instead of true")
    def test_understands_boolean_literal_true(self, test_render):
        test_render("#set ($v = true)$v")

    @pytest.mark.xfail(reason="Discrepancy with AWS - False instead of false")
    def test_understands_boolean_literal_false(self, test_render):
        test_render("#set ($v = false)$v")

    @pytest.mark.xfail(reason="Invalid syntax - VTL CLI fails parsing due to '#endOff'")
    def test_new_lines_in_templates_are_permitted_invalid(self, test_render):
        test_render(
            "hello #if ($show_greeting)${name}.\n#if($is_birthday)Happy Birthday\n#end.\n#endOff out later?",
            context={"name": "Steve", "show_greeting": True, "is_birthday": True},
        )

    def test_new_lines_in_templates_are_permitted(self, test_render):
        test_render(
            "hello #if ($show_greeting)${name}.\n#if($is_birthday)Happy Birthday\n#end.\n#end Off out later?",
            context={"name": "Steve", "show_greeting": True, "is_birthday": True},
        )

    @pytest.mark.xfail(
        reason="TODO - VTL CLI fails to parse list values as context argument"
    )
    def test_foreach_with_plain_content_loops_correctly(self, test_render):
        test_render(
            "#foreach ($name in $names)Hello you. #end",
            context={"names": ["Chris", "Steve"]},
        )

    @pytest.mark.xfail(
        reason="TODO - VTL CLI fails to parse list values as context argument"
    )
    def test_foreach_skipped_when_nested_in_a_failing_if(self, test_render):
        test_render(
            "#if ($false_value)#foreach ($name in $names)Hello you. #end#end",
            context={"false_value": False, "names": ["Chris", "Steve"]},
        )

    @pytest.mark.xfail(
        reason="TODO - VTL CLI fails to parse list values as context argument"
    )
    def test_foreach_with_expression_content_loops_correctly(self, test_render):
        test_render(
            "#foreach ($name in $names)Hello $you. #end",
            context={"you": "You", "names": ["Chris", "Steve"]},
        )

    @pytest.mark.xfail(
        reason="TODO - VTL CLI fails to parse list values as context argument"
    )
    def test_foreach_makes_loop_variable_accessible(self, test_render):
        test_render(
            "#foreach ($name in $names)Hello $name. #end",
            context={"you": "You", "names": ["Chris", "Steve"]},
        )

    @pytest.mark.xfail(
        reason="TODO - VTL CLI fails to parse list values as context argument"
    )
    def test_loop_variable_not_accessible_after_loop(self, test_render):
        test_render(
            "#foreach ($name in $names)Hello $name. #end$name",
            context={"you": "You", "names": ["Chris", "Steve"]},
        )

    @pytest.mark.xfail(
        reason="TODO - VTL CLI fails to parse list values as context argument"
    )
    def test_loop_variables_do_not_clash_in_nested_loops(self, test_render):
        test_render(
            "#foreach ($word in $greetings)$word to#foreach ($word in $names) $word#end. #end",
            context={"greetings": ["Hello", "Goodbye"], "names": ["Chris", "Steve"]},
        )

    @pytest.mark.xfail(
        reason="TODO - VTL CLI fails to parse list values as context argument"
    )
    def test_loop_counter_variable_available_in_loops(self, test_render):
        test_render(
            "#foreach ($word in $greetings)$velocityCount,#end",
            context={"greetings": ["Hello", "Goodbye"]},
        )

    @pytest.mark.xfail(
        reason="TODO - VTL CLI fails to parse list values as context argument"
    )
    def test_loop_counter_variable_available_in_loops_new(self, test_render):
        test_render(
            "#foreach ($word in $greetings)$foreach.count,#end",
            context={"greetings": ["Hello", "Goodbye"]},
        )

    @pytest.mark.xfail(
        reason="TODO - VTL CLI fails to parse list values as context argument"
    )
    def test_loop_index_variable_available_in_loops_new(self, test_render):
        test_render(
            "#foreach ($word in $greetings)$foreach.index,#end",
            context={"greetings": ["Hello", "Goodbye"]},
        )

    @pytest.mark.xfail(
        reason="TODO - VTL CLI fails to parse list values as context argument"
    )
    def test_loop_counter_variables_do_not_clash_in_nested_loops(self, test_render):
        test_render(
            "#foreach ($word in $greetings)Outer $velocityCount#foreach ($word in $names), inner $velocityCount#end. #end",
            context={"greetings": ["Hello", "Goodbye"], "names": ["Chris", "Steve"]},
        )

    @pytest.mark.xfail(
        reason="TODO - VTL CLI fails to parse list values as context argument"
    )
    def test_loop_counter_variables_do_not_clash_in_nested_loops_new(self, test_render):
        test_render(
            "#foreach ($word in $greetings)Outer $foreach.count#foreach ($word in $names), inner $foreach.count#end. #end",
            context={"greetings": ["Hello", "Goodbye"], "names": ["Chris", "Steve"]},
        )

    @pytest.mark.xfail(
        reason="TODO - VTL CLI fails to parse list values as context argument"
    )
    def test_loop_index_variables_do_not_clash_in_nested_loops_new(self, test_render):
        test_render(
            "#foreach ($word in $greetings)Outer $foreach.index#foreach ($word in $names), inner $foreach.index#end. #end",
            context={"greetings": ["Hello", "Goodbye"], "names": ["Chris", "Steve"]},
        )

    def test_has_next(self, test_render):
        test_render(
            "#foreach ($i in [1, 2, 3])$i. #if ($velocityHasNext)yes#end, #end",
        )

    def test_has_next_new(self, test_render):
        test_render(
            "#foreach ($i in [1, 2, 3])$i. #if ($foreach.hasNext)yes#end, #end",
        )

    def test_first(self, test_render):
        test_render(
            "#foreach ($i in [1, 2, 3])$i. #if ($foreach.first)yes#end, #end",
        )

    def test_last(self, test_render):
        test_render(
            "#foreach ($i in [1, 2, 3])$i. #if ($foreach.last)yes#end, #end",
        )

    def test_can_use_an_integer_variable_defined_in_template(self, test_render):
        test_render("#set ($value = 10)$value")

    def test_can_use_a_string_variable_defined_in_template(self, test_render):
        test_render('#set ($value = "Steve")$value')

    def test_can_use_a_single_quoted_string_variable_defined_in_template(
        self, test_render
    ):
        test_render("#set ($value = 'Steve')$value")

    @pytest.mark.xfail(reason="Discrepancy with AWS")
    def test_single_line_comments_skipped(self, test_render):
        test_render(
            "## comment\nStuff\nMore stuff## more comments $blah",
        )

    @pytest.mark.xfail(reason="Discrepancy with AWS")
    def test_multi_line_comments_skipped(self, test_render):
        test_render(
            "Stuff#*\n more comments *#\n and more stuff",
        )

    # TODO: this VTL string is invalid in AWS API Gateway (results in 500 error)
    # def test_string_literal_can_contain_embedded_escaped_quotes(self, test_render):
    #     template = airspeed.Template('#set ($name = "\\"batman\\"")$name')
    #     assert template.merge({}) == '"batman"'

    @pytest.mark.xfail(reason="Discrepancy with AWS")
    def test_string_literal_can_contain_embedded_escaped_newlines(self, test_render):
        test_render(
            '#set ($name = "\\\\batman\\nand robin")$name',
        )

    def test_string_literal_with_inner_double_quotes(self, test_render):
        test_render("#set($d = '{\"a\": 2}')$d")

    def test_string_interpolation_with_inner_double_double_quotes(self, test_render):
        test_render('#set($d = "{""a"": 2}")$d')

    @pytest.mark.xfail(reason="Discrepancy with AWS")
    def test_string_interpolation_with_multiple_double_quotes(self, test_render):
        # Note: in AWS this would yield r'1\\"2"3', as backslashes are not escaped
        test_render(r'#set($d = "1\\""2""3")$d')

    @pytest.mark.xfail(reason="Discrepancy with AWS")
    def test_else_block_evaluated_when_if_expression_false(self, test_render):
        test_render("#if ($value) true #else false #end")

    @pytest.mark.xfail(reason="Discrepancy with AWS")
    def test_curly_else(self, test_render):
        test_render("#if($value)true#{else}false#end")

    @pytest.mark.xfail(reason="Discrepancy with AWS")
    def test_curly_end(self, test_render):
        test_render("#if($value)true#{end}monkey")

    @pytest.mark.xfail(reason="Discrepancy with AWS")
    def test_velocity_style_escaping(self, test_render):  # example from Velocity docs
        template = textwrap.dedent(
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
        test_render(
            template,
            # TODO remove
            # expected=textwrap.dedent(
            #     r"""
            # foo
            # $email
            # \\foo
            # \
            # \\ \# \$
            # #end
            # \# end
            # #set( foo = "foo" )
            # """
            # ),
        )

    # def test_velocity_style_escaping_when_var_unset(self, test_render): # example from Velocity docs
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

    def test_true_elseif_evaluated_when_if_is_false(self, test_render):
        test_render(
            "#if ($value1) one #elseif ($value2) two #end",
            context={"value1": False, "value2": True},
        )

    # TODO: introduce test_render(..) fixture below!

    def test_false_elseif_skipped_when_if_is_true(self, test_render):
        template = airspeed.Template("#if ($value1) one #elseif ($value2) two #end")
        value1, value2 = True, False
        assert template.merge(locals()) == " one "

    def test_first_true_elseif_evaluated_when_if_is_false(self, test_render):
        template = airspeed.Template(
            "#if ($value1) one #elseif ($value2) two #elseif($value3) three #end"
        )
        value1, value2, value3 = False, True, True
        assert template.merge(locals()) == " two "

    def test_else_evaluated_when_if_and_elseif_are_false(self, test_render):
        template = airspeed.Template(
            "#if ($value1) one #elseif ($value2) two #else three #end"
        )
        value1, value2 = False, False
        assert template.merge(locals()) == " three "

    def test_syntax_error_contains_line_and_column_pos(self, test_render):
        try:
            airspeed.Template("#if ( $hello )\n\n#elseif blah").merge({})
        except airspeed.TemplateSyntaxError as e:
            assert (e.line, e.column) == (3, 9)
        else:
            pytest.fail("expected error")
        try:
            airspeed.Template("#else blah").merge({})
        except airspeed.TemplateSyntaxError as e:
            assert (e.line, e.column) == (1, 1)
        else:
            pytest.fail("expected error")

    def test_get_position_strings_in_syntax_error(self, test_render):
        try:
            airspeed.Template("#else whatever").merge({})
        except airspeed.TemplateSyntaxError as e:
            assert e.get_position_strings() == ["#else whatever", "^"]
        else:
            pytest.fail("expected error")

    def test_get_position_strings_in_syntax_error_when_newline_after_error(
        self, test_render
    ):
        try:
            airspeed.Template("#else whatever\n").merge({})
        except airspeed.TemplateSyntaxError as e:
            assert e.get_position_strings() == ["#else whatever", "^"]
        else:
            pytest.fail("expected error")

    def test_get_position_strings_in_syntax_error_when_newline_before_error(
        self, test_render
    ):
        try:
            airspeed.Template("foobar\n  #else whatever\n").merge({})
        except airspeed.TemplateSyntaxError as e:
            assert e.get_position_strings() == ["  #else whatever", "  ^"]
        else:
            pytest.fail("expected error")

    def test_compare_greater_than_operator(self, test_render):
        for operator in [">", "gt"]:
            template = airspeed.Template("#if ( $value %s 1 )yes#end" % operator)
            assert template.merge({"value": 0}) == ""
            assert template.merge({"value": 1}) == ""
            assert template.merge({"value": 2}) == "yes"

    def test_compare_greater_than_or_equal_operator(self, test_render):
        for operator in [">=", "ge"]:
            template = airspeed.Template("#if ( $value %s 1 )yes#end" % operator)
            assert template.merge({"value": 0}) == ""
            assert template.merge({"value": 1}) == "yes"
            assert template.merge({"value": 2}) == "yes"

    def test_compare_less_than_operator(self, test_render):
        for operator in ["<", "lt"]:
            template = airspeed.Template("#if ( $value %s 1 )yes#end" % operator)
            assert template.merge({"value": 0}) == "yes"
            assert template.merge({"value": 1}) == ""
            assert template.merge({"value": 2}) == ""

    def test_compare_less_than_or_equal_operator(self, test_render):
        for operator in ["<=", "le"]:
            template = airspeed.Template("#if ( $value %s 1 )yes#end" % operator)
            assert template.merge({"value": 0}) == "yes"
            assert template.merge({"value": 1}) == "yes"
            assert template.merge({"value": 2}) == ""

    def test_compare_equality_operator(self, test_render):
        for operator in ["==", "eq"]:
            template = airspeed.Template("#if ( $value %s 1 )yes#end" % operator)
            assert template.merge({"value": 0}) == ""
            assert template.merge({"value": 1}) == "yes"
            assert template.merge({"value": 2}) == ""

    def test_or_operator(self, test_render):
        template = airspeed.Template("#if ( $value1 || $value2 )yes#end")
        assert template.merge({"value1": False, "value2": False}) == ""
        assert template.merge({"value1": True, "value2": False}) == "yes"
        assert template.merge({"value1": False, "value2": True}) == "yes"

    def test_or_operator_otherform(self, test_render):
        template = airspeed.Template("#if ( $value1 or $value2 )yes#end")
        assert template.merge({"value1": False, "value2": False}) == ""
        assert template.merge({"value1": True, "value2": False}) == "yes"
        assert template.merge({"value1": False, "value2": True}) == "yes"

    def test_or_operator_considers_not_None_values_true(self, test_render):
        class SomeClass:
            pass

        template = airspeed.Template("#if ( $value1 || $value2 )yes#end")
        assert template.merge({"value1": None, "value2": None}) == ""
        assert template.merge({"value1": SomeClass(), "value2": False}) == "yes"
        assert template.merge({"value1": False, "value2": SomeClass()}) == "yes"

    def test_and_operator(self, test_render):
        template = airspeed.Template("#if ( $value1 && $value2 )yes#end")
        assert template.merge({"value1": False, "value2": False}) == ""
        assert template.merge({"value1": True, "value2": False}) == ""
        assert template.merge({"value1": False, "value2": True}) == ""
        assert template.merge({"value1": True, "value2": True}) == "yes"

    def test_and_operator_otherform(self, test_render):
        template = airspeed.Template("#if ( $value1 and $value2 )yes#end")
        assert template.merge({"value1": False, "value2": False}) == ""
        assert template.merge({"value1": True, "value2": False}) == ""
        assert template.merge({"value1": False, "value2": True}) == ""
        assert template.merge({"value1": True, "value2": True}) == "yes"

    def test_and_operator_considers_not_None_values_true(self, test_render):
        class SomeClass:
            pass

        template = airspeed.Template("#if ( $value1 && $value2 )yes#end")
        assert template.merge({"value1": None, "value2": None}) == ""
        assert template.merge({"value1": SomeClass(), "value2": True}) == "yes"
        assert template.merge({"value1": True, "value2": SomeClass()}) == "yes"

    def test_parenthesised_value(self, test_render):
        template = airspeed.Template("#if ( ($value1 == 1) && ($value2 == 2) )yes#end")
        assert template.merge({"value1": 0, "value2": 1}) == ""
        assert template.merge({"value1": 1, "value2": 1}) == ""
        assert template.merge({"value1": 0, "value2": 2}) == ""
        assert template.merge({"value1": 1, "value2": 2}) == "yes"

    def test_multiterm_expression(self, test_render):
        template = airspeed.Template("#if ( $value1 == 1 && $value2 == 2 )yes#end")
        assert template.merge({"value1": 0, "value2": 1}) == ""
        assert template.merge({"value1": 1, "value2": 1}) == ""
        assert template.merge({"value1": 0, "value2": 2}) == ""
        assert template.merge({"value1": 1, "value2": 2}) == "yes"

    def test_compound_condition(self, test_render):
        template = airspeed.Template("#if ( ($value) )yes#end")
        assert template.merge({"value": False}) == ""
        assert template.merge({"value": True}) == "yes"

    def test_logical_negation_operator(self, test_render):
        template = airspeed.Template("#if ( !$value )yes#end")
        assert template.merge({"value": False}) == "yes"
        assert template.merge({"value": True}) == ""

    def test_logical_alt_negation_operator(self, test_render):
        template = airspeed.Template("#if ( not $value )yes#end")
        assert template.merge({"value": False}) == "yes"
        assert template.merge({"value": True}) == ""

    def test_logical_negation_operator_yields_true_for_None(self, test_render):
        template = airspeed.Template("#if ( !$value )yes#end")
        assert template.merge({"value": None}) == "yes"

    def test_logical_negation_operator_honours_custom_truth_values(self, test_render):
        class BooleanValue(object):
            def __init__(self, value):
                self.value = value

            def __bool__(self):
                return self.value

            def __nonzero__(self):
                return self.__bool__()

        template = airspeed.Template("#if ( !$v)yes#end")
        assert template.merge({"v": BooleanValue(False)}) == "yes"
        assert template.merge({"v": BooleanValue(True)}) == ""

    def test_compound_binary_and_unary_operators(self, test_render):
        template = airspeed.Template("#if ( !$value1 && !$value2 )yes#end")
        assert template.merge({"value1": False, "value2": True}) == ""
        assert template.merge({"value1": True, "value2": False}) == ""
        assert template.merge({"value1": True, "value2": True}) == ""
        assert template.merge({"value1": False, "value2": False}) == "yes"

    def test_define_and_use_macro_with_no_parameters(self, test_render):
        template = airspeed.Template("#macro ( hello)hi#end#hello ()#hello()")
        assert template.merge({"text": "hello"}) == "hihi"

    def test_define_and_use_macro_with_one_parameter(self, test_render):
        template = airspeed.Template(
            "#macro ( bold $value)<strong>$value</strong>#end#bold ($text)"
        )
        assert template.merge({"text": "hello"}) == "<strong>hello</strong>"

    def test_define_and_use_macro_with_two_parameters_no_comma(self, test_render):
        template = airspeed.Template(
            "#macro ( bold $value $other)<strong>$value</strong>$other#end#bold ($text $monkey)"
        )
        assert (
            template.merge({"text": "hello", "monkey": "cheese"})
            == "<strong>hello</strong>cheese"
        )

    # We use commas with our macros and it seems to work
    # so it's correct behavior by definition; the real
    # question is whether using them without a comma is a legal variant
    # or not.  This should affect the above test; the following test
    # should be legal by definition

    def test_define_and_use_macro_with_two_parameters_with_comma(self, test_render):
        template = airspeed.Template(
            "#macro ( bold $value, $other)<strong>$value</strong>$other#end#bold ($text, $monkey)"
        )
        assert (
            template.merge({"text": "hello", "monkey": "cheese"})
            == "<strong>hello</strong>cheese"
        )

    def test_use_of_macro_name_is_case_insensitive(self, test_render):
        template = airspeed.Template(
            "#macro ( bold $value)<strong>$value</strong>#end#BoLd ($text)"
        )
        assert template.merge({"text": "hello"}) == "<strong>hello</strong>"

    def test_define_and_use_macro_with_two_parameter(self, test_render):
        template = airspeed.Template(
            "#macro (addition $value1 $value2 )$value1+$value2#end#addition (1 2)"
        )
        assert template.merge({}) == "1+2"
        template = airspeed.Template(
            "#macro (addition $value1 $value2 )$value1+$value2#end#addition( $one   $two )"
        )
        assert template.merge({"one": "ONE", "two": "TWO"}) == "ONE+TWO"

    def test_can_call_macro_with_newline_between_args(self, test_render):
        template = airspeed.Template(
            "#macro (hello $value1 $value2 )hello $value1 and $value2#end\n#hello (1,\n 2)"
        )
        assert template.merge({}) == "hello 1 and 2"

    def test_use_define_with_no_parameters(self, test_render):
        template = airspeed.Template("#define ( $hello)hi#end$hello()$hello()")
        assert template.merge({}) == "hihi"

    def test_use_define_with_parameters(self, test_render):
        template = airspeed.Template(
            '#define ( $echo $v1 $v2)$v1$v2#end$echo(1,"a")$echo("b",2)'
        )
        assert template.merge({"text": "hello"}) == "1ab2"
        template = airspeed.Template(
            '#define ( $echo $v1 $v2)$v1$v2#end$echo(1,"a")$echo($echo(2,"b"),"c")'
        )
        assert template.merge({}) == "1a2bc"
        template = airspeed.Template(
            '#define ( $echo $v1 $v2)$v1$v2#end$echo(1,"a")$echo("b",$echo(3,"c"))'
        )
        assert template.merge({}) == "1ab3c"

    def test_define_with_local_namespace(self, test_render):
        template = airspeed.Template(
            "#define ( $showindex )$foreach.index#end#foreach($x in [1,2,3])$showindex#end"
        )
        assert template.merge({}) == "012"

    def test_use_defined_func_multiple_times(self, test_render):
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
        assert result == "foobar"

    def test_use_defined_func_create_json_loop(self, test_render):
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
        assert result == '{"test":"123","test2":"abc"}{"foo":"bar"}'

    def test_valid_include_directive_include_content(self, test_render):
        class WorkingLoader:
            def load_text(self, name):
                if name == "foo.tmpl":
                    return "howdy"

        template = airspeed.Template('Message is: #include ("foo.tmpl")!')
        assert template.merge({}, loader=WorkingLoader()) == "Message is: howdy!"

    def test_valid_parse_directive_outputs_parsed_content(self, test_render):
        class WorkingLoader:
            def load_template(self, name):
                if name == "foo.tmpl":
                    return airspeed.Template("$message", name)

        template = airspeed.Template('Message is: #parse ("foo.tmpl")!')
        assert (
            template.merge({"message": "hola"}, loader=WorkingLoader())
            == "Message is: hola!"
        )
        template = airspeed.Template("Message is: #parse ($foo)!")
        assert (
            template.merge(
                {"foo": "foo.tmpl", "message": "hola"}, loader=WorkingLoader()
            )
            == "Message is: hola!"
        )

    def test_valid_parse_directive_merge_namespace(self, test_render):
        class WorkingLoader:
            def load_template(self, name):
                if name == "foo.tmpl":
                    return airspeed.Template("#set($message = 'hola')")

        template = airspeed.Template('#parse("foo.tmpl")Message is: $message!')
        assert template.merge({}, loader=WorkingLoader()) == "Message is: hola!"

    def test_assign_range_literal(self, test_render):
        template = airspeed.Template(
            "#set($values = [1..5])#foreach($value in $values)$value,#end"
        )
        assert template.merge({}) == "1,2,3,4,5,"
        template = airspeed.Template(
            "#set($values = [2..-2])#foreach($value in $values)$value,#end"
        )
        assert template.merge({}) == "2,1,0,-1,-2,"

    def test_local_namespace_methods_are_not_available_in_context(self, test_render):
        template = airspeed.Template("#macro(tryme)$values#end#tryme()")
        assert template.merge({}) == "$values"

    def test_array_literal(self, test_render):
        template = airspeed.Template(
            'blah\n#set($valuesInList = ["Hello ", $person, ", your lucky number is ", 7])\n#foreach($value in $valuesInList)$value#end\n\nblah'
        )
        assert (
            template.merge({"person": "Chris"})
            == "blah\nHello Chris, your lucky number is 7\nblah"
        )
        # NOTE: the original version of this test incorrectly preserved
        # the newline at the end of the #end line

    def test_dictionary_literal(self, test_render):
        template = airspeed.Template('#set($a = {"dog": "cat" , "horse":15})$a.dog')
        assert template.merge({}) == "cat"
        template = airspeed.Template('#set($a = {"dog": "$horse"})$a.dog')
        assert template.merge({"horse": "cow"}) == "cow"

    def test_dictionary_literal_as_parameter(self, test_render):
        template = airspeed.Template('$a({"color":"blue"})')
        ns = {"a": lambda x: x["color"] + " food"}
        assert template.merge(ns) == "blue food"

    def test_nested_array_literals(self, test_render):
        template = airspeed.Template(
            '#set($values = [["Hello ", "Steve"], ["Hello", " Chris"]])#foreach($pair in $values)#foreach($word in $pair)$word#end. #end'
        )
        assert template.merge({}) == "Hello Steve. Hello Chris. "

    def test_when_dictionary_does_not_contain_referenced_attribute_no_substitution_occurs(
        self,
    ):
        template = airspeed.Template(" $user.name ")
        assert template.merge({"user": self}) == " $user.name "

    def test_when_dictionary_has_same_key_as_built_in_method(self, test_render):
        template = airspeed.Template(" $user.items ")
        assert template.merge({"user": {"items": "1;2;3"}}) == " 1;2;3 "

    def test_when_non_dictionary_object_does_not_contain_referenced_attribute_no_substitution_occurs(
        self,
    ):
        class MyObject:
            pass

        template = airspeed.Template(" $user.name ")
        assert template.merge({"user": MyObject()}) == " $user.name "

    def test_variables_expanded_in_double_quoted_strings(self, test_render):
        template = airspeed.Template('#set($hello="hello, $name is my name")$hello')
        assert template.merge({"name": "Steve"}) == "hello, Steve is my name"

    def test_escaped_variable_references_not_expanded_in_double_quoted_strings(
        self, test_render
    ):
        template = airspeed.Template('#set($hello="hello, \\$name is my name")$hello')
        assert template.merge({"name": "Steve"}) == "hello, $name is my name"

    def test_macros_expanded_in_double_quoted_strings(self, test_render):
        template = airspeed.Template(
            '#macro(hi $person)$person says hello#end#set($hello="#hi($name)")$hello'
        )
        assert template.merge({"name": "Steve"}) == "Steve says hello"

    def test_color_spec(self, test_render):
        template = airspeed.Template('<span style="color: #13ff93">')
        assert template.merge({}) == '<span style="color: #13ff93">'

    # check for a plain hash outside of a context where it could be
    # confused with a directive or macro call.
    # this is useful for cases where someone put a hash in the target
    # of a link, which is typical when javascript is associated with the link

    def test_standalone_hashes(self, test_render):
        template = airspeed.Template("#")
        assert template.merge({}) == "#"
        template = airspeed.Template('"#"')
        assert template.merge({}) == '"#"'
        template = airspeed.Template('<a href="#">bob</a>')
        assert template.merge({}) == '<a href="#">bob</a>'

    def test_large_areas_of_text_handled_without_error(self, test_render):
        text = "qwerty uiop asdfgh jkl zxcvbnm. 1234" * 300
        template = airspeed.Template(text)
        assert template.merge({}) == text

    def test_foreach_with_unset_variable_expands_to_nothing(self, test_render):
        template = airspeed.Template("#foreach($value in $values)foo#end")
        assert template.merge({}) == ""

    def test_correct_scope_for_parameters_of_method_calls(self, test_render):
        template = airspeed.Template("$obj.get_self().method($param)")

        class C:
            def get_self(self):
                return self

            def method(self, p):
                if p == "bat":
                    return "monkey"

        value = template.merge({"obj": C(), "param": "bat"})
        assert value == "monkey"

    def test_preserves_unicode_strings(self, test_render):
        template = airspeed.Template("$value")
        value = "Grüße"
        assert template.merge(locals()) == value

    def test_preserves_unicode_strings_objects(self, test_render):
        template = airspeed.Template("$value")

        class Clazz:
            def __init__(self, value):
                self.value = value

            def __str__(self):
                return self.value

        value = Clazz("£12,000")
        assert template.merge(locals()) == six.text_type(value)

    def test_can_define_macros_in_parsed_files(self, test_render):
        class Loader:
            def load_template(self, name):
                if name == "foo.tmpl":
                    return airspeed.Template("#macro(themacro)works#end")

        template = airspeed.Template('#parse("foo.tmpl")#themacro()')
        assert template.merge({}, loader=Loader()) == "works"

    def test_modulus_operator(self, test_render):
        template = airspeed.Template("#set( $modulus = ($value % 2) )$modulus")
        assert template.merge({"value": 3}) == "1"

    def test_can_assign_empty_string(self, test_render):
        template = airspeed.Template("#set( $v = \"\" )#set( $y = '' ).$v.$y.")
        assert template.merge({}) == "..."

    def test_can_loop_over_numeric_ranges(self, test_render):
        # Test for bug #15
        template = airspeed.Template("#foreach( $v in [1..5] )$v\n#end")
        assert template.merge({}) == "1\n2\n3\n4\n5\n"

    def test_can_loop_over_numeric_ranges_backwards(self, test_render):
        template = airspeed.Template("#foreach( $v in [5..-2] )$v,#end")
        assert template.merge({}) == "5,4,3,2,1,0,-1,-2,"

    def test_ranges_over_references(self, test_render):
        template = airspeed.Template(
            "#set($start = 1)#set($end = 5)#foreach($i in [$start .. $end])$i-#end"
        )
        assert template.merge({}) == "1-2-3-4-5-"

    def test_user_defined_directive(self, test_render):
        class DummyDirective(airspeed._Element):
            PLAIN = re.compile(r"#(monkey)man(.*)$", re.S + re.I)

            def parse(self):
                (self.text,) = self.identity_match(self.PLAIN)

            def evaluate(self, stream, namespace, loader):
                stream.write(self.text)

        airspeed.UserDefinedDirective.DIRECTIVES.append(DummyDirective)
        template = airspeed.Template("hello #monkeyman")
        assert template.merge({}) == "hello monkey"
        airspeed.UserDefinedDirective.DIRECTIVES.remove(DummyDirective)

    def test_stop_directive(self, test_render):
        template = airspeed.Template("hello #stop world")
        assert template.merge({}) == "hello "

    def test_assignment_of_parenthesized_math_expression(self, test_render):
        template = airspeed.Template("#set($a = (5 + 4))$a")
        assert template.merge({}) == "9"

    def test_assignment_of_parenthesized_math_expression_with_reference(
        self, test_render
    ):
        template = airspeed.Template("#set($b = 5)#set($a = ($b + 4))$a")
        assert template.merge({}) == "9"

    def test_recursive_macro(self, test_render):
        template = airspeed.Template(
            "#macro ( recur $number)#if ($number > 0)#set($number = $number - 1)#recur($number)X#end#end#recur(5)"
        )
        assert template.merge({}) == "XXXXX"

    def test_addition_has_higher_precedence_than_comparison(self, test_render):
        template = airspeed.Template("#set($a = 4 > 2 + 5)$a")
        assert template.merge({}) == "False"

    def test_parentheses_work(self, test_render):
        template = airspeed.Template("#set($a = (5 + 4) > 2)$a")
        assert template.merge({}) == "True"

    def test_addition_has_higher_precedence_than_comparison_other_direction(
        self, test_render
    ):
        template = airspeed.Template("#set($a = 5 + 4 > 2)$a")
        assert template.merge({}) == "True"

    # Note: this template:
    # template = airspeed.Template('#set($a = (4 > 2) + 5)$a')
    # prints 6.  That's because Python automatically promotes True to 1
    # and False to 0.
    # This is weird, but I can't say it's wrong.

    def test_multiplication_has_higher_precedence_than_subtraction(self, test_render):
        template = airspeed.Template("#set($a = 5 * 4 - 2)$a")
        assert template.merge({}) == "18"

    def test_multiplication_has_higher_precedence_than_addition_reverse(
        self, test_render
    ):
        template = airspeed.Template("#set($a = 2 + 5 * 4)$a")
        assert template.merge({}) == "22"

    def test_parse_empty_dictionary(self, test_render):
        template = airspeed.Template("#set($a = {})$a")
        assert template.merge({}) == "{}"

    def test_macro_whitespace_and_newlines_ignored(self, test_render):
        template = airspeed.Template(
            """#macro ( blah )
hello##
#end
#blah()"""
        )
        assert template.merge({}) == "hello"

    def test_if_whitespace_and_newlines_ignored(self, test_render):
        template = airspeed.Template(
            """#if(true)
hello##
#end"""
        )
        assert template.merge({}) == "hello"

    def test_subobject_assignment(self, test_render):
        template = airspeed.Template("#set($outer.inner = 'monkey')")
        x = {"outer": {}}
        template.merge(x)
        assert x["outer"]["inner"] == "monkey"

    def test_expressions_with_numbers_with_fractions(self, test_render):
        template = airspeed.Template("#set($a = 100.0 / 50)$a")
        assert template.merge({}) == "2.0"
        # TODO: is that how Velocity would format a floating point?

    def test_multiline_arguments_to_function_calls(self, test_render):
        class Thing:
            def func(self, arg):
                return "y"

        template = airspeed.Template(
            """$x.func("multi
line")"""
        )
        assert template.merge({"x": Thing()}) == "y"

    def test_does_not_accept_dollar_digit_identifiers(self, test_render):
        template = airspeed.Template("$Something$0")
        assert template.merge({"0": "bar"}) == "$Something$0"

    def test_valid_vtl_identifiers(self, test_render):
        template = airspeed.Template("$_x $a $A")
        assert template.merge({"_x": "bar", "a": "z", "A": "Z"}) == "bar z Z"

    def test_invalid_vtl_identifier(self, test_render):
        template = airspeed.Template("$0")
        assert template.merge({"0": "bar"}) == "$0"

    def test_array_notation_int_index(self, test_render):
        template = airspeed.Template("$a[1]")
        assert template.merge({"a": ["foo", "bar"]}) == "bar"

    def test_array_notation_nested_indexes(self, test_render):
        template = airspeed.Template("$a[1][1]")
        assert template.merge({"a": ["foo", ["bar1", "bar2"]]}) == "bar2"

    def test_array_notation_dot(self, test_render):
        template = airspeed.Template("$a[1].bar1")
        assert template.merge({"a": ["foo", {"bar1": "bar2"}]}) == "bar2"

    def test_array_notation_dict_index(self, test_render):
        template = airspeed.Template('$a["foo"]')
        assert template.merge({"a": {"foo": "bar"}}) == "bar"

    def test_array_notation_empty_array_variable(self, test_render):
        template = airspeed.Template("$!a[1]")
        assert template.merge({"a": []}) == ""

    def test_array_notation_variable_index(self, test_render):
        template = airspeed.Template("#set($i = 1)$a[ $i ]")
        assert template.merge({"a": ["foo", "bar"]}) == "bar"

    def test_provides_helpful_error_location(self, test_render):
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
            pytest.fail("expected exception")
        except airspeed.TemplateExecutionError as e:
            assert e.filename == "mytemplate"
            assert e.start == 105
            assert e.end == 142
            assert isinstance(e.__cause__, TypeError)

    def test_outer_variable_assignable_from_foreach_block(self, test_render):
        template = airspeed.Template(
            "#set($var = 1)#foreach ($i in $items)" "$var,#set($var = $i)" "#end$var"
        )
        assert template.merge({"items": [2, 3, 4]}) == "1,2,3,4"

    def test_no_assignment_to_outer_var_if_same_varname_in_block(self, test_render):
        template = airspeed.Template(
            "#set($i = 1)$i," "#foreach ($i in [2, 3, 4])$i,#set($i = $i)#end" "$i"
        )
        assert template.merge({}) == "1,2,3,4,1"

    def test_nested_foreach_vars_are_scoped(self, test_render):
        template = airspeed.Template(
            "#foreach ($j in [1,2])"
            "#foreach ($i in [3, 4])$foreach.count,#end"
            "$foreach.count|#end"
        )
        assert template.merge({}) == "1,2,1|1,2,2|"

    def test_template_cannot_modify_its_args(self, test_render):
        template = airspeed.Template("#set($foo = 1)")
        ns = {"foo": 2}
        template.merge(ns)
        assert ns["foo"] == 2

    def test_doesnt_blow_stack(self, test_render):
        template = airspeed.Template(
            """
#foreach($i in [1..$end])
    $assembly##
#end
"""
        )
        ns = {"end": 400}
        template.merge(ns)

    def test_array_size(self, test_render):
        template = airspeed.Template("#set($foo = [1,2,3]) $foo.size()")
        output = template.merge({})
        assert " 3" == output

    def test_array_contains_true(self, test_render):
        template = airspeed.Template(
            "#set($foo = [1,2,3]) #if($foo.contains(1))found#end"
        )
        output = template.merge({})
        assert " found" == output

    def test_array_contains_false(self, test_render):
        template = airspeed.Template(
            "#set($foo = [1,2,3]) #if($foo.contains(10))found#end"
        )
        output = template.merge({})
        assert " " == output

    def test_array_get_item(self, test_render):
        template = airspeed.Template("#set($foo = [1,2,3]) $foo.get(1)")
        output = template.merge({})
        assert " 2" == output

    def test_array_add_item(self, test_render):
        template = airspeed.Template(
            "#set($foo = [1,2,3])"
            "#set( $ignore = $foo.add('string value') )"
            "#foreach($item in $foo)$item,#end"
        )
        output = template.merge({})
        assert "1,2,3,string value," == output

    def test_string_length(self, test_render):
        template = airspeed.Template("#set($foo = 'foobar123') $foo.length()")
        output = template.merge({})
        assert " 9" == output

    def test_string_replace_all(self, test_render):
        template = airspeed.Template(
            "#set($foo = 'foobar123bab') $foo.replaceAll('ba.', 'foo')"
        )
        output = template.merge({})
        assert " foofoo123foo" == output

    def test_string_starts_with_true(self, test_render):
        template = airspeed.Template(
            "#set($foo = 'foobar123') #if($foo.startsWith('foo'))yes!#end"
        )
        output = template.merge({})
        assert " yes!" == output

    def test_string_starts_with_false(self, test_render):
        template = airspeed.Template(
            "#set($foo = 'nofoobar123') #if($foo.startsWith('foo'))yes!#end"
        )
        output = template.merge({})
        assert " " == output

    def test_dict_put_item(self, test_render):
        template = airspeed.Template(
            "#set( $ignore = $test_dict.put('k', 'new value') )"
            "$ignore - $test_dict.k"
        )
        output = template.merge({"test_dict": {"k": "initial value"}})
        assert "initial value - new value" == output

    def test_dict_putall_items(self, test_render):
        template = airspeed.Template(
            "#set( $ignore = $test_dict.putAll({'k1': 'v3', 'k2': 'v2'}))"
            "$test_dict.k1 - $test_dict.k2"
        )
        output = template.merge({"test_dict": {"k1": "v1"}})
        assert "v3 - v2" == output

    def test_evaluate(self, test_render):
        template = airspeed.Template(
            """#set($source1 = "abc")
#set($select = "1")
#set($dynamicsource = "$source$select")
## $dynamicsource is now the string '$source1'
#evaluate($dynamicsource)"""
        )
        output = template.merge({})
        assert "abc" == output

    def test_return_macro(self, test_render):
        template = "#set($v1 = {})#set($ignore = $v1.put('foo', 'bar'))#return($v1)"
        template = airspeed.Template(template)
        output = template.merge({})
        assert '{"foo": "bar"}' == output


class TestInternals:
    def test_passed_in_namespace_not_modified_by_set(self):
        template = airspeed.Template("#set ($value = 10)$value")
        namespace = {}
        template.merge(namespace)
        assert namespace == {}

    def test_merge_to_stream(self, test_render):
        template = airspeed.Template("Hello $name!")
        output = six.StringIO()
        template.merge_to({"name": "Chris"}, output)
        assert output.getvalue() == "Hello Chris!"

    def test_silent_reference_function_calls_in_if_conditions(
        self, test_render_locally
    ):
        # again, this shouldn't make any difference
        test_render_locally(
            "#if($!{a.b.c('cheese')})yes!#end",
            context={"a": {"b": {"c": lambda x: "hello %s" % x}}},
            expected="yes!",
        )
        test_render_locally(
            "#if($!{a.b.c('cheese')})yes!#end",
            context={"a": {"b": {"c": lambda x: None}}},
            expected="",
        )
        test_render_locally("#if($!{a.b.c('cheese')})yes!#end", expected="")
        # with or without braces
        test_render_locally(
            "#if($!a.b.c('cheese'))yes!#end",
            context={"a": {"b": {"c": lambda x: "hello %s" % x}}},
            expected="yes!",
        )
        test_render_locally(
            "#if($!a.b.c('cheese'))yes!#end",
            context={"a": {"b": {"c": lambda x: None}}},
            expected="",
        )
        test_render_locally("#if($!a.b.c('cheese'))yes!#end", expected="")

    def test_reference_function_calls_in_if_conditions(self, test_render_locally):
        test_render_locally(
            "#if(${a.b.c('cheese')})yes!#end",
            context={"a": {"b": {"c": lambda x: "hello %s" % x}}},
            expected="yes!",
        )
        test_render_locally(
            "#if(${a.b.c('cheese')})yes!#end",
            context={"a": {"b": {"c": lambda x: None}}},
            expected="",
        )
        test_render_locally("#if(${a.b.c('cheese')})yes!#end", expected="")

    def test_can_return_value_from_an_attribute_of_a_context_object(
        self, test_render_locally
    ):
        class MyObj:
            pass

        o = MyObj()
        o.first_name = "Chris"
        test_render_locally(
            "Hello $name.first_name", context={"name": o}, expected="Hello Chris"
        )

    def test_can_return_value_from_a_method_of_a_context_object(
        self, test_render_locally
    ):
        class MyObj:
            def first_name(self):
                return "Chris"

        test_render_locally(
            "Hello $name.first_name()",
            context={"name": MyObj()},
            expected="Hello Chris",
        )

    def test_if_statement_honours_custom_truth_value_of_objects(
        self, test_render_locally
    ):
        class BooleanValue(object):
            def __init__(self, value):
                self.value = value

            def __bool__(self):
                return self.value

            def __nonzero__(self):
                return self.__bool__()

        test_render_locally(
            "#if ($v)yes#end",
            context={"v": BooleanValue(False)},
            expected="",
        )
        test_render_locally(
            "#if ($v)yes#end",
            context={"v": BooleanValue(True)},
            expected="yes",
        )

    def test_can_call_function_with_one_parameter(self, test_render_locally):
        def squared(number):
            return number * number

        test_render_locally("$squared(8)", context=locals(), expected="64")
        some_var = 6
        test_render_locally("$squared($some_var)", context=locals(), expected="36")
        test_render_locally(
            "$squared($squared($some_var))", context=locals(), expected="1296"
        )

    def test_can_call_function_with_two_parameters(self, test_render_locally):
        def multiply(number1, number2):
            return number1 * number2

        test_render_locally("$multiply(2, 4)", context=locals(), expected="8")
        test_render_locally("$multiply( 2 , 4 )", context=locals(), expected="8")
        value1, value2 = 4, 12
        test_render_locally(
            "$multiply($value1,$value2)", context=locals(), expected="48"
        )

    def test_extract_array_index_from_function_result(self, test_render_locally):
        def get_array():
            return ["p1", ["p2", "p3"]]

        test_render_locally("$get_array()[0]", context=locals(), expected="p1")
        test_render_locally("$get_array()[1][1]", context=locals(), expected="p3")


class TestInvalidCases:
    def test_unmatched_braces_raises_exception(self, test_render):
        # TODO: create fixture for negative tests!
        template = airspeed.Template("Hello ${name.")
        with pytest.raises(airspeed.TemplateSyntaxError):
            template.merge({})

    def test_too_many_end_clauses_trigger_error(self, test_render):
        template = airspeed.Template("#if (1)true!#end #end ")
        with pytest.raises(airspeed.TemplateSyntaxError):
            template.merge({})

    def test_illegal_to_have_elseif_after_else(self, test_render):
        template = airspeed.Template(
            "#if ($value1) one #else two #elseif($value3) three #end"
        )
        with pytest.raises(airspeed.TemplateSyntaxError):
            template.merge({})

    def test_cannot_define_macro_to_override_reserved_statements(self, test_render):
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
            with pytest.raises(airspeed.TemplateSyntaxError):
                template.merge({})

    def test_cannot_call_undefined_macro(self, test_render):
        template = airspeed.Template("#undefined()")
        with pytest.raises(airspeed.TemplateExecutionError):
            template.merge({})

    def test_cannot_redefine_macro(self, test_render):
        template = airspeed.Template("#macro ( hello)hi#end#macro(hello)again#end")
        # TODO: Should this be TemplateSyntaxError?
        with pytest.raises(airspeed.TemplateExecutionError):
            template.merge({})

    def test_include_directive_gives_error_if_no_loader_provided(self, test_render):
        template = airspeed.Template('#include ("foo.tmpl")')
        with pytest.raises(airspeed.TemplateError):
            template.merge({})

    def test_include_directive_yields_loader_error_if_included_content_not_found(
        self, test_render
    ):
        class BrokenLoader:
            def load_text(self, name):
                raise IOError(name)

        template = airspeed.Template('#include ("foo.tmpl")')
        with pytest.raises(airspeed.TemplateExecutionError) as exc:
            template.merge({}, loader=BrokenLoader())
        assert isinstance(exc.value.__cause__, IOError)

    def test_parse_directive_gives_error_if_no_loader_provided(self, test_render):
        template = airspeed.Template('#parse ("foo.tmpl")')
        with pytest.raises(airspeed.TemplateExecutionError):
            template.merge({})

    def test_parse_directive_yields_loader_error_if_parsed_content_not_found(
        self, test_render
    ):
        class BrokenLoader:
            def load_template(self, name):
                raise IOError(name)

        template = airspeed.Template('#parse ("foo.tmpl")')

        with pytest.raises(airspeed.TemplateExecutionError) as exc:
            template.merge({}, loader=BrokenLoader())
        assert isinstance(exc.value.__cause__, IOError)

    def test_foreach_with_non_iterable_variable_raises_error(self, test_render):
        template = airspeed.Template("#foreach($value in $values)foo#end")
        with pytest.raises(airspeed.TemplateExecutionError):
            template.merge({"values": 1})

    def test_array_notation_invalid_index(self, test_render):
        template = airspeed.Template('#set($i = "baz")$a[$i]')
        with pytest.raises(airspeed.TemplateExecutionError):
            template.merge({"a": ["foo", "bar"]})


# TODO:
#
#  Report locations for template errors in files included via loaders
#  Gobbling up whitespace (see WHITESPACE_TO_END_OF_LINE above, but need to apply in more places)
# Bind #macro calls at compile time?
# Scope of #set across if/elseif/else?
# there seems to be some confusion about the semantics of parameter
# passing to macros; an assignment in a macro body should persist past the
# macro call.  Confirm against Velocity.
