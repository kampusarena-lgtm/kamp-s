"""Windows APIs: interactive input, one instance, and kill-on-close miner jobs."""
import ctypes as c
from ctypes import wintypes as w
import csv
import io
import math
import os
import subprocess


class LASTINPUTINFO(c.Structure):
    _fields_ = [('cbSize', w.UINT), ('dwTime', w.DWORD)]


class WTS_SESSION_INFO(c.Structure):
    _fields_ = [('SessionId', w.DWORD), ('pWinStationName', w.LPWSTR), ('State', c.c_int)]


class BASIC_LIMIT(c.Structure):
    _fields_ = [('PerProcessUserTimeLimit', c.c_int64), ('PerJobUserTimeLimit', c.c_int64),
                ('LimitFlags', w.DWORD), ('MinimumWorkingSetSize', c.c_size_t),
                ('MaximumWorkingSetSize', c.c_size_t), ('ActiveProcessLimit', w.DWORD),
                ('Affinity', c.c_size_t), ('PriorityClass', w.DWORD), ('SchedulingClass', w.DWORD)]


class IO_COUNTERS(c.Structure):
    _fields_ = [(name, c.c_uint64) for name in ('ReadOperationCount', 'WriteOperationCount',
                'OtherOperationCount', 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]


class EXTENDED_LIMIT(c.Structure):
    _fields_ = [('BasicLimitInformation', BASIC_LIMIT), ('IoInfo', IO_COUNTERS),
                ('ProcessMemoryLimit', c.c_size_t), ('JobMemoryLimit', c.c_size_t),
                ('PeakProcessMemoryUsed', c.c_size_t), ('PeakJobMemoryUsed', c.c_size_t)]


class STARTUPINFO(c.Structure):
    _fields_ = [('cb', w.DWORD), ('lpReserved', w.LPWSTR), ('lpDesktop', w.LPWSTR),
                ('lpTitle', w.LPWSTR), ('dwX', w.DWORD), ('dwY', w.DWORD),
                ('dwXSize', w.DWORD), ('dwYSize', w.DWORD), ('dwXCountChars', w.DWORD),
                ('dwYCountChars', w.DWORD), ('dwFillAttribute', w.DWORD),
                ('dwFlags', w.DWORD), ('wShowWindow', w.WORD), ('cbReserved2', w.WORD),
                ('lpReserved2', c.POINTER(c.c_byte)), ('hStdInput', w.HANDLE),
                ('hStdOutput', w.HANDLE), ('hStdError', w.HANDLE)]


class PROCESS_INFORMATION(c.Structure):
    _fields_ = [('hProcess', w.HANDLE), ('hThread', w.HANDLE), ('dwProcessId', w.DWORD), ('dwThreadId', w.DWORD)]


class Windows:
    def __init__(self):
        if os.name != 'nt':
            raise RuntimeError('Live probes require Windows 11; use --simulate for policy testing')
        self.k = c.WinDLL('kernel32', use_last_error=True)
        self.u = c.WinDLL('user32', use_last_error=True)
        self.t = c.WinDLL('wtsapi32', use_last_error=True)
        specs = {
            'CreateMutexW': ([c.c_void_p, w.BOOL, w.LPCWSTR], w.HANDLE),
            'CreateJobObjectW': ([c.c_void_p, w.LPCWSTR], w.HANDLE),
            'CloseHandle': ([w.HANDLE], w.BOOL),
            'OpenProcess': ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            'QueryFullProcessImageNameW': ([w.HANDLE, w.DWORD, w.LPWSTR, c.POINTER(w.DWORD)], w.BOOL),
            'SetInformationJobObject': ([w.HANDLE, c.c_int, c.c_void_p, w.DWORD], w.BOOL),
            'AssignProcessToJobObject': ([w.HANDLE, w.HANDLE], w.BOOL),
            'TerminateJobObject': ([w.HANDLE, w.UINT], w.BOOL),
            'TerminateProcess': ([w.HANDLE, w.UINT], w.BOOL),
            'ResumeThread': ([w.HANDLE], w.DWORD),
            'WaitForSingleObject': ([w.HANDLE, w.DWORD], w.DWORD),
            'GetExitCodeProcess': ([w.HANDLE, c.POINTER(w.DWORD)], w.BOOL),
            'ProcessIdToSessionId': ([w.DWORD, c.POINTER(w.DWORD)], w.BOOL),
            'WTSGetActiveConsoleSessionId': ([], w.DWORD),
            'GetTickCount64': ([], c.c_uint64),
            'CreateProcessW': ([w.LPCWSTR, w.LPWSTR, c.c_void_p, c.c_void_p, w.BOOL,
                w.DWORD, c.c_void_p, w.LPCWSTR, c.POINTER(STARTUPINFO), c.POINTER(PROCESS_INFORMATION)], w.BOOL)
        }
        for name, (args, result) in specs.items():
            fn = getattr(self.k, name); fn.argtypes = args; fn.restype = result
        self.u.GetLastInputInfo.argtypes = [c.POINTER(LASTINPUTINFO)]
        self.u.GetLastInputInfo.restype = w.BOOL
        self.u.GetForegroundWindow.argtypes = []
        self.u.GetForegroundWindow.restype = w.HWND
        self.u.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]
        self.u.GetWindowThreadProcessId.restype = w.DWORD
        self.u.SetProcessDpiAwarenessContext.argtypes = [c.c_void_p]
        self.u.SetProcessDpiAwarenessContext.restype = w.BOOL
        # Capture physical pixels. If another component already set awareness,
        # Windows may reject this; the image size/aspect checks remain active.
        self.u.SetProcessDpiAwarenessContext(c.c_void_p(-4))
        self.u.OpenInputDesktop.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        self.u.OpenInputDesktop.restype = w.HANDLE
        self.u.CloseDesktop.argtypes = [w.HANDLE]
        self.u.CloseDesktop.restype = w.BOOL
        self.u.SendMessageTimeoutW.argtypes = [w.HWND, w.UINT, c.c_size_t, c.c_ssize_t,
            w.UINT, w.UINT, c.POINTER(c.c_size_t)]
        self.u.SendMessageTimeoutW.restype = c.c_ssize_t
        self.t.WTSEnumerateSessionsW.argtypes = [w.HANDLE, w.DWORD, w.DWORD,
            c.POINTER(c.POINTER(WTS_SESSION_INFO)), c.POINTER(w.DWORD)]
        self.t.WTSEnumerateSessionsW.restype = w.BOOL
        self.t.WTSFreeMemory.argtypes = [c.c_void_p]
        self.t.WTSFreeMemory.restype = None

    def check(self, ok):
        if not ok:
            raise c.WinError(c.get_last_error())

    def mutex(self):
        handle = self.k.CreateMutexW(None, False, 'Global\\CafeMiningAgent-v1')
        self.check(handle)
        if c.get_last_error() == 183:
            self.k.CloseHandle(handle)
            raise RuntimeError('Another CafeMining agent is running on this computer')
        return handle

    def input_state(self):
        sid = w.DWORD()
        self.check(self.k.ProcessIdToSessionId(os.getpid(), c.byref(sid)))
        if sid.value != self.k.WTSGetActiveConsoleSessionId() or sid.value == 0:
            return False, None
        sessions = c.POINTER(WTS_SESSION_INFO)(); count = w.DWORD()
        self.check(self.t.WTSEnumerateSessionsW(None, 0, 1, c.byref(sessions), c.byref(count)))
        try:
            active = [sessions[i].SessionId for i in range(count.value) if sessions[i].State == 0]
            if active != [sid.value]:
                return False, None
        finally:
            self.t.WTSFreeMemory(sessions)
        desktop = self.u.OpenInputDesktop(0, False, 1)
        if not desktop:
            return False, None
        self.u.CloseDesktop(desktop)
        info = LASTINPUTINFO(c.sizeof(LASTINPUTINFO), 0)
        self.check(self.u.GetLastInputInfo(c.byref(info)))
        elapsed = ((self.k.GetTickCount64() & 0xffffffff) - info.dwTime) & 0xffffffff
        return True, elapsed / 1000

    def monitor_power(self, off):
        # SC_MONITORPOWER, local interactive desktop. This does not sleep the PC.
        result = c.c_size_t()
        self.check(self.u.SendMessageTimeoutW(0xffff, 0x112, 0xf170,
            2 if off else -1, 0x2 | 0x8, 1000, c.byref(result)))

    def foreground_executable(self):
        hwnd = self.u.GetForegroundWindow()
        self.check(hwnd)
        pid = w.DWORD()
        self.check(self.u.GetWindowThreadProcessId(hwnd, c.byref(pid)))
        process = self.k.OpenProcess(0x1000, False, pid.value)
        self.check(process)
        try:
            length = w.DWORD(32768)
            buffer = c.create_unicode_buffer(length.value)
            self.check(self.k.QueryFullProcessImageNameW(process, 0, buffer, c.byref(length)))
            return buffer.value
        finally:
            self.k.CloseHandle(process)

    def request_reboot(self):
        # No /f: do not forcibly discard application data. No delayed shutdown
        # command is left behind that could fire after a new customer arrives.
        exe = os.path.join(os.environ['SystemRoot'], 'System32', 'shutdown.exe')
        subprocess.run([exe, '/r', '/t', '0', '/d', 'p:4:1', '/c',
            'CafeMining: verified empty table after customer departure'],
            check=True, capture_output=True, timeout=5, creationflags=0x08000000)


def gpu_state(exe):
    output = subprocess.run([str(exe), '--query-gpu=name,memory.total,temperature.gpu,power.draw',
        '--format=csv,noheader,nounits'], check=True, capture_output=True, text=True,
        timeout=2, creationflags=0x08000000 if os.name == 'nt' else 0).stdout
    rows = []
    for row in csv.reader(io.StringIO(output)):
        if len(row) != 4:
            raise ValueError('Malformed NVIDIA telemetry')
        name, memory, temp, power = (x.strip() for x in row)
        memory, temp = float(memory), float(temp)
        if not all(math.isfinite(x) for x in (memory, temp)) or memory <= 0:
            raise ValueError('Missing NVIDIA sensor')
        # Power is optional on older drivers; it is never used as total wall power.
        try:
            watts = float(power)
            if not math.isfinite(watts) or watts < 0:
                watts = None
        except ValueError:
            watts = None
        rows.append({'name': name, 'memory_mib': memory, 'temperature_c': temp, 'gpu_watts': watts})
    if len(rows) != 1:
        raise ValueError('This cafe profile expects exactly one NVIDIA GPU')
    return rows


class MinerJob:
    """Assign a SUSPENDED process before it can run or create child processes."""
    def __init__(self, api, exe, args, log_path):
        import msvcrt
        self.api, self.job, self.process = api, None, None
        self.stdout = None; self.stdin = None
        k = api.k
        self.job = k.CreateJobObjectW(None, None)
        api.check(self.job)
        pi = PROCESS_INFORMATION()
        try:
            limits = EXTENDED_LIMIT()
            limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
            api.check(k.SetInformationJobObject(self.job, 9, c.byref(limits), c.sizeof(limits)))
            self.stdout = open(log_path, 'ab', buffering=0)
            self.stdin = open('NUL', 'rb', buffering=0)
            out_handle = msvcrt.get_osfhandle(self.stdout.fileno())
            in_handle = msvcrt.get_osfhandle(self.stdin.fileno())
            os.set_handle_inheritable(out_handle, True)
            os.set_handle_inheritable(in_handle, True)
            si = STARTUPINFO()
            si.cb = c.sizeof(si); si.dwFlags = 0x100
            si.hStdInput = in_handle; si.hStdOutput = out_handle; si.hStdError = out_handle
            command = c.create_unicode_buffer(subprocess.list2cmdline([str(exe), *args]))
            api.check(k.CreateProcessW(str(exe), command, None, None, True,
                0x4 | 0x200 | 0x4000, None, str(exe.parent), c.byref(si), c.byref(pi)))
            self.process = pi.hProcess
            api.check(k.AssignProcessToJobObject(self.job, self.process))
            if k.ResumeThread(pi.hThread) == 0xffffffff:
                api.check(False)
        except BaseException:
            if pi.hProcess:
                k.TerminateProcess(pi.hProcess, 1)
            self.close()
            raise
        finally:
            if pi.hThread:
                k.CloseHandle(pi.hThread)
            if self.stdout:
                os.set_handle_inheritable(msvcrt.get_osfhandle(self.stdout.fileno()), False)
            if self.stdin:
                os.set_handle_inheritable(msvcrt.get_osfhandle(self.stdin.fileno()), False)

    def running(self):
        result = self.api.k.WaitForSingleObject(self.process, 0)
        if result == 0xffffffff:
            self.api.check(False)
        return result == 258

    def close(self):
        if self.job:
            self.api.k.TerminateJobObject(self.job, 0)
            self.api.k.CloseHandle(self.job)
            self.job = None
        if self.process:
            self.api.k.WaitForSingleObject(self.process, 3000)
            self.api.k.CloseHandle(self.process)
            self.process = None
        for stream in (self.stdout, self.stdin):
            if stream:
                stream.close()
        self.stdout = self.stdin = None
