"""Compilation/provenance regressions, including a local Git snapshot test."""
import copy
from contextlib import redirect_stdout, redirect_stderr
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from exercise_catalog import CatalogError, ExerciseCatalog
from import_exercises import (
    CONTENT_ROOT, EXPECTED_ENGINE_BLOBS, REPOSITORY, STARTER_UNITS,
    build_catalog, main, read_git_sources,
)


COMMIT = "621f35c5565b1f02c39576a70f657b929f1970b4"
LESSON_ID = "cpp_fundamentals__programas_y_ejecucion__problemas_instrucciones_y_resultados"
LESSON_PATH = CONTENT_ROOT + "/es/programming/cpp_fundamentals/programas_y_ejecucion/lesson_problemas_instrucciones_y_resultados.json"
# A real published block excerpt. The miniature lesson wrapper is test data,
# with a recomputed Git blob hash; it is not presented as an original Git blob.
REAL_CHOICE = {
    "type": "multiple_choice", "id": "objetivo_etiqueta",
    "question": "Las cajas deben distinguirse aunque dos tengan el mismo color. ¿Qué requisito debe quedar fijado antes de programar?",
    "options": ["Qué orden de impresión usar, aunque se repitan las etiquetas.",
                "Qué dato identifica cada caja de forma inequívoca.",
                "Qué color usar como único dato de cada etiqueta."],
    "correctIndex": 1,
    "explanation": "El color puede repetirse en cajas distintas. Antes de programar debemos establecer un dato que las distinga; imprimir una etiqueta no garantiza esa identificación.",
}


def blob(content):
    encoded = content.encode("utf-8")
    return hashlib.sha1(b"blob " + str(len(encoded)).encode("ascii") + b"\x00" + encoded).hexdigest()


def document(blocks, *, math=False):
    if math:
        lesson_id = "math_course_01__numeros_y_operaciones__magnitudes_y_numeracion"
        path = CONTENT_ROOT + "/es/math_physics/math_course_01/numeros_y_operaciones/lesson_magnitudes_y_numeracion.json"
    else:
        lesson_id, path = LESSON_ID, LESSON_PATH
    content = json.dumps({"id": lesson_id, "title": "Test wrapper", "pages": [{"blocks": blocks}]}, ensure_ascii=False) + "\n"
    return {"path": path, "blob_sha": blob(content), "content": content}


class ImportTests(unittest.TestCase):
    def compile(self, blocks, *, math=False):
        return build_catalog([document(blocks, math=math)], COMMIT, EXPECTED_ENGINE_BLOBS)

    def test_original_multiple_choice_compiles_to_server_owned_route_and_index(self):
        catalog, report = self.compile([REAL_CHOICE])
        rule = ExerciseCatalog.from_dict(catalog).rules[0]
        self.assertEqual(rule.id, "es/programming/" + LESSON_ID + "/objetivo_etiqueta")
        self.assertEqual(rule.route, "programming")
        self.assertTrue(rule.evaluate(1))
        self.assertFalse(rule.evaluate(2))
        self.assertEqual(report["installed_exercises"], 1)
        self.assertEqual(report["omitted_interactive_blocks"], 0)
        self.assertEqual(rule.source["commit"], COMMIT)

    def test_import_is_reproducible_and_whitespace_only_file_edit_keeps_version(self):
        original = document([REAL_CHOICE])
        one, report = build_catalog([original], COMMIT, EXPECTED_ENGINE_BLOBS)
        two, second_report = build_catalog([original], COMMIT, EXPECTED_ENGINE_BLOBS)
        self.assertEqual(one, two)
        self.assertEqual(report, second_report)
        changed = copy.deepcopy(original)
        changed["content"] = json.dumps(json.loads(changed["content"]), ensure_ascii=False, indent=4)
        changed["blob_sha"] = blob(changed["content"])
        three, _ = build_catalog([changed], "a" * 40, EXPECTED_ENGINE_BLOBS)
        self.assertEqual(one["exercises"][0]["version"], three["exercises"][0]["version"])
        self.assertNotEqual(one["exercises"][0]["source"]["blob_sha"], three["exercises"][0]["source"]["blob_sha"])

    def test_changed_question_or_option_text_changes_version_even_with_same_index(self):
        original, _ = self.compile([REAL_CHOICE])
        for key in ("question", "options"):
            changed = copy.deepcopy(REAL_CHOICE)
            if key == "question":
                changed[key] += " Texto cambiado."
            else:
                changed[key][0] += " Texto cambiado."
            modified, _ = self.compile([changed])
            self.assertNotEqual(original["exercises"][0]["version"], modified["exercises"][0]["version"])

    def test_unrelated_new_block_does_not_reset_previous_version(self):
        original, _ = self.compile([REAL_CHOICE])
        modified, _ = self.compile([{"type": "paragraph", "text": "New paragraph"}, REAL_CHOICE])
        self.assertEqual(original["exercises"][0]["version"], modified["exercises"][0]["version"])

    def test_source_provenance_rejects_tampered_blob_repository_and_engine(self):
        source = document([REAL_CHOICE])
        source["content"] += " "
        with self.assertRaisesRegex(CatalogError, "source_blob_hash_mismatch"):
            build_catalog([source], COMMIT, EXPECTED_ENGINE_BLOBS)
        with self.assertRaisesRegex(CatalogError, "unauthorized_curriculum_repository"):
            build_catalog([document([REAL_CHOICE])], COMMIT, EXPECTED_ENGINE_BLOBS, repository="other/repo")
        engines = dict(EXPECTED_ENGINE_BLOBS)
        engines[next(iter(engines))] = "0" * 40
        with self.assertRaisesRegex(CatalogError, "source_evaluator_changed"):
            build_catalog([document([REAL_CHOICE])], COMMIT, engines)
        with self.assertRaisesRegex(CatalogError, "invalid_source_commit"):
            build_catalog([document([REAL_CHOICE])], "main", EXPECTED_ENGINE_BLOBS)

    def test_missing_or_duplicate_ids_never_override_an_authorized_rule(self):
        with self.assertRaisesRegex(CatalogError, "duplicate_curriculum_exercise"):
            self.compile([REAL_CHOICE, REAL_CHOICE])
        sources = [document([REAL_CHOICE])] * 2
        with self.assertRaisesRegex(CatalogError, "duplicate_source_path"):
            build_catalog(sources, COMMIT, EXPECTED_ENGINE_BLOBS)
        bad = copy.deepcopy(REAL_CHOICE)
        bad["id"] = "../wrong id"
        with self.assertRaises(CatalogError):
            self.compile([bad])

    def test_every_unsupported_interactive_block_has_an_individual_reason(self):
        blocks = [REAL_CHOICE, {"type": "heading", "text": "Heading"},
                  {"type": "fill_code", "id": "fill", "answers": ["<<"]},
                  {"type": "inline_fill_code", "id": "inline"},
                  {"type": "drag_fill_code", "id": "drag"},
                  {"type": "cpp_compiler", "initialCode": "int main() {}"},
                  {"type": "future_exercise", "id": "future"}]
        catalog, report = self.compile(blocks)
        self.assertEqual(len(catalog["exercises"]), 1)
        self.assertEqual(report["omitted_interactive_blocks"], 5)
        self.assertEqual(len({item["id"] for item in report["omitted"]}), 5)
        self.assertEqual({item["reason"] for item in report["omitted"]}, {
            "cpp_fill_normalization_not_ported", "compiler_execution_not_supported", "unsupported_block_type:future_exercise"})
        self.assertEqual(report["sources"][0]["non_interactive_blocks"], 1)

    def test_unknown_validator_rejects_entire_composition_without_partial_rule(self):
        block = {"type": "math_puzzle", "schemaVersion": 1, "id": "compound", "prompt": "Test", "responses": [
            {"id": "first", "type": "math_numeric_input", "validator": {"type": "numeric", "expected": "2"}},
            {"id": "last", "type": "math_expression_input", "validator": {"type": "symbolic", "expected": "x+1"}},
        ]}
        catalog, report = self.compile([block], math=True)
        self.assertEqual(catalog["exercises"], [])
        self.assertEqual(report["omitted"][0]["reason"], "unsupported_validator:symbolic")

    def test_unknown_comparison_options_and_boolean_correct_index_are_not_installed(self):
        for key, value in (("correctIndex", True), ("serverCorrect", True)):
            changed = {**REAL_CHOICE, key: value}
            catalog, report = self.compile([changed])
            self.assertEqual(catalog["exercises"], [])
            self.assertEqual(len(report["omitted"]), 1)
        block = {"type": "math_puzzle", "id": "new_mode", "responses": [{"id": "r", "type": "math_numeric_input", "validator": {"type": "numeric", "expected": "2", "ignoreUnits": True}}]}
        catalog, report = self.compile([block], math=True)
        self.assertEqual(catalog["exercises"], [])
        self.assertEqual(report["omitted"][0]["reason"], "unrecognized_validation_options")

    def test_unreviewed_java_double_string_edges_are_explicitly_omitted(self):
        for validator, reason in (
            ({"type": "numeric", "expected": 1.0}, "numeric_json_double_not_imported"),
            ({"type": "numeric", "expected": "1", "tolerance": 5e-324}, "nonzero_numeric_tolerance_not_imported"),
            ({"type": "tolerance", "expected": "1"}, "nonzero_numeric_tolerance_not_imported"),
        ):
            block = {"type": "math_puzzle", "id": "edge", "responses": [{"id": "r", "type": "math_numeric_input", "validator": validator}]}
            catalog, report = self.compile([block], math=True)
            self.assertEqual(catalog["exercises"], [])
            self.assertEqual(report["omitted"][0]["reason"], reason)

    def test_published_bundle_reports_actual_language_coverage_without_inventing_parity(self):
        report = json.loads(Path(__file__).with_name("rules-catalog-coverage.json").read_text(encoding="utf-8"))
        catalog = ExerciseCatalog.from_file(Path(__file__).with_name("rules-catalog.json"))
        self.assertEqual(len(catalog.rules), 364)
        self.assertEqual(len(report["sources"]), 33)
        self.assertEqual(sum(source["installed_exercises"] for source in report["sources"]), len(catalog.rules))
        self.assertEqual(report["omitted_interactive_blocks"], len(report["omitted"]))
        self.assertEqual(report["omitted_interactive_blocks"], 36)
        for locale in ("es", "en", "fr"):
            self.assertEqual(report["counts_installed"][locale + "/math_physics/math_puzzle"], 79)
        self.assertEqual(report["counts_installed"]["es/programming/multiple_choice"], 29)
        self.assertEqual(report["counts_installed"]["en/programming/multiple_choice"], 25)
        self.assertEqual(report["counts_installed"]["fr/programming/multiple_choice"], 25)


class LocalGitImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "Android-source"
        self.repo.mkdir()
        self.git("init", "--quiet")
        self.engine_path = next(iter(EXPECTED_ENGINE_BLOBS))
        self.write(self.engine_path, "known evaluator test fixture\n")
        self.engine_blobs = {self.engine_path: blob("known evaluator test fixture\n")}
        self.patch = patch.dict(EXPECTED_ENGINE_BLOBS, self.engine_blobs, clear=True)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        base = CONTENT_ROOT + "/es/programming/cpp_fundamentals"
        self.course_path = base + "/course_cpp_fundamentals.json"
        self.unit_path = base + "/programas_y_ejecucion/unit_programas_y_ejecucion.json"
        self.write_json(self.course_path, {"id": "cpp_fundamentals", "units": [{"id": "cpp_fundamentals__programas_y_ejecucion"}]})
        self.write_json(self.unit_path, {"courseId": "cpp_fundamentals", "unitId": "cpp_fundamentals__programas_y_ejecucion", "lessons": [{"id": LESSON_ID}]})
        self.write(LESSON_PATH, document([REAL_CHOICE])["content"])
        self.commit = self.save_commit()

    def git(self, *args):
        result = subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True)
        return result.stdout.decode().strip()

    def write(self, path, content):
        file = self.repo / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8")

    def write_json(self, path, content):
        self.write(path, json.dumps(content) + "\n")

    def save_commit(self):
        self.git("add", ".")
        self.git("-c", "user.name=ServerTec tests", "-c", "user.email=tests@localhost", "commit", "--quiet", "-m", "test source")
        return self.git("rev-parse", "HEAD")

    def test_pinned_snapshot_ignores_uncommitted_android_changes(self):
        self.write(LESSON_PATH, document([{**REAL_CHOICE, "correctIndex": 2}])["content"])
        self.write(self.engine_path, "changed uncommitted evaluator\n")
        sources, engines = read_git_sources(self.repo, self.commit, [STARTER_UNITS[0]], ["es"])
        catalog, _ = build_catalog(sources, self.commit, engines)
        self.assertEqual(catalog["exercises"][0]["spec"]["correct_index"], 1)
        self.assertIn("changed uncommitted", (self.repo / self.engine_path).read_text())

    def test_changed_published_evaluator_is_refused_before_source_import(self):
        self.write(self.engine_path, "changed committed evaluator\n")
        commit = self.save_commit()
        with self.assertRaisesRegex(CatalogError, "source_evaluator_changed"):
            read_git_sources(self.repo, commit, [STARTER_UNITS[0]], ["es"])

    def test_manifest_prevents_archived_unlisted_lesson_from_becoming_authority(self):
        hidden = LESSON_PATH.replace("lesson_problemas_instrucciones_y_resultados", "lesson_archived")
        self.write(hidden, '{"not_a_published_lesson":true}\n')
        commit = self.save_commit()
        sources, _ = read_git_sources(self.repo, commit, [STARTER_UNITS[0]], ["es"])
        self.assertEqual([source["path"] for source in sources], [LESSON_PATH])

    def test_unpublished_unit_and_symlinked_source_are_rejected(self):
        with self.assertRaises(CatalogError):
            read_git_sources(self.repo, self.commit, ["programming/cpp_fundamentals/archived"], ["es"])
        source = self.repo / LESSON_PATH
        source.unlink()
        source.symlink_to("outside.json")
        commit = self.save_commit()
        with self.assertRaisesRegex(CatalogError, "missing_or_invalid_curriculum_source"):
            read_git_sources(self.repo, commit, [STARTER_UNITS[0]], ["es"])

    def test_cli_produces_reviewable_files_and_requires_replace_for_existing_outputs(self):
        output, coverage = self.base / "rules.json", self.base / "coverage.json"
        arguments = ["--repo", str(self.repo), "--commit", self.commit, "--unit", STARTER_UNITS[0], "--locale", "es", "--output", str(output), "--coverage", str(coverage)]
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(main(arguments), 0)
            before = output.read_bytes()
            self.assertEqual(main(arguments), 1)
            self.assertEqual(output.read_bytes(), before)
            self.assertEqual(main(arguments + ["--replace"]), 0)
        self.assertEqual(len(ExerciseCatalog.from_file(output).rules), 1)
        self.assertEqual(json.loads(coverage.read_text())["source_commit"], self.commit)
        self.assertEqual(self.git("status", "--porcelain"), "")


if __name__ == "__main__":
    unittest.main()
