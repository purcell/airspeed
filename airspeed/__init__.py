from __future__ import print_function

import re
import operator
import os
import string
import sys

import six

__all__ = [
    'Template',
    'TemplateError',
    'TemplateExecutionError',
    'TemplateSyntaxError',
    'CachingFileLoader']

# A dict that maps classes to dicts of additional methods.
# This allows support for methods that are available in Java-based Velocity
# implementations, e.g., .size() of a list or .length() of a string.
# Given a method 'm' invoked with parameters '*p' on an object of type 't',
# and if __additional_methods__[t][m] exists, we will invoke and return m(t, *p)
#
# For example, given a template variable "$foo = [1,2,3]", "$foo.size()" will
# result in calling method __additional_methods__[list]['size']($foo)
__additional_methods__ = {
    str: {
        'length': lambda self: len(self),
        'replaceAll': lambda self, pattern, repl: re.sub(pattern, repl, self),
        'startsWith': lambda self, prefix: self.startswith(prefix)
    },
    list: {
        'size': lambda self: len(self),
        'get': lambda self, index: self[index],
        'contains': lambda self, value: value in self,
        'add': lambda self, value: self.append(value)
    },
    dict: {
        'put': lambda self, key, value: self.update({key: value}),
        'keySet': lambda self: self.keys()
    }
}

try:
    dict
except NameError:
    from UserDict import UserDict

    class dict(UserDict):

        def __init__(self):
            self.data = {}
try:
    operator.__gt__
except AttributeError:
    operator.__gt__ = lambda a, b: a > b
    operator.__lt__ = lambda a, b: a < b
    operator.__ge__ = lambda a, b: a >= b
    operator.__le__ = lambda a, b: a <= b
    operator.__eq__ = lambda a, b: a == b
    operator.__ne__ = lambda a, b: a != b
    operator.mod = lambda a, b: a % b
try:
    basestring

    def is_string(s):
        return isinstance(s, basestring)
except NameError:
    def is_string(s):
        return isinstance(s, type(''))

###############################################################################
# Public interface
###############################################################################


def boolean_value(variable_value):
    if not variable_value:
        return False
    return not (variable_value is None)


def is_valid_vtl_identifier(text):
    return text and text[0] in set(string.ascii_letters + '_')


class Template:
    def __init__(self, content, filename="<string>"):
        self.content = content
        self.filename = filename
        self.root_element = None

    def merge(self, namespace, loader=None):
        output = StoppableStream()
        self.merge_to(namespace, output, loader)
        return output.getvalue()

    def ensure_compiled(self):
        if not self.root_element:
            self.root_element = TemplateBody(self.filename, self.content)

    def merge_to(self, namespace, fileobj, loader=None):
        if loader is None:
            loader = NullLoader()
        self.ensure_compiled()
        self.root_element.evaluate(fileobj, namespace, loader)


class TemplateError(Exception):
    pass


class TemplateExecutionError(TemplateError):
    def __init__(self, element, exc_info):
        cause, value, traceback = exc_info
        self.__cause__ = value
        self.element = element
        self.start, self.end, self.filename = (element.start, element.end,
                                               element.filename)
        self.msg = "Error in template '%s' at position " \
                   "%d-%d in expression: %s\n%s: %s" % \
                   (self.filename, self.start, self.end,
                    element.my_text(), cause.__name__, value)

    def __str__(self):
        return self.msg


class TemplateSyntaxError(TemplateError):
    def __init__(self, element, expected):
        self.element = element
        self.text_understood = element.full_text()[:element.end]
        self.line = 1 + self.text_understood.count('\n')
        self.column = len(
            self.text_understood) - self.text_understood.rfind('\n')
        got = element.next_text()
        if len(got) > 40:
            got = got[:36] + ' ...'
        Exception.__init__(
            self, "line %d, column %d: expected %s in %s, got: %s ..." %
            (self.line, self.column, expected, self.element_name(), got))

    def get_position_strings(self):
        error_line_start = 1 + self.text_understood.rfind('\n')
        if '\n' in self.element.next_text():
            error_line_end = self.element.next_text().find(
                '\n') + self.element.end
        else:
            error_line_end = len(self.element.full_text())
        error_line = self.element.full_text()[error_line_start:error_line_end]
        caret_pos = self.column
        return [error_line, ' ' * (caret_pos - 1) + '^']

    def element_name(self):
        return re.sub(
            '([A-Z])',
            lambda m: ' ' +
                      m.group(1).lower(),
            self.element.__class__.__name__).strip()


class NullLoader:
    def load_text(self, name):
        raise TemplateError("no loader available for '%s'" % name)

    def load_template(self, name):
        raise self.load_text(name)


class CachingFileLoader:
    def __init__(self, basedir, debugging=False):
        self.basedir = basedir
        self.known_templates = {}  # name -> (template, file_mod_time)
        self.debugging = debugging
        if debugging:
            print("creating caching file loader with basedir:", basedir)

    def filename_of(self, name):
        return os.path.join(self.basedir, name)

    def load_text(self, name):
        if self.debugging:
            print("Loading text from", self.basedir, name)
        f = open(self.filename_of(name))
        try:
            return f.read()
        finally:
            f.close()

    def load_template(self, name):
        if self.debugging:
            print("Loading template...", name,)
        mtime = os.path.getmtime(self.filename_of(name))
        if name in self.known_templates:
            template, prev_mtime = self.known_templates[name]
            if mtime <= prev_mtime:
                if self.debugging:
                    print("loading parsed template from cache")
                return template
        if self.debugging:
            print("loading text from disk")
        template = Template(self.load_text(name), filename=name)
        template.ensure_compiled()
        self.known_templates[name] = (template, mtime)
        return template


class StoppableStream(six.StringIO):
    def __init__(self, buf=''):
        self.stop = False
        six.StringIO.__init__(self, buf)

    def write(self, s):
        if not self.stop:
            six.StringIO.write(self, s)


###############################################################################
# Internals
###############################################################################

WHITESPACE_TO_END_OF_LINE = re.compile(r'[ \t\r]*\n(.*)', re.S)


class NoMatch(Exception):
    pass


class LocalNamespace(dict):
    def __init__(self, parent):
        dict.__init__(self)
        self.parent = parent

    def __getitem__(self, key):
        try:
            return dict.__getitem__(self, key)
        except KeyError:
            return self.parent[key]

    def find_outermost(self, key):
        try:
            dict.__getitem__(self, key)
            return self
        except KeyError:
            if isinstance(self.parent, LocalNamespace):
                return self.parent.find_outermost(key)
            else:
                return None

    def set_inherited(self, key, value):
        ns = self.find_outermost(key)
        if ns is None:
            ns = self
        ns[key] = value

    def top(self):
        if hasattr(self.parent, "top"):
            return self.parent.top()
        return self.parent

    def __repr__(self):
        return dict.__repr__(self) + '->' + repr(self.parent)


class _Element:
    def __init__(self, filename, text, start=0):
        self.filename = filename
        self._full_text = text
        self.start = self.end = start
        self.parse()

    def next_text(self):
        return self._full_text[self.end:]

    def my_text(self):
        return self._full_text[self.start:self.end]

    def full_text(self):
        return self._full_text

    def syntax_error(self, expected):
        return TemplateSyntaxError(self, expected)

    def identity_match(self, pattern):
        m = pattern.match(self._full_text, self.end)
        if not m:
            raise NoMatch()
        self.end = m.start(pattern.groups)
        return m.groups()[:-1]

    def next_match(self, pattern):
        m = pattern.match(self._full_text, self.end)
        if not m:
            return False
        self.end = m.start(pattern.groups)
        return m.groups()[:-1]

    def optional_match(self, pattern):
        m = pattern.match(self._full_text, self.end)
        if not m:
            return False
        self.end = m.start(pattern.groups)
        return True

    def require_match(self, pattern, expected):
        m = pattern.match(self._full_text, self.end)
        if not m:
            raise self.syntax_error(expected)
        self.end = m.start(pattern.groups)
        return m.groups()[:-1]

    def next_element(self, element_spec):
        if callable(element_spec):
            element = element_spec(self.filename, self._full_text, self.end)
            self.end = element.end
            return element
        else:
            for element_class in element_spec:
                try:
                    element = element_class(self.filename, self._full_text,
                                            self.end)
                except NoMatch:
                    pass
                else:
                    self.end = element.end
                    return element
            raise NoMatch()

    def require_next_element(self, element_spec, expected):
        if callable(element_spec):
            try:
                element = element_spec(self.filename, self._full_text,
                                       self.end)
            except NoMatch:
                raise self.syntax_error(expected)
            else:
                self.end = element.end
                return element
        else:
            for element_class in element_spec:
                try:
                    element = element_class(self.filename, self._full_text,
                                            self.end)
                except NoMatch:
                    pass
                else:
                    self.end = element.end
                    return element
            expected = ', '.join([cls.__name__ for cls in element_spec])
            raise self.syntax_error('one of: ' + expected)

    def evaluate(self, *args):
        try:
            return self.evaluate_raw(*args)
        except TemplateExecutionError:
            raise
        except:
            exc_info = sys.exc_info()
            six.reraise(TemplateExecutionError,
                        TemplateExecutionError(self, exc_info), exc_info[2])


class Text(_Element):
    PLAIN = re.compile(
        r'((?:[^\\\$#]+|\\[\$#])+|\$[^!\{a-z0-9_]|\$$|#$'
        r'|#[^\{\}a-zA-Z0-9#\*]+|\\.)(.*)$',
        re.S +
        re.I)
    ESCAPED_CHAR = re.compile(r'\\([\$#]\S+)')

    def parse(self):
        text, = self.identity_match(self.PLAIN)

        def unescape(match):
            return match.group(1)

        self.text = self.ESCAPED_CHAR.sub(unescape, text)

    def evaluate_raw(self, stream, namespace, loader):
        stream.write(self.text)


class FallthroughHashText(_Element):
    """ Plain text starting with a # but which didn't match an earlier
    directive or macro.  The canonical example is an HTML color spec.
    Note that it MUST NOT match block-ending directives.
    """
    # because of earlier elements, this will always start with a hash
    PLAIN = re.compile(r'(\#(?!end|else|elseif|\{(?:end|else|elseif)\}))(.*)$',
                       re.S)

    def parse(self):
        self.text, = self.identity_match(self.PLAIN)

    def evaluate_raw(self, stream, namespace, loader):
        stream.write(self.text)


class IntegerLiteral(_Element):
    INTEGER = re.compile(r'(-?\d+)(.*)', re.S)

    def parse(self):
        self.value, = self.identity_match(self.INTEGER)
        self.value = int(self.value)

    def calculate(self, namespace, loader):
        return self.value


class FloatingPointLiteral(_Element):
    FLOAT = re.compile(r'(-?\d+\.\d+)(.*)', re.S)

    def parse(self):
        self.value, = self.identity_match(self.FLOAT)
        self.value = float(self.value)

    def calculate(self, namespace, loader):
        return self.value


class BooleanLiteral(_Element):
    BOOLEAN = re.compile(r'((?:true)|(?:false))(.*)', re.S | re.I)

    def parse(self):
        self.value, = self.identity_match(self.BOOLEAN)
        self.value = self.value.lower() == 'true'

    def calculate(self, namespace, loader):
        return self.value


class StringLiteral(_Element):
    STRING = re.compile(r"'((?:\\['nrbt\\\\\\$]|[^'\\])*)'(.*)", re.S)
    ESCAPED_CHAR = re.compile(r"\\([nrbt'\\])")

    def parse(self):
        value, = self.identity_match(self.STRING)

        def unescape(match):
            return {
                'n': '\n',
                'r': '\r',
                'b': '\b',
                't': '\t',
                '"': '"',
                '\\': '\\',
                "'": "'"}.get(
                match.group(1),
                '\\' +
                match.group(1))

        self.value = self.ESCAPED_CHAR.sub(unescape, value)

    def calculate(self, namespace, loader):
        return self.value


class InterpolatedStringLiteral(StringLiteral):
    STRING = re.compile(r'"((?:\\["nrbt\\\\\\$]|[^"\\])*)"(.*)', re.S)
    ESCAPED_CHAR = re.compile(r'\\([nrbt"\\])')

    def parse(self):
        StringLiteral.parse(self)
        self.block = Block(self.filename, self.value, 0)

    def calculate(self, namespace, loader):
        output = StoppableStream()
        self.block.evaluate(output, namespace, loader)
        return output.getvalue()


class Range(_Element):
    MIDDLE = re.compile(r'([ \t]*\.\.[ \t]*)(.*)$', re.S)

    def parse(self):
        self.value1 = self.next_element((FormalReference, IntegerLiteral))
        self.identity_match(self.MIDDLE)
        self.value2 = self.next_element((FormalReference, IntegerLiteral))

    def calculate(self, namespace, loader):
        value1 = self.value1.calculate(namespace, loader)
        value2 = self.value2.calculate(namespace, loader)
        if value2 < value1:
            return range(value1, value2 - 1, -1)
        return range(value1, value2 + 1)


class ValueList(_Element):
    COMMA = re.compile(r'\s*,\s*(.*)$', re.S)

    def parse(self):
        self.values = []
        try:
            value = self.next_element(Value)
        except NoMatch:
            pass
        else:
            self.values.append(value)
            while self.optional_match(self.COMMA):
                value = self.require_next_element(Value, 'value')
                self.values.append(value)

    def calculate(self, namespace, loader):
        return [value.calculate(namespace, loader) for value in self.values]


class _EmptyValues:
    def calculate(self, namespace, loader):
        return []


class ArrayLiteral(_Element):
    START = re.compile(r'\[[ \t]*(.*)$', re.S)
    END = re.compile(r'[ \t]*\](.*)$', re.S)
    values = _EmptyValues()

    def parse(self):
        self.identity_match(self.START)
        try:
            self.values = self.next_element((Range, ValueList))
        except NoMatch:
            pass
        self.require_match(self.END, ']')
        self.calculate = self.values.calculate


class DictionaryLiteral(_Element):
    START = re.compile(r'{[ \t]*(.*)$', re.S)
    END = re.compile(r'[ \t]*}(.*)$', re.S)
    KEYVALSEP = re.compile(r'[ \t]*:[ \t]*(.*)$', re.S)
    PAIRSEP = re.compile(r'[ \t]*,[ \t]*(.*)$', re.S)

    def parse(self):
        self.identity_match(self.START)
        self.local_data = {}
        if self.optional_match(self.END):
            # it's an empty dictionary
            return
        while (True):
            key = self.next_element(Value)
            self.require_match(self.KEYVALSEP, ':')
            value = self.next_element(Value)
            self.local_data[key] = value
            if not self.optional_match(self.PAIRSEP):
                break
        self.require_match(self.END, '}')

    # Note that this delays calculation of values until it's used.
    # TODO confirm that that's correct.
    def calculate(self, namespace, loader):
        tmp = {}
        for (key, val) in self.local_data.items():
            tmp[key.calculate(namespace, loader)] = val.calculate(
                namespace, loader)
        return tmp


class Value(_Element):
    def parse(self):
        self.expression = self.next_element(
            (FormalReference,
             FloatingPointLiteral,
             IntegerLiteral,
             StringLiteral,
             InterpolatedStringLiteral,
             ArrayLiteral,
             DictionaryLiteral,
             ParenthesizedExpression,
             UnaryOperatorValue,
             BooleanLiteral))

    def calculate(self, namespace, loader):
        return self.expression.calculate(namespace, loader)


class NameOrCall(_Element):
    NAME = re.compile(r'([a-zA-Z0-9_]+)(.*)$', re.S)
    parameters = None
    index = None

    def parse(self):
        self.name, = self.identity_match(self.NAME)
        if not is_valid_vtl_identifier(self.name):
            raise NoMatch('Invalid VTL identifier %s.' % self.name)
        try:
            self.parameters = self.next_element(ParameterList)
        except NoMatch:
            try:
                self.index = self.next_element(ArrayIndex)
            except NoMatch:
                pass

    def calculate(self, current_object, loader, top_namespace):
        result = None
        try:
            result = current_object[self.name]
        except (KeyError, TypeError, AttributeError):
            pass
        if result is None and not isinstance(current_object, LocalNamespace):
            try:
                result = getattr(current_object, self.name)
            except AttributeError:
                pass
        if result is None:
            methods_for_type = __additional_methods__.get(current_object.__class__)
            if methods_for_type and self.name in methods_for_type:
                result = lambda *args: methods_for_type[self.name](current_object, *args)
        if result is None:
            return None  # TODO: an explicit 'not found' exception?
        if isinstance(result, _FunctionDefinition):
            params = self.parameters and self.parameters.calculate(top_namespace, loader) or []
            stream = StoppableStream()
            result.execute_function(stream, top_namespace, params, loader)
            return stream.getvalue()
        if self.parameters is not None:
            result = result(*self.parameters.calculate(top_namespace, loader))
        elif self.index is not None:
            array_index = self.index.calculate(top_namespace, loader)
            # If list make sure index is an integer
            if isinstance(
                    result, list) and not isinstance(
                    array_index, six.integer_types):
                raise ValueError(
                    "expected integer for array index, got '%s'" %
                    (array_index))
            try:
                result = result[array_index]
            except:
                result = None
        return result


class SubExpression(_Element):
    DOT = re.compile(r'\.(.*)', re.S)

    def parse(self):
        try:
            self.identity_match(self.DOT)
            self.expression = self.next_element(VariableExpression)
        except NoMatch:
            self.expression = self.next_element(ArrayIndex)
            self.subexpression = None
            try:
                self.subexpression = self.next_element(SubExpression)
            except NoMatch:
                pass

    def calculate(self, current_object, loader, global_namespace):
        args = [current_object, loader]
        if not isinstance(self.expression, ArrayIndex):
            return self.expression.calculate(*(args + [global_namespace]))
        index = self.expression.calculate(*args)
        result = current_object[index]
        if self.subexpression:
            result = self.subexpression.calculate(result, loader, global_namespace)
        return result


class VariableExpression(_Element):
    subexpression = None

    def parse(self):
        self.part = self.next_element(NameOrCall)
        try:
            self.subexpression = self.next_element(SubExpression)
        except NoMatch:
            pass

    def calculate(self, namespace, loader, global_namespace=None):
        if global_namespace is None:
            global_namespace = namespace
        value = self.part.calculate(namespace, loader, global_namespace)
        if self.subexpression:
            value = self.subexpression.calculate(
                value,
                loader,
                global_namespace)
        return value


class ParameterList(_Element):
    START = re.compile(r'\(\s*(.*)$', re.S)
    COMMA = re.compile(r'\s*,\s*(.*)$', re.S)
    END = re.compile(r'\s*\)(.*)$', re.S)
    values = _EmptyValues()

    def parse(self):
        self.identity_match(self.START)
        try:
            self.values = self.next_element(ValueList)
        except NoMatch:
            pass
        self.require_match(self.END, ')')

    def calculate(self, namespace, loader):
        return self.values.calculate(namespace, loader)


class ArrayIndex(_Element):
    START = re.compile(r'\[[ \t]*(.*)$', re.S)
    END = re.compile(r'[ \t]*\](.*)$', re.S)
    index = 0

    def parse(self):
        self.identity_match(self.START)
        self.index = self.require_next_element(
            (FormalReference,
             IntegerLiteral,
             InterpolatedStringLiteral,
             ParenthesizedExpression),
            'integer index or object key')
        self.require_match(self.END, ']')

    def calculate(self, namespace, loader):
        result = self.index.calculate(namespace, loader)
        return result

class AlternateValue(_Element):
    START = re.compile(r'\|(.*)$', re.S)

    def parse(self):
        self.identity_match(self.START)
        self.expression = self.require_next_element(Value, 'expression')
        self.calculate = self.expression.calculate


class FormalReference(_Element):
    START = re.compile(r'\$(!?)(\{?)(.*)$', re.S)
    CLOSING_BRACE = re.compile(r'\}(.*)$', re.S)

    def parse(self):
        self.silent, braces = self.identity_match(self.START)
        try:
            self.expression = self.next_element(VariableExpression)
            self.calculate = self.expression.calculate
        except NoMatch:
            self.expression = None
            self.calculate = None
        self.alternate = None
        if braces:
          try:
              self.alternate = self.next_element(AlternateValue)
          except NoMatch:
              pass
          self.require_match(self.CLOSING_BRACE, '}')

    def evaluate_raw(self, stream, namespace, loader):
        value = None
        if self.expression is not None:
            value = self.expression.calculate(namespace, loader)
        if value is None:
            if self.alternate is not None:
                value = self.alternate.calculate(namespace, loader)
            elif self.silent and self.expression is not None:
                value = ''
            else:
                value = self.my_text()
        if is_string(value):
            stream.write(value)
        else:
            stream.write(six.text_type(value))


class Null:
    def evaluate(self, stream, namespace, loader):
        pass


class Comment(_Element, Null):
    COMMENT = re.compile(
        '#(?:#.*?(?:\n|$)|\\*.*?\\*#(?:[ \t]*\n)?)(.*)$',
        re.M +
        re.S)

    def parse(self):
        self.identity_match(self.COMMENT)

    def evaluate(self, *args):
        pass


class BinaryOperator(_Element):
    BINARY_OP = re.compile(
        r'\s*(>=|<=|<|==|!=|>|%|\|\||&&|or|and|\+|\-|\*|\/|\%|gt|lt|ne|eq|ge'
        r'|le|not)\s*(.*)$',
        re.S)
    OPERATORS = {'>': operator.gt, 'gt': operator.gt,
                 '>=': operator.ge, 'ge': operator.ge,
                 '<': operator.lt, 'lt': operator.lt,
                 '<=': operator.le, 'le': operator.le,
                 '==': operator.eq, 'eq': operator.eq,
                 '!=': operator.ne, 'ne': operator.ne,
                 '%': operator.mod,
                 '||': lambda a, b: boolean_value(a) or boolean_value(b),
                 '&&': lambda a, b: boolean_value(a) and boolean_value(b),
                 'or': lambda a, b: boolean_value(a) or boolean_value(b),
                 'and': lambda a, b: boolean_value(a) and boolean_value(b),
                 '+': operator.add,
                 '-': operator.sub,
                 '*': operator.mul,
                 '/': operator.floordiv}
    # Based on http://introcs.cs.princeton.edu/java/11precedence/
    PRECEDENCE = {'>': 7, '<': 7, '==': 8, '>=': 7, '<=': 7, '!=': 9,
                  '||': 13, '&&': 12, 'or': 13, 'and': 12,
                  '+': 5, '-': 5, '*': 4, '/': 4, '%': 4,
                  'gt': 7, 'lt': 7, 'ne': 9, 'eq': 8, 'ge': 7, 'le': 7,
                  }

    # In velocity, if + is applied to one string and one numeric
    # argument, will convert the number into a string.
    # As far as I can tell, this is undocumented.
    # Note that this applies only to add, not to other operators

    def parse(self):
        op_string, = self.identity_match(self.BINARY_OP)
        self.apply_to = self.OPERATORS[op_string]
        self.precedence = self.PRECEDENCE[op_string]

    # This assumes that the self operator is "to the left"
    # of the argument, and thus gets higher precedence if they're
    # both boolean operators.
    # That is, the way this is used (see Expression.calculate)
    # it should return false if the two ops have the same precedence
    # that is, it's strictly greater than, not greater than or equal to
    # to get proper left-to-right evaluation, it should skew towards false.
    def greater_precedence_than(self, other):
        return self.precedence < other.precedence


class UnaryOperatorValue(_Element):
    UNARY_OP = re.compile(r'\s*(!|(?:not))\s*(.*)$', re.S)
    OPERATORS = {'!': operator.__not__, 'not': operator.__not__}

    def parse(self):
        op_string, = self.identity_match(self.UNARY_OP)
        self.value = self.next_element(Value)
        self.op = self.OPERATORS[op_string]

    def calculate(self, namespace, loader):
        return self.op(self.value.calculate(namespace, loader))


# Note: there appears to be no way to differentiate a variable or
# value from an expression, other than context.
class Expression(_Element):
    def parse(self):
        self.expression = [self.next_element(Value)]
        while (True):
            try:
                binary_operator = self.next_element(BinaryOperator)
                value = self.require_next_element(Value, 'value')
                self.expression.append(binary_operator)
                self.expression.append(value)
            except NoMatch:
                break

    def calculate(self, namespace, loader):
        if not self.expression or len(self.expression) == 0:
            return False
        # TODO: how does velocity deal with an empty condition expression?

        opstack = []
        valuestack = [self.expression[0]]
        terms = self.expression[1:]

        # use top of opstack on top 2 values of valuestack
        def stack_calculate(ops, values, namespace, loader):
            value2 = values.pop()
            if isinstance(value2, Value):
                value2 = value2.calculate(namespace, loader)
            value1 = values.pop()
            if isinstance(value1, Value):
                value1 = value1.calculate(namespace, loader)
            result = ops.pop().apply_to(value1, value2)
            # TODO this doesn't short circuit -- does velocity?
            # also note they're eval'd out of order
            values.append(result)

        while terms:
            # next is a binary operator
            if not opstack or terms[0].greater_precedence_than(opstack[-1]):
                opstack.append(terms[0])
                valuestack.append(terms[1])
                terms = terms[2:]
            else:
                stack_calculate(opstack, valuestack, namespace, loader)

        # now clean out the stacks
        while opstack:
            stack_calculate(opstack, valuestack, namespace, loader)

        if len(valuestack) != 1:
            print ("evaluation of expression in Condition.calculate "
                   "is messed up: final length of stack is not one")
            # TODO handle this officially

        result = valuestack[0]
        if isinstance(result, Value):
            result = result.calculate(namespace, loader)
        return result


class ParenthesizedExpression(_Element):
    START = re.compile(r'\(\s*(.*)$', re.S)
    END = re.compile(r'\s*\)(.*)$', re.S)

    def parse(self):
        self.identity_match(self.START)
        expression = self.next_element(Expression)
        self.require_match(self.END, ')')
        self.calculate = expression.calculate


class Condition(_Element):
    def parse(self):
        expression = self.next_element(ParenthesizedExpression)
        self.optional_match(WHITESPACE_TO_END_OF_LINE)
        self.calculate = expression.calculate
        # TODO do I need to do anything else here?


class End(_Element):
    END = re.compile(r'#(?:end|\{end\})(.*)', re.I + re.S)

    def parse(self):
        self.identity_match(self.END)
        self.optional_match(WHITESPACE_TO_END_OF_LINE)


class ElseBlock(_Element):
    START = re.compile(r'#(?:else|\{else\})(.*)$', re.S + re.I)

    def parse(self):
        self.identity_match(self.START)
        self.block = self.require_next_element(Block, 'block')
        self.evaluate = self.block.evaluate


class ElseifBlock(_Element):
    START = re.compile(r'#elseif\b\s*(.*)$', re.S + re.I)

    def parse(self):
        self.identity_match(self.START)
        self.condition = self.require_next_element(Condition, 'condition')
        self.block = self.require_next_element(Block, 'block')
        self.calculate = self.condition.calculate
        self.evaluate = self.block.evaluate


class IfDirective(_Element):
    START = re.compile(r'#if\b\s*(.*)$', re.S + re.I)
    else_block = Null()

    def parse(self):
        self.identity_match(self.START)
        self.condition = self.next_element(Condition)
        self.block = self.require_next_element(Block, "block")
        self.elseifs = []
        while True:
            try:
                self.elseifs.append(self.next_element(ElseifBlock))
            except NoMatch:
                break
        try:
            self.else_block = self.next_element(ElseBlock)
        except NoMatch:
            pass
        self.require_next_element(End, '#else, #elseif or #end')

    def evaluate_raw(self, stream, namespace, loader):
        if self.condition.calculate(namespace, loader):
            self.block.evaluate(stream, namespace, loader)
        else:
            for elseif in self.elseifs:
                if elseif.calculate(namespace, loader):
                    elseif.evaluate(stream, namespace, loader)
                    return
            self.else_block.evaluate(stream, namespace, loader)


# This can't deal with assignments like
# set($one.two().three = something)
# yet
class Assignment(_Element):
    START = re.compile(
        r'\s*\(\s*\$([a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*)\s*=\s*(.*)$',
        re.S +
        re.I)
    END = re.compile(r'\s*\)(?:[ \t]*\r?\n)?(.*)$', re.S + re.M)

    def parse(self):
        var_name, = self.identity_match(self.START)
        self.terms = var_name.split('.')
        self.value = self.require_next_element(Expression, "expression")
        self.require_match(self.END, ')')

    def evaluate_raw(self, stream, namespace, loader):
        val = self.value.calculate(namespace, loader)
        if len(self.terms) == 1:
            namespace.set_inherited(self.terms[0], val)
        else:
            cur = namespace
            for term in self.terms[:-1]:
                cur = cur[term]
            cur[self.terms[-1]] = val

class EvaluateDirective(_Element):
    START = re.compile(r'#evaluate\b(.*)')
    OPEN_PAREN = re.compile(r'[ \t]*\(\s*(.*)$', re.S)
    CLOSE_PAREN = re.compile(r'[ \t]*\)(.*)$', re.S)

    def parse(self):
        self.identity_match(self.START)
        self.require_match(self.OPEN_PAREN, '(')
        self.value = self.require_next_element(Value, 'value')
        self.require_match(self.CLOSE_PAREN, ')')

    def evaluate_raw(self, stream, namespace, loader):
        val = self.value.calculate(namespace, loader)
        Template(val, "#evaluate").merge_to(namespace, stream, loader)



class _FunctionDefinition(_Element):
    # Must be overridden to provide START and NAME patterns
    OPEN_PAREN = re.compile(r'[ \t]*\(\s*(.*)$', re.S)
    CLOSE_PAREN = re.compile(r'[ \t]*\)(.*)$', re.S)
    ARG_NAME = re.compile(r'[, \t]+\$([a-z][a-z_0-9]*)(.*)$', re.S + re.I)
    RESERVED_NAMES = []

    def parse(self):
        self.identity_match(self.START)
        self.require_match(self.OPEN_PAREN, '(')
        self.function_name, = self.require_match(self.NAME, 'function name')
        if self.function_name.lower() in self.RESERVED_NAMES:
            raise self.syntax_error('non-reserved name')
        self.arg_names = []
        while True:
            m = self.next_match(self.ARG_NAME)
            if not m:
                break
            self.arg_names.append(m[0])
        self.require_match(self.CLOSE_PAREN, ') or arg name')
        self.optional_match(WHITESPACE_TO_END_OF_LINE)
        self.block = self.require_next_element(Block, 'block')
        self.require_next_element(End, 'block')

    def execute_function(self, stream, namespace, arg_values, loader):
        if len(arg_values) != len(self.arg_names):
            raise Exception(
                "function %s expected %d arguments, got %d" %
                (self.function_name, len(self.arg_names), len(arg_values)))
        local_namespace = LocalNamespace(namespace)
        local_namespace.update(zip(self.arg_names, arg_values))
        self.block.evaluate(stream, local_namespace, loader)

class MacroDefinition(_FunctionDefinition):
    START = re.compile(r'#macro\b(.*)', re.S + re.I)
    NAME = re.compile(r'\s*([a-z][a-z_0-9]*)\b(.*)', re.S + re.I)
    RESERVED_NAMES = (
        'if',
        'else',
        'elseif',
        'set',
        'macro',
        'foreach',
        'parse',
        'include',
        'stop',
        'end',
        'define')

    def evaluate_raw(self, stream, namespace, loader):
        global_ns = namespace.top()
        macro_key = '#' + self.function_name.lower()
        if macro_key in global_ns:
            raise Exception("cannot redefine macro {0}".format(macro_key))

        global_ns[macro_key] = self

class MacroCall(_Element):
    START = re.compile(r'#([a-z][a-z_0-9]*)\b(.*)', re.S + re.I)
    OPEN_PAREN = re.compile(r'[ \t]*\(\s*(.*)$', re.S)
    CLOSE_PAREN = re.compile(r'[ \t]*\)(.*)$', re.S)
    SPACE_OR_COMMA = re.compile(r'\s*(?:,|\s)\s*(.*)$', re.S)

    def parse(self):
        macro_name, = self.identity_match(self.START)
        self.macro_name = macro_name.lower()
        self.args = []
        if self.macro_name in MacroDefinition.RESERVED_NAMES:
            raise NoMatch()
        if not self.optional_match(self.OPEN_PAREN):
            raise NoMatch() # Typically a hex colour literal
        while True:
            try:
                self.args.append(self.next_element(Value))
            except NoMatch:
                break
            if not self.optional_match(self.SPACE_OR_COMMA):
                break
        self.require_match(self.CLOSE_PAREN, 'argument value or )')

    def evaluate_raw(self, stream, namespace, loader):
        try:
            macro = namespace['#' + self.macro_name]
        except KeyError:
            raise Exception('no such macro: ' + self.macro_name)
        arg_values = [arg.calculate(namespace, loader) for arg in self.args]
        macro.execute_function(stream, namespace, arg_values, loader)

class DefineDefinition(_FunctionDefinition):
    START = re.compile(r'#define\b(.*)', re.S + re.I)
    NAME = re.compile(r'\s*\$([a-z][a-z_0-9]*)\b(.*)', re.S + re.I)

    def evaluate_raw(self, stream, namespace, loader):
        namespace[self.function_name] = self

class IncludeDirective(_Element):
    START = re.compile(r'#include\b(.*)', re.S + re.I)
    OPEN_PAREN = re.compile(r'[ \t]*\(\s*(.*)$', re.S)
    CLOSE_PAREN = re.compile(r'[ \t]*\)(.*)$', re.S)

    def parse(self):
        self.identity_match(self.START)
        self.require_match(self.OPEN_PAREN, '(')
        self.name = self.require_next_element(
            (StringLiteral,
             InterpolatedStringLiteral,
             FormalReference),
            'template name')
        self.require_match(self.CLOSE_PAREN, ')')

    def evaluate_raw(self, stream, namespace, loader):
        stream.write(loader.load_text(self.name.calculate(namespace, loader)))


class ParseDirective(_Element):
    START = re.compile(r'#parse\b(.*)', re.S + re.I)
    OPEN_PAREN = re.compile(r'[ \t]*\(\s*(.*)$', re.S)
    CLOSE_PAREN = re.compile(r'[ \t]*\)(.*)$', re.S)

    def parse(self):
        self.identity_match(self.START)
        self.require_match(self.OPEN_PAREN, '(')
        self.name = self.require_next_element(
            (StringLiteral,
             InterpolatedStringLiteral,
             FormalReference),
            'template name')
        self.require_match(self.CLOSE_PAREN, ')')

    def evaluate_raw(self, stream, namespace, loader):
        template = loader.load_template(self.name.calculate(namespace, loader))
        # TODO: local namespace?
        template.merge_to(namespace, stream, loader=loader)


class StopDirective(_Element):
    STOP = re.compile(r'#stop\b(.*)', re.S + re.I)

    def parse(self):
        self.identity_match(self.STOP)

    def evaluate_raw(self, stream, namespace, loader):
        if hasattr(stream, 'stop'):
            stream.stop = True


# Represents a SINGLE user-defined directive
class UserDefinedDirective(_Element):
    DIRECTIVES = []

    def parse(self):
        self.directive = self.next_element(self.DIRECTIVES)

    def evaluate_raw(self, stream, namespace, loader):
        self.directive.evaluate(stream, namespace, loader)


class SetDirective(_Element):
    START = re.compile(r'#set\b(.*)', re.S + re.I)

    def parse(self):
        self.identity_match(self.START)
        self.assignment = self.require_next_element(Assignment, 'assignment')

    def evaluate_raw(self, stream, namespace, loader):
        self.assignment.evaluate(stream, namespace, loader)


class ForeachDirective(_Element):
    START = re.compile(r'#foreach\b(.*)$', re.S + re.I)
    OPEN_PAREN = re.compile(r'[ \t]*\(\s*(.*)$', re.S)
    IN = re.compile(r'[ \t]+in[ \t]+(.*)$', re.S)
    LOOP_VAR_NAME = re.compile(r'\$([a-z_][a-z0-9_]*)(.*)$', re.S + re.I)
    CLOSE_PAREN = re.compile(r'[ \t]*\)(.*)$', re.S)

    def parse(self):
        # Could be cleaner b/c syntax error if no '('
        self.identity_match(self.START)
        self.require_match(self.OPEN_PAREN, '(')
        self.loop_var_name, = self.require_match(
            self.LOOP_VAR_NAME, 'loop var name')
        self.require_match(self.IN, 'in')
        self.value = self.next_element(Value)
        self.require_match(self.CLOSE_PAREN, ')')
        self.block = self.next_element(Block)
        self.require_next_element(End, '#end')

    def evaluate_raw(self, stream, namespace, loader):
        iterable = self.value.calculate(namespace, loader)
        counter = 1
        try:
            if iterable is None:
                return
            if hasattr(iterable, 'keys'):
                iterable = iterable.keys()
            try:
                iter(iterable)
            except TypeError:
                raise ValueError(
                    "value for $%s is not iterable in #foreach: %s" %
                    (self.loop_var_name, iterable))
            length = len(iterable)
            for item in iterable:
                localns = LocalNamespace(namespace)
                localns['velocityCount'] = counter
                localns['velocityHasNext'] = counter < length
                localns['foreach'] = {
                    "count": counter,
                    "index": counter - 1,
                    "hasNext": counter < length,
                    "first": counter == 1,
                    "last": counter == length}
                localns[self.loop_var_name] = item
                self.block.evaluate(stream, localns, loader)
                counter += 1
        except TypeError:
            raise


class TemplateBody(_Element):
    def parse(self):
        self.block = self.next_element(Block)
        if self.next_text():
            raise self.syntax_error('block element')

    def evaluate_raw(self, stream, namespace, loader):
        # Use the same namespace as the parent template, if sub-template
        if not isinstance(namespace, LocalNamespace):
            namespace = LocalNamespace(namespace)
        self.block.evaluate(stream, namespace, loader)


class Block(_Element):
    def parse(self):
        self.children = []
        while True:
            try:
                self.children.append(
                    self.next_element(
                        (Text,
                         FormalReference,
                         Comment,
                         IfDirective,
                         SetDirective,
                         ForeachDirective,
                         IncludeDirective,
                         ParseDirective,
                         MacroDefinition,
                         DefineDefinition,
                         StopDirective,
                         UserDefinedDirective,
                         EvaluateDirective,
                         MacroCall,
                         FallthroughHashText)))
            except NoMatch:
                break

    def evaluate_raw(self, stream, namespace, loader):
        for child in self.children:
            child.evaluate(stream, namespace, loader)
