#!/usr/bin/env python

import re
import cStringIO as StringIO

__all__ = ['TemplateSyntaxError', 'Template']

###############################################################################
# Public interface
###############################################################################

class Template:
    def __init__(self, content):
        self.content = content
        self.evaluator = None

    def merge(self, namespace):
        output = StringIO.StringIO()
        self.merge_to(namespace, output)
        return output.getvalue()

    def merge_to(self, namespace, fileobj):
        if not self.evaluator:
            self.evaluator = TemplateBody(self.content)
        self.evaluator.evaluate(namespace, fileobj)


class TemplateSyntaxError(Exception):
    def __init__(self, element, expected, got):
        if len(got) > 40:
            got = got[:36] + ' ...'
        Exception.__init__(self,"%s: expected %s, got: %s ..." % (element.__class__.__name__, expected, got))


###############################################################################
# Internals
###############################################################################

class NoMatch(Exception): pass


class LocalNamespace(dict):
    def __init__(self, parent):
        dict.__init__(self)
        self.parent = parent

    def __getitem__(self, key):
        try: return dict.__getitem__(self, key)
        except KeyError: return self.parent[key]

    def __repr__(self):
        return dict.__repr__(self) + '->' + repr(self.parent)


class _Element:
    def identity_match(self, pattern, text):
        m = pattern.match(text)
        if not m: raise NoMatch()
        return m.groups()

    def require_match(self, pattern, text, expected):
        m = pattern.match(text)
        if not m: raise TemplateSyntaxError(self, expected, text)
        return m.groups()

    def next_element(self, element_spec, text):
        if callable(element_spec):
            element = element_spec(text)
            return element, element.remaining_text
        else:
            for element_class in element_spec:
                try: element = element_class(text)
                except NoMatch: pass
                else: return element, element.remaining_text
            raise NoMatch()

    def require_next_element(self, element_spec, text, expected):
        if callable(element_spec):
            try: element = element_spec(text)
            except NoMatch: raise TemplateSyntaxError(self, expected, text)
            else: return element, element.remaining_text
        else:
            for element_class in element_spec:
                try: element = element_class(text)
                except NoMatch: pass
                else: return element, element.remaining_text
            expected = ', '.join([cls.__name__ for cls in element_spec])
            raise TemplateSyntaxError(self, 'one of: ' + expected, text)


class Text(_Element):
    MY_PATTERN = re.compile(r'^((?:[^\\\$#]|\\[\$#])+|\$[^!\{a-z0-9_]|\$$|\\\\)(.*)$', re.S + re.I)
    ESCAPED_CHAR = re.compile(r'\\([\\\$#])')
    def __init__(self, text):
        text, self.remaining_text = self.identity_match(self.MY_PATTERN, text)
        def unescape(match):
            return match.group(1)
        self.text = self.ESCAPED_CHAR.sub(unescape, text)

    def evaluate(self, namespace, stream):
        stream.write(self.text)


class IntegerLiteral(_Element):
    MY_PATTERN = re.compile(r'^(\d+)(.*)', re.S)
    def __init__(self, text):
        self.value, self.remaining_text = self.identity_match(self.MY_PATTERN, text)
        self.value = int(self.value)

    def calculate(self, namespace):
        return self.value


class StringLiteral(_Element):
    MY_PATTERN = re.compile(r'^"((?:\\["nrbt\\\\]|[^"\n\r"\\])+)"(.*)', re.S)
    ESCAPED_CHAR = re.compile(r'\\([nrbt"\\])')
    def __init__(self, text):
        value, self.remaining_text = self.identity_match(self.MY_PATTERN, text)
        def unescape(match):
            return {'n': '\n', 'r': '\r', 'b': '\b', 't': '\t', '"': '"', '\\': '\\'}[match.group(1)]
        self.value = self.ESCAPED_CHAR.sub(unescape, value)

    def calculate(self, namespace):
        return self.value


class Value(_Element):
    def __init__(self, text):
        self.expression, self.remaining_text = self.next_element((PlainReference, IntegerLiteral, StringLiteral), text)

    def calculate(self, namespace):
        return self.expression.calculate(namespace)


class NameOrCall(_Element):
    NAME_PATTERN = re.compile(r'^([a-zA-Z_][a-zA-Z0-9_]*)(.*)$', re.S)
    parameters = None
    def __init__(self, text):
        self.name, text = self.identity_match(self.NAME_PATTERN, text)
        try: self.parameters, text = self.next_element(ParameterList, text)
        except NoMatch: pass
        self.remaining_text = text

    def calculate(self, namespace, top_namespace):
        try: result = getattr(namespace, self.name)
        except AttributeError:
            try: result = namespace[self.name]
            except KeyError: result = None
        if result is None:
            return None ## TODO: an explicit 'not found' exception?
        if self.parameters is not None:
            values = [value.calculate(top_namespace) for value in self.parameters.values]
            result = result(*values)
        return result


class Expression(_Element):
    def __init__(self, text):
        self.names_and_calls = []
        part, text = self.require_next_element(NameOrCall, text, 'name')
        self.names_and_calls.append(part)
        while text.startswith('.'):
            try:
                part, text = self.next_element(NameOrCall, text[1:])
                self.names_and_calls.append(part)
            except NoMatch: break  # for the '$name. blah' case
        self.remaining_text = text

    def calculate(self, namespace):
        value = namespace
        for part in self.names_and_calls:
            value = part.calculate(value, namespace)
            if value is None: return None
        return value


class ParameterList(_Element):
    OPENING_PATTERN = re.compile(r'^\(\s*(.*)$', re.S)
    CLOSING_PATTERN = re.compile(r'^\s*\)(.*)$', re.S)
    COMMA_PATTERN = re.compile(r'^\s*,\s*(.*)$', re.S)

    def __init__(self, text):
        self.values = []
        text, = self.identity_match(self.OPENING_PATTERN, text)
        try: value, text = self.next_element(Value, text)
        except NoMatch:
            pass
        else:
            self.values.append(value)
            while True:
                m = self.COMMA_PATTERN.match(text)
                if not m: break
                value, text = self.require_next_element(Value, m.group(1), 'value')
                self.values.append(value)
        self.remaining_text, = self.require_match(self.CLOSING_PATTERN, text, ')')


class Placeholder(_Element):
    MY_PATTERN = re.compile(r'^\$(!?)(\{?)(.*)$', re.S)
    CLOSING_BRACE_PATTERN = re.compile(r'^\}(.*)$', re.S)
    def __init__(self, text):
        self.silent, self.braces, text = self.identity_match(self.MY_PATTERN, text)
        self.expression, text = self.require_next_element(Expression, text, 'expression')
        if self.braces:
            text, = self.require_match(self.CLOSING_BRACE_PATTERN, text, '}')
        self.remaining_text = text

    def evaluate(self, namespace, stream):
        value = self.expression.calculate(namespace)
        if value is None:
            if self.silent: value = ''
            else:
                value_as_str = '.'.join([name.name for name in self.expression.names_and_calls])
                if self.braces: value = '${%s}' % value_as_str
                else: value = '$%s' % value_as_str
        stream.write(str(value))


class PlainReference(_Element):
    def __init__(self, text):
        if not text.startswith('$'): raise NoMatch()
        self.expression, self.remaining_text = self.require_next_element(Expression, text[1:], 'name')
        self.calculate = self.expression.calculate


class Null:
    def evaluate(self, namespace, stream): pass


class Comment(_Element, Null):
    COMMENT_PATTERN = re.compile('^#(?:#.*?(?:\n|$)|\*.*?\*#(?:[ \t]*\n)?)(.*)$', re.M + re.S)
    def __init__(self, text):
        self.remaining_text, = self.identity_match(self.COMMENT_PATTERN, text)


class Condition(_Element):
    OPENING_PATTERN = re.compile(r'^\(\s*(.*)$', re.S)
    CLOSING_PATTERN = re.compile(r'^\s*\)(.*)$', re.S)
    def __init__(self, text):
        text, = self.require_match(self.OPENING_PATTERN, text, '(')
        self.expression, text = self.next_element(Value, text)
        self.remaining_text, = self.require_match(self.CLOSING_PATTERN, text, ')')
        self.calculate = self.expression.calculate


class End(_Element):
    END = re.compile(r'^#end(.*)', re.I + re.S)
    def __init__(self, text):
        self.remaining_text, = self.identity_match(self.END, text)


class ElseBlock(_Element):
    START = re.compile(r'^#else(.*)$', re.S + re.I)
    def __init__(self, text):
        text, = self.identity_match(self.START, text)
        self.block, self.remaining_text = self.require_next_element(Block, text, 'block')
        self.evaluate = self.block.evaluate


class ElseifBlock(_Element):
    START = re.compile(r'^#elseif\b\s*(.*)$', re.S + re.I)
    def __init__(self, text):
        text, = self.identity_match(self.START, text)
        self.condition, text = self.require_next_element(Condition, text, 'condition')
        self.block, self.remaining_text = self.require_next_element(Block, text, 'block')
        self.calculate = self.condition.calculate
        self.evaluate = self.block.evaluate


class IfDirective(_Element):
    START = re.compile(r'^#if\b\s*(.*)$', re.S + re.I)
    START_ELSEIF = re.compile(r'^#elseif\b\s*(.*)$', re.S + re.I)
    else_block = Null()

    def __init__(self, text):
        text, = self.identity_match(self.START, text)
        self.condition, text = self.next_element(Condition, text)
        self.block, text = self.next_element(Block, text)
        self.elseifs = []
        while True:
            try:
                elseif_block, text = self.next_element(ElseifBlock, text)
                self.elseifs.append(elseif_block)
            except NoMatch:
                break
        try: self.else_block, text = self.next_element(ElseBlock, text)
        except NoMatch: pass
        end, self.remaining_text = self.require_next_element(End, text, '#else, #elseif or #end')

    def evaluate(self, namespace, stream):
        if self.condition.calculate(namespace):
            self.block.evaluate(namespace, stream)
        else:
            for elseif in self.elseifs:
                if elseif.calculate(namespace):
                    elseif.evaluate(namespace, stream)
                    return
            self.else_block.evaluate(namespace, stream)


class Assignment(_Element):
    START = re.compile(r'^\s*\(\s*\$([a-z_][a-z0-9_]*)\s*=\s*(.*)$', re.S)
    CLOSING_PATTERN = re.compile(r'^\s*\)(?:[ \t]*\r?\n)?(.*)$', re.S + re.M)
    def __init__(self, text):
        self.var_name, text = self.identity_match(self.START, text)
        self.value, text = self.next_element(Value, text)
        self.remaining_text, = self.require_match(self.CLOSING_PATTERN, text, ')')

    def calculate(self, namespace):
        namespace[self.var_name] = self.value.calculate(namespace)


class SetDirective(_Element):
    START = re.compile(r'^#set\b(.*)', re.S + re.I)
    def __init__(self, text):
        text, = self.identity_match(self.START, text)
        self.assignment, self.remaining_text = self.require_next_element(Assignment, text, 'assignment')

    def evaluate(self, namespace, stream):
        self.assignment.calculate(namespace)


class ForeachDirective(_Element):
    START = re.compile(r'^#foreach\s*\(\s*\$([a-z_][a-z0-9_]*)\s*in\s*(.*)$', re.S + re.I)
    CLOSING_PATTERN = re.compile(r'^\s*\)(.*)$', re.S)
    def __init__(self, text):
        ## Could be cleaner b/c syntax error if no '('
        self.loop_var_name, text = self.identity_match(self.START, text)
        self.value, text = self.next_element(Value, text)
        text, = self.require_match(self.CLOSING_PATTERN, text, ')')
        self.block, text = self.next_element(Block, text)
        end, self.remaining_text = self.require_next_element(End, text, '#end')

    def evaluate(self, namespace, stream):
        iterable = self.value.calculate(namespace)
        counter = 1
        for item in iterable:
            namespace = LocalNamespace(namespace)
            namespace['velocityCount'] = counter
            namespace[self.loop_var_name] = item
            self.block.evaluate(namespace, stream)
            counter += 1


class TemplateBody(_Element):
    def __init__(self, text):
        self.block, text = self.next_element(Block, text)
        if text:
            raise TemplateSyntaxError(self, 'block element', self.block.remaining_text)

    def evaluate(self, namespace, stream):
        namespace = LocalNamespace(namespace)
        self.block.evaluate(namespace, stream)


class Block(_Element):
    def __init__(self, text):
        self.children = []
        while text:
            try:
                child, text = self.next_element((Text, Placeholder, Comment, IfDirective, SetDirective, ForeachDirective), text)
                self.children.append(child)
            except NoMatch:
                break
        self.remaining_text = text

    def evaluate(self, namespace, stream):
        for child in self.children:
            child.evaluate(namespace, stream)
