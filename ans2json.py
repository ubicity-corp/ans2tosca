#!/usr/bin/env python3
"""
ansible_argument_spec_extractor.py

Extract fully merged argument_spec from any Ansible module safely.
Mocks AnsibleModule and AnsibleAWSModule to capture argument_spec during main() execution.
Outputs JSON Schema (Draft-07).
"""

import sys
import os
import json
import argparse
import importlib.util
import types

# ----------------------------
# Mock class
# ----------------------------

class CaptureArgumentSpec:
    """
    Captures argument_spec from module execution.
    """
    captured_spec = None

    def __init__(self, argument_spec=None, supports_check_mode=False, *args, **kwargs):
        self.argument_spec = argument_spec or {}
        self.supports_check_mode = supports_check_mode
        # Capture the merged argument_spec
        CaptureArgumentSpec.captured_spec = self.argument_spec

    def exit_json(self, **kwargs):
        pass  # prevent module from exiting

    def fail_json(self, **kwargs):
        pass  # prevent module from exiting

# ----------------------------
# Helpers
# ----------------------------

def safe_import_module(path: str):
    """Safely import a Python module from a file path."""
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location("__ansible_module__", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def patch_module(module):
    """
    Patch the module to use CaptureArgumentSpec wherever AnsibleModule or AnsibleAWSModule is referenced.
    """
    # Patch top-level references
    if hasattr(module, "AnsibleModule"):
        module.AnsibleModule = CaptureArgumentSpec
    if hasattr(module, "AnsibleAWSModule"):
        module.AnsibleAWSModule = CaptureArgumentSpec

    # Patch any classes inheriting from AnsibleModule
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, type):
            bases = [b.__name__ for b in getattr(attr, "__mro__", [])]
            if "AnsibleModule" in bases or "AnsibleAWSModule" in bases:
                setattr(module, attr_name, CaptureArgumentSpec)

def extract_argument_spec(module):
    """
    Safely execute module.main() to capture argument_spec.
    Fallback to class attribute if main() fails.
    """
    patch_module(module)
    
    # Run main safely
    if hasattr(module, "main"):
        try:
            module.main()
        except Exception:
            pass  # ignore errors

    # Return captured argument_spec
    if getattr(CaptureArgumentSpec, "captured_spec", None):
        return CaptureArgumentSpec.captured_spec

    # Fallback: look for module-level argument_spec
    return getattr(module, "argument_spec", {})

# ----------------------------
# JSON Schema conversion
# ----------------------------
TYPE_MAP = {
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

def convert_field_to_schema(name, opts):
    prop = {}
    if not isinstance(opts, dict):
        return {"description": "UNRESOLVED"}, None
    ans_type = opts.get("type")
    json_type = TYPE_MAP.get(ans_type) if ans_type else "string"
    if json_type:
        prop["type"] = json_type
    if "choices" in opts:
        prop["enum"] = list(opts["choices"])
    if "default" in opts:
        prop["default"] = opts["default"]
    if ans_type in ("raw", "jsonarg"):
        prop.pop("type", None)
    # nested options
    if "options" in opts and isinstance(opts["options"], dict):
        prop["type"] = "object"
        nested = convert_arg_spec_to_schema(opts["options"])
        prop["properties"] = nested.get("properties", {})
        if "required" in nested:
            prop["required"] = nested["required"]
    if ans_type == "list" and "elements" in opts:
        elem_type = TYPE_MAP.get(opts["elements"]) if isinstance(opts["elements"], str) else None
        prop["items"] = {"type": elem_type} if elem_type else {}
    required_here = [name] if opts.get("required") else None
    return prop, required_here

def convert_arg_spec_to_schema(arg_spec):
    schema = {"type": "object", "properties": {}}
    required_fields = []
    for k, v in arg_spec.items():
        prop, req = convert_field_to_schema(k, v)
        schema["properties"][k] = prop
        if req:
            required_fields.extend(req)
    if required_fields:
        schema["required"] = list(dict.fromkeys(required_fields))  # dedupe
    return schema

# ----------------------------
# CLI
# ----------------------------
def main():
    parser = argparse.ArgumentParser(description="Extract Ansible module argument_spec as JSON Schema")
    parser.add_argument("module_path", help="Path to the module .py file")
    parser.add_argument("-o", "--out", help="Output JSON file (default: stdout)")
    args = parser.parse_args()

    module = safe_import_module(args.module_path)
    arg_spec = extract_argument_spec(module)

    if not arg_spec:
        print("WARNING: argument_spec could not be found", file=sys.stderr)

    schema = convert_arg_spec_to_schema(arg_spec)
    schema["$schema"] = "http://json-schema.org/draft-07/schema#"

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=2)
        print(f"Wrote JSON Schema to {args.out}")
    else:
        print(json.dumps(schema, indent=2))

if __name__ == "__main__":
    main()
