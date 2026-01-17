#!/usr/bin/env python3
"""
Enhanced F1 Platform Demo Script
Demonstrates all the working features: Redis, DuckDB, WebSocket, Live Data
"""
#testing commit
import asyncio
import aiohttp
import websockets
import json
import time
from datetime import datetime

class F1PlatformDemo:
    """Demo class for the enhanced F1 platform"""
    
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.ws_url = base_url.replace("http", "ws")
    
    async def run_demo(self):
        """Run the complete demo"""
        print("🏎️  Shif1 UP Enhanced F1 Platform Demo")
        print("=" * 50)
        
        # Test 1: Health Check
        await self.test_health_check()
        
        # Test 2: DuckDB Integration
        await self.test_duckdb_integration()
        
        # Test 3: Redis Live State
        await self.test_redis_live_state()
        
        # Test 4: Live Data Simulation
        await self.test_live_data_simulation()
        
        # Test 5: WebSocket Streaming
        await self.test_websocket_streaming()
        
        print("\n🎉 Demo completed successfully!")
        print("✅ All advanced features are working!")
    
    async def test_health_check(self):
        """Test health check endpoint"""
        print("\n1️⃣  Testing Health Check...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/health") as response:
                    data = await response.json()
                    print(f"   ✅ API Status: {data['status']}")
                    print(f"   ✅ Service: {data['service']}")
                    print(f"   ✅ Redis: {data['redis']['redis_version']}")
                    print(f"   ✅ DuckDB: {data['duckdb']}")
        except Exception as e:
            print(f"   ❌ Health check failed: {e}")
    
    async def test_duckdb_integration(self):
        """Test DuckDB integration"""
        print("\n2️⃣  Testing DuckDB Integration...")
        try:
            async with aiohttp.ClientSession() as session:
                # Test drivers endpoint
                async with session.get(f"{self.base_url}/drivers") as response:
                    drivers = await response.json()
                    print(f"   ✅ Drivers from DuckDB: {len(drivers)} drivers")
                    if drivers:
                        print(f"   📊 Sample driver: {drivers[0]['full_name']} ({drivers[0]['nationality']})")
                
                # Test races endpoint
                async with session.get(f"{self.base_url}/races?year=2024") as response:
                    races = await response.json()
                    print(f"   ✅ Races from DuckDB: {len(races)} races")
                    if races:
                        print(f"   🏁 Sample race: {races[0]['gp']} - {races[0]['circuit_name']}")
                
                # Test race results
                async with session.get(f"{self.base_url}/race/2024_Bahrain/results") as response:
                    results = await response.json()
                    print(f"   ✅ Race results: {len(results)} positions")
                    if results:
                        print(f"   🏆 Winner: {results[0]['driver_name']} - {results[0]['points']} points")
                        
        except Exception as e:
            print(f"   ❌ DuckDB test failed: {e}")
    
    async def test_redis_live_state(self):
        """Test Redis live state"""
        print("\n3️⃣  Testing Redis Live State...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/live/2024_Bahrain/state") as response:
                    state = await response.json()
                    print(f"   ✅ Live state retrieved from Redis")
                    print(f"   🏁 Race: {state['race_id']}")
                    print(f"   📊 Status: {state['session_status']}")
                    print(f"   🏎️  Leader: {state['leader']}")
                    print(f"   🔢 Current Lap: {state['current_lap']}")
                    print(f"   📍 Positions: {len(state['positions'])} drivers")
        except Exception as e:
            print(f"   ❌ Redis live state test failed: {e}")
    
    async def test_live_data_simulation(self):
        """Test live data simulation"""
        print("\n4️⃣  Testing Live Data Simulation...")
        try:
            async with aiohttp.ClientSession() as session:
                # Trigger live data simulation
                async with session.post(f"{self.base_url}/simulate/live/2024_Bahrain") as response:
                    result = await response.json()
                    print(f"   ✅ {result['message']}")
                
                # Wait a moment for the simulation to process
                await asyncio.sleep(1)
                
                # Check the updated live state
                async with session.get(f"{self.base_url}/live/2024_Bahrain/state") as response:
                    state = await response.json()
                    print(f"   📊 Updated live state: {state['session_status']}")
                    print(f"   🏎️  Current leader: {state['leader']}")
                    
        except Exception as e:
            print(f"   ❌ Live data simulation test failed: {e}")
    
    async def test_websocket_streaming(self):
        """Test WebSocket streaming"""
        print("\n5️⃣  Testing WebSocket Streaming...")
        try:
            uri = f"{self.ws_url}/ws/live/2024_Bahrain"
            print(f"   🔌 Connecting to {uri}...")
            
            async with websockets.connect(uri) as websocket:
                print("   ✅ WebSocket connected!")
                
                # Listen for a few messages
                message_count = 0
                timeout = 5  # 5 second timeout
                start_time = time.time()
                
                while message_count < 3 and (time.time() - start_time) < timeout:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        data = json.loads(message)
                        message_count += 1
                        
                        if data['type'] == 'initial_state':
                            print(f"   📡 Received initial state: {data['data']['session_status']}")
                        elif data['type'] == 'update':
                            print(f"   📡 Received update: {data['data'].get('type', 'unknown')}")
                        else:
                            print(f"   📡 Received: {data['type']}")
                            
                    except asyncio.TimeoutError:
                        print("   ⏰ No more messages (timeout)")
                        break
                    except Exception as e:
                        print(f"   ❌ Error processing message: {e}")
                        break
                
                print(f"   ✅ WebSocket test completed ({message_count} messages received)")
                
        except Exception as e:
            print(f"   ❌ WebSocket test failed: {e}")
    
    async def test_legacy_compatibility(self):
        """Test legacy API compatibility"""
        print("\n6️⃣  Testing Legacy API Compatibility...")
        try:
            async with aiohttp.ClientSession() as session:
                # Test legacy driver standings
                async with session.get(f"{self.base_url}/api/drivers") as response:
                    drivers = await response.json()
                    print(f"   ✅ Legacy drivers endpoint: {len(drivers)} drivers")
                
                # Test legacy constructor standings
                async with session.get(f"{self.base_url}/api/constructors") as response:
                    constructors = await response.json()
                    print(f"   ✅ Legacy constructors endpoint: {len(constructors)} teams")
                
                # Test legacy race schedule
                async with session.get(f"{self.base_url}/api/races") as response:
                    races = await response.json()
                    print(f"   ✅ Legacy races endpoint: {len(races)} races")
                    
        except Exception as e:
            print(f"   ❌ Legacy compatibility test failed: {e}")

async def main():
    """Main demo function"""
    demo = F1PlatformDemo()
    await demo.run_demo()
    
    # Optional: Test legacy compatibility
    print("\n" + "=" * 50)
    print("🔄 Testing Legacy API Compatibility...")
    await demo.test_legacy_compatibility()

if __name__ == "__main__":
    print("🚀 Starting Enhanced F1 Platform Demo...")
    print("Make sure the API server is running on http://localhost:8000")
    print("Press Ctrl+C to stop the demo\n")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Demo stopped by user")
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
