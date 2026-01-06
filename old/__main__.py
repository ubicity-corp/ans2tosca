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
import ans2tosca.json_schema
import ans2tosca.tosca

# Main module
def main():
    parser = argparse.ArgumentParser(description="Convert Ansible playbook to TOSCA")
    parser.add_argument("playbook", help="Path to the Ansible playbook")
    parser.add_argument('-v', '--version', action='version', version='%(prog)s ' + str(__version__))
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    args = parser.parse_args()

    # Parse playbook
    results = ans2tosca.playbook.parse_playbook(args.playbook)
    if not results:
        print("No tasks found in playbook")
        return

    # Convert to tosca
    tosca_yaml = ans2tosca.tosca.convert_playbook_to_tosca(args.playbook, results)
    
    # Write output
    output = yaml.dump(tosca_yaml, sort_keys=False)

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
    else:
        print(output)

if __name__ == "__main__":
    main()
