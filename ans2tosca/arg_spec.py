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
