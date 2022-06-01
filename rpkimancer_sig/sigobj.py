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
"""RPKI Signed Checklist implementation - draft-ietf-sidrops-rpki-rsc."""

from __future__ import annotations

import copy
import ipaddress
import json
import logging
import os
import typing

from rpkimancer.algorithms import DIGEST_ALGORITHMS, SHA256
from rpkimancer.asn1 import Interface
from rpkimancer.asn1.mod import RpkiSignedChecklist_2022
from rpkimancer.resources import (AFI, ASIdOrRange, ASIdOrRangeInfo,
                                  AsResourcesInfo, IPAddressRange,
                                  IPNetwork, IPNetworkBits,
                                  IPRange, IPRangeBits, IpResourcesInfo,
                                  bitstring_to_net, net_to_bitstring)
from rpkimancer.sigobj.base import EncapsulatedContentType, SignedObject

from .eecert import UnpublishedEECertificate

log = logging.getLogger(__name__)

ConstrainedAsResourcesInfo = typing.Iterable[ASIdOrRangeInfo]

ConstrainedIPAddressFamilyInfo = typing.Union[IPNetwork, IPRange]
ConstrainedIpResourcesInfo = typing.Iterable[ConstrainedIPAddressFamilyInfo]


class ConstrainedASIdentifiers(Interface):
    """ASN.1 ConstrainedASIdentifiers type."""

    content_syntax = RpkiSignedChecklist_2022.ConstrainedASIdentifiers

    def __init__(self, as_resources: ConstrainedAsResourcesInfo) -> None:
        """Initialise instance from python data."""
        data = {"asnum": [ASIdOrRange(a).content_data for a in as_resources]}
        super().__init__(data)


class ConstrainedIPAddrBlocks(Interface):
    """ASN.1 ConstrainedIPAddrBlocks type."""

    content_syntax = RpkiSignedChecklist_2022.ConstrainedIPAddrBlocks

    def __init__(self, ip_resources: ConstrainedIpResourcesInfo) -> None:
        """Initialise instance from python data."""
        log.info(f"preparing data for {self}")
        net_data_type = typing.Tuple[str, IPNetworkBits]
        entry_type = typing.Tuple[int, net_data_type]

        def _net_entry(data: ConstrainedIPAddressFamilyInfo) -> entry_type:
            if isinstance(data, (ipaddress.IPv4Network,
                                 ipaddress.IPv6Network)):
                return data.version, ("addressPrefix", net_to_bitstring(data))
            elif isinstance(data[0], (ipaddress.IPv4Address,
                                      ipaddress.IPv6Address)):
                return data[0].version, ("addressRange",
                                         IPAddressRange(data).content_data)
            else:
                raise ValueError

        by_afi = {afi_data: [net_data
                             for net_version, net_data
                             in map(_net_entry, ip_resources)
                             if net_version == afi_version]
                  for (afi_version, afi_data) in AFI.items()}
        data = [{"addressFamily": afi, "addressesOrRanges": entries}
                for afi, entries in by_afi.items() if entries]
        super().__init__(data)


class SignedChecklistContentType(EncapsulatedContentType):
    """encapContentInfo for RPKI Signed Checklists."""

    asn1_definition = RpkiSignedChecklist_2022.ct_rpkiSignedChecklist
    file_ext = "sig"

    def __init__(self, *,
                 paths: typing.Iterable[str],
                 anon_data: typing.Optional[typing.Iterable[bytes]] = None,
                 version: int = 0,
                 as_resources: typing.Optional[ConstrainedAsResourcesInfo] = None,  # noqa: E501
                 ip_resources: typing.Optional[ConstrainedIpResourcesInfo] = None,  # noqa: E501
                 digest_algorithm: typing.Tuple[int, ...] = SHA256) -> None:
        """Initialise the encapContentInfo."""
        checklist = list()
        alg = DIGEST_ALGORITHMS[digest_algorithm]
        for path in paths:
            with open(path, "rb") as f:
                content = f.read()
            digest = alg(content).digest()
            checklist.append({"fileName": os.path.basename(path),
                              "hash": digest})
        if anon_data is not None:
            for item in anon_data:
                digest = alg(item).digest()
                checklist.append({"hash": digest})
        data: typing.Dict[str, typing.Any] = {"version": version,
                                              "digestAlgorithm": {"algorithm": digest_algorithm},  # noqa: E501
                                              "checkList": checklist,
                                              "resources": {}}
        if ip_resources is not None:
            data["resources"]["ipAddrBlocks"] = ConstrainedIPAddrBlocks(ip_resources).content_data  # noqa: E501
        if as_resources is not None:
            data["resources"]["asID"] = ConstrainedASIdentifiers(as_resources).content_data  # noqa: E501
        super().__init__(data)
        self._as_resources = as_resources
        self._ip_resources = ip_resources

    @property
    def as_resources(self) -> typing.Optional[AsResourcesInfo]:
        """Get the AS Number Resources covered by this Checklist."""
        return self._as_resources

    @property
    def ip_resources(self) -> typing.Optional[IpResourcesInfo]:
        """Get the IP Address Resources covered by this Checklist."""
        return self._ip_resources

    def to_json(self) -> str:
        """Serialize as JSON."""
        data = copy.deepcopy(self.content_data)
        afi_bytes_version_map = {v: k for k, v in AFI.items()}
        data["digestAlgorithm"]["algorithm"] = ".".join(str(i)
                                                        for i in self.content_data["digestAlgorithm"]["algorithm"])  # noqa: E501
        for i, entry in enumerate(self.content_data["checkList"]):
            data_entry = data["checkList"][i]
            data_entry["hash"] = entry["hash"].hex()
        for i, asnum in enumerate(self.content_data["resources"]["asID"]["asnum"]):  # noqa: E501
            data["resources"]["asID"]["asnum"][i] = {asnum[0]: asnum[1]}
        for i, addr_block in enumerate(self.content_data["resources"]["ipAddrBlocks"]):  # noqa: E501
            data_addr_block = data["resources"]["ipAddrBlocks"][i]
            version = afi_bytes_version_map[addr_block["addressFamily"]]
            data_addr_block["addressFamily"] = f"ipv{version}"
            for j, addr in enumerate(addr_block["addressesOrRanges"]):
                addr_info: typing.Union[str, typing.Dict[str, str]]
                if addr[0] == "addressPrefix":
                    network = bitstring_to_net(addr[1], version)
                    addr_info = str(network)
                elif addr[0] == "addressRange":
                    min_addr, max_addr = bitstring_to_addr_range((addr[1]["min"],  # noqa: E501
                                                                  addr[1]["max"]),  # noqa: E501
                                                                 version)
                    addr_info = {"min": str(min_addr), "max": str(max_addr)}
                else:
                    raise ValueError
                data_addr_block["addressesOrRanges"][j] = {addr[0]: addr_info}
        log.info(data)
        return json.dumps(data, indent=2)


class SignedChecklist(SignedObject[SignedChecklistContentType]):
    """CMS ASN.1 ContentInfo for RPKI Signed Checklists."""

    ee_cert_cls = UnpublishedEECertificate

    def publish(self, *,
                rsc_output_dir: typing.Optional[str] = None,
                **kwargs: typing.Any) -> None:
        """Optionally out-of-tree publication."""
        if rsc_output_dir is not None:
            os.makedirs(rsc_output_dir, exist_ok=True)
            with open(os.path.join(rsc_output_dir, self.file_name),
                      "wb") as f:
                f.write(self.to_der())
        else:
            super().publish(**kwargs)


# TODO: move into rpkimancer.resources
def bitstring_to_addr_range(bits: IPRangeBits, version: int) -> IPRange:
    """Convert a pair of ASN.1 BIT STRING representations to an IPRange."""
    len_map = {4: ipaddress.IPV4LENGTH, 6: ipaddress.IPV6LENGTH}
    cls_map = {4: ipaddress.IPv4Address, 6: ipaddress.IPv6Address}
    addr_len = len_map[version]
    addr_cls = cls_map[version]
    (low_bits, low_len), (high_bits, high_len) = bits
    low = addr_cls(low_bits << addr_len - low_len)
    high = addr_cls((high_bits + 1 << addr_len - high_len) - 1)
    return typing.cast(IPRange, (low, high))
