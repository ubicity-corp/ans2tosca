# ----------------------------
# Conversion to JSON Schema
# ----------------------------

JSON_TYPE_MAP = {
    "str": "string", "string": "string",
    "bool": "boolean", "boolean": "boolean",
    "int": "integer", "integer": "integer",
    "float": "number",
    "dict": "object", "mapping": "object",
    "list": "array", "sequence": "array",
    "path": "string",
    "raw": None,
    "jsonarg": None,
    "bytes": "string",
}

def convert_field_to_json_schema(name, opts):
    prop = {}
    if not isinstance(opts, dict):
        return {"description": "UNRESOLVED"}, None
    ans_type = opts.get("type")
    json_type = JSON_TYPE_MAP.get(ans_type) if ans_type else "string"
    if json_type:
        prop["type"] = json_type
    if "choices" in opts:
        prop["enum"] = list(opts["choices"])
    if "default" in opts:
        prop["default"] = opts["default"]
    if ans_type in ("raw", "jsonarg"):
        prop.pop("type", None)
    # nested options
    if "options" in opts and isinstance(opts["options"], dict):
        prop["type"] = "object"
        nested = convert_arg_spec_to_json_schema(opts["options"])
        prop["properties"] = nested.get("properties", {})
        if "required" in nested:
            prop["required"] = nested["required"]
    if ans_type == "list" and "elements" in opts:
        elem_type = JSON_TYPE_MAP.get(opts["elements"]) if isinstance(opts["elements"], str) else None
        prop["items"] = {"type": elem_type} if elem_type else {}
    required_here = [name] if opts.get("required") else None
    return prop, required_here

def convert_arg_spec_to_json_schema(arg_spec):
    schema = {"type": "object", "properties": {}}
    required_fields = []
    for k, v in arg_spec.items():
        prop, req = convert_field_to_json_schema(k, v)
        schema["properties"][k] = prop
        if req:
            required_fields.extend(req)
    if required_fields:
        schema["required"] = list(dict.fromkeys(required_fields))
    return schema
