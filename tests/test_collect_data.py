"""Offline collector failures and the actual workflow's commit/report shell."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import collect_data as cd

TODAY = "2026-10-07"
FIXTURES = {
    "news": [{"title": "news", "link": "https://example.test/news", "body": "body"}],
    "markets": [{"question": "market?", "url": "https://example.test/market"}],
    "dune": [{"tx_hash": "0xfixture", "usdc_amount": 12000}],
    "metaculus": [{"title": "prediction", "url": "https://example.test/prediction"}],
    "guardian": [{"title": "Guardian", "url": "https://example.test/guardian"}],
}
SECRET = "do-not-publish-fixture-key"


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "src").mkdir()
        (self.root / "data").mkdir()
        self.manifest = self.root / "status.json"
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.test")
        self.configs = {}
        for source, config in cd.SOURCES.items():
            script, args, required, _, retention = config
            self.configs[source] = (script, args, (), 2, retention)
            self.write_script(source, f"print({json.dumps(FIXTURES[source])!r})")
            (self.root / "data" / f"{source}-{TODAY}.json").write_text(
                json.dumps([{**FIXTURES[source][0], "old": True}]) + "\n")
        self.git("add", "data")
        self.git("commit", "-qm", "baseline")
        self.sources = patch.object(cd, "SOURCES", self.configs)
        self.sources.start()
        self.addCleanup(self.sources.stop)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True,
                              capture_output=True, text=True).stdout.strip()

    def write_script(self, source, code):
        script = cd.SOURCES[source][0]
        (self.root / "src" / script).write_text(code + "\n")

    def read(self, source):
        return (self.root / "data" / f"{source}-{TODAY}.json").read_bytes()

    def fail_source(self, source, status=500):
        self.write_script(source, f'''import sys
print('[{{"partial":', end='')
print("requests.exceptions.HTTPError: {status} Client Error: error for url: https://example.test/?api-key={SECRET}", file=sys.stderr)
sys.exit(1)''')

    def collect(self):
        return cd.collect(TODAY, self.manifest, self.root)

    def test_guardian_401_keeps_same_day_and_old_data_commits_other_sources(self):
        old = self.root / "data/guardian-2026-01-01.json"
        old.write_bytes(self.read("guardian"))
        os.utime(old, (0, 0))
        self.git("add", "data")
        self.git("commit", "-qm", "older Guardian snapshot")
        before = self.read("guardian")
        self.fail_source("guardian", 401)
        unrelated = self.root / "data/unrelated.json"
        unrelated.write_text("broken")
        report = self.collect()
        self.assertEqual(report["sources"]["guardian"]["reason"], "HTTP 401")
        self.assertEqual(self.read("guardian"), before)
        self.assertTrue(old.exists())
        cd.stage(report, self.root)
        self.git("commit", "-qm", "partial collection")
        names = self.git("diff", "HEAD^", "HEAD", "--name-only").splitlines()
        self.assertEqual(names, [f"data/{name}-{TODAY}.json" for name in sorted(FIXTURES) if name != "guardian"])
        self.assertNotIn(SECRET, self.manifest.read_text())
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertFalse(cd.summarize(report))
        self.assertIn("Degraded", output.getvalue())
        self.assertNotIn(SECRET, output.getvalue())

    def test_first_collector_failure_does_not_block_later_sources(self):
        self.fail_source("news")
        report = self.collect()
        self.assertEqual(report["sources"]["news"]["status"], "failed")
        self.assertEqual(report["sources"]["guardian"]["status"], "success")

    def test_all_failed_leaves_data_unchanged_and_index_empty(self):
        before = {source: self.read(source) for source in FIXTURES}
        for source in FIXTURES:
            self.fail_source(source)
        report = self.collect()
        cd.stage(report, self.root)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "")
        self.assertEqual(before, {source: self.read(source) for source in FIXTURES})
        self.assertTrue(all(r["status"] == "failed" for r in report["sources"].values()))

    def test_unchanged_outputs_do_not_stage_or_make_empty_commit(self):
        report = self.collect()
        cd.stage(report, self.root)
        self.git("commit", "-qm", "first collection")
        head = self.git("rev-parse", "HEAD")
        report = self.collect()
        cd.stage(report, self.root)
        self.assertFalse(any(r["changed"] for r in report["sources"].values()))
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "")
        self.assertEqual(self.git("rev-parse", "HEAD"), head)

    def test_invalid_partial_or_empty_output_never_replaces_snapshot(self):
        before = self.read("guardian")
        for raw in ("", "[", "null", "{}", "[]", "[1]", '[{"title":"missing URL"}]',
                    '[{"title":"x", "url":"x", "number":NaN}]',
                    '[{"title":"x", "url":"x", "number":1e999}]'):
            with self.subTest(raw=raw):
                self.write_script("guardian", f"print({raw!r})")
                report = self.collect()
                self.assertEqual(report["sources"]["guardian"]["status"], "failed")
                self.assertEqual(self.read("guardian"), before)

    def test_failed_new_day_creates_no_snapshot(self):
        self.fail_source("guardian", 401)
        report = cd.collect("2026-10-08", self.manifest, self.root)
        self.assertFalse((self.root / "data/guardian-2026-10-08.json").exists())
        self.assertEqual(report["sources"]["guardian"]["changed"], [])

    def test_timeout_does_not_block_other_sources(self):
        script, args, required, _, retention = self.configs["news"]
        self.configs["news"] = (script, args, required, 0.03, retention)
        self.write_script("news", "import time; time.sleep(5)")
        report = self.collect()
        self.assertEqual(report["sources"]["news"]["reason"], "collector timed out")
        self.assertEqual(report["sources"]["guardian"]["status"], "success")

    def test_unconfigured_sources_are_skipped_without_empty_overwrite(self):
        script, args, _, timeout, retention = self.configs["guardian"]
        self.configs["guardian"] = (script, args, ("ABSENT_FIXTURE_KEY",), timeout, retention)
        before = self.read("guardian")
        report = self.collect()
        self.assertEqual(report["sources"]["guardian"]["status"], "skipped")
        self.assertEqual(self.read("guardian"), before)

    def test_valid_empty_optional_result_is_distinct_from_failure(self):
        self.write_script("dune", "print('[]')")
        self.assertEqual(self.collect()["sources"]["dune"]["status"], "success")
        self.assertEqual(json.loads(self.read("dune")), [])

    def test_warnings_publish_valid_output_but_report_partial_without_raw_logs(self):
        self.write_script("news", f"import sys; print({json.dumps(FIXTURES['news'])!r}); print({SECRET!r}, file=sys.stderr)")
        report = self.collect()
        self.assertEqual(report["sources"]["news"]["status"], "partial")
        self.assertTrue(report["sources"]["news"]["changed"])
        self.assertNotIn(SECRET, self.manifest.read_text())

    def test_success_retention_is_source_scoped(self):
        old = self.root / "data/news-2026-01-01.json"
        old.write_text("[]")
        os.utime(old, (0, 0))
        self.git("add", "data")
        self.git("commit", "-qm", "older news")
        report = self.collect()
        self.assertFalse(old.exists())
        cd.stage(report, self.root)
        self.assertIn("D\tdata/news-2026-01-01.json", self.git("diff", "--cached", "--name-status"))

    def test_changed_after_validation_is_rejected_before_any_staging(self):
        report = self.collect()
        (self.root / "data" / f"guardian-{TODAY}.json").write_text("[]")
        with self.assertRaises(ValueError):
            cd.stage(report, self.root)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "")

    def test_publish_failure_preserves_previous_data_and_continues(self):
        before = self.read("news")
        original = cd.atomic_write
        def cannot_publish_news(path, content):
            if path.name == f"news-{TODAY}.json":
                raise PermissionError(SECRET)
            return original(path, content)
        with patch.object(cd, "atomic_write", side_effect=cannot_publish_news):
            report = self.collect()
        self.assertEqual(report["sources"]["news"]["status"], "failed")
        self.assertEqual(self.read("news"), before)
        self.assertEqual(report["sources"]["guardian"]["status"], "success")
        self.assertNotIn(SECRET, self.manifest.read_text())

    def test_retention_failure_keeps_valid_changes_eligible_and_continues(self):
        old = self.root / "data/news-2026-01-01.json"
        old.write_text("[]")
        os.utime(old, (0, 0))
        original = Path.unlink
        def cannot_remove_old(path, *args, **kwargs):
            if path == old:
                raise PermissionError(SECRET)
            return original(path, *args, **kwargs)
        with patch.object(Path, "unlink", cannot_remove_old):
            report = self.collect()
        self.assertEqual(report["sources"]["news"]["status"], "partial")
        self.assertEqual(report["sources"]["news"]["reason"], "retention incomplete")
        self.assertTrue(report["sources"]["news"]["changed"])
        self.assertEqual(report["sources"]["guardian"]["status"], "success")
        cd.stage(report, self.root)
        self.assertIn(f"data/news-{TODAY}.json", self.git("diff", "--cached", "--name-only"))
        self.assertNotIn(SECRET, self.manifest.read_text())

    def test_workflow_commit_and_final_failure_using_real_shell(self):
        self.fail_source("guardian", 401)
        # Execute the repository workflow's actual Commit data shell locally,
        # with only git push pointed at a local bare fixture repository.
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/fetch-data.yml").read_text()
        start = workflow.index("      - name: Commit data")
        block = workflow[start:workflow.index("      # A degraded", start)]
        shell = block.split("        run: |\n", 1)[1]
        shell = "\n".join(line[10:] for line in shell.splitlines())
        shell = shell.replace("${{ steps.date.outputs.today }}", TODAY)
        script = Path(cd.__file__).resolve()
        (self.root / "src/collect_data.py").write_bytes(script.read_bytes())
        env = {**os.environ, "RUNNER_TEMP": str(self.root),
               "DUNE_API_KEY": "fixture", "DUNE_QUERY_ID": "fixture",
               "METACULUS_API_KEY": "fixture", "GUARDIAN_API_KEY": SECRET}
        collected = subprocess.run([sys.executable, "src/collect_data.py", "collect", "--date", TODAY,
                                    "--manifest", "collection-status.json"],
                                   cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(collected.returncode, 1)
        self.assertNotIn(SECRET, collected.stdout + collected.stderr)
        remote = self.root / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "-u", "origin", "HEAD")
        result = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", shell], cwd=self.root,
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        head = self.git("rev-parse", "HEAD")
        self.assertEqual(self.git("ls-remote", "origin", "HEAD").split()[0], head)
        status = subprocess.run([sys.executable, "src/collect_data.py", "report", "--manifest", "collection-status.json"],
                                cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(status.returncode, 1)
        self.assertIn("guardian: failed (HTTP 401)", status.stdout)
        again = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", shell], cwd=self.root,
                               env=env, capture_output=True, text=True)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("No changes.", again.stdout)
        self.assertEqual(self.git("rev-parse", "HEAD"), head)


if __name__ == "__main__":
    unittest.main()
