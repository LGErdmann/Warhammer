"""

"""

import streamlit as st
import sqlite3
import hashlib
import secrets
import json
import math
import html
import os
import random
from datetime import datetime, timezone

DB_PATH = os.environ.get("WG_DB_PATH", "cogitador.db")
REFRESH_S = 3.0
COMMS_FADE_S = 60

# ============================================================
#  DADOS DE WRATH & GLORY
# ============================================================
ATTRS = ["Strength", "Toughness", "Agility", "Initiative", "Willpower", "Intellect", "Fellowship"]
SKILLS = {
    "Athletics": "Strength", "Awareness": "Intellect", "Ballistic Skill": "Agility",
    "Cunning": "Fellowship", "Deception": "Fellowship", "Insight": "Fellowship",
    "Intimidation": "Willpower", "Investigation": "Intellect", "Leadership": "Willpower",
    "Medicae": "Intellect", "Persuasion": "Fellowship", "Pilot": "Agility",
    "Psychic Mastery": "Willpower", "Scholar": "Intellect", "Stealth": "Agility",
    "Survival": "Willpower", "Tech": "Intellect", "Weapon Skill": "Initiative",
}
PLAYER_SPECIES = ["Human", "Abhuman", "Adeptus Astartes", "Primaris Astartes", "Aeldari", "Ork"]
SPECIES_LABELS = {
    "Astra Militarum (Humano)": "Astra Militarum (Human)",
    "Adepta Sororitas": "Adepta Sororitas",
    "Aeldari (Asuryani)": "Aeldari (Asuryani)",
    "Inquisição": "Inquisition",
    "Drukhari": "Drukhari",
    "Ork": "Ork",
    "T'au": "T'au",
    "Necron": "Necron",
    "Tyranid": "Tyranid",
    "Genestealer": "Genestealer",
    "Daemon de Khorne": "Daemon of Khorne",
    "Daemon de Nurgle": "Daemon of Nurgle",
    "Daemon de Tzeentch": "Daemon of Tzeentch",
    "Daemon de Slaanesh": "Daemon of Slaanesh",
    "Cultista do Caos": "Chaos Cultist",
    "Fera": "Beast",
    "Servitor": "Servitor",
    "Outro": "Other",
    "Human": "Human",
    "Aeldari": "Aeldari",
    "Ork": "Ork",
    "Primaris Astartes": "Primaris Astartes",
}

def species_label(sp):
    return SPECIES_LABELS.get(sp, sp)

NPC_SPECIES = ["Adeptus Astartes", "Primaris Astartes", "Chaos Space Marine",
               "Astra Militarum (Humano)", "Adepta Sororitas", "Inquisição", "Rogue Trader",
               "Aeldari (Asuryani)", "Drukhari", "Ork", "T'au", "Necron", "Tyranid",
               "Genestealer", "Daemon de Khorne", "Daemon de Nurgle", "Daemon de Tzeentch",
               "Daemon de Slaanesh", "Cultista do Caos", "Fera", "Servitor", "Outro"]
ATTR_COST = {1: 0, 2: 4, 3: 10, 4: 20, 5: 35, 6: 55, 7: 80, 8: 110, 9: 145, 10: 185, 11: 230, 12: 280}
SKILL_COST = {0: 0, 1: 2, 2: 6, 3: 12, 4: 20, 5: 30, 6: 42, 7: 56, 8: 72}
# Species packages.
# XP here is the TOTAL package cost: attributes + skills + abilities.
# Abilities are not charged again as talents.
SPECIES_PACKAGES = {
    "Human": {"xp": 0, "attributes": {}, "skills": {}, "abilities": [], "speed": 6, "size": "Average"},
    "Abhuman": {"xp": 0, "attributes": {}, "skills": {}, "abilities": [], "speed": 6, "size": "Average"},
    "Adeptus Astartes": {
        "xp": 160,
        "attributes": {"Agility": 4, "Initiative": 4, "Intellect": 3, "Strength": 4, "Toughness": 4, "Willpower": 3},
        "skills": {"Athletics": 3, "Awareness": 3, "Ballistic Skill": 3, "Stealth": 3, "Weapon Skill": 3},
        "abilities": [
            "Defender of Humanity: Add +Rank Icons to any successful attack against a Mob.",
            "Honour the Chapter: You are subject to the orders of your chapter master, and must honour the beliefs and traditions of your chapter. Your Resolve increases by +1.",
            "Space Marine Implants: You are immune to the Bleeding Condition. You gain +1 bonus dice to any test related to one of the 19 implants if the GM agrees it is appropriate.",
        ], "speed": 7, "size": "Average"},
    "Primaris Astartes": {
        "xp": 198,
        "attributes": {"Agility": 4, "Initiative": 4, "Intellect": 3, "Strength": 5, "Toughness": 5, "Willpower": 3},
        "skills": {"Athletics": 3, "Awareness": 3, "Ballistic Skill": 4, "Stealth": 3, "Weapon Skill": 3},
        "abilities": [
            "Defender of Humanity: Add +Rank Icons to any successful attack against a Mob.",
            "Honour the Chapter (Primaris): You are subject to the orders of your chapter master, and must honour the beliefs and traditions of your chapter. Your Resolve increases by +1. As a Primaris, you ignore any impurities in your Chapter Gene-Seed and gain +3 Wounds.",
            "Space Marine Implants: You are immune to the Bleeding Condition. You gain +1 bonus dice to any test related to one of the 22 implants if the GM agrees it is appropriate.",
        ], "speed": 7, "size": "Average"},
    "Aeldari": {
        "xp": 10, "attributes": {"Agility": 3}, "skills": {},
        "abilities": ["Intense Emotion: +1 DN to all Resolve Tests. If you fail a Willpower-based test in a scene involving emotion, the GM gains +1 Ruin.", "Psychosensitive: You may choose to take the PSYKER Keyword."],
        "speed": 8, "size": "Average"},
    "Ork": {
        "xp": 20, "attributes": {"Strength": 3, "Toughness": 3}, "skills": {},
        "abilities": ["Orky: +1 bonus die to Intimidation Tests.", "Bigger is Better: You calculate Influence using Strength instead of Fellowship."],
        "speed": 6, "size": "Average"},
}

# Bonuses included by the Core Rulebook archetypes for the archetypes whose
# package data is encoded here. Other archetypes still set Species/Tier/XP and
# can be customised manually, matching the Advanced Character Creation workflow.
ARCHETYPE_PACKAGES = {
    "Sister Hospitaller": {"attributes":{"Willpower":3,"Intellect":3}, "skills":{"Medicae":1,"Scholar":1}},
    "Ministorum Priest": {"attributes":{"Willpower":3}, "skills":{"Scholar":1}},
    "Imperial Guard": {"attributes":{}, "skills":{"Ballistic Skill":2}},
    "Inquisitorial Acolyte": {"attributes":{}, "skills":{}},
    "Inquisitorial Sage": {"attributes":{"Intellect":3}, "skills":{"Scholar":2}},
    "Ganger": {"attributes":{}, "skills":{"Cunning":1}},
    "Corsair": {"attributes":{}, "skills":{"Pilot":1,"Ballistic Skill":1}},
    "Boy": {"attributes":{}, "skills":{"Weapon Skill":1}},
    "Sister of Battle": {"attributes": {"Strength":3,"Toughness":3,"Agility":3,"Willpower":3}, "skills":{"Ballistic Skill":2,"Scholar":1,"Weapon Skill":2}},
    "Sanctioned Psyker": {"attributes":{"Willpower":4}, "skills":{"Psychic Mastery":1}},
    "Skitarius": {"attributes":{"Toughness":3}, "skills":{"Ballistic Skill":2,"Tech":1}},
    "Death Cult Assassin": {"attributes":{"Agility":4}, "skills":{"Weapon Skill":2}},
    "Rogue Trader": {"attributes":{"Fellowship":3}, "skills":{"Awareness":1,"Cunning":1,"Insight":2,"Persuasion":2}},
    "Space Marine Scout": {"attributes":{"Strength":4,"Toughness":4,"Agility":4,"Initiative":4,"Willpower":3,"Intellect":3}, "skills":{"Athletics":3,"Awareness":3,"Ballistic Skill":3,"Stealth":3,"Weapon Skill":3}},
    "Ranger": {"attributes":{"Agility":3}, "skills":{"Ballistic Skill":2,"Stealth":1,"Survival":2}},
    "Kommando": {"attributes":{"Strength":3,"Toughness":3,"Agility":3}, "skills":{"Stealth":2,"Survival":1,"Weapon Skill":2}},
    "Tech-Priest": {"attributes":{"Intellect":3}, "skills":{"Scholar":1,"Tech":3}},
    "Crusader": {"attributes":{"Initiative":3,"Willpower":3}, "skills":{"Scholar":1,"Weapon Skill":3}},
    "Imperial Commissar": {"attributes":{"Strength":3,"Toughness":3,"Willpower":4}, "skills":{"Ballistic Skill":1,"Intimidation":2,"Leadership":2,"Weapon Skill":1}},
    "Tactical Space Marine": {"attributes":{"Strength":4,"Toughness":5,"Agility":5,"Initiative":5,"Willpower":3,"Intellect":3}, "skills":{"Athletics":3,"Awareness":3,"Ballistic Skill":5,"Leadership":1,"Scholar":1,"Stealth":3,"Survival":1,"Weapon Skill":4}},
    "Warlock": {"attributes":{}, "skills":{}},
    "Nob": {"attributes":{}, "skills":{}},
    "Inquisitor": {"attributes":{}, "skills":{}},
    "Primaris Intercessor": {"attributes":{}, "skills":{}},
}

VITAL_FIELDS = {"cur_wounds", "cur_shock", "cur_wrath"}

# Wrath & Glory 2e: Rank is based on total XP earned and may only increase.
RANKS = {
    1: {"name": "Initiate", "min_xp": 0, "bonus": 1},
    2: {"name": "Veteran", "min_xp": 40, "bonus": 2},
    3: {"name": "Champion", "min_xp": 80, "bonus": 3},
}
MAX_TIER = 4

# ============================================================
#  CHARACTER CREATION
# ============================================================
# Core Rulebook 2e archetypes. Archetype XP includes the Species package.
# This list is intentionally limited to the Core Rulebook; supplements can be added later.
ARCHETYPES = {
    "Sister Hospitaller": {"tier": 1, "species": "Human", "xp": 24, "faction": "Adepta Sororitas"},
    "Ministorum Priest": {"tier": 1, "species": "Human", "xp": 12, "faction": "Adeptus Ministorum"},
    "Imperial Guard": {"tier": 1, "species": "Human", "xp": 6, "faction": "Astra Militarum"},
    "Inquisitorial Acolyte": {"tier": 1, "species": "Human", "xp": 6, "faction": "Inquisition"},
    "Inquisitorial Sage": {"tier": 1, "species": "Human", "xp": 16, "faction": "Inquisition"},
    "Ganger": {"tier": 1, "species": "Human", "xp": 6, "faction": "Scum"},
    "Corsair": {"tier": 1, "species": "Aeldari", "xp": 10, "faction": "Aeldari"},
    "Boy": {"tier": 1, "species": "Ork", "xp": 20, "faction": "Orks"},
    "Sister of Battle": {"tier": 2, "species": "Human", "xp": 64, "faction": "Adepta Sororitas"},
    "Sanctioned Psyker": {"tier": 2, "species": "Human", "xp": 32, "faction": "Adeptus Astra Telepathica"},
    "Skitarius": {"tier": 2, "species": "Human", "xp": 28, "faction": "Adeptus Mechanicus"},
    "Death Cult Assassin": {"tier": 2, "species": "Human", "xp": 36, "faction": "Adeptus Ministorum"},
    "Tempestus Scion": {"tier": 2, "species": "Human", "xp": 30, "faction": "Astra Militarum"},
    "Rogue Trader": {"tier": 2, "species": "Human", "xp": 36, "faction": "Rogue Trader Dynasties"},
    "Scavvy": {"tier": 2, "species": "Human", "xp": 20, "faction": "Scum"},
    "Space Marine Scout": {"tier": 2, "species": "Adeptus Astartes", "xp": 170, "faction": "Adeptus Astartes"},
    "Ranger": {"tier": 2, "species": "Aeldari", "xp": 34, "faction": "Aeldari"},
    "Kommando": {"tier": 2, "species": "Ork", "xp": 54, "faction": "Orks"},
    "Tech-Priest": {"tier": 3, "species": "Human", "xp": 44, "faction": "Adeptus Mechanicus"},
    "Crusader": {"tier": 3, "species": "Human", "xp": 54, "faction": "Adeptus Ministorum"},
    "Imperial Commissar": {"tier": 3, "species": "Human", "xp": 76, "faction": "Astra Militarum"},
    "Desperado": {"tier": 3, "species": "Human", "xp": 52, "faction": "Scum"},
    "Tactical Space Marine": {"tier": 3, "species": "Adeptus Astartes", "xp": 277, "faction": "Adeptus Astartes"},
    "Warlock": {"tier": 3, "species": "Aeldari", "xp": 56, "faction": "Aeldari"},
    "Nob": {"tier": 3, "species": "Ork", "xp": 56, "faction": "Orks"},
    "Inquisitor": {"tier": 4, "species": "Human", "xp": 110, "faction": "Inquisition"},
    "Primaris Intercessor": {"tier": 4, "species": "Primaris Astartes", "xp": 228, "faction": "Adeptus Astartes"},
}

def rank_eligible_from_xp(xp):
    xp = int(xp or 0)
    if xp >= 80:
        return 3
    if xp >= 40:
        return 2
    return 1

def rank_label(rank):
    r = max(1, min(3, int(rank or 1)))
    return f"Rank {r} - {RANKS[r]['name']}"



def default_attributes():
    return {a: 1 for a in ATTRS}


def default_skills():
    return {s: 0 for s in SKILLS}


def is_astartes(sp):
    return "Astartes" in sp or "Space Marine" in sp


def species_package(sp):
    return SPECIES_PACKAGES.get(sp, {})


def species_base_attribute(sp, attr):
    return int(species_package(sp).get("attributes", {}).get(attr, 1))


def species_base_skill(sp, skill):
    return int(species_package(sp).get("skills", {}).get(skill, 0))


def apply_species_package(sp, attributes, skills):
    """Applies the minimum values granted by the species."""
    package = species_package(sp)

    for attr, value in package.get("attributes", {}).items():
        attributes[attr] = int(value)

    for skill, value in package.get("skills", {}).items():
        skills[skill] = int(value)

    return attributes, skills


def is_loyal_astartes(sp):
    return "Astartes" in sp and "Chaos" not in sp


def species_speed(sp):
    if "Aeldari" in sp or "Drukhari" in sp:
        return 8
    return 7 if is_astartes(sp) else 6


def rank_from_xp(xp, current_rank=1):
    """Returns the GM-controlled Rank and whether Tier Ascension is available."""
    xp = int(xp or 0)
    rank = max(1, min(3, int(current_rank or 1)))
    return rank, xp >= 100


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


def creation_base_attribute(ch, species, attr):
    if ch.get("creation_mode") == "archetype" and ch.get("archetype") in ARCHETYPE_PACKAGES:
        ap = ARCHETYPE_PACKAGES[ch["archetype"]]
        if attr in ap.get("attributes", {}):
            return int(ap["attributes"][attr])
    return species_base_attribute(species, attr)


def creation_base_skill(ch, species, skill):
    if ch.get("creation_mode") == "archetype" and ch.get("archetype") in ARCHETYPE_PACKAGES:
        ap = ARCHETYPE_PACKAGES[ch["archetype"]]
        if skill in ap.get("skills", {}):
            return int(ap["skills"][skill])
    return species_base_skill(species, skill)


def xp_spent(ch):
    species = ch.get("species", "")
    package = species_package(species)

    # The species package is paid once.
    # Attributes and skills included in the package are not charged again.
    if ch.get("creation_mode") == "archetype" and ch.get("archetype") in ARCHETYPES:
        total = int(ARCHETYPES[ch["archetype"]].get("xp", 0))
    else:
        total = int(package.get("xp", 0))

    for a in ATTRS:
        value = int(ch["attributes"].get(a, 1))
        base = creation_base_attribute(ch, species, a)

        if value > base:
            total += ATTR_COST.get(value, 0) - ATTR_COST.get(base, 0)

    for s in SKILLS:
        value = int(ch["skills"].get(s, 0))
        base = creation_base_skill(ch, species, s)

        if value > base:
            total += SKILL_COST.get(value, 0) - SKILL_COST.get(base, 0)

    for t in ch.get("talents", []):
        try:
            total += int(t.get("cost", 0))
        except Exception:
            pass

    total += int(ch.get("other_xp", 0))
    return total


def starting_xp(tier, advanced=False):
    """Wrath & Glory 2e starting XP. Advanced Creation adds Tier x10 bonus XP."""
    base = int(tier) * 100
    return base + (int(tier) * 10 if advanced else 0)


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
#  DATABASE (with automatic schema migration)
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
        user_id INTEGER, kind TEXT DEFAULT 'player', name TEXT, chapter TEXT, species TEXT, archetype TEXT, creation_mode TEXT DEFAULT 'archetype', archetype_history TEXT DEFAULT '[]',
        tier INTEGER DEFAULT 2, starting_tier INTEGER DEFAULT 2, rank INTEGER DEFAULT 1, earned_xp INTEGER DEFAULT 0, other_xp INTEGER DEFAULT 0,
        attributes TEXT, skills TEXT, talents TEXT, wargear TEXT, armour INTEGER DEFAULT 0,
        cur_wounds INTEGER DEFAULT 0, cur_shock INTEGER DEFAULT 0, cur_wrath INTEGER DEFAULT 0,
        notes TEXT, folder_id INTEGER, portrait BLOB, comms_on INTEGER DEFAULT 1, comms_changed_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS campaign(id INTEGER PRIMARY KEY CHECK (id=1),
        name TEXT, tier INTEGER DEFAULT 2, ruin INTEGER DEFAULT 0, session_no INTEGER DEFAULT 1)""")
    c.execute("""CREATE TABLE IF NOT EXISTS log(id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, author TEXT, text TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS session_record(id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_no INTEGER, title TEXT, notes TEXT, base_xp INTEGER DEFAULT 0, npc_ids TEXT DEFAULT '[]',
        created_at TEXT, closed_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS session_award(id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL, character_id INTEGER NOT NULL, base_xp INTEGER DEFAULT 0, bonus_xp INTEGER DEFAULT 0,
        total_xp INTEGER DEFAULT 0, UNIQUE(session_id, character_id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS combatant(character_id INTEGER PRIMARY KEY, added_at TEXT, initiative_order INTEGER DEFAULT 9999, initiative_modifier INTEGER DEFAULT 0)""")
    _ensure_columns(conn, "combatant", {"added_at": "TEXT", "initiative_order": "INTEGER DEFAULT 9999", "initiative_modifier": "INTEGER DEFAULT 0"})
    c.execute("""CREATE TABLE IF NOT EXISTS combat_encounter(
        id INTEGER PRIMARY KEY AUTOINCREMENT, session_no INTEGER, title TEXT, notes TEXT,
        started_at TEXT, ended_at TEXT, status TEXT DEFAULT 'active', round_no INTEGER DEFAULT 1,
        current_turn INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS combat_participant(
        id INTEGER PRIMARY KEY AUTOINCREMENT, encounter_id INTEGER NOT NULL, character_id INTEGER NOT NULL,
        side TEXT DEFAULT 'npc', initiative_mod INTEGER DEFAULT 0, initiative_roll INTEGER DEFAULT 0,
        initiative_icons INTEGER DEFAULT 0, initiative_total INTEGER DEFAULT 0, turn_order INTEGER DEFAULT 0,
        ambushed INTEGER DEFAULT 0, added_at TEXT, UNIQUE(encounter_id, character_id))""")
    conn.commit()
    # migration: ensure columns exist in databases created by older versions
    _ensure_columns(conn, "campaign", {"name": "TEXT", "tier": "INTEGER DEFAULT 2",
                                       "ruin": "INTEGER DEFAULT 0", "session_no": "INTEGER DEFAULT 1"})
    _ensure_columns(conn, "characters", {
        "user_id": "INTEGER", "kind": "TEXT DEFAULT 'player'", "name": "TEXT", "chapter": "TEXT",
        "species": "TEXT", "archetype": "TEXT", "creation_mode": "TEXT DEFAULT 'archetype'", "archetype_history": "TEXT DEFAULT '[]'", "tier": "INTEGER DEFAULT 2", "starting_tier": "INTEGER DEFAULT 2", "rank": "INTEGER DEFAULT 1", "earned_xp": "INTEGER DEFAULT 0",
        "other_xp": "INTEGER DEFAULT 0", "attributes": "TEXT", "skills": "TEXT", "talents": "TEXT",
        "wargear": "TEXT", "armour": "INTEGER DEFAULT 0", "cur_wounds": "INTEGER DEFAULT 0",
        "cur_shock": "INTEGER DEFAULT 0", "cur_wrath": "INTEGER DEFAULT 0", "notes": "TEXT",
        "folder_id": "INTEGER", "portrait": "BLOB", "comms_on": "INTEGER DEFAULT 1",
        "comms_changed_at": "TEXT"})
    _ensure_columns(conn, "folders", {"name": "TEXT"})
    # Existing characters keep their current Tier as their recorded starting Tier.
    conn.execute("UPDATE characters SET starting_tier = COALESCE(starting_tier, tier, 2) WHERE starting_tier IS NULL")
    # Existing characters inherit the Rank supported by their already-earned XP.
    conn.execute("""UPDATE characters SET rank = CASE
        WHEN earned_xp >= 80 THEN 3
        WHEN earned_xp >= 40 THEN 2
        ELSE 1 END
        WHERE rank IS NULL OR rank < 1""")
    conn.commit()
    if c.execute("SELECT COUNT(*) FROM campaign").fetchone()[0] == 0:
        c.execute("INSERT INTO campaign(id,name,tier,ruin,session_no) VALUES(1,?,2,0,1)", ("Gilead Crusade",))
    if c.execute("SELECT COUNT(*) FROM users WHERE role='gm'").fetchone()[0] == 0:
        salt = secrets.token_hex(16)
        c.execute("INSERT INTO users(username,pw_hash,salt,role,created_at) VALUES(?,?,?,?,?)",
                  ("magister", hash_pw("AveImperator1", salt), salt, "gm", now_iso()))
    # Migrate the previous simple combat roster into the new encounter log once.
    legacy = conn.execute("SELECT character_id FROM combatant").fetchall()
    if legacy and not conn.execute("SELECT 1 FROM combat_encounter WHERE status='active' LIMIT 1").fetchone():
        camp = conn.execute("SELECT session_no FROM campaign WHERE id=1").fetchone()
        session_no = int(camp[0] if camp else 1)
        cur = conn.execute("INSERT INTO combat_encounter(session_no,title,notes,started_at,status,round_no,current_turn) VALUES(?,?,?,?, 'active',1,0)",
                           (session_no, f"Combat - Session {session_no}", "Migrated from previous combat roster", now_iso()))
        eid = cur.lastrowid
        for r in legacy:
            ch = conn.execute("SELECT kind FROM characters WHERE id=?", (r[0],)).fetchone()
            if ch:
                conn.execute("INSERT OR IGNORE INTO combat_participant(encounter_id,character_id,side,added_at) VALUES(?,?,?,?)",
                             (eid, r[0], ch[0], now_iso()))
        conn.execute("DELETE FROM combatant")
    conn.commit(); conn.close()


def create_player(username, pw, creation_mode="archetype", tier=2, rank=1, species="Human", archetype=""):
    conn = get_conn(); c = conn.cursor()
    try:
        salt = secrets.token_hex(16)
        c.execute("INSERT INTO users(username,pw_hash,salt,role,created_at) VALUES(?,?,?,?,?)",
                  (username, hash_pw(pw, salt), salt, "player", now_iso()))
        uid = c.lastrowid
        tier = max(1, min(MAX_TIER, int(tier)))
        rank = max(1, min(3, int(rank)))
        species = species if species in PLAYER_SPECIES else "Human"
        archetype = archetype if archetype in ARCHETYPES else ""

        attrs = default_attributes()
        skills = default_skills()
        sp = SPECIES_PACKAGES.get(species, {})
        for attr, value in sp.get("attributes", {}).items():
            attrs[attr] = max(int(attrs.get(attr, 1)), int(value))
        for skill, value in sp.get("skills", {}).items():
            skills[skill] = max(int(skills.get(skill, 0)), int(value))
        ap = ARCHETYPE_PACKAGES.get(archetype, {})
        for attr, value in ap.get("attributes", {}).items():
            attrs[attr] = max(int(attrs.get(attr, 1)), int(value))
        for skill, value in ap.get("skills", {}).items():
            skills[skill] = max(int(skills.get(skill, 0)), int(value))

        c.execute("""INSERT INTO characters(user_id,kind,name,chapter,species,archetype,creation_mode,tier,starting_tier,rank,earned_xp,other_xp,
                     attributes,skills,talents,wargear,armour,cur_wounds,cur_shock,cur_wrath,notes,
                     comms_on,comms_changed_at)
                     VALUES(?, 'player', ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (uid, username, "", species, archetype, creation_mode, tier, tier, rank, 0, 0, json.dumps(attrs),
                   json.dumps(skills), json.dumps([]), "", 0, 0, 0, 0, "", 1, now_iso()))
        conn.commit(); return True, "Player recruited."
    except sqlite3.IntegrityError:
        return False, "That designation already exists."
    finally:
        conn.close()


def create_npc(name, species, tier, creation_mode="archetype", rank=1):
    conn = get_conn()
    tier = max(1, min(MAX_TIER, int(tier)))
    rank = max(1, min(3, int(rank)))
    default_arch = "" if creation_mode == "advanced" else default_archetype_for_species(species, tier)
    conn.execute("""INSERT INTO characters(user_id,kind,name,chapter,species,archetype,creation_mode,tier,starting_tier,rank,earned_xp,other_xp,
                    attributes,skills,talents,wargear,armour,cur_wounds,cur_shock,cur_wrath,notes,
                    comms_on,comms_changed_at)
                    VALUES(NULL,'npc',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (name or "NPC", "", species, default_arch, creation_mode, tier, tier, rank, 0, 0, json.dumps(default_attributes()),
                  json.dumps(default_skills()), json.dumps([]), "", 0, 0, 0, 0, "", 1, now_iso()))
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


def normalize_talents(raw):
    """Converts legacy and current talents to name + effect + XP."""
    if isinstance(raw, list):
        parsed = raw
    else:
        text = raw or "[]"
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = []
            if str(text).strip():
                parsed = [ln for ln in str(text).splitlines() if ln.strip()]

    out = []
    for t in parsed:
        if isinstance(t, dict):
            name = str(t.get("name", "")).strip()
            effect = str(t.get("effect", "")).strip()
            try:
                cost = int(t.get("cost", 20) or 0)
            except Exception:
                cost = 20
        else:
            name = str(t).strip()
            effect = ""
            cost = 20
        if name:
            out.append({"name": name, "effect": effect, "cost": cost})
    return out


def normalize_wargear(raw):
    """Converts legacy wargear to name + effect."""
    if isinstance(raw, list):
        parsed = raw
    else:
        text = raw or ""
        try:
            parsed = json.loads(text) if text.strip().startswith("[") else None
        except Exception:
            parsed = None
        if parsed is None:
            parsed = [{"name": ln.strip(), "effect": ""}
                      for ln in text.splitlines() if ln.strip()]

    out = []
    for w in parsed:
        if isinstance(w, dict):
            name = str(w.get("name", "")).strip()
            effect = str(w.get("effect", "")).strip()
        else:
            name = str(w).strip()
            effect = ""
        if name:
            out.append({"name": name, "effect": effect})
    return out


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
    ch["talents"] = normalize_talents(ch.get("talents"))
    ch["wargear"] = normalize_wargear(ch.get("wargear"))
    for a in ATTRS:
        ch["attributes"].setdefault(a, 1)
    for s in SKILLS:
        ch["skills"].setdefault(s, 0)
    for k, dv in {"tier": 2, "starting_tier": 2, "rank": 1, "earned_xp": 0, "other_xp": 0, "armour": 0, "cur_wounds": 0,
                  "cur_shock": 0, "cur_wrath": 0, "comms_on": 1, "kind": "player",
                  "name": "", "chapter": "", "species": "", "archetype": "", "creation_mode": "archetype", "archetype_history": "[]", "wargear": "", "notes": ""}.items():
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


def save_build(cid, name, chapter, species, tier, attributes, skills, talents, wargear, armour, notes, other_xp, archetype="", creation_mode="advanced"):
    conn = get_conn()
    conn.execute("""UPDATE characters SET name=?,chapter=?,species=?,archetype=?,creation_mode=?,tier=?,attributes=?,skills=?,
                    talents=?,wargear=?,armour=?,notes=?,other_xp=? WHERE id=?""",
                 (name, chapter, species, archetype, creation_mode, int(tier), json.dumps(attributes), json.dumps(skills),
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

def set_rank(cid, rank, force=False):
    rank = max(1, min(3, int(rank)))
    conn = get_conn()
    row = conn.execute("SELECT earned_xp, rank FROM characters WHERE id=?", (cid,)).fetchone()
    if row is None:
        conn.close(); return False
    earned = int(row["earned_xp"] or 0)
    eligible = rank_eligible_from_xp(earned)
    if rank < int(row["rank"] or 1) or (not force and rank > eligible):
        conn.close(); return False
    conn.execute("UPDATE characters SET rank=? WHERE id=?", (rank, cid))
    conn.commit(); conn.close(); return True

def get_archetype_history(ch):
    raw = ch.get("archetype_history") or "[]"
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return data if isinstance(data, list) else []
    except Exception:
        return []


def ascend_archetype(cid, new_archetype):
    """Perform Core Rulebook Archetype Ascension at the next Tier."""
    ch = load_character(cid)
    if not ch or ch.get("creation_mode") != "archetype":
        return False, "Archetype Ascension requires an Archetype character."
    if int(ch.get("rank", 1)) < 3 or int(ch.get("earned_xp", 0)) < 80:
        return False, "Archetype Ascension requires Rank 3 (80+ earned XP)."
    data = ARCHETYPES.get(new_archetype)
    if not data:
        return False, "Invalid Archetype."
    if data.get("tier") != int(ch.get("tier", 1)) + 1:
        return False, "The new Archetype must be from the next Tier."
    # The new Archetype must belong to the same Faction.
    current = ARCHETYPES.get(ch.get("archetype"), {})
    if current.get("faction") and data.get("faction") != current.get("faction"):
        return False, "The new Archetype must belong to the same Faction."
    history = get_archetype_history(ch)
    if ch.get("archetype"):
        history.append({"archetype": ch["archetype"], "tier": int(ch["tier"]), "retained": True})
    conn = get_conn()
    conn.execute("UPDATE characters SET archetype=?, tier=?, archetype_history=? WHERE id=?",
                 (new_archetype, int(data["tier"]), json.dumps(history), cid))
    conn.commit(); conn.close()
    return True, f"Character ascended to {new_archetype}. Attribute and Skill bonuses from the new Archetype were not granted."


def set_tier(cid, tier, force=False):
    tier = max(1, min(MAX_TIER, int(tier)))
    conn = get_conn()
    row = conn.execute("SELECT tier, starting_tier, earned_xp FROM characters WHERE id=?", (cid,)).fetchone()
    if row is None:
        conn.close(); return False
    current = int(row["tier"] or 1)
    starting = int(row["starting_tier"] or current or 1)
    earned = int(row["earned_xp"] or 0)
    max_allowed = min(MAX_TIER, starting + earned // 100)
    if tier < current or (not force and tier > max_allowed):
        conn.close(); return False
    conn.execute("UPDATE characters SET tier=? WHERE id=?", (tier, cid))
    conn.commit(); conn.close(); return True


def award_xp(cid, amt):
    conn = get_conn(); conn.execute("UPDATE characters SET earned_xp=MAX(0,earned_xp+?) WHERE id=?", (int(amt), cid))
    conn.commit(); conn.close()


def set_comms(cid, on):
    conn = get_conn()
    conn.execute("UPDATE characters SET comms_on=?, comms_changed_at=? WHERE id=?", (int(on), now_iso(), cid))
    conn.commit(); conn.close()


def set_comms_for_folder(fid, on):
    """Toggle Vox for all characters in a folder."""
    if fid is None:
        return
    conn = get_conn()
    conn.execute("UPDATE characters SET comms_on=?, comms_changed_at=? WHERE folder_id=?",
                 (int(on), now_iso(), int(fid)))
    conn.commit(); conn.close()


def set_folder_for_many(cids, fid):
    if not cids:
        return
    conn = get_conn()
    conn.executemany("UPDATE characters SET folder_id=? WHERE id=?",
                     [(fid if fid else None, int(cid)) for cid in cids])
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
    c.setdefault("name", "The Crusade"); c.setdefault("tier", 2); c.setdefault("ruin", 0); c.setdefault("session_no", 1)
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


def create_session_record(session_no, title, notes, base_xp, npc_ids):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO session_record(session_no,title,notes,base_xp,npc_ids,created_at) VALUES(?,?,?,?,?,?)",
        (int(session_no), title.strip(), notes.strip(), max(0, int(base_xp)), json.dumps([int(x) for x in npc_ids]), now_iso()),
    )
    sid = cur.lastrowid
    conn.commit(); conn.close()
    return sid


def award_session_xp(session_id, awards, close_session=True, advance_campaign=False):
    conn = get_conn()
    for cid, base_xp, bonus_xp in awards:
        total = max(0, int(base_xp)) + max(0, int(bonus_xp))
        conn.execute(
            "INSERT OR REPLACE INTO session_award(session_id,character_id,base_xp,bonus_xp,total_xp) VALUES(?,?,?,?,?)",
            (int(session_id), int(cid), max(0, int(base_xp)), max(0, int(bonus_xp)), total),
        )
        conn.execute("UPDATE characters SET earned_xp=MAX(0,earned_xp+?) WHERE id=?", (total, int(cid)))
    if close_session:
        conn.execute("UPDATE session_record SET closed_at=? WHERE id=?", (now_iso(), int(session_id)))
    if advance_campaign:
        conn.execute("UPDATE campaign SET session_no=session_no+1 WHERE id=1")
    conn.commit(); conn.close()


def get_session_records(limit=30):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM session_record ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
    conn.close(); return rows


def get_session_awards(session_id):
    conn = get_conn()
    rows = conn.execute("""SELECT sa.*, c.name, c.kind FROM session_award sa
                          JOIN characters c ON c.id=sa.character_id
                          WHERE sa.session_id=? ORDER BY c.name""", (int(session_id),)).fetchall()
    conn.close(); return rows


def _current_combat_id(create=False):
    conn = get_conn()
    row = conn.execute("SELECT id FROM combat_encounter WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()
    if row:
        cid = int(row["id"])
        conn.close(); return cid
    if not create:
        conn.close(); return None
    camp = conn.execute("SELECT session_no FROM campaign WHERE id=1").fetchone()
    session_no = int(camp[0] if camp else 1)
    cur = conn.execute("INSERT INTO combat_encounter(session_no,title,notes,started_at,status,round_no,current_turn) VALUES(?,?,?,?, 'active',1,0)",
                       (session_no, f"Combat - Session {session_no}", "", now_iso()))
    cid = cur.lastrowid
    conn.commit(); conn.close(); return int(cid)


def start_combat(title="", notes=""):
    conn = get_conn()
    active = conn.execute("SELECT id FROM combat_encounter WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()
    if active:
        conn.close(); return int(active[0])
    camp = conn.execute("SELECT session_no FROM campaign WHERE id=1").fetchone()
    session_no = int(camp[0] if camp else 1)
    cur = conn.execute("INSERT INTO combat_encounter(session_no,title,notes,started_at,status,round_no,current_turn) VALUES(?,?,?,?, 'active',1,0)",
                       (session_no, title.strip() or f"Combat - Session {session_no}", notes.strip(), now_iso()))
    cid = cur.lastrowid
    conn.commit(); conn.close(); return int(cid)


def add_combat_participant(character_id, initiative_mod=0, ambushed=False):
    eid = _current_combat_id(create=True)
    conn = get_conn()
    ch = conn.execute("SELECT id,kind FROM characters WHERE id=?", (int(character_id),)).fetchone()
    if not ch:
        conn.close(); return False
    conn.execute("""INSERT OR IGNORE INTO combat_participant(encounter_id,character_id,side,initiative_mod,ambushed,added_at)
                    VALUES(?,?,?,?,?,?)""", (eid, int(character_id), ch["kind"], int(initiative_mod), 1 if ambushed else 0, now_iso()))
    conn.commit(); conn.close(); return True


def remove_combat_participant(character_id):
    eid = _current_combat_id(False)
    if not eid: return
    conn = get_conn(); conn.execute("DELETE FROM combat_participant WHERE encounter_id=? AND character_id=?", (eid, int(character_id))); conn.commit(); conn.close()


def get_combatants():
    conn = get_conn()
    rows = conn.execute("""SELECT c.*, cb.initiative_order, cb.initiative_modifier
                          FROM characters c JOIN combatant cb ON cb.character_id=c.id
                          ORDER BY cb.initiative_order ASC, c.name ASC, c.id ASC""").fetchall()
    conn.close(); return [_decode(r) for r in rows]


def set_combatant(cid, active=True):
    conn = get_conn()
    if active:
        row = conn.execute("SELECT COALESCE(MAX(initiative_order), 0) + 1 FROM combatant").fetchone()
        next_order = int(row[0] or 1)
        conn.execute("INSERT OR REPLACE INTO combatant(character_id,added_at,initiative_order,initiative_modifier) VALUES(?,?,?,0)",
                     (int(cid), now_iso(), next_order))
    else:
        conn.execute("DELETE FROM combatant WHERE character_id=?", (int(cid),))
    conn.commit(); conn.close()


def set_combat_modifier(cid, modifier):
    conn = get_conn()
    conn.execute("UPDATE combatant SET initiative_modifier=? WHERE character_id=?", (int(modifier), int(cid)))
    conn.commit(); conn.close()


def move_combatant(cid, direction):
    current = get_combatants()
    ids = [int(c["id"]) for c in current]
    if int(cid) not in ids:
        return
    i = ids.index(int(cid)); j = i + int(direction)
    if j < 0 or j >= len(ids):
        return
    ids[i], ids[j] = ids[j], ids[i]
    conn = get_conn()
    for order, char_id in enumerate(ids, 1):
        conn.execute("UPDATE combatant SET initiative_order=? WHERE character_id=?", (order, char_id))
    conn.commit(); conn.close()


def clear_combat():
    conn = get_conn(); conn.execute("DELETE FROM combatant"); conn.commit(); conn.close()


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
    .combat-header{ background:linear-gradient(135deg,#2a1b0e,#100a06); border:2px solid var(--gold); border-radius:6px; padding:12px 16px; margin:10px 0 12px; text-align:center; }
    .combat-header .title{ font-family:'Cinzel',serif; font-size:1.25rem; font-weight:900; color:var(--gold2); letter-spacing:.14em; text-transform:uppercase; }
    .combat-header .sub{ font-size:.8rem; opacity:.75; letter-spacing:.08em; text-transform:uppercase; margin-top:3px; }
    .combat-card{ background:linear-gradient(110deg,#21170c,#120c07); border:1px solid #5a4421; border-radius:6px; padding:9px 12px; margin:0 0 7px; box-shadow:0 2px 5px #0008; }
    .combat-card.player{ border-left:6px solid var(--gold); }
    .combat-card.npc{ border-left:6px solid var(--npc); }
    .combat-pos{ font-family:'Cinzel',serif; font-size:1.55rem; font-weight:900; color:var(--gold2); text-align:center; line-height:1; }
    .combat-name{ font-family:'Cinzel',serif; font-size:1.05rem; font-weight:700; color:var(--bone); letter-spacing:.04em; }
    .combat-kind{ display:inline-block; font-family:'Cinzel',serif; font-size:.62rem; font-weight:700; letter-spacing:.08em; padding:2px 6px; border-radius:2px; margin-left:6px; vertical-align:middle; }
    .combat-kind.player{ color:#171209; background:var(--gold2); }
    .combat-kind.npc{ color:#fff; background:#754b9c; }
    .combat-meta{ font-size:.72rem; opacity:.72; text-transform:uppercase; letter-spacing:.05em; margin-top:2px; }
    .combat-arrow{ text-align:center; color:var(--gold); font-size:1rem; line-height:.8; margin:-2px 0 3px; opacity:.8; }
    .combat-mod{ font-family:'Cinzel',serif; font-size:.68rem; color:var(--gold2); text-transform:uppercase; letter-spacing:.04em; }
    .combat-legend{ display:flex; gap:14px; justify-content:center; font-size:.7rem; text-transform:uppercase; letter-spacing:.06em; opacity:.8; margin:5px 0 10px; }
    .combat-legend .p{ color:var(--gold2); } .combat-legend .n{ color:var(--npc); }
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


def archetype_options(tier=None, species=None):
    """Return every Core Rulebook Archetype. Tier, Rank and Species do not filter the list."""
    return list(ARCHETYPES.keys())


def default_archetype_for_species(species, tier=None):
    preferred = {
        "Human": {1: "Imperial Guard", 2: "Sister of Battle", 3: "Tech-Priest", 4: "Inquisitor"},
        "Adeptus Astartes": {2: "Space Marine Scout", 3: "Tactical Space Marine"},
        "Primaris Astartes": {4: "Primaris Intercessor"},
        "Aeldari": {1: "Corsair", 2: "Ranger", 3: "Warlock"},
        "Ork": {1: "Boy", 2: "Kommando", 3: "Nob"},
    }
    if tier is not None:
        return preferred.get(species, {}).get(int(tier), "")
    return next(iter(preferred.get(species, {}).values()), "")


def strip_archetype_package(cid, archetype, species):
    """Remove only automatic Archetype bonuses; preserve values bought manually."""
    if archetype not in ARCHETYPE_PACKAGES:
        return
    ap = ARCHETYPE_PACKAGES[archetype]
    for attr, value in ap.get("attributes", {}).items():
        key = _k(cid, "a", attr)
        current = int(st.session_state.get(key, value))
        if current <= int(value):
            st.session_state[key] = species_base_attribute(species, attr)
    for skill, value in ap.get("skills", {}).items():
        key = _k(cid, "s", skill)
        current = int(st.session_state.get(key, value))
        if current <= int(value):
            st.session_state[key] = species_base_skill(species, skill)


# ============================================================
#  CALLBACKS
# ============================================================
def cb_open(cid):
    st.session_state.editing = cid


def cb_close():
    st.session_state.editing = None


def cb_archetype_change(cid):
    ak = _k(cid, "sel", "arch")
    archetype = st.session_state.get(ak, "")
    data = ARCHETYPES.get(archetype)
    if not data:
        return
    previous = st.session_state.get(_k(cid, "meta", "previous_archetype"))
    species_before = st.session_state.get(_k(cid, "sel", "sp"), data["species"])
    if previous and previous != archetype:
        strip_archetype_package(cid, previous, species_before)
    # Species and Archetype are independent choices.
    # The Magister chooses both; selecting an Archetype must never change Species.
    selected_species = st.session_state.get(_k(cid, "sel", "sp"), species_before)
    package = species_package(selected_species)
    ap = ARCHETYPE_PACKAGES.get(archetype, {})
    for attr, value in package.get("attributes", {}).items():
        st.session_state[_k(cid, "a", attr)] = max(int(st.session_state.get(_k(cid, "a", attr), 1)), int(value))
    for skill, value in package.get("skills", {}).items():
        st.session_state[_k(cid, "s", skill)] = max(int(st.session_state.get(_k(cid, "s", skill), 0)), int(value))
    for attr, value in ap.get("attributes", {}).items():
        st.session_state[_k(cid, "a", attr)] = max(int(st.session_state.get(_k(cid, "a", attr), 1)), int(value))
    for skill, value in ap.get("skills", {}).items():
        st.session_state[_k(cid, "s", skill)] = max(int(st.session_state.get(_k(cid, "s", skill), 0)), int(value))
    st.session_state[_k(cid, "meta", "previous_archetype")] = archetype


def cb_species_change(cid):
    """Apply the selected Species package without wiping higher manual values."""
    ch = load_character(cid) or {}
    st.session_state.setdefault(_k(cid, "sel", "mode"), "archetype" if ch.get("creation_mode") == "archetype" else "advanced")
    ark = _k(cid, "sel", "arch")
    if ark not in st.session_state:
        st.session_state[ark] = ch.get("archetype") if ch.get("archetype") in ARCHETYPES else default_archetype_for_species(ch.get("species")) or list(ARCHETYPES.keys())[0]
    st.session_state.setdefault(_k(cid, "meta", "previous_archetype"), st.session_state.get(ark, ""))
    spk = _k(cid, "sel", "sp")
    species = st.session_state.get(spk, "")

    if species not in SPECIES_PACKAGES:
        return

    for attr, value in SPECIES_PACKAGES[species].get("attributes", {}).items():
        st.session_state[_k(cid, "a", attr)] = int(value)

    for skill, value in SPECIES_PACKAGES[species].get("skills", {}).items():
        st.session_state[_k(cid, "s", skill)] = int(value)


# ============================================================
#  COMPONENTES AO VIVO
# ============================================================
@st.fragment(run_every=REFRESH_S)
def live_vitals(cid):
    ch = load_character(cid)
    if not ch:
        return
    d = derived_traits(ch)
    rank, asc = rank_from_xp(ch["earned_xp"], ch.get("rank", 1))
    trio = [("cur_wounds", "Wounds", d["Max Wounds"]),
            ("cur_shock", "Shock", d["Max Shock"]),
            ("cur_wrath", "Wrath", d["Max Wrath"])]
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
        st.warning("100+ Earned XP - this character may ascend to the next Tier.")


@st.fragment(run_every=REFRESH_S)
def vox_live(listener_cid=None):
    """Show only Vox signals reaching the receiving character.

    Characters share the Vox network only when they belong to the same folder.
    Characters without a folder are isolated and receive no signals from others.
    In the Magister panel, without listener_cid, the entire network is monitored.
    """
    chars = list_characters()

    listener_folder = None
    restrict_folder = listener_cid is not None
    if restrict_folder:
        listener = load_character(listener_cid)
        if not listener or listener.get("folder_id") is None:
            st.markdown(
                "<div class='wg' style='opacity:.6'>No Vox network - no communications available.</div>",
                unsafe_allow_html=True,
            )
            return
        listener_folder = listener.get("folder_id")

    shown = []
    for ch in chars:
        if restrict_folder:
            # Vox only passes between characters in the same folder.
            if ch.get("folder_id") != listener_folder:
                continue
            # The character itself is not a network participant.
            if ch.get("id") == listener_cid:
                continue

        if ch["comms_on"]:
            shown.append((ch["name"] or "?", ch["kind"], True))
        elif secs_since(ch["comms_changed_at"]) < COMMS_FADE_S:
            shown.append((ch["name"] or "?", ch["kind"], False))

    if not shown:
        st.markdown("<div class='wg' style='opacity:.6'>No signal on the Vox network.</div>", unsafe_allow_html=True)
        return

    html = ""
    for name, kind, on in shown:
        ncls = "npc" if kind == "npc" else ""
        state = "<span class='vlive'>✠ ACTIVE</span>" if on else "<span class='vdead'>✠ CUT</span>"
        html += f"<div class='wg'><span class='{ncls}'>{name}</span> <span style='float:right'>{state}</span></div>"
    st.markdown(html, unsafe_allow_html=True)


# ============================================================
#  BATTLE VIEW (player themed)
# ============================================================
def battle_view(cid):
    ch = load_character(cid)
    if not ch:
        st.error("Character sheet not found.")
        return
    d = derived_traits(ch)
    rank, _ = rank_from_xp(ch["earned_xp"])
    ncls = "npc" if ch["kind"] == "npc" else ""
    st.markdown(f"<div class='hero'><div class='nm {ncls}'>{ch['name'] or 'Character'}</div>"
                f"<div class='meta'>{ch['chapter'] or ''} &nbsp;·&nbsp; {species_label(ch['species'])} &nbsp;·&nbsp; "
                f"Tier {ch['tier']} &nbsp;·&nbsp; Rank {rank}</div></div>", unsafe_allow_html=True)

    st.markdown("<div class='sectionttl'>Vitals</div>", unsafe_allow_html=True)
    live_vitals(cid)

    left, right = st.columns([1.5, 1])
    with left:
        st.markdown("<div class='sectionttl'>Derived Traits</div>", unsafe_allow_html=True)
        order = [("Defence", "Defence"), ("Resilience", "Resilience"), ("Soak", "Soak"),
                 ("Determination", "Determination"), ("Resolve", "Resolve"), ("Conviction", "Conviction"),
                 ("Passive Awareness", "Passive Awareness"), ("Influence", "Influence"), ("Speed", "Speed")]
        cards = "".join(f"<div class='statcard'><div class='l'>{pt}</div><div class='v'>{d[en]}</div></div>"
                        for en, pt in order)
        st.markdown(f"<div class='grid'>{cards}</div>", unsafe_allow_html=True)

        st.markdown("<div class='sectionttl'>Skills &nbsp;<small style='opacity:.6;letter-spacing:0'>Total = Skill + Attribute</small></div>", unsafe_allow_html=True)
        rows = "<div class='skhead'><span>Skill</span><span>Rank</span><span>Attr</span><span>Total</span></div>"
        for s in SKILLS:
            r = ch["skills"][s]; av = ch["attributes"][SKILLS[s]]
            rows += (f"<div class='skrow'><span class='n'>{s}</span><span class='c'>{r}</span>"
                     f"<span class='c'>+{av}</span><span class='t'>{r+av}</span></div>")
        st.markdown(rows, unsafe_allow_html=True)

    with right:
        if ch.get("archetype") and ch.get("creation_mode") == "archetype":
            st.markdown("<div class='sectionttl'>Archetype</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='tal'><span class='tn'>{html.escape(ch['archetype'])}</span></div>", unsafe_allow_html=True)
            ap = ARCHETYPE_PACKAGES.get(ch["archetype"], {})
            if ap.get("skills"):
                st.markdown("<div class='sectionttl'>Archetype Skill Bonuses</div>", unsafe_allow_html=True)
                for sk, rating in ap["skills"].items():
                    st.markdown(f"<div class='tal'><span class='tn'>{html.escape(sk)}</span><span class='tc'>+{int(rating)}</span></div>", unsafe_allow_html=True)

        package = species_package(ch["species"])
        if package.get("abilities"):
            st.markdown("<div class='sectionttl'>Species Abilities</div>", unsafe_allow_html=True)
            for ability in package["abilities"]:
                st.markdown(
                    f"<div class='tal'><span class='tn'>{ability}</span></div>",
                    unsafe_allow_html=True,
                )

        if ch.get("archetype") and ch.get("creation_mode") == "archetype":
            ap = ARCHETYPE_PACKAGES.get(ch["archetype"], {})
            askills = ap.get("skills", {})
            if askills:
                st.markdown("<div class='sectionttl'>Archetype Skills</div>", unsafe_allow_html=True)
                for sk, rating in askills.items():
                    st.markdown(f"<div class='tal'><span class='tn'>{html.escape(sk)}</span><span class='tc'>Rating {int(rating)}</span></div>", unsafe_allow_html=True)

        st.markdown("<div class='sectionttl'>Talents</div>", unsafe_allow_html=True)
        if ch["talents"]:
            for t in ch["talents"]:
                name = html.escape(str(t.get("name", "")))
                effect = html.escape(str(t.get("effect", "")))
                cost = f"<span class='tc'>{int(t.get('cost') or 0)} XP</span>" if t.get("cost") else ""
                effect_html = f"<div style='margin-top:5px;opacity:.75;line-height:1.35'>{effect}</div>" if effect else ""
                st.markdown(f"<div class='tal'><span class='tn'>{name}</span>{cost}{effect_html}</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='tal' style='opacity:.6'>No talents.</div>", unsafe_allow_html=True)

        st.markdown("<div class='sectionttl'>Wargear</div>", unsafe_allow_html=True)
        if ch["wargear"]:
            for w in ch["wargear"]:
                name = html.escape(str(w.get("name", "")))
                effect = html.escape(str(w.get("effect", "")))
                effect_html = f"<div style='margin-top:5px;opacity:.75;line-height:1.35'>{effect}</div>" if effect else ""
                st.markdown(f"<div class='wg'><b>{name}</b>{effect_html}</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='wg' style='opacity:.6'>No wargear.</div>", unsafe_allow_html=True)

        st.markdown("<div class='sectionttl'>Vox Network</div>", unsafe_allow_html=True)
        vox_live(cid)


# ============================================================
#  CHARACTER SHEET EDITOR (fully editable)
# ============================================================
def _k(cid, sec, f):
    return f"f_{cid}_{sec}_{f}"


def edit_view(cid, gm_mode=False):
    ch = load_character(cid)
    if not ch:
        st.error("Character sheet not found.")
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
    st.session_state.setdefault(_k(cid, "sel", "mode"), "archetype" if ch.get("creation_mode") == "archetype" else "advanced")
    ark = _k(cid, "sel", "arch")
    if ark not in st.session_state:
        st.session_state[ark] = ch.get("archetype") if ch.get("archetype") in ARCHETYPES else default_archetype_for_species(ch.get("species")) or list(ARCHETYPES.keys())[0]
    spk = _k(cid, "sel", "sp")
    if spk not in st.session_state:
        st.session_state[spk] = ch["species"] if ch["species"] in species_list else species_list[-1]

    # On first open, apply species bonuses without overwriting
    # already present on the sheet.
    species_init_key = _k(cid, "meta", "species_init")
    if not st.session_state.get(species_init_key, False):
        selected_species = st.session_state[spk]
        package = species_package(selected_species)

        for attr, value in package.get("attributes", {}).items():
            st.session_state[_k(cid, "a", attr)] = max(
                int(st.session_state[_k(cid, "a", attr)]),
                int(value),
            )

        for skill, value in package.get("skills", {}).items():
            st.session_state[_k(cid, "s", skill)] = max(
                int(st.session_state[_k(cid, "s", skill)]),
                int(value),
            )

        st.session_state[_k(cid, "meta", "previous_species")] = selected_species
        st.session_state[species_init_key] = True

    # Standard creation: the Magister defines Species + Archetype.
    # Advanced creation: the Magister enables the mode, then the Player
    # chooses Species + Archetype on the character sheet.
    mode = ch.get("creation_mode") or "archetype"
    if gm_mode:
        advanced_key = _k(cid, "sel", "advanced")
        if advanced_key not in st.session_state:
            st.session_state[advanced_key] = (mode == "advanced")
        advanced = st.checkbox("Advanced Character Creation", key=advanced_key)
        mode = "advanced" if advanced else "archetype"

        if mode == "archetype":
            arch_options = archetype_options()
            if st.session_state.get(ark) not in arch_options and arch_options:
                st.session_state[ark] = arch_options[0]
            if arch_options:
                st.selectbox(
                    "Archetype", arch_options, key=ark,
                    on_change=cb_archetype_change, args=(cid,),
                    format_func=lambda name: f"{name}  ·  T{ARCHETYPES[name]['tier']}  ·  {species_label(ARCHETYPES[name]['species'])}",
                )
                ad = ARCHETYPES[st.session_state[ark]]
                st.caption(f"Tier {ad['tier']} · {ad['species']} · {ad['xp']} XP · {ad['faction']}")
        else:
            st.info("Advanced Character Creation: the Player chooses Species. No Archetype is used.")
            st.session_state[ark] = ""
    else:
        if mode == "advanced":
            # Advanced Character Creation has no Archetype.
            # The Player chooses only Species; Tier and Rank remain controlled by the Magister.
            st.selectbox("Species", species_list, format_func=species_label,
                         key=spk, on_change=cb_species_change, args=(cid,))
            st.caption("Advanced Character Creation: you choose your Species. No Archetype is used.")
            st.session_state[ark] = ""
        else:
            selected_arch = ch.get("archetype") or st.session_state.get(ark, "")
            ad = ARCHETYPES.get(selected_arch)
            st.text_input("Archetype", value=selected_arch or "None", disabled=True, key=f"player_arch_{cid}")
            if ad:
                st.caption(f"Tier {ad['tier']} · {ad['faction']}")

    if mode == "archetype" and ch.get("creation_mode") != "archetype":
        cb_archetype_change(cid)
    elif mode == "advanced":
        st.session_state[ark] = ""

    c = st.columns([2, 2, 2])
    c[0].text_input("Name", key=_k(cid, "t", "name"))
    c[1].text_input("Chapter / Faction", key=_k(cid, "t", "chapter"))
    if gm_mode:
        if mode == "archetype":
            c[2].selectbox(
                "Species", species_list, format_func=species_label, key=spk,
                on_change=cb_species_change, args=(cid,),
            )
        else:
            c[2].text_input("Species", value=species_label(ch.get("species") or "Unknown"), disabled=True, key=f"gm_species_{cid}")
    elif mode != "advanced":
        c[2].text_input("Species", value=species_label(ch.get("species") or "Unknown"), disabled=True, key=f"player_species_{cid}")
    else:
        c[2].markdown("**Species**")
        c[2].caption(species_label(st.session_state[spk]))
    c = st.columns([1, 1, 1, 2])
    c[0].metric("Tier", int(st.session_state[_k(cid, "n", "tier")]))
    c[1].number_input("Armour", 0, 30, key=_k(cid, "n", "armour"))
    c[2].number_input("Other XP", 0, 100000, key=_k(cid, "n", "other"))
    if gm_mode:
        exp = c[3].number_input("Earned XP", 0, 100000, int(ch["earned_xp"]), key=f"earn_{cid}")
        if exp != ch["earned_xp"]:
            set_earned_xp(cid, exp)
    else:
        c[3].markdown(f"**Rank:** {rank_label(ch.get('rank', 1))}<br><small></small>", unsafe_allow_html=True)

    st.markdown("#### Attributes")
    acol = st.columns(4)
    for i, a in enumerate(ATTRS):
        acol[i % 4].number_input(a, 1, 12, key=_k(cid, "a", a))
    # Read current values before rendering the Skill pools.
    # Streamlit executes this function top-to-bottom, so these dictionaries
    # must exist before the skill widgets use them.
    cur_attr = {a: int(st.session_state[_k(cid, "a", a)]) for a in ATTRS}
    cur_skill = {s: int(st.session_state[_k(cid, "s", s)]) for s in SKILLS}

    st.markdown("#### Skills")
    scol = st.columns(3)
    for i, s in enumerate(SKILLS):
        with scol[i % 3]:
            cc = st.columns([3, 1])
            cc[0].number_input(s, 0, 8, key=_k(cid, "s", s))
            # Show the complete test pool beside each Skill.
            pool = int(st.session_state[_k(cid, "s", s)]) + int(st.session_state[_k(cid, "a", SKILLS[s])])
            cc[1].markdown(f"<div style='padding-top:30px;color:#e8c96a;font-family:Cinzel'>{pool}</div>",
                           unsafe_allow_html=True)

    package = species_package(st.session_state[spk])
    if package:
        st.markdown("#### Species Package")
        st.caption(f"Package: {package.get('xp', 0)} XP · "
                   f"Speed {package.get('speed', species_speed(st.session_state[spk]))} · "
                   f"Size {package.get('size', 'Average')}")

        abilities = package.get("abilities", [])
        if abilities:
            for ability in abilities:
                st.markdown(
                    f"<div class='tal'><span class='tn'>{ability}</span></div>",
                    unsafe_allow_html=True,
                )

    st.markdown("#### Talents")
    st.caption("Enter the name, effect, and XP cost. The effect will appear in Battle View.")
    tdf = ch["talents"] if ch["talents"] else [{"name": "", "effect": "", "cost": 20}]
    edited_talents = st.data_editor(
        tdf, num_rows="dynamic", key=f"tal_{cid}", use_container_width=True,
        column_config={
            "name": st.column_config.TextColumn("Talent", width="medium"),
            "effect": st.column_config.TextColumn("Effect", width="large"),
            "cost": st.column_config.NumberColumn("XP", min_value=0, step=5),
        },
    )
    talents = []
    for r in edited_talents:
        name = str(r.get("name", "") or "").strip()
        if name:
            talents.append({
                "name": name,
                "effect": str(r.get("effect", "") or "").strip(),
                "cost": int(r.get("cost") or 0),
            })

    st.markdown("#### Wargear")
    st.caption("Enter the name and effect. Both will appear in Battle View.")
    wdf = ch["wargear"] if ch["wargear"] else [{"name": "", "effect": ""}]
    edited_wargear = st.data_editor(
        wdf, num_rows="dynamic", key=f"wg_{cid}", use_container_width=True,
        column_config={
            "name": st.column_config.TextColumn("Wargear", width="medium"),
            "effect": st.column_config.TextColumn("Effect", width="large"),
        },
    )
    wargear = []
    for r in edited_wargear:
        name = str(r.get("name", "") or "").strip()
        if name:
            wargear.append({"name": name, "effect": str(r.get("effect", "") or "").strip()})

    wc = st.columns(2)
    wc[0].markdown("**Summary**")
    wc[0].caption(f"{len(wargear)} wargear item(s) · {len(talents)} talent(s)")
    wc[1].text_area("Notes", key=_k(cid, "t", "notes"), height=110)

    if mode == "advanced":
        # Advanced creation still records and applies the Player's selected
        # Archetype. The Advanced flag adds the Tier ×10 XP allowance.
        pass

    save_build(
        cid, st.session_state[_k(cid, "t", "name")], st.session_state[_k(cid, "t", "chapter")],
        st.session_state[spk], int(st.session_state[_k(cid, "n", "tier")]), cur_attr, cur_skill,
        talents, json.dumps(wargear, ensure_ascii=False), st.session_state[_k(cid, "n", "armour")],
        st.session_state[_k(cid, "t", "notes")], st.session_state[_k(cid, "n", "other")],
        st.session_state.get(ark, ""),
        mode
    )

    cur = dict(ch); cur.update({"attributes": cur_attr, "skills": cur_skill, "species": st.session_state[spk],
                                "tier": int(st.session_state[_k(cid, "n", "tier")]), "talents": talents,
                                "archetype": st.session_state.get(ark, ""),
                                "creation_mode": mode,
                                "other_xp": int(st.session_state[_k(cid, "n", "other")])})
    spent = xp_spent(cur); start = starting_xp(camp["tier"], advanced=(mode == "advanced")); avail = start + int(ch["earned_xp"]) - spent
    st.divider()
    x = st.columns(4)
    x[0].metric("Starting XP", start); x[1].metric("Earned XP", ch["earned_xp"])
    x[2].metric("XP Spent", spent); x[3].metric("XP Available", avail)
    if avail < 0:
        st.error(f"Over budget by {-avail} XP.")

    with st.expander("Portrait"):
        if ch.get("portrait"):
            st.image(ch["portrait"], width=170)
        up = st.file_uploader("Upload", type=["png", "jpg", "jpeg"], key=f"port_{cid}")
        if up is not None and st.button("Save Portrait", key=f"pb_{cid}"):
            set_portrait(cid, up.getvalue()); st.rerun()


# ============================================================
#  PAGES
# ============================================================
def login_page():
    st.markdown("<div class='banner'>✠ IMPERIAL COGITATOR ✠"
                "<span class='sub'>Adeptus Administratum · Campaign Record</span></div>", unsafe_allow_html=True)
    col = st.columns([1, 1.3, 1])[1]
    with col:
        st.markdown(" ")
        with st.form("login"):
            u = st.text_input("Designation")
            p = st.text_input("Access Code", type="password")
            ok = st.form_submit_button("Authenticate")
        if ok:
            user = verify_user(u.strip(), p)
            if user:
                st.session_state.user = user; st.rerun()
            else:
                st.error("Access denied.")
        
    st.markdown("<div class='foot'>THE EMPEROR PROTECTS</div>", unsafe_allow_html=True)


def folder_label(fid, folders):
    for f in folders:
        if f["id"] == fid:
            return f["name"]
    return "No folder"


def char_row(ch, folders):
    rank, _ = rank_from_xp(ch["earned_xp"], ch.get("rank", 1)); d = derived_traits(ch)
    ncls = "npc" if ch["kind"] == "npc" else ""
    vs = ("<span class='vlive'>ACTIVE</span>" if ch["comms_on"]
          else ("<span class='vdead'>CUT</span>" if secs_since(ch["comms_changed_at"]) < COMMS_FADE_S else ""))
    c = st.columns([3.2, 1.6, 0.9, 1, 0.6])
    c[0].markdown(f"<b class='{ncls}'>{ch['name'] or 'Unnamed'}{'*' if ch.get('creation_mode') == 'advanced' else ''}</b><br>"
                  f"<small style='opacity:.65'>{ch['species']} · T{ch['tier']} · Rank {rank}</small> {vs}",
                  unsafe_allow_html=True)
    c[1].markdown(f"<small>Shock {ch['cur_shock']}/{d['Max Shock']}<br>Wrath {ch['cur_wrath']}/{d['Max Wrath']}</small>",
                  unsafe_allow_html=True)
    c[2].button("Open", key=f"op_{ch['id']}", on_click=cb_open, args=(ch["id"],))
    if ch["comms_on"]:
        c[3].button("Cut Vox", key=f"vr_{ch['id']}", on_click=set_comms, args=(ch["id"], 0))
    else:
        c[3].button("Activate Vox", key=f"vr_{ch['id']}", on_click=set_comms, args=(ch["id"], 1))
    c[4].button("X", key=f"dl_{ch['id']}", on_click=delete_character, args=(ch["id"],))


def vox_toggle_list(chars):
    for ch in chars:
        ncls = "npc" if ch["kind"] == "npc" else ""
        c = st.columns([3, 1.4, 1.2])
        c[0].markdown(f"<span class='{ncls}'>{ch['name'] or 'Unnamed'}</span>", unsafe_allow_html=True)
        if ch["comms_on"]:
            c[1].markdown("<span class='vlive'>✠ ACTIVE</span>", unsafe_allow_html=True)
            c[2].button("Cut Vox", key=f"vt_{ch['id']}", on_click=set_comms, args=(ch["id"], 0))
        else:
            c[1].markdown("<span class='vdead'>✠ CUT</span>", unsafe_allow_html=True)
            c[2].button("Activate Vox", key=f"vt_{ch['id']}", on_click=set_comms, args=(ch["id"], 1))


def gm_view():
    camp = get_campaign()
    st.markdown("<div class='banner'>✠ MAGISTER SANCTUM ✠<span class='sub'>Campaign Command</span></div>",
                unsafe_allow_html=True)

    if st.session_state.get("editing"):
        cid = st.session_state.editing
        st.button("Back", on_click=cb_close)
        t = st.tabs(["Battle View", "Edit"])
        with t[0]:
            battle_view(cid)
        with t[1]:
            edit_view(cid, gm_mode=True)
        return

    tabs = st.tabs(["Characters", "Vox", "Progression", "Session", "Combat", "Campaign", "Maintenance"])

    # ---- Characters / Folders ----
    with tabs[0]:
        folders = list_folders()
        all_chars = list_characters()
        folder_map = {f["id"]: f["name"] for f in folders}
        folder_options = [None] + [f["id"] for f in folders]

        st.markdown("#### Table Organization")
        st.caption("* = Advanced Character Creation")
        st.caption("Use folders as campaign groups. They also define which characters share the Vox network.")

        # Quick folder creation
        fc = st.columns([4, 1])
        newf = fc[0].text_input("New Folder", key="newfolder", placeholder="e.g. Alpha Squad, Ship, Enemies...")
        if fc[1].button("Create Folder", use_container_width=True):
            if newf.strip():
                create_folder(newf.strip()); st.rerun()

        # Manage folders without hiding the main character list.
        if folders:
            st.markdown("**Existing Folders**")
            for f in folders:
                c = st.columns([3.8, 1, 1])
                nm = c[0].text_input("Name", f["name"], key=f"fn_{f['id']}", label_visibility="collapsed")
                if nm.strip() and nm != f["name"]:
                    rename_folder(f["id"], nm.strip())
                count = sum(1 for ch in all_chars if ch.get("folder_id") == f["id"])
                c[1].markdown(f"**{count}** character(s)")
                if c[2].button("Delete", key=f"fd_{f['id']}"):
                    delete_folder(f["id"]); st.rerun()

        st.divider()
        cre = st.columns(2)
        with cre[0]:
            st.markdown("#### Recruit Player")
            with st.form("newp"):
                nu = st.text_input("Username")
                npw = st.text_input("Password", type="password")
                st.markdown("**Character Definition**")
                pc2 = st.columns([1, 1, 2])
                ptier = pc2[0].number_input("Tier", 1, MAX_TIER, int(get_campaign()["tier"]))
                prank = pc2[1].selectbox("Rank", [1, 2, 3], format_func=rank_label)
                padvanced = pc2[2].checkbox("Advanced Character Creation", value=False)
                if not padvanced:
                    pc1 = st.columns(2)
                    pspecies = pc1[0].selectbox("Species", PLAYER_SPECIES, format_func=species_label)
                    parch = pc1[1].selectbox(
                        "Archetype", archetype_options(),
                        format_func=lambda name: f"{name}  ·  T{ARCHETYPES[name]['tier']}  ·  {ARCHETYPES[name]['faction']}"
                    )
                    st.caption("The Magister defines Species, Archetype, Tier and Rank. The Player cannot edit them.")
                else:
                    pspecies = ""
                    parch = ""
                    st.caption("Advanced Character Creation: the Player chooses Species. No Archetype is used.")
                if st.form_submit_button("Recruit"):
                    if nu.strip() and npw:
                        mode = "advanced" if padvanced else "archetype"
                        ok, msg = create_player(nu.strip(), npw, mode, ptier, prank, pspecies, parch)
                        (st.success if ok else st.error)(msg)
                        if ok:
                            st.rerun()
        with cre[1]:
            st.markdown("#### Create NPC")
            with st.form("newn"):
                nn = st.text_input("Name")
                nsp = st.selectbox("Species / Type", NPC_SPECIES)
                nc = st.columns([1, 1, 2])
                nt = nc[0].number_input("Tier", 1, MAX_TIER, int(get_campaign()["tier"]))
                nrank = nc[1].selectbox("Rank", [1, 2, 3], format_func=rank_label)
                nadvanced = nc[2].checkbox("Advanced Character Creation", value=False)
                if st.form_submit_button("Create NPC"):
                    create_npc(nn.strip(), nsp, nt, "advanced" if nadvanced else "archetype", nrank)
                    st.rerun()

        st.divider()
        view = st.radio("View", ["By Folder", "All", "Players", "NPCs"], horizontal=True, key="gm_servo_view")

        if view == "By Folder":
            groups = {None: []}
            for f in folders:
                groups[f["id"]] = []
            for ch in all_chars:
                groups.setdefault(ch.get("folder_id"), []).append(ch)

            for fid, items in groups.items():
                label = folder_map.get(fid, "No folder")
                icon = "◈" if fid is not None else "◇"
                st.markdown(f"#### {icon} {label}  ·  {len(items)} character(s)")
                if not items:
                    st.caption("No characters in this folder.")
                    continue
                for ch in items:
                    a = st.columns([4.2, 1.7, 1.1, 1.1])
                    with a[0]:
                        char_row(ch, folders)
                    opts = folder_options
                    idx = opts.index(ch.get("folder_id")) if ch.get("folder_id") in opts else 0
                    a[1].selectbox("Folder", opts, index=idx, key=f"mv_{ch['id']}",
                                   format_func=lambda x: folder_map.get(x, "No folder") if x is not None else "No folder",
                                   label_visibility="collapsed",
                                   on_change=lambda cid=ch["id"]: set_folder(cid, st.session_state[f"mv_{cid}"]))
                    a[2].markdown("📡 **Vox**")
                    if ch["comms_on"]:
                        if a[3].button("Cut Vox", key=f"gmvc_{ch['id']}"):
                            set_comms(ch["id"], 0); st.rerun()
                    else:
                        if a[3].button("Activate Vox", key=f"gmvc_{ch['id']}"):
                            set_comms(ch["id"], 1); st.rerun()

        else:
            filtered = all_chars
            if view == "Players":
                filtered = [c for c in all_chars if c["kind"] == "player"]
            elif view == "NPCs":
                filtered = [c for c in all_chars if c["kind"] == "npc"]
            for ch in filtered:
                a = st.columns([4.5, 2, 1.1])
                with a[0]:
                    char_row(ch, folders)
                opts = folder_options
                idx = opts.index(ch.get("folder_id")) if ch.get("folder_id") in opts else 0
                a[1].selectbox("Folder", opts, index=idx, key=f"mva_{ch['id']}",
                               format_func=lambda x: folder_map.get(x, "No folder") if x is not None else "No folder",
                               label_visibility="collapsed",
                               on_change=lambda cid=ch["id"]: set_folder(cid, st.session_state[f"mva_{cid}"]))
                a[2].markdown("📡" + (" ON" if ch["comms_on"] else " OFF"))

    # ---- Vox ----
    with tabs[1]:
        folders = list_folders()
        chars = list_characters()
        folder_map = {f["id"]: f["name"] for f in folders}
        groups = {None: []}
        for f in folders:
            groups[f["id"]] = []
        for ch in chars:
            groups.setdefault(ch.get("folder_id"), []).append(ch)

        st.markdown("#### Vox Network by Folder")
        st.caption("Each folder is a closed network. A character only receives signals from characters in the same folder.")

        # Quick network selection
        folder_choices = [None] + [f["id"] for f in folders]
        selected_fid = st.selectbox(
            "Network / Folder", folder_choices, key="vox_folder_select",
            format_func=lambda x: "No folder (isolated)" if x is None else folder_map.get(x, "Folder"),
        )

        if selected_fid is None:
            st.warning("Characters without a folder do not share Vox.")
        else:
            members = groups.get(selected_fid, [])
            on_count = sum(1 for ch in members if ch["comms_on"])
            c = st.columns([2, 2, 2])
            c[0].metric("Members", len(members))
            c[1].metric("Vox Active", on_count)
            c[2].metric("Cut", len(members) - on_count)
            b = st.columns(2)
            if b[0].button("Activate Folder Vox", use_container_width=True):
                set_comms_for_folder(selected_fid, 1); st.rerun()
            if b[1].button("Cut Folder Vox", use_container_width=True):
                set_comms_for_folder(selected_fid, 0); st.rerun()

            st.divider()
            if not members:
                st.info("This folder is empty.")
            else:
                vox_toggle_list(members)

        st.divider()
        st.markdown("#### All Networks")
        for fid, members in groups.items():
            label = "No folder" if fid is None else folder_map.get(fid, "Folder")
            on_count = sum(1 for ch in members if ch["comms_on"])
            st.markdown(f"**{label}** · {len(members)} member(s) · {on_count} active")
        st.markdown("#### Magister Monitor")
        vox_live()

    # ---- Progression ----
    with tabs[2]:
        st.markdown("#### Progression")
        st.caption("Rank and Tier are controlled by the Magister. XP thresholds unlock normal advancement; the Magister may also approve an early advancement.")

        def progression_section(title, kind):
            st.markdown(f"#### {title}")
            chars = list_characters(kind)
            if not chars:
                st.info(f"No {title.lower()}.")
                return
            for c in chars:
                earned = int(c.get("earned_xp", 0))
                rank = int(c.get("rank", 1))
                tier = int(c.get("tier", 1))
                next_rank = rank + 1
                next_rank_xp = RANKS[next_rank]["min_xp"] if next_rank <= 3 else None
                rank_missing = max(0, next_rank_xp - earned) if next_rank_xp is not None else 0
                next_tier = tier + 1
                tier_missing = max(0, 100 - earned) if next_tier <= MAX_TIER else 0
                with st.container(border=True):
                    st.markdown(f"**{c['name'] or 'Unnamed'}** · Tier {tier} · {rank_label(rank)}")
                    pc = st.columns(4)
                    pc[0].metric("Earned XP", earned)
                    pc[1].metric("Next Rank", "Maximum" if next_rank > 3 else f"{rank_label(next_rank)}")
                    pc[2].metric("XP to Next Rank", "-" if next_rank > 3 else str(rank_missing))
                    pc[3].metric("XP to Next Tier", "-" if next_tier > MAX_TIER else str(tier_missing))
                    ac = st.columns(2)
                    if next_rank <= 3:
                        ready = earned >= next_rank_xp
                        label = f"Approve Rank {next_rank}" if ready else f"Approve Rank {next_rank} Early"
                        if ac[0].button(label, key=f"prog_r_{c['id']}", use_container_width=True):
                            if set_rank(c["id"], next_rank, force=not ready):
                                add_log("Magister", f"{c['name']} advanced to Rank {next_rank}{' early' if not ready else ''}.")
                                st.rerun()
                    else:
                        ac[0].button("Maximum Rank", disabled=True, use_container_width=True, key=f"prog_r_max_{kind}_{c['id']}")
                    if next_tier <= MAX_TIER:
                        ready = earned >= 100
                        label = f"Approve Tier {next_tier}" if ready else f"Approve Tier {next_tier} Early"
                        if ac[1].button(label, key=f"prog_t_{c['id']}", use_container_width=True):
                            if set_tier(c["id"], next_tier, force=not ready):
                                add_log("Magister", f"{c['name']} advanced to Tier {next_tier}{' early' if not ready else ''}.")
                                st.rerun()
                    else:
                        ac[1].button("Maximum Tier", disabled=True, use_container_width=True, key=f"prog_t_max_{kind}_{c['id']}")

        progression_section("Players", "player")
        st.divider()
        progression_section("NPCs", "npc")

        st.divider()
        st.markdown("#### Archetype Ascension")
        st.caption("Archetype Ascension requires Rank 3 and moves to the next Tier within the same Faction. The new Archetype does not grant new Attribute or Skill bonuses.")
        eligible_arch = [c for c in list_characters() if c.get("creation_mode") == "archetype" and int(c.get("rank", 1)) >= 3 and int(c.get("tier", 1)) < MAX_TIER]
        if eligible_arch:
            for ac in eligible_arch:
                current_arch = ARCHETYPES.get(ac.get("archetype"), {})
                choices = [name for name, data in ARCHETYPES.items()
                           if int(data.get("tier", 0)) == int(ac["tier"]) + 1
                           and (not current_arch.get("faction") or data.get("faction") == current_arch.get("faction"))]
                if not choices:
                    continue
                st.markdown(f"**{ac['name']}** · Tier {ac['tier']} · {rank_label(ac['rank'])}")
                new_arch = st.selectbox("Next Archetype", choices, key=f"prog_arch_{ac['id']}")
                if st.button("Approve Archetype Ascension", key=f"prog_arch_btn_{ac['id']}", use_container_width=True):
                    ok, msg = ascend_archetype(ac["id"], new_arch)
                    (st.success if ok else st.error)(msg)
                    if ok:
                        add_log("Magister", f"{ac['name']} ascended to {new_arch}.")
                        st.rerun()
        else:
            st.info("No character is currently eligible for Archetype Ascension.")

    # ---- Session ----
    with tabs[3]:
        st.markdown("#### Session")
        st.caption("Close the session, award table XP and individual bonuses, record notes, and mark the NPCs involved.")
        current_session = int(camp.get("session_no", 1))
        players = list_characters("player")
        npcs = list_characters("npc")
        old_records = get_session_records(20)

        with st.form("session_record_form"):
            sc = st.columns([1.2, 2.8, 1.2])
            session_no = sc[0].number_input("Session", 1, 9999, current_session)
            title = sc[1].text_input("Session Title", placeholder="e.g. The Fall of Gilead")
            base_xp = sc[2].number_input("Table XP", 0, 10000, 20, step=5)
            notes = st.text_area("Session Notes", placeholder="Events, rewards, consequences, rulings, loot, reminders...")

            st.markdown("**NPCs involved**")
            npc_ids = []
            if npcs:
                ncols = st.columns(3)
                for i, npc in enumerate(npcs):
                    if ncols[i % 3].checkbox(f"{npc['name'] or 'Unnamed NPC'} · T{npc['tier']}", key=f"session_npc_{npc['id']}"):
                        npc_ids.append(npc["id"])
            else:
                st.caption("No NPCs available.")

            st.markdown("**Player XP**")
            award_rows = []
            if players:
                h = st.columns([3.5, 1.4, 1.4, 1.4])
                h[0].markdown("**Character**")
                h[1].markdown("**Present**")
                h[2].markdown("**Base XP**")
                h[3].markdown("**Bonus XP**")
                for pl in players:
                    cols = st.columns([3.5, 1.4, 1.4, 1.4])
                    present = cols[1].checkbox("Present", value=True, key=f"session_present_{pl['id']}", label_visibility="collapsed")
                    cols[0].markdown(f"**{pl['name'] or 'Unnamed'}** · T{pl['tier']} · {rank_label(pl['rank'])}")
                    cols[2].number_input("Base", min_value=0, max_value=10000, value=int(base_xp), step=5, key=f"session_base_{pl['id']}", label_visibility="collapsed", disabled=not present)
                    cols[3].number_input("Bonus", min_value=0, max_value=10000, value=0, step=5, key=f"session_bonus_{pl['id']}", label_visibility="collapsed", disabled=not present)
                    if present:
                        award_rows.append((pl["id"], st.session_state[f"session_base_{pl['id']}"], st.session_state[f"session_bonus_{pl['id']}"]))
            else:
                st.info("No players are registered.")

            advance = st.checkbox("Advance campaign to the next session", value=True)
            submit = st.form_submit_button("Close Session & Award XP", use_container_width=True)
            if submit:
                sid = create_session_record(session_no, title, notes, base_xp, npc_ids)
                award_session_xp(sid, award_rows, close_session=True, advance_campaign=advance)
                total_awarded = sum(int(a[1]) + int(a[2]) for a in award_rows)
                add_log("Magister", f"Session {int(session_no)} closed. {total_awarded} XP awarded across {len(award_rows)} player(s).")
                st.success("Session closed and XP awarded.")
                st.rerun()

        st.divider()
        st.markdown("#### Session History")
        if not old_records:
            st.caption("No session records yet.")
        for sr in old_records:
            status = "Closed" if sr["closed_at"] else "Draft"
            label = f"Session {sr['session_no']} · {sr['title'] or 'Untitled'} · {status}"
            with st.expander(label):
                st.write(sr["notes"] or "No notes.")
                try:
                    marked_ids = json.loads(sr["npc_ids"] or "[]")
                except Exception:
                    marked_ids = []
                marked = [n["name"] for n in npcs if n["id"] in marked_ids]
                st.write("NPCs involved: " + (", ".join(marked) if marked else "None"))
                awards = get_session_awards(sr["id"])
                if awards:
                    for aw in awards:
                        st.markdown(f"**{aw['name']}** · +{aw['total_xp']} XP (base {aw['base_xp']} + bonus {aw['bonus_xp']})")

    # ---- Combat ----
    with tabs[4]:
        st.markdown("#### Combat")
        st.caption("The Magister controls the combat order manually. Add Players and NPCs, apply initiative modifiers, and arrange the turn order.")
        all_combat_chars = list_characters()
        folders = list_folders()
        folder_map = {f["id"]: f["name"] for f in folders}
        active = {c["id"] for c in get_combatants()}

        fc = st.columns([1.8, 2.5, 1])
        folder_options = [None] + [f["id"] for f in folders]
        selected_folder = fc[0].selectbox("Filter by Folder", folder_options,
            format_func=lambda x: "All Folders" if x is None else folder_map.get(x, "Folder"), key="combat_folder")
        search = fc[1].text_input("Search Character", placeholder="Search by name, species, archetype, or faction", key="combat_search")
        if fc[2].button("Clear Combat", use_container_width=True, key="combat_clear"):
            clear_combat(); st.rerun()

        filtered = []
        q = search.strip().lower()
        for ch in all_combat_chars:
            if selected_folder is not None and ch.get("folder_id") != selected_folder:
                continue
            hay = " ".join([str(ch.get("name") or ""), str(ch.get("species") or ""), str(ch.get("archetype") or ""), str(ch.get("chapter") or "")]).lower()
            if q and q not in hay:
                continue
            filtered.append(ch)

        st.markdown(f"**Available Characters:** {len(filtered)}")
        for ch in filtered:
            cols = st.columns([4, 1.2, 1.2, 1.2])
            in_combat = ch["id"] in active
            folder_name = folder_map.get(ch.get("folder_id"), "No folder")
            kind_label = "NPC" if ch["kind"] == "npc" else "PLAYER"
            ncls = "npc" if ch["kind"] == "npc" else ""
            cols[0].markdown(f"**<span class='{ncls}'>{ch['name'] or 'Unnamed'}</span>** · {kind_label} · {species_label(ch['species'])} · T{ch['tier']} · {rank_label(ch['rank'])}<br><small>{folder_name}</small>", unsafe_allow_html=True)
            if cols[1].button("Remove" if in_combat else "Add", key=f"combat_toggle_{ch['id']}", use_container_width=True):
                set_combatant(ch["id"], not in_combat); st.rerun()
            if cols[2].button("Open", key=f"combat_open_{ch['id']}", use_container_width=True):
                st.session_state.editing = ch["id"]; st.rerun()
            cols[3].markdown("**IN COMBAT**" if in_combat else "")

        st.divider()
        current = get_combatants()
        st.markdown("<div class='combat-header'><div class='title'>⚔ Combat Order</div><div class='sub'>The Magister controls the sequence of turns</div></div>", unsafe_allow_html=True)
        st.markdown("<div class='combat-legend'><span class='p'>● Player</span><span class='n'>● NPC</span><span>↑↓ Reorder</span></div>", unsafe_allow_html=True)
        if not current:
            st.info("No characters are currently in combat. Add Players or NPCs above.")
        else:
            for idx, ch in enumerate(current):
                kind_label = "PLAYER" if ch["kind"] != "npc" else "NPC"
                role_cls = "player" if ch["kind"] != "npc" else "npc"
                name = ch["name"] or "Unnamed"
                modifier_value = int(ch.get("initiative_modifier", 0))
                sign = "+" if modifier_value >= 0 else ""
                st.markdown(
                    f"<div class='combat-card {role_cls}'><div style='display:flex;align-items:center;gap:12px'>"
                    f"<div class='combat-pos'>{idx + 1:02d}</div>"
                    f"<div style='flex:1'><div class='combat-name'>{name}<span class='combat-kind {role_cls}'>{kind_label}</span></div>"
                    f"<div class='combat-meta'>{species_label(ch['species'])} · Tier {ch['tier']} · {rank_label(ch['rank'])}</div></div>"
                    f"<div class='combat-mod'>INIT {sign}{modifier_value}</div></div></div>",
                    unsafe_allow_html=True,
                )
                controls = st.columns([1.1, 1.1, 1.1, 1.1, 1.6])
                if controls[0].button("↑ Move Up", key=f"combat_up_{ch['id']}", disabled=(idx == 0), use_container_width=True):
                    move_combatant(ch["id"], -1); st.rerun()
                if controls[1].button("↓ Move Down", key=f"combat_down_{ch['id']}", disabled=(idx == len(current) - 1), use_container_width=True):
                    move_combatant(ch["id"], 1); st.rerun()
                modifier = controls[2].number_input("Init Mod", -100, 100, modifier_value, step=1, key=f"combat_mod_{ch['id']}")
                if modifier != modifier_value:
                    set_combat_modifier(ch["id"], modifier)
                if controls[3].button("Open Sheet", key=f"combat_current_open_{ch['id']}", use_container_width=True):
                    st.session_state.editing = ch["id"]; st.rerun()
                if controls[4].button("Remove", key=f"combat_current_remove_{ch['id']}", use_container_width=True):
                    set_combatant(ch["id"], False); st.rerun()
                if idx < len(current) - 1:
                    st.markdown("<div class='combat-arrow'>▼</div>", unsafe_allow_html=True)

    # ---- Campaign ----
    # ---- Campaign ----
    with tabs[5]:
        st.markdown("#### Campaign Configuration")
        with st.form("campf"):
            cc = st.columns([3, 1, 1])
            cname = cc[0].text_input("Campaign Name", camp["name"])
            ctier = cc[1].number_input("Campaign Tier", 1, MAX_TIER, int(camp["tier"]))
            sess = cc[2].number_input("Session", 1, 999, int(camp["session_no"]))
            if st.form_submit_button("Save"):
                save_campaign(cname, ctier, camp["ruin"], sess); st.rerun()
        st.caption(f"Standard character XP: {starting_xp(camp['tier'])} (Tier {camp['tier']} × 100). Advanced Character Creation adds Tier ×10 bonus XP.")
        st.divider()
        st.markdown("#### Ruin")
        rc = st.columns([1, 1, 1, 3])
        rc[0].metric("Ruin", camp["ruin"])
        rc[1].button("−1", key="ruinm", on_click=adjust_ruin, args=(-1,))
        rc[2].button("+1", key="ruinp", on_click=adjust_ruin, args=(+1,))
        st.divider()
        st.markdown("#### Session Log")
        with st.form("voxlog"):
            msg = st.text_area("New Entry")
            if st.form_submit_button("Record"):
                if msg.strip():
                    add_log("Magister", msg.strip()); st.rerun()
        for lg in get_logs():
            st.markdown(f"<div class='row'><b>{lg['ts']}</b> - {lg['text']}</div>", unsafe_allow_html=True)

    # ---- Maintenance ----
    with tabs[6]:
        st.markdown("#### File Maintenance")
        st.caption("The .db backup contains everything: players, NPCs, folders, XP, Vox, portraits. "
                   "On free hosting the disk may reset; download backups regularly.")
        if os.path.exists(DB_PATH):
            size = os.path.getsize(DB_PATH) / (1024 * 1024)
            st.write(f"Database size: {size:.2f} MB (SQLite storage grows automatically).")
            with open(DB_PATH, "rb") as f:
                st.download_button("Download backup (cogitador.db)", f.read(),
                                   file_name="cogitador.db", mime="application/octet-stream")
        up = st.file_uploader("Restore backup", type=["db"])
        if up is not None and st.button("Overwrite everything"):
            with open(DB_PATH, "wb") as f:
                f.write(up.getbuffer())
            st.rerun()


def player_view():
    camp = get_campaign()
    st.markdown(f"<div class='banner'>✠ SERVICE RECORD ✠"
                f"<span class='sub'>{camp['name']} · Session {camp['session_no']}</span></div>", unsafe_allow_html=True)
    cid = char_id_for_user(st.session_state.user["id"])
    if not cid:
        st.error("No character sheet linked. Contact the Magister.")
        return
    t = st.tabs(["Battle View", "Character Sheet"])
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
        st.write(f"User: {st.session_state.user['username']}")
        st.write("Role: " + ("Magister" if role == "gm" else "Battle-Brother"))
        if role == "gm":
            st.metric("Ruin", camp["ruin"])
        st.divider()
        if st.button("Sign Out"):
            st.session_state.user = None; st.session_state.editing = None; st.rerun()
        with st.expander("Change Password"):
            with st.form("chpw"):
                a = st.text_input("New Password", type="password"); b = st.text_input("Confirm", type="password")
                if st.form_submit_button("Change"):
                    if a and a == b:
                        set_password(st.session_state.user["id"], a); st.success("Password updated.")
                    else:
                        st.error("Passwords do not match.")

    if st.session_state.user["role"] == "gm":
        gm_view()
    else:
        player_view()
    st.markdown("<div class='foot'>✠ THE EMPEROR PROTECTS ✠</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()