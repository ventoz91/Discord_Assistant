from gamefunc.compose_server import DockerComposeGameServer


def test_ssh_target_with_user():
    c = DockerComposeGameServer(host="1.2.3.4", user="admin", compose_dir="/home/data", service_name="svc")
    assert c.ssh_target() == "admin@1.2.3.4"


def test_ssh_target_without_user():
    c = DockerComposeGameServer(host="1.2.3.4", user="", compose_dir="/home/data", service_name="svc")
    assert c.ssh_target() == "1.2.3.4"


def test_container_name_defaults_to_service_name():
    c = DockerComposeGameServer(host="h", user="", compose_dir="/d", service_name="palworld")
    assert c.container_name == "palworld"


def test_container_name_can_differ():
    c = DockerComposeGameServer(host="h", user="", compose_dir="/d", service_name="palworld",
                                 container_name="palworld-server")
    assert c.container_name == "palworld-server"


def test_callables_are_resolved_live():
    """host/user/compose_dir may be callables so fixed servers re-read .env on
    every call instead of freezing values at construction (matches the rest of
    the project's hot-reload convention)."""
    state = {"host": "first.example"}
    c = DockerComposeGameServer(
        host=lambda: state["host"], user="admin", compose_dir="/home/data", service_name="svc",
    )
    assert c.ssh_target() == "admin@first.example"
    state["host"] = "second.example"
    assert c.ssh_target() == "admin@second.example"
