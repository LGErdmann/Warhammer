import sistema as S
import uuid

S.init_db()

def make_player(origin):
    uname = f"test_mm_{uuid.uuid4().hex[:8]}"
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

uid, cid, ch, run = make_player("Human")

# Buy a Common minion, then a Rare minion (different) - should stack to 2.
common_offer = {"type":"minion","origin":"Human","rarity":"Common", **{k:v for k,v in S._inc_generate_minion_offer("Human").items() if k not in ("type","origin","rarity")}}
node = {"type": "shop", "subtype": "start", "offers": [{**common_offer, "offer_id": 0}]}
run = S._inc_persist(run["id"], node=node, xp=9999)
run = S._inc_get_run(run["id"])
# Force a Common minion directly via a controlled offer instead of random.
common = S._inc_minion_stats("Human", "Common", 1)
node = {"type": "shop", "subtype": "start", "offers": [
    {"type":"minion","origin":"Human","rarity":"Common","name":common["name"],"icon":common["icon"],"label":common["name"],"cost":0,"detail":"","offer_id":0},
]}
run = S._inc_persist(run["id"], node=node)
run = S._inc_get_run(run["id"])
run = S._inc_shop_buy(run, ch, 0)
print("after buying Common:", [(m["name"], m["level"]) for m in run["minions"]])
assert len(run["minions"]) == 1

rare = S._inc_minion_stats("Human", "Rare", 1)
node = {"type": "shop", "subtype": "start", "offers": [
    {"type":"minion","origin":"Human","rarity":"Rare","name":rare["name"],"icon":rare["icon"],"label":rare["name"],"cost":0,"detail":"","offer_id":0},
]}
run = S._inc_persist(run["id"], node=node)
run = S._inc_get_run(run["id"])
run = S._inc_shop_buy(run, ch, 0)
print("after buying Rare (different):", [(m["name"], m["level"]) for m in run["minions"]])
assert len(run["minions"]) == 2, "different minions should stack"

# Buy the SAME Common minion again - should level it up, not add a duplicate.
node = {"type": "shop", "subtype": "start", "offers": [
    {"type":"minion","origin":"Human","rarity":"Common","name":common["name"],"icon":common["icon"],"label":common["name"],"cost":0,"detail":"","offer_id":0},
]}
run = S._inc_persist(run["id"], node=node)
run = S._inc_get_run(run["id"])
run = S._inc_shop_buy(run, ch, 0)
print("after buying Common again:", [(m["name"], m["level"], m["wounds_max"]) for m in run["minions"]])
assert len(run["minions"]) == 2, "same minion should level up, not duplicate"
common_minion = next(m for m in run["minions"] if m["name"] == common["name"])
assert common_minion["level"] == 2
assert common_minion["wounds_max"] > common["wounds_max"]
print("CUMULATIVE STACKING + LEVEL-UP VERIFIED\n")

conn = S.get_conn()
conn.execute("DELETE FROM incursion_run WHERE character_id=?", (cid,))
conn.execute("DELETE FROM characters WHERE id=?", (cid,))
conn.execute("DELETE FROM users WHERE id=?", (uid,))
conn.commit(); conn.close()

# --- Rarity abilities: Rare bleeds, Legendary attacks twice, Unique +50% dmg
uid, cid, ch, run = make_player("Human")
run = S._inc_persist(run["id"], minions=[S._inc_minion_stats("Human", "Legendary", 1)])
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
run2 = S._inc_combat_attack(run, ch, ["target1"], "__unarmed__", guaranteed_hit=True)
minion_entries = [e for e in run2["node"]["log"] if e.get("actor") == "minion"]
print(f"Legendary minion attacks this action: {len(minion_entries)} (should be 2)")
assert len(minion_entries) == 2, "Legendary should attack twice"
target_after = run2["node"]["enemies"][0]
print("target bleeding after Legendary hit:", target_after.get("statuses", {}).get("Bleeding"))
assert target_after.get("statuses", {}).get("Bleeding", 0) >= 1, "Legendary (Rare+) should inflict Bleeding"
print("RARITY ABILITIES (double attack + bleeding) VERIFIED")

conn = S.get_conn()
conn.execute("DELETE FROM incursion_run WHERE character_id=?", (cid,))
conn.execute("DELETE FROM characters WHERE id=?", (cid,))
conn.execute("DELETE FROM users WHERE id=?", (uid,))
conn.commit(); conn.close()
print("\nALL CHECKS PASSED")
