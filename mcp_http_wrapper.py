#!/usr/bin/env python3
"""Wrapper to connect MCP stdio to HTTP server."""

import sys
import json
import httpx
import asyncio
from asyncio import StreamReader

MCP_SERVER_URL = "https://g-ads-mcp-u53948.vm.elestio.app"


async def read_stdin():
    """Read from stdin asynchronously."""
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    return reader


async def main():
    """Main wrapper loop."""
    client = httpx.AsyncClient(timeout=30.0)
    
    try:
        reader = await read_stdin()
        
        while True:
            try:
                line = await reader.readline()
                if not line:
                    break
                    
                line_str = line.decode('utf-8').strip()
                if not line_str:
                    continue
                
                request = json.loads(line_str)
                
                # Forward to HTTP server
                response = await client.post(
                    f"{MCP_SERVER_URL}/message",
                    json=request
                )
                
                # Write response to stdout with proper JSON-RPC format
                server_response = response.json()
                
                # Format as proper JSON-RPC 2.0 response
                if "jsonrpc" in server_response:
                    # Already in JSON-RPC format
                    result = server_response
                elif "error" in server_response or "isError" in server_response:
                    # Error response
                    result = {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "error": server_response.get("error", server_response)
                    }
                else:
                    # Wrap in result
                    result = {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "result": server_response
                    }
                
                sys.stdout.write(json.dumps(result) + "\n")
                sys.stdout.flush()
                
            except json.JSONDecodeError:
                continue
            except Exception as e:
                error = {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32603,
                        "message": str(e)
                    },
                    "id": request.get("id") if 'request' in locals() else None
                }
                sys.stdout.write(json.dumps(error) + "\n")
                sys.stdout.flush()
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
