#!/usr/bin/env python3
"""
WHOOP Dashboard Auto-Updater
----------------------------
Watches a folder for new WHOOP CSV exports, rebuilds your dashboard HTML,
and automatically pushes it to your GitHub repo so Netlify updates live.

Setup:
  pip install watchdog pandas

Usage:
  1. Paste your GitHub repo URL below (GITHUB_REPO)
  2. Run: python whoop_watcher.py

The script clones your repo the first time, then pushes updates
automatically every time a new WHOOP CSV is detected.
"""

import os
import time
import json
import glob
import subprocess
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ── Config ─────────────────────────────────────────────────────────────────────
GITHUB_REPO  = "https://github.com/kanzspam/whoopdashboard2"
WATCH_FOLDER = str(Path.home() / "Downloads")
CSV_PATTERN  = "whoop*.csv"

# Derived paths — no need to edit
REPO_DIR    = str(Path.home() / ".whoop_repo")
OUTPUT_FILE = os.path.join(REPO_DIR, "index.html")
# ───────────────────────────────────────────────────────────────────────────────


def ensure_repo():
    """Clone the GitHub repo locally if it hasn't been cloned yet."""
    if GITHUB_REPO == "https://github.com/YOUR_USERNAME/YOUR_REPO":
        print("❌  Please open whoop_watcher.py and set your GITHUB_REPO URL at the top.")
        raise SystemExit(1)
    if not os.path.exists(os.path.join(REPO_DIR, ".git")):
        print("📦 Cloning your repo for the first time...")
        result = subprocess.run(["git", "clone", GITHUB_REPO, REPO_DIR],
                                capture_output=True, text=True)
        if result.returncode != 0:
            print(f"❌ Git clone failed:\n{result.stderr}")
            print("   Check that your repo URL is correct and you're logged into GitHub.")
            raise SystemExit(1)
        print(f"✅ Repo cloned to {REPO_DIR}")
    else:
        subprocess.run(["git", "-C", REPO_DIR, "pull", "--quiet"], capture_output=True)


def push_to_github():
    """Commit and push the updated dashboard HTML to GitHub."""
    try:
        subprocess.run(["git", "-C", REPO_DIR, "add", "index.html"],
                       check=True, capture_output=True)
        result = subprocess.run(
            ["git", "-C", REPO_DIR, "commit", "-m",
             f"update dashboard {datetime.now().strftime('%Y-%m-%d %H:%M')}"],
            capture_output=True, text=True
        )
        if "nothing to commit" in result.stdout:
            print("   No changes to push.")
            return
        subprocess.run(["git", "-C", REPO_DIR, "push"], check=True, capture_output=True)
        print("🚀 Pushed to GitHub — Netlify will update in ~30 seconds")
    except subprocess.CalledProcessError as e:
        print(f"❌ Git push failed: {e}")
        print("   Make sure you have push access and git credentials are configured.")


def parse_whoop_csv(filepath):
    """Parse a WHOOP export CSV and return dashboard-ready values."""
    df = pd.read_csv(filepath)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    col_map = {
        "recovery_score_%":              "recovery",
        "recovery_score":                "recovery",
        "hrv_rmssd_milli":               "hrv",
        "heart_rate_variability_ms":     "hrv",
        "resting_heart_rate_bpm":        "resting_hr",
        "resting_heart_rate":            "resting_hr",
        "sleep_performance_%":           "sleep_perf",
        "sleep_performance_percentage":  "sleep_perf",
        "sleep_duration_minutes":        "sleep_min",
        "asleep_duration_(min)":         "sleep_min",
        "day_strain":                    "strain",
        "spo2_%":                        "spo2",
        "skin_temp_fahrenheit":          "skin_temp",
        "rem_sleep_duration_(min)":      "rem_min",
        "light_sleep_duration_(min)":    "light_min",
        "slow_wave_sleep_duration_(min)":"deep_min",
        "sleep_latency_(min)":           "latency_min",
        "calories":                      "calories",
    }
    for old, new in col_map.items():
        if old in df.columns and new not in df.columns:
            df[new] = df[old]

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.sort_values("date", ascending=False)

    def safe(col, default=0, decimals=1):
        if col in df.columns:
            val = pd.to_numeric(df[col], errors="coerce").dropna()
            if not val.empty:
                return round(float(val.iloc[0]), decimals)
        return default

    def safe_trend(col, n=7, default=0, decimals=0):
        if col in df.columns:
            vals = pd.to_numeric(df[col], errors="coerce").dropna().head(n)
            if not vals.empty:
                return [round(float(v), decimals) for v in vals.tolist()[::-1]]
        return [default] * n

    recovery  = safe("recovery", 0, 0)
    hrv       = safe("hrv", 0, 0)
    rhr       = safe("resting_hr", 0, 0)
    sleep_m   = safe("sleep_min", 0, 0)
    sleep_p   = safe("sleep_perf", 0, 0)
    strain    = safe("strain", 0, 1)
    spo2      = safe("spo2", 97, 1)
    skin_t    = safe("skin_temp", 0, 1)
    rem_m     = safe("rem_min", 0, 0)
    light_m   = safe("light_min", 0, 0)
    deep_m    = safe("deep_min", 0, 0)
    latency   = safe("latency_min", 0, 0)

    if recovery >= 67:
        rec_color = "#00c47e"; rec_label = "Green — Good"
    elif recovery >= 34:
        rec_color = "#f59e42"; rec_label = "Yellow — Moderate"
    else:
        rec_color = "#e24b4a"; rec_label = "Red — Rest"

    strain_color = "#e24b4a" if strain >= 18 else "#f59e42" if strain >= 14 else "#4ea6ff"

    hrv_trend = safe_trend("hrv", 7, hrv)
    rec_trend = safe_trend("recovery", 7, recovery)

    today = datetime.today()
    day_labels = [(today - timedelta(days=6-i)).strftime("%a") for i in range(7)]

    return {
        "recovery":      recovery,
        "rec_color":     rec_color,
        "rec_label":     rec_label,
        "hrv":           hrv,
        "rhr":           rhr,
        "sleep_h":       int(sleep_m // 60),
        "sleep_mm":      int(sleep_m % 60),
        "sleep_perf":    sleep_p,
        "strain":        strain,
        "strain_color":  strain_color,
        "spo2":          spo2,
        "skin_temp":     skin_t,
        "rem_h":         int(rem_m // 60),
        "rem_m":         int(rem_m % 60),
        "light_h":       int(light_m // 60),
        "light_m":       int(light_m % 60),
        "deep_h":        int(deep_m // 60),
        "deep_m":        int(deep_m % 60),
        "latency":       int(latency),
        "hrv_trend":     hrv_trend,
        "rec_trend":     rec_trend,
        "day_labels":    day_labels,
        "last_updated":  datetime.now().strftime("%b %d, %Y at %I:%M %p"),
        "hrv_avg":       round(sum(hrv_trend) / len(hrv_trend)) if hrv_trend else hrv,
        "sleep_bar_pct": min(100, round(sleep_p)),
    }


def build_html(d):
    """Return the full dashboard HTML with real data injected."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>WHOOP Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&display=swap"/>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@2.44.0/tabler-icons.min.css"/>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#0e0f11;--surface:#17191d;--card:#1e2026;--border:rgba(255,255,255,.08);
  --text:#f0f0f0;--muted:#888;--hint:#555;
  --green:#00c47e;--blue:#4ea6ff;--purple:#a78bfa;--amber:#f59e42;--red:#e24b4a;
  --radius:12px;--radius-sm:8px;
}}
body{{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;padding:2rem 1rem}}
.page{{max-width:900px;margin:0 auto}}
.header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:2rem}}
.logo-row{{display:flex;align-items:center;gap:10px}}
.logo{{width:32px;height:32px;background:var(--green);border-radius:8px;display:flex;align-items:center;justify-content:center}}
.logo i{{color:#000;font-size:16px}}
h1{{font-size:20px;font-weight:600}}
.sub{{font-size:12px;color:var(--muted);margin-top:2px}}
.badge{{font-size:11px;background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:4px 10px;color:var(--muted)}}
.section-label{{font-size:10px;font-weight:600;letter-spacing:.08em;color:var(--hint);text-transform:uppercase;margin-bottom:10px}}
.grid4{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:1.5rem}}
@media(max-width:600px){{.grid4{{grid-template-columns:repeat(2,1fr)}}}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:1.5rem}}
@media(max-width:600px){{.grid2{{grid-template-columns:1fr}}}}
.metric{{background:var(--surface);border-radius:var(--radius-sm);padding:14px;border:1px solid var(--border)}}
.metric .lbl{{font-size:11px;color:var(--muted);margin-bottom:8px;display:flex;align-items:center;gap:4px}}
.metric .val{{font-size:24px;font-weight:600;line-height:1}}
.metric .unit{{font-size:11px;color:var(--muted);margin-top:4px}}
.metric .bar{{height:3px;background:rgba(255,255,255,.08);border-radius:2px;margin-top:12px;overflow:hidden}}
.metric .bar-fill{{height:100%;border-radius:2px}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:1.25rem;margin-bottom:1.5rem}}
.ring-wrap{{position:relative;width:100px;height:100px;flex-shrink:0}}
.ring-wrap svg{{position:absolute;top:0;left:0}}
.ring-center{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center}}
.ring-pct{{font-size:26px;font-weight:600}}
.ring-lbl{{font-size:10px;color:var(--muted)}}
.recovery-row{{display:flex;align-items:center;gap:20px}}
.recovery-stats{{flex:1;display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.rs-label{{font-size:11px;color:var(--muted);margin-bottom:3px}}
.rs-val{{font-size:16px;font-weight:500}}
.sleep-bars{{display:flex;flex-direction:column;gap:10px;margin-top:4px}}
.sleep-row{{display:flex;align-items:center;gap:10px}}
.sleep-lbl{{font-size:11px;color:var(--muted);width:56px;flex-shrink:0}}
.sleep-track{{flex:1;height:5px;background:rgba(255,255,255,.07);border-radius:3px;overflow:hidden}}
.sleep-fill{{height:100%;border-radius:3px}}
.sleep-val{{font-size:11px;color:var(--muted);width:36px;text-align:right;flex-shrink:0}}
.chart-wrap{{position:relative;width:100%;height:100px;margin-top:12px}}
.goals-header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}}
.add-btn{{display:flex;align-items:center;gap:5px;background:transparent;border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 12px;font-size:12px;color:var(--muted);cursor:pointer;font-family:inherit}}
.add-btn:hover{{background:var(--surface);color:var(--text)}}
.input-row{{display:none;gap:8px;margin-bottom:12px}}
.input-row.show{{display:flex}}
.input-row input{{flex:1;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 12px;font-size:13px;color:var(--text);font-family:inherit;outline:none}}
.input-row input:focus{{border-color:rgba(255,255,255,.2)}}
.input-row select{{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 10px;font-size:12px;color:var(--muted);cursor:pointer;font-family:inherit;outline:none}}
.input-row button{{padding:8px 14px;font-size:12px;border-radius:var(--radius-sm);border:1px solid var(--border);background:transparent;color:var(--text);cursor:pointer;font-family:inherit;font-weight:500}}
.input-row button:hover{{background:var(--surface)}}
.goals-list{{display:flex;flex-direction:column;gap:6px}}
.goal-item{{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:var(--radius-sm);border:1px solid var(--border);background:var(--surface);transition:opacity .15s}}
.goal-item.done{{opacity:.45}}
.goal-item.done .goal-text{{text-decoration:line-through;color:var(--muted)}}
.goal-check{{width:20px;height:20px;border-radius:5px;border:1px solid var(--border);display:flex;align-items:center;justify-content:center;cursor:pointer;flex-shrink:0;transition:background .1s}}
.goal-check.checked{{background:var(--green);border-color:var(--green)}}
.goal-check.checked i{{color:#000;font-size:12px}}
.goal-text{{font-size:13px;flex:1}}
.goal-tag{{font-size:10px;padding:2px 8px;border-radius:10px;flex-shrink:0;font-weight:500}}
.t-fitness{{background:rgba(0,196,126,.15);color:#00c47e}}
.t-nutrition{{background:rgba(245,158,66,.15);color:#f59e42}}
.t-wellness{{background:rgba(167,139,250,.15);color:#a78bfa}}
.t-work{{background:rgba(78,166,255,.15);color:#4ea6ff}}
.t-other{{background:rgba(255,255,255,.07);color:var(--muted)}}
.goal-del{{cursor:pointer;color:var(--hint);font-size:15px;flex-shrink:0}}
.goal-del:hover{{color:var(--muted)}}
.empty{{font-size:13px;color:var(--hint);text-align:center;padding:2rem 0}}
.updated{{font-size:11px;color:var(--hint);text-align:center;margin-top:2rem;padding-bottom:2rem}}
.divider{{height:1px;background:var(--border);margin:1.5rem 0}}
</style>
</head>
<body>
<div class="page">

<div class="header">
  <div class="logo-row">
    <div class="logo"><i class="ti ti-activity"></i></div>
    <div>
      <h1>WHOOP Dashboard</h1>
      <div class="sub">Auto-synced from your daily export</div>
    </div>
  </div>
  <div class="badge">Updated {d['last_updated']}</div>
</div>

<div class="section-label">Today's overview</div>
<div class="grid4">
  <div class="metric">
    <div class="lbl"><i class="ti ti-heart-rate-monitor" style="font-size:13px"></i>Recovery</div>
    <div class="val" style="color:{d['rec_color']}">{d['recovery']}<span style="font-size:14px;font-weight:400">%</span></div>
    <div class="unit">{d['rec_label']}</div>
    <div class="bar"><div class="bar-fill" style="width:{d['recovery']}%;background:{d['rec_color']}"></div></div>
  </div>
  <div class="metric">
    <div class="lbl"><i class="ti ti-flame" style="font-size:13px"></i>Day Strain</div>
    <div class="val" style="color:{d['strain_color']}">{d['strain']}</div>
    <div class="unit">of 21 max</div>
    <div class="bar"><div class="bar-fill" style="width:{round(d['strain']/21*100)}%;background:{d['strain_color']}"></div></div>
  </div>
  <div class="metric">
    <div class="lbl"><i class="ti ti-moon" style="font-size:13px"></i>Sleep</div>
    <div class="val">{d['sleep_h']}<span style="font-size:14px;font-weight:400">h {d['sleep_mm']}m</span></div>
    <div class="unit">{d['sleep_perf']}% performance</div>
    <div class="bar"><div class="bar-fill" style="width:{d['sleep_bar_pct']}%;background:var(--purple)"></div></div>
  </div>
  <div class="metric">
    <div class="lbl"><i class="ti ti-heartbeat" style="font-size:13px"></i>HRV</div>
    <div class="val">{d['hrv']}<span style="font-size:14px;font-weight:400">ms</span></div>
    <div class="unit">7-day avg {d['hrv_avg']}ms</div>
    <div class="bar"><div class="bar-fill" style="width:{min(100,round(d['hrv']/120*100))}%;background:var(--amber)"></div></div>
  </div>
</div>

<div class="grid2">
  <div class="card" style="margin-bottom:0">
    <div class="section-label">Recovery detail</div>
    <div class="recovery-row">
      <div class="ring-wrap">
        <svg width="100" height="100" viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="40" fill="none" stroke="rgba(255,255,255,.07)" stroke-width="8"/>
          <circle cx="50" cy="50" r="40" fill="none" stroke="{d['rec_color']}" stroke-width="8"
            stroke-dasharray="251.3" stroke-dashoffset="{round(251.3*(1-d['recovery']/100),1)}"
            stroke-linecap="round" transform="rotate(-90 50 50)"/>
        </svg>
        <div class="ring-center">
          <span class="ring-pct" style="color:{d['rec_color']}">{d['recovery']}</span>
          <span class="ring-lbl">score</span>
        </div>
      </div>
      <div class="recovery-stats">
        <div><div class="rs-label">Resting HR</div><div class="rs-val">{d['rhr']} bpm</div></div>
        <div><div class="rs-label">HRV</div><div class="rs-val">{d['hrv']} ms</div></div>
        <div><div class="rs-label">SpO₂</div><div class="rs-val">{d['spo2']}%</div></div>
        <div><div class="rs-label">Skin temp</div><div class="rs-val">{d['skin_temp']}°F</div></div>
      </div>
    </div>
  </div>
  <div class="card" style="margin-bottom:0">
    <div class="section-label">Sleep breakdown</div>
    <div class="sleep-bars">
      <div class="sleep-row">
        <span class="sleep-lbl">Total</span>
        <div class="sleep-track"><div class="sleep-fill" style="width:{d['sleep_bar_pct']}%;background:var(--purple)"></div></div>
        <span class="sleep-val">{d['sleep_h']}h{d['sleep_mm']}m</span>
      </div>
      <div class="sleep-row">
        <span class="sleep-lbl">REM</span>
        <div class="sleep-track"><div class="sleep-fill" style="width:{min(100,round(d['rem_m']/90*100))}%;background:#818cf8"></div></div>
        <span class="sleep-val">{d['rem_h']}h{d['rem_m']}m</span>
      </div>
      <div class="sleep-row">
        <span class="sleep-lbl">Deep</span>
        <div class="sleep-track"><div class="sleep-fill" style="width:{min(100,round(d['deep_m']/75*100))}%;background:#6366f1"></div></div>
        <span class="sleep-val">{d['deep_h']}h{d['deep_m']}m</span>
      </div>
      <div class="sleep-row">
        <span class="sleep-lbl">Light</span>
        <div class="sleep-track"><div class="sleep-fill" style="width:{min(100,round(d['light_m']/280*100))}%;background:#c4b5fd"></div></div>
        <span class="sleep-val">{d['light_h']}h{d['light_m']}m</span>
      </div>
      <div class="sleep-row">
        <span class="sleep-lbl">Latency</span>
        <div class="sleep-track"><div class="sleep-fill" style="width:{min(100,round(d['latency']/30*100))}%;background:#ddd6fe"></div></div>
        <span class="sleep-val">{d['latency']}m</span>
      </div>
    </div>
  </div>
</div>

<div class="card" style="margin-top:1.5rem">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
    <div class="section-label" style="margin:0">HRV trend — 7 days</div>
    <span style="font-size:11px;color:var(--hint)">ms</span>
  </div>
  <div class="chart-wrap">
    <canvas id="hrvChart" role="img" aria-label="7-day HRV trend"></canvas>
  </div>
</div>

<div class="card">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
    <div class="section-label" style="margin:0">Recovery trend — 7 days</div>
    <span style="font-size:11px;color:var(--hint)">%</span>
  </div>
  <div class="chart-wrap">
    <canvas id="recChart" role="img" aria-label="7-day recovery trend"></canvas>
  </div>
</div>

<div class="divider"></div>

<div class="goals-header">
  <div class="section-label" style="margin:0">Daily goals & tasks</div>
  <button class="add-btn" onclick="toggleInput()"><i class="ti ti-plus" style="font-size:13px"></i> Add goal</button>
</div>

<div class="input-row" id="inputRow">
  <input type="text" id="goalInput" placeholder="What do you want to accomplish today?" onkeydown="if(event.key==='Enter')addGoal()"/>
  <select id="goalTag">
    <option value="fitness">Fitness</option>
    <option value="nutrition">Nutrition</option>
    <option value="wellness">Wellness</option>
    <option value="work">Work</option>
    <option value="other">Other</option>
  </select>
  <button onclick="addGoal()">Add</button>
</div>

<div class="goals-list" id="goalsList"></div>
<div class="empty" id="emptyMsg">No goals yet — add something to get done today</div>

<div class="updated">Last synced from WHOOP export · {d['last_updated']}</div>

</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const HRV_DATA   = {json.dumps(d['hrv_trend'])};
const REC_DATA   = {json.dumps(d['rec_trend'])};
const DAY_LABELS = {json.dumps(d['day_labels'])};

const base = {{
  responsive:true, maintainAspectRatio:false,
  plugins:{{legend:{{display:false}}}},
  scales:{{
    x:{{grid:{{display:false}},ticks:{{font:{{size:10}},color:'#555'}}}},
    y:{{grid:{{color:'rgba(255,255,255,.05)'}},ticks:{{font:{{size:10}},color:'#555'}}}}
  }}
}};

new Chart(document.getElementById('hrvChart'),{{
  type:'line',
  data:{{labels:DAY_LABELS,datasets:[{{
    data:HRV_DATA,borderColor:'#00c47e',backgroundColor:'rgba(0,196,126,.08)',
    borderWidth:2,pointRadius:3,pointBackgroundColor:'#00c47e',fill:true,tension:.4
  }}]}},
  options:{{...base,scales:{{...base.scales,y:{{...base.scales.y,
    min:Math.max(0,Math.min(...HRV_DATA)-10),max:Math.max(...HRV_DATA)+10}}}}}}
}});

new Chart(document.getElementById('recChart'),{{
  type:'line',
  data:{{labels:DAY_LABELS,datasets:[{{
    data:REC_DATA,borderColor:'#4ea6ff',backgroundColor:'rgba(78,166,255,.08)',
    borderWidth:2,pointRadius:3,pointBackgroundColor:'#4ea6ff',fill:true,tension:.4
  }}]}},
  options:{{...base,scales:{{...base.scales,y:{{...base.scales.y,min:0,max:100}}}}}}
}});

const TAG_LABELS = {{fitness:'Fitness',nutrition:'Nutrition',wellness:'Wellness',work:'Work',other:'Other'}};
let goals = JSON.parse(localStorage.getItem('whoopGoals')||'[]');

function save(){{localStorage.setItem('whoopGoals',JSON.stringify(goals));}}
function toggleInput(){{
  document.getElementById('inputRow').classList.toggle('show');
  if(document.getElementById('inputRow').classList.contains('show'))
    document.getElementById('goalInput').focus();
}}
function addGoal(){{
  const inp=document.getElementById('goalInput');
  const tag=document.getElementById('goalTag').value;
  const text=inp.value.trim();
  if(!text)return;
  goals.push({{id:Date.now(),text,tag,done:false}});
  inp.value='';save();render();
  document.getElementById('inputRow').classList.remove('show');
}}
function toggleGoal(id){{const g=goals.find(x=>x.id===id);if(g){{g.done=!g.done;save();render();}}}}
function deleteGoal(id){{goals=goals.filter(x=>x.id!==id);save();render();}}
function render(){{
  const list=document.getElementById('goalsList');
  const empty=document.getElementById('emptyMsg');
  if(!goals.length){{list.innerHTML='';empty.style.display='block';return;}}
  empty.style.display='none';
  list.innerHTML=goals.map(g=>`
    <div class="goal-item${{g.done?' done':''}}">
      <div class="goal-check${{g.done?' checked':''}}" onclick="toggleGoal(${{g.id}})" role="checkbox" aria-checked="${{g.done}}" tabindex="0">
        ${{g.done?'<i class="ti ti-check"></i>':''}}
      </div>
      <span class="goal-text">${{g.text}}</span>
      <span class="goal-tag t-${{g.tag}}">${{TAG_LABELS[g.tag]}}</span>
      <i class="ti ti-x goal-del" onclick="deleteGoal(${{g.id}})" aria-label="Remove" tabindex="0"></i>
    </div>`).join('');
}}
render();
</script>
</body>
</html>"""


class WhoopHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and self._match(event.src_path):
            print(f"\n📥 New WHOOP export detected: {os.path.basename(event.src_path)}")
            time.sleep(1)
            self.process(event.src_path)

    def on_modified(self, event):
        if not event.is_directory and self._match(event.src_path):
            time.sleep(1)
            self.process(event.src_path)

    def _match(self, path):
        import fnmatch
        return fnmatch.fnmatch(os.path.basename(path).lower(), CSV_PATTERN.lower())

    def process(self, filepath):
        try:
            print("⚙️  Parsing data...")
            data = parse_whoop_csv(filepath)
            html = build_html(data)
            os.makedirs(REPO_DIR, exist_ok=True)
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"✅ Dashboard updated")
            print(f"   Recovery: {data['recovery']}%  |  HRV: {data['hrv']}ms  |  Sleep: {data['sleep_h']}h{data['sleep_mm']}m")
            push_to_github()
            self.cleanup(filepath)
        except Exception as e:
            print(f"❌ Error: {e}")

    def cleanup(self, csv_path):
        """Delete the CSV and any matching ZIP from Downloads after a successful push."""
        try:
            os.remove(csv_path)
            print(f"🗑️  Deleted CSV: {os.path.basename(csv_path)}")
        except Exception as e:
            print(f"⚠️  Could not delete CSV: {e}")
        for zip_file in glob.glob(os.path.join(WATCH_FOLDER, "whoop*.zip")):
            try:
                os.remove(zip_file)
                print(f"🗑️  Deleted ZIP: {os.path.basename(zip_file)}")
            except Exception as e:
                print(f"⚠️  Could not delete ZIP: {e}")


def process_existing():
    matches = glob.glob(os.path.join(WATCH_FOLDER, CSV_PATTERN))
    if not matches:
        return
    latest = max(matches, key=os.path.getmtime)
    print(f"📂 Found existing export: {os.path.basename(latest)}")
    WhoopHandler().process(latest)


if __name__ == "__main__":
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  WHOOP Dashboard Auto-Updater")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    ensure_repo()

    print(f"👀 Watching: {WATCH_FOLDER}")
    print(f"📦 Repo:     {REPO_DIR}")
    print(f"🌐 GitHub:   {GITHUB_REPO}\n")

    process_existing()

    observer = Observer()
    observer.schedule(WhoopHandler(), WATCH_FOLDER, recursive=False)
    observer.start()
    print("✅ Watcher running — press Ctrl+C to stop\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n👋 Stopped.")
    observer.join()
