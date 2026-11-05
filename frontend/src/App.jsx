
import { useCallback, useEffect, useState } from "react";
import "./App.css";

const API_URL = import.meta.env.VITE_API_URL || "https://nutritrack-backend-qsoc.onrender.com";
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
  const token = sessionStorage.getItem("nutritrack_token");
  if (token) headers.Authorization = `Bearer ${token}`;

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
  const [currentUser, setCurrentUser] = useState(() => {
    try {
      return JSON.parse(sessionStorage.getItem("nutritrack_user") || "null");
    } catch {
      return null;
    }
  });
  const [authMode, setAuthMode] = useState("login");
  const [authLoading, setAuthLoading] = useState(false);
  const [authForm, setAuthForm] = useState({
    name: "",
    email: "",
    password: "",
    age: "30",
    gender: "male",
    weight: "80",
    height: "175",
    activity_level: "moderate",
  });
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
        api(`/dashboard/${currentUser.id}`),
        api(`/food-logs/${currentUser.id}`),
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
  }, [currentUser?.id]);

  const loadProfile = useCallback(async () => {
    setProfileLoading(true);

    try {
      const data = await api(`/users/${currentUser.id}`);

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
  }, [currentUser?.id]);

  useEffect(() => {
    if (currentUser?.id && sessionStorage.getItem("nutritrack_token")) {
      loadDashboard();
      loadProfile();
    } else {
      setLoading(false);
      setProfileLoading(false);
    }
  }, [currentUser?.id, loadDashboard, loadProfile]);

  useEffect(() => {
    return () => {
      if (preview.startsWith("blob:")) {
        URL.revokeObjectURL(preview);
      }
    };
  }, [preview]);

  async function submitAuth(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    setAuthLoading(true);

    try {
      const isRegister = authMode === "register";
      const payload = isRegister
        ? {
            name: authForm.name.trim(),
            email: authForm.email.trim(),
            password: authForm.password,
            age: Number(authForm.age),
            gender: authForm.gender,
            weight: Number(authForm.weight),
            height: Number(authForm.height),
            activity_level: authForm.activity_level,
          }
        : {
            email: authForm.email.trim(),
            password: authForm.password,
          };

      const result = await api(
        isRegister ? "/auth/register" : "/auth/login",
        { method: "POST", body: JSON.stringify(payload) }
      );

      if (!result?.access_token || !result?.user?.id) {
        throw new Error("The server did not return a valid login session.");
      }

      sessionStorage.setItem("nutritrack_token", result.access_token);
      sessionStorage.setItem("nutritrack_user", JSON.stringify(result.user));
      setCurrentUser(result.user);
      setDashboard(null);
      setLogs([]);
      setProfile(DEFAULT_PROFILE);
      setProfileLoaded(false);
      setError("");
      setMessage(isRegister ? "Your account has been created." : "Welcome back!");
    } catch (err) {
      setError(err.message || "Authentication failed.");
    } finally {
      setAuthLoading(false);
    }
  }

  function logout() {
    sessionStorage.removeItem("nutritrack_token");
    sessionStorage.removeItem("nutritrack_user");
    setCurrentUser(null);
    setDashboard(null);
    setLogs([]);
    setProfile(DEFAULT_PROFILE);
    setProfileLoaded(false);
    setLoading(false);
    setProfileLoading(false);
    setError("");
    setMessage("");
    setAuthMode("login");
  }

  function updateAuthForm(field, value) {
    setAuthForm((previous) => ({ ...previous, [field]: value }));
  }

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
      const updated = await api(`/users/${currentUser.id}/profile`, {
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
      } else if (cleanedResults.some((food) => food.source?.toLowerCase().includes("gemini"))) {
        setMessage("Gemini generated an estimated nutrition result. Review the serving size and values before adding it.");
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
          user_id: currentUser.id,
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

  if (!currentUser) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <a className="brand auth-brand" href="#auth">
            <span className="brand-logo">N<span>+</span></span>
            <span className="brand-name">NUTRITRACK<small>FOOD · FITNESS · YOU</small></span>
          </a>
          <span className="section-kicker">YOUR PERSONAL NUTRITION SPACE</span>
          <h1>{authMode === "register" ? "Create your account." : "Welcome back."}</h1>
          <p className="auth-intro">Understand your food. Build healthier habits.</p>
          <div className="auth-tabs">
            <button type="button" className={authMode === "login" ? "auth-tab active" : "auth-tab"} onClick={() => { setAuthMode("login"); setError(""); }}>Log in</button>
            <button type="button" className={authMode === "register" ? "auth-tab active" : "auth-tab"} onClick={() => { setAuthMode("register"); setError(""); }}>Create account</button>
          </div>
          {error && <div className="notice notice-error" role="alert"><span>!</span><p>{error}</p></div>}
          <form className="auth-form" onSubmit={submitAuth}>
            {authMode === "register" && <>
              <label>Full name<input value={authForm.name} onChange={e => updateAuthForm("name", e.target.value)} required autoComplete="name" /></label>
            </>}
            <label>Email address<input type="email" value={authForm.email} onChange={e => updateAuthForm("email", e.target.value)} required autoComplete="email" /></label>
            <label>Password<input type="password" value={authForm.password} onChange={e => updateAuthForm("password", e.target.value)} required minLength="6" autoComplete={authMode === "register" ? "new-password" : "current-password"} /></label>
            {authMode === "register" && <>
              <div className="auth-grid">
                <label>Age<input type="number" min="1" max="119" value={authForm.age} onChange={e => updateAuthForm("age", e.target.value)} required /></label>
                <label>Gender<select value={authForm.gender} onChange={e => updateAuthForm("gender", e.target.value)}><option value="male">Male</option><option value="female">Female</option></select></label>
                <label>Weight (kg)<input type="number" min="1" max="499" step="0.1" value={authForm.weight} onChange={e => updateAuthForm("weight", e.target.value)} required /></label>
                <label>Height (cm)<input type="number" min="1" max="299" step="0.1" value={authForm.height} onChange={e => updateAuthForm("height", e.target.value)} required /></label>
                <label className="auth-full">Activity level<select value={authForm.activity_level} onChange={e => updateAuthForm("activity_level", e.target.value)}><option value="sedentary">Sedentary</option><option value="light">Light</option><option value="moderate">Moderate</option><option value="active">Active</option><option value="very active">Very active</option></select></label>
              </div>
            </>}
            <button className="btn-lime auth-submit" type="submit" disabled={authLoading}>{authLoading ? "Please wait..." : authMode === "register" ? "Create account ↗" : "Log in ↗"}</button>
          </form>
          <p className="auth-footnote">Your nutrition data is linked to your account.</p>
        </div>
      </div>
    );
  }

  const displayName = user.name || currentUser.name || "there";
  const firstName = displayName.trim().split(/\s+/)[0] || "there";
  const progressWidth = Math.min(100, Math.max(0, percent));
  const todayLabel = new Intl.DateTimeFormat("en-MY", {
    weekday: "long", day: "numeric", month: "long",
  }).format(new Date());

  return (
    <div className="nt-app">
      <header className="nt-header">
        <a className="nt-brand" href="#home" aria-label="NutriTrack home">
          <span className="nt-brand-mark">N<span>+</span></span>
          <span className="nt-brand-copy">NUTRITRACK<small>YOUR DAILY NUTRITION</small></span>
        </a>
        <nav className="nt-nav" aria-label="Main navigation">
          <a className="active" href="#home">Overview</a>
          <a href="#food-search">Food scanner</a>
          <a href="#diary">My diary</a>
          <a href="#profile">My goals</a>
        </nav>
        <div className="nt-user-menu">
          <a className="nt-user-chip" href="#profile"><span>{displayName.charAt(0).toUpperCase()}</span><b>{displayName}</b></a>
          <button type="button" className="nt-logout" onClick={logout}>Log out</button>
        </div>
      </header>

      <main className="nt-main" id="home">
        <div className="nt-welcome-row">
          <div>
            <div className="nt-eyebrow"><span className="nt-live-dot" /> YOUR PERSONAL HEALTH SPACE</div>
            <h1>Good day, {firstName}<span>.</span></h1>
            <p className="nt-subtitle">A little progress every day adds up. Here is your nutrition overview.</p>
          </div>
          <div className="nt-date-chip"><span>▦</span>{todayLabel}</div>
        </div>

        {error && <div className="nt-alert error" role="alert"><span>!</span><p>{error}</p><button type="button" onClick={() => setError("")} aria-label="Dismiss">×</button></div>}
        {message && <div className="nt-alert success" role="status"><span>✓</span><p>{message}</p><button type="button" onClick={() => setMessage("")} aria-label="Dismiss">×</button></div>}

        <section className="nt-overview-grid" aria-label="Daily calorie overview">
          <article className="nt-calorie-card">
            <div className="nt-card-heading"><div><span className="nt-card-label">DAILY CALORIE INTAKE</span><h2>Your energy today</h2></div><span className="nt-card-icon">✳</span></div>
            <div className="nt-calorie-main"><strong>{loading ? "…" : formatNumber(consumed)}</strong><span>kcal consumed</span></div>
            <div className="nt-progress-track"><span style={{ width: `${progressWidth}%` }} /></div>
            <div className="nt-progress-meta"><span>{Math.round(percent)}% of daily target</span><b>{formatNumber(goal)} kcal goal</b></div>
            <div className="nt-calorie-footer"><div><small>REMAINING</small><strong>{formatNumber(remaining)} <i>kcal</i></strong></div><div><small>DAILY TARGET</small><strong>{formatNumber(goal)} <i>kcal</i></strong></div></div>
          </article>
          <article className="nt-summary-card protein-card"><div className="nt-summary-icon">◉</div><span>FOOD ENTRIES</span><strong>{logs.length}</strong><small>Meals and snacks logged today</small><a href="#diary">View diary ↗</a></article>
          <article className="nt-summary-card bmi-card"><div className="nt-summary-icon">⌁</div><span>YOUR BMI</span><strong>{bmi == null ? "—" : bmi.toFixed(1)}</strong><small>{currentBmiCategory}</small><a href="#profile">View health profile ↗</a></article>
        </section>

        <section className="nt-quick-actions" aria-label="Quick actions">
          <a href="#food-search" className="nt-action-card"><span className="nt-action-icon">⌕</span><span><b>Find a food</b><small>Search nutrition information</small></span><i>↗</i></a>
          <button type="button" className="nt-action-card" onClick={() => { setPhotoExpanded(true); document.getElementById("food-search")?.scrollIntoView({ behavior: "smooth" }); }}><span className="nt-action-icon scan">▧</span><span><b>AI food scanner</b><small>Estimate nutrition from a photo</small></span><i>↗</i></button>
          <a href="#profile" className="nt-action-card"><span className="nt-action-icon goals">◎</span><span><b>Update my goals</b><small>Review your daily targets</small></span><i>↗</i></a>
        </section>

        <section className="nt-content-grid">
          <div className="nt-primary-column">
            <section className="nt-panel" id="food-search">
              <div className="nt-panel-heading"><div><span className="nt-eyebrow">SMART FOOD TRACKING</span><h2>What did you <em>eat?</em></h2><p>Search a meal or let AI estimate nutrition from a food photo.</p></div><span className="nt-step-tag">01 / TRACK</span></div>
              <form className="nt-search" onSubmit={searchFood}><span>⌕</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Try nasi lemak, ayam goreng, roti canai..." aria-label="Search food"/><button type="submit" disabled={searching}>{searching ? "Searching…" : "Search food"}</button></form>
              <div className="nt-popular"><span>POPULAR</span>{["Nasi lemak", "Ayam goreng", "Roti canai", " teh tarik"].map(item => <button key={item} type="button" onClick={() => setQuery(item.trim())}>{item.trim()}</button>)}</div>
              {results.length > 0 && <div className="nt-results"><div className="nt-results-title"><h3>Search results</h3><span>{results.length} found</span></div><div className="nt-food-grid">{results.map((food, index) => <FoodCard key={foodId(food) ?? `${food.name}-${index}`} food={food} />)}</div></div>}
              {searching && <div className="nt-inline-loading"><span className="nt-spinner"/>Finding nutrition information…</div>}
              {!searching && results.length === 0 && <div className="nt-search-hint"><span>✦</span><div><b>Nutrition lookup powered by AI</b><small>Search common Malaysian meals and review the estimated serving and macros.</small></div></div>}

              <div className="nt-scanner-box">
                <div className="nt-scanner-heading"><span className="nt-scanner-icon">✧</span><div><b>AI photo scanner</b><small>Turn a meal photo into a nutrition estimate</small></div><button type="button" onClick={() => setPhotoExpanded(value => !value)}>{photoExpanded ? "Hide" : "Open scanner"} {photoExpanded ? "−" : "+"}</button></div>
                {photoExpanded && <div className="nt-scanner-content">
                  <div className="nt-upload-area"><div className="nt-upload-symbol">▧</div><div><b>Upload your meal photo</b><p>Choose a clear JPG, PNG or WEBP image. Maximum 10 MB.</p></div><label className="nt-upload-button">Choose image<input type="file" accept="image/jpeg,image/png,image/webp" onChange={selectPhoto} disabled={analysing || saving}/></label></div>
                  {preview && <div className="nt-photo-preview"><img src={preview} alt="Selected food"/><div><b>{photo?.name || "Selected food"}</b><small>{photo ? (photo.size / 1024 / 1024).toFixed(2) : "0"} MB</small><div className="nt-photo-buttons"><button type="button" onClick={analysePhoto} disabled={analysing || saving}>{analysing ? "Analysing…" : "Analyse with AI"}</button><button type="button" className="nt-secondary-button" onClick={clearPhoto} disabled={analysing || saving}>Remove</button></div></div></div>}
                  {analysing && <div className="nt-inline-loading"><span className="nt-spinner"/>Gemini is analysing your food photo…</div>}
                </div>}
              </div>

              {selected && <div className="nt-selected-food"><div className="nt-selected-heading"><span>{foodEmoji(selected.name)}</span><div><small>REVIEW NUTRITION ESTIMATE</small><h3>{selected.name}</h3><p>{selected.serving_size}</p></div></div><div className="nt-macro-grid"><div><small>CALORIES</small><b>{formatNumber(selected.calories)} kcal</b></div><div><small>PROTEIN</small><b>{selected.protein} g</b></div><div><small>CARBS</small><b>{selected.carbohydrates} g</b></div><div><small>FAT</small><b>{selected.fat} g</b></div></div>{selected.disclaimer && <p className="nt-disclaimer">{selected.disclaimer}</p>}<div className="nt-add-controls"><label>Meal<select value={meal} onChange={event => setMeal(event.target.value)}>{MEALS.map(item => <option value={item} key={item}>{item.charAt(0).toUpperCase() + item.slice(1)}</option>)}</select></label><label>Quantity<input type="number" min="0.1" max="100" step="0.5" value={quantity} onChange={event => setQuantity(event.target.value)}/></label><button type="button" onClick={() => addToDiary()} disabled={saving || analysing}>{saving ? "Adding…" : "Add to diary ↗"}</button><button type="button" className="nt-secondary-button" onClick={() => setSelected(null)} disabled={saving}>Cancel</button></div></div>}
            </section>

            <section className="nt-panel" id="diary">
              <div className="nt-panel-heading"><div><span className="nt-eyebrow">YOUR DAILY JOURNAL</span><h2>Today's <em>food diary</em></h2><p>Keep track of every meal throughout your day.</p></div><span className="nt-step-tag">02 / REVIEW</span></div>
              <div className="nt-meal-summary">{MEALS.map(item => <div key={item}><span>{item === "breakfast" ? "☀" : item === "lunch" ? "◉" : item === "dinner" ? "☾" : "✳"} {item}</span><b>{formatNumber(meals[item] ?? meals[item === "snacks" ? "snack" : item] ?? 0)} <small>kcal</small></b></div>)}</div>
              {loading ? <div className="nt-empty"><span className="nt-spinner"/><p>Loading your food diary…</p></div> : logs.length > 0 ? <div className="nt-diary-list">{logs.map((log, index) => { const name = log.food?.name || log.food_name || log.name || `Food entry ${index + 1}`; const logMeal = String(log.meal_type || "snacks"); return <div className="nt-diary-row" key={log.id ?? log.log_id ?? `${name}-${index}`}><span className="nt-diary-emoji">{foodEmoji(name)}</span><div className="nt-diary-details"><b>{name}</b><small>{logMeal} · Quantity {log.quantity ?? 1}</small></div><strong>{formatNumber(log.calories ?? 0)} <small>kcal</small></strong><button type="button" onClick={() => deleteLog(log)} aria-label={`Remove ${name}`}>×</button></div>; })}</div> : <div className="nt-empty"><span>🥗</span><h3>No meals logged yet</h3><p>Start by searching for your first meal or scanning a food photo.</p><a href="#food-search">Find a food ↗</a></div>}
            </section>
          </div>

          <aside className="nt-sidebar">
            <section className="nt-panel nt-goal-panel"><div className="nt-panel-heading"><div><span className="nt-eyebrow">YOUR TARGET</span><h2>Daily <em>goal</em></h2></div></div><div className="nt-goal-number"><strong>{formatNumber(goal)}</strong><span>kcal / day</span></div><div className="nt-goal-track"><span style={{ width: `${progressWidth}%` }}/></div><div className="nt-goal-legend"><span>Consumed <b>{formatNumber(consumed)}</b></span><span>Left <b>{formatNumber(remaining)}</b></span></div><a className="nt-text-link" href="#profile">Adjust my target ↗</a></section>
            <section className="nt-panel nt-profile-panel" id="profile"><div className="nt-panel-heading"><div><span className="nt-eyebrow">PERSONAL DETAILS</span><h2>Health <em>profile</em></h2><p>Update your details to recalculate your target.</p></div></div>
              {profileLoading ? <div className="nt-empty"><span className="nt-spinner"/><p>Loading profile…</p></div> : <form className="nt-profile-form" onSubmit={saveProfile}>
                <label>Age (years)<input type="number" min="1" max="119" value={profile.age} onChange={event => updateProfile("age", event.target.value)} required/></label>
                <label>Sex<select value={profile.gender} onChange={event => updateProfile("gender", event.target.value)} required><option value="male">Male</option><option value="female">Female</option></select></label>
                <div className="nt-two-fields"><label>Weight (kg)<input type="number" min="1" max="499" step="0.1" value={profile.weight} onChange={event => updateProfile("weight", event.target.value)} required/></label><label>Height (cm)<input type="number" min="1" max="299" step="0.1" value={profile.height} onChange={event => updateProfile("height", event.target.value)} required/></label></div>
                <label>Activity level<select value={profile.activity_level} onChange={event => updateProfile("activity_level", event.target.value)} required><option value="sedentary">Sedentary</option><option value="light">Light</option><option value="moderate">Moderate</option><option value="active">Active</option><option value="very_active">Very active</option></select></label>
                <label>Weight goal<select value={profile.weight_goal} onChange={event => updateProfile("weight_goal", event.target.value)} required><option value="lose">Lose weight</option><option value="maintain">Maintain weight</option><option value="gain">Gain weight</option></select></label>
                <div className="nt-bmi-inline"><span>BMI <b>{bmi == null ? "—" : bmi.toFixed(1)}</b></span><span>{currentBmiCategory}</span></div>
                <button type="submit" disabled={profileSaving || !profileLoaded}>{profileSaving ? "Saving…" : "Save profile & recalculate"}</button>
              </form>}
            </section>
            <div className="nt-ai-note"><span>✦</span><div><b>AI nutrition estimates</b><p>Food values are estimates. Review serving sizes and nutrition before saving them to your diary.</p></div></div>
          </aside>
        </section>

        <footer className="nt-footer"><a className="nt-brand" href="#home"><span className="nt-brand-mark">N<span>+</span></span><span className="nt-brand-copy">NUTRITRACK<small>YOUR DAILY NUTRITION</small></span></a><span>Eat well. Feel well. Live well.</span><a href="#home">Back to top ↑</a></footer>
      </main>

      <nav className="nt-mobile-nav" aria-label="Mobile navigation"><a href="#home"><span>⌂</span><small>Home</small></a><a href="#food-search"><span>⌕</span><small>Search</small></a><button type="button" onClick={() => { setPhotoExpanded(true); document.getElementById("food-search")?.scrollIntoView({ behavior: "smooth" }); }}><span>✧</span><small>Scan</small></button><a href="#diary"><span>▤</span><small>Diary</small></a><a href="#profile"><span>◎</span><small>Goals</small></a></nav>
    </div>
  );
}

export default App;
