# Entari load check

The installation-and-loading workflow is inspired by
[BalconyJH/noneload](https://github.com/BalconyJH/noneload). This repository uses
an Entari-specific probe: Entari metadata and configuration, Launart service
lifecycle, Letoderea contract injection, atomic plugin reload, and unload
cleanup. The probe is tailored to HTMLRender and does not depend on NoneBot.

`check.py` installs this checkout as an ordinary distribution in a temporary
`uv` environment and then runs `runner.py` in a separate process. The runner is
copied into the isolated working directory, imports the installed wheel, loads
the plugin through Entari, and inspects its metadata, caller contracts, and
lifecycle. It does not import from `src/` or use an editable installation.

The local composite action is
[`../actions/entari-load-check/action.yml`](../actions/entari-load-check/action.yml).
The compatibility workflow
[`../workflows/entari-compat.yml`](../workflows/entari-compat.yml) runs these
profiles:

| Profile | Extra | Configuration under test |
| --- | --- | --- |
| `core` | none | Provider disabled; preparation and caller contracts load |
| `takumi` | `takumi` | Native provider warmup and worker-backed cleanup |
| `graphics` | `pillow,skia` | Both raster-scene capabilities compose independently |

Every installed-load profile runs on Python 3.11, 3.12, 3.13, and 3.14. A
separate Python 3.12 job runs the real Chromium integration test, including
Markdown math.

The lifecycle probe runs Entari's plugin service with a minimal local host
service. It does not connect to a Satori server or validate a live bot account.
Provider-disabled checks still exercise service preparation and cleanup;
Takumi warmup additionally initializes the native provider.

## Command line

```text
python check.py \
  --python-version 3.12 \
  --module-name entari_plugin_htmlrender \
  --project-name entari-plugin-htmlrender \
  --package . \
  --extras takumi \
  --config-file config.json \
  --timeout 300 \
  --result-file result.json
```

`--package` is resolved before the checker changes to its temporary directory.
The package is installed without `-e`; the requested extras are merged into the
local PEP 508 specifier. `--extras all` selects the project's declared `all`
extra.

The configuration file contains one JSON object and is passed to the runner from
the isolated directory. Its contents are not written to the result JSON, GitHub
outputs, or the step summary. The result records only `config_present`, bounded
and redacted process output, installed versions, and the runner's metadata.

The checker exits successfully only when all of these are true:

1. A fresh `uv` environment selects the requested Python.
2. The local project and requested extras install from a non-editable spec.
3. Distribution metadata can be inspected by its selected interpreter.
4. The isolated runner exits zero and writes `ok: true`.
5. Entari loads the installed module and the lifecycle probe completes.

The workflow's job timeouts bound the complete operation. The
checker applies its timeout to each isolated environment command and terminates
the runner's process tree on expiry. Diagnostic JSON is uploaded even when the
load check fails.

The checker regression tests run in a separate job. To run them locally without
the project's optional dependencies:

```sh
uv run --no-project --python 3.12 python -m unittest discover \
  -s .github/entari-load-check -p 'test_*.py' -v
```

## Extending the profiles

Keep the matrix small and tied to an integration boundary. Add a profile only
when it exercises a distinct optional distribution, native runtime, lifecycle,
or platform requirement. Full version coverage already belongs to the
repository's pytest and coverage workflows; this workflow complements them with
installed, non-editable loading.
