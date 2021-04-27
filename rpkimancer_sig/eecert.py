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

import logging

from rpkimancer.cert import EECertificate

log = logging.getLogger(__name__)


class UnpublishedEECertificate(EECertificate):
    """RPKI Unpublished EE Certificate."""

    sia = None
    mft_entry = None
