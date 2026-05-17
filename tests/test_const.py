"""Tests for MQTT topic constants added in PR #18."""
from custom_components.hafele_local_mqtt.const import TOPIC_SET_GROUP_CTL


def test_group_ctl_topic_template():
    """Group CTL topic follows gateway prefix and group name."""
    topic = TOPIC_SET_GROUP_CTL.format(prefix="Mesh", group_name="Living Room")
    assert topic == "Mesh/groups/Living Room/ctl"
