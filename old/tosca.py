import ans2tosca.arg_spec

def format_module_info(loaded):
    """
    Format information about a loaded module for display.
    """
    info = dict()
    if isinstance(loaded, str):
        # Error message
        info['status'] = f"{loaded}"
        return info
    
    info['type'] = 'Loaded Python Module'
    info['object'] = f"{loaded}"
    
    if hasattr(loaded, '__file__'):
        info['file'] = f"{loaded.__file__}"
        
        # Try to determine if it's from a collection based on path
        if 'ansible_collections' in loaded.__file__:
            parts = loaded.__file__.split('ansible_collections')[1].split('/')
            if len(parts) >= 3:
                info['collection'] = f"{parts[1]}.{parts[2]}"
    
    if hasattr(loaded, 'DOCUMENTATION'):
        info['has_documentation'] =  'Yes'
    
    return info


# ----------------------------
# Conversion to TOSCA
# ----------------------------

TOSCA_TYPE_MAP = {
    "str": "string", "string": "string",
    "bool": "boolean", "boolean": "boolean",
    "int": "integer", "integer": "integer",
    "float": "float",
    "dict": "map", "mapping": "map",
    "list": "list", "sequence": "list",
    "path": "string",
#    "raw": "any",
    "raw": "bytes",
    "jsonarg": "any",
    "bytes": "string",
}

def convert_field_to_tosca(field):
    if not isinstance(field, dict):
        return {"type": "any"}

    prop_type = TOSCA_TYPE_MAP.get(field.get("type"), "any")
    prop = {"type": prop_type}
    if field.get("required"):
        prop["required"] = True
    if "default" in field:
        prop["default"] = field["default"]
    if "choices" in field:
        prop["validation"] = {"$valid_values": ['$value', list(field["choices"])]}
    if "options" in field and isinstance(field["options"], dict):
        prop["type"] = "map"
        prop["properties"] = convert_arg_spec_to_tosca(field["options"])
    if prop_type == "list" and "elements" in field:
        prop["entry_schema"] = {"type": TOSCA_TYPE_MAP.get(field["elements"], "any")}
    return prop

def convert_arg_spec_to_tosca(arg_spec):
    tosca_props = {}
    for k, v in arg_spec.items():
        tosca_props[k] = convert_field_to_tosca(v)
    return tosca_props

def convert_task_to_tosca_type(idx, result):

    metadata = dict()
    metadata['id'] = f"{idx}"
    metadata['task'] = f"{result['task']}"
    metadata['module_name'] = f"{result['module_name']}"
    metadata['module_info'] = format_module_info(result['loaded_module'])

    module = result['loaded_module']
    arg_spec = ans2tosca.arg_spec.extract_argument_spec(module)
    tosca_yaml = {
        "metadata": metadata,
        "properties": ans2tosca.tosca.convert_arg_spec_to_tosca(arg_spec)
    }
    return tosca_yaml
    
def convert_playbook_to_tosca(playbook, results):
    
    node_types = dict()
    for idx, result in enumerate(results, 1):
        node_yaml = convert_task_to_tosca_type(idx, result)
        node_types[result['module_name']] = node_yaml

    tosca_yaml = {
        'tosca_definitions_version': 'tosca_2_0',
        'description': f"TOSCA types created from Ansible playbook {playbook}",
        'node_types': node_types
        }
    return tosca_yaml
