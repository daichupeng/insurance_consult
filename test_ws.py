import asyncio
import websockets
import json
import uuid

async def test():
    session_id = str(uuid.uuid4())
    
    import urllib.request
    req = urllib.request.Request("http://127.0.0.1:8000/api/sessions", method="POST")
    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read())
    session_id = data["session_id"]
    uri = f"ws://127.0.0.1:8000/ws/{session_id}"

    print(f"Testing with session {session_id}")
    async with websockets.connect(uri) as ws:
        async def send_msg(msg_type, content):
            print(f"> Sending: {content}")
            await ws.send(json.dumps({"type": msg_type, "message": content if msg_type == "start" else None, "content": content if msg_type == "answer" else None}))
        
        # 1. Start flow
        await send_msg("start", "I want to buy life insurance")
        
        # Wait for some status messages
        for _ in range(2):
            msg = await asyncio.wait_for(ws.recv(), timeout=30)
            print(f"< {msg}")
            
        # 2. Transient interruption
        await send_msg("answer", "Wait, what is a deductible?")
        msg = await asyncio.wait_for(ws.recv(), timeout=60)
        print(f"< {msg}")
        
        # 3. Terminal interruption
        await send_msg("answer", "Actually, I changed my mind. I need help filing a claim.")
        msg = await asyncio.wait_for(ws.recv(), timeout=60)
        print(f"< {msg}")
        
        # 4. Global command
        await send_msg("answer", "start over")
        msg = await asyncio.wait_for(ws.recv(), timeout=60)
        print(f"< {msg}")
        msg = await asyncio.wait_for(ws.recv(), timeout=60)
        print(f"< {msg}")

asyncio.run(test())
