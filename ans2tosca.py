#!/usr/bin/env python3
"""
ansible_arg_spec_to_jsonschema_complete.py

Full converter: Ansible module argument_spec -> JSON Schema (Draft-07)

Usage:
    python ansible_arg_spec_to_jsonschema_complete.py /path/to/module.py [--trust-import] [-o out.json]
    python ansible_arg_spec_to_jsonschema_complete.py --dir /path/to/collection/plugins/modules [--trust-import] -o schemas_dir/

Notes:
  - This script first tries safe static AST extraction. If that is incomplete and you pass
    --trust-import it will import/execute the module to get runtime-built specs.
  - Importing executes top-level code in the module. ONLY use --trust-import on trusted modules.
  - The converter attempts to express Ansible constraints in JSON Schema where possible, but
    preserves original Ansible constraints in "x-ansible" metadata for anything not representable.
"""

from __future__ import annotations
import ast
import json
import importlib.util
import argparse
import os
import sys
import itertools
from typing import Any, Dict, List, Tuple, Optional, Union

# ----------------------------
# Type mapping (Ansible -> JSON Schema)
# ----------------------------
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
    "sequence": "array",
    "path": "string",
    "raw": None,    # means "any"
    "jsonarg": None,
    "bytes": "string",
}

# ----------------------------
# Utilities: safe AST literal extraction (best-effort)
# ----------------------------
def safe_literal_eval(node: ast.AST) -> Any:
    """
    Evaluate an AST node to a Python literal when possible.
    Returns a Python value or a dict with "__UNRESOLVED__": ast.dump(node).
    """
    try:
        return ast.literal_eval(node)
    except Exception:
        # handle container nodes recursively
        if isinstance(node, ast.Dict):
            out = {}
            for k_node, v_node in zip(node.keys, node.values):
                key = safe_literal_eval(k_node)
                val = safe_literal_eval(v_node)
                out[key] = val
            return out
        if isinstance(node, ast.List):
            return [safe_literal_eval(e) for e in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(safe_literal_eval(e) for e in node.elts)
        if isinstance(node, ast.Set):
            return set(safe_literal_eval(e) for e in node.elts)
        # Name, Attribute, Call, Subscript, etc -> unresolved
        return {"__UNRESOLVED__": ast.dump(node)}

def extract_argument_spec_from_ast(source: str) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """
    Parse source and try to find:
      - top-level 'argument_spec = {...}'
      - AnsibleModule(..., argument_spec=...)
      - capture AnsibleModule kwargs: mutually_exclusive, required_one_of, required_together, aliases
    Returns (arg_spec_or_None, constraints)
    """
    tree = ast.parse(source)
    arg_spec = None
    constraints: Dict[str, Any] = {
        "mutually_exclusive": None,
        "required_one_of": None,
        "required_together": None,
        "required_any_of": None,
        "aliases": None,
        "_raw": []
    }

    # find assignments to argument_spec
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "argument_spec":
                    arg_spec = safe_literal_eval(node.value)
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == "argument_spec":
                arg_spec = safe_literal_eval(node.value)

    # find AnsibleModule(...) call keywords
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # name could be AnsibleModule or something.attr.AnsibleModule
            func = node.func
            func_name = None
            if isinstance(func, ast.Name):
                func_name = func.id
            elif isinstance(func, ast.Attribute):
                func_name = func.attr

            if func_name == "AnsibleModule":
                for kw in node.keywords:
                    if kw.arg == "argument_spec":
                        arg_spec = safe_literal_eval(kw.value)
                    elif kw.arg in ("mutually_exclusive", "required_one_of", "required_together", "required_any_of", "aliases"):
                        constraints[kw.arg] = safe_literal_eval(kw.value)

    return arg_spec, constraints

# ----------------------------
# Import fallback (executes module)
# ----------------------------
def import_module_dict(path: str) -> Dict[str, Any]:
    spec = importlib.util.spec_from_file_location("__ansible_module__", path)
    module = importlib.util.module_from_spec(spec)
    # This executes top-level code; be cautious!
    spec.loader.exec_module(module)
    return vars(module)

# ----------------------------
# Normalize raw argument_spec into canonical mapping
# ----------------------------
def normalize_arg_spec(raw: Any) -> Dict[str, Dict[str, Any]]:
    """
    Convert a raw extracted argument_spec into canonical dict of arg_name -> opts dict.

    Many modules already have the right shape. This function guards against None,
    unresolved placeholders, shorthand not-dict values, etc.
    """
    if raw is None:
        return {}
    if isinstance(raw, dict):
        normalized = {}
        for k, v in raw.items():
            # if v is unresolved marker as dict -> keep it but mark
            if isinstance(v, dict):
                normalized[k] = dict(v)  # shallow copy
            else:
                # sometimes modules put e.g. argument_spec = dict(arg1='string') - unlikely,
                # but if non-dict, wrap into unresolved wrapper
                normalized[k] = {"__UNRESOLVED_VALUE__": v}
        return normalized
    # unexpected shape
    return {"__UNRESOLVED_ARGUMENT_SPEC__": {"value": raw}}

# ----------------------------
# Helpers to convert a single arg option -> JSON Schema prop
# ----------------------------
def convert_field_to_schema(name: str, opts: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[List[str]]]:
    """
    Convert one argument spec entry (opts) into JSON Schema property.
    Returns (property_schema, required_fields_list_if_any)
    """
    prop: Dict[str, Any] = {}
    required_here: Optional[List[str]] = None

    # If opts is an unresolved marker
    if isinstance(opts, dict) and "__UNRESOLVED__" in opts:
        return ({"description": "UNRESOLVED", "x-ansible-raw": opts}, None)
    if not isinstance(opts, dict):
        return ({"description": "UNRESOLVED_NON_DICT", "x-ansible-raw": opts}, None)

    # Type
    ans_type = opts.get("type")
    json_type = TYPE_MAP.get(ans_type) if ans_type else "string"
    if json_type:
        prop["type"] = json_type

    # choices -> enum
    if "choices" in opts:
        # ensure JSON-serializable list
        prop["enum"] = list(opts["choices"])

    # default
    if "default" in opts:
        try:
            json.dumps(opts["default"])
            prop["default"] = opts["default"]
        except Exception:
            prop["default"] = str(opts["default"])

    # regex -> pattern
    if "regex" in opts:
        prop["pattern"] = opts["regex"]

    # elements (for lists)
    if ans_type == "list":
        # elements can be a simple type name or a dict of suboptions (rare)
        elements = opts.get("elements")
        if elements:
            elem_type = TYPE_MAP.get(elements) if isinstance(elements, str) else None
            if elem_type:
                prop.setdefault("type", "array")
                prop["items"] = {"type": elem_type}
            elif isinstance(elements, dict):
                # elements is a dict of suboptions describing object items
                # convert nested dict to schema for items
                nested_schema = convert_arg_spec_section_to_schema(elements)
                # nested_schema is an object wrapper - use its properties as item schema
                prop.setdefault("type", "array")
                prop["items"] = {
                    "type": "object",
                    "properties": nested_schema.get("properties", {})
                }
                if nested_schema.get("required"):
                    prop["items"]["required"] = nested_schema["required"]
            else:
                # fallback - allow any items
                prop.setdefault("type", "array")
                prop["items"] = {}
        else:
            prop.setdefault("type", "array")
            prop["items"] = {}

    # nested options (dict suboptions)
    if "options" in opts and isinstance(opts["options"], dict):
        nested = opts["options"]
        nested_schema = convert_arg_spec_section_to_schema(nested)
        prop["type"] = "object"
        prop["properties"] = nested_schema.get("properties", {})
        if "required" in nested_schema:
            prop["required"] = nested_schema["required"]

    # no_log, fallback, aliases -> preserved as x-ansible metadata per-field
    field_meta = {}
    for meta in ("no_log", "fallback", "aliases", "version_added", "removed_in_version", "apply_defaults"):
        if meta in opts:
            field_meta[meta] = opts[meta]
    if field_meta:
        prop.setdefault("x-ansible", {}).update(field_meta)

    # required
    if opts.get("required") is True:
        required_here = [name]

    # raw/jsonarg type: allow any -> remove type restriction
    if ans_type in ("raw", "jsonarg"):
        prop.pop("type", None)
        prop.setdefault("description", "")
        prop["description"] += " (Ansible raw/jsonarg allowed)"

    return prop, required_here

# ----------------------------
# Convert an entire arg_spec section to JSON Schema (object wrapper)
# ----------------------------
def convert_arg_spec_section_to_schema(arg_spec_section: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a dict mapping arg_name -> opts into a JSON Schema object fragment:
      { "type": "object", "properties": {...}, "required": [...] }
    """
    schema: Dict[str, Any] = {"type": "object", "properties": {}}
    required_fields: List[str] = []
    for arg_name, opts in (arg_spec_section or {}).items():
        prop_schema, req = convert_field_to_schema(arg_name, opts)
        schema["properties"][arg_name] = prop_schema
        if req:
            required_fields.extend(req)
    if required_fields:
        # dedupe while preserving order
        seen = set()
        dedup = []
        for r in required_fields:
            if r not in seen:
                dedup.append(r)
                seen.add(r)
        schema["required"] = dedup
    return schema

# ----------------------------
# Translate top-level Ansible constraints into JSON Schema constructs
# ----------------------------
def translate_constraints_to_schema(base_schema: Dict[str, Any], constraints: Dict[str, Any]) -> Dict[str, Any]:
    """
    Given a base object schema with 'properties' and optional 'required',
    translate AnsibleModule constraints into JSON Schema constructs in-place,
    and also put remaining raw constraints into base_schema['x-ansible'].
    """
    x_ansible = {}

    # helper
    def add_allof_clause(clause):
        base_schema.setdefault("allOf", []).append(clause)

    # required_one_of (or required_any_of): at least one of fields in each group must be present
    # constraints format: list OR list-of-lists; accept both shapes.
    ro = constraints.get("required_one_of") or constraints.get("required_any_of")
    if ro:
        # normalize to list-of-groups where each group is a list of names
        groups = []
        if isinstance(ro, (list, tuple)) and all(isinstance(x, str) for x in ro):
            groups = [list(ro)]
        elif isinstance(ro, (list, tuple)):
            # list of lists
            for g in ro:
                if isinstance(g, (list, tuple)):
                    groups.append(list(g))
                elif isinstance(g, str):
                    groups.append([g])
        # For each group, require at least one -> anyOf with required singletons
        if groups:
            any_of_groups = []
            for group in groups:
                group_any = []
                for fld in group:
                    group_any.append({"required": [fld]})
                any_of_groups.append({"anyOf": group_any})
            # Join groups with allOf (each group must have at least one)
            if len(any_of_groups) == 1:
                add_allof_clause(any_of_groups[0])
            else:
                # every group constraint must hold
                add_allof_clause({"allOf": any_of_groups})
        x_ansible["required_one_of"] = ro

    # required_together: fields in a group must be present together.
    # Use JSON Schema draft-07 dependentRequired: for each field, list other fields in group.
    rt = constraints.get("required_together")
    if rt:
        if isinstance(rt, (list, tuple)) and all(isinstance(x, str) for x in rt):
            groups = [list(rt)]
        elif isinstance(rt, (list, tuple)):
            groups = []
            for g in rt:
                if isinstance(g, (list, tuple)):
                    groups.append(list(g))
                elif isinstance(g, str):
                    groups.append([g])
        else:
            groups = []
        dependent_required = {}
        for group in groups:
            # for each member map to others
            for member in group:
                others = [x for x in group if x != member]
                if others:
                    dependent_required.setdefault(member, set()).update(others)
        # convert sets to lists
        if dependent_required:
            base_schema.setdefault("dependentRequired", {})
            for k, v in dependent_required.items():
                base_schema["dependentRequired"][k] = sorted(list(v))
        x_ansible["required_together"] = rt

    # mutually_exclusive: ensure not both (or not more than one) from groups present.
    # For a group, easiest pure-schema approach: for each pair (a,b) add {"not":{"required":[a,b]}}
    me = constraints.get("mutually_exclusive")
    if me:
        groups = []
        if isinstance(me, (list, tuple)) and all(isinstance(x, str) for x in me):
            groups = [list(me)]
        elif isinstance(me, (list, tuple)):
            for g in me:
                if isinstance(g, (list, tuple)):
                    groups.append(list(g))
                elif isinstance(g, str):
                    groups.append([g])
        for group in groups:
            # if group has "max 1 allowed" semantics, pairwise not-required enforces no pair simultaneously
            for a, b in itertools.combinations(group, 2):
                add_allof_clause({"not": {"required": [a, b]}})
        x_ansible["mutually_exclusive"] = me

    # aliases: JSON Schema can't express alternate property names directly well while keeping 'properties' shape.
    # We'll leave aliases in x-ansible and not mutate the properties, because allowing both names requires schema rewriting.
    if constraints.get("aliases"):
        x_ansible["aliases"] = constraints["aliases"]

    # include any constraints that the AST extraction returned raw
    for k in ("_raw",):
        if constraints.get(k):
            x_ansible[k] = constraints[k]

    if x_ansible:
        base_schema["x-ansible"] = x_ansible

    return base_schema

# ----------------------------
# Top-level builder that orchestrates extraction + conversion
# ----------------------------
def build_schema_for_module(path: str, trust_import: bool = False) -> Dict[str, Any]:
    """
    Build and return the JSON Schema for the module at path.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(path)

    with open(path, "r", encoding="utf-8") as f:
        source = f.read()

    arg_spec_raw, constraints = extract_argument_spec_from_ast(source)
    normalized = normalize_arg_spec(arg_spec_raw)

    unresolved_detected = (not normalized) or any(
        isinstance(v, dict) and ("__UNRESOLVED__" in v or "__UNRESOLVED_VALUE__" in v or "__UNRESOLVED_ARGUMENT_SPEC__" in v)
        for v in normalized.values()
    )

    # If unresolved and trust_import, import module to try to get runtime-built spec
    if unresolved_detected and trust_import:
        module_vars = import_module_dict(path)
        runtime_spec = None
        # common variable names
        if "argument_spec" in module_vars and isinstance(module_vars["argument_spec"], dict):
            runtime_spec = module_vars["argument_spec"]
        else:
            # search for likely candidate dicts
            candidates = []
            for name, val in module_vars.items():
                if isinstance(val, dict):
                    # heuristics: values are dicts and inner values are dicts with 'type' or 'choices' keys
                    inner_vals = list(val.values())
                    if inner_vals and all(isinstance(x, dict) for x in inner_vals):
                        # check if any inner dict has keys like 'type' or 'choices'
                        if any(('type' in inner.keys() or 'choices' in inner.keys() or 'options' in inner.keys()) for inner in inner_vals):
                            candidates.append(val)
            if candidates:
                runtime_spec = max(candidates, key=lambda d: len(d))
        if runtime_spec:
            normalized = normalize_arg_spec(runtime_spec)
            # try to merge runtime constraints found at module level
            for name in ("mutually_exclusive", "required_one_of", "required_together", "aliases"):
                if name in module_vars:
                    constraints[name] = module_vars[name]

    # convert normalized arg spec section to schema
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {},
    }

    # convert fields
    for arg_name, opts in normalized.items():
        prop_schema, req = convert_field_to_schema(arg_name, opts)
        schema["properties"][arg_name] = prop_schema
        if req:
            schema.setdefault("required", []).extend(req)

    # dedupe required
    if "required" in schema:
        seen = set()
        dedup = []
        for r in schema["required"]:
            if r not in seen:
                dedup.append(r)
                seen.add(r)
        schema["required"] = dedup

    # translate constraints into schema-level constructs where feasible
    schema = translate_constraints_to_schema(schema, constraints or {})

    # top-level x-ansible metadata: include any fields that cannot be converted, like alias mappings per-field
    # collect per-field aliases still present in normalized opts
    per_field_aliases = {}
    for arg_name, opts in normalized.items():
        if isinstance(opts, dict):
            if "aliases" in opts:
                per_field_aliases[arg_name] = opts["aliases"]
    if per_field_aliases:
        schema.setdefault("x-ansible", {}).setdefault("field_aliases", per_field_aliases)
    # If unresolved markers exist, put them into x-ansible.__unresolved for user debugging
    unresolved_map = {}
    for k, v in normalized.items():
        if isinstance(v, dict) and ("__UNRESOLVED__" in v or "__UNRESOLVED_VALUE__" in v or "__UNRESOLVED_ARGUMENT_SPEC__" in v):
            unresolved_map[k] = v
    if unresolved_map:
        schema.setdefault("x-ansible", {}).setdefault("__unresolved", unresolved_map)

    return schema

# ----------------------------
# CLI and batch helpers
# ----------------------------
def write_output(schema: Dict[str, Any], out_path: Optional[str]) -> None:
    if out_path:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=2, sort_keys=False, default=str)
        print("Wrote schema to:", out_path)
    else:
        print(json.dumps(schema, indent=2, sort_keys=False, default=str))


def process_single(args) -> None:
    schema = build_schema_for_module(args.module_path, trust_import=args.trust_import)
    write_output(schema, args.out)


def process_dir(args) -> None:
    dirpath = args.dir
    if not os.path.isdir(dirpath):
        raise FileNotFoundError(dirpath)
    outdir = args.out or os.path.join(".", "schemas")
    os.makedirs(outdir, exist_ok=True)
    count = 0
    for fname in os.listdir(dirpath):
        if not fname.endswith(".py"):
            continue
        path = os.path.join(dirpath, fname)
        try:
            schema = build_schema_for_module(path, trust_import=args.trust_import)
            outpath = os.path.join(outdir, fname.replace(".py", ".schema.json"))
            with open(outpath, "w", encoding="utf-8") as f:
                json.dump(schema, f, indent=2, sort_keys=False, default=str)
            count += 1
        except Exception as e:
            print(f"ERROR processing {path}: {e}", file=sys.stderr)
    print(f"Wrote {count} schemas to {outdir}")


def parse_cli():
    p = argparse.ArgumentParser(description="Convert Ansible module argument_spec to JSON Schema (full converter)")
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--module", dest="module_path", help="Path to a module .py file")
    grp.add_argument("--dir", dest="dir", help="Directory of modules to process (batch).")
    p.add_argument("--trust-import", action="store_true", help="If AST extraction fails, import/execute module to resolve runtime-built specs (unsafe).")
    p.add_argument("-o", "--out", help="Output file path (for single module) or output directory (for --dir).")
    return p.parse_args()

def main():
    args = parse_cli()
    if args.module_path:
        class Args: pass
        a = Args()
        a.module_path = args.module_path
        a.trust_import = args.trust_import
        a.out = args.out
        process_single(a)
    else:
        # batch
        class Args: pass
        a = Args()
        a.dir = args.dir
        a.trust_import = args.trust_import
        a.out = args.out
        process_dir(a)

if __name__ == "__main__":
    main()
