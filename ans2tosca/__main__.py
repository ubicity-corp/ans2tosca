"""
Ansible Playbook Variable Type Analyzer
Analyzes an Ansible playbook and reports the types of all variables found.
Can also generate TOSCA data type definitions.
"""

import sys
import argparse
from pathlib import Path

import ans2tosca.playbook as playbook
import ans2tosca.tosca as tosca


def playbook_name_to_camel_case(playbook_path):
    """
    Convert a playbook filename to CamelCase.
    
    Examples:
    - "deploy_web_server.yml" -> "DeployWebServer"
    - "install-nginx.yaml" -> "InstallNginx"
    - "setup_database.yml" -> "SetupDatabase"
    - "my_playbook" -> "MyPlaybook"
    
    Args:
        playbook_path: Path to the playbook file (can include directory)
    
    Returns:
        CamelCase string suitable for a node type name
    """
    # Extract just the filename without path
    filename = Path(playbook_path).name
    
    # Remove file extension (.yml, .yaml, etc.)
    name_without_ext = Path(filename).stem
    
    # Replace common separators with spaces
    # Handle: underscores, hyphens, dots
    normalized = name_without_ext.replace('_', ' ').replace('-', ' ').replace('.', ' ')
    
    # Split into words and capitalize each
    words = normalized.split()
    
    # Convert to CamelCase
    camel_case = ''.join(word.capitalize() for word in words)
    
    return camel_case

        
def main():
    parser = argparse.ArgumentParser(
        description="Convert Ansible playbook to TOSCA file"
    )
    parser.add_argument(
        "playbook",
        help="Path to the Ansible playbook file"
    )
    parser.add_argument(
        "-n", "--node-name",
        help="Optional name for the generated node type"
    )
    parser.add_argument(
        "-o", "--output",
        help="Optional output file path. Defaults to <stderr>"
    )

    # Parse command line arguments
    args = parser.parse_args()
    if args.node_name:
        node_type_name = args.node_name
    else:
        # Auto-generate from playbook filename
        node_type_name = playbook_name_to_camel_case(args.playbook)    

    # Extract variables defined in the playbook
    variables = playbook.process_playbook(args.playbook)

    # Create TOSCA
    tosca_output = tosca.create_tosca_file(variables, args.playbook, node_type_name)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(tosca_output)
    else:
        print(tosca_output)

if __name__ == "__main__":
    main()
