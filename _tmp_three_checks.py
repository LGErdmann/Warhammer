import sistema as S
import uuid

S.init_db()

def make_player(origin="Human"):
    uname = f"test3_{uuid.uuid4().hex[:8]}"
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

# --- 1) Post-combat recovery: 20% wounds + 10 shock -------------------
uid, cid, ch, run = make_player()
node = dict(run["node"])
node["enemies"][0]["wounds_current"] = 1  # one hit from dead
run = S._inc_persist(run["id"], node=node, wounds_current=5, shock_current=0)
run = S._inc_get_run(run["id"])
print(f"before victory: wounds={run['wounds_current']}/{run['wounds_max']} shock={run['shock_current']}/{run['shock_max']}")
target_uid = run["node"]["enemies"][0]["uid"]
run2 = S._inc_combat_attack(run, ch, [target_uid], "__unarmed__", guaranteed_hit=True)
print(f"after victory:  wounds={run2['wounds_current']}/{run2['wounds_max']} shock={run2['shock_current']}/{run2['shock_max']} node_type={run2['node'].get('type')}")
expected_wounds = min(run["wounds_max"], 5 + round(run["wounds_max"] * 0.20))
expected_shock = min(run["shock_max"], 0 + 10)
assert run2["wounds_current"] == expected_wounds, (run2["wounds_current"], expected_wounds)
assert run2["shock_current"] == expected_shock, (run2["shock_current"], expected_shock)
print("POST-COMBAT RECOVERY VERIFIED")

conn = S.get_conn()
conn.execute("DELETE FROM incursion_run WHERE character_id=?", (cid,))
conn.execute("DELETE FROM characters WHERE id=?", (cid,))
conn.execute("DELETE FROM users WHERE id=?", (uid,))
conn.commit(); conn.close()

# --- 2) Talent purchase grants shock based on rarity -------------------
uid, cid, ch, run = make_player()
before_shock_max = run["shock_max"]
# Find any talent offer type; if none, force one via the shop pool.
offers = S._inc_generate_offers(ch, run)
talent_offer = next((o for o in offers if o["type"] == "talent"), None)
if talent_offer is None:
    # generate a batch until we find a talent offer (random selection)
    for _ in range(20):
        offers = S._inc_generate_offers(ch, run)
        talent_offer = next((o for o in offers if o["type"] == "talent"), None)
        if talent_offer:
            break
assert talent_offer is not None, "could not find a talent offer to test"
node = {"type": "shop", "subtype": "random", "offers": offers}
run = S._inc_persist(run["id"], node=node, xp=9999)
run = S._inc_get_run(run["id"])
run = S._inc_shop_buy(run, ch, talent_offer["offer_id"])
rarity = talent_offer.get("rarity", "Common")
expected_bonus = S._INC_TALENT_SHOCK_BONUS.get(rarity, 2)
print(f"bought {rarity} talent '{talent_offer['label']}': shock_max {before_shock_max} -> {run['shock_max']} (expected +{expected_bonus})")
assert run["shock_max"] == before_shock_max + expected_bonus
print("TALENT-RARITY SHOCK BONUS VERIFIED")

conn = S.get_conn()
conn.execute("DELETE FROM incursion_run WHERE character_id=?", (cid,))
conn.execute("DELETE FROM characters WHERE id=?", (cid,))
conn.execute("DELETE FROM users WHERE id=?", (uid,))
conn.commit(); conn.close()

# --- 3) Turn order by Initiative ---------------------------------------
uid, cid, ch, run = make_player()
node = dict(run["node"])
# Slow player (Human base Initiative=3) vs a much faster enemy.
node["enemies"] = [{
    "uid": "fast-enemy", "name": "Blur", "tier": 1, "alive": True,
    "attributes": {"Initiative": 99}, "attack_skill": "Weapon Skill", "attack_pool": 1,
    "defence": 0, "resilience": 99, "wounds_max": 999, "wounds_current": 999,
    "shock_max": 10, "shock_current": 10, "wrath_current": 0, "wrath_max": 2,
    "weapon_name": "Fast Jab", "weapon_damage": 1, "weapon_ed": 0, "weapon_ap": 0,
    "armour_rating": 0, "armour_durability_max": 0, "armour_durability_current": 0,
    "speed": 1, "statuses": {},
}]
run = S._inc_persist(run["id"], node=node)
run = S._inc_get_run(run["id"])
run2 = S._inc_combat_attack(run, ch, ["fast-enemy"], "__unarmed__", guaranteed_hit=True)
actors_in_order = [e["actor"] for e in run2["node"]["log"] if e.get("action") == "attack"]
print("actor order (fast enemy should go first):", actors_in_order)
assert actors_in_order[0] == "enemy", actors_in_order

conn = S.get_conn()
conn.execute("DELETE FROM incursion_run WHERE character_id=?", (cid,))
conn.execute("DELETE FROM characters WHERE id=?", (cid,))
conn.execute("DELETE FROM users WHERE id=?", (uid,))
conn.commit(); conn.close()

# --- 3b) Turn order when PLAYER is faster (should stay player-first) --
uid, cid, ch, run = make_player()
node = dict(run["node"])
node["enemies"] = [{
    "uid": "slow-enemy", "name": "Slug", "tier": 1, "alive": True,
    "attributes": {"Initiative": 0}, "attack_skill": "Weapon Skill", "attack_pool": 1,
    "defence": 0, "resilience": 99, "wounds_max": 999, "wounds_current": 999,
    "shock_max": 10, "shock_current": 10, "wrath_current": 0, "wrath_max": 2,
    "weapon_name": "Slow Jab", "weapon_damage": 1, "weapon_ed": 0, "weapon_ap": 0,
    "armour_rating": 0, "armour_durability_max": 0, "armour_durability_current": 0,
    "speed": 1, "statuses": {},
}]
run = S._inc_persist(run["id"], node=node)
run = S._inc_get_run(run["id"])
run2 = S._inc_combat_attack(run, ch, ["slow-enemy"], "__unarmed__", guaranteed_hit=True)
actors_in_order = [e["actor"] for e in run2["node"]["log"] if e.get("action") == "attack"]
print("actor order (player faster, player should go first):", actors_in_order)
assert actors_in_order[0] == "player", actors_in_order
print("INITIATIVE TURN ORDER VERIFIED (both directions)")

conn = S.get_conn()
conn.execute("DELETE FROM incursion_run WHERE character_id=?", (cid,))
conn.execute("DELETE FROM characters WHERE id=?", (cid,))
conn.execute("DELETE FROM users WHERE id=?", (uid,))
conn.commit(); conn.close()
print("ALL CHECKS PASSED")
