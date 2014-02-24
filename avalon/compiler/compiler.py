# -*- coding: utf-8 -*-
#==============================================================================
# Copyright:    Hybrid Labs
# Licence:      See LICENSE
#==============================================================================

from __future__ import absolute_import

import ast
import inspect
import json
import sys

from types import ModuleType


class JSCode(object):
    def __getattr__(self, name):
        return self(name)

    def __call__(self, code):
        if code == 'Object':
            return object

JSCode = JSCode()


class BranchPoint(object):
    def __init__(self):
        self.count = 0

    def create(self):
        self.count += 1
        return self.count


class YieldSearch(ast.NodeVisitor):
    def visit_Yield(self, node):
        self.found_yield = True

    def visit_FunctionDef(self, node):
        pass


class NodeOptions(object):
    def __init__(self, options):
        self.__dict__.update(options)

    def __getattr__(self, name):
        return None


class JSCompiler(ast.NodeVisitor):
    KEYWORDS = ['default', 'switch', 'throw']

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
        if isinstance(obj, ModuleType):
            self.module = obj
        else:
            self.module = sys.modules.get(getattr(obj, '__module__', None))

    def visit(self, node, context=False, inherit=True, **kwargs):
        node.parent = self.node_chain[-1]
        if context is not False:
            node.context = context
        else:
            node.context = getattr(node, 'context', None)

        if inherit and node.parent:
            node.branch = getattr(node.parent, 'branch', None)
            node.loop_point = getattr(node.parent, 'loop_point', None)
            node.break_point = getattr(node.parent, 'break_point', None)
            node.context = node.context or node.parent.context
        else:
            node.branch = None
            node.loop_point = None
            node.break_point = None

        self.node_chain.append(node)
        method = 'visit_' + node.__class__.__name__
        method_func = getattr(self, method, self.generic_visit)
        if len(inspect.getargspec(method_func).args) == 3:
            ret = method_func(node, NodeOptions(kwargs))
        else:
            ret = method_func(node)
        self.node_chain.pop()
        return ret

    def lookup(self, name):
        from . import builtins, exceptions, types
        from .. import client, model

        if name == 'print':
            return name
        elif name == 'None':
            return 'null'
        elif name == 'True':
            return 'true'
        elif name == 'False':
            return 'false'

        value = (getattr(builtins, name, None) or
                 getattr(exceptions, name, None) or
                 getattr(types, name, None) or
                 getattr(self.module, name, None))

        if value is None:
            return None
        elif value is client.session:
            return 'avalon.session'
        elif value is model.model:
            return 'avalon.model'
        return self.safe_name(name)

    def safe_name(self, name):
        if name in JSCompiler.KEYWORDS:
            return name + '_'
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
        if not node.branch:
            raise SyntaxError('Return statement not inside a function block')

        tpl = ['$ctx.end = true;']
        value = self.visit(node.value) if node.value else None
        if value is not None:
            extend(tpl, 'return {0};', value)
        else:
            extend(tpl, 'return null;')
        return tpl

    # FunctionDef(
    #   identifier name, arguments args, stmt* body, expr* decorator_list)
    def visit_FunctionDef(self, node, options):
        args = [self.visit(a, inherit=False) for a in node.args.args]
        local = ', '.join(['{0}: {0}'.format(a) for a in args])
        args = ', '.join(args)
        node.name = self.safe_name(node.name)

        if node.context:
            assign = '{0}.{1}'.format(node.context, node.name)
        else:
            assign = 'var {0}'.format(node.name)

        tpl = [
            '{0} = function {1}({2}) {{'.format(assign, node.name, args),
            '  var $exception;',
            '  var $ctx = {next_state: 0, ctx: this, try_stack: []};',
            '  $ctx.local = {{{0}}};'.format(local),
            '  $ctx.func = function($ctx) {',
            '    while (true) try { switch($ctx.next_state) {',
            '      case 0:'
        ]

        node.branch = BranchPoint()
        for c in node.body:
            extend(tpl, indent(self.visit(c, '$ctx.local'), level=3))

        extend(tpl, [
            '      default: $ctx.end = true; return null;',
            '    }} catch($e) {',
            '      $exception = $e;',
            '      $ctx.next_state = $ctx.try_stack.pop();',
            '      if ($ctx.next_state === undefined) throw $exception;',
            '      continue;',
            '    }',
            '  }',
        ])

        if is_generator(node):
            extend(tpl, indent('return new generator($ctx);'))
        else:
            extend(tpl, indent('return $ctx.func.call(this, $ctx);'))
        extend(tpl, '};')
        return tpl

    #ClassDef(identifier name, expr* bases, stmt* body, expr* decorator_list)
    def visit_ClassDef(self, node):
        from .. import client

        if len(node.bases) > 1:
            raise NotImplementedError('Multiple inheritance not supported')

        tpl = []
        if node.bases:
            if isinstance(node.bases[0], ast.Attribute):
                scope_name = node.bases[0].attr
                scope = client._scopes.get(scope_name, None)
                if scope:
                    return self.visit_ClientScope(node, scope)

        if node.context:
            assign = '{0}.{1}'.format(node.context, node.name)
        else:
            assign = 'var {0}'.format(node.name)

        # Constructor
        node.name = self.safe_name(node.name)
        extend(tpl, '{0} = function {1}() {{'.format(assign, node.name))

        # Allow object creation without using `new`
        extend(tpl, indent([
            'if(!(this instanceof {0}) || this.__class__) {{'.format(
                node.name),
            '  var $O = function(args) {',
            '    return {0}.apply(this, args);'.format(node.name),
            '  };',
            '  $O.prototype = {0}.prototype;'.format(node.name),
            '  return new $O(arguments);',
            '}'
        ]))

        # Set object id
        extend(tpl, '  this.oid = object.oid = object.oid + 1;')

        # Set any instance magic properties
        extend(tpl, '  this.__class__ = {0};'.format(node.name))

        for c in node.body:
            if not isinstance(c, ast.FunctionDef):
                extend(tpl, indent(self.visit(c)))

        extend(tpl, [
            '  this.__bind__(this);',
            '  if (this.__init__) this.__init__.apply(this, arguments);',
            '};'
        ])

        # Class body
        base = self.visit(node.bases[0])
        if node.context:
            cls = assign
        else:
            cls = node.name

        # Inherit
        extend(tpl, 'var $C = function() {};')
        if node.bases:
            extend(tpl, '$C.prototype = {0}.prototype;'.format(base))
        extend(tpl, '{0}.prototype = new $C;'.format(cls))

        # Set any class magic properties
        assign = '{0}.prototype.{1} = {0}.{1} = "{2}"'
        extend(tpl, assign.format(cls, '__name__', node.name))

        # Methods
        for c in node.body:
            if isinstance(c, ast.FunctionDef):
                extend(tpl, self.visit(c, '{0}.prototype.{1} = {0}'.format(
                    cls, self.safe_name(c.name))))

        # Method binder
        extend(tpl, '{0}.prototype.{1} = {0}.{1} = function(self) {{'.format(
            cls, '__bind__'))
        if node.bases:
            extend(tpl, indent(
                'if ({0}.__bind__) {0}.__bind__(self);'.format(base)))

        for c in node.body:
            if not isinstance(c, ast.FunctionDef):
                continue
            extend(tpl, indent(
                'self.{0} = method(self, {1}.{0});'.format(
                    self.safe_name(c.name), node.name)))
        extend(tpl, '};')
        return tpl

    def visit_ClientScope(self, node, scope):
        inject = ['$scope', '$element']

        if node.context:
            assign = '{0}.{1}'.format(node.context, scope['name'])
        else:
            assign = 'var {0}'.format(scope['name'])

        args = ', '.join(inject)
        tpl = ['{0} = function {1}({2}) {{'.format(assign, node.name, args)]

        for c in node.body:
            extend(tpl, indent(self.visit(c, '$scope')))

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

        # Scope constructor
        extend(tpl, indent([
            'if ($scope.__init__) {',
            '  var __init__ = $scope.__init__;',
            '  delete $scope.__init__;',
            '  __init__($scope);',
            '}'
        ]))

        if node.context:
            scope = assign
        else:
            scope = scope['name']

        return extend(tpl, [
            '};',
            '{0}.$inject = {1};'
        ], scope, json.dumps(inject))

    # Assign(expr* targets, expr value)
    def visit_Assign(self, node):
        tpl = []
        if isinstance(node.value, ast.Yield):
            extend(tpl, self.visit(node.value))
            extend(tpl, 'var $assign = $ctx.send;')
        else:
            extend(tpl, 'var $assign = {0};'.format(self.visit(node.value)))

        for target in node.targets:
            if isinstance(target, ast.Tuple):
                for i, t in enumerate(target.elts):
                    if (isinstance(t, ast.Attribute) or
                            isinstance(t, ast.Subscript)):
                        tpl.append(self.visit(t, value='$assign[%s]' % i))
                        continue

                    t = self.visit(t)
                    if not node.context:
                        tpl.append('var {0};')
                    tpl.append('{0} = $assign[{1}];'.format(t, i))
            else:
                if (isinstance(target, ast.Attribute) or
                        isinstance(target, ast.Subscript)):
                    tpl.append(self.visit(target, value='$assign'))
                    continue

                target = self.visit(target)
                if not node.context:
                    tpl.append('var {0};')
                tpl.append('{0} = $assign;'.format(target))

        return tpl

    # AugAssign(expr target, operator op, expr value)
    def visit_AugAssign(self, node):
        op = JSCompiler.BIN_OP[type(node.op)]
        value = self.visit(node.value)

        if (isinstance(node.target, ast.Attribute) or
                isinstance(node.target, ast.Subscript)):
            item = self.visit(node.target, get=True)
            assign = '{0} {1} {2}'.format(item, op, value)
            return self.visit(node.target, value=assign)

        target = self.visit(node.target)
        return '{0} {1}= {2};'.format(target, op, value)

    # For(expr target, expr iter, stmt* body, stmt* orelse)
    def visit_For(self, node):
        if node.orelse:
            raise NotImplementedError('For else statement not supported')
        if not node.branch:
            raise SyntaxError('For statement not inside a function block')

        tpl = []
        node.loop_point = loop_point = node.branch.create()
        node.break_point = break_point = node.branch.create()
        try_except_point = node.branch.create()
        try_continue_point = node.branch.create()

        target_node = ast.Name('iter', None)
        assign_node = ast.Assign([target_node], node.iter)
        assign_node.context = '$ctx.local'
        extend(tpl, self.visit(assign_node))

        extend(tpl, [
            label(loop_point),
            '$ctx.try_stack.push({0});'.format(try_except_point),
            '{0} = $ctx.local.iter.next();'.format(self.visit(node.target)),
            '$ctx.try_stack.pop();',
            goto(try_continue_point),
            label(try_except_point),
            'if ($exception instanceof StopIteration) {0};'.format(
                goto(break_point)),
            'throw $exception;',
            label(try_continue_point)
        ])

        for c in node.body:
            extend(tpl, self.visit(c, '$ctx.local'))

        extend(tpl, [
            goto(loop_point),
            label(break_point)
        ])
        return tpl

    # While(expr test, stmt* body, stmt* orelse)
    def visit_While(self, node):
        if node.orelse:
            raise NotImplementedError('While else statement not supported')
        if not node.branch:
            raise SyntaxError('While statement not inside a function block')

        tpl = []
        node.loop_point = loop_point = node.branch.create()
        node.break_point = break_point = node.branch.create()

        extend(tpl, [
            label(loop_point),
            'if (!bool({0})) {1};'.format(
                self.visit(node.test), goto(break_point))
        ])

        for c in node.body:
            extend(tpl, self.visit(c, '$ctx.local'))

        extend(tpl, [
            goto(loop_point),
            label(break_point)
        ])
        return tpl

    # Print(expr? dest, expr* values, bool nl)
    def visit_Print(self, node):
        return 'console.log({0});'.format(
            ', '.join([self.visit(v) for v in node.values]))

    # If(expr test, stmt* body, stmt* orelse)
    def visit_If(self, node):
        if not node.branch:
            raise SyntaxError('If block not inside a function block')

        else_point = node.branch.create()
        continue_point = node.branch.create()
        tpl = [
            'if (!bool({0})) {1};'.format(
                self.visit(node.test), goto(else_point))
        ]

        for c in node.body:
            extend(tpl, self.visit(c))

        extend(tpl, [
            goto(continue_point),
            label(else_point)
        ])

        if node.orelse:
            for c in node.orelse:
                extend(tpl, self.visit(c))

        extend(tpl, label(continue_point))
        return tpl

    # Py2: Raise(expr? type, expr? inst, expr? tback)
    # Py3: Raise(expr? exc, expr? cause)
    def visit_Raise(self, node):
        if hasattr(node, 'type'):
            return 'throw {0}'.format(self.visit(node.type))
        else:
            return 'throw {0}'.format(self.visit(node.exc))

    # TryExcept(stmt* body, excepthandler* handlers, stmt* orelse)
    def visit_TryExcept(self, node):
        if not node.branch:
            raise SyntaxError('Try block not inside a function block')

        try_except_point = node.branch.create()
        try_continue_point = node.branch.create()

        tpl = ['$ctx.try_stack.push({0});'.format(try_except_point)]
        for c in node.body:
            extend(tpl, self.visit(c))

        extend(tpl, [
            '$ctx.try_stack.pop();',
            goto(try_continue_point),
            label(try_except_point)
        ])

        for c in node.handlers:
            extend(tpl, self.visit(c))

        return extend(tpl, [
            'if ($exception !== undefined) throw $exception;',
            label(try_continue_point)
        ])

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
        return '// pass'

    # Break
    def visit_Break(self, node):
        if not node.break_point:
            raise SyntaxError('Break not inside a loop block')
        return goto(node.break_point)

    # Continue
    def visit_Continue(self, node):
        if not node.loop_point:
            raise SyntaxError('Continue not inside a loop block')
        return goto(node.loop_point)

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
    def visit_Yield(self, node):
        if not node.branch:
            raise SyntaxError('Yield not inside a function block')

        yield_point = node.branch.create()
        value = self.visit(node.value) if node.value else 'null'
        return [
            '$ctx.result = {0};'.format(value),
            '$ctx.next_state = {0};'.format(yield_point),
            'return $ctx;',
            label(yield_point)
        ]

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
            func_context = 'undefined'

        if getattr(self.module, func, None) is JSCode:
            if isinstance(node.args[0], ast.List):
                return '\n'.join([c.s for c in node.args[0].elts])
            elif isinstance(node.args[0], ast.Str):
                return node.args[0].s
            else:
                raise SyntaxError('Invalid JSCode usage')

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
    def visit_Attribute(self, node, options):
        obj = self.visit(node.value)
        attr = node.attr
        if getattr(self.module, obj, None) is JSCode:
            return attr
        if options.get or isinstance(node.ctx, ast.Load):
            return 'getattr({0}, "{1}")'.format(obj, attr)
        elif isinstance(node.ctx, ast.Store):
            return 'setattr({0}, "{1}", {2})'.format(obj, attr, options.value)
        else:
            raise SyntaxError('Invalid ctx for attribute')

    # Subscript(expr value, slice slice, expr_context ctx)
    def visit_Subscript(self, node, options):
        obj = self.visit(node.value)
        index = self.visit(node.slice)
        if options.get or isinstance(node.ctx, ast.Load):
            return 'getitem({0}, {1})'.format(obj, index)
        elif isinstance(node.ctx, ast.Store):
            return 'setitem({0}, {1}, {2})'.format(obj, index, options.value)
        else:
            raise SyntaxError('Invaid ctx for subscript')

    # Name(identifier id, expr_context ctx)
    def visit_Name(self, node):
        lookup = self.lookup(node.id)
        if lookup:
            return lookup
        if node.context:
            return '{0}.{1}'.format(node.context, node.id)
        else:
            return node.id

    # List(expr* elts, expr_context ctx)
    def visit_List(self, node):
        return 'list([{0}])'.format(
            ', '.join([self.visit(c) for c in node.elts]))

    # Tuple(expr* elts, expr_context ctx)
    def visit_Tuple(self, node):
        return 'tuple([{0}])'.format(
            ', '.join([self.visit(c) for c in node.elts]))

    # Index(expr value)
    def visit_Index(self, node):
        return self.visit(node.value)

    # ExceptHandler(expr? type, identifier? name, stmt* body)
    def visit_ExceptHandler(self, node):
        tpl = []
        if node.type:
            tpl.append('if ($exception instanceof {0}) {{'.format(
                self.visit(node.type)))
        else:
            tpl.append('if ($exception) {')

        if node.name:
            if node.context:
                extend(tpl, '  {0}.{1} = $exception;', node.context, node.name)
            else:
                extend(tpl, '  var {0} = $exception;', node.name)

        for c in node.body:
            extend(tpl, indent(self.visit(c)))

        tpl.append(indent('$exception = undefined;'))
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


def extend(template, lines, *format_params):
    if isinstance(lines, list):
        if format_params:
            for i, line in enumerate(lines):
                try:
                    lines[i] = line.format(*format_params)
                except ValueError:
                    pass
        template.extend(lines)
    else:
        if format_params:
            lines = lines.format(*format_params)
        template.append(lines)
    return template


def goto(point, state='$ctx.next_state'):
    return '{{ {0} = {1}; continue; }}'.format(state, point)


def label(point):
    return 'case {0}:'.format(point)


def is_generator(node):
    searcher = YieldSearch()
    searcher.found_yield = False
    if isinstance(node, ast.FunctionDef):
        for c in node.body:
            searcher.visit(c)
    else:
        searcher.visit(node)
    return searcher.found_yield


def js_compile(obj):
    if not getattr(obj, '__js__', None):
        node = ast.parse(inspect.getsource(obj))
        obj.__js__ = JSCompiler(obj).visit(node)
    return obj.__js__


def runtime():
    from . import builtins, types, exceptions
    return js_compile(builtins) + js_compile(types) + js_compile(exceptions)
