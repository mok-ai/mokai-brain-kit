#!/usr/bin/env python3
"""autostart.py — Windows HKCU Run key helper (brain kit background services).

Idempotent register/unregister/list. Prefix "BrainKit" identifies our own
entries so list_entries doesn't leak unrelated user autoruns.

CLI:
  python autostart.py register BrainKitSynthDaemon  "wscript C:/brainkit/start_synth.vbs"
  python autostart.py unregister BrainKitSynthDaemon
  python autostart.py list
"""
import argparse
import sys

BRAINKIT_PREFIX = "BrainKit"


class _WinregBackend:
    """Real winreg-backed HKCU Run access. Only imported on Windows."""

    _RUN_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"

    def _open(self, write=False):
        import winreg  # lazy — non-Windows envs skip
        access = winreg.KEY_SET_VALUE if write else winreg.KEY_READ
        return winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._RUN_PATH, 0,
                              access | winreg.KEY_READ)

    def set(self, name, value):
        import winreg
        with self._open(write=True) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)

    def get(self, name):
        import winreg
        try:
            with self._open() as k:
                v, _ = winreg.QueryValueEx(k, name)
                return v
        except FileNotFoundError:
            return None

    def delete(self, name):
        import winreg
        try:
            with self._open(write=True) as k:
                winreg.DeleteValue(k, name)
            return True
        except FileNotFoundError:
            return False

    def enumerate(self):
        import winreg
        out = {}
        try:
            with self._open() as k:
                i = 0
                while True:
                    try:
                        n, v, _ = winreg.EnumValue(k, i)
                        out[n] = v
                        i += 1
                    except OSError:
                        break
        except OSError:
            pass
        return out


def _default_backend():
    return _WinregBackend()


def register(name: str, command: str, *, reg_backend=None) -> str:
    """Register a command in HKCU Run. Returns the command string."""
    r = reg_backend or _default_backend()
    r.set(name, command)
    return command


def unregister(name: str, *, reg_backend=None) -> bool:
    """Remove an entry from HKCU Run. Returns True if removed, False if not found."""
    r = reg_backend or _default_backend()
    return r.delete(name)


def list_entries(*, reg_backend=None) -> dict:
    """List only BrainKit-prefixed entries from HKCU Run."""
    r = reg_backend or _default_backend()
    return {n: v for n, v in r.enumerate().items() if n.startswith(BRAINKIT_PREFIX)}


def main():
    ap = argparse.ArgumentParser(description="HKCU Run key helper")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_reg = sub.add_parser("register")
    p_reg.add_argument("name")
    p_reg.add_argument("command")
    p_unreg = sub.add_parser("unregister")
    p_unreg.add_argument("name")
    sub.add_parser("list")
    args = ap.parse_args()
    if args.cmd == "register":
        register(args.name, args.command)
        print(f"[OK] registered: {args.name}")
    elif args.cmd == "unregister":
        removed = unregister(args.name)
        print(f"[{'OK' if removed else 'skip'}] {args.name}")
    else:
        for n, v in list_entries().items():
            print(f"  {n} = {v}")


if __name__ == "__main__":
    main()
