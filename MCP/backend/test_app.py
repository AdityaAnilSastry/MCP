"""
Verification and Integration Test Suite
Validates MCP Server, MCP Client, FastAPI Endpoints, and Error Handling.
"""

import os
import sys
import asyncio

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.mcp_client import mcp_client


async def run_tests():
    print("=" * 50)
    print("RUNNING FULL STACK MCP VERIFICATION SUITE")
    print("=" * 50)
    
    # 1. MCP Direct Tests
    print("\n[1] Testing MCP Server Tools via MCP Client...")
    tools = await mcp_client.list_tools()
    assert len(tools) == 2, f"Expected 2 tools, found {len(tools)}"
    tool_names = [t["name"] for t in tools]
    print(f"[PASS] Tool discovery: {tool_names}")
    
    time_res = await mcp_client.call_tool("get_current_time", {"timezone_name": "Asia/Kolkata"})
    assert "Current Time:" in time_res and "Asia/Kolkata" in time_res, f"Unexpected time output: {time_res}"
    print(f"[PASS] get_current_time output:\n  {time_res.splitlines()[0]}")
    
    calc_res = await mcp_client.call_tool("calculate", {"expression": "(100 * 25) + sqrt(625)"})
    assert "Result: 2525" in calc_res, f"Unexpected calc output: {calc_res}"
    print(f"[PASS] calculate output: {calc_res}")
    
    # 2. FastAPI Endpoints via ASGI
    print("\n[2] Testing FastAPI REST Endpoints...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # /api/health
        r_health = await client.get("/api/health")
        assert r_health.status_code == 200, f"Health failed: {r_health.text}"
        health_data = r_health.json()
        assert health_data["status"] == "healthy"
        assert health_data["mcp_status"] == "connected"
        print(f"[PASS] GET /api/health: {health_data['status']}, MCP: {health_data['mcp_status']}")
        
        # /api/tools
        r_tools = await client.get("/api/tools")
        assert r_tools.status_code == 200
        tools_data = r_tools.json()
        assert tools_data["count"] == 2
        print(f"[PASS] GET /api/tools: {tools_data['count']} tools found")
        
        # /api/chat - Time Query
        r_chat_time = await client.post("/api/chat", json={"message": "What is the current time in Tokyo?"})
        assert r_chat_time.status_code == 200
        chat_time_data = r_chat_time.json()
        assert chat_time_data["success"] is True
        assert len(chat_time_data["tools_used"]) > 0
        assert chat_time_data["tools_used"][0]["tool"] == "get_current_time"
        print("[PASS] POST /api/chat (Time query): MCP Tool executed successfully")
        
        # /api/chat - Math Query
        r_chat_math = await client.post("/api/chat", json={"message": "Calculate (256 * 48) + 12"})
        assert r_chat_math.status_code == 200
        chat_math_data = r_chat_math.json()
        assert chat_math_data["success"] is True
        assert len(chat_math_data["tools_used"]) > 0
        assert chat_math_data["tools_used"][0]["tool"] == "calculate"
        print("[PASS] POST /api/chat (Math query): MCP Tool executed successfully")
        
        # /api/chat - Empty Message Validation
        r_empty = await client.post("/api/chat", json={"message": "   "})
        assert r_empty.status_code in [400, 422]
        print(f"[PASS] POST /api/chat (Empty input validation): Status {r_empty.status_code}")

    print("\n" + "=" * 50)
    print("ALL VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(run_tests())
