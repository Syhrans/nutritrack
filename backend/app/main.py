
from fastapi import FastAPI, Depends, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text
from datetime import datetime, timezone, timedelta

import json
import os
import re
import hashlib
import hmac
import secrets

from dotenv import load_dotenv
from google import genai
from google.genai import types

from .database import Base, engine, get_db
from .models import Food, FoodLog, User
from .schemas import (
    FoodCreate,
    FoodLogCreate,
    UserCreate,
    UserLogin,
    CalorieGoalUpdate,
    UserProfileUpdate,
)

# ==========================================
# ENVIRONMENT AND GEMINI CONFIGURATION
# ==========================================

load_dotenv()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# ==========================================
# DATABASE INITIALIZATION AND MIGRATION
# ==========================================

Base.metadata.create_all(bind=engine)


def ensure_database_columns():
    """Safely add new columns to an existing database."""
    try:
        inspector = inspect(engine)

        user_columns = {
            column["name"]
            for column in inspector.get_columns("users")
        }

        with engine.begin() as connection:
            if "password_hash" not in user_columns:
                connection.execute(
                    text("ALTER TABLE users ADD COLUMN password_hash VARCHAR")
                )

            if "weight_goal" not in user_columns:
                connection.execute(
                    text(
                        "ALTER TABLE users ADD COLUMN weight_goal "
                        "VARCHAR NOT NULL DEFAULT 'maintain'"
                    )
                )

    except Exception as error:
        print("Database migration warning:", error)
        raise


ensure_database_columns()

# ==========================================
# FASTAPI APP AND CORS
# ==========================================

app = FastAPI(
    title="Calorie Tracker API",
    description="AI-powered calorie tracking application",
    version="1.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# TIMEZONE
# ==========================================

MALAYSIA_TIMEZONE = timezone(timedelta(hours=8))


def malaysia_now():
    return datetime.now(MALAYSIA_TIMEZONE)


# ==========================================
# MALAYSIAN FOOD DATABASE
# ==========================================

MALAYSIAN_FOODS = {
    "nasi lemak": {
        "name": "Nasi Lemak",
        "serving_size": "1 plate",
        "calories": 644,
        "protein": 20,
        "carbohydrates": 80,
        "fat": 28,
    },
    "ayam goreng": {
        "name": "Ayam Goreng",
        "serving_size": "1 piece",
        "calories": 280,
        "protein": 22,
        "carbohydrates": 8,
        "fat": 18,
    },
    "roti canai": {
        "name": "Roti Canai",
        "serving_size": "1 piece",
        "calories": 300,
        "protein": 6,
        "carbohydrates": 45,
        "fat": 11,
    },
    "mee goreng": {
        "name": "Mee Goreng",
        "serving_size": "1 plate",
        "calories": 450,
        "protein": 15,
        "carbohydrates": 65,
        "fat": 15,
    },
    "char kuey teow": {
        "name": "Char Kuey Teow",
        "serving_size": "1 plate",
        "calories": 550,
        "protein": 20,
        "carbohydrates": 70,
        "fat": 22,
    },
    "laksa": {
        "name": "Laksa",
        "serving_size": "1 bowl",
        "calories": 450,
        "protein": 18,
        "carbohydrates": 50,
        "fat": 20,
    },
    "satay": {
        "name": "Satay",
        "serving_size": "10 sticks",
        "calories": 350,
        "protein": 30,
        "carbohydrates": 10,
        "fat": 20,
    },
    "roti telur": {
        "name": "Roti Telur",
        "serving_size": "1 piece",
        "calories": 350,
        "protein": 12,
        "carbohydrates": 40,
        "fat": 16,
    },
    "nasi goreng": {
        "name": "Nasi Goreng",
        "serving_size": "1 plate",
        "calories": 550,
        "protein": 18,
        "carbohydrates": 75,
        "fat": 20,
    },
    "curry mee": {
        "name": "Curry Mee",
        "serving_size": "1 bowl",
        "calories": 500,
        "protein": 18,
        "carbohydrates": 55,
        "fat": 24,
    },
}

# ==========================================
# PASSWORD SECURITY
# ==========================================

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        310000,
    )

    return f"pbkdf2_sha256${salt.hex()}${password_hash.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    if not stored_hash:
        return False

    try:
        parts = stored_hash.split("$")

        if len(parts) != 3 or parts[0] != "pbkdf2_sha256":
            return False

        salt = bytes.fromhex(parts[1])
        expected_hash = bytes.fromhex(parts[2])

        actual_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            310000,
        )

        return hmac.compare_digest(actual_hash, expected_hash)

    except (ValueError, TypeError):
        return False


# ==========================================
# BMI AND CALORIE CALCULATIONS
# ==========================================

ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.2,
    "light": 1.375,
    "lightly active": 1.375,
    "moderate": 1.55,
    "moderately active": 1.55,
    "active": 1.725,
    "very active": 1.725,
    "extra active": 1.9,
}

VALID_WEIGHT_GOALS = {"lose", "maintain", "gain"}


def calculate_bmi(weight: float, height: float) -> float:
    if weight <= 0 or height <= 0:
        return 0.0

    height_metres = height / 100

    return round(weight / (height_metres * height_metres), 1)


def get_bmi_category(bmi: float) -> str:
    if bmi <= 0:
        return "Unavailable"
    if bmi < 18.5:
        return "Underweight"
    if bmi < 25:
        return "Normal weight"
    if bmi < 30:
        return "Overweight"

    return "Obesity"


def calculate_daily_calorie_goal(
    age: int,
    gender: str,
    weight: float,
    height: float,
    activity_level: str,
    weight_goal: str = "maintain",
) -> int:

    gender_text = (gender or "").strip().lower()
    activity_text = (activity_level or "moderate").strip().lower()
    goal_text = (weight_goal or "maintain").strip().lower()

    if gender_text in {"male", "m", "man"}:
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161

    multiplier = ACTIVITY_MULTIPLIERS.get(activity_text, 1.55)

    maintenance_calories = bmr * multiplier

    if goal_text == "lose":
        target = maintenance_calories - 400
    elif goal_text == "gain":
        target = maintenance_calories + 300
    else:
        target = maintenance_calories

    return max(1200, round(target))


def user_profile_response(user: User) -> dict:
    bmi = calculate_bmi(user.weight, user.height)

    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "age": user.age,
        "gender": user.gender,
        "weight": user.weight,
        "height": user.height,
        "activity_level": user.activity_level,
        "weight_goal": getattr(user, "weight_goal", "maintain") or "maintain",
        "bmi": bmi,
        "bmi_category": get_bmi_category(bmi),
        "daily_calorie_goal": user.daily_calorie_goal,
    }


# ==========================================
# GENERAL HELPERS
# ==========================================

def clean_number(value, default=0):
    if value is None:
        return default

    if isinstance(value, (int, float)):
        return value

    try:
        match = re.search(r"-?\d+(?:\.\d+)?", str(value))

        if match:
            return float(match.group())

    except (TypeError, ValueError):
        pass

    return default


def clean_ai_json(text_value):
    if not text_value:
        return {}

    text_value = text_value.strip()
    text_value = re.sub(r"```json", "", text_value, flags=re.IGNORECASE)
    text_value = re.sub(r"```", "", text_value)

    match = re.search(r"\{.*\}", text_value, re.DOTALL)

    if not match:
        return {}

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def convert_to_malaysia_time(created_at):
    if not created_at:
        return None

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    return created_at.astimezone(MALAYSIA_TIMEZONE)


def find_user(db: Session, user_id: int):
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


# ==========================================
# AUTOMATIC 30-DAY DIARY CLEANUP
# ==========================================

def cleanup_expired_food_logs(db: Session):
    """
    Permanently delete diary entries older than 30 days.

    The database stores timestamps as naive UTC values.
    """

    cutoff_utc = (
        datetime.now(timezone.utc).replace(tzinfo=None)
        - timedelta(days=30)
    )

    deleted_count = (
        db.query(FoodLog)
        .filter(FoodLog.created_at < cutoff_utc)
        .delete(synchronize_session=False)
    )

    if deleted_count:
        db.commit()
        print(
            f"Deleted {deleted_count} expired food diary entries."
        )

    return deleted_count


# ==========================================
# GEMINI HELPER
# ==========================================

async def ask_gemini(prompt: str):
    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Gemini API key is not configured. Check your backend .env file.",
        )

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)

        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )

        raw_response = getattr(response, "text", None)

        if not raw_response or not raw_response.strip():
            raise HTTPException(
                status_code=502,
                detail="Gemini returned an empty response.",
            )

        data = clean_ai_json(raw_response)

        if not data:
            raise HTTPException(
                status_code=502,
                detail="Gemini returned invalid nutrition data.",
            )

        return data

    except HTTPException:
        raise

    except Exception as error:
        error_text = str(error)

        print("Gemini API error:", error_text)

        if "API_KEY_INVALID" in error_text or "invalid api key" in error_text.lower():
            raise HTTPException(
                status_code=502,
                detail="Gemini rejected the API key. Check GEMINI_API_KEY.",
            )

        if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
            raise HTTPException(
                status_code=429,
                detail="Gemini API quota or rate limit reached. Try again later.",
            )

        raise HTTPException(
            status_code=502,
            detail="Gemini is temporarily unavailable. Please try again.",
        )


# ==========================================
# ROOT AND HEALTH
# ==========================================

@app.get("/")
def root():
    return {"message": "Calorie Tracker API is running!"}


@app.get("/health")
def health():
    return {"status": "healthy"}


# ==========================================
# REGISTER USER
# ==========================================

@app.post("/auth/register")
def register_user(user: UserCreate, db: Session = Depends(get_db)):

    email = str(user.email).strip().lower()

    if db.query(User).filter(User.email == email).first():
        raise HTTPException(
            status_code=400,
            detail="Email already registered",
        )

    goal = calculate_daily_calorie_goal(
        age=user.age,
        gender=user.gender,
        weight=user.weight,
        height=user.height,
        activity_level=user.activity_level,
        weight_goal="maintain",
    )

    new_user = User(
        name=user.name.strip(),
        email=email,
        password_hash=hash_password(user.password),
        age=user.age,
        gender=user.gender.strip().lower(),
        weight=user.weight,
        height=user.height,
        activity_level=user.activity_level.strip().lower(),
        weight_goal="maintain",
        daily_calorie_goal=goal,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "message": "Registration successful",
        "user": user_profile_response(new_user),
    }


# ==========================================
# LOGIN USER
# ==========================================

@app.post("/auth/login")
def login_user(login: UserLogin, db: Session = Depends(get_db)):

    email = str(login.email).strip().lower()

    user = db.query(User).filter(User.email == email).first()

    if not user or not verify_password(
        login.password,
        user.password_hash or "",
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    return {
        "message": "Login successful",
        "user": user_profile_response(user),
    }


# ==========================================
# CREATE USER - LEGACY ENDPOINT
# ==========================================

@app.post("/users")
def create_user(user: UserCreate, db: Session = Depends(get_db)):

    email = str(user.email).strip().lower()

    if db.query(User).filter(User.email == email).first():
        raise HTTPException(
            status_code=400,
            detail="Email already registered",
        )

    new_user = User(
        name=user.name.strip(),
        email=email,
        password_hash=hash_password(user.password),
        age=user.age,
        gender=user.gender.strip().lower(),
        weight=user.weight,
        height=user.height,
        activity_level=user.activity_level.strip().lower(),
        weight_goal="maintain",
        daily_calorie_goal=calculate_daily_calorie_goal(
            user.age,
            user.gender,
            user.weight,
            user.height,
            user.activity_level,
            "maintain",
        ),
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return user_profile_response(new_user)


# ==========================================
# GET USER PROFILE
# ==========================================

@app.get("/users/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    return user_profile_response(find_user(db, user_id))


# ==========================================
# UPDATE PROFILE AND RECALCULATE TARGET
# ==========================================

@app.put("/users/{user_id}/profile")
def update_user_profile(
    user_id: int,
    profile: UserProfileUpdate,
    db: Session = Depends(get_db),
):

    user = find_user(db, user_id)

    gender = profile.gender.strip().lower()
    activity_level = profile.activity_level.strip().lower()
    weight_goal = profile.weight_goal.strip().lower()

    if gender not in {"male", "female", "m", "f", "man", "woman"}:
        raise HTTPException(
            status_code=400,
            detail="Sex must be male or female for this calorie equation.",
        )

    if activity_level not in ACTIVITY_MULTIPLIERS:
        raise HTTPException(
            status_code=400,
            detail="Invalid activity level",
        )

    if weight_goal not in VALID_WEIGHT_GOALS:
        raise HTTPException(
            status_code=400,
            detail="Weight goal must be lose, maintain, or gain",
        )

    user.age = profile.age
    user.gender = gender
    user.weight = profile.weight
    user.height = profile.height
    user.activity_level = activity_level
    user.weight_goal = weight_goal

    user.daily_calorie_goal = calculate_daily_calorie_goal(
        age=user.age,
        gender=user.gender,
        weight=user.weight,
        height=user.height,
        activity_level=user.activity_level,
        weight_goal=user.weight_goal,
    )

    db.commit()
    db.refresh(user)

    return {
        "message": "Profile updated successfully",
        "user": user_profile_response(user),
    }


# ==========================================
# UPDATE DAILY CALORIE GOAL MANUALLY
# ==========================================

@app.put("/users/{user_id}/calorie-goal")
def update_calorie_goal(
    user_id: int,
    goal_data: CalorieGoalUpdate,
    db: Session = Depends(get_db),
):

    user = find_user(db, user_id)

    user.daily_calorie_goal = goal_data.calorie_goal

    db.commit()
    db.refresh(user)

    return {
        "message": "Daily calorie goal updated successfully",
        "user_id": user.id,
        "daily_calorie_goal": user.daily_calorie_goal,
    }


# ==========================================
# CREATE FOOD
# ==========================================

@app.post("/foods")
def create_food(food: FoodCreate, db: Session = Depends(get_db)):

    new_food = Food(**food.model_dump())

    db.add(new_food)
    db.commit()
    db.refresh(new_food)

    return new_food


# ==========================================
# GET ALL FOODS
# ==========================================

@app.get("/foods")
def get_foods(db: Session = Depends(get_db)):
    return db.query(Food).order_by(Food.name).all()


# ==========================================
# SEARCH FOOD
# DATABASE -> MALAYSIAN FOOD -> GEMINI
# ==========================================

@app.get("/foods/search")
async def search_food(name: str, db: Session = Depends(get_db)):

    search_text = name.strip().lower()

    if not search_text:
        return []

    # 1. Search the existing database
    foods = (
        db.query(Food)
        .filter(Food.name.ilike(f"%{search_text}%"))
        .all()
    )

    if foods:
        return foods

    # 2. Search the Malaysian food dictionary
    results = []

    for key, food in MALAYSIAN_FOODS.items():
        if search_text in key or key in search_text:
            results.append({
                **food,
                "source": "Malaysian food database",
            })

    if results:
        return results

    # 3. Use Gemini for other food names
    prompt = f"""
You are a nutrition assistant for a calorie tracking application.

Estimate the nutrition information for this food:
"{name}"

Use a realistic normal serving size.
Prefer Malaysian and Asian food information when relevant.
Do not invent a precise brand or restaurant.

Return ONLY valid JSON in this format:

{{
    "name": "Food name",
    "serving_size": "1 serving",
    "calories": 0,
    "protein": 0,
    "carbohydrates": 0,
    "fat": 0
}}

All nutrition values must be numeric and non-negative.
If the input is not a recognisable food, return an empty JSON object.
"""

    ai_data = await ask_gemini(prompt)

    food_name = ai_data.get("name")
    serving_size = ai_data.get("serving_size", "1 serving")

    if not isinstance(food_name, str) or not food_name.strip():
        return []

    if not isinstance(serving_size, str) or not serving_size.strip():
        serving_size = "1 serving"

    calories = max(0, clean_number(ai_data.get("calories")))
    protein = max(0, clean_number(ai_data.get("protein")))
    carbohydrates = max(
        0,
        clean_number(ai_data.get("carbohydrates")),
    )
    fat = max(0, clean_number(ai_data.get("fat")))

    if calories <= 0:
        return []

    return [{
        "name": food_name.strip(),
        "serving_size": serving_size.strip(),
        "calories": calories,
        "protein": protein,
        "carbohydrates": carbohydrates,
        "fat": fat,
        "source": f"Google Gemini ({GEMINI_MODEL})",
        "disclaimer": (
            "AI-generated nutrition estimate. Actual values may vary "
            "depending on ingredients and portion size."
        ),
    }]


# ==========================================
# CREATE FOOD LOG
# ==========================================

@app.post("/food-logs")
def create_food_log(log: FoodLogCreate, db: Session = Depends(get_db)):

    find_user(db, log.user_id)

    food = db.query(Food).filter(Food.id == log.food_id).first()

    if not food:
        raise HTTPException(
            status_code=404,
            detail="Food not found",
        )

    if log.quantity <= 0:
        raise HTTPException(
            status_code=400,
            detail="Quantity must be greater than 0",
        )

    # Remove expired history before creating a new entry.
    cleanup_expired_food_logs(db)

    new_log = FoodLog(
        user_id=log.user_id,
        food_id=log.food_id,
        meal_type=log.meal_type.strip().lower(),
        quantity=log.quantity,
        calories=food.calories * log.quantity,
    )

    db.add(new_log)
    db.commit()
    db.refresh(new_log)

    return new_log


# ==========================================
# GET FOOD LOGS - LAST 30 DAYS
# ==========================================

@app.get("/food-logs/{user_id}")
def get_food_logs(user_id: int, db: Session = Depends(get_db)):

    find_user(db, user_id)

    # Permanently remove diary entries older than 30 days.
    cleanup_expired_food_logs(db)

    logs = (
        db.query(FoodLog)
        .filter(FoodLog.user_id == user_id)
        .order_by(FoodLog.created_at.desc())
        .all()
    )

    result = []

    for log in logs:

        food = db.query(Food).filter(Food.id == log.food_id).first()

        created_at = convert_to_malaysia_time(log.created_at)

        result.append({
            "id": log.id,
            "user_id": log.user_id,
            "food_id": log.food_id,
            "meal_type": log.meal_type,
            "quantity": log.quantity,
            "calories": log.calories,
            "created_at": created_at.isoformat() if created_at else None,
            "food": {
                "id": food.id if food else None,
                "name": food.name if food else "Unknown Food",
                "serving_size": food.serving_size if food else "1 serving",
                "calories": food.calories if food else 0,
                "protein": food.protein if food else 0,
                "carbohydrates": food.carbohydrates if food else 0,
                "fat": food.fat if food else 0,
            },
        })

    return result


# ==========================================
# DELETE FOOD LOG
# ==========================================

@app.delete("/food-logs/{log_id}")
def delete_food_log(log_id: int, db: Session = Depends(get_db)):

    log = db.query(FoodLog).filter(FoodLog.id == log_id).first()

    if not log:
        raise HTTPException(
            status_code=404,
            detail="Food log not found",
        )

    db.delete(log)
    db.commit()

    return {"message": "Food log deleted successfully"}


# ==========================================
# DASHBOARD - TODAY ONLY, MALAYSIA TIME
# ==========================================

@app.get("/dashboard/{user_id}")
def dashboard(user_id: int, db: Session = Depends(get_db)):

    user = find_user(db, user_id)

    # Clean expired history.
    cleanup_expired_food_logs(db)

    # Malaysia's calendar date. Daily intake resets at 12:00 AM MYT.
    today = malaysia_now().date()

    logs = (
        db.query(FoodLog)
        .filter(FoodLog.user_id == user_id)
        .all()
    )

    today_logs = []

    for log in logs:

        if not log.created_at:
            continue

        created_at = log.created_at

        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        if created_at.astimezone(MALAYSIA_TIMEZONE).date() == today:
            today_logs.append(log)

    consumed = sum(log.calories or 0 for log in today_logs)

    meals = {
        "breakfast": 0,
        "lunch": 0,
        "dinner": 0,
        "snacks": 0,
    }

    for log in today_logs:

        meal = (log.meal_type or "").strip().lower()

        if meal in meals:
            meals[meal] += log.calories or 0
        elif meal == "snack":
            meals["snacks"] += log.calories or 0

    goal = user.daily_calorie_goal or 0
    remaining = max(goal - consumed, 0)

    progress = min(
        max((consumed / goal * 100) if goal > 0 else 0, 0),
        100,
    )

    bmi = calculate_bmi(user.weight, user.height)

    return {
        "date": str(today),
        "user": {
            "id": user.id,
            "name": user.name,
            "daily_calorie_goal": goal,
            "age": user.age,
            "gender": user.gender,
            "weight": user.weight,
            "height": user.height,
            "activity_level": user.activity_level,
            "weight_goal": getattr(user, "weight_goal", "maintain") or "maintain",
            "bmi": bmi,
            "bmi_category": get_bmi_category(bmi),
        },
        "calories": {
            "goal": goal,
            "consumed": round(consumed, 1),
            "remaining": round(remaining, 1),
            "progress": round(progress, 1),
        },
        "meals": {
            key: round(value, 1)
            for key, value in meals.items()
        },
    }


# ==========================================
# AI FOOD PHOTO ANALYSIS - GOOGLE GEMINI
# ==========================================

@app.post("/ai/analyze-food")
async def analyze_food(image: UploadFile = File(...)):

    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="Please upload an image file",
        )

    image_bytes = await image.read()

    if not image_bytes:
        raise HTTPException(
            status_code=400,
            detail="Uploaded image is empty",
        )

    max_image_bytes = 12 * 1024 * 1024

    if len(image_bytes) > max_image_bytes:
        raise HTTPException(
            status_code=413,
            detail="Image is too large. Please choose a photo smaller than 12 MB.",
        )

    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Gemini API key is not configured. Add GEMINI_API_KEY to the backend .env file.",
        )

    prompt = """
You are a food recognition and nutrition estimation assistant for a calorie tracker.

Identify the food shown in the image.
Prefer Malaysian and Asian food names when appropriate.

Estimate the visible portion, not an ideal restaurant serving.
If several foods are visible, estimate the main meal as one combined serving
and explain the portion in serving_size.

Do not claim exact nutritional accuracy from an image.

Return ONLY one valid JSON object with exactly these fields:

{
  "food_name": "name of food",
  "serving_size": "estimated visible serving",
  "calories": 0,
  "protein": 0,
  "carbohydrates": 0,
  "fat": 0,
  "confidence": 0.0
}

Calories are kcal.
Protein, carbohydrates and fat are grams.
All nutrition values must be numeric and non-negative.
Confidence must be a number from 0 to 1.
Do not include markdown or explanations outside the JSON.
"""

    try:

        client = genai.Client(api_key=GEMINI_API_KEY)

        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                prompt,
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=image.content_type,
                ),
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )

    except Exception as error:

        error_text = str(error)

        print("Gemini photo analysis error:", error_text)

        if "API_KEY_INVALID" in error_text or "invalid api key" in error_text.lower():
            raise HTTPException(
                status_code=502,
                detail="Gemini rejected the API key. Check GEMINI_API_KEY in your .env file.",
            )

        if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
            raise HTTPException(
                status_code=429,
                detail="Gemini API quota or rate limit reached. Please try again later.",
            )

        raise HTTPException(
            status_code=502,
            detail="Gemini could not analyse this image. Please try again with a clearer photo.",
        )

    raw_response = getattr(response, "text", None)

    if not raw_response or not raw_response.strip():
        raise HTTPException(
            status_code=502,
            detail="Gemini returned an empty response. Please try again.",
        )

    ai_data = clean_ai_json(raw_response)

    if not ai_data:
        raise HTTPException(
            status_code=502,
            detail="The Gemini response could not be read as nutrition data. Please try again.",
        )

    food_name = ai_data.get("food_name", "Unknown Food")
    serving_size = ai_data.get("serving_size", "1 serving")

    if isinstance(food_name, (dict, list)) or not str(food_name).strip():
        food_name = "Unknown Food"

    if isinstance(serving_size, (dict, list)) or not str(serving_size).strip():
        serving_size = "1 serving"

    confidence = clean_number(ai_data.get("confidence"))

    if confidence <= 1:
        confidence *= 100

    return {
        "food_name": str(food_name),
        "serving_size": str(serving_size),
        "calories": max(0, clean_number(ai_data.get("calories"))),
        "protein": max(0, clean_number(ai_data.get("protein"))),
        "carbohydrates": max(
            0,
            clean_number(ai_data.get("carbohydrates")),
        ),
        "fat": max(0, clean_number(ai_data.get("fat"))),
        "confidence": min(max(confidence, 0), 100),
        "source": f"Google Gemini ({GEMINI_MODEL})",
        "disclaimer": (
            "Nutrition values are estimates. Check the serving size "
            "before saving."
        ),
    }
