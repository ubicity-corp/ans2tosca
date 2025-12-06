# Ansible to TOSCA Converter

This tool converts Ansible playbooks to TOSCA as follows:

- It creates a TOSCA service template that can be used to invoke the
  playbook.
- It uses TOSCA types that are created automatically based on the
  Ansible modules that are used to process the playbook. Specifically,
  the tool extracts the fully merged `argument_spec` from any Ansible
  module safely and converts to property definitions in a
  corresponding TOSCA node types.

The current version is limited to creating TOSCA property definitions
based on the `argument_spec` in Ansible modules. Full support for
Ansible playbooks is under development.

## Using `ans2tosca`

The following shows the top-level commands exposed by the `ans2tosca`
as well as the available command line options:
```
usage: ans2tosca [-h] [-v] [-o OUT] [--format {jsonschema,tosca}] module_path

Convert Ansible module argument_spec to TOSCA or JSON Schema

positional arguments:
  module_path           Path to the module .py file

options:
  -h, --help            show this help message and exit
  -v, --version         show program's version number and exit
  -o OUT, --out OUT     Output file (default: stdout)
  --format {jsonschema,tosca}
                        Output format: tosca (default) or jsonschema
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

