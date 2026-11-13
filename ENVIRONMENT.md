# Reproduction environment

The reference execution used Linux x86-64, Python 3.12, a C compiler supporting
C11 and Z3 4.13.3.0. It used NumPy 2.3.5, python-sat 1.8.dev24 and cryptography
50.0.0 for the original S1 experiments. S2's synthetic and cached-input
analyses use only the Python standard library and a C compiler.

For the complete S1 plus S2 route, create an isolated Python environment:

```bash
python3.12 -m venv ../paper-m-environment
. ../paper-m-environment/bin/activate
python -m pip install -r requirements.txt
python run_reproduction.py full --output ../paper-m-full
```

Separate system requirements are Bash, GNU coreutils, a C compiler (`cc`) and
a loadable `libz3.so.4`. The package does not install system software or request
administrator privileges. A Python package bearing the Z3 name is not by
itself a check that the expected native library is available. The original
receipt records the native Z3 version actually loaded.

The `figures` mode additionally needs LibreOffice (`soffice` or `libreoffice`)
and Poppler's `pdftoppm` on PATH. Figure generation alone uses Python's standard
library. The retained exports were checked with LibreOfficeDev
26.8.0.0.alpha0. Inspect layout after exporting with another application build.

Do not run the Python audits with `-O`. Their assertions are intentional.
The top-level and S2 runners reject that mode. All example output paths point
outside the repository and must be unused. The runner refuses to overwrite
an existing result directory or to put generated data inside the repository.

Compiler and platform differences can change binary hashes and timing values.
New binaries are validated against independent Python calculations before
their empirical results are used. The required deterministic data counts and
verdicts must match; performance comparisons require their own stated design.
