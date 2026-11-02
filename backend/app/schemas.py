
from pydantic import BaseModel, EmailStr, Field


# ==========================================
# FOOD
# ==========================================

class FoodCreate(BaseModel):
    name: str
    serving_size: str
    calories: float = Field(ge=0, le=10000)
    protein: float = Field(default=0, ge=0)
    carbohydrates: float = Field(default=0, ge=0)
    fat: float = Field(default=0, ge=0)


# ==========================================
# FOOD LOG
# ==========================================

class FoodLogCreate(BaseModel):
    user_id: int
    food_id: int
    meal_type: str
    quantity: float = Field(default=1, gt=0, le=100)


# ==========================================
# USER REGISTRATION
# ==========================================

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=6)
    age: int = Field(gt=0, lt=120)
    gender: str
    weight: float = Field(gt=0, lt=500)
    height: float = Field(gt=0, lt=300)
    activity_level: str


# ==========================================
# USER LOGIN
# ==========================================

class UserLogin(BaseModel):
    email: EmailStr
    password: str


# ==========================================
# UPDATE USER PROFILE
# ==========================================

class UserProfileUpdate(BaseModel):
    age: int = Field(gt=0, lt=120)
    gender: str
    weight: float = Field(gt=0, lt=500)
    height: float = Field(gt=0, lt=300)
    activity_level: str
    weight_goal: str = Field(
        default="maintain",
        pattern="^(lose|maintain|gain)$"
    )


# ==========================================
# CALORIE GOAL
# ==========================================

class CalorieGoalUpdate(BaseModel):
    calorie_goal: float = Field(gt=0, le=10000)
