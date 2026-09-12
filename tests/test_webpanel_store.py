import pytest

import webpanel.store as store


@pytest.fixture(autouse=True)
def temp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_STORE_PATH", str(tmp_path / "deployed_servers.json"))


def test_empty_store_returns_empty_list():
    assert store.list_instances() == []
    assert store.get_instance("nope") is None


def test_add_and_get_instance():
    entry = store.add_instance(
        name="terraria-1", template="terraria", host="10.13.37.102", user="admin",
        compose_dir="/home/data/gameservers/deployed/terraria-1",
        ports=[{"host_port": 7777, "container_port": 7777, "protocol": "tcp"}],
        image="ryshe/terraria:latest",
    )
    assert entry["name"] == "terraria-1"
    fetched = store.get_instance("terraria-1")
    assert fetched == entry
    assert [i["name"] for i in store.list_instances()] == ["terraria-1"]


def test_duplicate_name_rejected():
    store.add_instance(name="dup", template="terraria", host="h", user="u",
                        compose_dir="/d", ports=[], image="img")
    with pytest.raises(ValueError):
        store.add_instance(name="dup", template="terraria", host="h", user="u",
                            compose_dir="/d", ports=[], image="img")


def test_remove_instance():
    store.add_instance(name="gone", template="terraria", host="h", user="u",
                        compose_dir="/d", ports=[], image="img")
    removed = store.remove_instance("gone")
    assert removed["name"] == "gone"
    assert store.get_instance("gone") is None
    assert store.remove_instance("gone") is None
