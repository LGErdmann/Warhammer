import sistema as S
import uuid

S.init_db()

def make_player(origin):
    uname = f"test_rev_{uuid.uuid4().hex[:8]}"
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

def kill_minion(run, name):
    minions = [dict(m) for m in run["minions"]]
    for m in minions:
        if m["name"] == name:
            m["alive"] = False; m["wounds_current"] = 0
    return S._inc_persist(run["id"], minions=minions)

# --- 1) Bulk only ever comes from Human/Tyranid sources ---------------------
non_ht_origins = [o for o in S.INC_ORIGIN_HELPER_MINION.keys()]
for origin in non_ht_origins:
    uid, cid, ch, run = make_player(origin)
    assert not run["minions"][0].get("bulk"), f"{origin}'s helper minion should never have bulk"
    cleanup(uid, cid)
print("BULK NEVER LEAKS TO NON-HUMAN/TYRANID HELPER MINIONS - VERIFIED\n")

# --- 2) Every-2-turn mid-fight passive revival: Tyranid only -----------------
uid, cid, ch, run = make_player("Human")
run = kill_minion(run, "Dreadnought")
run = S._inc_get_run(run["id"])
node = S._inc_combat_node("easy", 1)
tank = dict(node["enemies"][0]); tank["wounds_max"]=100000; tank["wounds_current"]=100000; tank["resilience"]=0
node["enemies"] = [tank]
run = S._inc_persist(run["id"], node=node)
run = S._inc_get_run(run["id"])
weapon = S._inc_usable_weapons(ch, run)[0]
for i in range(6):
    node = S._inc_combat_node("easy", 1)
    tank = dict(node["enemies"][0]); tank["wounds_max"]=100000; tank["wounds_current"]=100000; tank["resilience"]=0
    node["enemies"] = [tank]
    run = S._inc_persist(run["id"], node=node)
    run = S._inc_get_run(run["id"])
    target_uid = run["node"]["enemies"][0]["uid"]
    run = S._inc_combat_attack(run, ch, [target_uid], weapon["key"])
dread = next(m for m in run["minions"] if m["name"] == "Dreadnought")
print(f"Dreadnought alive after 6 combat turns without a Rest: {dread['alive']} (expect False - no mid-fight revival for Human)")
assert dread["alive"] is False
print("HUMAN DREADNOUGHT DOES NOT SELF-REVIVE MID-FIGHT - VERIFIED\n")
cleanup(uid, cid)

# --- Tyranid DOES self-revive mid-fight (unchanged behavior) ----------------
uid, cid, ch, run = make_player("Tyranid-Pattern")
run = kill_minion(run, "Apex Tyranid")
run = S._inc_get_run(run["id"])
weapon = S._inc_usable_weapons(ch, run)[0]
for i in range(6):
    node = S._inc_combat_node("easy", 1)
    tank = dict(node["enemies"][0]); tank["wounds_max"]=100000; tank["wounds_current"]=100000; tank["resilience"]=0
    node["enemies"] = [tank]
    run = S._inc_persist(run["id"], node=node)
    run = S._inc_get_run(run["id"])
    target_uid = run["node"]["enemies"][0]["uid"]
    run = S._inc_combat_attack(run, ch, [target_uid], weapon["key"])
apex = next(m for m in run["minions"] if m["name"] == "Apex Tyranid")
print(f"Apex Tyranid alive after 6 combat turns without a Rest: {apex['alive']} (expect True - Tyranid self-repairs)")
assert apex["alive"] is True
print("TYRANID APEX SELF-REVIVES MID-FIGHT - VERIFIED\n")
cleanup(uid, cid)

# --- 3) Rest revives everyone normally (Dreadnought included) --------------
uid, cid, ch, run = make_player("Human")
run = kill_minion(run, "Dreadnought")
run = S._inc_get_run(run["id"])
run = S._inc_persist(run["id"], node={"type": "choice_start"})
run = S._inc_get_run(run["id"])
run = S._inc_choose_start(run, ch, "rest")
dread = next(m for m in run["minions"] if m["name"] == "Dreadnought")
print(f"Dreadnought alive after Rest: {dread['alive']} (expect True)")
assert dread["alive"] is True
print("REST REVIVES THE DREADNOUGHT NORMALLY - VERIFIED\n")
cleanup(uid, cid)

# --- 4) Skipping Rest (picking shop) permanently kills a dead non-Tyranid minion ---
uid, cid, ch, run = make_player("Human")
run = kill_minion(run, "Dreadnought")
run = S._inc_get_run(run["id"])
run = S._inc_persist(run["id"], node={"type": "choice_start"})
run = S._inc_get_run(run["id"])
run = S._inc_choose_start(run, ch, "shop")
names = [m["name"] for m in run["minions"]]
print("minions after choosing shop over rest while Dreadnought was dead:", names)
assert "Dreadnought" not in names
print("SKIPPING REST WHILE DEAD PERMANENTLY REMOVES THE DREADNOUGHT - VERIFIED\n")
cleanup(uid, cid)

# --- 5) Tyranid minions are NEVER permanently lost this way -----------------
uid, cid, ch, run = make_player("Tyranid-Pattern")
run = kill_minion(run, "Apex Tyranid")
run = S._inc_get_run(run["id"])
run = S._inc_persist(run["id"], node={"type": "choice_start"})
run = S._inc_get_run(run["id"])
run = S._inc_choose_start(run, ch, "shop")
names = [m["name"] for m in run["minions"]]
print("minions after choosing shop over rest while Apex was dead:", names)
assert "Apex Tyranid" in names
print("TYRANID MINIONS ARE NEVER PERMANENTLY LOST THIS WAY - VERIFIED\n")
cleanup(uid, cid)

print("ALL CHECKS PASSED")
