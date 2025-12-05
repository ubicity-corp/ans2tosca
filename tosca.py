#!/usr/bin/env python3
"""
ansible_argument_spec_to_tosca.py

Extract fully merged argument_spec from any Ansible module safely
and convert it to TOSCA YAML.

Supports core modules, custom modules, and AWS modules.
"""

import sys
import os
import argparse
import importlib.util
import types
import yaml

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
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location("__ansible_module__", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def patch_module(module):
    if hasattr(module, "AnsibleModule"):
        module.AnsibleModule = CaptureArgumentSpec
    if hasattr(module, "AnsibleAWSModule"):
        module.AnsibleAWSModule = CaptureArgumentSpec
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, type):
            bases = [b.__name__ for b in getattr(attr, "__mro__", [])]
            if "AnsibleModule" in bases or "AnsibleAWSModule" in bases:
                setattr(module, attr_name, CaptureArgumentSpec)

def extract_argument_spec(module):
    patch_module(module)
    if hasattr(module, "main"):
        try:
            module.main()
        except Exception:
            pass
    return getattr(CaptureArgumentSpec, "captured_spec", {}) or getattr(module, "argument_spec", {})

# ----------------------------
# Convert to TOSCA YAML
# ----------------------------

TYPE_MAP = {
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

    prop_type = TYPE_MAP.get(field.get("type"), "any")
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
        prop["entry_schema"] = {"type": TYPE_MAP.get(field["elements"], "any")}
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
    parser = argparse.ArgumentParser(description="Extract Ansible module argument_spec as TOSCA YAML")
    parser.add_argument("module_path", help="Path to the module .py file")
    parser.add_argument("-o", "--out", help="Output YAML file (default: stdout)")
    args = parser.parse_args()

    module = safe_import_module(args.module_path)
    arg_spec = extract_argument_spec(module)

    if not arg_spec:
        print("WARNING: argument_spec could not be found", file=sys.stderr)

    tosca_yaml = {"properties": convert_arg_spec_to_tosca(arg_spec)}

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            yaml.dump(tosca_yaml, f, sort_keys=False)
        print(f"Wrote TOSCA YAML to {args.out}")
    else:
        print(yaml.dump(tosca_yaml, sort_keys=False))

if __name__ == "__main__":
    main()
