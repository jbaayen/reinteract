/* -*- mode: C; c-basic-offset: 4; indent-tabs-mode: nil; -*- */
/* See comment in ThunkPython.h for what this is about */

#include <dlfcn.h>
#include <stdlib.h>

#include "ThunkPython.h"

#define concat(x,y) x#y

#define LOOKUP_SYMBOL(s)                                        \
    do {                                                        \
        python_thunks.thunk_##s = dlsym(handle, #s);            \
        if (python_thunks.thunk_##s == NULL) {                  \
            fprintf(stderr, "Cannot find symbol %s\n", #s);     \
            return 0;                                           \
        }                                                       \
    }                                                           \
    while (0)

static void *
dlopen_framework(const char *framework_dir)
{
    static const char *library_path = "Versions/2.5/Python";
    char *buf = malloc(strlen(framework_dir) + 1 + strlen(library_path) + 1);
    if (!buf)
        return NULL;

    strcpy(buf, framework_dir);
    strcat(buf, "/");
    strcat(buf, library_path);

    void *handle = dlopen(buf, RTLD_GLOBAL | RTLD_LAZY);

    free(buf);
    if (handle)
        fprintf(stderr, "%s\n", buf);

    return handle;
}

int
init_thunk_python()
{
    const char *framework_dir = getenv("PYTHON_FRAMEWORK_DIR");
    void *handle = NULL;

    if (framework_dir)
        handle = dlopen_framework(framework_dir);

    if (!handle)
        handle = dlopen_framework("/Library/Frameworks/Python.framework");

    if (!handle)
        handle = dlopen_framework("/System/Library/Frameworks/Python.framework");

    if (!handle) {
        fprintf(stderr, "Cannot find path to Python framework\n");
        return 0;
    }

    LOOKUP_SYMBOL(PyArg_ParseTuple);
    LOOKUP_SYMBOL(PyErr_Occurred);
    LOOKUP_SYMBOL(PyErr_Occurred);
    LOOKUP_SYMBOL(PyErr_Print);
    LOOKUP_SYMBOL(PyErr_SetString);
    LOOKUP_SYMBOL(PyGILState_Ensure);
    LOOKUP_SYMBOL(PyGILState_Release);
    LOOKUP_SYMBOL(PyImport_ImportModule);
    LOOKUP_SYMBOL(PyModule_AddObject);
    LOOKUP_SYMBOL(PyObject_CallFunction);
    LOOKUP_SYMBOL(PyObject_CallMethod);
    LOOKUP_SYMBOL(PyObject_GetAttrString);
    LOOKUP_SYMBOL(PyObject_SetAttrString);
    LOOKUP_SYMBOL(PySequence_SetSlice);
    LOOKUP_SYMBOL(PyString_FromString);
    LOOKUP_SYMBOL(PySys_SetArgv);
    LOOKUP_SYMBOL(PyType_GenericNew);
    LOOKUP_SYMBOL(PyType_IsSubtype);
    LOOKUP_SYMBOL(PyType_Ready);
    LOOKUP_SYMBOL(Py_BuildValue);
    LOOKUP_SYMBOL(Py_InitModule4);
    LOOKUP_SYMBOL(Py_Initialize);
    LOOKUP_SYMBOL(Py_Finalize);
    LOOKUP_SYMBOL(_Py_NoneStruct);
    LOOKUP_SYMBOL(_Py_TrueStruct);
    LOOKUP_SYMBOL(_Py_ZeroStruct);
    LOOKUP_SYMBOL(PyExc_RuntimeError);
    LOOKUP_SYMBOL(PyExc_TypeError);

    return 1;
}
