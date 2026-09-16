import sistema as S
import uuid

S.init_db()

def make_player(origin):
    uname = f"test_tw_{uuid.uuid4().hex[:8]}"
    ok, err = S._inc_register_account(uname, "pw12345")
    assert ok, err
    conn = S.get_conn()
    user = conn.execute("SELECT id FROM users WHERE username=?", (uname,)).fetchone()
    uid = user["id"]
    cid = S.char_id_for_user(uid)
    conn.close()
    ch = S.load_character(cid)
    run = S._inc_start_run(ch, origin=origin)
    for o in list(run["node"]["offers"]):
        run = S._inc_shop_buy(run, ch, o["offer_id"])
    run = S._inc_shop_leave(run, ch)
    return uid, cid, ch, run

# --- Gating: Tyranid shop offers are ALL tyranid_wargear/tyranid_armour/talent_minion/attribute/minion/heal_charge
uid, cid, ch, run = make_player("Tyranid-Pattern")
for _ in range(15):
    offers = S._inc_generate_offers(ch, run)
    for o in offers:
        assert o["type"] in ("attribute", "tyranid_wargear", "tyranid_armour", "talent_minion", "minion", "heal_charge"), o
print("TYRANID GATING VERIFIED (no generic Imperium wargear/talents ever appear)\n")

conn = S.get_conn()
conn.execute("DELETE FROM incursion_run WHERE character_id=?", (cid,))
conn.execute("DELETE FROM characters WHERE id=?", (cid,))
conn.execute("DELETE FROM users WHERE id=?", (uid,))
conn.commit(); conn.close()

# --- Purchase + equip a tyranid_wargear item -----------------------------
uid, cid, ch, run = make_player("Tyranid-Pattern")
node = {"type": "shop", "subtype": "start", "offers": [
    {"type": "tyranid_wargear", "rarity": "Common", "name": "Chitin Claw", "icon": "🦞", "melee": True,
     "damage": 5, "ed": 1, "ap": 0, "effect": "On hit, your strongest Minion recovers 2 Wounds.",
     "minion_support": "heal_strongest_on_hit", "support_value": 2, "label": "Chitin Claw", "cost": 0,
     "detail": "", "offer_id": 0},
]}
run = S._inc_persist(run["id"], node=node)
run = S._inc_get_run(run["id"])
run = S._inc_shop_buy(run, ch, 0)
weapons = S._inc_usable_weapons(ch, run)
claw = next(w for w in weapons if w["name"] == "Chitin Claw")
print("Chitin Claw usable weapon entry:", claw)
assert claw["minion_support"] == "heal_strongest_on_hit" and claw["support_value"] == 2
print("PURCHASE + MINION_SUPPORT PASSTHROUGH VERIFIED\n")

# --- Effect: heal_strongest_on_hit ---------------------------------------
minion = S._inc_minion_stats("Ripper Swarm", "🦗", "Tyranid-Pattern", "Common", 1)
minion["wounds_current"] = 1  # damaged
run = S._inc_persist(run["id"], minions=[minion])
run = S._inc_get_run(run["id"])
node = {"type": "combat", "difficulty": "hard", "subtype": None, "resolved": False, "log": [], "reward_xp": 40,
        "enemies": [{
            "uid": "target1", "name": "Target", "tier": 1, "alive": True, "attributes": {"Initiative": 0},
            "attack_skill": "Weapon Skill", "attack_pool": 1, "defence": 0, "resilience": 0,
            "wounds_max": 999, "wounds_current": 999, "shock_max": 1, "shock_current": 1,
            "wrath_current": 0, "wrath_max": 2, "weapon_name": "Fist", "weapon_damage": 0,
            "weapon_ed": 0, "weapon_ap": 0, "armour_rating": 0, "armour_durability_max": 0,
            "armour_durability_current": 0, "speed": 1, "statuses": {},
        }]}
run = S._inc_persist(run["id"], node=node)
run = S._inc_get_run(run["id"])
run2 = S._inc_combat_attack(run, ch, ["target1"], claw["key"], guaranteed_hit=True)
print(f"minion wounds after Chitin Claw hit: {run2['minions'][0]['wounds_current']} (expected 3)")
assert run2["minions"][0]["wounds_current"] == 3
print("heal_strongest_on_hit VERIFIED\n")

conn = S.get_conn()
conn.execute("DELETE FROM incursion_run WHERE character_id=?", (cid,))
conn.execute("DELETE FROM characters WHERE id=?", (cid,))
conn.execute("DELETE FROM users WHERE id=?", (uid,))
conn.commit(); conn.close()

# --- Effect: revive_on_attack (Unique) -----------------------------------
uid, cid, ch, run = make_player("Tyranid-Pattern")
node = {"type": "shop", "subtype": "start", "offers": [
    {"type": "tyranid_wargear", "rarity": "Unique", "name": "The Devourer's Maw", "icon": "👄", "melee": True,
     "damage": 16, "ed": 3, "ap": -2, "effect": "revive", "minion_support": "revive_on_attack", "support_value": 0,
     "label": "The Devourer's Maw", "cost": 0, "detail": "", "offer_id": 0},
]}
run = S._inc_persist(run["id"], node=node)
run = S._inc_get_run(run["id"])
run = S._inc_shop_buy(run, ch, 0)
dead_minion = S._inc_minion_stats("Broodlord", "👑", "Tyranid-Pattern", "Unique", 1)
dead_minion["alive"] = False; dead_minion["wounds_current"] = 0
run = S._inc_persist(run["id"], minions=[dead_minion])
run = S._inc_get_run(run["id"])
node2 = {"type": "combat", "difficulty": "hard", "subtype": None, "resolved": False, "log": [], "reward_xp": 40,
         "enemies": [{
             "uid": "target2", "name": "Target2", "tier": 1, "alive": True, "attributes": {"Initiative": 0},
             "attack_skill": "Weapon Skill", "attack_pool": 1, "defence": 0, "resilience": 999,
             "wounds_max": 999, "wounds_current": 999, "shock_max": 1, "shock_current": 1,
             "wrath_current": 0, "wrath_max": 2, "weapon_name": "Fist", "weapon_damage": 0,
             "weapon_ed": 0, "weapon_ap": 0, "armour_rating": 0, "armour_durability_max": 0,
             "armour_durability_current": 0, "speed": 1, "statuses": {},
         }]}
run = S._inc_persist(run["id"], node=node2)
run = S._inc_get_run(run["id"])
weapons = S._inc_usable_weapons(ch, run)
maw = next(w for w in weapons if w["name"] == "The Devourer's Maw")
run2 = S._inc_combat_attack(run, ch, ["target2"], maw["key"])  # not guaranteed hit; should revive regardless of hit
m = run2["minions"][0]
print(f"minion after Devourer's Maw attack: alive={m['alive']} wounds={m['wounds_current']}/{m['wounds_max']}")
assert m["alive"] is True
print("revive_on_attack VERIFIED")

conn = S.get_conn()
conn.execute("DELETE FROM incursion_run WHERE character_id=?", (cid,))
conn.execute("DELETE FROM characters WHERE id=?", (cid,))
conn.execute("DELETE FROM users WHERE id=?", (uid,))
conn.commit(); conn.close()
print("\nALL CHECKS PASSED")
