/* -*- mode: C; c-basic-offset: 4; indent-tabs-mode: nil; -*-
 *
 * Copyright 2008 Owen Taylor
 *
 * This file is part of Reinteract and distributed under the terms
 * of the BSD license. See the file COPYING in the Reinteract
 * distribution for full details.
 *
 ************************************************************************/

/*
 * This header file is used to redirect the parts of the Python API that we
 * we use to a VTable of symbols dynamically looked up via dlopen/dlsym
 * and avoid statically linking to the Python framework. This allows us to
 * create a single executable that works both with the python.org installer
 * for OS X 10.4 and the system version of Python shipped with OS X 10.5.
 *
 * The downside is that we are bypassing the standard system linker facilities
 * so could be more easily tripped up by ABI changes. And this is a pain
 * to maintain. Note that anything added below also needs to be added in
 * ThunkPython.c.
 */

#ifndef __THUNK_PYTHON_H__
#define __THUNK_PYTHON_H__

#include <Python.h>

#ifndef PACKAGE_NAME
#error "config.h must be included before ThunkPython.h"
#endif

#ifdef USE_PYTHON_THUNKS

struct {
    int (*thunk_PyArg_ParseTuple)(PyObject *, const char *, ...);
    PyObject * (*thunk_PyErr_Occurred)(void);
    void (*thunk_PyErr_Print)(void);
    void (*thunk_PyErr_SetString)(PyObject *, const char *);
    PyGILState_STATE (*thunk_PyGILState_Ensure)(void);
    void (*thunk_PyGILState_Release)(PyGILState_STATE);
    PyObject * (*thunk_PyImport_ImportModule)(const char *name);
    PyObject * (*thunk_PyList_New)(Py_ssize_t);
    int (*thunk_PyList_SetItem)(PyObject *, Py_ssize_t, PyObject *);
    int (*thunk_PyModule_AddObject)(PyObject *, const char *, PyObject *);
    PyObject * (*thunk_PyObject_CallFunction)(PyObject *callable_object, char *format, ...);
    PyObject * (*thunk_PyObject_CallMethod)(PyObject *o, char *m, char *format, ...);
    PyObject * (*thunk_PyObject_GetAttrString)(PyObject *o, const char *attr_name);
    int (*thunk_PyObject_SetAttrString)(PyObject *o, char *attr_name, PyObject *v);

    int (*thunk_PySequence_SetSlice)(PyObject *o, Py_ssize_t i1, Py_ssize_t i2, PyObject *v);
    PyObject * (*thunk_PyString_FromString)(const char *);

    void (*thunk_PySys_SetArgv)(int, char **);

    PyObject * (*thunk_PyType_GenericNew)(PyTypeObject *, PyObject *, PyObject *);
    int (*thunk_PyType_IsSubtype)(PyTypeObject *, PyTypeObject *);
    int (*thunk_PyType_Ready)(PyTypeObject *);
    PyObject * (*thunk_Py_BuildValue)(const char *, ...);
    PyObject * (*thunk_Py_InitModule4)(const char *name, PyMethodDef *methods,
                                       const char *doc, PyObject *self,
                                       int apiver);
    void (*thunk_Py_Initialize)(void);
    void (*thunk_Py_Finalize)(void);

    PyObject *thunk__Py_NoneStruct;
    PyIntObject *thunk__Py_TrueStruct;
    PyIntObject *thunk__Py_ZeroStruct;
    PyObject ** thunk_PyExc_RuntimeError;
    PyObject ** thunk_PyExc_TypeError;
} python_thunks;

#define PyArg_ParseTuple (python_thunks.thunk_PyArg_ParseTuple)
#define PyErr_Occurred (python_thunks.thunk_PyErr_Occurred)
#define PyErr_Occurred (python_thunks.thunk_PyErr_Occurred)
#define PyErr_Print (python_thunks.thunk_PyErr_Print)
#define PyErr_SetString (python_thunks.thunk_PyErr_SetString)
#define PyGILState_Ensure (python_thunks.thunk_PyGILState_Ensure)
#define PyGILState_Release (python_thunks.thunk_PyGILState_Release)
#define PyImport_ImportModule (python_thunks.thunk_PyImport_ImportModule)
#define PyList_New (python_thunks.thunk_PyList_New)
#define PyList_SetItem (python_thunks.thunk_PyList_SetItem)
#define PyModule_AddObject (python_thunks.thunk_PyModule_AddObject)
#define PyObject_CallFunction (python_thunks.thunk_PyObject_CallFunction)
#define PyObject_CallMethod (python_thunks.thunk_PyObject_CallMethod)
#define PyObject_GetAttrString (python_thunks.thunk_PyObject_GetAttrString)
#define PyObject_SetAttrString (python_thunks.thunk_PyObject_SetAttrString)
#define PySequence_SetSlice (python_thunks.thunk_PySequence_SetSlice)
#define PyString_FromString (python_thunks.thunk_PyString_FromString)
#define PySys_SetArgv (python_thunks.thunk_PySys_SetArgv)
#define PyType_GenericNew (python_thunks.thunk_PyType_GenericNew)
#define PyType_IsSubtype (python_thunks.thunk_PyType_IsSubtype)
#define PyType_Ready (python_thunks.thunk_PyType_Ready)
#define Py_BuildValue (python_thunks.thunk_Py_BuildValue)
#define Py_InitModule4 (python_thunks.thunk_Py_InitModule4)
#define Py_Initialize (python_thunks.thunk_Py_Initialize)
#define Py_Finalize (python_thunks.thunk_Py_Finalize)

#define _Py_NoneStruct (*python_thunks.thunk__Py_NoneStruct)
#define _Py_TrueStruct (*python_thunks.thunk__Py_TrueStruct)
#define _Py_ZeroStruct (*python_thunks.thunk__Py_ZeroStruct)
#define PyExc_RuntimeError (*python_thunks.thunk_PyExc_RuntimeError)
#define PyExc_TypeError (*python_thunks.thunk_PyExc_TypeError)

int init_thunk_python();

#endif USE_PYTHON_THUNKS

#endif /* __THUNK_PYTHON_H__ */
