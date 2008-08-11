import copy
import imp
import sys

_counter = 1

class HelpResult:
    def __init__(self, arg):
        self.arg = arg

class _Helper:
    # We use a callable object here rather than a function so that we handle
    # help without arguments, just like the help builtin
    def __repr__(self):
        return "Type help(object) for help about object"

    def __call__(self, arg=None):
        if arg == None:
            return self
        
        return HelpResult(arg)

class Notebook:
    def __init__(self, path=[]):
        global _counter
        
        self.__prefix = "__reinteract" + str(_counter)
        _counter += 1

        self.__path = path
        self.__modules = {}

        self.__root_module = imp.new_module(self.__prefix)
        self.__root_module.path = path
        sys.modules[self.__prefix] = self.__root_module
        
    def set_path(self, path):
        if path != self.__path:
            self.__path = path
            self.__root_module.path = path
            self.__reset_all_modules()

    def __reset_all_modules(self):
        for (name, module) in enumerate(self.__modules):
            del sys.modules[self.__prefix + "." + name]

    def reset_module_by_filename(self, filename):
        for (name, module) in enumerate(self.__modules):
            if module.__filename__ == filename:
                del sys.modules[self.__prefix + "." + name]
                del self.__modules[name]
                return module

    def __load_local_module(self, fullname, f, pathname, description):
        prefixed = self.__prefix + "." + fullname
        
        # Trick ... to change the builtins array for the module we are about
        # to load, we stick an empty module initialized the way we want into
        # sys.modules and count on imp.load_module() finding that and doing
        # the rest of the loading into that module

        new = imp.new_module(prefixed)
        #Is this still necessary???
        #new.__dict__['__builtins__'] = self.create_builtins()
        
        assert not prefixed in sys.modules
        sys.modules[prefixed] = new
        result =  imp.load_module(prefixed, f, pathname, description)
        assert result == new
        
        return result

    def __find_and_load(self, fullname, name, parent=None, local=None):
        if parent == None:
            assert local == None
            try:
                f, pathname, description = imp.find_module(name, self.__path)
                local = True
            except ImportError:
                f, pathname, description = imp.find_module(name)
                local = False
        else:
            assert local != None
            f, pathname, description = imp.find_module(name, parent.__path__)

        try:
            if local:
                module = self.__load_local_module(fullname, f, pathname, description)
                self.__modules[name] = module
            else:
                module = imp.load_module(fullname, f, pathname, description)

            if parent != None:
                parent.__dict__[name] = module
        finally:
            if f != None:
                f.close()

        return module, local
        
    def __import_recurse(self, names):
        fullname = ".".join(names)
        
        try:
            return self.__modules[fullname], True
        except KeyError:
            pass
        
        try:
            return sys.modules[fullname], False
        except KeyError:
            pass

        if len(names) == 1:
            module, local = self.__find_and_load(fullname, names[-1])
        else:
            parent, local = self.__import_recurse(names[0:-1])
            module, _ = self.__find_and_load(fullname, names[-1], parent=parent, local=local)

        return module, local

    def __ensure_from_list_item(self, fullname, fromname, module, local):
        if fromname == "*": # * inside __all__, ignore
            return
        
        if not isinstance(fromname, basestring):
            raise TypeError("Item in from list is not a string")
        
        try:
            getattr(module, fromname)
        except AttributeError:
            self.__find_and_load(fullname + "." + fromname, fromname, parent=module, local=local)
        
    def do_import(self, name, globals=None, locals=None, fromlist=None, level=None):
        names = name.split('.')
        
        module, local =  self.__import_recurse(names)
        
        if fromlist != None:
            # In 'from a.b import c', if a.b.c doesn't exist after loading a.b, The built-in
            # __import__ will try to load a.b.c as a module; do the same here.
            for fromname in fromlist:
                if fromname == "*":
                    try:
                        all = getattr(module, "__all__")
                        for allname in all:
                            self.__ensure_from_list_item(name, allname, module, local)
                    except AttributeError:
                        pass
                else:
                    self.__ensure_from_list_item(name, fromname, module, local)
                            
            return module
        elif local:
            return self.__modules[names[0]]
        else:
            return sys.modules[names[0]]

    def create_globals(self):
        g = copy.copy(globals())
        g['__reinteract_notebook'] = self
        g['help'] = _Helper()
        return g

if __name__ == '__main__':
    import copy
    import os
    import tempfile

    base = tempfile.mkdtemp("", "shell_buffer")
    
    def cleanup():
        for root, dirs, files in os.walk(base, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))

    def cleanup_pyc():
        # Not absolutely necessary, but makes things less confusing if we do
        # this between tests
        for root, dirs, files in os.walk(base, topdown=False):
            for name in files:
                if name.endswith(".pyc"):
                    os.remove(os.path.join(root, name))
                
    def write_file(name, contents):
        absname = os.path.join(base, name)
        dirname = os.path.dirname(absname)
        try:
            os.makedirs(dirname)
        except:
            pass

        f = open(absname, "w")
        f.write(contents)
        f.close()

    def do_test(import_text, evaluate_text, expected):
        nb = Notebook(path=[base])

        scope = create_globals()
        
        exec import_text in scope
        result = eval(evaluate_text, scope)

        if result != expected:
            raise AssertionError("Got '%s', expected '%s'" % (result, expected))

        cleanup_pyc()

    try:
        write_file("mod1.py", "a = 1")
        write_file("package1/__init__.py", "__all__ = ['mod2']")
        write_file("package1/mod2.py", "b = 2")
        write_file("package2/__init__.py", "")
        write_file("package2/mod3.py", "import package1.mod2\nc = package1.mod2.b + 1")

        do_test("import mod1", "mod1.__file__", os.path.join(base, "mod1.py"))

        do_test("import mod1", "mod1.a", 1)
        do_test("import mod1 as m", "m.a", 1)
        do_test("from mod1 import a", "a", 1)
        do_test("from mod1 import a as a2", "a2", 1)

        do_test("import package1.mod2", "package1.mod2.b", 2)
        do_test("import package1.mod2 as m", "m.b", 2)
        do_test("from package1 import mod2", "mod2.b", 2)
        do_test("from package1 import *", "mod2.b", 2)

        # http://www.reinteract.org/trac/ticket/5
        do_test("import package2.mod3", "package2.mod3.c", 3)
    finally:
        cleanup()
