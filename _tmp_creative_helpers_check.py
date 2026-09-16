import sistema as S
import uuid

S.init_db()

def make_player(origin):
    uname = f"test_ch_{uuid.uuid4().hex[:8]}"
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

# --- 1) Helper minion has real flavor ability + growth_profile at start ----
uid, cid, ch, run = make_player("Aeldari-Pattern")
helper = run["minions"][0]
print("helper:", helper["name"], "| ability:", helper.get("ability"), "| growth_profile:", helper.get("growth_profile"))
assert helper.get("ability"), "helper minion should have real flavor ability text, not empty"
assert helper.get("growth_profile") == "bulwark"
cleanup(uid, cid)

# --- 2) Different profiles actually scale differently ----------------------
def force_loop_end(run, ch):
    run = S._inc_persist(run["id"], stage="boss")
    run = S._inc_get_run(run["id"])
    return S._inc_advance(run, ch)

results = {}
for origin, expect_profile in [("Aeldari-Pattern", "bulwark"), ("Tau-Pattern", "berserker"),
                                 ("Necron-Pattern", "swarm"), ("Sororitas-Pattern", "psyker"),
                                 ("Ork-Pattern", "kill_fed")]:
    uid, cid, ch, run = make_player(origin)
    assert run["minions"][0].get("growth_profile") == expect_profile, f"{origin} expected {expect_profile}, got {run['minions'][0].get('growth_profile')}"
    before = dict(run["minions"][0])
    run2 = force_loop_end(run, ch)
    run2 = S._inc_get_run(run2["id"])
    after = run2["minions"][0]
    dmg_pct = (after["damage"] - before["damage"]) / max(1, before["damage"])
    wounds_pct = (after["wounds_max"] - before["wounds_max"]) / max(1, before["wounds_max"])
    res_pct = (after["resilience"] - before["resilience"]) / max(1, before["resilience"])
    results[origin] = (dmg_pct, wounds_pct, res_pct)
    print(f"{origin:25s} ({expect_profile:10s}) dmg%={dmg_pct:.3f} wounds%={wounds_pct:.3f} res%={res_pct:.3f}")
    cleanup(uid, cid)

# berserker should have the highest damage growth of the bunch
assert results["Tau-Pattern"][0] > results["Aeldari-Pattern"][0]
assert results["Tau-Pattern"][0] > results["Necron-Pattern"][0]
# bulwark should have the highest wounds/resilience growth
assert results["Aeldari-Pattern"][1] > results["Tau-Pattern"][1]
assert results["Aeldari-Pattern"][2] > results["Tau-Pattern"][2]
print("DIFFERENT GROWTH PROFILES PRODUCE VISIBLY DIFFERENT SCALING - VERIFIED\n")

# --- 3) psyker scales with owner's OWN current shock ------------------------
uid, cid, ch, run = make_player("Sororitas-Pattern")
run = S._inc_persist(run["id"], shock_current=run["shock_max"])  # max out player shock
run = S._inc_get_run(run["id"])
before = dict(run["minions"][0])
run2 = force_loop_end(run, ch)
run2 = S._inc_get_run(run2["id"])
after = run2["minions"][0]
expected_gain = round(run["shock_current"] * 0.05)
print(f"psyker shock_max {before['shock_max']} -> {after['shock_max']} (expect +{expected_gain} from owner's shock)")
assert after["shock_max"] == before["shock_max"] + expected_gain
print("PSYKER PROFILE SCALES WITH OWNER'S CURRENT SHOCK - VERIFIED\n")
cleanup(uid, cid)

# --- 4) kill_fed scales with bosses_cleared ---------------------------------
uid, cid, ch, run = make_player("Ork-Pattern")
run = S._inc_persist(run["id"], bosses_cleared=4, stage="boss")
run = S._inc_get_run(run["id"])
before = dict(run["minions"][0])
run2 = S._inc_advance(run, ch)
run2 = S._inc_get_run(run2["id"])
after = run2["minions"][0]
print(f"kill_fed damage {before['damage']} -> {after['damage']} (expect +4 from bosses_cleared)")
assert after["damage"] == before["damage"] + 4
print("KILL_FED PROFILE SCALES WITH BOSSES_CLEARED - VERIFIED\n")
cleanup(uid, cid)

# --- 5) Human boss reward always includes a free Dreadnought module -------
uid, cid, ch, run = make_player("Human")
for _ in range(8):
    node = {"difficulty": "boss", "enemies": [{}]}
    offers = S._inc_generate_post_combat_offers(ch, run, node)
    types = [o["type"] for o in offers]
    assert "minion_module" in types, f"expected a guaranteed minion_module offer, got {types}"
    module_offer = next(o for o in offers if o["type"] == "minion_module")
    assert module_offer["cost"] == 0
print("HUMAN BOSS REWARD ALWAYS INCLUDES A FREE DREADNOUGHT MODULE - VERIFIED\n")
cleanup(uid, cid)

# --- 6) Non-Human, non-Tyranid boss reward is unaffected (still 3 talents) --
uid, cid, ch, run = make_player("Aeldari-Pattern")
node = {"difficulty": "boss", "enemies": [{}]}
offers = S._inc_generate_post_combat_offers(ch, run, node)
print("Aeldari boss reward types:", [o["type"] for o in offers])
assert all(o["type"] == "talent" for o in offers)
assert len(offers) == 3
print("OTHER ORIGINS' BOSS REWARD UNCHANGED - VERIFIED\n")
cleanup(uid, cid)

print("ALL CHECKS PASSED")
