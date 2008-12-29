# Copyright 2008 Owen Taylor
# Copyright 2008 Kai Willadsen
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

import copy
import inspect

def default_filter(baseclass, name):
    """Filter out attributes that should be excluded from a proxy class.

    @param baseclass: the class being proxied
    @param name: the C{baseclass} attribute being filtered
    @returns: False if C{baseclass.name} should not be proxied
    """
    if not inspect.ismethod(getattr(baseclass, name)):
        return False
    if name.startswith('_'):
        return False
    return True

class ReplayException(Exception):
    """
    Exception class to help with locating an exception-causing call for a
    recorded class. Note that information such as line numbers is not used,
    so it's currently only slightly helpful.
    """
    def __init__(self, orig_exception, orig_call):
        self.orig_exception = orig_exception
        self.orig_call = orig_call

    def __str__(self):
        exc_string = "on %(call_name)s()\n%(exc_name)s: %(exc_desc)s" % {
                           'call_name': self.orig_call[0],
                           'exc_name': self.orig_exception.__class__,
                           'exc_desc': str(self.orig_exception) }
        return exc_string

class RecordedObject(object):
    """
    A RecordedObject is a proxy for another object that Reinteract can't copy
    properly. It is designed for objects that are built up over a series of
    calls and then evaluated. This class should be used by subclassing
    C{RecordedObject} and then calling L{_set_target_class} on the new subclass.

    Because of the way that calls are recorded and replayed, exceptions from
    called methods will not be thrown until C{_replay} is called. To catch
    simple errors earlier, argument-checking support can be provided in
    subclasses by implementing a C{_check_} method for a given call. For
    example, to add argument checking for the C{plot} method, you would
    add the C{_check_plot} method to your subclass.
    """
    def __init__(self):
        self._recreation_calls = []

    def _replay(self, target):
        # At any point in time, an object's state can be recreated by
        # _replay()ing the calls recorded on it.
        for (call, args, kwargs) in self._recreation_calls:
            func = getattr(target, call)
            try:
                func(*args, **kwargs)
            except Exception, e:
                raise ReplayException(e, (call, args, kwargs))

    def __copy__(self):
        new = self.__class__()
        new._recreation_calls = copy.copy(self._recreation_calls)
        return new

    def _check_call(self, name, args, kwargs, spec):
        # This tries to duplicate some of python's argument checking logic
        num_args     = len(spec[0]) if spec[0] else 0
        use_varargs  = True if spec[1] else False
        use_kwargs   = True if spec[2] else False
        num_defaults = len(spec[3]) if spec[3] else 0

        given_args = len(args) + 1 # self not included
        min_args = num_args - num_defaults
        exact_args = num_defaults == 0 and not use_varargs
        if exact_args and given_args != num_args:
            raise TypeError("%(name)s() takes exactly %(reqd)d arguments (%(nargs)d given)" % {
                'name': name,
                'reqd': num_args,
                'nargs': given_args })
        elif given_args < min_args:
            raise TypeError("%(name)s() takes at least %(reqd)d arguments (%(nargs)d given)" % {
                'name': name,
                'reqd': min_args,
                'nargs': given_args })
        elif given_args > num_args and not use_varargs:
            raise TypeError("%(name)s() takes at most %(reqd)d arguments (%(nargs)d given)" % {
                'name': name,
                'reqd': num_args,
                'nargs': given_args })

        if kwargs and not use_kwargs:
            raise TypeError("%(name)s() got an unexpected keyword argument '%(kw)s'" % {
                'name': name,
                'kw': kwargs.iterkeys().next()})

    @classmethod
    def _set_target_class(cls, baseclass, attr_filter=default_filter):
        """
        Give class proxy methods from C{baseclass}, which can later be replayed.

        @param baseclass: the class to proxy
        @param attr_filter: a filter function for C{baseclass} attributes

          The C{attr_filter} function should take the baseclass and attribute
          name as arguments, and return True if an attribute should be
          included. This should be used to remove attributes that it makes
          little sense to include (e.g., C{__class__} or getters) or that you
          want to override. See L{default_filter}.
        """
        def _create_proxy_method(name):
            spec = inspect.getargspec(getattr(baseclass, name))
            try:
                func = getattr(cls, '_check_' + name)
            except AttributeError:
                func = getattr(cls, '_check_call')

            def record(self, *args, **kwargs):
                func(self, name, args, kwargs, spec)
                self._recreation_calls.append((name, args, kwargs))
            return record

        whitelist = (d for d in dir(baseclass) if attr_filter(baseclass, d))

        for attr in whitelist:
            if hasattr(cls, attr):
                raise AttributeError('%s already has attribute %s' % (cls, attr))
            record = _create_proxy_method(attr)
            record.__name__ = attr
            record.__doc__ = getattr(baseclass, attr).__doc__
            setattr(cls, attr, record)

