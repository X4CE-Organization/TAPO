TAPO 0.0.3 — standalone builds
==============================

TAPO is an expression-oriented, object-oriented language with aspects, pattern
matching, algebraic enums, generators, `with`, `defer`, numeric range patterns
and a batteries-included library.

New in 0.0.3:
  - `--sandbox` capability security for reads/writes/imports
  - `--max-steps`, `--max-depth`, `--timeout` resource limits
  - `--audit` runtime capability log and `tapo audit` static audit
  - `tapo bench` micro-benchmarks
  - per-class method lookup cache with mixin invalidation

Choose one:

  macos-arm64/tapo          macOS 11+ on Apple Silicon (arm64)
  linux-x64/tapo            Linux x86-64 (glibc)
  windows-x64/tapo.exe      Windows 10/11 x86-64 (portable, no Python needed)

Examples:

  ./macos-arm64/tapo examples/toolkit.tapo
  ./linux-x64/tapo examples/defer.tapo
  windows-x64\tapo.exe examples\generators.tapo

Security example:

  ./macos-arm64/tapo --sandbox --allow-write ./out app.tapo
  ./macos-arm64/tapo --sandbox --max-steps 200000 --timeout 5 app.tapo

Run the test suite with a binary:

  ./macos-arm64/tapo test tests
  windows-x64\tapo.exe test tests

If macOS or Linux blocks the binary because it is unsigned, mark it executable
and, on macOS, allow it in System Settings > Privacy & Security:

  chmod +x macos-arm64/tapo linux-x64/tapo

The Windows folder contains a bundled Python 3.9 runtime and a small native
launcher. It is verified for PE layout and imports on macOS, but should be run on
a real Windows machine before wide distribution.

Documentation is in docs/; examples are in examples/.

TAPO 0.0.3 · © 2026 X4CE · MIT
