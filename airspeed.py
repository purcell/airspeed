#!/usr/bin/env python

import re
import cStringIO as StringIO


class TemplateSyntaxError(Exception):
    def __init__(self, element, expected, got):
        if len(got) > 40:
            got = got[:36] + ' ...'
        Exception.__init__(self,"%s: expected %s, got: %s ..." % (element.__class__.__name__, expected, got))
class NoMatch(Exception): pass


class LocalNamespace(dict):
    def __init__(self, parent):
        dict.__init__(self)
        self.parent = parent
    def __getitem__(self, key):
        try: return dict.__getitem__(self, key)
        except KeyError: return self.parent[key]

class TextElement:
    MY_PATTERN = re.compile(r'^((?:[^\\\$#]|\\[\$#])+|\$[^!\{\}a-z0-9_])(.*)$', re.S + re.I)
    def __init__(self, text):
        m = self.MY_PATTERN.match(text)
        if not m: raise NoMatch()
        self.text, self.remaining_text = m.groups()

    def evaluate(self, namespace, stream):
        stream.write(self.text)


class IntegerLiteralElement:
    MY_PATTERN = re.compile(r'^(\d+)(.*)', re.S)
    def __init__(self, text):
        m = self.MY_PATTERN.match(text)
        if not m: raise NoMatch()
        self.value = int(m.group(1))
        self.remaining_text = m.group(2)

    def calculate(self, namespace):
        return self.value


class StringLiteralElement:
    MY_PATTERN = re.compile(r'^"((?:\\["nrbt\\]|[^"\n\r"\\])+)"(.*)', re.S)
    ESCAPED_CHAR = re.compile(r'\\([nrbt"\\])')
    def __init__(self, text):
        m = self.MY_PATTERN.match(text)
        if not m: raise NoMatch()
        def unescape(match):
            return {'n': '\n', 'r': '\r', 'b': '\b', 't': '\t', '"': '"', '\\': '\\'}[match.group(1)]
        self.value = self.ESCAPED_CHAR.sub(unescape, m.group(1))
        self.remaining_text = m.group(2)

    def calculate(self, namespace):
        return self.value


class ValueElement:
    def __init__(self, text):
        if text.startswith('$'):
            self.expression = ExpressionElement(text[1:])
        else:
            try:
                self.expression = IntegerLiteralElement(text)
            except NoMatch:
                self.expression = StringLiteralElement(text)
        self.remaining_text = self.expression.remaining_text

    def calculate(self, namespace):
        return self.expression.calculate(namespace)


class ExpressionElement:
    NAME_PATTERN = re.compile(r'^([a-zA-Z_][a-zA-Z0-9_]*)(.*)$', re.S)
    def __init__(self, text):
        self.names_and_calls = []
        try: text = self.read_name_or_call(text)
        except NoMatch: raise TemplateSyntaxError(self, 'name or call', text)
        while text.startswith('.'):
            try:
                text = self.read_name_or_call(text[1:])
            except NoMatch:   # for the '$name. blah' case
                break
        self.remaining_text = text

    def read_name_or_call(self, text):
        m = self.NAME_PATTERN.match(text)
        if not m: raise NoMatch()
        name, text = m.groups()
        parameter_list = None
        try:
            parameter_list = ParameterListElement(text)
            text = parameter_list.remaining_text
        except NoMatch:
            pass
        self.names_and_calls.append((name, parameter_list))
        return text

    def calculate(self, namespace):
        result = namespace
        for name, parameters in self.names_and_calls:
            try: result = getattr(result, name)
            except AttributeError:
                try: result = result[name]
                except KeyError: pass
            if result in (None, namespace): return None ## TODO: an explicit 'not found' exception?
            if parameters is not None:
                values = [value.calculate(namespace) for value in parameters.values]
                result = result(*values)
        return result


class ParameterListElement:
    OPENING_PATTERN = re.compile(r'^\(\s*(.*)$', re.S)
    CLOSING_PATTERN = re.compile(r'^\s*\)(.*)$', re.S)
    COMMA_PATTERN = re.compile(r'^\s*,\s*(.*)$', re.S)

    def __init__(self, text):
        self.values = []
        m = self.OPENING_PATTERN.match(text)
        if not m: raise NoMatch()
        text = m.group(1)
        while True:   ## FIXME
            m = self.COMMA_PATTERN.match(text)
            if not m: break
            value = ValueElement(m.group(1))
            text = value.remaining_text
            self.values.append(value)
        m = self.CLOSING_PATTERN.match(text)
        if not m: raise TemplateSyntaxError(self, ')', text)
        self.remaining_text = m.group(1)


class PlaceholderElement:
    MY_PATTERN = re.compile(r'^\$(!?)(\{?)(.*)$', re.S)
    CLOSING_BRACE_PATTERN = re.compile(r'^\}(.*)$', re.S)
    def __init__(self, text):
        m = self.MY_PATTERN.match(text)
        if not m: raise NoMatch()
        self.silent = bool(m.group(1))
        self.braces = bool(m.group(2))
        text = m.group(3)
        try:
            self.expression = ExpressionElement(text)
            text = self.expression.remaining_text
        except NoMatch:
            raise TemplateSyntaxError(self, 'expression', text)
        if self.braces:
            m = self.CLOSING_BRACE_PATTERN.match(text)
            if not m:
                raise TemplateSyntaxError(self, '}', text)
            text = m.group(1)
        self.remaining_text = text

    def evaluate(self, namespace, stream):
        value = self.expression.calculate(namespace)
        if value is None:
            if self.silent: value = ''
            else:
                value_as_str = '.'.join([name for name, params in self.expression.names_and_calls])
                if self.braces: value = '${%s}' % value_as_str
                else: value = '$%s' % value_as_str
        stream.write(str(value))


class CommentElement:
    COMMENT_PATTERN = re.compile('^##.*?(?:\n|$)(.*)$', re.M + re.S)
    MULTI_LINE_COMMENT_PATTERN = re.compile('^#\*.*?\*#(?:[ \t]*\n)?(.*$)', re.M + re.S)
    def __init__(self, text):
        for pattern in (self.COMMENT_PATTERN, self.MULTI_LINE_COMMENT_PATTERN):
            m = pattern.match(text)
            if not m: continue
            self.remaining_text = m.group(1)
            return
        raise NoMatch()

    def evaluate(self, namespace, stream):
        pass


class ConditionElement:
    OPENING_PATTERN = re.compile(r'^\(\s*(.*)$', re.S)
    CLOSING_PATTERN = re.compile(r'^\s*\)(.*)$', re.S)
    def __init__(self, text):
        m = self.OPENING_PATTERN.match(text)
        if not m: raise TemplateSyntaxError(self, '(', text)
        text = m.group(1)
        self.expression = ValueElement(text)
        text = self.expression.remaining_text
        m = self.CLOSING_PATTERN.match(text)
        if not m: raise TemplateSyntaxError(self, ')', text)
        self.remaining_text = m.group(1)

    def calculate(self, namespace):
        return self.expression.calculate(namespace)

class EndElement:
    END = re.compile(r'^#end(.*)', re.I + re.S)
    def __init__(self, text):
        m = self.END.match(text)
        if not m: raise NoMatch()
        self.remaining_text = m.group(1)


class IfElement:
    START = re.compile(r'^#if\b\s*(.*)', re.S + re.I)
    def __init__(self, text):
        m = self.START.match(text)
        if not m: raise NoMatch()
        text = m.group(1)
        self.condition = ConditionElement(text)
        text = self.condition.remaining_text
        self.block = BlockElement(text)
        text = self.block.remaining_text
        try:
            end = EndElement(text)
            self.remaining_text = end.remaining_text
        except NoMatch:
            raise TemplateSyntaxError(self, '#end', text)

    def evaluate(self, namespace, stream):
        if self.condition.calculate(namespace):
            self.block.evaluate(namespace, stream)


class SetElement:
    START = re.compile(r'^#set\s*\(\s*\$([a-z_][a-z0-9_]*)\s*=\s*(.*)$', re.S + re.I)
    CLOSING_PATTERN = re.compile(r'^\s*\)(.*)$', re.S)
    def __init__(self, text):
        m = self.START.match(text)
        if not m: raise NoMatch() ## Could be cleaner b/c syntax error if no '('
        self.var_name, text = m.groups()
        self.value = ValueElement(text)
        text = self.value.remaining_text
        m = self.CLOSING_PATTERN.match(text)
        if not m:
            raise TemplateSyntaxError(self, ')', text)
        self.remaining_text = m.group(1)

    def evaluate(self, namespace, stream):
        namespace[self.var_name] = self.value.calculate(namespace)


class ForeachElement:
    START = re.compile(r'^#foreach\s*\(\s*\$([a-z_][a-z0-9_]*)\s*in\s*(.*)$', re.S + re.I)
    CLOSING_PATTERN = re.compile(r'^\s*\)(.*)$', re.S)
    def __init__(self, text):
        m = self.START.match(text)
        if not m: raise NoMatch() ## Could be cleaner b/c syntax error if no '('
        self.loop_var_name, text = m.groups()
        self.value = ValueElement(text)
        text = self.value.remaining_text
        m = self.CLOSING_PATTERN.match(text)
        if not m:
            raise TemplateSyntaxError(self, ')', text)
        text = m.group(1)
        self.block = BlockElement(text)
        text = self.block.remaining_text
        try: end = EndElement(text)
        except NoMatch: raise TemplateSyntaxError(self, '#end', text)
        self.remaining_text = end.remaining_text


    def evaluate(self, namespace, stream):
        iterable = self.value.calculate(namespace)
        counter = 1
        for item in iterable:
            namespace = LocalNamespace(namespace)
            namespace['velocityCount'] = counter
            namespace[self.loop_var_name] = item
            self.block.evaluate(namespace, stream)
            counter += 1

class TemplateElement:
    def __init__(self, text):
        self.block = BlockElement(text)
        if self.block.remaining_text:
            raise TemplateSyntaxError(self, 'block element', self.block.remaining_text)

    def evaluate(self, namespace, stream):
        namespace = LocalNamespace(namespace)
        self.block.evaluate(namespace, stream)


class BlockElement:
    def __init__(self, text):
        self.children = []
        while text:
            child_matched = False
            for child_type in (TextElement, PlaceholderElement, CommentElement, IfElement, SetElement, ForeachElement):
                try:
                    child = child_type(text)
                    text = child.remaining_text
                    self.children.append(child)
                    child_matched = True
                    break
                except NoMatch:
                    continue
            if not child_matched:
                break
        self.remaining_text = text

    def evaluate(self, namespace, stream):
        for child in self.children:
            child.evaluate(namespace, stream)



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
            self.evaluator = TemplateElement(self.content)
        self.evaluator.evaluate(namespace, fileobj)
