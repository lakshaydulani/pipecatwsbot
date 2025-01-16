import uvicorn
from bot import main
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import HTMLResponse
import socket
import asyncio
# import psutil

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/test")
async def test():
    return HTMLResponse(content="api live version 1.3")

# @app.get("/live-ports")
# async def live_ports():
#     ports = [conn.laddr.port for conn in psutil.net_connections(kind='tcp') if conn.status == 'LISTEN']
#     return {"ports": ports}

@app.post("/start-call")
async def websocket_endpoint():
    def find_free_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]

    free_port = 8000; #find_free_port()
    print(f"Free port found: {free_port}")
    asyncio.create_task(main(free_port))
    # asyncio.create_task(killServer(free_port))
    return {"port": free_port}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8765)
