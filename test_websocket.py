#!/usr/bin/env python3
"""
WebSocket Test Client for F1 Live Data
Tests the WebSocket streaming functionality
"""

import asyncio
import websockets
import json
import sys

async def test_websocket():
    """Test WebSocket connection to live race updates"""
    uri = "ws://localhost:8000/ws/live/2024_Bahrain"
    
    try:
        print(f"🔌 Connecting to {uri}...")
        async with websockets.connect(uri) as websocket:
            print("✅ Connected to WebSocket!")
            
            # Listen for messages
            async for message in websocket:
                try:
                    data = json.loads(message)
                    print(f"📡 Received: {data['type']}")
                    
                    if data['type'] == 'initial_state':
                        print(f"🏁 Initial state: {data['data']['session_status']}")
                        print(f"🏎️  Leader: {data['data']['leader']}")
                        print(f"📊 Current lap: {data['data']['current_lap']}")
                    
                    elif data['type'] == 'update':
                        print(f"🔄 Update: {data['data'].get('type', 'unknown')}")
                        
                except json.JSONDecodeError:
                    print(f"❌ Invalid JSON: {message}")
                except Exception as e:
                    print(f"❌ Error processing message: {e}")
                    
    except websockets.exceptions.ConnectionClosed:
        print("❌ Connection closed. Is the API server running?")
    except Exception as e:
        print(f"❌ WebSocket error: {e}")

if __name__ == "__main__":
    print("🚀 Starting WebSocket test client...")
    asyncio.run(test_websocket())
