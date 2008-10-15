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

#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <stdarg.h>

#import "MenuController.h"
#import "pyNativeMainMenu.h"

static void
die(const char *format, ...)
{
    if (PyErr_Occurred())
        PyErr_Print();

    va_list vap;
    va_start(vap, format);
    vfprintf(stderr, format, vap);
    va_end(vap);

    fprintf(stderr, "\n");

    exit(1);
}

static PyObject *
getModuleAttribute(const char *moduleName, const char *attributeName)
{
    PyObject *module = PyImport_ImportModule(moduleName);
    if (module == NULL)
        die("Cannot import %s module", moduleName);

    PyObject *attribute = PyObject_GetAttrString(module, attributeName);
    if (attribute == NULL)
        die("Cannot get %s.%s", moduleName, attributeName);

    Py_DECREF(module);

    return attribute;
}

static BOOL
dirExists(NSString *path)
{
    struct stat s;

    if (stat([path UTF8String], &s) != 0)
        return FALSE;

    return S_ISDIR(s.st_mode);
}

static BOOL
fileExists(NSString *path)
{
    struct stat s;

    if (stat([path UTF8String], &s) != 0)
        return FALSE;

    return TRUE;
}

int main(int argc, char *argv[])
{
    NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];

    NSBundle *mainBundle = [NSBundle mainBundle];
    NSString *resourcePath = [mainBundle resourcePath];

    /* This allocates the shared NSApplication object and stores it in the
     * NSApp global variable */
    [NSApplication sharedApplication];

#ifdef USE_PYTHON_THUNKs
    /* Find the right version of Python and fill the vtable of "thunks"
     * to that library */
    if (!init_thunk_python())
        exit(1);
#endif

    /* Normal Python initialization */
    Py_Initialize();
    PySys_SetArgv(argc, (char **)argv);

    /* Set up sys.path and locate special directories. We do this in Python
     * on other platforms; conceptually program this replaces Reinteract.py
     * and so has that responsibility */
    PyObject *sysPath = getModuleAttribute("sys", "path");

    NSString *dialogsDir;
    NSString *examplesDir;

    /* If we are being run from the full bundle, then our Python files, etc.
     * are inside the Resources directory of the bundle. If we running from
     * the shell bundle we create uninstalled, then there is a special marker
     * file indicating that, and we we expect to find stuff up one directory
     * from the top of the bundle. Otherwise, the location of files is based
     * on the installation directory that is configured.
     */
    NSString *pythonDir = [resourcePath stringByAppendingPathComponent:@"python"];
    if (dirExists(pythonDir)) {
        dialogsDir = [resourcePath stringByAppendingPathComponent:@"dialogs"];
        examplesDir = [resourcePath stringByAppendingPathComponent:@"examples"];

        NSString *externalDir = [resourcePath stringByAppendingPathComponent:@"external"];
        PyObject *toInsert = Py_BuildValue("(ss)", [pythonDir UTF8String], [externalDir UTF8String]);
        PySequence_SetSlice(sysPath, 0, 0, toInsert);
        Py_DECREF(toInsert);

        /* Set environment variables used by dependencies */
        NSString *libdir = [resourcePath stringByAppendingPathComponent:@"lib"];
        NSString *sysconfdir = [resourcePath stringByAppendingPathComponent:@"etc"];
        NSString *pixbufModuleFile = [sysconfdir stringByAppendingPathComponent:@"gtk-2.0/gdk-pixbuf.loaders"];
        setenv("GDK_PIXBUF_MODULE_FILE", [pixbufModuleFile UTF8String], 1);
        setenv("GTK_EXE_PREFIX", [resourcePath UTF8String], 1);
        setenv("GTK_DATA_PREFIX", [resourcePath UTF8String], 1);
        setenv("GTK_SYSCONFDIR", [sysconfdir UTF8String], 1);
        NSString *imModuleFile = [sysconfdir stringByAppendingPathComponent:@"gtk-2.0/gtk.immodules"];
        setenv("GTK_IM_MODULE_FILE", [imModuleFile UTF8String], 1);
        setenv("PANGO_LIBDIR", [libdir UTF8String], 1);
        setenv("PANGO_SYSCONFDIR", [sysconfdir UTF8String], 1);
    } else if (fileExists([resourcePath stringByAppendingPathComponent:@"UNINSTALLED"])) {
        NSString *baseDir = [[mainBundle bundlePath] stringByDeletingLastPathComponent];
        dialogsDir = [baseDir stringByAppendingPathComponent:@"dialogs"];
        examplesDir = [baseDir stringByAppendingPathComponent:@"examples"];

        pythonDir = [baseDir stringByAppendingPathComponent:@"lib"];

        PyObject *toInsert = Py_BuildValue("(s)", [pythonDir UTF8String]);
        PySequence_SetSlice(sysPath, 0, 0, toInsert);
        Py_DECREF(toInsert);
    } else {
        dialogsDir = @DIALOGSDIR;
        examplesDir = @EXAMPLESDIR;
    }

    /* Set attributes in the global_settings objects */

    PyObject *globalSettings = getModuleAttribute("reinteract.global_settings", "global_settings");

    PyObject *pyDialogsDir = PyString_FromString([dialogsDir UTF8String]);
    PyObject_SetAttrString(globalSettings, "dialogs_dir", pyDialogsDir);
    Py_DECREF(pyDialogsDir);

    PyObject *pyExamplesDir = PyString_FromString([examplesDir UTF8String]);
    PyObject_SetAttrString(globalSettings, "examples_dir", pyExamplesDir);
    Py_DECREF(pyExamplesDir);

    PyObject_SetAttrString(globalSettings, "main_menu_mode", Py_True);

    /* Initialize reinteract.NativeMainMenu module; this provides two-way
     * communication between Python and the menu */
    init_py_native_main_menu();

    /* We're all set, now run run reinteract.main.main() */

    PyObject *main_module = getModuleAttribute("reinteract.main", "main");
    PyObject *result = PyObject_CallFunction(main_module, "");
    if (result  == NULL)
        die("Error calling main() function");

    Py_DECREF(result);

    Py_Finalize();

    [pool drain];

    return 0;
}
