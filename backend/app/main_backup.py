from fastapi import FastAPI, Depends, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text

from datetime import datetime, timezone, timedelta

import httpx
import base64
import json
import re
import hashlib
import hmac
import secrets

from .database import Base, engine, get_db
from .models import Food, FoodLog, User
from .schemas import (
    FoodCreate,
    FoodLogCreate,
    UserCreate,
    UserLogin,
    CalorieGoalUpdate,
)


# ==========================================
# DATABASE
# ==========================================

Base.metadata.create_all(bind=engine)


# ==========================================
# DATABASE MIGRATION
# ==========================================

def ensure_database_columns():
    """
    Add new database columns to existing databases
    when required.

    This is needed because SQLAlchemy create_all()
    does not automatically add new columns to an
    existing table.
    """

    inspector = inspect(engine)

    try:
        user_columns = [
            column["name"]
            for column in inspector.get_columns("users")
        ]

        if "password_hash" not in user_columns:

            with engine.begin() as connection:

                connection.execute(
                    text(
                        "ALTER TABLE users "
                        "ADD COLUMN password_hash VARCHAR"
                    )
                )

    except Exception as error:

        print(
            "Database migration warning:",
            error
        )


ensure_database_columns()


# ==========================================
# FASTAPI APP
# ==========================================

app = FastAPI(
    title="Calorie Tracker API",
    description="AI-powered calorie tracking application",
    version="1.0.0"
)


# ==========================================
# CORS
# ==========================================

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
# MALAYSIA TIMEZONE
# ==========================================

MALAYSIA_TIMEZONE = timezone(
    timedelta(hours=8)
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
    """
    Securely hash a password using PBKDF2-HMAC-SHA256.
    """

    salt = secrets.token_bytes(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        310000
    )

    return (
        "pbkdf2_sha256$"
        + salt.hex()
        + "$"
        + password_hash.hex()
    )


def verify_password(
    password: str,
    stored_hash: str
) -> bool:
    """
    Verify a password against its stored hash.
    """

    if not stored_hash:
        return False

    try:

        parts = stored_hash.split("$")

        if len(parts) != 3:
            return False

        algorithm = parts[0]
        salt_hex = parts[1]
        hash_hex = parts[2]

        if algorithm != "pbkdf2_sha256":
            return False

        salt = bytes.fromhex(
            salt_hex
        )

        expected_hash = bytes.fromhex(
            hash_hex
        )

        actual_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            310000
        )

        return hmac.compare_digest(
            actual_hash,
            expected_hash
        )

    except Exception:

        return False


# ==========================================
# CALORIE GOAL CALCULATION
# ==========================================

def calculate_daily_calorie_goal(
    age: int,
    gender: str,
    weight: float,
    height: float,
    activity_level: str
):
    """
    Calculate an estimated daily calorie goal
    using the Mifflin-St Jeor equation.
    """

    gender_text = (
        gender.strip().lower()
        if gender
        else ""
    )

    activity_text = (
        activity_level.strip().lower()
        if activity_level
        else "moderate"
    )

    # ------------------------------------------
    # BMR
    # ------------------------------------------

    if gender_text in [
        "male",
        "m",
        "man"
    ]:

        bmr = (
            10 * weight
            + 6.25 * height
            - 5 * age
            + 5
        )

    else:

        bmr = (
            10 * weight
            + 6.25 * height
            - 5 * age
            - 161
        )

    # ------------------------------------------
    # Activity multiplier
    # ------------------------------------------

    activity_multipliers = {

        "sedentary": 1.2,

        "light": 1.375,

        "lightly active": 1.375,

        "moderate": 1.55,

        "moderately active": 1.55,

        "active": 1.725,

        "very active": 1.725,

        "extra active": 1.9,
    }

    multiplier = activity_multipliers.get(
        activity_text,
        1.55
    )

    calorie_goal = (
        bmr * multiplier
    )

    return round(
        calorie_goal,
        0
    )


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def clean_number(value, default=0):
    """
    Convert a value into a number safely.
    """

    if value is None:
        return default

    if isinstance(
        value,
        (int, float)
    ):
        return value

    try:

        text_value = str(value)

        match = re.search(
            r"-?\d+(?:\.\d+)?",
            text_value
        )

        if match:

            return float(
                match.group()
            )

    except Exception:

        pass

    return default


def clean_ai_json(text_value):
    """
    Clean Ollama response and extract JSON.
    """

    if not text_value:

        return {}

    text_value = text_value.strip()

    text_value = re.sub(
        r"```json",
        "",
        text_value,
        flags=re.IGNORECASE
    )

    text_value = re.sub(
        r"```",
        "",
        text_value
    )

    match = re.search(
        r"\{.*\}",
        text_value,
        re.DOTALL
    )

    if not match:

        return {}

    json_text = match.group(0)

    try:

        return json.loads(
            json_text
        )

    except json.JSONDecodeError:

        return {}


def convert_to_malaysia_time(
    created_at
):
    """
    Convert database datetime into Malaysia time.
    """

    if not created_at:

        return None

    if created_at.tzinfo is None:

        created_at = created_at.replace(
            tzinfo=timezone.utc
        )

    return created_at.astimezone(
        MALAYSIA_TIMEZONE
    )


# ==========================================
# ROOT
# ==========================================

@app.get("/")
def root():

    return {
        "message": "Calorie Tracker API is running!"
    }


# ==========================================
# HEALTH CHECK
# ==========================================

@app.get("/health")
def health():

    return {
        "status": "healthy"
    }


# ==========================================
# REGISTER USER
# ==========================================

@app.post("/auth/register")
def register_user(
    user: UserCreate,
    db: Session = Depends(get_db)
):
    """
    Register a new user account.
    """

    email = (
        str(user.email)
        .strip()
        .lower()
    )

    existing_user = (
        db.query(User)
        .filter(
            User.email == email
        )
        .first()
    )

    if existing_user:

        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    if user.age <= 0:

        raise HTTPException(
            status_code=400,
            detail="Age must be greater than 0"
        )

    if user.weight <= 0:

        raise HTTPException(
            status_code=400,
            detail="Weight must be greater than 0"
        )

    if user.height <= 0:

        raise HTTPException(
            status_code=400,
            detail="Height must be greater than 0"
        )

    if not user.password:

        raise HTTPException(
            status_code=400,
            detail="Password is required"
        )

    daily_calorie_goal = (
        calculate_daily_calorie_goal(
            age=user.age,
            gender=user.gender,
            weight=user.weight,
            height=user.height,
            activity_level=user.activity_level
        )
    )

    password_hash = hash_password(
        user.password
    )

    new_user = User(

        name=user.name.strip(),

        email=email,

        password_hash=password_hash,

        age=user.age,

        gender=user.gender.strip(),

        weight=user.weight,

        height=user.height,

        activity_level=user.activity_level.strip(),

        daily_calorie_goal=daily_calorie_goal,
    )

    db.add(new_user)

    db.commit()

    db.refresh(new_user)

    return {

        "message": "Registration successful",

        "user": {

            "id": new_user.id,

            "name": new_user.name,

            "email": new_user.email,

            "age": new_user.age,

            "gender": new_user.gender,

            "weight": new_user.weight,

            "height": new_user.height,

            "activity_level": (
                new_user.activity_level
            ),

            "daily_calorie_goal": (
                new_user.daily_calorie_goal
            ),
        }
    }


# ==========================================
# LOGIN USER
# ==========================================

@app.post("/auth/login")
def login_user(
    login: UserLogin,
    db: Session = Depends(get_db)
):
    """
    Login using email and password.
    """

    email = (
        str(login.email)
        .strip()
        .lower()
    )

    user = (
        db.query(User)
        .filter(
            User.email == email
        )
        .first()
    )

    if not user:

        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    if not user.password_hash:

        raise HTTPException(
            status_code=400,
            detail=(
                "This existing account does not "
                "have a password yet. Please create "
                "a new account or set a password."
            )
        )

    if not verify_password(
        login.password,
        user.password_hash
    ):

        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    return {

        "message": "Login successful",

        "user": {

            "id": user.id,

            "name": user.name,

            "email": user.email,

            "age": user.age,

            "gender": user.gender,

            "weight": user.weight,

            "height": user.height,

            "activity_level": (
                user.activity_level
            ),

            "daily_calorie_goal": (
                user.daily_calorie_goal
            ),
        }
    }


# ==========================================
# CREATE USER
# ==========================================

@app.post("/users")
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db)
):

    email = (
        str(user.email)
        .strip()
        .lower()
    )

    existing_user = (
        db.query(User)
        .filter(
            User.email == email
        )
        .first()
    )

    if existing_user:

        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    daily_calorie_goal = (
        calculate_daily_calorie_goal(
            age=user.age,
            gender=user.gender,
            weight=user.weight,
            height=user.height,
            activity_level=user.activity_level
        )
    )

    new_user = User(

        name=user.name.strip(),

        email=email,

        password_hash=hash_password(
            user.password
        ),

        age=user.age,

        gender=user.gender.strip(),

        weight=user.weight,

        height=user.height,

        activity_level=user.activity_level.strip(),

        daily_calorie_goal=daily_calorie_goal,
    )

    db.add(new_user)

    db.commit()

    db.refresh(new_user)

    return {

        "id": new_user.id,

        "name": new_user.name,

        "email": new_user.email,

        "age": new_user.age,

        "gender": new_user.gender,

        "weight": new_user.weight,

        "height": new_user.height,

        "activity_level": (
            new_user.activity_level
        ),

        "daily_calorie_goal": (
            new_user.daily_calorie_goal
        ),
    }


# ==========================================
# GET USER
# ==========================================

@app.get("/users/{user_id}")
def get_user(
    user_id: int,
    db: Session = Depends(get_db)
):

    user = (
        db.query(User)
        .filter(
            User.id == user_id
        )
        .first()
    )

    if not user:

        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    return {

        "id": user.id,

        "name": user.name,

        "email": user.email,

        "age": user.age,

        "gender": user.gender,

        "weight": user.weight,

        "height": user.height,

        "activity_level": (
            user.activity_level
        ),

        "daily_calorie_goal": (
            user.daily_calorie_goal
        ),
    }


# ==========================================
# UPDATE DAILY CALORIE GOAL
# ==========================================

@app.put("/users/{user_id}/calorie-goal")
def update_calorie_goal(
    user_id: int,
    goal_data: CalorieGoalUpdate,
    db: Session = Depends(get_db)
):

    user = (
        db.query(User)
        .filter(
            User.id == user_id
        )
        .first()
    )

    if not user:

        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    user.daily_calorie_goal = (
        goal_data.calorie_goal
    )

    db.commit()

    db.refresh(user)

    return {

        "message": (
            "Daily calorie goal updated successfully"
        ),

        "user_id": user.id,

        "daily_calorie_goal": (
            user.daily_calorie_goal
        ),
    }


# ==========================================
# CREATE FOOD
# ==========================================

@app.post("/foods")
def create_food(
    food: FoodCreate,
    db: Session = Depends(get_db)
):

    food_data = food.model_dump()

    name = food_data.get(
        "name",
        "Unknown Food"
    )

    serving_size = food_data.get(
        "serving_size",
        "1 serving"
    )

    calories = clean_number(
        food_data.get("calories")
    )

    protein = clean_number(
        food_data.get("protein")
    )

    carbohydrates = clean_number(
        food_data.get("carbohydrates")
    )

    fat = clean_number(
        food_data.get("fat")
    )

    new_food = Food(

        name=name,

        serving_size=serving_size,

        calories=calories,

        protein=protein,

        carbohydrates=carbohydrates,

        fat=fat,
    )

    db.add(new_food)

    db.commit()

    db.refresh(new_food)

    return new_food


# ==========================================
# GET ALL FOODS
# ==========================================

@app.get("/foods")
def get_foods(
    db: Session = Depends(get_db)
):

    foods = (
        db.query(Food)
        .order_by(
            Food.name
        )
        .all()
    )

    return foods


# ==========================================
# SEARCH FOOD
# ==========================================

@app.get("/foods/search")
def search_food(
    name: str,
    db: Session = Depends(get_db)
):

    search_text = (
        name.strip().lower()
    )

    foods = (
        db.query(Food)
        .filter(
            Food.name.ilike(
                f"%{search_text}%"
            )
        )
        .all()
    )

    if foods:

        return foods

    results = []

    for key, food in MALAYSIAN_FOODS.items():

        if (
            search_text in key
            or key in search_text
        ):

            results.append(food)

    return results


# ==========================================
# CREATE FOOD LOG
# ==========================================

@app.post("/food-logs")
def create_food_log(
    log: FoodLogCreate,
    db: Session = Depends(get_db)
):

    user = (
        db.query(User)
        .filter(
            User.id == log.user_id
        )
        .first()
    )

    if not user:

        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    food = (
        db.query(Food)
        .filter(
            Food.id == log.food_id
        )
        .first()
    )

    if not food:

        raise HTTPException(
            status_code=404,
            detail="Food not found"
        )

    quantity = (
        log.quantity
        if log.quantity
        else 1
    )

    if quantity <= 0:

        raise HTTPException(
            status_code=400,
            detail=(
                "Quantity must be greater than 0"
            )
        )

    total_calories = (
        food.calories * quantity
    )

    new_log = FoodLog(

        user_id=log.user_id,

        food_id=log.food_id,

        meal_type=log.meal_type,

        quantity=quantity,

        calories=total_calories,
    )

    db.add(new_log)

    db.commit()

    db.refresh(new_log)

    return new_log


# ==========================================
# GET FOOD LOGS
# ==========================================

@app.get("/food-logs/{user_id}")
def get_food_logs(
    user_id: int,
    db: Session = Depends(get_db)
):

    user = (
        db.query(User)
        .filter(
            User.id == user_id
        )
        .first()
    )

    if not user:

        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    logs = (
        db.query(FoodLog)
        .filter(
            FoodLog.user_id == user_id
        )
        .order_by(
            FoodLog.created_at.desc()
        )
        .all()
    )

    result = []

    for log in logs:

        food = (
            db.query(Food)
            .filter(
                Food.id == log.food_id
            )
            .first()
        )

        created_at_malaysia = (
            convert_to_malaysia_time(
                log.created_at
            )
        )

        result.append({

            "id": log.id,

            "user_id": log.user_id,

            "food_id": log.food_id,

            "meal_type": log.meal_type,

            "quantity": log.quantity,

            "calories": log.calories,

            "created_at": (
                created_at_malaysia.isoformat()
                if created_at_malaysia
                else None
            ),

            "food": {

                "id": (
                    food.id
                    if food
                    else None
                ),

                "name": (
                    food.name
                    if food
                    else "Unknown Food"
                ),

                "serving_size": (
                    food.serving_size
                    if food
                    else "1 serving"
                ),

                "calories": (
                    food.calories
                    if food
                    else 0
                ),

                "protein": (
                    food.protein
                    if food
                    else 0
                ),

                "carbohydrates": (
                    food.carbohydrates
                    if food
                    else 0
                ),

                "fat": (
                    food.fat
                    if food
                    else 0
                ),
            }
        })

    return result


# ==========================================
# DELETE FOOD LOG
# ==========================================

@app.delete("/food-logs/{log_id}")
def delete_food_log(
    log_id: int,
    db: Session = Depends(get_db)
):

    log = (
        db.query(FoodLog)
        .filter(
            FoodLog.id == log_id
        )
        .first()
    )

    if not log:

        raise HTTPException(
            status_code=404,
            detail="Food log not found"
        )

    db.delete(log)

    db.commit()

    return {
        "message": (
            "Food log deleted successfully"
        )
    }


# ==========================================
# DASHBOARD - TODAY ONLY
# ==========================================

@app.get("/dashboard/{user_id}")
def dashboard(
    user_id: int,
    db: Session = Depends(get_db)
):

    user = (
        db.query(User)
        .filter(
            User.id == user_id
        )
        .first()
    )

    if not user:

        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    now_malaysia = datetime.now(
        MALAYSIA_TIMEZONE
    )

    today = now_malaysia.date()

    logs = (
        db.query(FoodLog)
        .filter(
            FoodLog.user_id == user_id
        )
        .all()
    )

    today_logs = []

    for log in logs:

        if not log.created_at:

            continue

        created_at = log.created_at

        if created_at.tzinfo is None:

            created_at = created_at.replace(
                tzinfo=timezone.utc
            )

        created_at_malaysia = (
            created_at.astimezone(
                MALAYSIA_TIMEZONE
            )
        )

        if (
            created_at_malaysia.date()
            == today
        ):

            today_logs.append(log)

    consumed = sum(
        log.calories or 0
        for log in today_logs
    )

    breakfast = 0
    lunch = 0
    dinner = 0
    snacks = 0

    for log in today_logs:

        calories = log.calories or 0

        meal = (
            log.meal_type.strip().lower()
            if log.meal_type
            else ""
        )

        if meal == "breakfast":

            breakfast += calories

        elif meal == "lunch":

            lunch += calories

        elif meal == "dinner":

            dinner += calories

        elif meal in [
            "snack",
            "snacks"
        ]:

            snacks += calories

    goal = (
        user.daily_calorie_goal
        or 0
    )

    remaining = max(
        goal - consumed,
        0
    )

    if goal > 0:

        progress = (
            consumed / goal
        ) * 100

    else:

        progress = 0

    progress = min(
        max(progress, 0),
        100
    )

    return {

        "date": str(today),

        "user": {

            "id": user.id,

            "name": user.name,

            "daily_calorie_goal": goal,
        },

        "calories": {

            "goal": goal,

            "consumed": consumed,

            "remaining": remaining,

            "progress": round(
                progress,
                1
            ),
        },

        "meals": {

            "breakfast": breakfast,

            "lunch": lunch,

            "dinner": dinner,

            "snacks": snacks,
        }
    }


# ==========================================
# AI FOOD ANALYSIS
# ==========================================

@app.post("/ai/analyze-food")
async def analyze_food(
    image: UploadFile = File(...)
):
    """
    Analyze a food image using Ollama Qwen3-VL.

    The request is intentionally optimized for a local 4B model:
    - no streaming
    - thinking disabled
    - limited output tokens
    - limited image size
    - explicit timeout
    """

    if not image.content_type:
        raise HTTPException(
            status_code=400,
            detail="Image content type is missing"
        )

    if not image.content_type.startswith("image/"):
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

    # Keep very large phone/camera uploads from making local vision
    # inference unnecessarily slow. This is a safety limit rather
    # than an image-quality requirement.
    max_image_bytes = 12 * 1024 * 1024

    if len(image_bytes) > max_image_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                "Image is too large. Please choose a photo "
                "smaller than 12 MB."
            )
        )

    image_base64 = base64.b64encode(
        image_bytes
    ).decode("utf-8")

    prompt = """
You are a food nutrition analysis assistant.

Look at the food in the image and identify the most likely food.
Prefer Malaysian and Asian food names when appropriate.

Return ONLY one valid JSON object.
Do not use markdown.
Do not include explanations.
Do not include reasoning.

Use exactly this structure:

{
  "food_name": "name of food",
  "serving_size": "estimated visible serving",
  "calories": 0,
  "protein": 0,
  "carbohydrates": 0,
  "fat": 0,
  "confidence": 0
}

Rules:
- calories = estimated calories for the visible serving
- protein = grams
- carbohydrates = grams
- fat = grams
- confidence = number from 0 to 1
- Make a reasonable estimate if exact ingredients are not visible.
- Keep the answer concise.
"""

    ollama_url = (
        "http://127.0.0.1:11434/api/generate"
    )

    request_data = {
        "model": "qwen3-vl:4b",
        "prompt": prompt,
        "images": [
            image_base64
        ],
        "stream": False,

        # Keep the model loaded between requests to reduce cold-start time.
        "keep_alive": "10m",

        # Qwen3 models can spend significant time generating
        # reasoning. We only need the final nutrition result.
        "think": False,

        # Limit generation so the model cannot spend a long time
        # producing unnecessary text.
        "options": {
            "temperature": 0.1,
            "num_predict": 1024
        }
    }

    timeout = httpx.Timeout(
        connect=10.0,
        read=180.0,
        write=30.0,
        pool=10.0,
    )

    print(
        f"AI Food Scanner: received {image.filename or 'image'} "
        f"({len(image_bytes) / 1024 / 1024:.2f} MB)"
    )

    try:
        async with httpx.AsyncClient(
            timeout=timeout
        ) as client:

            response = await client.post(
                ollama_url,
                json=request_data
            )

            response.raise_for_status()

            ollama_result = response.json()

    except httpx.ConnectError:

        raise HTTPException(
            status_code=503,
            detail=(
                "Unable to connect to Ollama. "
                "Please make sure Ollama is running."
            )
        )

    except httpx.TimeoutException:

        raise HTTPException(
            status_code=504,
            detail=(
                "AI analysis timed out after 180 seconds. "
                "The local Qwen3-VL model took too long to "
                "analyze this image. Try a smaller or clearer photo."
            )
        )

    except httpx.HTTPStatusError as error:

        error_detail = (
            error.response.text
            if error.response is not None
            else str(error)
        )

        raise HTTPException(
            status_code=502,
            detail=f"Ollama returned an HTTP error: {error_detail}"
        )

    except httpx.HTTPError as error:

        raise HTTPException(
            status_code=502,
            detail=f"Ollama connection error: {str(error)}"
        )

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=f"AI analysis failed: {str(error)}"
        )

    raw_response = ollama_result.get(
        "response",
        ""
    )

    if isinstance(raw_response, dict):
        raw_response = json.dumps(
            raw_response,
            ensure_ascii=False
        )

    if not isinstance(raw_response, str):
        raw_response = str(raw_response)

    print(
        "AI Food Scanner raw response:",
        raw_response[:1000]
    )

    if not raw_response.strip():
        thinking_text = ollama_result.get("thinking", "")
        done_reason = ollama_result.get("done_reason", "unknown")
        print(
            "AI Food Scanner returned empty response. "
            f"done_reason={done_reason}; "
            f"thinking_length={len(thinking_text) if isinstance(thinking_text, str) else 0}"
        )
        raise HTTPException(
            status_code=502,
            detail=(
                "The AI model did not return a final answer. "
                "Please try again. If this continues, check the backend console "
                "for the done_reason and thinking_length diagnostics."
            )
        )

    ai_data = clean_ai_json(
        raw_response
    )

    if not ai_data:
        print(
            "AI Food Scanner could not parse JSON. "
            f"Raw response preview: {raw_response[:500]!r}"
        )
        raise HTTPException(
            status_code=502,
            detail=(
                "The AI returned text that could not be read as nutrition data. "
                "Please try again with a clear food photo."
            )
        )

    food_name = ai_data.get(
        "food_name",
        "Unknown Food"
    )

    serving_size = ai_data.get(
        "serving_size",
        "1 serving"
    )

    calories = clean_number(
        ai_data.get("calories")
    )

    protein = clean_number(
        ai_data.get("protein")
    )

    carbohydrates = clean_number(
        ai_data.get("carbohydrates")
    )

    fat = clean_number(
        ai_data.get("fat")
    )

    confidence = clean_number(
        ai_data.get("confidence")
    )

    if confidence <= 1:
        confidence = (
            confidence * 100
        )

    confidence = min(
        max(
            confidence,
            0
        ),
        100
    )

    # Prevent object/dictionary values from leaking into the
    # frontend as "[object Object]".
    if isinstance(food_name, (dict, list)):
        food_name = "Unknown Food"

    if isinstance(serving_size, (dict, list)):
        serving_size = "1 serving"

    return {
        "food_name": str(
            food_name
        ),

        "serving_size": str(
            serving_size
        ),

        "calories": calories,

        "protein": protein,

        "carbohydrates": carbohydrates,

        "fat": fat,

        "confidence": confidence,

        "source": (
            "Ollama Qwen3-VL 4B"
        ),
    }
