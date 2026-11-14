/*
 * TAPO Windows launcher.
 *
 * This small console program locates the portable Python runtime that sits
 * next to it, then forwards every command-line argument to:
 *
 *     python.exe tapo_run.py <args...>
 *
 * Keeping the executable name separate from python.exe is important: Python
 * parses options such as -e before sitecustomize runs, so renaming python.exe
 * cannot support the full TAPO command line.
 */
#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shellapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <wchar.h>

static wchar_t *g_buffer = NULL;
static size_t g_length = 0;
static size_t g_capacity = 0;

static void fail(const wchar_t *message) {
    fwprintf(stderr, L"TAPO: %ls\n", message);
}

static void ensure_capacity(size_t extra) {
    size_t needed = g_length + extra + 1;
    if (needed <= g_capacity) return;
    size_t next = g_capacity ? g_capacity : 256;
    while (next < needed) next *= 2;
    wchar_t *grown = (wchar_t *)realloc(g_buffer, next * sizeof(wchar_t));
    if (!grown) {
        fail(L"out of memory");
        exit(1);
    }
    g_buffer = grown;
    g_capacity = next;
}

static void append_char(wchar_t ch) {
    ensure_capacity(1);
    g_buffer[g_length++] = ch;
    g_buffer[g_length] = L'\0';
}

/* Append one argument using the quoting rules understood by CommandLineToArgvW. */
static void append_argument(const wchar_t *argument) {
    append_char(L'"');
    int backslashes = 0;
    for (const wchar_t *p = argument; *p; ++p) {
        if (*p == L'\\') {
            ++backslashes;
        } else {
            if (*p == L'"') {
                for (int i = 0; i < backslashes * 2 + 1; ++i) append_char(L'\\');
                append_char(L'"');
            } else {
                for (int i = 0; i < backslashes; ++i) append_char(L'\\');
                append_char(*p);
            }
            backslashes = 0;
        }
    }
    for (int i = 0; i < backslashes * 2; ++i) append_char(L'\\');
    append_char(L'"');
    append_char(L' ');
}

int main(void) {
    SetConsoleOutputCP(CP_UTF8);
    SetConsoleCP(CP_UTF8);

    wchar_t executable[MAX_PATH * 2];
    DWORD length = GetModuleFileNameW(NULL, executable, MAX_PATH * 2);
    if (length == 0 || length >= MAX_PATH * 2) {
        fail(L"cannot locate the TAPO launcher");
        return 1;
    }
    wchar_t *slash = wcsrchr(executable, L'\\');
    if (!slash) {
        fail(L"cannot locate the TAPO directory");
        return 1;
    }
    *slash = L'\0';

    wchar_t python[MAX_PATH * 2];
    wchar_t script[MAX_PATH * 2];
    if (swprintf(python, MAX_PATH * 2, L"%ls\\python.exe", executable) < 0 ||
        swprintf(script, MAX_PATH * 2, L"%ls\\tapo_run.py", executable) < 0) {
        fail(L"path is too long");
        return 1;
    }

    int argc = 0;
    wchar_t **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (!argv) {
        fail(L"cannot read the command line");
        return 1;
    }

    append_argument(python);
    append_argument(script);
    for (int i = 1; i < argc; ++i) append_argument(argv[i]);

    SetEnvironmentVariableW(L"PYTHONUTF8", L"1");
    SetEnvironmentVariableW(L"PYTHONIOENCODING", L"utf-8");

    STARTUPINFOW startup;
    PROCESS_INFORMATION process;
    ZeroMemory(&startup, sizeof(startup));
    startup.cb = sizeof(startup);
    ZeroMemory(&process, sizeof(process));

    BOOL started = CreateProcessW(
        python,
        g_buffer,
        NULL,
        NULL,
        TRUE,
        0,
        NULL,
        NULL,
        &startup,
        &process
    );
    LocalFree(argv);
    if (!started) {
        fwprintf(stderr, L"TAPO: cannot start %ls (error %lu)\n", python, GetLastError());
        return 1;
    }

    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD code = 1;
    GetExitCodeProcess(process.hProcess, &code);
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    free(g_buffer);
    return (int)code;
}
