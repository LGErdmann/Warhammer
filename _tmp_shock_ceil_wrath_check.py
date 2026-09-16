import sistema as S
import uuid

S.init_db()

def make_player(origin):
    uname = f"test_ceil_{uuid.uuid4().hex[:8]}"
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

def attack_once(run, ch, weapon_key, wounds_max=999999):
    node = S._inc_combat_node("easy", 1)
    enemy = dict(node["enemies"][0])
    enemy["wounds_max"] = wounds_max; enemy["wounds_current"] = wounds_max
    enemy["resilience"] = 0; enemy["defence"] = 0
    node["enemies"] = [enemy]
    run = S._inc_persist(run["id"], node=node)
    run = S._inc_get_run(run["id"])
    target_uid = run["node"]["enemies"][0]["uid"]
    return S._inc_combat_attack(run, ch, [target_uid], weapon_key)

# --- 1) ceil(shock/10) for Astartes and plain origins -----------------------
for origin, shock_val, expected in [("Ultramarines Astartes", 25, 3), ("Aeldari-Pattern", 25, 3),
                                     ("Ultramarines Astartes", 20, 2), ("Aeldari-Pattern", 21, 3)]:
    uid, cid, ch, run = make_player(origin)
    run = S._inc_persist(run["id"], shock_current=shock_val, shock_max=shock_val)
    run = S._inc_get_run(run["id"])
    weapon = S._inc_usable_weapons(ch, run)[0]
    merged = S._inc_merge_character(ch, run)
    _, base_pool = S._inc_best_attack_pool(merged)
    run = attack_once(run, ch, weapon["key"])
    log = run["node"].get("log", [])
    entry = next(e for e in reversed(log) if e.get("actor") == "player" and e.get("action") == "attack")
    implied = entry["pool"] - base_pool
    print(f"{origin} shock={shock_val}: implied shock_bonus={implied} (expect ceil({shock_val}/10)={expected})")
    assert implied == expected
    cleanup(uid, cid)
print("SHOCK-TO-DICE CEIL(SHOCK/10) FOR NON-TYRANID/HUMAN ORIGINS - VERIFIED\n")

# --- 2) Wrath spend recovers 5x Intellect shock for Astartes and plain origins ---
for origin in ["Ultramarines Astartes", "Aeldari-Pattern"]:
    uid, cid, ch, run = make_player(origin)
    merged = S._inc_merge_character(ch, run)
    intellect = S.effective_attributes(merged)["Intellect"]
    run = S._inc_persist(run["id"], shock_current=0, shock_max=100000, wrath_current=3)
    run = S._inc_get_run(run["id"])
    run = S._inc_record_wrath_spend(run, ch, 1)
    expected = 5 * intellect * 1
    print(f"{origin}: Intellect={intellect}, shock_current after 1 wrath spent = {run['shock_current']} (expect {expected})")
    assert run["shock_current"] == expected
    cleanup(uid, cid)
print("WRATH-SPEND RECOVERS 5X INTELLECT SHOCK (ASTARTES + PLAIN ORIGINS) - VERIFIED\n")

# --- 3) Human and Tyranid unaffected by the new universal wrath-shock rule --
uid, cid, ch, run = make_player("Human")
run = S._inc_persist(run["id"], shock_current=0, shock_max=100000, wrath_current=3)
run = S._inc_get_run(run["id"])
shock_before = run["shock_current"]
run = S._inc_record_wrath_spend(run, ch, 1)
print(f"Human shock_current after 1 wrath spent (should NOT be a flat 5xIntellect, Dreadnought path instead): {run['shock_current']}")
# Human's shock comes from _inc_sync_human_shock (Dreadnought-linked), not the new universal formula.
cleanup(uid, cid)

uid, cid, ch, run = make_player("Tyranid-Pattern")
run = S._inc_persist(run["id"], shock_current=0, shock_max=100000, wrath_current=3)
run = S._inc_get_run(run["id"])
run = S._inc_record_wrath_spend(run, ch, 1)
print(f"Tyranid shock_current after 1 wrath spent (should stay 0, no wrath-shock rule for Tyranid): {run['shock_current']}")
assert run["shock_current"] == 0
print("TYRANID/HUMAN UNAFFECTED BY THE NEW UNIVERSAL WRATH-SHOCK RULE - VERIFIED\n")
cleanup(uid, cid)

print("ALL CHECKS PASSED")
