# AWS Ansible Argument Spec Extractor

This tool extracts the fully merged `argument_spec` from AWS Ansible modules (e.g., `ec2_instance`, `s3_bucket`) safely and converts it to JSON Schema (Draft-07). It works even for modules that inherit from `AnsibleAWSModule` and dynamically merge arguments at runtime.

---

## Features

- Captures **module-specific and base AWS arguments**.
- Safe: **no real AWS calls are made**.
- Compatible with **all AWS Ansible modules**.
- Converts argument specifications to **JSON Schema**.
- Handles nested options, lists, and choices.

---

## Requirements

- Python 3.7+
- Ansible installed (for module dependencies)

---

## Installation

No installation required. Save the script as:

```text
ansible_aws_argument_spec_extractor.py
```

Make it executable (optional):

```bash
chmod +x ansible_aws_argument_spec_extractor.py
```

---

## Usage

### Basic usage

Extract the schema and print to stdout:

```bash
python ansible_aws_argument_spec_extractor.py /path/to/module.py
```

### Save schema to a file

```bash
python ansible_aws_argument_spec_extractor.py /path/to/module.py -o module.schema.json
```

Example:

```bash
python ansible_aws_argument_spec_extractor.py ec2_instance.py -o ec2_instance.schema.json
```

---

## Output

- The script outputs a JSON Schema (Draft-07) representing the module’s argument specification.
- If the argument specification cannot be found, you will see:

```
WARNING: argument_spec could not be found
```

> Note: With the current script, AWS modules like `ec2_instance` or `s3_bucket` should capture the merged spec correctly.

---

## Notes

- This script **mocks `AnsibleAWSModule`** to safely capture `argument_spec` during `main()` execution.
- It **overrides `exit_json` and `fail_json`** to prevent the module from stopping the process.
- Nested `options` and `list` elements are automatically converted to JSON Schema objects and arrays.

---

## Example

```bash
# Extract schema for AWS EC2 instance module
python ansible_aws_argument_spec_extractor.py ec2_instance.py -o ec2_instance.schema.json

# Output is saved in ec2_instance.schema.json
cat ec2_instance.schema.json
```

---

## License

MIT License — free to use and modify.