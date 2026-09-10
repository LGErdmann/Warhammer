"""
Login inicial do Mestre:  usuário = magister   senha = AveImperator1  (troque após entrar!)
"""

import streamlit as st
import sqlite3
import hashlib
import secrets
import json
import math
import os
from datetime import datetime

DB_PATH = os.environ.get("WG_DB_PATH", "cogitador.db")

# ============================================================
#  DADOS DE WRATH & GLORY
# ============================================================
ATTRS = ["Strength", "Toughness", "Agility", "Initiative", "Willpower", "Intellect", "Fellowship"]
ATTR_ABBR = {"Strength": "S", "Toughness": "T", "Agility": "A", "Initiative": "I",
             "Willpower": "Wil", "Intellect": "Int", "Fellowship": "Fel"}

# Perícia -> atributo regente (conforme o livro / Forge do Doctors of Doom)
SKILLS = {
    "Athletics": "Strength", "Awareness": "Intellect", "Ballistic Skill": "Agility",
    "Cunning": "Fellowship", "Deception": "Fellowship", "Insight": "Fellowship",
    "Intimidation": "Willpower", "Investigation": "Intellect", "Leadership": "Willpower",
    "Medicae": "Intellect", "Persuasion": "Fellowship", "Pilot": "Agility",
    "Psychic Mastery": "Willpower", "Scholar": "Intellect", "Stealth": "Agility",
    "Survival": "Willpower", "Tech": "Intellect", "Weapon Skill": "Initiative",
}

SPECIES = ["Adeptus Astartes", "Primaris Astartes", "Astra Militarum (Humano)",
           "Adepta Sororitas", "Aeldari", "Ork", "Outro"]


def default_attributes():
    return {a: 1 for a in ATTRS}


def default_skills():
    return {s: 0 for s in SKILLS}


def rank_from_xp(xp):
    """Rank sobe a cada 40 XP ganho; teto de 3; a partir de 100 pode ascender de Tier (livro p.147)."""
    xp = int(xp or 0)
    rank = min(3, 1 + xp // 40)
    return rank, xp >= 100


def is_astartes(species):
    return species in ("Adeptus Astartes", "Primaris Astartes")


def derived_traits(ch):
    """Traços derivados pelas fórmulas do rulebook (reproduz o resultado do Forge)."""
    a, sk = ch["attributes"], ch["skills"]
    tier = int(ch.get("tier", 1))
    armour = int(ch.get("armour", 0))
    species = ch.get("species", "")
    T = a.get("Toughness", 1)
    I = a.get("Initiative", 1)
    Wil = a.get("Willpower", 1)
    Intl = a.get("Intellect", 1)
    Fel = a.get("Fellowship", 1)
    astartes = is_astartes(species)
    return {
        "Defence": I - 1,
        "Resilience": T + 1 + armour,
        "Soak": T,
        "Max Wounds": T + 2 * tier + (3 if species == "Primaris Astartes" else 0),
        "Max Shock": Wil + tier,
        "Determination": T,
        "Resolve": max(0, Wil - 1) + (1 if astartes else 0),
        "Conviction": Wil,
        "Passive Awareness": math.ceil((Intl + sk.get("Awareness", 0)) / 2),
        "Influence": max(0, Fel - 1),
        "Speed": 7 if astartes else (8 if species == "Aeldari" else 6),
    }


# ============================================================
#  BANCO DE DADOS (SQLite)
# ============================================================
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def hash_pw(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100_000).hex()


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
        pw_hash TEXT NOT NULL, salt TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'player', created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS characters(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE,
        name TEXT, chapter TEXT, species TEXT, tier INTEGER DEFAULT 2,
        earned_xp INTEGER DEFAULT 0, attributes TEXT, skills TEXT,
        talents TEXT, wargear TEXT, armour INTEGER DEFAULT 0,
        cur_wounds INTEGER DEFAULT 0, cur_shock INTEGER DEFAULT 0, notes TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS campaign(
        id INTEGER PRIMARY KEY CHECK (id=1), name TEXT,
        wrath INTEGER DEFAULT 0, session_no INTEGER DEFAULT 1)""")
    c.execute("""CREATE TABLE IF NOT EXISTS log(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, author TEXT, text TEXT)""")
    conn.commit()
    if c.execute("SELECT COUNT(*) FROM campaign").fetchone()[0] == 0:
        c.execute("INSERT INTO campaign(id,name,wrath,session_no) VALUES(1,?,0,1)",
                  ("A Cruzada de Gilead",))
    if c.execute("SELECT COUNT(*) FROM users WHERE role='gm'").fetchone()[0] == 0:
        salt = secrets.token_hex(16)
        c.execute("INSERT INTO users(username,pw_hash,salt,role,created_at) VALUES(?,?,?,?,?)",
                  ("magister", hash_pw("AveImperator1", salt), salt, "gm",
                   datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()


def create_user(username, pw, role):
    conn = get_conn()
    c = conn.cursor()
    try:
        salt = secrets.token_hex(16)
        c.execute("INSERT INTO users(username,pw_hash,salt,role,created_at) VALUES(?,?,?,?,?)",
                  (username, hash_pw(pw, salt), salt, role, datetime.utcnow().isoformat()))
        uid = c.lastrowid
        if role == "player":
            c.execute("""INSERT INTO characters(user_id,name,chapter,species,tier,earned_xp,
                         attributes,skills,talents,wargear,armour,cur_wounds,cur_shock,notes)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (uid, username, "", "Adeptus Astartes", 2, 0,
                       json.dumps(default_attributes()), json.dumps(default_skills()),
                       "", "", 0, 0, 0, ""))
        conn.commit()
        return True, "Servo registrado."
    except sqlite3.IntegrityError:
        return False, "Essa designação já existe nos arquivos."
    finally:
        conn.close()


def verify_user(username, pw):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    if row and hash_pw(pw, row["salt"]) == row["pw_hash"]:
        return {"id": row["id"], "username": row["username"], "role": row["role"]}
    return None


def set_password(uid, newpw):
    conn = get_conn()
    salt = secrets.token_hex(16)
    conn.execute("UPDATE users SET pw_hash=?,salt=? WHERE id=?", (hash_pw(newpw, salt), salt, uid))
    conn.commit()
    conn.close()


def list_players():
    conn = get_conn()
    rows = conn.execute("SELECT id,username FROM users WHERE role='player' ORDER BY username").fetchall()
    conn.close()
    return rows


def delete_user(uid):
    conn = get_conn()
    conn.execute("DELETE FROM characters WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit()
    conn.close()


def load_character(user_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM characters WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    if not row:
        return None
    ch = dict(row)
    ch["attributes"] = json.loads(ch["attributes"] or "{}")
    ch["skills"] = json.loads(ch["skills"] or "{}")
    for a in ATTRS:
        ch["attributes"].setdefault(a, 1)
    for s in SKILLS:
        ch["skills"].setdefault(s, 0)
    return ch


def save_character(ch):
    conn = get_conn()
    conn.execute("""UPDATE characters SET name=?,chapter=?,species=?,tier=?,earned_xp=?,
                    attributes=?,skills=?,talents=?,wargear=?,armour=?,cur_wounds=?,cur_shock=?,notes=?
                    WHERE user_id=?""",
                 (ch["name"], ch["chapter"], ch["species"], ch["tier"], ch["earned_xp"],
                  json.dumps(ch["attributes"]), json.dumps(ch["skills"]),
                  ch["talents"], ch["wargear"], ch["armour"], ch["cur_wounds"],
                  ch["cur_shock"], ch["notes"], ch["user_id"]))
    conn.commit()
    conn.close()


def award_xp(user_id, amount):
    conn = get_conn()
    conn.execute("UPDATE characters SET earned_xp = earned_xp + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()


def get_campaign():
    conn = get_conn()
    row = conn.execute("SELECT * FROM campaign WHERE id=1").fetchone()
    conn.close()
    return dict(row) if row else {"name": "", "wrath": 0, "session_no": 1}


def save_campaign(name, wrath, session_no):
    conn = get_conn()
    conn.execute("UPDATE campaign SET name=?,wrath=?,session_no=? WHERE id=1",
                 (name, wrath, session_no))
    conn.commit()
    conn.close()


def add_log(author, text):
    conn = get_conn()
    conn.execute("INSERT INTO log(ts,author,text) VALUES(?,?,?)",
                 (datetime.utcnow().strftime("%Y-%m-%d %H:%M"), author, text))
    conn.commit()
    conn.close()


def get_logs(limit=60):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return rows


# ============================================================
#  TEMA VISUAL (Warhammer 40k gótico)
# ============================================================
def inject_theme():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@500;700;900&family=EB+Garamond:ital@0;1&display=swap');
    :root{ --blood:#7a0f12; --blood2:#a4161a; --gold:#c9a227; --gold2:#e8c96a;
           --bone:#e8e0cf; --ink:#0c0a09; --panel:#1a1510; }
    .stApp{ background: radial-gradient(circle at 50% -8%, #221a12 0%, #0c0a09 55%) fixed; color:var(--bone); }
    html,body,[class*="css"], p, label, .stMarkdown{ font-family:'EB Garamond', Georgia, serif; color:var(--bone); }
    h1,h2,h3,h4,h5{ font-family:'Cinzel', serif !important; color:var(--gold) !important;
        letter-spacing:.08em; text-transform:uppercase; text-shadow:0 1px 2px #000; }
    .banner{ text-align:center; font-family:'Cinzel',serif; font-weight:900; font-size:2.1rem;
        color:var(--gold2); letter-spacing:.15em; padding:18px 0 6px;
        border-bottom:2px solid var(--gold); text-shadow:0 2px 6px #000; }
    .banner .sub{ display:block; font-size:.85rem; letter-spacing:.35em; color:var(--bone);
        opacity:.75; text-transform:uppercase; margin-top:4px; }
    .stButton>button{ background:linear-gradient(#241c14,#160f0a); color:var(--gold2);
        border:1px solid var(--gold); border-radius:2px; font-family:'Cinzel',serif;
        letter-spacing:.08em; text-transform:uppercase; font-weight:700; transition:.15s; }
    .stButton>button:hover{ background:linear-gradient(var(--blood),var(--blood2)); color:#fff;
        border-color:var(--gold2); }
    input, textarea, .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb]{
        background:#120d08 !important; color:var(--bone) !important; border-color:#4a3a20 !important; }
    [data-testid="stMetric"]{ background:var(--panel); border:1px solid #4a3a20;
        border-left:4px solid var(--gold); border-radius:3px; padding:8px 12px; }
    [data-testid="stMetricValue"]{ color:var(--gold2) !important; font-family:'Cinzel',serif; }
    [data-testid="stMetricLabel"]{ color:var(--bone) !important; text-transform:uppercase; letter-spacing:.05em; }
    section[data-testid="stSidebar"]{ background:#0f0b07; border-right:1px solid var(--gold); }
    hr{ border-color:var(--gold); opacity:.4; }
    .stTabs [data-baseweb="tab"]{ font-family:'Cinzel',serif; color:var(--bone);
        text-transform:uppercase; letter-spacing:.05em; }
    .stTabs [aria-selected="true"]{ color:var(--gold2) !important; border-bottom-color:var(--gold) !important; }
    .panel{ background:var(--panel); border:1px solid #4a3a20; border-radius:3px; padding:14px 18px; }
    .foot{ text-align:center; color:var(--gold); opacity:.6; font-family:'Cinzel',serif;
        letter-spacing:.3em; font-size:.8rem; margin-top:24px; }
    </style>
    """, unsafe_allow_html=True)


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
        st.caption("Identifique-se, servo do Imperador. Os hereges não passam.")
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
                st.error("⊘ Acesso negado. O Imperador vê tudo.")
    st.markdown("<div class='foot'>THE EMPEROR PROTECTS</div>", unsafe_allow_html=True)


def render_derived(ch):
    d = derived_traits(ch)
    rank, asc = rank_from_xp(ch["earned_xp"])
    st.markdown("#### ◈ Traços Derivados")
    c = st.columns(6)
    c[0].metric("Tier", ch["tier"])
    c[1].metric("Rank", rank)
    c[2].metric("XP Ganho", ch["earned_xp"])
    c[3].metric("Defence", d["Defence"])
    c[4].metric("Resilience", d["Resilience"])
    c[5].metric("Soak", d["Soak"])
    c = st.columns(6)
    c[0].metric("Wounds", f"{ch['cur_wounds']}/{d['Max Wounds']}")
    c[1].metric("Shock", f"{ch['cur_shock']}/{d['Max Shock']}")
    c[2].metric("Determination", d["Determination"])
    c[3].metric("Resolve", d["Resolve"])
    c[4].metric("Conviction", d["Conviction"])
    c[5].metric("Speed", d["Speed"])
    if asc:
        st.warning("⚜ 100+ XP ganho — este servo pode **ASCENDER DE TIER** (ver Archetype Ascension).")


def sheet_editor(ch, gm_mode=False):
    st.markdown(f"## ⚔ {ch['name'] or 'Servo Sem Nome'}")
    render_derived(ch)
    st.divider()
    with st.form(f"sheet_{ch['user_id']}"):
        cols = st.columns(3)
        name = cols[0].text_input("Nome do personagem", ch["name"])
        chapter = cols[1].text_input("Capítulo / Facção", ch["chapter"])
        sp_idx = SPECIES.index(ch["species"]) if ch["species"] in SPECIES else 0
        species = cols[2].selectbox("Espécie", SPECIES, index=sp_idx)

        cols = st.columns(3)
        tier = cols[0].number_input("Tier", 1, 5, int(ch["tier"]))
        armour = cols[1].number_input("Armadura (bônus Resiliência)", 0, 20, int(ch["armour"]))
        if gm_mode:
            earned = cols[2].number_input("XP Ganho (total)", 0, 100000, int(ch["earned_xp"]),
                                          help="Só o Mestre altera. Define o Rank.")
        else:
            cols[2].metric("XP Ganho", ch["earned_xp"])
            earned = int(ch["earned_xp"])

        st.markdown("#### ⚙ Atributos")
        acols = st.columns(7)
        na = {}
        for i, a in enumerate(ATTRS):
            na[a] = acols[i].number_input(ATTR_ABBR[a], 1, 12, int(ch["attributes"].get(a, 1)),
                                          key=f"a_{ch['user_id']}_{a}")

        st.markdown("#### ⚔ Perícias  \n<small>valor da perícia + atributo regente</small>",
                    unsafe_allow_html=True)
        ns = {}
        scols = st.columns(3)
        for i, s in enumerate(SKILLS):
            ns[s] = scols[i % 3].number_input(f"{s} ({ATTR_ABBR[SKILLS[s]]})", 0, 8,
                                              int(ch["skills"].get(s, 0)), key=f"s_{ch['user_id']}_{s}")

        st.markdown("#### ✠ Talentos & Wargear")
        tcol, wcol = st.columns(2)
        talents = tcol.text_area("Talentos (um por linha)", ch["talents"], height=140)
        wargear = wcol.text_area("Wargear (um por linha)", ch["wargear"], height=140)

        st.markdown("#### ☠ Combate / Estado")
        ccol = st.columns(2)
        cw = ccol[0].number_input("Ferimentos atuais (Wounds)", 0, 300, int(ch["cur_wounds"]))
        cs = ccol[1].number_input("Choque atual (Shock)", 0, 300, int(ch["cur_shock"]))
        notes = st.text_area("Anotações / Objetivos", ch["notes"], height=100)

        saved = st.form_submit_button("💾 Gravar Ficha nos Arquivos")

    if saved:
        ch.update({"name": name, "chapter": chapter, "species": species, "tier": int(tier),
                   "earned_xp": int(earned), "attributes": na, "skills": ns,
                   "talents": talents, "wargear": wargear, "armour": int(armour),
                   "cur_wounds": int(cw), "cur_shock": int(cs), "notes": notes})
        save_character(ch)
        st.success("✠ Ficha registrada nos arquivos do Administratum.")
        st.rerun()


def gm_view():
    st.markdown("<div class='banner'>✠ SANCTUM DO MAGISTER ✠"
                "<span class='sub'>Comando da Campanha</span></div>", unsafe_allow_html=True)
    tabs = st.tabs(["⛨ Servos da Mesa", "📜 Fichas", "⚜ Concessão de XP",
                    "🩸 Campanha & Vox", "🛠 Manutenção"])

    # --- Servos (contas) ---
    with tabs[0]:
        st.markdown("### Recrutar novo servo (jogador)")
        with st.form("new_player"):
            c = st.columns(2)
            nu = c[0].text_input("Designação (usuário)")
            npw = c[1].text_input("Código de acesso (senha)", type="password")
            if st.form_submit_button("Recrutar"):
                if nu.strip() and npw:
                    ok, msg = create_user(nu.strip(), npw, "player")
                    (st.success if ok else st.error)(msg)
                    if ok:
                        st.rerun()
                else:
                    st.error("Preencha usuário e senha.")
        st.divider()
        st.markdown("### Servos registrados")
        players = list_players()
        if not players:
            st.info("Nenhum jogador recrutado ainda.")
        for p in players:
            ch = load_character(p["id"])
            rank, _ = rank_from_xp(ch["earned_xp"]) if ch else (1, False)
            with st.expander(f"⚔ {p['username']} — {ch['name'] or '(sem nome)'} · "
                             f"Tier {ch['tier'] if ch else '?'} · Rank {rank}"):
                cc = st.columns([2, 2, 1])
                with cc[0].form(f"pw_{p['id']}"):
                    rp = st.text_input("Nova senha", type="password", key=f"rp_{p['id']}")
                    if st.form_submit_button("Redefinir senha"):
                        if rp:
                            set_password(p["id"], rp)
                            st.success("Senha redefinida.")
                if cc[2].button("🗑 Excluir", key=f"del_{p['id']}"):
                    delete_user(p["id"])
                    st.rerun()

    # --- Fichas ---
    with tabs[1]:
        players = list_players()
        if not players:
            st.info("Recrute jogadores na aba Servos para editar fichas.")
        else:
            names = {f"{p['username']}": p["id"] for p in players}
            pick = st.selectbox("Selecione o servo", list(names.keys()))
            ch = load_character(names[pick])
            if ch:
                sheet_editor(ch, gm_mode=True)

    # --- XP ---
    with tabs[2]:
        st.markdown("### Conceder Experiência de Batalha")
        st.caption("Rank sobe a cada 40 XP (40→R2, 80→R3). A partir de 100, o servo pode ascender de Tier.")
        players = list_players()
        if not players:
            st.info("Nenhum jogador para premiar.")
        else:
            names = {p["username"]: p["id"] for p in players}
            with st.form("xp"):
                c = st.columns([2, 1, 2])
                who = c[0].selectbox("Servo", ["— Toda a mesa —"] + list(names.keys()))
                amt = c[1].number_input("XP", -100, 500, 10)
                reason = c[2].text_input("Motivo (registro)")
                if st.form_submit_button("Conceder XP"):
                    targets = list(names.values()) if who == "— Toda a mesa —" else [names[who]]
                    for uid in targets:
                        award_xp(uid, int(amt))
                    add_log("Magister", f"Concedeu {amt} XP a {who}. {reason}".strip())
                    st.success(f"⚜ {amt} XP concedido a {who}.")
                    st.rerun()
            st.divider()
            st.markdown("#### Situação da mesa")
            for p in players:
                ch = load_character(p["id"])
                rank, asc = rank_from_xp(ch["earned_xp"])
                line = f"**{p['username']}** — {ch['earned_xp']} XP · Rank {rank} · Tier {ch['tier']}"
                st.write(line + ("  🔥 *pode ascender!*" if asc else ""))

    # --- Campanha & Vox ---
    with tabs[3]:
        camp = get_campaign()
        st.markdown("### Registro da Campanha")
        with st.form("camp"):
            c = st.columns([3, 1, 1])
            cname = c[0].text_input("Nome da campanha", camp["name"])
            wrath = c[1].number_input("Ira (Wrath) da mesa", 0, 50, int(camp["wrath"]))
            sess = c[2].number_input("Sessão nº", 1, 999, int(camp["session_no"]))
            if st.form_submit_button("Salvar"):
                save_campaign(cname, int(wrath), int(sess))
                st.success("Registro atualizado.")
                st.rerun()
        st.divider()
        st.markdown("### 📡 Vox-cast (registro de sessão)")
        with st.form("vox"):
            msg = st.text_area("Nova entrada no registro")
            if st.form_submit_button("Transmitir"):
                if msg.strip():
                    add_log("Magister", msg.strip())
                    st.rerun()
        for lg in get_logs():
            st.markdown(f"<div class='panel'>🕯 <b>{lg['ts']}</b> — <i>{lg['author']}</i><br>{lg['text']}</div>",
                        unsafe_allow_html=True)
            st.write("")

    # --- Manutenção (backup) ---
    with tabs[4]:
        st.markdown("### 🛠 Manutenção dos Arquivos")
        st.caption("Em hospedagem gratuita o armazenamento é volátil (reinicia às vezes). "
                   "Baixe o arquivo periodicamente e reenvie após um reinício para não perder dados.")
        if os.path.exists(DB_PATH):
            with open(DB_PATH, "rb") as f:
                st.download_button("⬇ Baixar backup (cogitador.db)", f.read(),
                                   file_name="cogitador.db", mime="application/octet-stream")
        up = st.file_uploader("⬆ Restaurar backup (.db)", type=["db"])
        if up is not None:
            if st.button("⚠ Sobrescrever arquivos com este backup"):
                with open(DB_PATH, "wb") as f:
                    f.write(up.getbuffer())
                st.success("Arquivos restaurados. Recarregando...")
                st.rerun()


def player_view():
    camp = get_campaign()
    st.markdown(f"<div class='banner'>⚔ FICHA DE SERVIÇO ⚔"
                f"<span class='sub'>{camp['name']} · Sessão {camp['session_no']}</span></div>",
                unsafe_allow_html=True)
    ch = load_character(st.session_state.user["id"])
    if not ch:
        st.error("Nenhuma ficha vinculada a este servo. Contate o Magister.")
        return
    sheet_editor(ch, gm_mode=False)


# ============================================================
#  MAIN
# ============================================================
def main():
    st.set_page_config(page_title="Cogitador Imperial · Wrath & Glory",
                       page_icon="✠", layout="wide")
    inject_theme()
    init_db()
    if "user" not in st.session_state:
        st.session_state.user = None

    if st.session_state.user is None:
        login_page()
        return

    with st.sidebar:
        camp = get_campaign()
        st.markdown(f"### ✠ {camp['name']}")
        role = st.session_state.user["role"]
        st.write(f"Servo: **{st.session_state.user['username']}**")
        st.write(f"Função: **{'Magister (Mestre)' if role == 'gm' else 'Irmão de Batalha'}**")
        if role == "gm":
            st.metric("Ira da Mesa (Wrath)", camp["wrath"])
        st.divider()
        if st.button("⏻ Encerrar Sessão"):
            st.session_state.user = None
            st.rerun()
        with st.expander("🔑 Alterar meu Código de Acesso"):
            with st.form("chpw"):
                a = st.text_input("Nova senha", type="password")
                b = st.text_input("Confirmar", type="password")
                if st.form_submit_button("Alterar"):
                    if a and a == b:
                        set_password(st.session_state.user["id"], a)
                        st.success("Código de acesso atualizado.")
                    else:
                        st.error("As senhas não conferem.")

    if st.session_state.user["role"] == "gm":
        gm_view()
    else:
        player_view()

    st.markdown("<div class='foot'>✠ THE EMPEROR PROTECTS ✠</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()