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
        output = []
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


class _Element:
    def match_or_reject(self, pattern, text):
        m = pattern.match(text)
        if not m: raise NoMatch()
        return m.groups()

    def require_match(self, pattern, text, expected):
        m = pattern.match(text)
        if not m: raise TemplateSyntaxError(self, expected, text)
        return m.groups()

    def next_element(self, element_class, text):
        element = element_class(text)
        return element, element.remaining_text

    def require_next_element(self, element_class, text, expected):
        try: element = element_class(text)
        except NoMatch: raise TemplateSyntaxError(self, expected, text)
        else: return element, element.remaining_text


class Text(_Element):
    MY_PATTERN = re.compile(r'^((?:[^\\\$#]|\\[\$#])+|\$[^!\{a-z0-9_]|\$$|\\\\)(.*)$', re.S + re.I)
    ESCAPED_CHAR = re.compile(r'\\([\\\$#])')
    def __init__(self, text):
        text, self.remaining_text = self.match_or_reject(self.MY_PATTERN, text)
        def unescape(match):
            return match.group(1)
        self.text = self.ESCAPED_CHAR.sub(unescape, text)

    def evaluate(self, namespace, stream):
        stream.write(self.text)



class IntegerLiteral(_Element):
    MY_PATTERN = re.compile(r'^(\d+)(.*)', re.S)
    def __init__(self, text):
        self.value, self.remaining_text = self.match_or_reject(self.MY_PATTERN, text)
        self.value = int(self.value)

    def calculate(self, namespace):
        return self.value


class StringLiteral(_Element):
    MY_PATTERN = re.compile(r'^"((?:\\["nrbt\\\\]|[^"\n\r"\\])+)"(.*)', re.S)
    ESCAPED_CHAR = re.compile(r'\\([nrbt"\\])')
    def __init__(self, text):
        value, self.remaining_text = self.match_or_reject(self.MY_PATTERN, text)
        def unescape(match):
            return {'n': '\n', 'r': '\r', 'b': '\b', 't': '\t', '"': '"', '\\': '\\'}[match.group(1)]
        self.value = self.ESCAPED_CHAR.sub(unescape, value)

    def calculate(self, namespace):
        return self.value


class Value(_Element):
    def __init__(self, text):
        if text.startswith('$'):
            self.expression = Expression(text[1:])
        else:
            try:
                self.expression = IntegerLiteral(text)
            except NoMatch:
                self.expression = StringLiteral(text)
        self.remaining_text = self.expression.remaining_text

    def calculate(self, namespace):
        return self.expression.calculate(namespace)


class Expression(_Element):
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
        name, text = self.match_or_reject(self.NAME_PATTERN, text)
        parameter_list = None
        try:
            parameter_list, text = self.next_element(ParameterList, text)
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


class ParameterList(_Element):
    OPENING_PATTERN = re.compile(r'^\(\s*(.*)$', re.S)
    CLOSING_PATTERN = re.compile(r'^\s*\)(.*)$', re.S)
    COMMA_PATTERN = re.compile(r'^\s*,\s*(.*)$', re.S)

    def __init__(self, text):
        self.values = []
        text, = self.match_or_reject(self.OPENING_PATTERN, text)
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
        self.silent, self.braces, text = self.match_or_reject(self.MY_PATTERN, text)
        self.expression, text = self.require_next_element(Expression, text, 'expression')
        if self.braces:
            text, = self.require_match(self.CLOSING_BRACE_PATTERN, text, '}')
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


class Null:
    def evaluate(self, namespace, stream): pass


class Comment(_Element, Null):
    COMMENT_PATTERN = re.compile('^#(?:#.*?(?:\n|$)|\*.*?\*#(?:[ \t]*\n)?)(.*)$', re.M + re.S)
    def __init__(self, text):
        self.remaining_text, = self.match_or_reject(self.COMMENT_PATTERN, text)


class Condition(_Element):
    OPENING_PATTERN = re.compile(r'^\(\s*(.*)$', re.S)
    CLOSING_PATTERN = re.compile(r'^\s*\)(.*)$', re.S)
    def __init__(self, text):
        text, = self.require_match(self.OPENING_PATTERN, text, '(')
        self.expression, text = self.next_element(Value, text)
        self.remaining_text, = self.require_match(self.CLOSING_PATTERN, text, ')')

    def calculate(self, namespace):
        return self.expression.calculate(namespace)


class End(_Element):
    END = re.compile(r'^#end(.*)', re.I + re.S)
    def __init__(self, text):
        self.remaining_text, = self.match_or_reject(self.END, text)


class IfDirective(_Element):
    START = re.compile(r'^#if\b\s*(.*)$', re.S + re.I)
    START_ELSEIF = re.compile(r'^#elseif\b\s*(.*)$', re.S + re.I)
    START_ELSE = re.compile(r'^#else(.*)$', re.S + re.I)
    else_block = Null()

    def __init__(self, text):
        text, = self.match_or_reject(self.START, text)
        self.condition, text = self.next_element(Condition, text)
        self.block, text = self.next_element(Block, text)
        self.elseif_conditions = []
        while True:
            m = self.START_ELSEIF.match(text)
            if not m: break
            text = m.group(1)
            elseif_condition, text = self.require_next_element(Condition, text, 'condition')
            elseif_block, text = self.require_next_element(Block, text, 'block')
            self.elseif_conditions.append((elseif_condition, elseif_block))
        m = self.START_ELSE.match(text)
        if m:
            self.else_block, text = self.require_next_element(Block, m.group(1), 'block')
        end, self.remaining_text = self.require_next_element(End, text, '#else, #elseif or #end')

    def evaluate(self, namespace, stream):
        if self.condition.calculate(namespace):
            self.block.evaluate(namespace, stream)
        else:
            for elseif, block in self.elseif_conditions:
                if elseif.calculate(namespace):
                    block.evaluate(namespace, stream)
                    return
            self.else_block.evaluate(namespace, stream)


class SetDirective(_Element):
    START = re.compile(r'^#set\s*\(\s*\$([a-z_][a-z0-9_]*)\s*=\s*(.*)$', re.S + re.I)
    CLOSING_PATTERN = re.compile(r'^\s*\)(?:[ \t]*\r?\n)?(.*)$', re.S + re.M)
    def __init__(self, text):
        ## Could be cleaner b/c syntax error if no '('
        self.var_name, text = self.match_or_reject(self.START, text)
        self.value, text = self.next_element(Value, text)
        self.remaining_text, = self.require_match(self.CLOSING_PATTERN, text, ')')

    def evaluate(self, namespace, stream):
        namespace[self.var_name] = self.value.calculate(namespace)


class ForeachDirective(_Element):
    START = re.compile(r'^#foreach\s*\(\s*\$([a-z_][a-z0-9_]*)\s*in\s*(.*)$', re.S + re.I)
    CLOSING_PATTERN = re.compile(r'^\s*\)(.*)$', re.S)
    def __init__(self, text):
        ## Could be cleaner b/c syntax error if no '('
        self.loop_var_name, text = self.match_or_reject(self.START, text)
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
            child = None
            for child_type in (Text, Placeholder, Comment, IfDirective, SetDirective, ForeachDirective):
                try:
                    child, text = self.next_element(child_type, text)
                    self.children.append(child)
                    break
                except NoMatch:
                    continue
            if child is None:
                break
        self.remaining_text = text

    def evaluate(self, namespace, stream):
        for child in self.children:
            child.evaluate(namespace, stream)


