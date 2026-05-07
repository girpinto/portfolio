import json
import urllib.request
import webbrowser
import os
import time as time_module
from pathlib import Path

# ─── CONFIG ───
YEAR = 2026
ROUND = 6  # Miami — verifica il numero del round

# ─── FETCH DATA ───
def fetch_json(url):
    print(f"  Fetching {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "F1DashboardBuilder/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())

def get_round_number():
    """Find the round number for Miami GP"""
    data = fetch_json(f"https://api.jolpi.ca/ergast/f1/{YEAR}.json")
    races = data["MRData"]["RaceTable"]["Races"]
    for race in races:
        if "miami" in race["raceName"].lower() or "miami" in race.get("Circuit", {}).get("circuitId", "").lower():
            return int(race["round"])
    return ROUND  # fallback

def fetch_race_data(round_num):
    print(f"\n[1/3] Fetching race results...")
    results = fetch_json(
        f"https://api.jolpi.ca/ergast/f1/{YEAR}/{round_num}/results.json"
    )

    print(f"[2/3] Fetching lap times...")
    all_laps = []
    offset = 0
    while True:
        data = fetch_json(
            f"https://api.jolpi.ca/ergast/f1/{YEAR}/{round_num}/laps.json?limit=1000&offset={offset}"
        )
        laps = data["MRData"]["RaceTable"]["Races"]
        if not laps or not laps[0].get("Laps"):
            break
        all_laps.extend(laps[0]["Laps"])
        total = int(data["MRData"]["total"])
        offset += 1000
        if offset >= total:
            break

    print(f"[3/3] Fetching pit stops...")
    pitstops = fetch_json(
        f"https://api.jolpi.ca/ergast/f1/{YEAR}/{round_num}/pitstops.json"
    )

    return results, all_laps, pitstops

def parse_lap_time(time_str):
    """Convert '1:31.234' or '1:02.345' to seconds"""
    if ":" in time_str:
        parts = time_str.split(":")
        return float(parts[0]) * 60 + float(parts[1])
    return float(time_str)

def process_data(results, all_laps, pitstops):
    race_data = results["MRData"]["RaceTable"]["Races"][0]
    race_name = race_data["raceName"]
    circuit = race_data["Circuit"]["circuitName"]

    # Build driver info
    drivers = {}
    for res in race_data["Results"]:
        driver_id = res["Driver"]["driverId"]
        drivers[driver_id] = {
            "code": res["Driver"].get("code", driver_id[:3].upper()),
            "name": f"{res['Driver']['givenName']} {res['Driver']['familyName']}",
            "team": res["Constructor"]["name"],
            "grid": int(res["grid"]),
            "position": res.get("positionText", "R"),
            "status": res.get("status", ""),
            "laps_completed": int(res.get("laps", 0)),
        }

    # Build lap times per driver
    driver_laps = {did: [] for did in drivers}
    for lap_data in all_laps:
        lap_num = int(lap_data["number"])
        for timing in lap_data["Timings"]:
            did = timing["driverId"]
            if did in driver_laps:
                driver_laps[did].append({
                    "lap": lap_num,
                    "time": parse_lap_time(timing["time"]),
                    "position": int(timing["position"]),
                })

    # Calculate cumulative times
    for did in driver_laps:
        cumulative = 0
        for lap in driver_laps[did]:
            cumulative += lap["time"]
            lap["cumulative"] = cumulative

    # Pit stops
    pit_data = {}
    try:
        pits = pitstops["MRData"]["RaceTable"]["Races"][0]["PitStops"]
        for pit in pits:
            did = pit["driverId"]
            if did not in pit_data:
                pit_data[did] = []
            pit_data[did].append({
                "lap": int(pit["lap"]),
                "duration": float(pit["duration"]) if pit.get("duration") else 0,
            })
    except (KeyError, IndexError):
        pass

    # Team colors
    team_colors = {
        "Red Bull": "#3671C6", "McLaren": "#FF8000",
        "Ferrari": "#E8002D", "Mercedes": "#27F4D2",
        "Aston Martin": "#229971", "Alpine": "#FF87BC",
        "Williams": "#64C4FF", "RB": "#6692FF",
        "Sauber": "#52E252", "Haas": "#B6BABD",
        # 2026 variations
        "Cadillac": "#FFD700", "Racing Bulls": "#6692FF",
        "Kick Sauber": "#52E252",
    }

    driver_list = []
    for did, info in drivers.items():
        laps = driver_laps.get(did, [])
        total_time = laps[-1]["cumulative"] if laps else 0
        color = "#FFFFFF"
        for team_name, tc in team_colors.items():
            if team_name.lower() in info["team"].lower():
                color = tc
                break

        driver_list.append({
            "id": did,
            "code": info["code"],
            "name": info["name"],
            "team": info["team"],
            "color": color,
            "grid": info["grid"],
            "result": info["position"],
            "status": info["status"],
            "laps": [{"lap": l["lap"], "time": l["time"], "cum": l["cumulative"], "pos": l["position"]} for l in laps],
            "pits": pit_data.get(did, []),
        })

    total_laps = max((d["laps"][-1]["lap"] for d in driver_list if d["laps"]), default=57)
    race_duration = max((d["laps"][-1]["cum"] for d in driver_list if d["laps"]), default=5400)

    return {
        "race_name": race_name,
        "circuit": circuit,
        "total_laps": total_laps,
        "race_duration": race_duration,
        "drivers": sorted(driver_list, key=lambda d: d["grid"]),
    }

# ─── MIAMI TRACK COORDINATES (stylized) ───
# Normalized 0-1000 coordinate system, ~80 points tracing the circuit
MIAMI_TRACK = [
    [589,630],[385,522],[370,510],[370,492],[405,459],[409,403],[417,389],[433,375],
    [480,355],[536,353],[570,364],[728,443],[760,443],[811,412],[837,408],[857,413],
    [896,442],[920,449],[955,440],[987,418],[1000,392],[996,368],[974,354],[922,358],
    [822,344],[620,355],[592,349],[519,324],[477,317],[417,319],[370,328],[316,345],
    [184,400],[57,469],[50,478],[49,486],[93,517],[98,531],[96,546],[83,561],
    [26,570],[0,609],[14,623],[5,672],[13,682],[882,674],[893,662],[890,652],
    [878,643],[844,623],[823,618],[789,622],[738,649],[692,660],[644,655],[589,630],
]

def generate_html(race_data):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{race_data['race_name']} — Race Replay</title>
<style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{
        font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
        background: #0a0a0f;
        color: #e0e0e0;
        overflow-x: hidden;
    }}

    .header {{
        padding: 1.5rem 2rem;
        background: #111118;
        border-bottom: 1px solid #222;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }}
    .header h1 {{
        font-size: 1.4rem;
        font-weight: 600;
    }}
    .header h1 span {{ color: #e8002d; }}
    .header-info {{
        font-size: 0.8rem;
        color: #888;
    }}

    .main {{
        display: grid;
        grid-template-columns: 1fr 320px;
        height: calc(100vh - 72px);
    }}

    .track-panel {{
        position: relative;
        display: flex;
        flex-direction: column;
    }}

    .track-container {{
        flex: 1;
        position: relative;
        padding: 2rem;
    }}

    .track-svg {{
        width: 100%;
        height: 100%;
    }}

    .controls {{
        padding: 1rem 2rem;
        background: #111118;
        border-top: 1px solid #222;
        display: flex;
        align-items: center;
        gap: 1rem;
    }}

    .play-btn {{
        width: 40px;
        height: 40px;
        border-radius: 50%;
        border: 2px solid #e8002d;
        background: transparent;
        color: #e8002d;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1rem;
        transition: all 0.2s;
    }}
    .play-btn:hover {{
        background: #e8002d;
        color: #fff;
    }}

    .timeline {{
        flex: 1;
        display: flex;
        flex-direction: column;
        gap: 0.3rem;
    }}

    .timeline-bar {{
        width: 100%;
        height: 6px;
        -webkit-appearance: none;
        appearance: none;
        background: #222;
        border-radius: 3px;
        outline: none;
        cursor: pointer;
    }}
    .timeline-bar::-webkit-slider-thumb {{
        -webkit-appearance: none;
        width: 14px;
        height: 14px;
        border-radius: 50%;
        background: #e8002d;
        cursor: pointer;
    }}

    .timeline-info {{
        display: flex;
        justify-content: space-between;
        font-size: 0.75rem;
        color: #666;
        font-variant-numeric: tabular-nums;
    }}

    .speed-btns {{
        display: flex;
        gap: 0.3rem;
    }}
    .speed-btn {{
        padding: 0.25rem 0.6rem;
        border: 1px solid #333;
        background: transparent;
        color: #888;
        font-size: 0.7rem;
        cursor: pointer;
        transition: all 0.2s;
    }}
    .speed-btn.active {{
        border-color: #e8002d;
        color: #e8002d;
    }}

    .sidebar {{
        background: #111118;
        border-left: 1px solid #222;
        overflow-y: auto;
        scrollbar-width: thin;
        scrollbar-color: #333 #111118;
    }}

    .sidebar-header {{
        padding: 1rem 1.2rem;
        border-bottom: 1px solid #222;
        font-size: 0.75rem;
        color: #666;
        text-transform: uppercase;
        letter-spacing: 2px;
        position: sticky;
        top: 0;
        background: #111118;
        z-index: 10;
    }}

    .driver-row {{
        display: flex;
        align-items: center;
        padding: 0.5rem 1.2rem;
        border-bottom: 1px solid #1a1a22;
        transition: background 0.2s;
        cursor: default;
        gap: 0.6rem;
    }}
    .driver-row:hover {{
        background: #1a1a22;
    }}

    .driver-pos {{
        width: 24px;
        font-size: 0.85rem;
        font-weight: 600;
        color: #888;
        text-align: center;
        font-variant-numeric: tabular-nums;
    }}

    .driver-color {{
        width: 3px;
        height: 24px;
        border-radius: 2px;
        flex-shrink: 0;
    }}

    .driver-info {{
        flex: 1;
        min-width: 0;
    }}

    .driver-code {{
        font-size: 0.85rem;
        font-weight: 600;
        letter-spacing: 0.5px;
    }}

    .driver-team {{
        font-size: 0.65rem;
        color: #555;
    }}

    .driver-gap {{
        font-size: 0.75rem;
        color: #666;
        font-variant-numeric: tabular-nums;
        text-align: right;
        min-width: 60px;
    }}

    .driver-status {{
        font-size: 0.6rem;
        color: #e8002d;
        text-transform: uppercase;
    }}

    .lap-counter {{
        font-size: 1.5rem;
        font-weight: 700;
        color: #fff;
        margin-right: 1rem;
        min-width: 100px;
        font-variant-numeric: tabular-nums;
    }}
    .lap-counter span {{
        font-size: 0.8rem;
        color: #666;
    }}

    .pit-indicator {{
        font-size: 0.55rem;
        background: #ff8000;
        color: #000;
        padding: 1px 4px;
        border-radius: 2px;
        font-weight: 600;
        margin-left: auto;
    }}
</style>
</head>
<body>

<div class="header">
    <h1><span>F1</span> {race_data['race_name']}</h1>
    <div class="header-info">{race_data['circuit']} — {race_data['total_laps']} Laps</div>
</div>

<div class="main">
    <div class="track-panel">
        <div class="track-container">
            <svg class="track-svg" viewBox="-50 267 1100 465" preserveAspectRatio="xMidYMid meet" id="trackSvg">
                <defs>
                    <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
                        <feGaussianBlur stdDeviation="4" result="blur"/>
                        <feMerge>
                            <feMergeNode in="blur"/>
                            <feMergeNode in="SourceGraphic"/>
                        </feMerge>
                    </filter>
                </defs>
                <!-- Track outline -->
                <polyline id="trackPath" fill="none" stroke="#222" stroke-width="16" stroke-linecap="round" stroke-linejoin="round"
                    points="{' '.join(f'{p[0]},{p[1]}' for p in MIAMI_TRACK)}" />
                <polyline fill="none" stroke="#333" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"
                    points="{' '.join(f'{p[0]},{p[1]}' for p in MIAMI_TRACK)}" />
                <!-- Start/finish line -->
                <line x1="589" y1="620" x2="589" y2="640" stroke="#fff" stroke-width="2" opacity="0.6"/>
                <text x="595" y="618" fill="#555" font-size="9" font-family="monospace">S/F</text>
                <!-- Turn labels -->
                
                <!-- Driver dots will be added by JS -->
            </svg>
        </div>
        <div class="controls">
            <button class="play-btn" id="playBtn" onclick="togglePlay()">&#9654;</button>
            <div class="lap-counter" id="lapCounter">Lap <span>0/{race_data['total_laps']}</span></div>
            <div class="timeline">
                <input type="range" class="timeline-bar" id="timeSlider" min="0" max="1000" value="0" oninput="onSlider(this.value)">
                <div class="timeline-info">
                    <span id="timeElapsed">0:00</span>
                    <span id="timeTotal">0:00</span>
                </div>
            </div>
            <div class="speed-btns">
                <button class="speed-btn" onclick="setSpeed(1)">1x</button>
                <button class="speed-btn active" onclick="setSpeed(5)">5x</button>
                <button class="speed-btn" onclick="setSpeed(15)">15x</button>
                <button class="speed-btn" onclick="setSpeed(30)">30x</button>
            </div>
        </div>
    </div>
    <div class="sidebar">
        <div class="sidebar-header">Live Standings</div>
        <div id="standings"></div>
    </div>
</div>

<script>
var RACE = {json.dumps(race_data, ensure_ascii=False)};
var TRACK = {json.dumps(MIAMI_TRACK)};

// Precompute track distances
var trackDist = [0];
for (var i = 1; i < TRACK.length; i++) {{
    var dx = TRACK[i][0] - TRACK[i-1][0];
    var dy = TRACK[i][1] - TRACK[i-1][1];
    trackDist.push(trackDist[i-1] + Math.sqrt(dx*dx + dy*dy));
}}
var totalTrackLen = trackDist[trackDist.length - 1];

function getTrackPoint(fraction) {{
    // fraction 0..1 along the track
    var target = fraction * totalTrackLen;
    for (var i = 1; i < trackDist.length; i++) {{
        if (trackDist[i] >= target) {{
            var segStart = trackDist[i-1];
            var segEnd = trackDist[i];
            var t = (target - segStart) / (segEnd - segStart);
            return [
                TRACK[i-1][0] + t * (TRACK[i][0] - TRACK[i-1][0]),
                TRACK[i-1][1] + t * (TRACK[i][1] - TRACK[i-1][1])
            ];
        }}
    }}
    return TRACK[TRACK.length - 1];
}}

// Create driver dots
var svg = document.getElementById('trackSvg');
var dots = {{}};
RACE.drivers.forEach(function(d) {{
    var g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('id', 'dot-' + d.id);

    var circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('r', '8');
    circle.setAttribute('fill', d.color);
    circle.setAttribute('stroke', '#000');
    circle.setAttribute('stroke-width', '1.5');
    circle.setAttribute('opacity', '0.95');
    g.appendChild(circle);

    var label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    label.setAttribute('text-anchor', 'middle');
    label.setAttribute('dy', '-12');
    label.setAttribute('fill', d.color);
    label.setAttribute('font-size', '9');
    label.setAttribute('font-family', 'monospace');
    label.setAttribute('font-weight', '600');
    label.textContent = d.code;
    g.appendChild(label);

    svg.appendChild(g);
    dots[d.id] = g;
}});

// Simulation state
var playing = false;
var currentTime = 0;
var speed = 5;
var raceDuration = RACE.race_duration;
var lastFrame = 0;

function getDriverState(driver, time) {{
    if (!driver.laps.length) return {{ lap:0, fraction:0, position:99, retired:true, inPit:false }};

    for (var i = 0; i < driver.laps.length; i++) {{
        if (driver.laps[i].cum > time) {{
            var currentLap = driver.laps[i].lap;
            var prevCum = i > 0 ? driver.laps[i-1].cum : 0;
            var lapTime = driver.laps[i].time;
            var timeInLap = time - prevCum;
            var fraction = Math.max(0, Math.min(1, timeInLap / lapTime));

            var inPit = false;
            for (var p = 0; p < driver.pits.length; p++) {{
                var pit = driver.pits[p];
                if (pit.lap === currentLap && pit.duration > 0) {{
                    var normalLapTime = lapTime - pit.duration;
                    if (normalLapTime < 0) normalLapTime = lapTime * 0.7;
                    var pitEntryFraction = normalLapTime / lapTime;
                    if (fraction >= pitEntryFraction) {{
                        inPit = true;
                        fraction = pitEntryFraction + (fraction - pitEntryFraction) * 0.5;
                    }}
                }}
            }}

            return {{
                lap: currentLap,
                fraction: fraction,
                position: driver.laps[i].pos,
                retired: false,
                inPit: inPit
            }};
        }}
    }}

    var lastLap = driver.laps[driver.laps.length - 1];
    var finished = driver.status === 'Finished' ||
                   driver.status.indexOf('Lap') !== -1;
    return {{
        lap: lastLap.lap,
        fraction: finished ? 1 : lastLap.cum < time ? 1 : 0,
        position: lastLap.pos,
        retired: !finished,
        inPit: false
    }};
}}

function updateDisplay(time) {{
    var states = [];

    RACE.drivers.forEach(function(d) {{
        var state = getDriverState(d, time);
        states.push({{ driver: d, state: state }});
    }});

    // ── SORT BY REAL POSITION ──
    // Use the API position from the most recent completed lap
    // This is the actual race classification
    states.sort(function(a, b) {{
        var aRetired = a.state.retired;
        var bRetired = b.state.retired;
        if (aRetired && !bRetired) return 1;
        if (!aRetired && bRetired) return -1;
        if (aRetired && bRetired) return b.state.lap - a.state.lap;

        // Primary: who has completed more laps is ahead
        if (a.state.lap !== b.state.lap) return b.state.lap - a.state.lap;

        // Same lap: use the API position (real classification)
        return a.state.position - b.state.position;
    }});

    // ── UPDATE DOTS WITH OFFSET TO PREVENT OVERLAP ──
    states.forEach(function(s, idx) {{
        var d = s.driver;
        var st = s.state;
        var g = dots[d.id];
        var pos = idx + 1;

        if (st.retired && time > (d.laps.length ? d.laps[d.laps.length-1].cum : 0) + 5) {{
            g.setAttribute('opacity', '0.15');
            return;
        }}

        g.setAttribute('opacity', '1');

        // ── KEY FIX: offset fraction by time gap from leader ──
        // Drivers on the same lap but behind get their fraction reduced
        // proportionally to their time gap, so they appear behind on track
        var visualFraction = st.fraction;

        if (idx > 0 && !st.retired) {{
            var leaderState = states[0].state;
            if (st.lap === leaderState.lap) {{
                // Same lap as leader: offset based on position
                // Find this driver's last completed lap time vs leader's
                var myLapIdx = Math.min(st.lap - 1, d.laps.length - 1);
                var leaderLapIdx = Math.min(st.lap - 1, states[0].driver.laps.length - 1);
                if (myLapIdx >= 0 && leaderLapIdx >= 0) {{
                    var myCum = d.laps[myLapIdx].cum;
                    var leaderCum = states[0].driver.laps[leaderLapIdx].cum;
                    var gap = myCum - leaderCum;
                    // Convert gap to fraction of a lap (avg lap ~90s)
                    var avgLap = d.laps[myLapIdx].time || 90;
                    var fractionOffset = gap / avgLap;
                    visualFraction = leaderState.fraction - fractionOffset;
                    // Wrap around
                    while (visualFraction < 0) visualFraction += 1;
                    while (visualFraction > 1) visualFraction -= 1;
                }}
            }} else {{
                // Lapped: just use their own fraction
                visualFraction = st.fraction;
            }}
        }}

        var pt = getTrackPoint(visualFraction);
        var circle = g.querySelector('circle');
        var label = g.querySelector('text');

        circle.setAttribute('cx', pt[0]);
        circle.setAttribute('cy', pt[1]);
        label.setAttribute('x', pt[0]);
        label.setAttribute('y', pt[1]);

        // Size: leader biggest
        var radius = Math.max(5, 11 - pos * 0.3);
        circle.setAttribute('r', radius);

        // Visual styling
        if (pos === 1) {{
            circle.setAttribute('stroke', d.color);
            circle.setAttribute('stroke-width', '3');
            circle.setAttribute('filter', 'url(#glow)');
        }} else if (st.inPit) {{
            circle.setAttribute('stroke', '#ff8000');
            circle.setAttribute('stroke-width', '3');
            circle.setAttribute('filter', '');
        }} else {{
            circle.setAttribute('stroke', '#000');
            circle.setAttribute('stroke-width', '1.5');
            circle.setAttribute('filter', '');
        }}

        label.textContent = pos + ' ' + d.code;
        label.setAttribute('dy', '-' + (radius + 4));
        label.setAttribute('font-size', pos <= 3 ? '10' : '8');

        // Bring podium to front
        if (pos <= 3) {{
            svg.appendChild(g);
        }}
    }});

    // ── SIDEBAR ──
    var html = '';
    states.forEach(function(s, i) {{
        var d = s.driver;
        var st = s.state;
        var pos = i + 1;
        var gap = '';

        if (i === 0) {{
            gap = 'Leader';
        }} else if (st.retired) {{
            gap = '<span class="driver-status">' + d.status + '</span>';
        }} else {{
            var leaderLap = states[0].state.lap;
            var lapDiff = leaderLap - st.lap;
            if (lapDiff >= 1) {{
                gap = '+' + lapDiff + ' Lap' + (lapDiff > 1 ? 's' : '');
            }} else {{
                // Time gap from cumulative lap times
                var myIdx = Math.min(st.lap - 1, d.laps.length - 1);
                var leaderIdx = Math.min(st.lap - 1, states[0].driver.laps.length - 1);
                if (myIdx >= 0 && leaderIdx >= 0) {{
                    var timeDiff = d.laps[myIdx].cum - states[0].driver.laps[leaderIdx].cum;
                    if (timeDiff < 0) timeDiff = 0;
                    if (timeDiff < 60) {{
                        gap = '+' + timeDiff.toFixed(1) + 's';
                    }} else {{
                        var m = Math.floor(timeDiff / 60);
                        var sec = (timeDiff % 60).toFixed(1);
                        gap = '+' + m + ':' + (parseFloat(sec) < 10 ? '0' : '') + sec;
                    }}
                }}
            }}
        }}

        var pitHtml = '';
        if (st.inPit) {{
            var pitCount = 0;
            for (var p = 0; p < d.pits.length; p++) {{
                if (d.pits[p].lap <= st.lap) pitCount++;
            }}
            pitHtml = '<span class="pit-indicator">PIT ' + pitCount + '</span>';
        }}

        var rowStyle = pos === 1 ? 'border-left:3px solid ' + d.color + ';' : '';

        html += '<div class="driver-row" style="' + rowStyle + '">' +
            '<div class="driver-pos">' + pos + '</div>' +
            '<div class="driver-color" style="background:' + d.color + '"></div>' +
            '<div class="driver-info">' +
                '<div class="driver-code">' + d.code + '</div>' +
                '<div class="driver-team">' + d.team + '</div>' +
            '</div>' +
            pitHtml +
            '<div class="driver-gap">' + gap + '</div>' +
        '</div>';
    }});
    document.getElementById('standings').innerHTML = html;

    var maxLap = 0;
    states.forEach(function(s) {{ if (s.state.lap > maxLap) maxLap = s.state.lap; }});
    document.getElementById('lapCounter').innerHTML = 'Lap <span>' + Math.min(maxLap, RACE.total_laps) + '/' + RACE.total_laps + '</span>';

    var mins = Math.floor(time / 60);
    var secs = Math.floor(time % 60);
    document.getElementById('timeElapsed').textContent = mins + ':' + (secs < 10 ? '0' : '') + secs;
    document.getElementById('timeSlider').value = Math.floor((time / raceDuration) * 1000);
}}

function animate(timestamp) {{
    if (!playing) return;
    if (!lastFrame) lastFrame = timestamp;
    var delta = (timestamp - lastFrame) / 1000;
    lastFrame = timestamp;
    currentTime = Math.min(currentTime + delta * speed, raceDuration);

    updateDisplay(currentTime);

    if (currentTime >= raceDuration) {{
        playing = false;
        document.getElementById('playBtn').innerHTML = '&#9654;';
        return;
    }}
    requestAnimationFrame(animate);
}}

function togglePlay() {{
    playing = !playing;
    document.getElementById('playBtn').innerHTML = playing ? '&#9646;&#9646;' : '&#9654;';
    if (playing) {{
        lastFrame = 0;
        if (currentTime >= raceDuration) currentTime = 0;
        requestAnimationFrame(animate);
    }}
}}

function onSlider(val) {{
    currentTime = (val / 1000) * raceDuration;
    updateDisplay(currentTime);
}}

function setSpeed(s) {{
    speed = s;
    document.querySelectorAll('.speed-btn').forEach(function(btn) {{
        btn.classList.toggle('active', parseFloat(btn.textContent) === s);
    }});
}}

// Initial display
var totalMins = Math.floor(raceDuration / 60);
var totalSecs = Math.floor(raceDuration % 60);
document.getElementById('timeTotal').textContent = totalMins + ':' + (totalSecs < 10 ? '0' : '') + totalSecs;
updateDisplay(0);
</script>
</body>
</html>"""


# ─── MAIN ───
def main():
    print("=" * 50)
    print("  F1 RACE REPLAY DASHBOARD BUILDER")
    print("=" * 50)

    print("\nFinding Miami GP round number...")
    round_num = get_round_number()
    print(f"  → Round {round_num}")

    results, laps, pitstops = fetch_race_data(round_num)
    print(f"\nProcessing data...")
    race_data = process_data(results, laps, pitstops)
    print(f"  → {len(race_data['drivers'])} drivers")
    print(f"  → {race_data['total_laps']} laps")
    print(f"  → {race_data['race_duration']:.0f}s race duration")

    print("\nGenerating dashboard...")
    html = generate_html(race_data)
    out_path = Path("f1_miami_replay_app.html")
    out_path.write_text(html, encoding="utf-8")
    print(f"  → Saved to {out_path.absolute()}")

    print("\nOpening in browser...")
    webbrowser.open(f"file://{out_path.absolute()}")

if __name__ == "__main__":
    main()