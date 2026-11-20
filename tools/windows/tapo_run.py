"""Portable Windows entry point for TAPO.

The C launcher next to this file invokes:

    python.exe tapo_run.py <arguments...>

The embedded Python distribution is deliberately isolated; add the bundled
package directory explicitly before importing the interpreter.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "Lib", "site-packages"))
# Make the bundled standard library discoverable even when the host Python
# executable lives outside this portable directory.
os.environ.setdefault("TAPO_PATH", os.path.join(HERE, "std"))

from tapo.cli import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
