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
import sys

from . import client


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

    def __init__(self, obj):
        self.obj = obj
        self.module = sys.modules[obj.__module__]
        self.node_chain = [None]

    def visit(self, node):
        node.parent = self.node_chain[-1]
        self.node_chain.append(node)
        ret = super(JSCompiler, self).visit(node)
        self.node_chain.pop()
        return ret

    def lookup(self, name):
        value = getattr(self.module, name, None)

        if value is None:
            return None
        elif value is client.session:
            return '_session'

    def generic_visit(self, node):
        raise NotImplementedError(node)

    # Module(stmt* body)
    def visit_Module(self, node):
        tpl = []
        for child in node.body:
            extend(tpl, self.visit(child))
        return '\n'.join(tpl)

    # Return(expr? value)
    def visit_Return(self, node):
        if node.value:
            return 'return {0}'.format(self.visit(node.value))
        else:
            return 'return'

    # FunctionDef(identifier name, arguments args,
    # stmt* body, expr* decorator_list)
    def visit_FunctionDef(self, node):
        context = getattr(node, 'context', 'this')
        args = ', '.join([self.visit(a) for a in node.args.args])
        tpl = [
            '{0}.{1} = function {1}({2}) {{'.format(
                context, node.name, args)
        ]

        for c in node.body:
            extend(tpl, indent(self.visit(c)))

        tpl.append('}')
        return tpl

    #ClassDef(identifier name, expr* bases, stmt* body, expr* decorator_list)
    def visit_ClassDef(self, node):
        if len(node.bases) > 1:
            raise NotImplementedError('Multiple inheritance not supported')

        tpl = []
        context = getattr(node, 'context', 'this')

        if node.bases:
            scope_name = node.bases[0].attr
            scope = client._scopes.get(scope_name, None)
            class_name = scope_name
        else:
            scope = None
            class_name = node.name

        inject = ['$scope', '$element'] if scope else []
        tpl.append('{0}.{1} = function {2}({3}) {{'.format(
            context, class_name, node.name, ', '.join(inject)))

        for c in node.body:
            if scope:
                c.context = '$scope'
            extend(tpl, indent(self.visit(c)))

        if scope:
            # Events
            tpl_on = '\n'.join(indent([
                '$element.on("{0}", "{1}", function eventHandler(e) {{',
                '  var t = angular.element(e.target).scope()',
                '  $scope.$apply(function() {{ $scope.{2}($scope, t, e) }})',
                '}})'
            ]))

            extend(tpl, [tpl_on.format(*e) for e in scope['events']])
            extend(tpl, indent([
                '$scope.$on("$destroy", function() {',
                '  $element.off()',
                '})'
            ]))

            # Support repeat scope
            extend(tpl, indent([
                'var _getattr = $scope.__getattr__',
                '$scope.__getattr__ = function __getattr__(self, value) {',
                '  return self.$item && self.$item[value] ||',
                '    _getattr && _getattr(self, value)',
                '}'
            ]))

            # Constructor
            extend(tpl, indent([
                'if ($scope.__init__) {',
                '  var __init__ = $scope.__init__',
                '  delete $scope.__init__',
                '  __init__($scope)',
                '}'
            ]))

        tpl.append('}')
        tpl.append('{0}.{1}.$inject = {2}'.format(
            context, class_name, json.dumps(inject)))

        if not scope and node.bases:
            tpl.append('{0}.{1}.prototype = new {2}()'.format(
                context, node.name, self.visit(node.bases[0])))

        return tpl

    # Assign(expr* targets, expr value)
    def visit_Assign(self, node):
        context = getattr(node, 'context', None)

        def assign(target, value):
            if context:
                return '{0}.{1} = {2}'.format(context, target, value)
            elif '.' in target or '[' in target:
                return '{0} = {1}'.format(target, value)
            else:
                return 'var {0} = {1}'.format(target, value)

        tpl = []
        for target in node.targets:
            if type(target) is ast.Tuple:
                stmt = 'var _assign = {0}'.format(self.visit(node.value))
                tpl.append(stmt)

                for i, t in enumerate(target.elts):
                    v = '_assign[{0}]'.format(i)
                    tpl.append(assign(self.visit(t), v))
            else:
                stmt = assign(self.visit(target), self.visit(node.value))
                tpl.append(stmt)

        return tpl

    # AugAssign(expr target, operator op, expr value)
    def visit_AugAssign(self, node):
        target = self.visit(node.target)
        op = JSCompiler.BIN_OP[type(node.op)]
        value = self.visit(node.value)
        return '{0} {1}= {2}'.format(target, op, value)

    # Print(expr? dest, expr* values, bool nl)
    def visit_Print(self, node):
        return 'console.log({0})'.format(
            ', '.join([self.visit(v) for v in node.values]))

    # If(expr test, stmt* body, stmt* orelse)
    def visit_If(self, node):
        tpl = ['if ({0}) {{'.format(self.visit(node.test))]
        for c in node.body:
            extend(tpl, indent(self.visit(c)))
        tpl.append('}')

        if node.orelse:
            tpl.append('else {')
            for c in node.orelse:
                extend(tpl, indent(self.visit(c)))
            tpl.append('}')

        return tpl

    # TryExcept(stmt* body, excepthandler* handlers, stmt* orelse)
    def visit_TryExcept(self, node):
        tpl = ['try {']

        for c in node.body:
            extend(tpl, indent(self.visit(c)))

        tpl.append('} catch(__exception__) {')

        for c in node.handlers:
            extend(tpl, indent(self.visit(c)))

        tpl.append('}')
        return tpl

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

    # Dict(expr* keys, expr* values)
    def visit_Dict(self, node):
        return '{{ {0} }}'.format(', '.join([
            '{0}: {1}'.format(self.visit(kv[0]), self.visit(kv[1]))
            for kv in zip(node.keys, node.values)
        ]))

    #Compare(expr left, cmpop* ops, expr* comparators)
    def visit_Compare(self, node):
        left = self.visit(node.left)
        ops = [JSCompiler.COMPARE_OP[type(op)] for op in node.ops]
        comparators = [self.visit(c) for c in node.comparators]

        tpl = []
        for op, right in zip(ops, comparators):
            tpl.append('{0} {1} {2}'.format(left, op, right))
            left = right

        return ' && '.join(tpl)

    # Call(expr func, expr* args, keyword* keywords,
    # xpr? starargs, expr? kwargs)
    def visit_Call(self, node):
        func = self.visit(node.func)
        func_context = getattr(node.func, 'context', 'this')

        if func == 'print':
            node.values = node.args
            return self.visit_Print(node)

        args = ', '.join([self.visit(a) for a in node.args])
        return '{0}.apply({1}, [{2}])'.format(func, func_context, args)

    # Num(object n)
    def visit_Num(self, node):
        return str(node.n)

    # Str(string s)
    def visit_Str(self, node):
        return '"{0}"'.format(node.s).replace('\n', '\\n\\\n')

    # Attribute(expr value, identifier attr, expr_context ctx)
    def visit_Attribute(self, node):
        if isinstance(node.ctx, ast.Load):
            tpl = '({0}.{1} || {0}.__getattr__ && {0}.__getattr__({0}, "{1}"))'
        else:
            tpl = '{0}.{1}'

        node.context = self.visit(node.value)
        return tpl.format(node.context, node.attr)

    # Subscript(expr value, slice slice, expr_context ctx)
    def visit_Subscript(self, node):
        value = self.visit(node.value)
        index = self.visit(node.slice)
        return '{0}[{1}]'.format(value, index)

    # Name(identifier id, expr_context ctx)
    def visit_Name(self, node):
        lookup = self.lookup(node.id)
        if lookup:
            return lookup
        elif node.id == 'None':
            return 'undefined'
        elif node.id == 'True':
            return 'true'
        elif node.id == 'False':
            return 'false'
        return str(node.id)

    # List(expr* elts, expr_context ctx)
    def visit_List(self, node):
        return '[{0}]'.format(', '.join([self.visit(c) for c in node.elts]))

    # Tuple(expr* elts, expr_context ctx)
    def visit_Tuple(self, node):
        return '[{0}]'.format(', '.join([self.visit(c) for c in node.elts]))

    # Index(expr value)
    def visit_Index(self, node):
        return self.visit(node.value)

    # ExceptHandler(expr? type, identifier? name, stmt* body)
    def visit_ExceptHandler(self, node):
        tpl = []
        if node.type:
            tpl.append('if (__exception__.type == {0}'.format(node.type))
        else:
            tpl.append('if (__exception__) {')

        for c in node.body:
            extend(tpl, indent(self.visit(c)))

        tpl.append(indent('__exception__ = undefined'))
        tpl.append('}')

        return tpl

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


def jscompile(obj):
    if not getattr(obj, '__js__', None):
        node = ast.parse(inspect.getsource(obj))
        obj.__js__ = JSCompiler(obj).visit(node)
    return obj.__js__
