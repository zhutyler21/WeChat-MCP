"""Offline AX traversal regressions; no UI activation or message operations."""
from itertools import repeat

import pytest

from wechat_mcp import wechat_accessibility as ax


class Node:
    def __init__(self, key, children=(), *, bucket=None, **attrs):
        self.key = key
        self.bucket = key if bucket is None else bucket
        self.children = children
        self.attrs = attrs


@pytest.fixture
def fake_ax(monkeypatch):
    def get(node, attribute):
        defaults = {
            ax.kAXRoleAttribute: "AXGroup",
            ax.kAXTitleAttribute: node.key,
            ax.kAXIdentifierAttribute: node.key,
            ax.kAXChildrenAttribute: node.children,
        }
        return node.attrs.get(attribute, defaults.get(attribute))

    monkeypatch.setattr(ax, "ax_get", get)
    # Separate Python wrappers can identify the same native AX object. Hash
    # collisions alone must NOT merge distinct native objects.
    monkeypatch.setattr(ax, "CFHash", lambda node: hash(node.bucket), raising=False)
    monkeypatch.setattr(ax, "CFEqual", lambda a, b: a.key == b.key, raising=False)
    return get


def visit(target, seen):
    def predicate(node, role, title, identifier):
        seen.append(node.key)
        return node.key == target
    return predicate


def test_none_root(fake_ax):
    assert ax.dfs(None, lambda *_: True) is None


def test_self_cycle_keeps_later_sibling(fake_ax):
    root, target = Node("root"), Node("target")
    root.children = [root, target]
    seen = []
    assert ax.dfs(root, visit("target", seen)) is target
    assert seen == ["root", "target"]


def test_two_node_cycle_returns_none(fake_ax):
    a, b = Node("a"), Node("b")
    a.children, b.children = [b], [a]
    seen = []
    assert ax.dfs(a, visit("absent", seen)) is None
    assert seen == ["a", "b"]


def test_native_alias_is_not_python_identity(fake_ax):
    root, alias, target = Node("root"), Node("root"), Node("target")
    assert root is not alias
    root.children, alias.children = [alias, target], [alias]
    seen = []
    assert ax.dfs(root, visit("target", seen)) is target
    assert seen == ["root", "target"]


def test_hash_collision_preserves_distinct_nodes(fake_ax):
    target = Node("target", bucket=0)
    root = Node("root", [Node("other", bucket=0), target], bucket=0)
    seen = []
    assert ax.dfs(root, visit("target", seen)) is target
    assert seen == ["root", "other", "target"]


def test_shared_nodes_preserve_depth_first_preorder(fake_ax):
    shared = Node("shared")
    root = Node("root", [Node("a", [shared]), Node("b", [shared]), Node("target")])
    seen = []
    assert ax.dfs(root, visit("target", seen)).key == "target"
    assert seen == ["root", "a", "shared", "b", "target"]


def test_deep_chain_does_not_use_python_recursion(fake_ax):
    target = root = Node("target")
    for index in range(2500):
        root = Node(str(index), [root])
    assert ax.dfs(root, lambda node, *_: node is target) is target


def test_first_match_does_not_enumerate_children(fake_ax):
    def forbidden():
        raise AssertionError("children must not be consumed after a match")
        yield
    root = Node("root", forbidden())
    assert ax.dfs(root, lambda *_: True) is root


def test_missing_children_returns_none(fake_ax):
    assert ax.dfs(Node("root", None), lambda *_: False) is None


def test_node_limit_is_explicit_not_false_absence(fake_ax):
    with pytest.raises(RuntimeError, match="node limit"):
        ax.dfs(Node("root", [Node("child")]), lambda *_: False, max_nodes=1)


def test_edge_limit_bounds_infinite_duplicate_children(fake_ax):
    root = Node("root")
    root.children = repeat(root)
    with pytest.raises(RuntimeError, match="edge limit"):
        ax.dfs(root, lambda *_: False, max_edges=8)


def test_elapsed_time_budget(fake_ax, monkeypatch):
    clock = iter([0.0, 2.0])
    monkeypatch.setattr(ax.time, "monotonic", lambda: next(clock))
    with pytest.raises(RuntimeError, match="time limit"):
        ax.dfs(Node("root"), lambda *_: False, max_seconds=1.0)


@pytest.mark.parametrize("limits", [{"max_nodes": 0}, {"max_edges": 0}, {"max_seconds": -1}])
def test_invalid_limits(fake_ax, limits):
    with pytest.raises(ValueError):
        ax.dfs(Node("root"), lambda *_: False, **limits)


def test_collect_sessions_uses_cycle_safe_walk_and_preserves_names(fake_ax):
    root = Node("root")
    one = Node("one", AXRole="AXStaticText", AXIdentifier="session_item_Test Group")
    ignored = Node("ignored", AXRole="AXStaticText", AXIdentifier="session_item_")
    root.children = [root, one, ignored]
    assert ax.collect_chat_elements(root) == {"Test Group": one}
    assert ax.find_chat_element_by_name(root, "test group") is one


def test_search_collection_is_cycle_safe_and_stably_sorted(fake_ax, monkeypatch):
    root = Node("root")
    one = Node("one", AXRole="AXStaticText", AXTitle="  First  ", AXPosition=(0, 20))
    two = Node("two", AXRole="AXStaticText", AXTitle="", AXValue="Fallback", AXPosition=(0, 10))
    three = Node("three", AXRole="AXStaticText", AXTitle="Tie", AXPosition=(0, 20))
    root.children = [root, one, two, three, one]
    monkeypatch.setattr(ax, "axvalue_to_point", lambda p: p)
    entries = ax._collect_search_entries(root)
    assert [(entry.text, entry.y) for entry in entries] == [("Fallback", 10), ("First", 20), ("Tie", 20)]


@pytest.mark.parametrize("collector", ["collect_chat_elements", "_collect_search_entries"])
def test_collectors_propagate_limits_instead_of_partial_results(fake_ax, monkeypatch, collector):
    original = ax.dfs
    monkeypatch.setattr(ax, "dfs", lambda root, predicate: original(root, predicate, max_nodes=1))
    with pytest.raises(RuntimeError, match="node limit"):
        getattr(ax, collector)(Node("root", [Node("child")]))


def test_existing_imported_dfs_binding_uses_fixed_implementation():
    from wechat_mcp import fetch_messages_by_chat_utils as fetch
    assert fetch.dfs is ax.dfs


def test_real_corefoundation_identity_without_reading_any_ui(monkeypatch):
    import os
    from CoreFoundation import CFEqual, CFHash
    from ApplicationServices import AXUIElementCreateApplication

    root = AXUIElementCreateApplication(os.getpid())
    alias = AXUIElementCreateApplication(os.getpid())
    target = AXUIElementCreateApplication(os.getpid() + 1)
    assert CFEqual(root, alias)
    assert CFHash(root) == CFHash(alias)
    # AX reads are still mocked. Only reference construction and native equality
    # use the OS; no real window/chat is accessed, activated, or modified.
    def get(node, attribute):
        if attribute == ax.kAXChildrenAttribute:
            return [alias, target] if CFEqual(node, root) else []
        return None
    monkeypatch.setattr(ax, "ax_get", get)
    assert ax.dfs(root, lambda node, *_: CFEqual(node, target)) is target
