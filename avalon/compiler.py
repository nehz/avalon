# -*- coding: utf-8 -*-
#==============================================================================
# Name:         compiler
# Description:  Python to Javascript compiler
# Copyright:    Hybrid Labs
# Licence:      Private
#==============================================================================

import ast
import inspect
import sys


#==============================================================================
# JSCompiler
#==============================================================================

class JSEnv(object):
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
        self.module = sys.modules[obj.__module__]

    def generic_visit(self, node):
        raise NotImplementedError(node)

    def visit_Module(self, node):
        module = []
        for child in node.body:
            module.extend(self.visit(child) or [])
        return '\n'.join(module)

    def visit_Expr(self, node):
        return self.visit(node.value)

    def visit_FunctionDef(self, node):
        if self.obj.__name__ == node.name:
            node.name = self.name

        args = ', '.join([self.visit(a) for a in node.args.args])
        template = ['function {0}({1}) {{'.format(node.name, args)]

        for c in node.body:
            c = indent(self.visit(c))

            if isinstance(c, list):
                template.extend(c)
            else:
                template.append(c)

        template.append('}')
        return template

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

    def visit_Pass(self, node):
        return ['// pass']

    def visit_BinOp(self, node):
        left = self.visit(node.left)
        op = JSCompiler.BIN_OP[type(node.op)]
        right = self.visit(node.right)
        return '{0} {1} {2}'.format(left, op, right)

    def visit_UnaryOp(self, node):
        op = JSCompiler.UNARY_OP[type(node.op)]
        operand = self.visit(node.operand)
        return '{0}({1})'.format(op, operand)

    def visit_Call(self, node):
        args = ', '.join([self.visit(a) for a in node.args])
        func = self.visit(node.func)
        return '{0}({1})'.format(func, args)

    def visit_Num(self, node):
        return str(node.n)

    def visit_Str(self, node):
        return '"{0}"'.format(node.s)

    def visit_Attribute(self, node):
        value = self.visit(node.value)
        if issubclass(getattr(self.module, value, None), JSEnv):
            return node.attr
        else:
            return '{0}.{1}'.format(value, node.attr)

    def visit_Subscript(self, node):
        value = self.visit(node.value)
        index = self.visit(node.slice)
        return '{0}[{1}]'.format(value, index)

    def visit_Name(self, node):
        return str(node.id)

    def visit_List(self, node):
        return str([self.visit(c) for c in node.elts])

    def visit_Tuple(self, node):
        return '[{0}]'.format(', '.join([self.visit(c) for c in node.elts]))

    def visit_Index(self, node):
        return self.visit(node.value)


#==============================================================================
# Helpers
#==============================================================================

def indent(lines):
    if isinstance(lines, list):
        return  ['    {0}'.format(lines) for l in lines]
    else:
        return '    {0}'.format(lines)


def jscompile(obj, name=None):
    if not getattr(obj, '__js__', None):
        node = ast.parse(inspect.getsource(obj))
        obj.__js__ = JSCompiler(obj, name).visit(node)
    return obj.__js__
