# Ansible to TOSCA Converter

## TOSCA Node Type Creation
This tool converts Ansible playbooks to TOSCA files as follows:

- A TOSCA node type is created that acts as a *wrapper* around the
  playbook.
- Playbook variables are converted to TOSCA property definitions for
  the newly created node type. Default values are assigned as
  specified in the playbook.
- A Standard interface is defined on the node type with a `create`
  operation that uses the playbook as its implementation artifact.
- Operation inputs are defined for the `create` operation that use
  `$get_property` functions to reference node properties

## TOSCA Data Type Creation

- Property definitions in the newly created TOSCA node types use TOSCA
  data types that are inferred from the types of the playbook
  variables.
- Primarty types are converted directly to their corresponding TOSCA
  types (string, integer, boolean, float, list, map).
- Playbook variables that are dictionaries are converted to complex
  TOSCA data types. Nested structures become separate, reusable TOSCA
  data types.
- For lists of dictionaries, custom `entry_schema` types are created. 

## Service Template Creation

> This feature has not yet been implemented.

Several Ansible playbooks may be required to configure devices or to
deploy services. These playbooks will be combined into a single TOSCA
service template as follows:

- For each of the playbooks, a corresponding TOSCA node type is
  defined.
- For each of the playbooks, a node template of the newly created
  TOSCA type is created.
- Execution ordering between the playbooks maps to `DependsOn`
  relationships between the node templates.

## Using `ans2tosca`

The following shows the top-level commands exposed by the `ans2tosca`
as well as the available command line options:
```
usage: ans2tosca [-h] [-n NODE_NAME] [-o OUTPUT] playbook

Convert Ansible playbook to TOSCA file

positional arguments:
  playbook              Path to the Ansible playbook file

options:
  -h, --help            show this help message and exit
  -n NODE_NAME, --node-name NODE_NAME
                        Optional name for the generated node type
  -o OUTPUT, --output OUTPUT
                        Optional output file path. Defaults to <stderr>
```

## Installing `ans2tosca`
`ans2tosca` is written in Python3. We recommend that you run the in a
virtual environment. To support virtual environments, make sure the
python virtual environments module is installed. On Fedora, the
virtual environment module appears to be included in the standard
Python3 installation. On Ubuntu, the virtual environments module can
be installed as follows:

    sudo apt install python3-venv

You can then create and activate your virtual environment as follows:

    python3 -m venv env
    source env/bin/activate
    
The `ans2tosca` tool uses
[PEP-517](https://www.python.org/dev/peps/pep-0517/) and
[PEP-518](https://www.python.org/dev/peps/pep-0518/) based
installation systems that require the latest version of ``pip``. To
upgrade ``pip`` to the latest version, run the following command in
your virtual environment:

    pip install -U pip 

Next, download the latest release from
[`https://github.com/ubicity-corp/ans2tosca/releases/download/v0.0.1/ans2tosca-0.0.1-py3-none-any.whl`](https://github.com/ubicity-corp/ans2tosca/releases/download/v0.0.1/ans2tosca-0.0.1-py3-none-any.whl)
and install it in the activated virtual environment using the downloaded
wheel file:

```
pip install ans2tosca-0.0.1-py3-none-any.whl
```
You can verify that the ans2tosca software has been installed 
by running the following command in your virtual environment:

    ans2tosca --version

This will display the version of the installed software. 

