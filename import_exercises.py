"""Compile a local published Android Git snapshot into an operator catalog.

No checkout or Android file is changed. Git blobs are read by an explicit commit
SHA, so uncommitted edits cannot acquire false published provenance. Runtime
ServerTec never invokes this tool. Unsupported interactive blocks are reported
individually and are not installed as evaluable exercises.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from exercise_catalog import (
    CatalogError, EVALUATOR_VERSION, ExerciseCatalog, MAX_CATALOG_BYTES, MAX_ITEMS,
    _canonical, _check, _identifier, _keys, _number, _finite_fraction,
    _text, _validate_response_spec, rule_version, strict_json_loads,
)


REPOSITORY = "SimDynamics/LearnGraphicsProgramming"
CONTENT_ROOT = "app/src/main/assets/content"
STARTER_UNITS = (
    "programming/cpp_fundamentals/programas_y_ejecucion",
    "math_physics/math_course_01/numeros_y_operaciones",
)
MAX_SOURCE_BYTES = 2 * 1024 * 1024
# A changed Android evaluator must be reviewed before importing new rules. This
# check intentionally errs toward refusing a changed source, even for UI edits.
EXPECTED_ENGINE_BLOBS = {
    "app/src/main/java/com/learngraphicsprogramming/app/LessonActivity.kt": "d1d471a226f93418d552013a237741d08c2f5e1d",
    "app/src/main/java/com/learngraphicsprogramming/app/CppExerciseAnswers.kt": "9732172d9cb31c129ffb9c3f8eb160914b4fc3d5",
    "app/src/main/java/com/learngraphicsprogramming/app/math/MathValidators.kt": "07df271a48befbceb7d8b2fc7e661a01708d7345",
    "app/src/main/java/com/learngraphicsprogramming/app/math/MathPuzzleSpec.kt": "c8ea1683694d08e8f553e87874d7602bb9d99449",
    "app/src/main/java/com/learngraphicsprogramming/app/math/MathAnswer.kt": "46af0e47c284a486555c81e72eb71851f46fcdde",
    "app/src/main/java/com/learngraphicsprogramming/app/math/MathPuzzleRenderer.kt": "cd41bd57da1a38be37d6fc79a21f38133a22254b",
}
NON_INTERACTIVE_BLOCKS = {"heading", "paragraph", "note", "code"}
_LESSON_PATH = re.compile(
    r"app/src/main/assets/content/(es|en|fr)/(programming|math_physics)/"
    r"([A-Za-z0-9_]+)/([A-Za-z0-9_]+)/lesson_([A-Za-z0-9_]+)\.json\Z"
)
_MATH_TEXT_TYPES = {"math_numeric_input", "math_expression_input"}
_MATH_FIELDS_TYPES = {"math_multi_input", "math_structured_answer", "math_equation_fill_blanks"}


class Unsupported(Exception):
    pass


def _known_keys(value, required, optional=()):
    _check(type(value) is dict and set(required) <= set(value), "invalid_curriculum")
    if not set(value) <= set(required) | set(optional):
        raise Unsupported("unrecognized_validation_options")


def _authored_ids(raw, key):
    values = raw.get(key)
    _check(type(values) is list and 1 <= len(values) <= MAX_ITEMS, "invalid_curriculum")
    ids = []
    for value in values:
        _check(type(value) is dict, "invalid_curriculum")
        ids.append(_identifier(value.get("id"), "invalid_curriculum"))
    _check(len(set(ids)) == len(ids), "duplicate_curriculum_id")
    return ids


def _scalar(validator):
    _check(type(validator) is dict and type(validator.get("type")) is str, "invalid_curriculum")
    kind = validator["type"]
    if kind in ("numeric", "tolerance", "exact_fraction"):
        _known_keys(validator, ("type", "expected"), ("tolerance",))
        expected = validator["expected"]
        _check(type(expected) in (str, int, float), "invalid_curriculum")
        # JSONObject Double.toString is not Python float repr at every edge.
        # The initial curriculum authors expected values as strings. Refuse
        # unreviewed floating JSON normalization instead of changing its value.
        if type(expected) is float:
            raise Unsupported("numeric_json_double_not_imported")
        expected = str(expected)
        tolerance = validator.get("tolerance", 1e-6 if kind == "tolerance" else 0)
        _check(type(tolerance) in (int, float), "invalid_curriculum")
        if tolerance != 0:
            raise Unsupported("nonzero_numeric_tolerance_not_imported")
        return {"kind": "number", "spec": {
            "expected": expected, "tolerance": "0",
            "finite_required": kind != "exact_fraction",
        }}
    if kind in ("text", "exact_text"):
        _known_keys(validator, ("type", "expected"))
        _text(validator["expected"], code="invalid_curriculum")
        return {"kind": "text", "spec": {"expected": validator["expected"]}}
    raise Unsupported("unsupported_validator:" + kind)


def compile_math_response(raw):
    _check(type(raw) is dict, "invalid_curriculum")
    identifier = _identifier(raw.get("id"), "invalid_curriculum")
    original_type, validator = raw.get("type"), raw.get("validator")
    _check(type(original_type) is str and type(validator) is dict, "invalid_curriculum")
    validator_type = validator.get("type")
    _check(type(validator_type) is str, "invalid_curriculum")
    fields_response = original_type in _MATH_FIELDS_TYPES or (original_type in _MATH_TEXT_TYPES and "fields" in raw)
    if original_type in _MATH_TEXT_TYPES and not fields_response:
        compiled = _scalar(validator)
    elif original_type in ("math_multiple_choice_single", "math_multiple_choice_multi"):
        if validator_type != "choice":
            raise Unsupported("unsupported_validator:" + validator_type)
        _known_keys(validator, ("type", "expected"))
        compiled = {"kind": "choice", "spec": {
            "options": _authored_ids(raw, "options"), "expected": validator["expected"],
            "multiple": original_type == "math_multiple_choice_multi",
        }}
    elif original_type == "math_ordering_drag":
        if validator_type != "order":
            raise Unsupported("unsupported_validator:" + validator_type)
        _known_keys(validator, ("type", "expected"))
        compiled = {"kind": "order", "spec": {"items": _authored_ids(raw, "items"), "expected": validator["expected"]}}
    elif original_type == "math_matching_drag":
        if validator_type != "matching":
            raise Unsupported("unsupported_validator:" + validator_type)
        _known_keys(validator, ("type", "expected"))
        compiled = {"kind": "matching", "spec": {
            "sources": _authored_ids(raw, "sources"), "targets": _authored_ids(raw, "targets"),
            "expected": validator["expected"],
        }}
    elif fields_response:
        if validator_type != "fields":
            raise Unsupported("unsupported_validator:" + validator_type)
        _known_keys(validator, ("type", "fields"))
        _authored_ids(raw, "fields")
        definitions = raw["fields"]
        editable, options = {}, {}
        for field in definitions:
            field_type = field.get("type", "numeric")
            if field_type not in ("numeric", "expression", "dropdown", "fixed"):
                raise Unsupported("unsupported_field_type:" + str(field_type))
            if field_type != "fixed":
                editable[field["id"]] = field
            elif type(field.get("text")) is not str:
                raise CatalogError("invalid_curriculum")
        expected = validator["fields"]
        _check(type(expected) is dict and set(expected) == set(editable), "invalid_curriculum")
        fields = {identifier: _scalar(value) for identifier, value in expected.items()}
        for name, field in editable.items():
            if field.get("type", "numeric") == "dropdown":
                if fields[name]["kind"] != "text":
                    raise Unsupported("unsupported_dropdown_validator")
                options[name] = _authored_ids(field, "options")
        compiled = {"kind": "fields", "spec": {"fields": fields, "options": options}}
    else:
        raise Unsupported("unsupported_response_type:" + original_type + ":validator:" + validator_type)
    result = {"id": identifier, **compiled}
    _validate_response_spec(result)
    return result


def compile_block(block, route):
    kind = block.get("type")
    _check(type(kind) is str, "invalid_curriculum")
    if route == "programming" and kind == "multiple_choice":
        _known_keys(block, ("type", "id", "question", "options", "correctIndex"), ("explanation", "reviewFeedback"))
        options = block["options"]
        _check(type(options) is list and all(type(option) is str and option for option in options), "invalid_curriculum")
        return kind, {"option_count": len(options), "correct_index": block["correctIndex"]}
    if route == "programming" and kind == "order_code":
        _known_keys(block, ("type", "id", "question", "fragments", "correctOrder"), ("explanation", "reviewFeedback"))
        return kind, {"fragments": block["fragments"], "correct_order": block["correctOrder"]}
    if route == "programming" and kind == "output_prediction":
        _known_keys(block, ("type", "id", "question", "answers"), ("language", "code", "outputComparison", "explanation", "reviewFeedback"))
        return kind, {"answers": block["answers"], "comparison": block.get("outputComparison", "trimmed")}
    if route == "math_physics" and kind == "math_puzzle":
        _known_keys(block, ("type", "id", "responses"), ("schemaVersion", "version", "prompt", "question", "representations", "tools", "feedback"))
        for key in ("schemaVersion", "version"):
            if key in block and not (type(block[key]) is int and block[key] == 1):
                raise Unsupported("unsupported_math_schema")
        responses = block["responses"]
        _check(type(responses) is list and 1 <= len(responses) <= MAX_ITEMS, "invalid_curriculum")
        return kind, {"responses": [compile_math_response(response) for response in responses]}
    if kind in ("fill_code", "inline_fill_code", "drag_fill_code"):
        raise Unsupported("cpp_fill_normalization_not_ported")
    if kind == "cpp_compiler":
        raise Unsupported("compiler_execution_not_supported")
    raise Unsupported("unsupported_block_type:" + kind)


def build_catalog(documents, commit, evaluator_blobs, *, repository=REPOSITORY):
    """Compile verified source blobs; no I/O. Used by the CLI and provenance QA."""
    _check(repository == REPOSITORY, "unauthorized_curriculum_repository")
    _check(type(commit) is str and re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "invalid_source_commit")
    _check(evaluator_blobs == EXPECTED_ENGINE_BLOBS, "source_evaluator_changed")
    _check(type(documents) is list and 1 <= len(documents) <= 4096, "invalid_curriculum")
    exercises, omitted, sources = [], [], []
    accepted_counts, omitted_counts = Counter(), Counter()
    seen_paths, seen_ids = set(), set()
    for document in sorted(documents, key=lambda item: item["path"]):
        _keys(document, ("path", "blob_sha", "content"))
        path, content, blob_sha = document["path"], document["content"], document["blob_sha"]
        _check(type(path) is str and path not in seen_paths, "duplicate_source_path")
        match = _LESSON_PATH.fullmatch(path)
        _check(match is not None, "invalid_source_path")
        locale, route, course, unit, slug = match.groups()
        _check(type(content) is str, "invalid_curriculum")
        encoded = content.encode("utf-8")
        _check(len(encoded) <= MAX_SOURCE_BYTES, "curriculum_source_too_large")
        digest = hashlib.sha1(b"blob " + str(len(encoded)).encode("ascii") + b"\x00" + encoded).hexdigest()
        _check(blob_sha == digest, "source_blob_hash_mismatch")
        lesson = strict_json_loads(content)
        _check(type(lesson) is dict and lesson.get("id") == f"{course}__{unit}__{slug}", "lesson_path_id_mismatch")
        lesson_id = _identifier(lesson["id"], "invalid_curriculum")
        pages = lesson.get("pages")
        _check(type(pages) is list and 1 <= len(pages) <= 4096, "invalid_curriculum")
        seen_paths.add(path)
        source_count, excluded_count, noninteractive = 0, 0, 0
        for page_index, page in enumerate(pages):
            _check(type(page) is dict and type(page.get("blocks")) is list and len(page["blocks"]) <= 4096, "invalid_curriculum")
            for block_index, block in enumerate(page["blocks"]):
                _check(type(block) is dict and type(block.get("type")) is str, "invalid_curriculum")
                if block["type"] in NON_INTERACTIVE_BLOCKS:
                    noninteractive += 1
                    continue
                block_id = _identifier(block.get("id", f"page_{page_index}_block_{block_index}"), "invalid_curriculum")
                identifier = _identifier(f"{locale}/{route}/{lesson_id}/{block_id}", "invalid_curriculum")
                _check(identifier not in seen_ids, "duplicate_curriculum_exercise")
                seen_ids.add(identifier)
                source = {
                    "repository": repository, "commit": commit, "path": path, "blob_sha": blob_sha,
                    "block_sha256": hashlib.sha256(_canonical(block).encode("utf-8")).hexdigest(),
                    "lesson_id": lesson_id, "block_id": block_id,
                    "page_index": page_index, "block_index": block_index,
                }
                try:
                    kind, spec = compile_block(block, route)
                    rule = {"id": identifier, "route": route, "kind": kind, "source": source, "spec": spec}
                    rule["version"] = rule_version(rule)
                    ExerciseCatalog.from_dict({"schema_version": 1, "evaluator": EVALUATOR_VERSION, "exercises": [rule]})
                except (Unsupported, CatalogError) as exc:
                    reason = str(exc) if isinstance(exc, Unsupported) else "invalid_rule:" + exc.code
                    omitted.append({"id": identifier, "kind": block["type"], "reason": reason, "source": source})
                    omitted_counts[f"{locale}/{route}/{block['type']}"] += 1
                    excluded_count += 1
                    continue
                exercises.append(rule)
                accepted_counts[f"{locale}/{route}/{kind}"] += 1
                source_count += 1
        sources.append({"path": path, "blob_sha": blob_sha, "lesson_id": lesson_id,
                        "installed_exercises": source_count, "omitted_interactive_blocks": excluded_count,
                        "non_interactive_blocks": noninteractive})
    catalog = {"schema_version": 1, "evaluator": EVALUATOR_VERSION, "exercises": exercises}
    ExerciseCatalog.from_dict(catalog)
    _check(len((_canonical(catalog) + "\n").encode("utf-8")) <= MAX_CATALOG_BYTES, "catalog_too_large")
    coverage = {
        "schema_version": 1, "repository": repository, "source_commit": commit,
        "evaluator": EVALUATOR_VERSION, "verified_engine_blobs": dict(evaluator_blobs),
        "scope": "Only the listed source lessons; this is not the complete curriculum.",
        "installed_exercises": len(exercises), "omitted_interactive_blocks": len(omitted),
        "counts_installed": dict(sorted(accepted_counts.items())),
        "counts_omitted": dict(sorted(omitted_counts.items())),
        "sources": sources, "omitted": omitted,
    }
    return catalog, coverage


def _git(repo, *args):
    try:
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True, timeout=30)
        return result.stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise CatalogError("cannot_read_local_git_snapshot") from exc


def read_git_sources(repo, commit, units, locales):
    _check(type(commit) is str and re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "invalid_source_commit")
    _check(_git(repo, "rev-parse", "--verify", commit + "^{commit}").decode("ascii").strip() == commit, "invalid_source_commit")
    tree = {}
    for entry in _git(repo, "ls-tree", "-r", "-l", "-z", commit).split(b"\x00"):
        if not entry:
            continue
        metadata, path = entry.split(b"\t", 1)
        mode, kind, sha, size = metadata.split()
        if kind == b"blob":
            tree[path.decode("utf-8")] = (sha.decode("ascii"), int(size), mode)
    engines = {path: tree.get(path, (None, 0, b""))[0] for path in EXPECTED_ENGINE_BLOBS}
    _check(engines == EXPECTED_ENGINE_BLOBS, "source_evaluator_changed")

    def read(path):
        item = tree.get(path)
        _check(item is not None and item[1] <= MAX_SOURCE_BYTES and item[2] in (b"100644", b"100755"), "missing_or_invalid_curriculum_source")
        data = _git(repo, "show", commit + ":" + path)
        _check(len(data) == item[1], "source_blob_size_mismatch")
        return {"path": path, "blob_sha": item[0], "content": data.decode("utf-8")}

    paths = set()
    for unit_path in units:
        _check(type(unit_path) is str and re.fullmatch(r"(programming|math_physics)/[A-Za-z0-9_]+/[A-Za-z0-9_]+", unit_path) is not None, "invalid_unit")
        route, course, slug = unit_path.split("/")
        for locale in locales:
            _check(locale in ("es", "en", "fr"), "invalid_locale")
            base = f"{CONTENT_ROOT}/{locale}/{route}/{course}"
            course_data = strict_json_loads(read(f"{base}/course_{course}.json")["content"])
            _check(course_data.get("id") == course and type(course_data.get("units")) is list and
                   f"{course}__{slug}" in [entry.get("id") for entry in course_data["units"]], "unit_not_published")
            unit_data = strict_json_loads(read(f"{base}/{slug}/unit_{slug}.json")["content"])
            _check(unit_data.get("courseId") == course and unit_data.get("unitId") == f"{course}__{slug}" and type(unit_data.get("lessons")) is list, "invalid_unit_manifest")
            for lesson in unit_data["lessons"]:
                identifier = _identifier(lesson.get("id"), "invalid_curriculum")
                parts = identifier.split("__")
                _check(len(parts) == 3 and parts[:2] == [course, slug], "invalid_lesson_manifest")
                path = f"{base}/{slug}/lesson_{parts[2]}.json"
                _check(path not in paths, "duplicate_lesson_manifest")
                paths.add(path)
    return [read(path) for path in sorted(paths)], engines


def _write_json(path, value, *, replace=False):
    path = Path(path)
    _check(replace or not path.exists(), "output_exists_use_replace")
    encoded = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    _check(len(encoded) <= MAX_CATALOG_BYTES, "catalog_too_large")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".catalog-", delete=False) as file:
            temporary = Path(file.name)
            file.write(encoded)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path, help="Local Android Git repository (read only)")
    parser.add_argument("--commit", required=True, help="Published 40-character source commit SHA")
    parser.add_argument("--unit", action="append", help="route/course/unit; defaults to both initial units")
    parser.add_argument("--locale", action="append", choices=("es", "en", "fr"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--coverage", required=True, type=Path)
    parser.add_argument("--replace", action="store_true", help="Replace the specified catalog/report files")
    args = parser.parse_args(argv)
    try:
        _check(args.output.resolve() != args.coverage.resolve(), "output_and_coverage_must_differ")
        _check(args.replace or not args.output.exists() and not args.coverage.exists(), "output_exists_use_replace")
        documents, engines = read_git_sources(args.repo, args.commit, args.unit or STARTER_UNITS, args.locale or ("es", "en", "fr"))
        catalog, coverage = build_catalog(documents, args.commit, engines)
        _write_json(args.coverage, coverage, replace=args.replace)
        _write_json(args.output, catalog, replace=args.replace)
        print(json.dumps({"installed_exercises": coverage["installed_exercises"],
                          "omitted_interactive_blocks": coverage["omitted_interactive_blocks"],
                          "source_lessons": len(coverage["sources"]), "source_commit": args.commit}))
        return 0
    except (CatalogError, UnicodeError, OSError) as exc:
        print("Import failed: " + (exc.code if isinstance(exc, CatalogError) else str(exc)), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
