#!/usr/bin/env python

import re
import cStringIO as StringIO

class TemplateSyntaxError(Exception): pass

class Tokeniser:
    PLAIN, IF, PLACEHOLDER, FOREACH, END = range(5)

    UP_TO_NEXT_TEMPLATE_BIT = re.compile('^(.*?)((?:#|\$).*)', re.MULTILINE + re.DOTALL)
    REST = '(.*)$'
    NAME = '[a-z0-9_]+'
    NAME_OR_CALL = NAME + '(?:\(\))?'
    EXPRESSION = '(' + NAME_OR_CALL + '(?:\.' + NAME_OR_CALL + ')*)'
    PLACEHOLDER_PATTERN = re.compile('^\$(!?)({?)' + EXPRESSION + '(}?)' + REST, re.IGNORECASE + re.DOTALL + re.MULTILINE)
    BEGIN_IF_PATTERN = re.compile('^#if[ \t]*\([ \t]*\$' + EXPRESSION + '[ \t]*\)' + REST, re.IGNORECASE + re.DOTALL + re.MULTILINE)
    BEGIN_FOREACH_PATTERN = re.compile('^#foreach[ \t]*\([ \t]*\$(' + NAME + ')[ \t]+in[ \t]+\$' + EXPRESSION + '[ \t]*\)' + REST, re.IGNORECASE + re.DOTALL + re.MULTILINE)
    END_PATTERN = re.compile('^#end' + REST, re.IGNORECASE + re.DOTALL + re.MULTILINE)

    def tokenise(self, text):
        while True:
            m = self.UP_TO_NEXT_TEMPLATE_BIT.match(text)
            if not m:
                yield self.PLAIN, text
                break
            plain, interesting = m.groups()
            yield self.PLAIN, plain
            m = self.PLACEHOLDER_PATTERN.match(interesting)
            if m:
                expression, silent, original_text, text = self.get_placeholder(m)
                yield self.PLACEHOLDER, (expression, silent, original_text)
                continue
            m = self.BEGIN_IF_PATTERN.match(interesting)
            if m:
                expression, text = m.groups()
                yield self.IF, expression
                continue
            m = self.BEGIN_FOREACH_PATTERN.match(interesting)
            if m:
                iter_var, expression, text = m.groups()
                yield self.FOREACH, (expression, iter_var)
                continue
            m = self.END_PATTERN.match(interesting)
            if m:
                yield self.END, None
                (text,) = m.groups()
                continue
            raise TemplateSyntaxError("invalid token: %s" % text[:40])

    def get_placeholder(self, match):
        silent, open_brace, var_name, close_brace, rest = match.groups()
        if open_brace and not close_brace:
            raise TemplateSyntaxError("unmatched braces")
        if close_brace and not open_brace:
            rest = close_brace + rest
            original_text = ''.join(('$', silent, var_name))
        else:
            original_text = ''.join(('$', open_brace, silent, var_name, close_brace))
        return var_name, bool(silent), original_text, rest



class Evaluator:
    def eval_expression(self, expression, namespace_dict):
        o = namespace_dict
        for part in expression.split('.'):
            if part.endswith('()'):  ## FIXME
                part = part[:-2]
                try: o = getattr(o, part)
                except AttributeError: pass
                else: o = o()
            else:
                try: o = getattr(o, part)
                except AttributeError:
                    try: o = o[part]
                    except KeyError: pass
            if o in (None, namespace_dict): return None
        return o


class BlockEvaluator(Evaluator):
    class LocalNamespace(dict):
        def __init__(self, parent_namespace):
            self.parent_namespace = parent_namespace
        def __getitem__(self, key):
            try: return dict.__getitem__(self, key)
            except KeyError: return self.parent_namespace[key]

    def __init__(self):
        self.children = []
        self.delegate = None

    def evaluate(self, output_stream, namespace):
        for child in self.children:
            child.evaluate(output_stream, namespace)

    def add_evaluator(self, evaluator):
        self.children.append(evaluator)
        if hasattr(evaluator, 'add_evaluator'):
            self.delegate = evaluator

    def delegate_token(self, token_type, token_value):
        if self.delegate:
            if self.delegate.feed(token_type, token_value):
                return True
            else: self.delegate = None
        return False

    def feed(self, token_type, token_value):
        if self.delegate_token(token_type, token_value):
            return True
        if token_type == Tokeniser.END: return False
        elif token_type == Tokeniser.PLAIN: self.add_evaluator(PlainTextEvaluator(token_value))
        elif token_type == Tokeniser.PLACEHOLDER: self.add_evaluator(PlaceholderEvaluator(token_value))
        elif token_type == Tokeniser.FOREACH: self.add_evaluator(ForeachEvaluator(token_value))
        elif token_type == Tokeniser.IF: self.add_evaluator(IfEvaluator(token_value))
        else: raise TemplateSyntaxError("illegal token in block: %s, %s" % (token_type, token_value))
        return True


class PlainTextEvaluator(Evaluator):
    def __init__(self, text):
        self.text = text

    def evaluate(self, output_stream, namespace):
        output_stream.write(self.text)


class PlaceholderEvaluator(Evaluator):
    def __init__(self, token_value):
        self.expression, self.silent, self.original_text = token_value

    def evaluate(self, output_stream, namespace):
        value = self.eval_expression(self.expression, namespace)
        if value is None:
            if self.silent: expression_value = ''
            else: expression_value = self.original_text
        else:
            expression_value = str(value)
        output_stream.write(expression_value)


class IfEvaluator(BlockEvaluator):
    def __init__(self, token_value):
        BlockEvaluator.__init__(self)
        self.condition_expression = token_value

    def evaluate(self, output_stream, namespace):
        value = self.eval_expression(self.condition_expression, namespace)
        if value:
            BlockEvaluator.evaluate(self, output_stream, namespace)


class ForeachEvaluator(BlockEvaluator):
    def __init__(self, token_value):
        BlockEvaluator.__init__(self)
        self.expression, self.iter_var = token_value

    def evaluate(self, output_stream, namespace):
        values = self.eval_expression(self.expression, namespace)
        for value in values:
            local_namespace = BlockEvaluator.LocalNamespace(namespace)
            local_namespace[self.iter_var] = value
            BlockEvaluator.evaluate(self, output_stream, local_namespace)


class Parser:
    def __init__(self):
        self.data = {}

    def merge(self, content):
        output = []
        evaluator = BlockEvaluator()
        for token_type, token_value in Tokeniser().tokenise(str(content)):
            evaluator.feed(token_type, token_value)
        output = StringIO.StringIO()
        evaluator.evaluate(output, self.data)
        return output.getvalue()

    def __setitem__(self, name, value):
        self.data[name] = value


class Template:

    def __init__(self, content):
        self.content = content

    def __str__(self):
        return self.content



