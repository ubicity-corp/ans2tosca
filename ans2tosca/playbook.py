import yaml
import re

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


def convert_jinja2_to_tosca(value):
    """
    Convert Jinja2 expressions to TOSCA function calls.
    Handles variable references like {{ username }} and constructs TOSCA concat/get_property.
    
    Examples:
    - "/home/{{ username }}" -> { $concat: ['/home/', { $get_property: username }] }
    - "{{ username }}_backup" -> { $concat: [{ $get_property: username }, '_backup'] }
    - "prefix_{{ var1 }}_{{ var2 }}_suffix" -> { $concat: ['prefix_', { $get_property: var1 }, '_', { $get_property: var2 }, '_suffix'] }
    
    Args:
        value: The string value to convert
    
    Returns: (converted, tosca_value) where converted is True if conversion happened
    """
    if not isinstance(value, str):
        return False, value
    
    # Check if string contains Jinja2 variable references (but not default filters)
    jinja_pattern = r'\{\{\s*(\w+)\s*\}\}'
    matches = list(re.finditer(jinja_pattern, value))
    
    if not matches:
        return False, value
    
    # If the entire string is just a single variable reference, use
    # get_property directly
    if len(matches) == 1 and matches[0].group(0) == value.strip():
        var_name = matches[0].group(1)
        return True, {'$get_property': ['SELF', var_name]}
    
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
        
        # Add get_property for the variable
        concat_parts.append({'$get_property': ['SELF', var_name]})
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
        return True, {'$concat': concat_parts}


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


def process_playbook(filepath):
    """Process a playbook file and return variable types."""
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
