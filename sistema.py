"""
"""

import streamlit as st
import sqlite3
import hashlib
import secrets
import json
import math
import os
from datetime import datetime, timezone

DB_PATH = os.environ.get("WG_DB_PATH", "cogitador.db")
REFRESH_S = 3.0
COMMS_FADE_S = 60

# ============================================================
#  DADOS DE WRATH & GLORY
# ============================================================
ATTRS = ["Strength", "Toughness", "Agility", "Initiative", "Willpower", "Intellect", "Fellowship"]
ATTR_PT = {"Strength": "Força", "Toughness": "Dureza", "Agility": "Agilidade",
           "Initiative": "Iniciativa", "Willpower": "Vontade", "Intellect": "Intelecto",
           "Fellowship": "Interação"}
SKILLS = {
    "Athletics": "Strength", "Awareness": "Intellect", "Ballistic Skill": "Agility",
    "Cunning": "Fellowship", "Deception": "Fellowship", "Insight": "Fellowship",
    "Intimidation": "Willpower", "Investigation": "Intellect", "Leadership": "Willpower",
    "Medicae": "Intellect", "Persuasion": "Fellowship", "Pilot": "Agility",
    "Psychic Mastery": "Willpower", "Scholar": "Intellect", "Stealth": "Agility",
    "Survival": "Willpower", "Tech": "Intellect", "Weapon Skill": "Initiative",
}
PLAYER_SPECIES = ["Adeptus Astartes", "Primaris Astartes", "Astra Militarum (Humano)",
                  "Adepta Sororitas", "Aeldari (Asuryani)", "Outro"]
NPC_SPECIES = ["Adeptus Astartes", "Primaris Astartes", "Chaos Space Marine",
               "Astra Militarum (Humano)", "Adepta Sororitas", "Inquisição", "Rogue Trader",
               "Aeldari (Asuryani)", "Drukhari", "Ork", "T'au", "Necron", "Tyranid",
               "Genestealer", "Daemon de Khorne", "Daemon de Nurgle", "Daemon de Tzeentch",
               "Daemon de Slaanesh", "Cultista do Caos", "Fera", "Servitor", "Outro"]
ATTR_COST = {1: 0, 2: 4, 3: 10, 4: 20, 5: 35, 6: 55, 7: 80, 8: 110, 9: 145, 10: 185, 11: 230, 12: 280}
SKILL_COST = {0: 0, 1: 2, 2: 6, 3: 12, 4: 20, 5: 30, 6: 42, 7: 56, 8: 72}
SPECIES_COST = {"Adeptus Astartes": 160, "Primaris Astartes": 198}
VITAL_FIELDS = {"cur_wounds", "cur_shock", "cur_wrath"}


def default_attributes():
    return {a: 1 for a in ATTRS}


def default_skills():
    return {s: 0 for s in SKILLS}


def is_astartes(sp):
    return "Astartes" in sp or "Space Marine" in sp


def is_loyal_astartes(sp):
    return "Astartes" in sp and "Chaos" not in sp


def species_speed(sp):
    if "Aeldari" in sp or "Drukhari" in sp:
        return 8
    return 7 if is_astartes(sp) else 6


def rank_from_xp(xp):
    xp = int(xp or 0)
    return min(3, 1 + xp // 40), xp >= 100


def derived_traits(ch):
    a, sk = ch["attributes"], ch["skills"]
    tier = int(ch.get("tier", 1)); armour = int(ch.get("armour", 0)); sp = ch.get("species", "")
    T = a.get("Toughness", 1); I = a.get("Initiative", 1); Wil = a.get("Willpower", 1)
    Intl = a.get("Intellect", 1); Fel = a.get("Fellowship", 1)
    return {
        "Defence": I - 1, "Resilience": T + 1 + armour, "Soak": T,
        "Max Wounds": T + 2 * tier + (3 if sp == "Primaris Astartes" else 0),
        "Max Shock": Wil + tier, "Max Wrath": tier, "Determination": T,
        "Resolve": max(0, Wil - 1) + (1 if is_loyal_astartes(sp) else 0),
        "Conviction": Wil, "Passive Awareness": math.ceil((Intl + sk.get("Awareness", 0)) / 2),
        "Influence": max(0, Fel - 1), "Speed": species_speed(sp),
    }


def xp_spent(ch):
    total = SPECIES_COST.get(ch.get("species", ""), 0)
    for a in ATTRS:
        total += ATTR_COST.get(int(ch["attributes"].get(a, 1)), 0)
    for s in SKILLS:
        total += SKILL_COST.get(int(ch["skills"].get(s, 0)), 0)
    for t in ch.get("talents", []):
        try:
            total += int(t.get("cost", 0))
        except Exception:
            pass
    total += int(ch.get("other_xp", 0))
    return total


def starting_xp(tier):
    return int(tier) * 100


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def secs_since(iso):
    if not iso:
        return 1e9
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()
    except Exception:
        return 1e9


# ============================================================
#  BANCO DE DADOS (com migração automática de schema)
# ============================================================
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def hash_pw(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100_000).hex()


def _ensure_columns(conn, table, cols):
    have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, ddl in cols.items():
        if name not in have:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def init_db():
    conn = get_conn(); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL, pw_hash TEXT NOT NULL, salt TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'player', created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS folders(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS characters(id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, kind TEXT DEFAULT 'player', name TEXT, chapter TEXT, species TEXT,
        tier INTEGER DEFAULT 2, earned_xp INTEGER DEFAULT 0, other_xp INTEGER DEFAULT 0,
        attributes TEXT, skills TEXT, talents TEXT, wargear TEXT, armour INTEGER DEFAULT 0,
        cur_wounds INTEGER DEFAULT 0, cur_shock INTEGER DEFAULT 0, cur_wrath INTEGER DEFAULT 0,
        notes TEXT, folder_id INTEGER, portrait BLOB, comms_on INTEGER DEFAULT 1, comms_changed_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS campaign(id INTEGER PRIMARY KEY CHECK (id=1),
        name TEXT, tier INTEGER DEFAULT 2, ruin INTEGER DEFAULT 0, session_no INTEGER DEFAULT 1)""")
    c.execute("""CREATE TABLE IF NOT EXISTS log(id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, author TEXT, text TEXT)""")
    conn.commit()
    # migração: garante colunas em bancos criados por versões antigas
    _ensure_columns(conn, "campaign", {"name": "TEXT", "tier": "INTEGER DEFAULT 2",
                                       "ruin": "INTEGER DEFAULT 0", "session_no": "INTEGER DEFAULT 1"})
    _ensure_columns(conn, "characters", {
        "user_id": "INTEGER", "kind": "TEXT DEFAULT 'player'", "name": "TEXT", "chapter": "TEXT",
        "species": "TEXT", "tier": "INTEGER DEFAULT 2", "earned_xp": "INTEGER DEFAULT 0",
        "other_xp": "INTEGER DEFAULT 0", "attributes": "TEXT", "skills": "TEXT", "talents": "TEXT",
        "wargear": "TEXT", "armour": "INTEGER DEFAULT 0", "cur_wounds": "INTEGER DEFAULT 0",
        "cur_shock": "INTEGER DEFAULT 0", "cur_wrath": "INTEGER DEFAULT 0", "notes": "TEXT",
        "folder_id": "INTEGER", "portrait": "BLOB", "comms_on": "INTEGER DEFAULT 1",
        "comms_changed_at": "TEXT"})
    _ensure_columns(conn, "folders", {"name": "TEXT"})
    conn.commit()
    if c.execute("SELECT COUNT(*) FROM campaign").fetchone()[0] == 0:
        c.execute("INSERT INTO campaign(id,name,tier,ruin,session_no) VALUES(1,?,2,0,1)", ("A Cruzada de Gilead",))
    if c.execute("SELECT COUNT(*) FROM users WHERE role='gm'").fetchone()[0] == 0:
        salt = secrets.token_hex(16)
        c.execute("INSERT INTO users(username,pw_hash,salt,role,created_at) VALUES(?,?,?,?,?)",
                  ("magister", hash_pw("AveImperator1", salt), salt, "gm", now_iso()))
    conn.commit(); conn.close()


def create_player(username, pw):
    conn = get_conn(); c = conn.cursor()
    try:
        salt = secrets.token_hex(16)
        c.execute("INSERT INTO users(username,pw_hash,salt,role,created_at) VALUES(?,?,?,?,?)",
                  (username, hash_pw(pw, salt), salt, "player", now_iso()))
        uid = c.lastrowid
        c.execute("""INSERT INTO characters(user_id,kind,name,chapter,species,tier,earned_xp,other_xp,
                     attributes,skills,talents,wargear,armour,cur_wounds,cur_shock,cur_wrath,notes,
                     comms_on,comms_changed_at)
                     VALUES(?, 'player', ?,?,?,?,0,0,?,?,?,?,0,0,0,0,?,1,?)""",
                  (uid, username, "", "Adeptus Astartes", 2, json.dumps(default_attributes()),
                   json.dumps(default_skills()), json.dumps([]), "", "", now_iso()))
        conn.commit(); return True, "Servo recrutado."
    except sqlite3.IntegrityError:
        return False, "Essa designação já existe."
    finally:
        conn.close()


def create_npc(name, species, tier):
    conn = get_conn()
    conn.execute("""INSERT INTO characters(user_id,kind,name,chapter,species,tier,earned_xp,other_xp,
                    attributes,skills,talents,wargear,armour,cur_wounds,cur_shock,cur_wrath,notes,
                    comms_on,comms_changed_at)
                    VALUES(NULL,'npc',?,?,?,?,0,0,?,?,?,?,0,0,0,0,?,1,?)""",
                 (name or "NPC", "", species, int(tier), json.dumps(default_attributes()),
                  json.dumps(default_skills()), json.dumps([]), "", "", now_iso()))
    conn.commit(); conn.close()


def verify_user(username, pw):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    if row and hash_pw(pw, row["salt"]) == row["pw_hash"]:
        return {"id": row["id"], "username": row["username"], "role": row["role"]}
    return None


def set_password(uid, newpw):
    conn = get_conn(); salt = secrets.token_hex(16)
    conn.execute("UPDATE users SET pw_hash=?,salt=? WHERE id=?", (hash_pw(newpw, salt), salt, uid))
    conn.commit(); conn.close()


def _decode(row):
    ch = dict(row)
    try:
        ch["attributes"] = json.loads(ch.get("attributes") or "{}")
    except Exception:
        ch["attributes"] = {}
    try:
        ch["skills"] = json.loads(ch.get("skills") or "{}")
    except Exception:
        ch["skills"] = {}
    raw = ch.get("talents") or "[]"; tal = []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            for t in parsed:
                if isinstance(t, dict):
                    tal.append({"name": t.get("name", ""), "cost": int(t.get("cost", 20))})
                else:
                    tal.append({"name": str(t), "cost": 20})
        elif isinstance(parsed, str) and parsed.strip():
            tal = [{"name": ln, "cost": 20} for ln in parsed.splitlines() if ln.strip()]
    except Exception:
        tal = [{"name": ln, "cost": 20} for ln in raw.splitlines() if ln.strip()]
    ch["talents"] = tal
    for a in ATTRS:
        ch["attributes"].setdefault(a, 1)
    for s in SKILLS:
        ch["skills"].setdefault(s, 0)
    for k, dv in {"tier": 2, "earned_xp": 0, "other_xp": 0, "armour": 0, "cur_wounds": 0,
                  "cur_shock": 0, "cur_wrath": 0, "comms_on": 1, "kind": "player",
                  "name": "", "chapter": "", "species": "", "wargear": "", "notes": ""}.items():
        if ch.get(k) is None:
            ch[k] = dv
    return ch


def load_character(cid):
    conn = get_conn(); row = conn.execute("SELECT * FROM characters WHERE id=?", (cid,)).fetchone()
    conn.close(); return _decode(row) if row else None


def char_id_for_user(uid):
    conn = get_conn(); row = conn.execute("SELECT id FROM characters WHERE user_id=?", (uid,)).fetchone()
    conn.close(); return row["id"] if row else None


def list_characters(kind=None):
    conn = get_conn()
    if kind:
        rows = conn.execute("SELECT * FROM characters WHERE kind=? ORDER BY name", (kind,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM characters ORDER BY name").fetchall()
    conn.close(); return [_decode(r) for r in rows]


def save_build(cid, name, chapter, species, tier, attributes, skills, talents, wargear, armour, notes, other_xp):
    conn = get_conn()
    conn.execute("""UPDATE characters SET name=?,chapter=?,species=?,tier=?,attributes=?,skills=?,
                    talents=?,wargear=?,armour=?,notes=?,other_xp=? WHERE id=?""",
                 (name, chapter, species, int(tier), json.dumps(attributes), json.dumps(skills),
                  json.dumps(talents), wargear, int(armour), notes, int(other_xp), cid))
    conn.commit(); conn.close()


def adjust_vital(cid, field, delta):
    if field not in VITAL_FIELDS:
        return
    conn = get_conn()
    row = conn.execute(f"SELECT {field} FROM characters WHERE id=?", (cid,)).fetchone()
    if row is not None:
        conn.execute(f"UPDATE characters SET {field}=? WHERE id=?", (max(0, int(row[0] or 0) + delta), cid))
        conn.commit()
    conn.close()


def set_earned_xp(cid, val):
    conn = get_conn(); conn.execute("UPDATE characters SET earned_xp=? WHERE id=?", (max(0, int(val)), cid))
    conn.commit(); conn.close()


def award_xp(cid, amt):
    conn = get_conn(); conn.execute("UPDATE characters SET earned_xp=MAX(0,earned_xp+?) WHERE id=?", (int(amt), cid))
    conn.commit(); conn.close()


def set_comms(cid, on):
    conn = get_conn()
    conn.execute("UPDATE characters SET comms_on=?, comms_changed_at=? WHERE id=?", (int(on), now_iso(), cid))
    conn.commit(); conn.close()


def set_folder(cid, fid):
    conn = get_conn(); conn.execute("UPDATE characters SET folder_id=? WHERE id=?", (fid if fid else None, cid))
    conn.commit(); conn.close()


def set_portrait(cid, blob):
    conn = get_conn(); conn.execute("UPDATE characters SET portrait=? WHERE id=?", (blob, cid))
    conn.commit(); conn.close()


def delete_character(cid):
    conn = get_conn()
    row = conn.execute("SELECT user_id FROM characters WHERE id=?", (cid,)).fetchone()
    conn.execute("DELETE FROM characters WHERE id=?", (cid,))
    if row and row["user_id"]:
        conn.execute("DELETE FROM users WHERE id=?", (row["user_id"],))
    conn.commit(); conn.close()


def create_folder(name):
    conn = get_conn(); conn.execute("INSERT INTO folders(name) VALUES(?)", (name,)); conn.commit(); conn.close()


def list_folders():
    conn = get_conn(); rows = conn.execute("SELECT * FROM folders ORDER BY name").fetchall(); conn.close(); return rows


def rename_folder(fid, name):
    conn = get_conn(); conn.execute("UPDATE folders SET name=? WHERE id=?", (name, fid)); conn.commit(); conn.close()


def delete_folder(fid):
    conn = get_conn()
    conn.execute("UPDATE characters SET folder_id=NULL WHERE folder_id=?", (fid,))
    conn.execute("DELETE FROM folders WHERE id=?", (fid,)); conn.commit(); conn.close()


def get_campaign():
    conn = get_conn(); row = conn.execute("SELECT * FROM campaign WHERE id=1").fetchone(); conn.close()
    c = dict(row) if row else {}
    c.setdefault("name", "A Cruzada"); c.setdefault("tier", 2); c.setdefault("ruin", 0); c.setdefault("session_no", 1)
    return c


def save_campaign(name, tier, ruin, session_no):
    conn = get_conn()
    conn.execute("UPDATE campaign SET name=?,tier=?,ruin=?,session_no=? WHERE id=1",
                 (name, int(tier), int(ruin), int(session_no)))
    conn.commit(); conn.close()


def adjust_ruin(delta):
    conn = get_conn(); conn.execute("UPDATE campaign SET ruin=MAX(0,ruin+?) WHERE id=1", (int(delta),))
    conn.commit(); conn.close()


def add_log(author, text):
    conn = get_conn()
    conn.execute("INSERT INTO log(ts,author,text) VALUES(?,?,?)", (datetime.now().strftime("%Y-%m-%d %H:%M"), author, text))
    conn.commit(); conn.close()


def get_logs(limit=60):
    conn = get_conn(); rows = conn.execute("SELECT * FROM log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close(); return rows


# ============================================================
#  TEMA
# ============================================================
def inject_theme():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@500;700;900&family=EB+Garamond:ital@0;1&display=swap');
    :root{ --blood:#7a0f12; --blood2:#a4161a; --gold:#c9a227; --gold2:#e8c96a; --bone:#e8e0cf;
           --panel:#171209; --panel2:#20180d; --npc:#b57edc; --green:#3fae5a; --red:#d13a3a; }
    .stApp{ background: radial-gradient(circle at 50% -8%, #221a12 0%, #0c0a09 55%) fixed; color:var(--bone); }
    html,body,[class*="css"],p,label,.stMarkdown{ font-family:'EB Garamond',Georgia,serif; color:var(--bone); }
    h1,h2,h3,h4,h5{ font-family:'Cinzel',serif !important; color:var(--gold) !important;
        letter-spacing:.06em; text-transform:uppercase; text-shadow:0 1px 2px #000; }
    .banner{ text-align:center; font-family:'Cinzel',serif; font-weight:900; font-size:1.7rem;
        color:var(--gold2); letter-spacing:.12em; padding:12px 0 4px; border-bottom:2px solid var(--gold); }
    .banner .sub{ display:block; font-size:.72rem; letter-spacing:.3em; color:var(--bone); opacity:.7;
        text-transform:uppercase; margin-top:3px; }
    .stButton>button{ background:linear-gradient(#241c14,#160f0a); color:var(--gold2);
        border:1px solid var(--gold); border-radius:2px; font-family:'Cinzel',serif; letter-spacing:.04em;
        text-transform:uppercase; font-weight:700; padding:2px 10px; font-size:.78rem; transition:.15s; }
    .stButton>button:hover{ background:linear-gradient(var(--blood),var(--blood2)); color:#fff; border-color:var(--gold2); }
    /* caixas de atributo/perícia compactas */
    .stNumberInput input{ padding:2px 6px !important; font-size:.9rem !important; }
    .stNumberInput{ max-width:150px; }
    input,textarea{ background:#120d08 !important; color:var(--bone) !important; border-color:#4a3a20 !important; }
    [data-testid="stMetric"]{ background:var(--panel); border:1px solid #4a3a20; border-left:4px solid var(--gold);
        border-radius:3px; padding:6px 10px; }
    [data-testid="stMetricValue"]{ color:var(--gold2) !important; font-family:'Cinzel',serif; }
    [data-testid="stMetricLabel"]{ color:var(--bone) !important; text-transform:uppercase; letter-spacing:.04em; }
    section[data-testid="stSidebar"]{ background:#0f0b07; border-right:1px solid var(--gold); }
    hr{ border-color:var(--gold); opacity:.4; }
    .stTabs [data-baseweb="tab"]{ font-family:'Cinzel',serif; text-transform:uppercase; letter-spacing:.05em; }
    .stTabs [aria-selected="true"]{ color:var(--gold2) !important; }
    .npc{ color:var(--npc) !important; }
    .vlive{ color:var(--green); font-weight:700; }
    .vdead{ color:var(--red); font-weight:700; }
    .row{ border:1px solid #3a2e18; border-radius:3px; padding:6px 10px; margin-bottom:6px; background:var(--panel); }
    .fold{ display:inline-block; }
    /* Visão de Batalha */
    .hero{ background:linear-gradient(135deg,#20180d,#100b06); border:1px solid var(--gold);
        border-radius:4px; padding:14px 18px; margin-bottom:10px; }
    .hero .nm{ font-family:'Cinzel',serif; font-size:1.6rem; font-weight:900; color:var(--gold2); letter-spacing:.06em; }
    .hero .meta{ color:var(--bone); opacity:.8; letter-spacing:.08em; text-transform:uppercase; font-size:.8rem; }
    .sectionttl{ font-family:'Cinzel',serif; color:var(--gold); text-transform:uppercase; letter-spacing:.1em;
        border-bottom:1px solid var(--gold); padding-bottom:3px; margin:12px 0 8px; font-size:.95rem; }
    .grid{ display:flex; flex-wrap:wrap; gap:7px; }
    .statcard{ background:var(--panel2); border:1px solid #3a2e18; border-left:3px solid var(--gold);
        border-radius:3px; padding:6px 12px; min-width:96px; }
    .statcard .l{ font-size:.68rem; text-transform:uppercase; letter-spacing:.06em; opacity:.75; }
    .statcard .v{ font-family:'Cinzel',serif; color:var(--gold2); font-size:1.35rem; line-height:1.1; }
    .skhead,.skrow{ display:grid; grid-template-columns:1fr 40px 40px 46px; gap:4px; padding:3px 8px; align-items:center; }
    .skhead{ font-family:'Cinzel',serif; font-size:.66rem; text-transform:uppercase; color:var(--gold);
        border-bottom:1px solid var(--gold); letter-spacing:.05em; }
    .skrow{ border-bottom:1px solid #241c10; }
    .skrow:nth-child(even){ background:rgba(255,255,255,.02); }
    .skrow .n{ letter-spacing:.02em; } .skrow .c{ text-align:center; opacity:.7; }
    .skrow .t{ text-align:center; font-family:'Cinzel',serif; color:var(--gold2); font-weight:700; }
    .tal,.wg{ background:var(--panel2); border:1px solid #3a2e18; border-radius:3px; padding:6px 10px; margin-bottom:5px; }
    .tal .tn{ font-family:'Cinzel',serif; color:var(--gold2); letter-spacing:.03em; }
    .tal .tc{ float:right; opacity:.6; font-size:.75rem; }
    .foot{ text-align:center; color:var(--gold); opacity:.5; font-family:'Cinzel',serif; letter-spacing:.3em;
        font-size:.75rem; margin-top:20px; }
    </style>
    """, unsafe_allow_html=True)


# ============================================================
#  CALLBACKS
# ============================================================
def cb_open(cid):
    st.session_state.editing = cid


def cb_close():
    st.session_state.editing = None


# ============================================================
#  COMPONENTES AO VIVO
# ============================================================
@st.fragment(run_every=REFRESH_S)
def live_vitals(cid):
    ch = load_character(cid)
    if not ch:
        return
    d = derived_traits(ch)
    rank, asc = rank_from_xp(ch["earned_xp"])
    trio = [("cur_wounds", "Ferimentos", d["Max Wounds"]),
            ("cur_shock", "Choque", d["Max Shock"]),
            ("cur_wrath", "Ira", d["Max Wrath"])]
    cols = st.columns(3)
    for i, (field, label, mx) in enumerate(trio):
        with cols[i]:
            st.metric(label, f"{ch[field]} / {mx}")
            b = st.columns(4)
            b[0].button("−5", key=f"lv{field}{cid}a", on_click=adjust_vital, args=(cid, field, -5))
            b[1].button("−1", key=f"lv{field}{cid}b", on_click=adjust_vital, args=(cid, field, -1))
            b[2].button("+1", key=f"lv{field}{cid}c", on_click=adjust_vital, args=(cid, field, +1))
            b[3].button("+5", key=f"lv{field}{cid}d", on_click=adjust_vital, args=(cid, field, +5))
    if asc:
        st.warning("100+ XP ganho — este servo pode ascender de Tier.")


@st.fragment(run_every=REFRESH_S)
def vox_live():
    chars = list_characters()
    shown = []
    for ch in chars:
        if ch["comms_on"]:
            shown.append((ch["name"] or "?", ch["kind"], True))
        elif secs_since(ch["comms_changed_at"]) < COMMS_FADE_S:
            shown.append((ch["name"] or "?", ch["kind"], False))
    if not shown:
        st.markdown("<div class='wg' style='opacity:.6'>Sem sinal na rede.</div>", unsafe_allow_html=True)
        return
    html = ""
    for name, kind, on in shown:
        ncls = "npc" if kind == "npc" else ""
        state = "<span class='vlive'>✠ ATIVO</span>" if on else "<span class='vdead'>✠ CORTADO</span>"
        html += f"<div class='wg'><span class='{ncls}'>{name}</span> <span style='float:right'>{state}</span></div>"
    st.markdown(html, unsafe_allow_html=True)


# ============================================================
#  VISÃO DE BATALHA (temática, do jogador)
# ============================================================
def battle_view(cid):
    ch = load_character(cid)
    if not ch:
        st.error("Ficha não encontrada.")
        return
    d = derived_traits(ch)
    rank, _ = rank_from_xp(ch["earned_xp"])
    ncls = "npc" if ch["kind"] == "npc" else ""
    st.markdown(f"<div class='hero'><div class='nm {ncls}'>{ch['name'] or 'Servo'}</div>"
                f"<div class='meta'>{ch['chapter'] or ''} &nbsp;·&nbsp; {ch['species']} &nbsp;·&nbsp; "
                f"Tier {ch['tier']} &nbsp;·&nbsp; Rank {rank}</div></div>", unsafe_allow_html=True)

    st.markdown("<div class='sectionttl'>Vitalidade</div>", unsafe_allow_html=True)
    live_vitals(cid)

    left, right = st.columns([1.5, 1])
    with left:
        st.markdown("<div class='sectionttl'>Traços Derivados</div>", unsafe_allow_html=True)
        order = [("Defence", "Defesa"), ("Resilience", "Resiliência"), ("Soak", "Absorção"),
                 ("Determination", "Determinação"), ("Resolve", "Resolução"), ("Conviction", "Convicção"),
                 ("Passive Awareness", "Percepção"), ("Influence", "Influência"), ("Speed", "Deslocamento")]
        cards = "".join(f"<div class='statcard'><div class='l'>{pt}</div><div class='v'>{d[en]}</div></div>"
                        for en, pt in order)
        st.markdown(f"<div class='grid'>{cards}</div>", unsafe_allow_html=True)

        st.markdown("<div class='sectionttl'>Perícias &nbsp;<small style='opacity:.6;letter-spacing:0'>Total = valor + atributo</small></div>", unsafe_allow_html=True)
        rows = "<div class='skhead'><span>Perícia</span><span>Val</span><span>Atr</span><span>Total</span></div>"
        for s in SKILLS:
            r = ch["skills"][s]; av = ch["attributes"][SKILLS[s]]
            rows += (f"<div class='skrow'><span class='n'>{s}</span><span class='c'>{r}</span>"
                     f"<span class='c'>+{av}</span><span class='t'>{r+av}</span></div>")
        st.markdown(rows, unsafe_allow_html=True)

    with right:
        st.markdown("<div class='sectionttl'>Talentos</div>", unsafe_allow_html=True)
        if ch["talents"]:
            for t in ch["talents"]:
                cost = f"<span class='tc'>{t['cost']} XP</span>" if t.get("cost") else ""
                st.markdown(f"<div class='tal'><span class='tn'>{t['name']}</span>{cost}</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='tal' style='opacity:.6'>Nenhum talento.</div>", unsafe_allow_html=True)

        st.markdown("<div class='sectionttl'>Wargear</div>", unsafe_allow_html=True)
        wl = [w for w in (ch["wargear"] or "").splitlines() if w.strip()]
        if wl:
            for w in wl:
                st.markdown(f"<div class='wg'>{w}</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='wg' style='opacity:.6'>Sem wargear.</div>", unsafe_allow_html=True)

        st.markdown("<div class='sectionttl'>Rede Vox</div>", unsafe_allow_html=True)
        vox_live()


# ============================================================
#  EDIÇÃO DA FICHA (tudo editável)
# ============================================================
def _k(cid, sec, f):
    return f"f_{cid}_{sec}_{f}"


def edit_view(cid, gm_mode=False):
    ch = load_character(cid)
    if not ch:
        st.error("Ficha não encontrada.")
        return
    camp = get_campaign()
    species_list = NPC_SPECIES if ch["kind"] == "npc" else PLAYER_SPECIES

    for a in ATTRS:
        st.session_state.setdefault(_k(cid, "a", a), int(ch["attributes"][a]))
    for s in SKILLS:
        st.session_state.setdefault(_k(cid, "s", s), int(ch["skills"][s]))
    st.session_state.setdefault(_k(cid, "t", "name"), ch["name"])
    st.session_state.setdefault(_k(cid, "t", "chapter"), ch["chapter"] or "")
    st.session_state.setdefault(_k(cid, "t", "wargear"), ch["wargear"] or "")
    st.session_state.setdefault(_k(cid, "t", "notes"), ch["notes"] or "")
    st.session_state.setdefault(_k(cid, "n", "tier"), int(ch["tier"]))
    st.session_state.setdefault(_k(cid, "n", "armour"), int(ch["armour"]))
    st.session_state.setdefault(_k(cid, "n", "other"), int(ch["other_xp"]))
    spk = _k(cid, "sel", "sp")
    if spk not in st.session_state:
        st.session_state[spk] = ch["species"] if ch["species"] in species_list else species_list[-1]

    c = st.columns([2, 2, 2])
    c[0].text_input("Nome", key=_k(cid, "t", "name"))
    c[1].text_input("Capítulo / Facção", key=_k(cid, "t", "chapter"))
    c[2].selectbox("Espécie", species_list, key=spk)
    c = st.columns([1, 1, 1, 2])
    c[0].number_input("Tier", 1, 5, key=_k(cid, "n", "tier"))
    c[1].number_input("Armadura", 0, 30, key=_k(cid, "n", "armour"))
    c[2].number_input("Outro XP", 0, 100000, key=_k(cid, "n", "other"))
    if gm_mode:
        exp = c[3].number_input("XP Ganho", 0, 100000, int(ch["earned_xp"]), key=f"earn_{cid}")
        if exp != ch["earned_xp"]:
            set_earned_xp(cid, exp)

    st.markdown("#### Atributos")
    acol = st.columns(4)
    for i, a in enumerate(ATTRS):
        acol[i % 4].number_input(a, 1, 12, key=_k(cid, "a", a))
    cur_attr = {a: int(st.session_state[_k(cid, "a", a)]) for a in ATTRS}
    cur_skill = {s: int(st.session_state[_k(cid, "s", s)]) for s in SKILLS}

    st.markdown("#### Perícias")
    scol = st.columns(3)
    for i, s in enumerate(SKILLS):
        with scol[i % 3]:
            cc = st.columns([3, 1])
            cc[0].number_input(s, 0, 8, key=_k(cid, "s", s))
            pool = cur_skill[s] + cur_attr[SKILLS[s]]
            cc[1].markdown(f"<div style='padding-top:30px;color:#e8c96a;font-family:Cinzel'>{pool}</div>",
                           unsafe_allow_html=True)

    st.markdown("#### Talentos")
    tdf = ch["talents"] if ch["talents"] else [{"name": "", "cost": 20}]
    edited = st.data_editor(tdf, num_rows="dynamic", key=f"tal_{cid}", use_container_width=True,
                            column_config={"name": st.column_config.TextColumn("Talento"),
                                           "cost": st.column_config.NumberColumn("XP", min_value=0, step=5)})
    talents = [{"name": r.get("name", ""), "cost": int(r.get("cost") or 0)}
               for r in edited if (r.get("name") or "").strip()]

    wc = st.columns(2)
    wc[0].text_area("Wargear", key=_k(cid, "t", "wargear"), height=110)
    wc[1].text_area("Anotações", key=_k(cid, "t", "notes"), height=110)

    save_build(cid, st.session_state[_k(cid, "t", "name")], st.session_state[_k(cid, "t", "chapter")],
               st.session_state[spk], st.session_state[_k(cid, "n", "tier")], cur_attr, cur_skill,
               talents, st.session_state[_k(cid, "t", "wargear")], st.session_state[_k(cid, "n", "armour")],
               st.session_state[_k(cid, "t", "notes")], st.session_state[_k(cid, "n", "other")])

    cur = dict(ch); cur.update({"attributes": cur_attr, "skills": cur_skill, "species": st.session_state[spk],
                                "tier": int(st.session_state[_k(cid, "n", "tier")]), "talents": talents,
                                "other_xp": int(st.session_state[_k(cid, "n", "other")])})
    spent = xp_spent(cur); start = starting_xp(camp["tier"]); avail = start + int(ch["earned_xp"]) - spent
    st.divider()
    x = st.columns(4)
    x[0].metric("XP Inicial", start); x[1].metric("XP Ganho", ch["earned_xp"])
    x[2].metric("XP Gasto", spent); x[3].metric("XP Disponível", avail)
    if avail < 0:
        st.error(f"Acima do orçamento por {-avail} XP.")

    with st.expander("Retrato"):
        if ch.get("portrait"):
            st.image(ch["portrait"], width=170)
        up = st.file_uploader("Enviar", type=["png", "jpg", "jpeg"], key=f"port_{cid}")
        if up is not None and st.button("Salvar retrato", key=f"pb_{cid}"):
            set_portrait(cid, up.getvalue()); st.rerun()


# ============================================================
#  PÁGINAS
# ============================================================
def login_page():
    st.markdown("<div class='banner'>✠ COGITADOR IMPERIAL ✠"
                "<span class='sub'>Adeptus Administratum · Registro de Campanha</span></div>", unsafe_allow_html=True)
    col = st.columns([1, 1.3, 1])[1]
    with col:
        st.markdown(" ")
        with st.form("login"):
            u = st.text_input("Designação")
            p = st.text_input("Código de Acesso", type="password")
            ok = st.form_submit_button("Autenticar")
        if ok:
            user = verify_user(u.strip(), p)
            if user:
                st.session_state.user = user; st.rerun()
            else:
                st.error("Acesso negado.")
        
    st.markdown("<div class='foot'>THE EMPEROR PROTECTS</div>", unsafe_allow_html=True)


def folder_label(fid, folders):
    for f in folders:
        if f["id"] == fid:
            return f["name"]
    return "Sem pasta"


def char_row(ch, folders):
    rank, _ = rank_from_xp(ch["earned_xp"]); d = derived_traits(ch)
    ncls = "npc" if ch["kind"] == "npc" else ""
    vs = ("<span class='vlive'>ATIVO</span>" if ch["comms_on"]
          else ("<span class='vdead'>CORTADO</span>" if secs_since(ch["comms_changed_at"]) < COMMS_FADE_S else ""))
    c = st.columns([3.2, 1.6, 0.9, 1, 0.6])
    c[0].markdown(f"<b class='{ncls}'>{ch['name'] or 'sem nome'}</b><br>"
                  f"<small style='opacity:.65'>{ch['species']} · T{ch['tier']} · Rank {rank}</small> {vs}",
                  unsafe_allow_html=True)
    c[1].markdown(f"<small>Choque {ch['cur_shock']}/{d['Max Shock']}<br>Ira {ch['cur_wrath']}/{d['Max Wrath']}</small>",
                  unsafe_allow_html=True)
    c[2].button("Abrir", key=f"op_{ch['id']}", on_click=cb_open, args=(ch["id"],))
    if ch["comms_on"]:
        c[3].button("Cortar", key=f"vr_{ch['id']}", on_click=set_comms, args=(ch["id"], 0))
    else:
        c[3].button("Ativar", key=f"vr_{ch['id']}", on_click=set_comms, args=(ch["id"], 1))
    c[4].button("X", key=f"dl_{ch['id']}", on_click=delete_character, args=(ch["id"],))


def vox_toggle_list(chars):
    for ch in chars:
        ncls = "npc" if ch["kind"] == "npc" else ""
        c = st.columns([3, 1.4, 1.2])
        c[0].markdown(f"<span class='{ncls}'>{ch['name'] or 'sem nome'}</span>", unsafe_allow_html=True)
        if ch["comms_on"]:
            c[1].markdown("<span class='vlive'>✠ ATIVO</span>", unsafe_allow_html=True)
            c[2].button("Cortar", key=f"vt_{ch['id']}", on_click=set_comms, args=(ch["id"], 0))
        else:
            c[1].markdown("<span class='vdead'>✠ CORTADO</span>", unsafe_allow_html=True)
            c[2].button("Ativar", key=f"vt_{ch['id']}", on_click=set_comms, args=(ch["id"], 1))


def gm_view():
    camp = get_campaign()
    st.markdown("<div class='banner'>✠ SANCTUM DO MAGISTER ✠<span class='sub'>Comando da Campanha</span></div>",
                unsafe_allow_html=True)

    if st.session_state.get("editing"):
        cid = st.session_state.editing
        st.button("Voltar", on_click=cb_close)
        t = st.tabs(["Visão de Batalha", "Edição"])
        with t[0]:
            battle_view(cid)
        with t[1]:
            edit_view(cid, gm_mode=True)
        return

    tabs = st.tabs(["Servos", "Vox", "Experiência", "Campanha", "Manutenção"])

    # ---- Servos ----
    with tabs[0]:
        folders = list_folders()
        st.markdown("#### Pastas")
        fc = st.columns([2, 1])
        newf = fc[0].text_input("Nova pasta", key="newfolder", label_visibility="collapsed",
                                placeholder="Nova pasta")
        if fc[1].button("Criar"):
            if newf.strip():
                create_folder(newf.strip()); st.rerun()
        if folders:
            fcols = st.columns(min(len(folders), 5))
            for i, f in enumerate(folders):
                with fcols[i % 5]:
                    nm = st.text_input("f", f["name"], key=f"fn_{f['id']}", label_visibility="collapsed")
                    if nm != f["name"]:
                        rename_folder(f["id"], nm)
                    st.button("Excluir", key=f"fd_{f['id']}", on_click=delete_folder, args=(f["id"],))
        st.divider()

        cre = st.columns(2)
        with cre[0]:
            st.markdown("#### Recrutar Jogador")
            with st.form("newp"):
                nu = st.text_input("Usuário"); npw = st.text_input("Senha", type="password")
                if st.form_submit_button("Recrutar"):
                    if nu.strip() and npw:
                        ok, msg = create_player(nu.strip(), npw)
                        (st.success if ok else st.error)(msg)
                        if ok:
                            st.rerun()
        with cre[1]:
            st.markdown("#### Criar NPC")
            with st.form("newn"):
                nn = st.text_input("Nome"); nsp = st.selectbox("Raça / Tipo", NPC_SPECIES)
                nt = st.number_input("Tier", 1, 5, 2)
                if st.form_submit_button("Criar NPC"):
                    create_npc(nn.strip(), nsp, nt); st.rerun()
        st.divider()

        view = st.radio("Organização", ["Por Tipo", "Por Pastas"], horizontal=True)
        if view == "Por Tipo":
            colp, coln = st.columns(2)
            with colp:
                st.markdown("#### Jogadores")
                for ch in list_characters("player"):
                    char_row(ch, folders)
            with coln:
                st.markdown("#### NPCs")
                for ch in list_characters("npc"):
                    char_row(ch, folders)
        else:
            allc = list_characters(); groups = {None: []}
            for f in folders:
                groups[f["id"]] = []
            for ch in allc:
                groups.setdefault(ch["folder_id"], []).append(ch)
            for fid, items in groups.items():
                st.markdown(f"#### {folder_label(fid, folders)}")
                if not items:
                    st.caption("vazia")
                for ch in items:
                    a = st.columns([5, 1.4])
                    with a[0]:
                        char_row(ch, folders)
                    opts = [None] + [f["id"] for f in folders]
                    idx = opts.index(ch["folder_id"]) if ch["folder_id"] in opts else 0
                    a[1].selectbox("Pasta", opts, index=idx, key=f"mv_{ch['id']}",
                                   format_func=lambda x: folder_label(x, folders), label_visibility="collapsed",
                                   on_change=lambda cid=ch["id"]: set_folder(cid, st.session_state[f"mv_{cid}"]))

    # ---- Vox ----
    with tabs[1]:
        st.markdown("#### Rede Vox — controle de comunicação")
        alvo = st.radio("Alvo", ["Jogadores", "NPCs"], horizontal=True)
        if alvo == "Jogadores":
            vox_toggle_list(list_characters("player"))
        else:
            modo = st.radio("Organizar", ["Individual", "Por pasta"], horizontal=True)
            npcs = list_characters("npc"); folders = list_folders()
            if modo == "Individual":
                vox_toggle_list(npcs)
            else:
                groups = {None: []}
                for f in folders:
                    groups[f["id"]] = []
                for ch in npcs:
                    groups.setdefault(ch["folder_id"], []).append(ch)
                for fid, items in groups.items():
                    if items:
                        st.markdown(f"**{folder_label(fid, folders)}**")
                        vox_toggle_list(items)
        st.divider()
        st.markdown("#### Sinais ativos")
        vox_live()

    # ---- Experiência ----
    with tabs[2]:
        st.markdown("#### Conceder Experiência")
        st.caption("Rank: 40 XP vira 2, 80 vira 3. A partir de 100, pode ascender de Tier.")
        chars = list_characters("player")
        if chars:
            names = {c["name"] or f"#{c['id']}": c["id"] for c in chars}
            with st.form("xpf"):
                cc = st.columns([2, 1, 2])
                who = cc[0].selectbox("Servo", ["Mesa inteira"] + list(names.keys()))
                amt = cc[1].number_input("XP", -200, 500, 10); why = cc[2].text_input("Motivo")
                if st.form_submit_button("Conceder"):
                    tgt = list(names.values()) if who == "Mesa inteira" else [names[who]]
                    for cid in tgt:
                        award_xp(cid, amt)
                    add_log("Magister", f"{amt:+} XP para {who}. {why}".strip()); st.rerun()
            st.divider()
            for c in chars:
                rk, asc = rank_from_xp(c["earned_xp"])
                st.write(f"**{c['name']}** — {c['earned_xp']} XP · Rank {rk}" + ("  · pode ascender" if asc else ""))
        else:
            st.info("Nenhum jogador.")

    # ---- Campanha ----
    with tabs[3]:
        st.markdown("#### Configuração da Campanha")
        with st.form("campf"):
            cc = st.columns([3, 1, 1])
            cname = cc[0].text_input("Nome da campanha", camp["name"])
            ctier = cc[1].number_input("Tier da campanha", 1, 5, int(camp["tier"]))
            sess = cc[2].number_input("Sessão", 1, 999, int(camp["session_no"]))
            if st.form_submit_button("Salvar"):
                save_campaign(cname, ctier, camp["ruin"], sess); st.rerun()
        st.caption(f"XP inicial dos personagens: {starting_xp(camp['tier'])} (Tier {camp['tier']} x 100).")
        st.divider()
        st.markdown("#### Pontos de Ruína (Ruin)")
        rc = st.columns([1, 1, 1, 3])
        rc[0].metric("Ruína", camp["ruin"])
        rc[1].button("−1", key="ruinm", on_click=adjust_ruin, args=(-1,))
        rc[2].button("+1", key="ruinp", on_click=adjust_ruin, args=(+1,))
        st.divider()
        st.markdown("#### Registro de sessão")
        with st.form("voxlog"):
            msg = st.text_area("Nova entrada")
            if st.form_submit_button("Registrar"):
                if msg.strip():
                    add_log("Magister", msg.strip()); st.rerun()
        for lg in get_logs():
            st.markdown(f"<div class='row'><b>{lg['ts']}</b> — {lg['text']}</div>", unsafe_allow_html=True)

    # ---- Manutenção ----
    with tabs[4]:
        st.markdown("#### Manutenção dos Arquivos")
        st.caption("O backup .db contém tudo: jogadores, NPCs, pastas, XP, vox, retratos. "
                   "Em hospedagem grátis o disco reinicia; baixe periodicamente e reenvie depois.")
        if os.path.exists(DB_PATH):
            size = os.path.getsize(DB_PATH) / (1024 * 1024)
            st.write(f"Tamanho do banco: {size:.2f} MB (SQLite aguenta ~281 TB; cresce sozinho).")
            with open(DB_PATH, "rb") as f:
                st.download_button("Baixar backup (cogitador.db)", f.read(),
                                   file_name="cogitador.db", mime="application/octet-stream")
        up = st.file_uploader("Restaurar backup", type=["db"])
        if up is not None and st.button("Sobrescrever tudo"):
            with open(DB_PATH, "wb") as f:
                f.write(up.getbuffer())
            st.rerun()


def player_view():
    camp = get_campaign()
    st.markdown(f"<div class='banner'>✠ FICHA DE SERVIÇO ✠"
                f"<span class='sub'>{camp['name']} · Sessão {camp['session_no']}</span></div>", unsafe_allow_html=True)
    cid = char_id_for_user(st.session_state.user["id"])
    if not cid:
        st.error("Nenhuma ficha vinculada. Contate o Magister.")
        return
    t = st.tabs(["Visão de Batalha", "Edição da Ficha"])
    with t[0]:
        battle_view(cid)
    with t[1]:
        edit_view(cid, gm_mode=False)


# ============================================================
#  MAIN
# ============================================================
def main():
    st.set_page_config(page_title="Cogitador Imperial", page_icon="✠", layout="wide")
    inject_theme(); init_db()
    st.session_state.setdefault("user", None)
    st.session_state.setdefault("editing", None)

    if st.session_state.user is None:
        login_page(); return

    with st.sidebar:
        camp = get_campaign(); role = st.session_state.user["role"]
        st.markdown(f"### ✠ {camp['name']}")
        st.write(f"Servo: {st.session_state.user['username']}")
        st.write("Função: " + ("Magister" if role == "gm" else "Irmão de Batalha"))
        if role == "gm":
            st.metric("Ruína (Ruin)", camp["ruin"])
        st.divider()
        if st.button("Encerrar Sessão"):
            st.session_state.user = None; st.session_state.editing = None; st.rerun()
        with st.expander("Alterar senha"):
            with st.form("chpw"):
                a = st.text_input("Nova senha", type="password"); b = st.text_input("Confirmar", type="password")
                if st.form_submit_button("Alterar"):
                    if a and a == b:
                        set_password(st.session_state.user["id"], a); st.success("Senha atualizada.")
                    else:
                        st.error("As senhas não conferem.")

    if st.session_state.user["role"] == "gm":
        gm_view()
    else:
        player_view()
    st.markdown("<div class='foot'>✠ THE EMPEROR PROTECTS ✠</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()