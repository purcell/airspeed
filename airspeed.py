#!/usr/bin/env python

import re
import cStringIO as StringIO


class TemplateSyntaxError(Exception): pass


"""
VARIABLE_NAME   ->   '[a-zA-Z]+'
TEXT            ->   '(?:[^\$#\\]|\\\\|\\\$|\\#)+'
TEMPLATE        ->   BLOCK
BLOCK           ->   TEXT
                   | PLACEHOLDER
                   | IF_DIRECTIVE
                   | BLOCK_DIRECTIVE
REFERENCE        ->  '\$'  VARIABLE_VALUE
SILENT_REFERENCE ->  '\$!' VARIABLE_VALUE
VARIABLE_VALUE   ->  VARIABLE_NAME
                   | VARIABLE_NAME '\.' VARIABLE_VALUE


"""



class Tokeniser:
    PLAIN, IF, PLACEHOLDER, FOREACH, END, SET, ELSE = range(7)

    UP_TO_NEXT_TEMPLATE_BIT = re.compile('^(.*?)((?:#|\$).*)', re.MULTILINE + re.DOTALL)
    REST = '(.*)$'
    NAME = '[a-z0-9_]+'
    NAME_OR_CALL = NAME + '(?:\(\))?'
    RE_FLAGS = re.IGNORECASE + re.DOTALL + re.MULTILINE
    EXPRESSION = '(' + NAME_OR_CALL + '(?:\.' + NAME_OR_CALL + ')*)'
    STRING_LITERAL = "'(?:\\\\|\\'|\\n|\\b|\\t)'"
    PLACEHOLDER_PATTERN = re.compile('^\$(!?)({?)' + EXPRESSION + '(}?)' + REST, RE_FLAGS)
    SET_PATTERN = re.compile('^#set[ \t]*\([ \t]*\$(' + NAME + ')[ \t]*=[ \t]*(\d+|"[^"]+")[ \t]*\)' + REST, RE_FLAGS)
    BEGIN_IF_PATTERN = re.compile('^#if[ \t]*\([ \t]*\$' + EXPRESSION + '[ \t]*\)' + REST, RE_FLAGS)
    BEGIN_FOREACH_PATTERN = re.compile('^#foreach[ \t]*\([ \t]*\$(' + NAME + ')[ \t]+in[ \t]+\$' + EXPRESSION + '[ \t]*\)' + REST, RE_FLAGS)
    END_PATTERN = re.compile('^#end' + REST, RE_FLAGS)
    ELSE_PATTERN = re.compile('^#else' + REST, RE_FLAGS)
    COMMENT_PATTERN = re.compile('^##.*?(?:\n|$)' + REST, RE_FLAGS)
    MULTI_LINE_COMMENT_PATTERN = re.compile('^#\*.*?\*#(?:[ \t]*\n)?' + REST, RE_FLAGS)

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
            m = self.SET_PATTERN.match(interesting)
            if m:
                (var_name, rvalue, text) = m.groups()
                yield self.SET, (var_name, rvalue)
                continue
            m = self.ELSE_PATTERN.match(interesting)
            if m:
                (text,) = m.groups()
                yield self.ELSE, None
                continue
            m = self.COMMENT_PATTERN.match(interesting)
            if m:
                (text,) = m.groups()
                continue
            m = self.MULTI_LINE_COMMENT_PATTERN.match(interesting)
            if m:
                (text,) = m.groups()
                continue
            if interesting.startswith('$'):
                text = interesting[1:]
                yield self.PLAIN, '$'
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
        self.evaluate_block(output_stream, BlockEvaluator.LocalNamespace(namespace))

    def evaluate_block(self, output_stream, namespace):
        for child in self.children:
            child.evaluate(output_stream, namespace)

    def add_evaluator(self, evaluator):
        self.children.append(evaluator)
        if hasattr(evaluator, 'add_evaluator'):
            self.delegate = evaluator

    def delegate_token(self, token_type, token_value):
        if self.delegate:
            if not self.delegate.feed(token_type, token_value):
                self.delegate = None
            return True
        return False

    def feed(self, token_type, token_value):
        if self.delegate_token(token_type, token_value):
            return True
        if token_type == Tokeniser.END: return False
        elif token_type == Tokeniser.PLAIN: self.add_evaluator(PlainTextEvaluator(token_value))
        elif token_type == Tokeniser.PLACEHOLDER: self.add_evaluator(PlaceholderEvaluator(token_value))
        elif token_type == Tokeniser.FOREACH: self.add_evaluator(ForeachEvaluator(token_value))
        elif token_type == Tokeniser.IF: self.add_evaluator(IfEvaluator(token_value))
        elif token_type == Tokeniser.SET: self.add_evaluator(SetEvaluator(token_value))
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

    def evaluate_block(self, output_stream, namespace):
        value = self.eval_expression(self.condition_expression, namespace)
        if value:
            BlockEvaluator.evaluate_block(self, output_stream, namespace)


class ForeachEvaluator(BlockEvaluator):
    def __init__(self, token_value):
        BlockEvaluator.__init__(self)
        self.expression, self.iter_var = token_value

    def evaluate_block(self, output_stream, namespace):
        values = self.eval_expression(self.expression, namespace)
        counter = 1
        for value in values:
            namespace[self.iter_var] = value
            namespace['velocityCount'] = counter
            BlockEvaluator.evaluate_block(self, output_stream, namespace)
            counter += 1


class SetEvaluator(Evaluator):
    def __init__(self, token_value):
        self.var_name, self.rvalue = token_value

    def evaluate(self, output_stream, namespace):
        if self.rvalue.startswith('"'):
            value = self.rvalue[1:-1]
        else:
            value = int(self.rvalue)
        namespace[self.var_name] = value


class Template:
    def __init__(self, content):
        self.content = content
        self.evaluator = None

    def merge(self, namespace):
        output = StringIO.StringIO()
        self.merge_to(namespace, output)
        return output.getvalue()

    def merge_to(self, namespace, fileobj):
        output = []
        if not self.evaluator:
            self.evaluator = BlockEvaluator()
            for token_type, token_value in Tokeniser().tokenise(self.content):
                self.evaluator.feed(token_type, token_value)
        self.evaluator.evaluate(fileobj, namespace)
