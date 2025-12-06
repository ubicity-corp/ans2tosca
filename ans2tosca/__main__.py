#!/usr/bin/env python3
"""
Extract fully merged argument_spec from any Ansible module safely and
convert it to either JSON Schema (Draft-07) or TOSCA YAML.

Supports core modules, custom modules, and AWS modules.
"""

# Version string
from . import __version__

# Command line parsing
import argparse

# Output
import json
import yaml

# Core functionality
import ans2tosca.arg_spec
import ans2tosca.json_schema
import ans2tosca.tosca

# Main module
def main():
    parser = argparse.ArgumentParser(description="Convert Ansible module argument_spec to TOSCA or JSON Schema")
    parser.add_argument('-v', '--version', action='version', version='%(prog)s ' + str(__version__))
    parser.add_argument("module_path", help="Path to the module .py file")
    parser.add_argument("-o", "--out", help="Output file (default: stdout)")
    parser.add_argument("--format", choices=["jsonschema", "tosca"], default="tosca",
                        help="Output format: tosca (default) or jsonschema")
    args = parser.parse_args()

    module = ans2tosca.arg_spec.safe_import_module(args.module_path)
    arg_spec = ans2tosca.arg_spec.extract_argument_spec(module)

    if not arg_spec:
        print("WARNING: argument_spec could not be found", file=sys.stderr)

    if args.format == "jsonschema":
        schema = ans2tosca.json_schema.convert_arg_spec_to_json_schema(arg_spec)
        schema["$schema"] = "http://json-schema.org/draft-07/schema#"
        output = json.dumps(schema, indent=2)
    else:
        tosca_yaml = {"properties": ans2tosca.tosca.convert_arg_spec_to_tosca(arg_spec)}
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
