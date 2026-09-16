import sistema as S
import uuid

S.init_db()

def make_player(origin):
    uname = f"test_apexv2_{uuid.uuid4().hex[:8]}"
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

def cleanup(uid, cid):
    conn = S.get_conn()
    conn.execute("DELETE FROM incursion_run WHERE character_id=?", (cid,))
    conn.execute("DELETE FROM characters WHERE id=?", (cid,))
    conn.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit(); conn.close()

uid, cid, ch, run = make_player("Tyranid-Pattern")
apex = next(m for m in run["minions"] if m["name"] == "Apex Tyranid")
print("Apex on start: bonus_die =", apex.get("bonus_die"), "bulk =", apex.get("bulk"))
assert apex.get("bonus_die") == 3, f"expected starting bonus_die=3, got {apex.get('bonus_die')}"
assert apex.get("bulk") is True, "Apex Tyranid must start with Bulk"
print("APEX STARTS WITH 3 BONUS DICE + BULK - VERIFIED\n")

print(f"player wounds_max={run['wounds_max']} (expect 5 + 10% of apex wounds_max={apex['wounds_max']} = {5 + round(apex['wounds_max']*0.10)})")
assert run["wounds_max"] == 5 + round(apex["wounds_max"] * 0.10)
print("TYRANID PLAYER WOUNDS = 5 FIXED + 10% OF APEX WOUNDS - VERIFIED\n")

# --- consume mechanic: 50%/50%, rarity-scaled bonus dice --------------------
weak_minion = S._inc_minion_stats("Weakling", "", "Tyranid-Pattern", "Rare", 1)  # Rare -> rank 2 -> +3 dice
weak_minion["wounds_max"] = 20; weak_minion["wounds_current"] = 20
weak_minion["shock_max"] = 10; weak_minion["shock_current"] = 10
run = S._inc_persist(run["id"], minions=run["minions"] + [weak_minion])
run = S._inc_get_run(run["id"])
apex_before = next(m for m in run["minions"] if m["name"] == "Apex Tyranid")
wm_before, sm_before, bd_before = apex_before["wounds_max"], apex_before["shock_max"], apex_before.get("bonus_die", 0)
player_wounds_max_before = run["wounds_max"]

run = S._inc_persist(run["id"], stage="boss")
run = S._inc_get_run(run["id"])
run2 = S._inc_advance(run, ch)
apex_after = next(m for m in run2["minions"] if m["name"] == "Apex Tyranid")
print(f"wounds_max {wm_before} -> {apex_after['wounds_max']} (expect +{round(20*0.5)})")
print(f"shock_max {sm_before} -> {apex_after['shock_max']} (expect +{round(10*0.5)})")
print(f"bonus_die {bd_before} -> {apex_after['bonus_die']} (expect +3 for Rare)")
assert apex_after["wounds_max"] == wm_before + round(20 * 0.5)
assert apex_after["shock_max"] == sm_before + round(10 * 0.5)
assert apex_after["bonus_die"] == bd_before + 3
print("APEX 50%/50% ABSORPTION + RARITY-SCALED BONUS DIE - VERIFIED\n")

print(f"player wounds_max {player_wounds_max_before} -> {run2['wounds_max']} (expect 5 + 10% of new apex wounds_max={apex_after['wounds_max']} = {5+round(apex_after['wounds_max']*0.10)})")
assert run2["wounds_max"] == 5 + round(apex_after["wounds_max"] * 0.10)
print("PLAYER WOUNDS RECOMPUTED AFTER APEX GROWS - VERIFIED\n")

# --- Apex pool actually rolls with its accumulated bonus_die ---------------
node = {"log": [], "enemies": [{"name": "Dummy", "uid": "d-0", "alive": True, "resilience": 0,
                                  "wounds_current": 100000, "wounds_max": 100000, "shock_current": 0, "defence": 0}]}
merged = {"attributes": {"Fellowship": 30}}
minions_for_attack = [dict(apex_after)]
minions_for_attack[0]["shock_current"] = 0
log = S._inc_minion_group_attack(minions_for_attack, node, merged)
pool_used = log[0]["pool"]
expected_min_pool = 30 + 0 + apex_after["bonus_die"]
print(f"Apex attack pool = {pool_used} (fellowship 30 + shock 0 + bonus_die {apex_after['bonus_die']} = {expected_min_pool})")
assert pool_used == expected_min_pool
print("ACCUMULATED BONUS DIE REFLECTED IN REAL ATTACK POOL - VERIFIED\n")

cleanup(uid, cid)
print("ALL CHECKS PASSED")
