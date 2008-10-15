/* -*- mode: ObjC; c-basic-offset: 4; indent-tabs-mode: nil; -*-
 *
 * Copyright 2008 Owen Taylor
 *
 * This file is part of Reinteract and distributed under the terms
 * of the BSD license. See the file COPYING in the Reinteract
 * distribution for full details.
 *
 ************************************************************************/

#include <config.h>

#include "ThunkPython.h"
#include <gdk/gdk.h>
#include <gdk/gdkquartz.h>
#include <pygobject.h>
#include <dlfcn.h>

#import "MenuController.h"

/* This file implements the reinteract.native_main_menu object, which is
 * glue between the menu and the PyGTK code. The interface here is:
 *
 * class NativeMainMenu:
 *     def do_action(self, action_name):
 *        """An Action was selected"""
 *        pass # Override in subclass
 *
 *     def enable_action(self, action_name):
 *        """Enable the action with the specified name"""
 *        [...]
 *
 *     def disable_action(self, action_name):
 *        """Disable the action with the specified name"""
 *        [...]
 *
 *     def get_action_names(self):
 *        """Return a list of all action names in the menu"""
 *        [...]
 *
 *     def handle_key_press(self, event):
 *        """Check key equivalents and activate a menu item if appropriate
 *
 *        @returns: True if a menu item was activated
 *        """
 *        [...]
 *
 * You use this class by deriving from it and instantiating a singleton
 * copy. Instantiating more than one copy of a derived class will produce
 * undefined and probably bad results.
 */

typedef struct {
    PyObject_HEAD
    MenuController *controller;
} pyNativeMainMenu;

static void
pyNativeMenu_actionCallback(NSString *actionName, void *data)
{
    pyNativeMainMenu *slf = data;

    PyGILState_STATE gstate;
    gstate = PyGILState_Ensure();

    PyObject *result = PyObject_CallMethod((PyObject *)slf, "do_action", "s", [actionName UTF8String]);
    if (result == NULL)
        PyErr_Print();
    else
        Py_DECREF(result);

    PyGILState_Release(gstate);
}

static int
pyNativeMainMenu_init(pyNativeMainMenu *slf, PyObject *args, PyObject *kwds)
{
    if (!PyArg_ParseTuple(args, ""))
        return -1;

    slf->controller = [[MenuController alloc] init];
    [slf->controller setActionCallback:pyNativeMenu_actionCallback callbackData:slf];

    // Create the MainMenu object from the NIB file and set our controller
    // object as the delegate
    NSNib *nib = [[NSNib alloc] initWithNibNamed: @"MainMenu" bundle:nil];
    if (![nib instantiateNibWithOwner:slf->controller topLevelObjects:nil]){
        PyErr_SetString(PyExc_RuntimeError, "Can't instantiate MainMenu.nib");
        return -1;
    }

    // Once the nib has been loaded and the objects created (the menu
    // is automatically added to the global NSApp), we don't need the data
    // of the NIB any more
    [nib release];

    [slf->controller addActionsFromMenu:[NSApp mainMenu]];

    // finishLaunching actually shows the menu. There might be some
    // justification for splitting calling this out into a separate menu
    [NSApp finishLaunching];

    return 0;
}

static PyObject *
pyNativeMainMenu_enable_action(pyNativeMainMenu *slf, PyObject *args)
{
    const char *action_name;

    if (!PyArg_ParseTuple(args, "s", &action_name))
        return NULL;

    [slf->controller enableAction:[NSString stringWithUTF8String:action_name]];

    Py_RETURN_NONE;
}

static PyObject *
pyNativeMainMenu_disable_action(pyNativeMainMenu *slf, PyObject *args)
{
    const char *action_name;

    if (!PyArg_ParseTuple(args, "s", &action_name))
        return NULL;

    [slf->controller disableAction:[NSString stringWithUTF8String:action_name]];

    Py_RETURN_NONE;
}

static PyObject *
pyNativeMainMenu_get_action_names(pyNativeMainMenu *slf)
{
    NSArray *names = [slf->controller actionNames];
    PyObject *result = PyList_New([names count]);
    int i;

    if (!result)
        return NULL;

    for (i = 0; i < [names count]; i++) {
        const char *name = [[names objectAtIndex:i] UTF8String];
        PyObject *py_name = PyString_FromString(name);
        if (!py_name) {
            Py_DECREF(result);
            return NULL;
        }

        PyList_SetItem(result, i, py_name); // Steals reference to py_name
    }

    return result;
}

static NSEvent *
event_get_nsevent(GdkEvent *event)
{
    static NSEvent *(*ptr_gdk_quartz_event_get_nsevent) (GdkEvent*);
    if (!ptr_gdk_quartz_event_get_nsevent) {
        ptr_gdk_quartz_event_get_nsevent = dlsym(RTLD_DEFAULT, "gdk_quartz_event_get_nsevent");
        if (!ptr_gdk_quartz_event_get_nsevent) {
            fprintf(stderr, "Can't get pointer to gdk_quartz_event_get_nsevent()");
            return NULL;
        }
    }

    return (*ptr_gdk_quartz_event_get_nsevent) (event);
}

/* All key events get intercepted by the gtk-quartz event loop before
 * normal processing by NSApplication can deliver them to the menu bar.
 * For this reason, we have to pass key events received on our toplevel
 * windows to the menu bar ourselves.
 *
 * Luckily the original NSEvent can be retrieved from the GdkEvent so
 * we don't have to synthesize a new event ourselves.
 */
static PyObject *
pyNativeMainMenu_handle_key_press(pyNativeMainMenu *slf, PyObject *args)
{
    PyObject *py_event;

    if (!PyArg_ParseTuple(args, "O", &py_event))
        return NULL;

#if 0
    /* Doing it this way would require us to call pygobject_init() first
     * which is possible but requires us to thunk more Python API to make
     * that (inline) functin happy. pyg_boxed_get() is just casting
     * and structure access, so doesn't require pygobject_init()
     */
    if (!pyg_boxed_check(py_event, GDK_TYPE_EVENT)) {
        PyErr_SetString(PyExc_TypeError, "Argument must be a GdkEvent");
        return NULL;
    }
#else
    PyObject *module = PyImport_ImportModule("gtk.gdk");
    PyObject *attribute = PyObject_GetAttrString(module, "Event");
    if (!PyObject_TypeCheck(py_event, (PyTypeObject *)attribute)) {
        PyErr_SetString(PyExc_TypeError, "Argument must be a GdkEvent");
        return NULL;
    }
#endif

    NSEvent *event = event_get_nsevent(pyg_boxed_get(py_event, GdkEvent));

    if ([[NSApp mainMenu] performKeyEquivalent:event])
        Py_RETURN_TRUE;
    else
        Py_RETURN_FALSE;
}

static PyMethodDef pyNativeMainMenu_methods[] = {
    {"enable_action", (PyCFunction)pyNativeMainMenu_enable_action, METH_VARARGS,
     "Enable the menu item with the specified action name"
    },
    {"disable_action", (PyCFunction)pyNativeMainMenu_disable_action, METH_VARARGS,
     "Disable the menu item with the specified action name"
    },
    {"get_action_names", (PyCFunction)pyNativeMainMenu_get_action_names, METH_NOARGS,
     "Return a list of all action names"
    },
    {"handle_key_press", (PyCFunction)pyNativeMainMenu_handle_key_press, METH_VARARGS,
     "Perform any key equivalents for the given key event"
    },
    {NULL}  /* Sentinel */
};

static PyTypeObject pyNativeMainMenuType = {
    PyObject_HEAD_INIT(NULL)
    0,                                 /*ob_size*/
    "reinteract.native_main_menu.NativeMainMenu", /*tp_name*/
    sizeof(pyNativeMainMenu),            /*tp_basicsize*/
    0,                                 /*tp_itemsize*/
    0,                                 /*tp_dealloc*/
    0,                                 /*tp_print*/
    0,                                 /*tp_getattr*/
    0,                                 /*tp_setattr*/
    0,                                 /*tp_compare*/
    0,                                 /*tp_repr*/
    0,                                 /*tp_as_number*/
    0,                                 /*tp_as_sequence*/
    0,                                 /*tp_as_mapping*/
    0,                                 /*tp_hash */
    0,                                 /*tp_call*/
    0,                                 /*tp_str*/
    0,                                 /*tp_getattro*/
    0,                                 /*tp_setattro*/
    0,                                 /*tp_as_buffer*/
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE, /*tp_flags*/
    "Native Interface to the main menu", /* tp_doc */
    0,                                 /* tp_traverse */
    0,                                 /* tp_clear */
    0,                                 /* tp_richcompare */
    0,                                 /* tp_weaklistoffset */
    0,                                 /* tp_iter */
    0,                                 /* tp_iternext */
    pyNativeMainMenu_methods,            /* tp_methods */
    0,                                 /* tp_members */
    0,                                 /* tp_getset */
    0,                                 /* tp_base */
    0,                                 /* tp_dict */
    0,                                 /* tp_descr_get */
    0,                                 /* tp_descr_set */
    0,                                 /* tp_dictoffset */
    (initproc)pyNativeMainMenu_init,   /* tp_init */
    0,                                 /* tp_alloc */
    0,                                 /* tp_new */
};

static PyMethodDef native_main_menu_methods[] = {
    { NULL } /* No module level methods */
};

PyMODINIT_FUNC
init_py_native_main_menu(void)
{
    PyObject *m;

    if (PyType_Ready(&pyNativeMainMenuType) < 0)
        return;

    // We need to load the reinteract package so we have the namespace
    // for reinteract.native_main_menu. We don't actually need anything
    // from reinteract.__init__.py, which is empty.

    PyObject *tmp = PyImport_ImportModule("reinteract");
    if (tmp)
        Py_DECREF(tmp);
    else {
        PyErr_Print();
        return;
    }

    m = Py_InitModule("reinteract.native_main_menu", native_main_menu_methods);

    pyNativeMainMenuType.tp_new = PyType_GenericNew;

    Py_INCREF(&pyNativeMainMenuType);
    PyModule_AddObject(m, "NativeMainMenu", (PyObject *)&pyNativeMainMenuType);
}
