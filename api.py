from fastapi import FastAPI
import uvicorn

app = FastAPI()
config = uvicorn.Config(app, loop="asyncio")
server = uvicorn.Server(config)

@app.get("/")
async def ping():
    return {"message": "pong"}

async def start_server():
    await server.serve()