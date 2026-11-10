from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import NamedTuple
import unittest
from unittest import mock

MODULE_PATH = Path(__file__).with_name("check.py")
SPEC = importlib.util.spec_from_file_location("entari_load_check", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
check = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = check
SPEC.loader.exec_module(check)


class RunningResult(NamedTuple):
    returncode: int
    stdout: str
    stderr: str


class ProjectFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "pyproject.toml").write_text(
            """
[project]
name = "entari-plugin-Example"
version = "1.2.3"

[project.optional-dependencies]
http = ["httpx>=0.28"]
all = ["httpx>=0.28"]
""".lstrip(),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()


class NormalizationTests(ProjectFixture):
    def test_normalize_module_name_rejects_non_import_values(self) -> None:
        self.assertEqual(
            check.normalize_module_name("entari_plugin_example"),
            "entari_plugin_example",
        )
        with self.assertRaisesRegex(check.CheckError, "module name"):
            check.normalize_module_name("../plugin")
        with self.assertRaisesRegex(check.CheckError, "import path"):
            check.normalize_module_name("")

    def test_normalize_extras_deduplicates_and_validates(self) -> None:
        self.assertEqual(
            check.normalize_extras(" http,all,HTTP,,httpx "),
            ("http", "all", "httpx"),
        )
        with self.assertRaisesRegex(check.CheckError, "invalid extra"):
            check.normalize_extras("http/extra")

    def test_merge_package_extras_is_non_editable_and_preserves_all(self) -> None:
        self.assertEqual(
            check.merge_package_extras(
                ".[http]",
                ("all", "http"),
                known_extras=("http", "all"),
            ),
            ".[http,all]",
        )
        self.assertEqual(
            check.merge_package_extras(
                str(self.root / "project"),
                (),
                known_extras=(),
            ),
            str(self.root / "project"),
        )
        with self.assertRaisesRegex(check.CheckError, "unknown project extras"):
            check.merge_package_extras(
                ".",
                ("missing",),
                known_extras=("all",),
            )

    def test_merge_package_extras_rejects_non_local_package(self) -> None:
        with self.assertRaisesRegex(check.CheckError, "local path"):
            check.merge_package_extras(
                "entari-plugin-example",
                ("all",),
                known_extras=("all",),
            )


class PackageResolutionTests(ProjectFixture):
    def test_resolves_path_before_isolated_cwd_and_installs_non_editably(self) -> None:
        resolved, project, spec = check.resolve_package(
            package=".",
            extras=("all",),
            project_root=self.root,
            project_name="",
        )

        self.assertEqual(resolved, str(self.root.resolve()))
        self.assertEqual(project, "entari-plugin-Example")
        self.assertEqual(spec, f"{self.root.resolve()}[all]")
        self.assertNotIn("-e", spec)

    def test_project_name_is_checked_case_and_separator_insensitively(self) -> None:
        _, project, _ = check.resolve_package(
            package=".",
            extras=(),
            project_root=self.root,
            project_name="ENTARI.plugin_example",
        )
        self.assertEqual(project, "entari-plugin-Example")
        with self.assertRaisesRegex(check.CheckError, "does not match"):
            check.resolve_package(
                package=".",
                extras=(),
                project_root=self.root,
                project_name="other",
            )

    def test_missing_package_is_a_validation_failure(self) -> None:
        with self.assertRaisesRegex(check.CheckError, "does not exist"):
            check.resolve_package(
                package="missing",
                extras=(),
                project_root=self.root,
                project_name="",
            )


class ResultTests(unittest.TestCase):
    def test_report_has_stable_public_shape(self) -> None:
        report = check.CheckReport(
            stage="complete",
            ok=True,
            module_name="plugin",
            project_name="entari-plugin-test",
            config_present=False,
            python_version="3.12.4",
            installed_version="1.0.0",
            installed_environment={"arclet-entari": "0.19.4"},
        )

        payload = report.as_dict()

        self.assertEqual(payload["version"], 1)
        self.assertTrue(payload["ok"])
        self.assertNotIn("config", payload)
        self.assertEqual(payload["installed_environment"], {"arclet-entari": "0.19.4"})

    def test_atomic_result_write_replaces_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result_file = Path(directory) / "nested" / "result.json"
            result_file.parent.mkdir()
            result_file.write_text("stale", encoding="utf-8")
            report = check.CheckReport(stage="install", error="failed")

            check.write_result(result_file, report)

            payload = json.loads(result_file.read_text(encoding="utf-8"))
            self.assertEqual(payload["stage"], "install")
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["result_file"], str(result_file.resolve()))

    def test_secret_configuration_is_redacted_from_output_and_summary(self) -> None:
        secret = "SENTINEL-7d93b458"
        output = f"failed with {secret}\ntoken=another-secret\nraw=ordinary"

        sanitized = check.redact(output, (secret,))
        summary = check.render_summary(
            check.CheckReport(
                stage="runner",
                error=f"runner rejected {secret}",
                output=output,
                config_present=True,
            ),
            secrets=(secret,),
        )

        self.assertNotIn(secret, sanitized)
        self.assertNotIn("another-secret", sanitized)
        self.assertIn("ordinary", sanitized)
        self.assertNotIn(secret, summary)
        self.assertNotIn("another-secret", summary)

    def test_github_outputs_exclude_configuration(self) -> None:
        report = check.CheckReport(
            stage="runner",
            module_name="plugin",
            project_name="entari-plugin-test",
            python_version="3.12.1",
            config_present=True,
        )
        with tempfile.TemporaryDirectory() as directory:
            output_file = Path(directory) / "github-output"
            with mock.patch.dict(
                os.environ,
                {"GITHUB_OUTPUT": str(output_file)},
                clear=False,
            ):
                check.output_github_values(report, Path(directory) / "result.json")

            emitted = output_file.read_text(encoding="utf-8")

        self.assertIn("ok=false", emitted)
        self.assertIn("stage=runner", emitted)
        self.assertIn("project-name=entari-plugin-test", emitted)
        self.assertIn("module-name=plugin", emitted)
        self.assertIn("python-version=3.12.1", emitted)
        self.assertIn("result-file=", emitted)
        self.assertNotIn("config", emitted)


class RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.python = self.root / "python"
        self.python.touch()
        runner_directory = self.root / "source"
        runner_directory.mkdir()
        self.runner = runner_directory / "runner.py"
        self.runner.touch()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _patched_run(
        self,
        payload: object,
        *,
        returncode: int = 0,
    ) -> RunningResult:
        def fake_run(*args: object, **kwargs: object) -> RunningResult:
            del args, kwargs
            (self.root / "runner-result.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            return RunningResult(returncode, "", "")

        patcher = mock.patch.object(check, "run", side_effect=fake_run)
        patcher.start()
        self.addCleanup(patcher.stop)
        return RunningResult(0, "", "")

    def test_runner_requires_zero_exit_and_ok_payload(self) -> None:
        self._patched_run(
            {
                "ok": True,
                "stage": "complete",
                "module_name": "plugin",
                "project_name": "entari-plugin-test",
            }
        )
        process, payload = check.run_runner(
            python=self.python,
            module_name="plugin",
            project_name="entari-plugin-test",
            timeout=10,
            workdir=self.root,
            config="",
            runner_source=self.runner,
        )

        self.assertEqual(process.returncode, 0)
        self.assertTrue(payload["ok"])

    def test_runner_nonzero_exit_is_preserved_for_check_impl(self) -> None:
        self._patched_run(
            {
                "ok": False,
                "stage": "probe",
                "module_name": "plugin",
                "project_name": "entari-plugin-test",
                "error": "failed",
            },
            returncode=1,
        )
        process, payload = check.run_runner(
            python=self.python,
            module_name="plugin",
            project_name="entari-plugin-test",
            timeout=10,
            workdir=self.root,
            config="",
            runner_source=self.runner,
        )

        self.assertEqual(process.returncode, 1)
        self.assertFalse(payload["ok"])

    def test_runner_identity_mismatch_is_rejected(self) -> None:
        self._patched_run(
            {
                "ok": True,
                "stage": "complete",
                "module_name": "other",
                "project_name": "entari-plugin-test",
            }
        )
        with self.assertRaisesRegex(check.CheckError, "module_name"):
            check.run_runner(
                python=self.python,
                module_name="plugin",
                project_name="entari-plugin-test",
                timeout=10,
                workdir=self.root,
                config="",
                runner_source=self.runner,
            )

    def test_empty_config_is_still_written_for_runner_contract(self) -> None:
        captured: dict[str, object] = {}

        def fake_run(command: object, **kwargs: object) -> RunningResult:
            del kwargs
            captured["command"] = command
            captured["config"] = (self.root / ".entari-load-check.json").read_text(
                encoding="utf-8"
            )
            (self.root / "runner-result.json").write_text(
                json.dumps(
                    {
                        "ok": True,
                        "stage": "complete",
                        "module_name": "plugin",
                        "project_name": "entari-plugin-test",
                    }
                ),
                encoding="utf-8",
            )
            return RunningResult(0, "", "")

        with mock.patch.object(check, "run", side_effect=fake_run) as run:
            check.run_runner(
                python=self.python,
                module_name="plugin",
                project_name="entari-plugin-test",
                timeout=10,
                workdir=self.root,
                config="",
                runner_source=self.runner,
            )

        self.assertEqual(captured["config"], "{}\n")
        self.assertEqual(
            (self.root / "runner.py").read_bytes(),
            self.runner.read_bytes(),
        )
        self.assertNotEqual(
            Path(captured["command"][2]),  # type: ignore[index]
            self.runner,
        )
        self.assertEqual(run.call_args.kwargs["stage"], "runner")
        self.assertTrue(run.call_args.kwargs["isolated"])

    def test_runner_receives_exact_config_json(self) -> None:
        config = '{"plugin": {"enabled": true}}\n'
        captured: dict[str, object] = {}

        def fake_run(command: object, **kwargs: object) -> RunningResult:
            del command, kwargs
            captured["config"] = (self.root / ".entari-load-check.json").read_text(
                encoding="utf-8"
            )
            (self.root / "runner-result.json").write_text(
                json.dumps(
                    {
                        "ok": True,
                        "stage": "complete",
                        "module_name": "plugin",
                        "project_name": "entari-plugin-test",
                    }
                ),
                encoding="utf-8",
            )
            return RunningResult(0, "", "")

        with mock.patch.object(check, "run", side_effect=fake_run):
            check.run_runner(
                python=self.python,
                module_name="plugin",
                project_name="entari-plugin-test",
                timeout=10,
                workdir=self.root,
                config=config,
                runner_source=self.runner,
            )

        self.assertEqual(captured["config"], config)

    def test_runner_version_must_match_installed_distribution(self) -> None:
        with self.assertRaisesRegex(check.CheckError, "installed_version"):
            check._metadata_probe(
                {
                    "project_name": "entari-plugin-test",
                    "installed_version": "2.0.0",
                },
                "entari-plugin-test",
                "1.0.0",
            )

    def test_nested_runner_metadata_redacts_config_and_schema(self) -> None:
        secret = "SENTINEL-7d93b458"
        config = json.dumps({"bot_token": secret}, indent=2)
        parsed = json.loads(config)
        payload = {
            "metadata": {
                "bot_token": secret,
                "nested": [{"message": f"contains {secret}"}],
            }
        }

        sanitized = check.sanitize_json_value(
            payload,
            secrets=check.config_secrets(config, parsed),
            sensitive_keys=check.config_keys(parsed),
        )

        rendered = json.dumps(sanitized)
        self.assertNotIn(secret, rendered)
        self.assertNotIn("bot_token", rendered)
        self.assertIn("***", rendered)

    def test_workflow_profiles_preserve_verified_environment_and_redact_config(
        self,
    ) -> None:
        profiles = (
            (
                {"provider": None, "startup": "off"},
                {
                    "arclet-entari": "0.19.4",
                    "entari-plugin-htmlrender": "0.2.0",
                    "python": "3.12.15",
                },
            ),
            (
                {
                    "provider": "takumi",
                    "startup": "warmup",
                    "provider_config": {"max_concurrency": 1},
                },
                {
                    "arclet-entari": "0.19.4",
                    "entari-plugin-htmlrender": "0.2.0",
                    "python": "3.12.15",
                    "takumi-py": "0.2.0",
                },
            ),
            (
                {
                    "provider": None,
                    "startup": "off",
                    "graphics": {
                        "backends": ["pillow", "skia"],
                        "backend": "pillow",
                    },
                },
                {
                    "arclet-entari": "0.19.4",
                    "entari-plugin-htmlrender": "0.2.0",
                    "pillow": "12.0.0",
                    "python": "3.12.15",
                    "skia-python": "144.0.post2",
                },
            ),
        )
        secret = "SENTINEL-PROFILE-7d93b458"
        for profile, environment in profiles:
            with self.subTest(profile=profile):
                config_object = {
                    **profile,
                    "credentials": {"bot_token": secret},
                }
                config = json.dumps(config_object)
                parsed = json.loads(config)
                report = check.CheckReport(
                    stage="complete",
                    ok=True,
                    config_present=True,
                    installed_environment=dict(environment),
                    output=f"provider={profile.get('provider')} {secret}",
                    error=f"credential={secret}",
                    runner={
                        "metadata": {
                            "provider": profile.get("provider"),
                            "backends": profile.get("graphics"),
                            "credentials": {"bot_token": secret},
                        },
                    },
                )

                check.sanitize_report_config_leaks(
                    report,
                    secrets=check.config_secrets(config, parsed),
                    sensitive_keys=check.config_keys(parsed),
                )

                self.assertEqual(report.installed_environment, environment)
                rendered = json.dumps(report.as_dict())
                self.assertNotIn(secret, rendered)
                self.assertNotIn("bot_token", rendered)
                self.assertNotIn("credentials", rendered)
                self.assertNotIn("takumi", report.output)
                if profile.get("graphics"):
                    self.assertNotIn("pillow", json.dumps(report.runner))

    def test_installed_environment_metadata_is_verified_by_isolated_python(
        self,
    ) -> None:
        expected = {
            "arclet-entari": "0.19.4",
            "pillow": "12.0.0",
            "skia-python": "144.0.post2",
        }
        result = RunningResult(
            0,
            json.dumps({"versions": expected, "missing": []}),
            "",
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(check, "run", return_value=result),
        ):
            verified = check._verify_installed_environment(
                python=Path(directory) / "python",
                environment=expected,
                timeout=10,
                workdir=Path(directory),
            )

        self.assertEqual(verified, expected)


class SubprocessTests(unittest.TestCase):
    def _python(self, source: str, result_file: Path) -> list[str]:
        return [
            sys.executable,
            "-c",
            f"from pathlib import Path; {source}",
            str(result_file),
        ]

    def test_timeout_terminates_process_tree_and_reports_stage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result_file = root / "child-result"
            with self.assertRaisesRegex(check.CheckError, "timed out") as raised:
                check.run(
                    self._python(
                        (
                            "import subprocess, sys, time; "
                            "subprocess.Popen([sys.executable,'-c','import time;"
                            "time.sleep(30)']); time.sleep(30)"
                        ),
                        result_file,
                    ),
                    cwd=root,
                    timeout=0.2,
                    isolated=True,
                    stage="runner",
                )
            self.assertEqual(raised.exception.stage, "runner")

    def test_isolated_environment_removes_python_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command = self._python(
                (
                    "import json, os, sys; "
                    "Path(sys.argv[1]).write_text("
                    "json.dumps({'pythonpath':os.environ.get('PYTHONPATH'),"
                    "'no_user':os.environ.get('PYTHONNOUSERSITE')}))"
                ),
                root / "environment.json",
            )
            with mock.patch.dict(os.environ, {"PYTHONPATH": "/workspace/src"}):
                result = check.run(
                    command,
                    cwd=root,
                    timeout=10,
                    isolated=True,
                )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads((root / "environment.json").read_text("utf-8"))
            self.assertIsNone(payload["pythonpath"])
            self.assertEqual(payload["no_user"], "1")


class CliTests(ProjectFixture):
    def test_parser_uses_locked_interface(self) -> None:
        args = check.build_parser().parse_args(
            [
                "--python-version",
                "3.11",
                "--module-name",
                "plugin",
                "--package",
                ".",
                "--project-name",
                "entari-plugin-Example",
                "--extras",
                "all,http",
                "--config-file",
                "config.yml",
                "--timeout",
                "30",
                "--result-file",
                "result.json",
            ]
        )

        self.assertEqual(args.python_version, "3.11")
        self.assertEqual(args.module_name, "plugin")
        self.assertEqual(args.package, ".")
        self.assertEqual(args.project_name, "entari-plugin-Example")
        self.assertEqual(args.extras, "all,http")
        self.assertEqual(args.config_file, "config.yml")
        self.assertEqual(args.timeout, 30)
        self.assertEqual(args.result_file, "result.json")

    def test_config_failure_still_writes_result_and_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result_file = Path(directory) / "result.json"
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                mock.patch.object(Path, "cwd", return_value=self.root),
                mock.patch("sys.stdout", stdout),
                mock.patch("sys.stderr", stderr),
            ):
                exit_code = check.main(
                    [
                        "--module-name",
                        "plugin",
                        "--config-file",
                        "missing.yml",
                        "--result-file",
                        str(result_file),
                    ]
                )

            payload = json.loads(result_file.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["stage"], "config")
        self.assertFalse(payload["ok"])
        self.assertNotIn("missing.yml", json.dumps(payload))

    def test_invalid_extras_fail_before_any_environment_operation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result_file = Path(directory) / "result.json"
            with (
                mock.patch.object(Path, "cwd", return_value=self.root),
                mock.patch.object(check, "check_impl") as impl,
            ):
                exit_code = check.main(
                    [
                        "--module-name",
                        "plugin",
                        "--extras",
                        "bad/extra",
                        "--result-file",
                        str(result_file),
                    ]
                )

            impl.assert_not_called()
            payload = json.loads(result_file.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["stage"], "validate")


if __name__ == "__main__":
    unittest.main()
