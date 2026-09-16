import sistema as S
import uuid

S.init_db()

def make_player(origin):
    uname = f"test_min_{uuid.uuid4().hex[:8]}"
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

# --- Gating: Ork-Pattern (not minion-eligible) never sees minion offers --
uid, cid, ch, run = make_player("Ork-Pattern")
offers = S._inc_generate_offers(ch, run)
print("Ork-Pattern shop offers:", [o["type"] for o in offers])
assert all(o["type"] != "minion" for o in offers), "Ork should never see minion offers"
conn = S.get_conn()
conn.execute("DELETE FROM incursion_run WHERE character_id=?", (cid,))
conn.execute("DELETE FROM characters WHERE id=?", (cid,))
conn.execute("DELETE FROM users WHERE id=?", (uid,))
conn.commit(); conn.close()
print("GATING VERIFIED\n")

# --- Human: guaranteed minion slot in shop; buying it equips immediately -
uid, cid, ch, run = make_player("Human")
offers = S._inc_generate_offers(ch, run)
print("Human shop offers:", [(o["type"], o.get("label")) for o in offers])
minion_offer = next(o for o in offers if o["type"] == "minion")
node = {"type": "shop", "subtype": "start", "offers": offers}
run = S._inc_persist(run["id"], node=node, xp=9999)
run = S._inc_get_run(run["id"])
run = S._inc_shop_buy(run, ch, minion_offer["offer_id"])
print("minion after purchase:", run["minion"])
assert run["minion"]["alive"] and run["minion"]["origin"] == "Human"
print("PURCHASE/AUTO-EQUIP VERIFIED\n")

# --- Combat: minion tanks a hit, minion attacks alongside player --------
node = {"type": "combat", "difficulty": "hard", "subtype": None, "resolved": False, "log": [], "reward_xp": 40,
        "enemies": [{
            "uid": "brute", "name": "Brute", "tier": 1, "alive": True, "attributes": {"Initiative": 0},
            "attack_skill": "Weapon Skill", "attack_pool": 20, "defence": 0, "resilience": 0,
            "wounds_max": 999, "wounds_current": 999, "shock_max": 1, "shock_current": 1,
            "wrath_current": 0, "wrath_max": 2, "weapon_name": "Fist", "weapon_damage": 30,
            "weapon_ed": 0, "weapon_ap": 0, "armour_rating": 0, "armour_durability_max": 0,
            "armour_durability_current": 0, "speed": 1, "statuses": {},
        }]}
run = S._inc_persist(run["id"], node=node)
run = S._inc_get_run(run["id"])
pre_wounds = run["wounds_current"]
pre_minion_wounds = run["minion"]["wounds_current"]
run2 = S._inc_combat_attack(run, ch, ["brute"], "__unarmed__", guaranteed_hit=True)
minion_entry = next((e for e in run2["node"]["log"] if e.get("actor") == "minion"), None)
enemy_entry = next(e for e in run2["node"]["log"] if e.get("actor") == "enemy")
print("minion attack entry:", minion_entry)
print("enemy attack entry (should target minion):", {k: enemy_entry[k] for k in ("target", "minion_damage", "wounds")})
print(f"player wounds unchanged: {pre_wounds} -> {run2['wounds_current']}")
print(f"minion wounds: {pre_minion_wounds} -> {run2['minion']['wounds_current']}")
assert minion_entry is not None, "minion should have attacked"
assert enemy_entry["target"] == "minion", "enemy hit should have been redirected to the minion"
assert enemy_entry["wounds"] == 0, "player should take 0 wounds while minion tanks"
assert run2["wounds_current"] == pre_wounds
assert run2["minion"]["wounds_current"] < pre_minion_wounds
print("TANKING + MINION ATTACK VERIFIED\n")

# --- Kill the minion, then Rest revives it -------------------------------
conn = S.get_conn()
conn.execute("SELECT 1")
conn.close()
run3 = S._inc_persist(run2["id"], minion={**run2["minion"], "wounds_current": 0, "alive": False})
run3 = S._inc_get_run(run3["id"])
print("minion status before rest:", run3["minion"]["alive"], run3["minion"]["wounds_current"])
run3 = S._inc_persist(run3["id"], node={"type": "choice_start"})
run3 = S._inc_get_run(run3["id"])
run4 = S._inc_choose_start(run3, ch, "rest")
print("minion status after rest:", run4["minion"]["alive"], run4["minion"]["wounds_current"], "/", run4["minion"]["wounds_max"])
assert run4["minion"]["alive"] and run4["minion"]["wounds_current"] == run4["minion"]["wounds_max"]
print("REVIVE ON REST VERIFIED")

conn = S.get_conn()
conn.execute("DELETE FROM incursion_run WHERE character_id=?", (cid,))
conn.execute("DELETE FROM characters WHERE id=?", (cid,))
conn.execute("DELETE FROM users WHERE id=?", (uid,))
conn.commit(); conn.close()
print("\nALL MINION CHECKS PASSED")
