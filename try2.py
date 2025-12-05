#!/usr/bin/env python3
import importlib.util
import inspect
import json
import sys
from types import ModuleType

# -------------------------------------------
# Mapping Ansible types → JSON Schema types
# -------------------------------------------
TYPE_MAP = {
    "str": "string",
    "bool": "boolean",
    "int": "integer",
    "float": "number",
    "dict": "object",
    "list": "array",
    "path": "string",
    "raw": None,   # "any"
    "jsonarg": None,
    "bytes": "string",
}


def load_module_from_path(path: str) -> ModuleType:
    """Dynamically load a Python module from a file."""
    spec = importlib.util.spec_from_file_location("ansible_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def find_argument_spec(mod: ModuleType) -> dict:
    """
    Locate the argument_spec dict inside the module.
    Usually defined as a variable or inside AnsibleModule() instantiation.
    """
    # Look for a top-level variable called argument_spec
    if hasattr(mod, "argument_spec"):
        return mod.argument_spec

    # Look inside the module for any dict named argument_spec
    for name, value in vars(mod).items():
        if name == "argument_spec" and isinstance(value, dict):
            return value

    # Try to inspect code for AnsibleModule(argument_spec=...)
    for name, obj in inspect.getmembers(mod):
        if inspect.isfunction(obj) or inspect.isclass(obj):
            try:
                source = inspect.getsource(obj)
                if "argument_spec" in source:
                    # not reliable, but best-effort
                    pass
            except OSError:
                pass

    raise ValueError("Could not find argument_spec in module.")


# ---------------------------------------------------
# Convert argument_spec dict → JSON Schema recursion
# ---------------------------------------------------
def convert_arg_spec_to_schema(arg_spec: dict) -> dict:
    schema = {"type": "object", "properties": {}, "required": []}

    for arg, opts in arg_spec.items():
        if not isinstance(opts, dict):
            continue

        json_type = TYPE_MAP.get(opts.get("type"), "string")

        prop = {}
        if json_type:
            prop["type"] = json_type

        # choices → enum
        if "choices" in opts:
            prop["enum"] = opts["choices"]

        # default
        if "default" in opts:
            prop["default"] = opts["default"]

        # elements= (list element type)
        if opts.get("type") == "list" and "elements" in opts:
            elem_type = TYPE_MAP.get(opts["elements"], "string")
            prop["items"] = {"type": elem_type}

        # nested dict (suboptions)
        if "options" in opts:
            prop.update(convert_arg_spec_to_schema(opts["options"]))

        # required
        if opts.get("required") is True:
            schema["required"].append(arg)

        schema["properties"][arg] = prop

    return schema


# ---------------------------------------------------
# Main
# ---------------------------------------------------
def main():
    if len(sys.argv) != 2:
        print("Usage: python ansible_arg_spec_to_jsonschema.py <module_path>")
        sys.exit(1)

    module_path = sys.argv[1]
    mod = load_module_from_path(module_path)
    arg_spec = find_argument_spec(mod)
    schema = convert_arg_spec_to_schema(arg_spec)

    print(json.dumps(schema, indent=2))


if __name__ == "__main__":
    main()
