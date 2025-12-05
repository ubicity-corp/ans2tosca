#!/usr/bin/env python3
"""
ansible_arg_spec_to_jsonschema_full.py

Usage:
    python ansible_arg_spec_to_jsonschema_full.py /path/to/module.py [--trust-import]

Description:
    - Attempts to extract Ansible module `argument_spec` (and related AnsibleModule constraints)
      and converts it to a JSON Schema (Draft-07 style) plus an "x-ansible" extension object
      carrying constraints that JSON Schema cannot express directly.
    - It first tries static AST extraction (safe). If that fails or is incomplete, and
      --trust-import is given, it will import/execute the module and pull runtime values.
    - Importing executes module top-level code. Only do that for trusted modules.
"""

import ast
import importlib.util
import json
import sys
import os
import argparse
from typing import Any, Dict, Tuple, List, Optional

# --- Mappings ---
TYPE_MAP = {
    "str": "string",
    "string": "string",
    "bool": "boolean",
    "boolean": "boolean",
    "int": "integer",
    "integer": "integer",
    "float": "number",
    "dict": "object",
    "mapping": "object",
    "list": "array",
    "path": "string",
    "raw": None,       # any
    "jsonarg": None,
    "bytes": "string",
}

# --- Helpers for safe AST literal evaluation (best-effort) ---
def safe_literal_eval(node: ast.AST) -> Any:
    """
    Evaluate an AST node into a Python literal when possible.
    Falls back to a marker when not possible.
    """
    try:
        return ast.literal_eval(node)
    except Exception:
        # handle common container constructions (dict merging via {..., **...}) or Name/Attribute
        if isinstance(node, ast.Dict):
            result = {}
            for k, v in zip(node.keys, node.values):
                key = safe_literal_eval(k)
                val = safe_literal_eval(v)
                result[key] = val
            return result
        if isinstance(node, ast.List):
            return [safe_literal_eval(e) for e in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(safe_literal_eval(e) for e in node.elts)
        # Name or attribute or call - can't evaluate safely
        return {"__UNRESOLVED__": ast.dump(node)}
    # unreachable


# --- AST Extraction ---
def extract_from_ast(source: str) -> Tuple[Optional[Dict], Dict]:
    """
    Parse the module source with AST and attempt to find:
      - a top-level variable named argument_spec (literal)
      - AnsibleModule(...) call with keyword argument argument_spec=...
      - other AnsibleModule kwargs: required_one_of, mutually_exclusive, required_together, aliases, required_one_of
    Returns (argument_spec_dict_or_None, constraints_dict)
    constraints_dict contains keys like 'mutually_exclusive', 'required_one_of', 'required_together', 'aliases'
    Any unresolved bits are stored as {"__UNRESOLVED__": <ast_dump>}
    """
    tree = ast.parse(source)
    arg_spec = None
    constraints = {
        "mutually_exclusive": None,
        "required_one_of": None,
        "required_together": None,
        "required_any_of": None,
        "aliases": None,
        # keep raw AST dumps if unresolved
        "_raw": []
    }

    # 1) find assignments to argument_spec
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "argument_spec":
                    value = safe_literal_eval(node.value)
                    arg_spec = value
                    break
        # also handle AnnAssign
        if isinstance(node, ast.AnnAssign):
            t = node.target
            if isinstance(t, ast.Name) and t.id == "argument_spec":
                value = safe_literal_eval(node.value)
                arg_spec = value

    # 2) find AnsibleModule(...) instantiation and keyword args
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # function could be AnsibleModule or something imported as AnsibleModule
            func = node.func
            func_name = None
            if isinstance(func, ast.Name):
                func_name = func.id
            elif isinstance(func, ast.Attribute):
                func_name = func.attr
            if func_name == "AnsibleModule":
                # check keywords
                for kw in node.keywords:
                    if kw.arg == "argument_spec":
                        arg_spec_val = safe_literal_eval(kw.value)
                        arg_spec = arg_spec_val
                    elif kw.arg in ("mutually_exclusive", "required_one_of", "required_together", "required_any_of", "aliases"):
                        constraints[kw.arg] = safe_literal_eval(kw.value)
                # sometimes required_one_of is provided as list-of-lists etc.
    return arg_spec, constraints


# --- Import fallback (exec module) ---
def import_module_from_path(path: str) -> dict:
    """
    Import the module file as a module object (executes top-level code).
    Returns the module.__dict__ mapping for inspection.
    WARNING: This executes module code. Use only for trusted modules.
    """
    spec = importlib.util.spec_from_file_location("__ansible_module_to_load__", path)
    module = importlib.util.module_from_spec(spec)
    # Execute module code
    spec.loader.exec_module(module)
    return module.__dict__


# --- Flatten / normalize Ansible argument_spec into a canonical Python dict structure ---
def normalize_arg_spec(raw: Any) -> Dict:
    """
    Converts extracted raw argument_spec (possibly containing unresolved markers) into
    a canonical dict mapping arg_name -> normalized option dict.
    If raw is unresolved sentinel, return {}
    """
    if raw is None:
        return {}
    if isinstance(raw, dict):
        normalized = {}
        for k, v in raw.items():
            # v expected to be a dict of properties for that arg. If unresolved marker present, keep it.
            if not isinstance(v, dict):
                # sometimes modules use shorthand like arg: dict(type='list') -> ast literal will give dict
                normalized[k] = {"__UNRESOLVED_VALUE__": v}
            else:
                normalized[k] = v.copy()
        return normalized
    # fallback
    return {}


# --- Convert Ansible argument_spec -> JSON Schema (plus x-ansible metadata) ---
def convert_to_jsonschema(arg_spec: Dict, constraints: Dict) -> Dict:
    """
    Build a JSON Schema (Draft-07-like) from arg_spec and attach x-ansible metadata for constraints.
    """
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {},
    }
    required_list = []
    x_ansible = {}

    for arg_name, opts in arg_spec.items():
        if opts is None:
            continue
        # If opts is an unresolved marker, preserve it
        if "__UNRESOLVED__" in getattr(opts, "__dict__", {}) or isinstance(opts, dict) and "__UNRESOLVED__" in opts:
            schema["properties"][arg_name] = {"description": "UNRESOLVED", "x-ansible-raw": opts}
            continue

        # opts should be a dictionary; handle when it's not
        if not isinstance(opts, dict):
            schema["properties"][arg_name] = {"description": "UNRESOLVED_NON_DICT", "x-ansible-raw": opts}
            continue

        prop: Dict = {}

        # handle aliases
        if "aliases" in opts:
            # record aliases in x-ansible on the property
            prop["x-ansible-aliases"] = opts.get("aliases")

        # type mapping
        ans_type = opts.get("type")
        json_type = None
        if ans_type:
            json_type = TYPE_MAP.get(ans_type, None)
        else:
            # sometimes modules don't specify type (default "str")
            json_type = "string"

        if json_type:
            prop["type"] = json_type

        # choices -> enum
        if "choices" in opts:
            prop["enum"] = opts["choices"]

        # default
        if "default" in opts:
            try:
                # ensure JSON serializable for default; if not, still include
                prop["default"] = opts["default"]
            except Exception:
                prop["default"] = str(opts["default"])

        # list 'elements' -> items.type
        if ans_type == "list" and "elements" in opts:
            elem = opts.get("elements")
            elem_type = TYPE_MAP.get(elem, None)
            if elem_type:
                prop["items"] = {"type": elem_type}
            else:
                prop["items"] = {}
                if isinstance(elem, dict):
                    # nested option for items (rare)
                    sub_schema = convert_to_jsonschema(elem, {})  # will set object schema wrapper; adjust
                    # elem was probably a dict of suboptions -> use its properties as item schema
                    if "properties" in sub_schema:
                        prop["items"] = {"type": "object", "properties": sub_schema["properties"]}
        # nested dict 'options' -> object properties
        if "options" in opts and isinstance(opts.get("options"), dict):
            nested = opts["options"]
            nested_schema = convert_to_jsonschema(nested, {})
            # nested_schema is an object wrapper; integrate
            prop["type"] = "object"
            prop["properties"] = nested_schema.get("properties", {})
            if "required" in nested_schema:
                prop["required"] = nested_schema["required"]

        # other Ansible-specific flags we preserve in x-ansible-per-field
        field_meta = {}
        for key in ("required", "no_log", "version_added", "aliases", "elements", "suboptions"):
            if key in opts:
                field_meta[key] = opts[key]
        if field_meta:
            prop.setdefault("x-ansible", {}).update(field_meta)

        # required
        if opts.get("required") is True:
            required_list.append(arg_name)

        # if type was 'raw' or 'jsonarg', relax type (allow any)
        if ans_type in ("raw", "jsonarg"):
            # We cannot represent 'any' cleanly in JSON Schema draft-07 aside from omitting 'type'
            prop.pop("type", None)
            prop["description"] = prop.get("description", "") + " (Ansible raw/jsonarg allowed)"

        schema["properties"][arg_name] = prop

    if required_list:
        schema["required"] = required_list

    # translate top-level constraints
    # JSON Schema can express some of these via anyOf/oneOf combinations, but translating all to schema gets complex;
    # we'll include both best-effort structural translation and raw metadata under x-ansible.
    top_constraints = {}
    if constraints:
        # copy over constraints that may be lists or lists-of-lists
        for k in ("mutually_exclusive", "required_one_of", "required_together", "required_any_of", "aliases"):
            if constraints.get(k) is not None:
                top_constraints[k] = constraints[k]

    # attempt to create JSON Schema conditionals for required_one_of -> anyOf with required lists
    if constraints.get("required_one_of"):
        ro = constraints["required_one_of"]
        # expected shape: list of lists, e.g. [['a','b']]
        if isinstance(ro, (list, tuple)):
            any_of = []
            # each entry could be a list of fields that require at least one present -> use anyOf with "required"?
            # required_one_of in Ansible typically means at least one of the listed fields must be present.
            # Represent as a single "anyOf" where each option is an object that "required": [field]
            # For nested groups, if ro is ['a','b'] -> anyOf: [{"required":["a"]},{"required":["b"]}]
            if all(isinstance(x, (str,)) for x in ro):
                for f in ro:
                    any_of.append({"required": [f]})
            else:
                # possibly list of lists
                for group in ro:
                    if isinstance(group, (list, tuple)):
                        # group means "at least one of these"
                        for f in group:
                            any_of.append({"required": [f]})
            if any_of:
                schema.setdefault("anyOf", []).extend(any_of)
    # mutually_exclusive -> cannot easily be expressed; record in x-ansible
    if constraints.get("mutually_exclusive"):
        top_constraints["mutually_exclusive"] = constraints["mutually_exclusive"]

    if top_constraints:
        schema["x-ansible"] = top_constraints

    return schema


# --- Utilities combining AST/static and import/runtime approaches ---
def load_and_extract(path: str, trust_import: bool = False) -> Tuple[Dict, Dict]:
    """
    Attempt to load module file, extract argument_spec and constraints.
    Returns (arg_spec_dict, constraints)
    """
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    # Try AST extraction first
    ast_spec, ast_constraints = extract_from_ast(src)
    arg_spec = normalize_arg_spec(ast_spec)
    # If AST gave nothing or contains unresolved markers, optionally import
    unresolved = False
    if not arg_spec:
        unresolved = True
    else:
        # check for unresolved markers inside
        for k, v in arg_spec.items():
            if isinstance(v, dict) and any(isinstance(x, dict) and "__UNRESOLVED__" in x for x in v.values() if isinstance(v, dict)):
                unresolved = True
                break

    if unresolved and trust_import:
        # Import runtime module and try to pull runtime values
        moddict = import_module_from_path(path)
        runtime_spec = None
        # try direct variables commonly present
        if "argument_spec" in moddict:
            runtime_spec = moddict["argument_spec"]
        else:
            # attempt to find variables that look like specs
            for name, val in moddict.items():
                if name.endswith("argument_spec") and isinstance(val, dict):
                    runtime_spec = val
                    break
        # If AnsibleModule constructed at runtime, some modules attach module.argspec or similar - attempt to instantiate?
        # Many modules create a variable 'module' after creating AnsibleModule(module_args=...) - but that requires execution
        if runtime_spec is None:
            # scan for any dicts that contain typical keys (type/choices/default)
            # best-effort: find the biggest dict of dicts
            candidates = []
            for name, val in moddict.items():
                if isinstance(val, dict):
                    # heuristics: if values are dicts containing 'type' or 'choices' it's likely an arg spec
                    if all(isinstance(v, dict) for v in val.values()) and any("type" in (list(v.keys())) or "choices" in v for v in val.values()):
                        candidates.append(val)
            if candidates:
                # pick largest
                runtime_spec = max(candidates, key=lambda d: len(d))
        if runtime_spec:
            arg_spec = runtime_spec
            # try to collect constraints from module dict (some modules define them at top-level)
            runtime_constraints = {}
            for key in ("mutually_exclusive", "required_one_of", "required_together", "aliases"):
                if key in moddict:
                    runtime_constraints[key] = moddict[key]
            # Also attempt to capture AnsibleModule kwargs: search for AnsibleModule calls in AST but use import to evaluate
            # Hard to reliably retrieve; keep AST constraints if present, and overlay runtime constraints
            merged_constraints = ast_constraints.copy()
            merged_constraints.update(runtime_constraints)
            return arg_spec, merged_constraints

    # fallback: return AST-extracted
    return arg_spec, ast_constraints


# --- Main CLI ---
def main():
    parser = argparse.ArgumentParser(description="Convert Ansible module argument_spec to JSON Schema")
    parser.add_argument("module_path", help="Path to the Ansible module .py file")
    parser.add_argument("--trust-import", action="store_true", help="Allow importing/executing the module if AST extraction is incomplete. Only use on trusted modules.")
    parser.add_argument("--out", "-o", help="Output filename (default stdout)")
    args = parser.parse_args()

    path = args.module_path
    if not os.path.isfile(path):
        print("ERROR: module path does not exist:", path, file=sys.stderr)
        sys.exit(2)

    try:
        arg_spec, constraints = load_and_extract(path, trust_import=args.trust_import)
    except Exception as e:
        print("ERROR while extracting arg_spec:", e, file=sys.stderr)
        sys.exit(3)

    if not arg_spec:
        print("WARNING: No argument_spec found (or extraction failed). Try --trust-import to import the module.", file=sys.stderr)

    schema = convert_to_jsonschema(arg_spec or {}, constraints or {})

    out_json = json.dumps(schema, indent=2, sort_keys=False, default=str)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out_json)
        print("Wrote JSON Schema to", args.out)
    else:
        print(out_json)


if __name__ == "__main__":
    main()
