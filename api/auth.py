import os
import httpx
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from api.db import get_user_by_email, create_user, update_user
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/auth")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
# Ensure these are set in .env
if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    print("WARNING: GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not set in .env")

REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8000/auth/callback")

@router.get("/login")
async def login(request: Request):
    """Step 1: Redirect user to Google OAuth page."""
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?response_type=code"
        f"&client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope=openid%20email%20profile"
        f"&prompt=select_account"
    )
    return RedirectResponse(url=auth_url)

@router.get("/callback")
async def callback(request: Request, code: str):
    """Step 2: Handle redirect from Google, exchange code for token and profile."""
    # 1. Exchange code for access token
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(token_url, data=data)
        if token_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to exchange code for token")
        
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        
        # 2. Use access token to get user info
        user_info_resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        if user_info_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to get user info from Google")
        
        user_info = user_info_resp.json()
        
    # 3. Create or update user in database
    email = user_info.get("email")
    name = user_info.get("name")
    picture = user_info.get("picture")
    
    existing_user = get_user_by_email(email)
    if existing_user:
        user = update_user(email, name, picture)
    else:
        user = create_user(email, name, picture)
    
    # 4. Set user session
    request.session["user"] = {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "picture": user["picture"]
    }
    
    # Redirect back to homepage
    return RedirectResponse(url="/")

@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")

@router.get("/me")
async def get_me(request: Request):
    user = request.session.get("user")
    if not user:
        return {"logged_in": False}
    return {"logged_in": True, "user": user}

@router.put("/profile")
async def update_profile(request: Request):
    user_session = request.session.get("user")
    if not user_session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    data = await request.json()
    email = user_session["email"]
    
    # Update DB
    updated_user = update_user(email, data.get("name", user_session["name"]), user_session["picture"], profile_data=data)
    
    # Update session
    request.session["user"] = dict(updated_user)
    
    return {"success": True, "user": updated_user}
