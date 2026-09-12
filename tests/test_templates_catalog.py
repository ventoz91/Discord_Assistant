import re

import yaml

from webpanel.routes_deploy import _NAME_RE, _PORT_LINE_RE
from webpanel.templates_catalog import TEMPLATES, render_compose_yaml


def test_curated_templates_have_required_shape():
    for key, tmpl in TEMPLATES.items():
        assert "label" in tmpl and "description" in tmpl and "default_volume_path" in tmpl
        if not tmpl.get("custom"):
            assert tmpl["image"], f"{key} should have a fixed image"


def test_render_compose_yaml_round_trips():
    yaml_text = render_compose_yaml(
        name="terraria-1",
        image="ryshe/terraria:latest",
        ports=[{"host_port": 7777, "container_port": 7777, "protocol": "tcp"}],
        env={"WORLD": "myworld"},
        volume_path="/data",
    )
    parsed = yaml.safe_load(yaml_text)
    service = parsed["services"]["terraria-1"]
    assert service["image"] == "ryshe/terraria:latest"
    assert service["container_name"] == "terraria-1"
    assert service["ports"] == ["7777:7777/tcp"]
    assert service["environment"] == {"WORLD": "myworld"}
    assert service["volumes"] == ["./data:/data"]


def test_render_compose_yaml_omits_environment_when_empty():
    yaml_text = render_compose_yaml(
        name="svc", image="img", ports=[{"host_port": 1, "container_port": 1, "protocol": "udp"}],
        env={}, volume_path="/data",
    )
    parsed = yaml.safe_load(yaml_text)
    assert "environment" not in parsed["services"]["svc"]


def test_instance_name_regex():
    assert _NAME_RE.match("terraria-1")
    assert _NAME_RE.match("ab")
    assert not _NAME_RE.match("1terraria")   # must start with a letter
    assert not _NAME_RE.match("Terraria")     # must be lowercase
    assert not _NAME_RE.match("a")            # too short
    assert not _NAME_RE.match("has_underscore")


def test_port_line_regex():
    m = _PORT_LINE_RE.match("27015:27015/udp")
    assert m and m.groups() == ("27015", "27015", "udp")
    assert _PORT_LINE_RE.match("7777:7778/TCP")  # case-insensitive
    assert not _PORT_LINE_RE.match("27015/udp")
    assert not _PORT_LINE_RE.match("27015:27015:extra/udp")
