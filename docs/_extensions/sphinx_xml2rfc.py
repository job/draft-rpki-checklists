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

import docutils
import os
import subprocess
import tempfile

import git

from sphinx.util import logging

logger = logging.getLogger(__name__)

HTML_OUTPUT_DIR = "_xml2rfc"


class DraftsIndex(docutils.nodes.General, docutils.nodes.Element):
    pass


class DraftsIndexDirective(docutils.parsers.rst.Directive):

    def run(self):
        return [DraftsIndex("")]


def gen_rfc_html(app):
    """Generate HTML output from XML sources at every git ref."""

    app.env.xml2rfc_drafts = []
    if not app.config.xml2rfc_drafts:
        return

    app.config.html_extra_path.append(HTML_OUTPUT_DIR)
    base_dir = os.path.join(app.confdir, HTML_OUTPUT_DIR,
                            app.config.xml2rfc_output)

    proc = subprocess.run(("xml2rfc", "--version"),
                          capture_output=True, check=True)
    xml2rfc_version = proc.stdout.decode().strip()
    logger.info(f"sphinx-xml2rfc: using {xml2rfc_version}")

    repo = git.Repo(path=os.path.dirname(__file__),
                    search_parent_directories=True)
    file_names = [f"{draft}.xml" for draft in app.config.xml2rfc_drafts]
    file_names += app.config.xml2rfc_sources

    for ref in repo.refs:
        output_dir = os.path.join(base_dir, *ref.path.split("/"))
        os.makedirs(output_dir, exist_ok=True)
        logger.debug(f"{output_dir=}")
        with tempfile.TemporaryDirectory() as tmpdir:
            logger.debug(f"{ref.path=}")
            for blob in ref.commit.tree.blobs:
                if blob.name not in file_names:
                    continue
                logger.debug(f"{blob.name=}")
                logger.debug(f"{blob.hexsha=}")
                with open(os.path.join(tmpdir, blob.name), "wb") as f:
                    blob.stream_data(f)
            for draft in app.config.xml2rfc_drafts:
                logger.info(f"generating html for {draft} at {ref.path}")
                cmd = ("xml2rfc", f"{draft}.xml",
                       "--html",
                       "--path", output_dir)
                try:
                    proc = subprocess.run(cmd, check=True, capture_output=True)
                except subprocess.CalledProcessError as e:
                    logger.warning(e.stderr.decode())
                logger.debug(proc.stdout.decode())
                app.env.xml2rfc_drafts.append((draft, ref.path))
    logger.debug(f"{app.env.xml2rfc_drafts=}")


def build_index(app, doctree, fromdocname):
    for node in doctree.traverse(DraftsIndex):
        logger.debug(f"{node=}")
        content = []
        for draft, path in app.env.xml2rfc_drafts:
            logger.debug(f"{draft=}, {path=}")
            p = docutils.nodes.paragraph()
            ref = docutils.nodes.reference(path, path)
            ref["refdocname"] = draft
            ref["refuri"] = f"/{app.config.xml2rfc_output}/{path}/{draft}.html"
            p += ref
            content.append(p)
        node.replace_self(content)


def setup(app):
    """Sphinx extension for xml2rfc rendering."""

    app.add_config_value("xml2rfc_drafts", [], "env")
    app.add_config_value("xml2rfc_sources", [], "env")
    app.add_config_value("xml2rfc_output", None, "env")

    app.add_node(DraftsIndex)

    app.add_directive("drafts-index", DraftsIndexDirective)

    app.connect("builder-inited", gen_rfc_html)
    app.connect("doctree-resolved", build_index)

    return {"version": "0.0.1",
            "parallel_read_safe": True,
            "parallel_write_safe": True}
