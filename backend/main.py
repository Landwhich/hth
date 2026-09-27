import ssl
ssl._create_default_https_context = ssl._create_unverified_context

from fastapi import FastAPI, Depends, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
import uuid
import random

from database import engine, Base, get_db
from models import User, ParkingScore
from auth import verify_token
from storage import upload_file_to_spaces

from src.park_checker import run_park_check

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://localhost:3844",
        "http://localhost:3844",
        "https://127.0.0.1:3844",
        "http://127.0.0.1:3844",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class UserSyncRequest(BaseModel):
    email: str
    username: str | None = None
    picture: str | None = None

@app.get("/")
def read_root():
    return {"message": "Hello, World!"}

@app.post("/auth/sync")
def sync_user(user_data: UserSyncRequest, token_payload: dict = Depends(verify_token), db: Session = Depends(get_db)):
    """
    Called by the frontend immediately after an Auth0 login.
    Checks if the user exists in NeonDB, and creates them if they don't.
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid token payload: missing sub")

    # Check if user already exists
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        # Create new user
        user = User(
            id=user_id,
            email=user_data.email,
            username=user_data.username,
            profile_picture=user_data.picture
        )
        db.add(user)
    else:
        # Update existing user info if it changed
        user.username = user_data.username or user.username
        user.profile_picture = user_data.picture or user.profile_picture
        
    db.commit()
    db.refresh(user)
    return {"message": "User synced", "user": {"id": user.id, "email": user.email}}

@app.post("/upload")
def upload_image(
    file: UploadFile = File(...),
    token_payload: dict = Depends(verify_token),
    db: Session = Depends(get_db)
):
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid token payload: missing sub")
    
    # Generate a unique filename using UUID
    extension = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    
    # To upload to a specific folder, simply prepend the folder path to the filename!
    # DigitalOcean (like AWS S3) creates folders automatically based on the filename.
    unique_filename = f"hth-2026/{uuid.uuid4()}.{extension}"

    import shutil
    import os
    
    temp_image_path = f"temp_{unique_filename.replace('/', '_')}"
    with open(temp_image_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    file.file.seek(0)

    # Upload to DigitalOcean Spaces
    try:
        public_url = upload_file_to_spaces(file.file, unique_filename, file.content_type)
    except Exception as e:
        if os.path.exists(temp_image_path):
            os.remove(temp_image_path)
        raise HTTPException(status_code=500, detail=f"Failed to upload to DigitalOcean: {str(e)}")
    
    # Run AI Analysis
    try:
        results = run_park_check(
            temp_image_path,
            None, # target will default for center screen for simplicity
            "output.jpg"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CV Pipeline error: {str(e)}")
    finally:
        if os.path.exists(temp_image_path):
            os.remove(temp_image_path)

    # Save the score to NeonDB
    score = results["score"]
    
    parking_score = ParkingScore(
        user_id=user_id,
        image_url=public_url,
        score=score,
        # feedback=results["feedback"],
    )
    db.add(parking_score)
    
    # Update the user's running average
    user = db.query(User).filter(User.id == user_id).first()
    previous_average_score = user.average_score if user else None
    if user:
        all_user_scores = db.query(ParkingScore).filter(ParkingScore.user_id == user_id).all()
        # all_user_scores includes the new one because it was added to the session, 
        # but to be safe we can just calculate it manually
        total_scores = sum(s.score for s in all_user_scores if s.id != parking_score.id) + score
        count_scores = len(all_user_scores) + (1 if parking_score not in all_user_scores else 0)
        user.average_score = round(total_scores / count_scores, 1)

    try:
        db.commit()
        db.refresh(parking_score)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    return {
        "message": "Image analyzed and saved successfully!",
        "score": parking_score.score,
        "image_url": parking_score.image_url,
        "average_score": user.average_score if user else None,
        "previous_average_score": previous_average_score
    }

@app.get("/leaderboard")
def get_leaderboard(db: Session = Depends(get_db)):
    """
    Returns users ranked for the leaderboard with their average score,
    total snaps count, and a generated avatar.
    """
    users = db.query(User).all()
    leaderboard = []

    for u in users:
        snaps = u.scores
        snaps_count = len(snaps)
        
        display_name = u.username if u.username else (u.email.split("@")[0] if u.email else "Anonymous Parker")
        
        # Calculate real average if average_score is not set or 0
        avg = u.average_score
        if snaps_count > 0 and (avg is None or avg == 0.0):
            avg = sum(s.score for s in snaps) / snaps_count
        elif avg is None:
            avg = 0.0

        leaderboard.append({
            "id": u.id,
            "username": display_name,
            "average_score": round(float(avg), 1),
            "total_snaps": snaps_count,
            "avatar": u.profile_picture or f"https://api.dicebear.com/7.x/avataaars/svg?seed={display_name}"
        })

    return leaderboard

@app.get("/profile/{user_id}")
def get_profile(user_id: str, db: Session = Depends(get_db)):
    """
    Returns a specific user's public profile and all their parking photos and scores.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    display_name = user.username if user.username else (user.email.split("@")[0] if user.email else "Anonymous Parker")
    
    # Get all scores sorted newest first
    scores = sorted(user.scores, key=lambda s: s.created_at, reverse=True)
    
    return {
        "id": user.id,
        "username": display_name,
        "average_score": user.average_score,
        "total_snaps": len(scores),
        "avatar": user.profile_picture or f"https://api.dicebear.com/7.x/avataaars/svg?seed={display_name}",
        "joined_at": user.created_at.isoformat() if user.created_at else None,
        "snaps": [
            {
                "id": s.id,
                "image_url": s.image_url,
                "score": s.score,
                "created_at": s.created_at.isoformat() if s.created_at else None
            }
            for s in scores
        ]
    }

@app.get("/items/{item_id}")
def read_item(item_id: int, q: str | None = None):
    return {"item_id": item_id, "query": q}
