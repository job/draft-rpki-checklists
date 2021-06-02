# Copyright (c) 2021 Ben Maddison. All rights reserved.
#
# The contents of this file are licensed under the MIT License
# (the "License"); you may not use this file except in compliance with the
# License.
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.
"""xml2rfc document generation extension."""

from __future__ import annotations

import difflib
import docutils
import itertools
import os
import subprocess
import tempfile
import typing

import git

import sphinx

logger = sphinx.util.logging.getLogger(__name__)


class VersionDirective(sphinx.directives.ObjectDescription):

    has_content = False
    required_arguments = 1
    option_spec = {
        "ref_type": docutils.parsers.rst.directives.unchanged_required,
        "ref_name": docutils.parsers.rst.directives.unchanged_required,
        "ref_path": docutils.parsers.rst.directives.unchanged_required
    }

    def run(self):
        self.version = Version(base_dir=get_base_dir(self.env.app),
                               draft=self.arguments[0].strip(),
                               ref_type=self.options.get("ref_type").strip(),
                               ref_name=self.options.get("ref_name").strip(),
                               ref_path=self.options.get("ref_path").strip())
        return super().run()

    def handle_signature(self, sig, signode):
        signode += sphinx.addnodes.desc_name(text=sig)
        return sig

    def transform_content(self, contentnode):
        src = self.version.read_src()
        code_block = docutils.nodes.literal_block(src, src)
        code_block["language"] = "text"
        contentnode += code_block

    def add_target_and_index(self, name_cls, draft, signode):
        signode["ids"].append(self.version.anchor)
        domain = self.env.get_domain("xml2rfc")
        domain.add_version(self.version)


class Version(typing.NamedTuple):

    base_dir: str
    draft: str
    ref_type: str
    ref_name: str
    ref_path: str

    @property
    def anchor(self):
        return f"xml2rfc-version-{self.draft}-{self.ref_type}-{self.ref_name}"

    def read_src(self):
        src_path = os.path.join(self.base_dir,
                                self.ref_path,
                                f"{self.draft}.txt")
        logger.info(f"reading internet draft content from {src_path}")
        with open(src_path) as fd:
            src = fd.read()
        return src


class VersionNotFound(Exception):
    pass

class DiffDirective(sphinx.directives.ObjectDescription):

    has_content = False
    required_arguments = 1
    option_spec = {
        "from": docutils.parsers.rst.directives.unchanged_required,
        "to": docutils.parsers.rst.directives.unchanged_required
    }

    def run(self):
        self.diff = Diff(draft=self.arguments[0].strip(),
                         ref_from=self.options.get("from").strip(),
                         ref_to=self.options.get("to").strip())
        return super().run()

    def handle_signature(self, sig, signode):
        signode += sphinx.addnodes.desc_name(text=sig)
        return sig

    def transform_content(self, contentnode):
        domain = self.env.get_domain("xml2rfc")
        from_version = domain.search_version(self.diff.ref_from)
        to_version = domain.search_version(self.diff.ref_to)
        diff_lines = difflib.unified_diff(from_version.read_src().split("\n"),
                                          to_version.read_src().split("\n"),
                                          fromfile=from_version.ref_path,
                                          tofile=to_version.ref_path)
        diff_src = "\n".join(diff_lines)
        code_block = docutils.nodes.literal_block(diff_src, diff_src)
        code_block["language"] = "diff"
        contentnode += code_block

    def add_target_and_index(self, name_cls, draft, signode):
        signode["ids"].append(self.diff.anchor)
        domain = self.env.get_domain("xml2rfc")
        domain.add_diff(self.diff)


class Diff(typing.NamedTuple):

    draft: str
    ref_to: str
    ref_from: str

    @property
    def anchor(self):
        return f"xml2rfc-diff-{self.draft}-{self.ref_from}-{self.ref_to}"


class VersionsIndex(sphinx.domains.Index):

    name = "version-index"
    localname = "Internet Draft Versions"
    shortname = "drafts"

    def generate(self, docnames=None):

        def by_ref_type(version):
            return version[2]

        versions = self.domain.get_objects()
        index = [(group, [(name, 0, docname, anchor, "", "", object_type)
                          for name, _, object_type, docname, anchor, _
                          in items])
                 for group, items in itertools.groupby(versions, by_ref_type)]
        logger.debug(f"{index=}")
        return index, True


class Xml2rfcDomain(sphinx.domains.Domain):

    name = "xml2rfc"
    roles = {"ref": sphinx.roles.XRefRole()}
    directives = {"version": VersionDirective,
                  "diff": DiffDirective}
    indices = (VersionsIndex,)
    initial_data = {"versions": set(),
                    "diffs": set()}

    def get_objects(self):
        for version, docname in self.data["versions"]:
            name = display_name = f"{version.draft}@{version.ref_name}"
            object_type = self.object_type_name(version.ref_type)
            anchor = version.anchor
            priority = 1
            yield (name, display_name, object_type, docname, anchor, priority)

    @property
    def versions(self):
        for version, _ in self.data["versions"]:
            yield version

    def search_version(self, ref_path):
        for version in self.versions:
            if version.ref_path == ref_path:
                return version
        raise VersionNotFound(ref_path)

    def resolve_xref(self, env, fromdocname, builder,
                     typ, target, node, contnode):
        return None

    @staticmethod
    def object_type_name(ref_type):
        base_name = "Internet Draft Version"
        names = {"branches": "Branch",
                 "tags": "Tag"}
        try:
            return f"{base_name} ({names[ref_type]})"
        except KeyError:
            return base_name

    def add_version(self, version):
        self.data["versions"].add((version, self.env.docname))

    def add_diff(self, diff):
        self.data["diffs"].add((diff, self.env.docname))


def get_base_dir(app):
    return os.path.join(app.confdir, app.config.xml2rfc_output)


def autogen(app):
    """Generate HTML output from XML sources at every git ref."""

    app.env.xml2rfc_versions = dict()
    if not app.config.xml2rfc_drafts:
        return

    if app.config.xml2rfc_autogen_versions:
        autogen_versions(app)
        if app.config.xml2rfc_autogen_docs:
            autogen_docs(app)
    return


def autogen_versions(app):
    proc = subprocess.run(("xml2rfc", "--version"),
                          capture_output=True, check=True)
    xml2rfc_version = proc.stdout.decode().strip()
    logger.info(f"sphinx-xml2rfc: using {xml2rfc_version}")

    repo = git.Repo(path=os.path.dirname(__file__),
                    search_parent_directories=True)
    file_names = [f"{draft}.xml" for draft in app.config.xml2rfc_drafts]
    file_names += app.config.xml2rfc_sources

    refs = {"branches": {b.name: b for b in repo.branches},
            "tags": {t.name: t for t in repo.tags}}

    versions = list()
    for ref_type, refs in refs.items():
        for ref_name, ref in refs.items():
            output_dir = os.path.join(get_base_dir(app), *ref.path.split("/"))
            os.makedirs(output_dir, exist_ok=True)
            logger.debug(f"{output_dir=}")
            with tempfile.TemporaryDirectory() as tmpdir:
                logger.debug(f"{ref_name=}, {ref.path=}")
                for blob in ref.commit.tree.blobs:
                    if blob.name not in file_names:
                        continue
                    logger.debug(f"{blob.name=}")
                    logger.debug(f"{blob.hexsha=}")
                    with open(os.path.join(tmpdir, blob.name), "wb") as f:
                        blob.stream_data(f)
                for draft in app.config.xml2rfc_drafts:
                    logger.info(f"generating output for {draft} at {ref.path}")
                    date = ref.commit.committed_datetime.strftime("%Y-%m-%d")
                    cmd = ("xml2rfc", f"{draft}.xml",
                           "--date", date,
                           "--no-pagination",
                           "--text",
                           "--path", output_dir)
                    logger.debug(f"{cmd=}")
                    try:
                        proc = subprocess.run(cmd, check=True,
                                              capture_output=True)
                    except subprocess.CalledProcessError as e:
                        logger.warning(e.stderr.decode())
                    logger.debug(proc.stderr.decode())
                    versions.append((draft, ref_type, ref_name, ref))
    app.env.xml2rfc_auto_versions = versions
    logger.debug(f"{app.env.xml2rfc_auto_versions=}")
    return


def prior_versions(app, ref):
    for version in app.env.xml2rfc_auto_versions:
        commit = version[3].commit
        if commit.committed_datetime < ref.commit.commited_datetime:
            yield version


def autogen_docs(app):
    base_dir = get_base_dir(app)
    with open(os.path.join(base_dir, "toc.md"), "w") as toc_fd:
        toc_fd.write("# Internet Drafts\n\n"
                     ":::{toctree}\n"
                     ":maxdepth: 3\n\n")
        for draft, versions in itertools.groupby(app.env.xml2rfc_auto_versions,
                                                 lambda v: v[0]):
            draft_toc = f"toc-{draft}"
            toc_fd.write(f"{draft_toc}\n")
            with open(os.path.join(base_dir, f"{draft_toc}.md"),
                      "w") as draft_toc_fd:
                draft_toc_fd.write(f"# `{draft}`\n\n"
                                   f":::{{toctree}}\n\n")
                for ref_type, versions in itertools.groupby(versions,
                                                            lambda v: v[1]):
                    ref_type_toc = f"{draft_toc}-{ref_type}"
                    draft_toc_fd.write(f"{ref_type_toc}\n")
                    with open(os.path.join(base_dir, f"{ref_type_toc}.md"),
                              "w") as ref_type_toc_fd:
                        ref_type_toc_fd.write(f"# {ref_type}\n\n"
                                              f":::{{toctree}}\n\n")
                        for _, _, ref_name, ref in versions:
                            draft_doc = os.path.join(*ref.path.split("/"),
                                                     draft)
                            ref_type_toc_fd.write(f"{draft_doc}\n")
                            with open(os.path.join(base_dir, f"{draft_doc}.md"),
                                      "w") as draft_fd:
                                draft_fd.write(f"# {ref_type}: {ref_name}\n\n"
                                               f":::{{xml2rfc:version}} {draft}\n"
                                               f":ref_type: {ref_type}\n"
                                               f":ref_name: {ref_name}\n"
                                               f":ref_path: {ref.path}\n"
                                               f":::\n")
                        ref_type_toc_fd.write(":::\n")
                draft_toc_fd.write(":::\n")
        toc_fd.write(":::\n")
    return


def setup(app):
    """Sphinx extension for xml2rfc rendering."""

    app.add_config_value("xml2rfc_drafts", [], "env")
    app.add_config_value("xml2rfc_sources", [], "env")
    app.add_config_value("xml2rfc_autogen_versions", True, "env")
    app.add_config_value("xml2rfc_autogen_docs", True, "env")
    app.add_config_value("xml2rfc_output", "_xml2rfc", "env")

    app.add_domain(Xml2rfcDomain)

    app.connect("builder-inited", autogen)

    return {"version": "0.0.1",
            "parallel_read_safe": True,
            "parallel_write_safe": True}
