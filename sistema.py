"""

"""

import streamlit as st
import psycopg2
import psycopg2.extras
import psycopg2.pool
import hashlib
import secrets
import json
import math
import html
import os
import random
import re
import copy
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

REFRESH_S = 1.0
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
# Core Rulebook 2e Conditions (p.199-200). Stored per-character as
# {name: stacks}; most are a simple on/off toggle (stacks=1), but a few
# (Bleeding, Hindered, Vulnerable) are explicitly meant to stack (p.198:
# "You can be subjected to the same Condition more than once... the
# penalties stack"). A GM/Player can also add a free-text marker beyond
# this list (e.g. a Wargear-granted activatable status like Cameleoline),
# tracked the same way.
CONDITIONS = ["Bleeding", "Blinded", "Exhausted", "Fear", "Frenzied", "Hindered",
              "On Fire", "Pinned", "Poisoned", "Prone", "Restrained", "Staggered",
              "Terror", "Vulnerable"]
CONDITION_COLOR = {
    "Bleeding": "#c62828", "On Fire": "#e65100", "Poisoned": "#558b2f",
    "Exhausted": "#616161", "Terror": "#4a148c", "Fear": "#4a148c",
}
POSITIVE_STATUSES = ["Cover", "Stealth"]
POSITIVE_STATUS_COLOR = {"Cover": "#2e7d32", "Stealth": "#1565c0", "Cameleoline": "#6a1b9a"}

INC_TALENT_ADAPTERS = {}

_INC_RARITIES = ("Common", "Uncommon", "Rare", "Legendary", "Unique")
_INC_RARITY_MAX_STACKS = {"Common": 5, "Uncommon": 5, "Rare": 5, "Legendary": 5, "Unique": 1}
# Every Talent acquisition (bought or stacked) permanently raises max Shock
# by this much - rarer Talents represent more of an edge, so they buy more
# of the resource that both soaks damage and now fuels bonus hit dice.
_INC_TALENT_SHOCK_BONUS = {"Common": 2, "Uncommon": 4, "Rare": 6, "Legendary": 10, "Unique": 15}

# 100 Incursion-only talents. Five copies of each talent exist in the pool;
# Unique talents still have a per-player stack cap of one.
_INC_TALENT_BLUEPRINTS = [
("Blood Engine", "Each successful attack restores 1 Shock.", "Common"),
("Iron Nerve", "Gain +1 attack die while below half Shock.", "Common"),
("Field Scavenger", "The first item acquired after each combat costs 25% less XP.", "Common"),
("Execution Rhythm", "A kill grants +1 die to the next attack.", "Common"),
("Brutal Momentum", "After a melee hit, gain +1 temporary Strength until combat ends.", "Common"),
("Deadeye Discipline", "After a ranged hit, gain +1 temporary Agility until combat ends.", "Common"),
("Pain Dividend", "The first Wound suffered each combat grants 1 Wrath.", "Common"),
("Second Wind", "When reduced below 50% Wounds, recover 2 Shock once per combat.", "Common"),
("Blood Mark", "Every 3 Icons on a hit inflicts 1 Bleeding.", "Common"),
("Hard Target", "While above half Wounds, gain +1 Defence.", "Common"),
("Close Quarters", "Melee attacks gain +1 damage.", "Common"),
("Suppressive Fire", "Ranged attacks gain +1 damage against full-Health enemies.", "Common"),
("Combat Rations", "Rest restores an additional 5% Wounds.", "Common"),
("Field Repairs", "Rest repairs an additional 5% weapon durability.", "Common"),
("Predator Instinct", "Gain +1 die against enemies with Bleeding.", "Common"),
("Veteran Grip", "Weapon durability loss from a Wrath Die 1 is reduced by 1.", "Common"),
("Shock Trooper", "The first Shock damage taken each combat is reduced by 1.", "Common"),
("Last Magazine", "At 25% or less Wounds, ranged damage gains +2.", "Common"),
("Butcher's Step", "After defeating an enemy, gain +1 Speed until the next node.", "Common"),
("Iron Stomach", "Consumable healing restores +2 additional Wounds.", "Common"),
("Ash Walker", "Gain +1 Agility while fighting in an Ambush.", "Uncommon"),
("Grim Focus", "The first attack each combat gains +2 dice.", "Uncommon"),
("Killing Stroke", "Critical Hits gain +2 damage.", "Uncommon"),
("Armour Eater", "Critical Hits reduce enemy armour durability by 2.", "Uncommon"),
("Blood Circuit", "Every 2 Wrath spent restores 1 Shock.", "Uncommon"),
("Steel Heart", "Every 3 Wounds suffered grants +1 permanent Toughness this run.", "Uncommon"),
("Predator's Eye", "The first hit against a fresh enemy gains +2 ED.", "Uncommon"),
("Rupture", "Every 3 Icons on a melee hit inflicts +1 Wound.", "Uncommon"),
("Recoil Mastery", "Ranged attacks ignore the first point of weapon durability damage each combat.", "Uncommon"),
("Executioner", "Deal +3 damage against enemies below half Wounds.", "Uncommon"),
("War Cry", "After a kill, gain +1 Strength until the next rest.", "Uncommon"),
("Battle Rhythm", "Each consecutive successful attack gains +1 die, resetting on a miss.", "Uncommon"),
("Hardwired", "Gain +1 Toughness while Shock is below half.", "Uncommon"),
("Adrenal Surge", "After taking Wounds, the next attack gains +2 dice.", "Uncommon"),
("Merciless Aim", "Critical Hits with firearms gain +1 ED.", "Uncommon"),
("Crushing Blow", "Critical Hits with melee weapons gain +2 damage.", "Uncommon"),
("Hunter's Patience", "If you do not attack for a round, your next attack gains +3 dice.", "Uncommon"),
("Battlefield Surgeon", "Medicae restores +1 Shock.", "Uncommon"),
("Relic Keeper", "Rest repairs +10% durability on your most damaged weapon.", "Uncommon"),
("Iron Discipline", "Every 5 Wrath spent grants +1 permanent Toughness this run.", "Uncommon"),
("Blood Price", "Wrath Die 1 on a hit inflicts 1 Bleeding.", "Uncommon"),
("Sunder", "Each Critical Hit removes 1 additional enemy armour durability.", "Rare"),
("War Machine", "While above half Wounds, all weapon damage gains +2.", "Rare"),
("Execution Protocol", "Critical Hits against wounded enemies gain +3 damage.", "Rare"),
("Death Spiral", "Each kill permanently grants +1 Strength for this run.", "Rare"),
("Predator's Harvest", "Every 3 kills permanently grants +1 Agility for this run.", "Rare"),
("Iron Bastion", "Gain +2 Resilience while stationary in combat.", "Rare"),
("Void Hunter", "Gain +2 dice against Tier 3+ enemies.", "Rare"),
("Blood Frenzy", "Each melee kill restores 2 Shock.", "Rare"),
("Ammunition Savant", "Firearm consumable ammunition has a 25% chance not to be consumed.", "Rare"),
("Master of Arms", "The first weapon attack each combat gains +2 ED.", "Rare"),
("Unbroken", "Once per combat, prevent the first Wound that would reduce you below 1 Wound.", "Rare"),
("Pain to Power", "Every 3 Shock lost grants +1 temporary Strength for the combat.", "Rare"),
("Bloodsmith", "Each Critical Hit repairs 2 durability on the weapon used.", "Rare"),
("Combat Meditation", "Every 4 Icons rolled restores 1 Shock.", "Rare"),
("Armour Master", "Your armour durability loss from enemy Critical Hits is reduced by 1.", "Rare"),
("Rapid Execution", "If your first attack hits, your next attack gains +2 dice.", "Rare"),
("Killer Instinct", "Enemies below 25% Wounds take +4 damage from your attacks.", "Rare"),
("Tactical Withdrawal", "A successful Flee also restores 2 Shock.", "Rare"),
("Warlord's Resolve", "At 0 Shock, gain +2 attack dice instead of becoming impaired.", "Rare"),
("Savage Precision", "Melee attacks gain +1 ED against Bleeding enemies.", "Rare"),
("Cold Vengeance", "After an enemy deals Wounds to you, your next attack against it gains +3 damage.", "Rare"),
("Relentless", "Successful attacks grant +1 die to the next attack, stacking during combat.", "Rare"),
("Titan Grip", "Melee weapons gain +2 base damage.", "Legendary"),
("Execution Matrix", "Every Critical Hit against a target below half Wounds deals +4 additional Wounds.", "Legendary"),
("Wrathforged", "Every Wrath spent grants +1 permanent Strength this run.", "Legendary"),
("Iron Soul", "Every 4 Wrath spent grants +1 permanent Toughness this run.", "Legendary"),
("Blood Crown", "Every 5 kills grants +1 permanent Strength and Toughness.", "Legendary"),
("Perfect Kill", "A Critical Hit that defeats an enemy restores all Shock.", "Legendary"),
("Armour Reaver", "Critical Hits completely ignore 3 points of enemy Resilience from Armour.", "Legendary"),
("Storm of Steel", "A successful firearm attack gains +1 additional target against a second locked enemy.", "Legendary"),
("Deathless", "Once per run, surviving 0 Wounds leaves you at 1 Wound instead.", "Legendary"),
("Masterwork Instinct", "Weapon durability penalties are halved, rounded down.", "Legendary"),
("Blood Economy", "Every 3 Wrath spent grants +1 XP.", "Legendary"),
("Ruin Breaker", "Boss enemies suffer +5 damage from your first successful attack.", "Legendary"),
("Apex Hunter", "Against Tier 4 enemies, gain +4 attack dice and +4 damage.", "Legendary"),
("Unstoppable", "You cannot lose more than 50% of current Wounds from one attack.", "Legendary"),
("War Saint", "Critical Hits restore 2 Shock and 1 Wrath.", "Legendary"),
("Relentless Core", "Every successful attack restores 1 Wrath.", "Legendary"),
("Doom Sight", "Your first miss each combat is converted into a hit with 1 Icon.", "Legendary"),
("Void Temper", "Your highest-durability weapon gains +5 damage.", "Legendary"),
("Champion's Blood", "Boss victories permanently grant +1 to all seven Attributes for the run.", "Legendary"),
("Emperor's Edge", "Critical Hits with a weapon at full durability deal +6 damage.", "Unique"),
("The Last Wall", "When you would die, survive at 1 Wound once per run and fully restore Shock.", "Unique"),
("Black Crusade", "Each enemy defeated permanently grants +1 damage to every weapon this run.", "Unique"),
("Lion's Shadow", "Your first successful attack each combat is automatically Critical.", "Unique"),
("Machine Spirit", "Your equipped weapon cannot lose durability from Wrath Die 1.", "Unique"),
("Blood Throne", "Every Critical Hit restores all Shock and grants +2 Wrath.", "Unique"),
("Unbroken Oath", "If you reach 0 Wounds, reset to 25% Wounds once per run and continue combat.", "Unique"),
("Death Sentence", "The first attack against a boss always deals at least 10 Wounds on a hit.", "Unique"),
("Eternal Arsenal", "You may carry a fourth weapon, but only one copy of it can be equipped.", "Unique"),
("The Emperor's Favour", "Once per node, turn one failed attack into a Critical Hit.", "Unique"),
("Master of War", "Every successful attack permanently grants +1 attack die for the rest of the run.", "Unique"),
("Angelic Fury", "While at or below 25% Wounds, every hit is Critical.", "Unique"),
("Unyielding Flesh", "The first Wound suffered each combat is reduced to 0.", "Unique"),
("Crimson Reprisal", "Each Critical Hit caused restores 2 Shock.", "Unique"),
("Sundering Blow", "Each Critical Hit destroys 2 enemy armour durability.", "Unique"),
("Relic of Defiance", "Once per combat, ignore all damage from one enemy attack.", "Unique"),
("Omega Protocol", "At the start of a boss combat, fully restore Wounds, Shock and Wrath.", "Unique"),
]
# Fill any accidental count drift deterministically with themed talents.
while len(_INC_TALENT_BLUEPRINTS) < 100:
    i = len(_INC_TALENT_BLUEPRINTS) + 1
    _INC_TALENT_BLUEPRINTS.append((f"Forbidden Doctrine {i:02d}", f"Gain +{1 + i % 3} damage on attacks after spending Wrath.", "Common"))
INC_NEW_TALENTS = [(n, e) for n,e,_ in _INC_TALENT_BLUEPRINTS[:100]]
for _name, _effect, _rarity in _INC_TALENT_BLUEPRINTS[:100]:
    INC_TALENT_ADAPTERS[_name.lower()] = {"kind":"trigger", "rule":_effect, "trigger":"incursion_custom"}



def _incursion_item_blueprints():
    firearm_heads=["Vigil","Aquila","Vox","Cinder","Mourn","Helix","Penitent","Solar","Obsidian","Crux"]
    firearm_tails=["Pattern","Carbine","Repeater","Lance","Caster","Pistol","Rifle","Autogun","Driver","Barrage"]
    melee_heads=["Executioner","Martyr","Reaver","Penitent","Iron","Black","Crimson","Sanctum","Grave","Dread"]
    melee_tails=["Blade","Cleaver","Maul","Sword","Axe","Halberd","Glaive","Claw","Hammer","Spear"]
    armour_heads=["Aquila","Penitent","Bastion","Obsidian","Solar","Martyr","Crucible","Raven","Iron","Cathedral"]
    armour_tails=["Plate","Carapace","Bulwark","Cuirass","Harness","Shell","Mantle","Aegis","Ward","Panoply"]
    consum_heads=["Red","Black","White","Saint","Forge","Medicae","Combat","Vox","Cinder","Iron"]
    consum_tails=["Stim", "Regen", "Coagulant", "Injector", "Ration", "Ampoule", "Serum", "Dose", "Charge", "Tonic"]
    rarity=["Common"]*20+["Uncommon"]*20+["Rare"]*20+["Legendary"]*20+["Unique"]*20
    out=[]
    for i in range(100):
        r=rarity[i]
        dmg=8+(i%10)+([0,1,2,3,5][i//20])
        ed=1+(i%4)//2
        ap=0 if i%5<3 else -1-(i%20)//10
        name=f"{firearm_heads[i%10]} {firearm_tails[i//10]} {i+1:02d}"
        out.append({"kind":"wargear","name":name,"effect":f"{r} firearm · Damage {dmg} +{ed} ED · AP {ap}","cost":15+([0,10,25,50,90][i//20]),"source":"Wrath Incursion","details":{"incursion_only":True,"category":"firearm","rarity":r,"damage":str(dmg),"ed":ed,"ap":ap,"keywords":["Incursion","Firearm"]}})
    for i in range(100):
        r=rarity[i]; bonus=2+(i%8)+([0,1,2,3,5][i//20]); ed=2+(i%4); ap=-((i%4)//2)
        name=f"{melee_heads[i%10]} {melee_tails[i//10]} {i+1:02d}"
        out.append({"kind":"wargear","name":name,"effect":f"{r} melee · Strength +{bonus} · +{ed} ED · AP {ap}","cost":15+([0,10,25,50,90][i//20]),"source":"Wrath Incursion","details":{"incursion_only":True,"category":"melee","rarity":r,"damage":f"(S) +{bonus}","damage_attribute":"Strength","ed":ed,"ap":ap,"keywords":["Incursion","Melee"]}})
    for i in range(100):
        r=rarity[i]; ar=1+(i%5)+([0,1,1,2,3][i//20])
        name=f"{armour_heads[i%10]} {armour_tails[i//10]} {i+1:02d}"
        out.append({"kind":"wargear","name":name,"effect":f"{r} armour · Armour Rating +{ar}","cost":20+([0,15,30,60,110][i//20]),"source":"Wrath Incursion","details":{"incursion_only":True,"category":"armour","rarity":r,"armour_rating":ar,"keywords":["Incursion","Armour"]}})
    for i in range(100):
        r=rarity[i]; heal=3+(i%8)+([0,1,2,4,6][i//20])
        name=f"{consum_heads[i%10]} {consum_tails[i//10]} {i+1:02d}"
        effect=f"{r} consumable · Restore {heal} Wounds or Shock when used."
        out.append({"kind":"wargear","name":name,"effect":effect,"cost":8+([0,5,15,30,60][i//20]),"source":"Wrath Incursion","details":{"incursion_only":True,"category":"consumable","rarity":r,"heal_wounds":heal,"heal_shock":heal,"stackable":True,"stack_group":name,"keywords":["Incursion","Consumable"]}})
    return out


def _ensure_incursion_wargear_catalog():
    # One transaction for all 400 Incursion items. This is important on Supabase:
    # opening/committing 400 separate connections would make startup painfully slow.
    blueprints=_incursion_item_blueprints(); conn=get_conn()
    existing={str(r.get("name","")).lower() for r in list_craft_items("wargear",active_only=False)}
    now=now_iso(); inserted=False
    for item in blueprints:
        if item["name"].lower() in existing: continue
        conn.execute("INSERT INTO craft_items(kind,name,effect,cost,source,source_url,details,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,1,?,?)",
                     (item["kind"],item["name"],item.get("effect",""),int(item.get("cost",0)),item.get("source",""),item.get("source_url",""),json.dumps(item.get("details",{}),ensure_ascii=False),now,now)); inserted=True
    conn.commit(); conn.close()
    if inserted: invalidate_craft_cache()


def _ensure_incursion_catalog():
    # One connection/transaction for the complete 100-talent bootstrap.
    conn=get_conn()
    conn.execute("CREATE TABLE IF NOT EXISTS incursion_talent_pool(name TEXT PRIMARY KEY, rarity TEXT, pool_total INTEGER DEFAULT 5, pool_available INTEGER DEFAULT 5, max_stacks INTEGER DEFAULT 5)")
    existing={str(r.get("name","")).lower():r for r in list_craft_items("talent",active_only=False)}
    now=now_iso(); inserted=False
    for name,effect,rarity in _INC_TALENT_BLUEPRINTS[:100]:
        if name.lower() not in existing:
            details={"incursion_executable":True,"incursion_only":True,"rarity":rarity,"max_stacks":_INC_RARITY_MAX_STACKS[rarity],"pool_total":5}
            conn.execute("INSERT INTO craft_items(kind,name,effect,cost,source,source_url,details,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,1,?,?)",
                         ("talent",name,effect,30,"Wrath Incursion","",json.dumps(details,ensure_ascii=False),now,now)); inserted=True
        conn.execute("INSERT INTO incursion_talent_pool(name,rarity,pool_total,pool_available,max_stacks) VALUES(?,?,?,?,?) ON CONFLICT(name) DO NOTHING",
                     (name,rarity,5,5,_INC_RARITY_MAX_STACKS[rarity]))
    conn.commit(); conn.close()
    if inserted: invalidate_craft_cache()


def _inc_talent_catalog_row(talent):
    name = str(talent.get("name", "") if isinstance(talent, dict) else talent).strip()
    try: cid = int(talent.get("craft_id", -1) or -1) if isinstance(talent, dict) else -1
    except Exception: cid = -1
    rows = list_craft_items("talent", active_only=False)
    if cid > 0:
        row = next((r for r in rows if int(r.get("id", -1)) == cid), None)
        if row and craft_details(row).get("incursion_only"): return row
    return next((r for r in rows if str(r.get("name", "")).strip().lower() == name.lower()
                 and craft_details(r).get("incursion_only")), None)

def _inc_talent_catalog_row(talent):
    name = str(talent.get("name", "") if isinstance(talent, dict) else talent).strip()
    try: cid = int(talent.get("craft_id", -1) or -1) if isinstance(talent, dict) else -1
    except Exception: cid = -1
    rows = list_craft_items("talent", active_only=False)
    if cid > 0:
        row = next((r for r in rows if int(r.get("id", -1)) == cid), None)
        if row: return row
    return next((r for r in rows if str(r.get("name", "")).strip().lower() == name.lower()), None)

def _inc_talent_adapters(ch, run=None):
    merged = _inc_merge_character(ch, run or {}) if run else ch
    out = []
    for talent in normalize_talents(merged.get("talents", [])):
        name = str(talent.get("name", "")).strip(); low = name.lower()
        row = _inc_talent_catalog_row(talent)
        details = craft_details(row) if row else _gear_details_dict(talent.get("details", {}))
        modifiers = craft_modifiers(row) if row else {}
        adapter = INC_TALENT_ADAPTERS.get(low)
        if adapter:
            out.append({"name": name, "status": "active", "rule": adapter["rule"], "trigger": adapter["trigger"], "modifiers": modifiers})
        elif modifiers:
            mods = ", ".join(f"{k.replace('_',' ').title()} {int(v):+d}" for k,v in modifiers.items())
            out.append({"name": name, "status": "passive", "rule": f"Passive sheet effect: {mods}.", "trigger": "", "modifiers": modifiers})
        else:
            effect = str((row or {}).get("effect", talent.get("effect", "")) or "").strip()
            out.append({"name": name, "status": "source" if effect else "manual",
                        "rule": f"Roguelike adaptation: {effect}" if effect else "No executable Incursion rule registered yet.",
                        "trigger": "", "modifiers": modifiers, "details": details})
    return out

def _inc_has_talent(ch, name, run=None):
    target = str(name).strip().lower()
    merged = _inc_merge_character(ch, run or {}) if run else ch
    return any(str(x.get("name", "")).strip().lower() == target for x in normalize_talents(merged.get("talents", [])))

_COND_CUSTOM = "__custom__"
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
    # Wrath is a resource, not a Tier-scaled derived maximum in W&G 2e.
    # Baseline is 2 points at the start of each session; Touched by Fate adds +Rank.
    rank = max(1, int(ch.get("rank", 1) or 1))
    talent_names = {str(x.get("name", "")).strip().lower() if isinstance(x, dict) else str(x).strip().lower()
                    for x in (ch.get("talents") or [])}
    starting_wrath = 2 + (rank if "touched by fate" in talent_names else 0) + gear.get("wrath", 0)
    return {
        "Defence": defence, "Resilience": resilience, "Soak": T,
        "Max Wounds": max_wounds, "Max Shock": max_shock, "Max Wrath": starting_wrath,
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
#
#  Two backends are supported behind the exact same call surface used
#  everywhere else in this file (conn.execute(sql, params) with '?'
#  placeholders, cursor.fetchone()/.fetchall() returning rows indexable by
#  both column name and position, cursor.lastrowid, cursor.rowcount,
#  conn.commit()/.rollback()/.close()/.cursor()):
#    - SQLite (default): a local file, used when no SUPABASE_DB_URL is set.
#    - Postgres (Supabase): used when SUPABASE_DB_URL is configured, so the
#      campaign survives Streamlit Cloud redeploys (a local SQLite file does
#      not - it resets to whatever is in the repo on every redeploy).
#  _PgConn/_PgCursor below translate the small set of syntax differences
#  (placeholders, AUTOINCREMENT, BLOB, INSERT...RETURNING for lastrowid) so
#  the ~200 call sites throughout this file did not need to change.
# ============================================================
def _pg_dsn():
    global _PG_DSN_CACHE, _PG_DSN_RESOLVED
    if not _PG_DSN_RESOLVED:
        dsn = os.environ.get("SUPABASE_DB_URL")
        if not dsn:
            try:
                dsn = st.secrets.get("SUPABASE_DB_URL")
            except Exception:
                dsn = None
        _PG_DSN_CACHE = dsn or None
        _PG_DSN_RESOLVED = True
    return _PG_DSN_CACHE
_PG_DSN_CACHE = None
_PG_DSN_RESOLVED = False


def using_postgres():
    return bool(_pg_dsn())


class _PgRow:
    """Mimics sqlite3.Row: indexable by column name AND by position."""
    __slots__ = ("_cols", "_vals")

    def __init__(self, cols, vals):
        self._cols = cols
        self._vals = tuple(bytes(v) if isinstance(v, memoryview) else v for v in vals)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._vals[key]
        try:
            idx = self._cols.index(key)
        except ValueError:
            raise KeyError(key)
        return self._vals[idx]

    def get(self, key, default=None):
        try:
            return self[key]
        except (KeyError, IndexError):
            return default

    def keys(self):
        return list(self._cols)

    def __contains__(self, key):
        return key in self._cols

    def __iter__(self):
        return iter(self._cols)

    def __len__(self):
        return len(self._cols)

    def __eq__(self, other):
        if isinstance(other, _PgRow):
            return self._cols == other._cols and self._vals == other._vals
        return NotImplemented


_PG_INSERT_RE = re.compile(r"^\s*INSERT\s+INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.I)
_PG_NO_ID_TABLES = {"combatant", "incursion_talent_pool"}


def _translate_sql_pg(sql):
    """Rewrite the handful of SQLite-specific bits of `sql` for Postgres.
    Everything else (the actual query logic) is standard SQL and needs no
    translation. Returns (translated_sql, wants_lastrowid)."""
    out = re.sub(r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT", "SERIAL PRIMARY KEY", sql, flags=re.I)
    out = re.sub(r"\bBLOB\b", "BYTEA", out, flags=re.I)
    wants_id = False
    m = _PG_INSERT_RE.match(out)
    if m and m.group(1).lower() not in _PG_NO_ID_TABLES and "RETURNING" not in out.upper():
        wants_id = True
    out = out.replace("?", "%s")
    if wants_id:
        tail = out.rstrip()
        semi = tail.endswith(";")
        if semi: tail = tail[:-1]
        out = tail + " RETURNING id" + (";" if semi else "")
    return out, wants_id


class _PgCursor:
    def __init__(self, raw):
        self._cur = raw
        self.lastrowid = None

    def execute(self, sql, params=()):
        sql2, wants_id = _translate_sql_pg(sql)
        self._cur.execute(sql2, tuple(params) if params else None)
        self.lastrowid = None
        if wants_id:
            try:
                row = self._cur.fetchone()
                if row is not None:
                    self.lastrowid = row[0]
            except psycopg2.ProgrammingError:
                pass
        return self

    def _cols(self):
        return [d[0] for d in self._cur.description] if self._cur.description else []

    def fetchone(self):
        row = self._cur.fetchone()
        return None if row is None else _PgRow(self._cols(), row)

    def fetchall(self):
        cols = self._cols()
        return [_PgRow(cols, r) for r in self._cur.fetchall()]

    @property
    def rowcount(self):
        return self._cur.rowcount


class _PgConn:
    def __init__(self, raw, pool):
        self._raw = raw
        self._pool = pool

    def cursor(self):
        return _PgCursor(self._raw.cursor())

    def execute(self, sql, params=()):
        return _PgCursor(self._raw.cursor()).execute(sql, params)

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        # Return the connection to the pool instead of really closing it.
        # A defensive rollback first clears any aborted-transaction state
        # left by an exception that skipped an explicit rollback, so the
        # connection is always reusable by the next caller that checks it out.
        try:
            self._raw.rollback()
        except Exception:
            pass
        self._pool.putconn(self._raw)


@st.cache_resource(show_spinner=False)
def _pg_pool():
    return psycopg2.pool.ThreadedConnectionPool(1, 10, dsn=_pg_dsn(), connect_timeout=10)


def get_conn():
    if not using_postgres():
        raise RuntimeError(
            "SUPABASE_DB_URL is not configured. This campaign lives in Postgres "
            "(Supabase) only - there is no local-file fallback, so a missing "
            "connection string fails loudly here instead of silently starting "
            "a throwaway local database that loses everything on the next "
            "redeploy. Set SUPABASE_DB_URL in .streamlit/secrets.toml (local) "
            "or the app's Secrets panel (Streamlit Cloud)."
        )
    pool = _pg_pool()
    raw = pool.getconn()
    # Autocommit matches how a lightweight local store would behave: a plain
    # SELECT never opens an implicit transaction. Without this, psycopg2's
    # default non-autocommit mode leaves every connection "in transaction"
    # after even a read-only query, forcing close() to pay a second network
    # round-trip (ROLLBACK) just to release it back to the pool - doubling
    # latency on the overwhelming majority of calls, which are reads. Each
    # write statement still commits immediately and atomically on its own;
    # the handful of call sites doing several related writes before one
    # conn.commit() (now a harmless no-op) only lose all-or-nothing atomicity
    # across THOSE statements, not correctness of any single statement.
    raw.autocommit = True
    return _PgConn(raw, pool)


def hash_pw(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100_000).hex()


def _ensure_columns(conn, table, cols):
    have = {r[0] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name=?", (table,)
    ).fetchall()}
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
    except psycopg2.IntegrityError:
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
        spectator_code TEXT DEFAULT '', spectator_show_players INTEGER DEFAULT 0, spectator_show_monsters INTEGER DEFAULT 0,
        owlbear_enabled INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS owlbear_roll_request(
        id INTEGER PRIMARY KEY AUTOINCREMENT, character_id INTEGER NOT NULL, character_name TEXT DEFAULT '',
        label TEXT DEFAULT '', kind TEXT DEFAULT 'test', formula TEXT NOT NULL, dice_count INTEGER DEFAULT 0,
        modifier INTEGER DEFAULT 0, status TEXT DEFAULT 'pending', requested_at TEXT, resolved_at TEXT)""")
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
        name TEXT NOT NULL, effect TEXT DEFAULT '', details TEXT DEFAULT '{}', quantity INTEGER DEFAULT 1,
        status TEXT DEFAULT 'pending', requested_at TEXT, resolved_at TEXT, resolved_by TEXT DEFAULT '')""")
    # ---- Wrath Incursion (solo roguelike mini-game) -----------------------
    # Isolated from every table above: a run only ever READS a character's
    # attributes/skills/wargear/talents/powers as its starting point. It
    # never writes to characters/cur_wounds/cur_wealth/earned_xp and never
    # creates a wargear_requisition - nothing it does needs the Magister's
    # approval or touches the real sheet.
    c.execute("""CREATE TABLE IF NOT EXISTS incursion_run(
        id INTEGER PRIMARY KEY AUTOINCREMENT, character_id INTEGER NOT NULL,
        status TEXT DEFAULT 'active', stage TEXT DEFAULT 'start', loop_no INTEGER DEFAULT 1,
        bosses_cleared INTEGER DEFAULT 0, hp_current INTEGER, hp_max INTEGER, xp INTEGER DEFAULT 0,
        bonus_attributes TEXT DEFAULT '{}', bonus_skills TEXT DEFAULT '{}',
        extra_wargear TEXT DEFAULT '[]', starting_wargear TEXT DEFAULT '[]', extra_talents TEXT DEFAULT '[]',
        extra_powers TEXT DEFAULT '[]', extra_keywords TEXT DEFAULT '[]', heal_charges INTEGER DEFAULT 1,
        consumable_charges TEXT DEFAULT '{}', equipped_armor_key TEXT DEFAULT '', free_upgrade_used INTEGER DEFAULT 0,
        wounds_current INTEGER, wounds_max INTEGER, shock_current INTEGER, shock_max INTEGER,
        wrath_current INTEGER, wrath_max INTEGER, armour_durability_current INTEGER DEFAULT 0,
        armour_durability_max INTEGER DEFAULT 0, weapon_durabilities TEXT DEFAULT '{}',
        incursion_statuses TEXT DEFAULT '{}',
        pending_boss3_pvp INTEGER DEFAULT 0, node TEXT, created_at TEXT, ended_at TEXT, death_reason TEXT, xp_earned INTEGER DEFAULT 0)""")
    _ensure_columns(conn, "incursion_run", {
        "consumable_charges": "TEXT DEFAULT '{}'", "starting_wargear": "TEXT DEFAULT '[]'", "bonus_skills": "TEXT DEFAULT '{}'",
        "equipped_armor_key": "TEXT DEFAULT ''", "free_upgrade_used": "INTEGER DEFAULT 0",
        "wounds_current": "INTEGER", "wounds_max": "INTEGER", "shock_current": "INTEGER", "shock_max": "INTEGER",
        "wrath_current": "INTEGER", "wrath_max": "INTEGER", "armour_durability_current": "INTEGER DEFAULT 0",
        "armour_durability_max": "INTEGER DEFAULT 0", "weapon_durabilities": "TEXT DEFAULT '{}'", "xp_earned": "INTEGER DEFAULT 0",
        "incursion_statuses": "TEXT DEFAULT '{}'", "run_number": "INTEGER DEFAULT 1",
        "origin": "TEXT DEFAULT ''", "minions": "TEXT DEFAULT '[]'",
    })
    c.execute("""CREATE TABLE IF NOT EXISTS incursion_pvp_queue(
        id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL, character_id INTEGER NOT NULL,
        checkpoint TEXT NOT NULL, snapshot TEXT NOT NULL, status TEXT DEFAULT 'waiting',
        result TEXT, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS incursion_pvp_match(
        id INTEGER PRIMARY KEY AUTOINCREMENT, checkpoint TEXT NOT NULL,
        run_a INTEGER NOT NULL, run_b INTEGER NOT NULL,
        char_a INTEGER NOT NULL, char_b INTEGER NOT NULL,
        state TEXT NOT NULL, status TEXT DEFAULT 'active',
        created_at TEXT, updated_at TEXT)""")
    # A run that ends in death leaves behind a mob built from that
    # character's final stats/weapon - future Incursions (anyone's) can run
    # into it. Saved only here, never added to the game's own Bestiary.
    c.execute("""CREATE TABLE IF NOT EXISTS incursion_fallen_mob(
        id INTEGER PRIMARY KEY AUTOINCREMENT, source_character_id INTEGER, name TEXT NOT NULL, tier INTEGER NOT NULL,
        species TEXT DEFAULT '', attributes TEXT NOT NULL, attack_skill TEXT NOT NULL, attack_pool INTEGER NOT NULL,
        weapon_name TEXT NOT NULL, weapon_damage INTEGER NOT NULL, loop_no_reached INTEGER NOT NULL,
        bosses_cleared INTEGER NOT NULL, created_at TEXT)""")
    conn.commit()
    # migration: ensure columns exist in databases created by older versions
    _ensure_columns(conn, "campaign", {"name": "TEXT", "tier": "INTEGER DEFAULT 2",
                                       "ruin": "INTEGER DEFAULT 0", "session_no": "INTEGER DEFAULT 1",
                                       "spectator_code": "TEXT DEFAULT ''", "spectator_show_players": "INTEGER DEFAULT 0",
                                       "spectator_show_monsters": "INTEGER DEFAULT 0",
                                       "owlbear_enabled": "INTEGER DEFAULT 0"})
    _ensure_columns(conn, "wargear_requisition", {"quantity": "INTEGER DEFAULT 1"})
    _ensure_columns(conn, "owlbear_roll_request", {"kind": "TEXT DEFAULT 'test'"})
    had_wealth_column = "cur_wealth" in {r[0] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name=?", ("characters",)
    ).fetchall()}
    _ensure_columns(conn, "characters", {
        "user_id": "INTEGER", "kind": "TEXT DEFAULT 'player'", "name": "TEXT", "chapter": "TEXT",
        "species": "TEXT", "archetype": "TEXT", "creation_mode": "TEXT DEFAULT 'archetype'", "archetype_history": "TEXT DEFAULT '[]'", "tier": "INTEGER DEFAULT 2", "starting_tier": "INTEGER DEFAULT 2", "rank": "INTEGER DEFAULT 1", "earned_xp": "INTEGER DEFAULT 0",
        "other_xp": "INTEGER DEFAULT 0", "faction": "TEXT DEFAULT ''", "keywords": "TEXT DEFAULT '[]'", "archetype_choices": "TEXT DEFAULT '{}'", "attributes": "TEXT", "skills": "TEXT", "talents": "TEXT", "powers": "TEXT",
        "wargear": "TEXT", "armour": "INTEGER DEFAULT 0", "cur_wounds": "INTEGER DEFAULT 0",
        "cur_shock": "INTEGER DEFAULT 0", "cur_wrath": "INTEGER DEFAULT 0", "cur_ammo": "INTEGER DEFAULT 3",
        "cur_corruption": "INTEGER DEFAULT 0", "cur_wealth": "INTEGER DEFAULT 0", "cur_faith": "INTEGER DEFAULT 0", "notes": "TEXT",
        "folder_id": "INTEGER", "portrait": "BLOB", "comms_on": "INTEGER DEFAULT 1",
        "comms_changed_at": "TEXT", "updated_at": "TEXT", "revision": "INTEGER DEFAULT 0",
        "temp_instance": "INTEGER DEFAULT 0", "conditions": "TEXT DEFAULT '{}'",
        "approval_status": "TEXT DEFAULT 'approved'"})
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
                conn.execute("""INSERT INTO combat_participant(encounter_id,character_id,side,added_at) VALUES(?,?,?,?)
                                ON CONFLICT(encounter_id,character_id) DO NOTHING""",
                             (eid, r[0], ch[0], now_iso()))
        conn.execute("DELETE FROM combatant")
    conn.commit()
    _load_custom_archetypes(conn)
    conn.close()
    _ensure_incursion_catalog()
    _ensure_incursion_wargear_catalog()


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

def create_player(username, pw, creation_mode="archetype", tier=2, rank=1, species="", archetype="", pending=False):
    conn = get_conn(); c = conn.cursor()
    try:
        salt = secrets.token_hex(16)
        c.execute("INSERT INTO users(username,pw_hash,salt,role,created_at) VALUES(?,?,?,?,?)",
                  (username, hash_pw(pw, salt), salt, "player", now_iso()))
        uid = c.lastrowid
        tier = max(1, min(MAX_TIER, int(tier)))
        rank = max(1, min(3, int(rank)))
        if pending:
            # Self-registration never offers Advanced Character Creation - the
            # Magister always sets Species/Archetype for a Player they didn't
            # personally recruit, since Advanced mode has no Archetype to vet.
            creation_mode = "archetype"
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
                     comms_on,comms_changed_at,approval_status)
                     VALUES(?, 'player', ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (uid, username, "", species, archetype, ARCHETYPES.get(archetype, {}).get("faction", "") if creation_mode == "archetype" else "", json.dumps([], ensure_ascii=False), json.dumps({}, ensure_ascii=False), creation_mode, tier, tier, rank, 0, 0, json.dumps(attrs),
                   json.dumps(skills), json.dumps([]), json.dumps([]), json.dumps(normalize_wargear((archetype_starting_wargear(archetype) if creation_mode == "archetype" else []) + starting_ammo_for_wargear(archetype_starting_wargear(archetype) if creation_mode == "archetype" else [])), ensure_ascii=False), 0, 0, 0, 0,
                   # Core Rulebook 2e, p.38: Corruption starts at 0, Wealth starts equal to Tier.
                   0, tier, "", 1, now_iso(), "pending" if pending else "approved"))
        conn.commit()
        return True, ("Registration submitted. The Magister must approve it before you can play."
                       if pending else "Player recruited.")
    except psycopg2.IntegrityError:
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
            for k in ("craft_id", "source", "source_url", "details", "rarity", "max_stacks", "stacks"):
                if k in t: entry[k] = t[k]
            entry["stacks"] = max(1, int(entry.get("stacks", 1) or 1))
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
    if row is not None and not isinstance(row, dict):
        try: row = dict(row)
        except Exception: row = {}
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

    # Conditional Wargear effects are never folded into this passive set.
    # They are evaluated separately from the character's current positive
    # statuses, so an item cannot grant a situational bonus all the time.
    return mods


def _has_positive_status(ch, name):
    conds = ch.get("conditions", {}) or {}
    wanted = str(name).strip().casefold()
    return any(str(k).strip().casefold() == wanted and int(v or 0) > 0 for k, v in conds.items())


def _has_cameleoline(ch):
    for w in normalize_wargear(ch.get("wargear", [])):
        if not w.get("equipped", True):
            continue
        if str(w.get("name", "")).strip().casefold() == "cameleoline cloak":
            return True
    return False


def active_positive_statuses(ch):
    active = []
    for status in POSITIVE_STATUSES:
        if _has_positive_status(ch, status):
            active.append(status)
    if _has_cameleoline(ch) and any(x in active for x in ("Cover", "Stealth")):
        active.append("Cameleoline")
    return active


def conditional_wargear_modifiers(ch):
    mods = {}
    if _has_cameleoline(ch) and any(_has_positive_status(ch, x) for x in ("Cover", "Stealth")):
        mods["defence"] = 1
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

    for k, v in conditional_wargear_modifiers(ch).items():
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


def create_wargear_requisition(cid, name="", effect="", details=None, source_craft_id=None, quantity=1):
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
    stackable, _ = _infer_stackable_gear(name, details or {})
    quantity = max(1, int(quantity or 1)) if stackable else 1
    conn = get_conn()
    conn.execute("""INSERT INTO wargear_requisition(character_id,source_craft_id,name,effect,details,quantity,status,requested_at)
                    VALUES(?,?,?,?,?,?, 'pending', ?)""",
                 (int(cid), int(source_craft_id) if source_craft_id else None, str(name).strip(),
                  str(effect or ""), json.dumps(details or {}, ensure_ascii=False), int(quantity), now_iso()))
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


def update_requisition_item(rid, name, effect, details, quantity=1):
    """The Magister may tidy up a Player's custom item before approving it."""
    stackable, _ = _infer_stackable_gear(name, details or {})
    quantity = max(1, int(quantity or 1)) if stackable else 1
    conn = get_conn()
    conn.execute("UPDATE wargear_requisition SET name=?, effect=?, details=?, quantity=? WHERE id=? AND status='pending'",
                 (str(name).strip(), str(effect or ""), json.dumps(details or {}, ensure_ascii=False), int(quantity), int(rid)))
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
    quantity = max(1, int(row["quantity"]) if "quantity" in row.keys() and row["quantity"] else 1)
    result_msg = "Requisition approved and added to the character's Wargear."
    if quantity > 1:
        ok2, msg2 = adjust_wargear_quantity(cid, craft_id, quantity - 1, actor_name=actor_name,
                                             source="Requisition Approved", actor_role="gm")
        result_msg = (f"Requisition approved: {quantity}x added to the character's Wargear." if ok2
                       else f"Approved 1 unit, but could not add the remaining {quantity - 1}: {msg2}")
    conn = get_conn()
    conn.execute("UPDATE wargear_requisition SET status='approved', source_craft_id=?, resolved_at=?, resolved_by=? WHERE id=?",
                 (int(craft_id), now_iso(), actor_name, int(rid)))
    conn.commit(); conn.close()
    return True, result_msg


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
        sql = "SELECT * FROM craft_items WHERE kind=?" + (" AND active=1" if active_only else "") + " ORDER BY LOWER(name)"
        rows = conn.execute(sql, (kind,)).fetchall()
    else:
        sql = "SELECT * FROM craft_items" + (" WHERE active=1" if active_only else "") + " ORDER BY kind, LOWER(name)"
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


_ATTR_ABBREV = {"Strength": "S"}  # the book's own convention (p.183: melee Damage adds Strength);
                                   # any other Attribute (homebrew items) falls back to 3 letters.


def _attr_abbrev(attr):
    return _ATTR_ABBREV.get(attr, str(attr)[:3].upper())


def _weapon_base_damage(details, attrs):
    """Resolve only the weapon's base Damage value.

    W&G stores Damage, ED and AP separately.  Older catalog entries may still
    contain text such as ``(S) +5`` or ``10 +1 ED``.  Never concatenate every
    digit in that text: ``10 +1 ED`` must resolve to 10, not 101.
    """
    details = details or {}
    attrs = attrs or {}
    text = str(details.get("damage") or "").strip()
    attr_name = str(details.get("damage_attribute") or "").strip()

    # Legacy / free-text Attribute + Damage formats:
    # (S) +5, (S)+5, S+5, Strength + 5
    if not attr_name:
        m = re.match(r"^\s*\(?\s*([A-Za-z]+)\s*\)?\s*\+\s*(-?\d+)", text, re.I)
        if m:
            token = m.group(1).strip().lower()
            attr_name = next(
                (a for a in ATTRS if token == a.lower() or token == _attr_abbrev(a).lower()),
                "",
            )

    if attr_name:
        # For structured entries the first signed integer is the flat Damage
        # component.  ED is stored separately and must never become damage.
        m = re.search(r"[-+]?\s*(\d+)", text)
        flat = int(m.group(1)) if m else 0
        if "-" in m.group(0) if m else False:
            flat = -flat
        return int(attrs.get(attr_name, 0) or 0) + flat

    # Plain/ranged Damage.  Read the FIRST numeric value only.
    # Example: "10 +1 ED" -> 10, never 101.
    m = re.search(r"[-+]?\s*\d+", text)
    if not m:
        return 0
    try:
        return int(re.sub(r"\s+", "", m.group(0)))
    except ValueError:
        return 0


def _wargear_stat_html(details, extra_style="", attrs=None):
    """Render a Wargear item's combat profile the way the Core Rulebook's
    weapon tables present it (p.217+): Damage, ED and AP as separate labelled
    values in that order, AP shown as '-' when 0 rather than a bare zero
    (matching the book's own table convention) instead of the single
    combined 'Damage: 10 +1 ED' string this used to collapse them into.

    Actual dice are rolled in Owlbear Rodeo, not here (see battle_view). When
    `attrs` is given (a specific character's current effective Attributes,
    not just the catalog entry) and the weapon adds an Attribute to its
    Damage (the Craft editor's Attribute selector, or the legacy '(S) +N'
    text for items registered before that field existed), a second line
    spells out the resolved number below the book formula, so nobody has to
    do the Attribute + weapon bonus arithmetic by hand at the table."""
    parts = []
    dmg_text = details.get("damage")
    resolved_line = ""
    if dmg_text not in (None, ""):
        parts.append(f"<b>{T('Damage')}</b> {html.escape(str(dmg_text))}")
        attr_name = str(details.get("damage_attribute") or "").strip()
        if not attr_name and str(dmg_text).strip().upper().startswith("(S)"):
            attr_name = "Strength"
        if attrs is not None and attr_name:
            total = _weapon_base_damage(details, attrs)
            attr_val = int(attrs.get(attr_name, 0) or 0)
            resolved_line = (f"<div style='margin-top:2px;opacity:.7;font-size:.72rem'>"
                              f"= <b>{total}</b> ({T(attr_name)} {attr_val} {str(dmg_text).strip().split(')', 1)[-1].strip()})"
                              f"</div>")
    if details.get("ed") not in (None, "", 0):
        parts.append(f"<b>ED</b> {html.escape(str(details['ed']))}")
    if details.get("ap") not in (None, ""):
        try: ap_val = int(details.get("ap") or 0)
        except (TypeError, ValueError): ap_val = 0
        parts.append(f"<b>AP</b> {ap_val if ap_val else '–'}")
    if details.get("range") not in (None, ""):
        parts.append(f"<b>{T('Range')}</b> {html.escape(str(details['range']))}")
    if details.get("salvo") not in (None, ""):
        parts.append(f"<b>Salvo</b> {html.escape(str(details['salvo']))}")
    traits = details.get("traits")
    if traits:
        if isinstance(traits, str): traits = _req_list(traits)
        traits = [str(x) for x in traits if str(x).strip()]
        if traits:
            parts.append(f"<b>{T('Traits')}</b> {html.escape(', '.join(traits))}")
    if not parts:
        return ""
    joined = "".join(f"<span style='margin-right:12px'>{p}</span>" for p in parts)
    return f"<div style='margin-top:5px;opacity:.85;font-size:.78rem;{extra_style}'>{joined}{resolved_line}</div>"


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
    if kind == "wargear":
        stat_html = _wargear_stat_html(details)
        if stat_html: body.append(stat_html)
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
    try:
        raw_cond = ch.get("conditions") or "{}"
        ch["conditions"] = json.loads(raw_cond) if isinstance(raw_cond, str) else raw_cond
        if not isinstance(ch["conditions"], dict): ch["conditions"] = {}
    except Exception:
        ch["conditions"] = {}
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


def list_characters(kind=None, include_pending=False):
    conn = get_conn()
    clauses, args = [], []
    if kind:
        clauses.append("kind=?"); args.append(kind)
    if not include_pending:
        # Self-registered characters awaiting the Magister's review are not
        # "in the game" yet: they stay off the roster, Combat, and Vox until
        # approved (see list_pending_registrations/approve_registration).
        clauses.append("approval_status != 'pending'")
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(f"SELECT * FROM characters{where} ORDER BY name", args).fetchall()
    conn.close(); return [_decode(r) for r in rows]


def list_pending_registrations():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM characters WHERE approval_status='pending' ORDER BY name").fetchall()
    conn.close(); return [_decode(r) for r in rows]


def approve_registration(cid):
    conn = get_conn()
    conn.execute("UPDATE characters SET approval_status='approved', updated_at=? WHERE id=?", (now_iso(), int(cid)))
    conn.commit(); conn.close()
    return True, "Registration approved. The character is now in the game."


def reject_registration(cid):
    """Rejecting a self-registration deletes both the character and its
    account immediately - there is no character sheet to keep, since it was
    never approved into the game."""
    conn = get_conn()
    row = conn.execute("SELECT user_id FROM characters WHERE id=?", (int(cid),)).fetchone()
    if not row:
        conn.close(); return False, "Character not found."
    conn.execute("DELETE FROM characters WHERE id=?", (int(cid),))
    if row["user_id"]:
        conn.execute("DELETE FROM users WHERE id=?", (int(row["user_id"]),))
    conn.commit(); conn.close()
    return True, "Registration rejected and deleted."


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
    # from your previous Archetype" · so the new Archetype's starting Wargear
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


def set_condition(cid, name, stacks):
    """Add/update/remove one Condition marker on a character (p.199-200).
    stacks<=0 removes it entirely; any name is accepted so a Wargear-granted
    activatable status (e.g. Cameleoline) can be tracked the same way as a
    Core Rulebook Condition like Bleeding."""
    name = str(name or "").strip()
    if not name:
        return False, "Condition name is required."
    conn = get_conn()
    row = conn.execute("SELECT conditions, revision FROM characters WHERE id=?", (int(cid),)).fetchone()
    if not row:
        conn.close(); return False, "Character not found."
    try:
        current = json.loads(row["conditions"] or "{}")
        if not isinstance(current, dict): current = {}
    except Exception:
        current = {}
    stacks = int(stacks)
    if stacks <= 0:
        current.pop(name, None)
    else:
        current[name] = stacks
    conn.execute("UPDATE characters SET conditions=?, updated_at=?, revision=revision+1 WHERE id=?",
                 (json.dumps(current, ensure_ascii=False), now_iso(), int(cid)))
    conn.commit(); conn.close()
    return True, "Condition updated."



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
    c.setdefault("owlbear_enabled", 0)
    return c


def set_owlbear_enabled(enabled):
    conn = get_conn()
    conn.execute("UPDATE campaign SET owlbear_enabled=? WHERE id=1", (1 if enabled else 0,))
    conn.commit(); conn.close()


def create_owlbear_roll_request(cid, character_name, label, base_pool, bonus_dice=0, kind="test"):
    """Queue a roll for the Owlbear Rodeo extension to actually perform inside
    the room (experimental, see the Campaign tab toggle). This app never rolls
    the dice itself for this path - it just hands off the formula.

    `bonus_dice` is a player-entered adjustment (Talents/Abilities granting
    "+Rank bonus dice", cover penalties, etc. are not on the sheet as a fixed
    number, so this is filled in per-roll) added to (or, if negative,
    subtracted from) the character's base pool - Wrath & Glory's bonuses are
    always extra/fewer dice, never a flat +N to the total (p.161).

    `kind` tells the extension how to interpret the dice: every Attribute/
    Skill Test ('test' - Attack Tests included) always includes a Wrath Die
    (p.158), while a Damage/ED roll ('damage') does not (p.184)."""
    base_pool = int(base_pool)
    bonus_dice = int(bonus_dice)
    dice_count = max(0, base_pool + bonus_dice)
    kind = kind if kind in ("test", "damage") else "test"
    formula = f"{dice_count}d6"
    label_full = str(label or "")
    if bonus_dice:
        label_full += f" ({bonus_dice:+d} dice)"
    conn = get_conn()
    conn.execute("""INSERT INTO owlbear_roll_request(character_id,character_name,label,kind,formula,dice_count,modifier,status,requested_at)
                    VALUES(?,?,?,?,?,?,?,'pending',?)""",
                 (int(cid), str(character_name or ""), label_full, kind, formula, dice_count, bonus_dice, now_iso()))
    conn.commit(); conn.close()
    return True, f"Roll request sent to Owlbear: {formula}"


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
            """INSERT INTO session_award(session_id,character_id,base_xp,bonus_xp,total_xp) VALUES(?,?,?,?,?)
               ON CONFLICT(session_id,character_id) DO UPDATE SET
                   base_xp=excluded.base_xp, bonus_xp=excluded.bonus_xp, total_xp=excluded.total_xp""",
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
    conn.execute("""INSERT INTO combat_participant(encounter_id,character_id,side,initiative_mod,ambushed,added_at)
                    VALUES(?,?,?,?,?,?)
                    ON CONFLICT(encounter_id,character_id) DO NOTHING""", (eid, int(character_id), ch["kind"], int(initiative_mod), 1 if ambushed else 0, now_iso()))
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

    /* Terminal Select screen: choice between the Cogitador (campaign
       manager) and Wrath Incursion (solo roguelike), both inside this same
       app but kept deliberately separate experiences end to end. */
    .mode-card{ text-align:center; padding:26px 16px; border-radius:6px; border:1px solid #4a3a20;
        background:linear-gradient(160deg,var(--panel2),#140f09); margin-bottom:10px; }
    .mode-card .mt{ font-family:'Cinzel',serif; letter-spacing:.1em; text-transform:uppercase;
        font-size:1.15rem; color:var(--gold2); }
    .mode-card .ms{ font-size:.76rem; color:var(--bone); opacity:.75; margin-top:6px; line-height:1.5; }
    .mode-card.system{ border-color:var(--gold); }
    .mode-card.incursion{ border-color:var(--blood2); background:linear-gradient(160deg,#241212,#140909); }
    .mode-card.incursion .mt{ color:#e8a0a0; }

    /* ============================================================
       WRATH INCURSION · solo roguelike, deliberately a different visual
       register from the Cogitador (colder, redder, more feral) so the two
       "terminals" never feel like the same screen.
       ============================================================ */
    .inc-banner{ text-align:center; font-family:'Cinzel',serif; font-weight:900; font-size:1.8rem;
        color:#e8a0a0; letter-spacing:.16em; padding:10px 0 4px; border-bottom:2px solid var(--blood2); }
    .inc-banner .sub{ display:block; font-size:.7rem; letter-spacing:.28em; color:var(--bone); opacity:.7;
        text-transform:uppercase; margin-top:3px; }
    .inc-hud{ display:flex; flex-wrap:wrap; gap:8px; margin:10px 0 16px; }
    .inc-chip{ background:var(--panel2); border:1px solid #4a3a20; border-left:3px solid var(--blood2);
        border-radius:3px; padding:6px 12px; font-size:.72rem; color:var(--bone); opacity:.85; }
    .inc-chip b{ display:block; color:#e8a0a0; font-family:'Cinzel',serif; font-size:1.05rem; }
    .inc-track{ display:flex; gap:4px; overflow-x:auto; margin-bottom:14px; padding-bottom:4px; }
    .inc-stage{ flex:0 0 auto; padding:4px 10px; border-radius:3px; font-size:.66rem; letter-spacing:.05em;
        text-transform:uppercase; background:var(--panel2); border:1px solid #3a2e18; color:var(--bone); opacity:.55; white-space:nowrap; }
    .inc-stage.now{ border-color:var(--blood2); opacity:1; color:#fff; background:linear-gradient(var(--blood),var(--blood2)); }
    
/* INCURSION THEATRE - kept deliberately compact: this header renders above
   every Incursion screen, so its height directly decides whether the
   actual controls below need a scroll to reach. */
    .incursion-frame{position:relative;margin:0 0 8px;padding:8px 14px 6px;background:radial-gradient(circle at 50% 0%,rgba(122,20,20,.18),transparent 48%),linear-gradient(180deg,rgba(20,14,10,.98),rgba(8,7,6,.98));border:1px solid #5d4828;border-top:2px solid #8f6b32;box-shadow:inset 0 0 35px rgba(0,0,0,.65),0 8px 28px rgba(0,0,0,.32)}
    .incursion-frame:before,.incursion-frame:after{content:"";display:block;height:1px;background:linear-gradient(90deg,transparent,#76582b,transparent);margin:0 12% 4px}
    .inc-banner{position:relative;text-align:center;font-family:Cinzel,serif;font-weight:900;font-size:1.2rem;color:#e8d7ad;letter-spacing:.18em;padding:2px 0 4px;border:0;text-shadow:0 0 18px rgba(200,150,60,.18)}
    .inc-banner:after{display:none}
    .inc-banner .sub{display:block;font-size:.56rem;letter-spacing:.24em;color:#a99672;text-transform:uppercase;margin-top:2px}
    .inc-command-line{display:none}
    .inc-command-line b{color:#c9ad70;font-weight:700}.inc-command-line .live{color:#b84b42}
    .inc-hud{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:5px;margin:6px 0 8px}
    .inc-shock-action{border:1px solid rgba(155,114,194,.45);background:linear-gradient(90deg,rgba(55,31,75,.42),rgba(16,11,22,.7));padding:5px 8px;margin:5px 0;font-size:.62rem;letter-spacing:.06em;text-transform:uppercase}.inc-shock-action span{display:block;color:#b89bd0;font-size:.52rem}.inc-shock-action b{display:block;color:#e0d1e8;margin-top:1px}.inc-shock-action small{display:block;color:#9d8da7;margin-top:1px;text-transform:none;letter-spacing:.02em}.inc-player-vitals{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin:6px 0 6px}
    /* Compact on purpose: this HUD renders above every screen in the
       Incursion, so a player never has to scroll past it just to reach the
       actual choice/shop/combat buttons below - see the "screen must fit
       without scrolling" request. */
    .inc-player-vital{position:relative;overflow:hidden;min-height:36px;padding:4px 7px;border:1px solid #403323;background:#0d0b09;box-shadow:inset 0 0 12px var(--pv-glow)}
    .inc-player-vital:before{content:"";position:absolute;inset:0;background:linear-gradient(90deg,var(--pv-color) 0%,var(--pv-color) var(--pv-pct),transparent var(--pv-pct),transparent 100%);opacity:.28;transition:all .25s ease}
    .inc-player-vital>*{position:relative;z-index:1}
    .inc-player-vital b{display:block;font:700 .82rem Cinzel,serif;color:#e4d5b0;line-height:1.1}
    .inc-player-vital .pv-label{display:block;margin-top:1px;font:7px monospace;letter-spacing:.1em;color:#8f8065}
    .inc-player-vital.wounds{--pv-color:hsl(145,62%,42%);--pv-glow:rgba(55,170,95,.3)}
    .inc-player-vital.armour{--pv-color:#b58b3a;--pv-glow:rgba(181,139,58,.28)}
.inc-player-vital.shock{--pv-color:#9b72c2;--pv-glow:rgba(150,105,205,.3)}
    .inc-player-vital.wounds .pv-label{color:#8bcf9b}.inc-player-vital.shock .pv-label{color:#c6a7df}
    .inc-chip{position:relative;background:linear-gradient(180deg,#17120d,#0f0c09);border:1px solid #493a25;border-radius:0;border-top:2px solid #5f4725;padding:4px 7px;font-size:.55rem;color:#8f8065;opacity:1;text-transform:uppercase;letter-spacing:.06em}
    .inc-chip:after{content:"";position:absolute;left:0;bottom:0;width:25%;height:1px;background:#8a2d27}.inc-chip b{display:block;color:#ded0ad;font-family:Cinzel,serif;font-size:.86rem;letter-spacing:.02em;line-height:1.1}.inc-chip.wound b{color:#c95a50}.inc-chip.shock b{color:#c6a45c}.inc-chip.wrath b{color:#dfc278}
    .inc-track{display:grid;grid-template-columns:repeat(7,1fr);gap:2px;overflow:hidden;margin:0 0 8px;padding:0}.inc-stage{position:relative;text-align:center;padding:3px 4px;border-radius:0;font-size:.5rem;letter-spacing:.06em;text-transform:uppercase;background:#100d09;border:1px solid #322719;color:#665941;white-space:nowrap;opacity:.72}.inc-stage.now{border-color:#8c642a;opacity:1;color:#ead7a8;background:linear-gradient(180deg,#322317,#17110b);box-shadow:inset 0 -2px 0 #9b2d27}.inc-stage.now span{display:none}.inc-stage.now:before{content:"NOW";display:block;font-size:.4rem;color:#b64a40;letter-spacing:.1em;margin-bottom:1px}
    .inc-card{position:relative;border:1px solid #473822;border-radius:0;background:linear-gradient(180deg,rgba(22,17,12,.97),rgba(12,10,8,.97));padding:12px 14px;margin-bottom:8px;box-shadow:inset 0 0 25px rgba(0,0,0,.32)}.inc-card:before{content:"";position:absolute;top:-1px;left:12px;right:12px;height:1px;background:linear-gradient(90deg,transparent,#74552a,transparent)}
    .inc-title{font-family:Cinzel,serif;color:#d8c18a;text-transform:uppercase;letter-spacing:.12em;font-size:.88rem;margin:0 0 4px}.inc-flavor{color:#b4a78d;opacity:.78;font-size:.74rem;line-height:1.45;margin-bottom:6px}
    /* Shop/loot offer cards - border and name colour shift by rarity so a
       Legendary or Unique item/talent/power reads as such at a glance. */
    .inc-offer{position:relative;border:1px solid #473822;border-radius:0;background:linear-gradient(180deg,rgba(22,17,12,.97),rgba(12,10,8,.97));padding:10px 12px;margin-bottom:8px}
    .inc-offer .ot{font:9px monospace;letter-spacing:.14em;text-transform:uppercase;color:#8f8065}
    .inc-offer .on{font:700 .92rem Cinzel,serif;color:#d8c18a;margin:3px 0;text-transform:uppercase;letter-spacing:.03em}
    .inc-offer .od{font-size:.74rem;color:#b4a78d;opacity:.85;line-height:1.42;margin-bottom:6px}
    .inc-offer .oc{font:700 .8rem Cinzel,serif;color:#e8c96a}
    .inc-offer.rarity-common{border-color:#5a5245}
    .inc-offer.rarity-uncommon{border-color:#4c9a5b;box-shadow:0 0 10px rgba(76,154,91,.18)}
    .inc-offer.rarity-uncommon .on{color:#8fd98f}
    .inc-offer.rarity-rare{border-color:#3d78c9;box-shadow:0 0 10px rgba(61,120,201,.22)}
    .inc-offer.rarity-rare .on{color:#8fc0ff}
    .inc-offer.rarity-legendary{border-color:#c9922e;box-shadow:0 0 14px rgba(201,146,46,.3)}
    .inc-offer.rarity-legendary .on{color:#ffcf6b}
    .inc-offer.rarity-unique{border-color:#b23ad0;box-shadow:0 0 16px rgba(178,58,208,.35)}
    .inc-offer.rarity-unique .on{color:#e6a3ff}
    /* Weapon tiles in combat: pressed, not opened from a dropdown - the
       active one stays visibly highlighted, and melee vs ranged has a
       distinct icon so the two are never confused at a glance. */
    .inc-weapon-tile{border:1px solid #473822;background:linear-gradient(180deg,rgba(22,17,12,.97),rgba(12,10,8,.97));padding:8px;text-align:center;margin-bottom:4px}
    .inc-weapon-tile.active{border-color:#c9922e;box-shadow:0 0 12px rgba(201,146,46,.35);background:linear-gradient(180deg,rgba(40,30,14,.97),rgba(18,13,8,.97))}
    .inc-weapon-tile .wt-icon{font-size:1.3rem;line-height:1.1}
    .inc-weapon-tile .wt-name{font:700 .78rem Cinzel,serif;color:#d8c18a;text-transform:uppercase;margin:2px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .inc-weapon-tile.active .wt-name{color:#ffcf6b}
    .inc-weapon-tile .wt-stats{font:9px monospace;color:#8f8065}
    /* Rarity-coloured backpack tiles - same palette as shop offers so an
       item's rarity reads the same everywhere it appears. */
    .inc-backpack-title{font-family:Cinzel,serif;color:#cdb77f;letter-spacing:.14em;font-size:.72rem;text-align:center;margin-bottom:8px;text-transform:uppercase}
    .inc-pack-item{position:relative;border:1px solid #473822;background:linear-gradient(180deg,rgba(22,17,12,.97),rgba(12,10,8,.97));padding:6px 8px;margin-bottom:5px;display:flex;align-items:center;gap:6px}
    .inc-pack-item .pack-icon{font-size:1rem}
    .inc-pack-item .pack-name{flex:1;font:700 .74rem Cinzel,serif;color:#d8c18a;text-transform:uppercase;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .inc-pack-item .pack-sub{font:8px monospace;color:#8f8065;white-space:nowrap}
    .inc-pack-item.rarity-uncommon{border-color:#4c9a5b}.inc-pack-item.rarity-uncommon .pack-name{color:#8fd98f}
    .inc-pack-item.rarity-rare{border-color:#3d78c9}.inc-pack-item.rarity-rare .pack-name{color:#8fc0ff}
    .inc-pack-item.rarity-legendary{border-color:#c9922e;box-shadow:0 0 10px rgba(201,146,46,.25)}.inc-pack-item.rarity-legendary .pack-name{color:#ffcf6b}
    .inc-pack-item.rarity-unique{border-color:#b23ad0;box-shadow:0 0 12px rgba(178,58,208,.3)}.inc-pack-item.rarity-unique .pack-name{color:#e6a3ff}
    .inc-pack-item.equipped{border-left:3px solid #6fae7a}
    /* Minion combat cards reuse .inc-enemy's layout, coloured by rarity -
       same palette as the shop/backpack tiles so a Minion's rarity reads
       the same everywhere it appears. */
    .inc-enemy.rarity-uncommon{border-color:#4c9a5b}
    .inc-enemy.rarity-rare{border-color:#3d78c9}
    .inc-enemy.rarity-legendary{border-color:#c9922e;box-shadow:0 0 14px rgba(201,146,46,.25)}
    .inc-enemy.rarity-unique{border-color:#b23ad0;box-shadow:0 0 16px rgba(178,58,208,.3)}
    .inc-enemy{position:relative;border:1px solid #3a2e18;border-radius:0;padding:13px;background:#11100d;min-height:160px;overflow:hidden;transition:transform .15s ease,border-color .15s ease,box-shadow .15s ease}.inc-enemy:after{content:"";position:absolute;right:-28px;bottom:-28px;width:90px;height:90px;border:1px solid rgba(190,160,90,.12);transform:rotate(45deg);pointer-events:none}.inc-enemy.selected{transform:translateY(-2px);border-color:#c64a3d;box-shadow:0 0 0 1px rgba(198,74,61,.25),0 0 24px rgba(120,20,15,.18)}.inc-enemy.selected:before{content:"TARGET LOCK";position:absolute;right:8px;top:7px;font:9px monospace;letter-spacing:.13em;color:#d96a5d}.inc-enemy.dead{opacity:.3;filter:grayscale(1)}.inc-enemy .en{position:relative;z-index:1;font-family:Cinzel,serif;font-weight:700;font-size:.9rem;color:#ded0ad;letter-spacing:.06em;text-transform:uppercase}.inc-enemy .et{position:relative;z-index:1;font-size:.61rem;color:#89785d;opacity:.9;text-transform:uppercase;margin:3px 0 8px;letter-spacing:.08em}.inc-npc-vitals{position:relative;z-index:1;display:grid;grid-template-columns:repeat(3,1fr);gap:5px;margin:8px 0}.inc-npc-vitals span{border:1px solid #2e2418;padding:6px 5px;text-align:center;font-size:.56rem;color:#766750;text-transform:uppercase}.inc-npc-vitals b{display:block;color:#c9b98f;font:700 .82rem Cinzel,serif}.inc-vital{position:relative;overflow:hidden;box-shadow:inset 0 0 18px var(--vital-glow)}.inc-vital:before{content:"";position:absolute;inset:0;z-index:0;background:linear-gradient(90deg,var(--vital-color) 0%,var(--vital-color) var(--vital-pct),transparent var(--vital-pct),transparent 100%);opacity:.22}.inc-vital>*{position:relative;z-index:1}.inc-vital.wounds{--vital-glow:rgba(55,170,95,.30);--vital-color:hsl(calc(120 * var(--vital-pct-num)),72%,42%)}.inc-vital.shock{--vital-glow:rgba(150,105,205,.30);--vital-color:#9b72c2}.inc-vital-label{display:block;margin-top:2px;font-size:.52rem;letter-spacing:.12em}.inc-vital.wounds .inc-vital-label{color:#8bcf9b}.inc-vital.shock .inc-vital-label{color:#c6a7df}.inc-npc-def{position:relative;z-index:1;font:10px monospace;color:#827157;letter-spacing:.05em;border-top:1px solid #292016;padding-top:7px}.inc-enemy.enemy-v0{background:linear-gradient(155deg,#101715 0%,#0b0d0c 55%,#101812 100%);border-left:4px solid #5d8b73}.inc-enemy.enemy-v0 .inc-enemy-strip{color:#79a88f;border-bottom-color:#294238}.inc-enemy.enemy-v0 .en{color:#b9d4c4}.inc-enemy.enemy-v1{background:linear-gradient(155deg,#18130c 0%,#0e0b08 58%,#191208 100%);border-left:4px solid #b08a45}.inc-enemy.enemy-v1 .inc-enemy-strip{color:#c7a662;border-bottom-color:#4c3a1f}.inc-enemy.enemy-v1 .en{color:#e0c994}.inc-enemy.enemy-v2{background:linear-gradient(155deg,#190d0d 0%,#0e0909 58%,#1a0d0c 100%);border-left:4px solid #a7473d}.inc-enemy.enemy-v2 .inc-enemy-strip{color:#d06a60;border-bottom-color:#54231f}.inc-enemy.enemy-v2 .en{color:#e1aaa4}.inc-enemy.enemy-v3{background:linear-gradient(155deg,#16101b 0%,#0b0910 58%,#17101d 100%);border-left:4px solid #8760a8}.inc-enemy.enemy-v3 .inc-enemy-strip{color:#a985c1;border-bottom-color:#3c2849}.inc-enemy.enemy-v3 .en{color:#ceb9d9}.inc-enemy.enemy-v0 .inc-npc-vitals span{border-color:#294238}.inc-enemy.enemy-v1 .inc-npc-vitals span{border-color:#4c3a1f}.inc-enemy.enemy-v2 .inc-npc-vitals span{border-color:#54231f}.inc-enemy.enemy-v3 .inc-npc-vitals span{border-color:#3c2849}
    .inc-log{max-height:280px;overflow-y:auto;background:#090807;border:1px solid #332719;border-radius:0;padding:10px;margin-bottom:14px;display:flex;flex-direction:column-reverse;gap:4px}.inc-log-line{font-size:.7rem;padding:6px 8px;border-radius:0;border-left:2px solid transparent;font-family:monospace}.inc-log-line.player{background:rgba(70,82,72,.1);border-left-color:#8c7546}.inc-log-line.enemy{background:rgba(120,20,20,.09);border-left-color:#87322c}.inc-log-line.system{text-align:center;font-style:italic;color:#9b8455;border-left:none}
    .inc-banner-win{font-family:Cinzel,serif;text-align:center;padding:14px;border-radius:0;margin-bottom:14px;letter-spacing:.15em;text-transform:uppercase;background:linear-gradient(90deg,rgba(80,60,20,.08),rgba(201,162,39,.16),rgba(80,60,20,.08));border:1px solid #8a6b32;color:#ddc581}.inc-banner-lose{font-family:Cinzel,serif;text-align:center;padding:14px;border-radius:0;margin-bottom:14px;letter-spacing:.15em;text-transform:uppercase;background:rgba(100,15,15,.13);border:1px solid #7d302b;color:#d87870}
    .inc-action-title{font-family:Cinzel,serif;color:#cdb77f;letter-spacing:.2em;font-size:.72rem;text-align:center;margin-bottom:8px;text-transform:uppercase}.inc-status-blood{color:#d65a52;font-weight:700;text-transform:uppercase;letter-spacing:.05em}.inc-talent-reaction{border:1px solid #6f2d28;background:linear-gradient(135deg,#190b0b,#0d0808);padding:16px;margin:12px 0;box-shadow:0 0 22px rgba(120,0,0,.18)}
    .inc-talent-card{border-left:2px solid #77633c;background:#14100b;padding:9px 12px;margin:6px 0;border-radius:0}.inc-talent-card.active{border-left-color:#b23a35}.inc-talent-card.passive{border-left-color:#3e7f5a}.inc-talent-card.manual{border-left-color:#6d5a39;opacity:.7}.inc-talent-card span{display:block;font-size:.72rem;opacity:.72;margin-top:3px;line-height:1.45}.inc-chip small{display:block;font-size:.49rem;letter-spacing:.14em;opacity:.72;margin-top:3px}.inc-enemy{transition:transform .15s ease,border-color .15s ease;min-height:176px;border:1px solid #3a2d1d;box-sizing:border-box}.inc-enemy:hover{transform:translateY(-2px);border-color:#80602c}.inc-enemy-strip{display:flex;justify-content:space-between;border-bottom:1px solid #2d2418;padding-bottom:6px;margin-bottom:9px;font:9px monospace;letter-spacing:.12em;color:#75654c}.inc-enemy.tier-1{border-top:3px solid #59604b}.inc-enemy.tier-2{border-top:3px solid #827044}.inc-enemy.tier-3{border-top:3px solid #9b4b39}.inc-enemy.tier-4{border-top:3px solid #b6a05e;box-shadow:0 0 18px rgba(180,150,70,.08)}.inc-enemy.selected{border:1px solid #c34b3e;box-shadow:0 0 0 1px rgba(195,75,62,.22),0 0 16px rgba(160,40,30,.14);background:linear-gradient(180deg,#21100d,#100b08)}.inc-enemy-status{position:relative;z-index:2;min-height:16px;margin-top:8px}.inc-vox{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:7px;width:100%;box-sizing:border-box;margin:10px 0 0;padding:6px 8px;border:1px solid #4b3a25;background:linear-gradient(90deg,rgba(20,16,10,.92),rgba(7,7,6,.96),rgba(20,16,10,.92));box-shadow:inset 0 0 12px rgba(0,0,0,.55),0 0 8px rgba(0,0,0,.18)}.vox-label,.vox-state{font:7px monospace;letter-spacing:.12em;color:#75664c}.vox-wave{height:16px;display:flex;align-items:center;justify-content:center;gap:2px;overflow:hidden}.vox-wave i{display:block;width:2px;height:4px;background:#8d7650;opacity:.8;animation:incvox 1.05s ease-in-out infinite}.vox-wave i:nth-child(2){animation-delay:.08s}.vox-wave i:nth-child(3){animation-delay:.16s}.vox-wave i:nth-child(4){animation-delay:.24s}.vox-wave i:nth-child(5){animation-delay:.32s}.vox-wave i:nth-child(6){animation-delay:.40s}.vox-wave i:nth-child(7){animation-delay:.48s}.inc-enemy.selected .vox-wave i{background:#c65b50}.inc-enemy.selected .vox-state{color:#c65b50}.inc-enemy.enemy-v1 .vox-wave i{background:#c7a662}.inc-enemy.enemy-v2 .vox-wave i{background:#c65b50}.inc-enemy.enemy-v3 .vox-wave i{background:#a985c1}@keyframes incvox{0%,100%{height:3px;opacity:.35}20%{height:9px;opacity:.7}40%{height:15px;opacity:1}60%{height:7px;opacity:.75}80%{height:12px;opacity:.9}}
.inc-wrath-spend{border:1px solid #604d28;background:linear-gradient(180deg,#1d170d,#0e0b07);padding:5px;text-align:center;min-height:44px}.inc-wrath-spend span{display:block;font:8px monospace;letter-spacing:.12em;color:#8b7650}.inc-wrath-spend b{font:700 1.15rem Cinzel,serif;color:#e7c66c}.inc-wrath-spend small{font:8px monospace;color:#756044;margin-left:5px}.inc-wrath-spend+*{}
    @media (max-width:900px){.inc-hud{grid-template-columns:repeat(4,1fr)}.inc-track{grid-template-columns:repeat(4,1fr)}}@media (max-width:600px){.inc-hud{grid-template-columns:repeat(2,1fr)}.inc-track{display:flex;overflow-x:auto}.inc-stage{flex:0 0 120px}.inc-banner{font-size:1.35rem;letter-spacing:.13em}.inc-command-line{font-size:8px}}
    /* Everything-fits-without-scrolling pass for the Incursion screens: the
       cards themselves were already tight, but Streamlit's own per-element
       vertical gaps (~1rem each, stacked across HUD/header/dice tray/enemy
       row/action panel) were the real height cost. Scoped via :has() to the
       .incursion-frame marker div so the campaign-manager pages are untouched. */
    .block-container:has(.incursion-frame){padding-top:.5rem !important;padding-bottom:.5rem !important;max-width:80% !important}
    header[data-testid="stHeader"]:has(~ div .incursion-frame){height:0;min-height:0}
    .block-container:has(.incursion-frame) [data-testid="stVerticalBlock"]{gap:.3rem !important}
    .block-container:has(.incursion-frame) [data-testid="stVerticalBlockBorderWrapper"]{padding:.4rem .6rem !important}
    .block-container:has(.incursion-frame) [data-testid="stHorizontalBlock"]{gap:.4rem !important;align-items:end}
    .block-container:has(.incursion-frame) .stRadio{margin:0 !important}
    .block-container:has(.incursion-frame) .stRadio>div{gap:.5rem !important}
    .block-container:has(.incursion-frame) .stButton>button{padding:.3rem .6rem !important;min-height:0 !important}
    .block-container:has(.incursion-frame) .stSelectbox{margin-bottom:0 !important}
    .block-container:has(.incursion-frame) .stCaption{margin:0 !important}
    .block-container:has(.incursion-frame) hr{margin:.3rem 0 !important}
    .block-container:has(.incursion-frame) .inc-enemy{min-height:0;padding:8px}
    .block-container:has(.incursion-frame) .inc-npc-vitals{margin:5px 0}
    .block-container:has(.incursion-frame) .inc-npc-vitals span{padding:3px 4px}

    .inc-mini-readout{height:100%;min-height:42px;border:1px solid #3c2d1a;background:#0e0b08;text-align:center;padding:6px}.inc-mini-readout b{display:block;font:700 1.05rem Cinzel,serif;color:#d8c18a}.inc-mini-readout span{font:9px monospace;color:#7f6d50;letter-spacing:.12em}.inc-live-panel{border:1px solid #72582c;background:linear-gradient(180deg,#17120d,#0c0907);padding:18px;text-align:center;margin:10px 0}.inc-duel-stat{display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px;border:1px solid #493821;padding:9px;background:#100c08}.inc-duel-stat b{font:700 1.05rem Cinzel,serif;color:#dfc278;text-align:center}.inc-duel-stat span{font:9px monospace;color:#77654a;text-align:center}.inc-duel-stat.enemy{border-color:#63302b}.inc-wait-turn{text-align:center;border:1px solid #493821;padding:14px;color:#9c8760;font:10px monospace;letter-spacing:.12em;margin:10px 0}.inc-rank-panel{border:1px solid #493821;background:#0d0a07;margin-top:10px}.inc-rank-head,.inc-rank-row{display:grid;grid-template-columns:55px 1fr 90px;align-items:center;gap:10px;padding:9px 12px}.inc-rank-head{font:9px monospace;letter-spacing:.14em;color:#786648;border-bottom:1px solid #302418}.inc-rank-row{border-bottom:1px solid #241b11}.inc-rank-row:last-child{border-bottom:0}.inc-rank-pos{font:700 .8rem Cinzel,serif;color:#b99b5a}.inc-rank-name{font:700 .78rem Cinzel,serif;color:#d8c18a;text-transform:uppercase}.inc-rank-name small{display:block;font:9px monospace;color:#75664e;margin-top:2px;text-transform:none}.inc-rank-xp{text-align:right;font:700 .82rem Cinzel,serif;color:#dfc278}.inc-rank-empty{text-align:center;padding:18px;font:10px monospace;color:#75664e;letter-spacing:.1em}.inc-rank-panel + *{margin-top:8px}
    /*     SPECTATOR VOX-FEED · deliberately the most theatrical page in the
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

    .inq-nav-title{font-family:Cinzel,serif;color:var(--gold2);letter-spacing:.14em;font-size:.7rem;text-align:center;margin:2px 0 9px}
    .inq-nav-title:after{content:"";display:block;border-bottom:1px solid #4a3a20;margin:7px 0 2px}
    .inc-combat-header,.inc-identity{border:1px solid #5a4523;background:linear-gradient(135deg,#17110b,#0d0a07);padding:7px 12px;margin:0 0 6px;box-shadow:0 0 24px rgba(0,0,0,.28)}
    .inc-kicker{font-size:.55rem;letter-spacing:.18em;color:var(--gold);text-transform:uppercase;font-family:Cinzel,serif}
    .inc-hero-name{font-family:Cinzel,serif;font-size:1.02rem;color:var(--gold2);letter-spacing:.06em;text-transform:uppercase;margin-top:1px}
    .inc-hero-sub{font-size:.62rem;letter-spacing:.08em;color:var(--bone);opacity:.62;text-transform:uppercase;margin-top:1px}
    .inc-action-title{font-family:Cinzel,serif;color:var(--gold2);letter-spacing:.18em;font-size:.8rem;text-align:center;margin-bottom:8px}
    .inc-status-blood{color:#d65a52;font-weight:700;text-transform:uppercase;letter-spacing:.05em}
    .inc-talent-reaction{border:1px solid #7b2b2b;background:linear-gradient(135deg,#190b0b,#0d0808);padding:16px;margin:12px 0;box-shadow:0 0 22px rgba(120,0,0,.18)}
    .inc-talent-card{border-left:3px solid #77633c;background:#14100b;padding:9px 12px;margin:6px 0;border-radius:2px}.inc-talent-card.active{border-left-color:#b23a35}.inc-talent-card.passive{border-left-color:#3e7f5a}.inc-talent-card.manual{border-left-color:#6d5a39;opacity:.7}.inc-talent-card span{display:block;font-size:.72rem;opacity:.72;margin-top:3px;line-height:1.45}
    .inc-chip small{display:block;font-size:.52rem;letter-spacing:.14em;opacity:.58;margin-top:2px}.inc-chip.wound b{color:#d85a50}.inc-chip.shock b{color:#d4a94c}.inc-chip.wrath b{color:#e8c96a}.inc-enemy{transition:transform .15s ease,border-color .15s ease}.inc-enemy:hover{transform:translateY(-2px);border-color:#80602c}
    /* Combat feedback: a one-shot animation on whichever card the most
       recent action actually touched, so a hit/miss/damage taken reads as
       an event instead of just numbers changing on the same static card.
       Runs once per render because Streamlit gives each rerun a fresh DOM
       node - a CSS `animation` (not `transition`) always autoplays once on
       a newly-mounted element. */
    @keyframes inc-hit-shake{0%{transform:translateX(0)}20%{transform:translateX(-6px)}40%{transform:translateX(5px)}60%{transform:translateX(-3px)}80%{transform:translateX(2px)}100%{transform:translateX(0)}}
    @keyframes inc-hit-glow{0%{box-shadow:0 0 0 rgba(178,58,53,0)}25%{box-shadow:0 0 26px rgba(178,58,53,.85)}100%{box-shadow:0 0 0 rgba(178,58,53,0)}}
    @keyframes inc-miss-fade{0%{opacity:.4}100%{opacity:1}}
    @keyframes inc-player-flash{0%{opacity:0;transform:translateY(-4px)}15%{opacity:1;transform:translateY(0)}85%{opacity:1}100%{opacity:0}}
    .inc-enemy.inc-just-hit{animation:inc-hit-shake .4s ease, inc-hit-glow .8s ease}
    .inc-enemy.inc-just-missed{animation:inc-miss-fade .5s ease}
    .inc-hit-flash-player{animation:inc-player-flash 2.4s ease forwards;text-align:center;font-family:Cinzel,serif;letter-spacing:.14em;color:#ff8a80;background:rgba(178,58,53,.14);border:1px solid #b23a35;padding:8px;margin:0 0 10px;text-transform:uppercase}
    /* Dice tray: the live roll display shown up front in combat instead of a
       scrolling log below the fold - one glance shows both sides' last roll. */
    .inc-dice-tray{display:flex;gap:14px;justify-content:space-between;background:rgba(10,10,14,.55);border:1px solid rgba(198,163,90,.35);border-radius:8px;padding:10px 14px;margin:0 0 12px}
    .inc-dice-col{flex:1;min-width:0}
    .inc-dice-label{font-family:Cinzel,serif;letter-spacing:.12em;font-size:.7rem;opacity:.8;margin-bottom:6px;text-transform:uppercase}
    .inc-dice-label.you{color:#8fd3ff}
    .inc-dice-label.foe{color:#ff8a80}
    .inc-dice-row-inner{display:flex;flex-wrap:wrap;gap:6px}
    .inc-die{display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;border-radius:5px;background:#1c1c22;border:1px solid rgba(255,255,255,.18);color:#ddd;font-weight:700;font-size:.85rem;animation:inc-die-roll .4s ease both;animation-delay:calc(var(--d) * 60ms)}
    .inc-die.icon1{box-shadow:0 0 6px 1px rgba(255,215,120,.55);border-color:rgba(255,215,120,.6);color:#ffe9b0}
    .inc-die.icon2{box-shadow:0 0 10px 3px rgba(255,190,60,.75);border-color:rgba(255,190,60,.9);color:#fff3d0}
    .inc-die.wrath{outline:2px solid rgba(178,58,53,.85);outline-offset:2px}
    .inc-die.wrath.crit{animation:inc-die-roll .4s ease both,inc-wrath-crit 1.2s ease-in-out .4s infinite;box-shadow:0 0 16px 5px rgba(255,80,60,.9)}
    .inc-dice-meta{display:flex;gap:8px;margin-top:6px;font-size:.7rem;opacity:.85}
    .inc-dice-result.hit{color:#8fd98f;font-weight:700}
    .inc-dice-result.miss{color:#999;font-weight:700}
    .inc-dice-empty{opacity:.5;font-style:italic;font-size:.8rem}
    @keyframes inc-die-roll{from{transform:rotate(-35deg) scale(.4);opacity:0}to{transform:rotate(0) scale(1);opacity:1}}
    @keyframes inc-wrath-crit{0%,100%{box-shadow:0 0 16px 5px rgba(255,80,60,.9)}50%{box-shadow:0 0 24px 10px rgba(255,140,60,1)}}
    /* Field Loadout: purchased/looted items as visible badges, not just an
       entry buried inside the discard dropdown - the whole point is that a
       player can SEE a purchase actually landed. */
    .inc-gear-badges{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 14px}
    .inc-gear-badge{display:inline-block;border:1px solid #5a4523;background:#171009;color:#e8dcc0;font-size:.72rem;letter-spacing:.02em;padding:5px 10px;border-radius:2px}
    .inc-tutorial{display:flex;flex-direction:column;gap:8px;margin-top:6px}
    .inc-tutorial-row{border-left:3px solid #6d5a39;background:#14100b;padding:8px 12px;border-radius:2px}
    .inc-tutorial-row b{display:block;font-family:Cinzel,serif;color:var(--gold2);letter-spacing:.1em;font-size:.76rem;margin-bottom:3px}
    .inc-tutorial-row span{display:block;font-size:.78rem;line-height:1.5;opacity:.85}
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
           plus two small buttons) · the blanket column-stacking rule above
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
    "Attributes": "Atributos",
    "Positive Statuses": "Status Positivos", "Cover": "Cobertura", "Stealth": "Furtividade",
    "Status": "Status", "Add Status": "Adicionar Status",
    "Cameleoline is active: +1 bonus die to Stealth, +1 Defence.":
        "Cameleoline ativo: +1 dado bônus em Furtividade, +1 Defesa.",
    "Cameleoline is inactive until Cover or Stealth is active.":
        "Cameleoline inativo até Cobertura ou Furtividade ficar ativa.",
    "Your registration is awaiting the Magister's approval. You can freely edit your "
    "character sheet in the meantime, but if the Magister rejects it, your account and "
    "sheet are deleted immediately.":
        "Seu registro está aguardando aprovação do Mestre. Você pode editar sua ficha livremente "
        "enquanto isso, mas se o Mestre recusar, sua conta e ficha serão deletadas imediatamente.",
    "Conditions": "Condições", "No active Conditions.": "Nenhuma condição ativa.",
    "Roll": "Rolar", "Attack": "Ataque", "Damage": "Dano", "Dice": "Dados", "Icons": "Ícones",
    "Total": "Total", "Wrath Critical": "Crítico de Fúria", "Complication": "Complicação",
    "Tests": "Testes", "Special Tests": "Testes Especiais", "Corruption Test": "Teste de Corrupção",
    "Fear/Terror Test": "Teste de Medo/Terror", "Send this roll to Owlbear": "Enviar essa rolagem pro Owlbear",
    "Mod": "Mod",
    "Add Condition": "Adicionar Condição", "Condition": "Condição", "Stacks": "Acúmulo",
    "Apply": "Aplicar", "Custom…": "Personalizada…", "Custom name": "Nome personalizado",
    "Bleeding": "Sangramento", "Blinded": "Cego", "Exhausted": "Exausto", "Fear": "Medo",
    "Frenzied": "Enfurecido", "Hindered": "Impedido", "On Fire": "Em Chamas", "Pinned": "Fixado",
    "Poisoned": "Envenenado", "Prone": "Prostrado", "Restrained": "Contido", "Staggered": "Atordoado",
    "Terror": "Terror", "Vulnerable": "Vulnerável",
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
    "Quantity": "Quantidade",
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


def _owlbear_tests_sidebar(cid):
    """Every Core Rulebook Test (p.119-142, p.158) a Player can make from
    their own sheet, each with a one-click 'send to Owlbear' die icon.
    Experimental: only shown when the Magister enables Owlbear Rodeo
    Integration on the Campaign tab (see _gm_tab_campaign)."""
    ch = load_character(cid)
    if not ch:
        return
    gear_mods = equipped_wargear_modifiers(ch)
    attrs = effective_attributes(ch, gear_mods)
    skills = effective_skills(ch, gear_mods)
    d = derived_traits(ch, gear_mods)

    def roll_row(label, pool, key):
        c = st.columns([3, 1.3, 1])
        c[0].markdown(f"<div style='padding-top:6px;font-size:.82rem'>{T(label)} <span style='opacity:.6'>({pool})</span></div>",
                      unsafe_allow_html=True)
        mod = c[1].number_input(T("Mod"), -10, 10, 0, key=f"{key}_mod", label_visibility="collapsed")
        if c[2].button("🎲", key=key, use_container_width=True, help=T("Send this roll to Owlbear")):
            ok, msg = create_owlbear_roll_request(cid, ch.get("name", ""), T(label), int(pool), bonus_dice=int(mod), kind="test")
            (st.toast if ok else st.error)(msg)

    st.markdown(f"**🦉 {T('Tests')}**")
    with st.expander(T("Attributes"), expanded=False):
        for a in ATTRS:
            roll_row(a, int(attrs.get(a, 1)), f"sidebar_roll_attr_{cid}_{a}")
    with st.expander(T("Skills"), expanded=False):
        for s, at in SKILLS.items():
            pool = int(attrs.get(at, 1)) + int(skills.get(s, 0))
            roll_row(s, pool, f"sidebar_roll_skill_{cid}_{s}")
    with st.expander(T("Special Tests"), expanded=False):
        roll_row("Determination", int(d.get("Determination", 1)), f"sidebar_roll_det_{cid}")
        roll_row("Corruption Test", int(d.get("Conviction", 1)), f"sidebar_roll_corr_{cid}")
        roll_row("Fear/Terror Test", int(d.get("Resolve", 0)), f"sidebar_roll_fear_{cid}")


def _render_status_section(cid, ch, key_prefix=""):
    """Buffs (Cover, Stealth, ...) and debuffs (Bleeding, Poisoned, ...) in one
    shared badge list - only the colour tells them apart (green/blue for a
    positive status, red/amber for a Condition). Shared between Battle View
    and the Character Sheet tab so a Player/GM sees the same Status no
    matter which tab they're on. `key_prefix` keeps widget keys unique since
    Streamlit renders every tab's body on every rerun, not just the visible
    one - both callers are alive at once for the same character."""
    st.markdown(f"<div class='sectionttl'>{T('Status')}</div>", unsafe_allow_html=True)
    conds = ch.get("conditions", {}) or {}
    if conds:
        badge_cols = st.columns(min(len(conds), 6))
        for i, cname in enumerate(sorted(conds.keys())):
            stacks = int(conds[cname])
            color = POSITIVE_STATUS_COLOR.get(cname) or CONDITION_COLOR.get(cname, "#b8860b")
            label = f"{T(cname)} ({stacks})" if stacks > 1 else T(cname)
            with badge_cols[i % len(badge_cols)]:
                st.markdown(f"<span style='background:{color};color:#fff;padding:3px 10px;border-radius:12px;"
                            f"font-size:.78rem;font-family:Cinzel;letter-spacing:.03em;display:inline-block;margin-bottom:4px'>"
                            f"{html.escape(label)}</span>", unsafe_allow_html=True)
                if st.button("−", key=f"{key_prefix}cond_rm_{cid}_{cname}"):
                    set_condition(cid, cname, stacks - 1)
                    st.rerun()
    else:
        st.caption(T("No active Conditions."))
    if _has_cameleoline(ch):
        if "Cameleoline" in active_positive_statuses(ch):
            st.caption(f"🦎 {T('Cameleoline is active: +1 bonus die to Stealth, +1 Defence.')}")
        else:
            st.caption(f"🦎 {T('Cameleoline is inactive until Cover or Stealth is active.')}")
    with st.expander(T("Add Status"), expanded=False):
        cadd = st.columns([2, 1, 1])
        options = POSITIVE_STATUSES + CONDITIONS + [_COND_CUSTOM]
        preset = cadd[0].selectbox(T("Status"), options,
                                    format_func=lambda x: T("Custom…") if x == _COND_CUSTOM else T(x),
                                    key=f"{key_prefix}cond_pick_{cid}")
        custom_name = ""
        if preset == _COND_CUSTOM:
            custom_name = st.text_input(T("Custom name"), key=f"{key_prefix}cond_custom_{cid}",
                                         placeholder="e.g. Cameleoline Active")
        cstacks = cadd[1].number_input(T("Stacks"), 1, 20, 1, key=f"{key_prefix}cond_stacks_{cid}")
        cadd[2].markdown("<div style='padding-top:28px'></div>", unsafe_allow_html=True)
        if cadd[2].button(T("Apply"), key=f"{key_prefix}cond_apply_{cid}", use_container_width=True):
            name = custom_name.strip() if preset == _COND_CUSTOM else preset
            if name:
                ok, msg = set_condition(cid, name, int(conds.get(name, 0)) + int(cstacks))
                if ok: st.rerun()
                else: st.error(msg)


@st.fragment
def battle_view(cid):
    ch = load_character(cid)
    if not ch:
        st.error("Character sheet not found.")
        return
    camp = get_campaign()
    gear_mods = equipped_wargear_modifiers(ch)
    d = derived_traits(ch, gear_mods)
    rank = int(ch.get("rank", 1) or 1)
    ncls = "npc" if ch["kind"] == "npc" else ""
    st.markdown(f"<div class='hero'><div class='nm {ncls}'>{ch['name'] or T('Character')}</div>"
                f"<div class='meta'>{ch['chapter'] or ''} &nbsp;·&nbsp; {species_label(ch['species'])} &nbsp;·&nbsp; "
                f"{T('Tier')} {ch['tier']} &nbsp;·&nbsp; {T('Rank')} {rank}</div></div>", unsafe_allow_html=True)

    st.markdown(f"<div class='sectionttl'>{T('Vitals')}</div>", unsafe_allow_html=True)
    live_vitals(cid, ch, gear_mods)

    _render_status_section(cid, ch, key_prefix="bv_")

    left, right = st.columns([1.5, 1])
    with left:
        st.markdown(f"<div class='sectionttl'>{T('Attributes')}</div>", unsafe_allow_html=True)
        base_attr_top = {str(k): int(v) for k, v in (ch.get("attributes", {}) or {}).items()}
        attr_cards = "".join(
            f"<div class='statcard'><div class='l'>{T(a)}</div><div class='v'>{base_attr_top.get(a, 1)}"
            + (f"<span class='gear-mod'>{int(gear_mods.get(a.lower(), 0) or 0):+d}</span>" if gear_mods.get(a.lower()) else "")
            + "</div></div>"
            for a in ATTRS
        )
        st.markdown(f"<div class='grid'>{attr_cards}</div>", unsafe_allow_html=True)

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
            base_attrs = effective_attributes(ch, gear_mods)
            base_skills = effective_skills(ch, gear_mods)
            owlbear_on = bool(camp.get("owlbear_enabled"))
            for widx, w in enumerate(ch["wargear"]):
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
                stats_html = _wargear_stat_html(details, attrs=base_attrs)
                st.markdown(f"<div class='wg'><b>{name}</b>{stats_html}{effect_html}</div>", unsafe_allow_html=True)

                if owlbear_on and details.get("damage") not in (None, ""):
                    is_melee = str(details.get("damage", "")).strip().upper().startswith("(S)")
                    skill_name = "Weapon Skill" if is_melee else "Ballistic Skill"
                    attr_name = SKILLS[skill_name]
                    pool = int(base_attrs.get(attr_name, 1)) + int(base_skills.get(skill_name, 0))
                    try: ed_n = int(details.get("ed", 0) or 0)
                    except (TypeError, ValueError): ed_n = 0
                    ocols = st.columns([2, 1, 2, 1])
                    atk_mod = ocols[1].number_input(T("Mod"), -10, 10, 0, key=f"owlbear_atk_mod_{cid}_{widx}", label_visibility="collapsed")
                    if ocols[0].button(f"🦉 {T('Attack')} ({pool}d6)", key=f"owlbear_atk_{cid}_{widx}", use_container_width=True):
                        ok, msg = create_owlbear_roll_request(cid, ch.get("name", ""), f"{raw_name} · {T(skill_name)}", pool, bonus_dice=int(atk_mod), kind="test")
                        (st.toast if ok else st.error)(msg)
                    dmg_mod = ocols[3].number_input(T("Mod"), -10, 10, 0, key=f"owlbear_dmg_mod_{cid}_{widx}", label_visibility="collapsed")
                    if ocols[2].button(f"🦉 {T('Damage')} ({ed_n}d6)", key=f"owlbear_dmg_{cid}_{widx}", use_container_width=True):
                        ok, msg = create_owlbear_roll_request(cid, ch.get("name", ""), f"{raw_name} · {T('Damage')}", ed_n, bonus_dice=int(dmg_mod), kind="damage")
                        (st.toast if ok else st.error)(msg)
        else:
            st.markdown(f"<div class='wg' style='opacity:.6'>{T('No wargear.')}</div>", unsafe_allow_html=True)

        pending_req = [r for r in list_requisitions(character_id=cid) if r["status"] == "pending"]
        for r in pending_req:
            label = "Em Análise" if st.session_state.get("ui_lang") == "pt" else "Under Review"
            qty_suffix = f" ×{int(r.get('quantity', 1) or 1)}" if int(r.get('quantity', 1) or 1) > 1 else ""
            st.markdown(
                f"<div class='wg wg-pending'><b>{html.escape(r['name'])}{qty_suffix}</b>"
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


@st.fragment
def edit_view(cid, gm_mode=False):
    # Keep the official catalog available for both GM management and Player talent purchases.
    sync_official_craft_catalog()
    ch = load_character(cid)
    if not ch:
        st.error("Character sheet not found.")
        return
    _render_status_section(cid, ch, key_prefix="sheet_")
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

    # This override is a one-shot hand-off from cb_archetype_change(), applying
    # the newly picked Archetype's starting Wargear exactly once so it can be
    # saved below. It must not linger in session_state past this render: Wargear
    # is only ever seeded at creation/Archetype-change time, so once it's part
    # of the saved sheet, later GM/Player edits (including removals) must stick
    # on every subsequent render/auto-refresh instead of being overwritten again.
    _arch_gear_key = _k(cid, "meta", "archetype_starting_wargear")
    wdf = normalize_wargear(st.session_state.pop(_arch_gear_key, ch.get("wargear", [])))
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
            category = html.escape(str(details_w.get("category", "Wargear") or "Wargear").title())
            stat_html = _wargear_stat_html(details_w, attrs=cur_attr)
            wc2 = st.columns([3.2, 5.2, 1.15, 1.15])
            wc2[0].markdown(
                f"<div class='inventory-name'>{display_name} <span class='inventory-qty'>{('× ' + str(qty)) if stackable_w else ''}</span></div>"
                f"<div class='inventory-meta'>{category}</div>", unsafe_allow_html=True)
            wc2[1].markdown(f"{stat_html}<div class='inventory-effect'>{effect}</div>", unsafe_allow_html=True)

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


def _login_hologram_globe():
    """Purely decorative: a CSS-only rotating hologram globe above the login
    form, one small glowing point per Player whose Vox is currently Active
    (the closest existing signal to 'logged in' - this app has no separate
    session-presence tracker). Folder-mates cluster together on the globe's
    surface; a Player with no folder sits alone as an isolated point. No JS -
    the spin and every point's placement are plain CSS 3D transforms, so
    positions are stable between reruns (seeded by name, not randomised)."""
    try:
        chars = [c for c in list_characters() if c.get("kind") == "player" and c.get("comms_on")]
    except Exception:
        chars = []

    st.markdown("""
    <style>
    .holo-wrap{ position:relative; width:230px; height:230px; margin:4px auto 14px; perspective:820px; }
    .holo-sphere{ position:absolute; inset:0; border-radius:50%;
        background:radial-gradient(circle at 32% 28%, rgba(201,162,39,.20), rgba(201,162,39,.02) 55%, transparent 72%);
        box-shadow: inset 0 0 40px rgba(201,162,39,.15), 0 0 22px rgba(201,162,39,.12); }
    .holo-ring{ position:absolute; left:50%; top:50%; width:230px; height:230px;
        margin:-115px 0 0 -115px; border:1px solid rgba(201,162,39,.22);
        border-radius:50%; transform-style:preserve-3d; pointer-events:none; }
    /* Four meridians (great circles through the poles), evenly spaced in
       longitude, plus two latitude bands crossing them at different tilts -
       every ring shares one axis (the rotator's spin) but each sits on a
       different plane, so together they read as one wireframe sphere
       instead of ellipses sliding along a single flat axis. */
    .holo-ring-m1{ transform:rotateY(0deg); }
    .holo-ring-m2{ transform:rotateY(45deg); }
    .holo-ring-m3{ transform:rotateY(90deg); }
    .holo-ring-m4{ transform:rotateY(135deg); }
    .holo-ring-lat1{ transform:rotateX(78deg); }
    .holo-ring-lat2{ transform:rotateX(-55deg) rotateZ(20deg); }
    .holo-rotator{ position:absolute; inset:0; transform-style:preserve-3d; animation: holo-spin 24s linear infinite; }
    @keyframes holo-spin{ from{ transform:rotateY(0deg); } to{ transform:rotateY(360deg); } }
    .holo-point{ position:absolute; left:50%; top:50%; width:0; height:0; transform-style:preserve-3d; }
    .holo-dot{ position:absolute; left:-3px; top:-3px; width:6px; height:6px; border-radius:50%;
        background:#e8c96a; box-shadow:0 0 6px 2px rgba(201,162,39,.9); }
    .holo-label{ position:absolute; left:6px; top:-7px; font-size:6.5px; white-space:nowrap;
        color:#e8e0cf; font-family:'Cinzel',serif; letter-spacing:.02em;
        text-shadow:0 0 3px #000, 0 0 6px rgba(201,162,39,.5); opacity:.9; }
    .holo-empty{ text-align:center; font-size:.7rem; opacity:.55; letter-spacing:.15em;
        text-transform:uppercase; margin-top:-6px; margin-bottom:10px; }
    </style>
    """, unsafe_allow_html=True)

    # The wireframe rings live INSIDE the rotator (not as static siblings) so
    # they spin together with the points, like the surface of one solid
    # turning planet rather than dots drifting over a fixed cage.
    rings_html = "".join(
        f"<div class='holo-ring holo-ring-{cls}'></div>"
        for cls in ("m1", "m2", "m3", "m4", "lat1", "lat2")
    )

    if not chars:
        st.markdown(f"<div class='holo-wrap'><div class='holo-sphere'></div>"
                     f"<div class='holo-rotator'>{rings_html}</div></div>"
                     "<div class='holo-empty'>No signal</div>", unsafe_allow_html=True)
        return

    def jitter(seed, spread):
        h = int(hashlib.md5(seed.encode()).hexdigest(), 16)
        return (h % 10000) / 10000.0 * spread - spread / 2

    groups = {}
    for c in chars:
        groups.setdefault(c.get("folder_id"), []).append(c)
    group_keys = list(groups.keys())
    n_groups = max(1, len(group_keys))

    points = []
    for gi, key in enumerate(group_keys):
        members = groups[key]
        is_folder = key is not None
        home_theta = (360.0 / n_groups) * gi
        for mi, ch in enumerate(members):
            name = str(ch.get("name") or "Unnamed")
            first_name = name.strip().split()[0] if name.strip() else "Unnamed"
            if is_folder:
                theta = home_theta + jitter(f"{name}-t", 22) + (mi - (len(members) - 1) / 2) * 8
                phi = jitter(f"{name}-p", 46)
            else:
                # Isolated: scattered on its own, never pulled toward a cluster.
                theta = jitter(f"{name}-iso-t", 360)
                phi = jitter(f"{name}-iso-p", 150)
            safe_name = html.escape(first_name)
            points.append(
                f"<div class='holo-point' style='transform:rotateY({theta:.1f}deg) rotateX({phi:.1f}deg) translateZ(100px)'>"
                f"<span class='holo-dot'></span><span class='holo-label'>{safe_name}</span></div>"
            )

    st.markdown(
        f"<div class='holo-wrap'><div class='holo-sphere'></div>"
        f"<div class='holo-rotator'>{rings_html}{''.join(points)}</div></div>",
        unsafe_allow_html=True,
    )


# ============================================================
#  WRATH INCURSION · solo roguelike mini-game
#  Lives entirely inside sistema.py (one deployment, one login system per
#  terminal - see mode_chooser_page()) but is fully isolated data-wise: a
#  run only ever READS a character's attributes/skills/wargear/talents/
#  powers as its starting point via load_character(). It never writes to
#  characters/cur_wounds/cur_wealth/earned_xp and never creates a
#  wargear_requisition - nothing here needs the Magister's approval or
#  touches the real sheet. All run state lives in incursion_run /
#  incursion_pvp_queue / incursion_fallen_mob (see init_db()).
#
#  Combat is a deliberately simplified version of the tabletop's own dice
#  engine (no reactions/Complications/Wrath spending - this runs solo,
#  unattended): roll one d6 per point of dice pool; 4-5 = 1 Icon, 6 = an
#  Exalted Icon worth 2. A hit needs total Icons >= the target's Defence;
#  Icons beyond that add bonus damage. Damage is the attacker's best
#  equipped weapon's resolved Damage (via _weapon_base_damage, same as the
#  Craft tab), reduced by the target's Resilience.
# ============================================================
INC_SEQUENCE = ["start", "easy", "random", "medium", "pvp_mid", "hard", "boss"]
INC_STAGE_LABELS = {
    "start": "Encampment", "easy": "Patrol", "random": "Chance Encounter", "medium": "Ambush",
    "pvp_mid": "Challenge", "hard": "Front Line", "boss": "Enemy Champion", "pvp_boss3": "Duel of Glory",
}
INC_REWARD_XP = {"easy": 15, "medium": 28, "hard": 45, "boss": 120}
INC_REST_HEAL_FRACTION = 0.25
INC_FALLEN_CHANCE = 0.35
INC_EASY_POOL_CAP = 4
INC_DEBUFF_CHANCE = 0.25
INC_DEBUFF_ATTRS = ["Initiative", "Agility", "Strength", "Willpower"]

# "Once per fight" Talent/status flags - none of these were ever being
# cleared anywhere, so every "once per fight" Talent (Combat Veteran,
# Predator's Mark, Unyielding Flesh, Iron Resolve, and the new Indomitable/
# Reanimation Protocols below) only ever fired ONCE FOR THE ENTIRE RUN,
# not once per fight as their text promised - a real, pre-existing reason
# Talents felt weak. Cleared whenever the current fight actually ends
# (victory or a successful Flee).
_INC_PER_FIGHT_STATUS_FLAGS = (
    "combat_first_hit_used", "predator_mark_used", "unyielding_used",
    "iron_resolve_used", "reroll_miss_used", "reanimation_used", "combat_turn_count",
)


def _inc_reset_per_fight_statuses(statuses):
    statuses = dict(statuses or {})
    for k in _INC_PER_FIGHT_STATUS_FLAGS:
        statuses.pop(k, None)
    statuses["enemy_debuffs"] = {}
    return statuses
INC_DIFFICULTY_TIER = {"easy": 1, "medium": 2, "hard": 3, "boss": 4}
INC_PVP_XP_REWARD = {"mid": 180, "boss3": 300}
INC_FALLEN_PREFIXES = ["Spectre of", "Shade of", "Corrupted Echo of", "Remnant of"]
INC_FLAVOR_KEYWORDS = ["Zealous", "Grim", "Vigilant", "Bloodied", "Unyielding", "Cold-Eyed", "Wrathful"]


# ---- persistence -----------------------------------------------------
def _inc_json_field(value, fallback):
    """Decode a JSON-bearing column that may come back either as a plain
    string (TEXT columns, the normal case for every table this feature
    creates) or already-parsed (psycopg2 auto-deserializes a genuine JSONB
    column, which incursion_fallen_mob.attributes ended up as - a leftover
    from an earlier prototype - so this stays defensive rather than
    assuming one representation)."""
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _inc_decode_run(row):
    r = dict(row)
    r["bonus_attributes"] = _inc_json_field(r.get("bonus_attributes"), {})
    r["bonus_skills"] = _inc_json_field(r.get("bonus_skills"), {})
    r["incursion_statuses"] = _inc_json_field(r.get("incursion_statuses"), {})
    r["consumable_charges"] = _inc_json_field(r.get("consumable_charges"), {})
    r["weapon_durabilities"] = _inc_json_field(r.get("weapon_durabilities"), {})
    r["minions"] = _inc_json_field(r.get("minions"), [])
    for f in ("starting_wargear", "extra_wargear", "extra_talents", "extra_powers", "extra_keywords"):
        r[f] = _inc_json_field(r.get(f), [])
    r["node"] = _inc_json_field(r.get("node"), None)
    r["pending_boss3_pvp"] = bool(r.get("pending_boss3_pvp"))
    r["free_upgrade_used"] = bool(r.get("free_upgrade_used"))

    # Older Incursion rows can have NULL in the newer life-pool columns.
    # Never let NULL reach combat arithmetic.
    for f in (
        "wounds_current", "wounds_max", "shock_current", "shock_max",
        "wrath_current", "wrath_max", "xp", "xp_earned", "loop_no", "bosses_cleared",
        "heal_charges", "armour_durability_current", "armour_durability_max",
    ):
        value = r.get(f)
        if value is not None:
            try:
                r[f] = int(value)
            except (TypeError, ValueError):
                pass
    return r


def _inc_hydrate_run_pools(run):
    """Repair legacy/incomplete runs before they reach the Incursion UI or combat.

    The Incursion life pools are run-local. If a database row was created before
    the wounds/shock/wrath columns were added, those columns are NULL. Rebuild
    the missing values from the character sheet and persist them once.
    """
    if not run:
        return run

    missing = any(run.get(f) is None for f in (
        "wounds_current", "wounds_max", "shock_current", "shock_max",
        "wrath_current", "wrath_max", "armour_durability_current", "armour_durability_max",
    ))
    if not missing:
        return run

    conn = get_conn()
    row = conn.execute("SELECT * FROM characters WHERE id=?", (run["character_id"],)).fetchone()
    if not row:
        conn.close()
        return run
    ch = _decode(row)
    conn.close()

    # Include upgrades already bought during this run when rebuilding maxima.
    merged = _inc_merge_character(ch, run)
    pools = _inc_life_pools(merged)
    armour_rating = _inc_armour_durability(ch, run)[1]

    updates = {}
    if run.get("wounds_max") is None:
        updates["wounds_max"] = pools["wounds_max"]
    if run.get("shock_max") is None:
        updates["shock_max"] = pools["shock_max"]
    if run.get("wrath_max") is None:
        updates["wrath_max"] = pools["wrath_max"]

    # Prefer the old hp columns if an older run has them; otherwise start full.
    old_hp_max = run.get("hp_max")
    old_hp_current = run.get("hp_current")
    if run.get("wounds_max") is None and old_hp_max is not None:
        try:
            updates["wounds_max"] = int(old_hp_max)
        except (TypeError, ValueError):
            pass
    if run.get("wounds_current") is None:
        if old_hp_current is not None:
            try:
                updates["wounds_current"] = max(0, int(old_hp_current))
            except (TypeError, ValueError):
                pass
        if "wounds_current" not in updates:
            updates["wounds_current"] = updates.get("wounds_max", pools["wounds_max"])

    if run.get("shock_current") is None:
        updates["shock_current"] = updates.get("shock_max", pools["shock_max"])
    if run.get("wrath_current") is None:
        updates["wrath_current"] = updates.get("wrath_max", pools["wrath_max"])
    if run.get("armour_durability_max") is None:
        updates["armour_durability_max"] = armour_rating
    if run.get("armour_durability_current") is None:
        updates["armour_durability_current"] = armour_rating

    # Clamp repaired/current values to their maxima.
    final_wounds_max = int(updates.get("wounds_max", run.get("wounds_max") or pools["wounds_max"]))
    final_shock_max = int(updates.get("shock_max", run.get("shock_max") or pools["shock_max"]))
    final_wrath_max = int(updates.get("wrath_max", run.get("wrath_max") or pools["wrath_max"]))
    updates["wounds_max"] = final_wounds_max
    updates["shock_max"] = final_shock_max
    updates["wrath_max"] = final_wrath_max
    updates["wounds_current"] = min(final_wounds_max, max(0, int(updates["wounds_current"])))
    updates["shock_current"] = min(final_shock_max, max(0, int(updates["shock_current"])))
    updates["wrath_current"] = max(0, int(updates["wrath_current"]))

    conn = get_conn()
    conn.execute(
        "UPDATE incursion_run SET wounds_current=?, wounds_max=?, shock_current=?, shock_max=?, wrath_current=?, wrath_max=?, armour_durability_current=?, armour_durability_max=? WHERE id=?",
        (updates["wounds_current"], updates["wounds_max"], updates["shock_current"],
         updates["shock_max"], updates["wrath_current"], updates["wrath_max"],
         updates.get("armour_durability_current", run.get("armour_durability_current", 0)),
         updates.get("armour_durability_max", run.get("armour_durability_max", 0)), run["id"]),
    )
    conn.commit()
    conn.close()
    run.update(updates)
    return run


def _inc_get_run(run_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM incursion_run WHERE id=?", (run_id,)).fetchone()
    conn.close()
    return _inc_hydrate_run_pools(_inc_decode_run(row)) if row else None


def _inc_get_active_run(cid):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM incursion_run WHERE character_id=? AND status='active' ORDER BY id DESC LIMIT 1", (cid,)
    ).fetchone()
    conn.close()
    return _inc_hydrate_run_pools(_inc_decode_run(row)) if row else None


def _inc_get_latest_run(cid):
    """Most recent run regardless of status - used to decide whether to show
    the death recap screen (a run just ended) vs. the fresh intro screen (no
    run has ever been started), which _inc_get_active_run can't distinguish
    since both cases return no 'active' row."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM incursion_run WHERE character_id=? ORDER BY id DESC LIMIT 1", (cid,)
    ).fetchone()
    conn.close()
    return _inc_hydrate_run_pools(_inc_decode_run(row)) if row else None


def _inc_persist(run_id, **fields):
    sets, args = [], []
    for k, v in fields.items():
        if isinstance(v, (dict, list)):
            v = json.dumps(v)
        elif isinstance(v, bool):
            v = int(v)
        sets.append(f"{k}=?")
        args.append(v)
    args.append(run_id)
    conn = get_conn()
    conn.execute(f"UPDATE incursion_run SET {', '.join(sets)} WHERE id=?", args)
    conn.commit(); conn.close()
    return _inc_get_run(run_id)


# ---- character rules (reuses the real sheet's own math) --------------
def _inc_is_armour_item(w):
    d = _gear_details_dict(w.get("details", {}))
    category = str(d.get("category", "")).lower()
    if "armour" in category or "armor" in category:
        return True
    return d.get("armour_rating") not in (None, "")


def _inc_merge_character(ch, run):
    """Build the isolated Incursion sheet.

    Only the character's starting Attributes and starting non-armour items cross
    the boundary. Skills, Talents, Powers, Armour, Rank and Tier from the live
    character sheet never enter the run. Every later change is stored on the run.
    """
    merged = dict(ch)
    origin = run.get("origin")
    if origin and ch.get("kind") == "incursion" and origin in INC_ORIGINS:
        # An incursion-kind account's stored Attributes are just an unused
        # flat baseline - the run's chosen Origin (picked fresh every run,
        # see _inc_render_origin_select) is the real source of truth.
        attrs = _inc_origin_attributes(origin)
    else:
        attrs = {a: int((ch.get("attributes") or {}).get(a, 1) or 1) for a in ATTRS}
    for k,v in (run.get("bonus_attributes") or {}).items(): attrs[k] = int(attrs.get(k,1)) + int(v)
    statuses=dict(run.get("incursion_statuses") or {})
    for k,v in (statuses.get("talent_permanent_attributes") or {}).items(): attrs[k]=int(attrs.get(k,1))+int(v)
    for k,v in (statuses.get("combat_attribute_bonus") or {}).items(): attrs[k]=int(attrs.get(k,1))+int(v)
    # Some enemies can inflict a debuff on a hit - lasts for the rest of
    # the fight only, cleared by _inc_finish_combat_round once it resolves.
    for k,v in (statuses.get("enemy_debuffs") or {}).items(): attrs[k]=max(1,int(attrs.get(k,1))+int(v))
    merged["attributes"]=attrs
    merged["skills"]={s:0 for s in SKILLS}
    # Rank/Tier are run-local baselines, not inherited from the character.
    # species drives species_speed()'s Aeldari/Astartes check, so an
    # Origin's "-Pattern" name doubles as its Speed identity for free.
    merged["rank"]=1; merged["tier"]=1; merged["species"]=origin if (origin and ch.get("kind")=="incursion") else "Human"
    initial=[dict(w) for w in (run.get("starting_wargear") or [])]
    wargear=initial + [dict(w) for w in (run.get("extra_wargear") or [])]
    armor_key=run.get("equipped_armor_key")
    for w in wargear:
        if _inc_is_armour_item(w): w["equipped"]=(bool(armor_key) and _inc_weapon_key(w)==armor_key)
    merged["wargear"]=wargear
    merged["talents"]=list(run.get("extra_talents") or [])
    merged["powers"]=[]
    return merged


def _inc_discard_item(run, ch, item_key):
    """Discard one run-local Wargear item outside combat."""
    starting = list(run.get("starting_wargear") or [])
    extra = list(run.get("extra_wargear") or [])
    all_items = starting + extra
    item = next((w for w in all_items if _inc_weapon_key(w) == str(item_key)), None)
    if item is None:
        raise ValueError("item_not_found")

    key = _inc_weapon_key(item)
    is_armour = _inc_is_armour_item(item)
    quantity = int(item.get("quantity", 1) or 1)

    def remove_one(items):
        out = []
        removed = False
        for w in items:
            if not removed and _inc_weapon_key(w) == key:
                if quantity > 1 and int(w.get("quantity", 1) or 1) > 1:
                    w = dict(w)
                    w["quantity"] = int(w.get("quantity", 1) or 1) - 1
                    out.append(w)
                else:
                    removed = True
                    continue
            else:
                out.append(w)
        return out, removed

    starting, removed = remove_one(starting)
    if not removed:
        extra, removed = remove_one(extra)
    if not removed:
        raise ValueError("item_not_found")

    updates = {
        "starting_wargear": starting,
        "extra_wargear": extra,
    }

    values = _inc_weapon_durability_map(run)
    if key in values:
        values.pop(key, None)
    updates["weapon_durabilities"] = values

    if is_armour and str(run.get("equipped_armor_key") or "") == key:
        updates.update({
            "equipped_armor_key": "",
            "armour_durability_current": 0,
            "armour_durability_max": 0,
        })

    return _inc_persist(run["id"], **updates)


def _inc_render_backpack(run, ch):
    """Right-side loadout panel: every carried item as a rarity-coloured
    tile - a firearm/melee icon and an EQUIPPED marker for Armour instead
    of a dropdown you had to open to see what you're even carrying."""
    for minion in (run.get("minions") or []):
        rarity_cls = f"rarity-{str(minion.get('rarity') or 'Common').lower()}"
        status = "ACTIVE" if minion.get("alive") else "DOWN · revives on Rest"
        level = int(minion.get("level", 1) or 1)
        lvl_tag = f" · Lv{level}" if level > 1 else ""
        st.markdown(
            f"<div class='inc-pack-item {rarity_cls}'><span class='pack-icon'>{minion.get('icon','🐾')}</span>"
            f"<span class='pack-name'>{html.escape(str(minion.get('name','Minion')))}{lvl_tag}</span>"
            f"<span class='pack-sub'>{int(minion.get('wounds_current',0))}/{int(minion.get('wounds_max',0))}W · "
            f"{int(minion.get('shock_current',0))}/{int(minion.get('shock_max',0))}S · {status}</span></div>",
            unsafe_allow_html=True)
    items = list(run.get("starting_wargear") or []) + list(run.get("extra_wargear") or [])
    st.markdown("<div class='inc-backpack-title'>BACKPACK</div>", unsafe_allow_html=True)
    if not items:
        st.caption("Empty.")
        return
    seen = set()
    for item in items:
        key = _inc_weapon_key(item)
        if key in seen:
            continue
        seen.add(key)
        details = _gear_details_dict(item.get("details", {}))
        rarity = str(details.get("rarity") or "Common").lower()
        quantity = int(item.get("quantity", 1) or 1)
        name = str(item.get("name", "Item"))
        is_armour = _inc_is_armour_item(item)
        is_weapon = details.get("damage") not in (None, "")
        heal_wounds = int(details.get("heal_wounds", 0) or 0); heal_shock = int(details.get("heal_shock", 0) or 0)
        equipped_cls = ""
        if is_armour:
            equipped = str(run.get("equipped_armor_key") or "") == key
            icon = "🛡"; sub = "EQUIPPED" if equipped else "STORED"
            equipped_cls = "equipped" if equipped else ""
        elif is_weapon:
            melee = bool(details.get("damage_attribute")) or str(details.get("damage", "")).strip().upper().startswith("(S)")
            icon = "⚔" if melee else "🔫"
            current, maximum = _inc_weapon_durability(ch, run, key, item)
            sub = f"DUR {current}/{maximum}"
        else:
            icon = "◆"; sub = f"×{quantity}" if quantity > 1 else "ITEM"
        st.markdown(
            f"<div class='inc-pack-item rarity-{rarity} {equipped_cls}'>"
            f"<span class='pack-icon'>{icon}</span><span class='pack-name'>{html.escape(name)}</span>"
            f"<span class='pack-sub'>{html.escape(sub)}</span></div>", unsafe_allow_html=True)
        if not is_armour and not is_weapon and (heal_wounds or heal_shock):
            # Healing Consumables (Stims etc.) were previously stuck in the
            # backpack with no way to actually use them - only weapons had
            # a "damage" field and thus showed up as a usable action.
            if st.button("USE", key=f"inc_pack_use_{run['id']}_{key}", use_container_width=True):
                try:
                    _inc_use_consumable(run, ch, key)
                except ValueError as exc:
                    st.error(str(exc).replace("_", " ").title())
                else:
                    st.rerun()
        elif not is_armour:
            if st.button("Discard", key=f"inc_pack_discard_{run['id']}_{key}", use_container_width=True):
                try:
                    _inc_discard_item(run, ch, key)
                except ValueError as exc:
                    st.error(str(exc).replace("_", " ").title())
                else:
                    st.rerun()

def _inc_armour_options(ch, run):
    """Every distinct owned/bought Armour-category item, for the Rest
    screen's 'Worn Armour' picker - lets a character who owns more than one
    suit choose which is equipped for the run, same idea as the weapon
    picker in combat."""
    all_gear = list((run.get("starting_wargear") or [])) + list(run.get("extra_wargear") or [])
    seen, options = set(), []
    for w in all_gear:
        if not _inc_is_armour_item(w):
            continue
        key = _inc_weapon_key(w)
        if key in seen:
            continue
        seen.add(key)
        d = _gear_details_dict(w.get("details", {}))
        options.append({"key": key, "name": w.get("name", "Armour"), "rating": d.get("armour_rating", "")})
    return options


def _inc_rarity_rank(w):
    details = _gear_details_dict(w.get("details", {}))
    rarity = str(details.get("rarity", "Common") or "Common").strip().lower()
    return {"common": 1, "uncommon": 2, "rare": 3, "very rare": 4, "unique": 5}.get(rarity, 1)


def _inc_wargear_durability_max(w):
    """Run-local durability ceiling. Rarity 1..5 gives 15..75 durability."""
    return 15 * _inc_rarity_rank(w)


def _inc_destroyed_keys(run):
    statuses = dict(run.get("incursion_statuses") or {})
    return set(str(x) for x in (statuses.get("destroyed_wargear") or []))


def _inc_weapon_durability_map(run):
    return {str(k): int(v) for k, v in (run.get("weapon_durabilities") or {}).items()}


def _inc_weapon_durability(ch, run, weapon_key, weapon_item=None):
    weapon_item = weapon_item or next(
        (w for w in (list(run.get("starting_wargear") or []) + list(ch.get("wargear") or []) + list(run.get("extra_wargear") or []))
         if _inc_weapon_key(w) == weapon_key), None)
    if weapon_item is None:
        return 0, 0
    maximum = _inc_wargear_durability_max(weapon_item)
    values = _inc_weapon_durability_map(run)
    current = int(values.get(str(weapon_key), maximum))
    return max(0, min(current, maximum)), maximum


def _inc_set_weapon_durability(run, weapon_key, current):
    values = _inc_weapon_durability_map(run)
    values[str(weapon_key)] = max(0, int(current))
    return _inc_persist(run["id"], weapon_durabilities=values)


def _inc_recover_rest_durability(run, ch):
    """Rest repairs surviving armour by 25-30% and every weapon by 25-100%."""
    destroyed = _inc_destroyed_keys(run)
    all_gear = list(ch.get("wargear") or []) + list(run.get("extra_wargear") or [])
    armour_key = run.get("equipped_armor_key")
    armour_current, armour_max = _inc_armour_durability(ch, run)
    armour_gain = random.randint(max(1, math.ceil(armour_max * 0.25)), max(1, math.floor(armour_max * 0.30))) if armour_max > 0 else 0
    armour_current = min(armour_max, armour_current + armour_gain)
    values = _inc_weapon_durability_map(run)
    repaired = []
    for w in all_gear:
        if not w.get("equipped", True) or _inc_is_armour_item(w):
            continue
        details = _gear_details_dict(w.get("details", {}))
        if details.get("damage") in (None, ""):
            continue
        key = _inc_weapon_key(w)
        if key in destroyed:
            continue
        maximum = _inc_wargear_durability_max(w)
        current = int(values.get(key, maximum))
        if current >= maximum:
            continue
        low = max(1, math.ceil(maximum * 0.25))
        high = max(low, maximum)
        gain = random.randint(low, high)
        values[key] = min(maximum, current + gain)
        repaired.append((w.get("name", "Weapon"), gain, values[key], maximum))
    updates = {"weapon_durabilities": values, "armour_durability_current": armour_current,
               "armour_durability_max": armour_max}
    return _inc_persist(run["id"], **updates), repaired, armour_gain


def _inc_break_armour_if_needed(run, ch):
    current, maximum = _inc_armour_durability(ch, run)
    if maximum <= 0 or current > 0:
        return run, False
    armour_key = run.get("equipped_armor_key")
    if not armour_key:
        return run, False
    statuses = dict(run.get("incursion_statuses") or {})
    destroyed = set(str(x) for x in (statuses.get("destroyed_wargear") or []))
    destroyed.add(str(armour_key))
    statuses["destroyed_wargear"] = sorted(destroyed)
    extra = list(run.get("extra_wargear") or [])
    extra = [w for w in extra if _inc_weapon_key(w) != str(armour_key)]
    return _inc_persist(run["id"], equipped_armor_key="", armour_durability_current=0,
                        armour_durability_max=0, extra_wargear=extra, incursion_statuses=statuses), True


def _inc_damage_weapon_from_wrath_one(run, ch, weapon_key):
    weapon = next((w for w in (list(ch.get("wargear") or []) + list(run.get("extra_wargear") or []))
                   if _inc_weapon_key(w) == weapon_key), None)
    if weapon is None or _inc_is_armour_item(weapon):
        return run, 0, 0, 0
    current, maximum = _inc_weapon_durability(ch, run, weapon_key, weapon)
    if maximum <= 0:
        return run, 0, current, maximum
    new_current = max(0, current - 1)
    run = _inc_set_weapon_durability(run, weapon_key, new_current)
    return run, 1, new_current, maximum


def _inc_armour_rating(ch, run=None):
    """Return the Armour Rating of the armour currently worn in this run."""
    run = run or {}
    armor_key = run.get("equipped_armor_key")
    all_gear = list(ch.get("wargear") or []) + list(run.get("extra_wargear") or [])
    selected = None
    if armor_key:
        selected = next((w for w in all_gear if _inc_is_armour_item(w) and _inc_weapon_key(w) == armor_key), None)
    if selected is None:
        selected = next((w for w in all_gear if _inc_is_armour_item(w) and w.get("equipped", True)), None)
    if selected is None:
        return 0
    details = _gear_details_dict(selected.get("details", {}))
    try:
        m = re.search(r"[0-9]+", str(details.get("armour_rating", "")))
        return int(m.group(0)) if m else 0
    except Exception:
        return 0


def _inc_armour_durability(ch, run):
    armor_key = run.get("equipped_armor_key")
    all_gear = list(run.get("starting_wargear") or []) + list(ch.get("wargear") or []) + list(run.get("extra_wargear") or [])
    destroyed = _inc_destroyed_keys(run)
    selected = None
    if armor_key and str(armor_key) not in destroyed:
        selected = next((w for w in all_gear if _inc_is_armour_item(w) and _inc_weapon_key(w) == armor_key), None)
    if selected is None:
        selected = next((w for w in all_gear if _inc_is_armour_item(w) and _inc_weapon_key(w) not in destroyed and w.get("equipped", True)), None)
    if selected is None:
        return 0, 0
    maximum = _inc_wargear_durability_max(selected)
    current = int(run.get("armour_durability_current", maximum) or maximum)
    stored_max = int(run.get("armour_durability_max", maximum) or maximum)
    if stored_max != maximum:
        current = maximum
    return max(0, min(current, maximum)), maximum


def _inc_player_traits(ch, run):
    """Derived Traits with run-local armour durability applied."""
    merged = _inc_merge_character(ch, run)
    traits = derived_traits(merged)
    # Broken armour is removed from the run loadout, so derived Resilience already reflects its loss.
    return traits


def _inc_life_pools(ch):
    # Incursion life pools are derived only from the character's starting
    # Attributes. Wounds now defaults to 25 at the baseline Toughness (3)
    # rather than a bare 5 - Shock absorbs damage before Wounds do (see
    # _inc_damage_result), so a small Wounds pool read as far too fragile
    # once Shock became the actual first line of defence. +1 Wounds per
    # point of Toughness above baseline is unchanged, so attribute
    # purchases and Origin bonuses still grow it exactly as before.
    # Shock base raised to 15 (at baseline Willpower 3) - with Shock now
    # both a damage buffer and a source of bonus hit dice, a base of 4 ran
    # out (and stopped helping either role) almost immediately.
    attrs={a:int((ch.get("attributes") or {}).get(a,1) or 1) for a in ATTRS}
    return {"wounds_max": int(attrs.get("Toughness",1))+22,
            "shock_max": int(attrs.get("Willpower",1))+12,
            "wrath_max": 2}


def _inc_damage_result(total_damage, resilience, ap=0, shock_current=None, defence=0):
    """Resolve a hit: Resilience (adjusted by Armour Penetration) soaks
    damage like armour, same as before, and that soaked total is what CAN
    drain Shock while any is standing. Once Shock is fully spent, the
    remainder reaching Wounds passes through a second reduction - Defence
    - before it counts as a Wound; being hard to hit still helps even on a
    hit that gets through. shock_current=None (no Shock pool to reference,
    e.g. the compressed offline duel simulation) sends all of the
    Resilience-reduced damage to Wounds, still passing through Defence.
    """
    total_damage = max(0, int(total_damage or 0))
    effective_resilience = max(0, int(resilience or 0) + int(ap or 0))
    net = max(0, total_damage - effective_resilience)
    defence = max(0, int(defence or 0))
    if shock_current is None:
        return 0, max(0, net - defence), effective_resilience
    shock_avail = max(0, int(shock_current or 0))
    shock_dealt = min(net, shock_avail)
    remainder = net - shock_dealt
    wounds_dealt = max(0, remainder - defence)
    return shock_dealt, wounds_dealt, effective_resilience


def _inc_roll_damage(base_damage, ed):
    """Roll a weapon's Extra Damage Dice: each ED die adds its full face
    value to damage. This is NOT the Icon conversion used for to-hit rolls
    (4-5=1, 6=2) - conflating the two made every point of ED worth ~0.67
    damage on average instead of a full d6 (~3.5), which is why almost
    nothing could out-damage Resilience even with a decent-ED weapon."""
    rolls = [random.randint(1, 6) for _ in range(max(0, int(ed or 0)))]
    bonus = sum(rolls)
    return int(base_damage or 0) + bonus, rolls


def _inc_best_weapon(ch):
    attrs = effective_attributes(ch)
    best, best_dmg = None, -10 ** 9
    for w in (ch.get("wargear") or []):
        if not w.get("equipped", True):
            continue
        details = _gear_details_dict(w.get("details", {}))
        if details.get("damage") in (None, ""):
            continue
        dmg = int(details.get("damage_base", _weapon_base_damage(details, attrs)) or _weapon_base_damage(details, attrs))
        if dmg > best_dmg:
            best_dmg = dmg
            best = {
                "name": w.get("name", "Wargear"),
                "damage": dmg,
                "ed": int(details.get("ed", 0) or 0),
                "ap": int(details.get("ap", 0) or 0),
                "melee": bool(details.get("damage_attribute")) or str(details.get("damage", "")).strip().upper().startswith("(S)"),
            }
    if best is None:
        s = int(attrs.get("Strength", 1))
        return {"name": "Unarmed Strike", "damage": s, "ed": 1, "ap": 0, "melee": True}
    return best


def _inc_weapon_key(w):
    cid = _wargear_craft_id(w)
    return str(cid) if cid > 0 else str(w.get("name", ""))


def _inc_is_weapon_item(w):
    d=_gear_details_dict(w.get("details",{})); c=str(d.get("category",d.get("type",""))).lower()
    return c in ("firearm","melee","weapon") or d.get("damage") not in (None,"")


def _inc_usable_weapons(ch, run):
    """Return equipped weapons with their actual W&G damage profile."""
    merged = _inc_merge_character(ch, run)
    attrs = effective_attributes(merged)
    charges = run.get("consumable_charges") or {}
    weapons = []
    destroyed = _inc_destroyed_keys(run)
    for w in (merged.get("wargear") or []):
        if not w.get("equipped", True):
            continue
        key = _inc_weapon_key(w)
        if key in destroyed:
            continue
        details = _gear_details_dict(w.get("details", {}))
        if details.get("damage") in (None, ""):
            continue
        is_stackable, _ = _infer_stackable_gear(w.get("name", ""), details)
        is_consumable = is_stackable and not _is_ammo_resource(w)
        key = _inc_weapon_key(w)
        remaining = None
        if is_consumable:
            remaining = charges.get(key)
            if remaining is None:
                remaining = int(w.get("quantity", 1) or 0)
            if remaining <= 0:
                continue
        base_damage = int(details.get("damage_base", _weapon_base_damage(details, attrs)) or _weapon_base_damage(details, attrs))
        if details.get("damage_attribute"):
            # Stored damage_base is the current run weapon's resolved base and includes upgrades.
            base_damage = int(details.get("damage_base", base_damage) or base_damage)
        else:
            base_damage = int(details.get("damage_base", base_damage) or base_damage)
        durability_current, durability_max = _inc_weapon_durability(ch, run, key, w)
        damage_penalty = durability_max - durability_current
        weapons.append({
            "key": key,
            "name": w.get("name", "Wargear"),
            "damage": max(0, int(base_damage) - damage_penalty),
            "base_damage": int(base_damage),
            "durability_current": durability_current,
            "durability_max": durability_max,
            "ed": int(details.get("ed", 0) or 0),
            "ap": int(details.get("ap", 0) or 0),
            "melee": bool(details.get("damage_attribute")) or str(details.get("damage", "")).strip().upper().startswith("(S)"),
            "consumable": is_consumable,
            "remaining": remaining,
            "minion_support": details.get("minion_support"),
            "support_value": int(details.get("support_value", 0) or 0),
        })
    if not weapons:
        s = int(attrs.get("Strength", 1))
        weapons.append({"key": "__unarmed__", "name": "Unarmed Strike",
                        "damage": s, "ed": 1, "ap": 0, "melee": True,
                        "consumable": False, "remaining": None})
    return weapons


def _inc_weapon_by_key(ch, run, key):
    options = _inc_usable_weapons(ch, run)
    return next((w for w in options if w["key"] == key), options[0])


def _inc_usable_consumables(ch, run):
    """Wargear whose only effect is healing (heal_wounds/heal_shock), with
    no damage profile - these never appeared in _inc_usable_weapons (which
    requires a "damage" field to list anything at all), so a bought Stim
    just sat in the backpack doing nothing, with no action anywhere to
    actually use it."""
    merged = _inc_merge_character(ch, run)
    charges = run.get("consumable_charges") or {}
    out = []
    seen = set()
    for w in (merged.get("wargear") or []):
        if not w.get("equipped", True):
            continue
        details = _gear_details_dict(w.get("details", {}))
        if details.get("damage") not in (None, ""):
            continue
        heal_wounds = int(details.get("heal_wounds", 0) or 0)
        heal_shock = int(details.get("heal_shock", 0) or 0)
        if heal_wounds <= 0 and heal_shock <= 0:
            continue
        key = _inc_weapon_key(w)
        if key in seen:
            continue
        seen.add(key)
        remaining = charges.get(key)
        if remaining is None:
            remaining = int(w.get("quantity", 1) or 0)
        if remaining <= 0:
            continue
        out.append({"key": key, "name": w.get("name", "Item"), "heal_wounds": heal_wounds,
                     "heal_shock": heal_shock, "remaining": remaining,
                     "rarity": str(details.get("rarity") or "Common")})
    return out


def _inc_apply_consumable(run, ch, item_key):
    item = next((i for i in _inc_usable_consumables(ch, run) if i["key"] == item_key), None)
    if item is None: raise ValueError("item_not_found")
    new_wounds = min(int(run.get("wounds_max", 0) or 0), int(run.get("wounds_current", 0) or 0) + item["heal_wounds"])
    new_shock = min(int(run.get("shock_max", 0) or 0), int(run.get("shock_current", 0) or 0) + item["heal_shock"])
    charges = dict(run.get("consumable_charges") or {})
    charges[item_key] = max(0, item["remaining"] - 1)
    return item, new_wounds, new_shock, charges


def _inc_use_consumable(run, ch, item_key):
    """Out-of-combat use (Encampment/Shop/Backpack) - no enemy turn to trigger."""
    item, new_wounds, new_shock, charges = _inc_apply_consumable(run, ch, item_key)
    return _inc_persist(run["id"], wounds_current=new_wounds, shock_current=new_shock, consumable_charges=charges)


def _inc_combat_use_item(run, ch, item_key):
    """In-combat use - costs your turn, same as Medicae/Heal does."""
    if not run.get("node") or run["node"].get("type") != "combat": raise ValueError("wrong_node")
    node = copy.deepcopy(run["node"])
    item, new_wounds, new_shock, charges = _inc_apply_consumable(run, ch, item_key)
    run = _inc_persist(run["id"], consumable_charges=charges)
    log = [{"actor": "player", "action": "use_item", "item": item["name"],
            "heal_wounds": item["heal_wounds"], "heal_shock": item["heal_shock"]}]
    player_traits = _inc_player_traits(ch, run)
    minions = _inc_load_minions(run)
    log += _inc_minion_group_attack(minions, node, _inc_merge_character(ch, run))
    log += _inc_enemy_turn(node.get("enemies", []), player_traits, new_shock, minions)
    run = _inc_persist(run["id"], wounds_current=new_wounds, shock_current=new_shock)
    return _inc_finish_combat_round(run, ch, node, log, minions=minions)


def _inc_best_attack_pool(ch):
    attrs = effective_attributes(ch)
    skills = effective_skills(ch)
    # W&G 2e pools are Attribute + Skill, not the bare Attribute alone - a
    # melee-built character who dumped Initiative/Agility to invest in
    # Weapon/Ballistic Skill was being reduced to a 1-die pool (nearly
    # always missing) despite real combat training, and Bestiary entries'
    # printed pools (e.g. "Ballistic Skill 5") already bake the skill in,
    # so leaving it out here made enemies relatively far more accurate too.
    ws_pool = int(attrs.get("Initiative", 1)) + int(skills.get("Weapon Skill", 0) or 0)
    bs_pool = int(attrs.get("Agility", 1)) + int(skills.get("Ballistic Skill", 0) or 0)
    # Floor of 5, not 3: _inc_merge_character() deliberately zeroes every
    # Incursion character's Skills (real or self-registered), so the Skill
    # term above is ALWAYS 0 for a player - only enemies (built straight
    # from Bestiary sheets, which keep their real skill_map) ever benefit
    # from the Attribute+Skill fix. A book tier-1 threat's printed pool
    # bakes in a skill component of roughly +2 to +5 on top of its
    # Attribute; without an equivalent for players, everyone was stuck at
    # bare Initiative/Agility (often 3, sometimes only the one Origin that
    # happens to buff it) while every enemy rolled meaningfully more dice.
    return ("Weapon Skill", max(5, ws_pool)) if ws_pool >= bs_pool else ("Ballistic Skill", max(5, bs_pool))


def _inc_roll_pool(size):
    rolls = [random.randint(1, 6) for _ in range(max(1, size))]
    icons = sum(2 if r == 6 else (1 if r >= 4 else 0) for r in rolls)
    # One die in the pool is always the Wrath Die (p.158); by convention the
    # last one rolled. A 6 on it is a critical that regains 1 Wrath.
    wrath_crit = rolls[-1] == 6
    return rolls, icons, wrath_crit

def _inc_roll_icons(size):
    rolls = [random.randint(1, 6) for _ in range(max(1, int(size)))]
    icons = sum(2 if r == 6 else (1 if r >= 4 else 0) for r in rolls)
    return rolls, icons


# ---- enemies: Bestiary + fallen players -------------------------------
def _inc_bestiary_by_tier(tier):
    pool = [e for e in _BESTIARY_ENTRIES if e[1] == tier]
    return pool or [e for e in _BESTIARY_ENTRIES if e[1] == 1]


def _inc_scale_factor(loop_no):
    return 1 + (loop_no - 1) * 0.18


def _inc_enemy_sheet(name, tier, species, faction, attrs, skill_pools, wargear, abilities=""):
    """Build an Incursion enemy through the same sheet math as normal NPCs."""
    skill_map = {sk: max(0, int(pool) - int(attrs.get(SKILLS[sk], 1))) for sk, pool in skill_pools.items()}
    sheet = {
        "name": name, "kind": "npc", "species": species, "faction": faction,
        "archetype": f"{name} (Bestiary)", "tier": int(tier), "rank": 1,
        "creation_mode": "archetype", "attributes": dict(attrs), "skills": skill_map,
        "wargear": normalize_wargear(list(wargear or [])),
        "talents": ([{"name": f"{name}, Bestiary Abilities", "effect": abilities, "cost": 0}] if abilities else []),
        "powers": [], "keywords": [],
    }
    gear = equipped_wargear_modifiers(sheet)
    traits = derived_traits(sheet, gear)
    weapon = _inc_best_weapon(sheet)
    atk_skill, atk_pool = _inc_best_attack_pool(sheet)
    return sheet, traits, weapon, atk_skill, atk_pool

def _inc_build_enemy_from_bestiary(entry, loop_no, idx):
    name, tier, species, faction, attrs_list, skill_pools, wargear, abilities = entry
    scale = _inc_scale_factor(loop_no)
    attrs = {a: max(1, round(v + (loop_no - 1) * 0.6)) for a, v in zip(ATTRS, attrs_list)}
    sheet, traits, weapon, atk_skill, atk_pool = _inc_enemy_sheet(
        name, tier, species, faction, attrs, skill_pools, wargear, abilities
    )
    enemy_armour = next((w for w in (sheet.get("wargear") or []) if _inc_is_armour_item(w) and w.get("equipped", True)), None)
    enemy_armour_max = _inc_wargear_durability_max(enemy_armour) if enemy_armour else 0
    enemy_armour_rating = int(_gear_details_dict(enemy_armour.get("details", {})).get("armour_rating", 0) or 0) if enemy_armour else 0
    return {
        "uid": f"b-{name}-{idx}-{random.randint(0, 999999)}", "name": name, "tier": int(tier),
        "species": species, "faction": faction, "attributes": attrs,
        "attack_skill": atk_skill, "attack_pool": max(1, round(atk_pool * (1 + (loop_no - 1) * 0.12))),
        "defence": int(traits["Defence"]), "resilience": int(traits["Resilience"]), "base_resilience": int(traits["Resilience"]),
        "speed": int(traits["Speed"]), "statuses": {},
        "armour_rating": enemy_armour_rating, "armour_durability_max": enemy_armour_max, "armour_durability_current": enemy_armour_max,
        "wounds_max": int(traits["Max Wounds"]), "wounds_current": int(traits["Max Wounds"]),
        "shock_max": int(traits["Max Shock"]), "shock_current": int(traits["Max Shock"]),
        "wrath_current": 2, "wrath_max": 2,
        "weapon_name": weapon["name"] if weapon else (wargear[0] if wargear else "Melee Attack"),
        "weapon_damage": int(round((weapon["damage"] if weapon else 3) * scale)),
        "weapon_ed": int(weapon.get("ed", 1) if weapon else 1),
        "weapon_ap": int(weapon.get("ap", 0) if weapon else 0),
        "alive": True, "fallen": False,
    }

def _inc_fetch_fallen_pool(tier, limit=20):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM incursion_fallen_mob WHERE tier=? ORDER BY RANDOM() LIMIT ?", (tier, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _inc_build_enemy_from_fallen(row, loop_no, idx):
    scale = _inc_scale_factor(loop_no)
    base_attrs = _inc_json_field(row.get("attributes"), {})
    attrs = {k: max(1, round(v + (loop_no - 1) * 0.6)) for k, v in base_attrs.items()}
    tier = int(row["tier"])
    sheet = {
        "name": row["name"], "kind": "npc", "species": row.get("species", "Human"),
        "faction": "Fallen", "tier": tier, "rank": 1, "creation_mode": "advanced",
        "attributes": attrs, "skills": {}, "wargear": [], "talents": [], "powers": [], "keywords": [],
    }
    traits = derived_traits(sheet)
    return {
        "uid": f"f-{row['id']}-{idx}-{random.randint(0, 999999)}", "name": row["name"], "tier": tier,
        "species": row.get("species", ""), "faction": "Fallen", "attributes": attrs,
        "attack_skill": row["attack_skill"],
        "attack_pool": max(1, round(int(row["attack_pool"]) * (1 + (loop_no - 1) * 0.12))),
        "defence": int(traits["Defence"]), "resilience": int(traits["Resilience"]), "base_resilience": int(traits["Resilience"]),
        "speed": int(traits["Speed"]), "statuses": {},
        "armour_rating": 0, "armour_durability_max": 0, "armour_durability_current": 0,
        "wounds_max": int(traits["Max Wounds"]), "wounds_current": int(traits["Max Wounds"]),
        "shock_max": int(traits["Max Shock"]), "shock_current": int(traits["Max Shock"]),
        "wrath_current": 2, "wrath_max": 2,
        "weapon_name": row["weapon_name"], "weapon_damage": round(int(row["weapon_damage"]) * scale),
        "weapon_ed": int(row.get("weapon_ed", 0) or 0), "weapon_ap": int(row.get("weapon_ap", 0) or 0),
        "alive": True, "fallen": True,
    }

def _inc_spawn_group(difficulty, loop_no):
    tier = INC_DIFFICULTY_TIER[difficulty]
    book_pool = _inc_bestiary_by_tier(tier)
    count = 1
    if difficulty == "medium":
        count = 2 if (loop_no >= 2 and random.random() < 0.5) else 1
    if difficulty == "hard":
        count = 2 if random.random() < 0.6 else 1
    if difficulty == "boss":
        count = 1 + int(loop_no - 1) // 4
    # The fallen-mob pool is only ever fetched (one DB round trip, at most
    # once per fight) if the dice actually call for it - most fights never
    # roll a fallen mob at all, so this saves a query on the common path.
    # Never on "easy": a fallen mob's pool/damage come from whatever the
    # source character's real sheet could do at time of death, not a
    # book-balanced tier-1 number - a former player character can hit far
    # harder than a fresh Bestiary Cultist even when correctly filed under
    # tier 1. Reserved for medium/hard/boss, where a rough surprise is
    # appropriate and the player already has some XP or gear.
    fallen_pool = None
    enemies = []
    for i in range(int(count)):
        if difficulty != "easy" and random.random() < INC_FALLEN_CHANCE:
            if fallen_pool is None:
                fallen_pool = _inc_fetch_fallen_pool(tier) or []
            if fallen_pool:
                enemies.append(_inc_build_enemy_from_fallen(random.choice(fallen_pool), loop_no, i))
                continue
        enemies.append(_inc_build_enemy_from_bestiary(random.choice(book_pool), loop_no, i))
    if difficulty == "easy":
        # Book NPC pools already bake in a trained Skill rating on top of
        # the Attribute (an Enforcer or Ork Boy prints pool 6-7), which is
        # fine for a squad fight in the tabletop but murder for a solo
        # Rank-1 operative whose own pool starts at the floor of 3 - the
        # very first, gentlest encounter type was out-dicing the player
        # more than 2:1 before either side rolled a single die.
        for e in enemies:
            e["attack_pool"] = min(int(e["attack_pool"]), INC_EASY_POOL_CAP)
    return enemies


def _inc_tier_for(run):
    power = run["bosses_cleared"] * 2 + (run["loop_no"] - 1)
    return max(1, min(4, 1 + power // 3))


def _inc_record_fallen(ch, run):
    merged = _inc_merge_character(ch, run)
    atk_skill, atk_pool = _inc_best_attack_pool(merged)
    weapon = _inc_best_weapon(merged)
    prefix = random.choice(INC_FALLEN_PREFIXES)
    conn = get_conn()
    conn.execute(
        "INSERT INTO incursion_fallen_mob(source_character_id,name,tier,species,attributes,attack_skill,"
        "attack_pool,weapon_name,weapon_damage,loop_no_reached,bosses_cleared,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (ch["id"], f"{prefix} {ch.get('name', '')}", _inc_tier_for(run), ch.get("species", ""),
         json.dumps(effective_attributes(merged)), atk_skill, atk_pool, weapon["name"], weapon["damage"],
         run["loop_no"], run["bosses_cleared"], now_iso()))
    conn.commit(); conn.close()


# ---- shop --------------------------------------------------------------
def _inc_attribute_cost(current_value):
    return round(15 * (1.6 ** max(0, current_value - 1)))


def _inc_is_psyker(ch):
    skills = ch.get("skills") or {}
    if int(skills.get("Psychic Mastery", 0) or 0) > 0:
        return True
    kws = [str(k).upper() for k in (ch.get("keywords") or [])]
    return any("PSYKER" in k for k in kws)


def _inc_generate_offers(ch, run):
    merged = _inc_merge_character(ch, run)
    attrs = effective_attributes(merged)
    origin = run.get("origin")
    is_tyranid = (origin == "Tyranid-Pattern")
    is_minion_origin = origin in INC_MINION_ORIGINS
    candidates=[]
    for attr in ATTRS:
        cur=int(attrs.get(attr,1)); candidates.append({"type":"attribute","attr":attr,"cost":_inc_attribute_cost(cur),"label":f"+1 {attr}","detail":f"Current: {cur}","rarity":"Common"})
    if is_tyranid:
        # "eles só podem usar coisas de tyranídeos" - a Tyranid run's
        # wargear is ALWAYS drawn from its own bio-wargear pool, never the
        # generic Imperium catalog, and every piece supports the Minions.
        for _ in range(3):
            candidates.append(_inc_generate_tyranid_wargear_offer())
    else:
        pool=[r for r in list_craft_items("wargear", active_only=True) if craft_details(r).get("incursion_only")]
        weapons=[r for r in pool if str(craft_details(r).get("category","")).lower() in ("firearm","melee")]
        armour=[r for r in pool if _inc_is_armour_item({"details":craft_details(r)})]
        consumables=[r for r in pool if str(craft_details(r).get("category","")).lower() in ("consumable","grenade")]
        owned_weapons=[w for w in (merged.get("wargear") or []) if _inc_is_weapon_item(w)]
        talent_rows=[r for r in _inc_talent_pool_rows() if craft_details(next((x for x in list_craft_items("talent",active_only=False) if int(x["id"])==int(r.get("id",-1))),{})).get("incursion_only")]
        def add_random(rows, n=2):
            for row in random.sample(rows,min(n,len(rows))):
                d=craft_details(row); rarity=d.get("rarity","Common")
                candidates.append({"type":"wargear","craft_id":int(row["id"]),"name":row["name"],"effect":row.get("effect",""),"cost":max(10,int(row.get("cost",20) or 20)),"label":row["name"],"detail":f"{rarity} · {row.get('effect','')}","rarity":rarity})
        add_random(weapons,2)
        add_random(armour,1)
        add_random(consumables,1)
    # Talent offers: a Tyranid-Pattern run's Talents are ALWAYS Minion
    # Talents only, never the general combat pool - "os tyranídios só têm
    # talentos relacionados a minions". Human (the other Minion-eligible
    # Origin) mixes both pools; everyone else never sees a Minion Talent.
    if not is_tyranid:
        talent_catalog={int(r["id"]):r for r in list_craft_items("talent",active_only=False)}
        available_talents=[]
        for pr in _inc_talent_pool_rows():
            row=next((r for r in talent_catalog.values() if str(r["name"]).lower()==str(pr["name"]).lower()),None)
            if row: available_talents.append((row,pr))
        for row,pr in random.sample(available_talents,min(2,len(available_talents))):
            d=craft_details(row); candidates.append({"type":"talent","craft_id":int(row["id"]),"name":row["name"],"effect":row.get("effect",""),"cost":max(15,int(row.get("cost",30) or 30)),"label":row["name"],"detail":f"{pr['rarity']} · {row.get('effect','')}","rarity":pr['rarity']})
    if is_minion_origin:
        n = 2 if is_tyranid else 1
        for mt in random.sample(INC_MINION_TALENTS, min(n, len(INC_MINION_TALENTS))):
            cost = max(15, INC_MINION_RARITY_STATS[mt["rarity"]]["cost"])
            candidates.append({"type":"talent_minion","name":mt["name"],"effect":mt["effect"],"cost":cost,
                                "label":mt["name"],"detail":f"{mt['rarity']} · {mt['effect']}","rarity":mt["rarity"]})
    candidates.append({"type":"heal_charge","cost":20,"label":"Medicae Ration","detail":"+1 Medicae use in combat","rarity":"Common"})
    picked = random.sample(candidates, min(3, len(candidates))) if candidates else []
    # Minions get a GUARANTEED slot for Human/Tyranid runs, every shop -
    # "toda loja de boss aparece pelo menos 1" (and every other shop too).
    if is_minion_origin:
        minion_offer = _inc_generate_minion_offer(origin)
        if picked: picked[0] = minion_offer
        else: picked = [minion_offer]
    return [{**o,"offer_id":i} for i,o in enumerate(picked[:3])]

def _inc_generate_first_encampment_offers(ch, run):
    """The very first choice of an Incursion, and only this one: exactly two
    Wargear items plus one Talent, all free - pick ONE, the rest are lost.
    A dedicated pool rather than _inc_generate_offers()'s general random mix,
    so a fresh run never opens on three Attribute offers with nothing to
    actually equip."""
    merged = _inc_merge_character(ch, run)
    pool = [r for r in list_craft_items("wargear", active_only=True) if craft_details(r).get("incursion_only")]
    weapons = [r for r in pool if str(craft_details(r).get("category", "")).lower() in ("firearm", "melee")]
    armour = [r for r in pool if _inc_is_armour_item({"details": craft_details(r)})]
    item_rows = random.sample(weapons, min(1, len(weapons))) + random.sample(armour, min(1, len(armour)))
    remaining_pool = [r for r in pool if r not in item_rows]
    while len(item_rows) < 2 and remaining_pool:
        item_rows.append(remaining_pool.pop(random.randrange(len(remaining_pool))))

    candidates = []
    for row in item_rows:
        d = craft_details(row)
        rarity = d.get("rarity", "Common")
        candidates.append({"type": "wargear", "craft_id": int(row["id"]), "name": row["name"],
                            "effect": row.get("effect", ""), "cost": 0,
                            "label": row["name"], "detail": f"{rarity} · {row.get('effect', '')}",
                            "rarity": rarity, "first_encampment_free": True})

    talent_catalog = {int(r["id"]): r for r in list_craft_items("talent", active_only=False)}
    available_talents = []
    for pr in _inc_talent_pool_rows():
        row = next((r for r in talent_catalog.values() if str(r["name"]).lower() == str(pr["name"]).lower()), None)
        if row and craft_details(row).get("incursion_only"):
            available_talents.append((row, pr))
    if available_talents:
        row, pr = random.choice(available_talents)
        candidates.append({"type": "talent", "craft_id": int(row["id"]), "name": row["name"],
                            "effect": row.get("effect", ""), "cost": 0, "label": row["name"],
                            "detail": f"{pr['rarity']} · {row.get('effect', '')}", "rarity": pr['rarity'],
                            "first_encampment_free": True})

    return [{**o, "offer_id": i} for i, o in enumerate(candidates)]


def _inc_pool_updates_for_attribute(ch, run, bonus_attrs, attr):
    """When a purchased Attribute is Toughness or Willpower, Max Wounds/Max
    Shock grow immediately - recompute them and carry the current value's
    absolute increase over to current, same as leveling up would on the
    real sheet."""
    if attr not in ("Toughness", "Willpower"):
        return {}
    merged = _inc_merge_character(ch, {**run, "bonus_attributes": bonus_attrs})
    pools = _inc_life_pools(merged)
    updates = {}
    if attr == "Toughness":
        delta = max(0, pools["wounds_max"] - run["wounds_max"])
        updates["wounds_max"] = pools["wounds_max"]
        updates["wounds_current"] = min(pools["wounds_max"], run["wounds_current"] + delta)
    if attr == "Willpower":
        delta = max(0, pools["shock_max"] - run["shock_max"])
        updates["shock_max"] = pools["shock_max"]
        updates["shock_current"] = min(pools["shock_max"], run["shock_current"] + delta)
    return updates


def _inc_apply_purchase(run, ch, offer):
    if run["xp"] < offer["cost"]: raise ValueError("not_enough_xp")
    bonus_attrs=dict(run.get("bonus_attributes") or {})
    starting_wargear=list(run.get("starting_wargear") or [])
    extra_wargear=list(run.get("extra_wargear") or [])
    extra_talents=normalize_talents(run.get("extra_talents") or [])
    extra_keywords=list(run.get("extra_keywords") or []); heal_charges=int(run.get("heal_charges",1) or 0); pool_updates={}
    if offer["type"]=="attribute":
        bonus_attrs[offer["attr"]]=int(bonus_attrs.get(offer["attr"],0))+1
        pool_updates.update(_inc_pool_updates_for_attribute(ch,run,bonus_attrs,offer["attr"]))
    elif offer["type"]=="talent":
        row=_inc_talent_catalog_row({"craft_id":offer["craft_id"]})
        if row is None: raise ValueError("item_not_found")
        name=str(row["name"]); rarity,max_stacks=_inc_talent_rarity(name)
        current=next((x for x in extra_talents if str(x.get("name","")).lower()==name.lower()),None)
        current_stacks=int(current.get("stacks",1)) if current else 0
        if current_stacks>=max_stacks: raise ValueError("talent_stack_limit")
        if not _inc_pool_claim_talent(name): raise ValueError("talent_unavailable")
        if current: current["stacks"]=current_stacks+1
        else:
            entry=_build_craft_entry(row,"talent"); entry.update({"rarity":rarity,"max_stacks":max_stacks,"stacks":1}); extra_talents.append(entry)
        shock_bonus=_INC_TALENT_SHOCK_BONUS.get(rarity,2)
        new_shock_max=int(run.get("shock_max",0) or 0)+shock_bonus
        pool_updates.update({"shock_max":new_shock_max,"shock_current":min(new_shock_max,int(run.get("shock_current",0) or 0)+shock_bonus)})
    elif offer["type"]=="wargear":
        conn=get_conn(); row=conn.execute("SELECT * FROM craft_items WHERE id=? AND kind='wargear'",(int(offer["craft_id"]),)).fetchone(); conn.close()
        if row is None: raise ValueError("item_not_found")
        entry=_build_craft_entry(row,"wargear")
        if _inc_is_armour_item(entry):
            # Only one armour exists in the run. A new suit permanently replaces the old one.
            starting_wargear=[w for w in starting_wargear if not _inc_is_armour_item(w)]
            extra_wargear=[w for w in extra_wargear if not _inc_is_armour_item(w)]
            extra_wargear.append(entry)
            key=_inc_weapon_key(entry); maximum=_inc_wargear_durability_max(entry)
            pool_updates.update({"equipped_armor_key":key,"armour_durability_current":maximum,"armour_durability_max":maximum})
        elif _inc_is_weapon_item(entry):
            same=next((w for w in starting_wargear+extra_wargear if _inc_weapon_key(w)==_inc_weapon_key(entry)),None)
            if same:
                d=_gear_details_dict(same.get("details",{})); level=min(5,int(d.get("incursion_level",1) or 1)+1); d["incursion_level"]=level
                d["upgrade_bonus"]=int(d.get("upgrade_bonus",0) or 0)+2
                d["damage_base"]=_weapon_base_damage(d,effective_attributes(_inc_merge_character(ch,{**run,"starting_wargear":starting_wargear,"extra_wargear":extra_wargear})))+2
                if level%2==0: d["ed"]=int(d.get("ed",0) or 0)+1
                same["details"]=d
            else:
                if sum(1 for w in starting_wargear+extra_wargear if _inc_is_weapon_item(w))>=3: raise ValueError("weapon_limit")
                d=_gear_details_dict(entry.get("details",{})); d["incursion_level"]=1; d["damage_base"]=_weapon_base_damage(d,effective_attributes(_inc_merge_character(ch,{**run,"starting_wargear":starting_wargear,"extra_wargear":extra_wargear}))); entry["details"]=d
                extra_wargear.append(entry)
        else:
            existing=next((w for w in extra_wargear if int(w.get("craft_id",-1) or -1)==int(entry.get("craft_id",-2))),None)
            if existing: existing["quantity"]=int(existing.get("quantity",1))+1
            else: extra_wargear.append(entry)
    elif offer["type"]=="heal_charge": heal_charges+=1
    elif offer["type"]=="minion":
        # Always active the instant it's bought, no separate equip step.
        # A DIFFERENT Minion stacks alongside any you already have; buying
        # the SAME one again levels it up (full heal, better stats)
        # instead of adding a duplicate.
        current_minions=[dict(m) for m in (run.get("minions") or [])]
        existing=next((m for m in current_minions if m.get("name")==offer["name"]),None)
        icon=offer.get("icon","🐾")
        if existing:
            new_level=int(existing.get("level",1) or 1)+1
            leveled=_inc_minion_stats(offer["name"],icon,offer["origin"],offer["rarity"],new_level)
            current_minions=[leveled if m.get("name")==offer["name"] else m for m in current_minions]
        else:
            current_minions.append(_inc_minion_stats(offer["name"],icon,offer["origin"],offer["rarity"],1))
        pool_updates["minions"]=current_minions
    elif offer["type"]=="talent_minion":
        name=offer["name"]; rarity=offer.get("rarity","Common")
        current=next((x for x in extra_talents if str(x.get("name","")).lower()==name.lower()),None)
        if current: current["stacks"]=int(current.get("stacks",1) or 1)+1
        else: extra_talents.append({"name":name,"effect":offer.get("effect",""),"rarity":rarity,"cost":offer["cost"],"stacks":1,"max_stacks":5})
        shock_bonus=_INC_TALENT_SHOCK_BONUS.get(rarity,2)
        new_shock_max=int(run.get("shock_max",0) or 0)+shock_bonus
        pool_updates.update({"shock_max":new_shock_max,"shock_current":min(new_shock_max,int(run.get("shock_current",0) or 0)+shock_bonus)})
    elif offer["type"]=="tyranid_wargear":
        if sum(1 for w in starting_wargear+extra_wargear if _inc_is_weapon_item(w))>=3: raise ValueError("weapon_limit")
        entry={"name":offer["name"],"effect":offer.get("effect",""),"equipped":True,"quantity":1,
               "details":{"category":"melee weapon" if offer.get("melee") else "firearm",
                          "damage":str(offer["damage"]),"ed":int(offer.get("ed",0) or 0),"ap":int(offer.get("ap",0) or 0),
                          "rarity":offer["rarity"],"incursion_only":True,"stackable":False,
                          "minion_support":offer.get("minion_support"),"support_value":int(offer.get("support_value",0) or 0)}}
        extra_wargear.append(entry)
    elif offer["type"]=="tyranid_armour":
        entry={"name":offer["name"],"effect":offer.get("effect","Tyranid bio-armour."),"equipped":True,"quantity":1,
               "details":{"category":"armour","armour_rating":int(offer["armour_rating"]),"rarity":offer["rarity"],
                          "incursion_only":True,"stackable":False}}
        starting_wargear=[w for w in starting_wargear if not _inc_is_armour_item(w)]
        extra_wargear=[w for w in extra_wargear if not _inc_is_armour_item(w)]
        extra_wargear.append(entry)
        key=_inc_weapon_key(entry); maximum=_inc_wargear_durability_max(entry)
        pool_updates.update({"equipped_armor_key":key,"armour_durability_current":maximum,"armour_durability_max":maximum})
    else: raise ValueError("unknown_offer_type")
    updated=_inc_persist(run["id"],xp=run["xp"]-offer["cost"],bonus_attributes=bonus_attrs,starting_wargear=starting_wargear,extra_wargear=extra_wargear,extra_talents=extra_talents,extra_powers=[],extra_keywords=extra_keywords,heal_charges=heal_charges,**pool_updates)
    if offer["type"]=="wargear":
        allgear=updated.get("starting_wargear",[])+updated.get("extra_wargear",[])
        added=next((w for w in allgear if int(w.get("craft_id",-1) or -1)==int(offer.get("craft_id",-2))),None)
        if added and _inc_is_weapon_item(added):
            vals=_inc_weapon_durability_map(updated); key=_inc_weapon_key(added); vals.setdefault(key,_inc_wargear_durability_max(added)); updated=_inc_persist(updated["id"],weapon_durabilities=vals)
    elif offer["type"]=="tyranid_wargear":
        allgear=updated.get("starting_wargear",[])+updated.get("extra_wargear",[])
        added=next((w for w in allgear if w.get("name")==offer["name"]),None)
        if added:
            vals=_inc_weapon_durability_map(updated); key=_inc_weapon_key(added); vals.setdefault(key,_inc_wargear_durability_max(added)); updated=_inc_persist(updated["id"],weapon_durabilities=vals)
    return updated


# ---- post-combat reward choice -----------------------------------------
_INC_RARITY_RANK = {"Common": 0, "Uncommon": 1, "Rare": 2, "Legendary": 3, "Unique": 4}


def _inc_reward_min_rarity(difficulty, enemy_count):
    """Reward quality floor for the post-combat choice: scales with how
    hard the fight was - its Difficulty tier, bumped a notch further if it
    was a multi-enemy fight."""
    tier = {"easy": 0, "medium": 1, "hard": 2, "boss": 3}.get(difficulty, 0)
    if int(enemy_count or 0) >= 2:
        tier += 1
    return min(3, tier)


def _inc_generate_post_combat_offers(ch, run, node):
    """Exactly 3 FREE reward options after any combat victory - quality
    floor scales with the difficulty just cleared and the enemy count. A
    boss kill instead offers 3 Talents to choose from (a free Talent for
    downing a Champion), never wargear or attributes."""
    difficulty = str(node.get("difficulty", "easy"))
    enemy_count = len(node.get("enemies", []) or [])
    talent_catalog = {int(r["id"]): r for r in list_craft_items("talent", active_only=False)}

    def talent_candidates(min_rank):
        out = []
        for pr in _inc_talent_pool_rows():
            row = next((r for r in talent_catalog.values() if str(r["name"]).lower() == str(pr["name"]).lower()), None)
            if row and craft_details(row).get("incursion_only") and _INC_RARITY_RANK.get(pr["rarity"], 0) >= min_rank:
                out.append((row, pr))
        return out

    if difficulty == "boss":
        available = talent_candidates(0)
        candidates = []
        for row, pr in random.sample(available, min(3, len(available))):
            candidates.append({"type": "talent", "craft_id": int(row["id"]), "name": row["name"],
                                "effect": row.get("effect", ""), "cost": 0, "label": row["name"],
                                "detail": f"{pr['rarity']} · {row.get('effect', '')}", "rarity": pr["rarity"]})
        return [{**o, "offer_id": i} for i, o in enumerate(candidates)]

    min_rank = _inc_reward_min_rarity(difficulty, enemy_count)
    pool = [r for r in list_craft_items("wargear", active_only=True) if craft_details(r).get("incursion_only")]
    def rank_of(row):
        return _INC_RARITY_RANK.get(craft_details(row).get("rarity", "Common"), 0)
    filtered = [r for r in pool if rank_of(r) >= min_rank] or pool
    wargear_candidates = filtered

    available_talents = talent_candidates(min_rank) or talent_candidates(0)

    candidates = []
    attrs = effective_attributes(_inc_merge_character(ch, run))
    for row in random.sample(wargear_candidates, min(2, len(wargear_candidates))):
        d = craft_details(row); rarity = d.get("rarity", "Common")
        candidates.append({"type": "wargear", "craft_id": int(row["id"]), "name": row["name"],
                            "effect": row.get("effect", ""), "cost": 0, "label": row["name"],
                            "detail": f"{rarity} · {row.get('effect', '')}", "rarity": rarity})
    if available_talents:
        row, pr = random.choice(available_talents)
        candidates.append({"type": "talent", "craft_id": int(row["id"]), "name": row["name"],
                            "effect": row.get("effect", ""), "cost": 0, "label": row["name"],
                            "detail": f"{pr['rarity']} · {row.get('effect', '')}", "rarity": pr["rarity"]})
    while len(candidates) < 3:
        attr = random.choice(ATTRS); cur = int(attrs.get(attr, 1))
        candidates.append({"type": "attribute", "attr": attr, "cost": 0, "label": f"+1 {attr}",
                            "detail": f"Current: {cur}", "rarity": "Common"})
    return [{**o, "offer_id": i} for i, o in enumerate(candidates[:3])]


def _inc_post_combat_loot(run, ch, node):
    offers = _inc_generate_post_combat_offers(ch, run, node)
    subtype = "boss" if node.get("difficulty") == "boss" else "combat"
    return _inc_persist(run["id"], node={"type": "reward_choice", "subtype": subtype, "offers": offers,
                                          "reward_xp": int(node.get("reward_xp", 0) or 0)})


def _inc_reward_choice_take(run, ch, offer_id):
    node = run.get("node") or {}
    if node.get("type") != "reward_choice": raise ValueError("wrong_node")
    offer = next((o for o in node.get("offers", []) if o.get("offer_id") == offer_id), None)
    if offer is None: raise ValueError("offer_not_found")
    updated = _inc_apply_purchase(run, ch, offer)
    return _inc_advance(updated, ch)

# ---- node/stage state machine -----------------------------------------
INC_RUN_ESCALATION_PER_ATTEMPT = 0.35  # extra "loops" worth of scaling per attempt past the grace window
INC_RUN_ESCALATION_GRACE_ATTEMPTS = 2  # this many attempts (run_number 1, 2) get zero bonus - no punishing an early death
INC_RUN_ESCALATION_CAP = 4.0           # hard ceiling, however many times this character has tried


def _inc_effective_loop(run):
    """The loop_no actually fed to enemy scaling: this run's own progress
    PLUS a small, capped bump from previous attempts (dead or not) beyond
    a short grace window - so a long-time veteran sees a harder world, but
    someone who just died on attempt 2 does NOT get punished with an even
    tougher attempt 3. Uncapped, this used to compound (1.5 loops per
    attempt, no grace, no ceiling) into effectively unwinnable openings for
    exactly the players who most needed an easy one - a character with 13
    prior deaths was inheriting +18 effective loops on their very first,
    supposedly-easiest fight."""
    run_number = int(run.get("run_number", 1) or 1)
    attempts_past_grace = max(0, run_number - INC_RUN_ESCALATION_GRACE_ATTEMPTS)
    bonus = min(INC_RUN_ESCALATION_CAP, attempts_past_grace * INC_RUN_ESCALATION_PER_ATTEMPT)
    return run["loop_no"] + bonus


def _inc_scaled_xp(base, loop_no):
    return round(base * (1 + (loop_no - 1) * 0.15))


def _inc_combat_node(difficulty, loop_no, subtype=None):
    return {
        "type": "combat", "difficulty": difficulty, "subtype": subtype,
        "enemies": _inc_spawn_group(difficulty, loop_no), "log": [],
        "reward_xp": _inc_scaled_xp(INC_REWARD_XP[difficulty], loop_no), "resolved": False,
    }


def _inc_build_node_for_stage(stage, ch, run):
    eff_loop = _inc_effective_loop(run)
    if stage == "start":
        return {"type": "choice_start"}
    if stage == "easy":
        return _inc_combat_node("easy", eff_loop)
    if stage == "random":
        roll = random.random()
        if roll < 0.4:
            return _inc_combat_node("medium", eff_loop, subtype="ambush")
        if roll < 0.7:
            return {"type": "shop", "subtype": "random", "offers": _inc_generate_offers(ch, run)}
        return {"type": "reward", "subtype": "random", "xp_bonus": _inc_scaled_xp(20, eff_loop)}
    if stage == "medium":
        return _inc_combat_node("medium", eff_loop)
    if stage == "pvp_mid":
        return {"type": "pvp_choice", "checkpoint": "mid"}
    if stage == "hard":
        return _inc_combat_node("hard", eff_loop)
    if stage == "boss":
        return _inc_combat_node("boss", eff_loop)
    if stage == "pvp_boss3":
        return {"type": "pvp_choice", "checkpoint": "boss3"}
    return {"type": "choice_start"}


def _inc_stage_after(run):
    if run["stage"] == "boss" and run["pending_boss3_pvp"]:
        return "pvp_boss3"
    if run["stage"] in ("boss", "pvp_boss3"):
        return "start"
    i = INC_SEQUENCE.index(run["stage"])
    return INC_SEQUENCE[(i + 1) % len(INC_SEQUENCE)]


def _inc_advance(run, ch):
    nxt = _inc_stage_after(run)
    loop_no = run["loop_no"] + 1 if nxt == "start" else run["loop_no"]
    pending_clear = False if run["stage"] in ("boss", "pvp_boss3") else run["pending_boss3_pvp"]
    node = _inc_build_node_for_stage(nxt, ch, {**run, "loop_no": loop_no})
    return _inc_persist(run["id"], stage=nxt, loop_no=loop_no, pending_boss3_pvp=pending_clear, node=node)


def _inc_mark_dead(run, ch, reason):
    try: _inc_record_fallen(ch, run)
    except Exception: pass
    # Physical talent copies return to the global Incursion pool only when the owner dies.
    for t in normalize_talents(run.get("extra_talents") or []):
        _inc_pool_release_talent(str(t.get("name","")), int(t.get("stacks",1) or 1))
    conn=get_conn(); conn.execute("UPDATE incursion_run SET status='dead', ended_at=?, death_reason=?, wounds_current=0 WHERE id=?",(now_iso(),reason,run["id"])); conn.commit(); conn.close()
    return _inc_get_run(run["id"])


## Guaranteed the moment starting_wargear turns out to have no weapon at all
## (a caster/support character, or a fresh account with an empty sheet) -
## nobody should start an Incursion able to only throw fists.
INC_STANDARD_WEAPON = {
    "name": "Incursion Combat Knife", "effect": "Standard Incursion sidearm.", "equipped": True, "quantity": 1,
    "details": {"category": "melee weapon", "damage": "(S) +2", "damage_attribute": "Strength", "ed": 1, "ap": 0,
                "rarity": "Common", "incursion_only": True, "stackable": False},
}


def _inc_start_run(ch, origin=None):
    if _inc_get_active_run(ch["id"]):
        raise ValueError("run_already_active")
    # An incursion-kind account has no real sheet - Origin is chosen fresh
    # each run (see _inc_render_origin_select) and its Attributes are used
    # in place of whatever is on the stored row, which is just a flat,
    # unused baseline. A real campaign character (origin=None) is
    # unaffected and keeps using its actual sheet, as before.
    run_ch = ch
    origin_talent = None
    if origin and ch.get("kind") == "incursion" and origin in INC_ORIGINS:
        run_ch = dict(ch); run_ch["attributes"] = _inc_origin_attributes(origin)
        origin_talent = dict(INC_ORIGIN_TALENTS[origin])
    pools = _inc_life_pools(run_ch)
    starting_wargear = [dict(w) for w in (run_ch.get("wargear") or []) if not _inc_is_armour_item(w) and w.get("equipped", True)]
    _start_weapons=[w for w in starting_wargear if _inc_is_weapon_item(w)]
    _start_nonweapons=[w for w in starting_wargear if not _inc_is_weapon_item(w)]
    if not _start_weapons:
        _start_weapons = [dict(INC_STANDARD_WEAPON)]
    starting_wargear=_start_weapons[:3]+_start_nonweapons
    standard_armour = {"name":"Incursion Field Plate","effect":"Standard Incursion armour. Armour Rating +2.","equipped":True,"quantity":1,
                       "details":{"category":"armour","armour_rating":2,"rarity":"Common","incursion_only":True,"stackable":False}}
    starting_wargear.append(standard_armour)
    extra_talents = [origin_talent] if origin_talent else []
    first_run_stub = {"bonus_attributes": {}, "bonus_skills": {}, "extra_wargear": [], "starting_wargear": starting_wargear,
                      "extra_talents": extra_talents, "extra_powers": [], "equipped_armor_key": _inc_weapon_key(standard_armour)}
    first_offers = _inc_generate_first_encampment_offers(run_ch, first_run_stub)
    first_node = {"type": "shop", "subtype": "first_encampment", "offers": first_offers}
    initial_armour_key = _inc_weapon_key(standard_armour)
    armour_max = _inc_wargear_durability_max(standard_armour)
    weapon_values = {}
    for w in starting_wargear:
        details = _gear_details_dict(w.get("details", {}))
        if w.get("equipped", True) and details.get("damage") not in (None, ""):
            weapon_values[_inc_weapon_key(w)] = _inc_wargear_durability_max(w)
    conn = get_conn()
    # Each prior run (dead or otherwise) this character has started makes the
    # Bestiary hit harder from the first fight of this new one - see
    # _inc_combat_node()'s use of run_number. Counted, not stored per-run
    # elsewhere, so it survives across every future attempt automatically.
    run_number = int((conn.execute("SELECT COUNT(*) AS n FROM incursion_run WHERE character_id=?", (ch["id"],)).fetchone() or {"n": 0})["n"]) + 1
    cur = conn.execute(
        "INSERT INTO incursion_run(character_id,status,stage,loop_no,run_number,wounds_current,wounds_max,"
        "shock_current,shock_max,wrath_current,wrath_max,xp,xp_earned,armour_durability_current,"
        "armour_durability_max,weapon_durabilities,incursion_statuses,node,created_at,equipped_armor_key,starting_wargear,"
        "extra_talents,origin) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (ch["id"], "active", "start", 1, run_number, pools["wounds_max"], pools["wounds_max"],
         pools["shock_max"], pools["shock_max"], pools["wrath_max"], pools["wrath_max"], 0, 0,
         armour_max, armour_max, json.dumps(weapon_values), json.dumps({}), json.dumps(first_node), now_iso(), initial_armour_key, json.dumps(starting_wargear),
         json.dumps(extra_talents), origin or ""))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return _inc_get_run(new_id)


def _inc_choose_start(run, ch, choice):
    if not run.get("node") or run["node"].get("type") != "choice_start":
        raise ValueError("wrong_node")
    if choice == "rest":
        heal = max(1, round(run["wounds_max"] * INC_REST_HEAL_FRACTION))
        run, repaired, armour_gain = _inc_recover_rest_durability(run, ch)
        run = _inc_persist(run["id"], wounds_current=min(run["wounds_max"], run["wounds_current"] + heal),
                            shock_current=run["shock_max"], node={"type": "rest_upgrade"},
                            minions=_inc_revive_minions(run))
        return run
    if choice == "first_encampment":
        offers = _inc_generate_first_encampment_offers(ch, run)
        return _inc_persist(run["id"], node={"type": "shop", "subtype": "first_encampment", "offers": offers})
    if choice == "shop":
        return _inc_persist(run["id"], node={"type": "shop", "subtype": "start", "offers": _inc_generate_offers(ch, run)})
    raise ValueError("invalid_choice")


def _inc_skill_cost(current_value):
    return round(12 * (1.5 ** max(0, current_value)))


def _inc_rest_train_attribute(run, ch, attr):
    free = not run["free_upgrade_used"]
    merged = _inc_merge_character(ch, run)
    cost = 0 if free else _inc_attribute_cost(int(effective_attributes(merged).get(attr, 1)))
    if run["xp"] < cost:
        raise ValueError("not_enough_xp")
    bonus_attrs = dict(run.get("bonus_attributes") or {})
    bonus_attrs[attr] = int(bonus_attrs.get(attr, 0)) + 1
    pool_updates = _inc_pool_updates_for_attribute(ch, run, bonus_attrs, attr)
    return _inc_persist(run["id"], xp=run["xp"] - cost, bonus_attributes=bonus_attrs,
                         free_upgrade_used=True, **pool_updates)


def _inc_rest_train_skill(run, ch, skill):
    free = not run["free_upgrade_used"]
    merged = _inc_merge_character(ch, run)
    cost = 0 if free else _inc_skill_cost(int(effective_skills(merged).get(skill, 0)))
    if run["xp"] < cost:
        raise ValueError("not_enough_xp")
    bonus_skills = dict(run.get("bonus_skills") or {})
    bonus_skills[skill] = int(bonus_skills.get(skill, 0)) + 1
    return _inc_persist(run["id"], xp=run["xp"] - cost, bonus_skills=bonus_skills, free_upgrade_used=True)


def _inc_rest_set_armour(run, ch, armour_key):
    # A loadout choice, not a purchase. Rest also restores the selected armour.
    rating = 0
    for option in _inc_armour_options(ch, run):
        if option["key"] == armour_key:
            all_gear = list(run.get("starting_wargear") or []) + list(run.get("extra_wargear") or [])
            item = next((w for w in all_gear if _inc_weapon_key(w) == armour_key and _inc_is_armour_item(w)), None)
            rating = _inc_wargear_durability_max(item) if item else 0
            break
    return _inc_persist(run["id"], equipped_armor_key=armour_key,
                        armour_durability_current=rating, armour_durability_max=rating)


def _inc_rest_continue(run, ch):
    if not run.get("node") or run["node"].get("type") != "rest_upgrade":
        raise ValueError("wrong_node")
    return _inc_advance(run, ch)


def _inc_shop_buy(run, ch, offer_id):
    if not run.get("node") or run["node"].get("type") != "shop": raise ValueError("wrong_node")
    offer=next((o for o in run["node"].get("offers",[]) if o.get("offer_id")==offer_id),None)
    if offer is None: raise ValueError("offer_not_found")
    updated=_inc_apply_purchase(run,ch,offer)
    remaining=[o for o in run["node"].get("offers",[]) if o.get("offer_id")!=offer_id]
    node=dict(updated["node"]); node["offers"]=remaining
    return _inc_persist(updated["id"],node=node)


def _inc_generate_free_reroll_offer(ch, run):
    """One replacement offer for a First Encampment reroll, drawn from the
    same broad mix a normal shop uses (attribute/wargear/talent/heal_charge) -
    not just wargear, since rerolling a weapon or armour slot is explicitly
    NOT meant to guarantee another weapon or armour back. Always free: it is
    still part of the free starting kit, just reshuffled."""
    picked = dict(random.choice(_inc_generate_offers(ch, run)))
    picked["cost"] = 0
    picked["first_encampment_free"] = True
    return picked


def _inc_shop_reroll(run, ch, offer_id):
    if not run.get("node") or run["node"].get("type") != "shop" or run["node"].get("subtype") != "first_encampment":
        raise ValueError("wrong_node")
    offers = run["node"].get("offers", [])
    if not any(o.get("offer_id") == offer_id for o in offers):
        raise ValueError("offer_not_found")
    rerolled = set(run["node"].get("rerolled_ids") or [])
    if offer_id in rerolled:
        raise ValueError("reroll_already_used")
    new_offer = _inc_generate_free_reroll_offer(ch, run)
    new_offer["offer_id"] = offer_id
    updated_offers = [new_offer if o.get("offer_id") == offer_id else o for o in offers]
    rerolled.add(offer_id)
    node = dict(run["node"]); node["offers"] = updated_offers; node["rerolled_ids"] = sorted(rerolled)
    return _inc_persist(run["id"], node=node)


def _inc_shop_leave(run, ch):
    return _inc_advance(run, ch)


def _inc_reward_continue(run, ch):
    if not run.get("node") or run["node"].get("type") != "reward":
        raise ValueError("wrong_node")
    run = _inc_persist(run["id"], xp=run["xp"] + run["node"]["xp_bonus"], xp_earned=run.get("xp_earned", 0) + run["node"]["xp_bonus"])
    return _inc_advance(run, ch)


# ---- combat --------------------------------------------------------------
def _inc_pool_claim_talent(name):
    conn = get_conn()
    row = conn.execute("UPDATE incursion_talent_pool SET pool_available=pool_available-1 WHERE name=? AND pool_available>0", (name,))
    if getattr(row, "rowcount", 0) != 1:
        conn.rollback(); conn.close(); return False
    conn.commit(); conn.close(); return True


def _inc_pool_release_talent(name, amount=1):
    amount=max(0,int(amount or 0))
    if amount <= 0: return
    conn=get_conn(); conn.execute("UPDATE incursion_talent_pool SET pool_available=CASE WHEN pool_available+?>pool_total THEN pool_total ELSE pool_available+? END WHERE name=?", (amount,amount,name)); conn.commit(); conn.close()


def _inc_talent_rarity(name):
    conn=get_conn(); row=conn.execute("SELECT rarity,max_stacks FROM incursion_talent_pool WHERE lower(name)=lower(?)", (name,)).fetchone(); conn.close()
    if row: return str(row["rarity"]), int(row["max_stacks"])
    return "Common", 5


def _inc_talent_pool_rows():
    conn=get_conn(); rows=conn.execute("SELECT * FROM incursion_talent_pool WHERE pool_available>0 ORDER BY RANDOM()").fetchall(); conn.close(); return [dict(r) for r in rows]


def _inc_talent_count(ch, run, name):
    target = str(name).strip().lower()
    merged = _inc_merge_character(ch, run)
    return sum(max(1, int(x.get("stacks", 1) or 1)) for x in normalize_talents(merged.get("talents", []))
               if str(x.get("name", "")).strip().lower() == target)

def _inc_talent_names(ch, run):
    merged = _inc_merge_character(ch, run)
    return {str(x.get("name", "")).strip().lower() for x in normalize_talents(merged.get("talents", []))}

def _inc_talent_has(ch, run, name):
    return _inc_talent_count(ch, run, name) > 0

def _inc_talent_status(run):
    return dict(run.get("incursion_statuses") or {})

def _inc_talent_persist_status(run, statuses):
    return _inc_persist(run["id"], incursion_statuses=statuses)

def _inc_record_wrath_spend(run, ch, amount):
    amount = max(0, int(amount or 0))
    if amount <= 0:
        return run
    if not _inc_talent_has(ch, run, "Wrathforged") and not _inc_talent_has(ch, run, "Iron Discipline"):
        return run
    statuses = _inc_talent_status(run)
    perm = dict(statuses.get("talent_permanent_attributes") or {})
    wrathforged = _inc_talent_count(ch, run, "Wrathforged")
    iron = _inc_talent_count(ch, run, "Iron Discipline")
    if wrathforged:
        perm["Strength"] = int(perm.get("Strength", 0) or 0) + amount * wrathforged
    if iron:
        bank = int(statuses.get("iron_discipline_wrath_bank", 0) or 0) + amount
        gains = bank // 3
        if gains:
            perm["Toughness"] = int(perm.get("Toughness", 0) or 0) + gains * iron
            bank %= 3
        statuses["iron_discipline_wrath_bank"] = bank
    statuses["talent_permanent_attributes"] = perm
    return _inc_talent_persist_status(run, statuses)

def _inc_apply_player_talent_attack_effects(ch, run, target, entry):
    """Apply executable Incursion talent effects to one successful player attack."""
    statuses = _inc_talent_status(run)
    changed = False
    hit = bool(entry.get("hit"))
    crit = bool(entry.get("wrath_crit"))
    icons = int(entry.get("icons", 0) or 0)
    wounds_before = int(target.get("wounds_current", 0) or 0)

    blood_ledger = _inc_talent_count(ch, run, "Blood Ledger")
    if hit and blood_ledger:
        amount = (icons // 2) * blood_ledger
        if amount:
            target["statuses"] = dict(target.get("statuses") or {})
            target["statuses"]["Bleeding"] = int(target["statuses"].get("Bleeding", 0) or 0) + amount
            entry["talent_bleeding"] = amount

    blood_price = _inc_talent_count(ch, run, "Blood Price")
    if hit and blood_price and entry.get("rolls") and int(entry["rolls"][-1]) == 1:
        target["statuses"] = dict(target.get("statuses") or {})
        target["statuses"]["Bleeding"] = int(target["statuses"].get("Bleeding", 0) or 0) + blood_price
        entry["talent_bleeding"] = int(entry.get("talent_bleeding", 0) or 0) + 1

    extra_ed = 0
    pred_focus = _inc_talent_count(ch, run, "Predatory Focus")
    hunter = _inc_talent_count(ch, run, "Hunter of Weakness")
    veteran = _inc_talent_count(ch, run, "Combat Veteran")
    mark = _inc_talent_count(ch, run, "Predator's Mark")
    if hit and pred_focus and icons >= 3: extra_ed += pred_focus
    if hit and hunter and int((target.get("statuses") or {}).get("Bleeding", 0) or 0) > 0: extra_ed += hunter
    if hit and veteran and not statuses.get("combat_first_hit_used"):
        extra_ed += veteran; statuses["combat_first_hit_used"] = True; changed = True
    if hit and mark and not statuses.get("predator_mark_used"):
        if wounds_before == int(target.get("wounds_max", wounds_before) or wounds_before):
            extra_ed += 2 * mark; statuses["predator_mark_used"] = True; changed = True
    entry["talent_extra_ed"] = extra_ed

    crimson = _inc_talent_count(ch, run, "Crimson Reprisal")
    if crit and crimson:
        current = int(run.get("shock_current", 0) or 0); maximum = int(run.get("shock_max", 0) or 0)
        recovered = min(maximum - current, crimson)
        run = _inc_persist(run["id"], shock_current=current + recovered); changed = False
        entry["talent_shock"] = recovered
        statuses = _inc_talent_status(run)
    iron_fury = _inc_talent_count(ch, run, "Iron Fury")
    if crit and iron_fury:
        combat = dict(statuses.get("combat_attribute_bonus") or {})
        combat["Toughness"] = int(combat.get("Toughness", 0) or 0) + 3 * iron_fury
        statuses["combat_attribute_bonus"] = combat; changed = True
    critical_mass = _inc_talent_count(ch, run, "Critical Mass")
    if crit and critical_mass:
        combat = dict(statuses.get("combat_attribute_bonus") or {})
        combat["Strength"] = int(combat.get("Strength", 0) or 0) + critical_mass
        statuses["combat_attribute_bonus"] = combat; changed = True
    sundering = _inc_talent_count(ch, run, "Sundering Blow")
    breaker = _inc_talent_count(ch, run, "Armour Breaker")
    if crit and (sundering or breaker):
        amount = sundering + (2 * breaker)
        current = int(target.get("armour_durability_current", 0) or 0)
        if current > 0:
            lost = min(amount, current); target["armour_durability_current"] = current - lost
            entry["enemy_armour_damage"] = lost
            if target["armour_durability_current"] <= 0 and target.get("armour_rating", 0):
                target["resilience"] = max(0, int(target.get("base_resilience", target["resilience"])) - int(target.get("armour_rating", 0)))
                target["armour_broken"] = True
    execution = _inc_talent_count(ch, run, "Execution Doctrine")
    skull = _inc_talent_count(ch, run, "Skull Hunter")
    if crit and execution and wounds_before <= max(1, int(target.get("wounds_max", 1)) // 2):
        entry["talent_bonus_wounds"] = 2 * execution
    if crit and skull and int(target.get("tier", 1) or 1) >= 3:
        entry["talent_bonus_wounds"] = int(entry.get("talent_bonus_wounds", 0) or 0) + skull
    bloodsmith = _inc_talent_count(ch, run, "Bloodsmith")
    if crit and bloodsmith:
        weapon_key = str(entry.get("weapon_key", ""))
        if weapon_key and weapon_key != "__unarmed__":
            current, maximum = _inc_weapon_durability(ch, run, weapon_key)
            repaired = min(maximum, current + 2 * bloodsmith) - current
            if repaired:
                run = _inc_set_weapon_durability(run, weapon_key, current + repaired)
                entry["talent_weapon_repair"] = repaired

    battle_trance = _inc_talent_count(ch, run, "Battle Trance")
    if hit and battle_trance:
        recover = (icons // 4) * battle_trance
        if recover:
            current = int(run.get("shock_current", 0) or 0); maximum = int(run.get("shock_max", 0) or 0)
            run = _inc_persist(run["id"], shock_current=min(maximum, current + recover)); entry["talent_shock"] = int(entry.get("talent_shock", 0) or 0) + recover; statuses = _inc_talent_status(run)
    if changed:
        run = _inc_talent_persist_status(run, statuses)
    return run

def _inc_load_minions(run):
    return [dict(m) for m in (run.get("minions") or [])]


def _inc_enemy_turn(enemies, player_traits, player_shock_current=0, minions=None):
    log=[]
    minions=minions or []
    # Tracked locally so a second (or third) enemy hitting in the same
    # round correctly sees the Shock the first enemy already drained -
    # _inc_finish_combat_round then re-derives the real totals by summing
    # this log's shock/wounds fields against the actual run state, so
    # nothing here needs to touch the run directly.
    player_shock_left=max(0,int(player_shock_current or 0))
    for enemy in enemies:
        if not enemy["alive"]: continue
        wrath=max(0,int(enemy.get("wrath_current",0) or 0)); max_shock=max(1,int(enemy.get("shock_max",1) or 1)); current_shock=max(0,int(enemy.get("shock_current",0) or 0))
        if wrath>0 and current_shock<max_shock//2:
            recovered=min(max_shock-current_shock,wrath); enemy["shock_current"]=current_shock+recovered; enemy["wrath_current"]=wrath-recovered
            log.append({"actor":"enemy","action":"recover_shock","actor_name":enemy["name"],"shock":recovered,"wrath_spent":recovered}); continue
        base_pool=max(1,int(enemy.get("attack_pool",1) or 1)); expected_icons=base_pool//2
        needed=max(0,int(player_traits["Defence"])-expected_icons)
        wrath_spent=min(wrath, max(1, needed) if wrath > 0 else 0)
        attack_pool=base_pool+wrath_spent; enemy["wrath_current"]=wrath-wrath_spent
        rolls,icons,wrath_die_6=_inc_roll_pool(attack_pool); hit=icons>=player_traits["Defence"]; total_damage=0; shock=0; wounds=0; damage_rolls=[]; critical=bool(hit and wrath_die_6)
        if critical: enemy["wrath_current"]+=1
        debuff_attr=None; debuff_amount=0; minion_damage=0; minion_name=None
        # Minions "levam o dano na frente" - the first still-standing one
        # soaks hits meant for the player (own Shock first, then Wounds,
        # same rule as the player), in list order, until it goes down.
        target_minion=next((m for m in minions if m.get("alive") and int(m.get("wounds_current",0) or 0)>0),None)
        if hit:
            total_damage,damage_rolls=_inc_roll_damage(enemy.get("weapon_damage",0),enemy.get("weapon_ed",0))
            if critical:
                crit_total,crit_rolls=_inc_roll_damage(0,3); total_damage+=crit_total; damage_rolls.extend(crit_rolls)
            if target_minion:
                m_net=max(0,total_damage-int(target_minion.get("resilience",0) or 0))
                m_shock_avail=max(0,int(target_minion.get("shock_current",0) or 0))
                m_shock_dealt=min(m_net,m_shock_avail); m_wounds_dealt=m_net-m_shock_dealt
                target_minion["shock_current"]=max(0,int(target_minion.get("shock_current",0) or 0)-m_shock_dealt)
                target_minion["wounds_current"]=max(0,int(target_minion.get("wounds_current",0) or 0)-m_wounds_dealt)
                if target_minion["wounds_current"]<=0: target_minion["alive"]=False
                minion_damage=m_shock_dealt+m_wounds_dealt; minion_name=target_minion["name"]
            else:
                shock,wounds,_=_inc_damage_result(total_damage,player_traits["Resilience"],enemy.get("weapon_ap",0),player_shock_left,player_traits["Defence"])
                player_shock_left=max(0,player_shock_left-shock)
                # Some enemies (Tier 2+) can inflict a debilitating hit - a -1
                # to a random combat Attribute for the rest of this fight.
                if int(enemy.get("tier",1) or 1)>=2 and random.random()<INC_DEBUFF_CHANCE:
                    debuff_attr=random.choice(INC_DEBUFF_ATTRS); debuff_amount=-1
        log.append({"actor":"enemy","action":"attack","actor_name":enemy["name"],"skill":enemy["attack_skill"],"pool":attack_pool,"rolls":rolls,"icons":icons,"weapon":enemy["weapon_name"],"hit":hit,"damage":total_damage,"shock":shock,"wounds":wounds,"damage_rolls":damage_rolls,"critical":critical,"wrath_spent":wrath_spent,"wrath_gained":1 if critical else 0,"wrath_current":enemy["wrath_current"],"debuff_attr":debuff_attr,"debuff_amount":debuff_amount,"target":"minion" if target_minion else "player","minion_damage":minion_damage,"minion_name":minion_name})
    return log


def _inc_attack_talent_triggers(ch, run, target, rolls):
    if not _inc_has_talent(ch, "Blood Must Die", run): return []
    sixes = [i for i, value in enumerate(rolls) if int(value) == 6]
    if not sixes: return []
    return [{"type": "blood_must_die", "target_uid": target["uid"], "target_name": target["name"], "dice_indices": sixes}]

def _inc_apply_talent_trigger(node, trigger, selected_indices):
    if trigger.get("type") != "blood_must_die": return 0
    target = next((e for e in node.get("enemies", []) if e.get("uid") == trigger.get("target_uid")), None)
    if not target or not target.get("alive"): return 0
    selected = [int(i) for i in selected_indices]
    if not selected: return 0
    statuses = dict(target.get("statuses") or {})
    statuses["Bleeding"] = int(statuses.get("Bleeding", 0) or 0) + len(selected)
    target["statuses"] = statuses
    return len(selected)

def _inc_apply_weapon_minion_support(run, minions, support, value, hit_any, crit_any, kills):
    """Every piece of Tyranid-Pattern Wargear (see INC_TYRANID_WARGEAR)
    supports the Minions rather than the player directly - this is where
    each named effect actually happens, once per Strike action."""
    alive = [m for m in minions if m.get("alive") and int(m.get("wounds_current", 0) or 0) > 0]
    if support == "heal_strongest_on_hit" and hit_any and alive:
        strongest = max(alive, key=lambda m: int(m.get("wounds_max", 0) or 0))
        strongest["wounds_current"] = min(int(strongest.get("wounds_max", 0) or 0), int(strongest.get("wounds_current", 0) or 0) + value)
    elif support == "bonus_die_on_hit" and hit_any:
        for m in minions:
            m["next_bonus_die"] = int(m.get("next_bonus_die", 0) or 0) + value
    elif support == "shock_heal_weakest_on_crit" and crit_any and alive:
        weakest = min(alive, key=lambda m: int(m.get("shock_current", 0) or 0))
        weakest["shock_current"] = int(weakest.get("shock_max", 0) or 0)
    elif support == "boost_on_kills" and kills:
        statuses = _inc_talent_status(run)
        kill_count = int(statuses.get("tyranid_weapon_kills", 0) or 0) + kills
        procs, remainder = divmod(kill_count, 2)
        if procs > 0:
            for m in minions:
                m["damage"] = int(m.get("damage", 0) or 0) + procs
                m["shock_max"] = int(m.get("shock_max", 0) or 0) + procs * value
                m["shock_current"] = int(m.get("shock_current", 0) or 0) + procs * value
        statuses["tyranid_weapon_kills"] = remainder
        run = _inc_talent_persist_status(run, statuses)
    elif support == "revive_on_attack":
        dead = next((m for m in minions if not m.get("alive")), None)
        if dead:
            dead["alive"] = True
            dead["wounds_current"] = max(1, int(dead.get("wounds_max", 1) or 1) // 2)
            dead["shock_current"] = int(dead.get("shock_max", 0) or 0)
    return run


def _inc_minion_group_attack(minions, node, merged):
    """Every alive Minion fights alongside you, no matter what action you
    took this turn (Attack, Heal, Recover Shock, use an Item...) - one
    attack each, against the first live enemy, using its own damage/ED and
    a pool driven by your Fellowship PLUS that Minion's own current Shock
    (same "Shock buys hit dice" rule the player gets). Rarity is a power
    tier, not just bigger numbers: Rare+ Bleeds on hit, Legendary+ attacks
    twice, Unique also hits 50% harder (see INC_MINION_RARITY_ABILITY)."""
    log = []
    fellowship = max(1, int(merged.get("attributes", {}).get("Fellowship", 1) or 1))
    for minion in minions:
        if not (minion.get("alive") and int(minion.get("wounds_current", 0) or 0) > 0):
            continue
        rarity = minion.get("rarity", "Common")
        swings = 2 if rarity in ("Legendary", "Unique") else 1
        dmg_mult = 1.5 if rarity == "Unique" else 1.0
        bleeds = rarity in ("Rare", "Legendary", "Unique")
        m_pool = fellowship + max(0, int(minion.get("shock_current", 0) or 0)) + int(minion.pop("next_bonus_die", 0) or 0)
        for _swing in range(swings):
            live_targets = [e for e in node["enemies"] if e["alive"]]
            if not live_targets:
                break
            mtarget = live_targets[0]
            m_rolls, m_icons, m_wrath_die_6 = _inc_roll_pool(m_pool)
            m_hit = m_icons >= mtarget["defence"]
            m_damage = 0
            if m_hit:
                m_damage, _m_dr = _inc_roll_damage(int(minion.get("damage", 0) or 0), int(minion.get("ed", 0) or 0))
                m_damage = round(m_damage * dmg_mult)
                m_net = max(0, m_damage - int(mtarget.get("resilience", 0) or 0))
                mtarget["wounds_current"] = max(0, int(mtarget.get("wounds_current", 0) or 0) - m_net)
                if mtarget["wounds_current"] <= 0: mtarget["alive"] = False
                if bleeds:
                    mstatuses = dict(mtarget.get("statuses") or {})
                    mstatuses["Bleeding"] = int(mstatuses.get("Bleeding", 0) or 0) + 1
                    mtarget["statuses"] = mstatuses
            log.append({"actor": "minion", "action": "attack", "actor_name": minion.get("name", "Minion"),
                        "target_name": mtarget["name"], "target_uid": mtarget["uid"], "weapon": minion.get("name", "Minion"),
                        "pool": m_pool, "rolls": m_rolls, "icons": m_icons, "hit": m_hit, "damage": m_damage,
                        "shock": 0, "wounds": 0, "target_defeated": not mtarget["alive"]})
    return log


def _inc_resolve_player_attack(ch, run, node, target_uids, weapon, bonus_die=0, six_mode="ED", guaranteed_hit=False):
    merged = _inc_merge_character(ch, run)
    skill_name, pool = _inc_best_attack_pool(merged)
    player_traits = _inc_player_traits(ch, run)
    targets = [e for e in node["enemies"] if e["alive"] and e["uid"] in target_uids]
    if not targets:
        raise ValueError("no_valid_targets")
    status = _inc_talent_status(run)
    extra_pool = 0
    last_stand = _inc_talent_count(ch, run, "Last Stand")
    if last_stand and int(run.get("wounds_current", 0) or 0) <= max(1, int(run.get("wounds_max", 1) or 1) // 4): extra_pool += 2 * last_stand
    below_half_wounds = int(run.get("wounds_current", 0) or 0) <= max(1, int(run.get("wounds_max", 1) or 1) // 2)
    if below_half_wounds and weapon.get("melee") and _inc_talent_has(ch, run, "WAAAGH!"): extra_pool += 2
    if below_half_wounds and _inc_talent_has(ch, run, "Red Thirst") and weapon.get("melee"): extra_pool += 2
    if below_half_wounds and _inc_talent_has(ch, run, "Vow of the Crusade"): extra_pool += 2
    extra_pool += int(status.get("next_attack_bonus_dice", 0) or 0)
    status["next_attack_bonus_dice"] = 0
    run = _inc_talent_persist_status(run, status) if extra_pool or _inc_talent_has(ch, run, "Relentless Assault") else run
    # Whoever has the higher Initiative acts first - if any alive enemy
    # out-paces the player, they strike before the player's attack (and
    # their Damage/Shock hit lands before the player's own Shock-driven
    # bonus dice for THIS attack are counted, since acting second means
    # you're already reacting with whatever Shock you have left).
    player_initiative = int(merged.get("attributes", {}).get("Initiative", 1) or 1)
    fastest_enemy_initiative = max(
        (int(e.get("attributes", {}).get("Initiative", 1) or 1) for e in node["enemies"] if e["alive"]),
        default=0)
    enemy_acts_first = fastest_enemy_initiative > player_initiative
    minions = _inc_load_minions(run)
    pre_log = []
    shock_now = max(0, int(run.get("shock_current", 0) or 0))
    if enemy_acts_first:
        pre_log = _inc_enemy_turn(node["enemies"], player_traits, shock_now, minions)
        enemy_shock_dealt = sum(int(e.get("shock", 0) or 0) for e in pre_log if e.get("action") == "attack")
        shock_now = max(0, shock_now - enemy_shock_dealt)
    # Every point of Shock still standing adds a hit die - Shock is now the
    # buffer that eats damage before Wounds do, so keeping it topped up is
    # both defence AND offence, and losing it in a fight costs you both.
    shock_bonus = shock_now
    per_target_pool = max(1, pool - (len(targets) - 1) + int(bonus_die or 0) + extra_pool + shock_bonus)
    log = []
    wrath_gained = 0
    reroll_uses = 0
    if _inc_talent_has(ch, run, "Indomitable"): reroll_uses = 1
    if _inc_talent_has(ch, run, "Shield of Faith"): reroll_uses = max(reroll_uses, 1)
    if _inc_talent_has(ch, run, "Tactical Doctrine"): reroll_uses = max(reroll_uses, 2)
    for target in targets:
        rolls, icons, wrath_die_6 = _inc_roll_pool(per_target_pool)
        hit = bool(guaranteed_hit) or icons >= target["defence"]
        if not hit and reroll_uses:
            reroll_status = _inc_talent_status(run)
            used = int(reroll_status.get("reroll_miss_used", 0) or 0)
            if used < reroll_uses:
                reroll_status["reroll_miss_used"] = used + 1
                run = _inc_talent_persist_status(run, reroll_status)
                rolls2, icons2, wrath_die_6_2 = _inc_roll_pool(per_target_pool)
                if icons2 >= target["defence"]:
                    rolls, icons, wrath_die_6 = rolls2, icons2, wrath_die_6_2
                    hit = True
        critical = bool(hit and wrath_die_6)
        if critical:
            wrath_gained += 1
        total_damage = 0
        shock = 0
        wounds = 0
        damage_rolls = []
        shiftable = 0
        preview_entry = {}
        if hit:
            # Exalted Icons can be shifted into ED while retaining enough Icons to hit.
            sixes = rolls.count(6)
            shiftable = min(sixes, max(0, (icons - target["defence"]) // 2))
            # Exalted Icons (6s) are always converted to extra ED when available.
            # A Critical (Wrath Die = 6 on a successful attack) always grants 1 Wrath.
            total_ed = int(weapon.get("ed", 0) or 0) + shiftable
            preview_entry = {"hit": hit, "wrath_crit": critical, "icons": icons, "rolls": rolls,
                              "weapon_key": weapon.get("key", "__unarmed__")}
            run = _inc_apply_player_talent_attack_effects(ch, run, target, preview_entry)
            total_ed += int(preview_entry.get("talent_extra_ed", 0) or 0)
            total_damage, damage_rolls = _inc_roll_damage(weapon["damage"], total_ed)
            if critical:
                # Simple Critical option: +3 ED and a narrative critical effect.
                crit_total, crit_rolls = _inc_roll_damage(0, 3)
                total_damage += crit_total
                damage_rolls.extend(crit_rolls)
            shock, wounds, _effective_res = _inc_damage_result(total_damage, target["resilience"], weapon.get("ap", 0), target.get("shock_current", 0), target.get("defence", 0))
            bonus_wounds = int(preview_entry.get("talent_bonus_wounds", 0) or 0)
            wounds += bonus_wounds
            target["shock_current"] = max(0, int(target.get("shock_current", 0) or 0) - shock)
            target["wounds_current"] = max(0, int(target.get("wounds_current", 0) or 0) - wounds)
            if target["wounds_current"] <= 0:
                target["alive"] = False
                statuses = _inc_talent_status(run)
                ruthless = _inc_talent_count(ch, run, "Ruthless Momentum")
                if ruthless:
                    perm = dict(statuses.get("talent_permanent_attributes") or {})
                    perm["Strength"] = int(perm.get("Strength", 0) or 0) + ruthless
                    statuses["talent_permanent_attributes"] = perm
                harvest = _inc_talent_count(ch, run, "Predator's Harvest")
                if harvest:
                    kills = int(statuses.get("predator_harvest_kills", 0) or 0) + 1
                    if kills % 3 == 0:
                        perm = dict(statuses.get("talent_permanent_attributes") or {})
                        perm["Agility"] = int(perm.get("Agility", 0) or 0) + harvest
                        statuses["talent_permanent_attributes"] = perm
                    statuses["predator_harvest_kills"] = kills
                if statuses != _inc_talent_status(run):
                    run = _inc_talent_persist_status(run, statuses)
            if hit and _inc_talent_has(ch, run, "Relentless Assault"):
                statuses = _inc_talent_status(run); statuses["next_attack_bonus_dice"] = int(statuses.get("next_attack_bonus_dice", 0) or 0) + _inc_talent_count(ch, run, "Relentless Assault")
                run = _inc_talent_persist_status(run, statuses)
        log.append({"actor": "player", "action": "attack", "target_name": target["name"], "target_uid": target["uid"],
                    "skill": skill_name, "pool": per_target_pool, "rolls": rolls, "icons": icons,
                    "weapon": weapon["name"], "hit": hit, "damage": total_damage, "shock": shock, "wounds": wounds,
                    "damage_rolls": damage_rolls, "target_defeated": not target["alive"],
                    "wrath_crit": critical, "shifted_ed": shiftable if hit else 0,
                    "talent_bleeding": int(preview_entry.get("talent_bleeding", 0) or 0),
                    "talent_shock": int(preview_entry.get("talent_shock", 0) or 0),
                    "talent_extra_ed": int(preview_entry.get("talent_extra_ed", 0) or 0),
                    "talent_bonus_wounds": int(preview_entry.get("talent_bonus_wounds", 0) or 0),
                    "enemy_armour_damage": int(preview_entry.get("enemy_armour_damage", 0) or 0),
                    "enemy_armour_broken": bool(preview_entry.get("armour_broken")),
                    "talent_weapon_repair": int(preview_entry.get("talent_weapon_repair", 0) or 0)})
        if hit:
            triggers = _inc_attack_talent_triggers(ch, run, target, rolls)
            if triggers: node["pending_talent_triggers"] = triggers
    support = weapon.get("minion_support")
    if support and minions:
        run = _inc_apply_weapon_minion_support(run, minions, support, int(weapon.get("support_value", 0) or 0),
                                                hit_any=any(e["hit"] for e in log),
                                                crit_any=any(e.get("wrath_crit") for e in log),
                                                kills=sum(1 for e in log if e.get("target_defeated")))
    if node.get("pending_talent_triggers"):
        return pre_log + log, wrath_gained, minions
    log += _inc_minion_group_attack(minions, node, merged)
    if enemy_acts_first:
        return pre_log + log, wrath_gained, minions
    return log + _inc_enemy_turn(node["enemies"], player_traits, run.get("shock_current", 0), minions), wrath_gained, minions


def _inc_resolve_player_heal(ch, run, node, spend_wrath=0):
    if run["heal_charges"] <= 0: raise ValueError("no_heal_charges")
    spend_wrath=max(0,min(1,int(spend_wrath or 0)))
    if spend_wrath>int(run.get("wrath_current",0) or 0): raise ValueError("no_wrath")
    merged=_inc_merge_character(ch,run); player_traits=_inc_player_traits(ch,run)
    heal_amount=max(1,round(run["wounds_max"]*0.3)); new_wounds=min(run["wounds_max"],run["wounds_current"]+heal_amount)
    per_wrath=max(1,int(merged.get("rank",1) or 1)+int(merged.get("tier",1) or 1))
    shock_recovered=min(run["shock_max"]-run["shock_current"],spend_wrath*per_wrath); new_shock=run["shock_current"]+shock_recovered
    log=[{"actor":"player","action":"heal","amount":new_wounds-run["wounds_current"],"shock_recovered":shock_recovered,"wrath_spent":spend_wrath}]
    minions=_inc_load_minions(run)
    log+=_inc_minion_group_attack(minions,node,merged)
    return log+_inc_enemy_turn(node["enemies"],player_traits,new_shock,minions),new_wounds,new_shock,run["heal_charges"]-1,int(run["wrath_current"])-spend_wrath,minions


def _inc_resolve_player_flee(ch, run, node, target_uid, bonus_die=0):
    """Contest Speed pools; success requires strictly more Icons than the target."""
    bonus_die=max(0,int(bonus_die or 0))
    if bonus_die>int(run.get("wrath_current",0) or 0): raise ValueError("no_wrath")
    merged = _inc_merge_character(ch, run)
    player_traits = _inc_player_traits(ch, run)
    target = next((e for e in node["enemies"] if e["alive"] and e["uid"] == target_uid), None)
    if target is None:
        raise ValueError("no_valid_target")
    player_speed = max(1,int(player_traits.get("Speed",1))) + bonus_die
    target_speed = max(1, int(target.get("speed", 1)))
    p_rolls, p_icons, p_wrath_die_6 = _inc_roll_pool(player_speed)
    t_rolls, t_icons = _inc_roll_icons(target_speed)
    success = p_icons > t_icons
    log = [{"actor": "player", "action": "flee", "target_name": target["name"],
            "pool": player_speed, "rolls": p_rolls, "icons": p_icons,
            "wrath_die_1": bool(p_rolls and p_rolls[-1] == 1),
            "target_pool": target_speed, "target_rolls": t_rolls, "target_icons": t_icons,
            "success": success, "wrath_spent": int(bonus_die)}]
    if success:
        node["resolved"] = True
        node["fled"] = True
        node["victory"] = False
        return log, run["wrath_current"] - bonus_die, True, None
    minions = _inc_load_minions(run)
    return log + _inc_enemy_turn(node["enemies"], player_traits, run.get("shock_current", 0), minions), run["wrath_current"] - bonus_die, False, minions



def _inc_finish_combat_round(run, ch, node, round_log, wrath_gained=0, minions=None):
    enemy_crits = sum(1 for entry in round_log if entry.get("actor") == "enemy" and entry.get("critical"))
    if enemy_crits:
        current_armour, max_armour = _inc_armour_durability(ch, run)
        if max_armour > 0 and current_armour > 0:
            lost = min(current_armour, enemy_crits)
            run = _inc_persist(run["id"], armour_durability_current=current_armour - lost, armour_durability_max=max_armour)
            round_log = list(round_log) + [{"actor":"player","action":"armour_damage","amount":lost,
                                             "armour_durability":current_armour-lost,"reason":"enemy_critical"}]
        run, broken = _inc_break_armour_if_needed(run, ch)
        if broken:
            round_log.append({"actor":"player","action":"armour_broken","amount":0})
    node["log"] = (node.get("log") or []) + round_log
    if minions:
        # Every 2 turns, one downed Minion crawls back up on its own - half
        # Wounds, full Shock - independent of Rest or what action you took.
        statuses = _inc_talent_status(run)
        turn_count = int(statuses.get("combat_turn_count", 0) or 0) + 1
        statuses["combat_turn_count"] = turn_count
        if turn_count % 2 == 0:
            dead = next((m for m in minions if not m.get("alive")), None)
            if dead:
                dead["alive"] = True
                dead["wounds_current"] = max(1, int(dead.get("wounds_max", 1) or 1) // 2)
                dead["shock_current"] = int(dead.get("shock_max", 0) or 0)
        run = _inc_talent_persist_status(run, statuses)
    enemy_shock = sum(int(e.get("shock", 0) or 0) for e in round_log if e.get("actor") == "enemy")
    enemy_wounds = sum(int(e.get("wounds", 0) or 0) for e in round_log if e.get("actor") == "enemy")
    new_shock = max(0, int(run.get("shock_current", 0) or 0) - enemy_shock)
    new_wounds = max(0, int(run.get("wounds_current", 0) or 0) - enemy_wounds)
    if _inc_talent_has(ch, run, "Unyielding Flesh") and enemy_wounds > 0:
        statuses = _inc_talent_status(run)
        if not statuses.get("unyielding_used"):
            new_wounds = min(int(run.get("wounds_max", 0) or 0), new_wounds + _inc_talent_count(ch, run, "Unyielding Flesh"))
            statuses["unyielding_used"] = True
            run = _inc_talent_persist_status(run, statuses)
    if enemy_wounds > 0 and _inc_talent_has(ch, run, "Adrenaline Surge"):
        statuses = _inc_talent_status(run); statuses["next_attack_bonus_dice"] = int(statuses.get("next_attack_bonus_dice", 0) or 0) + _inc_talent_count(ch, run, "Adrenaline Surge")
        run = _inc_talent_persist_status(run, statuses)
    new_wrath = max(0, int(run.get("wrath_current",0) or 0)) + int(wrath_gained or 0)
    if _inc_talent_has(ch, run, "Iron Resolve") and new_shock <= 0 and enemy_shock > 0:
        statuses = _inc_talent_status(run)
        if not statuses.get("iron_resolve_used"):
            new_wrath += _inc_talent_count(ch, run, "Iron Resolve"); statuses["iron_resolve_used"] = True; run = _inc_talent_persist_status(run, statuses)
    merciless = _inc_talent_count(ch, run, "Merciless")
    if merciless and any(e.get("actor") == "player" and e.get("target_defeated") for e in round_log):
        new_shock = min(int(run.get("shock_max", 0) or 0), new_shock + merciless)
    debuff_hits = [e for e in round_log if e.get("actor") == "enemy" and e.get("debuff_attr")]
    if debuff_hits:
        statuses = _inc_talent_status(run)
        debuffs = dict(statuses.get("enemy_debuffs") or {})
        for e in debuff_hits:
            debuffs[e["debuff_attr"]] = int(debuffs.get(e["debuff_attr"], 0) or 0) + int(e["debuff_amount"])
        statuses["enemy_debuffs"] = debuffs
        run = _inc_talent_persist_status(run, statuses)
    all_dead = all(not e["alive"] for e in node["enemies"])

    if new_wounds <= 0:
        statuses = _inc_talent_status(run)
        if _inc_talent_has(ch, run, "Reanimation Protocols") and not statuses.get("reanimation_used"):
            new_wounds = max(1, int(run.get("wounds_max", 1) or 1) // 4)
            statuses["reanimation_used"] = True
            run = _inc_talent_persist_status(run, statuses)
        else:
            _inc_persist(run["id"], shock_current=new_shock, wounds_current=0, wrath_current=new_wrath, node=node, **({"minions": minions} if minions is not None else {}))
            return _inc_mark_dead({**run, "wounds_current": 0}, ch, "Fell in battle")

    if all_dead:
        # Fight is over - clear per-fight Talent flags and enemy debuffs.
        run = _inc_talent_persist_status(run, _inc_reset_per_fight_statuses(_inc_talent_status(run)))
        node["resolved"], node["victory"] = True, True
        # Post-fight recovery: winning a fight is its own small breather -
        # 20% of max Wounds and a flat 10 Shock back before whatever comes
        # next (loot, another fight, the shop).
        new_wounds = min(int(run.get("wounds_max", 0) or 0), new_wounds + round(int(run.get("wounds_max", 0) or 0) * 0.20))
        new_shock = min(int(run.get("shock_max", 0) or 0), new_shock + 10)
        bosses_cleared, pending_boss3 = run["bosses_cleared"], run["pending_boss3_pvp"]
        if run["stage"] == "boss":
            bosses_cleared += 1
            if bosses_cleared % 3 == 0:
                pending_boss3 = True
        updated = _inc_persist(run["id"], shock_current=new_shock, wounds_current=new_wounds, wrath_current=new_wrath,
                               xp=run["xp"] + node["reward_xp"], xp_earned=run.get("xp_earned", 0) + node["reward_xp"], node=node,
                               bosses_cleared=bosses_cleared, pending_boss3_pvp=pending_boss3,
                               **({"minions": minions} if minions is not None else {}))
        loot_node = _inc_post_combat_loot(updated, ch, node)
        return loot_node if loot_node is not None else updated

    return _inc_persist(run["id"], shock_current=new_shock, wounds_current=new_wounds, wrath_current=new_wrath, node=node,
                         **({"minions": minions} if minions is not None else {}))


def _inc_resolve_pending_talent(run, ch, selected_indices):
    node = copy.deepcopy(run.get("node") or {})
    triggers = node.get("pending_talent_triggers") or []
    if not triggers: raise ValueError("no_pending_talent")
    applied = sum(_inc_apply_talent_trigger(node, t, selected_indices) for t in triggers)
    node.pop("pending_talent_triggers", None)
    log = [{"actor":"player","action":"talent_trigger","talent":"Blood Must Die","amount":applied,"target_name":triggers[0].get("target_name","Target")}]
    minions = _inc_load_minions(run)
    log += _inc_minion_group_attack(minions, node, _inc_merge_character(ch, run))
    log += _inc_enemy_turn(node.get("enemies", []), _inc_player_traits(ch, run), run.get("shock_current", 0), minions)
    return _inc_finish_combat_round(run, ch, node, log, minions=minions)

def _inc_combat_attack(run, ch, target_uids, weapon_key, bonus_die=0, six_mode="ED", restore_shock=False, guaranteed_hit=False):
    if not run.get("node") or run["node"].get("type")!="combat": raise ValueError("wrong_node")
    bonus_die=max(0,int(bonus_die or 0))
    restore_shock=bool(restore_shock)
    guaranteed_hit=bool(guaranteed_hit)
    if sum([restore_shock, guaranteed_hit, bool(bonus_die)]) > 1:
        raise ValueError("choose_one_wrath_effect")
    if bonus_die>int(run.get("wrath_current",0) or 0): raise ValueError("no_wrath")
    if restore_shock and int(run.get("wrath_current",0) or 0)<1: raise ValueError("no_wrath")
    if guaranteed_hit and int(run.get("wrath_current",0) or 0)<1: raise ValueError("no_wrath")
    node=copy.deepcopy(run["node"]); weapon=_inc_weapon_by_key(ch,run,weapon_key)
    if weapon.get("key") != "__unarmed__" and int(weapon.get("durability_current", 0)) <= 0:
        raise ValueError("weapon_broken")
    if restore_shock:
        merged=_inc_merge_character(ch,run)
        current_shock=int(run.get("shock_current",0) or 0); max_shock=int(run.get("shock_max",0) or 0)
        if current_shock>=max_shock: raise ValueError("shock_full")
        rank=max(1,int(merged.get("rank",1) or 1)); tier=max(1,int(merged.get("tier",1) or 1))
        recovered=min(max_shock-current_shock,rank+tier)
        run=_inc_persist(run["id"],shock_current=current_shock+recovered,wrath_current=int(run["wrath_current"])-1)
        run=_inc_record_wrath_spend(run, ch, 1)
        bonus_die=0
    elif guaranteed_hit:
        # Spends exactly 1 Wrath - one guaranteed hit per turn, not a
        # dice-pool bonus. Rolled dice/icons still show for flavour and can
        # still crit on the Wrath Die, but the hit/miss check is skipped.
        run=_inc_persist(run["id"],wrath_current=int(run["wrath_current"])-1)
        run=_inc_record_wrath_spend(run, ch, 1)
    elif bonus_die:
        run=_inc_persist(run["id"],wrath_current=int(run["wrath_current"])-bonus_die)
        run=_inc_record_wrath_spend(run, ch, bonus_die)
    round_log,wrath_gained,minions=_inc_resolve_player_attack(ch,run,node,target_uids,weapon,bonus_die=bonus_die,six_mode=six_mode,guaranteed_hit=guaranteed_hit)
    weapon_ones = sum(1 for entry in round_log if entry.get("actor") == "player" and entry.get("rolls") and int(entry["rolls"][-1]) == 1)
    if weapon_ones and weapon.get("key") != "__unarmed__":
        run, lost, weapon_cur, weapon_max = _inc_damage_weapon_from_wrath_one(run, ch, weapon["key"])
        round_log.append({"actor":"player","action":"weapon_damage","amount":lost,"weapon":weapon.get("name","Weapon"),
                          "durability_current":weapon_cur,"durability_max":weapon_max})
    if weapon.get("consumable"):
        charges=dict(run.get("consumable_charges") or {}); charges[weapon["key"]]=max(0,int(weapon["remaining"])-1); run=_inc_persist(run["id"],consumable_charges=charges)
    return _inc_finish_combat_round(run,ch,node,round_log,wrath_gained,minions=minions)


def _inc_resolve_restore_shock(ch, run, node):
    if not run.get("node") or run["node"].get("type") != "combat":
        raise ValueError("wrong_node")
    current_wrath = int(run.get("wrath_current", 0) or 0)
    if current_wrath < 1:
        raise ValueError("no_wrath")
    current_shock = int(run.get("shock_current", 0) or 0)
    max_shock = int(run.get("shock_max", 0) or 0)
    if current_shock >= max_shock:
        raise ValueError("shock_full")
    merged = _inc_merge_character(ch, run)
    rank = max(1, int(merged.get("rank", 1) or 1))
    tier = max(1, int(merged.get("tier", 1) or 1))
    recovered = min(max_shock - current_shock, rank + tier)
    new_shock = current_shock + recovered
    log = [{"actor": "player", "action": "restore_shock", "shock_recovered": recovered, "wrath_spent": 1}]
    player_traits = _inc_player_traits(ch, run)
    minions = _inc_load_minions(run)
    log += _inc_minion_group_attack(minions, node, merged)
    return log + _inc_enemy_turn(node.get("enemies", []), player_traits, new_shock, minions), new_shock, current_wrath - 1, minions


def _inc_combat_restore_shock(run, ch):
    if not run.get("node") or run["node"].get("type") != "combat":
        raise ValueError("wrong_node")
    node = copy.deepcopy(run["node"])
    round_log, new_shock, wrath_left, minions = _inc_resolve_restore_shock(ch, run, node)
    run = _inc_persist(run["id"], shock_current=new_shock, wrath_current=wrath_left)
    run = _inc_record_wrath_spend(run, ch, 1)
    return _inc_finish_combat_round(run, ch, node, round_log, minions=minions)


def _inc_combat_heal(run, ch, spend_wrath=0):
    if not run.get("node") or run["node"].get("type")!="combat": raise ValueError("wrong_node")
    node=copy.deepcopy(run["node"]); round_log,new_wounds,new_shock,charges_left,wrath_left,minions=_inc_resolve_player_heal(ch,run,node,spend_wrath=spend_wrath)
    run=_inc_persist(run["id"],heal_charges=charges_left,wounds_current=new_wounds,shock_current=new_shock,wrath_current=wrath_left)
    run=_inc_record_wrath_spend(run,ch,int(spend_wrath or 0))
    return _inc_finish_combat_round(run,ch,node,round_log,minions=minions)


def _inc_combat_flee(run, ch, target_uid, bonus_die=0):
    if not run.get("node") or run["node"].get("type") != "combat":
        raise ValueError("wrong_node")
    node = copy.deepcopy(run["node"])
    round_log, wrath_left, escaped, minions = _inc_resolve_player_flee(ch, run, node, target_uid, bonus_die=bonus_die)
    if escaped:
        node["log"] = (node.get("log") or []) + round_log
        run = _inc_persist(run["id"], wrath_current=wrath_left, node=node)
        run = _inc_talent_persist_status(run, _inc_reset_per_fight_statuses(_inc_talent_status(run)))
        return _inc_record_wrath_spend(run, ch, int(bonus_die or 0))
    run = _inc_persist(run["id"], wrath_current=wrath_left)
    run = _inc_record_wrath_spend(run, ch, int(bonus_die or 0))
    return _inc_finish_combat_round(run, ch, node, round_log, minions=minions)



def _inc_combat_continue(run, ch):
    if not run.get("node") or run["node"].get("type") != "combat" or not run["node"].get("resolved"):
        raise ValueError("wrong_node")
    return _inc_advance(run, ch)


# ---- PvP: Challenge / Duel of Glory checkpoints -------------------------
def _inc_build_snapshot(ch, run):
    merged = _inc_merge_character(ch, run)
    return {
        # species from merged, not the raw character - for an incursion-kind
        # account this is the run's Origin (e.g. "Aeldari-Pattern"), which is
        # what species_speed() needs to grant the right Speed in the duel.
        "name": ch.get("name", ""), "tier": merged.get("tier", 1), "armour": ch.get("armour", 0),
        "species": merged.get("species", ""), "attributes": merged["attributes"], "skills": merged.get("skills", {}),
        "wargear": merged["wargear"], "talents": merged.get("talents", []), "powers": merged.get("powers", []),
        "wounds_current": run["wounds_current"], "wounds_max": run["wounds_max"],
        "loop_no": run["loop_no"], "bosses_cleared": run["bosses_cleared"],
    }


def _inc_simulate_fight(attacker, defender, hp_a_start, hp_b_start):
    """Compressed PvP fight using the same weapon ED/AP damage rules as combat.
    Shock is intentionally omitted from the unattended duel model."""
    atk_traits, def_traits = derived_traits(attacker), derived_traits(defender)
    atk_skill, atk_pool = _inc_best_attack_pool(attacker)
    def_skill, def_pool = _inc_best_attack_pool(defender)
    atk_weapon, def_weapon = _inc_best_weapon(attacker), _inc_best_weapon(defender)

    hp_a, hp_b, log = hp_a_start, hp_b_start, []
    for _round in range(1, 7):
        if hp_a <= 0 or hp_b <= 0:
            break
        rolls, icons, wrath_die_6 = _inc_roll_pool(atk_pool)
        hit = icons >= def_traits["Defence"]
        dmg = 0
        if hit:
            shiftable = min(rolls.count(6), max(0, (icons - def_traits["Defence"]) // 2))
            total, _dr = _inc_roll_damage(atk_weapon["damage"], atk_weapon.get("ed", 0) + shiftable)
            if hit and wrath_die_6:
                crit_total, _cr = _inc_roll_damage(0, 3)
                total += crit_total
            _shock, dmg, _res = _inc_damage_result(total, def_traits["Resilience"], atk_weapon.get("ap", 0))
            hp_b = max(0, hp_b - dmg)
        log.append({"side": "attacker", "skill": atk_skill, "pool": atk_pool, "rolls": rolls, "icons": icons,
                    "weapon": atk_weapon["name"], "hit": hit, "damage": dmg})
        if hp_b <= 0:
            break
        rolls, icons, wrath_die_6 = _inc_roll_pool(def_pool)
        hit = icons >= atk_traits["Defence"]
        dmg = 0
        if hit:
            shiftable = min(rolls.count(6), max(0, (icons - atk_traits["Defence"]) // 2))
            total, _dr = _inc_roll_damage(def_weapon["damage"], def_weapon.get("ed", 0) + shiftable)
            if hit and wrath_die_6:
                crit_total, _cr = _inc_roll_damage(0, 3)
                total += crit_total
            _shock, dmg, _res = _inc_damage_result(total, atk_traits["Resilience"], def_weapon.get("ap", 0))
            hp_a = max(0, hp_a - dmg)
        log.append({"side": "defender", "skill": def_skill, "pool": def_pool, "rolls": rolls, "icons": icons,
                    "weapon": def_weapon["name"], "hit": hit, "damage": dmg})

    hp_a, hp_b = max(0, hp_a), max(0, hp_b)
    if hp_a <= 0 and hp_b <= 0:
        winner = "draw"
    elif hp_b <= 0:
        winner = "attacker"
    elif hp_a <= 0:
        winner = "defender"
    else:
        winner = "attacker" if (hp_a / hp_a_start) >= (hp_b / hp_b_start) else "defender"
    return {"log": log, "hp_a": hp_a, "hp_b": hp_b, "winner": winner}


def _inc_match_state_from_snapshots(a, b):
    def player(snap):
        traits = derived_traits(snap)
        return {
            "name": snap.get("name", "Operative"),
            "snapshot": snap,
            "wounds": int(snap.get("wounds_current", traits["Max Wounds"]) or 0),
            "wounds_max": int(snap.get("wounds_max", traits["Max Wounds"]) or traits["Max Wounds"]),
            "shock": int(snap.get("shock_current", traits["Max Shock"]) or 0),
            "shock_max": int(snap.get("shock_max", traits["Max Shock"]) or traits["Max Shock"]),
            "wrath": 2,
            "defence": int(traits["Defence"]),
            "resilience": int(traits["Resilience"]),
            "speed": int(traits["Speed"]),
        }
    return {"a": player(a), "b": player(b), "turn": "a", "log": [], "winner": None}


def _inc_create_pvp_match(waiting, current):
    a_snap = _inc_json_field(waiting["snapshot"], {})
    b_snap = _inc_json_field(current["snapshot"], {})
    state = _inc_match_state_from_snapshots(a_snap, b_snap)
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO incursion_pvp_match(checkpoint,run_a,run_b,char_a,char_b,state,status,created_at,updated_at) VALUES(?,?,?,?,?,?,'active',?,?)",
        (waiting["checkpoint"], waiting["run_id"], current["run_id"], waiting["character_id"], current["character_id"],
         json.dumps(state), now_iso(), now_iso()))
    match_id = cur.lastrowid
    # Only "waiting" has a queue row to update - it's the one polling via
    # _inc_resolve_waiting_pvp for a match to appear. "current" is the
    # player who just walked in and found them, and gets its pvp_match
    # node set synchronously by the caller instead; it was never inserted
    # into incursion_pvp_queue, so a second UPDATE keyed on current["id"]
    # (a field that never existed) crashed with KeyError every time two
    # players actually met at a Challenge checkpoint.
    conn.execute("UPDATE incursion_pvp_queue SET status='matched', result=? WHERE id=?", (json.dumps({"match_id": match_id, "side": "a"}), waiting["id"]))
    conn.commit(); conn.close()
    return match_id


def _inc_queue_or_match(run, ch, checkpoint):
    my_snapshot = _inc_build_snapshot(ch, run)
    conn = get_conn()
    waiting = conn.execute(
        "SELECT * FROM incursion_pvp_queue WHERE checkpoint=? AND status='waiting' AND character_id<>? "
        "ORDER BY created_at LIMIT 1", (checkpoint, ch["id"])
    ).fetchone()
    conn.close()
    if waiting:
        match_id = _inc_create_pvp_match(dict(waiting), {"run_id": run["id"], "character_id": ch["id"], "checkpoint": checkpoint, "snapshot": json.dumps(my_snapshot)})
        opponent_run = _inc_get_run(int(waiting["run_id"]))
        if opponent_run:
            _inc_persist(opponent_run["id"], node={"type": "pvp_match", "checkpoint": checkpoint, "match_id": match_id, "side": "a"})
        return {"matched": True, "match_id": match_id, "side": "b"}
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO incursion_pvp_queue(run_id,character_id,checkpoint,snapshot,status,created_at) VALUES (?,?,?,?,'waiting',?)",
        (run["id"], ch["id"], checkpoint, json.dumps(my_snapshot), now_iso()))
    conn.commit(); queue_id = cur.lastrowid; conn.close()
    return {"matched": False, "queue_id": queue_id}


def _inc_get_pvp_match(match_id):
    conn = get_conn(); row = conn.execute("SELECT * FROM incursion_pvp_match WHERE id=?", (match_id,)).fetchone(); conn.close()
    if not row: return None
    r = dict(row); r["state"] = _inc_json_field(r.get("state"), {}); return r


def _inc_pvp_apply_attack(match, side, spend_wrath=0, six_mode="ED"):
    state = copy.deepcopy(match["state"])
    other = "b" if side == "a" else "a"
    actor = state[side]; target = state[other]
    if state.get("winner") or state.get("turn") != side:
        raise ValueError("not_your_turn")
    spend_wrath = max(0, int(spend_wrath or 0))
    if spend_wrath > int(actor.get("wrath", 0)):
        raise ValueError("no_wrath")
    snap = actor["snapshot"]
    weapon = _inc_best_weapon(snap)
    skill_name, base_pool = _inc_best_attack_pool(snap)
    pool = max(1, int(base_pool) + spend_wrath)
    actor["wrath"] -= spend_wrath
    rolls, icons, wrath_die_6 = _inc_roll_pool(pool)
    hit = icons >= int(target["defence"])
    damage = shock = wounds = 0
    shifted = 0
    wrath_gained = 1 if hit and wrath_die_6 else 0
    if hit:
        shifted = min(rolls.count(6), max(0, (icons - int(target["defence"])) // 2))
        total_damage, _ = _inc_roll_damage(weapon["damage"], int(weapon.get("ed", 0)) + shifted)
        if wrath_die_6:
            crit_total, _ = _inc_roll_damage(0, 3); total_damage += crit_total
        shock, wounds, _ = _inc_damage_result(total_damage, int(target["resilience"]), int(weapon.get("ap", 0)), int(target.get("shock", 0)), int(target.get("defence", 0)))
        target["shock"] = max(0, int(target["shock"]) - shock)
        target["wounds"] = max(0, int(target["wounds"]) - wounds)
    actor["wrath"] += wrath_gained
    entry = {"side": side, "actor": actor["name"], "target": target["name"], "action": "attack", "skill": skill_name,
             "pool": pool, "rolls": rolls, "icons": icons, "weapon": weapon["name"], "hit": hit,
             "damage": total_damage if hit else 0, "shock": shock, "wounds": wounds, "wrath_spent": spend_wrath,
             "wrath_gained": wrath_gained, "shifted": shifted}
    state["log"].append(entry)
    if target["wounds"] <= 0:
        state["winner"] = side
        state["turn"] = None
    else:
        state["turn"] = other
    conn = get_conn()
    conn.execute("UPDATE incursion_pvp_match SET state=?,status=?,updated_at=? WHERE id=?",
                 (json.dumps(state), "resolved" if state.get("winner") else "active", now_iso(), match["id"]))
    conn.commit(); conn.close()
    return state


def _inc_pvp_recover_shock(match, side, spend_wrath=0):
    state = copy.deepcopy(match["state"]); actor = state[side]
    if state.get("winner") or state.get("turn") != side: raise ValueError("not_your_turn")
    spend_wrath=max(0,min(1,int(spend_wrath or 0)))
    if spend_wrath > int(actor.get("wrath",0)): raise ValueError("no_wrath")
    snap=actor["snapshot"]; rank=int(snap.get("rank",1) or 1); tier=int(snap.get("tier",1) or 1)
    recovered=min(int(actor["shock_max"])-int(actor["shock"]), spend_wrath*(rank+tier))
    actor["wrath"] -= spend_wrath; actor["shock"] += recovered
    other="b" if side=="a" else "a"
    state["log"].append({"side":side,"actor":actor["name"],"action":"recover_shock","shock":recovered,"wrath_spent":spend_wrath})
    state["turn"]=other
    conn=get_conn(); conn.execute("UPDATE incursion_pvp_match SET state=?,updated_at=? WHERE id=?",(json.dumps(state),now_iso(),match["id"])); conn.commit(); conn.close()
    return state


def _inc_pvp_finalize_run(run, ch, match, side):
    state=match["state"]; winner=state.get("winner"); actor=state[side]; opponent=state["b" if side=="a" else "a"]
    if not winner: return run
    won = winner == side
    xp = INC_PVP_XP_REWARD[match["checkpoint"]] if won else 0
    wounds=max(0,int(actor["wounds"]))
    node={"type":"pvp_result","won":won,"opponent_name":opponent["name"],"xp_gained":xp,"log":state.get("log",[])}
    updated=_inc_persist(run["id"],wounds_current=wounds,xp=run["xp"]+xp,xp_earned=run.get("xp_earned",0)+xp,node=node)
    if wounds<=0:
        updated=_inc_mark_dead(updated,ch,"Defeated in a duel against another player")
    return updated


def _inc_pvp_queue(run, ch):
    if not run.get("node") or run["node"].get("type") != "pvp_choice": raise ValueError("wrong_node")
    checkpoint=run["node"]["checkpoint"]; outcome=_inc_queue_or_match(run,ch,checkpoint)
    if not outcome["matched"]:
        return _inc_persist(run["id"],node={"type":"pvp_waiting","checkpoint":checkpoint,"queue_id":outcome["queue_id"]})
    return _inc_persist(run["id"],node={"type":"pvp_match","checkpoint":checkpoint,"match_id":outcome["match_id"],"side":outcome["side"]})


def _inc_pvp_skip(run, ch):
    if not run.get("node") or run["node"].get("type") != "pvp_choice": raise ValueError("wrong_node")
    return _inc_advance(run,ch)


def _inc_pvp_result_continue(run,ch):
    if not run.get("node") or run["node"].get("type") != "pvp_result": raise ValueError("wrong_node")
    return _inc_advance(run,ch)


def _inc_resolve_waiting_pvp(run,ch):
    if not run.get("node") or run["node"].get("type") != "pvp_waiting": return run
    result=_inc_check_resolved(run["node"]["queue_id"])
    if not result: return run
    match=_inc_get_pvp_match(result.get("match_id")) if result.get("match_id") else None
    if not match: return run
    return _inc_persist(run["id"],node={"type":"pvp_match","checkpoint":match["checkpoint"],"match_id":match["id"],"side":result.get("side","a")})


def _inc_check_resolved(queue_id):
    conn=get_conn(); row=conn.execute("SELECT * FROM incursion_pvp_queue WHERE id=?",(queue_id,)).fetchone(); conn.close()
    if not row or row["status"] not in ("matched","resolved"): return None
    result=_inc_json_field(row["result"],None)
    return result


def _inc_leaderboard(limit=10):
    """Return each player's best single-run XP total, highest first."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT u.id AS user_id, u.username, c.name AS character_name,
               r.xp_earned, r.loop_no, r.bosses_cleared, r.status, r.id AS run_id
        FROM incursion_run r
        JOIN characters c ON c.id = r.character_id
        JOIN users u ON u.id = c.user_id
        WHERE u.role != 'spectator'
          AND COALESCE(r.xp_earned, 0) > 0
        ORDER BY COALESCE(r.xp_earned, 0) DESC, r.loop_no DESC, r.id ASC
    """).fetchall()
    conn.close()

    # One entry per player: only their highest-XP run counts.
    best = {}
    for row in rows:
        r = dict(row)
        uid = r["user_id"]
        if uid not in best:
            best[uid] = r
    ranked = sorted(best.values(), key=lambda r: (-int(r["xp_earned"] or 0), -int(r["loop_no"] or 0), int(r["run_id"])))
    for i, r in enumerate(ranked[:limit], 1):
        r["rank"] = i
    return ranked[:limit]


def _inc_render_login_leaderboard():
    ranking=_inc_leaderboard(10)
    st.markdown("<div class='inc-rank-panel'><div class='inc-rank-head'><span>RANK</span><span>OPERATIVE</span><span>RUN XP</span></div>",unsafe_allow_html=True)
    if not ranking:
        st.markdown("<div class='inc-rank-empty'>NO ASCENSIONS RECORDED</div></div>",unsafe_allow_html=True); return
    rows=[]
    for r in ranking:
        name=r.get('character_name') or r.get('username') or 'Unknown'; pos=int(r['rank'])
        rows.append(f"<div class='inc-rank-row'><span class='inc-rank-pos'>{pos:02d}</span><span class='inc-rank-name'>{html.escape(str(name))}<small>{html.escape(str(r.get('username') or ''))}</small></span><span class='inc-rank-xp'>{int(r['xp_earned']):,}</span></div>")
    st.markdown(''.join(rows)+"</div>",unsafe_allow_html=True)


# ---- UI ------------------------------------------------------------------
def _inc_render_hud(ch, run):
    merged=_inc_merge_character(ch,run); traits=derived_traits(merged); adapters=_inc_talent_adapters(ch,run)
    if ch.get("kind") == "incursion":
        # No sheet, no Tier for a self-registered Operative - Origin (a
        # per-run choice) is the identity that matters here instead.
        subtitle = f"{html.escape(str(run.get('origin') or 'Unassigned Origin'))} · STATUS: DEPLOYED"
    else:
        subtitle = f"{html.escape(str(ch.get('archetype') or ch.get('species') or 'Operative'))} · TIER {int(ch.get('tier',1) or 1)} · RANK {int(ch.get('rank',1) or 1)} · STATUS: DEPLOYED"
    st.markdown(f"<div class='inc-identity'><div class='inc-kicker'>OPERATIVE RECORD // ACTIVE DEPLOYMENT</div><div class='inc-hero-name'>{html.escape(str(ch.get('name') or 'Unnamed'))}</div><div class='inc-hero-sub'>{subtitle}</div></div>",unsafe_allow_html=True)
    wounds_pct=100.0*max(0,int(run['wounds_current'] or 0))/max(1,int(run['wounds_max'] or 1)); shock_pct=100.0*max(0,int(run['shock_current'] or 0))/max(1,int(run['shock_max'] or 1)); wounds_hue=max(0.0,min(120.0,wounds_pct*1.2))
    armour_current, armour_max = _inc_armour_durability(ch, run)
    armour_label = f"{armour_current}/{armour_max}" if armour_max else "NONE"
    st.markdown(f"<div class='inc-player-vitals'><div class='inc-player-vital wounds' style='--pv-pct:{wounds_pct:.1f}%;--pv-hue:{wounds_hue:.1f}'><b>{run['wounds_current']}/{run['wounds_max']}</b><span class='pv-label'>WOUNDS · LIFE</span></div><div class='inc-player-vital shock' style='--pv-pct:{shock_pct:.1f}%'><b>{run['shock_current']}/{run['shock_max']}</b><span class='pv-label'>SHOCK</span></div><div class='inc-player-vital armour'><b>{armour_label}</b><span class='pv-label'>ARMOUR DURABILITY</span></div></div><div class='inc-hud'><div class='inc-chip wrath'><b>{run['wrath_current']} ∞</b><small>WRATH</small></div><div class='inc-chip'><b>{run['xp']}</b><small>RUN XP</small></div><div class='inc-chip'><b>{run['loop_no']}</b><small>LOOP</small></div><div class='inc-chip'><b>{run['bosses_cleared']}</b><small>CHAMPIONS</small></div><div class='inc-chip'><b>{run['heal_charges']}</b><small>MEDICAE</small></div><div class='inc-chip'><b>{traits['Defence']}/{traits['Resilience']}</b><small>DEF / RES</small></div></div>",unsafe_allow_html=True)
    track=''.join(f"<div class='inc-stage {'now' if s==run['stage'] else ''}'><span>{'✠' if s==run['stage'] else '·'}</span>{INC_STAGE_LABELS[s]}</div>" for s in INC_SEQUENCE)
    st.markdown(f"<div class='inc-track'>{track}</div>",unsafe_allow_html=True)
    with st.expander(f"TALENT CODEX · {len(adapters)}",expanded=False):
        for t in adapters: st.markdown(f"<div class='inc-talent-card {t.get('status','manual')}'><b>{html.escape(t['name'])}</b><span>{html.escape(t['rule'])}</span></div>",unsafe_allow_html=True)
    _inc_render_tutorial()


def _inc_render_minion_status(run, node):
    """Each Minion's Wounds/Shock bars and its last roll, shown right in
    combat (not just the backpack) - so what it's doing is as visible as
    the enemies it's tanking for."""
    minions = run.get("minions") or []
    if not minions:
        return
    log = node.get("log") or []
    def last_attack(name):
        return next((e for e in reversed(log) if e.get("actor") == "minion" and e.get("actor_name") == name), None)
    cols = st.columns(len(minions))
    for col, minion in zip(cols, minions):
        with col:
            wounds_max = max(1, int(minion.get("wounds_max", 1) or 1)); wounds_cur = max(0, min(wounds_max, int(minion.get("wounds_current", 0) or 0)))
            shock_max = max(1, int(minion.get("shock_max", 1) or 1)); shock_cur = max(0, min(shock_max, int(minion.get("shock_current", 0) or 0)))
            wounds_pct = 100.0 * wounds_cur / wounds_max; shock_pct = 100.0 * shock_cur / shock_max
            status = "ACTIVE" if minion.get("alive") else "DOWN"
            rarity_cls = f"rarity-{str(minion.get('rarity') or 'Common').lower()}"
            entry = last_attack(minion.get("name"))
            if entry:
                rolls = entry.get("rolls") or []
                dice = "".join(f"<span class='inc-die {'icon2' if r == 6 else ('icon1' if r >= 4 else '')}'>{r}</span>" for r in rolls)
                hit_cls = "hit" if entry.get("hit") else "miss"
                result = "HIT" if entry.get("hit") else "MISS"
                roll_html = (f"<div class='inc-dice-row-inner'>{dice}</div>"
                             f"<div class='inc-dice-meta'><span class='inc-dice-result {hit_cls}'>{result}</span>"
                             f"<span class='inc-dice-icons'>rolled {int(entry.get('damage',0) or 0)} dmg</span></div>")
            else:
                roll_html = "<div class='inc-dice-empty'>No rolls yet</div>"
            st.markdown(
                f"<div class='inc-enemy {rarity_cls}'>"
                f"<div class='inc-enemy-strip'><span>{minion.get('icon','🐾')} {html.escape(str(minion.get('name','Minion')))}</span><span>{status}</span></div>"
                f"<div class='inc-npc-vitals'>"
                f"<span class='inc-vital wounds' style='--vital-pct:{wounds_pct:.1f}%;--vital-pct-num:{wounds_pct/100:.3f};--vital-color:#b23a35'><b>{wounds_cur}/{wounds_max}</b><span class='inc-vital-label'>WOUNDS</span></span>"
                f"<span class='inc-vital shock' style='--vital-pct:{shock_pct:.1f}%;--vital-color:#9b72c2'><b>{shock_cur}/{shock_max}</b><span class='inc-vital-label'>SHOCK</span></span>"
                f"</div>{roll_html}</div>", unsafe_allow_html=True)


def _inc_render_dice_tray(node):
    """Shows the last roll for each side up front, in place of a scrolling
    log. Icons glow (double glow on a 6/Exalted); the Wrath Die is ringed,
    and pulses if it crit."""
    log = node.get("log") or []
    def last_attack(actor):
        return next((e for e in reversed(log) if e.get("actor") == actor and e.get("action") == "attack"), None)
    def dice_html(entry):
        if not entry:
            return "<div class='inc-dice-empty'>No rolls yet</div>"
        rolls = entry.get("rolls") or []
        n = len(rolls)
        dice = []
        for i, r in enumerate(rolls):
            is_wrath = (i == n - 1)
            icon_cls = "icon2" if r == 6 else ("icon1" if r >= 4 else "")
            wrath_cls = "wrath" if is_wrath else ""
            crit_cls = "crit" if (is_wrath and r == 6) else ""
            dice.append(f"<span class='inc-die {icon_cls} {wrath_cls} {crit_cls}' style='--d:{i}'>{r}</span>")
        hit_cls = "hit" if entry.get("hit") else "miss"
        weapon = html.escape(str(entry.get("weapon", "")))
        if not entry.get("hit"):
            result_label = "MISS"
        else:
            # Lead with what actually landed, not the pre-Resilience damage
            # roll - a "12 damage" headline next to a target that only lost
            # 4 Wounds reads as a miscalc when it was really Resilience
            # eating the rest.
            wounds_dealt = int(entry.get("wounds", 0) or 0)
            shock_dealt = int(entry.get("shock", 0) or 0)
            if wounds_dealt:
                result_label = f"{wounds_dealt} WOUNDS"
            elif shock_dealt:
                result_label = f"{shock_dealt} SHOCK"
            else:
                result_label = "NO EFFECT"
            if entry.get("target_defeated"):
                result_label += " · DEFEATED"
        wrath_note = " · WRATH CRIT" if entry.get("wrath_crit") else ""
        return (f"<div class='inc-dice-row-inner'>{''.join(dice)}</div>"
                f"<div class='inc-dice-meta'><span class='inc-dice-result {hit_cls}'>{result_label}</span>"
                f"<span class='inc-dice-icons'>{int(entry.get('icons', 0) or 0)} ICONS · rolled {int(entry.get('damage',0) or 0)} dmg{wrath_note}</span>"
                f"<span class='inc-dice-weapon'>{weapon}</span></div>")
    st.markdown(
        f"<div class='inc-dice-tray'>"
        f"<div class='inc-dice-col'><div class='inc-dice-label you'>YOUR ROLL</div>{dice_html(last_attack('player'))}</div>"
        f"<div class='inc-dice-col'><div class='inc-dice-label foe'>ENEMY ROLL</div>{dice_html(last_attack('enemy'))}</div>"
        f"</div>", unsafe_allow_html=True)


def _inc_render_duel_log(log):
    lines = []
    for e in reversed(log or []):
        label = "You" if e["side"] == "attacker" else "Opponent"
        cls = "player" if e["side"] == "attacker" else "enemy"
        if not e["hit"]:
            lines.append(f"<div class='inc-log-line {cls}'><b>{label}</b> attacks with {html.escape(e['weapon'])} "
                         f"· <i>misses</i> ({e['pool']}d6, {e['icons']} icons)</div>")
        else:
            lines.append(f"<div class='inc-log-line {cls}'><b>{label}</b> hits with {html.escape(e['weapon'])}: "
                         f"<b>{e['damage']}</b> damage ({e['pool']}d6, {e['icons']} icons)</div>")
    if not lines:
        lines = ["<div class='inc-log-line system'>The duel begins...</div>"]
    st.markdown(f"<div class='inc-log'>{''.join(lines)}</div>", unsafe_allow_html=True)


def _inc_render_tutorial():
    with st.expander("HOW TO PLAY · read this first", expanded=False):
        st.markdown(
            "<div class='inc-tutorial'>"
            "<div class='inc-tutorial-row'><b>WOUNDS</b><span>Your life. Hits zero, the Incursion ends.</span></div>"
            "<div class='inc-tutorial-row'><b>SHOCK</b><span>A buffer in front of Wounds - damage empties this "
            "first, and only the leftover reaches Wounds. Rest fully restores it; MEDICAE and Wrath can too.</span></div>"
            "<div class='inc-tutorial-row'><b>WRATH</b><span>Earned when your Wrath Die (one die in every roll) "
            "shows a 6 on a hit. Spend it for a bonus attack die, or to recover Shock mid-fight.</span></div>"
            "<div class='inc-tutorial-row'><b>ICONS</b><span>Every attack rolls a pool of d6: 4-5 = 1 Icon, "
            "6 = 2 Icons. You need Icons ≥ the target's Defence to hit; extra Icons add bonus damage.</span></div>"
            "<div class='inc-tutorial-row'><b>⚔ STRIKE</b><span>Pick one or more locked targets and attack with "
            "your selected Weapon. Hitting several at once splits your dice thinner across each.</span></div>"
            "<div class='inc-tutorial-row'><b>MEDICAE / FLEE</b><span>Spend a turn to heal instead of attacking, "
            "or try to break contact and skip this fight (the enemy still gets to act either way).</span></div>"
            "<div class='inc-tutorial-row'><b>SUPPLIES</b><span>Between fights, spend this run's own XP - never "
            "your real Wealth - on Attributes, Wargear, Talents, Psychic Powers or Medicae charges.</span></div>"
            "<div class='inc-tutorial-row'><b>DUEL OF GLORY</b><span>Every third Champion slain may open a duel "
            "against another player at the same gate - purely optional, and worth a lot of XP if you win.</span></div>"
            "<div class='inc-tutorial-row'><b>ONE-WAY DOOR</b><span>Everything here - Attributes bought, gear "
            "found, XP earned - lives only in this run. Nothing is ever written back to your real character "
            "sheet, and each new Incursion starts fresh (though the Bestiary remembers how many runs you've "
            "survived, and hits harder for it).</span></div>"
            "</div>", unsafe_allow_html=True)


def _inc_render_origin_select(ch, key_prefix):
    """Origin picker + compact battle sheet, shown before starting a run
    for an incursion-kind account. Origin is a per-run choice, not locked
    to the account, so this is offered fresh every time - changing it here
    has no effect on anything except the run about to start."""
    origins = list(INC_ORIGINS.keys())
    key = f"{key_prefix}_origin"
    if st.session_state.get(key) not in origins:
        st.session_state[key] = origins[0]
    origin = st.selectbox("Origin", origins, key=key)
    attrs = _inc_origin_attributes(origin)
    talent = INC_ORIGIN_TALENTS[origin]
    attr_line = " · ".join(f"{a} {attrs[a]}" for a in ATTRS)
    weapon_dmg = int(attrs.get("Strength", 3)) + 2
    st.markdown(
        f"<div class='inc-card'><div class='inc-title'>Battle Sheet · {html.escape(origin)}</div>"
        f"<div class='inc-flavor'>{html.escape(attr_line)}</div>"
        f"<div class='inc-offer'><div class='ot'>Signature Talent</div><div class='on'>{html.escape(talent['name'])}</div>"
        f"<div class='od'>{html.escape(talent['effect'])}</div></div>"
        f"<div class='inc-offer'><div class='ot'>Starting Wargear</div><div class='on'>Incursion Combat Knife · Field Plate</div>"
        f"<div class='od'>Knife: {weapon_dmg} DMG · +1 ED · melee. Field Plate: +2 Armour.</div></div>"
        f"</div>", unsafe_allow_html=True)
    return origin


def _inc_render_intro(ch):
    st.markdown(
        "<div class='inc-card'><div class='inc-title'>Begin the Incursion</div>"
        "<div class='inc-flavor'>Your character sheet and equipment are the base for this descent. XP earned "
        "here buys Attributes, Wargear, Talents and Psychic Powers only for the duration of the run · nothing "
        "is written back to your real sheet. Every third Champion slain may open a Duel of Glory against "
        "another player who reached the same gate. The Incursion continues until you fall.</div></div>",
        unsafe_allow_html=True)
    _inc_render_tutorial()
    origin = _inc_render_origin_select(ch, "inc_intro") if ch.get("kind") == "incursion" else None
    if st.button("BEGIN INCURSION", key="inc_start", use_container_width=True):
        try:
            _inc_start_run(ch, origin=origin)
        except ValueError:
            pass
        st.rerun()


def _inc_render_dead(run, ch):
    st.markdown(
        "<div class='inc-card' style='text-align:center'>"
        "<div class='inc-title'>The Incursion Has Ended</div>"
        f"<div class='inc-flavor'>{html.escape(run.get('death_reason') or 'Fallen in battle.')}</div>"
        "<div class='inc-hud' style='justify-content:center'>"
        f"<div class='inc-chip'><b>{run['loop_no']}</b>Loops</div>"
        f"<div class='inc-chip'><b>{run['bosses_cleared']}</b>Champions</div>"
        f"<div class='inc-chip'><b>{run['xp']}</b>Final XP</div>"
        "</div></div>", unsafe_allow_html=True)
    origin = _inc_render_origin_select(ch, "inc_dead") if ch.get("kind") == "incursion" else None
    if st.button("NEW INCURSION", key="inc_restart", use_container_width=True):
        try:
            _inc_start_run(ch, origin=origin)
        except ValueError:
            pass
        st.rerun()


def _inc_render_choice_start(run, ch):
    if int(run.get("loop_no", 1) or 1) == 1:
        st.markdown("<div class='inc-card'><div class='inc-title'>First Encampment</div>"
                    "<div class='inc-flavor'>Choose one field acquisition. It costs no XP.</div></div>", unsafe_allow_html=True)
        if st.button("OPEN FIELD CACHE", key=f"inc_first_cache_{run['id']}", use_container_width=True):
            _inc_choose_start(run, ch, "first_encampment"); st.rerun()
        return
    st.markdown("<div class='inc-card'><div class='inc-title'>Encampment</div>"
                "<div class='inc-flavor'>A brief respite before pressing on.</div></div>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("<div class='inc-card'><b>Rest</b><br><span style='font-size:.8rem;opacity:.75'>"
                    "Fully recover Shock and 25% of max Wounds. Armour recovers 25-30% durability and weapons recover 25-100%.</span></div>",
                    unsafe_allow_html=True)
        if st.button("Rest", key="inc_rest", use_container_width=True):
            _inc_choose_start(run, ch, "rest"); st.rerun()
    with c2:
        st.markdown("<div class='inc-card'><b>Supplies</b><br><span style='font-size:.8rem;opacity:.75'>"
                    "Visit the field shop: weapons, talents, powers, attributes.</span></div>", unsafe_allow_html=True)
        if st.button("Supplies", key="inc_shop_choice", use_container_width=True):
            _inc_choose_start(run, ch, "shop"); st.rerun()


def _inc_render_rest_upgrade(run, ch):
    st.markdown("<div class='inc-card'><div class='inc-title'>Field Preparations</div>"
                "<div class='inc-flavor'>Train an Attribute, inspect your current armour, or move on.</div></div>",
                unsafe_allow_html=True)
    if not run["free_upgrade_used"]:
        st.info("Your first Attribute or Skill upgrade this Incursion is free.")

    merged = _inc_merge_character(ch, run)
    attrs = effective_attributes(merged)
    skills = effective_skills(merged)
    free = not run["free_upgrade_used"]

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Train Attribute**")
        attr_pick = st.selectbox("Attribute", ATTRS, key=f"inc_attr_pick_{run['id']}", label_visibility="collapsed")
        cost = 0 if free else _inc_attribute_cost(int(attrs.get(attr_pick, 1)))
        st.caption(f"Current {attr_pick}: {attrs.get(attr_pick, 1)} · Cost: {cost} XP")
        if st.button("Train Attribute", key=f"inc_train_attr_{run['id']}", disabled=run["xp"] < cost,
                     use_container_width=True):
            try:
                _inc_rest_train_attribute(run, ch, attr_pick)
            except ValueError:
                pass
            st.rerun()
    with c2:
        st.markdown("**Incursion Attributes Only**")
        st.caption("The live character's Skills, Talents, Powers, Armour and Rank are isolated from this run.")
        st.markdown("<div class='inc-card'><b>RUN-LOCAL PROGRESSION</b><br>Attributes, weapons, armour, consumables and Incursion Talents are stored only in this descent.</div>", unsafe_allow_html=True)
    with c3:
        st.markdown("**Worn Armour**")
        armour_opts = _inc_armour_options(ch, run)
        if armour_opts:
            keys = [a["key"] for a in armour_opts]
            names = {a["key"]: a["name"] for a in armour_opts}
            cur = run.get("equipped_armor_key") or keys[0]
            if cur not in keys:
                cur = keys[0]
            picked = st.selectbox("Armour", keys, index=keys.index(cur), format_func=lambda k: names[k],
                                   key=f"inc_armour_pick_{run['id']}", label_visibility="collapsed")
            if picked != run.get("equipped_armor_key"):
                _inc_rest_set_armour(run, ch, picked); st.rerun()
        else:
            st.caption("No Armour owned.")

    if st.button("Continue", key="inc_rest_continue", use_container_width=True):
        _inc_rest_continue(run, ch); st.rerun()


def _inc_render_shop(run, ch, node):
    flash_key = f"inc_purchase_flash_{run['id']}"
    flash = st.session_state.pop(flash_key, None)
    if flash:
        st.success(flash)
    error_flash = st.session_state.pop(f"{flash_key}_error", None)
    if error_flash:
        st.error(error_flash)
    if node.get("subtype") == "first_encampment":
        st.markdown("<div class='inc-card'><div class='inc-title'>First Encampment</div>"
                    "<div class='inc-flavor'>Take everything before you march — both items and the talent are free. Not happy with one? Reroll it once — it can come back as anything, not necessarily the same kind of offer.</div></div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div class='inc-card'><div class='inc-title'>Supplies</div>"
                    f"<div class='inc-flavor'>Available XP: <b>{run['xp']}</b></div></div>", unsafe_allow_html=True)
    offers = node.get("offers")
    if offers is None and node.get("subtype") == "first_encampment":
        # Only ever generate ONCE, on the very first render of this node -
        # an empty list means every offer has already been acquired, not
        # "never generated yet". Treating those the same let a player loop
        # Acquire -> list empties -> regenerate 3 more free offers forever.
        offers = _inc_generate_first_encampment_offers(ch, run)
        node = dict(node); node["offers"] = offers
        _inc_persist(run["id"], node=node)
    offers = offers or []
    type_label = {"attribute": "Attribute", "wargear": "Wargear", "talent": "Talent",
                  "power": "Psychic Power", "heal_charge": "Supply", "keyword": "Keyword",
                  "minion": "Minion", "talent_minion": "Minion Talent",
                  "tyranid_wargear": "Bio-Weapon", "tyranid_armour": "Bio-Armour"}
    if not offers:
        st.caption("Nothing left to buy here.")
    else:
        cols = st.columns(len(offers))
        for col, offer in zip(cols, offers):
            with col:
                rarity_cls = f"rarity-{str(offer.get('rarity') or 'Common').lower()}"
                st.markdown(
                    f"<div class='inc-offer {rarity_cls}'><div class='ot'>{type_label.get(offer['type'], offer['type'].title())}</div>"
                    f"<div class='on'>{html.escape(offer['label'])}</div>"
                    f"<div class='od'>{html.escape(offer.get('detail') or '')}</div>"
                    f"<div class='oc'>{offer['cost']} XP</div></div>", unsafe_allow_html=True)
                if node.get("subtype") == "first_encampment":
                    bcol1, bcol2 = st.columns(2)
                    with bcol1:
                        if st.button("Acquire", key=f"inc_buy_{offer['offer_id']}", use_container_width=True):
                            try:
                                _inc_shop_buy(run, ch, offer["offer_id"])
                                st.session_state[flash_key] = f"Acquired: {offer['label']} — see FIELD LOADOUT above."
                            except ValueError as e:
                                st.session_state[flash_key] = None
                                st.session_state[f"{flash_key}_error"] = f"Could not acquire {offer['label']} ({e})."
                            st.rerun()
                    with bcol2:
                        already_rerolled = offer["offer_id"] in (node.get("rerolled_ids") or [])
                        if st.button("Rerolled" if already_rerolled else "Reroll", key=f"inc_reroll_{offer['offer_id']}",
                                     disabled=already_rerolled, use_container_width=True):
                            try:
                                _inc_shop_reroll(run, ch, offer["offer_id"])
                            except ValueError as e:
                                st.session_state[flash_key] = None
                                st.session_state[f"{flash_key}_error"] = f"Could not reroll ({e})."
                            st.rerun()
                elif st.button("Acquire", key=f"inc_buy_{offer['offer_id']}", disabled=run["xp"] < offer["cost"],
                             use_container_width=True):
                    try:
                        _inc_shop_buy(run, ch, offer["offer_id"])
                        st.session_state[flash_key] = f"Acquired: {offer['label']} — see FIELD LOADOUT above."
                    except ValueError as e:
                        st.session_state[flash_key] = None
                        st.session_state[f"{flash_key}_error"] = f"Could not acquire {offer['label']} ({e})."
                    st.rerun()
    leave_label = "MARCH OUT" if node.get("subtype") == "first_encampment" else "Continue"
    if st.button(leave_label, key="inc_shop_leave", use_container_width=True):
        _inc_shop_leave(run, ch); st.rerun()


def _inc_wrath_spend_control(run_id, current, key_prefix, label="WRATH", compact=False):
    """Compact button based Wrath allocator used by Incursion actions."""
    state_key=f"{key_prefix}_{run_id}"
    current=max(0,int(current or 0))
    if int(current)<=0:
        st.session_state.pop(state_key, None)
        return 0
    if state_key not in st.session_state:
        st.session_state[state_key]=0
    spent=max(0,min(int(current),int(st.session_state.get(state_key,0) or 0)))
    a,b,c=st.columns([1,2,1])
    with a:
        if st.button("−",key=f"{state_key}_minus",use_container_width=True,disabled=spent<=0):
            st.session_state[state_key]=max(0,spent-1); st.rerun()
    with b:
        st.markdown(f"<div class='inc-wrath-spend'><span>{html.escape(label)}</span><b>{spent}</b><small>+{spent} DIE</small></div>",unsafe_allow_html=True)
    with c:
        if st.button("+",key=f"{state_key}_plus",use_container_width=True,disabled=spent>=int(current)):
            st.session_state[state_key]=min(int(current),spent+1); st.rerun()
    return spent


def _inc_render_combat(run, ch, node):
    diff_label={"easy":"PATROL","medium":"AMBUSH","hard":"FRONT LINE","boss":"ENEMY CHAMPION"}[node["difficulty"]]
    merged=_inc_merge_character(ch,run); traits=derived_traits(merged); live=[e for e in node["enemies"] if e["alive"]]
    target_key=f"inc_targets_{run['id']}"
    selected_targets=[uid for uid in st.session_state.get(target_key,[]) if any(e["uid"]==uid and e["alive"] for e in live)]
    if live and not selected_targets:
        selected_targets=[live[0]["uid"]]
    st.session_state[target_key]=selected_targets
    st.markdown(f"<div class='inc-combat-header'><div class='inc-kicker'>THREAT CONTACT</div><div class='inc-title'>{diff_label}</div><div class='inc-flavor'>⚔ Select targets directly. One strike can hit every locked contact.</div></div>",unsafe_allow_html=True)
    _inc_render_dice_tray(node)
    _inc_render_minion_status(run, node)
    if node.get("resolved"):
        msg="ESCAPED INTO THE DARK · NO XP AWARDED" if node.get("fled") else f"VICTORY · +{node['reward_xp']} XP"
        st.markdown(f"<div class='inc-banner-win'>{msg}</div>",unsafe_allow_html=True)
    # One-shot "just happened" animations: compare this render's log length
    # against what was stored last render, so only entries added by the most
    # recent action animate - not the whole fight's history replaying every
    # rerun.
    log_now = node.get("log") or []
    log_seen_key = f"inc_log_seen_{run['id']}_{node['difficulty']}"
    prev_seen = st.session_state.get(log_seen_key, len(log_now))
    fresh = log_now[prev_seen:] if len(log_now) > prev_seen else []
    st.session_state[log_seen_key] = len(log_now)
    fresh_hit_uids = {e.get("target_uid") for e in fresh if e.get("actor") == "player" and e.get("hit") and e.get("target_uid")}
    fresh_miss_uids = {e.get("target_uid") for e in fresh if e.get("actor") == "player" and not e.get("hit") and e.get("target_uid")}
    player_damage_taken = sum(int(e.get("damage", 0) or 0) for e in fresh if e.get("actor") == "enemy" and e.get("hit"))
    if player_damage_taken > 0:
        st.markdown(f"<div class='inc-hit-flash-player'>⚠ YOU TOOK {player_damage_taken} DAMAGE</div>", unsafe_allow_html=True)
    # Full-width enemy grid, chunked into rows of up to 3 - this scales to
    # however many enemies actually spawn (1 enemy fills the row; 4+ wraps
    # onto a second row) instead of squeezing everyone into a fixed split
    # or a fixed grid that gets nonsensically cramped as the count grows.
    enemies = node["enemies"]
    per_row = min(3, max(1, len(enemies)))
    for row_start in range(0, len(enemies), per_row):
        row = list(enumerate(enemies))[row_start:row_start + per_row]
        cols = st.columns(len(row))
        for col, (i, e) in zip(cols, row):
            with col:
                bleed=int((e.get("statuses") or {}).get("Bleeding",0) or 0)
                wounds_max=max(1,int(e.get("wounds_max",1) or 1)); wounds_cur=max(0,min(wounds_max,int(e.get("wounds_current",0) or 0)))
                shock_max=max(1,int(e.get("shock_max",1) or 1)); shock_cur=max(0,min(shock_max,int(e.get("shock_current",0) or 0)))
                wounds_pct=100.0*wounds_cur/wounds_max; shock_pct=100.0*shock_cur/shock_max
                shock_light=38.0 + (28.0 * shock_pct / 100.0)
                wounds_hue=max(0.0,min(120.0,wounds_pct*1.2))
                state="TARGET LOCK" if e["uid"] in selected_targets else ("NEUTRALIZED" if not e["alive"] else "AVAILABLE")
                state_cls="selected" if e["uid"] in selected_targets else ("dead" if not e["alive"] else "")
                threat_cls=f"tier-{max(1,min(4,int(e.get('tier',1) or 1)))}"
                visual_cls=f"enemy-v{i % 4}"
                anim_cls = "inc-just-hit" if e["uid"] in fresh_hit_uids else ("inc-just-missed" if e["uid"] in fresh_miss_uids else "")
                bleed_html=f"<span class='inc-status-blood'>BLEEDING {bleed}</span>" if bleed else ""
                st.markdown(
                    f"<div class='inc-enemy {state_cls} {threat_cls} {anim_cls}'>"
                    f"<div class='inc-enemy-strip'><span>⚔ T{i+1:02d}</span><span>{state}</span></div>"
                    f"<div class='en'>{html.escape(e['name'])}</div>"
                    f"<div class='et'>TIER {e['tier']} · {html.escape(e['weapon_name'])}</div>"
                    f"<div class='inc-npc-vitals'><span class='inc-vital wounds' style='--vital-pct:{wounds_pct:.1f}%;--vital-pct-num:{wounds_pct/100:.3f};--vital-color:#b23a35'><b>{wounds_cur}/{wounds_max}</b><span class='inc-vital-label'>WOUNDS · LIFE</span></span><span class='inc-vital shock' style='--vital-pct:{shock_pct:.1f}%;--vital-pct-num:{shock_pct/100:.3f};--vital-color:hsl(270,55%,{shock_light:.1f}%)'><b>{shock_cur}/{shock_max}</b><span class='inc-vital-label'>SHOCK</span></span><span><b>{e.get('wrath_current',0)}</b>WRATH</span></div>"
                    f"<div class='inc-npc-def'>DEF {e['defence']} · RES {e['resilience']} · SPD {e.get('speed',1)}" + (f" · ARM DUR {int(e.get('armour_durability_current',0))}/{int(e.get('armour_durability_max',0))}" if int(e.get('armour_durability_max',0) or 0) > 0 else "") + "</div>"
                    f"<div class='inc-enemy-status'>{bleed_html}</div></div>", unsafe_allow_html=True)
                if e["alive"] and not node.get("resolved"):
                    label="UNLOCK" if e["uid"] in selected_targets else "LOCK TARGET"
                    if st.button(label,key=f"inc_target_{run['id']}_{e['uid']}",use_container_width=True):
                        current=list(st.session_state.get(target_key,[])); current.remove(e["uid"]) if e["uid"] in current else current.append(e["uid"]); st.session_state[target_key]=current; st.rerun()
    if node.get("resolved"):
        if st.button("CONTINUE",key="inc_combat_continue",use_container_width=True): _inc_combat_continue(run,ch); st.rerun()
        return
    pending=node.get("pending_talent_triggers") or []
    if pending:
        tr=pending[0]; choices=[int(i) for i in tr.get("dice_indices",[])]
        st.markdown(f"<div class='inc-talent-reaction'><div class='inc-kicker'>TALENT TRIGGER</div><div class='inc-title'>Blood Must Die</div><div class='inc-flavor'>Choose 6s to apply Bleeding to {html.escape(str(tr.get('target_name','the target')))}.</div></div>",unsafe_allow_html=True)
        picked=st.session_state.get(f"inc_bmd_{run['id']}",[])
        for i in choices:
            key=f"inc_bmd_btn_{run['id']}_{i}"; active=i in picked
            if st.button(("SELECTED" if active else "SELECT")+f" · DIE {i+1}",key=key,use_container_width=True):
                picked=list(picked); picked.remove(i) if i in picked else picked.append(i); st.session_state[f"inc_bmd_{run['id']}"]=picked; st.rerun()
        if st.button("APPLY BLOOD",key=f"inc_bmd_apply_{run['id']}",disabled=not picked,use_container_width=True): _inc_resolve_pending_talent(run,ch,picked); st.rerun()
        return
    # Action row spans the full width; ATTACK packs weapon select + both
    # STRIKE buttons into one horizontal row instead of stacking each on
    # its own line - this is what actually keeps total page height down
    # now that the layout is full-width again instead of a 50/50 split.
    action=st.radio("",["ATTACK","FLEE","HEAL","ITEM"],key=f"inc_action_{run['id']}",horizontal=True,label_visibility="collapsed")
    with st.container(border=True):
        if action=="ATTACK":
            weapons=_inc_usable_weapons(ch,run); keys=[w["key"] for w in weapons]; wk=f"inc_weapon_{run['id']}"
            if st.session_state.get(wk) not in keys: st.session_state[wk]=keys[0]
            # Tiles you press, not a dropdown you have to open first - the
            # active weapon stays visually highlighted, and the melee/ranged
            # icon makes the two kinds tell apart at a glance.
            wtiles=st.columns(len(weapons))
            for wcol,w in zip(wtiles,weapons):
                with wcol:
                    active=st.session_state.get(wk)==w["key"]
                    icon="⚔" if w.get("melee") else "🔫"
                    st.markdown(
                        f"<div class='inc-weapon-tile {'active' if active else ''}'>"
                        f"<div class='wt-icon'>{icon}</div><div class='wt-name'>{html.escape(w['name'])}</div>"
                        f"<div class='wt-stats'>{w['damage']} DMG · DUR {int(w.get('durability_current',0))}/{int(w.get('durability_max',0))} · +{int(w.get('ed',0) or 0)} ED</div>"
                        f"</div>", unsafe_allow_html=True)
                    if st.button("IN USE" if active else "USE",key=f"inc_wtile_{run['id']}_{w['key']}",use_container_width=True,disabled=active):
                        st.session_state[wk]=w["key"]; st.rerun()
            _base_skill,_base_pool=_inc_best_attack_pool(merged); _shock_bonus=max(0,int(run.get("shock_current",0) or 0))
            st.caption(f"Attack pool: {_base_pool+_shock_bonus} dice ({_base_pool} from {_base_skill} + {_shock_bonus} from Shock standing)")
            wrath_avail=int(run.get("wrath_current",0) or 0)
            shock_full=int(run.get("shock_current",0) or 0)>=int(run.get("shock_max",0) or 0)
            guaranteed_hit=False; restore_shock=False
            if wrath_avail>0:
                # Wrath buys a guaranteed hit, not more dice in the pool -
                # exactly 1 Wrath, at most once per turn, no stacking.
                mode_opts=["No Wrath","Guaranteed Hit (1 Wrath)"]+([] if shock_full else ["Recover Shock Instead"])
                mode=st.radio(f"Wrath ({wrath_avail} available)",mode_opts,key=f"inc_wrath_mode_{run['id']}",horizontal=True)
                if mode=="Guaranteed Hit (1 Wrath)":
                    st.caption("Spends exactly 1 Wrath - this Strike hits automatically, no roll needed to land it.")
                    guaranteed_hit=True
                elif mode=="Recover Shock Instead":
                    st.caption("Spends exactly 1 Wrath, still attacks, no bonus die - recovers Rank + Tier Shock.")
                    restore_shock=True
            if st.button("⚔ STRIKE",key="inc_attack",use_container_width=True,disabled=not selected_targets):
                try: _inc_combat_attack(run,ch,selected_targets,st.session_state.get(wk),restore_shock=restore_shock,guaranteed_hit=guaranteed_hit)
                except ValueError as exc: st.error(str(exc).replace('_',' ').title())
                st.session_state[target_key]=[]; st.rerun()
        elif action=="FLEE":
            target=st.selectbox("Target",[e["uid"] for e in live],key=f"inc_fl_{run['id']}",format_func=lambda uid:next(e['name'] for e in live if e['uid']==uid))
            if int(run.get("wrath_current",0))>0:
                spend=_inc_wrath_spend_control(run['id'],int(run.get('wrath_current',0)),"inc_flee_wrath","+DICE THIS ROLL")
            else: spend=0
            if st.button("BREAK CONTACT",key="inc_flee",use_container_width=True):
                try: _inc_combat_flee(run,ch,target,bonus_die=int(spend))
                except ValueError as exc: st.error(str(exc).replace('_',' ').title())
                st.rerun()
        elif action=="HEAL":
            if int(run.get("wrath_current",0))>0:
                spend=_inc_wrath_spend_control(run['id'],min(1,int(run.get('wrath_current',0))),"inc_heal_wrath","+1 WRATH: EXTRA SHOCK")
            else: spend=0
            st.caption(f"Medicae charges {run['heal_charges']} · Restore Wounds and Shock")
            if st.button("MEDICAE",key="inc_heal",disabled=run['heal_charges']<1,use_container_width=True):
                try: _inc_combat_heal(run,ch,spend_wrath=int(spend))
                except ValueError as exc: st.error(str(exc).replace('_',' ').title())
                st.rerun()
        else:
            consumables=_inc_usable_consumables(ch,run)
            if not consumables:
                st.caption("No usable Consumables carried.")
            else:
                ccols=st.columns(len(consumables))
                for ccol,item in zip(ccols,consumables):
                    with ccol:
                        rarity_cls=f"rarity-{item['rarity'].lower()}"
                        heal_bits=" · ".join(x for x in [
                            f"+{item['heal_wounds']} Wounds" if item['heal_wounds'] else "",
                            f"+{item['heal_shock']} Shock" if item['heal_shock'] else ""] if x)
                        st.markdown(
                            f"<div class='inc-offer {rarity_cls}'><div class='ot'>Consumable</div>"
                            f"<div class='on'>{html.escape(item['name'])}</div>"
                            f"<div class='od'>{html.escape(heal_bits)}</div>"
                            f"<div class='oc'>×{item['remaining']}</div></div>", unsafe_allow_html=True)
                        if st.button("USE",key=f"inc_use_item_{run['id']}_{item['key']}",use_container_width=True):
                            try: _inc_combat_use_item(run,ch,item["key"])
                            except ValueError as exc: st.error(str(exc).replace('_',' ').title())
                            st.rerun()


def _inc_render_reward_choice(run, ch, node):
    is_boss = node.get("subtype") == "boss"
    title = "Champion's Due" if is_boss else "Spoils of War"
    flavor = "Choose one free Talent for downing the Champion." if is_boss else "Choose one reward, free - the other two are lost."
    st.markdown(f"<div class='inc-card'><div class='inc-title'>{title}</div><div class='inc-flavor'>{flavor}</div></div>", unsafe_allow_html=True)
    offers = node.get("offers") or []
    type_label = {"attribute": "Attribute", "wargear": "Wargear", "talent": "Talent", "power": "Psychic Power"}
    if not offers:
        st.caption("Nothing to claim here.")
        if st.button("Continue", key=f"inc_reward_choice_skip_{run['id']}", use_container_width=True):
            _inc_advance(run, ch); st.rerun()
        return
    cols = st.columns(len(offers))
    for col, offer in zip(cols, offers):
        with col:
            rarity_cls = f"rarity-{str(offer.get('rarity') or 'Common').lower()}"
            st.markdown(
                f"<div class='inc-offer {rarity_cls}'><div class='ot'>{type_label.get(offer['type'], offer['type'].title())}</div>"
                f"<div class='on'>{html.escape(offer['label'])}</div>"
                f"<div class='od'>{html.escape(offer.get('detail') or '')}</div>"
                f"<div class='oc'>FREE</div></div>", unsafe_allow_html=True)
            if st.button("TAKE", key=f"inc_reward_take_{run['id']}_{offer['offer_id']}", use_container_width=True):
                try: _inc_reward_choice_take(run, ch, offer["offer_id"])
                except ValueError as exc: st.error(str(exc).replace('_',' ').title())
                st.rerun()

def _inc_render_reward(run, ch, node):
    st.markdown(f"<div class='inc-card'><div class='inc-title'>Spoils</div>"
                f"<div class='inc-flavor'>Among the wreckage, usable supplies.</div>"
                f"<b>+{node['xp_bonus']} XP</b></div>", unsafe_allow_html=True)
    if st.button("Continue", key="inc_reward_continue", use_container_width=True):
        _inc_reward_continue(run, ch); st.rerun()


def _inc_render_pvp_choice(run, ch, node):
    label="DUEL OF GLORY" if node["checkpoint"]=="boss3" else "PLAYER CONTACT"
    st.markdown(f"<div class='inc-card'><div class='inc-title'>{label}</div><div class='inc-flavor'>Enter a live duel with another player at this checkpoint. Both operatives take turns from the same battlefield.</div></div>",unsafe_allow_html=True)
    c1,c2=st.columns(2)
    with c1:
        if st.button("ENTER DUEL",key="inc_pvp_queue",use_container_width=True): _inc_pvp_queue(run,ch); st.rerun()
    with c2:
        if st.button("CONTINUE",key="inc_pvp_skip",use_container_width=True): _inc_pvp_skip(run,ch); st.rerun()


@st.fragment(run_every=2)
def _inc_render_pvp_waiting(run, ch):
    fresh=_inc_get_run(run["id"]); node=(fresh or run).get("node") or {}
    if fresh and node.get("type")=="pvp_waiting":
        _inc_resolve_waiting_pvp(fresh,ch); fresh=_inc_get_run(run["id"]); node=(fresh or run).get("node") or {}
    if node.get("type")=="pvp_match": st.rerun(); return
    st.markdown("<div class='inc-live-panel'><div class='inc-kicker'>LIVE MATCHMAKING</div><div class='inc-title'>SEARCHING FOR OPPONENT</div><div class='inc-flavor'>This screen updates automatically. Stay here until another player enters the same gate.</div></div>",unsafe_allow_html=True)


@st.fragment(run_every=2)
def _inc_render_pvp_match(run, ch, node):
    match=_inc_get_pvp_match(node.get("match_id"))
    if not match:
        st.error("Battlefield unavailable."); return
    side=node.get("side"); state=match["state"]; me=state[side]; opp=state["b" if side=="a" else "a"]
    if state.get("winner"):
        fresh=_inc_pvp_finalize_run(run,ch,match,side); st.rerun(); return
    my_turn=state.get("turn")==side
    st.markdown(f"<div class='inc-combat-header'><div class='inc-kicker'>LIVE VOX COMBAT</div><div class='inc-title'>{html.escape(me['name'])} VS {html.escape(opp['name'])}</div><div class='inc-flavor'>{'YOUR TURN' if my_turn else 'OPPONENT TURN · LIVE FEED'}</div></div>",unsafe_allow_html=True)
    c1,c2=st.columns(2)
    with c1: st.markdown(f"<div class='inc-duel-stat'><b>{me['wounds']}/{me['wounds_max']}</b><span>WOUNDS</span><b>{me['shock']}/{me['shock_max']}</b><span>SHOCK</span><b>{me['wrath']}</b><span>WRATH</span></div>",unsafe_allow_html=True)
    with c2: st.markdown(f"<div class='inc-duel-stat enemy'><b>{opp['wounds']}/{opp['wounds_max']}</b><span>WOUNDS</span><b>{opp['shock']}/{opp['shock_max']}</b><span>SHOCK</span><b>{opp['wrath']}</b><span>WRATH</span></div>",unsafe_allow_html=True)
    if my_turn:
        weapons=_inc_usable_weapons(ch,run); keys=[w['key'] for w in weapons]; wk=f"inc_pvp_weapon_{match['id']}"
        if st.session_state.get(wk) not in keys: st.session_state[wk]=keys[0]
        st.selectbox("Weapon",keys,key=wk,format_func=lambda k: next(w['name'] for w in weapons if w['key']==k))
        if me["wrath"]>0:
            spend=_inc_wrath_spend_control(match['id'],int(me["wrath"]),"inc_pvp_wrath","WRATH TO DICE")
        else: spend=0
        if st.button("STRIKE",key=f"inc_pvp_strike_{match['id']}",use_container_width=True):
            _inc_pvp_apply_attack(match,side,int(spend)); st.rerun()
        if me["wrath"]>0:
            if st.button("RECOVER SHOCK",key=f"inc_pvp_recover_{match['id']}",use_container_width=True):
                _inc_pvp_recover_shock(match,side,int(me["wrath"])); st.rerun()
    else:
        st.markdown("<div class='inc-wait-turn'>WAITING FOR THE OPPONENT · LIVE FEED</div>",unsafe_allow_html=True)
    _inc_render_duel_log(state.get("log"))


def _inc_render_pvp_result(run, ch, node):
    title="VICTORY" if node["won"] else "DEFEAT"
    st.markdown(f"<div class='inc-banner-win'>{title} · {html.escape(node['opponent_name'])} · +{node['xp_gained']} XP</div>" if node["won"] else f"<div class='inc-banner-lose'>{title} · {html.escape(node['opponent_name'])}</div>",unsafe_allow_html=True)
    _inc_render_duel_log(node.get("log"))
    if st.button("CONTINUE",key="inc_pvp_result_continue",use_container_width=True): _inc_pvp_result_continue(run,ch); st.rerun()


def mode_chooser_page():
    st.markdown("<div class='banner'>IMPERIAL COGITATOR<span class='sub'>Choose Your Terminal</span></div>",
                unsafe_allow_html=True)
    cols = st.columns(2)
    with cols[0]:
        st.markdown(
            "<div class='mode-card system'><div class='mt'>Imperial Cogitator</div>"
            "<div class='ms'>Campaign management for the Magister and Battle-Brothers. Character sheets, "
            "combat tracking, requisitions.</div></div>", unsafe_allow_html=True)
        if st.button("ENTER THE COGITATOR", key="mode_system", use_container_width=True):
            st.session_state.app_mode = "system"; st.rerun()
    with cols[1]:
        st.markdown(
            "<div class='mode-card incursion'><div class='mt'>Wrath Incursion</div>"
            "<div class='ms'>A solo roguelike descent. Your character and equipment are the starting point · "
            "nothing you do here touches your real sheet.</div></div>", unsafe_allow_html=True)
        if st.button("ENTER THE INCURSION", key="mode_incursion", use_container_width=True):
            st.session_state.app_mode = "incursion"; st.rerun()
    st.markdown("<div class='foot'>THE EMPEROR PROTECTS</div>", unsafe_allow_html=True)


## Incursion has its own, separate registration path: no character sheet,
## no Magister approval, no waiting. Pick a Designation, an Access Code,
## and an Origin (a handful of flat Attribute bonuses) and you can descend
## immediately. This is entirely independent of the Cogitador's own
## self-registration (create_player, pending until the Magister approves) -
## a player who already has a real campaign character keeps using that
## same login here instead, unaffected by any of this.
INC_ORIGINS = {
    "Human": {"Fellowship": 1, "Intellect": 1},
    "Aeldari-Pattern": {"Agility": 2, "Initiative": 2},
    "Ork-Pattern": {"Strength": 2, "Toughness": 2},
    "Necron-Pattern": {"Toughness": 2, "Initiative": 2},
    "Tau-Pattern": {"Agility": 2, "Intellect": 2},
    "Ogryn-Pattern": {"Strength": 3, "Toughness": 1},
    "Custodes-Pattern": {"Strength": 2, "Initiative": 2},
    "Sororitas-Pattern": {"Willpower": 2, "Agility": 2},
    "Kroot-Pattern": {"Agility": 2, "Initiative": 2},
    "Genestealer-Cultist-Pattern": {"Strength": 2, "Agility": 2},
    "Death-Guard-Pattern": {"Toughness": 3, "Strength": 1},
    "Grey-Knight-Pattern": {"Willpower": 2, "Initiative": 2},
    "Chaos-Pattern": {"Strength": 2, "Willpower": 2},
    "Tyranid-Pattern": {"Agility": 2, "Toughness": 2},
    # Space Marine Chapters - each a distinct Astartes sub-origin rather
    # than one generic "Astartes-Pattern". Named with "Astartes" in the
    # string so is_astartes()/species_speed() still grant the Speed 7
    # bonus that being a Space Marine implies.
    "Ultramarines Astartes": {"Strength": 2, "Willpower": 2},
    "Blood Angels Astartes": {"Strength": 2, "Initiative": 2},
    "Dark Angels Astartes": {"Willpower": 2, "Initiative": 2},
    "Space Wolves Astartes": {"Strength": 2, "Toughness": 2},
    "Imperial Fists Astartes": {"Toughness": 2, "Willpower": 2},
    "Salamanders Astartes": {"Toughness": 2, "Fellowship": 2},
    "Raven Guard Astartes": {"Agility": 2, "Initiative": 2},
    "White Scars Astartes": {"Agility": 2, "Strength": 2},
    "Iron Hands Astartes": {"Toughness": 2, "Intellect": 2},
    "Black Templars Astartes": {"Willpower": 2, "Strength": 2},
}
INC_ORIGIN_BASE_ATTR = 3

# Each Origin's signature Talent - unique to that Origin, never offered
# through the ordinary shop pool, granted automatically for the run once
# that Origin is chosen. Origin (and therefore this Talent) is a per-run
# choice, not locked to the account - see _inc_render_origin_select.
INC_ORIGIN_TALENTS = {
    # Buffed and, for the handful most likely to be a first pick, actually
    # wired into real code (see _inc_apply_player_talent_attack_effects /
    # _inc_finish_combat_round for the "wired" ones below) rather than
    # description-only flavour.
    "Human": {"name": "Indomitable", "effect": "Once per FIGHT (not just once per Incursion), reroll any one failed Test."},  # wired
    "Aeldari-Pattern": {"name": "Battle Precognition", "effect": "Once per fight, reroll your Wrath Die AND keep the better of the two results."},
    "Ork-Pattern": {"name": "WAAAGH!", "effect": "While below half Wounds, add +2 bonus dice (not +1) to all melee attacks."},  # wired
    "Necron-Pattern": {"name": "Reanimation Protocols", "effect": "Once per fight (not just once per Incursion), if you would be reduced to 0 Wounds, instead remain at 25% Max Wounds."},  # wired
    "Tau-Pattern": {"name": "For the Greater Good", "effect": "Once per fight, add +4 bonus dice to a ranged attack."},
    "Ogryn-Pattern": {"name": "Bone 'Ead", "effect": "Reduce all Shock damage taken by 3 (minimum 0)."},
    "Custodes-Pattern": {"name": "Guardian Eternal", "effect": "Twice per fight, negate one hit entirely before damage is rolled."},
    "Sororitas-Pattern": {"name": "Shield of Faith", "effect": "Once per fight, reroll any one failed Test."},
    "Kroot-Pattern": {"name": "Pack Hunter", "effect": "+2 bonus dice on the first attack against any target no one has attacked yet this fight."},
    "Genestealer-Cultist-Pattern": {"name": "The Stars Are Right", "effect": "Every Critical Hit grants an extra attack action (no longer once per fight)."},
    "Death-Guard-Pattern": {"name": "Nurgle's Gift", "effect": "Immune to Bleeding; recover 3 Wounds (not 1) whenever you inflict Bleeding."},
    "Grey-Knight-Pattern": {"name": "Aegis of the Emperor", "effect": "Twice per fight, reduce incoming damage from a single hit by double your Willpower."},
    "Chaos-Pattern": {"name": "Dark Blessing", "effect": "Your first Guaranteed Hit or Recover Shock each fight costs 0 Wrath instead of 1."},
    "Tyranid-Pattern": {"name": "Hive Mind Link", "effect": "Your Minion's attack pool gains +4 dice and it revives once mid-fight if killed."},
    "Ultramarines Astartes": {"name": "Tactical Doctrine", "effect": "Twice per fight, reroll a missed attack."},
    "Blood Angels Astartes": {"name": "Red Thirst", "effect": "While below half Wounds, add +2 bonus dice (not +1) to melee attacks."},
    "Dark Angels Astartes": {"name": "Secrets of the Rock", "effect": "Once per fight (not just once per Incursion), avoid one Wound entirely."},
    "Space Wolves Astartes": {"name": "Curse of the Wulfen", "effect": "Melee Critical Hits deal +3 damage (not +1)."},
    "Imperial Fists Astartes": {"name": "Bolter Drill", "effect": "Ranged attacks gain +2 ED (not +1)."},
    "Salamanders Astartes": {"name": "Flame-Touched", "effect": "+3 Medicae charges (not +1) per Incursion; immune to Bleeding."},
    "Raven Guard Astartes": {"name": "Shadow Strike", "effect": "The first attack against each new enemy group gains +3 bonus dice."},
    "White Scars Astartes": {"name": "Hit and Run", "effect": "May Flee without triggering an enemy turn, twice per fight."},
    "Iron Hands Astartes": {"name": "The Flesh is Weak", "effect": "Weapon and Armour durability loss is reduced by 2 per hit (not 1)."},
    "Black Templars Astartes": {"name": "Vow of the Crusade", "effect": "While below half Wounds, add +2 bonus dice (not +1) to all attacks."},
}


def _inc_origin_attributes(origin):
    attrs = {a: INC_ORIGIN_BASE_ATTR for a in ATTRS}
    for k, v in INC_ORIGINS.get(origin, {}).items():
        attrs[k] = attrs.get(k, INC_ORIGIN_BASE_ATTR) + v
    return attrs


# ---- Minions: exclusive to Human and Tyranid-Pattern Origins -----------
# Minions are cumulative - buying a DIFFERENT Minion adds it alongside any
# others; buying the SAME Minion again levels the existing one up (full
# heal, better stats) instead of adding a duplicate. All fight alongside
# you every player action (pool driven by your Fellowship), tank hits
# meant for you in order until they drop ("leva o dano na frente"), and
# revive to full on Rest. Never a separate equip step - bought = active.
INC_MINION_ORIGINS = ("Human", "Tyranid-Pattern")
INC_MINION_RARITY_STATS = {
    "Common":    {"wounds": 8,  "shock": 4,  "resilience": 2, "damage": 3,  "ed": 1, "cost": 15},
    "Uncommon":  {"wounds": 14, "shock": 6,  "resilience": 3, "damage": 5,  "ed": 1, "cost": 30},
    "Rare":      {"wounds": 20, "shock": 8,  "resilience": 4, "damage": 7,  "ed": 2, "cost": 50},
    "Legendary": {"wounds": 30, "shock": 12, "resilience": 6, "damage": 10, "ed": 2, "cost": 80},
    "Unique":    {"wounds": 45, "shock": 16, "resilience": 8, "damage": 14, "ed": 3, "cost": 120},
}
# Rarity is also a power tier for special abilities, not just bigger
# numbers: Rare+ makes every hit Bleed the target, Legendary+ attacks
# twice per player action, Unique also hits 50% harder on top of that.
INC_MINION_RARITY_ABILITY = {
    "Common": "", "Uncommon": "",
    "Rare": "On hit, inflicts 1 Bleeding.",
    "Legendary": "On hit, inflicts 1 Bleeding. Attacks twice per action.",
    "Unique": "On hit, inflicts 1 Bleeding. Attacks twice per action. Damage +50%.",
}
INC_MINION_CATALOG = {
    "Human": {
        "Common": [{"name": "Conscript Aide", "icon": "🪖"}, {"name": "Servitor Drudge", "icon": "🤖"}, {"name": "Menial Grunt", "icon": "🔧"}],
        "Uncommon": [{"name": "Chem-Dog Handler", "icon": "🐕"}, {"name": "Scout Sniper", "icon": "🎯"}, {"name": "Combat Medic", "icon": "⚕"}],
        "Rare": [{"name": "Rough Rider Outrider", "icon": "🐴"}, {"name": "Storm Trooper", "icon": "🪂"}, {"name": "Flamer Support", "icon": "🔥"}],
        "Legendary": [{"name": "Ogryn Bodyguard", "icon": "💪"}, {"name": "Tech-Priest Enginseer", "icon": "⚙"}, {"name": "Veteran Sergeant", "icon": "🎖"}],
        "Unique": [{"name": "Primaris Lieutenant Escort", "icon": "🎖"}, {"name": "Inquisitorial Agent", "icon": "🕵"}, {"name": "Living Saint's Herald", "icon": "✨"}],
    },
    "Tyranid-Pattern": {
        "Common": [{"name": "Ripper Swarm", "icon": "🦗"}, {"name": "Spore Mine", "icon": "🍄"}, {"name": "Spinegaunt Pack", "icon": "🦂"}],
        "Uncommon": [{"name": "Termagant Brood", "icon": "🐛"}, {"name": "Gargoyle Swarm", "icon": "🦇"}, {"name": "Cursed Cherub Swarm", "icon": "🐦"}],
        "Rare": [{"name": "Hormagaunt Pack", "icon": "🏃"}, {"name": "Lictor Ambusher", "icon": "🕷"}, {"name": "Raveners", "icon": "🐍"}],
        "Legendary": [{"name": "Tyranid Warrior", "icon": "⚔"}, {"name": "Zoanthrope", "icon": "🧠"}, {"name": "Venomthrope", "icon": "☠"}],
        "Unique": [{"name": "Broodlord", "icon": "👑"}, {"name": "Hive Tyrant Guard", "icon": "🐲"}, {"name": "Trygon Prime", "icon": "🦖"}],
    },
}
# Minion-related Talents - exclusive to Human/Tyranid-Pattern; a Tyranid
# run's Talent offers are ALWAYS drawn only from this list (see
# _inc_generate_offers), never the general combat Talent pool.
INC_MINION_TALENTS = [
    {"name": "Loyal Retinue", "rarity": "Common", "effect": "Your Minions' max Wounds increase by 10 (each)."},
    {"name": "Voice of Command", "rarity": "Uncommon", "effect": "Your Minions' attack pool gains +3 dice (each)."},
    {"name": "Symbiotic Bond", "rarity": "Rare", "effect": "Whenever a Minion is hit, you recover 2 Shock."},
    {"name": "Undying Swarm", "rarity": "Legendary", "effect": "Each Minion revives once mid-fight if killed (in addition to on Rest)."},
    {"name": "Alpha Predator", "rarity": "Unique", "effect": "Your Minions' damage is doubled (each)."},
]
_INC_MINION_LEVEL_GROWTH = 0.25  # +25% to every stat per level beyond 1

# Tyranid-Pattern's own Wargear pool - "eles só podem usar coisas de
# tyranídeos": a Tyranid run's wargear offers are drawn ONLY from here
# (see _inc_generate_offers), never the generic Imperium catalog, and
# every single piece supports the Minions rather than just the player.
# minion_support is checked in _inc_resolve_player_attack; support_value
# is that effect's magnitude.
INC_TYRANID_WARGEAR = {
    "Common": [{"name": "Chitin Claw", "icon": "🦞", "melee": True, "damage": 5, "ed": 1, "ap": 0,
                "effect": "On hit, your strongest Minion recovers 2 Wounds.",
                "minion_support": "heal_strongest_on_hit", "support_value": 2}],
    "Uncommon": [{"name": "Spore Mine Launcher", "icon": "🍄", "melee": False, "damage": 6, "ed": 1, "ap": 0,
                  "effect": "On hit, all your Minions gain +2 dice on their next attack.",
                  "minion_support": "bonus_die_on_hit", "support_value": 2}],
    "Rare": [{"name": "Rending Talons", "icon": "🦂", "melee": True, "damage": 8, "ed": 2, "ap": -1,
              "effect": "On a Critical, your weakest Minion fully recovers Shock.",
              "minion_support": "shock_heal_weakest_on_crit", "support_value": 0}],
    "Legendary": [{"name": "Bio-Plasma Cannon", "icon": "☣", "melee": False, "damage": 12, "ed": 2, "ap": -2,
                   "effect": "Every 2 kills, all your Minions permanently gain +1 Damage and +2 max Shock.",
                   "minion_support": "boost_on_kills", "support_value": 2}],
    "Unique": [{"name": "The Devourer's Maw", "icon": "👄", "melee": True, "damage": 16, "ed": 3, "ap": -2,
                "effect": "Every attack revives one downed Minion at half Wounds and full Shock.",
                "minion_support": "revive_on_attack", "support_value": 0}],
}
INC_TYRANID_ARMOUR = {
    "Common": {"name": "Chitin Plating", "icon": "🛡", "armour_rating": 2},
    "Uncommon": {"name": "Carapace Hide", "icon": "🛡", "armour_rating": 3},
    "Rare": {"name": "Bio-Plated Hide", "icon": "🛡", "armour_rating": 4},
    "Legendary": {"name": "Warrior Carapace", "icon": "🛡", "armour_rating": 6},
    "Unique": {"name": "Broodlord's Exoskeleton", "icon": "🛡", "armour_rating": 8},
}


def _inc_generate_tyranid_wargear_offer():
    rarity = random.choice(_INC_RARITIES)
    if random.random() < 0.35:
        arm = INC_TYRANID_ARMOUR[rarity]
        cost = INC_MINION_RARITY_STATS[rarity]["cost"]
        return {"type": "tyranid_armour", "rarity": rarity, "name": arm["name"], "icon": arm["icon"],
                "armour_rating": arm["armour_rating"], "label": arm["name"], "cost": cost,
                "detail": f"{rarity} · Armour Rating +{arm['armour_rating']} · Tyranid bio-armour"}
    weapon = random.choice(INC_TYRANID_WARGEAR[rarity])
    cost = INC_MINION_RARITY_STATS[rarity]["cost"]
    detail = f"{rarity} · {weapon['damage']} DMG +{weapon['ed']} ED · AP {weapon['ap']} · {weapon['effect']}"
    return {"type": "tyranid_wargear", "rarity": rarity, "name": weapon["name"], "icon": weapon["icon"],
            "melee": weapon["melee"], "damage": weapon["damage"], "ed": weapon["ed"], "ap": weapon["ap"],
            "effect": weapon["effect"], "minion_support": weapon["minion_support"], "support_value": weapon["support_value"],
            "label": weapon["name"], "cost": cost, "detail": detail}


def _inc_minion_stats(name, icon, origin, rarity, level=1):
    """Stats keyed on an explicit name/icon (not re-rolled here) so
    levelling up a Minion you already own keeps its identity - only
    _inc_generate_minion_offer picks a random named variant for a NEW one."""
    stats = INC_MINION_RARITY_STATS[rarity]
    level = max(1, int(level or 1))
    mult = 1 + _INC_MINION_LEVEL_GROWTH * (level - 1)
    def scale(v): return max(1, round(v * mult))
    return {"name": name, "icon": icon, "origin": origin, "rarity": rarity, "level": level,
            "ability": INC_MINION_RARITY_ABILITY.get(rarity, ""),
            "wounds_max": scale(stats["wounds"]), "wounds_current": scale(stats["wounds"]),
            "shock_max": scale(stats["shock"]), "shock_current": scale(stats["shock"]),
            "resilience": scale(stats["resilience"]), "damage": scale(stats["damage"]),
            "ed": stats["ed"], "alive": True}


def _inc_generate_minion_offer(origin):
    rarity = random.choice(_INC_RARITIES)
    stats = INC_MINION_RARITY_STATS[rarity]
    variants = INC_MINION_CATALOG.get(origin, {}).get(rarity) or [{"name": f"{rarity} Minion", "icon": "🐾"}]
    entry = random.choice(variants)
    ability = INC_MINION_RARITY_ABILITY.get(rarity, "")
    detail = f"{rarity} · {stats['wounds']} Wounds · {stats['shock']} Shock · {stats['damage']} DMG +{stats['ed']} ED · Res {stats['resilience']}"
    if ability: detail += f" · {ability}"
    return {"type": "minion", "origin": origin, "rarity": rarity, "name": entry["name"], "icon": entry["icon"],
            "label": entry["name"], "cost": stats["cost"], "detail": detail}


def _inc_revive_minions(run):
    """Full heal on Rest - every dead Minion comes back at max Wounds/Shock."""
    minions = [dict(m) for m in (run.get("minions") or [])]
    for m in minions:
        m["wounds_current"] = int(m.get("wounds_max", 0) or 0)
        m["shock_current"] = int(m.get("shock_max", 0) or 0)
        m["alive"] = True
    return minions


def _inc_register_account(username, pw):
    """No character sheet, no Tier, no Origin at account creation - Origin
    is chosen (and can be changed) each time a run is started instead, via
    _inc_render_origin_select. This row exists only so char_id_for_user /
    load_character have something to find; none of its fields are read for
    an incursion-kind character once a run's Origin takes over."""
    username = (username or "").strip()
    if not username or not pw:
        return False, "Designation and Access Code are required."
    conn = get_conn()
    existing = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if existing:
        conn.close()
        return False, "That Designation is already taken."
    salt = secrets.token_hex(16)
    cur = conn.execute(
        "INSERT INTO users(username,pw_hash,salt,role,created_at) VALUES (?,?,?,?,?)",
        (username, hash_pw(pw, salt), salt, "player", now_iso()))
    uid = cur.lastrowid
    attrs = {a: INC_ORIGIN_BASE_ATTR for a in ATTRS}
    conn.execute(
        """INSERT INTO characters(user_id,kind,name,species,archetype,tier,starting_tier,rank,
            attributes,skills,talents,powers,wargear,armour,creation_mode,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (uid, "incursion", username, "", "Incursion Operative", 1, 1, 1,
         json.dumps(attrs), "{}", "[]", "[]", "[]", 0, "incursion", now_iso()))
    conn.commit()
    conn.close()
    return True, None


def incursion_login_page():
    if st.button("← Imperial Cogitator", key="incursion_login_back"):
        st.session_state.app_mode = "system"; st.rerun()
    st.markdown("<div class='incursion-frame'><div class='inc-banner'>WRATH INCURSION<span class='sub'>A Solo Descent Into Ruin</span></div><div class='inc-command-line'><span>ORDO MILITARIS // DESCENT TERMINAL</span><b class='live'>LIVE FEED</b><span>AUTHORITY: MAGISTER</span></div></div>", unsafe_allow_html=True)
    col = st.columns([1, 1.3, 1])[1]
    with col:
        with st.form("incursion_login"):
            u = st.text_input("Designation")
            p = st.text_input("Access Code", type="password")
            ok = st.form_submit_button("Descend")
        if ok:
            user = verify_user(u.strip(), p)
            if user and user["role"] != "spectator":
                st.session_state.user = user; st.rerun()
            else:
                st.error("Access denied.")

        with st.expander("New Operative? Register Here", expanded=False):
            st.caption("No character sheet needed, no Magister approval - descend immediately. Origin is "
                       "chosen fresh (and can be changed) every time you begin an Incursion. Already have "
                       "a campaign character? Just log in above with that same account instead.")
            with st.form("incursion_register"):
                ru = st.text_input("Designation", key="inc_reg_user")
                rpw = st.text_input("Access Code", type="password", key="inc_reg_pw")
                reg_ok = st.form_submit_button("Register & Descend")
            if reg_ok:
                success, err = _inc_register_account(ru, rpw)
                if success:
                    user = verify_user(ru.strip(), rpw)
                    st.session_state.user = user; st.rerun()
                else:
                    st.error(err)
    _inc_render_login_leaderboard()
    st.markdown("<div class='foot'>THE EMPEROR PROTECTS</div>", unsafe_allow_html=True)


def incursion_view():
    with st.sidebar:
        st.markdown("### WRATH INCURSION")
        st.write(f"User: {st.session_state.user['username']}")
        st.divider()
        if st.button("Sign Out", key="incursion_signout"):
            st.session_state.user = None; st.rerun()
        if st.button("← Imperial Cogitator", key="incursion_to_cogitator"):
            st.session_state.app_mode = "system"; st.rerun()

    st.markdown("<div class='incursion-frame'><div class='inc-banner'>WRATH INCURSION<span class='sub'>A Solo Descent Into Ruin</span></div><div class='inc-command-line'><span>ORDO MILITARIS // DESCENT TERMINAL</span><b class='live'>LIVE FEED</b><span>AUTHORITY: MAGISTER</span></div></div>", unsafe_allow_html=True)

    uid = st.session_state.user["id"]
    cid = char_id_for_user(uid)
    if cid is None:
        st.warning("This account has no character in the campaign yet. Create one in the Imperial Cogitator first.")
        return
    ch = load_character(cid)
    if ch is None:
        st.error("Character not found.")
        return

    run = _inc_get_latest_run(cid)
    if run and run["status"] == "active" and (run.get("node") or {}).get("type") == "pvp_waiting":
        run = _inc_resolve_waiting_pvp(run, ch)

    if run is None:
        _inc_render_intro(ch); return
    if run["status"] == "dead":
        _inc_render_dead(run, ch); return

    _inc_render_hud(ch, run)
    node = run.get("node") or {}
    ntype = node.get("type")

    def _dispatch():
        if ntype == "choice_start":
            _inc_render_choice_start(run, ch)
        elif ntype == "rest_upgrade":
            _inc_render_rest_upgrade(run, ch)
        elif ntype == "shop":
            _inc_render_shop(run, ch, node)
        elif ntype == "combat":
            _inc_render_combat(run, ch, node)
        elif ntype == "reward":
            _inc_render_reward(run, ch, node)
        elif ntype == "reward_choice":
            _inc_render_reward_choice(run, ch, node)
        elif ntype == "pvp_choice":
            _inc_render_pvp_choice(run, ch, node)
        elif ntype == "pvp_waiting":
            _inc_render_pvp_waiting(run, ch)
        elif ntype == "pvp_match":
            _inc_render_pvp_match(run, ch, node)
        elif ntype == "pvp_result":
            _inc_render_pvp_result(run, ch, node)

    if ntype not in ("combat", "pvp_match"):
        # Backpack lives on the right so it's always visible without eating
        # into the main flow's vertical space - not shown during combat,
        # where the weapon tiles in the action panel cover equip choices.
        main_col, pack_col = st.columns([3, 1])
        with pack_col:
            _inc_render_backpack(run, ch)
        with main_col:
            _dispatch()
    else:
        _dispatch()


def login_page():
    if st.button("ENTER THE INCURSION", key="system_login_incursion"):
        st.session_state.app_mode = "incursion"; st.rerun()
    st.markdown("<div class='banner'>IMPERIAL COGITATOR"
                "<span class='sub'>Adeptus Administratum · Campaign Record</span></div>", unsafe_allow_html=True)
    _login_hologram_globe()
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

        with st.expander("New Recruit? Register Here", expanded=False):
            st.caption("Create your own account and character. Advanced Character Creation is not offered "
                       "here - only the Magister can grant that. Your character needs the Magister's approval "
                       "before it's in the game; you can freely edit it while it's pending, but if the "
                       "Magister rejects it, the account and sheet are deleted immediately.")
            with st.form("self_register"):
                ru = st.text_input("Designation", key="self_register_user")
                rpw = st.text_input("Access Code", type="password", key="self_register_pw")
                st.markdown("**Character Definition**")
                rc2 = st.columns(2)
                rtier = rc2[0].number_input("Tier", 1, MAX_TIER, int(get_campaign()["tier"]), key="self_register_tier")
                rrank = rc2[1].selectbox("Rank", [1, 2, 3], format_func=rank_label, key="self_register_rank")
                rc1 = st.columns(2)
                rspecies = rc1[0].selectbox("Species", PLAYER_SPECIES, format_func=species_label, key="self_register_species")
                rarch = rc1[1].selectbox(
                    "Archetype", archetype_options(),
                    format_func=lambda name: f"{name}  ·  T{ARCHETYPES[name]['tier']}  ·  {ARCHETYPES[name]['faction']}",
                    key="self_register_arch"
                )
                reg_ok = st.form_submit_button("Register")
            if reg_ok:
                if not ru.strip() or not rpw:
                    st.error("Designation and Access Code are required.")
                else:
                    ok, msg = create_player(ru.strip(), rpw, "archetype", rtier, rrank, rspecies, rarch, pending=True)
                    if ok:
                        new_user = verify_user(ru.strip(), rpw)
                        if new_user:
                            st.session_state.user = new_user; st.rerun()
                    else:
                        st.error(msg)

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


@st.fragment
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
            base_attrs = {str(k): int(v) for k, v in (ch.get("attributes", {}) or {}).items()}
            # Base Attribute alongside the gear-modified one, so the Magister
            # doesn't have to open the full sheet just to see what's raw vs
            # what a Trait/Talent is adding on top.
            st.markdown("**Attributes**  " + " · ".join(
                f"{a[:3].upper()} {attrs.get(a,1)}" + (f" ({base_attrs.get(a,1)})" if attrs.get(a,1) != base_attrs.get(a,1) else "")
                for a in ATTRS))
            st.markdown("**Skills**  " + " · ".join(f"{sk[:4]} {skills.get(sk,0)+attrs.get(at,1)}" for sk, at in SKILLS.items()))
            corr = corruption_level_info(ch.get("cur_corruption", 0))
            st.caption(f"Wounds {int(ch.get('cur_wounds',0))}/{d['Max Wounds']} · Shock {int(ch.get('cur_shock',0))}/{d['Max Shock']} · Wrath {int(ch.get('cur_wrath',0))}/{d['Max Wrath']} · Corruption {corr['points']} ({corr['name']})")
        c[0].caption(f"{ch['species']} · T{ch['tier']} · Rank {rank} {vs}", unsafe_allow_html=True)
        conds = ch.get("conditions", {}) or {}
        if conds:
            badges = " ".join(
                f"<span style='background:{CONDITION_COLOR.get(n,'#b8860b')};color:#fff;padding:1px 8px;"
                f"border-radius:10px;font-size:.68rem;margin-right:3px'>{html.escape(n)}{f' ({s})' if int(s) > 1 else ''}</span>"
                for n, s in sorted(conds.items())
            )
            c[0].markdown(badges, unsafe_allow_html=True)
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


def _safe_int(val, default=0):
    """Parse a number that may come from free-form catalog JSON (e.g. a
    placeholder like '·' or 'N/A' for a field that doesn't apply to that
    item) without crashing the editor that displays it."""
    try:
        return int(val)
    except (TypeError, ValueError):
        try:
            return int(float(val))
        except (TypeError, ValueError):
            return default


def _render_wargear_data(prefix, details=None):
    details = dict(details or {}); a = st.columns(3)
    rarity_options = ["Common", "Uncommon", "Rare", "Very Rare", "Unique"]; old_rarity = str(details.get("rarity", "Common"))
    rarity = a[0].selectbox("Rarity", rarity_options, index=rarity_options.index(old_rarity) if old_rarity in rarity_options else 0, key=f"{prefix}_rarity")
    value = a[1].number_input("Value", 0, 1000000, _safe_int(details.get("value", 0)), key=f"{prefix}_value")
    category_options = ["", "weapon", "armour", "gear", "ammo", "grenade", "missile", "reload", "upgrade"]; old_category = str(details.get("category", "")).lower()
    category = a[2].selectbox("Category", category_options, index=category_options.index(old_category) if old_category in category_options else 0, key=f"{prefix}_category")
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
    # Damage is a flat number plus an optional Attribute that adds to it (p.183:
    # melee weapons add Strength - the book only ever prints "(S)", but the
    # field accepts any Attribute for homebrew items). A weapon registered
    # before this field existed (stored as free text like '(S) +5') gets its
    # flat number and Attribute parsed back out here, so opening it for edit
    # doesn't lose or reset anything.
    old_damage_text = str(details.get("damage", "")).strip()
    default_attr = str(details.get("damage_attribute", "")).strip()
    default_override = ""
    default_flat = 0
    m = re.match(r"^\(([A-Za-z]+)\)\s*\+?\s*(-?\d+)$", old_damage_text)
    if not default_attr and m:
        abbrev, num = m.group(1).upper(), int(m.group(2))
        default_flat = num
        default_attr = next((x for x in ATTRS if _attr_abbrev(x).upper() == abbrev), "")
        if not default_attr:
            default_override = old_damage_text
    elif default_attr:
        num_m = re.search(r"(-?\d+)\s*$", old_damage_text) or re.search(r"(-?\d+)", old_damage_text)
        default_flat = int(num_m.group(1)) if num_m else 0
    elif re.fullmatch(r"-?\d+", old_damage_text):
        default_flat = int(old_damage_text)
    elif old_damage_text:
        default_override = old_damage_text

    b = st.columns(5)
    dmg_flat = b[0].number_input("Damage", -20, 100, default_flat, key=f"{prefix}_damage_flat",
                                  help="The flat number from the book's Damage column.")
    attr_options = [""] + ATTRS
    dmg_attr = b[1].selectbox("+ Attribute", attr_options,
                               index=attr_options.index(default_attr) if default_attr in attr_options else 0,
                               format_func=lambda x: "None" if x == "" else x,
                               key=f"{prefix}_damage_attr",
                               help="Melee weapons add an Attribute (usually Strength, p.183) to their Damage. "
                                    "Leave as None for ranged weapons, which are already a plain number.")
    ed = b[2].number_input("ED", 0, 20, _safe_int(details.get("ed", 0)), key=f"{prefix}_ed")
    ap = b[3].number_input("AP", -20, 20, _safe_int(details.get("ap", 0)), key=f"{prefix}_ap")
    rng = b[4].text_input("Range", str(details.get("range", "")), key=f"{prefix}_range")
    c = st.columns([1, 3])
    salvo = c[0].number_input("Salvo", 0, 20, _safe_int(details.get("salvo", 0)), key=f"{prefix}_salvo")
    dmg_override = c[1].text_input("Damage Text Override", default_override, key=f"{prefix}_damage_override",
                                    help="Only for special cases the fields above can't express, like 'Uses the "
                                         "profile of the Missile fired'. Leave blank to use Damage + Attribute.")
    if dmg_override.strip():
        damage = dmg_override.strip()
    elif dmg_attr:
        sign = "+" if dmg_flat >= 0 else ""
        damage = f"({_attr_abbrev(dmg_attr)}) {sign}{int(dmg_flat)}"
    else:
        damage = str(int(dmg_flat))
    kw_options = sorted(set(_craft_keyword_options() + ["Explosive", "Bolt", "Las", "Flame", "Plasma", "Melta", "Shuriken", "Projectile", "Fire"]))
    old_kw = [str(x) for x in (details.get("keywords", []) or [])]; old_lower = {x.lower() for x in old_kw}
    keywords = st.multiselect("Wargear Keywords", kw_options, default=[x for x in kw_options if x.lower() in old_lower], key=f"{prefix}_gear_keywords")
    custom_kw = st.text_input("Other Wargear Keywords", ", ".join(x for x in old_kw if x.lower() not in {v.lower() for v in kw_options}), key=f"{prefix}_custom_keywords")
    stackable = st.checkbox("Stackable", value=bool(details.get("stackable", False)), key=f"{prefix}_stackable")
    stack_group = st.text_input("Stack Group", str(details.get("stack_group", "")), key=f"{prefix}_stack_group")
    return {"rarity": rarity, "value": int(value), "category": category, "stackable": bool(stackable), "stack_group": stack_group.strip(), "keywords": _req_list(keywords) + _req_list(custom_kw), "traits": traits, "damage": damage, "damage_attribute": dmg_attr, "ed": int(ed), "ap": int(ap), "range": rng, "salvo": int(salvo)}


def _render_power_data(prefix, details=None):
    details = dict(details or {}); a = st.columns(4)
    dn = a[0].number_input("DN", 0, 20, _safe_int(details.get("dn", 0)), key=f"{prefix}_dn")
    activation = a[1].text_input("Activation", str(details.get("activation", "")), key=f"{prefix}_activation")
    potency = a[2].number_input("Potency", 0, 20, _safe_int(details.get("potency", 0)), key=f"{prefix}_potency")
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
                ecost = st.number_input("XP Cost", 0, 10000, _safe_int(row.get("cost",0)), key=f"edit_cost_{edit_id}") if row["kind"] in ("talent","power") else 0
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

    pending = list_pending_registrations()
    with _section(f"Pending Registrations · {len(pending)}",
                  "Players who registered themselves from the login screen, without going through you "
                  "directly. They are not in the game yet - not on the roster, not addable to Combat or Vox - "
                  "until you Approve. Rejecting deletes the account and character sheet immediately.",
                  expanded=bool(pending), key="pending_registrations_section"):
        if not pending:
            st.caption("No pending self-registrations.")
        for ch in pending:
            with st.container(border=True):
                head = st.columns([3, 1])
                head[0].markdown(f"**{html.escape(ch.get('name') or 'Unnamed')}** · {species_label(ch.get('species',''))} "
                                 f"· {html.escape(ch.get('archetype') or '')} · T{ch.get('tier',1)} · {rank_label(ch.get('rank',1))}")
                if head[1].button("Open Sheet", key=f"pending_open_{ch['id']}", use_container_width=True):
                    st.session_state["editing"] = ch["id"]; st.rerun()
                bc = st.columns(2)
                if bc[0].button("Approve", key=f"pending_approve_{ch['id']}", type="primary", use_container_width=True):
                    ok, msg = approve_registration(ch["id"])
                    (st.success if ok else st.error)(msg)
                    if ok: st.rerun()
                if bc[1].button("Reject (Delete)", key=f"pending_reject_{ch['id']}", use_container_width=True):
                    ok, msg = reject_registration(ch["id"])
                    (st.success if ok else st.error)(msg)
                    if ok: st.rerun()

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
                            base_attrs = {str(k): int(v) for k, v in (ch.get("attributes", {}) or {}).items()}
                            st.markdown("**Attributes**  " + " · ".join(
                                f"{a[:3].upper()} {attrs.get(a, 1)}" + (f" ({base_attrs.get(a,1)})" if attrs.get(a,1) != base_attrs.get(a,1) else "")
                                for a in ATTRS))
                            st.markdown("**Skills**  " + " · ".join(f"{sk[:4]} {skills.get(sk, 0) + attrs.get(at, 1)}" for sk, at in SKILLS.items()))
                        temp_tag = " · ⚠ TEMP (unsaved)" if ch.get("temp_instance") else ""
                        st.caption(f"{role_label} · {species_label(ch.get('species'))} · T{ch.get('tier', 1)} · {rank_label(rank)} · {folder_name}{temp_tag}")
                        # Combat-critical Traits stay visible at a glance instead of hiding behind the popover.
                        st.caption(f"Defence {int(d.get('Defence', 0) or 0)} · Resilience {int(d.get('Resilience', 0) or 0)} "
                                   f"· Speed {int(d.get('Speed', 0) or 0)} · Resolve {int(d.get('Resolve', 0) or 0)}")
                        conds = ch.get("conditions", {}) or {}
                        if conds:
                            badges = " ".join(
                                f"<span style='background:{CONDITION_COLOR.get(n,'#b8860b')};color:#fff;padding:1px 8px;"
                                f"border-radius:10px;font-size:.68rem;margin-right:3px'>{html.escape(n)}{f' ({s})' if int(s) > 1 else ''}</span>"
                                for n, s in sorted(conds.items())
                            )
                            st.markdown(badges, unsafe_allow_html=True)
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
                  "absent players, etc.) that only ever shows current Shock · nothing else. They join by typing "
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

    with _section("Owlbear Rodeo Integration (Experimental)",
                  "Lets Players send their Attack/Damage rolls to be rolled inside Owlbear Rodeo instead of "
                  "on this page, visible to the whole table there. Requires installing the companion Owlbear "
                  "extension in your room separately - this toggle only turns the buttons on for Players. "
                  "Experimental: the dice are rolled by the Owlbear-side extension, not verified by this app."):
        owlbear_on = st.checkbox("Enable Owlbear roll buttons for Players", value=bool(camp.get("owlbear_enabled")), key="owlbear_enabled_cb")
        if owlbear_on != bool(camp.get("owlbear_enabled")):
            set_owlbear_enabled(owlbear_on); st.rerun()

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
                  "only as context for your decision · nothing here is enforced automatically.",
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
                qty_suffix = f" ×{int(r.get('quantity', 1) or 1)}" if int(r.get('quantity', 1) or 1) > 1 else ""
                head[0].markdown(f"**{html.escape(ch.get('name') or 'Unnamed')}** requests{qty_suffix}:")
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
                    equantity = int(r.get("quantity", 1) or 1)
                    if newdetails.get("stackable"):
                        equantity = st.number_input("Quantity", 1, 99, equantity, key=f"req_qty_{r['id']}")
                    if st.button("Save Edits", key=f"req_save_{r['id']}"):
                        update_requisition_item(r["id"], ename, eeffect, newdetails, equantity)
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


_BACKUP_TABLES = ["users", "folders", "characters", "campaign", "log", "session_record",
                  "session_award", "combatant", "progression_undo", "player_audit",
                  "craft_items", "custom_archetypes", "combat_encounter",
                  "combat_participant", "combat_log", "wargear_requisition"]
_BACKUP_NO_SEQUENCE = {"combatant", "campaign"}


def _export_all_tables_json():
    """Dump every table's rows as JSON - the Postgres-mode equivalent of a
    SQLite file backup, since there is no single file to hand out anymore."""
    conn = get_conn()
    dump = {}
    for t in _BACKUP_TABLES:
        rows = conn.execute(f"SELECT * FROM {t}").fetchall()
        dump[t] = [dict(r) for r in rows]
    conn.close()
    return json.dumps(dump, ensure_ascii=False, default=lambda v: v.hex() if isinstance(v, (bytes, bytearray)) else str(v))


def _import_all_tables_json(text):
    """Restore every table from a JSON export produced by _export_all_tables_json().
    Portrait (BYTEA) fields are hex-encoded by the export and decoded back here."""
    data = json.loads(text)
    if not isinstance(data, dict) or not any(t in data for t in _BACKUP_TABLES):
        return False, "That file does not look like a campaign backup export."
    conn = get_conn()
    try:
        for t in reversed(_BACKUP_TABLES):
            if t in data:
                conn.execute(f"DELETE FROM {t}")
        for t in _BACKUP_TABLES:
            rows = data.get(t) or []
            if not rows:
                continue
            cols = list(rows[0].keys())
            placeholders = ",".join("?" for _ in cols)
            sql = f"INSERT INTO {t}({','.join(cols)}) VALUES({placeholders})"
            for r in rows:
                vals = []
                for c in cols:
                    v = r.get(c)
                    if c == "portrait" and isinstance(v, str) and v:
                        try: v = bytes.fromhex(v)
                        except ValueError: pass
                    vals.append(v)
                conn.execute(sql, tuple(vals))
            if t not in _BACKUP_NO_SEQUENCE:
                maxid = conn.execute(f"SELECT MAX(id) FROM {t}").fetchone()[0]
                if maxid is not None:
                    conn.execute("SELECT setval(pg_get_serial_sequence(?, 'id'), ?)", (t, maxid))
    except Exception as exc:
        conn.close()
        return False, f"Restore failed, some tables may be partially updated: {exc}"
    conn.close()
    invalidate_craft_cache()
    return True, "Backup restored."


@st.fragment
def _gm_tab_maintenance():
    with _section("Database Maintenance", "Export or restore the campaign's data as a JSON snapshot: "
                  "players, NPCs, folders, XP, Vox, portraits, everything. Restoring overwrites all current data. "
                  "The database itself runs on Supabase, which keeps its own automatic backups independently of this."):
        st.caption("Everything saves straight to Supabase the instant it changes - there is no separate "
                   "save step and no local file to manage. This export/restore is only for your own extra "
                   "copies or moving data between campaigns.")
        if st.button("Prepare Backup for Download", key="maint_prepare_backup_pg"):
            st.session_state["maint_backup_json"] = _export_all_tables_json()
        if st.session_state.get("maint_backup_json"):
            st.download_button("Download backup (cogitador_backup.json)", st.session_state["maint_backup_json"],
                               file_name="cogitador_backup.json", mime="application/json")
        up = st.file_uploader("Restore backup", type=["json"], key="maint_restore_upload_pg")
        if up is not None and st.button("Overwrite everything", key="maint_restore_btn_pg"):
            ok, msg = _import_all_tables_json(up.getvalue().decode("utf-8"))
            if ok:
                st.session_state.pop("maint_backup_json", None)
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)


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
    Notes, nothing else · deliberately superficial."""
    camp = get_campaign()
    st.markdown(
        "<div class='spectator-banner'>✠ VOX-AUSPEX FEED ✠"
        f"<span class='sub'>{html.escape(camp.get('name', ''))} &nbsp;·&nbsp; Session {camp.get('session_no', 1)}</span>"
        "<span class='spectator-static'>◆ ◇ ◆ ◇ ◆</span></div>",
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


@st.fragment
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
        rqty = 1
        if details.get("stackable"):
            rqty = st.number_input(T("Quantity"), 1, 99, 1, key=f"reqnew_qty_{cid}")
        if st.button(T("Submit Requisition"), type="primary", use_container_width=True, key=f"reqnew_submit_{cid}"):
            if not rname.strip() or not rdesc.strip():
                st.error(T("Name and Description / Effect are required."))
            else:
                ok, msg = create_wargear_requisition(
                    cid, name=rname.strip(), effect=rdesc.strip(),
                    details={**details, "structured_rules": True, "custom": True, "official": False},
                    quantity=rqty,
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
            stackable, _ = _infer_stackable_gear(row["name"], craft_details(row))
            cqty = 1
            if stackable:
                cqty = st.number_input(T("Quantity"), 1, 99, 1, key=f"req_catalog_qty_{cid}")
            if st.button(T("Request This Item"), key=f"req_catalog_btn_{cid}"):
                ok, msg = create_wargear_requisition(cid, source_craft_id=int(row["id"]), quantity=cqty)
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
        qty_suffix = f" ×{int(r.get('quantity', 1) or 1)}" if int(r.get('quantity', 1) or 1) > 1 else ""
        cols = st.columns([5, 1.4, 1])
        cols[0].markdown(f"<div class='tal'><span class='tn'>{html.escape(r['name'])}{qty_suffix}</span>"
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
    ch = load_character(cid)
    if ch and ch.get("approval_status") == "pending":
        st.warning(T("Your registration is awaiting the Magister's approval. You can freely edit your "
                      "character sheet in the meantime, but if the Magister rejects it, your account and "
                      "sheet are deleted immediately."))
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
@st.cache_resource(show_spinner=False)
def _ensure_schema_once():
    # init_db() is pure schema setup (CREATE TABLE IF NOT EXISTS + a column
    # check per table) - dozens of round trips to Postgres. main() used to
    # call it unconditionally on every single rerun (every click, from
    # every connected session), which was most of what made the app feel
    # slow. st.cache_resource runs this body exactly once for the life of
    # the server process and shares that across every session, same as the
    # connection pool below already does.
    init_db()
    return True


def main():
    # Collapsed by default in Incursion so the run actually fills the
    # screen - the sidebar's Sign Out/nav buttons are still reachable, just
    # not eating width by default the way the campaign manager wants them to.
    sidebar_state = "collapsed" if st.session_state.get("app_mode") == "incursion" else "expanded"
    st.set_page_config(page_title="Cogitador Imperial", page_icon="✠", layout="wide", initial_sidebar_state=sidebar_state)
    inject_theme(); _ensure_schema_once()
    st.session_state.setdefault("user", None)
    st.session_state.setdefault("editing", None)
    st.session_state.setdefault("app_mode", "system")

    if st.session_state.app_mode == "incursion":
        if st.session_state.user is None:
            incursion_login_page(); return
        incursion_view(); return

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
        with st.container(border=True):
            st.markdown("<div class='inq-nav-title'>✠ TERMINAL ACCESS</div>", unsafe_allow_html=True)
            if st.button("☠  ENTER WRATH INCURSION", key="system_to_incursion", use_container_width=True):
                st.session_state.app_mode = "incursion"; st.rerun()
            if st.button("⟲  SIGN OUT", key="system_signout", use_container_width=True):
                st.session_state.user = None; st.session_state.editing = None; st.rerun()
            if st.button("←  IMPERIAL COGITATOR LOGIN", key="system_to_chooser", use_container_width=True):
                st.session_state.user = None; st.session_state.editing = None
                st.session_state.app_mode = "system"; st.rerun()

        if role == "player" and camp.get("owlbear_enabled"):
            sidebar_cid = char_id_for_user(st.session_state.user["id"])
            if sidebar_cid:
                st.divider()
                _owlbear_tests_sidebar(sidebar_cid)

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