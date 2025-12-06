"""Extract argument specs from Ansible modules. 

This can be challenging for modules like AWS modules (e.g.,
ec2_instance, s3_bucket) or AnsibleAWSModule subclasses that don't
store the argument_spec as a simple class attribute or top-level
variable at import time. Instead, The actual argument_spec is
constructed inside the module’s main() function.  Sometimes it calls
helper functions from module_utils/aws/core.py to merge base AWS
args. The merged argument_spec does not exist until the module runs or
the constructor runs with valid parameters.

For modules where the argument spec only exists inside main() or the
constructor at runtime, the module's main has to be called. However,
safe import + safe instantiation is not enough, because constructors
may fail without required kwargs.

Instead, we run the module in a controlled sandbox that executes the
module with mocked AnsibleModule (like the pytest-ansible
strategy). This mocked module patches

    AnsibleModule.__init__
    AnsibleModule.exit_json
    AnsibleModule.fail_json

This will then allow us to call main(), which will populate the merged
argument_spec.
"""
import sys
import os
import importlib.util
import types

# ----------------------------
# Mock class to capture argument_spec
# ----------------------------

class CaptureArgumentSpec:
    captured_spec = None

    def __init__(self, argument_spec=None, supports_check_mode=False, *args, **kwargs):
        self.argument_spec = argument_spec or {}
        self.supports_check_mode = supports_check_mode
        CaptureArgumentSpec.captured_spec = self.argument_spec

    def exit_json(self, **kwargs):
        pass

    def fail_json(self, **kwargs):
        pass

# ----------------------------
# Helpers
# ----------------------------

def safe_import_module(path: str):
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location("__ansible_module__", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def patch_module(module):
    if hasattr(module, "AnsibleModule"):
        module.AnsibleModule = CaptureArgumentSpec
    if hasattr(module, "AnsibleK8SModule"):
        module.AnsibleK8SModule = CaptureArgumentSpec
    if hasattr(module, "AnsibleAWSModule"):
        module.AnsibleAWSModule = CaptureArgumentSpec
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, type):
            bases = [b.__name__ for b in getattr(attr, "__mro__", [])]
            if "AnsibleModule" in bases or "AnsibleAWSModule" in bases or "AnsibleK8SModule" :
                setattr(module, attr_name, CaptureArgumentSpec)

def extract_argument_spec(module):
    patch_module(module)
    if hasattr(module, "main"):
        try:
            module.main()
        except Exception:
            pass
    return getattr(CaptureArgumentSpec, "captured_spec", {}) or getattr(module, "argument_spec", {})
