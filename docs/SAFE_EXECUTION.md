# Safe execution

Every property below is structural, not advisory. There is no configuration flag that relaxes them.

## Executable allowlist

`ALLOWED_EXECUTABLES` maps a **key** to candidate binary names. A caller selects a provider version;
it can never supply a path, a name, or a new entry. `resolve_executable("bash")` and
`resolve_executable("/usr/bin/python3")` both resolve to nothing — tested.

## No shell, ever

Commands are argv arrays passed to `subprocess.run` with `shell=False`. `SafeCommandDescriptor`
carries an executable *key* plus a tuple of literal arguments produced by a reviewed input builder.
No caller-authored text is ever interpolated into a solver control file; templates are code-defined.

## Filesystem containment

Working directories are server-generated hex tokens under one controlled root. `safe_join` validates
each component against a strict pattern and re-resolves the final path to prove it stays inside the
root. `../escape`, `..`, `a/../../b`, `/etc/passwd`, dotfiles and names with spaces are all rejected.

## Environment allowlist

Only `PATH`, `LANG`, `LC_ALL`, `HOME`, `TMPDIR` and `OMP_NUM_THREADS` reach a child process. Database
URLs, tokens and cloud credentials are dropped — tested with a planted variable.

## Bounds

Wall-time timeout (default 60s, hard maximum 900s), stdout capped at 64 KB, stderr at 32 KB,
artifacts at 256 KB, 10 steps per workflow, 10 jobs per synchronous request, 100 route-preview targets.
The `ResourceRequest` record is explicit about which bounds are *enforced* versus *metadata only*.

## No network

Nothing is downloaded during a run. Potentials, pseudopotentials, thermodynamic databases and model
weights must be registered and approved in advance, or the route refuses.

## The compute-backend seam

`ComputeBackend` exists so a queue or HPC backend can be added later without changing callers. Phase 6
ships exactly one: `local_bounded_v1`, synchronous and local.
