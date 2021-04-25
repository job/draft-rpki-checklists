# draft-ietf-sidrops-rpki-rsc

Work in progress repository for Internet-Draft draft-ietf-sidrops-rpki-rsc

## Usage

### Draft documents

The source files for the Internet-Draft documents are:

- `draft-ietf-sidrops-rpki-rsc.xml`
- `RpkiSignedChecklist-2021.asn`

To regenerate the text and HTML versions after making changes, run:

``` sh
make drafts
```

### Object prototyping

An [rpkimancer](https://github.com/benmaddison/rpkimancer/) plug-in is also
available, providing the ability to read and write example checklist objects.

To install (in the root of your checkout):

``` sh
pip install .
```

Object creation and inspection is provided by the `rpkincant` CLI tool.

See `rpkincant --help` for usage information.

After making changes to the ASN.1 module source, execute `make asn1` to update
the patched version in python distribution tree.

To setup a development environment with the required test dependencies:

``` sh
python -m venv .venv
. .venv/bin/activate
pip install -r packaging/requirements-dev.txt
```
