import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from hashlib import sha256
from typing import Optional, List
from bson import ObjectId

from database import db, create_document, get_documents

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"

            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


# -------------------- Auth --------------------
class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    name: str
    email: EmailStr
    avatar_url: Optional[str] = None


def _hash_password(pw: str) -> str:
    return sha256(pw.encode("utf-8")).hexdigest()


@app.post("/auth/register", response_model=AuthResponse)
def register(data: RegisterRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    existing = db["authuser"].find_one({"email": data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    doc = {
        "name": data.name,
        "email": str(data.email),
        "password_hash": _hash_password(data.password),
        "avatar_url": None,
    }
    create_document("authuser", doc)
    return AuthResponse(name=data.name, email=data.email, avatar_url=None)


@app.post("/auth/login", response_model=AuthResponse)
def login(data: LoginRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    user = db["authuser"].find_one({"email": str(data.email)})
    if not user or user.get("password_hash") != _hash_password(data.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return AuthResponse(name=user.get("name"), email=user.get("email"), avatar_url=user.get("avatar_url"))


# -------------------- Notifications --------------------
class CreateNotificationRequest(BaseModel):
    email: EmailStr
    title: str
    body: str


class MarkAllReadRequest(BaseModel):
    email: EmailStr


class NotificationItem(BaseModel):
    id: str
    title: str
    body: str
    read: bool
    created_at: Optional[str] = None


@app.post("/notifications")
def create_notification(data: CreateNotificationRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    # Only allow notifications for known users (optional check)
    user = db["authuser"].find_one({"email": str(data.email)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    doc = {
        "user_email": str(data.email),
        "title": data.title,
        "body": data.body,
        "read": False,
    }
    nid = create_document("notification", doc)
    return {"id": nid, "status": "created"}


@app.get("/notifications", response_model=List[NotificationItem])
def list_notifications(email: EmailStr):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    raw = db["notification"].find({"user_email": str(email)}).sort("created_at", -1)
    items: List[NotificationItem] = []
    for d in raw:
        items.append(
            NotificationItem(
                id=str(d.get("_id")),
                title=d.get("title", ""),
                body=d.get("body", ""),
                read=bool(d.get("read", False)),
                created_at=d.get("created_at").isoformat() if d.get("created_at") else None,
            )
        )
    return items


@app.post("/notifications/mark-all-read")
def mark_all_read(data: MarkAllReadRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    db["notification"].update_many({"user_email": str(data.email), "read": False}, {"$set": {"read": True}})
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
