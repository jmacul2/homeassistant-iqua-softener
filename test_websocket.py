#!/usr/bin/env python3
"""
Test script to check iQua WebSocket connectivity outside of Home Assistant.
This helps isolate whether the issue is with the integration or the underlying library.
"""

import asyncio
import aiohttp
import json
import sys
from iqua_softener import IquaSoftener

# Default WebSocket base URL - can be overridden
DEFAULT_WEBSOCKET_BASE = "wss://api.myiquaapp.com"

def get_websocket_base_url(softener):
    """Get the WebSocket base URL from the softener library or use default."""
    try:
        # Try to get base URL from the library if it has this capability
        if hasattr(softener, 'get_base_url'):
            http_base = softener.get_base_url()
            # Convert HTTP/HTTPS to WebSocket URL
            if http_base.startswith('https://'):
                return http_base.replace('https://', 'wss://')
            elif http_base.startswith('http://'):
                return http_base.replace('http://', 'ws://')
        
        # Try to get it from other library attributes
        if hasattr(softener, 'base_url'):
            http_base = softener.base_url
            if http_base.startswith('https://'):
                return http_base.replace('https://', 'wss://')
            elif http_base.startswith('http://'):
                return http_base.replace('http://', 'ws://')
                
    except Exception as err:
        print(f"  Could not derive WebSocket base URL from library: {err}")
    
    # Fallback to default
    print(f"  Using default WebSocket base URL: {DEFAULT_WEBSOCKET_BASE}")
    return DEFAULT_WEBSOCKET_BASE

async def test_websocket_connection(username, password, device_sn):
    """Test WebSocket connection independently."""
    print(f"Testing WebSocket connection for device: {device_sn}")
    
    try:
        # Create IquaSoftener instance
        print("Creating IquaSoftener instance...")
        softener = IquaSoftener(username, password, device_sn, enable_websocket=True)
        
        # Test basic authentication first
        print("Testing basic authentication...")
        try:
            data = softener.get_data()
            print("✓ Basic authentication successful")
            print(f"  Device state: {data.state.value}")
            print(f"  Current flow: {data.current_water_flow}")
        except Exception as e:
            print(f"✗ Basic authentication failed: {e}")
            return False
        
        # Get WebSocket URI
        print("Getting WebSocket URI...")
        try:
            ws_uri = softener.get_websocket_uri()
            if not ws_uri:
                print("✗ WebSocket URI is empty")
                return False
            
            print(f"✓ WebSocket URI obtained (length: {len(ws_uri)})")
            
            # Handle relative URI (starts with /ws/) by constructing full URL
            if ws_uri.startswith('/ws/'):
                print(f"  Got relative URI: {ws_uri[:50]}...")
                websocket_base = get_websocket_base_url(softener)
                full_uri = f"{websocket_base}{ws_uri}"
                print(f"  Constructing full URI with base {websocket_base}")
                print(f"  Full URI: {full_uri.split('?')[0]}?p=...")
                ws_uri = full_uri
            elif ws_uri.startswith('wss://') or ws_uri.startswith('ws://'):
                # Show base URI without token
                uri_parts = ws_uri.split('?')
                base_uri = uri_parts[0] if uri_parts else ws_uri
                print(f"  Full URI: {base_uri}")
            else:
                print(f"  Unexpected URI format: {ws_uri[:50]}...")
            
        except AttributeError:
            print("✗ get_websocket_uri method not available in library")
            return False
        except Exception as e:
            print(f"✗ Failed to get WebSocket URI: {e}")
            return False
        
        # Test WebSocket connection
        print("Testing WebSocket connection...")
        session = aiohttp.ClientSession()
        
        try:
            async with session.ws_connect(
                ws_uri,
                timeout=aiohttp.ClientTimeout(total=10),
                heartbeat=30,
            ) as ws:
                print("✓ WebSocket connected successfully!")
                
                # Wait for a few messages
                print("Waiting for messages (10 seconds)...")
                message_count = 0
                
                try:
                    async with asyncio.timeout(10):
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    data = json.loads(msg.data)
                                    message_count += 1
                                    print(f"  Message {message_count}: {data}")
                                    
                                    if message_count >= 3:  # Stop after 3 messages
                                        break
                                        
                                except json.JSONDecodeError:
                                    print(f"  Invalid JSON: {msg.data}")
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                print(f"  WebSocket error: {ws.exception()}")
                                break
                            elif msg.type == aiohttp.WSMsgType.CLOSE:
                                print("  WebSocket closed by server")
                                break
                                
                except asyncio.TimeoutError:
                    print("  Timeout waiting for messages")
                
                if message_count > 0:
                    print(f"✓ Received {message_count} WebSocket messages")
                    return True
                else:
                    print("⚠ WebSocket connected but no messages received")
                    return True  # Connection works, just no data
                    
        except aiohttp.ClientResponseError as e:
            if e.status == 400:
                print(f"✗ WebSocket 400 error: {e}")
                print("  This usually indicates an authentication/token issue")
            else:
                print(f"✗ WebSocket HTTP error: {e}")
            return False
        except Exception as e:
            print(f"✗ WebSocket connection failed: {e}")
            return False
        finally:
            await session.close()
            
    except Exception as e:
        print(f"✗ Test failed: {e}")
        return False

def main():
    """Main function to run the test."""
    if len(sys.argv) < 4 or len(sys.argv) > 5:
        print("Usage: python test_websocket.py <username> <password> <device_serial> [websocket_base_url]")
        print("Example: python test_websocket.py myuser@email.com mypassword ABC123")
        print("Example: python test_websocket.py myuser@email.com mypassword ABC123 wss://custom.api.com")
        sys.exit(1)
    
    username = sys.argv[1]
    password = sys.argv[2]
    device_sn = sys.argv[3]
    
    # Override default WebSocket base URL if provided
    if len(sys.argv) == 5:
        global DEFAULT_WEBSOCKET_BASE
        DEFAULT_WEBSOCKET_BASE = sys.argv[4]
        print(f"Using custom WebSocket base URL: {DEFAULT_WEBSOCKET_BASE}")
    
    print("iQua WebSocket Connection Test")
    print("=" * 40)
    
    success = asyncio.run(test_websocket_connection(username, password, device_sn))
    
    print("\n" + "=" * 40)
    if success:
        print("✓ WebSocket test completed successfully")
        print("\nIf this test passes but Home Assistant still has issues,")
        print("the problem is likely in the integration code.")
    else:
        print("✗ WebSocket test failed")
        print("\nPossible solutions:")
        print("1. Check your iQua credentials")
        print("2. Verify device serial number")
        print("3. Check if your account has WebSocket access")
        print("4. Try again later (server might be temporarily down)")
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()