from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# 👇 加这一段
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发阶段直接放开
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Hello World"}
