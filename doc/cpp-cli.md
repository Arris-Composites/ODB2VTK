# C++ command line

Build the Release executable and add the Abaqus runtime DLL directory to PATH
as described in the [build guide](cpp-build.md). ODBs must be compatible with
the installed SDK. From the repository root:

```powershell
$env:PATH = 'C:\ABAQUS\2025\EstProducts\win_b64\code\bin;' + $env:PATH
cpp/build/native/Release/ODB2VTK.exe --help
cpp/build/native/Release/ODB2VTK.exe --header 1 --odbFile C:/work/Job-1.odb
cpp/build/native/Release/ODB2VTK.exe --header 0 --odbFile C:/work/Job-1.odb --instance Part-1 --step Step-1:0,1 --format binary --writeHistory 1 --suffix _binary
cpp/build/native/Release/ODB2VTK.exe --header 0 --odbFile C:/work/Job-1.odb --instance Part-1 --step Step-1:0,1 --writePVD 1 --suffix _binary
```

Replace `Part-1` with an actual instance name from the header JSON. The second
command writes `Job-1.json`. The third writes binary VTUs and history under
`Job-1_binary`; the fourth adds its PVD without rewriting any VTUs.

| Flag | Meaning/default |
| --- | --- |
| `--header 0\|1` | Required; 1 writes JSON, 0 exports selected data |
| `--odbFile FILE` | Required existing input file |
| `--instance NAME...` | Required for data; preserves instance order |
| `--step STEP:0,1...` | Required for data; preserves step and frame order |
| `--suffix TEXT` | Empty by default |
| `--format ascii\|binary` | ASCII by default; binary is uncompressed appended raw |
| `--writeHistory 0\|1` | Default 0; 1 also writes history once |
| `--writePVD 0\|1` | Default 0; 1 selects collection-only mode |
| `-h`, `--help` | Help without source creation/SDK API initialization |

Normal frame export writes **no PVD**, matching Python's CLI. Collection-only
mode requires every selected VTU to exist and leaves its bytes and modification
time unchanged. It can also write history with `--writeHistory 1`. Header mode
ignores instance/step selection and does not write history or a collection.

Use explicit comma-separated frame indices; ranges, negative values, repeated
frames, repeated steps and repeated instances are rejected. Step names may
contain colons; the final colon separates the frame list. Multiple step tokens
follow `--step`, for example `--step Step-2:1,0 Step-1:0,1`.
Single-value flags support `--flag=value`; use that form for suffixes beginning
with a dash. Windows uses a wide-character entry point to retain Unicode
arguments, including suffixes. Quotes protect paths and suffixes containing spaces.

The native parser deliberately rejects repeated flags and abbreviated flag names;
Python's argparse currently permits some of those forms. Required flags must be
spelled fully. There is no native `--jobs` or Python-worker receipt protocol.
Parallel coordination remains a separate follow-up.

Statuses are 0 for success, 2 for arguments/selections and 1 for runtime failures.
Errors go to stderr. On a later failure, `Completed before failure` lists files
already published, including prior history output. Source closure occurs before
successful return. Complete output preflight precedes history/frame publication,
so a known frame/collection conflict cannot leave newly written history behind.

## Reproduce validation

In a NumPy/VTK environment with Abaqus on PATH, use a fresh output directory:

```powershell
python cpp/validation/validate_cli.py --exe cpp/build/native/Release/ODB2VTK.exe --odb C:/work/Job-1.odb --instance Part-1 --output C:/temp/cpp-cli-check
```

The tool runs native processes and the public Python CLI in Abaqus processes,
checks their statuses, compares both formats plus JSON/CSV/PVD, verifies default
behavior, and deliberately exercises preflight and locked-file failures. Its
Python wrapper records the public `main()` status because the Abaqus launcher
may mask Python exits. Arguments are transported through JSON to prevent the
Windows batch launcher from changing Unicode before Python parses them. No
Python production parsing/conversion code is patched.

For a generated multi-step/instance fixture:

```powershell
abaqus python cpp/validation/create_cli_fixture.py C:/temp/two-step.odb
python cpp/validation/validate_cli.py --exe cpp/build/native/Release/ODB2VTK.exe --odb C:/temp/two-step.odb --instance B A --steps Step-2:1,0 Step-1:0,1 --output C:/temp/cpp-cli-order
```

See [Phase 4 results](cpp-phase4-results.md) for the validated environment and limits.
