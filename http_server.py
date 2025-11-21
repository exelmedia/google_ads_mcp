#!/usr/bin/env python3
"""HTTP server wrapper for Google Ads MCP server."""

import asyncio
import json
import os
from typing import Any, Dict
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Import tools from server module
import server

app = FastAPI(title="Google Ads MCP HTTP Server")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "server": "Google Ads MCP Server",
        "version": "1.0.0",
        "transport": "http"
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/sse")
async def sse_endpoint_get(request: Request):
    """SSE endpoint for MCP communication (GET for streaming)."""
    async def event_generator():
        try:
            # Send endpoint information
            endpoint_info = {
                "jsonrpc": "2.0",
                "method": "endpoint",
                "params": {
                    "capabilities": {
                        "tools": {}
                    },
                    "serverInfo": {
                        "name": "Google Ads MCP Server",
                        "version": "1.0.0"
                    }
                }
            }
            yield f"event: endpoint\n"
            yield f"data: {json.dumps(endpoint_info)}\n\n"
            
            # Keep connection alive
            while True:
                await asyncio.sleep(30)
                yield f": keepalive\n\n"
                
        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": str(e)
                }
            }
            yield f"event: error\n"
            yield f"data: {json.dumps(error_response)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.post("/sse")
async def sse_endpoint_post(request: Request):
    """SSE endpoint for MCP communication (POST for requests)."""
    async def event_generator():
        try:
            body = await request.json()
            result = await process_mcp_request(body)
            yield f"data: {json.dumps(result)}\n\n"
        except Exception as e:
            error_response = {
                "error": str(e),
                "type": type(e).__name__
            }
            yield f"data: {json.dumps(error_response)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.post("/message")
async def message_endpoint(request: Request):
    """REST endpoint for MCP messages."""
    try:
        body = await request.json()
        result = await process_mcp_request(body)
        return result
    except Exception as e:
        return {
            "error": str(e),
            "type": type(e).__name__
        }, 500


async def process_mcp_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Process an MCP request and return the result."""
    method = request.get("method")
    
    if method == "tools/list":
        return {
            "tools": [
                {
                    "name": "list_accessible_customers",
                    "description": "Returns ids of customers directly accessible by the user authenticating the call.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                },
                {
                    "name": "search",
                    "description": "Fetches data from the Google Ads API using the search method",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "customer_id": {"type": "string"},
                            "fields": {"type": "array", "items": {"type": "string"}},
                            "resource": {"type": "string"},
                            "conditions": {"type": "array", "items": {"type": "string"}},
                            "orderings": {"type": "array", "items": {"type": "string"}},
                            "limit": {"type": "integer"},
                            "query": {"type": "string"}
                        },
                        "required": ["customer_id"]
                    }
                }
            ]
        }
    
    elif method == "tools/call":
        params = request.get("params", {})
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        try:
            # Get raw functions from server module, not MCP-wrapped tools
            if tool_name == "list_accessible_customers":
                # Access the actual function, not the MCP tool wrapper
                tool_func = server.mcp._tool_manager._tools["list_accessible_customers"]
                result = tool_func.fn()
            elif tool_name == "search":
                tool_func = server.mcp._tool_manager._tools["search"]
                result = tool_func.fn(**arguments)
            else:
                return {
                    "error": f"Tool '{tool_name}' not found",
                    "isError": True
                }
            
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, indent=2)
                    }
                ]
            }
        except Exception as e:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error calling tool: {str(e)}"
                    }
                ],
                "isError": True
            }
    
    elif method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "Google Ads MCP Server",
                "version": "1.0.0"
            }
        }
    
    else:
        return {
            "error": f"Unknown method: {method}",
            "isError": True
        }


def run_http_server(host: str = "0.0.0.0", port: int = None):
    """Run the HTTP server."""
    if port is None:
        port = int(os.environ.get("PORT", 3030))
    
    print(f"🚀 Google Ads MCP HTTP Server starting on {host}:{port}")
    print(f"📊 Available tools: search, list_accessible_customers")
    print(f"🔑 Required env vars: GOOGLE_ADS_DEVELOPER_TOKEN, GOOGLE_PROJECT_ID")
    
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_http_server()
