# -*- coding: utf-8 -*-
#==============================================================================
# Name:         compiler
# Description:  Python to Javascript compiler
# Copyright:    Hybrid Labs
# Licence:      Private
#==============================================================================

import ast
import inspect
import json


#==============================================================================
# JSCompiler
#==============================================================================

class JSEnv(object):
    def __getitem__(self, item):
        pass

    def alert(self, message):
        pass


class JSCompiler(ast.NodeVisitor):
    BOOL_OP = {
        ast.And: '&&',
        ast.Or: '||',
    }

    BIN_OP = {
        ast.Add: '+',
        ast.Sub: '-',
        ast.Mult: '*',
        ast.Div: '/',
        ast.Mod: '%',
        ast.LShift: '<<',
        ast.RShift: '>>',
        ast.BitOr: '|',
        ast.BitXor: '^',
        ast.BitAnd: '&',
    }

    UNARY_OP = {
        ast.Invert: '~',
        ast.Not: '!',
        ast.UAdd: '+',
        ast.USub: '-',
    }

    COMPARE_OP = {
        ast.Eq: '==',
        ast.NotEq: '!=',
        ast.Lt: '<',
        ast.LtE: '<=',
        ast.Gt: '>',
        ast.GtE: '>=',
        ast.Is: '===',
        ast.IsNot: '!==',
    }

    def __init__(self, obj, name):
        self.obj = obj
        self.name = name

    def generic_visit(self, node):
        raise NotImplementedError(node)

    # Module(stmt* body)
    def visit_Module(self, node):
        template = []
        for child in node.body:
            template.extend(self.visit(child) or [])
        return '\n'.join(template)

    # Return(expr? value)
    def visit_Return(self, node):
        if node.value:
            return 'return {0}'.format(self.visit(node.value))
        else:
            return 'return'

    # FunctionDef(identifier name, arguments args,
    # stmt* body, expr* decorator_list)
    def visit_FunctionDef(self, node):
        if self.name and self.obj.__name__ == node.name:
            node.name = self.name

        context = getattr(node, 'context', 'this')
        args = ', '.join([self.visit(a) for a in node.args.args])
        template = [
            '{0}.{1} = function {1}({2}) {{'.format(
                context, node.name, args)
        ]

        for c in node.body:
            extend(template, indent(self.visit(c)))

        template.append('}')
        return template

    #ClassDef(identifier name, expr* bases, stmt* body, expr* decorator_list)
    def visit_ClassDef(self, node):
        from . import client

        if len(node.bases) > 1:
            raise NotImplementedError('Multiple inheritance not implemented')

        template = []
        context = getattr(node, 'context', 'this')
        is_scope = node.name in client._scopes
        inject = ['$scope'] if is_scope else []
        classname = self.visit(node.bases[0]).split('.')[-1] \
            if is_scope else node.name

        template.append('{0}.{1} = function {2}({3}) {{'.format(
            context, classname, node.name, ', '.join(inject)))

        for c in node.body:
            if is_scope:
                c.context = '$scope'

            extend(template, indent(self.visit(c)))

        template.append('}')
        template.append('{0}.{1}.$inject = {2}'.format(
            context, classname, json.dumps(inject)))

        if not is_scope and node.bases:
            template.append('{0}.{1}.prototype = new {2}()'.format(
                context, node.name, self.visit(node.bases[0])))

        return template

    # Assign(expr* targets, expr value)
    def visit_Assign(self, node):
        def assign(target, value):
            return 'var {0} = {1}'.format(target, value)

        template = []
        for target in node.targets:
            if type(target) is ast.Tuple:
                stmt = 'var _assign = {0}'.format(self.visit(node.value))
                template.append(stmt)

                for i, t in enumerate(target.elts):
                    v = '_assign[{0}]'.format(i)
                    template.append(assign(self.visit(t), v))
            else:
                stmt = assign(self.visit(target), self.visit(node.value))
                template.append(stmt)

        return template

    # Print(expr? dest, expr* values, bool nl)
    def visit_Print(self, node):
        return 'console.log({0})'.format(
            ', '.join([self.visit(v) for v in node.values]))

    # TryExcept(stmt* body, excepthandler* handlers, stmt* orelse)
    def visit_TryExcept(self, node):
        template = ['try {']

        for c in node.body:
            extend(template, indent(self.visit(c)))

        template.append('} catch(__exception__) {')

        for c in node.handlers:
            extend(template, indent(self.visit(c)))

        template.append('}')
        return template

    # Try(stmt* body, excepthandler* handlers, stmt* orelse, stmt* finalbody)
    def visit_Try(self, node):
        return self.visit_TryExcept(node)

    # Expr(expr value)
    def visit_Expr(self, node):
        return self.visit(node.value)

    # Pass
    def visit_Pass(self, node):
        return ['// pass']

    # BinOp(expr left, operator op, expr right)
    def visit_BinOp(self, node):
        left = self.visit(node.left)
        op = JSCompiler.BIN_OP[type(node.op)]
        right = self.visit(node.right)
        return '{0} {1} {2}'.format(left, op, right)

    # UnaryOp(unaryop op, expr operand)
    def visit_UnaryOp(self, node):
        op = JSCompiler.UNARY_OP[type(node.op)]
        operand = self.visit(node.operand)
        return '{0}({1})'.format(op, operand)

    # Call(expr func, expr* args, keyword* keywords,
    # xpr? starargs, expr? kwargs)
    def visit_Call(self, node):
        func = self.visit(node.func)

        if func == 'print':
            node.values = node.args
            return self.visit_Print(node)

        args = ', '.join([self.visit(a) for a in node.args])
        return '{0}({1})'.format(func, args)

    # Num(object n)
    def visit_Num(self, node):
        return str(node.n)

    # Str(string s)
    def visit_Str(self, node):
        return '"{0}"'.format(node.s).replace('\n', '\\n\\\n')

    # Attribute(expr value, identifier attr, expr_context ctx)
    def visit_Attribute(self, node):
        value = self.visit(node.value)
        return '{0}.{1}'.format(value, node.attr)

    # Subscript(expr value, slice slice, expr_context ctx)
    def visit_Subscript(self, node):
        value = self.visit(node.value)
        index = self.visit(node.slice)
        return '{0}[{1}]'.format(value, index)

    # Name(identifier id, expr_context ctx)
    def visit_Name(self, node):
        if node.id == 'None':
            return 'undefined'
        elif node.id == 'True':
            return 'true'
        elif node.id == 'False':
            return 'false'
        return str(node.id)

    # List(expr* elts, expr_context ctx)
    def visit_List(self, node):
        return str([self.visit(c) for c in node.elts])

    # Tuple(expr* elts, expr_context ctx)
    def visit_Tuple(self, node):
        return '[{0}]'.format(', '.join([self.visit(c) for c in node.elts]))

    # Index(expr value)
    def visit_Index(self, node):
        return self.visit(node.value)

    # ExceptHandler(expr? type, identifier? name, stmt* body)
    def visit_ExceptHandler(self, node):
        template = []
        if node.type:
            template.append('if (__exception__.type == {0}'.format(node.type))
        else:
            template.append('if (__exception__) {')

        for c in node.body:
            extend(template, indent(self.visit(c)))

        template.append(indent('__exception__ = undefined'))
        template.append('}')

        return template

    # arg = (identifier arg, expr? annotation)
    def visit_arg(self, node):
        return str(node.arg)


#==============================================================================
# Helpers
#==============================================================================

def indent(lines, spaces=2, level=1):
    spaces = ' ' * (spaces * level)
    if isinstance(lines, list):
        return  ['{0}{1}'.format(spaces, l) for l in lines]
    else:
        return '{0}{1}'.format(spaces, lines)


def extend(template, lines):
    if isinstance(lines, list):
        template.extend(lines)
    else:
        template.append(lines)
    return template


def jscompile(obj, name=None):
    if not getattr(obj, '__js__', None):
        node = ast.parse(inspect.getsource(obj))
        obj.__js__ = JSCompiler(obj, name).visit(node)
    return obj.__js__
