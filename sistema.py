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
import re
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
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
PLAYER_SPECIES = ["Human", "Adeptus Astartes", "Primaris Astartes", "Aeldari", "Ork"]
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

# Core Rulebook Species Attribute Maximums (base Ratings, before bonuses).
SPECIES_ATTRIBUTE_MAX = {
    "Human": {a: 8 for a in ATTRS},
    "Adeptus Astartes": {"Strength": 10, "Toughness": 10, "Agility": 9, "Initiative": 9, "Willpower": 10, "Intellect": 10, "Fellowship": 8},
    "Primaris Astartes": {"Strength": 12, "Toughness": 12, "Agility": 9, "Initiative": 9, "Willpower": 10, "Intellect": 10, "Fellowship": 8},
    "Aeldari": {"Strength": 7, "Toughness": 7, "Agility": 12, "Initiative": 12, "Willpower": 12, "Intellect": 10, "Fellowship": 6},
    "Ork": {"Strength": 12, "Toughness": 12, "Agility": 7, "Initiative": 7, "Willpower": 8, "Intellect": 7, "Fellowship": 7},
}

FACTION_OPTIONS = ["The Imperium", "Adepta Sororitas", "Adeptus Astra Telepathica", "Adeptus Mechanicus", "Adeptus Ministorum", "Astra Militarum", "The Inquisition", "Rogue Trader Dynasties", "Scum", "Adeptus Astartes", "Aeldari", "Orks", "Chaos"]
POWER_DISCIPLINES = {
    "Chameleon": "Universal", "Compel": "Universal", "Conceal Phenomena": "Universal",
    "Invoke Luck": "Universal", "Inflict Pain": "Universal", "Conjure Flame": "Universal",
    "Dull Pain": "Universal", "Flash Bang": "Universal", "Subvert Machine": "Universal",
    "Hover": "Universal", "Psychic Torch": "Universal", "Phantom Grip": "Universal",
    "Mental Force": "Universal", "Otherworldly Voices": "Universal", "Smite": "Universal",
    "Enfeeble": "Biomancy", "Life Leech": "Biomancy", "Warp Speed": "Biomancy",
    "Phantom Form": "Biomancy", "Regeneration": "Biomancy", "Shape Flesh": "Biomancy",
    "Forewarning": "Divination", "Prescience": "Divination", "Misfortune": "Divination",
    "Psychometry": "Divination", "Scrier’s Gaze": "Divination",
    "Fiery Form": "Pyromancy", "Flame Breath": "Pyromancy", "Mindfire": "Pyromancy",
    "Molten Beam": "Pyromancy", "Spontaneous Combustion": "Pyromancy", "Wall Of Flame": "Pyromancy",
    "Assail": "Telekinesis", "Crush": "Telekinesis", "Levitation": "Telekinesis",
    "Telekinetic Dome": "Telekinesis", "Grav-Warp": "Telekinesis", "Shock Wave": "Telekinesis",
    "Erasure": "Telepathy", "Fog The Mind": "Telepathy", "Mind Probe": "Telepathy",
    "Psychic Shriek": "Telepathy", "Telepathy": "Telepathy", "Terrify": "Telepathy",
    "Dark Flame": "Maleficarum", "Possession": "Maleficarum", "Soul Shrivel": "Maleficarum",
    "Touch Of Corruption": "Maleficarum", "Infernal Gaze": "Maleficarum",
    "Conceal / Reveal": "Runes of Battle", "Embolden / Horrify": "Runes of Battle",
    "Empower / Enervate": "Runes of Battle", "Enhance / Drain": "Runes of Battle",
    "Protect / Jinx": "Runes of Battle", "Quicken / Restrain": "Runes of Battle",
}


# Attribute and Skill increases included in the Core Rulebook Archetype package.
# These are written directly onto the character sheet when the Archetype is
# selected and are included in the Archetype XP cost. They are not gear-style
# bonuses and are not displayed as separate modifiers.
ARCHETYPE_PACKAGES = {
    "Sister Hospitaller": {"attributes":{"Willpower":3,"Intellect":3}, "skills":{"Medicae":1,"Scholar":1}},
    "Ministorum Priest": {"attributes":{"Willpower":3}, "skills":{"Scholar":1}},
    "Imperial Guard": {"attributes":{}, "skills":{"Ballistic Skill":2}},
    "Inquisitorial Acolyte": {"attributes":{}, "skills":{}, "skills_any_to": 2, "skills_any_count": 1},
    "Inquisitorial Sage": {"attributes":{"Intellect":3}, "skills":{"Scholar":2}},
    "Ganger": {"attributes":{}, "skills":{"Cunning":1}},
    "Corsair": {"attributes":{"Agility":3}, "skills":{"Athletics":2}},
    "Boy": {"attributes":{"Strength":3,"Toughness":3}, "skills":{"Weapon Skill":2}},
    "Sister of Battle": {"attributes":{"Strength":3,"Toughness":3,"Agility":3,"Willpower":3}, "skills":{"Ballistic Skill":2,"Scholar":1,"Weapon Skill":2}},
    "Sanctioned Psyker": {"attributes":{"Willpower":4}, "skills":{"Psychic Mastery":1}},
    "Skitarius": {"attributes":{"Toughness":3}, "skills":{"Ballistic Skill":2,"Tech":1}},
    "Death Cult Assassin": {"attributes":{"Agility":4}, "skills":{"Weapon Skill":2}},
    "Tempestus Scion": {"attributes":{"Strength":3,"Toughness":3,"Agility":3}, "skills":{"Ballistic Skill":2,"Stealth":2}},
    "Rogue Trader": {"attributes":{"Fellowship":3}, "skills":{"Awareness":1,"Cunning":1,"Insight":2,"Persuasion":2}},
    "Scavvy": {"attributes":{"Toughness":2}, "skills":{"Survival":1}},
    "Space Marine Scout": {"attributes":{"Strength":4,"Toughness":4,"Agility":4,"Initiative":4,"Willpower":3,"Intellect":3}, "skills":{"Athletics":3,"Awareness":3,"Ballistic Skill":3,"Stealth":3,"Weapon Skill":3}},
    "Ranger": {"attributes":{"Agility":3}, "skills":{"Ballistic Skill":2,"Stealth":1,"Survival":2}},
    "Kommando": {"attributes":{"Strength":3,"Toughness":3,"Agility":3}, "skills":{"Stealth":2,"Survival":1,"Weapon Skill":2}},
    "Tech-Priest": {"attributes":{"Intellect":3}, "skills":{"Scholar":1,"Tech":3}},
    "Crusader": {"attributes":{"Initiative":3,"Willpower":3}, "skills":{"Scholar":1,"Weapon Skill":3}},
    "Imperial Commissar": {"attributes":{"Strength":3,"Toughness":3,"Willpower":4}, "skills":{"Ballistic Skill":1,"Intimidation":2,"Leadership":2,"Weapon Skill":1}},
    "Desperado": {"attributes":{"Agility":3,"Intellect":2}, "skills":{"Awareness":2,"Cunning":2,"Investigation":2}},
    "Tactical Space Marine": {"attributes":{"Strength":4,"Toughness":5,"Agility":5,"Initiative":5,"Willpower":3,"Intellect":3}, "skills":{"Athletics":3,"Awareness":3,"Ballistic Skill":5,"Leadership":1,"Scholar":1,"Stealth":3,"Survival":1,"Weapon Skill":4}},
    "Warlock": {"attributes":{"Agility":3,"Willpower":4}, "skills":{"Psychic Mastery":2}},
    "Nob": {"attributes":{"Strength":4,"Toughness":3}, "skills":{"Intimidation":2}},
    "Inquisitor": {"attributes":{"Intellect":4,"Willpower":4}, "skills":{}, "skills_any_to": 4, "skills_any_count": 2},
    "Primaris Intercessor": {"attributes":{"Strength":5,"Toughness":6,"Agility":5,"Initiative":5,"Willpower":3,"Intellect":3}, "skills":{"Athletics":3,"Awareness":3,"Ballistic Skill":6,"Stealth":3,"Weapon Skill":3}},
}



ARCHETYPE_ABILITIES = {'Sister Hospitaller': 'Loyal Compassion', 'Ministorum Priest': 'Fiery Invective', 'Imperial Guard': 'Look Out, Sir!', 'Inquisitorial Acolyte': 'Inquisitorial Decree', 'Inquisitorial Sage': 'Administratum Records', 'Ganger': 'Scrounger', 'Corsair': 'Dancing on the Blade’s Edge', 'Boy': 'Get Stuck In', 'Sister of Battle': 'Purity of Faith', 'Sanctioned Psyker': 'Psyker', 'Skitarius': 'Heavily Augmented', 'Death Cult Assassin': 'Glancing Blow', 'Tempestus Scion': 'Elite Soldier', 'Rogue Trader': 'Warrant of Trade', 'Scavvy': 'Mutant', 'Space Marine Scout': 'Use the Terrain', 'Ranger': 'From the Shadows', 'Kommando': 'Kunnin‘ Plan', 'Tech-Priest': 'Rite of Repair', 'Crusader': 'Armour of Faith', 'Imperial Commissar': 'Fearsome Respect', 'Desperado': 'Valuable Prey', 'Tactical Space Marine': 'Tactical Versatility', 'Warlock': 'Runes of Battle', 'Nob': 'The Green Tide', 'Inquisitor': 'Unchecked Authority', 'Primaris Intercessor': 'Intercessor Focus'}

# Core Rulebook 2e starting Wargear by Archetype.
ARCHETYPE_STARTING_WARGEAR = {'Sister Hospitaller': ['Sororitas Power Armour', "Chirurgeon's Tools", 'Chain Bayonet (wrist mounted)', 'Laspistol', 'Sororitas Vestments', 'Copy of the Rule of the Sororitas'], 'Ministorum Priest': ['Chainsword', 'Laspistol', 'Rosarius', 'Knife', 'Ministorum Robes', 'Missionary Kit'], 'Imperial Guard': ['Flak Armour', 'Lasgun', 'Knife', 'Munitorum Issue Mess Kit', 'Grooming Kit', "Imperial Infantryman's Uplifting Primer", '3 Ration Packs'], 'Inquisitorial Acolyte': ['Flak Armour', 'Symbol of Authority', 'IMPERIUM Weapon (Value 5 or less, Uncommon or lower)', 'Second IMPERIUM Weapon (Value 5 or less, Uncommon or lower)'], 'Inquisitorial Sage': ['Administratum Robes', 'Laspistol', 'Knife', 'Auto Quill', 'Data-Slate', '3 Scrolls of Ancient Records'], 'Ganger': ['Knife', 'Bedroll', 'Canteen', 'Gang Colours', 'Laspistol'], 'Corsair': ['Corsair Armour', 'Shuriken Pistol', 'Lasblaster', 'Spirit Stone', '3 Plasma Grenades', 'Void Suit'], 'Boy': ['Shoota', 'Slugga', 'Choppa', 'Ripped Clothes'], 'Sister of Battle': ['Sororitas Power Armour', 'Chaplet Ecclesiasticus', 'Sororitas Vestments', 'Writing Kit', 'Copy of the Rule of the Sororitas', 'Boltgun'], 'Sanctioned Psyker': ['Laspistol', 'Force Stave', 'Psykana Mercy Blade', 'Munitorum Issue Mess Kit', 'Blanket', 'Grooming Kit', '2 Ration Packs'], 'Skitarius': ['Combi-Tool', 'Galvanic Rifle', 'Skitarii Auto-Cuirass'], 'Death Cult Assassin': ['Two Death Cult Power Blades', 'Bodyglove', 'Knife', 'Laspistol', '3 doses of Stimm'], 'Tempestus Scion': ['Tempestus Carapace', 'Hot-Shot Lasgun', 'Grav-Chute', 'Knife', 'Munitorum Issue Mess Kit', "Imperial Infantryman's Uplifting Primer", 'Slate Monitron', 'Monoscope', '3 Ration Packs'], 'Rogue Trader': ['Imperial Frigate', 'Flak Coat', 'Wargear Choice (Value up to Tier+4, Rare or lower)', 'Second Wargear Choice (Value up to Tier+4, Rare or lower)'], 'Scavvy': ['Laspistol', 'Knife', 'Bedroll', 'Canteen', 'Tattered Clothes'], 'Space Marine Scout': ['Scout Armour', 'Astartes Combat Knife', '3 Frag Grenades', 'Vox Bead', 'Boltgun'], 'Ranger': ['Cameleoline Cloak', 'Aeldari Mesh Armour', 'Ranger Long Rifle', 'Shuriken Pistol', 'Knife', 'Spirit Stone', 'Bedroll', 'Blanket', 'Magnocular Scope'], 'Kommando': ['Shoota', 'Slugga', 'Choppa', '3 Stikkbombs', 'Survival Kit'], 'Tech-Priest': ['Omnissian Axe', 'Laspistol', 'One Mechadendrite', '2 Augmetics', 'Combi-Tool', 'Light Power Armour', 'Omnissian Sigil'], 'Crusader': ['Power Sword', 'Storm Shield', 'Carapace Armour', 'Ministorum Robes'], 'Imperial Commissar': ['Bolt Pistol', 'Chainsword', 'Flak Coat', 'Munitorum Issue Mess Kit', 'Blanket', 'Grooming Kit', 'Uplifting Primer', '3 Ration Packs'], 'Desperado': ['Flak Coat', 'Preysense Goggles', 'Maps of the Heartworlds', 'Combi-Tool', 'Projectile Weapon', 'Uncommon Melee Weapon'], 'Tactical Space Marine': ['Aquila Mk VII Power Armour', 'Boltgun', 'Bolt Pistol', 'Astartes Combat Knife', '3 Frag Grenades', '3 Krak Grenades'], 'Warlock': ['Rune Armour', 'Witchblade', 'Shuriken Pistol', 'Set of Wraithbone Runes', 'Spirit Stone'], 'Nob': ["'Eavy Armour", 'Kustom Slugga', 'Kustom Choppa'], 'Inquisitor': ['Inquisitorial Rosette', 'Boltgun', 'Bolt Pistol', 'Flak Coat'], 'Primaris Intercessor': ['Mark X Tacticus Power Armour', 'Bolt Rifle', 'Heavy Bolt Pistol', 'Astartes Combat Knife', '3 Frag Grenades', '3 Krak Grenades', 'Ballistic Appeasement Autoreliquary']}

ARCHETYPE_GEAR_ALIASES = {
    "aquila mk vii power armour": "Aquila Mk VII",
    "mark x tacticus power armour": "Tacticus Mk X",
    "munitorum issue mess kit": "Munitorum-Issue Mess Kit",
    "auto quill": "Auto-Quill",
    "vox-bead": "Vox Bead",
    "ballistic appeasement autoreliquary": "Ballistic Appeasement Auto-Reliquary",
}

def _catalog_gear_row(catalog, name):
    target = str(name or "").strip().lower()
    alias = ARCHETYPE_GEAR_ALIASES.get(target, name)
    candidates = [str(alias or "").strip().lower(), target]
    for candidate in candidates:
        row = next((r for r in catalog if str(r.get("name", "")).strip().lower() == candidate), None)
        if row is not None:
            return row
    def compact(value):
        return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())
    target_compact = compact(alias)
    if target_compact:
        row = next((r for r in catalog if compact(r.get("name", "")) == target_compact), None)
        if row is not None:
            return row
    return None

def archetype_starting_wargear(archetype):
    """Build the complete Archetype starting Wargear package."""
    out = []
    try:
        catalog = list_craft_items("wargear")
    except Exception:
        catalog = []
    for raw in ARCHETYPE_STARTING_WARGEAR.get(archetype, []):
        qty, base = _gear_quantity_name(raw)
        row = _catalog_gear_row(catalog, base)
        if row is not None:
            entry_list = _craft_character_add([], row, "wargear")
            if entry_list:
                entry = entry_list[0]
                entry["quantity"] = qty
                entry.setdefault("details", {})["archetype_default"] = True
                out.extend(entry_list)
                continue
        out.append({
            "name": base if qty > 1 else raw,
            "effect": "",
            "equipped": True,
            "quantity": qty,
            "source": "Wrath & Glory Core Rulebook 2e",
            "details": {"archetype_default": True},
        })
    return normalize_wargear(out)

VITAL_FIELDS = {"cur_wounds", "cur_shock", "cur_wrath", "cur_corruption", "cur_wealth"}

# Official First Founding Chapters from the Core Rulebook (2nd edition).
# Homebrew material is intentionally excluded from this catalog.
CHAPTERS = {
    "Blood Angels": {
        "legion": "IX", "primarch": "Sanguinius",
        "ability": "Savage Echoes: You may reroll Double Rank dice once per melee attack Test.",
        "tradition": "The Red Thirst: Whenever you are in melee combat and see blood, make a DN 3 Willpower Test. If you fail, you are Frenzied."
    },
    "Dark Angels": {
        "legion": "I", "primarch": "Lion El'Jonson",
        "ability": "Fire Discipline: When Dark Angels make a ranged attack using a held action, they ignore up to Rank penalties on the attack.",
        "tradition": "The Secret: Dark Angels distrust anyone outside of their Chapter. They suffer a +2 DN penalty for Interaction Tests involving anyone outside the Dark Angels Chapter."
    },
    "Imperial Fists": {
        "legion": "VII", "primarch": "Rogal Dorn",
        "ability": "Siege Masters: You may reroll Double Rank dice once per attack against a building, fortification, or enemy in cover. You may also add +Rank bonus dice to Tests related to architectural engineering.",
        "tradition": "No Retreat: If an Imperial Fists Space Marine fails a Willpower Test, the GM gains 1 Ruin."
    },
    "Iron Hands": {
        "legion": "X", "primarch": "Ferrus Manus",
        "ability": "The Flesh Is Weak: Choose one Augmetic Enhancement. You do not suffer the penalties of being Wounded and gain +1 bonus die to Willpower Tests for every augmetic you have.",
        "tradition": "Ruthless Logic: You suffer a +2 DN penalty to Fellowship-based Tests against a target that does not have the IRON HANDS or ADEPTUS MECHANICUS Keywords."
    },
    "Raven Guard": {
        "legion": "XIX", "primarch": "Corvus Corax",
        "ability": "Master of Shadows: You may reroll Rank dice once per Stealth Test. Running, using a Jump Pack, or similar circumstances do not affect your Stealth Tests.",
        "tradition": "Dark Heritage: You are missing the Mucranoid and Bletcher's Gland implants and suffer a +1 DN penalty to Fellowship-based Tests against targets that could be frightened by your appearance."
    },
    "Salamanders": {
        "legion": "XVIII", "primarch": "Vulkan",
        "ability": "Promethean Cult: You may reroll Rank dice once per attack Test made with a weapon with the FIRE or MELTA Keywords. You may reroll Double Rank dice once each time you roll Determination against damage from FIRE or MELTA.",
        "tradition": "Infernal Inheritance: Whenever an ally within 30 metres is killed, the GM gains +1 Ruin. You suffer a +2 DN penalty to Fellowship-based Tests against targets that could be frightened by your appearance."
    },
    "Space Wolves": {
        "legion": "VI", "primarch": "Leman Russ",
        "ability": "Hunters Unleashed: You have the Acute Sense Talent and the Dual Wield Talent.",
        "tradition": "Savage Within: You cannot Fall Back."
    },
    "Ultramarines": {
        "legion": "XIII", "primarch": "Roboute Guilliman",
        "ability": "Tactical Versatility: You may Shift for Glory twice as part of a Test.",
        "tradition": "Pride of Ultramar: You start each session with 1 Wrath Point instead of 2."
    },
    "White Scars": {
        "legion": "V", "primarch": "Jaghatai Khan",
        "ability": "Lightning Assault: You may reroll Double Rank dice once each time you make a Pilot Test. You triple your Speed when you Charge.",
        "tradition": "Ritual Scarring: You suffer a +1 DN penalty to Fellowship-based Tests against targets that could be frightened by your appearance."
    },
}
CHAPTER_OPTIONS = list(CHAPTERS.keys()) + ["Other / Successor Chapter"]


# Wrath & Glory 2e: Rank is based on total XP earned and may only increase.
RANKS = {
    1: {"name": "Initiate", "min_xp": 0, "bonus": 1},
    2: {"name": "Veteran", "min_xp": 40, "bonus": 2},
    3: {"name": "Champion", "min_xp": 80, "bonus": 3},
}
MAX_TIER = 4

# Core Rulebook 2e, Corruption Levels table (p.285): the Level and its
# Corruption Test DN Modifier are derived from accumulated Corruption
# Points, which are tracked on the character like Wounds/Shock/Wrath.
# Level 5 (26+) has no DN Modifier because the character instead becomes a
# Chaos Spawn, lost to the GM's control.
CORRUPTION_LEVELS = [
    (0, "Pure", 0),
    (6, "Tarnished", 1),
    (12, "Contaminated", 2),
    (16, "Tainted", 3),
    (21, "Defiled", 4),
    (26, "Chaos Spawn", None),
]


def corruption_level_info(points):
    """Return the Corruption Level, its name, Test DN Modifier, and the
    points needed to reach the next Level, for a given Corruption Points total."""
    points = max(0, int(points or 0))
    level, name, dn_modifier, next_threshold = 0, "Pure", 0, CORRUPTION_LEVELS[1][0]
    for i, (start, lvl_name, mod) in enumerate(CORRUPTION_LEVELS):
        if points >= start:
            level, name, dn_modifier = i, lvl_name, mod
            next_threshold = CORRUPTION_LEVELS[i + 1][0] if i + 1 < len(CORRUPTION_LEVELS) else None
    return {"level": level, "name": name, "dn_modifier": dn_modifier, "next_threshold": next_threshold, "points": points}

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
    "Ganger": {"tier": 1, "species": "Human", "xp": 2, "faction": "Scum"},
    "Corsair": {"tier": 1, "species": "Aeldari", "xp": 16, "faction": "Aeldari"},
    "Boy": {"tier": 1, "species": "Ork", "xp": 26, "faction": "Orks"},
    "Sister of Battle": {"tier": 2, "species": "Human", "xp": 64, "faction": "Adepta Sororitas"},
    "Sanctioned Psyker": {"tier": 2, "species": "Human", "xp": 32, "faction": "Adeptus Astra Telepathica"},
    "Skitarius": {"tier": 2, "species": "Human", "xp": 28, "faction": "Adeptus Mechanicus"},
    "Death Cult Assassin": {"tier": 2, "species": "Human", "xp": 36, "faction": "Adeptus Ministorum"},
    "Tempestus Scion": {"tier": 2, "species": "Human", "xp": 52, "faction": "Astra Militarum"},
    "Rogue Trader": {"tier": 2, "species": "Human", "xp": 36, "faction": "Rogue Trader Dynasties"},
    "Scavvy": {"tier": 2, "species": "Human", "xp": 16, "faction": "Scum"},
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
    "Primaris Intercessor": {"tier": 4, "species": "Primaris Astartes", "xp": 300, "faction": "Adeptus Astartes"},
}

# ============================================================
#  BESTIARY (Core Rulebook 2e, "Bestiary" chapter, p.322+)
# ============================================================
# Registered into the same ARCHETYPES/ARCHETYPE_PACKAGES/ARCHETYPE_STARTING_WARGEAR
# registries as Player Archetypes so the Generic NPC mob generator (Combat tab)
# can build them through the exact same pipeline. Every name ends in
# "(Bestiary)" so it is never confused with a Player-facing Archetype in any
# dropdown that lists them together.
# The Bestiary format (p.323) prints each Skill as a single combined dice pool
# (Skill Rating + linked Attribute Rating already added together), so the
# Skill Rating stored below is back-solved as pool - attribute. Defence,
# Resilience, Wounds, and Shock are derived from this system's normal
# Attribute-formula instead of the printed flat numbers, per the book itself
# (p.322): "Their statistics ... rather than strictly following the same
# mechanics used to build characters", so some drift from the exact printed
# numbers is expected and left to the Magister to tweak.
_BESTIARY_ENTRIES = [
    # (name, tier, species, faction, attributes[S,T,A,I,W,Int,Fel], skill pools{name: pool}, starting wargear[], abilities text)
    ("Imperial Citizen", 1, "Human", "The Imperium",
     [2, 2, 3, 2, 3, 1, 2], {"Awareness": 3}, [],
     "ACTION: Unarmed 2 +1 ED / Range 1. COMPLICATION: Cheap Augmetic, an augmetic malfunctions; Hindered "
     "until repaired (DN 3 Tech). DETERMINATION: Spend 1 Ruin to roll 2d6. Default Skill Pool (unlisted "
     "Skills): 4. (Bestiary, Imperial Threats, Core Rulebook 2e)"),
    ("Astra Militarum Trooper", 1, "Human", "Astra Militarum",
     [3, 3, 3, 3, 2, 1, 2], {"Awareness": 5, "Ballistic Skill": 5}, ["Lasgun", "Frag Grenade", "Knife", "Flak Armour"],
     "ACTION: Lasgun 7 +1 ED / Range 12-24-36 / Salvo 2 / Rapid Fire (1), Reliable. Frag Grenade (1 Ammo) "
     "10 +4 ED / Range 12 / Blast (6). Knife or Bayonet 5 +2 ED / Range 1. DETERMINATION: Spend 1 Ruin to "
     "roll 3d6. Default Skill Pool: 4. (Bestiary, Imperial Threats, Core Rulebook 2e)"),
    ("Tactical Space Marine", 3, "Adeptus Astartes", "Adeptus Astartes",
     [7, 5, 5, 5, 4, 4, 2], {"Awareness": 9, "Ballistic Skill": 10, "Weapon Skill": 9},
     ["Aquila Mk VII Power Armour", "Boltgun", "Astartes Combat Knife"],
     "BONUSES: Know No Fear (reroll failed Resolve Test dice). Space Marine Implants. Champion (3 personal "
     "Ruin). ACTION: Boltgun 10 +1 ED / Range 12-24-36 / Salvo 2 / Brutal, Rapid Fire (2). Astartes Combat "
     "Knife 10 +2 ED / Range 1 / Reliable. RUIN: Angel of Death, spend 1 Ruin to add the Tier in ED to all "
     "attacks this Round. DETERMINATION: Spend 1 Ruin to roll 6d6. Default Skill Pool: 7. "
     "(Bestiary, Imperial Threats, Core Rulebook 2e)"),
    ("Enforcer", 1, "Human", "The Imperium",
     [3, 3, 3, 3, 3, 3, 3], {"Awareness": 6, "Intimidation": 7, "Investigation": 6, "Weapon Skill": 6},
     ["Combat Shotgun", "Shock Maul", "Flak Armour"],
     "BONUSES: Brutal Discipline (+2 bonus dice vs. SCUM/HERETIC). BATTLECRY: Freeze, Scum!, Intimidation "
     "Interaction Attack against 2 targets, no penalty. ACTION: Combat Shotgun 10 +1 ED / Range 6-12-18 / "
     "Salvo 2 / Assault, Rapid-Fire (1), Spread. Shock Maul 7 +4 ED / AP -1 / Range 1 / Agonising, Brutal. "
     "DETERMINATION: Spend 1 Ruin to roll 5d6. Default Skill Pool: 5. (Bestiary, Imperial Threats, Core Rulebook 2e)"),
    ("Chrono Gladiator", 2, "Human", "Scum",
     [4, 4, 2, 4, 3, 2, 1], {"Awareness": 4}, ["Power Claw"],
     "ACTION: Power Claw 13 +3 ED / AP -2 / Range 1 / Brutal, Unwieldy (2). WRATH: Borrowed Time, Free "
     "Action attack against any target in range. REACTION: Combat Stimms, once per round, suffer 1 Shock "
     "to take an immediate Combat Action. DETERMINATION: Spend 1 Ruin to roll 4d6. Default Skill Pool: 7. "
     "(Bestiary, Imperial Threats, Core Rulebook 2e)"),
    ("Mutant", 1, "Human", "Scum",
     [4, 3, 3, 4, 3, 2, 2], {"Weapon Skill": 6}, ["Industrial Bludgeon"],
     "BONUSES: Mutative, whenever this Threat deals a Wound, the GM gains +1 Ruin. ACTION: Industrial "
     "Bludgeon 8 +2 ED / Range 1 / Brutal, Unwieldy. WRATH: Sticky Fingers. REACTION: Desperation. "
     "DETERMINATION: Spend 1 Ruin to roll 3d6. Default Skill Pool: 5. (Bestiary, Imperial Threats, Core Rulebook 2e)"),
    ("Scum", 1, "Human", "Scum",
     [2, 3, 3, 3, 2, 1, 2], {"Awareness": 6, "Stealth": 7, "Weapon Skill": 6}, ["Autopistol", "Combat Knife"],
     "ACTION: Autopistol 7 +1 ED / Range 6-12-18 / Salvo 2 / Pistol. Combat Knife 4 +2 ED / Range 1. "
     "BATTLECRY: Without Honour, first round, may substitute Stealth for Weapon/Ballistic Skill Tests. "
     "DETERMINATION: Spend 1 Ruin to roll 3d6. Default Skill Pool: 5. (Bestiary, Imperial Threats, Core Rulebook 2e)"),
    ("Combat Servitor", 2, "Servitor", "Adeptus Mechanicus",
     [4, 2, 2, 2, 1, 1, 1], {"Weapon Skill": 5}, ["Servo Arm"],
     "BONUSES: Iron Soul, unaffected by mind-affecting abilities, never needs a Resolve Test. Printed Shock "
     "is '-' (Unstoppable, never suffers Shock damage). ACTION: Servo Arm 9 +2 ED / AP -3 / Range 1 / Brutal, "
     "Unwieldy (2). COMPLICATION: Error, Exhausted for 1 Round. DETERMINATION: Spend 1 Ruin to roll 3d6. "
     "Default Skill Pool: 4. (Bestiary, Imperial Threats, Core Rulebook 2e)"),
    ("Servo-Skull", 1, "Servitor", "Adeptus Mechanicus",
     [1, 1, 2, 4, 2, 3, 2], {"Awareness": 6, "Stealth": 7}, [],
     "BONUSES: Iron Soul. Assistant, Elite/Adversary allies within 10m gain +2 bonus dice to Skill Tests. "
     "Printed Shock is '-' (Unstoppable). ACTION: Skull Bash 3 +1 ED / Range 1. Flight, Speed 10, Size Tiny. "
     "DETERMINATION: Spend 1 Ruin to roll 2d6. Default Skill Pool: 5. (Bestiary, Imperial Threats, Core Rulebook 2e)"),
    ("Cultist", 1, "Cultista do Caos", "Chaos",
     [2, 3, 2, 3, 3, 2, 3], {"Awareness": 4, "Deception": 5, "Stealth": 5, "Weapon Skill": 5},
     ["Autopistol", "Knife"],
     "BONUSES: Devotion, GM gains 1 Ruin whenever a Cultist is slain by a Critical Hit. ACTION: Shoot and "
     "Stab (no Multi-Action penalty for Autopistol + Knife). Autopistol 7 +1 ED / Range 6-12-18 / Salvo 2 / "
     "Pistol. Knife 4 +2 ED / Range 1. DETERMINATION: Spend 1 Ruin to roll 3d6. Default Skill Pool: 3. "
     "(Bestiary, Heretical Threats, Core Rulebook 2e)"),
    ("Cult Leader", 3, "Cultista do Caos", "Chaos",
     [3, 4, 3, 4, 5, 4, 4], {"Awareness": 7, "Deception": 7, "Intimidation": 7, "Persuasion": 8, "Stealth": 6, "Weapon Skill": 7},
     ["Autopistol", "Chainsword"],
     "BONUSES: Herald of Ruin, Champion (1 personal Ruin), Priest of the Dark Gods (+2 bonus dice to "
     "Interaction Attacks). BATTLECRY: Kneel Before the Dark Gods! ACTION: Autopistol 7 +1 ED / Range "
     "6-12-18 / Salvo 2 / Pistol. Chainsword 8 +4 ED / Range 1 / Brutal, Parry. RUIN: Kill Them ALL! "
     "DETERMINATION: Spend 1 Ruin to roll 4d6. Default Skill Pool: 6. (Bestiary, Heretical Threats, Core Rulebook 2e)"),
    ("Rogue Psyker", 3, "Cultista do Caos", "Chaos",
     [2, 3, 2, 5, 5, 4, 2], {"Awareness": 6, "Psychic Mastery": 8}, ["Laspistol"],
     "BONUSES: Champion (2 personal Ruin), Warp Touched (bonus Wrath dice on Psychic Mastery Tests equal "
     "to Tier). ACTION: Maleficarum (Smite or a Maleficarum power). Laspistol 7 +1 ED / Range 6-12-18 / "
     "Salvo 1 / Pistol, Reliable. RUIN: Psychic Storm. DETERMINATION: Spend 1 Ruin to roll 3d6. Default "
     "Skill Pool: 5. (Bestiary, Heretical Threats, Core Rulebook 2e)"),
    ("Possessed Mortal", 3, "Cultista do Caos", "Chaos",
     [5, 4, 2, 4, 3, 4, 3], {"Awareness": 9, "Weapon Skill": 7}, [],
     "BONUSES: Champion (2 personal Ruin). BATTLECRY: Frightful Form (DN 3 Fear Test). ACTION: Horrifying "
     "Tendril 11 +2 ED / AP -2 / Range 4. DETERMINATION: Daemonic Determination, spend 1 Ruin to roll 4d6; "
     "can roll against Mortal Wounds, negated Wounds are ignored instead of becoming Shock. ANNIHILATION: "
     "Burnt Body, Warp Explosion 5 +5 ED / Agonising, Blast (6). Default Skill Pool: 6. "
     "(Bestiary, Heretical Threats, Core Rulebook 2e)"),
    ("Chaos Space Marine", 4, "Chaos Space Marine", "Chaos",
     [8, 6, 5, 5, 4, 3, 2], {"Awareness": 9, "Ballistic Skill": 8, "Weapon Skill": 8},
     ["Bolt Pistol", "Chainsword", "Mark V Power Armour"],
     "BONUSES: Architect of Ruin (GM gains 1 Ruin at the start of each of this Threat's turns), Champion "
     "(1 personal Ruin), Mark of Chaos, Space Marine Implants. ACTION: Bolt Pistol 10 +1 ED / Range 6-12-18 "
     "/ Salvo 1 / Brutal, Pistol. Chainsword 13 +4 ED / Range 1 / Brutal, Parry. RUIN: Veteran of the Long "
     "War, add the Tier as ED to all attacks this Round. DETERMINATION: Spend 1 Ruin to roll 6d6. Default "
     "Skill Pool: 5. (Bestiary, Heretical Threats, Core Rulebook 2e)"),
    ("Possessed Chaos Space Marine", 4, "Chaos Space Marine", "Chaos",
     [9, 8, 6, 6, 5, 5, 1], {"Awareness": 9, "Ballistic Skill": 9, "Weapon Skill": 9}, ["Mark V Power Armour"],
     "BONUSES: Architect of Ruin, Champion (4 personal Ruin), Writhing Tentacles (Multi-Attack all Engaged "
     "enemies without a DN penalty). BATTLECRY: Sea of Mutations (apply a Severe Mutation at combat start). "
     "ACTION: Horrifying Mutations 13 +2 ED / AP -2 / Range 1. RUIN: Veteran of the Long War. DETERMINATION: "
     "Daemonic Determination, spend 1 Ruin to roll 9d6. ANNIHILATION: Painful Lessons (GM gains 2 Ruin on "
     "death). Default Skill Pool: 5. (Bestiary, Heretical Threats, Core Rulebook 2e)"),
    ("Bloodletter", 3, "Daemon de Khorne", "Chaos",
     [7, 6, 3, 4, 3, 3, 3], {"Awareness": 9, "Weapon Skill": 10}, [],
     "BONUSES: Locus of Fury, anyone meleeing within 2m may reroll 1s on Weapon Skill Tests. Printed Shock "
     "is '-' (Unstoppable). BATTLECRY: Frightful Form. ACTION: Hellblade 13 +2 ED / AP -3 / Range 1 / "
     "Brutal, Parry. WRATH: Blood for the Blood God! (inflicts Bleeding). DETERMINATION: Daemonic "
     "Determination, spend 1 Ruin to roll 6d6. Default Skill Pool: 5. (Bestiary, Daemonic Threats, Core Rulebook 2e)"),
    ("Daemonette", 3, "Daemon de Slaanesh", "Chaos",
     [5, 4, 7, 7, 4, 4, 6], {"Awareness": 9, "Deception": 9, "Persuasion": 9, "Weapon Skill": 9}, [],
     "BONUSES: Allure of Slaanesh, attacks against Daemonettes use Willpower instead of Agility/Initiative. "
     "Printed Shock is '-' (Unstoppable). BATTLECRY: Disquieting Creature & Quicksilver Swiftness (DN 3 Fear "
     "Test; acts first as though Seizing the Initiative). ACTION: Piercing Claws 11 +2 ED / AP -1 / Range 1 "
     "/ Parry, Penetrating (3). DETERMINATION: Daemonic Determination, spend 1 Ruin to roll 4d6. Default "
     "Skill Pool: 8. (Bestiary, Daemonic Threats, Core Rulebook 2e)"),
    ("Pink Horror", 3, "Daemon de Tzeentch", "Chaos",
     [3, 3, 3, 4, 4, 4, 4], {"Awareness": 9, "Psychic Mastery": 9, "Weapon Skill": 9}, [],
     "Printed Shock is '-' (Unstoppable). BATTLECRY: Frightful Form. ACTION: Coruscating Flames 9 +1 ED / "
     "Range 12-24-36 / Salvo 1 / Assault, Inflicts (On Fire), Spread. Magical Claws 6 +2 ED / Range 1. "
     "DETERMINATION: Daemonic Determination, spend 1 Ruin to roll 3d6. ANNIHILATION: Split, becomes two "
     "Blue Horrors. Default Skill Pool: 8. (Bestiary, Daemonic Threats, Core Rulebook 2e)"),
    ("Blue Horror", 3, "Daemon de Tzeentch", "Chaos",
     [3, 3, 3, 4, 4, 4, 4], {"Awareness": 7, "Psychic Mastery": 8, "Weapon Skill": 8}, [],
     "Printed Wounds: 3 (uses Pink Horror's Attributes with lower Skills). ACTION: Scrabbling Claws 5 +2 ED "
     "/ Range 1. ANNIHILATION: Split, becomes two Brimstone Horrors. Default Skill Pool: 7. "
     "(Bestiary, Daemonic Threats, Core Rulebook 2e)"),
    ("Brimstone Horror", 3, "Daemon de Tzeentch", "Chaos",
     [3, 3, 3, 4, 4, 4, 4], {"Awareness": 5, "Psychic Mastery": 7, "Weapon Skill": 7}, [],
     "Printed Wounds: 1 (uses Pink Horror's Attributes with lower Skills). ACTION: Scrabbling Claws 4 +1 ED "
     "/ Range 1. Default Skill Pool: 6. (Bestiary, Daemonic Threats, Core Rulebook 2e)"),
    ("Plaguebearer", 3, "Daemon de Nurgle", "Chaos",
     [4, 8, 3, 4, 3, 3, 1], {"Awareness": 7, "Weapon Skill": 9}, [],
     "BONUSES: Cloud of Flies, counts as Full Cover at all times. Printed Shock is '-' (Unstoppable). "
     "BATTLECRY: Frightful Form. ACTION: Plaguesword 11 +2 ED / Range 1 / Inflict (Poison 7), Parry. "
     "DETERMINATION: Disgustingly Resilient, no Ruin cost to roll Determination, roll 7d6; can roll "
     "against Mortal Wounds. Default Skill Pool: 8. (Bestiary, Daemonic Threats, Core Rulebook 2e)"),
    ("Poxwalker", 1, "Human", "Chaos",
     [4, 3, 2, 2, 1, 1, 1], {"Awareness": 3, "Weapon Skill": 5}, [],
     "BONUSES: Mindless, automatically passes Resolve Tests. ACTION: Infectious Fists and Teeth 6 +1 ED / "
     "Range 1 / Inflicts (Poison 3). DETERMINATION: Spend 1 Ruin to roll 3d6. Default Skill Pool: 3. "
     "(Bestiary, Daemonic Threats, Core Rulebook 2e)"),
    ("Chaos Spawn", 3, "Fera", "Chaos",
     [5, 6, 5, 4, 1, 1, 1], {"Awareness": 6, "Weapon Skill": 9}, [],
     "BONUSES: Architect of Ruin, Champion. BATTLECRY: Terrifying (DN 5 Terror Test). ACTION: Hideous "
     "Mutations, roll 1d3 each turn: 1) Razor Claw 12 +3 ED / AP -4 / Range 1; 2) Grasping Tendrils 12 +3 "
     "ED / AP -2 / Range 4; 3) Dripping Poison 12 +3 ED / AP -2 / Inflict (Poison 7) / Range 1. "
     "DETERMINATION: Spend 1 Ruin to roll 6d6. Size Large. Default Skill Pool: 5. "
     "(Bestiary, Daemonic Threats, Core Rulebook 2e)"),
    ("Ork Boy", 1, "Ork", "Orks",
     [4, 4, 2, 3, 1, 1, 1], {"Awareness": 4, "Ballistic Skill": 4, "Weapon Skill": 7},
     ["Slugga", "Choppa", "Frag Grenade"],
     "BONUSES: 'Ere We Go!, +2 damage to melee attacks if Engaged at the start of its Turn. BATTLECRY: Get "
     "Stuck In! (Charge + DN 3 Fear Test on a hit). ACTION: Slugga 10 +1 ED / Range 6-12-18 / Salvo 1 / "
     "Pistol, Waaagh! Choppa 7 +3 ED / Range 1 / Reliable, Waaagh! Stikkbombz (2) 9 +5 ED / Range 16 / Blast "
     "(6). DETERMINATION: Spend 1 Ruin to roll 4d6. Default Skill Pool: 5. (Bestiary, Ork Threats, Core Rulebook 2e)"),
    ("Kommando (Ork)", 2, "Ork", "Orks",
     [4, 4, 4, 3, 2, 2, 1], {"Awareness": 6, "Ballistic Skill": 4, "Cunning": 6, "Stealth": 8, "Survival": 7, "Weapon Skill": 7},
     ["Slugga", "Choppa"],
     "BATTLECRY: Sneaky Gitz, first round of an ambush, may use Stealth pool (8) for any Test. ACTION: "
     "Slugga 10 +1 ED / Range 6-12-18 / Salvo 1 / Pistol, Waaagh! Choppa 7 +3 ED / Range 1 / Reliable, "
     "Waaagh! Stikkbombz (2) 9 +5 ED / Range 24 / Blast (6). DETERMINATION: Spend 1 Ruin to roll 4d6. "
     "Default Skill Pool: 5. (Bestiary, Ork Threats, Core Rulebook 2e)"),
    ("Ork Nob", 2, "Ork", "Orks",
     [6, 6, 2, 4, 3, 1, 2], {"Awareness": 4, "Ballistic Skill": 3, "Weapon Skill": 10}, ["Shoota", "'Eavy Armour"],
     "BONUSES: Champion (3 personal Ruin), 'Ere We Go! ACTION: Shoota 10 +1 ED / Range 9-18-27 / Salvo 2 / "
     "Assault, Waaagh! Big Choppa 11 +5 ED / AP -1 / Range 1 / Waaagh! Stikkbombz (2) 9 +5 ED / Range 20 / "
     "Blast (6). RUIN: I'm Da Boss! (allied ORKs within 10m gain +2 bonus dice to Weapon Skill Tests). "
     "REACTION: Orks Is Never Defeated. DETERMINATION: Spend 1 Ruin to roll 4d6. Default Skill Pool: 6. "
     "(Bestiary, Ork Threats, Core Rulebook 2e)"),
    ("Painboy", 2, "Ork", "Orks",
     [5, 4, 3, 4, 3, 2, 1], {"Awareness": 6, "Medicae": 6, "Weapon Skill": 8}, ["Power Claw"],
     "BONUSES: Champion (3 personal Ruin), Bionik Boyz, 'Ere We Go! ACTION: Wetwork (Dok's Tools + weapon "
     "attack, no Multi-Action penalty). Dok's Tools, DN 3 Medicae (Int) Test heals an ally. Power Claw 11 "
     "+5 ED / AP -3 / Range 1 / Brutal, Unwieldy (3), Waaagh! 'Urty Syringe 8 +2 ED / Rending (6). RUIN: "
     "Kwik Fix. DETERMINATION: Spend 1 Ruin to roll 4d6. Default Skill Pool: 5. (Bestiary, Ork Threats, Core Rulebook 2e)"),
    ("Grot", 1, "Ork", "Orks",
     [1, 1, 3, 3, 2, 2, 1], {"Awareness": 4, "Ballistic Skill": 2}, ["Autopistol", "Combat Knife"],
     "ACTION: Grot Blasta 7 +1 ED / Range 6-12-18 / Salvo 1 / Pistol. Combat Knife 3 +2 ED / Range 1. Size "
     "Small. DETERMINATION: Spend 1 Ruin to roll 3d6. Default Skill Pool: 4. (Bestiary, Ork Threats, Core Rulebook 2e)"),
    ("Killa Kan", 2, "Ork", "Orks",
     [10, 5, 3, 3, 3, 2, 1], {"Awareness": 6, "Ballistic Skill": 7, "Weapon Skill": 6}, [],
     "ACTION: Grotzooka 12 +2 ED / AP -1 / Range 9-18-36 / Salvo 1 / Brutal, Spread. Buzz Saw 17 +6 ED / AP "
     "-2 / Range 1 / Brutal, Unwieldy (2). REACTION: Kanned Rage (becomes Frenzied on an Icon). "
     "DETERMINATION: Spend 1 Ruin to roll 4d6. ANNIHILATION: Explosive, Killa Kan Explosion 12 +5 ED / "
     "Blast (10) on a Complication. Size Large. Default Skill Pool: 5. (Bestiary, Ork Threats, Core Rulebook 2e)"),
]

ARCHETYPE_STARTING_TALENTS = {}
BESTIARY_ARCHETYPE_NAMES = frozenset(f"{_e[0]} (Bestiary)" for _e in _BESTIARY_ENTRIES)
for _name, _tier, _species, _faction, _attrs7, _skill_pools, _wargear, _abilities in _BESTIARY_ENTRIES:
    _full_name = f"{_name} (Bestiary)"
    _attr_map = dict(zip(ATTRS, _attrs7))
    _skills_map = {sk: max(0, int(pool) - int(_attr_map.get(SKILLS[sk], 1))) for sk, pool in _skill_pools.items()}
    ARCHETYPES[_full_name] = {"tier": _tier, "species": _species, "xp": 0, "faction": _faction, "bestiary": True}
    ARCHETYPE_PACKAGES[_full_name] = {"attributes": _attr_map, "skills": _skills_map}
    ARCHETYPE_STARTING_WARGEAR[_full_name] = _wargear
    ARCHETYPE_STARTING_TALENTS[_full_name] = [{"name": f"{_name}, Bestiary Abilities", "effect": _abilities, "cost": 0}]

CORE_ARCHETYPE_NAMES = frozenset(ARCHETYPES.keys())

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


def derived_traits(ch, gear_mods=None):
    # Compute the equipped-Wargear modifiers once and thread them through,
    # instead of effective_attributes()/effective_skills() each recomputing
    # them independently, this function runs on every render of every
    # character sheet, popover and Combat row for every connected user.
    # Callers that already have gear_mods (most call sites do, since they
    # also need it for their own display) should pass it in to skip the
    # rebuild entirely.
    gear = gear_mods if gear_mods is not None else equipped_wargear_modifiers(ch)
    a, sk = effective_attributes(ch, gear), effective_skills(ch, gear)
    tier = int(ch.get("tier", 1)); base_armour = 0; sp = ch.get("species", "")
    T = int(a.get("Toughness", 1))
    I = int(a.get("Initiative", 1))
    Wil = int(a.get("Willpower", 1))
    Intl = int(a.get("Intellect", 1))
    Fel = int(a.get("Fellowship", 1))
    shield_armour = gear.get("shield_armour", 0)
    defence = I - 1 + gear.get("defence", 0) + shield_armour
    armour = base_armour + gear.get("armour", 0)
    resilience = T + 1 + armour + gear.get("resilience", 0) + shield_armour
    max_wounds = T + 2 * tier + (3 if sp == "Primaris Astartes" else 0) + gear.get("wounds", 0)
    max_shock = Wil + tier + gear.get("shock", 0)
    speed = species_speed(sp) + gear.get("speed", 0)
    return {
        "Defence": defence, "Resilience": resilience, "Soak": T,
        "Max Wounds": max_wounds, "Max Shock": max_shock, "Max Wrath": tier + gear.get("wrath", 0),
        "Determination": T, "Resolve": max(0, Wil - 1) + (1 if is_loyal_astartes(sp) else 0),
        "Conviction": Wil, "Passive Awareness": math.ceil((Intl + sk.get("Awareness", 0)) / 2),
        "Influence": max(0, Fel - 1), "Speed": speed,
        "Equipment Armour": armour,
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
        choices = ch.get("archetype_choices", {}) or {}
        selected = choices.get("skills", []) if isinstance(choices, dict) else []
        target = int(ap.get("skills_any_to", 0) or 0)
        if skill in selected and target:
            return max(species_base_skill(species, skill), target)
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

    # Psychic Powers cost XP just like Talents (the catalog carries a real
    # cost for each), but were never added here, available_xp then never
    # dropped after buying one, letting Powers be bought for effectively free.
    for p in ch.get("powers", []):
        try:
            total += int(p.get("cost", 0))
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
    # WAL + busy timeout allow the Magister and multiple Players to use the
    # same SQLite database concurrently without requiring page refreshes.
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def hash_pw(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100_000).hex()


def _ensure_columns(conn, table, cols):
    have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, ddl in cols.items():
        if name not in have:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def _load_custom_archetypes(conn=None):
    """Load campaign-defined Archetypes into the same runtime registries as Core Archetypes."""
    global ARCHETYPES, ARCHETYPE_PACKAGES, ARCHETYPE_ABILITIES, ARCHETYPE_STARTING_WARGEAR
    own = conn is None
    if own:
        conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM custom_archetypes ORDER BY name").fetchall()
        for r in rows:
            name = str(r["name"]).strip()
            if not name:
                continue
            def j(field, fallback):
                try:
                    value = json.loads(r[field] or fallback)
                    return value if value is not None else fallback
                except Exception:
                    return fallback
            attrs = j("attributes", "{}")
            skills = j("skills", "{}")
            gear = j("starting_wargear", "[]")
            keywords = j("keywords", "[]")
            ARCHETYPES[name] = {
                "tier": max(1, min(MAX_TIER, int(r["tier"] or 1))),
                "species": str(r["species"] or "Human"),
                "xp": int(r["xp"] or 0),
                "faction": str(r["faction"] or ""),
                "custom": True,
                "keywords": keywords if isinstance(keywords, list) else [],
            }
            ARCHETYPE_PACKAGES[name] = {
                "attributes": attrs if isinstance(attrs, dict) else {},
                "skills": skills if isinstance(skills, dict) else {},
            }
            ARCHETYPE_ABILITIES[name] = str(r["ability"] or "")
            ARCHETYPE_STARTING_WARGEAR[name] = gear if isinstance(gear, list) else []
    finally:
        if own:
            conn.close()


def _custom_archetype_rows():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM custom_archetypes ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_custom_archetype(data, archetype_id=None):
    name = str(data.get("name", "")).strip()
    if not name:
        return False, "Archetype name is required."
    if name in CORE_ARCHETYPE_NAMES:
        return False, "That name is reserved for a Core Rulebook Archetype."
    conn = get_conn()
    try:
        old_name = None
        if archetype_id:
            old = conn.execute("SELECT name FROM custom_archetypes WHERE id=?", (int(archetype_id),)).fetchone()
            if not old:
                return False, "Archetype not found."
            old_name = str(old["name"])
        attrs = data.get("attributes", {}) or {}
        skills = data.get("skills", {}) or {}
        gear = data.get("starting_wargear", []) or []
        keywords = data.get("keywords", []) or []
        payload = (name, int(data.get("tier", 1)), str(data.get("species", "Human")),
                   str(data.get("faction", "")), int(data.get("xp", 0)), str(data.get("ability", "")),
                   json.dumps(attrs, ensure_ascii=False), json.dumps(skills, ensure_ascii=False),
                   json.dumps(gear, ensure_ascii=False), json.dumps(keywords, ensure_ascii=False), now_iso())
        if archetype_id:
            conn.execute("""UPDATE custom_archetypes SET name=?,tier=?,species=?,faction=?,xp=?,ability=?,
                           attributes=?,skills=?,starting_wargear=?,keywords=?,updated_at=? WHERE id=?""", payload + (int(archetype_id),))
            if old_name and old_name != name:
                conn.execute("UPDATE characters SET archetype=? WHERE archetype=?", (name, old_name))
                for registry in (ARCHETYPES, ARCHETYPE_PACKAGES, ARCHETYPE_ABILITIES, ARCHETYPE_STARTING_WARGEAR):
                    registry.pop(old_name, None)
        else:
            conn.execute("""INSERT INTO custom_archetypes(name,tier,species,faction,xp,ability,attributes,skills,starting_wargear,keywords,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?)""", payload)
        conn.commit()
        _load_custom_archetypes(conn)
        return True, "Archetype saved."
    except sqlite3.IntegrityError:
        conn.rollback()
        return False, "An Archetype with that name already exists."
    except Exception as exc:
        conn.rollback()
        return False, f"Could not save Archetype: {exc}"
    finally:
        conn.close()



def delete_custom_archetype(archetype_id):
    conn = get_conn()
    try:
        row = conn.execute("SELECT name FROM custom_archetypes WHERE id=?", (int(archetype_id),)).fetchone()
        if not row:
            return False, "Archetype not found."
        name = str(row["name"])
        used = conn.execute("SELECT COUNT(*) FROM characters WHERE archetype=?", (name,)).fetchone()[0]
        if int(used) > 0:
            return False, "This Archetype is assigned to a character and cannot be deleted."
        conn.execute("DELETE FROM custom_archetypes WHERE id=?", (int(archetype_id),))
        conn.commit()
        for registry in (ARCHETYPES, ARCHETYPE_PACKAGES, ARCHETYPE_ABILITIES, ARCHETYPE_STARTING_WARGEAR):
            registry.pop(name, None)
        return True, "Archetype deleted."
    finally:
        conn.close()


def _custom_archetype_id_by_name(name):
    conn = get_conn()
    row = conn.execute("SELECT id FROM custom_archetypes WHERE name=?", (str(name),)).fetchone()
    conn.close()
    return int(row[0]) if row else None


def init_db():
    conn = get_conn(); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL, pw_hash TEXT NOT NULL, salt TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'player', created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS folders(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS characters(id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, kind TEXT DEFAULT 'player', name TEXT, chapter TEXT, species TEXT, archetype TEXT, creation_mode TEXT DEFAULT 'archetype', archetype_history TEXT DEFAULT '[]',
        tier INTEGER DEFAULT 2, starting_tier INTEGER DEFAULT 2, rank INTEGER DEFAULT 1, earned_xp INTEGER DEFAULT 0, other_xp INTEGER DEFAULT 0, faction TEXT DEFAULT '', keywords TEXT DEFAULT '[]', archetype_choices TEXT DEFAULT '{}',
        attributes TEXT, skills TEXT, talents TEXT, powers TEXT, wargear TEXT, armour INTEGER DEFAULT 0,
        cur_wounds INTEGER DEFAULT 0, cur_shock INTEGER DEFAULT 0, cur_wrath INTEGER DEFAULT 0, cur_ammo INTEGER DEFAULT 3,
        cur_corruption INTEGER DEFAULT 0, cur_wealth INTEGER DEFAULT 0, cur_faith INTEGER DEFAULT 0,
        notes TEXT, folder_id INTEGER, portrait BLOB, comms_on INTEGER DEFAULT 1, comms_changed_at TEXT, updated_at TEXT, revision INTEGER DEFAULT 0,
        temp_instance INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS campaign(id INTEGER PRIMARY KEY CHECK (id=1),
        name TEXT, tier INTEGER DEFAULT 2, ruin INTEGER DEFAULT 0, session_no INTEGER DEFAULT 1,
        spectator_code TEXT DEFAULT '', spectator_show_players INTEGER DEFAULT 0, spectator_show_monsters INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS log(id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, author TEXT, text TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS session_record(id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_no INTEGER, title TEXT, notes TEXT, base_xp INTEGER DEFAULT 0, npc_ids TEXT DEFAULT '[]',
        created_at TEXT, closed_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS session_award(id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL, character_id INTEGER NOT NULL, base_xp INTEGER DEFAULT 0, bonus_xp INTEGER DEFAULT 0,
        total_xp INTEGER DEFAULT 0, UNIQUE(session_id, character_id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS combatant(character_id INTEGER PRIMARY KEY, added_at TEXT, initiative_order INTEGER DEFAULT 9999, initiative_modifier INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS progression_undo(
        id INTEGER PRIMARY KEY AUTOINCREMENT, character_id INTEGER NOT NULL, action TEXT NOT NULL,
        snapshot TEXT NOT NULL, created_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS player_audit(
        id INTEGER PRIMARY KEY AUTOINCREMENT, character_id INTEGER NOT NULL, user_id INTEGER,
        actor TEXT NOT NULL, source TEXT NOT NULL, field TEXT NOT NULL,
        old_value TEXT, new_value TEXT, changed_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS craft_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, name TEXT NOT NULL,
        effect TEXT DEFAULT '', cost INTEGER DEFAULT 0, source TEXT DEFAULT '', source_url TEXT DEFAULT '',
        details TEXT DEFAULT '{}', active INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS custom_archetypes(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, tier INTEGER DEFAULT 1,
        species TEXT DEFAULT 'Human', faction TEXT DEFAULT '', xp INTEGER DEFAULT 0, ability TEXT DEFAULT '',
        attributes TEXT DEFAULT '{}', skills TEXT DEFAULT '{}', starting_wargear TEXT DEFAULT '[]',
        keywords TEXT DEFAULT '[]', created_at TEXT, updated_at TEXT)""")
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
    c.execute("""CREATE TABLE IF NOT EXISTS combat_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT, session_no INTEGER, started_at TEXT, ended_at TEXT,
        rounds INTEGER DEFAULT 1, participants TEXT DEFAULT '[]')""")
    c.execute("""CREATE TABLE IF NOT EXISTS wargear_requisition(
        id INTEGER PRIMARY KEY AUTOINCREMENT, character_id INTEGER NOT NULL, source_craft_id INTEGER,
        name TEXT NOT NULL, effect TEXT DEFAULT '', details TEXT DEFAULT '{}', status TEXT DEFAULT 'pending',
        requested_at TEXT, resolved_at TEXT, resolved_by TEXT DEFAULT '')""")
    conn.commit()
    # migration: ensure columns exist in databases created by older versions
    _ensure_columns(conn, "campaign", {"name": "TEXT", "tier": "INTEGER DEFAULT 2",
                                       "ruin": "INTEGER DEFAULT 0", "session_no": "INTEGER DEFAULT 1",
                                       "spectator_code": "TEXT DEFAULT ''", "spectator_show_players": "INTEGER DEFAULT 0",
                                       "spectator_show_monsters": "INTEGER DEFAULT 0"})
    had_wealth_column = "cur_wealth" in {r[1] for r in conn.execute("PRAGMA table_info(characters)").fetchall()}
    _ensure_columns(conn, "characters", {
        "user_id": "INTEGER", "kind": "TEXT DEFAULT 'player'", "name": "TEXT", "chapter": "TEXT",
        "species": "TEXT", "archetype": "TEXT", "creation_mode": "TEXT DEFAULT 'archetype'", "archetype_history": "TEXT DEFAULT '[]'", "tier": "INTEGER DEFAULT 2", "starting_tier": "INTEGER DEFAULT 2", "rank": "INTEGER DEFAULT 1", "earned_xp": "INTEGER DEFAULT 0",
        "other_xp": "INTEGER DEFAULT 0", "faction": "TEXT DEFAULT ''", "keywords": "TEXT DEFAULT '[]'", "archetype_choices": "TEXT DEFAULT '{}'", "attributes": "TEXT", "skills": "TEXT", "talents": "TEXT", "powers": "TEXT",
        "wargear": "TEXT", "armour": "INTEGER DEFAULT 0", "cur_wounds": "INTEGER DEFAULT 0",
        "cur_shock": "INTEGER DEFAULT 0", "cur_wrath": "INTEGER DEFAULT 0", "cur_ammo": "INTEGER DEFAULT 3",
        "cur_corruption": "INTEGER DEFAULT 0", "cur_wealth": "INTEGER DEFAULT 0", "cur_faith": "INTEGER DEFAULT 0", "notes": "TEXT",
        "folder_id": "INTEGER", "portrait": "BLOB", "comms_on": "INTEGER DEFAULT 1",
        "comms_changed_at": "TEXT", "updated_at": "TEXT", "revision": "INTEGER DEFAULT 0",
        "temp_instance": "INTEGER DEFAULT 0"})
    if not had_wealth_column:
        # Core Rulebook 2e, p.38: "Your starting Wealth is equal to your
        # Tier." Existing characters migrating to this column all land on
        # the column's SQL default of 0, so backfill them once to the RAW
        # starting value instead of silently leaving everyone at 0 Wealth.
        conn.execute("UPDATE characters SET cur_wealth = tier")
        conn.commit()
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
    conn.commit()
    _load_custom_archetypes(conn)
    conn.close()


STANDARD_AMMO_CATALOG = {
    "PROJECTILE": "Projectile Ammo",
    "LAS": "Las Ammo",
    "FIRE": "Flame Ammo",
    "FLAME": "Flame Ammo",
    "BOLT": "Bolt Ammo",
    "PLASMA": "Plasma Ammo",
    "MELTA": "Melta Ammo",
    "SHURIKEN": "Shuriken Ammo",
}


def _weapon_ammo_keyword(wargear):
    """Pick the first standard Ammo type compatible with a ranged weapon."""
    for w in normalize_wargear(wargear):
        d = _gear_details_dict(w.get("details", {}))
        if str(d.get("category", "")).lower() in {"ammo", "grenade", "missile", "reload"}:
            continue
        keys = [str(x).upper() for x in (d.get("keywords", []) or [])]
        for key in keys:
            if key in STANDARD_AMMO_CATALOG:
                return key
        name = str(w.get("name", "")).lower()
        for key in STANDARD_AMMO_CATALOG:
            if key.lower() in name:
                return key
    return "PROJECTILE"


def starting_ammo_for_wargear(wargear, quantity=3):
    """Create the Core Rulebook's 3 starting Ammo points, using a compatible type by default."""
    keyword = _weapon_ammo_keyword(wargear)
    ammo_name = STANDARD_AMMO_CATALOG[keyword]
    try:
        catalog = list_craft_items("wargear")
        row = next((r for r in catalog if str(r.get("name", "")).strip().lower() == ammo_name.lower()), None)
    except Exception:
        row = None
    if row is None:
        return [{"name": ammo_name, "effect": "", "equipped": True, "quantity": int(quantity),
                 "details": {"category": "ammo", "stackable": True, "stack_group": keyword, "keywords": [keyword], "official": True}}]
    entry = _craft_character_add([], row, "wargear")
    if entry:
        entry[0]["quantity"] = int(quantity)
        entry[0].setdefault("details", {})["starting_ammo"] = True
    return normalize_wargear(entry)

def create_player(username, pw, creation_mode="archetype", tier=2, rank=1, species="", archetype=""):
    conn = get_conn(); c = conn.cursor()
    try:
        salt = secrets.token_hex(16)
        c.execute("INSERT INTO users(username,pw_hash,salt,role,created_at) VALUES(?,?,?,?,?)",
                  (username, hash_pw(pw, salt), salt, "player", now_iso()))
        uid = c.lastrowid
        tier = max(1, min(MAX_TIER, int(tier)))
        rank = max(1, min(3, int(rank)))
        if creation_mode == "advanced":
            # In Advanced Character Creation the Magister does not choose Species.
            # The Player selects Species on their character sheet.
            species = ""
            archetype = ""
        else:
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

        c.execute("""INSERT INTO characters(user_id,kind,name,chapter,species,archetype,faction,keywords,archetype_choices,creation_mode,tier,starting_tier,rank,earned_xp,other_xp,
                     attributes,skills,talents,powers,wargear,armour,cur_wounds,cur_shock,cur_wrath,cur_corruption,cur_wealth,notes,
                     comms_on,comms_changed_at)
                     VALUES(?, 'player', ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (uid, username, "", species, archetype, ARCHETYPES.get(archetype, {}).get("faction", "") if creation_mode == "archetype" else "", json.dumps([], ensure_ascii=False), json.dumps({}, ensure_ascii=False), creation_mode, tier, tier, rank, 0, 0, json.dumps(attrs),
                   json.dumps(skills), json.dumps([]), json.dumps([]), json.dumps(normalize_wargear((archetype_starting_wargear(archetype) if creation_mode == "archetype" else []) + starting_ammo_for_wargear(archetype_starting_wargear(archetype) if creation_mode == "archetype" else [])), ensure_ascii=False), 0, 0, 0, 0,
                   # Core Rulebook 2e, p.38: Corruption starts at 0, Wealth starts equal to Tier.
                   0, tier, "", 1, now_iso()))
        conn.commit(); return True, "Player recruited."
    except sqlite3.IntegrityError:
        return False, "That designation already exists."
    finally:
        conn.close()


def _npc_attrs_skills_gear(species, creation_mode, archetype):
    """Shared build logic for a fresh NPC: species + archetype packages applied
    to base attributes/skills, plus normalized starting Wargear/Ammo."""
    attrs = default_attributes()
    skills = default_skills()
    species_alias = {
        "Astra Militarum (Humano)": "Human",
        "Adepta Sororitas": "Human",
        "Inquisição": "Human",
        "Rogue Trader": "Human",
        "Aeldari (Asuryani)": "Aeldari",
    }
    sp = SPECIES_PACKAGES.get(species_alias.get(species, species), {})
    for attr, value in sp.get("attributes", {}).items():
        attrs[attr] = max(int(attrs.get(attr, 1)), int(value))
    for skill, value in sp.get("skills", {}).items():
        skills[skill] = max(int(skills.get(skill, 0)), int(value))

    ap = ARCHETYPE_PACKAGES.get(archetype, {})
    for attr, value in ap.get("attributes", {}).items():
        attrs[attr] = max(int(attrs.get(attr, 1)), int(value))
    for skill, value in ap.get("skills", {}).items():
        skills[skill] = max(int(skills.get(skill, 0)), int(value))

    starting_gear = archetype_starting_wargear(archetype) if creation_mode != "advanced" else []
    starting_gear = normalize_wargear(starting_gear + starting_ammo_for_wargear(starting_gear))
    # Bestiary entries (see ARCHETYPE_STARTING_TALENTS) carry their printed
    # Abilities/Bonuses/Actions as a single descriptive Talent, since those are
    # mostly conditional/activated effects rather than passive sheet modifiers.
    starting_talents = [dict(t) for t in ARCHETYPE_STARTING_TALENTS.get(archetype, [])]
    return attrs, skills, starting_gear, starting_talents


def _auto_spend_xp(attrs, skills, budget, spent_already, npc_ctx=None, max_talents_powers=2):
    """Greedily spends whatever is left of `budget` (after `spent_already`).

    If `npc_ctx` is given, first rolls up to `max_talents_powers` random
    Talents and/or Powers whose Keyword/Rank/Tier/Attribute requirements the
    mob already meets, the exact same eligibility rules a Player purchasing
    them would face (craft_keyword_match + _requirements_satisfied), then
    spends whatever XP remains on the cheapest next Attribute/Skill upgrade
    available, one point at a time, until nothing affordable remains. Used
    to quickly build combat-ready Generic NPCs that have "all their XP
    spent" without a specific manual build."""
    remaining = int(budget) - int(spent_already)
    bought_talents, bought_powers = [], []
    if remaining <= 0:
        return attrs, skills, bought_talents, bought_powers

    if npc_ctx is not None and max_talents_powers > 0:
        pool = list(list_craft_items("talent")) + list(list_craft_items("power"))
        random.shuffle(pool)
        for row in pool:
            if len(bought_talents) + len(bought_powers) >= max_talents_powers:
                break
            cost = int(row.get("cost", 0) or 0)
            if cost <= 0 or cost > remaining:
                continue
            probe = {**npc_ctx, "attributes": attrs, "skills": skills,
                     "talents": bought_talents, "powers": bought_powers}
            if not craft_keyword_match(probe, row):
                continue
            ok, _reason = _requirements_satisfied(probe, row)
            if not ok:
                continue
            kind = str(row.get("kind", "talent")).lower()
            kind = kind if kind in ("talent", "power") else "talent"
            entry = _build_craft_entry(dict(row), kind)
            (bought_powers if kind == "power" else bought_talents).append(entry)
            remaining -= cost

    attr_cap = max(ATTR_COST.keys())
    skill_cap = max(SKILL_COST.keys())
    while remaining > 0:
        best = None  # (step_cost, "attr"/"skill", key)
        for a in ATTRS:
            cur = int(attrs.get(a, 1))
            if cur >= attr_cap:
                continue
            step_cost = ATTR_COST.get(cur + 1, 10**9) - ATTR_COST.get(cur, 0)
            if step_cost <= remaining and (best is None or step_cost < best[0]):
                best = (step_cost, "attr", a)
        for s in SKILLS:
            cur = int(skills.get(s, 0))
            if cur >= skill_cap:
                continue
            step_cost = SKILL_COST.get(cur + 1, 10**9) - SKILL_COST.get(cur, 0)
            if step_cost <= remaining and (best is None or step_cost < best[0]):
                best = (step_cost, "skill", s)
        if best is None:
            break
        step_cost, kind, key = best
        if kind == "attr":
            attrs[key] = int(attrs.get(key, 1)) + 1
        else:
            skills[key] = int(skills.get(key, 0)) + 1
        remaining -= step_cost
    return attrs, skills, bought_talents, bought_powers


def create_npc(name, species, tier, creation_mode="archetype", rank=1, archetype=""):
    conn = get_conn()
    tier = max(1, min(MAX_TIER, int(tier)))
    rank = max(1, min(3, int(rank)))
    if creation_mode == "advanced":
        archetype = ""
    else:
        archetype = archetype if archetype in ARCHETYPES else default_archetype_for_species(species, tier)

    attrs, skills, starting_gear, starting_talents = _npc_attrs_skills_gear(species, creation_mode, archetype)
    faction = ARCHETYPES.get(archetype, {}).get("faction", "") if archetype else ""
    conn.execute("""INSERT INTO characters(user_id,kind,name,chapter,species,archetype,faction,keywords,archetype_choices,creation_mode,tier,starting_tier,rank,earned_xp,other_xp,
                    attributes,skills,talents,powers,wargear,armour,cur_wounds,cur_shock,cur_wrath,cur_corruption,cur_wealth,notes,
                    comms_on,comms_changed_at)
                    VALUES(NULL,'npc',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (name or "NPC", "", species, archetype, faction, json.dumps([], ensure_ascii=False), json.dumps({}, ensure_ascii=False), creation_mode, tier, tier, rank, 0, 0, json.dumps(attrs),
                  json.dumps(skills), json.dumps(starting_talents, ensure_ascii=False), json.dumps([]), json.dumps(starting_gear, ensure_ascii=False), 0, 0, 0, 0,
                  # Core Rulebook 2e, p.38: Corruption starts at 0, Wealth starts equal to Tier.
                  0, tier, "", 1, now_iso()))
    conn.commit(); conn.close()


def generic_npc_options():
    """Archetypes usable for quick disposable Generic NPC mobs (Magister-only combat filler)."""
    return list(ARCHETYPES.keys())


def create_generic_npcs(archetype, tier, quantity, spend_xp=True):
    """Instantiates `quantity` disposable NPC mobs of the given Archetype/Tier
    directly into the active combat encounter. They are flagged temp_instance=1:
    hidden from the normal roster and deleted automatically once combat ends,
    unless the Magister explicitly saves one from its character sheet
    (see save_temp_instance)."""
    if archetype not in ARCHETYPES:
        return []
    tier = max(1, min(MAX_TIER, int(tier)))
    quantity = max(1, min(20, int(quantity)))
    species = ARCHETYPES[archetype].get("species", "Human")
    faction = ARCHETYPES[archetype].get("faction", "")
    budget = starting_xp(tier)
    # Bestiary stat blocks are printed complete and tier-agnostic (p.322: "not
    # strictly following the same mechanics used to build characters"),
    # auto-spending leftover Tier XP on top of them would distort the intended
    # numbers, so it never applies to them regardless of the Magister's toggle.
    if archetype in BESTIARY_ARCHETYPE_NAMES:
        spend_xp = False

    conn = get_conn()
    prefix = f"{archetype} #"
    existing = conn.execute(
        "SELECT name FROM characters WHERE archetype=? AND temp_instance=1", (archetype,)
    ).fetchall()
    next_idx = 1
    for r in existing:
        nm = r["name"] or ""
        if nm.startswith(prefix):
            try:
                next_idx = max(next_idx, int(nm[len(prefix):].strip()) + 1)
            except Exception:
                pass

    ids = []
    for i in range(quantity):
        attrs, skills, starting_gear, starting_talents = _npc_attrs_skills_gear(species, "archetype", archetype)
        bought_powers = []
        if spend_xp:
            base_ch = {"species": species, "attributes": attrs, "skills": skills,
                       "creation_mode": "archetype", "archetype": archetype, "talents": [], "other_xp": 0}
            npc_ctx = {"species": species, "archetype": archetype, "faction": faction, "chapter": "",
                       "creation_mode": "archetype", "tier": tier, "rank": 1, "keywords": []}
            attrs, skills, bought_talents, bought_powers = _auto_spend_xp(
                attrs, skills, budget, xp_spent(base_ch), npc_ctx=npc_ctx, max_talents_powers=2)
            starting_talents = starting_talents + bought_talents
        name = f"{prefix}{next_idx + i}"
        cur = conn.execute("""INSERT INTO characters(user_id,kind,name,chapter,species,archetype,faction,keywords,archetype_choices,creation_mode,tier,starting_tier,rank,earned_xp,other_xp,
                        attributes,skills,talents,powers,wargear,armour,cur_wounds,cur_shock,cur_wrath,cur_corruption,cur_wealth,notes,
                        comms_on,comms_changed_at,temp_instance)
                        VALUES(NULL,'npc',?,?,?,?,?,?,?,'archetype',?,?,1,0,0,?,?,?,?,?,0,0,0,0,0,?,?,1,?,1)""",
                            (name, "", species, archetype, faction, json.dumps([], ensure_ascii=False), json.dumps({}, ensure_ascii=False),
                             tier, tier, json.dumps(attrs), json.dumps(skills), json.dumps(starting_talents, ensure_ascii=False),
                             json.dumps(bought_powers, ensure_ascii=False),
                             json.dumps(starting_gear, ensure_ascii=False), tier, "", now_iso()))
        ids.append(int(cur.lastrowid))
    conn.commit(); conn.close()
    for cid in ids:
        add_combat_participant(cid)
    return ids


def save_temp_instance(cid):
    """Turns a disposable Generic NPC (temp_instance=1) into a normal, permanent
    character sheet that survives combat ending and shows up on the roster."""
    conn = get_conn()
    conn.execute("UPDATE characters SET temp_instance=0 WHERE id=?", (int(cid),))
    conn.commit(); conn.close()


def purge_unsaved_temp_instances(character_ids=None):
    """Deletes still-disposable Generic NPCs (temp_instance=1), either a given
    set of character ids, or every one left in the database if none is given.
    Called when combat ends/clears so unsaved mobs don't linger forever."""
    conn = get_conn()
    if character_ids is None:
        conn.execute("DELETE FROM characters WHERE temp_instance=1")
    elif character_ids:
        qmarks = ",".join("?" * len(character_ids))
        conn.execute(f"DELETE FROM characters WHERE temp_instance=1 AND id IN ({qmarks})",
                     [int(x) for x in character_ids])
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
            entry = {"name": name, "effect": effect, "cost": cost}
            for k in ("craft_id", "source", "source_url", "details"):
                if k in t: entry[k] = t[k]
            out.append(entry)
    return out


def _gear_quantity_name(name):
    """Split legacy names such as '3 Frag Grenades' into quantity + base name."""
    import re
    m = re.match(r"^\s*(\d+)\s+(.+?)\s*$", str(name or ""))
    if m:
        base = m.group(2).strip()
        # Starting gear sometimes uses plural resource names ("3 Frag Grenades").
        if base.lower().endswith(" grenades"):
            base = base[:-1]
        elif base.lower().endswith(" missiles"):
            base = base[:-1]
        elif base.lower().endswith(" stikkbombs"):
            base = base[:-1]
        return int(m.group(1)), base
    return 1, str(name or "").strip()


def _gear_details_dict(value):
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            obj = json.loads(value)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


def _infer_stackable_gear(name, details=None):
    """Ammo, grenades and missiles are stack resources in Wrath & Glory."""
    d = _gear_details_dict(details)
    category = str(d.get("category", d.get("type", ""))).strip().lower()
    keywords = [str(x).strip().lower() for x in (d.get("keywords", []) or [])]
    text = str(name or "").lower()
    if d.get("stackable") is True:
        return True, str(d.get("stack_group") or name).strip()
    ammo_words = ("ammo", "ammunition", "bolt ammo", "las ammo", "flame ammo", "plasma ammo", "melta ammo", "shuriken ammo", "projectile ammo")
    explosive = "explosive" in keywords
    is_ammo = category in {"ammo", "ammunition", "reload"} or any(x in text for x in ammo_words)
    is_grenade = category in {"grenade", "missile", "grenades", "missiles"} or "grenade" in text or "missile" in text or "stikkbomb" in text
    if is_ammo:
        group = str(d.get("stack_group") or text.replace(" ammo", "").strip())
        return True, group
    if is_grenade:
        return True, str(d.get("stack_group") or text)
    return False, ""


def normalize_wargear(raw):
    """Normalize Wargear and merge stackable Ammo/Grenades/Missiles."""
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
    stack_index = {}
    for w in parsed:
        if isinstance(w, dict):
            raw_name = str(w.get("name", "")).strip()
            effect = str(w.get("effect", "")).strip()
            details = _gear_details_dict(w.get("details", {}))
            quantity = max(1, int(w.get("quantity", 1) or 1))
        else:
            raw_name, effect, details, quantity = str(w).strip(), "", {}, 1
        if not raw_name:
            continue

        legacy_qty, base_name = _gear_quantity_name(raw_name)
        if quantity == 1 and legacy_qty > 1:
            quantity = legacy_qty
        name = base_name if legacy_qty > 1 else raw_name
        stackable, group = _infer_stackable_gear(name, details)
        if stackable:
            details["stackable"] = True
            details["stack_group"] = group
            details["category"] = details.get("category") or ("ammo" if "ammo" in name.lower() else "grenade" if "grenade" in name.lower() or "stikkbomb" in name.lower() else "missile" if "missile" in name.lower() else details.get("category", ""))
            key = (int(w.get("craft_id", -1)) if isinstance(w, dict) and w.get("craft_id") not in (None, "") else -1, group.lower())
            if key in stack_index:
                out[stack_index[key]]["quantity"] = int(out[stack_index[key]].get("quantity", 1)) + quantity
                continue
        entry = {"name": name, "effect": effect, "equipped": bool(w.get("equipped", True)) if isinstance(w, dict) else True}
        entry["quantity"] = quantity
        entry["details"] = details
        for k in ("craft_id", "source", "source_url"):
            if isinstance(w, dict) and k in w:
                entry[k] = w[k]
        if stackable:
            stack_index[key] = len(out)
        out.append(entry)
    return out


def normalize_powers(raw):
    """Normalize Psychic Powers stored on characters."""
    if isinstance(raw, list):
        parsed = raw
    else:
        text = raw or "[]"
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = []
    out = []
    for p in parsed:
        if isinstance(p, dict):
            name = str(p.get("name", "")).strip()
            effect = str(p.get("effect", "")).strip()
            cost = int(p.get("cost", 0) or 0)
        else:
            name, effect, cost = str(p).strip(), "", 0
        if name:
            entry = {"name": name, "effect": effect, "cost": cost}
            for k in ("craft_id", "source", "source_url", "details"):
                if isinstance(p, dict) and k in p:
                    entry[k] = p[k]
            out.append(entry)
    return out


def sync_official_craft_catalog(force=False):
    """Craft data is campaign-local. No network synchronization is used."""
    st.session_state["craft_sync_done"] = True
    st.session_state["craft_sync_version"] = 6
    st.session_state["craft_sync_errors"] = []


def craft_details(row):
    details = row.get("details", {}) if isinstance(row, dict) else {}
    if isinstance(details, str):
        try: details = json.loads(details)
        except Exception: details = {}
    return details if isinstance(details, dict) else {}


def character_keywords(ch):
    """Return the Keywords currently possessed by a character.

    Wrath & Glory Keywords represent faction/nature, allegiance and specific
    sub-groups. Species and Archetype provide the normal starting Keywords;
    Chapter and explicit character choices can add more specific Keywords.
    """
    keys = set()
    species = str(ch.get("species", "") or "").strip()
    arch = str(ch.get("archetype", "") or "").strip()

    species_keywords = {
        "Human": {"Imperium"},
        "Abhuman": {"Imperium"},
        "Adeptus Astartes": {"Imperium", "Adeptus Astartes"},
        "Primaris Astartes": {"Imperium", "Adeptus Astartes", "Primaris"},
        "Aeldari": {"Aeldari", "Asuryani"},
        "Aeldari (Asuryani)": {"Aeldari", "Asuryani"},
        "Ork": {"Ork"},
        "Drukhari": {"Aeldari", "Drukhari"},
        "T'au": {"T'au"},
        "Necron": {"Necron"},
        "Tyranid": {"Tyranid"},
        "Genestealer": {"Genestealer"},
        "Chaos Space Marine": {"Chaos", "Adeptus Astartes"},
    }
    keys.update(species_keywords.get(species, set()))

    faction = str(ch.get("faction", "") or ARCHETYPES.get(arch, {}).get("faction", "") or "")
    faction_map = {
        "Adeptus Astartes": "Adeptus Astartes",
        "Adepta Sororitas": "Adepta Sororitas",
        "Adeptus Ministorum": "Adeptus Ministorum",
        "Astra Militarum": "Astra Militarum",
        "Inquisition": "Inquisition",
        "Adeptus Mechanicus": "Adeptus Mechanicus",
        "Aeldari": "Aeldari",
        "Orks": "Ork",
        "Rogue Trader Dynasties": "Rogue Trader",
        "Scum": "Scum",
        "Adeptus Astra Telepathica": "Adeptus Astra Telepathica",
    }
    if faction in faction_map:
        keys.add(faction_map[faction])

    # These are the normal Core Rulebook archetype-level Keywords represented
    # by the archetype/faction data already present in this application.
    archetype_keywords = {
        "Sister Hospitaller": {"Adepta Sororitas"},
        "Ministorum Priest": {"Adeptus Ministorum"},
        "Imperial Guard": {"Astra Militarum"},
        "Inquisitorial Acolyte": {"Inquisition"},
        "Inquisitorial Sage": {"Inquisition", "Adeptus Administratum"},
        "Ganger": {"Scum"},
        "Corsair": {"Aeldari", "Anhrathe", "Outcast"},
        "Boy": {"Ork"},
        "Sister of Battle": {"Adepta Sororitas"},
        "Sanctioned Psyker": {"Psyker", "Adeptus Astra Telepathica"},
        "Skitarius": {"Adeptus Mechanicus"},
        "Death Cult Assassin": {"Adeptus Ministorum"},
        "Tempestus Scion": {"Astra Militarum"},
        "Rogue Trader": {"Rogue Trader"},
        "Scavvy": {"Scum"},
        "Space Marine Scout": {"Adeptus Astartes"},
        "Ranger": {"Aeldari", "Asuryani", "Outcast"},
        "Kommando": {"Ork"},
        "Tech-Priest": {"Adeptus Mechanicus"},
        "Crusader": {"Adeptus Ministorum"},
        "Imperial Commissar": {"Astra Militarum"},
        "Desperado": {"Scum"},
        "Tactical Space Marine": {"Adeptus Astartes"},
        "Warlock": {"Aeldari", "Asuryani", "Psyker"},
        "Nob": {"Ork"},
        "Inquisitor": {"Inquisition"},
        "Primaris Intercessor": {"Adeptus Astartes", "Primaris"},
    }
    keys.update(archetype_keywords.get(arch, set()))
    custom_arch_keywords = ARCHETYPES.get(arch, {}).get("keywords", [])
    if isinstance(custom_arch_keywords, list):
        keys.update(str(x).strip() for x in custom_arch_keywords if str(x).strip())

    chapter = str(ch.get("chapter", "") or "").strip()
    if chapter and chapter != "Other / Successor Chapter":
        keys.add(chapter)

    # A custom list may be stored on a character by future campaign rules.
    explicit = ch.get("keywords", [])
    if isinstance(explicit, str):
        try:
            explicit = json.loads(explicit)
        except Exception:
            explicit = re.split(r",|;", explicit)
    if isinstance(explicit, list):
        keys.update(str(x).strip() for x in explicit if str(x).strip())

    return {k.strip().lower() for k in keys if str(k).strip()}


def _split_requirement_tokens(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(x).strip() for x in value if str(x).strip()]
    return [x.strip() for x in re.split(r",|;", str(value)) if x.strip()]


def _requirement_data(row):
    details = craft_details(row)
    req = details.get("requirements", {})
    if not isinstance(req, dict):
        req = {}
    if not req.get("prerequisites") and details.get("prerequisites"):
        req["prerequisites"] = str(details.get("prerequisites", ""))
    return req


def _check_prerequisites(ch, text, available):
    text = str(text or "").strip()
    if not text or text.lower() in {"none", "n/a", "-"}:
        return True, "Eligible"

    vals = _attribute_values(ch)
    rank = int(ch.get("rank", 1) or 1)
    tier = int(ch.get("tier", 1) or 1)

    parts = [x.strip() for x in re.split(r",|;", text) if x.strip()]
    for raw in parts:
        token = raw.strip()
        low = token.lower()

        if low.startswith("must not possess "):
            kw = low[len("must not possess "):].strip().replace("<", "").replace(">", "")
            if kw and _keyword_ok(kw, available):
                return False, f"Cannot possess Keyword: {token[len('must not possess '):].strip()}"
            continue

        if " or " in low:
            alternatives = [x.strip() for x in re.split(r"\s+or\s+", token, flags=re.I)]
            ok_alt = False
            for alt in alternatives:
                am = re.match(r"^(.+?)\s+(\d+)\+$", alt.strip())
                if am:
                    stat, minimum = am.group(1).strip(), int(am.group(2))
                    stat_key = stat.lower()
                    if stat_key == "ballistics skill": stat_key = "ballistic skill"
                    if vals.get(stat_key, 0) >= minimum or vals.get(stat.lower(), 0) >= minimum:
                        ok_alt = True; break
                else:
                    if _keyword_ok(alt.replace("<", "").replace(">", ""), available):
                        ok_alt = True; break
            if not ok_alt:
                return False, f"Requires one of: {token}"
            continue

        m = re.match(r"^(.+?)\s+(\d+)\+$", token)
        if m:
            stat = m.group(1).strip()
            minimum = int(m.group(2))
            stat_low = stat.lower()
            if stat_low == "rank":
                if rank < minimum: return False, f"Requires Rank {minimum}+"
            elif stat_low == "tier":
                if tier < minimum: return False, f"Requires Tier {minimum}+"
            elif stat_low in {"attribute", "skill"}:
                if max(vals.values() or [0]) < minimum:
                    return False, f"Requires any {stat} {minimum}+"
            elif vals.get(stat_low, 0) < minimum:
                # Accept the CRB spelling "Ballistics Skill" as Ballistic Skill.
                if stat_low == "ballistics skill" and vals.get("ballistic skill", 0) >= minimum:
                    continue
                return False, f"Requires {stat} {minimum}+"
            continue

        kw = token.replace("<", "").replace(">", "").strip()
        if not _keyword_ok(kw, available):
            return False, f"Requires Keyword: {token}"

    return True, "Eligible"


def _keyword_ok(token, available):
    token = str(token or "").strip().lower()
    if not token:
        return True
    aliases = {
        "astartes": "adeptus astartes",
        "space marine": "adeptus astartes",
        "ballistics skill": "ballistic skill",
    }
    canonical = aliases.get(token, token)
    return canonical in {str(x).strip().lower() for x in available}


def _attribute_values(ch):
    """Return current Attribute and Skill values for prerequisite checks."""
    values = {}
    for name, value in (ch.get("attributes", {}) or {}).items():
        values[str(name).strip().lower()] = int(value or 0)
    for name, value in (ch.get("skills", {}) or {}).items():
        key = str(name).strip().lower()
        if key == "ballistics skill":
            key = "ballistic skill"
        values[key] = int(value or 0)
    return values


def _requirements_satisfied(ch, row):
    req = _requirement_data(row)
    available = character_keywords(ch)

    for raw in _split_requirement_tokens(req.get("keywords_all", [])):
        token = raw.strip().lower().replace("<", "").replace(">", "")
        if "any of the following keywords:" in token:
            opts = re.split(r",|\bor\b", token.split("any of the following keywords:", 1)[1])
            if not any(_keyword_ok(part, available) for part in opts):
                return False, "Requires one of: " + ", ".join(x.strip() for x in opts if x.strip())
        elif " or " in token:
            if not any(_keyword_ok(part, available) for part in token.split(" or ")):
                return False, f"Requires one of: {raw}"
        elif not _keyword_ok(token, available):
            return False, f"Requires Keyword: {raw}"

    any_kw = _split_requirement_tokens(req.get("keywords_any", []))
    if any_kw and not any(_keyword_ok(x, available) for x in any_kw):
        return False, "Requires one of: " + ", ".join(any_kw)

    rank = int(ch.get("rank", 1) or 1)
    tier = int(ch.get("tier", 1) or 1)
    if rank < int(req.get("rank_min", 0) or 0):
        return False, f"Requires Rank {int(req['rank_min'])}+"
    if tier < int(req.get("tier_min", 0) or 0):
        return False, f"Requires Tier {int(req['tier_min'])}+"

    vals = _attribute_values(ch)
    for attr, minimum in (req.get("attributes", {}) or {}).items():
        if vals.get(str(attr).lower(), 0) < int(minimum):
            return False, f"Requires {attr} {int(minimum)}+"
    for skill, minimum in (req.get("skills", {}) or {}).items():
        skill_key = str(skill).lower()
        if skill_key == "ballistics skill": skill_key = "ballistic skill"
        if vals.get(skill_key, 0) < int(minimum):
            return False, f"Requires {skill} {int(minimum)}+"

    species = _split_requirement_tokens(req.get("species", []))
    if species and str(ch.get("species", "")).lower() not in {x.lower() for x in species}:
        return False, "Requires Species: " + ", ".join(species)
    archetypes = _split_requirement_tokens(req.get("archetypes", []))
    if archetypes and str(ch.get("archetype", "")).lower() not in {x.lower() for x in archetypes}:
        return False, "Requires Archetype: " + ", ".join(archetypes)

    if str(row.get("kind", "") if isinstance(row, dict) else "").lower() == "power":
        if "psyker" not in available:
            return False, "Requires Keyword: PSYKER"
        power_name = str(row.get("name", ""))
        pdetails = craft_details(row)
        pkw = {str(x).strip().lower() for x in (pdetails.get("keywords", []) or [])}
        if "aeldari" in pkw and "aeldari" not in available:
            return False, "Requires Keyword: AELDARI"
        prereq = str(pdetails.get("prerequisites", "") or "").strip()
        if prereq and prereq.lower() not in {"none", "n/a", "-"}:
            m = re.search(r"at least one other (.+?) power", prereq, flags=re.I)
            if m:
                discipline = m.group(1).strip().lower()
                owned_names = {str(x.get("name", "")).strip().lower() for x in normalize_powers(ch.get("powers", []))}
                known = {name.lower() for name, d in POWER_DISCIPLINES.items() if d.lower() == discipline}
                if not known:
                    known = {str(r.get("name", "")).lower() for r in list_craft_items("power") if str(craft_details(r).get("discipline", "")).lower() == discipline}
                if not (owned_names & known):
                    return False, f"Requires another {m.group(1).strip()} Power"
            elif not _keyword_ok(prereq, available):
                ok_text, reason_text = _check_prerequisites(ch, prereq, available)
                if not ok_text:
                    return False, reason_text

    owned = {str(t.get("name", "")).strip().lower() for t in normalize_talents(ch.get("talents", []))}
    for talent in _split_requirement_tokens(req.get("talents", [])):
        if talent.lower() not in owned:
            return False, f"Requires Talent: {talent}"

    # Validate only prerequisite clauses that are not represented by the
    # structured fields above. This avoids treating rulebook prose such as
    # "Any of the following Keywords" as an AND list.
    raw_prereq = str(req.get("prerequisites", "") or "").strip()
    if re.search(r"must not possess\s+(.+?)\s+keyword", raw_prereq, re.I):
        for forbidden in re.findall(r"must not possess\s+(.+?)\s+keyword", raw_prereq, re.I):
            if _keyword_ok(forbidden, available):
                return False, f"Cannot possess Keyword: {forbidden.strip()}"
    for required_talent in re.findall(r"(?:the\s+)?([^,;]+?)\s+Talent(?:\s|\)|,|;|$)", raw_prereq, re.I):
        name = required_talent.strip(" .(")
        if name and name.lower() not in owned:
            return False, f"Requires Talent: {name}"
    faith_match = re.search(r"at least\s+(\d+)\s+Faith", raw_prereq, re.I)
    if faith_match and int(ch.get("faith", 0) or 0) < int(faith_match.group(1)):
        return False, f"Requires {faith_match.group(1)} Faith"
    if "[MARK OF CHAOS]" in raw_prereq.upper() and not _keyword_ok("MARK OF CHAOS", available):
        return False, "Requires Keyword: MARK OF CHAOS"
    return True, "Eligible"

def talent_is_available(ch, row):
    ok, _ = _requirements_satisfied(ch, row)
    return ok

def craft_keyword_match(ch, row):
    available = character_keywords(ch)
    details = craft_details(row)
    explicit = {str(x).strip().lower() for x in (details.get("keywords", []) or []) if str(x).strip()}
    req = _requirement_data(row)
    req_all = {str(x).strip().lower() for x in _split_requirement_tokens(req.get("keywords_all", [])) if str(x).strip()}
    req_any = {str(x).strip().lower() for x in _split_requirement_tokens(req.get("keywords_any", [])) if str(x).strip()}
    if str(row.get("kind", "")).lower() == "power":
        if "psyker" not in available:
            return False
        factional = explicit & {"aeldari", "asuryani", "chaos"}
        return not factional or bool(factional & available)
    relevant = (explicit | req_all | req_any) - {"psychic", "kinetic", "auditory", "fire", "light"}
    species = {str(x).strip().lower() for x in _split_requirement_tokens(req.get("species", []))}
    actual_species = str(ch.get("species", "") or "").strip().lower()
    if species and actual_species in species:
        return True
    return not relevant or bool(relevant & available)

def craft_purchase_status(ch, row, available_xp):
    ok, reason = _requirements_satisfied(ch, row)
    cost = int(row.get("cost", 0) or 0)
    if not ok: return "red", reason
    if int(available_xp) < cost: return "orange", f"Requires {cost} XP; {int(available_xp)} XP available."
    return "green", "Available to purchase."

def craft_status_color(status):
    return {"green": "#2e7d32", "orange": "#ef6c00", "red": "#c62828"}.get(status, "#c62828")

def craft_status_text(status, reason):
    if status == "green":
        return "Available to purchase."
    return str(reason)

def craft_modifiers(row):
    """Return only automatic numeric modifiers granted by an equipped Wargear item.

    Armour Traits from the Core Rulebook are normalized here so every Wargear
    bonus has one source of truth and cannot be applied twice. Conditional text
    such as Cameleoline's cover/shadow bonus is deliberately not automatic.
    """
    details = craft_details(row)
    mods = {}
    raw = details.get("modifiers", {}) or {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            text = str(v).strip()
            if re.fullmatch(r"[+-]?\d+", text):
                mods[str(k).strip().lower()] = int(text)

    traits = details.get("traits", []) or []
    if isinstance(traits, str):
        traits = _req_list(traits)
    effect = str(row.get("effect", "") if isinstance(row, dict) else "")
    trait_text = ", ".join(str(x) for x in traits)
    if effect:
        m = re.search(r"traits?\s*:\s*(.+?)(?:\.|$)", effect, re.I)
        if m:
            trait_text += ", " + m.group(1)

    # Powered (X): gain X Strength while wearing the armour. Adds on top of
    # any manual Strength modifier above them (e.g. a homebrew item that is
    # both Powered and has an extra manual bonus), only duplicate mentions
    # of Powered within this same item's own Traits list are deduplicated
    # via max(), since those describe the same single rating, not two
    # independent sources.
    powered_ratings = [int(x) for x in re.findall(r"powered\s*\(\s*(\d+)\s*\)", trait_text, re.I)]
    if powered_ratings:
        mods["strength"] = mods.get("strength", 0) + max(powered_ratings)

    # Bulk (X): reduce Speed by X while the armour is worn. Same
    # add-on-top-of-manual, dedupe-only-within-itself treatment as Powered.
    bulk_ratings = [int(x) for x in re.findall(r"bulk\s*\(\s*(\d+)\s*\)", trait_text, re.I)]
    if bulk_ratings:
        mods["speed"] = mods.get("speed", 0) - max(bulk_ratings)

    # Shield: its AR is added to Defence and Resilience, rather than being
    # treated as ordinary body armour. Keep it separate to avoid double count.
    if re.search(r"(?:^|[,;])\s*shield\s*(?:[,;]|$)", trait_text, re.I):
        ar = mods.get("armour")
        if ar is not None:
            mods["shield_armour"] = max(mods.get("shield_armour", 0), int(ar))
            mods.pop("armour", None)

    if "armour" not in mods and "shield_armour" not in mods and details.get("armour_rating") not in (None, ""):
        try:
            numeric = re.search(r"[0-9]+", str(details.get("armour_rating")))
            if numeric:
                mods["armour"] = int(numeric.group(0))
        except Exception:
            pass
    return mods


def effective_attributes(ch, gear_mods=None):
    base = {str(k): int(v) for k, v in (ch.get("attributes", {}) or {}).items()}
    mods = gear_mods if gear_mods is not None else equipped_wargear_modifiers(ch)
    return {k: int(v) + int(mods.get(k.lower(), 0)) for k, v in base.items()}


def effective_skills(ch, gear_mods=None):
    base = {str(k): int(v) for k, v in (ch.get("skills", {}) or {}).items()}
    mods = gear_mods if gear_mods is not None else equipped_wargear_modifiers(ch)
    return {k: int(v) + int(mods.get(k.lower(), 0)) for k, v in base.items()}


def _owned_item_modifiers(owned_entry, catalog_by_id, catalog_by_name=None):
    """Resolve one owned Talent/Power/Wargear entry to its Automatic Sheet
    Modifiers, preferring the live catalog row (so a GM's later catalog
    edits apply retroactively) and falling back to the entry's own frozen
    details snapshot otherwise."""
    row = None
    try:
        cid = int(owned_entry.get("craft_id", -1) or -1)
        if cid > 0:
            row = catalog_by_id.get(cid)
    except Exception:
        row = None
    if row is None and catalog_by_name is not None:
        row = catalog_by_name.get(str(owned_entry.get("name", "")).strip().lower())
    if row is not None:
        return craft_modifiers(row)
    return craft_modifiers({"details": _gear_details_dict(owned_entry.get("details", {}))})


def equipped_wargear_modifiers(ch):
    """Aggregate every passive Automatic Sheet Modifier currently active on
    this character:
      - equipped Wargear (Traits like Powered/Bulk/Shield, Armour Rating,
        plus any manual modifier), only while equipped;
      - owned Talents, permanent the moment they are purchased, since
        Talents have no 'equipped' state;
      - known Psychic Powers, included for GM flexibility, but craft_view's
        Power editor warns that almost all Powers are activated/temporary
        and should not carry a modifier here.
    """
    mods = {}

    wargear_catalog = list_craft_items("wargear", active_only=False)
    wargear_by_id = {int(r["id"]): r for r in wargear_catalog}
    wargear_by_name = {str(r.get("name", "")).strip().lower(): r for r in wargear_catalog}
    for w in normalize_wargear(ch.get("wargear", [])):
        if not w.get("equipped", True):
            continue
        for k, v in _owned_item_modifiers(w, wargear_by_id, wargear_by_name).items():
            key = str(k).strip().lower()
            mods[key] = mods.get(key, 0) + int(v)

    talent_by_id = {int(r["id"]): r for r in list_craft_items("talent", active_only=False)}
    for t in normalize_talents(ch.get("talents", [])):
        for k, v in _owned_item_modifiers(t, talent_by_id).items():
            key = str(k).strip().lower()
            mods[key] = mods.get(key, 0) + int(v)

    power_by_id = {int(r["id"]): r for r in list_craft_items("power", active_only=False)}
    for p in normalize_powers(ch.get("powers", [])):
        for k, v in _owned_item_modifiers(p, power_by_id).items():
            key = str(k).strip().lower()
            mods[key] = mods.get(key, 0) + int(v)

    return mods

def assign_craft_to_character(cid, craft_id, kind, actor_name="", actor_user_id=None, source="Craft Assignment"):
    """Add one catalog Talent, Psychic Power or Wargear atomically to a character."""
    kind = str(kind).strip().lower()
    if kind not in ("talent", "power", "wargear"):
        return False, "Invalid catalog item type."
    column = {"talent": "talents", "power": "powers", "wargear": "wargear"}[kind]
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM characters WHERE id=?", (int(cid),)).fetchone()
        item = conn.execute("SELECT * FROM craft_items WHERE id=? AND kind=? AND active=1", (int(craft_id), kind)).fetchone()
        if row is None:
            return False, "Character not found."
        if item is None:
            return False, f"{kind.title()} item not found in the active campaign catalog."

        ch = _decode(row)
        current = normalize_talents(ch.get("talents", [])) if kind == "talent" else \
                  normalize_powers(ch.get("powers", [])) if kind == "power" else \
                  normalize_wargear(ch.get("wargear", []))
        old_value = list(current)

        entry = _build_craft_entry(dict(item), kind)
        updated = list(current)
        if kind in ("talent", "power"):
            if any(int(x.get("craft_id", -1) or -1) == int(craft_id) for x in updated):
                return True, f"{kind.title()} already assigned."
            updated.append(entry)
        else:
            existing = next((x for x in updated if int(x.get("craft_id", -1) or -1) == int(craft_id)), None)
            stackable = bool((entry.get("details", {}) or {}).get("stackable", False))
            if existing is not None and stackable:
                existing["quantity"] = int(existing.get("quantity", 1) or 1) + int(entry.get("quantity", 1) or 1)
            elif existing is not None:
                return True, "Wargear already assigned."
            else:
                updated.append(entry)
            updated = normalize_wargear(updated)

        if updated == current:
            return True, f"{kind.title()} already assigned."

        if kind == "wargear":
            item_details = _gear_details_dict(item["details"] if "details" in item.keys() else {})
            item_category = str(item_details.get("category", item_details.get("type", ""))).strip().lower()
            item_name = str(item["name"] or "")
            item_is_ammo = item_category in {"ammo", "ammunition", "reload"} or "ammo" in item_name.lower() or "cartridge" in item_name.lower() or "cartucho" in item_name.lower()
            if item_is_ammo:
                _, old_total = ammo_inventory(ch)
                _, new_total = ammo_inventory({**ch, "wargear": updated})
                if new_total > ammo_capacity(ch):
                    return False, f"Ammo capacity reached ({ammo_capacity(ch)} total Ammo)."

        new_revision = int(ch.get("revision", 0) or 0) + 1
        encoded = json.dumps(updated, ensure_ascii=False)
        cur = conn.execute(
            f"UPDATE characters SET {column}=?, updated_at=?, revision=? WHERE id=? AND revision=?",
            (encoded, now_iso(), new_revision, int(cid), int(ch.get("revision", 0) or 0))
        )
        if cur.rowcount != 1:
            conn.rollback()
            return False, "Concurrent change detected. The latest character version was not overwritten."
        conn.commit()

        if actor_user_id and actor_name:
            record_player_audit(cid, actor_user_id, actor_name, source, [(column, old_value, updated)])
        return True, f"{kind.title()} assigned."
    except Exception as exc:
        conn.rollback()
        return False, f"Could not assign {kind.title()}: {exc}"
    finally:
        conn.close()


def create_wargear_requisition(cid, name="", effect="", details=None, source_craft_id=None):
    """A Player asks for a piece of Wargear, either a brand-new item they
    describe themselves or one already in the catalog. It sits as 'pending'
    (visible on the Player's sheet in red, granting nothing) until the
    Magister resolves it on the Requisitions tab."""
    if source_craft_id:
        row = conn = None
        conn = get_conn()
        row = conn.execute("SELECT * FROM craft_items WHERE id=? AND kind='wargear' AND active=1", (int(source_craft_id),)).fetchone()
        conn.close()
        if not row:
            return False, "That catalog item no longer exists."
        name = row["name"]; effect = row["effect"] or ""; details = craft_details(row)
    else:
        if not str(name or "").strip():
            return False, "Name is required."
    conn = get_conn()
    conn.execute("""INSERT INTO wargear_requisition(character_id,source_craft_id,name,effect,details,status,requested_at)
                    VALUES(?,?,?,?,?, 'pending', ?)""",
                 (int(cid), int(source_craft_id) if source_craft_id else None, str(name).strip(),
                  str(effect or ""), json.dumps(details or {}, ensure_ascii=False), now_iso()))
    conn.commit(); conn.close()
    return True, "Requisition submitted for the Magister's review."


def list_requisitions(character_id=None, status=None):
    conn = get_conn()
    q = "SELECT * FROM wargear_requisition WHERE 1=1"
    args = []
    if character_id is not None:
        q += " AND character_id=?"; args.append(int(character_id))
    if status is not None:
        q += " AND status=?"; args.append(str(status))
    q += " ORDER BY id DESC"
    rows = conn.execute(q, args).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        try: d["details"] = json.loads(d.get("details") or "{}")
        except Exception: d["details"] = {}
        out.append(d)
    return out


def update_requisition_item(rid, name, effect, details):
    """The Magister may tidy up a Player's custom item before approving it."""
    conn = get_conn()
    conn.execute("UPDATE wargear_requisition SET name=?, effect=?, details=? WHERE id=? AND status='pending'",
                 (str(name).strip(), str(effect or ""), json.dumps(details or {}, ensure_ascii=False), int(rid)))
    conn.commit(); conn.close()


def delete_requisition(rid):
    conn = get_conn()
    conn.execute("DELETE FROM wargear_requisition WHERE id=?", (int(rid),))
    conn.commit(); conn.close()


def resolve_requisition(rid, approve, actor_name=""):
    """Approve or deny a pending Requisition.

    Approving a request for an existing catalog item just assigns it.
    Approving a brand-new item first registers it in the Wargear catalog
    (so it becomes available to everyone from then on, per the Magister's
    request), then assigns that new catalog entry to the requesting character.
    """
    conn = get_conn()
    row = conn.execute("SELECT * FROM wargear_requisition WHERE id=?", (int(rid),)).fetchone()
    conn.close()
    if not row:
        return False, "Requisition not found."
    if row["status"] != "pending":
        return False, "This Requisition was already resolved."
    cid = int(row["character_id"])
    if not approve:
        conn = get_conn()
        conn.execute("UPDATE wargear_requisition SET status='denied', resolved_at=?, resolved_by=? WHERE id=?",
                     (now_iso(), actor_name, int(rid)))
        conn.commit(); conn.close()
        return True, "Requisition denied."

    try:
        details = json.loads(row["details"] or "{}")
    except Exception:
        details = {}
    craft_id = row["source_craft_id"]
    if not craft_id:
        craft_id = save_craft_item({
            "kind": "wargear", "name": row["name"], "effect": row["effect"] or "",
            "source": "Player Requisition", "details": {**details, "custom": True, "official": False},
        })
    ok, msg = assign_craft_to_character(cid, craft_id, "wargear", source="Requisition Approved")
    if not ok:
        return False, msg
    conn = get_conn()
    conn.execute("UPDATE wargear_requisition SET status='approved', source_craft_id=?, resolved_at=?, resolved_by=? WHERE id=?",
                 (int(craft_id), now_iso(), actor_name, int(rid)))
    conn.commit(); conn.close()
    return True, "Requisition approved and added to the character's Wargear."


def adjust_wargear_quantity(cid, craft_id, delta, actor_name="", actor_user_id=None, source="Wargear Quantity Change", actor_role="gm"):
    """Atomically add/remove one stackable Wargear unit (Ammo/Grenade/Missile)."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM characters WHERE id=?", (int(cid),)).fetchone()
        item = conn.execute("SELECT * FROM craft_items WHERE id=? AND kind='wargear'", (int(craft_id),)).fetchone()
        if row is None or item is None:
            return False, "Character or Wargear item not found."
        ch = _decode(row)
        if actor_role == "player":
            if ch.get("kind") != "player" or int(ch.get("user_id") or -1) != int(actor_user_id or -2):
                return False, "Players can only edit their own character sheet."
        current = normalize_wargear(ch.get("wargear", []))
        # Standard and special Ammo share one carrying pool. Grenades/Missiles do not.
        item_details = _gear_details_dict(item["details"] if "details" in item.keys() else {})
        item_category = str(item_details.get("category", item_details.get("type", ""))).strip().lower()
        item_name = str(item["name"] or "")
        item_is_ammo = item_category in {"ammo", "ammunition", "reload"} or "ammo" in item_name.lower() or "cartridge" in item_name.lower() or "cartucho" in item_name.lower()
        if actor_role == "player" and int(delta) > 0 and not item_is_ammo:
            return False, "Players cannot add Wargear or consumables. Ask the Magister to assign it."
        if item_is_ammo and int(delta) > 0:
            _, ammo_total = ammo_inventory(ch)
            if ammo_total + int(delta) > ammo_capacity(ch):
                return False, f"Ammo capacity reached ({ammo_capacity(ch)} total Ammo). The Magister controls the character's maximum Ammo capacity."
        target = None
        for w in current:
            if int(w.get("craft_id", -1) or -1) == int(craft_id):
                target = w; break
        if target is None:
            if delta <= 0:
                return False, "This stack is not assigned to the character."
            current = _craft_character_add(current, dict(item), "wargear")
            target = next((w for w in current if int(w.get("craft_id", -1) or -1) == int(craft_id)), None)
            if target is None:
                return False, "Could not create the Wargear stack."
            if delta != 1:
                target["quantity"] = max(0, int(target.get("quantity", 1)) + int(delta) - 1)
        else:
            target["quantity"] = int(target.get("quantity", 1)) + int(delta)
        if int(target.get("quantity", 0)) <= 0:
            current = [w for w in current if w is not target]
        else:
            current = normalize_wargear(current)
        old = normalize_wargear(ch.get("wargear", []))
        new_revision = int(ch.get("revision", 0) or 0) + 1
        cur = conn.execute("UPDATE characters SET wargear=?,updated_at=?,revision=? WHERE id=? AND revision=?",
                           (json.dumps(current, ensure_ascii=False), now_iso(), new_revision, int(cid), int(ch.get("revision", 0) or 0)))
        if cur.rowcount != 1:
            conn.rollback(); return False, "Concurrent change detected."
        conn.commit()
        if actor_user_id and actor_name:
            record_player_audit(cid, actor_user_id, actor_name, source, [("wargear", old, current)])
        return True, "Wargear quantity updated."
    except Exception as exc:
        conn.rollback(); return False, f"Could not update Wargear quantity: {exc}"
    finally:
        conn.close()


def assign_wargear_to_character(cid, craft_id, actor_name="", actor_user_id=None):
    return assign_craft_to_character(cid, craft_id, "wargear", actor_name, actor_user_id, "Magister Wargear Assignment")


@st.cache_data(show_spinner=False)
def _cached_craft_items(kind, active_only):
    conn = get_conn()
    if kind:
        sql = "SELECT * FROM craft_items WHERE kind=?" + (" AND active=1" if active_only else "") + " ORDER BY name COLLATE NOCASE"
        rows = conn.execute(sql, (kind,)).fetchall()
    else:
        sql = "SELECT * FROM craft_items" + (" WHERE active=1" if active_only else "") + " ORDER BY kind, name COLLATE NOCASE"
        rows = conn.execute(sql).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_craft_items(kind=None, active_only=True):
    """Cached read of the Craft catalog (Talents/Powers/Wargear).

    This is looked up on every effective-attribute/skill/derived-trait
    computation for every character, on every render of every open Battle
    Sheet/Combat panel, with a GM and several Players connected at once
    that adds up fast. The cache has no time-based expiry: it is exact and
    permanent until the catalog actually changes, at which point every
    write path (save_craft_item, delete_craft_item, and the Craft tab's
    enable/disable/delete actions) calls invalidate_craft_cache() so the
    next read is forced back to SQLite. This keeps every dependent
    computation in sync with the instant something changes, rather than
    within some polling window.
    """
    return _cached_craft_items(kind, active_only)


def invalidate_craft_cache():
    _cached_craft_items.clear()


def save_craft_item(item, item_id=None):
    now = now_iso()
    conn = get_conn()
    payload = json.dumps(item.get("details", {}), ensure_ascii=False)
    new_id = int(item_id) if item_id else None
    if item_id:
        existing = conn.execute("SELECT active FROM craft_items WHERE id=?", (int(item_id),)).fetchone()
        active = int(item.get("active", existing[0] if existing else 1))
        conn.execute("""UPDATE craft_items SET kind=?,name=?,effect=?,cost=?,source=?,source_url=?,details=?,active=?,updated_at=? WHERE id=?""",
                     (item["kind"], item["name"], item.get("effect", ""), int(item.get("cost", 0) or 0),
                      item.get("source", ""), item.get("source_url", ""), payload, active, now, int(item_id)))
    else:
        source_url = item.get("source_url", "")
        existing = None
        if source_url:
            existing = conn.execute("SELECT id,active FROM craft_items WHERE kind=? AND source_url=? LIMIT 1",
                                    (item["kind"], source_url)).fetchone()
        if existing:
            # Synchronization updates official data but preserves the Magister's
            # active/disabled campaign choice.
            conn.execute("""UPDATE craft_items SET name=?,effect=?,cost=?,source=?,details=?,updated_at=? WHERE id=?""",
                         (item["name"], item.get("effect", ""), int(item.get("cost", 0) or 0),
                          item.get("source", ""), payload, now, int(existing[0])))
            new_id = int(existing[0])
        else:
            cur = conn.execute("""INSERT INTO craft_items(kind,name,effect,cost,source,source_url,details,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,1,?,?)""",
                         (item["kind"], item["name"], item.get("effect", ""), int(item.get("cost", 0) or 0),
                          item.get("source", ""), source_url, payload, now, now))
            new_id = int(cur.lastrowid)
    conn.commit(); conn.close()
    invalidate_craft_cache()
    return new_id


def delete_craft_item(item_id):
    conn = get_conn(); conn.execute("UPDATE craft_items SET active=0, updated_at=? WHERE id=?", (now_iso(), int(item_id))); conn.commit(); conn.close()
    invalidate_craft_cache()


def craft_description_html(row, kind="craft", name_color=None, title_text=""):
    name = html.escape(str(row.get("name", "")))
    effect = str(row.get("effect", "") or "").strip()
    details = craft_details(row)
    keywords = details.get("keywords", [])
    if isinstance(keywords, str): keywords = _req_list(keywords)
    keywords = [str(x).strip() for x in keywords if str(x).strip()]
    req = details.get("requirements", {}) if isinstance(details.get("requirements", {}), dict) else {}
    prereq = str(details.get("prerequisites", "") or "").strip()
    if not prereq and isinstance(req, dict): prereq = str(req.get("prerequisites", "") or "").strip()
    style = f" style=\"color:{name_color}\"" if name_color else ""
    title = f" title=\"{html.escape(title_text, quote=True)}\"" if title_text else ""
    body = []
    if effect: body.append(f"<div class='craft-description-text'>{html.escape(effect).replace(chr(10), '<br>')}</div>")
    if keywords: body.append(f"<div class='craft-description-meta'><b>Keywords:</b> {html.escape(', '.join(keywords))}</div>")
    if prereq: body.append(f"<div class='craft-description-meta'><b>Prerequisites:</b> {html.escape(prereq)}</div>")
    if not body: body.append("<div class='craft-description-meta'>No registered description.</div>")
    return f"<details class='craft-details'><summary><span class='craft-details-name'{style}{title}>{name}</span></summary>{''.join(body)}</details>"


def _craft_keyword_options():
    """Return known Keywords for Craft prerequisite and Wargear editors."""
    values = set()
    for ch in list_characters():
        values.update(character_keywords(ch))
        values.update(_req_list(ch.get("keywords", [])))
    for row in list_craft_items(active_only=False):
        details = craft_details(row)
        for value in details.get("keywords", []) if isinstance(details.get("keywords", []), list) else _req_list(details.get("keywords", "")):
            if str(value).strip(): values.add(str(value).strip())
        req = details.get("requirements", {}) or {}
        if isinstance(req, dict):
            values.update(_req_list(req.get("keywords_all", [])))
            values.update(_req_list(req.get("keywords_any", [])))
    return sorted(values, key=str.lower)


def craft_keyword_values(row):
    details = craft_details(row)
    values = details.get("keywords", [])
    if isinstance(values, str): values = _req_list(values)
    return sorted({str(x).strip() for x in values if str(x).strip()}, key=str.lower)


def craft_keyword_filter(rows, selected):
    selected = {str(x).strip().lower() for x in (selected or []) if str(x).strip()}
    if not selected: return list(rows)
    return [row for row in rows if selected.issubset({x.lower() for x in craft_keyword_values(row)})]


def craft_item_label(row):
    source = str(row.get("source", "") or "").strip()
    return f"{row['name']}" + (f" · {source}" if source else "")


def _build_craft_entry(row, kind):
    """Build one character-owned Talent/Power/Wargear entry from a catalog row.

    This is the single place that shapes an owned entry, it always sets
    craft_id (as a real int) and a proper dict `details`, which is what
    every craft_id-based lookup (Wargear modifiers, Faith Talents, quantity
    adjustment, duplicate-purchase checks, etc.) relies on downstream.
    """
    details = craft_details(row)
    if kind in ("talent", "power"):
        return {"name": row["name"], "effect": row.get("effect", ""), "cost": int(row.get("cost", 0) or 0),
                "craft_id": int(row["id"]), "source": row.get("source", ""), "source_url": row.get("source_url", ""),
                "details": details}
    stackable, group = _infer_stackable_gear(row["name"], details)
    if stackable:
        details["stackable"] = True
        details["stack_group"] = group
    return {"name": row["name"], "effect": row.get("effect", ""), "equipped": True, "quantity": 1,
            "craft_id": int(row["id"]), "source": row.get("source", ""), "source_url": row.get("source_url", ""),
            "details": details}


def _craft_character_add(items, row, kind):
    """Add one catalog `row` (a dict/Row with at least id/name/effect/...) to
    an owned `items` list, merging into a matching stackable Wargear entry
    if one is already present."""
    if kind == "wargear":
        details = craft_details(row)
        stackable, _ = _infer_stackable_gear(row["name"], details)
        if stackable:
            existing = next((x for x in items if int(x.get("craft_id", -1) or -1) == int(row["id"])), None)
            if existing is not None:
                existing["quantity"] = int(existing.get("quantity", 1)) + 1
                return normalize_wargear(items)
    entry = _build_craft_entry(row, kind)
    if not any(str(x.get("name", "")).strip().lower() == str(entry["name"]).strip().lower()
               and int(x.get("craft_id", -1) or -1) == int(row["id"]) for x in items):
        items.append(entry)
    return normalize_wargear(items) if kind == "wargear" else items


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
    ch["powers"] = normalize_powers(ch.get("powers"))
    ch["wargear"] = normalize_wargear(ch.get("wargear"))
    try:
        raw_choices = ch.get("archetype_choices") or "{}"
        ch["archetype_choices"] = json.loads(raw_choices) if isinstance(raw_choices, str) else raw_choices
        if not isinstance(ch["archetype_choices"], dict): ch["archetype_choices"] = {}
    except Exception:
        ch["archetype_choices"] = {}
    try:
        raw_kw = ch.get("keywords") or "[]"
        ch["keywords"] = json.loads(raw_kw) if isinstance(raw_kw, str) else raw_kw
        if not isinstance(ch["keywords"], list): ch["keywords"] = []
    except Exception:
        ch["keywords"] = []
    for a in ATTRS:
        ch["attributes"].setdefault(a, 1)
    for s in SKILLS:
        ch["skills"].setdefault(s, 0)
    for k, dv in {"tier": 2, "starting_tier": 2, "rank": 1, "earned_xp": 0, "other_xp": 0, "armour": 0, "cur_wounds": 0,
                  "cur_shock": 0, "cur_wrath": 0, "cur_ammo": 3, "cur_corruption": 0, "cur_wealth": 0, "cur_faith": 0, "comms_on": 1, "kind": "player",
                  "name": "", "chapter": "", "species": "", "archetype": "", "faction": "", "keywords": [], "archetype_choices": {}, "creation_mode": "archetype", "archetype_history": "[]", "powers": "", "wargear": "", "notes": "", "updated_at": "", "revision": 0, "temp_instance": 0}.items():
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


def _audit_value(value):
    """Stable JSON/text representation for the player audit log."""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    return str(value)


def record_player_audit(cid, user_id, actor, source, changes):
    """Write one audit row per changed character-sheet field made by a Player.

    Temporarily disabled at the user's request, body commented out below.
    Uncomment to re-enable the Player audit trail."""
    return
    # if not changes or not user_id or not actor:
    #     return
    # conn = get_conn(); ts = now_iso(); rows = []
    # for field, old_value, new_value in changes:
    #     if _audit_value(old_value) == _audit_value(new_value):
    #         continue
    #     rows.append((int(cid), int(user_id), str(actor), str(source), str(field),
    #                  _audit_value(old_value), _audit_value(new_value), ts))
    # if rows:
    #     conn.executemany("""INSERT INTO player_audit
    #         (character_id,user_id,actor,source,field,old_value,new_value,changed_at)
    #         VALUES(?,?,?,?,?,?,?,?)""", rows)
    #     conn.commit()
    # conn.close()


def get_player_audit(character_id, limit=300):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM player_audit WHERE character_id=? ORDER BY id DESC LIMIT ?",
                        (int(character_id), int(limit))).fetchall()
    conn.close(); return [dict(r) for r in rows]


def count_player_audit(character_id):
    """Row count only, avoids pulling every audit row (old/new value text) just to call len()."""
    conn = get_conn()
    row = conn.execute("SELECT COUNT(*) FROM player_audit WHERE character_id=?", (int(character_id),)).fetchone()
    conn.close(); return int(row[0] or 0)



def get_player_registry():
    conn = get_conn()
    rows = conn.execute("""SELECT c.*, u.username AS username
                         FROM characters c LEFT JOIN users u ON u.id=c.user_id
                         WHERE c.kind='player' ORDER BY c.name, c.id""").fetchall()
    conn.close(); return [_decode(r) for r in rows]

def save_build(cid, name, chapter, species, tier, attributes, skills, talents, wargear, armour, notes, other_xp,
               archetype="", creation_mode="advanced", actor_role="gm", actor_user_id=None, actor_name="",
               source="Character Sheet", expected_revision=None, powers=None, faction=None, keywords=None, archetype_choices=None):
    conn = get_conn()
    row = conn.execute("SELECT * FROM characters WHERE id=?", (int(cid),)).fetchone()
    if row is None:
        conn.close(); return False, "Character not found."
    old = _decode(row)
    current_revision = int(old.get("revision", 0) or 0)
    if actor_role == "player":
        if old.get("kind") != "player" or int(old.get("user_id") or -1) != int(actor_user_id or -2):
            conn.close(); return False, "Players can only edit their own character sheet."
        old_wg = normalize_wargear(old.get("wargear", []))
        new_wg = normalize_wargear(wargear)
        old_counts = {}
        for item in old_wg:
            key = int(item.get("craft_id", -1) or -1) if int(item.get("craft_id", -1) or -1) > 0 else str(item.get("name", "")).strip().lower()
            old_counts[key] = old_counts.get(key, 0) + max(1, int(item.get("quantity", 1) or 1))
        new_counts = {}
        for item in new_wg:
            key = int(item.get("craft_id", -1) or -1) if int(item.get("craft_id", -1) or -1) > 0 else str(item.get("name", "")).strip().lower()
            new_counts[key] = new_counts.get(key, 0) + max(1, int(item.get("quantity", 1) or 1))
        for key, qty in new_counts.items():
            if key not in old_counts or qty > old_counts[key]:
                conn.close(); return False, "Players cannot add Wargear. Ask the Magister to assign new equipment."
    if expected_revision is not None and current_revision != int(expected_revision):
        conn.close(); return False, "This character sheet changed in another session. The latest version was loaded; review your edits before saving again."
    faction_value = str(faction if faction is not None else (old.get("faction", "") or "")).strip()
    keyword_value = [str(x).strip() for x in (keywords if keywords is not None else old.get("keywords", [])) if str(x).strip()]
    archetype_choice_value = dict(archetype_choices if archetype_choices is not None else (old.get("archetype_choices", {}) or {}))
    new_values = {"name": name, "chapter": chapter, "species": species, "archetype": archetype, "faction": faction_value, "keywords": keyword_value, "archetype_choices": archetype_choice_value,
                  "creation_mode": creation_mode, "tier": int(tier), "attributes": attributes, "skills": skills,
                  "talents": talents, "powers": normalize_powers(powers) if powers is not None else old.get("powers", []), "wargear": wargear, "armour": int(armour), "notes": notes, "other_xp": int(other_xp)}
    old_values = {"name": old.get("name", ""), "chapter": old.get("chapter", ""), "species": old.get("species", ""),
                  "archetype": old.get("archetype", ""), "faction": old.get("faction", ""), "keywords": old.get("keywords", []), "archetype_choices": old.get("archetype_choices", {}), "creation_mode": old.get("creation_mode", "advanced"),
                  "tier": int(old.get("tier", 1)), "attributes": old.get("attributes", {}), "skills": old.get("skills", {}),
                  "talents": old.get("talents", []), "powers": old.get("powers", []), "wargear": old.get("wargear", []), "armour": int(old.get("armour", 0)),
                  "notes": old.get("notes", ""), "other_xp": int(old.get("other_xp", 0))}
    changes = [(f, old_values[f], new_values[f]) for f in new_values]
    if not any(_audit_value(a) != _audit_value(b) for _, a, b in changes):
        conn.close(); return True, "No changes."
    new_revision = current_revision + 1
    capacity_snapshot = dict(old)
    capacity_snapshot["attributes"] = attributes
    capacity_snapshot["wargear"] = normalize_wargear(wargear)
    ammo_after = min(current_ammo(old), ammo_capacity(capacity_snapshot))
    cur = conn.execute("""UPDATE characters SET name=?,chapter=?,species=?,archetype=?,faction=?,keywords=?,archetype_choices=?,creation_mode=?,tier=?,attributes=?,skills=?,
                    talents=?,powers=?,wargear=?,armour=?,notes=?,other_xp=?,cur_ammo=?,updated_at=?,revision=? WHERE id=? AND revision=?""",
                 (name, chapter, species, archetype, faction_value, json.dumps(keyword_value, ensure_ascii=False), json.dumps(archetype_choice_value, ensure_ascii=False), creation_mode, int(tier), json.dumps(attributes), json.dumps(skills),
                  json.dumps(talents), json.dumps(new_values["powers"], ensure_ascii=False), wargear, int(armour), notes, int(other_xp), ammo_after, now_iso(), new_revision, int(cid), current_revision))
    if cur.rowcount != 1:
        conn.rollback(); conn.close(); return False, "Concurrent change detected. The latest version was not overwritten."
    conn.commit(); conn.close()
    if actor_role == "player":
        record_player_audit(cid, actor_user_id, actor_name, source, changes)
    return True, "Saved."


def adjust_vital(cid, field, delta, actor_role="gm", actor_user_id=None, actor_name="", source="Battle Sheet"):
    if field not in VITAL_FIELDS:
        return False
    conn = get_conn(); row = conn.execute("SELECT * FROM characters WHERE id=?", (int(cid),)).fetchone()
    if row is None:
        conn.close(); return False
    old = _decode(row); old_val = int(old.get(field, 0) or 0)
    # Corruption Points and Wealth are open-ended resource pools with no
    # fixed ceiling (Corruption Level 5 is a narrative end state, not a
    # cap), so only Wounds/Shock/Wrath are clamped to a derived maximum.
    maximums = {"cur_wounds": derived_traits(old)["Max Wounds"], "cur_shock": derived_traits(old)["Max Shock"], "cur_wrath": derived_traits(old)["Max Wrath"]}
    if field in maximums:
        new_val = max(0, min(int(maximums[field]), old_val + int(delta)))
    else:
        new_val = max(0, old_val + int(delta))
    new_rev = int(old.get("revision", 0) or 0) + 1
    conn.execute("UPDATE characters SET %s=?, updated_at=?, revision=? WHERE id=?" % field,
                 (new_val, now_iso(), new_rev, int(cid)))
    conn.commit(); conn.close()
    if actor_role == "player" and actor_user_id:
        record_player_audit(cid, actor_user_id, actor_name, source, [(field, old_val, new_val)])
    return True


def _progression_snapshot(ch):
    """Fields that can be restored when the Magister needs to undo a progression mistake."""
    fields = ["name", "chapter", "species", "archetype", "creation_mode", "archetype_history",
              "tier", "starting_tier", "rank", "earned_xp", "other_xp", "attributes", "skills",
              "talents", "powers", "wargear", "armour", "notes"]
    snap = {}
    for field in fields:
        value = ch.get(field)
        if field in {"attributes", "skills", "talents", "powers", "wargear"}:
            snap[field] = value
        else:
            snap[field] = value
    return snap

def record_progression_undo(cid, action):
    ch = load_character(cid)
    if not ch:
        return
    conn = get_conn()
    conn.execute("INSERT INTO progression_undo(character_id,action,snapshot,created_at) VALUES(?,?,?,?)",
                 (int(cid), str(action), json.dumps(_progression_snapshot(ch), ensure_ascii=False), now_iso()))
    # Keep a useful but bounded correction history.
    conn.execute("""DELETE FROM progression_undo WHERE character_id=? AND id NOT IN
                    (SELECT id FROM progression_undo WHERE character_id=? ORDER BY id DESC LIMIT 20)""", (int(cid), int(cid)))
    conn.commit(); conn.close()

def get_progression_undo(cid, limit=10):
    conn = get_conn()
    rows = conn.execute("SELECT id, action, created_at FROM progression_undo WHERE character_id=? ORDER BY id DESC LIMIT ?",
                        (int(cid), int(limit))).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def restore_progression_undo(undo_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM progression_undo WHERE id=?", (int(undo_id),)).fetchone()
    if not row:
        conn.close(); return False, "Correction record not found."
    snap = json.loads(row["snapshot"])
    # Save the current state too, so an accidental undo can itself be undone.
    current = conn.execute("SELECT * FROM characters WHERE id=?", (int(row["character_id"]),)).fetchone()
    if not current:
        conn.close(); return False, "Character not found."
    current_ch = _decode(current)
    conn.execute("INSERT INTO progression_undo(character_id,action,snapshot,created_at) VALUES(?,?,?,?)",
                 (int(row["character_id"]), "Before undo: " + str(row["action"]),
                  json.dumps(_progression_snapshot(current_ch), ensure_ascii=False), now_iso()))
    conn.execute("""UPDATE characters SET name=?,chapter=?,species=?,archetype=?,creation_mode=?,archetype_history=?,
                    tier=?,starting_tier=?,rank=?,earned_xp=?,other_xp=?,attributes=?,skills=?,talents=?,wargear=?,
                    armour=?,notes=?,updated_at=?,revision=revision+1 WHERE id=?""",
                 (snap.get("name", ""), snap.get("chapter", ""), snap.get("species", ""), snap.get("archetype", ""),
                  snap.get("creation_mode", "archetype"), snap.get("archetype_history", "[]"), int(snap.get("tier", 1)),
                  int(snap.get("starting_tier", 1)), int(snap.get("rank", 1)), int(snap.get("earned_xp", 0)),
                  int(snap.get("other_xp", 0)), json.dumps(snap.get("attributes", {})), json.dumps(snap.get("skills", {})),
                  json.dumps(snap.get("talents", []), ensure_ascii=False), json.dumps(snap.get("wargear", []), ensure_ascii=False),
                  int(snap.get("armour", 0)), snap.get("notes", ""), now_iso(), int(row["character_id"])))
    conn.commit(); conn.close()
    return True, f"Reverted {row['action']}."

def set_earned_xp(cid, val):
    record_progression_undo(cid, "Manual XP correction")
    conn = get_conn(); conn.execute("UPDATE characters SET earned_xp=?, updated_at=?, revision=revision+1 WHERE id=?", (max(0, int(val)), now_iso(), cid))
    conn.commit(); conn.close()

def adjust_earned_xp(cid, delta):
    ch = load_character(cid)
    if not ch:
        return False
    record_progression_undo(cid, "XP adjustment")
    new_xp = max(0, int(ch.get("earned_xp", 0)) + int(delta))
    conn = get_conn()
    conn.execute("UPDATE characters SET earned_xp=?, updated_at=?, revision=revision+1 WHERE id=?", (new_xp, now_iso(), cid))
    conn.commit(); conn.close(); return True

def correct_progression_state(cid, earned_xp, rank, tier):
    """GM-only correction tool. Unlike normal advancement, this may move XP/Rank/Tier backwards."""
    ch = load_character(cid)
    if not ch:
        return False
    record_progression_undo(cid, "Manual progression correction")
    conn = get_conn()
    conn.execute("UPDATE characters SET earned_xp=?, rank=?, tier=?, updated_at=?, revision=revision+1 WHERE id=?",
                 (max(0, int(earned_xp)), max(1, min(3, int(rank))), max(1, min(MAX_TIER, int(tier))), now_iso(), int(cid)))
    conn.commit(); conn.close()
    return True

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
    record_progression_undo(cid, f"Rank change to {rank}")
    conn.execute("UPDATE characters SET rank=?, updated_at=?, revision=revision+1 WHERE id=?", (rank, now_iso(), cid))
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
    target_pkg = ARCHETYPE_PACKAGES.get(new_archetype, {})
    for attr, minimum in target_pkg.get("attributes", {}).items():
        if int(ch.get("attributes", {}).get(attr, 1)) < int(minimum):
            return False, f"Requires {attr} {int(minimum)}+ before Ascension."
    for skill, minimum in target_pkg.get("skills", {}).items():
        if int(ch.get("skills", {}).get(skill, 0)) < int(minimum):
            return False, f"Requires {skill} {int(minimum)}+ before Ascension."
    record_progression_undo(cid, f"Archetype Ascension to {new_archetype}")
    history = get_archetype_history(ch)
    if ch.get("archetype"):
        history.append({"archetype": ch["archetype"], "tier": int(ch["tier"]), "retained": True})
    # Core Rulebook 2e p.155: "add all of the Archetype benefits (Archetype
    # Abilities, Wargear, Influence, etc.)... and retain all of the benefits
    # from your previous Archetype" — so the new Archetype's starting Wargear
    # is merged into (not swapped for) whatever the character already has.
    current_gear = normalize_wargear(ch.get("wargear", []))
    package_gear = archetype_starting_wargear(new_archetype)
    existing_names = {str(x.get("name", "")).strip().lower() for x in current_gear}
    for gear in package_gear:
        if str(gear.get("name", "")).strip().lower() not in existing_names:
            current_gear.append(gear)
    if package_gear:
        current_gear = normalize_wargear(current_gear + starting_ammo_for_wargear(package_gear))
    conn = get_conn()
    conn.execute("UPDATE characters SET archetype=?, tier=?, archetype_history=?, wargear=?, updated_at=?, revision=revision+1 WHERE id=?",
                 (new_archetype, int(data["tier"]), json.dumps(history), json.dumps(current_gear, ensure_ascii=False), now_iso(), cid))
    conn.commit(); conn.close()
    return True, f"Character ascended to {new_archetype}, gaining its starting Wargear. Required Attributes and Skills were already met; the new Archetype does not grant them again."


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
    record_progression_undo(cid, f"Tier change to {tier}")
    conn.execute("UPDATE characters SET tier=?, updated_at=?, revision=revision+1 WHERE id=?", (tier, now_iso(), cid))
    conn.commit(); conn.close(); return True


def award_xp(cid, amt):
    if int(amt) == 0:
        return
    record_progression_undo(cid, f"Awarded {int(amt)} XP")
    conn = get_conn(); conn.execute("UPDATE characters SET earned_xp=MAX(0,earned_xp+?), updated_at=?, revision=revision+1 WHERE id=?", (int(amt), now_iso(), cid))
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


def set_portrait(cid, blob, actor_role="gm", actor_user_id=None, actor_name="", source="Character Sheet"):
    conn = get_conn(); row = conn.execute("SELECT portrait FROM characters WHERE id=?", (int(cid),)).fetchone()
    old_blob = row["portrait"] if row else None
    conn.execute("UPDATE characters SET portrait=?, updated_at=?, revision=revision+1 WHERE id=?", (blob, now_iso(), int(cid)))
    conn.commit(); conn.close()
    if actor_role == "player" and actor_user_id:
        old_label = "Portrait present" if old_blob else "No portrait"
        record_player_audit(cid, actor_user_id, actor_name, source, [("portrait", old_label, "Portrait updated")])



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
    c.setdefault("spectator_code", ""); c.setdefault("spectator_show_players", 0); c.setdefault("spectator_show_monsters", 0)
    return c


def save_campaign(name, tier, ruin, session_no):
    conn = get_conn()
    conn.execute("UPDATE campaign SET name=?,tier=?,ruin=?,session_no=? WHERE id=1",
                 (name, int(tier), int(ruin), int(session_no)))
    conn.commit(); conn.close()


def generate_spectator_code():
    """Mints a new random Spectator Code, invalidating any previous one."""
    code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
    conn = get_conn()
    conn.execute("UPDATE campaign SET spectator_code=? WHERE id=1", (code,))
    conn.commit(); conn.close()
    return code


def clear_spectator_code():
    conn = get_conn()
    conn.execute("UPDATE campaign SET spectator_code='' WHERE id=1")
    conn.commit(); conn.close()


def set_spectator_visibility(show_players=None, show_monsters=None):
    conn = get_conn()
    if show_players is not None:
        conn.execute("UPDATE campaign SET spectator_show_players=? WHERE id=1", (1 if show_players else 0,))
    if show_monsters is not None:
        conn.execute("UPDATE campaign SET spectator_show_monsters=? WHERE id=1", (1 if show_monsters else 0,))
    conn.commit(); conn.close()


def verify_spectator_code(code):
    code = str(code or "").strip().upper()
    if not code:
        return False
    camp = get_campaign()
    stored = str(camp.get("spectator_code", "") or "").strip().upper()
    return bool(stored) and secrets.compare_digest(stored, code)


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
    # Snapshot each character before applying the session award so the Magister can undo it.
    for cid, base_xp, bonus_xp in awards:
        total = max(0, int(base_xp)) + max(0, int(bonus_xp))
        if total:
            record_progression_undo(int(cid), f"Session XP award #{int(session_id)}")
    conn = get_conn()
    for cid, base_xp, bonus_xp in awards:
        total = max(0, int(base_xp)) + max(0, int(bonus_xp))
        conn.execute(
            "INSERT OR REPLACE INTO session_award(session_id,character_id,base_xp,bonus_xp,total_xp) VALUES(?,?,?,?,?)",
            (int(session_id), int(cid), max(0, int(base_xp)), max(0, int(bonus_xp)), total),
        )
        conn.execute("UPDATE characters SET earned_xp=MAX(0,earned_xp+?), updated_at=?, revision=revision+1 WHERE id=?", (total, now_iso(), int(cid)))
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
    """Return the characters in the active encounter, in manual attack order."""
    eid = _current_combat_id(False)
    if not eid:
        return []
    conn = get_conn()
    rows = conn.execute("""SELECT c.*, cp.initiative_mod AS initiative_modifier,
                                 cp.turn_order AS initiative_order
                          FROM characters c
                          JOIN combat_participant cp ON cp.character_id=c.id
                          WHERE cp.encounter_id=?
                          ORDER BY cp.turn_order ASC, c.name ASC, c.id ASC""", (int(eid),)).fetchall()
    conn.close()
    return [_decode(r) for r in rows]


def set_combatant(cid, active=True):
    """Add or remove a character from the active combat encounter."""
    eid = _current_combat_id(create=bool(active))
    if not eid:
        return
    conn = get_conn()
    try:
        if active:
            exists = conn.execute(
                "SELECT 1 FROM combat_participant WHERE encounter_id=? AND character_id=?",
                (int(eid), int(cid)),
            ).fetchone()
            if not exists:
                row = conn.execute(
                    "SELECT COALESCE(MAX(turn_order), 0) + 1 FROM combat_participant WHERE encounter_id=?",
                    (int(eid),),
                ).fetchone()
                next_order = int(row[0] or 1)
                ch = conn.execute("SELECT kind FROM characters WHERE id=?", (int(cid),)).fetchone()
                if ch:
                    conn.execute(
                        """INSERT INTO combat_participant(encounter_id,character_id,side,turn_order,added_at)
                           VALUES(?,?,?,?,?)""",
                        (int(eid), int(cid), str(ch[0] or "npc"), next_order, now_iso()),
                    )
        else:
            conn.execute(
                "DELETE FROM combat_participant WHERE encounter_id=? AND character_id=?",
                (int(eid), int(cid)),
            )
            rows = conn.execute(
                "SELECT id FROM combat_participant WHERE encounter_id=? ORDER BY turn_order ASC, id ASC",
                (int(eid),),
            ).fetchall()
            for order, row in enumerate(rows, 1):
                conn.execute("UPDATE combat_participant SET turn_order=? WHERE id=?", (order, int(row[0])))
        conn.commit()
    finally:
        conn.close()
    if not active:
        # Generic NPC mobs are disposable: pulling one out of combat without
        # saving it discards the instance instead of leaving it in the roster.
        purge_unsaved_temp_instances([cid])


def set_combat_modifier(cid, modifier):
    eid = _current_combat_id(False)
    if not eid:
        return
    conn = get_conn()
    conn.execute(
        "UPDATE combat_participant SET initiative_mod=? WHERE encounter_id=? AND character_id=?",
        (int(modifier), int(eid), int(cid)),
    )
    conn.commit()
    conn.close()


def move_combatant(cid, direction):
    """Move a combatant up or down in the manual attack order."""
    eid = _current_combat_id(False)
    if not eid:
        return
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, character_id FROM combat_participant WHERE encounter_id=? ORDER BY turn_order ASC, id ASC",
        (int(eid),),
    ).fetchall()
    ids = [int(r[1]) for r in rows]
    if int(cid) not in ids:
        conn.close()
        return
    i = ids.index(int(cid))
    j = i + int(direction)
    if j < 0 or j >= len(ids):
        conn.close()
        return
    ids[i], ids[j] = ids[j], ids[i]
    for order, char_id in enumerate(ids, 1):
        conn.execute(
            "UPDATE combat_participant SET turn_order=? WHERE encounter_id=? AND character_id=?",
            (order, int(eid), int(char_id)),
        )
    conn.commit()
    conn.close()


def combat_state():
    eid = _current_combat_id(False)
    if not eid:
        return {"id": None, "round": 1, "current": 0}
    conn = get_conn(); row = conn.execute("SELECT id,round_no,current_turn,status FROM combat_encounter WHERE id=?", (eid,)).fetchone(); conn.close()
    if not row:
        return {"id": eid, "round": 1, "current": 0}
    return {"id": int(row["id"]), "round": max(1, int(row["round_no"] or 1)), "current": max(0, int(row["current_turn"] or 0)), "status": row["status"]}

def set_combat_turn(index, round_no=None):
    eid = _current_combat_id(True); current = get_combatants()
    if not current: return
    idx = max(0, min(len(current) - 1, int(index)))
    state = combat_state(); rnd = max(1, int(round_no if round_no is not None else state.get("round", 1)))
    conn = get_conn(); conn.execute("UPDATE combat_encounter SET current_turn=?,round_no=? WHERE id=?", (idx, rnd, eid)); conn.commit(); conn.close()

def advance_combat_turn(delta=1):
    current = get_combatants()
    if not current: return
    state = combat_state(); idx = int(state.get("current", 0)) + int(delta); rnd = int(state.get("round", 1))
    while idx >= len(current): idx -= len(current); rnd += 1
    while idx < 0: idx += len(current); rnd = max(1, rnd - 1)
    set_combat_turn(idx, rnd)

def clear_combat():
    eid = _current_combat_id(False)
    if not eid:
        return
    conn = get_conn()
    participant_ids = [int(r[0]) for r in conn.execute(
        "SELECT character_id FROM combat_participant WHERE encounter_id=?", (int(eid),)).fetchall()]
    conn.execute("DELETE FROM combat_participant WHERE encounter_id=?", (int(eid),))
    conn.execute("UPDATE combat_encounter SET current_turn=0,round_no=1 WHERE id=?", (int(eid),))
    conn.commit()
    conn.close()
    # Any Generic NPC mob still unsaved when combat clears is disposable by design.
    purge_unsaved_temp_instances(participant_ids)


def log_combat_end():
    """Snapshot every combatant's final Wounds/Shock/Wrath into a permanent
    Combat Log entry tagged to the current session, then clear the live
    tracker. A no-op (just clears) if nobody was actually in combat."""
    current = get_combatants()
    if not current:
        clear_combat()
        return False
    state = combat_state()
    conn = get_conn()
    started_at = None
    if state.get("id"):
        row = conn.execute("SELECT started_at FROM combat_encounter WHERE id=?", (int(state["id"]),)).fetchone()
        started_at = row["started_at"] if row else None
    camp_row = conn.execute("SELECT session_no FROM campaign WHERE id=1").fetchone()
    session_no = int(camp_row[0] if camp_row else 1)
    participants = []
    for ch in current:
        d = derived_traits(ch)
        participants.append({
            "character_id": int(ch["id"]), "name": ch.get("name") or "Unnamed", "kind": ch.get("kind"),
            "species": ch.get("species"), "tier": int(ch.get("tier", 1) or 1),
            "cur_wounds": int(ch.get("cur_wounds", 0) or 0), "max_wounds": int(d.get("Max Wounds", 0) or 0),
            "cur_shock": int(ch.get("cur_shock", 0) or 0), "max_shock": int(d.get("Max Shock", 0) or 0),
            "cur_wrath": int(ch.get("cur_wrath", 0) or 0), "max_wrath": int(d.get("Max Wrath", 0) or 0),
        })
    conn.execute(
        "INSERT INTO combat_log(session_no,started_at,ended_at,rounds,participants) VALUES(?,?,?,?,?)",
        (session_no, started_at, now_iso(), int(state.get("round", 1) or 1), json.dumps(participants, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()
    clear_combat()
    return True


def get_combat_logs(session_no=None, limit=100):
    conn = get_conn()
    if session_no is not None:
        rows = conn.execute("SELECT * FROM combat_log WHERE session_no=? ORDER BY id DESC LIMIT ?",
                            (int(session_no), int(limit))).fetchall()
    else:
        rows = conn.execute("SELECT * FROM combat_log ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
    conn.close()
    out = []
    for r in rows:
        entry = dict(r)
        try:
            entry["participants"] = json.loads(entry.get("participants") or "[]")
        except Exception:
            entry["participants"] = []
        out.append(entry)
    return out


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
    .combat-arrow{ text-align:center; color:var(--gold); font-size:1rem; line-height:.8; margin:-2px 0 3px; opacity:.8; }
    .info-tip{ display:inline-flex; align-items:center; justify-content:center; width:1.35em; height:1.35em;
        margin-top:6px; border-radius:50%; border:1px solid var(--gold); color:var(--gold2);
        font-family:'Cinzel',serif; font-size:.72rem; font-weight:700; cursor:help; opacity:.85; user-select:none; }
    .info-tip:hover{ opacity:1; background:var(--panel2); }
    .st-key-lang_flags{ position:fixed !important; top:60px; right:16px; z-index:1000000;
        width:44px !important; min-width:44px !important; max-width:44px !important; height:40px !important;
        flex:none !important; padding:0 !important; border:1px solid var(--gold); border-radius:6px; overflow:hidden; }
    .st-key-lang_flags button{ width:42px !important; height:38px !important; min-height:38px !important;
        padding:0 !important; margin:0 !important; border:none !important; border-radius:5px !important;
        background:var(--panel) !important; font-family:'Cinzel',serif !important; font-weight:900 !important;
        letter-spacing:.05em !important; font-size:.85rem !important; color:var(--gold2) !important; }
    .st-key-lang_flags button:hover{ background:linear-gradient(var(--blood),var(--blood2)) !important; color:#fff !important; }
    .combat-pos{ font-family:'Cinzel',serif; font-weight:900; color:var(--gold2); font-size:1.3rem; text-align:center; line-height:2.2; }
    .combat-pos-active{ color:#171209; background:var(--gold2); border-radius:50%; width:1.9em; height:1.9em; margin:0 auto; line-height:1.9em; box-shadow:0 0 8px var(--gold2); }
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
    .tal,.wg{ background:var(--panel2); border:1px solid #3a2e18; border-radius:4px; padding:7px 10px; margin-bottom:6px; }
    .wg-pending{ border-color:var(--red); border-left:3px solid var(--red); }
    .wg-pending b{ color:var(--red); }
    .wg-pending-tag{ float:right; font-family:'Cinzel',serif; color:var(--red); font-size:.68rem;
        letter-spacing:.08em; text-transform:uppercase; opacity:.9; }
    .resource-card{ background:linear-gradient(90deg,rgba(36,27,14,.96),rgba(24,18,10,.96)); border:1px solid #4a3719; border-left:3px solid var(--gold); border-radius:3px; padding:8px 11px; margin:4px 0 8px; }
    .resource-head{ display:flex; justify-content:space-between; align-items:center; font-family:'Cinzel',serif; color:var(--gold2); letter-spacing:.06em; font-size:.8rem; }
    .resource-note{ margin-top:3px; color:#b8af9d; font-size:.72rem; line-height:1.35; }
    .resource-subtitle{ color:var(--gold); font-family:'Cinzel',serif; letter-spacing:.08em; font-size:.78rem; border-bottom:1px solid rgba(191,151,70,.3); padding:4px 0; margin:8px 0 3px; }
    .resource-row{ min-height:34px; display:flex; flex-direction:column; justify-content:center; border-bottom:1px solid rgba(191,151,70,.13); padding:4px 3px; }
    .resource-row .resource-name{ font-family:'Cinzel',serif; font-size:.84rem; color:#e8d9b5; }
    .resource-row .resource-meta{ font-size:.69rem; color:#8f8778; margin-top:1px; }
    .resource-row.consumable .resource-name{ color:#d8c28e; }
    .wgdesc,.taleffect{ margin-top:6px; padding-top:6px; border-top:1px solid rgba(191,151,70,.18); opacity:.82; line-height:1.42; font-size:.84rem; }
    .wgdesc{ color:#d8d0bf; } .taleffect{ color:#d8d0bf; }
    .tal .tn{ font-family:'Cinzel',serif; color:var(--gold2); letter-spacing:.03em; }
    .chapter-card{ background:var(--panel2); border:1px solid #3a2e18; border-left:3px solid var(--gold); border-radius:3px; padding:9px 12px; margin-bottom:6px; }
    .chapter-card .ctitle{ font-family:'Cinzel',serif; color:var(--gold2); font-size:.95rem; font-weight:700; letter-spacing:.02em; }
    .chapter-card .cmeta{ float:right; opacity:.65; font-size:.75rem; }
    .chapter-card .clabel{ color:var(--gold); font-family:'Cinzel',serif; font-size:.68rem; text-transform:uppercase; letter-spacing:.07em; margin-top:7px; }
    .chapter-card .ctext{ margin-top:2px; line-height:1.45; font-size:.88rem; }
    .tal .tc{ float:right; opacity:.6; font-size:.75rem; }
    .craft-shop-name{ font-family:'Cinzel',serif; font-size:.76rem; font-weight:700; letter-spacing:.025em; line-height:1.05; }
    .craft-shop-cost{ color:rgba(216,208,191,.52); font-size:.66rem; white-space:nowrap; }
.gear-mod-sheet{color:#55c878;font-family:Cinzel;font-weight:700;font-size:.9rem;padding-top:30px;text-align:center}.gear-mod-sheet::before{content:""}
.gear-mod{margin-left:4px;color:#55c96b;font-size:.68em;font-weight:700;vertical-align:middle;}
.ammo-vital-value{min-height:30px;padding-top:2px;text-align:center;color:#d7d0c2;font-family:Cinzel,serif;font-size:1.05rem;}
.vital-label{font-family:Cinzel,serif;color:#c9a227;letter-spacing:.08em;font-size:.78rem;margin-bottom:4px;}

    .craft-details{ margin:0 0 3px; border-bottom:1px solid #342817; }
    .craft-details summary{ cursor:pointer; list-style:none; padding:2px 0; font-family:'Cinzel',serif; font-size:.76rem; letter-spacing:.025em; }
    .craft-details summary::-webkit-details-marker{ display:none; }
    .craft-details summary:before{ content:'▸'; color:var(--gold); margin-right:6px; font-size:.65rem; }
    .craft-details[open] summary:before{ content:'▾'; }
    .craft-description-text{ padding:4px 8px 5px 18px; color:var(--bone); font-size:.78rem; line-height:1.25; }
    .craft-description-meta{ padding:1px 8px 4px 18px; color:rgba(232,224,207,.62); font-size:.68rem; }
    .sheet-banner{ background:linear-gradient(110deg,#21170c,#120c07); border:1px solid #5a4421; border-left:4px solid var(--gold); padding:7px 10px; margin:8px 0 9px; font-family:'Cinzel',serif; color:var(--gold2); letter-spacing:.08em; text-transform:uppercase; }
    .foot{ text-align:center; color:var(--gold); opacity:.5; font-family:'Cinzel',serif; letter-spacing:.3em;
        font-size:.75rem; margin-top:20px; }

    /* ============================================================
       SPECTATOR VOX-FEED — deliberately the most theatrical page in the
       app: it shows almost nothing (only current Shock, gated by the
       Magister), so the presentation is what carries it.
       ============================================================ */
    .spectator-banner{ text-align:center; font-family:'Cinzel',serif; font-weight:900; font-size:2rem;
        color:var(--gold2); letter-spacing:.16em; padding:18px 0 6px; border-bottom:2px solid var(--gold);
        text-shadow:0 0 14px rgba(232,201,106,.35); }
    .spectator-banner .sub{ display:block; font-size:.8rem; letter-spacing:.3em; color:var(--bone); opacity:.75;
        text-transform:uppercase; margin-top:5px; }
    .spectator-banner .spectator-static{ display:block; margin-top:8px; color:var(--blood2); opacity:.55;
        letter-spacing:.6em; font-size:.85rem; animation:spectator-flicker 2.6s infinite; }
    @keyframes spectator-flicker{ 0%,100%{opacity:.55;} 45%{opacity:.15;} 50%{opacity:.65;} 55%{opacity:.2;} }
    .spectator-flavor{ text-align:center; color:var(--bone); opacity:.6; font-style:italic; font-size:.82rem;
        margin:10px auto 18px; max-width:640px; line-height:1.5; }
    .spectator-panel-ttl{ font-family:'Cinzel',serif; color:var(--gold); text-transform:uppercase;
        letter-spacing:.18em; text-align:center; border-bottom:1px solid var(--gold); padding-bottom:6px;
        margin-bottom:12px; font-size:1rem; }
    .spectator-locked{ text-align:center; font-family:'Cinzel',serif; color:var(--red); opacity:.75;
        letter-spacing:.1em; padding:26px 8px; font-size:.85rem; }
    .shock-row{ display:flex; align-items:center; gap:10px; padding:7px 4px; border-bottom:1px solid #241c10; }
    .shock-name{ font-family:'Cinzel',serif; color:var(--gold2); letter-spacing:.1em; font-size:.78rem;
        min-width:56px; }
    .shock-bar{ flex:1; height:12px; background:#160f0a; border:1px solid #4a3a20; border-radius:6px; overflow:hidden; }
    .shock-fill{ height:100%; background:linear-gradient(90deg,var(--green),#79c98e); transition:width .4s ease; }
    .shock-fill.spectator-warn{ background:linear-gradient(90deg,#c9922e,#e8c96a); }
    .shock-fill.spectator-danger{ background:linear-gradient(90deg,var(--blood),var(--red)); }
    .shock-value{ font-family:'Cinzel',serif; color:var(--bone); opacity:.85; font-size:.78rem; min-width:44px;
        text-align:right; }

    /* ============================================================
       RESPONSIVE / MOBILE
       Streamlit has no reliable server-side "is this a phone" signal,
       so recognition happens the standard web way: the browser itself
       matches this media query against the viewport. This is what
       Players opening their Battle Sheet or Character Sheet on a phone
       actually hit, since a GM's desk usually has a real screen.
       ============================================================ */
    @media (max-width: 768px){
        .block-container{ padding-left:.6rem !important; padding-right:.6rem !important; padding-top:1rem !important; }
        /* Every multi-column row stacks into a single column instead of
           squeezing five slivers into a 360px screen. */
        div[data-testid="stHorizontalBlock"]{ flex-direction:column !important; gap:.35rem !important; }
        div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]{
            width:100% !important; min-width:100% !important; flex:1 1 100% !important;
        }
        /* Bigger tap targets for fingers instead of a mouse cursor. */
        .stButton>button, .stDownloadButton>button, .stFormSubmitButton>button{
            min-height:44px; width:100%; font-size:.82rem; padding:8px 10px;
        }
        .stNumberInput input, .stTextInput input, .stSelectbox, .stTextArea textarea{ font-size:1rem !important; }
        /* Titles that were sized for a wide desktop banner. */
        .banner{ font-size:1.05rem; letter-spacing:.06em; padding:10px 6px 4px; }
        .banner .sub{ font-size:.6rem; letter-spacing:.14em; }
        .hero{ padding:10px 12px; }
        .hero .nm{ font-size:1.25rem; }
        .hero .meta{ font-size:.72rem; }
        .sectionttl{ font-size:.82rem; margin:10px 0 6px; }
        .grid{ gap:5px; }
        .statcard{ flex:1 1 42%; min-width:0; padding:5px 8px; }
        .statcard .v{ font-size:1.1rem; }
        .statcard .l{ font-size:.68rem; }
        /* Talent/Power/Wargear entries are already bordered blocks; just
           tighten them up to match the desktop's information density. */
        .tal, .wg{ padding:6px 8px; margin-bottom:5px; }
        .tal .tn{ font-size:.86rem; }
        .wg > b{ font-size:.86rem; }
        .wgdesc, .taleffect{ font-size:.76rem; margin-top:4px; padding-top:4px; }
        /* The Skills table's 4-column grid: keep it on one line per Skill,
           just narrower, rather than stacking (it would stop reading as a
           table at all). */
        .skhead,.skrow{ grid-template-columns:1fr 32px 46px 40px; gap:2px; padding:3px 4px; font-size:.8rem; }
        /* Tabs: scroll sideways instead of shrinking every label to nothing. */
        .stTabs [data-baseweb="tab-list"]{ overflow-x:auto; flex-wrap:nowrap; }
        .stTabs [data-baseweb="tab"]{ font-size:.66rem; padding:6px 8px; white-space:nowrap; }
        /* Popovers (character/combatant details) should not overflow off
           the side of a narrow screen. */
        div[data-testid="stPopoverBody"]{ max-width:92vw !important; }
        /* Shrink metric/caption text closer to the desktop density instead
           of everything ballooning to fill a narrow screen. */
        [data-testid="stMetricValue"]{ font-size:1.05rem !important; }
        [data-testid="stMetricLabel"]{ font-size:.68rem !important; }
        [data-testid="stMetric"]{ padding:4px 8px !important; }
        .stMarkdown p, .stCaption, [data-testid="stCaptionContainer"]{ font-size:.82rem !important; }
        /* Compact metric + stacked -/+ widgets (Wounds/Shock/Wrath/Ammo/Ruin)
           are already a single self-contained "block" (a bordered stMetric
           plus two small buttons) — the blanket column-stacking rule above
           was blowing each one up into three separate full-width rows
           instead of keeping it as one tight card, so it's exempted here
           and kept as a compact horizontal block like the desktop layout. */
        [class*="_vsb"] div[data-testid="stHorizontalBlock"]{
            flex-direction:row !important; gap:.3rem !important; align-items:stretch !important;
        }
        [class*="_vsb"] div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]{
            width:auto !important; min-width:0 !important; flex:unset !important;
        }
        [class*="_vsb"] div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:first-child{
            flex:1 1 auto !important;
        }
        [class*="_vsb"] div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:last-child{
            flex:0 0 52px !important; width:52px !important;
        }
        [class*="_vsb"] .stButton>button{ min-height:0 !important; padding:3px 4px !important; font-size:.68rem !important; }
    }
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
    species_alias = {
        "Astra Militarum (Humano)": "Human",
        "Adepta Sororitas": "Human",
        "Inquisição": "Human",
        "Rogue Trader": "Human",
        "Aeldari (Asuryani)": "Aeldari",
    }
    normalized_species = species_alias.get(species, species)
    if tier is not None:
        return preferred.get(normalized_species, {}).get(int(tier), "")
    return next(iter(preferred.get(normalized_species, {}).values()), "")


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
    # This callback fires from a button rendered inside char_row(), which is
    # an @st.fragment. Per Streamlit, a widget interaction inside a fragment
    # only reruns that fragment by default, gm_view(), which actually reads
    # st.session_state.editing to switch to the sheet, lives outside it and
    # would not re-execute until some unrelated full-app rerun happened
    # later. That looked like "Open" was doing nothing / taking forever.
    # st.rerun() forces the full-app rerun this needs.
    st.rerun()


def cb_close():
    st.session_state.editing = None
    st.rerun()


def cb_delete_character(cid):
    # Same fragment-scoping reason as cb_open(): this fires from a button
    # inside char_row() (@st.fragment). Without an explicit full-app rerun,
    # the row for the now-deleted character keeps rendering with its last
    # known state until something else happens to trigger one, so a deleted
    # character appears to linger in the Characters list.
    delete_character(cid)
    st.rerun()


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
    current_gear = normalize_wargear((load_character(cid) or {}).get("wargear", []))
    package_gear = archetype_starting_wargear(archetype)
    existing_names = {str(x.get("name", "")).strip().lower() for x in current_gear}
    for gear in package_gear:
        if str(gear.get("name", "")).strip().lower() not in existing_names:
            current_gear.append(gear)
    if package_gear:
        current_gear = normalize_wargear(current_gear + starting_ammo_for_wargear(package_gear))
    st.session_state[_k(cid, "meta", "archetype_starting_wargear")] = current_gear
    st.session_state[_k(cid, "meta", "previous_archetype")] = archetype


def cb_species_change(cid):
    """Apply the selected Species package without deleting values bought above the old package."""
    ch = load_character(cid) or {}
    st.session_state.setdefault(_k(cid, "sel", "mode"), "archetype" if ch.get("creation_mode") == "archetype" else "advanced")
    ark = _k(cid, "sel", "arch")
    if ark not in st.session_state:
        st.session_state[ark] = ch.get("archetype") if ch.get("archetype") in ARCHETYPES else default_archetype_for_species(ch.get("species")) or list(ARCHETYPES.keys())[0]
    st.session_state.setdefault(_k(cid, "meta", "previous_archetype"), st.session_state.get(ark, ""))
    spk = _k(cid, "sel", "sp")
    species = st.session_state.get(spk, "")
    previous_species = st.session_state.get(_k(cid, "meta", "previous_species"), ch.get("species", ""))

    if species not in SPECIES_PACKAGES:
        return

    # Remove only the old automatic Species package values. Higher values are
    # preserved because they represent XP/customisation already on the sheet.
    if previous_species in SPECIES_PACKAGES and previous_species != species:
        old_package = SPECIES_PACKAGES[previous_species]
        for attr, value in old_package.get("attributes", {}).items():
            key = _k(cid, "a", attr)
            current = int(st.session_state.get(key, value))
            if current <= int(value):
                st.session_state[key] = 1
        for skill, value in old_package.get("skills", {}).items():
            key = _k(cid, "s", skill)
            current = int(st.session_state.get(key, value))
            if current <= int(value):
                st.session_state[key] = 0

    for attr, value in SPECIES_PACKAGES[species].get("attributes", {}).items():
        st.session_state[_k(cid, "a", attr)] = max(1, int(value), int(st.session_state.get(_k(cid, "a", attr), 1)))
    for skill, value in SPECIES_PACKAGES[species].get("skills", {}).items():
        st.session_state[_k(cid, "s", skill)] = max(0, int(value), int(st.session_state.get(_k(cid, "s", skill), 0)))

    st.session_state[_k(cid, "meta", "previous_species")] = species


# ============================================================
#  COMPONENTES AO VIVO
# ============================================================
def _gear_mod_caption(mod):
    """Small inline green badge for a Wargear-driven bonus, matching the .gear-mod style used everywhere else."""
    if mod:
        st.markdown(f"<div style='margin-top:-6px'><span class='gear-mod'>{int(mod):+d} gear</span></div>", unsafe_allow_html=True)


def _vital_stat_block(col, label, value, maximum=None, cid=None, field=None, editable=False,
                       actor_role="gm", actor_user_id=None, actor_name="", key_prefix="", max_mod=0,
                       adjust_fn=None):
    """Render one Wounds/Shock/Wrath-style stat using the Battle Sheet's compact metric + −/+ pattern.

    The − and + controls stack vertically right beside the value, instead of
    spreading across separate columns, so this is the single source of the
    vitals widget style and every page (the Player/GM Battle Sheet, the
    Combat panel, the Ruin counter, etc.) stays compact and identical.
    `max_mod` surfaces any Wargear modifier folded into `maximum` (e.g. a
    +Wounds trinket) as the same green badge used in the Skills table.
    `maximum=None` renders just the value, for open-ended pools like Wealth
    that have no fixed ceiling to show a "current / max" against.
    By default the +/- buttons call adjust_vital(cid, field, delta, ...).
    Pass `adjust_fn` for a pool with its own adjuster (e.g. Faith uses
    adjust_faith(cid, delta, ...), which has no `field`, leave `field=None`
    in that case and the buttons drop it from the call.
    """
    display = f"{value} / {maximum}" if maximum is not None else f"{value}"
    with col:
        if editable and cid is not None:
            fn = adjust_fn or adjust_vital
            if field is not None:
                plus_args = (cid, field, +1, actor_role, actor_user_id, actor_name)
                minus_args = (cid, field, -1, actor_role, actor_user_id, actor_name)
            else:
                plus_args = (cid, +1, actor_role, actor_user_id, actor_name)
                minus_args = (cid, -1, actor_role, actor_user_id, actor_name)
            with st.container(key=f"{key_prefix}_vsb"):
                row = st.columns([5, 1], gap="small")
                row[0].metric(label, display)
                with row[1]:
                    st.button("+", key=f"{key_prefix}plus", on_click=fn, args=plus_args, use_container_width=True)
                    st.button("−", key=f"{key_prefix}minus", on_click=fn, args=minus_args, use_container_width=True)
        else:
            st.metric(label, display)
        _gear_mod_caption(max_mod)


def _ammo_stat_block(col, cid, ch, editable=False, actor_role="gm", actor_user_id=None,
                      actor_name="", key_prefix="", source_prefix="Ammo", cap_mod=None, gear_mods=None):
    """Render the Ammo Pool using the same compact metric + stacked −/+ pattern."""
    ammo_total = current_ammo(ch, gear_mods)
    ammo_max = ammo_capacity(ch, gear_mods)
    with col:
        if editable:
            with st.container(key=f"{key_prefix}_vsb"):
                acols = st.columns([5, 1], gap="small")
                with acols[0]:
                    st.markdown("<div class='vital-label'>AMMO</div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='ammo-vital-value'><b>{ammo_total}</b> / {ammo_max}</div>", unsafe_allow_html=True)
                with acols[1]:
                    if st.button("+", key=f"{key_prefix}plus", disabled=ammo_total >= ammo_max, use_container_width=True):
                        result = adjust_ammo_pool(cid, 1, actor_role=actor_role, actor_user_id=actor_user_id,
                                                  actor_name=actor_name, source=f"{source_prefix} +1")
                        if result[0]: st.rerun()
                        else: st.error(result[1])
                    if st.button("−", key=f"{key_prefix}minus", disabled=ammo_total <= 0, use_container_width=True):
                        result = adjust_ammo_pool(cid, -1, actor_role=actor_role, actor_user_id=actor_user_id,
                                                  actor_name=actor_name, source=f"{source_prefix} -1")
                        if result[0]: st.rerun()
                        else: st.error(result[1])
        else:
            st.markdown("<div class='vital-label'>AMMO</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='ammo-vital-value'><b>{ammo_total}</b> / {ammo_max}</div>", unsafe_allow_html=True)
        # cap_mod: total non-Strength bonus folded into the Ammo capacity
        # (Ammo Backpack/Bandolier flat bonuses, plus the Craft editor's
        # "Ammo" Automatic Sheet Modifier), the base-from-Strength part is
        # not a gear bonus, so it is excluded from the badge.
        _gear_mod_caption(cap_mod if cap_mod is not None else 0)


def live_vitals(cid, ch=None, gear_mods=None):
    # Accepts an already-loaded character/gear so callers that already have
    # them (battle_view always does) skip a second DB round trip and a
    # second Wargear-modifier rebuild for the same character on every render.
    ch = ch if ch is not None else load_character(cid)
    if not ch:
        return
    gear = gear_mods if gear_mods is not None else equipped_wargear_modifiers(ch)
    d = derived_traits(ch, gear)
    rank, asc = rank_from_xp(ch["earned_xp"], ch.get("rank", 1))
    user = st.session_state.get("user") or {}
    is_player = user.get("role") != "gm"
    actor_role = "player" if is_player else "gm"
    actor_user_id = user.get("id")
    actor_name = user.get("username", "")

    trio = [("cur_wounds", "Wounds", d["Max Wounds"], "wounds"),
            ("cur_shock", "Shock", d["Max Shock"], "shock"),
            ("cur_wrath", "Wrath", d["Max Wrath"], "wrath")]
    cols = st.columns(4)
    for i, (field, label, mx, mod_key) in enumerate(trio):
        _vital_stat_block(cols[i], label, ch[field], mx, cid=cid, field=field, editable=True,
                          actor_role=actor_role, actor_user_id=actor_user_id, actor_name=actor_name,
                          key_prefix=f"lv{field}{cid}", max_mod=int(gear.get(mod_key, 0) or 0))

    _ammo_stat_block(cols[3], cid, ch, editable=True, actor_role=actor_role, actor_user_id=actor_user_id,
                     actor_name=actor_name, key_prefix=f"lvammo{cid}",
                     source_prefix="Player Ammo" if is_player else "Magister Ammo",
                     cap_mod=ammo_capacity_bonus(ch, gear), gear_mods=gear)

    # Core Rulebook 2e, p.38/p.285: Corruption Points and Wealth are tracked
    # resource pools like Wounds/Shock/Wrath/Ammo above, not fixed-formula
    # Traits, so they get the same adjustable metric + −/+ treatment.
    corr_cols = st.columns(2)
    corr_info = corruption_level_info(ch.get("cur_corruption", 0))
    corr_max = corr_info["next_threshold"] if corr_info["next_threshold"] is not None else corr_info["points"]
    _vital_stat_block(corr_cols[0], "Corruption", corr_info["points"], corr_max, cid=cid, field="cur_corruption",
                      editable=True, actor_role=actor_role, actor_user_id=actor_user_id, actor_name=actor_name,
                      key_prefix=f"lvcorr{cid}")
    dn_text = f" ({corr_info['dn_modifier']:+d} DN to Corruption Tests)" if corr_info["dn_modifier"] else ""
    corr_cols[0].caption(f"Level {corr_info['level']} - {corr_info['name']}{dn_text}")

    _vital_stat_block(corr_cols[1], "Wealth", int(ch.get("cur_wealth", 0) or 0), cid=cid, field="cur_wealth",
                      editable=True, actor_role=actor_role, actor_user_id=actor_user_id, actor_name=actor_name,
                      key_prefix=f"lvwealth{cid}")
    corr_cols[1].caption("Spend on Bribery and Wargear Requisition (p.206).")

    if corr_info["level"] >= 5:
        st.error("Corruption Level 5 - Chaos Spawn (p.286). This character is lost to the Warp; the GM now controls them as a Chaos Spawn.")

    # Core Rulebook 2e, p.142: Faith only exists for characters who have
    # purchased at least one Faith Talent (Adeptus Ministorum / Adepta
    # Sororitas), hidden entirely otherwise, since it does not apply.
    f_max = faith_max(ch)
    if f_max > 0:
        faith_cols = st.columns([2, 2, 1])
        _vital_stat_block(faith_cols[0], "Faith", min(f_max, int(ch.get("cur_faith", 0) or 0)), f_max,
                          cid=cid, field=None, editable=True, actor_role=actor_role, actor_user_id=actor_user_id,
                          actor_name=actor_name, key_prefix=f"lvfaith{cid}", adjust_fn=adjust_faith)
        faith_cols[1].caption("Spend to trigger Faith Talent abilities. Restored to maximum each session or Respite (p.142).")
        with faith_cols[2]:
            st.write("")
            if st.button("Restore to Max", key=f"lvfaithrestore{cid}", use_container_width=True):
                result = restore_faith(cid, actor_role=actor_role, actor_user_id=actor_user_id, actor_name=actor_name)
                if result[0]: st.rerun()
                else: st.error(result[1])

    if asc:
        st.warning("100+ Earned XP - this character may ascend to the next Tier.")


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
def stackable_wargear(ch):
    result = []
    for w in normalize_wargear(ch.get("wargear", [])):
        d = _gear_details_dict(w.get("details", {}))
        stackable, _ = _infer_stackable_gear(w.get("name", ""), d)
        if stackable:
            result.append(w)
    return result


def _is_ammo_resource(w):
    d = _gear_details_dict(w.get("details", {}))
    category = str(d.get("category", d.get("type", ""))).strip().lower()
    text = str(w.get("name", "")).lower()
    return category in {"ammo", "ammunition", "reload"} or " ammo" in text or text.endswith("ammo") or "cartridge" in text or "cartucho" in text


def ammo_inventory(ch):
    """Return the individual Ammo stacks and their combined current quantity."""
    stacks = [w for w in stackable_wargear(ch) if _is_ammo_resource(w)]
    total = sum(max(0, int(w.get("quantity", 0) or 0)) for w in stacks)
    return stacks, total


def _wargear_craft_id(w):
    """Resolve the catalog id for legacy Wargear entries that predate craft_id."""
    try:
        cid = int(w.get("craft_id", -1) or -1)
        if cid > 0:
            return cid
    except Exception:
        pass
    name = str(w.get("name", "")).strip().lower()
    if not name:
        return -1
    try:
        rows = list_craft_items("wargear", active_only=False)
        row = next((r for r in rows if str(r.get("name", "")).strip().lower() == name), None)
        return int(row["id"]) if row else -1
    except Exception:
        return -1


def current_ammo(ch, gear_mods=None):
    """Return the character's abstract Ammo Pool, independent of ammo type stacks."""
    try:
        raw = max(0, int(ch.get("cur_ammo", 0) or 0))
        return min(raw, ammo_capacity(ch, gear_mods))
    except Exception:
        return 0


def adjust_ammo_pool(cid, delta, actor_role="gm", actor_user_id=None, actor_name="", source="Ammo Pool"):
    """Adjust the abstract Ammo Pool freely between 0 and the current carrying capacity."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM characters WHERE id=?", (int(cid),)).fetchone()
        if row is None:
            return False, "Character not found."
        ch = _decode(row)
        if actor_role == "player":
            if ch.get("kind") != "player" or int(ch.get("user_id") or -1) != int(actor_user_id or -2):
                return False, "Players can only edit their own character sheet."
        maximum = ammo_capacity(ch)
        old_val = current_ammo(ch)
        new_val = max(0, min(maximum, old_val + int(delta)))
        if new_val == old_val:
            return True, "Ammo Pool unchanged."
        new_rev = int(ch.get("revision", 0) or 0) + 1
        cur = conn.execute("UPDATE characters SET cur_ammo=?, updated_at=?, revision=? WHERE id=? AND revision=?",
                           (new_val, now_iso(), new_rev, int(cid), int(ch.get("revision", 0) or 0)))
        if cur.rowcount != 1:
            conn.rollback()
            return False, "Concurrent change detected."
        conn.commit()
        if actor_role == "player" and actor_user_id:
            record_player_audit(cid, actor_user_id, actor_name, source, [("cur_ammo", old_val, new_val)])
        return True, "Ammo Pool updated."
    except Exception as exc:
        conn.rollback()
        return False, f"Could not update Ammo Pool: {exc}"
    finally:
        conn.close()


def faith_max(ch):
    """Core Rulebook 2e, p.142: each Faith Talent purchased grants +1
    maximum Faith. Faith Talents are Talents flagged with the
    details.faith_talent option in the Craft catalog (Adeptus Ministorum /
    Adepta Sororitas Talents such as By His Will, Shield of Faith, etc.).
    Prefers the live catalog entry over the owned Talent's frozen snapshot,
    matching how Wargear modifiers are resolved."""
    catalog = {int(r["id"]): r for r in list_craft_items("talent", active_only=False)}
    count = 0
    for t in normalize_talents(ch.get("talents", [])):
        row = None
        try:
            tid = int(t.get("craft_id", -1) or -1)
            if tid > 0:
                row = catalog.get(tid)
        except Exception:
            row = None
        details = craft_details(row) if row is not None else _gear_details_dict(t.get("details", {}))
        if details.get("faith_talent"):
            count += 1
    return count


def adjust_faith(cid, delta, actor_role="gm", actor_user_id=None, actor_name="", source="Faith"):
    """Adjust Faith Points between 0 and the character's current Faith maximum."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM characters WHERE id=?", (int(cid),)).fetchone()
        if row is None:
            return False, "Character not found."
        ch = _decode(row)
        if actor_role == "player":
            if ch.get("kind") != "player" or int(ch.get("user_id") or -1) != int(actor_user_id or -2):
                return False, "Players can only edit their own character sheet."
        maximum = faith_max(ch)
        old_val = min(maximum, int(ch.get("cur_faith", 0) or 0))
        new_val = max(0, min(maximum, old_val + int(delta)))
        if new_val == old_val:
            return True, "Faith unchanged."
        new_rev = int(ch.get("revision", 0) or 0) + 1
        cur = conn.execute("UPDATE characters SET cur_faith=?, updated_at=?, revision=? WHERE id=? AND revision=?",
                           (new_val, now_iso(), new_rev, int(cid), int(ch.get("revision", 0) or 0)))
        if cur.rowcount != 1:
            conn.rollback()
            return False, "Concurrent change detected."
        conn.commit()
        if actor_role == "player" and actor_user_id:
            record_player_audit(cid, actor_user_id, actor_name, source, [("cur_faith", old_val, new_val)])
        return True, "Faith updated."
    except Exception as exc:
        conn.rollback()
        return False, f"Could not update Faith: {exc}"
    finally:
        conn.close()


def restore_faith(cid, actor_role="gm", actor_user_id=None, actor_name="", source="Faith Restored"):
    """Core Rulebook 2e, p.142: Faith is restored to maximum at the start of
    each session and whenever a Respite is completed."""
    ch = load_character(cid)
    if not ch:
        return False, "Character not found."
    return adjust_faith(cid, faith_max(ch), actor_role=actor_role, actor_user_id=actor_user_id,
                        actor_name=actor_name, source=source)


def ammo_capacity_bonus(ch, gear=None):
    """Non-Strength bonus folded into the Ammo capacity: containers plus the
    Craft editor's "Ammo" Automatic Sheet Modifier. Split out from
    ammo_capacity() so the UI can badge just the gear-driven part."""
    gear = gear if gear is not None else equipped_wargear_modifiers(ch)
    # The Craft editor's "Ammo" Automatic Sheet Modifier (Vitals / Capacity
    # group) has to land here, or setting it there would silently do nothing.
    bonus = int(gear.get("ammo", 0) or 0)
    for w in normalize_wargear(ch.get("wargear", [])):
        if not w.get("equipped", True):
            continue
        d = _gear_details_dict(w.get("details", {}))
        explicit_bonus = d.get("ammo_capacity_bonus", None)
        if explicit_bonus is not None:
            try:
                bonus += int(explicit_bonus or 0)
            except Exception:
                pass
        else:
            name = str(w.get("name", "")).lower()
            if "ammo backpack" in name:
                bonus += 10
            elif "bandolier" in name:
                bonus += 2
    return bonus


def ammo_capacity(ch, gear_mods=None):
    """Core Rulebook Ammo carrying limit: max(3, half Strength), plus explicit container bonuses."""
    gear = gear_mods if gear_mods is not None else equipped_wargear_modifiers(ch)
    attrs = effective_attributes(ch, gear)
    strength = max(0, int(attrs.get("Strength", 0) or 0))
    # The rulebook gives a whole-number inventory resource. For odd Strength values,
    # round the half-Strength value up so the character is never assigned a fractional slot.
    base = max(3, (strength + 1) // 2)
    return base + ammo_capacity_bonus(ch, gear)


def render_ammo_section(cid, ch, compact=False, gm_mode=False):
    ammo, _ammo_inventory_total = ammo_inventory(ch)
    ammo_total = current_ammo(ch)
    consumables = [w for w in stackable_wargear(ch) if not _is_ammo_resource(w)]
    if not ammo and not consumables:
        return

    capacity = ammo_capacity(ch)
    st.markdown("<div class='sectionttl'>Ammunition & Consumables</div>", unsafe_allow_html=True)

    if ammo:
        st.markdown(
            f"<div class='resource-card'><div class='resource-head'><span>AMMUNITION POOL</span><b>{ammo_total} / {capacity}</b></div>"
            f"<div class='resource-note'>Tracked by Ammo type. Spend Ammo when Reloading, using a Salvo option, or when a Complication requires it.</div></div>",
            unsafe_allow_html=True,
        )

        for idx, w in enumerate(ammo):
            d = _gear_details_dict(w.get("details", {}))
            qty = int(w.get("quantity", 1) or 1)
            label = str(w.get("name", "Ammo"))
            keywords = d.get("keywords", []) or []
            meta = ", ".join(str(x) for x in keywords) if keywords else "Matching weapon type"
            st.markdown(
                f"<div class='resource-row'><span class='resource-name'>{html.escape(label)}</span>"
                f"<span class='resource-meta'>{html.escape(meta)} · ×{qty}</span></div>",
                unsafe_allow_html=True,
            )

    if consumables:
        st.markdown("<div class='resource-subtitle'>GRENADES & MISSILES</div>", unsafe_allow_html=True)
        for idx, w in enumerate(consumables):
            d = _gear_details_dict(w.get("details", {}))
            qty = int(w.get("quantity", 1) or 1)
            category = str(d.get("category", "Consumable")).title()
            label = str(w.get("name", "Consumable"))
            craft_id = _wargear_craft_id(w)
            cols = st.columns([4.8, 1, 1])
            cols[0].markdown(
                f"<div class='resource-row consumable'><span class='resource-name'>{html.escape(label)}</span>"
                f"<span class='resource-meta'>{html.escape(category)} · ×{qty}</span></div>",
                unsafe_allow_html=True,
            )
            if cols[1].button("USE 1", key=f"battle_expl_use_{cid}_{idx}", disabled=craft_id < 1 or qty <= 0):
                result = adjust_wargear_quantity(cid, craft_id, -1,
                                                 actor_name=(st.session_state.get("user") or {}).get("username", ""),
                                                 actor_user_id=(st.session_state.get("user") or {}).get("id"),
                                                 source="Magister Consumable Used" if gm_mode else "Player Consumable Used",
                                                 actor_role="gm" if gm_mode else "player")
                if result[0]: st.rerun()
                else: st.error(result[1])
            if gm_mode and cols[2].button("+ 1", key=f"battle_expl_add_{cid}_{idx}", disabled=craft_id < 1):
                result = adjust_wargear_quantity(cid, craft_id, 1,
                                                 actor_name=(st.session_state.get("user") or {}).get("username", ""),
                                                 actor_user_id=(st.session_state.get("user") or {}).get("id"),
                                                 source="Magister Consumable Added", actor_role="gm")
                if result[0]: st.rerun()
                else: st.error(result[1])


# ============================================================
#  PLAYER UI TRANSLATION (purely visual, never touches stored data)
# ============================================================
# Only the interface chrome of the two Player pages (Battle View, Character
# Sheet) is translated: section headers, field labels, static captions, and
# the Attribute/Skill names. Character names, Notes, and catalog-driven text
# (Talent/Power/Wargear names and rules effects) are game content, not app
# chrome, and are deliberately left as written, translating them would mean
# maintaining a full Portuguese translation of the rulebook's text, which is
# out of scope for a "visual only" toggle.
TRANSLATE_PT = {
    # Attributes
    "Strength": "Força", "Toughness": "Resistência", "Agility": "Agilidade", "Initiative": "Iniciativa",
    "Willpower": "Força de Vontade", "Intellect": "Intelecto", "Fellowship": "Carisma",
    # Skills
    "Athletics": "Atletismo", "Awareness": "Percepção", "Ballistic Skill": "Perícia de Tiro",
    "Cunning": "Astúcia", "Deception": "Enganação", "Insight": "Perspicácia", "Intimidation": "Intimidação",
    "Investigation": "Investigação", "Leadership": "Liderança", "Medicae": "Medicina", "Persuasion": "Persuasão",
    "Pilot": "Pilotagem", "Psychic Mastery": "Domínio Psíquico", "Scholar": "Erudição", "Stealth": "Furtividade",
    "Survival": "Sobrevivência", "Tech": "Tecnologia", "Weapon Skill": "Perícia de Combate",
    # Derived Traits
    "Defence": "Defesa", "Resilience": "Resiliência", "Soak": "Absorção", "Determination": "Determinação",
    "Resolve": "Resolução", "Conviction": "Convicção", "Passive Awareness": "Percepção Passiva",
    "Influence": "Influência", "Speed": "Velocidade",
    # Section headers / general chrome
    "Vitals": "Vitalidade", "Derived Traits": "Traços Derivados", "Corruption": "Corrupção", "Wealth": "Riqueza",
    "Faith": "Fé", "Skills": "Perícias", "Total = Skill + Attribute": "Total = Perícia + Atributo",
    "Skill": "Perícia", "Rank": "Grau", "Attr": "Atr", "Total": "Total", "Archetype": "Arquétipo",
    "Archetype Ability": "Habilidade do Arquétipo", "Species & Chapter Abilities": "Habilidades de Espécie e Capítulo",
    "Talents": "Talentos", "No talents.": "Nenhum talento.", "Psychic Powers": "Poderes Psíquicos",
    "No Psychic Powers.": "Nenhum Poder Psíquico.", "Wargear": "Equipamento", "No wargear.": "Nenhum equipamento.",
    "Range": "Alcance", "Damage": "Dano", "AP": "PA", "Salvo": "Rajada", "Traits": "Traços", "Rarity": "Raridade",
    "Value": "Valor", "Vox Network": "Rede Vox", "Character": "Personagem",
    "Core Profile · Attributes": "Perfil Central · Atributos", "Core Profile · Skills": "Perfil Central · Perícias",
    "Species & Chapter": "Espécie e Capítulo", "Arsenal · Wargear": "Arsenal · Equipamento",
    "Advancements · Talents": "Avanços · Talentos", "Available Talents": "Talentos Disponíveis",
    "Available Psychic Powers": "Poderes Psíquicos Disponíveis", "Purchase": "Comprar",
    "Name": "Nome", "Chapter": "Capítulo", "Species": "Espécie", "Tier": "Nível", "Armour": "Armadura",
    "Other XP": "Outro XP", "Starting XP": "XP Inicial", "Earned XP": "XP Ganho", "XP Spent": "XP Gasto",
    "XP Available": "XP Disponível", "Notes": "Anotações", "Portrait": "Retrato", "Upload": "Enviar",
    "Save Portrait": "Salvar Retrato", "Battle View": "Visão de Batalha", "Character Sheet": "Ficha de Personagem",
    "Change Password": "Alterar Senha", "Sign Out": "Sair", "New Password": "Nova Senha", "Confirm": "Confirmar",
    "Change": "Alterar", "Package": "Pacote", "Size": "Tamanho", "Average": "Médio",
    "Provided by equipped Armour Wargear": "Fornecida pela Armadura equipada",
    "Advancements · Psychic Powers": "Avanços · Poderes Psíquicos",
    "Over budget by": "Acima do orçamento em",
    "Purchase Talents by meeting their registered prerequisites and spending XP.":
        "Compre Talentos cumprindo os pré-requisitos registrados e gastando XP.",
    "Keywords": "Palavras-chave", "Search Talents...": "Buscar Talentos...",
    "No Talents match the search.": "Nenhum Talento corresponde à busca.",
    "No talents purchased.": "Nenhum talento comprado.",
    "Search Psychic Powers...": "Buscar Poderes Psíquicos...",
    "No Psychic Powers match the search.": "Nenhum Poder Psíquico corresponde à busca.",
    "No Psychic Powers purchased.": "Nenhum Poder Psíquico comprado.",
    "INVENTORY": "INVENTÁRIO", "EQUIPPED": "EQUIPADO", "STOWED": "GUARDADO", "USE 1": "USAR 1",
    "REMOVE": "REMOVER", "No Wargear assigned.": "Nenhum equipamento atribuído.",
    "Summary": "Resumo",
    "Base Attribute maximum for this Species. Bonuses may raise the final total above this limit.":
        "Máximo de Atributo base para esta Espécie. Bônus podem elevar o total final acima deste limite.",
    "Custom Chapter": "Capítulo Personalizado", "Chapter applies to Adeptus Astartes characters.":
        "Capítulo se aplica a personagens Adeptus Astartes.",
    "Session": "Sessão", "No character sheet linked. Contact the Magister.":
        "Nenhuma ficha vinculada. Contate o Mestre.",
    "Requisition": "Requisição", "Requisition Log": "Registro de Requisições",
    "Ask the Magister for a piece of Wargear. It shows as Under Review, granting nothing, "
    "until approved, describe a new item, or request one already known to the campaign.":
        "Peça um item de Equipamento ao Mestre. Ele fica marcado como Em Análise, sem conceder nada, "
        "até ser aprovado, descreva um item novo ou peça um que a campanha já conhece.",
    "Request a New Item": "Requisitar Item Novo", "Description": "Descrição",
    "Submit Requisition": "Enviar Requisição", "Request a Catalog Item": "Requisitar Item do Catálogo",
    "Request This Item": "Requisitar Este Item", "The Wargear catalog is empty.": "O catálogo de Equipamento está vazio.",
    "Your Requisitions": "Suas Requisições", "No Requisitions filed yet.": "Nenhuma requisição enviada ainda.",
    "Dismiss": "Descartar",
    "Requisition submitted for the Magister's review.": "Requisição enviada para análise do Mestre.",
    "Name is required.": "O nome é obrigatório.",
    "That catalog item no longer exists.": "Esse item do catálogo não existe mais.",
    "Description / Effect": "Descrição / Efeito",
    "Name and Description / Effect are required.": "Nome e Descrição / Efeito são obrigatórios.",
    "Same fields as the Magister's own Craft catalog. Nothing here applies to your sheet "
    "until the Magister approves it.":
        "Os mesmos campos do catálogo de Craft do Mestre. Nada aqui se aplica à sua ficha "
        "até o Mestre aprovar.",
    "Ask the Magister for a piece of Wargear. It shows as Under Review, granting nothing, "
    "until approved, whether it's a brand-new item you define here (same editor the Magister "
    "uses for the Craft catalog) or one already known to the campaign.":
        "Peça um item de Equipamento ao Mestre. Ele fica marcado como Em Análise, sem conceder nada, "
        "até ser aprovado, seja um item novo que você define aqui (o mesmo editor que o Mestre usa "
        "no catálogo de Craft) ou um que a campanha já conhece.",
}


def T(text):
    """Translate a piece of Player-facing UI chrome if the Player picked
    Portuguese via the flag toggle. Purely cosmetic, never touches what is
    actually stored on the character. Falls back to the original English if
    no translation is registered or the Player has not switched languages."""
    if st.session_state.get("ui_lang") != "pt":
        return text
    return TRANSLATE_PT.get(text, text)


def _language_flag_toggle():
    """Small fixed-corner PT/EN toggle for the two Player pages: a single
    square button, styled in the app's own Cinzel/gold theme, showing the
    currently active language as text ("BR"/"US"); clicking it flips to the
    other language and the label flips with it. Session-local and purely
    visual, it only changes which strings T() returns, never any stored
    character data."""
    lang = st.session_state.get("ui_lang", "en")
    with st.container(key="lang_flags"):
        if st.button("BR" if lang == "pt" else "US", key="lang_toggle_btn", help="Português / English"):
            st.session_state["ui_lang"] = "en" if lang == "pt" else "pt"
            st.rerun()


@st.fragment(run_every=REFRESH_S)
def battle_view(cid):
    ch = load_character(cid)
    if not ch:
        st.error("Character sheet not found.")
        return
    gear_mods = equipped_wargear_modifiers(ch)
    d = derived_traits(ch, gear_mods)
    rank = int(ch.get("rank", 1) or 1)
    ncls = "npc" if ch["kind"] == "npc" else ""
    st.markdown(f"<div class='hero'><div class='nm {ncls}'>{ch['name'] or T('Character')}</div>"
                f"<div class='meta'>{ch['chapter'] or ''} &nbsp;·&nbsp; {species_label(ch['species'])} &nbsp;·&nbsp; "
                f"{T('Tier')} {ch['tier']} &nbsp;·&nbsp; {T('Rank')} {rank}</div></div>", unsafe_allow_html=True)

    st.markdown(f"<div class='sectionttl'>{T('Vitals')}</div>", unsafe_allow_html=True)
    live_vitals(cid, ch, gear_mods)

    left, right = st.columns([1.5, 1])
    with left:
        st.markdown(f"<div class='sectionttl'>{T('Derived Traits')}</div>", unsafe_allow_html=True)
        order = [("Defence", "Defence"), ("Resilience", "Resilience"), ("Soak", "Soak"),
                 ("Determination", "Determination"), ("Resolve", "Resolve"), ("Conviction", "Conviction"),
                 ("Passive Awareness", "Passive Awareness"), ("Influence", "Influence"), ("Speed", "Speed")]
        def gear_value(key):
            key_l = str(key).lower()
            # Keep in sync with derived_traits(): the Shield trait's Armour
            # Rating (shield_armour) adds to both Defence and Resilience.
            shield = int(gear_mods.get("shield_armour", 0) or 0)
            if key_l == "resilience":
                return int(gear_mods.get("armour", 0) or 0) + int(gear_mods.get("resilience", 0) or 0) + shield
            if key_l == "defence":
                return int(gear_mods.get("defence", 0) or 0) + shield
            return int(gear_mods.get(key_l, 0) or 0)

        def gear_badge(key):
            value = gear_value(key)
            return f"<span class='gear-mod'>{value:+d}</span>" if value else ""

        def derived_display(key):
            value = int(d[key])
            modifier = gear_value(key)
            return f"{value - modifier}{gear_badge(key)}"

        cards = "".join(
            f"<div class='statcard'><div class='l'>{T(pt)}</div><div class='v'>{derived_display(en)}</div></div>"
            for en, pt in order
        )
        # Corruption and Wealth (p.285, p.38) are tracked point pools, not
        # attribute-formula Traits, so they are read here from the
        # character sheet directly rather than through gear_value()/derived_display().
        corr_info = corruption_level_info(ch.get("cur_corruption", 0))
        cards += (
            f"<div class='statcard'><div class='l'>{T('Corruption')}</div>"
            f"<div class='v'>{corr_info['level']} · {html.escape(corr_info['name'])}</div></div>"
            f"<div class='statcard'><div class='l'>{T('Wealth')}</div><div class='v'>{int(ch.get('cur_wealth', 0) or 0)}</div></div>"
        )
        # Faith (p.142) only applies to characters with at least one Faith Talent.
        f_max_card = faith_max(ch)
        if f_max_card > 0:
            cards += f"<div class='statcard'><div class='l'>{T('Faith')}</div><div class='v'>{min(f_max_card, int(ch.get('cur_faith', 0) or 0))} / {f_max_card}</div></div>"
        st.markdown(f"<div class='grid'>{cards}</div>", unsafe_allow_html=True)

        st.markdown(f"<div class='sectionttl'>{T('Skills')} &nbsp;<small style='opacity:.6;letter-spacing:0'>{T('Total = Skill + Attribute')}</small></div>", unsafe_allow_html=True)
        rows = f"<div class='skhead'><span>{T('Skill')}</span><span>{T('Rank')}</span><span>{T('Attr')}</span><span>{T('Total')}</span></div>"
        base_sk = {str(k): int(v) for k, v in (ch.get("skills", {}) or {}).items()}
        base_attr = {str(k): int(v) for k, v in (ch.get("attributes", {}) or {}).items()}
        for s in SKILLS:
            attr_name = SKILLS[s]
            skill_base = int(base_sk.get(s, 0))
            attr_base = int(base_attr.get(attr_name, 0))
            skill_mod = int(gear_mods.get(str(s).lower(), 0) or 0)
            attr_mod = int(gear_mods.get(str(attr_name).lower(), 0) or 0)
            skill_total = skill_base + skill_mod
            attr_total = attr_base + attr_mod
            total = skill_total + attr_total
            skill_badge = f"<span class='gear-mod'>{skill_mod:+d}</span>" if skill_mod else ""
            attr_badge = f"<span class='gear-mod'>{attr_mod:+d}</span>" if attr_mod else ""
            # Show the base Rank/Attribute plus the green gear badge separately
            # (e.g. "5 +4"), not the already-summed value next to the badge
            # again (which read as "9 +4" and looked like the bonus was
            # being double-counted). Total still uses the full summed values.
            rows += (f"<div class='skrow'><span class='n'>{T(s)}</span><span class='c'>{skill_base}{skill_badge}</span>"
                     f"<span class='c'>+{attr_base}{attr_badge}</span><span class='t'>{total}</span></div>")
        st.markdown(rows, unsafe_allow_html=True)

    with right:
        if ch.get("archetype") and ch.get("creation_mode") == "archetype":
            st.markdown(f"<div class='sectionttl'>{T('Archetype')}</div>", unsafe_allow_html=True)
            aname = html.escape(ch['archetype'])
            st.markdown(f"<div class='tal'><span class='tn'>{aname}</span></div>", unsafe_allow_html=True)
            if ch['archetype'] in ARCHETYPE_ABILITIES:
                st.markdown(f"<div class='tal'><span class='tn'>{T('Archetype Ability')}: {html.escape(ARCHETYPE_ABILITIES[ch['archetype']])}</span></div>", unsafe_allow_html=True)
        # Chapter abilities are resolved from the latest saved character data,
        # so changing Chapter on the sheet is reflected on the next refresh.
        latest_chapter = str(ch.get("chapter", "") or "").strip()
        package = species_package(ch["species"])
        chapter_abilities = []
        if latest_chapter in CHAPTERS and ch.get("species") in ("Adeptus Astartes", "Primaris Astartes"):
            cd = CHAPTERS[latest_chapter]
            if cd.get("ability"): chapter_abilities.append(cd["ability"])
            if cd.get("tradition"): chapter_abilities.append(cd["tradition"])
        if package.get("abilities") or chapter_abilities:
            st.markdown(f"<div class='sectionttl'>{T('Species & Chapter Abilities')}</div>", unsafe_allow_html=True)
            for ability in package.get("abilities", []):
                st.markdown(f"<div class='tal'><span class='tn'>{html.escape(str(ability))}</span></div>", unsafe_allow_html=True)
            for ability in chapter_abilities:
                st.markdown(f"<div class='tal'><span class='tn'>{html.escape(str(ability))}</span></div>", unsafe_allow_html=True)

        st.markdown(f"<div class='sectionttl'>{T('Talents')}</div>", unsafe_allow_html=True)
        talent_catalog = {str(r["name"]).strip().lower(): r for r in list_craft_items("talent")}
        if ch["talents"]:
            for t in ch["talents"]:
                raw_name = str(t.get("name", ""))
                name = html.escape(raw_name)
                effect_raw = str(t.get("effect", "") or "").strip()
                if not effect_raw or effect_raw.lower().startswith("core rulebook"):
                    row = talent_catalog.get(raw_name.strip().lower())
                    if row is not None:
                        effect_raw = str(row["effect"] or "").strip()
                effect = html.escape(effect_raw)
                cost = f"<span class='tc'>{int(t.get('cost') or 0)} XP</span>" if t.get("cost") else ""
                effect_html = f"<div class='taleffect'>{effect}</div>" if effect else ""
                st.markdown(f"<div class='tal'><span class='tn'>{name}</span>{cost}{effect_html}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='tal' style='opacity:.6'>{T('No talents.')}</div>", unsafe_allow_html=True)

        st.markdown(f"<div class='sectionttl'>{T('Psychic Powers')}</div>", unsafe_allow_html=True)
        powers = normalize_powers(ch.get("powers", []))
        if powers:
            for pwr in powers:
                st.markdown(f"<div class='tal'><span class='tn'>{html.escape(str(pwr.get('name','')))}</span><div style='margin-top:5px;opacity:.75;line-height:1.35'>{html.escape(str(pwr.get('effect','')))}</div></div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='tal' style='opacity:.6'>{T('No Psychic Powers.')}</div>", unsafe_allow_html=True)

        render_ammo_section(cid, ch, gm_mode=((st.session_state.get("user") or {}).get("role") == "gm"))

        st.markdown(f"<div class='sectionttl'>{T('Wargear')}</div>", unsafe_allow_html=True)
        wargear_catalog = {str(r["name"]).strip().lower(): r for r in list_craft_items("wargear")}
        if ch["wargear"]:
            for w in ch["wargear"]:
                raw_name = str(w.get("name", ""))
                name = html.escape(raw_name)
                effect_raw = str(w.get("effect", "") or "").strip()
                if not effect_raw or effect_raw.lower().startswith("core rulebook"):
                    row = wargear_catalog.get(raw_name.strip().lower())
                    if row is not None:
                        effect_raw = str(row["effect"] or "").strip()
                effect = html.escape(effect_raw)
                effect_html = f"<div class='wgdesc'>{effect}</div>" if effect else ""
                details = w.get("details", {}) or {}
                if isinstance(details, str):
                    try: details = json.loads(details)
                    except Exception: details = {}
                stats = []
                for key, label in (("range", "Range"), ("damage", "Damage"), ("ap", "AP"), ("salvo", "Salvo"), ("traits", "Traits"), ("rarity", "Rarity"), ("value", "Value")):
                    if details.get(key) not in (None, ""):
                        stats.append(f"<span style='margin-right:12px'><b>{T(label)}</b> {html.escape(str(details[key]))}</span>")
                stats_html = f"<div style='margin-top:5px;opacity:.85;font-size:.78rem'>{''.join(stats)}</div>" if stats else ""
                st.markdown(f"<div class='wg'><b>{name}</b>{stats_html}{effect_html}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='wg' style='opacity:.6'>{T('No wargear.')}</div>", unsafe_allow_html=True)

        pending_req = [r for r in list_requisitions(character_id=cid) if r["status"] == "pending"]
        for r in pending_req:
            label = "Em Análise" if st.session_state.get("ui_lang") == "pt" else "Under Review"
            st.markdown(
                f"<div class='wg wg-pending'><b>{html.escape(r['name'])}</b>"
                f"<span class='wg-pending-tag'>{label}</span>"
                f"<div class='wgdesc'>{html.escape(r.get('effect','') or '')}</div></div>",
                unsafe_allow_html=True,
            )

        st.markdown(f"<div class='sectionttl'>{T('Vox Network')}</div>", unsafe_allow_html=True)
        vox_live(cid)


# ============================================================
#  CHARACTER SHEET EDITOR (fully editable)
# ============================================================
def _k(cid, sec, f):
    return f"f_{cid}_{sec}_{f}"


def _sync_character_widgets(cid, ch, species_list):
    meta_key = _k(cid, "meta", "db_revision")
    db_revision = int(ch.get("revision", 0) or 0)
    previous = st.session_state.get(meta_key)
    if previous is not None and int(previous) == db_revision:
        return False
    if previous is not None:
        for a in ATTRS: st.session_state[_k(cid, "a", a)] = int(ch["attributes"].get(a, 1))
        for sk in SKILLS: st.session_state[_k(cid, "s", sk)] = int(ch["skills"].get(sk, 0))
        st.session_state[_k(cid, "t", "name")] = ch.get("name", "")
        st.session_state[_k(cid, "t", "chapter")] = ch.get("chapter", "") or ""
        st.session_state[_k(cid, "t", "notes")] = ch.get("notes", "") or ""
        st.session_state[_k(cid, "n", "tier")] = int(ch.get("tier", 1))
        st.session_state[_k(cid, "n", "armour")] = int(ch.get("armour", 0))
        st.session_state[_k(cid, "n", "other")] = int(ch.get("other_xp", 0))
        st.session_state[_k(cid, "sel", "arch")] = ch.get("archetype", "") or ""
        if ch.get("species") in species_list: st.session_state[_k(cid, "sel", "sp")] = ch.get("species")
    st.session_state[meta_key] = db_revision
    st.session_state[_k(cid, "meta", "last_sync")] = now_iso()
    return previous is not None


@st.fragment(run_every=REFRESH_S)
def edit_view(cid, gm_mode=False):
    # Keep the official catalog available for both GM management and Player talent purchases.
    sync_official_craft_catalog()
    ch = load_character(cid)
    if not ch:
        st.error("Character sheet not found.")
        return
    camp = get_campaign()
    species_list = NPC_SPECIES if ch["kind"] == "npc" else PLAYER_SPECIES

    synced_from_remote = _sync_character_widgets(cid, ch, species_list)
    if synced_from_remote: st.info("Character sheet synchronized with the latest version from another session.")

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
    # Advanced creation: the Magister only enables the mode. The Player
    # chooses Species on the character sheet. No Archetype is used.
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
                # Species and Archetype are independent choices the Magister sets
                # separately (see cb_archetype_change), this is only a hint of
                # the Archetype's Core Rulebook default, never forced onto the sheet.
                st.caption(f"Tier {ad['tier']} · Core Rulebook Species: {species_label(ad['species'])} · {ad['xp']} XP · {ad['faction']}")
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

    if mode == "advanced":
        fcols = st.columns([1.4, 2.6])
        current_faction = str(ch.get("faction", "") or "")
        faction_options = [""] + FACTION_OPTIONS
        if current_faction not in faction_options: faction_options.append(current_faction)
        faction_value = fcols[0].selectbox("Faction", faction_options, index=faction_options.index(current_faction), key=_k(cid, "sel", "faction"), format_func=lambda x: "None" if not x else x)
        kw_default = ", ".join(ch.get("keywords", []) or [])
        if st.session_state.get(spk) == "Aeldari":
            psyker_key = _k(cid, "sel", "advanced_psyker")
            psyker_default = "PSYKER" in {str(x).upper() for x in (ch.get("keywords", []) or [])}
            psyker = st.checkbox("Take PSYKER Keyword", value=psyker_default, key=psyker_key, help="Aeldari may choose the PSYKER Keyword during Advanced Character Creation.")
        else:
            psyker = False
        keyword_text = fcols[1].text_input("Additional Keywords", value=kw_default, key=_k(cid, "t", "keywords"), help="Advanced Creation: choose Keywords with the GM. Species Keywords are automatic.")
        keyword_list = [x.strip() for x in re.split(r",|;", keyword_text) if x.strip()]
        if psyker and not any(str(x).strip().lower() == "psyker" for x in keyword_list): keyword_list.append("PSYKER")
        if not psyker: keyword_list = [x for x in keyword_list if str(x).strip().lower() != "psyker"]
        st.session_state[_k(cid, "meta", "faction")] = faction_value
        st.session_state[_k(cid, "meta", "keywords")] = keyword_list
    else:
        st.session_state[_k(cid, "meta", "faction")] = str(ch.get("faction", "") or ARCHETYPES.get(st.session_state.get(ark, ""), {}).get("faction", ""))
        st.session_state[_k(cid, "meta", "keywords")] = list(ch.get("keywords", []) or [])

    c = st.columns([2, 2, 2])
    c[0].text_input(T("Name"), key=_k(cid, "t", "name"))
    current_chapter = st.session_state.get(_k(cid, "t", "chapter"), ch.get("chapter") or "")
    if st.session_state.get(spk) in ("Adeptus Astartes", "Primaris Astartes"):
        chapter_choice = c[1].selectbox(
            T("Chapter"),
            CHAPTER_OPTIONS,
            index=(CHAPTER_OPTIONS.index(current_chapter) if current_chapter in CHAPTER_OPTIONS else len(CHAPTER_OPTIONS)-1),
            key=_k(cid, "sel", "chapter"),
        )
        if chapter_choice == "Other / Successor Chapter":
            c[1].text_input(T("Custom Chapter"), value="" if current_chapter in CHAPTER_OPTIONS else current_chapter, key=_k(cid, "t", "chapter_custom"))
            st.session_state[_k(cid, "t", "chapter")] = st.session_state.get(_k(cid, "t", "chapter_custom"), "")
        else:
            st.session_state[_k(cid, "t", "chapter")] = chapter_choice
    else:
        st.session_state[_k(cid, "t", "chapter")] = ""
        c[1].caption(T("Chapter applies to Adeptus Astartes characters."))
    if gm_mode:
        if mode == "archetype":
            c[2].selectbox(
                "Species", species_list, format_func=species_label, key=spk,
                on_change=cb_species_change, args=(cid,),
            )
        else:
            # In Advanced Character Creation the Magister does not choose Species.
            # Leave this field completely out of the Magister's character editor.
            c[2].markdown("**Species**")
            c[2].caption("Chosen by the Player")
    elif mode != "advanced":
        c[2].text_input(T("Species"), value=species_label(ch.get("species") or "Unknown"), disabled=True, key=f"player_species_{cid}")
    else:
        c[2].markdown(f"**{T('Species')}**")
        c[2].caption(species_label(st.session_state[spk]))
    if gm_mode:
        c = st.columns([1, 1, 1, 1.4, 1])
        # Tier is a normal sheet field (saved through save_build() below like
        # everything else here), so the Magister can simply type a new value.
        c[0].number_input("Tier", 1, MAX_TIER, key=_k(cid, "n", "tier"))
        c[1].markdown("**Armour**")
        c[1].caption("From equipped Armour")
        # Earned XP is awarded only when the Magister closes a session, so it
        # stays read-only here, editing a character sheet must never grant XP
        # by accident. Rank/Tier corrections with full undo history are still
        # available in Progression > Corrections & Undo.
        c[2].metric("Earned XP", int(ch.get("earned_xp", 0)))
        rank_key = _k(cid, "sel", "gm_rank")
        st.session_state.setdefault(rank_key, int(ch.get("rank", 1)))
        c[3].selectbox("Rank", [1, 2, 3], format_func=rank_label, key=rank_key)
        c[4].markdown("<div style='padding-top:28px'></div>", unsafe_allow_html=True)
        if c[4].button("Apply Rank", key=f"gm_apply_rank_{cid}", use_container_width=True,
                       disabled=int(st.session_state[rank_key]) == int(ch.get("rank", 1))):
            # correct_progression_state() (unlike set_rank()) allows moving Rank
            # in either direction, matching "the Magister can change everything".
            # Earned XP and Tier are passed through unchanged, only Rank moves.
            if correct_progression_state(cid, int(ch.get("earned_xp", 0)), int(st.session_state[rank_key]), int(ch.get("tier", 1))):
                st.rerun()
        c2 = st.columns([1, 3])
        c2[0].number_input("Other XP", 0, 100000, key=_k(cid, "n", "other"))
    else:
        c = st.columns([1, 1, 1, 2])
        c[0].metric(T("Tier"), int(st.session_state[_k(cid, "n", "tier")]))
        c[1].markdown(f"**{T('Armour')}**")
        c[1].caption(T("Provided by equipped Armour Wargear"))
        c[2].number_input(T("Other XP"), 0, 100000, key=_k(cid, "n", "other"))
        c[3].markdown(f"**{T('Rank')}:** {rank_label(ch.get('rank', 1))}<br><small></small>", unsafe_allow_html=True)

    st.markdown(f"<div class='sheet-banner'>{T('Core Profile · Attributes')}</div>", unsafe_allow_html=True)
    acol = st.columns(4)
    attr_max = SPECIES_ATTRIBUTE_MAX.get(st.session_state.get(spk, ""), {a: 12 for a in ATTRS})
    sheet_gear_mods = equipped_wargear_modifiers({**ch, "wargear": normalize_wargear(ch.get("wargear", []))})
    for i, a in enumerate(ATTRS):
        max_rating = int(attr_max.get(a, 12))
        if int(st.session_state[_k(cid, "a", a)]) > max_rating:
            st.session_state[_k(cid, "a", a)] = max_rating
        with acol[i % 4]:
            ac = st.columns([4, 1])
            ac[0].number_input(T(a), 1, max_rating, key=_k(cid, "a", a), help=T("Base Attribute maximum for this Species. Bonuses may raise the final total above this limit."))
            mod = int(sheet_gear_mods.get(a.lower(), 0) or 0)
            if mod:
                ac[1].markdown(f"<div class='gear-mod-sheet'>{mod:+d}</div>", unsafe_allow_html=True)
    # Read current values before rendering the Skill pools.
    # Streamlit executes this function top-to-bottom, so these dictionaries
    # must exist before the skill widgets use them.
    cur_attr = {a: int(st.session_state[_k(cid, "a", a)]) for a in ATTRS}

    if mode == "archetype" and st.session_state.get(ark) in ARCHETYPE_PACKAGES:
        ap = ARCHETYPE_PACKAGES[st.session_state[ark]]
        any_count = int(ap.get("skills_any_count", 0) or 0)
        any_to = int(ap.get("skills_any_to", 0) or 0)
        if any_count and any_to:
            st.markdown("#### Archetype Skill Choice")
            choices_key = _k(cid, "meta", "archetype_choices")
            choices = st.session_state.setdefault(choices_key, dict(ch.get("archetype_choices", {}) or {}))
            selected = list(choices.get("skills", []) or [])
            options = list(SKILLS.keys())
            selected = [x for x in selected if x in options]
            for n in range(any_count):
                available_options = [x for x in options if x not in selected[:n]]
                current_choice = selected[n] if n < len(selected) and selected[n] in available_options else available_options[0]
                choice = st.selectbox(f"Skill to raise to {any_to} · {n+1}", available_options, index=available_options.index(current_choice), key=f"{choices_key}_{n}")
                if n < len(selected): selected[n] = choice
                else: selected.append(choice)
            choices["skills"] = selected[:any_count]
            st.session_state[choices_key] = choices
            for choice in selected[:any_count]:
                st.session_state[_k(cid, "s", choice)] = max(int(st.session_state[_k(cid, "s", choice)]), any_to)


    st.markdown(f"<div class='sheet-banner'>{T('Core Profile · Skills')}</div>", unsafe_allow_html=True)
    scol = st.columns(3)
    for i, s in enumerate(SKILLS):
        with scol[i % 3]:
            cc = st.columns([3, 1])
            cc[0].number_input(T(s), 0, 8, key=_k(cid, "s", s))
            skill_base = int(st.session_state[_k(cid, "s", s)])
            attr_base = int(st.session_state[_k(cid, "a", SKILLS[s])])
            skill_mod = int(sheet_gear_mods.get(s.lower(), 0) or 0)
            attr_mod = int(sheet_gear_mods.get(SKILLS[s].lower(), 0) or 0)
            pool = skill_base + skill_mod + attr_base + attr_mod
            badges = ""
            if skill_mod:
                badges += f"<span class='gear-mod'>{skill_mod:+d}</span>"
            if attr_mod:
                badges += f"<span class='gear-mod'>{attr_mod:+d}</span>"
            cc[1].markdown(f"<div style='padding-top:30px;color:#e8c96a;font-family:Cinzel'>{pool}</div>{badges}",
                           unsafe_allow_html=True)

    cur_skill = {s: int(st.session_state[_k(cid, "s", s)]) for s in SKILLS}

    package = species_package(st.session_state[spk])
    if package:
        st.markdown(f"#### {T('Species & Chapter')}")
        st.caption(f"{T('Package')}: {package.get('xp', 0)} XP · "
                   f"{T('Speed')} {package.get('speed', species_speed(st.session_state[spk]))} · "
                   f"{T('Size')} {T(package.get('size', 'Average'))}")

        abilities = list(package.get("abilities", []))
        if st.session_state.get(spk) in ("Adeptus Astartes", "Primaris Astartes"):
            selected_chapter = st.session_state.get(_k(cid, "t", "chapter"), "")
            if selected_chapter in CHAPTERS:
                cd = CHAPTERS[selected_chapter]
                if cd.get("ability"): abilities.append(cd["ability"])
                if cd.get("tradition"): abilities.append(cd["tradition"])
        if abilities:
            st.markdown(f"#### {T('Species & Chapter Abilities')}")
            for ability in abilities:
                st.markdown(f"<div class='tal'><span class='tn'>{html.escape(str(ability))}</span></div>", unsafe_allow_html=True)

    st.markdown(f"<div class='sheet-banner'>{T('Arsenal · Wargear')}</div>", unsafe_allow_html=True)

    # Talents are purchased by Players when their Keywords/prerequisites allow them.
    # Wargear is assigned and equipped by the Magister.
    catalog_talents = list_craft_items("talent")
    catalog_wargear = list_craft_items("wargear")
    current_build = {**ch,
                     "species": st.session_state[spk],
                     "archetype": st.session_state.get(ark, ""),
                     "creation_mode": mode,
                     "attributes": cur_attr,
                     "skills": cur_skill,
                     "tier": int(st.session_state[_k(cid, "n", "tier")]),
                     "other_xp": int(st.session_state[_k(cid, "n", "other")]),
                     "talents": normalize_talents(ch.get("talents", [])),
                     "archetype_choices": st.session_state.get(_k(cid, "meta", "archetype_choices"), ch.get("archetype_choices", {}))}
    # The XP budget is the character's OWN Tier (Core Rulebook 2e: "starting
    # XP" is Tier x100), not the campaign's current Tier setting, those only
    # coincide for Players kept in lockstep with the campaign. A Generic NPC
    # mob (or any NPC) can be built at a different Tier on purpose, and using
    # the campaign Tier here made "XP Spent"/"XP Available" wrong for them.
    available_xp = starting_xp(current_build["tier"], advanced=(mode == "advanced")) + int(ch.get("earned_xp", 0)) - xp_spent(current_build)
    keys = sorted(character_keywords(current_build))

    st.markdown(f"<div class='sheet-banner'>{T('Advancements · Talents')}</div>", unsafe_allow_html=True)
    st.caption(T("Purchase Talents by meeting their registered prerequisites and spending XP."))
    if keys:
        st.caption(T("Keywords") + ": " + ", ".join(k.title() for k in keys))

    if not gm_mode:
        owned_ids = {int(t.get("craft_id", -1) or -1) for t in normalize_talents(ch.get("talents", []))}
        visible = [r for r in catalog_talents if int(r["id"]) not in owned_ids and craft_keyword_match(current_build, r)]
        with st.expander(f"{T('Available Talents')}  ·  {len(visible)}", expanded=False):
            talent_query = st.text_input("", key=f"talent_search_{cid}", placeholder=T("Search Talents..."), label_visibility="collapsed")
            if talent_query.strip():
                q = talent_query.strip().lower()
                visible = [r for r in visible if q in str(r.get("name", "")).lower()]
            if visible:
                for r in visible:
                    rid = int(r["id"])
                    status, reason = craft_purchase_status(current_build, r, available_xp)
                    color = craft_status_color(status)
                    cost = int(r.get("cost", 0) or 0)
                    cols = st.columns([7, 1.25, 1.55])
                    cols[0].markdown(craft_description_html(r, "craft", name_color=color, title_text=craft_status_text(status, reason)), unsafe_allow_html=True)
                    cols[1].markdown(f"<span class='craft-shop-cost'>{cost} XP</span>", unsafe_allow_html=True)
                    if cols[2].button(T("Purchase"), key=f"talent_buy_{cid}_{rid}", disabled=status != "green", use_container_width=True):
                        result = assign_craft_to_character(cid, rid, "talent", actor_name=(st.session_state.get("user") or {}).get("username", ""), actor_user_id=(st.session_state.get("user") or {}).get("id"), source="Talent Purchase")
                        if result[0]: st.rerun()
                        st.error(result[1])
            else:
                st.caption(T("No Talents match the search."))
    else:
        if catalog_talents:
            with st.expander(f"Assign Talent  ·  {len(catalog_talents)}", expanded=False):
                talent_query = st.text_input("", key=f"gm_talent_search_{cid}", placeholder="Search Talents...", label_visibility="collapsed")
                filtered_talents = [r for r in catalog_talents if talent_query.strip().lower() in str(r.get("name", "")).lower()] if talent_query.strip() else catalog_talents
                for r in filtered_talents:
                    rid = int(r["id"]); cols = st.columns([7, 1.55])
                    cols[0].markdown(craft_description_html(r, "talent"), unsafe_allow_html=True)
                    if cols[1].button("Assign", key=f"gm_talent_add_{cid}_{rid}", use_container_width=True):
                        result = assign_craft_to_character(cid, rid, "talent", source="Magister Talent Assignment")
                        if result[0]: st.rerun()
                        st.error(result[1])
                if not filtered_talents: st.caption("No Talents match the search.")

    owned_talents = normalize_talents(ch.get("talents", []))
    if owned_talents:
        for t in owned_talents:
            tc = st.columns([2.2, 4.8, 1])
            tc[0].markdown(f"**{html.escape(str(t.get('name', '')))}**")
            tc[1].caption(str(t.get("effect", "")))
            tc[2].caption(f"{int(t.get('cost', 0) or 0)} XP")
    else:
        st.caption(T("No talents purchased."))

    st.markdown(f"<div class='sheet-banner'>{T('Advancements · Psychic Powers')}</div>", unsafe_allow_html=True)
    owned_powers = normalize_powers(ch.get("powers", []))
    if not gm_mode:
        catalog_powers = list_craft_items("power")
        owned_power_ids = {int(x.get("craft_id", -1) or -1) for x in owned_powers}
        visible_powers = [r for r in catalog_powers if int(r["id"]) not in owned_power_ids and craft_keyword_match(current_build, r)]
        with st.expander(f"{T('Available Psychic Powers')}  ·  {len(visible_powers)}", expanded=False):
            power_query = st.text_input("", key=f"power_search_{cid}", placeholder=T("Search Psychic Powers..."), label_visibility="collapsed")
            if power_query.strip():
                q = power_query.strip().lower()
                visible_powers = [r for r in visible_powers if q in str(r.get("name", "")).lower()]
            if visible_powers:
                for r in visible_powers:
                    rid = int(r["id"])
                    status, reason = craft_purchase_status(current_build, r, available_xp)
                    color = craft_status_color(status)
                    cost = int(r.get("cost", 0) or 0)
                    cols = st.columns([7, 1.25, 1.55])
                    cols[0].markdown(craft_description_html(r, "craft", name_color=color, title_text=craft_status_text(status, reason)), unsafe_allow_html=True)
                    cols[1].markdown(f"<span class='craft-shop-cost'>{cost} XP</span>", unsafe_allow_html=True)
                    if cols[2].button(T("Purchase"), key=f"power_buy_{cid}_{rid}", disabled=status != "green", use_container_width=True):
                        result = assign_craft_to_character(cid, rid, "power", actor_name=(st.session_state.get("user") or {}).get("username", ""), actor_user_id=(st.session_state.get("user") or {}).get("id"), source="Psychic Power Purchase")
                        if result[0]: st.rerun()
                        st.error(result[1])
            else:
                st.caption(T("No Psychic Powers match the search."))
    else:
        catalog_powers = list_craft_items("power")
        if catalog_powers:
            with st.expander(f"Assign Psychic Power  ·  {len(catalog_powers)}", expanded=False):
                power_query = st.text_input("", key=f"gm_power_search_{cid}", placeholder="Search Psychic Powers...", label_visibility="collapsed")
                filtered_powers = [r for r in catalog_powers if power_query.strip().lower() in str(r.get("name", "")).lower()] if power_query.strip() else catalog_powers
                for r in filtered_powers:
                    rid = int(r["id"]); cols = st.columns([7, 1.55])
                    cols[0].markdown(craft_description_html(r, "power"), unsafe_allow_html=True)
                    if cols[1].button("Assign", key=f"gm_power_add_{cid}_{rid}", use_container_width=True):
                        result = assign_craft_to_character(cid, rid, "power", source="Magister Psychic Power Assignment")
                        if result[0]: st.rerun()
                        st.error(result[1])
                if not filtered_powers: st.caption("No Psychic Powers match the search.")

    if gm_mode and catalog_wargear:
        with st.expander(f"Assign Wargear  ·  {len(catalog_wargear)}", expanded=False):
            gear_query = st.text_input("", key=f"gm_gear_search_{cid}", placeholder="Search Wargear...", label_visibility="collapsed")
            gear_keywords = sorted({kw for row in catalog_wargear for kw in craft_keyword_values(row)}, key=str.lower)
            selected_gear_keywords = st.multiselect("Keywords", gear_keywords, key=f"gm_gear_keywords_{cid}", placeholder="Filter by Keyword...", label_visibility="collapsed")
            filtered_gear = [r for r in catalog_wargear if gear_query.strip().lower() in str(r.get("name", "")).lower()] if gear_query.strip() else list(catalog_wargear)
            filtered_gear = craft_keyword_filter(filtered_gear, selected_gear_keywords)
            for r in filtered_gear:
                rid = int(r["id"]); cols = st.columns([7, 1.55])
                cols[0].markdown(craft_description_html(r, "wargear"), unsafe_allow_html=True)
                if cols[1].button("Assign", key=f"gm_gear_add_{cid}_{rid}", use_container_width=True):
                    result = assign_craft_to_character(cid, rid, "wargear", source="Magister Wargear Assignment")
                    if result[0]: st.rerun()
                    st.error(result[1])
            if not filtered_gear: st.caption("No Wargear matches the current filters.")

    wdf = normalize_wargear(st.session_state.get(_k(cid, "meta", "archetype_starting_wargear"), ch.get("wargear", [])))
    if mode == "archetype" and st.session_state.get(ark, "") and not wdf:
        starting_wdf = archetype_starting_wargear(st.session_state.get(ark, ""))
        if starting_wdf:
            wdf = normalize_wargear(starting_wdf + starting_ammo_for_wargear(starting_wdf))

    if wdf:
        st.markdown("<div class='arsenal-panel'>", unsafe_allow_html=True)
        st.markdown(f"<div class='resource-subtitle'>{T('INVENTORY')}</div>", unsafe_allow_html=True)
        for idx, w in enumerate(wdf):
            qty = max(1, int(w.get("quantity", 1) or 1))
            details_w = _gear_details_dict(w.get("details", {}))
            stackable_w = bool(details_w.get("stackable", False))
            ammo_w = _is_ammo_resource(w)
            display_name = html.escape(str(w.get("name", "")))
            effect = html.escape(str(w.get("effect", "") or ""))
            category = html.escape(str(details_w.get("category", details_w.get("type", "Wargear")) or "Wargear").title())
            wc2 = st.columns([3.2, 5.2, 1.15, 1.15])
            wc2[0].markdown(
                f"<div class='inventory-name'>{display_name} <span class='inventory-qty'>{('× ' + str(qty)) if stackable_w else ''}</span></div>"
                f"<div class='inventory-meta'>{category}</div>", unsafe_allow_html=True)
            wc2[1].markdown(f"<div class='inventory-effect'>{effect}</div>", unsafe_allow_html=True)

            if stackable_w:
                if gm_mode:
                    qcols = wc2[2].columns(2)
                    if qcols[0].button("−", key=f"sheet_qm_{cid}_{idx}"):
                        result = adjust_wargear_quantity(cid, _wargear_craft_id(w), -1,
                                                         actor_name=(st.session_state.get("user") or {}).get("username", ""),
                                                         actor_user_id=(st.session_state.get("user") or {}).get("id"),
                                                         source="Magister Wargear Stack -1", actor_role="gm")
                        if result[0]: st.rerun()
                        else: st.error(result[1])
                    if qcols[1].button("+", key=f"sheet_qp_{cid}_{idx}"):
                        result = adjust_wargear_quantity(cid, _wargear_craft_id(w), 1,
                                                         actor_name=(st.session_state.get("user") or {}).get("username", ""),
                                                         actor_user_id=(st.session_state.get("user") or {}).get("id"),
                                                         source="Magister Wargear Stack +1", actor_role="gm")
                        if result[0]: st.rerun()
                        else: st.error(result[1])
                else:
                    if wc2[2].button(T("USE 1"), key=f"sheet_use_{cid}_{idx}", disabled=qty <= 0 or _wargear_craft_id(w) < 1):
                        result = adjust_wargear_quantity(cid, _wargear_craft_id(w), -1,
                                                         actor_name=(st.session_state.get("user") or {}).get("username", ""),
                                                         actor_user_id=(st.session_state.get("user") or {}).get("id"),
                                                         source="Player Wargear Used", actor_role="player")
                        if result[0]: st.rerun()
                        else: st.error(result[1])
            else:
                equipped = bool(w.get("equipped", True))
                if wc2[2].button(T("EQUIPPED") if equipped else T("STOWED"), key=f"sheet_eq_{cid}_{idx}"):
                    wdf[idx]["equipped"] = not equipped
                    result = save_build(cid, ch["name"], ch.get("chapter", ""), st.session_state[spk], int(st.session_state[_k(cid, "n", "tier")]),
                                        cur_attr, cur_skill, normalize_talents(ch.get("talents", [])), json.dumps(wdf, ensure_ascii=False),
                                        int(st.session_state[_k(cid, "n", "armour")]), ch.get("notes", ""), int(st.session_state[_k(cid, "n", "other")]),
                                        st.session_state.get(ark, ""), mode, actor_role=("gm" if gm_mode else "player"),
                                        actor_user_id=(st.session_state.get("user") or {}).get("id"),
                                        actor_name=(st.session_state.get("user") or {}).get("username", ""), source="Wargear Equip Toggle",
                                        expected_revision=int(ch.get("revision", 0) or 0))
                    if result[0]: st.rerun()
                    else: st.error(result[1])

            if wc2[3].button(T("REMOVE"), key=f"sheet_rm_{cid}_{idx}"):
                wdf.pop(idx)
                result = save_build(cid, ch["name"], ch.get("chapter", ""), st.session_state[spk], int(st.session_state[_k(cid, "n", "tier")]),
                                    cur_attr, cur_skill, normalize_talents(ch.get("talents", [])), json.dumps(wdf, ensure_ascii=False),
                                    int(st.session_state[_k(cid, "n", "armour")]), ch.get("notes", ""), int(st.session_state[_k(cid, "n", "other")]),
                                    st.session_state.get(ark, ""), mode, actor_role=("gm" if gm_mode else "player"),
                                    actor_user_id=(st.session_state.get("user") or {}).get("id"),
                                    actor_name=(st.session_state.get("user") or {}).get("username", ""), source="Wargear Removal",
                                    expected_revision=int(ch.get("revision", 0) or 0))
                if result[0]: st.rerun()
                else: st.error(result[1])
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.caption(T("No Wargear assigned."))

    talents = normalize_talents(ch.get("talents", []))
    wargear = normalize_wargear(wdf)
    wc = st.columns(2)
    wc[0].markdown(f"**{T('Summary')}**")
    wc[0].caption(f"{len(wargear)} wargear item(s) · {len(talents)} talent(s)")
    wc[1].text_area(T("Notes"), key=_k(cid, "t", "notes"), height=110)

    save_result = save_build(
        cid, st.session_state[_k(cid, "t", "name")], st.session_state[_k(cid, "t", "chapter")],
        st.session_state[spk], int(st.session_state[_k(cid, "n", "tier")]), cur_attr, cur_skill,
        talents, json.dumps(wargear, ensure_ascii=False), st.session_state[_k(cid, "n", "armour")],
        st.session_state[_k(cid, "t", "notes")], st.session_state[_k(cid, "n", "other")],
        st.session_state.get(ark, ""),
        mode,
        actor_role=("gm" if gm_mode else "player"),
        actor_user_id=(st.session_state.get("user") or {}).get("id"),
        actor_name=(st.session_state.get("user") or {}).get("username", ""),
        source=("Magister Character Sheet" if gm_mode else "Player Character Sheet"),
        expected_revision=int(st.session_state.get(_k(cid, "meta", "db_revision"), ch.get("revision", 0) or 0)),
        faction=st.session_state.get(_k(cid, "meta", "faction"), ch.get("faction", "")),
        keywords=st.session_state.get(_k(cid, "meta", "keywords"), ch.get("keywords", [])),
        archetype_choices=st.session_state.get(_k(cid, "meta", "archetype_choices"), ch.get("archetype_choices", {}))
    )
    if save_result[0]:
        latest = load_character(cid)
        if latest: st.session_state[_k(cid, "meta", "db_revision")] = int(latest.get("revision", 0) or 0)
    else:
        latest = load_character(cid)
        if latest: _sync_character_widgets(cid, latest, species_list)
        st.warning(save_result[1])
        st.stop()

    cur = dict(current_build); cur.update({"talents": talents})
    spent = xp_spent(cur); start = starting_xp(cur["tier"], advanced=(mode == "advanced")); avail = start + int(ch["earned_xp"]) - spent
    st.divider()
    x = st.columns(4)
    x[0].metric(T("Starting XP"), start); x[1].metric(T("Earned XP"), ch["earned_xp"])
    x[2].metric(T("XP Spent"), spent); x[3].metric(T("XP Available"), avail)
    if avail < 0:
        st.error(f"{T('Over budget by')} {-avail} XP.")

    with st.expander(T("Portrait")):
        if ch.get("portrait"):
            st.image(ch["portrait"], width=170)
        up = st.file_uploader(T("Upload"), type=["png", "jpg", "jpeg"], key=f"port_{cid}")
        if up is not None and st.button(T("Save Portrait"), key=f"pb_{cid}"):
            set_portrait(cid, up.getvalue(), actor_role=("gm" if gm_mode else "player"),
                         actor_user_id=(st.session_state.get("user") or {}).get("id"),
                         actor_name=(st.session_state.get("user") or {}).get("username", ""),
                         source=("Magister Character Sheet" if gm_mode else "Player Character Sheet")); st.rerun()


# ============================================================
#  PAGES
# ============================================================
@contextmanager
def _section(title, help_text, expanded=False, key=None):
    """Standard collapsed-by-default section wrapper used across every
    Magister tab: a title, a small circled '?' that shows its explanation on
    hover (no click needed), and content hidden until clicked open.

    `expanded` only sets the INITIAL state. A stable `key` (auto-derived from
    `title` when omitted) makes Streamlit track the open/closed state in
    st.session_state, so once the Magister manually expands a section it
    stays expanded across reruns (switching tabs, other widgets changing,
    etc.) instead of snapping back to `expanded` every time. Callers whose
    title text changes at runtime (a live count, an edit-mode toggle) MUST
    pass an explicit `key`, since an auto-derived one would change together
    with the title and lose the remembered state right when it matters most.

    (st.expander in this Streamlit version has no `help=` parameter, so the
    tooltip is a plain HTML span with a native browser hover title, placed
    next to the section's own expander.)
    """
    if key is None:
        key = "sec_" + re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    hcol, qcol = st.columns([30, 1])
    with qcol:
        st.markdown(f"<span class='info-tip' title='{html.escape(str(help_text))}'>?</span>", unsafe_allow_html=True)
    with hcol:
        exp = st.expander(title, expanded=expanded, key=key)
    with exp:
        yield


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

        # Hidden Spectator Code entry: an inconspicuous rune rather than a
        # labelled "Spectator Login" control, per the Magister's request that
        # it not be obvious on the login screen. Anyone who knows to look can
        # still find it; nobody stumbles on it by accident.
        with st.expander("◈", expanded=False):
            with st.form("spectator_login"):
                spec_code = st.text_input("", placeholder="Vox-Cipher", label_visibility="collapsed")
                spec_ok = st.form_submit_button("Tune In")
            if spec_ok:
                if verify_spectator_code(spec_code):
                    st.session_state.user = {"id": None, "username": "Spectator", "role": "spectator"}
                    st.rerun()
                else:
                    st.error("Signal not recognised.")

    st.markdown("<div class='foot'>THE EMPEROR PROTECTS</div>", unsafe_allow_html=True)


def folder_label(fid, folders):
    for f in folders:
        if f["id"] == fid:
            return f["name"]
    return "No folder"


@st.fragment(run_every=REFRESH_S)
def char_row(ch, folders):
    fresh = load_character(int(ch["id"]))
    if fresh is not None:
        ch = fresh
    # Compute the Wargear modifiers once for this row and thread them through
    # every derived computation below, instead of each one rebuilding the
    # same lookup independently, this row re-renders every REFRESH_S for
    # every character the GM has open, across every connected session.
    gear = equipped_wargear_modifiers(ch)
    rank = int(ch.get("rank", 1) or 1); d = derived_traits(ch, gear)
    ncls = "npc" if ch["kind"] == "npc" else ""
    vs = ("<span class='vlive'>ACTIVE</span>" if ch["comms_on"]
          else ("<span class='vdead'>CUT</span>" if secs_since(ch["comms_changed_at"]) < COMMS_FADE_S else ""))
    c = st.columns([3.2, 1.6, 0.9, 1, 0.6])
    with c[0]:
        label = f"{ch['name'] or 'Unnamed'}{'*' if ch.get('creation_mode') == 'advanced' else ''}"
        with st.popover(label, use_container_width=True):
            st.markdown(f"**{species_label(ch.get('species',''))}** · T{ch.get('tier',1)} · {rank_label(rank)}")
            if ch.get("archetype"): st.caption(str(ch.get("archetype")))
            attrs = effective_attributes(ch, gear); skills = effective_skills(ch, gear)
            st.markdown("**Attributes**  " + " · ".join(f"{a[:3].upper()} {attrs.get(a,1)}" for a in ATTRS))
            st.markdown("**Skills**  " + " · ".join(f"{sk[:4]} {skills.get(sk,0)+attrs.get(at,1)}" for sk, at in SKILLS.items()))
            corr = corruption_level_info(ch.get("cur_corruption", 0))
            st.caption(f"Wounds {int(ch.get('cur_wounds',0))}/{d['Max Wounds']} · Shock {int(ch.get('cur_shock',0))}/{d['Max Shock']} · Wrath {int(ch.get('cur_wrath',0))}/{d['Max Wrath']} · Corruption {corr['points']} ({corr['name']})")
        c[0].caption(f"{ch['species']} · T{ch['tier']} · Rank {rank} {vs}", unsafe_allow_html=True)
    _ammo_total = current_ammo(ch, gear)
    ammo_text = f"{_ammo_total}/{ammo_capacity(ch, gear)}"
    corr = corruption_level_info(ch.get("cur_corruption", 0))
    c[1].markdown(f"<small>Wounds {ch['cur_wounds']}/{d['Max Wounds']}<br>Shock {ch['cur_shock']}/{d['Max Shock']}<br>Wrath {ch['cur_wrath']}/{d['Max Wrath']}<br>Ammo {ammo_text}<br>Corruption {corr['points']} ({corr['name']})</small>", unsafe_allow_html=True)
    c[2].button("Open", key=f"op_{ch['id']}", on_click=cb_open, args=(ch["id"],))
    if ch["comms_on"]:
        c[3].button("Cut Vox", key=f"vr_{ch['id']}", on_click=set_comms, args=(ch["id"], 0))
    else:
        c[3].button("Activate Vox", key=f"vr_{ch['id']}", on_click=set_comms, args=(ch["id"], 1))
    c[4].button("X", key=f"dl_{ch['id']}", on_click=cb_delete_character, args=(ch["id"],))


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


# Player Audit tab temporarily disabled at the user's request. The whole
# function below is disabled with real '#' comments (a bare triple-quoted
# string here would be auto-displayed by Streamlit's "magic" top-level
# expression output, which is exactly what happened the first time this was
# tried). Uncomment every line below, and its tab wiring in gm_view(), to restore.
# @st.fragment(run_every=REFRESH_S)
# def players_audit_view():
#     players = get_player_registry()
#     with _section("Player Registry & Audit", "Every Player's Tier/Rank at a glance, and a full change-log per "
#                   "Player (who changed what, when, and the before/after value). Updates automatically."):
#         st.caption("Live audit of changes made by Players. This panel synchronizes automatically.")
#         if not players:
#             st.info("No Players are registered."); return
#         for c in players:
#             count = count_player_audit(c["id"])
#             cols = st.columns([3.5, 1, 1.5, 1.2])
#             cols[0].markdown(f"**{c['name'] or 'Unnamed'}** · `{c.get('username') or 'unlinked'}`")
#             cols[1].caption(f"T{c['tier']} · {rank_label(c['rank'])}")
#             cols[2].metric("Changes", count)
#             if cols[3].button("Audit", key=f"audit_open_{c['id']}", use_container_width=True):
#                 st.session_state["audit_player_id"] = int(c["id"]); st.rerun()
#         ids = [int(c["id"]) for c in players]
#         selected = st.session_state.get("audit_player_id")
#         if selected not in ids: selected = ids[0]; st.session_state["audit_player_id"] = selected
#         labels = {int(c["id"]): f"{c['name'] or 'Unnamed'} · {c.get('username') or 'unlinked'}" for c in players}
#         selected = st.selectbox("Player", ids, index=ids.index(selected), format_func=lambda x: labels[x], key="audit_player_select")
#         st.session_state["audit_player_id"] = selected
#         rows = get_player_audit(selected, 500)
#         st.divider(); st.markdown(f"### Audit: {labels[selected]}")
#         if not rows: st.info("No Player changes have been recorded yet."); return
#         for r in rows:
#             stamp = str(r["changed_at"]).replace("T", " ")[:19]
#             st.markdown(f"**{stamp}** · {r['actor']} · `{r['source']}` · **{r['field']}**")
#             left, right = st.columns(2)
#             with left: st.caption("Before"); st.code(str(r.get("old_value", "")), language="text")
#             with right: st.caption("After"); st.code(str(r.get("new_value", "")), language="text")
#             st.divider()


def _req_list(value):
    return [x.strip() for x in re.split(r",|;", str(value or "")) if x.strip()]


CRAFT_TRAITS = [
    "Assault", "Blast", "Brutal", "Combi", "Dakka", "Felling", "Force", "Force Shield",
    "Flame", "Heavy", "Melta", "Parry", "Penetrating", "Pistol", "Powered", "Rapid Fire",
    "Reliable", "Rending", "Shield", "Sniper", "Steadfast", "Toxic", "Unwieldy", "Warp Weapon",
    "Waaagh!", "’Ere We Go", "2-Handed", "Bulk"
]
CRAFT_TRAIT_PARAMETER = {
    "Blast": "Blast size", "Dakka": "Dakka rating", "Felling": "Felling rating", "Penetrating": "Penetrating rating",
    "Rapid Fire": "Rapid Fire rating", "Rending": "Rending rating", "Sniper": "Sniper rating", "Bulk": "Bulk rating", "Powered": "Powered rating"
}


def _render_craft_requirements(prefix, details=None, kind="talent"):
    details = dict(details or {})
    req = _requirement_data({"details": details})
    st.markdown("**Prerequisites**")
    c1, c2 = st.columns(2)
    rank_min = c1.number_input("Minimum Rank", 0, 3, int(req.get("rank_min", 0) or 0), key=f"{prefix}_rank")
    tier_min = c2.number_input("Minimum Tier", 0, MAX_TIER, int(req.get("tier_min", 0) or 0), key=f"{prefix}_tier")
    kw_options = _craft_keyword_options()
    old_kw = _req_list(req.get("keywords_all", []))
    kw_default = [x for x in kw_options if x.lower() in {str(v).lower() for v in old_kw}]
    keywords = st.multiselect("Required Keywords", kw_options, default=kw_default, key=f"{prefix}_keywords")
    custom_kw = st.text_input("Other Required Keywords", ", ".join(x for x in old_kw if x.lower() not in {v.lower() for v in kw_options}), key=f"{prefix}_custom_keywords")
    species_options = list(dict.fromkeys(PLAYER_SPECIES + [x for x in NPC_SPECIES if x not in PLAYER_SPECIES]))
    old_species = _req_list(req.get("species", []))
    species = st.multiselect("Required Species", species_options, default=[x for x in old_species if x in species_options], key=f"{prefix}_species")
    arch_options = list(ARCHETYPES.keys())
    old_arch = _req_list(req.get("archetypes", []))
    archetypes = st.multiselect("Required Archetype", arch_options, default=[x for x in old_arch if x in arch_options], key=f"{prefix}_archetypes")
    talent_names = [r["name"] for r in list_craft_items("talent")]
    old_talents = _req_list(req.get("talents", []))
    required_talents = st.multiselect("Required Talents", talent_names, default=[x for x in old_talents if x in talent_names], key=f"{prefix}_talents")
    extra_required = st.text_input("Other Required Talents", ", ".join(x for x in old_talents if x not in talent_names), key=f"{prefix}_other_talents")
    with st.expander("Attribute and Skill Requirements", expanded=False):
        attrs = {}; ac = st.columns(4); old_attrs = req.get("attributes", {}) or {}
        for i, attr in enumerate(ATTRS):
            n = ac[i % 4].number_input(f"{attr} minimum", 0, 12, int(old_attrs.get(attr, 0) or 0), key=f"{prefix}_attr_{i}")
            if n: attrs[attr] = int(n)
        skills = {}; sc = st.columns(3); old_skills = req.get("skills", {}) or {}
        for i, skill in enumerate(SKILLS):
            n = sc[i % 3].number_input(f"{skill} minimum", 0, 8, int(old_skills.get(skill, 0) or 0), key=f"{prefix}_skill_{i}")
            if n: skills[skill] = int(n)
    return {"keywords_all": _req_list(keywords) + _req_list(custom_kw), "keywords_any": [], "rank_min": int(rank_min), "tier_min": int(tier_min),
            "species": species, "archetypes": archetypes, "talents": required_talents + _req_list(extra_required), "attributes": attrs, "skills": skills}


def _render_craft_modifiers(prefix, details=None, kind="wargear"):
    """Manual 'Automatic Sheet Modifiers' editor, shared by Wargear, Talent
    and Power. `kind` controls the caption (each has different rules
    implications) and whether the Wargear-only Armour Rating group appears.
    """
    details = dict(details or {}); old = details.get("modifiers", {}) or {}; mods = {}
    st.markdown("**Automatic Sheet Modifiers**")
    if kind == "wargear":
        st.caption("These are only direct numeric changes to the character sheet, on top of whatever "
                   "the Traits above already grant automatically (see 'Automatic from Traits'). Use "
                   "Traits/this section only for effects with no rule text to resolve, like Pistol or Blast.")
    elif kind == "talent":
        st.caption("Permanent the moment this Talent is purchased, Talents have no 'equipped' state. "
                   "Use this only for a Talent whose bonus is always on, not one that requires spending "
                   "a resource or taking an Action to trigger.")
    else:  # power
        st.caption("⚠️ Most Psychic Powers are activated abilities lasting a scene/Round, not a "
                   "permanent bonus, a modifier here applies forever, just from knowing the Power. "
                   "Only use this for a Power that is genuinely passive/innate.")
    # Initiative is not repeated here: it is already one of the seven
    # Attributes above, and both fields would silently collide on the same
    # underlying "initiative" modifier key.
    groups = [("Attributes", list(ATTRS)), ("Skills", list(SKILLS.keys())), ("Derived Traits", ["defence", "resilience", "speed"]), ("Vitals / Capacity", ["wounds", "shock", "wrath", "ammo"])]
    if kind == "wargear":
        groups.append(("Armour Rating", ["armour"]))
    for title, keys in groups:
        with st.expander(title, expanded=False):
            cols = st.columns(4)
            for i, key in enumerate(keys):
                n = cols[i % 4].number_input(key.replace("_", " ").title(), -20, 20, int(old.get(key, 0) or 0), key=f"{prefix}_mod_{key}")
                if n: mods[key] = int(n)
    return mods


def _wargear_trait_bonus_preview(details):
    """Read-only preview of the bonus already auto-derived from this
    Wargear's Traits/Armour Rating (Powered, Bulk, Shield), kept visually
    separate from the manual Automatic Sheet Modifiers below so a GM never
    double-enters the same bonus in both places."""
    preview = craft_modifiers({"details": {**details, "modifiers": {}}})
    st.markdown("**Automatic from Traits**")
    if preview:
        st.success(", ".join(f"{k.title()} {v:+d}" for k, v in preview.items())
                   + ", already applied while equipped. Do not repeat this below.")
    else:
        st.caption("No automatic bonus detected. Powered (X), Bulk (X), Shield and Armour Rating "
                   "are recognized automatically from the Traits and Armour Rating fields above.")


def _render_wargear_data(prefix, details=None):
    details = dict(details or {}); a = st.columns(4)
    rarity_options = ["Common", "Uncommon", "Rare", "Very Rare", "Unique"]; old_rarity = str(details.get("rarity", "Common"))
    rarity = a[0].selectbox("Rarity", rarity_options, index=rarity_options.index(old_rarity) if old_rarity in rarity_options else 0, key=f"{prefix}_rarity")
    value = a[1].number_input("Value", 0, 1000000, int(details.get("value", 0) or 0), key=f"{prefix}_value")
    wtype = a[2].text_input("Type", str(details.get("type", "")), key=f"{prefix}_type")
    category_options = ["", "weapon", "armour", "gear", "ammo", "grenade", "missile", "reload", "upgrade"]; old_category = str(details.get("category", "")).lower()
    category = a[3].selectbox("Category", category_options, index=category_options.index(old_category) if old_category in category_options else 0, key=f"{prefix}_category")
    old_traits = details.get("traits", []) or []; old_traits = _req_list(old_traits) if isinstance(old_traits, str) else [str(x) for x in old_traits]
    selected_base = [t for t in CRAFT_TRAITS if any(x.lower().startswith(t.lower()) for x in old_traits)]
    with st.expander("Traits", expanded=bool(selected_base)):
        selected = st.multiselect("Wargear Traits", CRAFT_TRAITS, default=selected_base, key=f"{prefix}_trait_select")
        trait_values = {}
        for trait in selected:
            if trait in CRAFT_TRAIT_PARAMETER:
                old_value = ""
                for x in old_traits:
                    m = re.match(rf"{re.escape(trait)}\s*\(([^)]*)\)", x, re.I)
                    if m: old_value = m.group(1)
                trait_values[trait] = st.text_input(CRAFT_TRAIT_PARAMETER[trait], old_value, key=f"{prefix}_trait_value_{re.sub(r'[^a-z0-9]+','_',trait.lower())}")
    traits = [f"{t} ({str(trait_values.get(t, '')).strip()})" if t in CRAFT_TRAIT_PARAMETER and str(trait_values.get(t, '')).strip() else t for t in selected]
    b = st.columns(5)
    damage = b[0].text_input("Damage", str(details.get("damage", "")), key=f"{prefix}_damage")
    ed = b[1].number_input("ED", 0, 20, int(details.get("ed", 0) or 0), key=f"{prefix}_ed")
    ap = b[2].number_input("AP", -20, 20, int(details.get("ap", 0) or 0), key=f"{prefix}_ap")
    rng = b[3].text_input("Range", str(details.get("range", "")), key=f"{prefix}_range")
    salvo = b[4].number_input("Salvo", 0, 20, int(details.get("salvo", 0) or 0), key=f"{prefix}_salvo")
    kw_options = sorted(set(_craft_keyword_options() + ["Explosive", "Bolt", "Las", "Flame", "Plasma", "Melta", "Shuriken", "Projectile", "Fire"]))
    old_kw = [str(x) for x in (details.get("keywords", []) or [])]; old_lower = {x.lower() for x in old_kw}
    keywords = st.multiselect("Wargear Keywords", kw_options, default=[x for x in kw_options if x.lower() in old_lower], key=f"{prefix}_gear_keywords")
    custom_kw = st.text_input("Other Wargear Keywords", ", ".join(x for x in old_kw if x.lower() not in {v.lower() for v in kw_options}), key=f"{prefix}_custom_keywords")
    stackable = st.checkbox("Stackable", value=bool(details.get("stackable", False)), key=f"{prefix}_stackable")
    stack_group = st.text_input("Stack Group", str(details.get("stack_group", "")), key=f"{prefix}_stack_group")
    return {"rarity": rarity, "value": int(value), "type": wtype, "category": category, "stackable": bool(stackable), "stack_group": stack_group.strip(), "keywords": _req_list(keywords) + _req_list(custom_kw), "traits": traits, "damage": damage, "ed": int(ed), "ap": int(ap), "range": rng, "salvo": int(salvo)}


def _render_power_data(prefix, details=None):
    details = dict(details or {}); a = st.columns(4)
    dn = a[0].number_input("DN", 0, 20, int(details.get("dn", 0) or 0), key=f"{prefix}_dn")
    activation = a[1].text_input("Activation", str(details.get("activation", "")), key=f"{prefix}_activation")
    potency = a[2].number_input("Potency", 0, 20, int(details.get("potency", 0) or 0), key=f"{prefix}_potency")
    discipline = a[3].text_input("Discipline", str(details.get("discipline", "")), key=f"{prefix}_discipline")
    return {"dn": int(dn), "activation": activation, "potency": int(potency), "discipline": discipline}


def _craft_kind_label(kind):
    return {"talent": "Talent", "wargear": "Wargear", "power": "Psychic Power"}.get(kind, kind.title())


@st.fragment
def craft_view():
    st.markdown("#### Craft")
    st.caption("Talents and Psychic Powers are purchased with XP. Wargear is equipment and never has an XP purchase cost.")
    all_items = list_craft_items(active_only=False)
    sets = {k: [r for r in all_items if r["kind"] == k] for k in ("talent", "power", "wargear")}
    tabs = st.tabs([f"Talents ({len(sets['talent'])})", f"Psychic Powers ({len(sets['power'])})", f"Wargear ({len(sets['wargear'])})"])

    def render_catalog(kind, rows, title):
        search = st.text_input("Search", key=f"craft_search_{kind}", placeholder=f"Search {title.lower()}...")
        show_disabled = st.checkbox("Show disabled entries", value=False, key=f"craft_disabled_{kind}")
        visible = rows if show_disabled else [r for r in rows if int(r.get("active", 1))]
        if search.strip():
            q = search.lower(); visible = [r for r in visible if q in str(r.get("name", "")).lower() or q in str(r.get("effect", "")).lower()]
        with _section(f"Catalog · {len(visible)} entries",
                      "Every registered entry of this kind. Click one to see its full rules text, "
                      "requirements, and sheet modifiers, or to Disable/Edit/Delete it.",
                      key=f"craft_catalog_section_{kind}"):
            for r in visible:
                details = craft_details(r); req = _requirement_data(r)
                label = f"{r['name']} · {int(r.get('cost',0) or 0)} XP · #{r['id']}" if kind in ("talent", "power") else f"{r['name']} · #{r['id']}"
                with st.expander(label, expanded=False):
                    if r.get("effect"): st.write(r["effect"])
                    if req.get("keywords_all"): st.caption("Required Keywords: " + ", ".join(req["keywords_all"]))
                    # Full effective total (Traits like Powered/Bulk/Shield + any manual entry),
                    # not just the manually-entered part, so the catalog view matches what
                    # actually applies to a character sheet.
                    effective_mods = craft_modifiers(r)
                    if effective_mods: st.caption("Sheet modifiers: " + ", ".join(f"{k.title()} {int(v):+d}" for k,v in effective_mods.items() if v))
                    if kind == "talent" and details.get("faith_talent"): st.caption("Faith Talent · grants +1 maximum Faith (p.142)")
                    if kind == "wargear":
                        extra = [f"{lab}: {details.get(key)}" for key,lab in (("category","Category"),("damage","Damage"),("ed","ED"),("ap","AP"),("range","Range"),("salvo","Salvo"),("traits","Traits"),("keywords","Keywords")) if details.get(key) not in (None,"",[])]
                        if extra: st.caption(" · ".join(extra))
                    if kind == "power":
                        extra = [f"{lab}: {details.get(key)}" for key,lab in (("dn","DN"),("activation","Activation"),("potency","Potency"),("discipline","Discipline")) if details.get(key) not in (None,"",0)]
                        if extra: st.caption(" · ".join(extra))
                    b = st.columns(3)
                    if b[0].button("Disable" if int(r.get("active",1)) else "Enable", key=f"ct_{kind}_{r['id']}"):
                        conn=get_conn(); conn.execute("UPDATE craft_items SET active=?,updated_at=? WHERE id=?", (0 if int(r.get("active",1)) else 1, now_iso(), int(r["id"]))); conn.commit(); conn.close()
                        invalidate_craft_cache(); st.rerun()
                    if b[1].button("Edit", key=f"ce_{kind}_{r['id']}"): st.session_state["craft_edit_id"] = int(r["id"]); st.rerun()
                    if b[2].button("Delete", key=f"cd_{kind}_{r['id']}"):
                        conn=get_conn(); conn.execute("DELETE FROM craft_items WHERE id=?", (int(r["id"]),)); conn.commit(); conn.close()
                        invalidate_craft_cache(); st.rerun()

    def register_form(kind, title):
        with _section(f"Register {title}",
                      "Adds a brand-new catalog entry: name, effect text, XP cost (Talents/Powers "
                      "only), purchase requirements, and any automatic sheet modifiers it grants."):
            cname = st.text_input("Name", key=f"craft_new_name_{kind}")
            cdesc = st.text_area("Description / Effect", key=f"craft_new_effect_{kind}", height=100)
            if kind in ("talent", "power"):
                cost = st.number_input("XP Cost", 0, 10000, 0, key=f"craft_new_cost_{kind}")
            else:
                cost = 0; st.caption("Wargear has no XP cost. Value is recorded separately.")
            req = _render_craft_requirements(f"craft_new_{kind}_req", {}, kind); details = {"requirements": req}
            if kind == "wargear":
                # Traits/Armour Rating first, so the auto-bonus preview below
                # reflects what was just typed, and the manual modifiers
                # section comes last so it's visually the "extra" one.
                details.update(_render_wargear_data(f"craft_new_{kind}_gear", details))
                _wargear_trait_bonus_preview(details)
                details["modifiers"] = _render_craft_modifiers(f"craft_new_{kind}_mods", details, "wargear")
            elif kind == "power":
                details.update(_render_power_data(f"craft_new_{kind}_power", details))
                details["modifiers"] = _render_craft_modifiers(f"craft_new_{kind}_mods", details, "power")
            elif kind == "talent":
                details["faith_talent"] = st.checkbox(
                    "Faith Talent (Adeptus Ministorum / Adepta Sororitas)", value=False, key=f"craft_new_{kind}_faith",
                    help="Core Rulebook p.142: purchasing a Faith Talent grants +1 maximum Faith.")
                details["modifiers"] = _render_craft_modifiers(f"craft_new_{kind}_mods", details, "talent")
            source = st.text_input("Source / Book", key=f"craft_new_source_{kind}")
            if st.button(f"Register {title}", type="primary", use_container_width=True, key=f"craft_register_{kind}"):
                if not cname.strip() or not cdesc.strip(): st.error("Name and Description / Effect are required.")
                else:
                    save_craft_item({"kind":kind,"name":cname.strip(),"effect":cdesc.strip(),"cost":int(cost),"source":source.strip(),"details":{**details,"structured_rules":True,"custom":True,"official":False}}); st.rerun()

    for i, (kind, title) in enumerate((("talent","Talent"),("power","Psychic Power"),("wargear","Wargear"))):
        with tabs[i]: render_catalog(kind, sets[kind], title); register_form(kind, title)

    edit_id = st.session_state.get("craft_edit_id")
    if edit_id:
        row = next((r for r in all_items if int(r["id"]) == int(edit_id)), None)
        if row:
            with _section(f"Edit: {row['name']}",
                          "Edit this entry's fields directly. Save Changes overwrites it in place; Cancel discards edits.",
                          expanded=True, key=f"craft_edit_section_{edit_id}"):
                details = craft_details(row)
                ename = st.text_input("Name", row["name"], key=f"edit_name_{edit_id}")
                eeffect = st.text_area("Description / Effect", row.get("effect", ""), height=100, key=f"edit_effect_{edit_id}")
                ecost = st.number_input("XP Cost", 0, 10000, int(row.get("cost",0) or 0), key=f"edit_cost_{edit_id}") if row["kind"] in ("talent","power") else 0
                if row["kind"] == "wargear": st.caption("Wargear has no XP cost.")
                ereq = _render_craft_requirements(f"edit_req_{edit_id}", details, row["kind"]); newdetails = {"requirements": ereq}
                if row["kind"] == "wargear":
                    newdetails.update(_render_wargear_data(f"edit_wargear_{edit_id}", details))
                    _wargear_trait_bonus_preview(newdetails)
                    newdetails["modifiers"] = _render_craft_modifiers(f"edit_wargear_mod_{edit_id}", details, "wargear")
                elif row["kind"] == "power":
                    newdetails.update(_render_power_data(f"edit_power_{edit_id}", details))
                    newdetails["modifiers"] = _render_craft_modifiers(f"edit_power_mod_{edit_id}", details, "power")
                elif row["kind"] == "talent":
                    newdetails["faith_talent"] = st.checkbox(
                        "Faith Talent (Adeptus Ministorum / Adepta Sororitas)", value=bool(details.get("faith_talent")), key=f"edit_{edit_id}_faith",
                        help="Core Rulebook p.142: purchasing a Faith Talent grants +1 maximum Faith.")
                    newdetails["modifiers"] = _render_craft_modifiers(f"edit_talent_mod_{edit_id}", details, "talent")
                esource = st.text_input("Source / Book", row.get("source", ""), key=f"edit_source_{edit_id}")
                b1,b2=st.columns(2)
                if b1.button("Save Changes", type="primary", use_container_width=True, key=f"edit_save_{edit_id}"):
                    save_craft_item({**row,"name":ename.strip(),"effect":eeffect.strip(),"cost":int(ecost),"source":esource.strip(),"details":{**newdetails,"structured_rules":True,"custom":True,"official":False}}, int(edit_id)); st.session_state.pop("craft_edit_id",None); st.rerun()
                if b2.button("Cancel", use_container_width=True, key=f"edit_cancel_{edit_id}"): st.session_state.pop("craft_edit_id",None); st.rerun()

@st.fragment
def archetypes_view():
    st.markdown("#### Archetypes")
    st.caption("Create campaign-specific Archetypes. Custom Archetypes use the same creation, progression and starting-equipment systems as Core Archetypes.")

    custom_rows = _custom_archetype_rows()
    custom_by_id = {int(r["id"]): r for r in custom_rows}
    edit_id = st.session_state.get("archetype_edit_id")
    edit_row = custom_by_id.get(int(edit_id)) if edit_id else None

    with _section("Edit Custom Archetype" if edit_row else "Create Custom Archetype",
                  "Defines a homebrew Archetype: Tier, Species, Faction, XP cost, an Ability, its starting "
                  "Attribute/Skill package, and starting Wargear, usable everywhere Core Archetypes are.",
                  expanded=bool(edit_row), key="archetype_editor_section"):
        name = st.text_input("Name", value=str(edit_row["name"]) if edit_row else "", key="arch_editor_name")
        c = st.columns(4)
        tier = c[0].number_input("Tier", 1, MAX_TIER, int(edit_row["tier"]) if edit_row else 1, key="arch_editor_tier")
        species_options = list(dict.fromkeys(PLAYER_SPECIES + NPC_SPECIES))
        old_species = str(edit_row["species"]) if edit_row else "Human"
        species = c[1].selectbox("Species", species_options, index=species_options.index(old_species) if old_species in species_options else 0, format_func=species_label, key="arch_editor_species")
        faction_options = list(dict.fromkeys(FACTION_OPTIONS + ["", "Custom"]))
        old_faction = str(edit_row["faction"]) if edit_row else ""
        faction = c[2].selectbox("Faction", faction_options, index=faction_options.index(old_faction) if old_faction in faction_options else 0, key="arch_editor_faction")
        xp = c[3].number_input("XP Cost", 0, 10000, int(edit_row["xp"]) if edit_row else 0, key="arch_editor_xp")
        ability = st.text_input("Archetype Ability", value=str(edit_row["ability"]) if edit_row else "", key="arch_editor_ability")
        old_kw = []
        if edit_row:
            try: old_kw = json.loads(edit_row["keywords"] or "[]")
            except Exception: old_kw = []
        keywords = st.text_input("Archetype Keywords", value=", ".join(old_kw), key="arch_editor_keywords", placeholder="Example: Astartes, Psyker, Rogue Trader")

        st.markdown("**Attribute Package**")
        old_attrs = {}
        old_skills = {}
        if edit_row:
            try: old_attrs = json.loads(edit_row["attributes"] or "{}")
            except Exception: old_attrs = {}
            try: old_skills = json.loads(edit_row["skills"] or "{}")
            except Exception: old_skills = {}
        attrs = {}
        ac = st.columns(4)
        for i, attr in enumerate(ATTRS):
            value = ac[i % 4].number_input(attr, 1, 12, int(old_attrs.get(attr, 1)), key=f"arch_editor_attr_{i}")
            if value > 1: attrs[attr] = int(value)

        st.markdown("**Skill Package**")
        skills = {}
        sc = st.columns(4)
        for i, skill in enumerate(SKILLS):
            value = sc[i % 4].number_input(skill, 0, 8, int(old_skills.get(skill, 0)), key=f"arch_editor_skill_{i}")
            if value > 0: skills[skill] = int(value)

        old_gear = []
        if edit_row:
            try: old_gear = json.loads(edit_row["starting_wargear"] or "[]")
            except Exception: old_gear = []
        gear_rows = list_craft_items("wargear")
        gear_names = [str(r["name"]) for r in gear_rows]
        gear_default = [x for x in old_gear if x in gear_names]
        starting_gear_selected = st.multiselect("Starting Wargear", gear_names, default=gear_default, key="arch_editor_gear")
        qty_lines = st.text_area("Starting Wargear Quantities", value="\n".join(
            str(x) for x in old_gear if x not in gear_default
        ), key="arch_editor_gear_qty", placeholder="Optional extra entries, one per line. Example: Frag Grenade x3")
        starting_gear = list(starting_gear_selected)
        for line in _split_requirement_tokens(qty_lines.replace("\n", ",")):
            base = _gear_quantity_name(line)[1]
            if _catalog_gear_row(gear_rows, base) is not None:
                starting_gear.append(line.strip())
            elif line.strip():
                st.warning(f"Starting Wargear not found in catalog: {base}")
        st.caption("Starting equipment is resolved against the Wargear catalog. Quantities can be written as 'Frag Grenade x3'.")

        buttons = st.columns(2)
        if buttons[0].button("Save Archetype", type="primary", use_container_width=True, key="arch_editor_save"):
            data = {
                "name": name, "tier": tier, "species": species, "faction": faction, "xp": xp, "ability": ability,
                "keywords": _req_list(keywords), "attributes": attrs, "skills": skills, "starting_wargear": starting_gear
            }
            ok, msg = save_custom_archetype(data, int(edit_id) if edit_id else None)
            (st.success if ok else st.error)(msg)
            if ok:
                st.session_state.pop("archetype_edit_id", None)
                st.rerun()
        if buttons[1].button("Cancel", use_container_width=True, key="arch_editor_cancel"):
            st.session_state.pop("archetype_edit_id", None); st.rerun()

    with _section(f"Custom Archetypes · {len(custom_rows)}", "Every homebrew Archetype created for this "
                  "campaign, with quick Edit/Delete actions.", key="archetype_list_section"):
        if not custom_rows:
            st.info("No custom Archetypes have been created yet.")
            return
        for row in custom_rows:
            with st.container(border=True):
                h = st.columns([4, 1, 1, 1])
                h[0].markdown(f"**{html.escape(str(row['name']))}** · T{int(row['tier'])} · {species_label(row['species'])}")
                h[1].caption(f"{int(row['xp'])} XP")
                h[2].caption(str(row['faction'] or "No Faction"))
                if h[3].button("Edit", key=f"arch_edit_{row['id']}"):
                    st.session_state["archetype_edit_id"] = int(row["id"]); st.rerun()
                details = []
                if row["ability"]: details.append("Ability: " + str(row["ability"]))
                try:
                    kw = json.loads(row["keywords"] or "[]")
                    if kw: details.append("Keywords: " + ", ".join(kw))
                except Exception: pass
                try:
                    gear = json.loads(row["starting_wargear"] or "[]")
                    if gear: details.append("Wargear: " + ", ".join(gear))
                except Exception: pass
                if details: st.caption(" · ".join(details))
                dc = st.columns([1, 5])
                if dc[0].button("Delete", key=f"arch_del_{row['id']}"):
                    ok, msg = delete_custom_archetype(int(row["id"]))
                    (st.success if ok else st.error)(msg)
                    if ok: st.rerun()


def render_combat_log_entry(log):
    """One Combat Log entry as a single compact line, click to see each
    participant's final Wounds/Shock/Wrath, a popover nests safely inside
    an expander, unlike another expander."""
    participants = log.get("participants", []) or []
    ended = str(log.get("ended_at") or "").replace("T", " ")[:16]
    summary = f"{ended} · {int(log.get('rounds', 1) or 1)} round(s) · {len(participants)} participant(s)"
    with st.popover(summary, use_container_width=True):
        for p in participants:
            ncls = "npc" if p.get("kind") == "npc" else ""
            st.markdown(
                f"<div class='wg'><span class='{ncls}'><b>{html.escape(str(p.get('name', '')))}</b></span>"
                f" · {species_label(p.get('species', ''))} · T{int(p.get('tier', 1) or 1)}"
                f"<div style='opacity:.75;font-size:.82rem;margin-top:2px'>"
                f"Wounds {p.get('cur_wounds', 0)}/{p.get('max_wounds', 0)}"
                f" · Shock {p.get('cur_shock', 0)}/{p.get('max_shock', 0)}"
                f" · Wrath {p.get('cur_wrath', 0)}/{p.get('max_wrath', 0)}</div></div>",
                unsafe_allow_html=True,
            )


def render_session_combat_logs(session_no):
    logs = get_combat_logs(session_no=session_no)
    if not logs:
        st.caption("No combats logged this session.")
        return
    for log in logs:
        render_combat_log_entry(log)


# Each of the Magister tabs below is its own @st.fragment. Streamlit's
# st.tabs() computes every tab's body on every rerun regardless of which one
# is visible, it only hides the others with CSS, so without this,
# clicking anything in one tab (e.g. Combat) silently recomputed all nine
# other tabs (Characters, Craft, Progression, Session, ...) on every single
# interaction. Wrapping each tab's body in a fragment scopes a rerun
# triggered inside it to just that tab. Nested fragments (e.g. char_row()
# inside _gm_tab_characters, or players_audit_view()/craft_view() which are
# fragments themselves) are supported by this Streamlit version. Any action
# whose effect must be visible outside its own tab already calls st.rerun()
# explicitly, which always triggers a full-app rerun even from inside a
# fragment, so those keep working exactly as before.
@st.fragment
def _gm_tab_characters():
    folders = list_folders()
    # Disposable Generic NPC mobs (Combat tab) stay off the main roster unless saved.
    all_chars = [c for c in list_characters() if not c.get("temp_instance")]
    folder_map = {f["id"]: f["name"] for f in folders}
    folder_options = [None] + [f["id"] for f in folders]

    with _section("Table Organization", "Folders group characters into campaign teams, they also define who "
                  "shares a Vox network. Create, rename, or delete folders here."):
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

    cre = st.columns(2)
    with cre[0]:
        with _section("Recruit Player", "Creates a new Player account/character. The Magister sets Species, "
                      "Archetype, Tier and Rank; the Player logs in separately to fill out the rest of the sheet."):
            # This control is intentionally outside the form so changing it
            # immediately shows/hides the Species and Archetype fields.
            padvanced = st.checkbox("Advanced Character Creation", value=False, key="recruit_player_advanced")
            with st.form("newp"):
                nu = st.text_input("Username")
                npw = st.text_input("Password", type="password")
                st.markdown("**Character Definition**")
                pc2 = st.columns(2)
                ptier = pc2[0].number_input("Tier", 1, MAX_TIER, int(get_campaign()["tier"]))
                prank = pc2[1].selectbox("Rank", [1, 2, 3], format_func=rank_label)
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
                    st.info("Advanced Character Creation: the Player chooses Species on the character sheet. No Archetype is used.")
                if st.form_submit_button("Recruit"):
                    if nu.strip() and npw:
                        mode = "advanced" if padvanced else "archetype"
                        ok, msg = create_player(nu.strip(), npw, mode, ptier, prank, pspecies, parch)
                        (st.success if ok else st.error)(msg)
                        if ok:
                            st.rerun()
    with cre[1]:
        with _section("Create NPC", "Creates a new NPC character sheet directly (no login). Same Species/"
                      "Archetype/Tier/Rank definition as recruiting a Player, but fully controlled by the Magister."):
            # Keep NPC creation visually aligned with Player recruitment.
            # Advanced NPCs still let the Magister define Species, but have no Archetype.
            nadvanced = st.checkbox("Advanced Character Creation", value=False, key="create_npc_advanced")
            with st.form("newn"):
                nn = st.text_input("Name")
                st.markdown("**Character Definition**")
                nc = st.columns(2)
                nt = nc[0].number_input("Tier", 1, MAX_TIER, int(get_campaign()["tier"]))
                nrank = nc[1].selectbox("Rank", [1, 2, 3], format_func=rank_label)
                nc2 = st.columns(2)
                nsp = nc2[0].selectbox("Species", NPC_SPECIES, format_func=species_label)
                if not nadvanced:
                    narc = nc2[1].selectbox(
                        "Archetype", archetype_options(),
                        format_func=lambda name: f"{name}  ·  T{ARCHETYPES[name]['tier']}  ·  {ARCHETYPES[name]['faction']}"
                    )
                    st.caption("The Magister defines Species, Archetype, Tier and Rank for this NPC.")
                else:
                    narc = ""
                    st.info("Advanced Character Creation: the Magister defines Species. No Archetype is used.")
                if st.form_submit_button("Create NPC"):
                    create_npc(nn.strip(), nsp, nt, "advanced" if nadvanced else "archetype", nrank, narc)
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
            with st.expander(f"{icon} {label}  ·  {len(items)} character(s)", expanded=False):
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
                    a[2].markdown("✠ **Vox**")
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
            a[2].markdown("✠" + (" ON" if ch["comms_on"] else " OFF"))


@st.fragment
def _gm_tab_vox():
    folders = list_folders()
    chars = [c for c in list_characters() if not c.get("temp_instance")]
    folder_map = {f["id"]: f["name"] for f in folders}
    groups = {None: []}
    for f in folders:
        groups[f["id"]] = []
    for ch in chars:
        groups.setdefault(ch.get("folder_id"), []).append(ch)

    with _section("Vox Network by Folder", "Each folder is a closed Vox network, a character only receives "
                  "signals from characters in the same folder. Pick a folder to see and toggle its members' Vox."):
        st.caption("Each folder is a closed network. A character only receives signals from characters in the same folder.")

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

    with _section("All Networks", "A quick overview of every folder's network: how many characters it has "
                  "and how many currently have Vox active."):
        for fid, members in groups.items():
            label = "No folder" if fid is None else folder_map.get(fid, "Folder")
            on_count = sum(1 for ch in members if ch["comms_on"])
            st.markdown(f"**{label}** · {len(members)} member(s) · {on_count} active")

    with _section("Magister Monitor", "A live feed of every Vox signal being sent across all networks, "
                  "visible only to the Magister regardless of folder."):
        vox_live()


@st.fragment
def _gm_tab_progression():
    st.caption("Rank and Tier are controlled by the Magister. XP thresholds unlock normal advancement; the Magister may also approve an early advancement.")

    def progression_section(title, kind):
        with _section(title, f"Shows each {title[:-1] if title.endswith('s') else title}'s Earned XP and how far "
                      "they are from their next Rank/Tier, with buttons to approve advancement (early if needed)."):
            chars = [c for c in list_characters(kind) if not c.get("temp_instance")]
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
                # Core Rulebook 2e p.147: a Tier increase costs 100 XP "in the
                # current Tier", and earned_xp is a lifetime cumulative total
                # that is never reset on Ascension (Rank isn't either). So the
                # real threshold for the next Tier is (next_tier - starting_tier)
                # x 100, matching the formula set_tier() already uses, not a
                # flat 100 XP regardless of how many Tiers were already bought.
                starting_tier = int(c.get("starting_tier", tier) or tier)
                next_tier_threshold = max(0, (next_tier - starting_tier) * 100)
                tier_missing = max(0, next_tier_threshold - earned) if next_tier <= MAX_TIER else 0
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
                        ready = earned >= next_tier_threshold
                        label = f"Approve Tier {next_tier}" if ready else f"Approve Tier {next_tier} Early"
                        if ac[1].button(label, key=f"prog_t_{c['id']}", use_container_width=True):
                            if set_tier(c["id"], next_tier, force=not ready):
                                add_log("Magister", f"{c['name']} advanced to Tier {next_tier}{' early' if not ready else ''}.")
                                st.rerun()
                    else:
                        ac[1].button("Maximum Tier", disabled=True, use_container_width=True, key=f"prog_t_max_{kind}_{c['id']}")

    progression_section("Players", "player")
    progression_section("NPCs", "npc")

    with _section("Archetype Ascension", "Requires Rank 3 and moves a character to the next Tier's Archetype "
                  "within the same Faction. The new Archetype does not grant new Attribute or Skill bonuses."):
        eligible_arch = [c for c in list_characters() if not c.get("temp_instance") and c.get("creation_mode") == "archetype" and int(c.get("rank", 1)) >= 3 and int(c.get("tier", 1)) < MAX_TIER]
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

    with _section("Corrections & Undo", "GM-only recovery tools for mistakes: remove XP, restore Rank/Tier, or "
                  "undo an Ascension/other progression change. Normal advancement rules are not enforced here."):
        correction_chars = [c for c in list_characters() if not c.get("temp_instance")]
        if correction_chars:
            correction_labels = {int(c["id"]): f"{c['name'] or 'Unnamed'} · {c['kind'].upper()} · Tier {c['tier']} · {rank_label(c['rank'])} · {c['earned_xp']} XP" for c in correction_chars}
            correction_id = st.selectbox("Character", list(correction_labels.keys()), format_func=lambda x: correction_labels[x], key="progression_correction_character")
            cc = load_character(correction_id)
            if cc:
                with st.container(border=True):
                    st.markdown(f"**{cc['name'] or 'Unnamed'}**")
                    cols = st.columns(3)
                    new_xp = cols[0].number_input("Earned XP", min_value=0, max_value=100000, value=int(cc.get("earned_xp", 0)), step=5, key=f"corr_xp_{correction_id}")
                    new_rank = cols[1].selectbox("Rank", [1, 2, 3], index=max(0, min(2, int(cc.get("rank", 1)) - 1)), format_func=rank_label, key=f"corr_rank_{correction_id}")
                    new_tier = cols[2].number_input("Tier", min_value=1, max_value=MAX_TIER, value=int(cc.get("tier", 1)), step=1, key=f"corr_tier_{correction_id}")
                    if st.button("Apply Progression Correction", key=f"corr_apply_{correction_id}", type="primary", use_container_width=True):
                        if correct_progression_state(correction_id, new_xp, new_rank, new_tier):
                            add_log("Magister", f"Corrected progression for {cc['name'] or 'Unnamed'}: Tier {new_tier}, Rank {new_rank}, {new_xp} XP.")
                            st.success("Progression corrected. The previous state was saved for undo.")
                            st.rerun()

                    st.markdown("**Recent progression history**")
                    history_rows = get_progression_undo(correction_id, 10)
                    if history_rows:
                        for h in history_rows:
                            stamp = str(h["created_at"]).replace("T", " ")[:19]
                            hc = st.columns([4, 1.5])
                            hc[0].caption(f"{stamp} · {h['action']}")
                            if hc[1].button("Undo", key=f"undo_prog_{h['id']}", use_container_width=True):
                                ok, msg = restore_progression_undo(h["id"])
                                if ok:
                                    add_log("Magister", f"Undid progression change for {cc['name'] or 'Unnamed'}: {h['action']}")
                                    st.success(msg)
                                    st.rerun()
                                else:
                                    st.error(msg)
                    else:
                        st.caption("No progression corrections or advancement changes have been recorded yet.")


@st.fragment
def _gm_tab_session():
    camp = get_campaign()
    current_session = int(camp.get("session_no", 1))
    players = list_characters("player")
    npcs = [c for c in list_characters("npc") if not c.get("temp_instance")]
    old_records = get_session_records(20)

    with _section("Session", "Close out the current table session in one step: award base + bonus XP per "
                  "Player, record which NPCs were involved, and optionally advance the campaign's Session number."):
        st.caption("Close the session, award table XP and individual bonuses, record notes, and mark the NPCs involved.")
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

    with _section("Session History", "Every past Session record: notes, NPCs involved, XP awarded, and that "
                  "Session's Combat Log. Click a Session to see its details."):
        if not old_records:
            st.caption("No session records yet.")
        for sr in old_records:
            status = "Closed" if sr["closed_at"] else "Draft"
            label = f"Session {sr['session_no']} · {sr['title'] or 'Untitled'} · {status}"
            # A nested st.expander/st.popover isn't allowed inside this section's
            # own expander, and render_session_combat_logs() below already opens
            # a popover per combat, so a plain toggle button substitutes here.
            show_key = f"session_hist_show_{sr['id']}"
            if st.button(label, key=f"session_hist_btn_{sr['id']}", use_container_width=True):
                st.session_state[show_key] = not st.session_state.get(show_key, False)
            if st.session_state.get(show_key, False):
                with st.container(border=True):
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
                    st.markdown("**Combat Log**")
                    render_session_combat_logs(sr["session_no"])


@st.fragment
def _gm_tab_combat():
    camp = get_campaign()
    head_row = st.columns([5, 1.3])
    head_row[0].markdown("#### Combat")
    if head_row[1].button("End Combat", use_container_width=True, key="combat_clear"):
        logged = log_combat_end()
        st.session_state["combat_just_logged"] = bool(logged)
        st.rerun()
    if st.session_state.pop("combat_just_logged", False):
        st.success("Combat logged. See the Combat Log below or in Session history.")

    all_combat_chars = list_characters()
    folders = list_folders()
    folder_map = {f["id"]: f["name"] for f in folders}
    current = get_combatants()
    active = {c["id"] for c in current}

    with _section(f"Active Combat · {len(current)} combatant(s)",
                  "The live attack order for the current encounter: Round/Turn tracking, each combatant's "
                  "quick stats, and Wounds/Shock/Ammo/Wrath trackers. Reorder with ↑/↓, click Open for the full sheet.",
                  expanded=False, key="combat_active_section"):
        current_idx = -1
        if current:
            state = combat_state()
            current_idx = min(state["current"], len(current) - 1)
            turn_cols = st.columns([1.1, 1.3, 1.3, 3], gap="small")
            turn_cols[0].metric("Round", state["round"])
            if turn_cols[1].button("◀ Previous Turn", use_container_width=True, key="combat_turn_prev"):
                advance_combat_turn(-1)
                st.rerun()
            if turn_cols[2].button("Next Turn ▶", use_container_width=True, key="combat_turn_next"):
                advance_combat_turn(+1)
                st.rerun()
            current_name = html.escape(current[current_idx].get("name") or "Unnamed")
            turn_cols[3].markdown(
                f"<div style='padding-top:8px'>Current turn: <b>{current_name}</b> (#{current_idx + 1})</div>",
                unsafe_allow_html=True,
            )

        if not current:
            st.info("No characters are currently in combat. Add Players or NPCs below.")
        else:
            st.caption("↑ / ↓ reorder the attack sequence · click a name for Attributes and Skills.")
            user = st.session_state.user or {}
            for idx, ch in enumerate(current):
                gear = equipped_wargear_modifiers(ch)
                d = derived_traits(ch, gear)
                is_npc = ch.get("kind") == "npc"
                role_label = "NPC" if is_npc else "PLAYER"
                rank = int(ch.get("rank", 1) or 1)
                folder_name = folder_map.get(ch.get("folder_id"), "No folder")

                is_current_turn = (idx == current_idx)
                with st.container(border=True):
                    # Position number + name/details popover + reorder/remove, all in one row.
                    head = st.columns([0.5, 3.2, 0.9, 0.6, 1], gap="small")
                    pos_cls = "combat-pos combat-pos-active" if is_current_turn else "combat-pos"
                    head[0].markdown(f"<div class='{pos_cls}'>{idx + 1}</div>", unsafe_allow_html=True)
                    with head[1]:
                        pop_label = ("▶ " + (ch.get("name") or "Unnamed")) if is_current_turn else (ch.get("name") or "Unnamed")
                        with st.popover(pop_label, use_container_width=True, key=f"combat_pop_{ch['id']}"):
                            st.markdown(f"**{species_label(ch.get('species', ''))}** · T{ch.get('tier', 1)} · {rank_label(rank)}")
                            if ch.get("archetype"):
                                st.caption(str(ch.get("archetype")))
                            attrs = effective_attributes(ch, gear); skills = effective_skills(ch, gear)
                            st.markdown("**Attributes**  " + " · ".join(f"{a[:3].upper()} {attrs.get(a, 1)}" for a in ATTRS))
                            st.markdown("**Skills**  " + " · ".join(f"{sk[:4]} {skills.get(sk, 0) + attrs.get(at, 1)}" for sk, at in SKILLS.items()))
                        temp_tag = " · ⚠ TEMP (unsaved)" if ch.get("temp_instance") else ""
                        st.caption(f"{role_label} · {species_label(ch.get('species'))} · T{ch.get('tier', 1)} · {rank_label(rank)} · {folder_name}{temp_tag}")
                        # Combat-critical Traits stay visible at a glance instead of hiding behind the popover.
                        st.caption(f"Defence {int(d.get('Defence', 0) or 0)} · Resilience {int(d.get('Resilience', 0) or 0)} "
                                   f"· Speed {int(d.get('Speed', 0) or 0)} · Resolve {int(d.get('Resolve', 0) or 0)}")
                    head[2].button("Open", key=f"combat_open_{ch['id']}", use_container_width=True,
                                   on_click=cb_open, args=(ch["id"],))
                    with head[3]:
                        if st.button("↑", key=f"combat_up_{ch['id']}", disabled=(idx == 0), use_container_width=True):
                            move_combatant(ch["id"], -1)
                            st.rerun()
                        if st.button("↓", key=f"combat_down_{ch['id']}", disabled=(idx == len(current) - 1), use_container_width=True):
                            move_combatant(ch["id"], 1)
                            st.rerun()
                    if head[4].button("Remove", key=f"combat_current_remove_{ch['id']}", use_container_width=True):
                        set_combatant(ch["id"], False)
                        st.rerun()

                    # Wounds/Shock/Ammo/Wrath, in the same compact metric + stacked −/+ pattern as the Battle Sheet.
                    vcols = st.columns(4, gap="small")
                    _vital_stat_block(vcols[0], "Wounds", max(0, int(ch.get("cur_wounds", 0) or 0)), int(d.get("Max Wounds", 0) or 0),
                                      cid=ch["id"], field="cur_wounds", editable=is_npc, actor_role="gm",
                                      actor_user_id=user.get("id"), actor_name=user.get("username", "Magister"),
                                      key_prefix=f"combat_w_{ch['id']}", max_mod=int(gear.get("wounds", 0) or 0))
                    _vital_stat_block(vcols[1], "Shock", max(0, int(ch.get("cur_shock", 0) or 0)), int(d.get("Max Shock", 0) or 0),
                                      cid=ch["id"], field="cur_shock", editable=is_npc, actor_role="gm",
                                      actor_user_id=user.get("id"), actor_name=user.get("username", "Magister"),
                                      key_prefix=f"combat_s_{ch['id']}", max_mod=int(gear.get("shock", 0) or 0))
                    _ammo_stat_block(vcols[2], ch["id"], ch, editable=is_npc, actor_role="gm",
                                     actor_user_id=user.get("id"), actor_name=user.get("username", "Magister"),
                                     key_prefix=f"combat_a_{ch['id']}", source_prefix="Combat Quick Panel",
                                     cap_mod=ammo_capacity_bonus(ch, gear), gear_mods=gear)
                    _vital_stat_block(vcols[3], "Wrath", max(0, int(ch.get("cur_wrath", 0) or 0)), int(d.get("Max Wrath", 0) or 0),
                                      max_mod=int(gear.get("wrath", 0) or 0))

                if idx < len(current) - 1:
                    st.markdown("<div class='combat-arrow'>▼</div>", unsafe_allow_html=True)

    with _section(f"Add Combatants · {len(current)} in combat",
                  "Add or remove Players/NPCs from the active combat encounter, filtered by folder or search.",
                  expanded=False, key="combat_add_section"):
        fc = st.columns([1.8, 2.5])
        folder_options = [None] + [f["id"] for f in folders]
        selected_folder = fc[0].selectbox(
            "Filter by Folder",
            folder_options,
            format_func=lambda x: "All Folders" if x is None else folder_map.get(x, "Folder"),
            key="combat_folder",
        )
        search = fc[1].text_input(
            "Search Character",
            placeholder="Search by name, species, archetype, or faction",
            key="combat_search",
        )

        filtered = []
        q = search.strip().lower()
        for ch in all_combat_chars:
            if selected_folder is not None and ch.get("folder_id") != selected_folder:
                continue
            hay = " ".join([
                str(ch.get("name") or ""),
                str(ch.get("species") or ""),
                str(ch.get("archetype") or ""),
                str(ch.get("chapter") or ""),
                str(ch.get("faction") or ""),
            ]).lower()
            if q and q not in hay:
                continue
            filtered.append(ch)

        st.caption("Players and NPCs are read-only here except for the manual attack order and NPC quick vitals.")
        if not filtered:
            st.caption("No characters match the current filter.")
        else:
            for ch in filtered:
                in_combat = ch["id"] in active
                cols = st.columns([5, 1.2, 2])
                kind_label = "NPC" if ch["kind"] == "npc" else "PLAYER"
                ncls = "npc" if ch["kind"] == "npc" else ""
                cols[0].markdown(
                    f"<span class='{ncls}'><b>{html.escape(ch.get('name') or 'Unnamed')}</b></span> · {kind_label} · "
                    f"{species_label(ch.get('species'))} · T{ch.get('tier', 1)} · {rank_label(ch.get('rank', 1))}",
                    unsafe_allow_html=True,
                )
                if cols[1].button("Remove" if in_combat else "Add", key=f"combat_toggle_{ch['id']}", use_container_width=True):
                    set_combatant(ch["id"], not in_combat)
                    st.rerun()
                cols[2].caption("IN COMBAT" if in_combat else "")

    with _section("Generate Generic NPCs · quick mobs for combat",
                  "Builds disposable NPC mobs from an Archetype (or a Bestiary Threat) and drops them "
                  "straight into combat. They vanish when combat ends unless saved from their sheet."):
        st.caption("Instances only, they have no permanent character sheet, all their XP for the Tier is "
                   "auto-spent, and they are deleted automatically when combat ends unless you click "
                   "\"Save Character\" on their sheet first.")
        gc = st.columns([2.2, 1, 1, 1.4])
        mob_arch = gc[0].selectbox(
            "Archetype", generic_npc_options(),
            format_func=lambda name: f"{name}  ·  T{ARCHETYPES[name]['tier']}  ·  {ARCHETYPES[name]['faction']}",
            key="mob_archetype",
        )
        mob_tier = gc[1].number_input("Tier", 1, MAX_TIER, int(ARCHETYPES[mob_arch]["tier"]), key="mob_tier")
        mob_qty = gc[2].number_input("Quantity", 1, 20, 3, key="mob_qty")
        mob_spend = gc[3].checkbox("Spend all XP", value=True, key="mob_spend_xp",
                                    help="Rolls up to 2 random Talents/Powers whose Keyword/Rank/Tier/Attribute requirements the mob already meets, then spends whatever XP is left on Attribute/Skill upgrades, so the mob isn't stuck at bare minimums. Ignored for (Bestiary) entries, their printed stat block is used as-is.",
                                    disabled=(mob_arch in BESTIARY_ARCHETYPE_NAMES))
        if mob_arch in BESTIARY_ARCHETYPE_NAMES:
            st.caption("(Bestiary) entries use the Core Rulebook's printed Attributes/Skills/Wargear directly, "
                       "Defence/Resilience/Wounds/Shock still run through this sheet's normal formula, so expect "
                       "some drift from the exact numbers in the book (the rulebook itself calls this out).")
        if st.button("Create Generic NPCs", key="mob_create", use_container_width=True):
            new_ids = create_generic_npcs(mob_arch, int(mob_tier), int(mob_qty), bool(mob_spend))
            if new_ids:
                st.success(f"{len(new_ids)} {mob_arch} instance(s) added to combat.")
            st.rerun()

    session_no_now = int(camp.get("session_no", 1) or 1)
    session_logs = get_combat_logs(session_no=session_no_now)
    with _section(f"Combat Log · Session {session_no_now} · {len(session_logs)} combat(s)",
                  "A permanent record of every combat ended this Session: participants and their "
                  "final Wounds/Shock/Wrath. Click a combat to see the details.",
                  key="combat_log_section"):
        st.caption("Click a combat to see each participant's final Wounds/Shock/Wrath.")
        if not session_logs:
            st.caption("No combats logged this session yet. Ending a combat above records one here.")
        else:
            for log in session_logs:
                render_combat_log_entry(log)


@st.fragment
def _gm_tab_campaign():
    camp = get_campaign()
    with _section("Campaign Configuration", "Sets the campaign's name, Tier (the starting XP budget for new "
                  "Players/NPCs), and current Session number."):
        with st.form("campf"):
            cc = st.columns([3, 1, 1])
            cname = cc[0].text_input("Campaign Name", camp["name"])
            ctier = cc[1].number_input("Campaign Tier", 1, MAX_TIER, int(camp["tier"]))
            sess = cc[2].number_input("Session", 1, 999, int(camp["session_no"]))
            if st.form_submit_button("Save"):
                save_campaign(cname, ctier, camp["ruin"], sess); st.rerun()
        st.caption(f"Standard character XP: {starting_xp(camp['tier'])} (Tier {camp['tier']} × 100). Advanced Character Creation adds Tier ×10 bonus XP.")
    with _section("Ruin", "Ruin is the Magister's shared resource pool, spent to let Threats roll "
                  "Determination, use Ruin Actions, and trigger other GM-side effects during play."):
        # Same compact metric + stacked −/+ pattern as the Battle Sheet vitals.
        with st.container(key="ruin_campaign_vsb"):
            rc = st.columns([5, 1], gap="small")
            rc[0].metric("Ruin", camp["ruin"])
            with rc[1]:
                st.button("+", key="ruinplus", on_click=adjust_ruin, args=(+1,), use_container_width=True)
                st.button("−", key="ruinminus", on_click=adjust_ruin, args=(-1,), use_container_width=True)
    with _section("Spectator Feed", "A public, read-only Vox-feed page for people watching the table (streamers, "
                  "absent players, etc.) that only ever shows current Shock — nothing else. They join by typing "
                  "the code below on the login screen (hidden there so it isn't stumbled on by accident)."):
        code = str(camp.get("spectator_code", "") or "")
        cc2 = st.columns([2, 1])
        if code:
            cc2[0].markdown(f"<div class='row'>Spectator Code: <b style='letter-spacing:.25em;font-family:Cinzel'>{html.escape(code)}</b></div>", unsafe_allow_html=True)
        else:
            cc2[0].caption("No active Spectator Code. Generate one to let people watch.")
        if cc2[1].button("Generate New Code", key="spectator_new_code", use_container_width=True):
            generate_spectator_code(); st.rerun()
        if code and st.button("Revoke Code", key="spectator_revoke_code"):
            clear_spectator_code(); st.rerun()
        st.caption("Nothing else about a Player or NPC is ever exposed to Spectators, even when visible below.")
        vc = st.columns(2)
        show_players = vc[0].checkbox("Show Players' Shock", value=bool(camp.get("spectator_show_players")), key="spectator_show_players_cb")
        show_monsters = vc[1].checkbox("Show Monsters' Shock", value=bool(camp.get("spectator_show_monsters")), key="spectator_show_monsters_cb")
        if show_players != bool(camp.get("spectator_show_players")) or show_monsters != bool(camp.get("spectator_show_monsters")):
            set_spectator_visibility(show_players, show_monsters); st.rerun()

    with _section("Session Log", "A free-form, timestamped log of table notes/events. Entries are permanent "
                  "and visible to the Magister only, oldest at the bottom."):
        with st.form("voxlog"):
            msg = st.text_area("New Entry")
            if st.form_submit_button("Record"):
                if msg.strip():
                    add_log("Magister", msg.strip()); st.rerun()
        for lg in get_logs():
            st.markdown(f"<div class='row'><b>{lg['ts']}</b> - {lg['text']}</div>", unsafe_allow_html=True)


@st.fragment
def _gm_tab_requisitions():
    pending = list_requisitions(status="pending")
    with _section(f"Pending Requisitions · {len(pending)}",
                  "Wargear Players have asked for, waiting on your approval. Wealth/Influence are shown "
                  "only as context for your decision — nothing here is enforced automatically.",
                  expanded=bool(pending)):
        if not pending:
            st.caption("No open Requisitions.")
        chars_by_id = {c["id"]: c for c in list_characters()}
        for r in pending:
            ch = chars_by_id.get(r["character_id"])
            if not ch:
                continue
            gear = equipped_wargear_modifiers(ch)
            d = derived_traits(ch, gear)
            with st.container(border=True):
                head = st.columns([3, 1, 1, 1])
                head[0].markdown(f"**{html.escape(ch.get('name') or 'Unnamed')}** requests:")
                head[1].metric("Wealth", int(ch.get("cur_wealth", 0) or 0))
                head[2].metric("Influence", int(d.get("Influence", 0) or 0))
                is_custom = not r.get("source_craft_id")
                if head[3].button("Edit" if is_custom else "View", key=f"req_edit_{r['id']}", use_container_width=True, disabled=not is_custom):
                    st.session_state["req_editing"] = r["id"] if st.session_state.get("req_editing") != r["id"] else None

                editing = is_custom and st.session_state.get("req_editing") == r["id"]
                if editing:
                    details = r.get("details", {}) or {}
                    ename = st.text_input("Name", r["name"], key=f"req_name_{r['id']}")
                    eeffect = st.text_area("Description / Effect", r.get("effect", ""), height=80, key=f"req_effect_{r['id']}")
                    newdetails = dict(details)
                    newdetails.update(_render_wargear_data(f"req_gear_{r['id']}", details))
                    _wargear_trait_bonus_preview(newdetails)
                    newdetails["modifiers"] = _render_craft_modifiers(f"req_mods_{r['id']}", newdetails, "wargear")
                    if st.button("Save Edits", key=f"req_save_{r['id']}"):
                        update_requisition_item(r["id"], ename, eeffect, newdetails)
                        st.rerun()
                else:
                    st.markdown(f"<div class='wg'><b>{html.escape(r['name'])}</b>"
                                f"<div class='wgdesc'>{html.escape(r.get('effect','') or '')}</div></div>", unsafe_allow_html=True)
                    if not is_custom:
                        st.caption("Requested from the existing Wargear catalog, nothing to edit.")

                bc = st.columns(2)
                if bc[0].button("Approve", key=f"req_approve_{r['id']}", type="primary", use_container_width=True):
                    ok, msg = resolve_requisition(r["id"], True, actor_name=(st.session_state.get("user") or {}).get("username", "Magister"))
                    (st.success if ok else st.error)(msg)
                    if ok:
                        st.session_state.pop("req_editing", None)
                        add_log("Magister", f"Approved {ch.get('name')}'s Requisition for {r['name']}.")
                        st.rerun()
                if bc[1].button("Deny", key=f"req_deny_{r['id']}", use_container_width=True):
                    ok, msg = resolve_requisition(r["id"], False, actor_name=(st.session_state.get("user") or {}).get("username", "Magister"))
                    (st.success if ok else st.error)(msg)
                    if ok:
                        add_log("Magister", f"Denied {ch.get('name')}'s Requisition for {r['name']}.")
                        st.rerun()

    resolved = [r for r in list_requisitions() if r["status"] != "pending"][:30]
    with _section(f"Requisition History · {len(resolved)}",
                  "Recently approved or denied Requisitions, for reference.", key="requisition_history_section"):
        if not resolved:
            st.caption("Nothing resolved yet.")
        chars_by_id = {c["id"]: c for c in list_characters()}
        for r in resolved:
            ch = chars_by_id.get(r["character_id"])
            color = "#3fae5a" if r["status"] == "approved" else "#d13a3a"
            st.markdown(
                f"<div class='row'><b>{html.escape((ch or {}).get('name', 'Unknown'))}</b> · {html.escape(r['name'])} "
                f"· <span style='color:{color}'>{r['status'].upper()}</span></div>",
                unsafe_allow_html=True,
            )


@st.fragment
def _gm_tab_maintenance():
    with _section("File Maintenance", "Download or restore the campaign's entire SQLite database file, "
                  "players, NPCs, folders, XP, Vox, portraits, everything. Restoring overwrites all current data."):
        st.caption("The .db backup contains everything: players, NPCs, folders, XP, Vox, portraits. "
                   "On free hosting the disk may reset; download backups regularly.")
        if os.path.exists(DB_PATH):
            size = os.path.getsize(DB_PATH) / (1024 * 1024)
            st.write(f"Database size: {size:.2f} MB (SQLite storage grows automatically).")
            # Reading the whole DB file into memory here unconditionally used to run
            # on every single interaction anywhere in the Magister view (st.tabs()
            # computes every tab's body on every rerun, not just the visible one),
            # not just when this tab is open. Gate the actual read behind a click.
            if st.button("Prepare Backup for Download", key="maint_prepare_backup"):
                st.session_state["maint_backup_ready"] = True
            if st.session_state.get("maint_backup_ready"):
                with open(DB_PATH, "rb") as f:
                    st.download_button("Download backup (cogitador.db)", f.read(),
                                       file_name="cogitador.db", mime="application/octet-stream")
        up = st.file_uploader("Restore backup", type=["db"])
        if up is not None and st.button("Overwrite everything"):
            with open(DB_PATH, "wb") as f:
                f.write(up.getbuffer())
            st.rerun()


def gm_view():
    st.markdown("<div class='banner'>✠ MAGISTER SANCTUM ✠<span class='sub'>Campaign Command</span></div>",
                unsafe_allow_html=True)

    if st.session_state.get("editing"):
        cid = st.session_state.editing
        bc = st.columns([1, 2, 5])
        bc[0].button("Back", on_click=cb_close)
        editing_ch = load_character(cid)
        if editing_ch and editing_ch.get("temp_instance"):
            if bc[1].button("Save Character", key="save_temp_instance_btn", use_container_width=True):
                save_temp_instance(cid)
                st.rerun()
            bc[2].caption("⚠ This is a disposable Generic NPC instance, it will be deleted when combat ends "
                          "unless you save it now to keep it as a permanent character sheet.")
        t = st.tabs(["Battle View", "Edit"])
        with t[0]:
            battle_view(cid)
        with t[1]:
            edit_view(cid, gm_mode=True)
        return

    # Player Audit tab temporarily disabled at the user's request.
    # Restore by uncommenting the original tabs line below (and the
    # `players_audit_view()` call further down) and removing the replacement.
    # tabs = st.tabs(["Characters", "Players", "Craft", "Archetypes", "Vox", "Progression", "Session", "Combat", "Campaign", "Maintenance"])
    tabs = st.tabs(["Characters", "Craft", "Archetypes", "Vox", "Progression", "Session", "Combat", "Requisitions", "Campaign", "Maintenance"])

    with tabs[0]:
        _gm_tab_characters()
    # with tabs[1]:
    #     players_audit_view()
    with tabs[1]:
        craft_view()
    with tabs[2]:
        archetypes_view()
    with tabs[3]:
        _gm_tab_vox()
    with tabs[4]:
        _gm_tab_progression()
    with tabs[5]:
        _gm_tab_session()
    with tabs[6]:
        _gm_tab_combat()
    with tabs[7]:
        _gm_tab_requisitions()
    with tabs[8]:
        _gm_tab_campaign()
    with tabs[9]:
        _gm_tab_maintenance()


@st.fragment(run_every=REFRESH_S)
def spectator_view():
    """A public, read-only Vox-feed for spectators (streamers, absent Players,
    etc.) who joined via a Spectator Code, entered through the hidden '◈'
    control on the login screen. By design this is the ONLY thing a Spectator
    can ever see: each side's current Shock, and only for whichever side the
    Magister has toggled visible in Campaign > Spectator Feed. No names beyond
    what's needed to tell combatants apart, no Wounds, no Wrath, no Tier, no
    Notes, nothing else — deliberately superficial."""
    camp = get_campaign()
    st.markdown(
        "<div class='spectator-banner'>✠ VOX-AUSPEX FEED ✠"
        f"<span class='sub'>{html.escape(camp.get('name', ''))} &nbsp;·&nbsp; Session {camp.get('session_no', 1)}</span>"
        "<span class='spectator-static'>ᛝ ⟟ ᛝ ⟟ ᛝ</span></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='spectator-flavor'>Cogitator-relayed vitality signals only. All tactical and "
        "biographical data remains encrypted at the Adeptus Administratum.</div>",
        unsafe_allow_html=True,
    )

    def shock_panel(title, chars, visible):
        st.markdown(f"<div class='spectator-panel-ttl'>{title}</div>", unsafe_allow_html=True)
        if not visible:
            st.markdown("<div class='spectator-locked'>✠ VOX-LINK SEVERED BY THE MAGISTER ✠</div>", unsafe_allow_html=True)
            return
        if not chars:
            st.markdown("<div class='spectator-locked'>NO SIGNAL DETECTED</div>", unsafe_allow_html=True)
            return
        rows = []
        for i, ch in enumerate(chars, 1):
            gear = equipped_wargear_modifiers(ch)
            d = derived_traits(ch, gear)
            cur = max(0, int(ch.get("cur_shock", 0) or 0))
            mx = max(1, int(d.get("Max Shock", 1) or 1))
            pct = max(0, min(100, round(100 * cur / mx)))
            danger = " spectator-danger" if pct >= 75 else (" spectator-warn" if pct >= 40 else "")
            codename = f"{title[:1]}-{i:02d}"
            rows.append(
                f"<div class='shock-row'><span class='shock-name'>{codename}</span>"
                f"<div class='shock-bar'><div class='shock-fill{danger}' style='width:{pct}%'></div></div>"
                f"<span class='shock-value'>{cur}/{mx}</span></div>"
            )
        st.markdown("".join(rows), unsafe_allow_html=True)

    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            players = [c for c in list_characters("player") if not c.get("temp_instance")]
            shock_panel("IMPERIAL FORCES", players, bool(camp.get("spectator_show_players")))
    with right:
        with st.container(border=True):
            npcs = [c for c in list_characters("npc") if not c.get("temp_instance")]
            shock_panel("HOSTILE CONTACTS", npcs, bool(camp.get("spectator_show_monsters")))

    st.markdown("<div class='foot'>✠ THE EMPEROR PROTECTS ✠</div>", unsafe_allow_html=True)
    if st.button("Disconnect", key="spectator_disconnect"):
        st.session_state.user = None; st.rerun()


def _player_tab_requisition(cid):
    st.markdown(f"<div class='sectionttl'>{T('Requisition Log')}</div>", unsafe_allow_html=True)
    st.caption(T("Ask the Magister for a piece of Wargear. It shows as Under Review, granting nothing, "
                 "until approved, whether it's a brand-new item you define here (same editor the Magister "
                 "uses for the Craft catalog) or one already known to the campaign."))

    with st.expander(T("Request a New Item"), expanded=False):
        st.caption(T("Same fields as the Magister's own Craft catalog. Nothing here applies to your sheet "
                     "until the Magister approves it."))
        rname = st.text_input(T("Name"), key=f"reqnew_name_{cid}")
        rdesc = st.text_area(T("Description / Effect"), key=f"reqnew_effect_{cid}", height=100)
        details = {}
        details.update(_render_wargear_data(f"reqnew_gear_{cid}", details))
        _wargear_trait_bonus_preview(details)
        details["modifiers"] = _render_craft_modifiers(f"reqnew_mods_{cid}", details, "wargear")
        if st.button(T("Submit Requisition"), type="primary", use_container_width=True, key=f"reqnew_submit_{cid}"):
            if not rname.strip() or not rdesc.strip():
                st.error(T("Name and Description / Effect are required."))
            else:
                ok, msg = create_wargear_requisition(
                    cid, name=rname.strip(), effect=rdesc.strip(),
                    details={**details, "structured_rules": True, "custom": True, "official": False},
                )
                (st.success if ok else st.error)(T(msg) if ok else msg)
                if ok: st.rerun()

    with st.expander(T("Request a Catalog Item"), expanded=False):
        catalog = list_craft_items("wargear")
        if catalog:
            names = [r["name"] for r in catalog]
            picked = st.selectbox(T("Wargear"), names, key=f"req_catalog_pick_{cid}")
            row = next(r for r in catalog if r["name"] == picked)
            if row.get("effect"):
                st.caption(row["effect"])
            if st.button(T("Request This Item"), key=f"req_catalog_btn_{cid}"):
                ok, msg = create_wargear_requisition(cid, source_craft_id=int(row["id"]))
                (st.success if ok else st.error)(T(msg) if ok else msg)
                if ok: st.rerun()
        else:
            st.caption(T("The Wargear catalog is empty."))

    mine = list_requisitions(character_id=cid)
    st.markdown(f"<div class='sectionttl'>{T('Your Requisitions')}</div>", unsafe_allow_html=True)
    if not mine:
        st.caption(T("No Requisitions filed yet."))
    for r in mine:
        badge = {"pending": ("Em Análise" if st.session_state.get("ui_lang") == "pt" else "Under Review", "#c9922e"),
                 "approved": ("Aprovado" if st.session_state.get("ui_lang") == "pt" else "Approved", "#3fae5a"),
                 "denied": ("Negado" if st.session_state.get("ui_lang") == "pt" else "Denied", "#d13a3a")}.get(r["status"], (r["status"], "#999"))
        cols = st.columns([5, 1.4, 1])
        cols[0].markdown(f"<div class='tal'><span class='tn'>{html.escape(r['name'])}</span>"
                          f"<div class='taleffect'>{html.escape(r.get('effect','') or '')}</div></div>", unsafe_allow_html=True)
        cols[1].markdown(f"<span style='color:{badge[1]};font-family:Cinzel;letter-spacing:.05em;font-size:.8rem'>{badge[0].upper()}</span>", unsafe_allow_html=True)
        if r["status"] != "pending":
            if cols[2].button(T("Dismiss"), key=f"req_dismiss_{r['id']}", use_container_width=True):
                delete_requisition(r["id"]); st.rerun()


def player_view():
    _language_flag_toggle()
    camp = get_campaign()
    st.markdown(f"<div class='banner'>✠ SERVICE RECORD ✠"
                f"<span class='sub'>{camp['name']} · {T('Session')} {camp['session_no']}</span></div>", unsafe_allow_html=True)
    cid = char_id_for_user(st.session_state.user["id"])
    if not cid:
        st.error(T("No character sheet linked. Contact the Magister."))
        return
    t = st.tabs([T("Battle View"), T("Character Sheet"), T("Requisition")])
    with t[0]:
        battle_view(cid)
    with t[1]:
        edit_view(cid, gm_mode=False)
    with t[2]:
        _player_tab_requisition(cid)


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

    if st.session_state.user["role"] == "spectator":
        spectator_view(); return

    with st.sidebar:
        camp = get_campaign(); role = st.session_state.user["role"]
        st.markdown(f"### ✠ {camp['name']}")
        st.write(f"User: {st.session_state.user['username']}")
        st.write("Role: " + ("Magister" if role == "gm" else "Battle-Brother"))
        if role == "gm":
            # Same compact metric + stacked −/+ pattern as the Battle Sheet
            # vitals and the Campaign tab's Ruin counter.
            with st.container(key="ruin_sidebar_vsb"):
                ruin_cols = st.columns([5, 1], gap="small")
                ruin_cols[0].metric("Ruin", camp["ruin"])
                with ruin_cols[1]:
                    st.button("+", key="sidebar_ruin_plus", on_click=adjust_ruin, args=(+1,), use_container_width=True)
                    st.button("−", key="sidebar_ruin_minus", on_click=adjust_ruin, args=(-1,), use_container_width=True)
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