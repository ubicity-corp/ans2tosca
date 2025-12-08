#!/usr/bin/env python3
"""
Script to load the Python module that processes each task in an Ansible playbook.
Supports both built-in modules and collection modules.
"""

import yaml
import sys
import importlib
import importlib.util
from pathlib import Path


def find_collection_paths():
    """
    Find all Ansible collection paths.
    """
    collection_paths = []
    
    try:
        from ansible import context
        from ansible.module_utils.common.collections import is_sequence
        
        # Try to get collection paths from ansible configuration
        try:
            from ansible.utils.collection_loader import AnsibleCollectionConfig
            config = AnsibleCollectionConfig()
            if hasattr(config, 'collection_paths'):
                collection_paths.extend(config.collection_paths)
        except:
            pass
        
        # Try default collection paths
        default_paths = [
            Path.home() / '.ansible' / 'collections' / 'ansible_collections',
            Path('/usr/share/ansible/collections/ansible_collections'),
            Path('/etc/ansible/collections/ansible_collections'),
        ]
        
        for path in default_paths:
            if path.exists():
                collection_paths.append(str(path))
    except:
        pass
    
    return collection_paths


def load_collection_module(namespace, collection, module_name):
    """
    Load a module from an Ansible collection.
    Example: ansible.builtin.copy -> namespace=ansible, collection=builtin, module=copy
    """
    try:
        # Try to import as a Python module
        module_path = f"ansible_collections.{namespace}.{collection}.plugins.modules.{module_name}"
        return importlib.import_module(module_path)
    except (ImportError, ModuleNotFoundError):
        pass
    
    # Try to find it in collection paths and load it dynamically
    collection_paths = find_collection_paths()
    for base_path in collection_paths:
        module_file = Path(base_path) / namespace / collection / 'plugins' / 'modules' / f"{module_name}.py"
        if module_file.exists():
            # Load the module from file path
            spec = importlib.util.spec_from_file_location(
                f"ansible_collections.{namespace}.{collection}.plugins.modules.{module_name}",
                module_file
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)
                return module
    
    return None


def load_ansible_module(module_name):
    """
    Load the Python module for an Ansible module.
    Handles both FQCN (Fully Qualified Collection Names) and short names.
    Returns the loaded module object or information about it.
    """
    try:
        # Check if it's a FQCN (e.g., ansible.builtin.copy or community.general.docker_container)
        parts = module_name.split('.')
        
        if len(parts) >= 3:
            # This is a FQCN: namespace.collection.module_name
            namespace = parts[0]
            collection = parts[1]
            module = '.'.join(parts[2:])  # Handle nested module names
            
            result = load_collection_module(namespace, collection, module)
            if result:
                return result
        
        # Try as built-in ansible module first
        if len(parts) >= 2:
            simple_name = parts[-1]
        else:
            simple_name = module_name
        
        # Try built-in ansible.builtin collection first
        builtin_result = load_collection_module('ansible', 'builtin', simple_name)
        if builtin_result:
            return builtin_result
        
        # Common patterns for legacy Ansible module imports (pre-collection)
        import_patterns = [
            f"ansible.modules.{simple_name}",
            f"ansible.modules.system.{simple_name}",
            f"ansible.modules.commands.{simple_name}",
            f"ansible.modules.files.{simple_name}",
            f"ansible.modules.packaging.os.{simple_name}",
            f"ansible.modules.cloud.{simple_name}",
            f"ansible.modules.network.{simple_name}",
        ]
        
        for pattern in import_patterns:
            try:
                module = importlib.import_module(pattern)
                return module
            except (ImportError, ModuleNotFoundError):
                continue
        
        return f"Could not load module: {module_name}"
        
    except Exception as e:
        return f"Error loading module {module_name}: {str(e)}"


def extract_module_name(task):
    """
    Extract the module name from a task definition.
    """
    # Skip keys that are not module names
    skip_keys = {'name', 'tags', 'when', 'register', 'become', 'become_user', 
                 'vars', 'with_items', 'loop', 'notify', 'changed_when', 
                 'failed_when', 'ignore_errors', 'delegate_to', 'run_once',
                 'until', 'retries', 'delay', 'environment', 'no_log',
                 'async', 'poll', 'connection', 'remote_user', 'block',
                 'rescue', 'always', 'any_errors_fatal', 'max_fail_percentage'}
    
    for key in task:
        if key not in skip_keys:
            return key
    return None


def parse_playbook(playbook_path):
    """
    Parse an Ansible playbook and extract tasks with their modules.
    """
    with open(playbook_path, 'r') as f:
        playbook = yaml.safe_load(f)
    
    results = []
    
    if not playbook:
        return results
    
    # Iterate through plays
    for play_idx, play in enumerate(playbook):
        play_name = play.get('name', f'Play {play_idx + 1}')
        
        # Check for tasks
        tasks = play.get('tasks', [])
        
        for task_idx, task in enumerate(tasks):
            task_name = task.get('name', f'Task {task_idx + 1}')
            module_name = extract_module_name(task)
            
            if module_name:
                loaded_module = load_ansible_module(module_name)
                results.append({
                    'play': play_name,
                    'task': task_name,
                    'module_name': module_name,
                    'loaded_module': loaded_module
                })
        
        # Check for pre_tasks
        pre_tasks = play.get('pre_tasks', [])
        for task_idx, task in enumerate(pre_tasks):
            task_name = task.get('name', f'Pre-task {task_idx + 1}')
            module_name = extract_module_name(task)
            
            if module_name:
                loaded_module = load_ansible_module(module_name)
                results.append({
                    'play': play_name,
                    'task': f"[PRE] {task_name}",
                    'module_name': module_name,
                    'loaded_module': loaded_module
                })
        
        # Check for post_tasks
        post_tasks = play.get('post_tasks', [])
        for task_idx, task in enumerate(post_tasks):
            task_name = task.get('name', f'Post-task {task_idx + 1}')
            module_name = extract_module_name(task)
            
            if module_name:
                loaded_module = load_ansible_module(module_name)
                results.append({
                    'play': play_name,
                    'task': f"[POST] {task_name}",
                    'module_name': module_name,
                    'loaded_module': loaded_module
                })
    
    return results
