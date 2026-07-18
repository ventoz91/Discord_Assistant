import types

import pytest

import AIfunc.responses as responses


def _msg(content=None, tool_calls=None):
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=types.SimpleNamespace(
            content=content, tool_calls=tool_calls or []
        ))],
        usage=None,
    )


def _call(cid, name, args='{"query": "x"}'):
    return types.SimpleNamespace(id=cid, function=types.SimpleNamespace(name=name, arguments=args))


SEARCH_TOOL = {"type": "function", "function": {"name": "google_search", "parameters": {}}}
IMAGE_TOOL = {"type": "function", "function": {"name": "generate_image", "parameters": {}}}
TOOLS = [SEARCH_TOOL, IMAGE_TOOL]


@pytest.fixture
def fake_model(monkeypatch):
    """Queue of scripted responses; records the kwargs of every call."""
    state = types.SimpleNamespace(queue=[], calls=[])

    async def fake_completion(**kwargs):
        state.calls.append(kwargs)
        return state.queue.pop(0)

    monkeypatch.setattr(responses, "async_chat_completion", fake_completion)
    return state


@pytest.fixture
def search_executor():
    state = types.SimpleNamespace(queries=[])

    async def execute(args):
        state.queries.append(args.get("query"))
        return f"result for {args.get('query')}"

    state.execute = execute
    return state


async def test_chained_searches_resolve_across_turns(fake_model, search_executor):
    fake_model.queue = [
        _msg(tool_calls=[_call("1", "google_search", '{"query": "first"}')]),
        _msg(tool_calls=[_call("2", "google_search", '{"query": "second"}')]),
        _msg(content="final answer"),
    ]
    content, tool_calls = await responses.generate_gpt_response(
        [{"role": "user", "content": "hi"}], "personality", tools=TOOLS,
        auto_resolve={"google_search": search_executor.execute},
    )
    assert content == "final answer"
    assert tool_calls == []
    assert search_executor.queries == ["first", "second"]
    assert len(fake_model.calls) == 3
    # Tool results were fed back into the conversation
    roles = [m["role"] for m in fake_model.calls[-1]["messages"]]
    assert roles.count("tool") == 2


async def test_non_auto_tool_calls_returned_to_caller(fake_model, search_executor):
    fake_model.queue = [
        _msg(tool_calls=[
            _call("1", "google_search", '{"query": "q"}'),
            _call("2", "generate_image", '{"prompt": "a crab"}'),
        ]),
        _msg(content="here you go"),
    ]
    content, tool_calls = await responses.generate_gpt_response(
        [{"role": "user", "content": "hi"}], "p", tools=TOOLS,
        auto_resolve={"google_search": search_executor.execute},
    )
    assert content == "here you go"
    assert [tc.function.name for tc in tool_calls] == ["generate_image"]


async def test_turn_cap_withholds_auto_tools_on_last_round(fake_model, search_executor, monkeypatch):
    monkeypatch.setenv("MAX_AGENT_TURNS", "2")
    fake_model.queue = [
        _msg(tool_calls=[_call("1", "google_search")]),
        _msg(tool_calls=[_call("2", "google_search")]),
        _msg(content="forced answer"),
    ]
    content, tool_calls = await responses.generate_gpt_response(
        [{"role": "user", "content": "hi"}], "p", tools=TOOLS,
        auto_resolve={"google_search": search_executor.execute},
    )
    assert content == "forced answer"
    # Final (2nd follow-up) call must not offer google_search anymore
    last_tools = [t["function"]["name"] for t in fake_model.calls[-1].get("tools", [])]
    assert "google_search" not in last_tools
    # But the first follow-up still offered it (that's the chaining fix)
    mid_tools = [t["function"]["name"] for t in fake_model.calls[1].get("tools", [])]
    assert "google_search" in mid_tools


async def test_executor_failure_fed_back_as_tool_error(fake_model):
    async def broken(args):
        raise RuntimeError("tavily down")

    fake_model.queue = [
        _msg(tool_calls=[_call("1", "google_search")]),
        _msg(content="answered without search"),
    ]
    content, _ = await responses.generate_gpt_response(
        [{"role": "user", "content": "hi"}], "p", tools=TOOLS,
        auto_resolve={"google_search": broken},
    )
    assert content == "answered without search"
    tool_msgs = [m for m in fake_model.calls[-1]["messages"] if m["role"] == "tool"]
    assert "Tool error" in tool_msgs[0]["content"]


async def test_no_tools_plain_response(fake_model):
    fake_model.queue = [_msg(content="plain")]
    result = await responses.generate_gpt_response([{"role": "user", "content": "hi"}], "p")
    assert result == "plain"
