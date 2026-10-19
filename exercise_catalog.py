"""Immutable, operator-installed exercise rules and bounded pure evaluators.

The HTTP client selects an installed ID/version and supplies only its answer.
It cannot provide a route, expected answer, validator, regex, or executable code.
Rules are compiled from the published Android curriculum by import_exercises.py.
The importer records original IDs and source Git blob/commit hashes. Runtime
loading performs no network requests and evaluation performs no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
import unicodedata


EVALUATOR_VERSION = "servertec-exercises-v1"
MAX_CATALOG_BYTES = 8 * 1024 * 1024
MAX_ANSWER_BYTES = 8 * 1024
MAX_ITEMS = 128
MAX_RULES = 20_000
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:-]{0,255}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
# Fixed parser, bounded to 256 characters before matching. This is not a
# caller-supplied regular expression. Java BigDecimal accepts decimal digits.
_DECIMAL = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")


class CatalogError(Exception):
    def __init__(self, code: str, status: int = 422):
        super().__init__(code)
        self.code, self.status = code, status


def _check(condition: bool, code: str = "invalid_catalog") -> None:
    if not condition:
        raise CatalogError(code)


def _keys(value, required, optional=(), *, code="invalid_catalog") -> None:
    _check(type(value) is dict or type(value) is MappingProxyType, code)
    _check(set(required) <= set(value) <= set(required) | set(optional), code)


def _identifier(value, code="invalid_catalog") -> str:
    _check(type(value) is str and _ID.fullmatch(value) is not None, code)
    return value


def _text(value, *, maximum=8192, nonblank=True, code="invalid_catalog") -> str:
    _check(type(value) is str and len(value) <= maximum, code)
    _check(not any(0xD800 <= ord(c) <= 0xDFFF or c == "\x00" for c in value), code)
    if nonblank:
        _check(bool(_trim(value)), code)
    return value


def _whitespace(character: str) -> bool:
    # Kotlin Char.isWhitespace = Java isWhitespace || isSpaceChar. Python's
    # str.strip additionally removes U+0085, which must remain significant.
    return character in "\t\n\v\f\r\x1c\x1d\x1e\x1f" or unicodedata.category(character) in ("Zs", "Zl", "Zp")


def _trim(value: str) -> str:
    begin, end = 0, len(value)
    while begin < end and _whitespace(value[begin]):
        begin += 1
    while end > begin and _whitespace(value[end - 1]):
        end -= 1
    return value[begin:end]


def _bounded_json(value, *, answer: bool) -> None:
    code = "invalid_answer" if answer else "invalid_catalog"
    max_depth, max_nodes = (8, 2048) if answer else (24, 2_000_000)
    nodes = 0

    def visit(item, depth):
        nonlocal nodes
        nodes += 1
        _check(depth <= max_depth and nodes <= max_nodes, code)
        if item is None or type(item) is bool:
            return
        if type(item) is int:
            _check(-(1 << 63) <= item < (1 << 63), code)
            return
        if type(item) is float:
            _check(math.isfinite(item), code)
            return
        if type(item) is str:
            _text(item, maximum=8192 if answer else MAX_CATALOG_BYTES,
                  nonblank=False, code=code)
            return
        if type(item) is list:
            _check(not answer or len(item) <= MAX_ITEMS, code)
            for child in item:
                visit(child, depth + 1)
            return
        if type(item) is dict:
            _check(not answer or len(item) <= MAX_ITEMS, code)
            for key, child in item.items():
                _text(key, maximum=256, nonblank=False, code=code)
                visit(child, depth + 1)
            return
        raise CatalogError(code)

    visit(value, 0)
    if answer:
        _check(len(_canonical(value).encode("utf-8")) <= MAX_ANSWER_BYTES, code)


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def rule_version(rule: dict) -> str:
    """Hash rule semantics and its authored block, excluding Git provenance.

    A commit or another block changing must not reset this exercise's identity.
    The complete authored block hash includes question/options/format, so moving
    answer text without changing correctIndex still produces a new version.
    """
    try:
        unsigned = {key: rule[key] for key in ("id", "route", "kind", "spec")}
        unsigned["content_sha256"] = rule["source"]["block_sha256"]
    except (KeyError, TypeError) as exc:
        raise CatalogError("invalid_catalog") from exc
    return hashlib.sha256(_canonical({"evaluator": EVALUATOR_VERSION, "rule": unsigned}).encode("utf-8")).hexdigest()


def strict_json_loads(data: str):
    """Reject duplicate keys and JSON non-finite extensions before compilation."""
    def pairs(items):
        result = {}
        for key, value in items:
            _check(key not in result, "duplicate_json_key")
            result[key] = value
        return result

    def constant(_value):
        raise CatalogError("non_finite_json")

    try:
        result = json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
        _bounded_json(result, answer=False)
        return result
    except (ValueError, TypeError, RecursionError) as exc:
        raise CatalogError("invalid_catalog") from exc


def _freeze(value):
    if type(value) is dict:
        return MappingProxyType({key: _freeze(child) for key, child in value.items()})
    if type(value) is list:
        return tuple(_freeze(child) for child in value)
    return value


def _list(value, *, maximum=MAX_ITEMS):
    _check(type(value) in (list, tuple) and 1 <= len(value) <= maximum)
    return value


def _ids(value):
    items = _list(value)
    for item in items:
        _identifier(item)
    _check(len(set(items)) == len(items))
    return items


def _number(raw, *, code="invalid_answer") -> Fraction:
    """Android Rational.parse: decimals/fractions/percent, without expression eval.

    Input and decimal scale/precision limits mirror MathValidators.kt. A bound
    is checked before Fraction construction, so exponents cannot allocate huge
    integers. Numeric equality never passes through binary floating point.
    """
    _text(raw, maximum=256, code=code)
    # BigDecimal parses Java UTF-16 char digits, not supplementary Unicode
    # code points. Python's \d/Decimal additionally accept astral digits.
    _check(all(ord(character) <= 0xFFFF for character in raw), code)
    source = _trim(raw).replace("−", "-").replace(",", ".")
    percent = source.endswith("%")
    if percent:
        source = _trim(source[:-1])
    parts = source.split("/")
    _check(len(parts) in (1, 2), code)

    def decimal(part):
        part = _trim(part)
        _check(_DECIMAL.fullmatch(part) is not None, code)
        try:
            value = Decimal(part)
            digits = value.as_tuple()
            _check(type(digits.exponent) is int and abs(digits.exponent) <= 1000 and len(digits.digits) <= 256, code)
            return Fraction(value)
        except (InvalidOperation, ValueError, OverflowError) as exc:
            raise CatalogError(code) from exc

    result = decimal(parts[0])
    if len(parts) == 2:
        denominator = decimal(parts[1])
        _check(denominator != 0, code)
        result /= denominator
    if percent:
        result /= 100
    return result


def _finite_fraction(value: Fraction, *, code="invalid_answer") -> None:
    try:
        # Android first divides BigDecimal using MathContext.DECIMAL64, then
        # converts that 16-significant-digit result to Double. Checking the
        # direct Fraction float admits values Android rejects near overflow.
        with localcontext(Context(prec=16, rounding=ROUND_HALF_EVEN)):
            decimal64 = Decimal(value.numerator) / Decimal(value.denominator)
        _check(math.isfinite(float(decimal64)), code)
    except OverflowError as exc:
        raise CatalogError(code) from exc


def _validate_scalar_spec(kind, spec):
    if kind == "number":
        _keys(spec, ("expected", "tolerance", "finite_required"))
        expected = _number(spec["expected"], code="invalid_catalog")
        _finite_fraction(expected, code="invalid_catalog")
        tolerance = _number(spec["tolerance"], code="invalid_catalog")
        _check(tolerance >= 0)
        _finite_fraction(tolerance, code="invalid_catalog")
        _check(type(spec["finite_required"]) is bool)
    elif kind == "text":
        _keys(spec, ("expected",))
        _text(spec["expected"])
    else:
        raise CatalogError("unsupported_validator")


def _validate_response_spec(response):
    _keys(response, ("id", "kind", "spec"))
    _identifier(response["id"])
    kind, spec = response["kind"], response["spec"]
    if kind in ("number", "text"):
        _validate_scalar_spec(kind, spec)
    elif kind == "choice":
        _keys(spec, ("options", "expected", "multiple"))
        options, expected = _ids(spec["options"]), _ids(spec["expected"])
        _check(type(spec["multiple"]) is bool)
        _check(set(expected) <= set(options) and (spec["multiple"] or len(expected) == 1))
    elif kind == "order":
        _keys(spec, ("items", "expected"))
        _check(set(_ids(spec["items"])) == set(_ids(spec["expected"])))
    elif kind == "matching":
        _keys(spec, ("sources", "targets", "expected"))
        sources, targets = _ids(spec["sources"]), _ids(spec["targets"])
        expected = spec["expected"]
        _check(type(expected) in (dict, MappingProxyType) and set(expected) == set(sources))
        _check(all(type(v) is str and v in targets for v in expected.values()))
        _check(len(set(expected.values())) == len(expected))
    elif kind == "fields":
        _keys(spec, ("fields", "options"))
        fields, options = spec["fields"], spec["options"]
        _check(type(fields) in (dict, MappingProxyType) and 1 <= len(fields) <= MAX_ITEMS)
        _check(type(options) in (dict, MappingProxyType) and set(options) <= set(fields))
        for name, field in fields.items():
            _identifier(name)
            _keys(field, ("kind", "spec"))
            _validate_scalar_spec(field["kind"], field["spec"])
        for name, choices in options.items():
            _ids(choices)
            field = fields[name]
            _check(field["kind"] == "text" and field["spec"]["expected"] in choices)
    else:
        raise CatalogError("unsupported_validator")


def _validate_rule_spec(kind, route, spec):
    if kind == "multiple_choice":
        _check(route == "programming")
        _keys(spec, ("option_count", "correct_index"))
        _check(type(spec["option_count"]) is int and 2 <= spec["option_count"] <= MAX_ITEMS)
        _check(type(spec["correct_index"]) is int and 0 <= spec["correct_index"] < spec["option_count"])
    elif kind == "order_code":
        _check(route == "programming")
        _keys(spec, ("fragments", "correct_order"))
        fragments = _list(spec["fragments"])
        for fragment in fragments:
            _text(fragment)
        order = _list(spec["correct_order"])
        _check(len(order) == len(fragments) and all(type(value) is int for value in order) and set(order) == set(range(len(order))))
    elif kind == "output_prediction":
        _check(route == "programming")
        _keys(spec, ("answers", "comparison"))
        for answer in _list(spec["answers"]):
            _text(answer)
        _check(type(spec["comparison"]) is str and spec["comparison"] in ("exact", "trimmed"))
    elif kind == "math_puzzle":
        _check(route == "math_physics")
        _keys(spec, ("responses",))
        responses = _list(spec["responses"])
        for response in responses:
            _validate_response_spec(response)
        _check(len({response["id"] for response in responses}) == len(responses))
    else:
        raise CatalogError("unsupported_exercise_kind")


def _typed(answer, kind, key):
    _keys(answer, ("type", key), code="invalid_answer")
    _check(type(answer["type"]) is str and answer["type"] == kind, "invalid_answer")
    return answer[key]


def _validate_scalar_answer(kind, spec, value):
    _text(value, maximum=256 if kind == "number" else 8192, code="incomplete_answer")
    if kind == "number":
        number = _number(value)
        if spec["finite_required"]:
            _finite_fraction(number)


def _validate_response_answer(response, answer):
    kind, spec = response["kind"], response["spec"]
    if kind in ("number", "text"):
        _validate_scalar_answer(kind, spec, _typed(answer, "text", "value"))
    elif kind == "choice":
        selected = _typed(answer, "choice", "selected")
        _check(type(selected) is list and 1 <= len(selected) <= len(spec["options"]), "incomplete_answer")
        _check(all(type(item) is str and item in spec["options"] for item in selected), "invalid_answer")
        _check(len(set(selected)) == len(selected) and (spec["multiple"] or len(selected) == 1), "invalid_answer")
    elif kind == "order":
        values = _typed(answer, "order", "ids")
        _check(type(values) is list and len(values) == len(spec["items"]), "incomplete_answer")
        _check(all(type(item) is str for item in values), "invalid_answer")
        _check(len(set(values)) == len(values) and set(values) == set(spec["items"]), "incomplete_answer")
    elif kind == "matching":
        pairs = _typed(answer, "matching", "pairs")
        _check(type(pairs) is dict and set(pairs) == set(spec["sources"]), "incomplete_answer")
        _check(all(type(value) is str and value in spec["targets"] for value in pairs.values()), "invalid_answer")
        _check(len(set(pairs.values())) == len(pairs), "incomplete_answer")
    elif kind == "fields":
        values = _typed(answer, "fields", "values")
        _check(type(values) is dict and set(values) == set(spec["fields"]), "incomplete_answer")
        for name, field in spec["fields"].items():
            _validate_scalar_answer(field["kind"], field["spec"], values[name])
            if name in spec["options"]:
                _check(values[name] in spec["options"][name], "invalid_answer")


def _evaluate_scalar(kind, spec, value):
    if kind == "text":
        return value == spec["expected"]
    return abs(_number(value) - _number(spec["expected"])) <= _number(spec["tolerance"])


def _evaluate_response(response, answer):
    kind, spec = response["kind"], response["spec"]
    if kind in ("number", "text"):
        return _evaluate_scalar(kind, spec, answer["value"])
    if kind == "choice":
        return set(answer["selected"]) == set(spec["expected"])
    if kind == "order":
        return tuple(answer["ids"]) == spec["expected"]
    if kind == "matching":
        return answer["pairs"] == spec["expected"]
    if kind == "fields":
        return all(_evaluate_scalar(field["kind"], field["spec"], answer["values"][name])
                   for name, field in spec["fields"].items())
    raise CatalogError("unsupported_validator")


@dataclass(frozen=True)
class ExerciseRule:
    id: str
    version: str
    route: str
    kind: str
    source: object
    spec: object

    def validate_answer(self, answer) -> None:
        """Check every response before an incorrect result may debit a wallet."""
        _bounded_json(answer, answer=True)
        if self.kind == "multiple_choice":
            _check(type(answer) is int and 0 <= answer < self.spec["option_count"], "invalid_answer")
        elif self.kind == "order_code":
            _check(type(answer) is list and len(answer) == len(self.spec["correct_order"]), "incomplete_answer")
            _check(all(type(value) is str for value in answer), "invalid_answer")
            _check(Counter(answer) == Counter(self.spec["fragments"]), "incomplete_answer")
        elif self.kind == "output_prediction":
            _text(answer, code="incomplete_answer")
        elif self.kind == "math_puzzle":
            _check(type(answer) is dict and set(answer) == {response["id"] for response in self.spec["responses"]}, "incomplete_answer")
            for response in self.spec["responses"]:
                _validate_response_answer(response, answer[response["id"]])
        else:
            raise CatalogError("unsupported_exercise_kind")

    def evaluate(self, answer) -> bool:
        self.validate_answer(answer)
        if self.kind == "multiple_choice":
            return answer == self.spec["correct_index"]
        if self.kind == "order_code":
            return tuple(answer) == tuple(self.spec["fragments"][index] for index in self.spec["correct_order"])
        if self.kind == "output_prediction":
            normalized = _trim(answer) if self.spec["comparison"] == "trimmed" else answer
            return any(normalized == (_trim(expected) if self.spec["comparison"] == "trimmed" else expected)
                       for expected in self.spec["answers"])
        if self.kind == "math_puzzle":
            # validate_answer above deliberately visits ALL fields/responses.
            return all(_evaluate_response(response, answer[response["id"]]) for response in self.spec["responses"])
        raise CatalogError("unsupported_exercise_kind")


@dataclass(frozen=True)
class ExerciseCatalog:
    rules: tuple
    _by_id: object
    _known_ids: frozenset

    @classmethod
    def from_file(cls, path):
        try:
            with Path(path).open("rb") as file:
                raw = file.read(MAX_CATALOG_BYTES + 1)
            _check(len(raw) <= MAX_CATALOG_BYTES, "catalog_too_large")
            return cls.from_dict(strict_json_loads(raw.decode("utf-8")))
        except (OSError, UnicodeError) as exc:
            raise CatalogError("catalog_unavailable", 503) from exc

    @classmethod
    def from_dict(cls, document):
        _bounded_json(document, answer=False)
        _keys(document, ("schema_version", "evaluator", "exercises"))
        _check(type(document["schema_version"]) is int and document["schema_version"] == 1)
        _check(document["evaluator"] == EVALUATOR_VERSION)
        _check(type(document["exercises"]) is list and len(document["exercises"]) <= MAX_RULES)
        entries, lookup = [], {}
        for raw in document["exercises"]:
            _keys(raw, ("id", "version", "route", "kind", "source", "spec"))
            identifier = _identifier(raw["id"])
            version = raw["version"]
            _check(type(version) is str and _SHA256.fullmatch(version) is not None)
            _validate_source(raw["source"], raw["route"])
            _check(version == rule_version(raw), "exercise_version_mismatch")
            _check(type(raw["route"]) is str and raw["route"] in ("programming", "math_physics"))
            _check(type(raw["kind"]) is str)
            _validate_rule_spec(raw["kind"], raw["route"], raw["spec"])
            key = (identifier, version)
            _check(key not in lookup, "duplicate_exercise_version")
            entry = ExerciseRule(identifier, version, raw["route"], raw["kind"], _freeze(raw["source"]), _freeze(raw["spec"]))
            entries.append(entry)
            lookup[key] = entry
        return cls(tuple(entries), MappingProxyType(lookup), frozenset(rule.id for rule in entries))

    def resolve(self, exercise_id, exercise_version) -> ExerciseRule:
        _identifier(exercise_id, "invalid_exercise_id")
        _check(type(exercise_version) is str and _SHA256.fullmatch(exercise_version) is not None, "invalid_exercise_version")
        rule = self._by_id.get((exercise_id, exercise_version))
        if rule is None:
            if exercise_id in self._known_ids:
                raise CatalogError("exercise_version_unavailable", 409)
            raise CatalogError("unknown_exercise", 404)
        return rule


def _validate_source(source, route):
    _keys(source, ("repository", "commit", "path", "blob_sha", "block_sha256", "lesson_id", "block_id", "page_index", "block_index"))
    _check(source["repository"] == "SimDynamics/LearnGraphicsProgramming")
    _check(type(source["commit"]) is str and _SHA1.fullmatch(source["commit"]) is not None)
    _check(type(source["blob_sha"]) is str and _SHA1.fullmatch(source["blob_sha"]) is not None)
    _check(type(source["block_sha256"]) is str and _SHA256.fullmatch(source["block_sha256"]) is not None)
    _identifier(source["lesson_id"])
    _identifier(source["block_id"])
    path = source["path"]
    _check(type(path) is str and len(path) <= 512 and re.fullmatch(r"app/src/main/assets/content/(es|en|fr)/(programming|math_physics)/[A-Za-z0-9_]+/[A-Za-z0-9_]+/lesson_[A-Za-z0-9_]+\.json", path) is not None)
    _check(path.split("/")[6] == route)
    for key in ("page_index", "block_index"):
        _check(type(source[key]) is int and 0 <= source[key] <= 4095)
