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
REFRESH_S = 3.0          # polling dos painéis ao vivo
COMMS_FADE_S = 60        # segundos até o nome sumir após o corte do vox

# ============================================================
#  DADOS DE WRATH & GLORY
# ============================================================
ATTRS = ["Strength", "Toughness", "Agility", "Initiative", "Willpower", "Intellect", "Fellowship"]
ATTR_ABBR = {"Strength": "S", "Toughness": "T", "Agility": "A", "Initiative": "I",
             "Willpower": "Wil", "Intellect": "Int", "Fellowship": "Fel"}

SKILLS = {  # perícia -> atributo regente (livro / Forge)
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
               "Daemon de Slaanesh", "Cultista do Caos", "Fera / Besta", "Servitor", "Outro"]

# custos de XP (livro p.24-25) — custo TOTAL a partir de 1 (atributo) / 0 (perícia)
ATTR_COST = {1: 0, 2: 4, 3: 10, 4: 20, 5: 35, 6: 55, 7: 80, 8: 110, 9: 145, 10: 185, 11: 230, 12: 280}
SKILL_COST = {0: 0, 1: 2, 2: 6, 3: 12, 4: 20, 5: 30, 6: 42, 7: 56, 8: 72}
SPECIES_COST = {"Adeptus Astartes": 160, "Primaris Astartes": 198}  # demais: 0 (some via "outro XP")

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
    tier = int(ch.get("tier", 1))
    armour = int(ch.get("armour", 0))
    sp = ch.get("species", "")
    T = a.get("Toughness", 1); I = a.get("Initiative", 1); Wil = a.get("Willpower", 1)
    Intl = a.get("Intellect", 1); Fel = a.get("Fellowship", 1)
    return {
        "Defence": I - 1,
        "Resilience": T + 1 + armour,
        "Soak": T,
        "Max Wounds": T + 2 * tier + (3 if sp == "Primaris Astartes" else 0),
        "Max Shock": Wil + tier,
        "Max Wrath": tier,
        "Determination": T,
        "Resolve": max(0, Wil - 1) + (1 if is_loyal_astartes(sp) else 0),
        "Conviction": Wil,
        "Passive Awareness": math.ceil((Intl + sk.get("Awareness", 0)) / 2),
        "Influence": max(0, Fel - 1),
        "Speed": species_speed(sp),
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


def starting_xp(campaign_tier):
    return int(campaign_tier) * 100


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
#  BANCO DE DADOS
# ============================================================
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def hash_pw(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100_000).hex()


def init_db():
    conn = get_conn(); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
        pw_hash TEXT NOT NULL, salt TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'player',
        created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS folders(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS characters(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, kind TEXT DEFAULT 'player',
        name TEXT, chapter TEXT, species TEXT, tier INTEGER DEFAULT 2,
        earned_xp INTEGER DEFAULT 0, other_xp INTEGER DEFAULT 0,
        attributes TEXT, skills TEXT, talents TEXT, wargear TEXT, armour INTEGER DEFAULT 0,
        cur_wounds INTEGER DEFAULT 0, cur_shock INTEGER DEFAULT 0, cur_wrath INTEGER DEFAULT 0,
        notes TEXT, folder_id INTEGER, portrait BLOB,
        comms_on INTEGER DEFAULT 1, comms_changed_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS campaign(
        id INTEGER PRIMARY KEY CHECK (id=1), name TEXT, tier INTEGER DEFAULT 2,
        ruin INTEGER DEFAULT 0, session_no INTEGER DEFAULT 1)""")
    c.execute("""CREATE TABLE IF NOT EXISTS log(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, author TEXT, text TEXT)""")
    conn.commit()
    if c.execute("SELECT COUNT(*) FROM campaign").fetchone()[0] == 0:
        c.execute("INSERT INTO campaign(id,name,tier,ruin,session_no) VALUES(1,?,2,0,1)",
                  ("A Cruzada de Gilead",))
    if c.execute("SELECT COUNT(*) FROM users WHERE role='gm'").fetchone()[0] == 0:
        salt = secrets.token_hex(16)
        c.execute("INSERT INTO users(username,pw_hash,salt,role,created_at) VALUES(?,?,?,?,?)",
                  ("magister", hash_pw("AveImperator1", salt), salt, "gm", now_iso()))
    conn.commit(); conn.close()


# ---------- usuários ----------
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
                  (uid, username, "", "Adeptus Astartes", 2,
                   json.dumps(default_attributes()), json.dumps(default_skills()),
                   json.dumps([]), "", "", now_iso()))
        conn.commit(); return True, "Servo recrutado."
    except sqlite3.IntegrityError:
        return False, "Essa designação já existe."
    finally:
        conn.close()


def create_npc(name, species, tier):
    conn = get_conn(); c = conn.cursor()
    c.execute("""INSERT INTO characters(user_id,kind,name,chapter,species,tier,earned_xp,other_xp,
                 attributes,skills,talents,wargear,armour,cur_wounds,cur_shock,cur_wrath,notes,
                 comms_on,comms_changed_at)
                 VALUES(NULL,'npc',?,?,?,?,0,0,?,?,?,?,0,0,0,0,?,1,?)""",
              (name or "NPC", "", species, int(tier),
               json.dumps(default_attributes()), json.dumps(default_skills()),
               json.dumps([]), "", "", now_iso()))
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


# ---------- personagens ----------
def _decode(row):
    ch = dict(row)
    try:
        ch["attributes"] = json.loads(ch["attributes"] or "{}")
    except Exception:
        ch["attributes"] = {}
    try:
        ch["skills"] = json.loads(ch["skills"] or "{}")
    except Exception:
        ch["skills"] = {}
    # talentos: normaliza para lista de {name, cost}
    raw = ch.get("talents") or "[]"
    tal = []
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
    return ch


def load_character(cid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM characters WHERE id=?", (cid,)).fetchone()
    conn.close()
    return _decode(row) if row else None


def char_id_for_user(uid):
    conn = get_conn()
    row = conn.execute("SELECT id FROM characters WHERE user_id=?", (uid,)).fetchone()
    conn.close()
    return row["id"] if row else None


def list_characters(kind=None):
    conn = get_conn()
    if kind:
        rows = conn.execute("SELECT * FROM characters WHERE kind=? ORDER BY name", (kind,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM characters ORDER BY name").fetchall()
    conn.close()
    return [_decode(r) for r in rows]


def save_build(cid, name, chapter, species, tier, attributes, skills, talents,
               wargear, armour, notes, other_xp):
    """Salva só o 'build' — NÃO toca em vitais nem em earned_xp (evita sobrescrever)."""
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
        v = max(0, int(row[0] or 0) + delta)
        conn.execute(f"UPDATE characters SET {field}=? WHERE id=?", (v, cid))
        conn.commit()
    conn.close()


def set_earned_xp(cid, val):
    conn = get_conn()
    conn.execute("UPDATE characters SET earned_xp=? WHERE id=?", (max(0, int(val)), cid))
    conn.commit(); conn.close()


def award_xp(cid, amt):
    conn = get_conn()
    conn.execute("UPDATE characters SET earned_xp=MAX(0,earned_xp+?) WHERE id=?", (int(amt), cid))
    conn.commit(); conn.close()


def set_comms(cid, on):
    conn = get_conn()
    conn.execute("UPDATE characters SET comms_on=?, comms_changed_at=? WHERE id=?",
                 (int(on), now_iso(), cid))
    conn.commit(); conn.close()


def set_folder(cid, fid):
    conn = get_conn()
    conn.execute("UPDATE characters SET folder_id=? WHERE id=?",
                 (fid if fid else None, cid))
    conn.commit(); conn.close()


def set_portrait(cid, blob):
    conn = get_conn()
    conn.execute("UPDATE characters SET portrait=? WHERE id=?", (blob, cid))
    conn.commit(); conn.close()


def delete_character(cid):
    conn = get_conn()
    row = conn.execute("SELECT user_id FROM characters WHERE id=?", (cid,)).fetchone()
    conn.execute("DELETE FROM characters WHERE id=?", (cid,))
    if row and row["user_id"]:
        conn.execute("DELETE FROM users WHERE id=?", (row["user_id"],))
    conn.commit(); conn.close()


# ---------- pastas ----------
def create_folder(name):
    conn = get_conn(); conn.execute("INSERT INTO folders(name) VALUES(?)", (name,))
    conn.commit(); conn.close()


def list_folders():
    conn = get_conn(); rows = conn.execute("SELECT * FROM folders ORDER BY name").fetchall()
    conn.close(); return rows


def rename_folder(fid, name):
    conn = get_conn(); conn.execute("UPDATE folders SET name=? WHERE id=?", (name, fid))
    conn.commit(); conn.close()


def delete_folder(fid):
    conn = get_conn()
    conn.execute("UPDATE characters SET folder_id=NULL WHERE folder_id=?", (fid,))
    conn.execute("DELETE FROM folders WHERE id=?", (fid,))
    conn.commit(); conn.close()


# ---------- campanha / log ----------
def get_campaign():
    conn = get_conn(); row = conn.execute("SELECT * FROM campaign WHERE id=1").fetchone()
    conn.close(); return dict(row) if row else {"name": "", "tier": 2, "ruin": 0, "session_no": 1}


def save_campaign(name, tier, ruin, session_no):
    conn = get_conn()
    conn.execute("UPDATE campaign SET name=?,tier=?,ruin=?,session_no=? WHERE id=1",
                 (name, int(tier), int(ruin), int(session_no)))
    conn.commit(); conn.close()


def adjust_ruin(delta):
    conn = get_conn()
    conn.execute("UPDATE campaign SET ruin=MAX(0,ruin+?) WHERE id=1", (int(delta),))
    conn.commit(); conn.close()


def add_log(author, text):
    conn = get_conn()
    conn.execute("INSERT INTO log(ts,author,text) VALUES(?,?,?)",
                 (datetime.now().strftime("%Y-%m-%d %H:%M"), author, text))
    conn.commit(); conn.close()


def get_logs(limit=60):
    conn = get_conn(); rows = conn.execute("SELECT * FROM log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close(); return rows


# ============================================================
#  TEMA VISUAL
# ============================================================
def inject_theme():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@500;700;900&family=EB+Garamond:ital@0;1&display=swap');
    :root{ --blood:#7a0f12; --blood2:#a4161a; --gold:#c9a227; --gold2:#e8c96a;
           --bone:#e8e0cf; --panel:#1a1510; --green:#3fae5a; --red:#d13a3a; }
    .stApp{ background: radial-gradient(circle at 50% -8%, #221a12 0%, #0c0a09 55%) fixed; color:var(--bone); }
    html,body,[class*="css"],p,label,.stMarkdown{ font-family:'EB Garamond',Georgia,serif; color:var(--bone); }
    h1,h2,h3,h4,h5{ font-family:'Cinzel',serif !important; color:var(--gold) !important;
        letter-spacing:.07em; text-transform:uppercase; text-shadow:0 1px 2px #000; }
    .banner{ text-align:center; font-family:'Cinzel',serif; font-weight:900; font-size:2rem;
        color:var(--gold2); letter-spacing:.14em; padding:16px 0 6px;
        border-bottom:2px solid var(--gold); text-shadow:0 2px 6px #000; }
    .banner .sub{ display:block; font-size:.8rem; letter-spacing:.32em; color:var(--bone);
        opacity:.72; text-transform:uppercase; margin-top:4px; }
    .stButton>button{ background:linear-gradient(#241c14,#160f0a); color:var(--gold2);
        border:1px solid var(--gold); border-radius:2px; font-family:'Cinzel',serif;
        letter-spacing:.05em; text-transform:uppercase; font-weight:700; transition:.15s; }
    .stButton>button:hover{ background:linear-gradient(var(--blood),var(--blood2)); color:#fff; border-color:var(--gold2); }
    input,textarea,.stTextInput input,.stNumberInput input{ background:#120d08 !important;
        color:var(--bone) !important; border-color:#4a3a20 !important; }
    [data-testid="stMetric"]{ background:var(--panel); border:1px solid #4a3a20;
        border-left:4px solid var(--gold); border-radius:3px; padding:6px 10px; }
    [data-testid="stMetricValue"]{ color:var(--gold2) !important; font-family:'Cinzel',serif; }
    [data-testid="stMetricLabel"]{ color:var(--bone) !important; text-transform:uppercase; letter-spacing:.04em; }
    section[data-testid="stSidebar"]{ background:#0f0b07; border-right:1px solid var(--gold); }
    hr{ border-color:var(--gold); opacity:.4; }
    .panel{ background:var(--panel); border:1px solid #4a3a20; border-radius:3px; padding:12px 16px; margin-bottom:8px; }
    .vox{ font-family:'Cinzel',serif; letter-spacing:.06em; font-weight:700; padding:4px 0; }
    .vox-on{ color:var(--green); text-shadow:0 0 6px rgba(63,174,90,.5); }
    .vox-off{ color:var(--red); text-shadow:0 0 6px rgba(209,58,58,.5); animation:flick 1.1s infinite; }
    @keyframes flick{ 50%{opacity:.45;} }
    .foot{ text-align:center; color:var(--gold); opacity:.55; font-family:'Cinzel',serif;
        letter-spacing:.3em; font-size:.78rem; margin-top:22px; }
    </style>
    """, unsafe_allow_html=True)


# ============================================================
#  COMPONENTES AO VIVO
# ============================================================
@st.fragment(run_every=REFRESH_S)
def live_vitals(cid, allow_edit):
    ch = load_character(cid)
    if not ch:
        return
    d = derived_traits(ch)
    rank, asc = rank_from_xp(ch["earned_xp"])
    st.markdown(f"### ⚔ {ch['name'] or 'Servo'} &nbsp; <small style='color:#c9a227'>"
                f"Tier {ch['tier']} · Rank {rank}</small>", unsafe_allow_html=True)
    trio = [("cur_wounds", "FERIMENTOS", d["Max Wounds"], "☠"),
            ("cur_shock", "CHOQUE", d["Max Shock"], "✷"),
            ("cur_wrath", "IRA (WRATH)", d["Max Wrath"], "🔥")]
    cols = st.columns(3)
    for i, (field, label, mx, ic) in enumerate(trio):
        with cols[i]:
            st.metric(f"{ic} {label}", f"{ch[field]} / {mx}")
            if allow_edit:
                b = st.columns(4)
                b[0].button("−5", key=f"lv_{field}_{cid}_m5", on_click=adjust_vital, args=(cid, field, -5))
                b[1].button("−1", key=f"lv_{field}_{cid}_m1", on_click=adjust_vital, args=(cid, field, -1))
                b[2].button("+1", key=f"lv_{field}_{cid}_p1", on_click=adjust_vital, args=(cid, field, +1))
                b[3].button("+5", key=f"lv_{field}_{cid}_p5", on_click=adjust_vital, args=(cid, field, +5))
    if asc:
        st.warning("⚜ 100+ XP ganho — este servo pode ASCENDER DE TIER.")


@st.fragment(run_every=REFRESH_S)
def vox_network():
    st.markdown("#### 📡 Rede Vox")
    chars = list_characters()
    live = []
    for ch in chars:
        if ch["comms_on"]:
            live.append((ch["name"] or "?", "on", ch["kind"]))
        elif secs_since(ch["comms_changed_at"]) < COMMS_FADE_S:
            live.append((ch["name"] or "?", "off", ch["kind"]))
        # senão: sinal perdido -> some
    if not live:
        st.caption("— nenhum sinal ativo —")
        return
    html = ""
    for name, state, kind in live:
        tag = "IRMÃO" if kind == "player" else "NPC"
        cls = "vox-on" if state == "on" else "vox-off"
        dot = "🟢" if state == "on" else "🔴"
        html += f"<div class='vox {cls}'>{dot} {name} <small style='opacity:.6'>[{tag}]</small></div>"
    st.markdown(html, unsafe_allow_html=True)


# ============================================================
#  EDITOR DE FICHA (reativo: perícias e XP calculam sozinhos)
# ============================================================
def _k(cid, section, field):
    return f"f_{cid}_{section}_{field}"


def sheet_editor(cid, gm_mode=False):
    ch = load_character(cid)
    if not ch:
        st.error("Ficha não encontrada.")
        return
    camp = get_campaign()
    species_list = NPC_SPECIES if ch["kind"] == "npc" else PLAYER_SPECIES

    # ---- inicializa o estado dos widgets uma vez por ficha ----
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
    st.session_state.setdefault(_k(cid, "n", "other_xp"), int(ch["other_xp"]))
    sp_key = _k(cid, "sel", "species")
    if sp_key not in st.session_state:
        st.session_state[sp_key] = ch["species"] if ch["species"] in species_list else species_list[-1]

    # ---- identificação ----
    c = st.columns([2, 2, 2])
    c[0].text_input("Nome", key=_k(cid, "t", "name"))
    c[1].text_input("Capítulo / Facção", key=_k(cid, "t", "chapter"))
    c[2].selectbox("Espécie", species_list, key=sp_key)
    c = st.columns([1, 1, 1, 2])
    c[0].number_input("Tier", 1, 5, key=_k(cid, "n", "tier"))
    c[1].number_input("Armadura", 0, 30, key=_k(cid, "n", "armour"))
    c[2].number_input("Outro XP gasto", 0, 100000, key=_k(cid, "n", "other_xp"),
                      help="Habilidade de arquétipo, pacotes de ascensão, poderes psíquicos, etc.")
    if gm_mode:
        exp = c[3].number_input("XP Ganho (Rank)", 0, 100000, int(ch["earned_xp"]),
                                key=f"earn_{cid}")
        if exp != ch["earned_xp"]:
            set_earned_xp(cid, exp)

    # ---- atributos ----
    st.markdown("#### ⚙ Atributos")
    acol = st.columns(7)
    for i, a in enumerate(ATTRS):
        acol[i].number_input(ATTR_ABBR[a], 1, 12, key=_k(cid, "a", a))

    # valores atuais (para cálculo ao vivo)
    cur_attr = {a: int(st.session_state[_k(cid, "a", a)]) for a in ATTRS}
    cur_skill = {s: int(st.session_state[_k(cid, "s", s)]) for s in SKILLS}

    # ---- perícias com pool automático ----
    st.markdown("#### ⚔ Perícias &nbsp;<small style='opacity:.6'>(Pool = valor + atributo, calculado automaticamente)</small>",
                unsafe_allow_html=True)
    scol = st.columns(3)
    for i, s in enumerate(SKILLS):
        with scol[i % 3]:
            cc = st.columns([3, 1])
            cc[0].number_input(f"{s} ({ATTR_ABBR[SKILLS[s]]})", 0, 8, key=_k(cid, "s", s))
            pool = cur_skill[s] + cur_attr[SKILLS[s]]
            cc[1].markdown(f"<div style='padding-top:28px;color:#e8c96a;font-family:Cinzel'>= <b>{pool}</b></div>",
                           unsafe_allow_html=True)

    # ---- talentos (nome + custo XP) ----
    st.markdown("#### ✠ Talentos &nbsp;<small style='opacity:.6'>(nome + custo de XP)</small>",
                unsafe_allow_html=True)
    tdf = ch["talents"] if ch["talents"] else [{"name": "", "cost": 20}]
    edited = st.data_editor(tdf, num_rows="dynamic", key=f"tal_{cid}",
                            column_config={"name": st.column_config.TextColumn("Talento"),
                                           "cost": st.column_config.NumberColumn("XP", min_value=0, step=5)},
                            use_container_width=True)
    talents = [{"name": r.get("name", ""), "cost": int(r.get("cost") or 0)}
               for r in edited if (r.get("name") or "").strip()]

    st.markdown("#### ✠ Wargear & Anotações")
    wc = st.columns(2)
    wc[0].text_area("Wargear (um por linha)", key=_k(cid, "t", "wargear"), height=120)
    wc[1].text_area("Anotações / Objetivos", key=_k(cid, "t", "notes"), height=120)

    # ---- monta o build atual e salva ----
    cur = dict(ch)
    cur.update({"attributes": cur_attr, "skills": cur_skill, "species": st.session_state[sp_key],
                "tier": int(st.session_state[_k(cid, "n", "tier")]),
                "other_xp": int(st.session_state[_k(cid, "n", "other_xp")]),
                "talents": talents})
    save_build(cid,
               st.session_state[_k(cid, "t", "name")], st.session_state[_k(cid, "t", "chapter")],
               st.session_state[sp_key], st.session_state[_k(cid, "n", "tier")],
               cur_attr, cur_skill, talents, st.session_state[_k(cid, "t", "wargear")],
               st.session_state[_k(cid, "n", "armour")], st.session_state[_k(cid, "t", "notes")],
               st.session_state[_k(cid, "n", "other_xp")])

    # ---- painel de XP e traços derivados ----
    st.divider()
    spent = xp_spent(cur)
    start = starting_xp(camp["tier"])
    avail = start + int(ch["earned_xp"]) - spent
    st.markdown("#### ◈ Orçamento de XP")
    x = st.columns(4)
    x[0].metric("XP Inicial (Tier campanha)", start)
    x[1].metric("XP Ganho", ch["earned_xp"])
    x[2].metric("XP Gasto", spent)
    x[3].metric("XP Disponível", avail)
    if avail < 0:
        st.error(f"⚠ Acima do orçamento por {-avail} XP.")

    d = derived_traits(cur)
    st.markdown("#### ◈ Traços Derivados")
    y = st.columns(6)
    for i, key in enumerate(["Defence", "Resilience", "Soak", "Determination", "Resolve", "Conviction"]):
        y[i].metric(key, d[key])
    y = st.columns(6)
    y[0].metric("Max Wounds", d["Max Wounds"]); y[1].metric("Max Shock", d["Max Shock"])
    y[2].metric("Max Wrath", d["Max Wrath"]); y[3].metric("Passive Aware", d["Passive Awareness"])
    y[4].metric("Influence", d["Influence"]); y[5].metric("Speed", d["Speed"])

    # ---- retrato ----
    with st.expander("🖼 Retrato da ficha (opcional)"):
        if ch.get("portrait"):
            st.image(ch["portrait"], width=180)
        up = st.file_uploader("Enviar retrato", type=["png", "jpg", "jpeg"], key=f"port_{cid}")
        if up is not None and st.button("Salvar retrato", key=f"portb_{cid}"):
            set_portrait(cid, up.getvalue())
            st.success("Retrato gravado.")
            st.rerun()


# ============================================================
#  PÁGINAS
# ============================================================
def login_page():
    st.markdown("<div class='banner'>✠ COGITADOR IMPERIAL ✠"
                "<span class='sub'>Adeptus Administratum · Registro de Campanha</span></div>",
                unsafe_allow_html=True)
    st.write("")
    col = st.columns([1, 1.3, 1])[1]
    with col:
        st.markdown("### ⛨ Acesso ao Cogitador")
        st.caption("Identifique-se, servo do Imperador.")
        with st.form("login"):
            u = st.text_input("Designação (usuário)")
            p = st.text_input("Código de Acesso (senha)", type="password")
            ok = st.form_submit_button("AUTENTICAR")
        if ok:
            user = verify_user(u.strip(), p)
            if user:
                st.session_state.user = user
                st.rerun()
            else:
                st.error("⊘ Acesso negado.")
        st.caption("Acesso inicial do Mestre → **magister** / **AveImperator1** (troque depois).")
    st.markdown("<div class='foot'>THE EMPEROR PROTECTS</div>", unsafe_allow_html=True)


def folder_label(fid, folders):
    for f in folders:
        if f["id"] == fid:
            return f["name"]
    return "— Sem pasta —"


def char_row(ch, folders, gm=True):
    """Linha expansível de um personagem na página de Servos."""
    rank, _ = rank_from_xp(ch["earned_xp"])
    vox = "🟢" if ch["comms_on"] else ("🔴" if secs_since(ch["comms_changed_at"]) < COMMS_FADE_S else "⚫")
    title = f"{vox} {ch['name'] or '(sem nome)'} — {ch['species']} · T{ch['tier']} · Rank {rank}"
    with st.expander(title):
        d = derived_traits(ch)
        m = st.columns(3)
        m[0].metric("☠ Wounds", f"{ch['cur_wounds']}/{d['Max Wounds']}")
        m[1].metric("✷ Shock", f"{ch['cur_shock']}/{d['Max Shock']}")
        m[2].metric("🔥 Wrath", f"{ch['cur_wrath']}/{d['Max Wrath']}")
        # vox + pasta
        a = st.columns([1, 1, 2])
        if ch["comms_on"]:
            a[0].button("Cortar Vox", key=f"voxoff_{ch['id']}", on_click=set_comms, args=(ch["id"], 0))
        else:
            a[0].button("Restaurar Vox", key=f"voxon_{ch['id']}", on_click=set_comms, args=(ch["id"], 1))
        opts = [None] + [f["id"] for f in folders]
        cur_idx = opts.index(ch["folder_id"]) if ch["folder_id"] in opts else 0
        a[2].selectbox("Pasta", opts, index=cur_idx, key=f"fold_{ch['id']}",
                       format_func=lambda x: folder_label(x, folders),
                       on_change=lambda cid=ch["id"]: set_folder(cid, st.session_state[f"fold_{cid}"]))
        # ficha
        if st.button("📜 Abrir ficha", key=f"open_{ch['id']}"):
            st.session_state.editing = ch["id"]
            st.rerun()
        if st.button("🗑 Excluir", key=f"del_{ch['id']}"):
            delete_character(ch["id"])
            st.rerun()


def gm_view():
    camp = get_campaign()
    st.markdown("<div class='banner'>✠ SANCTUM DO MAGISTER ✠"
                "<span class='sub'>Comando da Campanha</span></div>", unsafe_allow_html=True)

    # editor aberto?
    if st.session_state.get("editing"):
        cid = st.session_state.editing
        if st.button("‹ Voltar aos Servos"):
            st.session_state.editing = None
            st.rerun()
        live_vitals(cid, allow_edit=True)
        st.divider()
        sheet_editor(cid, gm_mode=True)
        return

    tabs = st.tabs(["⛨ Servos & NPCs", "⚜ XP", "🩸 Campanha & Ruína", "📡 Vox", "🛠 Manutenção"])

    # ---------- Servos & NPCs ----------
    with tabs[0]:
        folders = list_folders()
        with st.expander("📁 Pastas (podem misturar Jogadores e NPCs)"):
            cc = st.columns([2, 1])
            newf = cc[0].text_input("Nova pasta", key="newfolder")
            if cc[1].button("Criar pasta"):
                if newf.strip():
                    create_folder(newf.strip())
                    st.rerun()
            for f in folders:
                fc = st.columns([3, 1])
                nm = fc[0].text_input("nome", f["name"], key=f"fn_{f['id']}", label_visibility="collapsed")
                if nm != f["name"]:
                    rename_folder(f["id"], nm)
                if fc[1].button("Excluir", key=f"fdel_{f['id']}"):
                    delete_folder(f["id"])
                    st.rerun()

        st.divider()
        # criação
        cre = st.columns(2)
        with cre[0]:
            st.markdown("### ⚔ Recrutar Jogador")
            with st.form("newp"):
                nu = st.text_input("Usuário")
                npw = st.text_input("Senha", type="password")
                if st.form_submit_button("Recrutar"):
                    if nu.strip() and npw:
                        ok, msg = create_player(nu.strip(), npw)
                        (st.success if ok else st.error)(msg)
                        if ok:
                            st.rerun()
                    else:
                        st.error("Preencha usuário e senha.")
        with cre[1]:
            st.markdown("### ☠ Criar NPC")
            with st.form("newn"):
                nn = st.text_input("Nome do NPC")
                nsp = st.selectbox("Raça / Tipo", NPC_SPECIES)
                nt = st.number_input("Tier", 1, 5, 2)
                if st.form_submit_button("Criar NPC"):
                    create_npc(nn.strip(), nsp, nt)
                    st.rerun()

        st.divider()
        view = st.radio("Organização", ["Por Tipo (2 colunas)", "Por Pastas"], horizontal=True)
        if view == "Por Tipo (2 colunas)":
            colp, coln = st.columns(2)
            with colp:
                st.markdown("### ⚔ Jogadores")
                for ch in list_characters("player"):
                    char_row(ch, folders)
            with coln:
                st.markdown("### ☠ NPCs")
                for ch in list_characters("npc"):
                    char_row(ch, folders)
        else:
            allc = list_characters()
            groups = {None: []}
            for f in folders:
                groups[f["id"]] = []
            for ch in allc:
                groups.setdefault(ch["folder_id"], []).append(ch)
            for fid, items in groups.items():
                st.markdown(f"### 📁 {folder_label(fid, folders)}")
                if not items:
                    st.caption("— vazia —")
                for ch in items:
                    char_row(ch, folders)

    # ---------- XP ----------
    with tabs[1]:
        st.markdown("### Conceder Experiência de Batalha")
        st.caption("Rank: 40 XP→R2, 80→R3. A partir de 100, pode ascender de Tier.")
        chars = list_characters("player")
        if not chars:
            st.info("Nenhum jogador.")
        else:
            names = {c["name"] or f"#{c['id']}": c["id"] for c in chars}
            with st.form("xpf"):
                cc = st.columns([2, 1, 2])
                who = cc[0].selectbox("Servo", ["— Toda a mesa —"] + list(names.keys()))
                amt = cc[1].number_input("XP", -200, 500, 10)
                why = cc[2].text_input("Motivo")
                if st.form_submit_button("Conceder"):
                    tgt = list(names.values()) if who == "— Toda a mesa —" else [names[who]]
                    for cid in tgt:
                        award_xp(cid, amt)
                    add_log("Magister", f"{amt:+} XP → {who}. {why}".strip())
                    st.success("Concedido.")
                    st.rerun()
            st.divider()
            for c in chars:
                rk, asc = rank_from_xp(c["earned_xp"])
                st.write(f"**{c['name']}** — {c['earned_xp']} XP · Rank {rk} · Tier {c['tier']}"
                         + ("  🔥 *pode ascender!*" if asc else ""))

    # ---------- Campanha & Ruína ----------
    with tabs[2]:
        st.markdown("### Configuração da Campanha")
        with st.form("campf"):
            cc = st.columns([3, 1, 1])
            cname = cc[0].text_input("Nome da campanha", camp["name"])
            ctier = cc[1].number_input("Tier da campanha", 1, 5, int(camp["tier"]),
                                       help="Define o XP inicial de todos: Tier × 100.")
            sess = cc[2].number_input("Sessão nº", 1, 999, int(camp["session_no"]))
            if st.form_submit_button("Salvar"):
                save_campaign(cname, ctier, camp["ruin"], sess)
                st.success("Salvo.")
                st.rerun()
        st.caption(f"XP inicial atual dos personagens: **{starting_xp(camp['tier'])}** "
                   f"(Tier {camp['tier']} × 100).")
        st.divider()
        st.markdown("### ☠ Pontos de Ruína (Ruin) do Mestre")
        rc = st.columns([1, 1, 1, 1, 3])
        rc[0].metric("Ruína", camp["ruin"])
        rc[1].button("−1", key="ruin_m", on_click=adjust_ruin, args=(-1,))
        rc[2].button("+1", key="ruin_p", on_click=adjust_ruin, args=(+1,))
        rc[3].button("Zerar", key="ruin_z", on_click=lambda: save_campaign(camp["name"], camp["tier"], 0, camp["session_no"]))

    # ---------- Vox ----------
    with tabs[3]:
        vox_network()
        st.divider()
        st.markdown("### 📡 Vox-cast (registro de sessão)")
        with st.form("voxlog"):
            msg = st.text_area("Nova entrada")
            if st.form_submit_button("Transmitir"):
                if msg.strip():
                    add_log("Magister", msg.strip())
                    st.rerun()
        for lg in get_logs():
            st.markdown(f"<div class='panel'>🕯 <b>{lg['ts']}</b> — <i>{lg['author']}</i><br>{lg['text']}</div>",
                        unsafe_allow_html=True)

    # ---------- Manutenção ----------
    with tabs[4]:
        st.markdown("### 🛠 Manutenção dos Arquivos (só o Mestre)")
        st.caption("O backup .db contém TUDO: jogadores, NPCs, pastas, XP, vox, retratos. "
                   "Em hospedagem grátis o disco é volátil — baixe periodicamente e reenvie após reinício.")
        if os.path.exists(DB_PATH):
            size = os.path.getsize(DB_PATH) / (1024 * 1024)
            st.write(f"Tamanho atual do banco: **{size:.2f} MB** "
                     f"(o SQLite aguenta até ~281 TB; cresce sozinho com fichas e retratos).")
            with open(DB_PATH, "rb") as f:
                st.download_button("⬇ Baixar backup completo (cogitador.db)", f.read(),
                                   file_name="cogitador.db", mime="application/octet-stream")
        up = st.file_uploader("⬆ Restaurar backup (.db)", type=["db"])
        if up is not None and st.button("⚠ Sobrescrever tudo com este backup"):
            with open(DB_PATH, "wb") as f:
                f.write(up.getbuffer())
            st.success("Restaurado.")
            st.rerun()


def player_view():
    camp = get_campaign()
    st.markdown(f"<div class='banner'>⚔ FICHA DE SERVIÇO ⚔"
                f"<span class='sub'>{camp['name']} · Sessão {camp['session_no']}</span></div>",
                unsafe_allow_html=True)
    cid = char_id_for_user(st.session_state.user["id"])
    if not cid:
        st.error("Nenhuma ficha vinculada. Contate o Magister.")
        return
    # topo: vitais editáveis ao vivo + rede vox
    top = st.columns([3, 1.4])
    with top[0]:
        live_vitals(cid, allow_edit=True)
    with top[1]:
        vox_network()
    st.divider()
    sheet_editor(cid, gm_mode=False)


# ============================================================
#  MAIN
# ============================================================
def main():
    st.set_page_config(page_title="Cogitador Imperial · Wrath & Glory", page_icon="✠", layout="wide")
    inject_theme()
    init_db()
    st.session_state.setdefault("user", None)
    st.session_state.setdefault("editing", None)

    if st.session_state.user is None:
        login_page()
        return

    with st.sidebar:
        camp = get_campaign()
        role = st.session_state.user["role"]
        st.markdown(f"### ✠ {camp['name']}")
        st.write(f"Servo: **{st.session_state.user['username']}**")
        st.write(f"Função: **{'Magister (Mestre)' if role == 'gm' else 'Irmão de Batalha'}**")
        if role == "gm":
            st.metric("☠ Ruína (Ruin)", camp["ruin"])
        st.divider()
        if st.button("⏻ Encerrar Sessão"):
            st.session_state.user = None
            st.session_state.editing = None
            st.rerun()
        with st.expander("🔑 Alterar minha senha"):
            with st.form("chpw"):
                a = st.text_input("Nova senha", type="password")
                b = st.text_input("Confirmar", type="password")
                if st.form_submit_button("Alterar"):
                    if a and a == b:
                        set_password(st.session_state.user["id"], a)
                        st.success("Senha atualizada.")
                    else:
                        st.error("As senhas não conferem.")

    if st.session_state.user["role"] == "gm":
        gm_view()
    else:
        player_view()

    st.markdown("<div class='foot'>✠ THE EMPEROR PROTECTS ✠</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()