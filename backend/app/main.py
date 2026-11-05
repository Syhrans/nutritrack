
from fastapi import FastAPI, Depends, HTTPException, File, UploadFile
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy.orm import Session
from sqlalchemy import inspect, text

from datetime import datetime, timezone, timedelta, date
from typing import Optional

import jwt
import json
import os
import re
import hashlib
import hmac
import secrets

from dotenv import load_dotenv
load_dotenv()

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
# TIMEZONE
# ==========================================

MALAYSIA_TIMEZONE = timezone(timedelta(hours=8))


def get_malaysia_now():
    return datetime.now(MALAYSIA_TIMEZONE)


def get_malaysia_today():
    return get_malaysia_now().date()


def convert_to_malaysia_time(created_at):
    if not created_at:
        return None

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    return created_at.astimezone(MALAYSIA_TIMEZONE)


def is_log_on_date(log, selected_date):
    """Compare a food log timestamp against a Malaysia calendar date."""
    if not log.created_at:
        return False

    malaysia_created_at = convert_to_malaysia_time(log.created_at)

    return malaysia_created_at.date() == selected_date


# ==========================================
# FASTAPI APP AND CORS
# ==========================================

JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY",
    "dev-only-change-this-secret"
)

if os.getenv("RENDER") and JWT_SECRET_KEY == "dev-only-change-this-secret":
    raise RuntimeError(
        "JWT_SECRET_KEY must be configured in Render environment variables"
    )

JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")
)

security = HTTPBearer(auto_error=False)


def create_access_token(user_id: int) -> str:
    expires = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": str(user_id),
        "exp": expires
    }

    return jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM]
        )

        subject = payload.get("sub")
        user_id = int(subject)

    except (jwt.InvalidTokenError, TypeError, ValueError):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return find_user(db, user_id)


def require_owner(path_user_id: int, current_user: User):
    if path_user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You cannot access another user's data"
        )


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
        "https://nutritrack-frontend-3988.onrender.com",
        os.getenv("FRONTEND_URL", "").rstrip("/"),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    """Calculate BMI using kg and cm."""
    if weight <= 0 or height <= 0:
        return 0.0

    height_metres = height / 100

    return round(
        weight / (height_metres * height_metres),
        1
    )


def get_bmi_category(bmi: float) -> str:
    """Adult BMI categories; interpretation differs for children."""
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

    """Estimate maintenance calories, then adjust for the selected goal."""

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

    text_value = re.sub(
        r"\`\`\`json",
        "",
        text_value,
        flags=re.IGNORECASE
    )

    text_value = re.sub(r"\`\`\`", "", text_value)

    match = re.search(r"\{.*\}", text_value, re.DOTALL)

    if not match:
        return {}

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def find_user(db: Session, user_id: int):
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    return user


# ==========================================
# ROOT AND DATABASE HEALTH DIAGNOSTIC
# ==========================================

@app.get("/")
def root():
    return {
        "message": "NutriTrack API is running!",
        "version": "1.2.0"
    }


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        database_type = engine.dialect.name

        if database_type == "postgresql":
            result = db.execute(
                text("""
                    SELECT
                        current_database() AS database_name,
                        current_schema() AS schema_name
                """)
            ).mappings().one()

            database_name = result["database_name"]
            schema_name = result["schema_name"]

        elif database_type == "sqlite":
            result = db.execute(
                text("PRAGMA database_list")
            ).fetchone()

            database_name = result[2] if result else "unknown"
            schema_name = "main"

        else:
            database_name = "unknown"
            schema_name = "unknown"

        inspector = inspect(engine)

        if database_type == "postgresql":
            tables = inspector.get_table_names(schema="public")
        else:
            tables = inspector.get_table_names()

        users_count = None

        if "users" in tables:
            users_count = db.query(User).count()

        return {
            "status": "healthy",
            "database_type": database_type,
            "database_name": database_name,
            "schema": schema_name,
            "tables": tables,
            "users_table_exists": "users" in tables,
            "registered_users": users_count
        }

    except Exception as error:
        db.rollback()

        print("DATABASE HEALTH CHECK ERROR:", str(error))

        raise HTTPException(
            status_code=503,
            detail="Database connection or diagnostic query failed."
        )


# ==========================================
# REGISTER USER
# ==========================================

@app.post("/auth/register")
def register_user(
    user: UserCreate,
    db: Session = Depends(get_db)
):

    email = str(user.email).strip().lower()

    if db.query(User).filter(User.email == email).first():
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
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
        "access_token": create_access_token(new_user.id),
        "token_type": "bearer",
        "user": user_profile_response(new_user),
    }


# ==========================================
# LOGIN USER
# ==========================================

@app.post("/auth/login")
def login_user(
    login: UserLogin,
    db: Session = Depends(get_db)
):

    email = str(login.email).strip().lower()

    user = db.query(User).filter(User.email == email).first()

    if not user or not verify_password(
        login.password,
        user.password_hash or ""
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    return {
        "message": "Login successful",
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "user": user_profile_response(user),
    }


# ==========================================
# GET USER PROFILE
# ==========================================

@app.get("/users/{user_id}")
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_owner(user_id, current_user)

    return user_profile_response(find_user(db, user_id))


# ==========================================
# UPDATE PROFILE AND RECALCULATE TARGET
# ==========================================

@app.put("/users/{user_id}/profile")
def update_user_profile(
    user_id: int,
    profile: UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    require_owner(user_id, current_user)

    user = find_user(db, user_id)

    gender = profile.gender.strip().lower()
    activity_level = profile.activity_level.strip().lower()
    weight_goal = profile.weight_goal.strip().lower()

    if gender not in {"male", "female", "m", "f", "man", "woman"}:
        raise HTTPException(
            status_code=400,
            detail="Sex must be male or female for this calorie equation."
        )

    if activity_level not in ACTIVITY_MULTIPLIERS:
        raise HTTPException(
            status_code=400,
            detail="Invalid activity level"
        )

    if weight_goal not in VALID_WEIGHT_GOALS:
        raise HTTPException(
            status_code=400,
            detail="Weight goal must be lose, maintain, or gain"
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
    current_user: User = Depends(get_current_user),
):

    require_owner(user_id, current_user)

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
def create_food(
    food: FoodCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

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
# ==========================================

@app.get("/foods/search")
async def search_food(
    name: str,
    db: Session = Depends(get_db)
):
    """Search local foods first, then use Gemini for an estimate."""

    search_text = name.strip()

    if not search_text:
        return []

    normalized = search_text.lower()

    foods = (
        db.query(Food)
        .filter(Food.name.ilike(f"%{normalized}%"))
        .all()
    )

    if foods:
        return foods

    local_matches = []

    for key, food in MALAYSIAN_FOODS.items():
        if normalized in key or key in normalized:
            local_matches.append({
                **food,
                "source": "NutriTrack food database"
            })

    if local_matches:
        return local_matches

    return [await estimate_food_from_text(search_text)]


# ==========================================
# CREATE FOOD LOG
# ==========================================

@app.post("/food-logs")
def create_food_log(
    log: FoodLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    require_owner(log.user_id, current_user)
    find_user(db, log.user_id)

    food = db.query(Food).filter(
        Food.id == log.food_id
    ).first()

    if not food:
        raise HTTPException(
            status_code=404,
            detail="Food not found"
        )

    if log.quantity <= 0:
        raise HTTPException(
            status_code=400,
            detail="Quantity must be greater than 0"
        )

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
# GET FOOD LOGS - TODAY ONLY BY DEFAULT
# ==========================================

@app.get("/food-logs/{user_id}")
def get_food_logs(
    user_id: int,
    date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    require_owner(user_id, current_user)
    find_user(db, user_id)

    # If a date is supplied, use it.
    # Otherwise, automatically use today's Malaysia date.
    if date:
        try:
            selected_date = datetime.strptime(
                date,
                "%Y-%m-%d"
            ).date()

        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid date format. Please use YYYY-MM-DD."
            )

    else:
        selected_date = get_malaysia_today()

    logs = (
        db.query(FoodLog)
        .filter(FoodLog.user_id == user_id)
        .order_by(FoodLog.created_at.desc())
        .all()
    )

    result = []

    for log in logs:

        # Ignore logs without a timestamp.
        if not log.created_at:
            continue

        malaysia_created_at = convert_to_malaysia_time(
            log.created_at
        )

        # IMPORTANT:
        # Only show food logs belonging to the selected Malaysia date.
        if malaysia_created_at.date() != selected_date:
            continue

        food = db.query(Food).filter(
            Food.id == log.food_id
        ).first()

        result.append({
            "id": log.id,
            "user_id": log.user_id,
            "food_id": log.food_id,
            "meal_type": log.meal_type,
            "quantity": log.quantity,
            "calories": log.calories,
            "created_at": malaysia_created_at.isoformat(),

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
def delete_food_log(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    log = db.query(FoodLog).filter(
        FoodLog.id == log_id
    ).first()

    if not log:
        raise HTTPException(
            status_code=404,
            detail="Food log not found"
        )

    # Ensure users can only delete their own records.
    require_owner(log.user_id, current_user)

    db.delete(log)
    db.commit()

    return {
        "message": "Food log deleted successfully"
    }


# ==========================================
# DASHBOARD - TODAY ONLY
# ==========================================

@app.get("/dashboard/{user_id}")
def dashboard(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    require_owner(user_id, current_user)

    user = find_user(db, user_id)

    today = get_malaysia_today()

    logs = (
        db.query(FoodLog)
        .filter(FoodLog.user_id == user_id)
        .all()
    )

    # Only today's food records are included in dashboard calculations.
    today_logs = [
        log for log in logs
        if is_log_on_date(log, today)
    ]

    consumed = sum(
        log.calories or 0
        for log in today_logs
    )

    meals = {
        "breakfast": 0,
        "lunch": 0,
        "dinner": 0,
        "snacks": 0
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
        100
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
            "weight_goal": getattr(
                user,
                "weight_goal",
                "maintain"
            ) or "maintain",
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
# AI FOOD ANALYSIS - GOOGLE GEMINI
# ==========================================

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.5-flash-lite"
)

GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY",
    ""
).strip()


# ==========================================
# GEMINI TEXT FOOD ESTIMATION
# ==========================================

async def estimate_food_from_text(food_query: str):
    """Estimate nutrition for a text food search using Google Gemini."""

    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Gemini API key is not configured. Add GEMINI_API_KEY to the backend .env file."
        )

    prompt = f"""You are a nutrition estimation assistant for a calorie tracker used in Malaysia.
Estimate the nutrition for this food: {food_query!r}.
Use a realistic, typical single serving. Prefer Malaysian/Asian food context when relevant.
If the query describes a meal with several components, estimate the combined meal.
Do not invent brand-specific official nutrition facts. These are estimates, not verified values.
If the food is ambiguous, choose the most common interpretation and state the assumed serving clearly.

Return ONLY valid JSON with exactly these fields:
{{
  "food_name": "clear food name",
  "serving_size": "typical serving with quantity",
  "calories": 0,
  "protein": 0,
  "carbohydrates": 0,
  "fat": 0,
  "confidence": 0.0
}}
Calories are kcal; protein, carbohydrates and fat are grams. All values must be numeric and non-negative.
Confidence must be between 0 and 1. No markdown or extra text."""

    try:
        client = genai.Client(
            api_key=GEMINI_API_KEY
        )

        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2
            ),
        )

    except Exception as error:

        error_text = str(error)

        print(
            "Gemini text food-search error:",
            error_text
        )

        if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
            raise HTTPException(
                status_code=429,
                detail="Gemini API quota or rate limit reached. Please try again later."
            )

        if "API_KEY_INVALID" in error_text or "invalid api key" in error_text.lower():
            raise HTTPException(
                status_code=502,
                detail="Gemini rejected the API key. Check GEMINI_API_KEY in your backend .env file."
            )

        raise HTTPException(
            status_code=502,
            detail="Gemini could not estimate this food. Please try again."
        )

    ai_data = clean_ai_json(
        getattr(response, "text", None) or ""
    )

    if not ai_data:
        raise HTTPException(
            status_code=502,
            detail="Gemini returned nutrition data that could not be read. Please try again."
        )

    food_name = ai_data.get("food_name")
    serving_size = ai_data.get("serving_size")

    if not isinstance(food_name, str) or not food_name.strip():
        food_name = food_query.strip().title()

    if not isinstance(serving_size, str) or not serving_size.strip():
        serving_size = "1 serving (estimated)"

    calories = max(
        0,
        clean_number(ai_data.get("calories"))
    )

    protein = max(
        0,
        clean_number(ai_data.get("protein"))
    )

    carbohydrates = max(
        0,
        clean_number(ai_data.get("carbohydrates"))
    )

    fat = max(
        0,
        clean_number(ai_data.get("fat"))
    )

    if calories <= 0:
        raise HTTPException(
            status_code=502,
            detail="Gemini did not return a valid calorie estimate. Please try a more specific food name."
        )

    confidence = clean_number(
        ai_data.get("confidence")
    )

    if confidence <= 1:
        confidence *= 100

    return {
        "name": food_name.strip(),
        "serving_size": serving_size.strip(),
        "calories": calories,
        "protein": protein,
        "carbohydrates": carbohydrates,
        "fat": fat,
        "confidence": min(max(confidence, 0), 100),
        "source": f"Google Gemini ({GEMINI_MODEL})",
        "disclaimer": "AI nutrition estimate for a typical serving. Actual values vary by recipe and portion size.",
    }


# ==========================================
# GEMINI IMAGE FOOD ANALYSIS
# ==========================================

@app.post("/ai/analyze-food")
async def analyze_food(
    image: UploadFile = File(...)
):

    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="Please upload an image file"
        )

    image_bytes = await image.read()

    if not image_bytes:
        raise HTTPException(
            status_code=400,
            detail="Uploaded image is empty"
        )

    max_image_bytes = 12 * 1024 * 1024

    if len(image_bytes) > max_image_bytes:
        raise HTTPException(
            status_code=413,
            detail="Image is too large. Please choose a photo smaller than 12 MB."
        )

    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Gemini API key is not configured. Add GEMINI_API_KEY to the backend .env file."
        )

    prompt = """
You are a food recognition and nutrition estimation assistant for a calorie tracker.
Identify the food shown in the image. Prefer Malaysian and Asian food names when appropriate.
Estimate the visible portion, not an ideal restaurant serving. If several foods are visible,
estimate the main meal as one combined serving and explain the portion in serving_size.
Do not claim exact nutritional accuracy from an image; make a reasonable estimate.

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
Calories are kcal. Protein, carbohydrates and fat are grams.
All nutrition values must be numeric and non-negative.
Confidence must be a number from 0 to 1.
Do not include markdown or explanations outside the JSON.
"""

    try:
        client = genai.Client(
            api_key=GEMINI_API_KEY
        )

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

        print(
            "Gemini API error:",
            error_text
        )

        if "API_KEY_INVALID" in error_text or "invalid api key" in error_text.lower():
            raise HTTPException(
                status_code=502,
                detail="Gemini rejected the API key. Check GEMINI_API_KEY in your .env file."
            )

        if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
            raise HTTPException(
                status_code=429,
                detail="Gemini API quota or rate limit reached. Please try again later."
            )

        raise HTTPException(
            status_code=502,
            detail="Gemini could not analyse this image. Please try again with a clearer photo."
        )

    raw_response = getattr(
        response,
        "text",
        None
    )

    if not raw_response or not raw_response.strip():
        raise HTTPException(
            status_code=502,
            detail="Gemini returned an empty response. Please try again."
        )

    ai_data = clean_ai_json(raw_response)

    if not ai_data:
        raise HTTPException(
            status_code=502,
            detail="The Gemini response could not be read as nutrition data. Please try again."
        )

    food_name = ai_data.get(
        "food_name",
        "Unknown Food"
    )

    serving_size = ai_data.get(
        "serving_size",
        "1 serving"
    )

    if isinstance(food_name, (dict, list)) or not str(food_name).strip():
        food_name = "Unknown Food"

    if isinstance(serving_size, (dict, list)) or not str(serving_size).strip():
        serving_size = "1 serving"

    confidence = clean_number(
        ai_data.get("confidence")
    )

    if confidence <= 1:
        confidence *= 100

    return {
        "food_name": str(food_name),
        "serving_size": str(serving_size),
        "calories": max(
            0,
            clean_number(ai_data.get("calories"))
        ),
        "protein": max(
            0,
            clean_number(ai_data.get("protein"))
        ),
        "carbohydrates": max(
            0,
            clean_number(ai_data.get("carbohydrates"))
        ),
        "fat": max(
            0,
            clean_number(ai_data.get("fat"))
        ),
        "confidence": min(
            max(confidence, 0),
            100
        ),
        "source": f"Google Gemini ({GEMINI_MODEL})",
    }
