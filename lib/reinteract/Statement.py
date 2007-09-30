#!/usr/bin/python

import compiler
import copy

class Statement:
    def __init__(self, text, parent = None):
        self.__text = text
        self.__parent = parent
        self.__result_scope = None

    def get_result_scope(self):
        return self.__result_scope

    def __get_modified_names(self):
        tree = compiler.parse(self.__text)
        if not isinstance(tree, compiler.ast.Module):
            return []

        if not isinstance(tree.node, compiler.ast.Stmt):
            return []

        stmt = tree.node

        #
        # We recognize the pattern
        #
        #   <name>.function()
        #
        # As likely mutating <name> with a side-effect
        #
        modified = []
        for node in stmt.nodes:
            if not isinstance(node, compiler.ast.Discard):
                continue

            discard = node
            if not isinstance(discard.expr, compiler.ast.CallFunc):
                continue

            node = discard.expr.node
            if not isinstance(node, compiler.ast.Getattr):
                continue

            node = node.expr
            if not isinstance(node, compiler.ast.Name):
                continue

            modified.append(node.name)

        return modified

    def eval(self):
        modified = self.__get_modified_names()
        
        if self.__parent:
            scope = copy.copy(self.__parent.get_result_scope())
        else:
            scope = {}

        for name in modified:
            scope[name] = copy.copy(scope[name])

        exec self.__text in globals(), scope

        self.__result_scope = scope

if __name__=='__main__':
    s1 = Statement("a = 1")
    s1.eval()
    s2 = Statement("c = 3; b = [1,2]", parent=s1)
    s2.eval()
    s3 = Statement("b.insert(0, 0)", parent=s2)
    s3.eval()
    s4 = Statement("c = a + b[0]", parent=s3)
    s4.eval()

    s32 = Statement("c = a + b[0]", parent=s2)
    s32.eval()

    print s4.get_result_scope()['c']
    print s32.get_result_scope()['c']

