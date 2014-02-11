# -*- coding: utf-8 -*-
#==============================================================================
# Copyright:    Hybrid Labs
# Licence:      Private
#==============================================================================

import ast
import inspect
import json
import sys
import types

from .. import client, model


class JSCode(object):
    def __init__(self, code):
        pass


class YieldPoint(object):
    def __init__(self):
        self.count = 0

    def create(self):
        self.count += 1
        return self.count


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
        self.node_chain = [None]
        if isinstance(obj, types.ModuleType):
            self.module = obj
        else:
            self.module = sys.modules.get(getattr(obj, '__module__', None))

    def visit(self, node, context=None, inherit=True):
        node.parent = self.node_chain[-1]
        node.context = getattr(node, 'context', context)
        if inherit and node.parent:
            node.yield_point = getattr(node.parent, 'yield_point', None)
            node.loop_point = getattr(node.parent, 'loop_point', None)
            node.break_point = getattr(node.parent, 'break_point', None)
            node.context = node.context or node.parent.context

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
        elif value is model.model:
            return 'avalon.model'
        return name

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
            return 'return {0};'.format(self.visit(node.value))
        else:
            return 'return;'

    # FunctionDef(
    #   identifier name, arguments args, stmt* body, expr* decorator_list)
    def visit_FunctionDef(self, node):
        context = node.context or 'this'
        args = [self.visit(a, inherit=False) for a in node.args.args]
        local = ', '.join(['{0}: {0}'.format(a) for a in args])
        args = ', '.join(args)

        tpl = [
            '{0}.{1} = function {1}({2}) {{'.format(context, node.name, args),
            '  var $ctx = {next_state: 0, ctx: this};',
            '  $ctx.local = {{{0}}};'.format(local),
            '  $ctx.func = function($ctx) {',
            '    while (true) switch($ctx.next_state) {',
            '      case 0:'
        ]

        node.yield_point = YieldPoint()
        for c in node.body:
            extend(tpl, indent(self.visit(c, '$ctx.local'), level=3))

        extend(tpl, [
            '      default: return;',
            '    }',
            '  }',
            '  return $ctx.func.call(this, $ctx);',
            '}'
        ])
        return tpl

    #ClassDef(identifier name, expr* bases, stmt* body, expr* decorator_list)
    def visit_ClassDef(self, node):
        if len(node.bases) > 1:
            raise NotImplementedError('Multiple inheritance not supported')

        tpl = []
        context = node.context or 'this'

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
            extend(tpl, indent(self.visit(c, '$scope' if scope else None)))

        if scope:
            # Events
            tpl_on = '\n'.join(indent([
                '$element.on("{0}", "{1}", function eventHandler(e) {{',
                '  var t = angular.element(e.target).scope();',
                '  $scope.$apply(function() {{ $scope.{2}($scope, t, e) }});',
                '}})'
            ]))

            extend(tpl, [tpl_on.format(*e) for e in scope['events']])
            extend(tpl, indent([
                '$scope.$on("$destroy", function() {',
                '  $element.off();',
                '})'
            ]))

            # Support repeat scope
            extend(tpl, indent([
                'var $getattr = $scope.__getattr__;',
                '$scope.__getattr__ = function __getattr__(self, value) {',
                '  return self.$item && self.$item[value] ||',
                '    $getattr && $getattr(self, value);',
                '}'
            ]))

            # Constructor
            extend(tpl, indent([
                'if ($scope.__init__) {',
                '  var __init__ = $scope.__init__;',
                '  delete $scope.__init__;',
                '  __init__($scope);',
                '}'
            ]))

        extend(tpl, [
            '};',
            '{0}.{1}.$inject = {2};'.format(
                context, class_name, json.dumps(inject))
        ])

        if not scope and node.bases:
            tpl.append('{0}.{1}.prototype = new {2}();'.format(
                context, node.name, self.visit(node.bases[0])))

        return tpl

    # Assign(expr* targets, expr value)
    def visit_Assign(self, node):
        tpl = []
        context = getattr(node, 'context', None)

        if isinstance(node.value, ast.Yield):
            if getattr(node, 'yield_point', None):
                node.value.yield_point = node.yield_point
            extend(tpl, self.visit(node.value))
            extend(tpl, 'var $assign = $ctx.send;')
        else:
            extend(tpl, 'var $assign = {0};'.format(self.visit(node.value)))

        for target in node.targets:
            if isinstance(target, ast.Tuple):
                for i, t in enumerate(target.elts):
                    t = self.visit(t)
                    if not context:
                        tpl.append('var {0} = $assign[{1}];'.format(t, i))
                    tpl.append('{0} = $assign[{1}];'.format(t, i))
            else:
                target = self.visit(target)
                if not context:
                    tpl.append('var {0} = $assign;'.format(target))
                tpl.append('{0} = $assign;'.format(target))

        return tpl

    # AugAssign(expr target, operator op, expr value)
    def visit_AugAssign(self, node):
        target = self.visit(node.target)
        op = JSCompiler.BIN_OP[type(node.op)]
        value = self.visit(node.value)
        return '{0} {1}= {2};'.format(target, op, value)

    # For(expr target, expr iter, stmt* body, stmt* orelse)
    def visit_For(self, node):
        if node.orelse:
            raise NotImplementedError('For else statement not supported')
        if not hasattr(node, 'yield_point'):
            raise SyntaxError('For statement not inside a function block')

        tpl = []
        loop_point = node.yield_point.create()
        break_point = node.yield_point.create()

        target_node = ast.Name('iter', None)
        assign_node = ast.Assign([target_node], node.iter)
        assign_node.context = '$ctx.local'
        extend(tpl, self.visit_Assign(assign_node))

        # TODO: Check StopIteration exception
        extend(tpl, [
            'case {0}:'.format(loop_point),
            'try {{ $ctx.local.{0} = $ctx.local.iter.next(); }}'.format(
                self.visit(node.target)),
            'catch($exception) {',
            '  $ctx.next_state = {0}; continue; '.format(break_point),
            '}'
        ])

        for c in node.body:
            extend(tpl, self.visit(c, '$ctx.local'))

        extend(tpl, [
            '$ctx.next_state = {0}; continue;'.format(loop_point),
            'case {0}:'.format(break_point)
        ])
        return tpl

    # While(expr test, stmt* body, stmt* orelse)
    def visit_While(self, node):
        if node.orelse:
            raise NotImplementedError('While else statement not supported')
        if not hasattr(node, 'yield_point'):
            raise SyntaxError('While statement not inside a function block')

        tpl = []
        loop_point = node.yield_point.create()
        break_point = node.yield_point.create()

        extend(tpl, [
            'case {0}:'.format(loop_point),
            'if (!({0})) {{'.format(self.visit(node.test)),
            '  $ctx.next_state = {0}; continue;'.format(break_point),
            '}'
        ])

        for c in node.body:
            extend(tpl, self.visit(c, '$ctx.local'))

        extend(tpl, [
            '$ctx.next_state = {0}; continue;'.format(loop_point),
            'case {0}:'.format(break_point)
        ])
        return tpl

    # Print(expr? dest, expr* values, bool nl)
    def visit_Print(self, node):
        return 'console.log({0});'.format(
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
        tpl = []

        if not hasattr(node, 'yield_point'):
            raise SyntaxError('Try block not inside a function block')

        except_point = node.yield_point.create()
        continue_point = node.yield_point.create()

        for c in node.body:
            if isinstance(c, ast.Yield):
                extend(tpl, self.visit_Yield(c, except_point=except_point)),
            else:
                extend(tpl, [
                    'try {{ {0} }}'.format(self.visit(c)),
                    'catch($exception) {',
                    '  $ctx.next_state = {0}; continue;'.format(except_point),
                    '}'
                ])

        extend(tpl, [
            '$ctx.next_state = {0}; continue;'.format(continue_point),
            'case {0}:'.format(except_point)
        ])

        for c in node.handlers:
            extend(tpl, self.visit(c))

        tpl.append('case {0}:'.format(continue_point))
        return tpl

    # Try(stmt* body, excepthandler* handlers, stmt* orelse, stmt* finalbody)
    def visit_Try(self, node):
        return self.visit_TryExcept(node)

    # Import(alias* names)
    def visit_Import(self, node):
        return ''

    # ImportFrom(identifier? module, alias* names, int? level)
    def visit_ImportFrom(self, node):
        return ''

    # Expr(expr value)
    def visit_Expr(self, node):
        return self.visit(node.value)

    # Pass
    def visit_Pass(self, node):
        return ['// pass']

    # BoolOp(boolop op, expr* values)
    def visit_BoolOp(self, node):
        op = JSCompiler.BOOL_OP[type(node.op)]
        return '({0})'.format(op.join([self.visit(v) for v in node.values]))

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

    # Yield(expr? value)
    def visit_Yield(self, node, except_point=None):
        if not getattr(node, 'yield_point', None):
            raise SyntaxError('Yield not inside a function block')

        tpl = []
        if except_point is not None:
            tpl = ['try {']

        yield_point = node.yield_point.create()
        body = [
            'var $tmp = {0};'.format(self.visit(node.value)),
            '$ctx.next_state = {0};'.format(yield_point),
            '$ctx.yield = $tmp;',
            'return $ctx;'
        ]

        if except_point is not None:
            extend(tpl, indent(body))
            extend(tpl, (
                '} catch ($exception) {',
                '  $ctx.next_state = {0}; continue;'.format(except_point),
                '}'
            ))
        else:
            extend(tpl, body)

        extend(tpl, 'case {0}:'.format(yield_point))
        return tpl

    #Compare(expr left, cmpop* ops, expr* comparators)
    def visit_Compare(self, node):
        left = self.visit(node.left)
        ops = [JSCompiler.COMPARE_OP[type(op)] for op in node.ops]
        comparators = [self.visit(c) for c in node.comparators]

        tpl = []
        for op, right in zip(ops, comparators):
            tpl.append('{0} {1} {2}'.format(left, op, right))
            left = right
        return '&&'.join(tpl)

    # Call(
    #   expr func, expr* args, keyword* keywords, xpr? starargs, expr? kwargs)
    def visit_Call(self, node):
        func = self.visit(node.func)
        if isinstance(node.func, ast.Attribute):
            func_context = self.visit(node.func.value)
        else:
            func_context = 'this'

        if getattr(self.module, func, None) is JSCode:
            return node.args[0].s

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
            tpl = 'getattr({0}, "{1}")'
        else:
            tpl = '{0}.{1}'
        return tpl.format(self.visit(node.value), node.attr)

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

        if getattr(node, 'context', None):
            return '{0}.{1}'.format(node.context, node.id)
        else:
            return node.id

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


def indent(lines, spaces=2, level=1):
    spaces = ' ' * (spaces * level)
    if isinstance(lines, list):
        return ['{0}{1}'.format(spaces, l) for l in lines]
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


def runtime():
    from . import built_ins
    return jscompile(built_ins)
