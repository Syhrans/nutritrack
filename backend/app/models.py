
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
)
from sqlalchemy.sql import func

from .database import Base


# ==========================================
# FOOD TABLE
# ==========================================

class Food(Base):
    __tablename__ = "foods"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    name = Column(
        String,
        nullable=False,
    )

    serving_size = Column(
        String,
        nullable=False,
    )

    calories = Column(
        Float,
        nullable=False,
    )

    protein = Column(
        Float,
        default=0,
    )

    carbohydrates = Column(
        Float,
        default=0,
    )

    fat = Column(
        Float,
        default=0,
    )


# ==========================================
# USER TABLE
# ==========================================

class User(Base):
    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    name = Column(
        String,
        nullable=False,
    )

    email = Column(
        String,
        unique=True,
        nullable=False,
        index=True,
    )

    # Secure password hash
    password_hash = Column(
        String,
        nullable=True,
    )

    age = Column(
        Integer,
        nullable=False,
    )

    gender = Column(
        String,
        nullable=False,
    )

    weight = Column(
        Float,
        nullable=False,
    )

    height = Column(
        Float,
        nullable=False,
    )

    activity_level = Column(
        String,
        nullable=False,
    )

    # Weight goal: lose, maintain, or gain
    weight_goal = Column(
        String,
        nullable=False,
        default="maintain",
        server_default="maintain",
    )

    # Personalized daily calorie target
    daily_calorie_goal = Column(
        Float,
        nullable=False,
    )


# ==========================================
# FOOD LOG TABLE
# ==========================================

class FoodLog(Base):
    __tablename__ = "food_logs"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )

    food_id = Column(
        Integer,
        ForeignKey("foods.id"),
        nullable=False,
    )

    meal_type = Column(
        String,
        nullable=False,
    )

    quantity = Column(
        Float,
        default=1,
    )

    calories = Column(
        Float,
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
