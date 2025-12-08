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
import os
import json
import yaml

# Core functionality
import ans2tosca.playbook
import ans2tosca.arg_spec
import ans2tosca.json_schema
import ans2tosca.tosca

def format_module_info(loaded):
    """
    Format information about a loaded module for display.
    """
    if isinstance(loaded, str):
        # Error message
        return [f"   Status: {loaded}"]
    
    info = []
    info.append(f"   Type: Loaded Python Module")
    info.append(f"   Loaded Module: {loaded}")
    
    if hasattr(loaded, '__file__'):
        info.append(f"   Module File: {loaded.__file__}")
        
        # Try to determine if it's from a collection based on path
        if 'ansible_collections' in loaded.__file__:
            parts = loaded.__file__.split('ansible_collections')[1].split('/')
            if len(parts) >= 3:
                info.append(f"   Collection: {parts[1]}.{parts[2]}")
    
    if hasattr(loaded, 'DOCUMENTATION'):
        info.append(f"   Has Documentation: Yes")
    
    return info


# Main module
def main():
    parser = argparse.ArgumentParser(description="Convert Ansible playbook to TOSCA")
    parser.add_argument("playbook", help="Path to the Ansible playbook")
    parser.add_argument('-v', '--version', action='version', version='%(prog)s ' + str(__version__))
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    parser.add_argument("--format", choices=["jsonschema", "tosca"], default="tosca",
                        help="Output format: tosca (default) or jsonschema")
    args = parser.parse_args()

    # Parse playbook
    results = ans2tosca.playbook.parse_playbook(args.playbook)
    if not results:
        print("No tasks found in playbook")
        return
    
    print(f"\n{'='*80}")
    print(f"Ansible Playbook Analysis: {args.playbook}")
    print(f"{'='*80}\n")
    
    for idx, result in enumerate(results, 1):
        print(f"{idx}. Task: {result['task']}")
        print(f"   Play: {result['play']}")
        print(f"   Module Name: {result['module_name']}")
        
        for line in format_module_info(result['loaded_module']):
            print(line)
        print()

        module = result['loaded_module']
        arg_spec = ans2tosca.arg_spec.extract_argument_spec(module)

        if args.format == "jsonschema":
            schema = ans2tosca.json_schema.convert_arg_spec_to_json_schema(arg_spec)
            schema["$schema"] = "http://json-schema.org/draft-07/schema#"
            output = json.dumps(schema, indent=2)
        else:
            tosca_yaml = {"properties": ans2tosca.tosca.convert_arg_spec_to_tosca(arg_spec)}
            output = yaml.dump(tosca_yaml, sort_keys=False)

        if args.output:
            os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"Wrote {args.format.upper()} to {args.output}")
        else:
            print(output)

if __name__ == "__main__":
    main()
