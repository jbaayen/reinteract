import imp
import sys

_counter = 1

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
    
    def __import_recurse(self, names, fromlist):
        name = ".".join(names)
        
        try:
            return self.__modules[name], True
        except KeyError:
            pass
        
        try:
            return sys.modules[name], False
        except KeyError:
            pass

        if len(names) == 1:
            parent = None
            try:
                f, pathname, description = imp.find_module(name, self.__path)
                local = True
            except ImportError:
                f, pathname, description = imp.find_module(name)
                local = False
        else:
            child_names = names[0:-1]
            parent, local = self.__import_recurse(names[0:-1], fromlist)
            f, pathname, description = imp.find_module(names[-1], parent.__path__)

        try:
            if local:
                module = imp.load_module(self.__prefix + "." + name, f, pathname, description)
                self.__modules[name] = module
            else:
                print name, f, pathname, description
                module = imp.load_module(name, f, pathname, description)

            if parent != None:
                parent.__dict__[names[-1]] = module
        finally:
            if f != None:
                f.close()

        return module, local
        
    def do_import(self, name, globals=None, locals=None, fromlist=None, level=None):
        names = name.split('.')
        
        module, local =  self.__import_recurse(names, fromlist)
        if fromlist != None:
            return module
        elif local:
            return self.__modules[names[0]]
        else:
            return sys.modules[names[0]]
