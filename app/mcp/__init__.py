"""Headless Model Context Protocol (MCP) server for RimSort.

The package is import-cheap on purpose: ``app.mcp.entrypoint`` is the only
module that pulls in the metadata stack, and it is imported lazily from
``app.__main__`` when ``--mcp`` is passed.
"""
