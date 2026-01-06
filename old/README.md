# Ansible to TOSCA Converter

This tool converts Ansible playbooks to TOSCA as follows:

- For each task in the playbook, it finds the corresponding Ansible
  module that is used to execute that task.
- It then extracts the fully merged `argument_spec` of that module.
- It converts this argument spec to property definitions in a
  corresponding TOSCA node type.
- It creates a TOSCA service template that can be used to invoke the
  playbook.

The current version is limited to creating TOSCA types with the
corresponding property definitions based on the `argument_spec` in
Ansible modules. Full support for creating TOSCA service templates is
under development.

## Using `ans2tosca`

The following shows the top-level commands exposed by the `ans2tosca`
as well as the available command line options:
```
Usage: ans2tosca [-h] [-v] [-o OUTPUT] [--format {tosca,jsonschema}] playbook

Convert Ansible playbook to TOSCA

positional arguments:
  playbook              Path to the Ansible playbook

options:
  -h, --help            show this help message and exit
  -v, --version         show program's version number and exit
  -o OUTPUT, --output OUTPUT
                        Output file (default: stdout)
  --format {tosca,jsonschema}
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

