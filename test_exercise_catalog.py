"""Real-curriculum grading and adversarial input contracts, with no network."""
import copy
from dataclasses import FrozenInstanceError
from fractions import Fraction
import json
from pathlib import Path
import tempfile
import unittest

from exercise_catalog import (
    CatalogError, EVALUATOR_VERSION, ExerciseCatalog, MAX_ANSWER_BYTES,
    _number, rule_version, strict_json_loads,
)


CATALOG_PATH = Path(__file__).with_name("rules-catalog.json")


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        cls.catalog = ExerciseCatalog.from_file(CATALOG_PATH)

    def rule(self, block, locale="es"):
        found = [rule for rule in self.catalog.rules if rule.source["block_id"] == block and rule.id.startswith(locale + "/")]
        self.assertEqual(len(found), 1, block)
        return found[0]

    def variant(self, block, spec, *, kind=None):
        raw = copy.deepcopy(next(value for value in self.data["exercises"]
                                 if value["source"]["block_id"] == block and value["id"].startswith("es/")))
        raw["spec"] = spec
        if kind is not None:
            raw["kind"] = kind
        raw["version"] = rule_version(raw)
        document = {"schema_version": 1, "evaluator": EVALUATOR_VERSION, "exercises": [raw]}
        return ExerciseCatalog.from_dict(document).rules[0]

    def rejected(self, rule, answer):
        with self.assertRaises(CatalogError):
            rule.validate_answer(answer)
        with self.assertRaises(CatalogError):
            rule.evaluate(answer)

    def test_real_first_question_in_all_three_languages(self):
        for locale in ("es", "en", "fr"):
            rule = self.rule("objetivo_etiqueta", locale)
            self.assertTrue(rule.evaluate(1))
            self.assertFalse(rule.evaluate(0))
            self.assertFalse(rule.evaluate(2))
            self.assertEqual(rule.route, "programming")

    def test_choice_integer_type_is_not_boolean_float_string_or_null(self):
        rule = self.rule("objetivo_etiqueta")
        for value in (True, False, 1.0, "1", None, [], {}, -1, 3, 1 << 63):
            with self.subTest(value=value):
                self.rejected(rule, value)

    def test_exact_output_preserves_spaces_newlines_quotes_and_language(self):
        for locale, expected in (("es", "Archivo preparado"), ("en", "File ready"), ("fr", "Fichier préparé")):
            rule = self.rule("literal_independiente", locale)
            self.assertTrue(rule.evaluate(expected))
            for wrong in (" " + expected, expected + "\n", '"' + expected + '"', expected.replace(" ", "  ")):
                self.assertFalse(rule.evaluate(wrong))
            for incomplete in ("", "\n\t", 0, True, {"answer": expected, "correct": True}):
                self.rejected(rule, incomplete)

    def test_trimmed_output_matches_kotlin_whitespace_without_erasing_nel(self):
        rule = self.variant("literal_independiente", {"answers": ["Listo\n12"], "comparison": "trimmed"})
        self.assertTrue(rule.evaluate("\u00a0\tListo\n12\r\n"))
        self.assertFalse(rule.evaluate("Listo 12"))
        self.assertFalse(rule.evaluate("\u0085Listo\n12"))

    def test_order_uses_original_fragment_text_not_client_indices(self):
        rule = self.rule("armar_programa")
        correct = ["#include <iostream>", "int main() {", '    std::cout << "Acceso autorizado";', "    return 0;\n}"]
        self.assertTrue(rule.evaluate(correct))
        self.assertFalse(rule.evaluate(list(reversed(correct))))
        self.rejected(rule, [1, 3, 0, 2])
        self.rejected(rule, correct[:-1])
        self.rejected(rule, correct[:-1] + [correct[0]])
        self.rejected(rule, [line.strip() for line in correct])

    def test_duplicate_authored_fragments_retain_multiplicity(self):
        rule = self.variant("armar_programa", {"fragments": ["a;", "a;", "b;"], "correct_order": [0, 2, 1]})
        self.assertTrue(rule.evaluate(["a;", "b;", "a;"]))
        self.assertFalse(rule.evaluate(["b;", "a;", "a;"]))
        self.rejected(rule, ["a;", "b;", "b;"])

    def test_math_numeric_equivalent_fraction_decimal_percent(self):
        rule = self.rule("referencia_altura")
        for value in ("-3", " −3 ", "-6/2", "-3,0", "-3e0", "-300%", "−٦/٢"):
            self.assertTrue(rule.evaluate({"referencia_altura__valor": {"type": "text", "value": value}}), value)
        self.assertFalse(rule.evaluate({"referencia_altura__valor": {"type": "text", "value": "3"}}))
        self.assertEqual(rule.route, "math_physics")

    def test_numeric_parser_rejects_expressions_extensions_and_resource_abuse(self):
        rule = self.rule("referencia_altura")
        for value in ("", "1/0", "1/2/3", "3 + 0", "-3f", "1_000", "NaN", "Infinity",
                      "1e9999999999999999999999", "1e1001", "0." + "0" * 254 + "1",
                      "__import__('os').system('echo invalid')", "-3\x00", "-3%%", "𝟙", "1e𝟙"):
            with self.subTest(value=value):
                self.rejected(rule, {"referencia_altura__valor": {"type": "text", "value": value}})
        for value in (True, -3, -3.0, None, [], {}):
            self.rejected(rule, {"referencia_altura__valor": {"type": "text", "value": value}})

    def test_fraction_arithmetic_does_not_round_large_adjacent_integers(self):
        value = "9007199254740993"
        rule = self.variant("referencia_altura", {"responses": [{"id": "n", "kind": "number", "spec": {
            "expected": value, "tolerance": "0", "finite_required": True}}]})
        self.assertTrue(rule.evaluate({"n": {"type": "text", "value": value}}))
        self.assertFalse(rule.evaluate({"n": {"type": "text", "value": "9007199254740992"}}))
        self.assertEqual(_number("1e-1000"), Fraction(1, 10 ** 1000))

    def test_numeric_finiteness_matches_android_decimal64_rounding_boundary(self):
        rule = self.rule("referencia_altura")
        for value in ("1.7976931348623156e308", "-1.7976931348623156e308", "1e309", "-1e309"):
            self.rejected(rule, {"referencia_altura__valor": {"type": "text", "value": value}})
        for value in ("1.797693134862315e308", "-1.797693134862315e308"):
            self.assertFalse(rule.evaluate({"referencia_altura__valor": {"type": "text", "value": value}}))

    def test_exact_fraction_can_compare_large_values_that_numeric_rejects(self):
        rule = self.variant("referencia_altura", {"responses": [{"id": "n", "kind": "number", "spec": {
            "expected": "-3", "tolerance": "0", "finite_required": False}}]})
        self.assertFalse(rule.evaluate({"n": {"type": "text", "value": "1e1000"}}))

    def test_absolute_tolerance_is_rational_and_boundary_inclusive(self):
        rule = self.variant("referencia_altura", {"responses": [{"id": "n", "kind": "number", "spec": {
            "expected": "1/3", "tolerance": "0.01", "finite_required": True}}]})
        for answer in ("97/300", "103/300"):
            self.assertTrue(rule.evaluate({"n": {"type": "text", "value": answer}}))
        self.assertFalse(rule.evaluate({"n": {"type": "text", "value": "104/300"}}))

    def test_math_multi_choice_is_a_complete_set_with_valid_option_ids(self):
        rule = self.rule("divisiones_definidas")
        def answer(values):
            return {"divisiones_definidas__eleccion": {"type": "choice", "selected": values}}
        self.assertTrue(rule.evaluate(answer(["d", "a"])))
        self.assertFalse(rule.evaluate(answer(["a"])))
        for values in ([], ["a", "a"], ["a", "unknown"], [True], "a", None):
            self.rejected(rule, answer(values))

    def test_math_matching_and_order_require_all_items_exactly_once(self):
        matching = self.rule("opuestos")
        self.assertTrue(matching.evaluate({"opuestos__relaciones": {"type": "matching", "pairs": {"c": "z", "b": "x", "a": "y"}}}))
        self.assertFalse(matching.evaluate({"opuestos__relaciones": {"type": "matching", "pairs": {"a": "x", "b": "y", "c": "z"}}}))
        for pairs in ({"a": "y"}, {"a": "y", "b": "y", "c": "z"}, {"a": "q", "b": "x", "c": "z"}):
            self.rejected(matching, {"opuestos__relaciones": {"type": "matching", "pairs": pairs}})
        order = self.rule("orden_enteros")
        self.assertTrue(order.evaluate({"orden_enteros__orden": {"type": "order", "ids": ["a", "b", "c", "d", "e"]}}))
        self.assertFalse(order.evaluate({"orden_enteros__orden": {"type": "order", "ids": ["e", "d", "c", "b", "a"]}}))
        self.rejected(order, {"orden_enteros__orden": {"type": "order", "ids": ["a", "a", "c", "d", "e"]}})

    def test_incomplete_later_field_does_not_hide_behind_earlier_wrong_field(self):
        rule = self.rule("descomponer_ceros")
        self.assertTrue(rule.evaluate({"descomponer_ceros__datos": {"type": "fields", "values": {"u": "6", "m": "5000"}}}))
        self.assertFalse(rule.evaluate({"descomponer_ceros__datos": {"type": "fields", "values": {"m": "500", "u": "6"}}}))
        for values in ({"m": "500", "u": ""}, {"m": "500", "u": "1/0"}, {"m": "500"}, {"m": "500", "u": "6", "extra": "0"}):
            self.rejected(rule, {"descomponer_ceros__datos": {"type": "fields", "values": values}})

    def test_entire_composition_is_validated_before_any_wrong_verdict(self):
        number = {"kind": "number", "spec": {"expected": "4", "tolerance": "0", "finite_required": True}}
        rule = self.variant("referencia_altura", {"responses": [{"id": "first", **number}, {"id": "last", **number}]})
        self.rejected(rule, {"first": {"type": "text", "value": "5"}, "last": {"type": "text", "value": ""}})
        self.rejected(rule, {"first": {"type": "text", "value": "5"}})
        self.assertFalse(rule.evaluate({"first": {"type": "text", "value": "5"}, "last": {"type": "text", "value": "4"}}))

    def test_client_cannot_override_validator_type_route_expected_or_result(self):
        rule = self.rule("referencia_altura")
        for extra in ({"correct": True}, {"expected": "3"}, {"route": "programming"}, {"validator": {"type": "text", "expected": "3"}}):
            self.rejected(rule, {"referencia_altura__valor": {"type": "text", "value": "3", **extra}})
        self.rejected(rule, {"referencia_altura__valor": {"type": "unknown", "value": "-3"}})

    def test_size_depth_nonfinite_and_surrogate_limits(self):
        rule = self.rule("literal_independiente")
        for answer in ("x" * (MAX_ANSWER_BYTES + 1), "é" * (MAX_ANSWER_BYTES // 2), "\ud800", float("nan"), float("inf")):
            self.rejected(rule, answer)
        deep = 0
        for _ in range(10):
            deep = [deep]
        self.rejected(rule, deep)
        cyclic = []
        cyclic.append(cyclic)
        self.rejected(rule, cyclic)

    def test_strict_loading_rejects_duplicates_nan_and_wrong_schema_types(self):
        for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
            with self.assertRaises(CatalogError):
                strict_json_loads(text)
        for bad in (True, 1.0, "1", 2):
            document = {"schema_version": bad, "evaluator": EVALUATOR_VERSION, "exercises": []}
            with self.assertRaises(CatalogError):
                ExerciseCatalog.from_dict(document)

    def test_rule_hash_detects_tampered_expected_and_unknown_comparators(self):
        record = copy.deepcopy(next(r for r in self.data["exercises"] if r["kind"] == "multiple_choice"))
        record["spec"]["correct_index"] = (record["spec"]["correct_index"] + 1) % 3
        document = {"schema_version": 1, "evaluator": EVALUATOR_VERSION, "exercises": [record]}
        with self.assertRaisesRegex(CatalogError, "exercise_version_mismatch"):
            ExerciseCatalog.from_dict(document)
        for spec in ({"answers": ["x"], "comparison": "regex"}, {"answers": ["x"], "comparison": "exact", "pattern": ".*"}):
            with self.assertRaises(CatalogError):
                self.variant("literal_independiente", spec)

    def test_commit_and_blob_metadata_changes_do_not_reset_semantic_version(self):
        record = copy.deepcopy(self.data["exercises"][0])
        original = record["version"]
        record["source"]["commit"] = "f" * 40
        record["source"]["blob_sha"] = "e" * 40
        record["source"]["page_index"] += 1
        self.assertEqual(rule_version(record), original)
        record["source"]["block_sha256"] = "d" * 64
        self.assertNotEqual(rule_version(record), original)

    def test_catalog_deep_freeze_owns_its_data_and_explicit_versions(self):
        data = copy.deepcopy(self.data)
        catalog = ExerciseCatalog.from_dict(data)
        rule = catalog.rules[0]
        data["exercises"][0]["spec"]["responses"][0]["spec"]["expected"] = "99"
        self.assertEqual(rule.spec["responses"][0]["spec"]["expected"], "-3")
        with self.assertRaises(TypeError):
            rule.spec["responses"][0]["spec"]["expected"] = "99"
        with self.assertRaises(FrozenInstanceError):
            rule.route = "programming"
        self.assertIs(catalog.resolve(rule.id, rule.version), rule)
        with self.assertRaisesRegex(CatalogError, "exercise_version_unavailable"):
            catalog.resolve(rule.id, "0" * 64)
        with self.assertRaisesRegex(CatalogError, "unknown_exercise"):
            catalog.resolve("does-not-exist", "0" * 64)
        for version in (True, 1, None, rule.version.upper(), "../catalog"):
            with self.assertRaises(CatalogError):
                catalog.resolve(rule.id, version)

    def test_missing_catalog_never_becomes_an_empty_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(CatalogError, "catalog_unavailable"):
                ExerciseCatalog.from_file(Path(directory) / "missing.json")


if __name__ == "__main__":
    unittest.main()
