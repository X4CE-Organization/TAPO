# Building standalone TAPO executables

TAPO itself is an interpreter, not a native compiler. The release archives wrap
the Python interpreter and the TAPO runtime into a single executable (macOS and
Linux) or a small portable directory with a native launcher (Windows).

## macOS (Apple Silicon)

```bash
python3 -m venv /tmp/tapo-build-venv
/tmp/tapo-build-venv/bin/pip install pyinstaller==6.22.3
/tmp/tapo-build-venv/bin/pyinstaller --clean --noconfirm \
  --distpath dist/macos-arm64 --workpath build/macos tapo.spec
```

The result is `dist/macos-arm64/tapo` (Mach-O arm64).

## Linux (x86-64)

Build inside a Python 3.9 container so the resulting ELF does not depend on the
host's Python installation:

```bash
docker run --rm --platform linux/amd64 \
  -v "$PWD:/work" -w /work \
  docker.m.daocloud.io/library/python:3.9-slim \
  bash -lc '
    apt-get update && apt-get install -y binutils
    pip install pyinstaller==6.22.3
    PYTHONPATH=src python -m tapo test
    pyinstaller --clean --noconfirm \
      --distpath dist/linux-x64 --workpath build/linux tapo.spec
  '
```

The result is `dist/linux-x64/tapo` (ELF x86-64, glibc).

## Windows (portable x86-64)

Windows uses the official embeddable Python distribution and a tiny C launcher.
The launcher forwards every argument to `python.exe tapo_run.py ...`, so options
such as `-e` work exactly like they do on macOS/Linux.

1. Download and unpack
   `https://www.python.org/ftp/python/3.9.13/python-3.9.13-embed-amd64.zip`.
2. Keep `python.exe`, `python39.dll`, `python39.zip` and edit `python39._pth`:

   ```text
   python39.zip
   .
   Lib\site-packages
   import site
   ```

3. Copy the runtime:

   ```text
   Lib/site-packages/tapo/   <- src/tapo
   std/                      <- std/
   tapo_run.py               <- tools/windows/tapo_run.py
   ```

4. Compile the launcher with a mingw-w64 cross compiler:

   ```bash
   x86_64-w64-mingw32-gcc -O2 -o tapo.exe tools/windows/launcher.c -lshell32
   ```

   Zig works too:

   ```bash
   zig cc -target x86_64-windows-gnu -O2 -o tapo.exe \
     tools/windows/launcher.c -lshell32
   ```

5. Run `tapo.exe version`, `tapo.exe -e "println(1)"` and a script before
   packaging the directory.

## Release layout

The release folder contains:

```text
TAPO-0.0.2/
├── macos-arm64/tapo
├── linux-x64/tapo
├── windows-x64/tapo.exe + runtime files
├── examples/
├── README.txt
├── SHA256SUMS.txt
└── LICENSE
```

The exact commands used for a release are kept in the project history and in
`tapo.spec`. The Windows build is verified for PE layout and imports on macOS;
run it on a real Windows machine before publishing a release.
