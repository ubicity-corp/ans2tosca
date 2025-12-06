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
    "raw": "any",
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
        prop["constraints"] = [{"valid_values": list(field["choices"])}]
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
