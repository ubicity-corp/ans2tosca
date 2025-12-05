#!/usr/bin/env python3
"""
ansible_argument_spec_extractor.py

General-purpose tool to extract argument_spec from any Ansible module,
including those inheriting from AnsibleModule subclasses, safely.

Outputs JSON Schema (Draft-07) for the module arguments.
"""

import os
import sys
import json
import importlib.util
import argparse
import inspect
from types import ModuleType
from typing import Dict, Any

# ----------------------------
# Helpers
# ----------------------------

def safe_import_module(path: str) -> ModuleType:
    """Import a Python module from path safely."""
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location("__ansible_module__", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def find_ansible_module_class(module: ModuleType):
    """
    Find class that inherits from AnsibleModule (or subclass).
    Returns the class object or None.
    """
    for name, obj in inspect.getmembers(module, inspect.isclass):
        try:
            for base in inspect.getmro(obj):
                if base.__name__ == "AnsibleModule":
                    return obj
        except Exception:
            continue
    return None

def instantiate_module_class(cls, extra_spec=None):
    """
    Instantiate the module safely, overriding exit_json/fail_json.
    """
    class DummyModule(cls):
        def __init__(self, *args, **kwargs):
            # Inject argument_spec if provided
            if extra_spec:
                kwargs["argument_spec"] = extra_spec
            super().__init__(*args, **kwargs)

        def exit_json(self, **kwargs): 
            # prevent real exit
            pass
        def fail_json(self, **kwargs): 
            # prevent real exit
            pass

    # create instance with empty args, supports_check_mode=False
    instance = DummyModule(argument_spec=extra_spec or {}, supports_check_mode=False)
    return instance

def merge_argument_spec(module):
    """
    Extract the full argument_spec for any Ansible module.
    """
    # 1. Look for top-level variable
    arg_spec = getattr(module, "argument_spec", None)
    if arg_spec and isinstance(arg_spec, dict):
        return arg_spec

    # 2. Look for a class inheriting from AnsibleModule
    cls = find_ansible_module_class(module)
    if cls:
        instance = instantiate_module_class(cls)
        return getattr(instance, "argument_spec", {})

    return {}

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

def convert_field_to_schema(name: str, opts: Dict[str, Any]):
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

def convert_arg_spec_to_schema(arg_spec: Dict[str, Any]):
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
    arg_spec = merge_argument_spec(module)
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
