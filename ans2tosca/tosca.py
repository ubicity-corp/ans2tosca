from collections import defaultdict
import yaml

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
                        'default': field_value  # Include default value
                    }
                else:
                    # List of primitives
                    entry_type = infer_list_entry_type(field_value)
                    properties[field_name] = {
                        'type': 'list',
                        'entry_schema': {'type': entry_type},
                        'default': field_value  # Include default value
                    }
            else:
                # Simple type
                properties[field_name] = {
                    'type': get_tosca_type(field_value),
                    'default': field_value  # Include default value
                }
        
        return {
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


def generate_tosca_node_type(variables, playbook_path):
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
        }
        
        # Add default value only if it exists (could be a TOSCA function)
        if has_default:
            prop_def['default'] = var_value
        
        # For complex types, reference the generated data type
        if isinstance(var_value, dict) and not isinstance(var_value, dict) or (isinstance(var_value, dict) and '$get_property' not in var_value and '$concat' not in var_value):
            prop_def['type'] = f'AnsibleData_{prop_name}'
        elif isinstance(var_value, list) and not isinstance(var_value, dict):
            if var_value and isinstance(var_value[0], dict):
                prop_def['type'] = 'list'
                prop_def['entry_schema'] = {'type': f'AnsibleData_{prop_name}_item'}
            else:
                prop_def['type'] = 'list'
                prop_def['entry_schema'] = {'type': infer_list_entry_type(var_value)}
        
        # Add description based on type
        if isinstance(var_value, dict) and 'concat' not in var_value and '$get_property' not in var_value:
            prop_def['description'] = f'Configuration for {prop_name}'
        elif isinstance(var_value, list):
            prop_def['description'] = f'List of {prop_name}'
        else:
            prop_def['description'] = f'Value for {prop_name}'
        
        properties[prop_name] = prop_def
    
    # Generate property inputs for the create operation
    # Map each property to $get_property function
    operation_inputs = {}
    for prop_name in properties.keys():
        operation_inputs[prop_name] = {'$get_property': ['SELF', prop_name]}
    
    # Create the node type definition
    node_type = {
        'derived_from': 'ubct:Root',
        'description': f'Node type generated from Ansible playbook {playbook_path}',
        'properties': properties,
        'interfaces': {
            'Standard': {
                'operations': {
                    'create': {
                        'implementation': {
                            'primary': {
                                'file': playbook_path,
                                'type': 'ubct:Ansible'
                                }
                        },
                        'inputs': operation_inputs
                    }
                }
            }
        }
    }
    
    return node_type


def generate_service_template_inputs(variables):
    """Generate service template input definitions from Ansible variables.
    """
    inputs = {}
    
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
        }
        
        # Add default value only if it exists (could be a TOSCA function)
        if has_default:
            prop_def['required'] = False
        
        # For complex types, reference the generated data type
        if isinstance(var_value, dict) and not isinstance(var_value, dict) or (isinstance(var_value, dict) and '$get_property' not in var_value and '$concat' not in var_value):
            prop_def['type'] = f'AnsibleData_{prop_name}'
        elif isinstance(var_value, list) and not isinstance(var_value, dict):
            if var_value and isinstance(var_value[0], dict):
                prop_def['type'] = 'list'
                prop_def['entry_schema'] = {'type': f'AnsibleData_{prop_name}_item'}
            else:
                prop_def['type'] = 'list'
                prop_def['entry_schema'] = {'type': infer_list_entry_type(var_value)}
        inputs[prop_name] = prop_def
    
    return inputs


def generate_tosca_node_template(variables, node_type_name):
    """Generate TOSCA node template definition from Ansible variables.
    Property assignments retrieve values from inputs.
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
        
        properties[prop_name] = {'$get_input': prop_name}
    
    # Create the node type definition
    node_template = {
        'type': node_type_name,
        'properties': properties,
        }
    
    return node_template


def format_tosca_output(tosca_types, tosca_node_type, node_type_name, inputs,
                        tosca_node_template, node_template_name):
    """Format TOSCA types and node type as YAML string."""
    tosca_document = {
        'tosca_definitions_version': 'tosca_2_0',
        'description': 'TOSCA node type wrapper for Ansible playbook',
        'imports': [
            {
                'profile': 'com.ubicity:2.0',
                'namespace': 'ubct'
                }
        ]
    }
    
    tosca_document['data_types'] = tosca_types
    tosca_document['node_types'] = {
        node_type_name: tosca_node_type
    }
    tosca_document['service_template'] = {
        'inputs': inputs,
        'node_templates': {
            node_template_name: tosca_node_template
        }
    }
    
    return yaml.dump(tosca_document, default_flow_style=False, sort_keys=False, width=120)


def create_tosca_file(variables, playbook_path, node_type_name, node_template_name):

    # Generate TOSCA data types
    tosca_types = generate_tosca_data_types(variables)

    # Generate TOSCA node type
    tosca_node_type = generate_tosca_node_type(variables, playbook_path)

    # Generate TOSCA service template inputs
    tosca_inputs = generate_service_template_inputs(variables)

    # Generate TOSCA node template
    tosca_node_template = generate_tosca_node_template(variables, node_type_name)

    # Create TOSCA definitions
    tosca_output = format_tosca_output(tosca_types, tosca_node_type, node_type_name, tosca_inputs, tosca_node_template, node_template_name)

    return tosca_output
