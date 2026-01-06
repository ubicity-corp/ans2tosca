"""
Ansible Playbook Variable Type Analyzer
Analyzes an Ansible playbook and reports the types of all variables found.
Can also generate TOSCA data type definitions.
"""

import yaml
import sys
import argparse
import re
from pathlib import Path
from collections import defaultdict


def get_var_type(value):
    """Return a human-readable type name for a variable."""
    if isinstance(value, bool):
        return "boolean"
    elif isinstance(value, int):
        return "integer"
    elif isinstance(value, float):
        return "float"
    elif isinstance(value, str):
        return "string"
    elif isinstance(value, list):
        return f"list (length: {len(value)})"
    elif isinstance(value, dict):
        return f"dictionary (keys: {len(value)})"
    elif value is None:
        return "null/None"
    else:
        return type(value).__name__


def get_tosca_type(value):
    """Convert Python type to TOSCA type."""
    if isinstance(value, bool):
        return "boolean"
    elif isinstance(value, int):
        return "integer"
    elif isinstance(value, float):
        return "float"
    elif isinstance(value, str):
        return "string"
    elif isinstance(value, list):
        return "list"
    elif isinstance(value, dict):
        return "map"
    else:
        return "string"  # default fallback


def extract_jinja2_default(value):
    """
    Extract default value from Jinja2 expressions like:
    {{ var_name | default('value') }}
    {{ var_name | default("value") }}
    {{ var_name | default(123) }}
    {{ var_name | default(true) }}
    {{ var_name | default(false) }}
    
    Returns tuple: (has_default, default_value, inferred_type)
    """
    if not isinstance(value, str):
        return False, value, None
    
    # Pattern to match {{ ... | default(...) }}
    pattern = r'\{\{\s*[^|]+\|\s*default\s*\(\s*([\'"]?)(.+?)\1\s*\)\s*\}\}'
    match = re.search(pattern, value)
    
    if match:
        quote = match.group(1)
        default_val = match.group(2)
        
        # If quoted, it's a string
        if quote:
            return True, default_val, 'string'
        
        # Try to infer type from unquoted value
        default_val_stripped = default_val.strip()
        
        # Boolean
        if default_val_stripped.lower() == 'true':
            return True, True, 'boolean'
        elif default_val_stripped.lower() == 'false':
            return True, False, 'boolean'
        
        # Integer
        try:
            int_val = int(default_val_stripped)
            return True, int_val, 'integer'
        except ValueError:
            pass
        
        # Float
        try:
            float_val = float(default_val_stripped)
            return True, float_val, 'float'
        except ValueError:
            pass
        
        # List (basic detection)
        if default_val_stripped.startswith('[') and default_val_stripped.endswith(']'):
            return True, default_val_stripped, 'list'
        
        # Dict (basic detection)
        if default_val_stripped.startswith('{') and default_val_stripped.endswith('}'):
            return True, default_val_stripped, 'map'
        
        # Default to string
        return True, default_val_stripped, 'string'
    
    return False, value, None


def convert_jinja2_to_tosca(value, use_get_property=False):
    """
    Convert Jinja2 expressions to TOSCA function calls.
    Handles variable references like {{ username }} and constructs TOSCA concat/get_input or get_property.
    
    Examples:
    - "/home/{{ username }}" -> { concat: ['/home/', { get_input: username }] }
    - "{{ username }}_backup" -> { concat: [{ get_input: username }, '_backup'] }
    - "prefix_{{ var1 }}_{{ var2 }}_suffix" -> { concat: ['prefix_', { get_input: var1 }, '_', { get_input: var2 }, '_suffix'] }
    
    Args:
        value: The string value to convert
        use_get_property: If True, use get_property instead of get_input
    
    Returns: (converted, tosca_value) where converted is True if conversion happened
    """
    if not isinstance(value, str):
        return False, value
    
    # Check if string contains Jinja2 variable references (but not default filters)
    jinja_pattern = r'\{\{\s*(\w+)\s*\}\}'
    matches = list(re.finditer(jinja_pattern, value))
    
    if not matches:
        return False, value
    
    # If the entire string is just a single variable reference, use get_input/get_property directly
    if len(matches) == 1 and matches[0].group(0) == value.strip():
        var_name = matches[0].group(1)
        if use_get_property:
            return True, {'get_property': ['SELF', var_name]}
        else:
            return True, {'get_input': var_name}
    
    # Build concat parts
    concat_parts = []
    last_end = 0
    
    for match in matches:
        start = match.start()
        end = match.end()
        var_name = match.group(1)
        
        # Add literal string before this variable
        if start > last_end:
            literal = value[last_end:start]
            if literal:
                concat_parts.append(literal)
        
        # Add get_input or get_property for the variable
        if use_get_property:
            concat_parts.append({'get_property': ['SELF', var_name]})
        else:
            concat_parts.append({'get_input': var_name})
        
        last_end = end
    
    # Add any remaining literal string
    if last_end < len(value):
        literal = value[last_end:]
        if literal:
            concat_parts.append(literal)
    
    # Return concat function
    if len(concat_parts) == 1:
        return True, concat_parts[0]
    else:
        return True, {'concat': concat_parts}


def build_tosca_structure(variables):
    """
    Build a hierarchical structure for TOSCA type definitions.
    Groups variables by their parent paths to identify complex types.
    """
    # Structure to hold type definitions
    type_definitions = {}
    
    # Group variables by their parent path
    path_groups = defaultdict(dict)
    
    for var_path, var_value in variables.items():
        # Skip registered variables and external files
        if var_path.startswith('register.') or var_path.startswith('vars_files.'):
            continue
        
        # Parse the path
        parts = var_path.replace('[', '.').replace(']', '').split('.')
        
        # Build nested structure
        if len(parts) == 1:
            # Top-level variable
            path_groups['__root__'][parts[0]] = var_value
        else:
            # Nested variable - group by parent
            parent_path = '.'.join(parts[:-1])
            field_name = parts[-1]
            path_groups[parent_path][field_name] = var_value
    
    return path_groups


def infer_list_entry_type(lst):
    """Infer the type of list entries."""
    if not lst or len(lst) == 0:
        return "string"  # default
    
    first_item = lst[0]
    if isinstance(first_item, dict):
        return "map"
    elif isinstance(first_item, list):
        return "list"
    else:
        return get_tosca_type(first_item)


def generate_tosca_data_types(variables, base_name="AnsibleData"):
    """
    Generate TOSCA data type definitions from Ansible variables.
    """
    # Build the structure
    path_groups = build_tosca_structure(variables)
    
    # Generate TOSCA types
    tosca_types = {}
    type_counter = {}
    
    def get_type_name(base, suffix=""):
        """Generate unique type names."""
        key = f"{base}{suffix}"
        if key not in type_counter:
            type_counter[key] = 0
            return key
        else:
            type_counter[key] += 1
            return f"{key}_{type_counter[key]}"
    
    def process_dict_to_tosca(fields, type_name_base):
        """Convert a dictionary of fields to a TOSCA type definition."""
        properties = {}
        
        for field_name, field_value in fields.items():
            if isinstance(field_value, dict):
                # Nested dictionary - create a custom type
                nested_type_name = get_type_name(type_name_base, f".{field_name}".replace('.', '_'))
                nested_def = process_dict_to_tosca(field_value, nested_type_name)
                tosca_types[nested_type_name] = nested_def
                
                properties[field_name] = {
                    'type': nested_type_name,
                    'required': False,
                    'default': field_value  # Include default value
                }
            elif isinstance(field_value, list):
                # List type
                if field_value and isinstance(field_value[0], dict):
                    # List of objects - create custom type
                    list_item_type = get_type_name(type_name_base, f".{field_name}_item".replace('.', '_'))
                    item_def = process_dict_to_tosca(field_value[0], list_item_type)
                    tosca_types[list_item_type] = item_def
                    
                    properties[field_name] = {
                        'type': 'list',
                        'entry_schema': {'type': list_item_type},
                        'required': False,
                        'default': field_value  # Include default value
                    }
                else:
                    # List of primitives
                    entry_type = infer_list_entry_type(field_value)
                    properties[field_name] = {
                        'type': 'list',
                        'entry_schema': {'type': entry_type},
                        'required': False,
                        'default': field_value  # Include default value
                    }
            else:
                # Simple type
                properties[field_name] = {
                    'type': get_tosca_type(field_value),
                    'required': False,
                    'default': field_value  # Include default value
                }
        
        return {
            'derived_from': 'tosca.datatypes.Root',
            'properties': properties
        }
    
    # Process top-level variables
    for var_name, var_value in path_groups.get('__root__', {}).items():
        if isinstance(var_value, dict):
            type_name = get_type_name(base_name, f"_{var_name}")
            tosca_types[type_name] = process_dict_to_tosca(var_value, type_name)
        elif isinstance(var_value, list) and var_value and isinstance(var_value[0], dict):
            type_name = get_type_name(base_name, f"_{var_name}_item")
            tosca_types[type_name] = process_dict_to_tosca(var_value[0], type_name)
    
    return tosca_types


def generate_tosca_node_type(variables, playbook_path, node_type_name="AnsibleNode"):
    """
    Generate TOSCA node type definition from Ansible variables.
    Creates properties from vars and an interface with the playbook as implementation.
    """
    properties = {}
    
    for var_name, var_value in variables.items():
        # Skip registered variables and external files
        if var_name.startswith('register.') or var_name.startswith('vars_files.'):
            continue
        
        # Only process top-level vars
        if not var_name.startswith('vars.'):
            continue
        
        # Remove 'vars.' prefix for property name
        prop_name = var_name.replace('vars.', '', 1)
        
        # Skip if it's a nested field (contains dots after vars.)
        if '.' in prop_name or '[' in prop_name:
            continue
        
        # Determine if property is required based on whether it has a default value
        # Properties with defaults are not required, those without are required
        has_default = var_value is not None
        
        prop_def = {
            'type': get_tosca_type(var_value),
            'required': not has_default  # Required if no default value
        }
        
        # Convert any get_input references to get_property for node type context
        converted_value = convert_get_input_to_get_property(var_value)
        
        # Add default value only if it exists (could be a TOSCA function)
        if has_default:
            prop_def['default'] = converted_value
        
        # For complex types, reference the generated data type
        if isinstance(converted_value, dict) and not isinstance(converted_value, dict) or (isinstance(converted_value, dict) and 'get_property' not in converted_value and 'concat' not in converted_value):
            prop_def['type'] = f'AnsibleData_{prop_name}'
        elif isinstance(converted_value, list) and not isinstance(converted_value, dict):
            if converted_value and isinstance(converted_value[0], dict):
                prop_def['type'] = 'list'
                prop_def['entry_schema'] = {'type': f'AnsibleData_{prop_name}_item'}
            else:
                prop_def['type'] = 'list'
                prop_def['entry_schema'] = {'type': infer_list_entry_type(converted_value)}
        
        # Add description based on type
        if isinstance(converted_value, dict) and 'concat' not in converted_value and 'get_property' not in converted_value:
            prop_def['description'] = f'Configuration for {prop_name}'
        elif isinstance(converted_value, list):
            prop_def['description'] = f'List of {prop_name}'
        else:
            prop_def['description'] = f'Value for {prop_name}'
        
        properties[prop_name] = prop_def
    
    # Generate property inputs for the create operation
    # Map each property to get_property function
    operation_inputs = {}
    for prop_name in properties.keys():
        operation_inputs[prop_name] = {'get_property': ['SELF', prop_name]}
    
    # Create the node type definition
    node_type = {
        'derived_from': 'tosca.nodes.Root',
        'description': f'Node type generated from Ansible playbook {playbook_path}',
        'properties': properties,
        'interfaces': {
            'Standard': {
                'type': 'tosca.interfaces.node.lifecycle.Standard',
                'operations': {
                    'create': {
                        'implementation': {
                            'primary': playbook_path,
                            'dependencies': []
                        },
                        'inputs': operation_inputs
                    }
                }
            }
        }
    }
    
    return node_type


def convert_get_input_to_get_property(value):
    """
    Recursively convert get_input references to get_property references.
    This is needed when converting from inputs (topology template) to properties (node type).
    """
    if isinstance(value, dict):
        if 'get_input' in value:
            # Convert get_input to get_property
            return {'get_property': ['SELF', value['get_input']]}
        elif 'concat' in value:
            # Process concat array
            new_concat = []
            for item in value['concat']:
                new_concat.append(convert_get_input_to_get_property(item))
            return {'concat': new_concat}
        else:
            # Recursively process other dicts
            return {k: convert_get_input_to_get_property(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [convert_get_input_to_get_property(item) for item in value]
    else:
        return value


def format_tosca_output(tosca_types, tosca_node_type=None, node_type_name="AnsibleNode"):
    """Format TOSCA types and node type as YAML string."""
    tosca_document = {
        'tosca_definitions_version': 'tosca_simple_yaml_1_3',
        'description': 'TOSCA definitions generated from Ansible playbook variables'
    }
    
    if tosca_types:
        tosca_document['data_types'] = tosca_types
    
    if tosca_node_type:
        tosca_document['node_types'] = {
            node_type_name: tosca_node_type
        }
    
    return yaml.dump(tosca_document, default_flow_style=False, sort_keys=False, width=120)
    """
    Recursively flatten nested dictionaries and list items.
    Returns a flat dictionary with dot-notation keys.
    """
    items = {}
    
    for key, value in variables.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else key
        
        if isinstance(value, dict):
            # Add the dictionary itself
            items[new_key] = value
            # Recursively flatten nested dictionaries
            items.update(flatten_variables(value, new_key, sep=sep))
        elif isinstance(value, list):
            # Add the list itself
            items[new_key] = value
            # Process list items
            for idx, item in enumerate(value):
                list_key = f"{new_key}[{idx}]"
                if isinstance(item, dict):
                    items[list_key] = item
                    items.update(flatten_variables(item, list_key, sep=sep))
                elif isinstance(item, list):
                    items[list_key] = item
                else:
                    items[list_key] = item
        else:
            items[new_key] = value
    
    return items


def extract_vars_from_playbook(playbook_data):
    """Extract variables from playbook structure."""
    variables = {}
    
    if not isinstance(playbook_data, list):
        playbook_data = [playbook_data]
    
    for play in playbook_data:
        if not isinstance(play, dict):
            continue
            
        # Extract vars section
        if 'vars' in play:
            for var_name, var_value in play['vars'].items():
                # First check if it's a Jinja2 default expression
                has_default, extracted_value, inferred_type = extract_jinja2_default(var_value)
                if has_default:
                    variables[f"vars.{var_name}"] = extracted_value
                else:
                    # Check if it contains variable references that need TOSCA conversion
                    converted, tosca_value = convert_jinja2_to_tosca(var_value)
                    variables[f"vars.{var_name}"] = tosca_value
        
        # Extract vars_files references
        if 'vars_files' in play:
            for vars_file in play['vars_files']:
                variables[f"vars_files.{vars_file}"] = f"<external file: {vars_file}>"
        
        # Extract register variables from tasks
        if 'tasks' in play:
            for task in play['tasks']:
                if isinstance(task, dict) and 'register' in task:
                    reg_var = task['register']
                    task_name = task.get('name', 'unnamed task')
                    variables[f"register.{reg_var}"] = f"<registered from: {task_name}>"
                
                # Extract set_fact variables
                if isinstance(task, dict) and 'set_fact' in task:
                    for fact_name, fact_value in task['set_fact'].items():
                        has_default, extracted_value, inferred_type = extract_jinja2_default(fact_value)
                        if has_default:
                            variables[f"set_fact.{fact_name}"] = extracted_value
                        else:
                            converted, tosca_value = convert_jinja2_to_tosca(fact_value)
                            variables[f"set_fact.{fact_name}"] = tosca_value
        
        # Extract pre_tasks
        if 'pre_tasks' in play:
            for task in play['pre_tasks']:
                if isinstance(task, dict) and 'register' in task:
                    reg_var = task['register']
                    variables[f"register.{reg_var}"] = "<registered from pre_tasks>"
        
        # Extract post_tasks
        if 'post_tasks' in play:
            for task in play['post_tasks']:
                if isinstance(task, dict) and 'register' in task:
                    reg_var = task['register']
                    variables[f"register.{reg_var}"] = "<registered from post_tasks>"
    
    return variables


def analyze_playbook(filepath):
    """Analyze a playbook file and return variable types."""
    try:
        with open(filepath, 'r') as f:
            playbook_data = yaml.safe_load(f)
        
        variables = extract_vars_from_playbook(playbook_data)
        
        return variables
    
    except yaml.YAMLError as e:
        print(f"Error parsing YAML: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(f"Error: File '{filepath}' not found", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def print_variable_report(variables, show_values=False, recursive=False):
    """Print a formatted report of variables and their types."""
    if not variables:
        print("No variables found in playbook.")
        return
    
    # Flatten variables if recursive mode is enabled
    if recursive:
        variables = flatten_variables(variables)
    
    print(f"\n{'Variable Name':<60} {'Type':<30} {'Value' if show_values else ''}")
    print("=" * (90 if not show_values else 150))
    
    for var_name, var_value in sorted(variables.items()):
        var_type = get_var_type(var_value)
        
        if show_values:
            # Truncate long values
            value_str = str(var_value)
            if len(value_str) > 50:
                value_str = value_str[:47] + "..."
            print(f"{var_name:<60} {var_type:<30} {value_str}")
        else:
            print(f"{var_name:<60} {var_type:<30}")
    
    print(f"\nTotal variables found: {len(variables)}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Ansible playbook variables and report their types"
    )
    parser.add_argument(
        "playbook",
        help="Path to the Ansible playbook file"
    )
    parser.add_argument(
        "-v", "--values",
        action="store_true",
        help="Show variable values along with types"
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Recursively show types of nested dictionary and list items"
    )
    parser.add_argument(
        "-t", "--tosca",
        action="store_true",
        help="Generate TOSCA data type definitions"
    )
    parser.add_argument(
        "-n", "--node-type",
        action="store_true",
        help="Generate TOSCA node type definition with interface (use with -t)"
    )
    parser.add_argument(
        "--node-name",
        default="AnsibleNode",
        help="Name for the generated node type (default: AnsibleNode)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file path (for TOSCA output)"
    )
    
    args = parser.parse_args()
    
    variables = analyze_playbook(args.playbook)
    
    if args.tosca:
        # Generate TOSCA data types
        tosca_types = generate_tosca_data_types(variables)
        tosca_node_type = None
        
        # Generate node type if requested
        if args.node_type:
            tosca_node_type = generate_tosca_node_type(variables, args.playbook, args.node_name)
        
        tosca_output = format_tosca_output(tosca_types, tosca_node_type, args.node_name)
        
        if args.output:
            with open(args.output, 'w') as f:
                f.write(tosca_output)
            print(f"TOSCA definitions written to: {args.output}")
        else:
            print(tosca_output)
    elif args.json:
        import json
        # Flatten for JSON output if recursive
        if args.recursive:
            variables = flatten_variables(variables)
        
        output = {
            var_name: {
                "type": get_var_type(var_value),
                "value": var_value if args.values else None
            }
            for var_name, var_value in variables.items()
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        print(f"\nAnalyzing playbook: {args.playbook}")
        print_variable_report(variables, show_values=args.values, recursive=args.recursive)


if __name__ == "__main__":
    main()
