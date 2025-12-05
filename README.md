# Ansible Module Argument Spec Extractor

This tool extracts the fully merged `argument_spec` from any Ansible module safely and converts it to JSON Schema (Draft-07). It works for both core Ansible modules and custom modules, including AWS modules that inherit from `AnsibleAWSModule`.

---

## Features

- Captures **module-specific and base arguments**.
- Safe: **no real actions or external calls are made**.
- Compatible with **all Ansible modules**, including custom modules and AWS modules.
- Converts argument specifications to **JSON Schema**.
- Handles nested options, lists, and choices.
- Falls back to module-level `argument_spec` if dynamic extraction fails.

---

## Requirements

- Python 3.7+
- Ansible installed (for module dependencies)

---

## Installation

No installation required. Save the script as:

```text
ansible_argument_spec_extractor.py
```

Make it executable (optional):

```bash
chmod +x ansible_argument_spec_extractor.py
```

---

## Usage

### Basic usage

Extract the schema and print to stdout:

```bash
python ansible_argument_spec_extractor.py /path/to/module.py
```

### Save schema to a file

```bash
python ansible_argument_spec_extractor.py /path/to/module.py -o module.schema.json
```

Example:

```bash
python ansible_argument_spec_extractor.py user.py -o user.schema.json
```

---

## Output

- The script outputs a JSON Schema (Draft-07) representing the module’s argument specification.
- If the argument specification cannot be found, you may see:

```
WARNING: argument_spec could not be found
```

> The script attempts dynamic extraction first, then falls back to static module-level `argument_spec` if necessary.

---

## Notes

- This script **mocks `AnsibleModule` and `AnsibleAWSModule`** to safely capture `argument_spec` during `main()` execution.
- It **overrides `exit_json` and `fail_json`** to prevent the module from stopping the process.
- Nested `options` and `list` elements are automatically converted to JSON Schema objects and arrays.

---

## Example

```bash
# Extract schema for the user module
python ansible_argument_spec_extractor.py user.py -o user.schema.json

# Output is saved in user.schema.json
cat user.schema.json
```

---

## License

MIT License — free to use and modify.