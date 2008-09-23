#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdlib.h>

#include "Python.h"
#include <string.h>

static void fail(void) {
    MessageBoxA(NULL, "Cannot determine location of Reinteract.pyw from EXE name", NULL, MB_OK);
    exit(1);
}

int WINAPI WinMain(HINSTANCE hInstance,
                   HINSTANCE hPrevInstance,
                   LPSTR lpCmdLine,
                   int nCmdShow)
{
#define BUF_SIZE 1024
    char buf[BUF_SIZE];
    char *argv[2] = { "Reinteract.exe", "Reinteract.pyw" };
    char *dirend;
    
    int count = GetModuleFileNameA(NULL, buf, BUF_SIZE);
    if (count == 0 || count == BUF_SIZE)
	fail();

    /* This will fail in some exotic cases like C:Reinteract.exe */
    dirend = buf + count;
    while (dirend > buf && *(dirend - 1) != '/' && *(dirend - 1) != '\\')
	dirend--;

    /* Change to the the EXE directory so that we find our DLL's despite Python
     * using LOAD_WITH_ALTERED_SEARCH_PATH. Modifying %PATH% would be another
     * option. Doing it this way also simplifies passing in Reinteract.pyw
     * as the first argument.
     */
    if (dirend > buf) {
	*dirend = '\0';
	SetCurrentDirectory(buf);
    }

    return Py_Main(2, argv);
}
