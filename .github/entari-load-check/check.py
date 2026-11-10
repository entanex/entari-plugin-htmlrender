#!/usr/bin/env python3
"""Install an Entari project in isolation and verify that its plugin loads."""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import tomllib
from typing import Any, Final

CANONICALIZE_RE: Final = re.compile(r"[-_.]+")
RESULT_VERSION: Final = 1
SUMMARY_OUTPUT_LIMIT: Final = 12_000
OUTPUT_LIMIT: Final = 64_000
REQUIRED_RUNNER_KEYS: Final = frozenset({"ok", "stage"})
SECRET_MARKERS: Final = (
    "token",
    "secret",
    "password",
    "passwd",
    "private",
    "credential",
    "authorization",
    "cookie",
    "api-key",
    "apikey",
)
ANSI_RE: Final = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class CheckError(RuntimeError):
    """A load-check stage failed in a way that should fail the action."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


@dataclass(frozen=True, slots=True)
class RunningResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        if self.stdout and self.stderr:
            return f"{self.stdout.rstrip()}\n{self.stderr.rstrip()}"
        return self.stdout or self.stderr


@dataclass(slots=True)
class CheckReport:
    stage: str
    ok: bool = False
    module_name: str = ""
    project_name: str = ""
    package: str = "."
    extras: tuple[str, ...] = ()
    config_present: bool = False
    python_version: str = ""
    installed_version: str | None = None
    installed_environment: dict[str, str] = field(default_factory=dict)
    runner: dict[str, object] = field(default_factory=dict)
    output: str = ""
    error: str = ""
    result_file: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "version": RESULT_VERSION,
            "ok": self.ok,
            "stage": self.stage,
            "module_name": self.module_name,
            "project_name": self.project_name,
            "package": self.package,
            "extras": list(self.extras),
            "config_present": self.config_present,
            "python_version": self.python_version,
            "installed_version": self.installed_version,
            "installed_environment": self.installed_environment,
            "runner": self.runner,
            "output": self.output,
            "error": self.error,
            "result_file": self.result_file,
        }


def canonicalize_name(value: str) -> str:
    """Return the PEP 503 normalization of a distribution or extra name."""
    return CANONICALIZE_RE.sub("-", value).lower()


def normalize_module_name(value: str) -> str:
    """Reject values that cannot be passed to the isolated probe."""
    module = value.strip()
    if (
        not module
        or any(character.isspace() for character in module)
        or "/" in module
        or "\\" in module
    ):
        raise CheckError("validate", "module name must be a non-empty import path")
    parts = module.split(".")
    if any(not part.isidentifier() for part in parts):
        raise CheckError("validate", f"invalid module name: {module!r}")
    return module


def normalize_extras(values: Sequence[str] | str | None) -> tuple[str, ...]:
    """Normalize a comma-separated extra list while preserving project names."""
    if values is None:
        return ()
    items = values.split(",") if isinstance(values, str) else list(values)
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        for part in item.split(","):
            extra = part.strip()
            if not extra:
                continue
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", extra):
                raise CheckError("validate", f"invalid extra name: {extra!r}")
            key = canonicalize_name(extra)
            if key not in seen:
                seen.add(key)
                result.append(extra)
    return tuple(result)


def merge_package_extras(
    package: str,
    extras: Sequence[str],
    *,
    known_extras: Sequence[str],
) -> str:
    """Merge extras into a local package spec without enabling editable mode."""
    spec = package.strip() or "."
    base, separator, remainder = spec.partition("[")
    base = base.strip()
    local = base in {".", ".."} or base.startswith(("./", "../", ".\\", "..\\", "/"))
    if not local:
        raise CheckError(
            "validate",
            "the package must be a local path so it can be installed non-editably",
        )

    existing: tuple[str, ...] = ()
    suffix = ""
    if separator:
        closing = remainder.find("]")
        if closing < 0:
            raise CheckError("validate", f"invalid package extra spec: {spec!r}")
        existing = normalize_extras(remainder[:closing])
        suffix = remainder[closing + 1 :].strip()
        if suffix:
            raise CheckError(
                "validate",
                "local package specs may not carry markers after the extras",
            )
    merged = (*existing, *extras)
    deduplicated = tuple(dict.fromkeys(normalize_extras(merged)))
    known = {canonicalize_name(extra) for extra in known_extras}
    unknown = [extra for extra in deduplicated if canonicalize_name(extra) not in known]
    if unknown:
        raise CheckError(
            "metadata",
            "unknown project extras: " + ", ".join(sorted(unknown)),
        )
    if not deduplicated:
        return base
    return f"{base}[{','.join(deduplicated)}]"


def project_metadata(project_root: Path) -> dict[str, Any]:
    """Read only the project table needed to identify the installed package."""
    pyproject = project_root / "pyproject.toml"
    try:
        parsed = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise CheckError("metadata", f"cannot read {pyproject}: {error}") from error
    project = parsed.get("project")
    if not isinstance(project, dict):
        raise CheckError("metadata", f"{pyproject} has no [project] table")
    name = project.get("name")
    if not isinstance(name, str) or not name.strip():
        raise CheckError("metadata", f"{pyproject} has no [project].name")
    optional = project.get("optional-dependencies") or {}
    if not isinstance(optional, dict):
        raise CheckError("metadata", "project.optional-dependencies must be a table")
    return {"name": name.strip(), "optional_dependencies": optional}


def resolve_package(
    *,
    package: str,
    extras: tuple[str, ...],
    project_root: Path,
    project_name: str,
) -> tuple[str, str, str]:
    """Return resolved path, project name, and non-editable install spec."""
    path_text = package.partition("[")[0].strip() or "."
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = project_root / path
    resolved_path = path.resolve()
    if not resolved_path.exists():
        raise CheckError("validate", f"package path does not exist: {resolved_path}")
    metadata = project_metadata(resolved_path)
    actual_name = metadata["name"]
    if project_name and canonicalize_name(project_name) != canonicalize_name(
        actual_name
    ):
        raise CheckError(
            "metadata",
            f"project-name {project_name!r} does not match pyproject name {actual_name!r}",
        )
    declared_extras = tuple(metadata["optional_dependencies"])
    package_extras = normalize_extras(package.partition("[")[2].partition("]")[0])
    install = merge_package_extras(
        str(resolved_path),
        (*package_extras, *extras),
        known_extras=declared_extras,
    )
    return str(resolved_path), actual_name, install


def subprocess_environment(*, isolated: bool) -> dict[str, str]:
    env = os.environ.copy()
    if isolated:
        env["PYTHONNOUSERSITE"] = "1"
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
    return env


def run(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout: float | None,
    isolated: bool = False,
    stage: str = "command",
) -> RunningResult:
    """Run a command, terminating its process group if it exceeds the deadline."""
    process = subprocess.Popen(  # noqa: S603
        list(command),
        cwd=cwd,
        env=subprocess_environment(isolated=isolated),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=os.name != "nt",
        creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        terminate_process_tree(process)
        stdout, stderr = process.communicate()
        raise CheckError(
            stage,
            f"command timed out after {timeout:g} seconds",
        ) from None
    return RunningResult(process.returncode, stdout or "", stderr or "")


def terminate_process_tree(process: subprocess.Popen[str]) -> None:
    """Terminate a child subprocess and any descendants when possible."""
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            taskkill = shutil.which("taskkill")
            if not taskkill:
                process.terminate()
            else:
                subprocess.run(  # noqa: S603
                    [taskkill, "/PID", str(process.pid), "/T", "/F"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
        else:
            os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, OSError, subprocess.TimeoutExpired):
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            process.kill()


def atomic_write_text(path: Path, content: str) -> None:
    """Write UTF-8 JSON or text without exposing a partial destination file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def write_result(path: Path, report: CheckReport) -> None:
    report.result_file = str(path.resolve())
    atomic_write_text(
        path,
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n",
    )


def write_github_output(name: str, value: str) -> None:
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        return
    path = Path(output_file)
    if "\n" in value or "\r" in value:
        delimiter = f"EOF_{name}_{os.getpid()}"
        block = f"{name}<<{delimiter}\n{value}\n{delimiter}\n"
    else:
        block = f"{name}={value}\n"
    with path.open("a", encoding="utf-8") as stream:
        stream.write(block)


def write_step_summary(markdown: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with Path(summary_path).open("a", encoding="utf-8") as stream:
        stream.write(markdown)


def strip_ansi(value: str) -> str:
    return ANSI_RE.sub("", value)


def redact(text: str, secrets: Iterable[str]) -> str:
    sanitized = strip_ansi(text)
    for secret in sorted(secrets, key=len, reverse=True):
        for variant in (
            secret,
            json.dumps(secret)[1:-1],
            secret.replace("\n", "\\n"),
        ):
            if variant:
                sanitized = sanitized.replace(variant, "***")
    for marker in SECRET_MARKERS:
        sanitized = re.sub(
            rf"(?i)({re.escape(marker)}[^\n:=]*[:=]\s*)[^\s,}}\]]+",
            r"\1***",
            sanitized,
        )
    return sanitized


def config_secrets(config: str, parsed: object) -> tuple[str, ...]:
    """Collect config text and scalar strings that must not reach reports."""
    values: list[str] = [config] if config else []

    def visit(value: object) -> None:
        if isinstance(value, str):
            if value:
                values.append(value)
        elif isinstance(value, Mapping):
            for key, item in value.items():
                if isinstance(key, str) and len(key) >= 4:
                    values.append(key)
                visit(item)
        elif isinstance(value, Sequence) and not isinstance(value, str | bytes):
            for item in value:
                visit(item)

    visit(parsed)
    return tuple(dict.fromkeys(values))


def config_keys(parsed: object) -> frozenset[str]:
    """Collect JSON object keys so runner metadata cannot echo config schema."""
    keys: set[str] = set()

    def visit(value: object) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if isinstance(key, str) and key:
                    keys.add(key)
                visit(item)
        elif isinstance(value, Sequence) and not isinstance(value, str | bytes):
            for item in value:
                visit(item)

    visit(parsed)
    return frozenset(keys)


def sanitize_json_value(
    value: object,
    *,
    secrets: Iterable[str],
    sensitive_keys: Iterable[str],
) -> object:
    """Recursively redact config values and schema names from runner JSON."""
    secret_list = tuple(secrets)
    key_list = tuple(sensitive_keys)
    if isinstance(value, Mapping):
        sanitized: dict[str, object] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            if key in key_list or any(
                len(candidate) >= 4 and candidate in key for candidate in key_list
            ):
                key = "***"
            else:
                key = redact(key, secret_list)
            sanitized[key] = sanitize_json_value(
                item,
                secrets=secret_list,
                sensitive_keys=key_list,
            )
        return sanitized
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [
            sanitize_json_value(
                item,
                secrets=secret_list,
                sensitive_keys=key_list,
            )
            for item in value
        ]
    if isinstance(value, str):
        return redact(value, secret_list)
    return value


def sanitize_report_config_leaks(
    report: CheckReport,
    *,
    secrets: Iterable[str],
    sensitive_keys: Iterable[str],
) -> None:
    """Scrub config-tainted free text while retaining verified distribution data."""
    secret_list = tuple(secrets)
    key_list = tuple(sensitive_keys)
    sanitized_runner = sanitize_json_value(
        report.runner,
        secrets=secret_list,
        sensitive_keys=key_list,
    )
    assert isinstance(sanitized_runner, dict)
    report.runner = sanitized_runner
    report.output = bounded_output(redact(report.output, secret_list))
    report.error = redact(report.error, secret_list)


def bounded_output(output: str) -> str:
    if len(output) <= OUTPUT_LIMIT:
        return output
    return (
        output[:SUMMARY_OUTPUT_LIMIT]
        + "\n... output truncated ...\n"
        + output[-SUMMARY_OUTPUT_LIMIT:]
    )


def render_summary(report: CheckReport, *, secrets: Iterable[str]) -> str:
    safe_output = bounded_output(redact(report.output, secrets))
    safe_error = redact(report.error, secrets)
    status = "PASS" if report.ok else "FAIL"
    environment = "\n".join(
        f"- `{name}`: `{value}`"
        for name, value in sorted(report.installed_environment.items())
    )
    runner_exit = report.runner.get("exit_code")
    lines = [
        "## Entari load check",
        "",
        f"- Status: **{status}**",
        f"- Stage: `{report.stage}`",
        f"- Project: `{report.project_name}`",
        f"- Module: `{report.module_name}`",
        f"- Package: `{report.package}`",
        f"- Extras: `{','.join(report.extras) or '<none>'}`",
        f"- Python: `{report.python_version}`",
        f"- Installed version: `{report.installed_version or '<unknown>'}`",
        f"- Runner exit: `{runner_exit if runner_exit is not None else '<not run>'}`",
        f"- Config supplied: `{str(report.config_present).lower()}`",
    ]
    if environment:
        lines.extend(["", "### Installed environment", "", environment])
    if safe_error:
        lines.extend(["", "### Error", "", "```text", safe_error, "```"])
    if safe_output:
        lines.extend(["", "### Sanitized output", "", "```text", safe_output, "```"])
    lines.append("")
    return "\n".join(lines)


def output_github_values(report: CheckReport, result_file: Path) -> None:
    for name, value in (
        ("ok", "true" if report.ok else "false"),
        ("stage", report.stage),
        ("project-name", report.project_name),
        ("module-name", report.module_name),
        ("python-version", report.python_version),
        ("result-file", str(result_file.resolve())),
    ):
        write_github_output(name, value)


def resolve_result_path(
    value: str | None,
    *,
    invocation_cwd: Path,
    work_root: Path,
) -> Path:
    if value:
        path = Path(value).expanduser()
        return path if path.is_absolute() else invocation_cwd / path
    return work_root / "result.json"


def config_payload(path: str | None, *, invocation_cwd: Path) -> tuple[str, bool]:
    if path is None or not path.strip():
        return "", False
    config_path = Path(path).expanduser()
    if not config_path.is_absolute():
        config_path = invocation_cwd / config_path
    try:
        return config_path.read_text(encoding="utf-8"), True
    except OSError as error:
        raise CheckError(
            "config",
            f"cannot read config file: {error.strerror or type(error).__name__}",
        ) from error


def _metadata_probe(
    runner_result: Mapping[str, Any],
    project_name: str,
    installed_version: str | None,
) -> dict[str, str]:
    installed_distribution = runner_result.get("project_name")
    if installed_distribution is not None and (
        not isinstance(installed_distribution, str)
        or canonicalize_name(installed_distribution) != canonicalize_name(project_name)
    ):
        raise CheckError(
            "validate-runner",
            "runner project_name does not match installed distribution metadata",
        )
    runner_version = runner_result.get("installed_version")
    if runner_version is not None and (
        not isinstance(runner_version, str) or not runner_version.strip()
    ):
        raise CheckError(
            "validate-runner",
            "runner installed_version must be a non-empty string when provided",
        )
    if runner_version is not None and runner_version != installed_version:
        raise CheckError(
            "validate-runner",
            "runner installed_version does not match installed distribution metadata",
        )
    installed_environment = runner_result.get("installed_environment") or {}
    if not isinstance(installed_environment, Mapping) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in installed_environment.items()
    ):
        raise CheckError(
            "validate-runner",
            "runner installed_environment must be a string mapping",
        )
    return dict(installed_environment)


def _verify_installed_environment(
    *,
    python: Path,
    environment: Mapping[str, str],
    timeout: float,
    workdir: Path,
) -> dict[str, str]:
    """Read every reported version from the isolated interpreter's metadata."""
    if not environment:
        return {}
    distribution_names = sorted(set(environment) - {"python"})
    probe = (
        "import importlib.metadata as metadata, json, platform, sys; "
        "names = json.loads(sys.argv[1]); "
        "versions = {'python': platform.python_version()}; "
        "missing = [];\n"
        "for name in names:\n"
        "    try:\n"
        "        versions[name] = metadata.version(name)\n"
        "    except metadata.PackageNotFoundError:\n"
        "        missing.append(name)\n"
        "print(json.dumps({'versions': versions, 'missing': missing}))"
    )
    result = run(
        [
            str(python),
            "-I",
            "-c",
            probe,
            json.dumps(distribution_names),
        ],
        cwd=workdir,
        timeout=timeout,
        isolated=True,
        stage="environment",
    )
    if result.returncode != 0:
        raise CheckError(
            "environment",
            "the isolated interpreter could not inspect installed environment metadata",
        )
    try:
        payload = json.loads(result.stdout)
        versions = payload["versions"]
        missing = payload["missing"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise CheckError(
            "environment",
            "installed environment metadata probe returned invalid JSON",
        ) from error
    if not isinstance(versions, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in versions.items()
    ):
        raise CheckError(
            "environment",
            "installed environment metadata probe returned invalid versions",
        )
    if not isinstance(missing, list) or missing:
        raise CheckError(
            "environment",
            "runner reported distributions that are absent from the isolated environment",
        )
    if versions != dict(environment):
        raise CheckError(
            "environment",
            "runner environment metadata does not match the isolated environment",
        )
    return versions


def run_runner(
    *,
    python: Path,
    module_name: str,
    project_name: str,
    timeout: float,
    workdir: Path,
    config: str,
    runner_source: Path,
) -> tuple[RunningResult, dict[str, Any]]:
    runner_result_path = workdir / "runner-result.json"
    runner_result_path.unlink(missing_ok=True)
    config_path = workdir / ".entari-load-check.json"
    atomic_write_text(
        config_path,
        config or "{}\n",
    )
    copied_runner = workdir / "runner.py"
    shutil.copy2(runner_source, copied_runner)
    command = [
        str(python),
        "-I",
        str(copied_runner),
        "--module-name",
        module_name,
        "--project-name",
        project_name,
        "--config-file",
        str(config_path),
        "--result-file",
        str(runner_result_path),
    ]
    process_result = run(
        command,
        cwd=workdir,
        timeout=timeout,
        isolated=True,
        stage="runner",
    )
    if not runner_result_path.is_file():
        raise CheckError(
            "validate-runner",
            "runner exited without writing its result file",
        )
    try:
        payload = json.loads(runner_result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CheckError(
            "validate-runner", f"runner result is invalid JSON: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise CheckError("validate-runner", "runner result must be a JSON object")
    missing = REQUIRED_RUNNER_KEYS - payload.keys()
    if missing:
        raise CheckError(
            "validate-runner",
            "runner result is missing keys: " + ", ".join(sorted(missing)),
        )
    if not isinstance(payload["ok"], bool):
        raise CheckError("validate-runner", "runner result ok must be boolean")
    if not isinstance(payload["stage"], str) or not payload["stage"]:
        raise CheckError("validate-runner", "runner result stage must be a string")
    if payload.get("module_name") not in {None, module_name}:
        raise CheckError(
            "validate-runner",
            "runner module_name does not match requested module",
        )
    return process_result, payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-version", default="3.12")
    parser.add_argument("--module-name", required=True)
    parser.add_argument("--package", default=".")
    parser.add_argument("--project-name", default="")
    parser.add_argument("--extras", default="")
    parser.add_argument("--config-file")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--result-file")
    return parser


def check_impl(
    *,
    python_version: str,
    module_name: str,
    package: str,
    project_name: str,
    extras: tuple[str, ...],
    config_file: str | None,
    timeout: float,
    invocation_cwd: Path,
    result_file: Path,
) -> tuple[CheckReport, tuple[str, ...]]:
    """Execute every stage and always return a serializable report."""
    config = ""
    config_present = False
    secrets: tuple[str, ...] = ()
    report = CheckReport(
        stage="validate",
        module_name=module_name,
        project_name=project_name,
        package=package,
        extras=extras,
        config_present=False,
        result_file=str(result_file.resolve()),
    )
    work_root = Path(tempfile.mkdtemp(prefix="entari-load-check-")).resolve()
    report.package = str(work_root)
    report.output = ""
    config_json: object = {}
    try:
        report.stage = "config"
        config, config_present = config_payload(
            config_file,
            invocation_cwd=invocation_cwd,
        )
        report.config_present = config_present
        if config_present:
            try:
                config_json = json.loads(config)
            except json.JSONDecodeError as error:
                raise CheckError(
                    "config",
                    "config file must contain one JSON object",
                ) from error
            if not isinstance(config_json, dict):
                raise CheckError(
                    "config",
                    "config file must contain one JSON object",
                )
        secrets = config_secrets(config, config_json)
        report.stage = "validate"
        report.module_name = normalize_module_name(module_name)
        if timeout <= 0:
            raise CheckError("validate", "timeout must be positive")
        resolved_package, detected_project, install_spec = resolve_package(
            package=package,
            extras=extras,
            project_root=invocation_cwd,
            project_name=project_name,
        )
        report.package = resolved_package
        report.project_name = detected_project
        runner_source = Path(__file__).with_name("runner.py")
        if not runner_source.is_file():
            raise CheckError("runner", f"runner not found: {runner_source}")

        uv = shutil.which("uv")
        if not uv:
            raise CheckError("venv", "uv is required but was not found in PATH")

        venv = work_root / ".venv"
        report.stage = "venv"
        result = run(
            [uv, "venv", "--python", python_version, str(venv)],
            cwd=work_root,
            timeout=timeout,
            stage="venv",
        )
        if result.returncode != 0:
            report.output = result.output
            raise CheckError("venv", "uv venv failed")
        python = (
            venv / "Scripts" / "python.exe"
            if os.name == "nt"
            else venv / "bin" / "python"
        )
        if not python.is_file():
            raise CheckError("venv", f"venv Python not found: {python}")

        report.stage = "install"
        install = run(
            [
                uv,
                "pip",
                "install",
                "--python",
                str(python),
                install_spec,
            ],
            cwd=work_root,
            timeout=timeout,
            stage="install",
        )
        report.output = install.output
        if install.returncode != 0:
            raise CheckError("install", "uv pip install failed")

        report.stage = "metadata"
        result = run(
            [
                str(python),
                "-I",
                "-c",
                (
                    "import json, importlib.metadata as m; "
                    "print(json.dumps({'version':m.version(__import__('sys').argv[1]),"
                    "'python':__import__('sys').version},ensure_ascii=False))"
                ),
                report.project_name,
            ],
            cwd=work_root,
            timeout=timeout,
            isolated=True,
            stage="metadata",
        )
        if result.returncode != 0:
            report.output += "\n" + result.output
            raise CheckError(
                "metadata",
                f"installed distribution {report.project_name!r} cannot be inspected",
            )
        try:
            metadata = json.loads(result.stdout)
            report.installed_version = metadata["version"]
            report.python_version = metadata["python"]
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise CheckError(
                "metadata", "metadata probe returned invalid JSON"
            ) from error

        report.stage = "runner"
        runner_process, runner_result = run_runner(
            python=python,
            module_name=report.module_name,
            project_name=report.project_name,
            timeout=timeout,
            workdir=work_root,
            config=config,
            runner_source=runner_source,
        )
        report.output += "\n" + runner_process.output
        report.runner = {
            "exit_code": runner_process.returncode,
            "stage": runner_result.get("stage"),
            "ok": runner_result.get("ok"),
            "error": redact(str(runner_result.get("error") or ""), secrets),
            "metadata": runner_result.get("metadata"),
        }
        reported_environment = _metadata_probe(
            runner_result,
            report.project_name,
            report.installed_version,
        )
        report.stage = "environment"
        report.installed_environment = _verify_installed_environment(
            python=python,
            environment=reported_environment,
            timeout=timeout,
            workdir=work_root,
        )
        report.stage = "runner"
        if runner_process.returncode != 0:
            raise CheckError("runner", "runner returned a non-zero exit code")
        if runner_result["ok"] is not True:
            raise CheckError(
                "runner",
                "runner did not successfully load the Entari plugin",
            )
        report.stage = "complete"
        report.ok = True
    except CheckError as error:
        report.stage = error.stage
        report.error = redact(str(error), secrets)
    except Exception as error:
        report.error = f"{type(error).__name__} during load check"
    finally:
        sensitive_keys = config_keys(config_json)
        sanitize_report_config_leaks(
            report,
            secrets=secrets,
            sensitive_keys=sensitive_keys,
        )
        shutil.rmtree(work_root, ignore_errors=True)
        write_result(result_file, report)
        output_github_values(report, result_file)
        write_step_summary(render_summary(report, secrets=secrets))
        print(  # noqa: T201 - machine-readable terminal result
            json.dumps(
                {
                    "ok": report.ok,
                    "stage": report.stage,
                    "project_name": report.project_name,
                    "module_name": report.module_name,
                    "python_version": report.python_version,
                    "installed_version": report.installed_version,
                    "result_file": report.result_file,
                },
                ensure_ascii=False,
            )
        )
    return report, secrets


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    invocation_cwd = Path.cwd().resolve()
    fallback_root = Path(tempfile.gettempdir()) / "entari-load-check"
    result_file = resolve_result_path(
        args.result_file,
        invocation_cwd=invocation_cwd,
        work_root=fallback_root,
    )
    try:
        extras = normalize_extras(args.extras)
    except CheckError as error:
        report = CheckReport(
            stage=error.stage,
            package=args.package,
            error=str(error),
            result_file=str(result_file.resolve()),
        )
        write_result(result_file, report)
        output_github_values(report, result_file)
        write_step_summary(render_summary(report, secrets=()))
        print(str(error), file=sys.stderr)  # noqa: T201
        return 1
    report, _secrets = check_impl(
        python_version=args.python_version,
        module_name=args.module_name,
        package=args.package,
        project_name=args.project_name,
        extras=extras,
        config_file=args.config_file,
        timeout=args.timeout,
        invocation_cwd=invocation_cwd,
        result_file=result_file,
    )
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
