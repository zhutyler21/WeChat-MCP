# Accessibility traversal failures

## Recursion is different from a missing control

A traceback containing repeated `dfs(child, predicate)` or collector `walk(...)`
frames followed by `RecursionError: maximum recursion depth exceeded` indicates a
traversal failure. It does **not**, by itself, establish that Accessibility
permission was denied or that a particular WeChat/macOS version is unsupported.

AX references are not guaranteed to form an acyclic Python object tree. A native
AX element may refer to itself, or the same native element may appear through
separate Python wrappers. Diagnose native identity with `CFEqual`, not `is`.
Avoid raising Python's recursion limit as a fix.

`dfs` now performs iterative depth-first preorder traversal, deduplicating native
objects with `CFHash` and `CFEqual` (including hash-collision checks). The session
and search-result collectors reuse the same traversal. Existing first-match
behavior, session-name mapping, title/value fallback, and stable Y sorting are
preserved; repeated references to the same native element are visited once.

The default limits are 10,000 distinct native elements, 20,000 references
(including the root and repeated references), and 10 seconds per traversal.
An incomplete search raises `AXTraversalLimitError` rather than returning `None`
or partially collected results. Limits can be passed as keyword arguments to
`dfs`; they are not new MCP tool arguments. Elapsed-time checks run between
operations and cannot interrupt an in-flight OS call or a blocking predicate.

## What to check next

If recursion is resolved but a search field or message list is still missing:

1. Check the actual process's Accessibility permission. Capture-based readers
   also need Screen Recording permission; these are separate checks.
2. Confirm WeChat is running and signed in. Record whether the desktop is locked
   or the process is in a different GUI session. Compare with a normal, manually
   unlocked session when possible; do not disable OS protections or automate login.
3. Record the actual WeChat/macOS version, UI language, and the missing role or
   identifier. Selector/window-layout compatibility is a separate issue from
   traversal safety.
4. Separate MCP connectivity from business success. The current server can
   return a list containing an `error` dictionary; inspect the tool payload, not
   only HTTP status, initialization, or `isError`. Never turn a failed read into
   a "no new messages" summary.

A locked session and an AX cycle can coexist without proving that the lock caused
the cycle. Passing traversal tests does not prove locked-screen support or
successful real chat retrieval. This change does not alter selectors, permission
handling, session policy, MCP error format, or message-sending behavior.

## Run the offline regressions

On macOS with Python 3.12+ and the project dependencies installed:

```bash
uv run --with pytest pytest tests/test_accessibility_traversal.py -q
```

The tests fake AX attribute reads and never activate WeChat, access a real chat,
or post input events. One test constructs AX references and exercises real
CoreFoundation equality while still mocking **all** attribute reads. Coverage
includes cycles, native aliases, hash collisions, deep trees, preorder, early
return, traversal budgets, collector behavior, and existing imported bindings.

When reporting an issue, share a redacted traceback and control metadata rather
than message text, contact/group names, screenshots, credentials, or host addresses.
