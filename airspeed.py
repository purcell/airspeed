#!/usr/bin/env python

import re

class SyntaxError(Exception):
    pass


class Tokeniser:
    PLAIN, IF, PLACEHOLDER, END = range(4)

    REST = '(.*)$'    
    UP_TO_NEXT_TEMPLATE_BIT = re.compile('^(.*?)((?:#|\$).*)', re.MULTILINE + re.DOTALL)

    NAME_OR_CALL = '[a-z0-9_]+(?:\(\))?'
    EXPRESSION = '(' + NAME_OR_CALL + '(?:\.' + NAME_OR_CALL + ')*)'
    PLACEHOLDER_PATTERN = re.compile('^\$(!?)({?)' + EXPRESSION + '(}?)' + REST, re.IGNORECASE)
    BEGIN_IF_PATTERN = re.compile('^#if[ \t]*\([ \t]*\$' + EXPRESSION + '[ \t]*\)' + REST, re.IGNORECASE)
    END_PATTERN = re.compile('^#end' + REST, re.IGNORECASE)
    
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
            m = self.END_PATTERN.match(interesting)
            if m:
                yield self.END, None
                (text,) = m.groups()
                continue
            raise SyntaxError("invalid token: %s" % text[:40])
        
    def get_placeholder(self, match):
        silent, open_brace, var_name, close_brace, rest = match.groups()
        if open_brace and not close_brace:
            raise SyntaxError("unmatched braces")
        if close_brace and not open_brace:
            rest = close_brace + rest
            original_text = ''.join(('$', silent, var_name))
        else:
            original_text = ''.join(('$', open_brace, silent, var_name, close_brace))
        return var_name, bool(silent), original_text, rest


class Parser:
    
    def __init__(self):
        self.data = {}
        
    def merge(self, content):
        output = []
        filter_output_at_nesting_level = [False]
        for token_type, token_value in Tokeniser().tokenise(str(content)):
            filter_at_this_level = filter_output_at_nesting_level[-1]
            if token_type == Tokeniser.PLAIN:
                if not filter_at_this_level: output.append(token_value)
                continue
            if token_type == Tokeniser.PLACEHOLDER:
                expression, silent, original_text = token_value
                value = self.find(expression)
                if value is None:
                    if silent: expression_value = ''
                    else: expression_value = original_text
                else:
                    expression_value = str(value)
                if not filter_at_this_level: output.append(expression_value)
                continue
            if token_type == Tokeniser.IF:
                value = self.find(token_value)
                filter_my_content = filter_at_this_level or not bool(value)
                filter_output_at_nesting_level.append(filter_my_content)
                continue
            if token_type == Tokeniser.END:
                if len(filter_output_at_nesting_level) == 1:
                    raise SyntaxError("#end without beginning of block")
                del filter_output_at_nesting_level[-1]
                continue
            raise SyntaxError("invalid token: %s" % text[:40])
                
        if len(filter_output_at_nesting_level) > 1:
            raise SyntaxError("Unclosed block")
        return ''.join(output)
        

    def find(self, expression):
        o = self.data
        for part in expression.split('.'):
            if part.endswith('()'):
                part = part[:-2]
                try: o = getattr(o, part)
                except AttributeError: pass
                else: o = o()
            else:
                try: o = getattr(o, part)
                except AttributeError:
                    try: o = o[part]
                    except KeyError: pass
            if o in (None, self.data): return None
        return o
                
        
    def __setitem__(self, name, value):
        self.data[name] = value


class Template:

    def __init__(self, content):
        self.content = content
        
    def __str__(self):
        return self.content
    

    
        
