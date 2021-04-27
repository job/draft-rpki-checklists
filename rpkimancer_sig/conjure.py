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
"""rpkincant conjure plugins for RPKI Signed Checklists."""

from __future__ import annotations

import glob
import ipaddress
import logging
import os
import typing

from rpkimancer.cli import Args
from rpkimancer.cli.conjure import (ConjurePlugin,
                                    DEFAULT_CA_AS_RESOURCES,
                                    DEFAULT_CA_IP_RESOURCES,
                                    META_AS, META_IP, META_PATH,
                                    PluginReturn)

if typing.TYPE_CHECKING:
    from rpkimancer.cert import CertificateAuthority

log = logging.getLogger(__name__)

RSC_SUB_DIR = "sigs"


class ConjureChecklist(ConjurePlugin):
    """rpkincant conjure plugin for RPKI Signed Checklists."""

    def init_parser(self) -> None:
        """Set up command line argument parser."""
        default_paths = [p for p in glob.glob(os.path.join(os.path.dirname(__file__),  # noqa: E501
                                                           "**", "*.asn"),
                                              recursive=True)
                         if os.path.isfile(p)]
        self.parser.add_argument("--rsc-paths",
                                 nargs="+", default=default_paths,
                                 metavar=META_PATH,
                                 help="Files to include in the RSC object "  # noqa: E501
                                      "(default: %(default)s)")
        self.parser.add_argument("--rsc-as-resources",
                                 nargs="+", type=int,
                                 default=DEFAULT_CA_AS_RESOURCES,
                                 metavar=META_AS,
                                 help="ASN(s) to include in the RSC object "
                                      "(default: %(default)s)")
        self.parser.add_argument("--rsc-ip-resources",
                                 nargs="+", type=ipaddress.ip_network,
                                 default=DEFAULT_CA_IP_RESOURCES,
                                 metavar=META_IP,
                                 help="IP resources to include in the RSC object "  # noqa: E501
                                      "(default: %(default)s)")

    def run(self,
            parsed_args: Args,
            ca: CertificateAuthority,
            *args: typing.Any,
            **kwargs: typing.Any) -> PluginReturn:
        """Run with the given arguments."""
        # create RSC object
        from .sigobj import SignedChecklist
        log.info("creating signed checklist object")
        rsc_output_dir = os.path.join(parsed_args.output_dir, RSC_SUB_DIR)
        SignedChecklist(issuer=ca,
                        paths=parsed_args.rsc_paths,
                        as_resources=parsed_args.rsc_as_resources,
                        ip_resources=parsed_args.rsc_ip_resources)
        return {"rsc_output_dir": rsc_output_dir}
