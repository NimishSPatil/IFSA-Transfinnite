"""Start the Pulp Riot control tower:  python run.py   ->  http://localhost:8600"""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.environ.get("PORT", "8600")), reload=False)
