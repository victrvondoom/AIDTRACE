"""AIDTRACE agent: Claude reasoning over the caller's own graph, through a fixed read-only tool registry.

The graph engines answer first and always. The model is consulted only when a question needs interpretation,
only when the switch is on and a key is configured, and only through the tools in `tools.py`.
"""
