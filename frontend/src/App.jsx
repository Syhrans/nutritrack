
import { useCallback, useEffect, useState } from "react";
import "./App.css";

const API_URL = "http://127.0.0.1:8000";
const USER_ID = 1;
const MAX_IMAGE_SIZE = 10 * 1024 * 1024;

const MEALS = ["breakfast", "lunch", "dinner", "snacks"];

const DEFAULT_PROFILE = {
  age: 30,
  gender: "male",
  weight: 80,
  height: 175,
  activity_level: "moderate",
  weight_goal: "maintain",
};

async function api(path, options = {}) {
  const headers = { ...options.headers };

  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  let response;

  try {
    response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers,
    });
  } catch {
    throw new Error(
      "Cannot connect to the API. Make sure the FastAPI server is running."
    );
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;

    try {
      const body = await response.json();
      detail = body.detail || body.message || detail;

      if (typeof detail !== "string") {
        detail = JSON.stringify(detail);
      }
    } catch {
      // Use default error message.
    }

    throw new Error(detail);
  }

  if (response.status === 204) return null;
  return response.json();
}

function foodShape(food = {}) {
  return {
    ...food,
    name: String(
      food.name || food.food_name || food.detected_food || "Food"
    ),
    serving_size: String(
      food.serving_size || food.serving || "1 serving"
    ),
    calories: Number(food.calories ?? 0),
    protein: Number(food.protein ?? food.protein_g ?? 0),
    carbohydrates: Number(
      food.carbohydrates ?? food.carbs ?? food.carbs_g ?? 0
    ),
    fat: Number(food.fat ?? food.fat_g ?? 0),
  };
}

function foodId(food) {
  return food?.id ?? food?.food_id ?? null;
}

function formatNumber(value) {
  return Math.round(Number(value) || 0).toLocaleString();
}

function calculateBMI(weight, height) {
  const kg = Number(weight);
  const cm = Number(height);

  if (
    !Number.isFinite(kg) ||
    !Number.isFinite(cm) ||
    kg <= 0 ||
    cm <= 0
  ) {
    return null;
  }

  return kg / ((cm / 100) ** 2);
}

function bmiCategory(bmi) {
  if (bmi == null) return "Not available";
  if (bmi < 18.5) return "Underweight";
  if (bmi < 25) return "Normal weight";
  if (bmi < 30) return "Overweight";
  return "Obesity range";
}

// Convert backend activity names into the frontend select values.
function normalizeActivity(value) {
  const activity = String(value || "moderate")
    .toLowerCase()
    .replace(/[\s-]+/g, "_");

  if (activity === "lightly_active") return "light";
  if (activity === "moderately_active") return "moderate";
  if (activity === "very_active") return "very_active";
  if (activity === "extra_active") return "very_active";

  return activity;
}

// Remove duplicate food names while keeping the most complete record.
function removeDuplicateFoods(items) {
  const uniqueFoods = new Map();

  items.forEach((rawFood) => {
    const food = foodShape(rawFood);
    const key = food.name.trim().toLowerCase();

    if (!key) return;

    const completeness = [
      food.calories,
      food.protein,
      food.carbohydrates,
      food.fat,
    ].filter((value) => Number.isFinite(value) && value > 0).length;

    const existing = uniqueFoods.get(key);

    if (!existing || completeness > existing.completeness) {
      uniqueFoods.set(key, {
        food,
        completeness,
      });
    }
  });

  return Array.from(uniqueFoods.values()).map((item) => item.food);
}

function App() {
  const [dashboard, setDashboard] = useState(null);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState(null);
  const [meal, setMeal] = useState("breakfast");
  const [quantity, setQuantity] = useState("1");
  const [saving, setSaving] = useState(false);

  const [photo, setPhoto] = useState(null);
  const [preview, setPreview] = useState("");
  const [analysing, setAnalysing] = useState(false);
  const [photoExpanded, setPhotoExpanded] = useState(false);

  const [profile, setProfile] = useState(DEFAULT_PROFILE);
  const [profileLoading, setProfileLoading] = useState(true);
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileLoaded, setProfileLoaded] = useState(false);

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const [dashboardData, diaryData] = await Promise.all([
        api(`/dashboard/${USER_ID}`),
        api(`/food-logs/${USER_ID}`),
      ]);

      setDashboard(dashboardData);

      const diaryItems = Array.isArray(diaryData)
        ? diaryData
        : diaryData?.items ||
          diaryData?.food_logs ||
          diaryData?.data ||
          [];

      setLogs(Array.isArray(diaryItems) ? diaryItems : []);
    } catch (err) {
      console.error("Could not load dashboard or diary:", err);
      setError(`Could not load your dashboard or diary: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadProfile = useCallback(async () => {
    setProfileLoading(true);

    try {
      const data = await api(`/users/${USER_ID}`);

      setProfile({
        age: data.age ?? DEFAULT_PROFILE.age,
        gender: String(data.gender ?? DEFAULT_PROFILE.gender).toLowerCase(),
        weight: data.weight ?? DEFAULT_PROFILE.weight,
        height: data.height ?? DEFAULT_PROFILE.height,
        activity_level: normalizeActivity(data.activity_level),
        weight_goal: data.weight_goal ?? DEFAULT_PROFILE.weight_goal,
      });

      setProfileLoaded(true);
    } catch (err) {
      console.error("Could not load profile:", err);
      setError(`Could not load your profile: ${err.message}`);
    } finally {
      setProfileLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDashboard();
    loadProfile();
  }, [loadDashboard, loadProfile]);

  useEffect(() => {
    return () => {
      if (preview.startsWith("blob:")) {
        URL.revokeObjectURL(preview);
      }
    };
  }, [preview]);

  const user = dashboard?.user || {};
  const calorieData = dashboard?.calories || {};

  const goal = Number(
    calorieData.goal ?? user.daily_calorie_goal ?? 2000
  );

  const consumed = Number(
    calorieData.consumed ?? dashboard?.consumed_calories ?? 0
  );

  const remaining = Math.max(
    0,
    Number(calorieData.remaining ?? goal - consumed)
  );

  const percent =
    goal > 0 ? Math.min(100, (consumed / goal) * 100) : 0;

  const meals = dashboard?.meals || {};

  const bmi = calculateBMI(profile.weight, profile.height);
  const currentBmiCategory = bmiCategory(bmi);

  function updateProfile(field, value) {
    setProfile((previous) => ({
      ...previous,
      [field]: value,
    }));
  }

  async function saveProfile(event) {
    event.preventDefault();
    setError("");
    setMessage("");

    const age = Number(profile.age);
    const weight = Number(profile.weight);
    const height = Number(profile.height);

    if (
      !Number.isFinite(age) ||
      age < 1 ||
      age >= 120 ||
      !Number.isFinite(weight) ||
      weight <= 0 ||
      weight >= 500 ||
      !Number.isFinite(height) ||
      height <= 0 ||
      height >= 300
    ) {
      setError("Please enter a valid age, weight, and height.");
      return;
    }

    if (
      !["male", "female"].includes(profile.gender) ||
      !["sedentary", "light", "moderate", "active", "very_active"].includes(
        profile.activity_level
      ) ||
      !["lose", "maintain", "gain"].includes(profile.weight_goal)
    ) {
      setError("Please check your sex, activity level, and weight goal.");
      return;
    }

    setProfileSaving(true);

    try {
      const updated = await api(`/users/${USER_ID}/profile`, {
        method: "PUT",
        body: JSON.stringify({
          age,
          gender: profile.gender,
          weight,
          height,
          // Backend accepts "very active", not "very_active".
          activity_level:
            profile.activity_level === "very_active"
              ? "very active"
              : profile.activity_level,
          weight_goal: profile.weight_goal,
        }),
      });

      // Backend returns { message, user: {...} }.
      const updatedUser = updated.user || updated;

      setProfile({
        age: updatedUser.age ?? age,
        gender: String(
          updatedUser.gender ?? profile.gender
        ).toLowerCase(),
        weight: updatedUser.weight ?? weight,
        height: updatedUser.height ?? height,
        activity_level: normalizeActivity(
          updatedUser.activity_level ?? profile.activity_level
        ),
        weight_goal: updatedUser.weight_goal ?? profile.weight_goal,
      });

      setProfileLoaded(true);
      setMessage(
        "Your profile and daily calorie target have been updated."
      );

      await loadDashboard();
    } catch (err) {
      setError(`Could not save your profile: ${err.message}`);
    } finally {
      setProfileSaving(false);
    }
  }

  async function searchFood(event) {
    event?.preventDefault();

    if (!query.trim()) {
      setError("Enter a food name to search.");
      return;
    }

    setSearching(true);
    setError("");
    setMessage("");
    setResults([]);
    setSelected(null);

    try {
      const data = await api(
        `/foods/search?name=${encodeURIComponent(query.trim())}`
      );

      const list = Array.isArray(data)
        ? data
        : data?.results ||
          data?.foods ||
          data?.items ||
          (data ? [data] : []);

      const cleanedResults = removeDuplicateFoods(list);

      setResults(cleanedResults);

      if (!cleanedResults.length) {
        setMessage("No matching food found. Try another search.");
      }
    } catch (err) {
      setError(`Search failed: ${err.message}`);
    } finally {
      setSearching(false);
    }
  }

  function chooseFood(food) {
    setSelected(foodShape(food));
    setQuantity("1");
    setError("");
    setMessage("");

    document
      .getElementById("food-search")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function addToDiary(food = selected) {
    if (!food) return;

    const amount = Number(quantity);

    if (!Number.isFinite(amount) || amount <= 0) {
      setError("Quantity must be greater than zero.");
      return;
    }

    if (!Number.isFinite(food.calories) || food.calories <= 0) {
      setError("The food must have a valid calorie estimate.");
      return;
    }

    setSaving(true);
    setError("");
    setMessage("");

    try {
      let id = foodId(food);

      if (id == null) {
        const created = await api("/foods", {
          method: "POST",
          body: JSON.stringify({
            name: food.name,
            serving_size: food.serving_size || "1 serving",
            calories: food.calories,
            protein: food.protein,
            carbohydrates: food.carbohydrates,
            fat: food.fat,
          }),
        });

        id = foodId(created);
      }

      if (id == null) {
        throw new Error("The API did not return a food ID.");
      }

      await api("/food-logs", {
        method: "POST",
        body: JSON.stringify({
          user_id: USER_ID,
          food_id: id,
          meal_type: meal,
          quantity: amount,
        }),
      });

      setSelected(null);
      setMessage(
        `${food.name} added to your diary (${formatNumber(
          food.calories * amount
        )} kcal).`
      );

      await loadDashboard();
    } catch (err) {
      setError(`Could not add food: ${err.message}`);
    } finally {
      setSaving(false);
    }
  }

  function selectPhoto(event) {
    const file = event.target.files?.[0];
    if (!file) return;

    setError("");
    setMessage("");

    if (!file.type.startsWith("image/")) {
      setError("Please choose a valid image file.");
      event.target.value = "";
      return;
    }

    if (file.size > MAX_IMAGE_SIZE) {
      setError("Image must be smaller than 10 MB.");
      event.target.value = "";
      return;
    }

    setPhoto(file);
    setSelected(null);
    setPreview(URL.createObjectURL(file));
  }

  async function analysePhoto() {
    if (!photo) {
      setError("Choose a food photo first.");
      return;
    }

    setAnalysing(true);
    setError("");
    setMessage("");
    setSelected(null);

    try {
      const formData = new FormData();
      formData.append("image", photo);

      const result = await api("/ai/analyze-food", {
        method: "POST",
        body: formData,
      });

      const item = foodShape(
        result?.food || result?.result || result?.analysis || result
      );

      if (
        !item.name.trim() ||
        item.name.toLowerCase() === "food not identified"
      ) {
        throw new Error(
          "The AI could not identify the food. Try a clearer photo."
        );
      }

      if (!Number.isFinite(item.calories) || item.calories <= 0) {
        throw new Error(
          "The AI did not return a valid calorie estimate. Please try again."
        );
      }

      setSelected({
        ...item,
        source: result?.source || item.source,
        disclaimer:
          result?.disclaimer ||
          "Nutrition values are estimates. Check the serving size before saving.",
      });

      setQuantity("1");
      setMeal("lunch");

      setMessage(
        "Photo analysed. Review the estimated nutrition before adding it to your diary."
      );
    } catch (err) {
      setError(`Photo analysis failed: ${err.message}`);
    } finally {
      setAnalysing(false);
    }
  }

  function clearPhoto() {
    setPhoto(null);
    setPreview("");
    setSelected(null);
    setPhotoExpanded(false);
    setError("");
    setMessage("");
  }

  async function deleteLog(log) {
    const id = log.id ?? log.log_id;

    if (id == null) {
      setError("This diary entry has no log ID.");
      return;
    }

    if (!window.confirm("Remove this diary entry?")) return;

    setError("");
    setMessage("");

    try {
      await api(`/food-logs/${id}`, { method: "DELETE" });
      setMessage("Diary entry removed.");
      await loadDashboard();
    } catch (err) {
      setError(`Could not remove entry: ${err.message}`);
    }
  }

  function foodEmoji(name = "") {
    const text = name.toLowerCase();

    if (text.includes("ayam") || text.includes("chicken")) return "🍗";
    if (text.includes("ikan") || text.includes("fish")) return "🐟";
    if (text.includes("telur") || text.includes("egg")) return "🥚";
    if (text.includes("sayur") || text.includes("vegetable")) return "🥦";
    if (text.includes("pisang") || text.includes("banana")) return "🍌";
    if (text.includes("jambu") || text.includes("apple")) return "🍏";
    if (text.includes("nasi") || text.includes("rice")) return "🍚";
    if (text.includes("roti") || text.includes("bread")) return "🥞";
    if (text.includes("mee") || text.includes("noodle")) return "🍜";

    return "🥗";
  }

  function FoodCard({ food }) {
    const isAiEstimate =
      food.source?.toLowerCase().includes("gemini") ||
      food.source?.toLowerCase().includes("ai");

    return (
      <article className="food-card">
        <div className="food-emoji">{foodEmoji(food.name)}</div>

        <div className="food-info">
          <h3>{food.name}</h3>
          <p>{food.serving_size}</p>

          <div className="food-macros">
            <span>P {food.protein}g</span>
            <span>C {food.carbohydrates}g</span>
            <span>F {food.fat}g</span>
          </div>

          {isAiEstimate && (
            <small className="ai-disclaimer">AI nutrition estimate</small>
          )}
        </div>

        <div className="food-side">
          <strong>{formatNumber(food.calories)}</strong>
          <small>kcal</small>

          <button
            className="mini-add"
            type="button"
            onClick={() => chooseFood(food)}
          >
            Select +
          </button>
        </div>
      </article>
    );
  }

  return (
    <div className="site">
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />

      <header className="topbar">
        <a className="brand" href="#home">
          <span className="brand-logo">
            N<span>+</span>
          </span>
          <span className="brand-name">
            NUTRITRACK
            <small>FOOD · FITNESS · YOU</small>
          </span>
        </a>

        <nav className="navigation">
          <a className="nav-active" href="#home">Home</a>
          <a href="#profile">BMI & Calories</a>
          <a href="#food-search">Food Search</a>
          <a href="#diary">My Diary</a>
        </nav>

        <a className="profile-pill" href="#profile">
          <span className="profile-dot">
            {(user.name || "A").charAt(0).toUpperCase()}
          </span>
          <span>{user.name || "My Account"}</span>
          <span className="profile-arrow">⌄</span>
        </a>
      </header>

      <main className="page">
        <section className="hero" id="home">
          <div className="hero-copy">
            <div className="hero-kicker">
              <span /> YOUR PERSONAL NUTRITION SPACE
            </div>

            <h1>
              Discover a<br />
              healthier <span>you.</span>
            </h1>

            <p className="hero-description">
              Eat what you love. Understand what you eat.
              Build better habits, one meal at a time.
            </p>

            <div className="hero-actions">
              <a className="btn-lime" href="#profile">
                Calculate my goals <span>↗</span>
              </a>
              <a className="btn-outline" href="#diary">
                My food diary <span>→</span>
              </a>
            </div>

            <div className="hero-social-proof">
              <div className="avatar-stack">
                <span>🥑</span>
                <span>🍋</span>
                <span>🥦</span>
                <b>+</b>
              </div>
              <div>
                <strong>Better choices, every day</strong>
                <small>Your personal nutrition journey starts here.</small>
              </div>
            </div>
          </div>

          <div className="hero-visual">
            <div className="visual-orbit orbit-one" />
            <div className="visual-orbit orbit-two" />
            <div className="visual-glow" />

            <div className="hero-badge badge-top">
              <span>✳</span> DAILY WELLNESS
            </div>

            <div className="hero-plate">
              <div className="plate-ring">
                <div className="plate-food">
                  <div className="plate-leaf leaf-one" />
                  <div className="plate-leaf leaf-two" />
                  <div className="plate-leaf leaf-three" />
                  <div className="plate-rice">🍚</div>
                  <div className="plate-protein">🍗</div>
                  <div className="plate-veggies">🥦</div>
                  <div className="plate-tomato">🍅</div>
                </div>
              </div>
            </div>

            <div className="floating-card float-calories">
              <span className="float-icon">✳</span>
              <div>
                <small>CONSUMED TODAY</small>
                <strong>
                  {loading ? "..." : formatNumber(consumed)} <i>kcal</i>
                </strong>
              </div>
            </div>

            <div className="floating-card float-goal">
              <span className="goal-ring">✓</span>
              <div>
                <small>DAILY CALORIE GOAL</small>
                <strong>{formatNumber(goal)} kcal</strong>
              </div>
            </div>

            <div className="hero-stats">
              <span className="stats-label">YOUR DAILY STATS</span>
              <div>
                <small>Consumed</small>
                <strong>{formatNumber(consumed)} <i>kcal</i></strong>
              </div>
              <div>
                <small>Remaining</small>
                <strong className="stat-green">
                  {formatNumber(remaining)} <i>kcal</i>
                </strong>
              </div>
              <div>
                <small>Daily goal</small>
                <strong>{formatNumber(goal)} <i>kcal</i></strong>
              </div>
              <div className="hero-progress">
                <span style={{ width: `${percent}%` }} />
              </div>
              <small className="progress-note">
                {Math.round(percent)}% of your daily goal
              </small>
            </div>

            <div className="hero-caption">
              NOURISH YOUR BODY <span>✳</span>
            </div>
          </div>

          <div className="hero-index">
            <span>01</span> / YOUR JOURNEY
          </div>
        </section>

        {error && (
          <div className="notice notice-error" role="alert">
            <span>!</span>
            <p>{error}</p>
            <button
              onClick={() => setError("")}
              type="button"
              aria-label="Dismiss error"
            >
              ×
            </button>
          </div>
        )}

        {message && (
          <div className="notice notice-success" role="status">
            <span>✓</span>
            <p>{message}</p>
            <button
              onClick={() => setMessage("")}
              type="button"
              aria-label="Dismiss message"
            >
              ×
            </button>
          </div>
        )}

        <section className="quick-stats">
          <div className="quick-stat">
            <span className="quick-stat-icon lime">◉</span>
            <div>
              <small>CALORIES CONSUMED</small>
              <strong>{formatNumber(consumed)} <i>kcal</i></strong>
              <p>Today's intake</p>
            </div>
          </div>

          <div className="quick-stat">
            <span className="quick-stat-icon mint">↘</span>
            <div>
              <small>CALORIES REMAINING</small>
              <strong>{formatNumber(remaining)} <i>kcal</i></strong>
              <p>Room for your next meal</p>
            </div>
          </div>

          <div className="quick-stat">
            <span className="quick-stat-icon blue">◎</span>
            <div>
              <small>DAILY TARGET</small>
              <strong>{formatNumber(goal)} <i>kcal</i></strong>
              <p>Your personal goal</p>
            </div>
          </div>

          <div className="quick-stat">
            <span className="quick-stat-icon peach">♡</span>
            <div>
              <small>GOAL CONSUMED</small>
              <strong>{Math.round(percent)}<i>%</i></strong>
              <p>Of your daily target</p>
            </div>
          </div>
        </section>

        <section className="section-panel" id="profile">
          <div className="section-top">
            <div>
              <span className="section-kicker">YOUR PERSONAL PROFILE</span>
              <h2>BMI & calorie <span>calculator.</span></h2>
              <p>
                Update your details to estimate your BMI and daily calorie
                target.
              </p>
            </div>
            <span className="section-number">01</span>
          </div>

          {profileLoading ? (
            <p className="empty-state">Loading your profile...</p>
          ) : (
            <>
              <form className="profile-form" onSubmit={saveProfile}>
                <div className="profile-fields">
                  <label>
                    Age (years)
                    <input
                      type="number"
                      min="1"
                      max="119"
                      value={profile.age}
                      onChange={(event) =>
                        updateProfile("age", event.target.value)
                      }
                      required
                    />
                  </label>

                  <label>
                    Sex
                    <select
                      value={profile.gender}
                      onChange={(event) =>
                        updateProfile("gender", event.target.value)
                      }
                      required
                    >
                      <option value="male">Male</option>
                      <option value="female">Female</option>
                    </select>
                  </label>

                  <label>
                    Weight (kg)
                    <input
                      type="number"
                      min="1"
                      max="499"
                      step="0.1"
                      value={profile.weight}
                      onChange={(event) =>
                        updateProfile("weight", event.target.value)
                      }
                      required
                    />
                  </label>

                  <label>
                    Height (cm)
                    <input
                      type="number"
                      min="1"
                      max="299"
                      step="0.1"
                      value={profile.height}
                      onChange={(event) =>
                        updateProfile("height", event.target.value)
                      }
                      required
                    />
                  </label>

                  <label>
                    Activity level
                    <select
                      value={profile.activity_level}
                      onChange={(event) =>
                        updateProfile("activity_level", event.target.value)
                      }
                      required
                    >
                      <option value="sedentary">
                        Sedentary — little exercise
                      </option>
                      <option value="light">
                        Light — exercise 1–3 days/week
                      </option>
                      <option value="moderate">
                        Moderate — exercise 3–5 days/week
                      </option>
                      <option value="active">
                        Active — exercise 6–7 days/week
                      </option>
                      <option value="very_active">
                        Very active — intense activity
                      </option>
                    </select>
                  </label>

                  <label>
                    Weight goal
                    <select
                      value={profile.weight_goal}
                      onChange={(event) =>
                        updateProfile("weight_goal", event.target.value)
                      }
                      required
                    >
                      <option value="lose">Lose weight</option>
                      <option value="maintain">Maintain weight</option>
                      <option value="gain">Gain weight</option>
                    </select>
                  </label>
                </div>

                <button
                  className="btn-lime"
                  type="submit"
                  disabled={profileSaving || !profileLoaded}
                >
                  {profileSaving
                    ? "Saving profile..."
                    : "Save profile & recalculate ↗"}
                </button>
              </form>

              <div className="profile-results">
                <article className="profile-result-card">
                  <span className="section-kicker">YOUR BMI</span>
                  <strong>{bmi == null ? "—" : bmi.toFixed(1)}</strong>
                  <p>{currentBmiCategory}</p>
                  <small>
                    Adult BMI categories are a screening guide, not a diagnosis.
                  </small>
                </article>

                <article className="profile-result-card">
                  <span className="section-kicker">DAILY CALORIE TARGET</span>
                  <strong>
                    {formatNumber(user.daily_calorie_goal ?? goal)}
                    <small> kcal/day</small>
                  </strong>
                  <p>
                    Goal:{" "}
                    {profile.weight_goal === "lose"
                      ? "Lose weight"
                      : profile.weight_goal === "gain"
                        ? "Gain weight"
                        : "Maintain weight"}
                  </p>
                  <small>
                    An estimate based on your profile and activity level.
                  </small>
                </article>
              </div>

              <p className="nutrition-tip">
                Calorie needs vary between individuals. BMI does not directly
                measure body fat or overall health. Use these results as
                estimates, not medical advice.
              </p>
            </>
          )}
        </section>

        <section className="section-panel" id="food-search">
          <div className="section-top">
            <div>
              <span className="section-kicker">FIND YOUR NEXT FAVOURITE</span>
              <h2>What's on your <span>plate?</span></h2>
              <p>Search Malaysian favourites or upload a meal photo.</p>
            </div>
            <span className="section-number">02</span>
          </div>

          <form className="search-bar" onSubmit={searchFood}>
            <span className="search-icon">⌕</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search nasi lemak, ayam goreng, roti canai..."
              aria-label="Search food"
            />
            <button
              className="btn-lime"
              type="submit"
              disabled={searching}
            >
              {searching ? "Searching..." : "Search food ↗"}
            </button>
          </form>

          <div className="popular-searches">
            <span>POPULAR</span>
            {["Nasi lemak", "Ayam goreng", "Nasi ayam", "Roti canai"].map(
              (term) => (
                <button
                  type="button"
                  key={term}
                  onClick={() => setQuery(term)}
                >
                  {term}
                </button>
              )
            )}
          </div>

          {results.length > 0 && (
            <div className="result-area">
              <div className="subheading">
                <h3>Search results</h3>
                <span>{results.length} found</span>
              </div>
              <div className="food-grid">
                {results.map((food, index) => (
                  <FoodCard
                    key={foodId(food) ?? `${food.name}-${index}`}
                    food={food}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Compact photo-analysis button */}
          {!photoExpanded ? (
            <button
              className="btn-outline photo-compact-button"
              type="button"
              onClick={() => setPhotoExpanded(true)}
            >
              <span>▧</span> Analyse food from photo ↗
            </button>
          ) : (
            <div className="photo-analysis-expanded">
              <div className="photo-upload">
                <div className="upload-symbol">▧</div>
                <div className="upload-copy">
                  <h3>AI food photo analysis</h3>
                  <p>
                    Upload a meal photo to estimate calories, protein,
                    carbohydrates, and fat using Google Gemini.
                  </p>
                  <small>JPG, PNG, or WEBP · Maximum 10 MB</small>
                </div>
                <label className="btn-outline upload-label">
                  Choose photo
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    onChange={selectPhoto}
                    disabled={analysing || saving}
                  />
                </label>
              </div>

              {preview && (
                <div className="photo-review">
                  <img src={preview} alt="Selected food for AI analysis" />
                  <div>
                    <strong>{photo?.name || "Selected food photo"}</strong>
                    <p>
                      Image size:{" "}
                      {photo
                        ? (photo.size / 1024 / 1024).toFixed(2)
                        : "0"}{" "}
                      MB
                    </p>
                    <div className="photo-actions">
                      <button
                        className="btn-lime"
                        type="button"
                        onClick={analysePhoto}
                        disabled={analysing || saving}
                      >
                        {analysing
                          ? "AI is analysing..."
                          : "Analyse photo ↗"}
                      </button>
                      <button
                        className="cancel-button"
                        type="button"
                        onClick={clearPhoto}
                        disabled={analysing || saving}
                      >
                        Remove photo
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {analysing && (
                <div className="analysis-progress" role="status">
                  <span className="analysis-spinner" />
                  <div>
                    <strong>Analysing your food photo...</strong>
                    <p>
                      Google Gemini is analysing your photo. This may take a
                      few seconds.
                    </p>
                  </div>
                </div>
              )}

              <button
                className="cancel-button photo-close-button"
                type="button"
                onClick={() => setPhotoExpanded(false)}
                disabled={analysing || saving}
              >
                Close photo analysis
              </button>
            </div>
          )}

          {selected && (
            <div className="selected-panel">
              <div className="selected-title">
                <span className="selected-emoji">
                  {foodEmoji(selected.name)}
                </span>
                <div>
                  <small>
                    {selected.source?.toLowerCase().includes("gemini") ||
                    selected.source === "Ollama AI estimate" ||
                    selected.source === "Ollama Qwen3-VL 4B"
                      ? "AI ESTIMATE — PLEASE REVIEW"
                      : "READY TO ADD"}
                  </small>
                  <h3>{selected.name}</h3>
                  <p>
                    {selected.serving_size} ·{" "}
                    {formatNumber(
                      selected.calories * (Number(quantity) || 1)
                    )}{" "}
                    kcal
                  </p>
                </div>
              </div>

              <div className="nutrition-breakdown">
                <div>
                  <span>Calories</span>
                  <strong>{formatNumber(selected.calories)} kcal</strong>
                </div>
                <div>
                  <span>Protein</span>
                  <strong>{selected.protein} g</strong>
                </div>
                <div>
                  <span>Carbs</span>
                  <strong>{selected.carbohydrates} g</strong>
                </div>
                <div>
                  <span>Fat</span>
                  <strong>{selected.fat} g</strong>
                </div>
              </div>

              {selected.disclaimer && (
                <p className="ai-disclaimer">{selected.disclaimer}</p>
              )}

              <div className="selected-controls">
                <label>
                  Meal
                  <select
                    value={meal}
                    onChange={(event) => setMeal(event.target.value)}
                  >
                    {MEALS.map((item) => (
                      <option value={item} key={item}>
                        {item.charAt(0).toUpperCase() + item.slice(1)}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  Quantity
                  <input
                    type="number"
                    min="0.1"
                    max="100"
                    step="0.5"
                    value={quantity}
                    onChange={(event) => setQuantity(event.target.value)}
                  />
                </label>

                <button
                  className="btn-lime"
                  type="button"
                  onClick={() => addToDiary()}
                  disabled={saving || analysing}
                >
                  {saving ? "Adding..." : "Add to diary ↗"}
                </button>

                <button
                  className="cancel-button"
                  type="button"
                  onClick={() => setSelected(null)}
                  disabled={saving}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </section>

        <section className="section-panel" id="diary">
          <div className="section-top">
            <div>
              <span className="section-kicker">YOUR DAILY PROGRESS</span>
              <h2>Your food <span>diary.</span></h2>
              <p>Every meal is another step towards your goal.</p>
            </div>
            <span className="section-number">03</span>
          </div>

          <div className="meal-totals">
            {MEALS.map((item) => (
              <div className="meal-total" key={item}>
                <span>
                  {item === "breakfast"
                    ? "☀"
                    : item === "lunch"
                      ? "◉"
                      : item === "dinner"
                        ? "☾"
                        : "✳"}{" "}
                  {item}
                </span>
                <strong>
                  {formatNumber(
                    meals[item] ??
                      meals[item === "snacks" ? "snack" : item] ??
                      0
                  )}{" "}
                  <small>kcal</small>
                </strong>
              </div>
            ))}
          </div>

          {loading ? (
            <p className="empty-state">Loading your diary...</p>
          ) : logs.length > 0 ? (
            <div className="diary-list">
              {logs.map((log, index) => {
                const name =
                  log.food?.name ||
                  log.food_name ||
                  log.name ||
                  `Food entry ${index + 1}`;

                const logMeal = String(log.meal_type || "snacks");

                return (
                  <div
                    className="diary-row"
                    key={log.id ?? log.log_id ?? `${name}-${index}`}
                  >
                    <span className="diary-emoji">{foodEmoji(name)}</span>
                    <div className="diary-info">
                      <strong>{name}</strong>
                      <small>
                        {logMeal} · Quantity {log.quantity ?? 1}
                      </small>
                    </div>
                    <strong className="diary-kcal">
                      {formatNumber(log.calories ?? 0)} kcal
                    </strong>
                    <button
                      className="remove-log"
                      type="button"
                      onClick={() => deleteLog(log)}
                      aria-label={`Remove ${name}`}
                    >
                      ×
                    </button>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="empty-state">
              <span>🥗</span>
              <h3>Your food diary starts here.</h3>
              <p>
                Search for a meal to add your first diary entry.
              </p>
              <a className="btn-lime" href="#food-search">
                Find a meal ↗
              </a>
            </div>
          )}
        </section>

        <footer className="footer">
          <a className="brand" href="#home">
            <span className="brand-logo">
              N<span>+</span>
            </span>
            <span className="brand-name">
              NUTRITRACK
              <small>FOOD · FITNESS · YOU</small>
            </span>
          </a>
          <p>Eat well. Feel well. Live well.</p>
          <a href="#home">Back to top ↑</a>
        </footer>
      </main>
    </div>
  );
}

export default App;
