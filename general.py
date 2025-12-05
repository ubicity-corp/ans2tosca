#!/usr/bin/env python3
"""
ansible_argument_spec_exporter_robust.py

Universal extractor of argument_spec from any Ansible module.
Handles:
- Modules inheriting from AnsibleModule
- Modules using module_class = AnsibleModule (composition)
- Modules that read stdin at import or in main()
Outputs JSON Schema (Draft-07) or TOSCA YAML.
"""

import sys
import os
import argparse
import importlib.util
import inspect
import json
import yaml
import io

# ----------------------------
# Mock class to capture argument_spec
# ----------------------------

class CaptureArgumentSpec:
    captured_spec = None

    def __init__(self, argument_spec=None, supports_check_mode=False, *args, **kwargs):
        self.argument_spec = argument_spec or {}
        self.supports_check_mode = supports_check_mode
        CaptureArgumentSpec.captured_spec = self.argument_spec

    def exit_json(self, **kwargs):
        pass

    def fail_json(self, **kwargs):
        pass

# ----------------------------
# Helpers
# ----------------------------

def safe_import_module(path: str):
    """Safely import a Python module from file path."""
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location("__ansible_module__", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def is_ansible_module_subclass(cls):
    """Check if cls inherits from AnsibleModule."""
    if not inspect.isclass(cls):
        return False
    for base in inspect.getmro(cls):
        if base.__name__ == "AnsibleModule":
            return True
    return False

def patch_module_classes(module):
    """
    Patch:
    - Classes that inherit from AnsibleModule
    - Classes that define module_class = AnsibleModule
    """
    for name, cls in inspect.getmembers(module, inspect.isclass):
        # inheritance
        if is_ansible_module_subclass(cls):
            setattr(module, name, CaptureArgumentSpec)
        # module_class composition
        elif hasattr(cls, "module_class") and getattr(cls, "module_class", None).__name__ == "AnsibleModule":
            cls.module_class = CaptureArgumentSpec
    # patch top-level AnsibleModule reference if present
    if hasattr(module, "AnsibleModule"):
        module.AnsibleModule = CaptureArgumentSpec

def extract_argument_spec(module):
    """Patch classes and call main() to capture argument_spec."""
    patch_module_classes(module)
    if hasattr(module, "main"):
        try:
            module.main()
        except Exception:
            pass
    return getattr(CaptureArgumentSpec, "captured_spec", {}) or getattr(module, "argument_spec", {})

# ----------------------------
# Conversion to JSON Schema
# ----------------------------

JSON_TYPE_MAP = {
    "str": "string", "string": "string",
    "bool": "boolean", "boolean": "boolean",
    "int": "integer", "integer": "integer",
    "float": "number",
    "dict": "object", "mapping": "object",
    "list": "array", "sequence": "array",
    "path": "string",
    "raw": None,
    "jsonarg": None,
    "bytes": "string",
}

def convert_field_to_json_schema(name, opts):
    prop = {}
    if not isinstance(opts, dict):
        return {"description": "UNRESOLVED"}, None
    ans_type = opts.get("type")
    json_type = JSON_TYPE_MAP.get(ans_type) if ans_type else "string"
    if json_type:
        prop["type"] = json_type
    if "choices" in opts:
        prop["enum"] = list(opts["choices"])
    if "default" in opts:
        prop["default"] = opts["default"]
    if ans_type in ("raw", "jsonarg"):
        prop.pop("type", None)
    if "options" in opts and isinstance(opts["options"], dict):
        prop["type"] = "object"
        nested = convert_arg_spec_to_json_schema(opts["options"])
        prop["properties"] = nested.get("properties", {})
        if "required" in nested:
            prop["required"] = nested["required"]
    if ans_type == "list" and "elements" in opts:
        elem_type = JSON_TYPE_MAP.get(opts["elements"]) if isinstance(opts["elements"], str) else None
        prop["items"] = {"type": elem_type} if elem_type else {}
    required_here = [name] if opts.get("required") else None
    return prop, required_here

def convert_arg_spec_to_json_schema(arg_spec):
    schema = {"type": "object", "properties": {}}
    required_fields = []
    for k, v in arg_spec.items():
        prop, req = convert_field_to_json_schema(k, v)
        schema["properties"][k] = prop
        if req:
            required_fields.extend(req)
    if required_fields:
        schema["required"] = list(dict.fromkeys(required_fields))
    return schema

# ----------------------------
# Conversion to TOSCA
# ----------------------------

TOSCA_TYPE_MAP = {
    "str": "string", "string": "string",
    "bool": "boolean", "boolean": "boolean",
    "int": "integer", "integer": "integer",
    "float": "float",
    "dict": "map", "mapping": "map",
    "list": "list", "sequence": "list",
    "path": "string",
    "raw": "any",
    "jsonarg": "any",
    "bytes": "string",
}

def convert_field_to_tosca(field):
    if not isinstance(field, dict):
        return {"type": "any"}
    prop_type = TOSCA_TYPE_MAP.get(field.get("type"), "any")
    prop = {"type": prop_type}
    if field.get("required"):
        prop["required"] = True
    if "default" in field:
        prop["default"] = field["default"]
    if "choices" in field:
        prop["constraints"] = [{"valid_values": list(field["choices"])}]
    if "options" in field and isinstance(field["options"], dict):
        prop["type"] = "map"
        prop["properties"] = convert_arg_spec_to_tosca(field["options"])
    if prop_type == "list" and "elements" in field:
        prop["entry_schema"] = {"type": TOSCA_TYPE_MAP.get(field["elements"], "any")}
    return prop

def convert_arg_spec_to_tosca(arg_spec):
    tosca_props = {}
    for k, v in arg_spec.items():
        tosca_props[k] = convert_field_to_tosca(v)
    return tosca_props

# ----------------------------
# CLI
# ----------------------------

def main():
    parser = argparse.ArgumentParser(description="Universal Ansible module argument_spec extractor")
    parser.add_argument("module_path", help="Path to the module .py file")
    parser.add_argument("-o", "--out", help="Output file (default: stdout)")
    parser.add_argument("--format", choices=["jsonschema", "tosca"], default="jsonschema",
                        help="Output format: jsonschema (default) or tosca")
    args = parser.parse_args()

    # Patch stdin BEFORE importing module
    _orig_stdin = sys.stdin
    sys.stdin = io.StringIO('{}')  # empty JSON
    try:
        module = safe_import_module(args.module_path)
        arg_spec = extract_argument_spec(module)
    finally:
        sys.stdin = _orig_stdin

    if not arg_spec:
        print("WARNING: argument_spec could not be found", file=sys.stderr)

    if args.format == "jsonschema":
        schema = convert_arg_spec_to_json_schema(arg_spec)
        schema["$schema"] = "http://json-schema.org/draft-07/schema#"
        output = json.dumps(schema, indent=2)
    else:
        tosca_yaml = {"properties": convert_arg_spec_to_tosca(arg_spec)}
        output = yaml.dump(tosca_yaml, sort_keys=False)

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Wrote {args.format.upper()} to {args.out}")
    else:
        print(output)

if __name__ == "__main__":
    main()
