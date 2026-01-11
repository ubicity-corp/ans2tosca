"""
Ansible Playbook Variable Type Analyzer
Analyzes an Ansible playbook and reports the types of all variables found.
Can also generate TOSCA data type definitions.
"""

import sys
import argparse
from pathlib import Path

import re

import ans2tosca.playbook as playbook
import ans2tosca.tosca as tosca


def playbook_name_to_kebab_case(playbook_name: str) -> str:
    """
    Convert an Ansible playbook filename to kebab-case.
    
    Strips directories, file extensions, and converts the remaining name to kebab-case.
    
    Args:
        playbook_name: The playbook filename (e.g., 'deploy_app.yml', 'playbooks/SetupServer.yaml')
    
    Returns:
        Kebab-case version of the name (e.g., 'deploy-app', 'setup-server')
    
    Examples:
        >>> playbook_name_to_kebab_case('deploy_app.yml')
        'deploy-app'
        >>> playbook_name_to_kebab_case('playbooks/SetupServer.yaml')
        'setup-server'
        >>> playbook_name_to_kebab_case('/path/to/configure-database.yml')
        'configure-database'
        >>> playbook_name_to_kebab_case('MyPlayBook.YML')
        'my-play-book'
    """
    # Strip directories and file extension using pathlib
    name_without_ext = Path(playbook_name).stem
    
    # Handle CamelCase by inserting hyphens before uppercase letters
    # that follow lowercase letters or numbers
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1-\2', name_without_ext)
    
    # Handle sequences like "HTTPServer" -> "HTTP-Server"
    s2 = re.sub('([a-z0-9])([A-Z])', r'\1-\2', s1)
    
    # Replace underscores and spaces with hyphens
    s3 = s2.replace('_', '-').replace(' ', '-')
    
    # Convert to lowercase
    kebab = s3.lower()
    
    # Remove any duplicate hyphens
    kebab = re.sub(r'-+', '-', kebab)
    
    # Strip leading/trailing hyphens
    kebab = kebab.strip('-')
    
    return kebab

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

    # Auto-generate from playbook filename
    node_template_name = playbook_name_to_kebab_case(args.playbook)    
        
    # Extract variables defined in the playbook
    variables = playbook.process_playbook(args.playbook)

    # Create TOSCA
    tosca_output = tosca.create_tosca_file(variables, args.playbook, node_type_name, node_template_name)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(tosca_output)
    else:
        print(tosca_output)

if __name__ == "__main__":
    main()
