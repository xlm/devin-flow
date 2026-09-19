import os

import pytest

from devin_flow.devin import get_devin_client

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("DEVIN_API_TOKEN") or not os.environ.get("DEVIN_ORG_ID"),
        reason="DEVIN_API_TOKEN or DEVIN_ORG_ID is not set",
    ),
]


def test_live_list_sessions() -> None:
    get_devin_client().list_sessions(limit=1)


def test_live_list_playbooks() -> None:
    get_devin_client().list_playbooks()
