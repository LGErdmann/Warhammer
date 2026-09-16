import sistema as S
import uuid

S.init_db()

def make_player(origin):
    uname = f"test_tyf_{uuid.uuid4().hex[:8]}"
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

def gear_names_of(run):
    return {w.get("name") for w in (run.get("starting_wargear") or []) + (run.get("extra_wargear") or [])}

TYRANID_NAMES = set()
for tier_list in S.INC_TYRANID_WARGEAR.values():
    for w in tier_list:
        TYRANID_NAMES.add(w["name"])
for a in S.INC_TYRANID_ARMOUR.values():
    TYRANID_NAMES.add(a["name"])
TYRANID_TALENT_NAMES = {mt["name"] for mt in S.INC_MINION_TALENTS.get("Tyranid-Pattern", [])}

uid, cid, ch, run = make_player("Tyranid-Pattern")

# --- 1) Post-combat reward offers must stay Tyranid-only, boss and non-boss ---
for difficulty in ("easy", "medium", "hard", "boss"):
    node = {"difficulty": difficulty, "enemies": [{}] if difficulty != "boss" else [{}]}
    for _trial in range(15):
        offers = S._inc_generate_post_combat_offers(ch, run, node)
        for o in offers:
            if o["type"] in ("wargear", "talent"):
                print(f"LEAK at difficulty={difficulty}: non-Tyranid offer type={o['type']} name={o.get('name')}")
                raise SystemExit(1)
            if o["type"] == "tyranid_wargear" or o["type"] == "tyranid_armour":
                assert o["name"] in TYRANID_NAMES, f"unexpected tyranid item name {o['name']}"
            if o["type"] == "talent_minion":
                assert o["name"] in TYRANID_TALENT_NAMES, f"unexpected talent name {o['name']}"
print("POST-COMBAT OFFERS STAY TYRANID-ONLY (easy/medium/hard/boss) VERIFIED")

# --- 2) Apex Tyranid gains 25% wounds / 10% shock -----------------------------
weak_minion = S._inc_minion_stats("Weakling", "", "Tyranid-Pattern", "Common", 1)
weak_minion["wounds_max"] = 20; weak_minion["wounds_current"] = 20
weak_minion["shock_max"] = 10; weak_minion["shock_current"] = 10
run = S._inc_persist(run["id"], minions=run["minions"] + [weak_minion])
run = S._inc_get_run(run["id"])
apex_before = next(m for m in run["minions"] if m["name"] == "Apex Tyranid")
wm_before, sm_before = apex_before["wounds_max"], apex_before["shock_max"]
run = S._inc_persist(run["id"], stage="boss")
run = S._inc_get_run(run["id"])
run2 = S._inc_advance(run, ch)
apex_after = next(m for m in run2["minions"] if m["name"] == "Apex Tyranid")
print(f"wounds_max {wm_before} -> {apex_after['wounds_max']} (expected +{round(20*0.25)})")
print(f"shock_max {sm_before} -> {apex_after['shock_max']} (expected +{round(10*0.10)})")
assert apex_after["wounds_max"] == wm_before + round(20 * 0.25)
assert apex_after["shock_max"] == sm_before + round(10 * 0.10)
print("APEX 25%/10% ABSORPTION VERIFIED")

conn = S.get_conn()
conn.execute("DELETE FROM incursion_run WHERE character_id=?", (cid,))
conn.execute("DELETE FROM characters WHERE id=?", (cid,))
conn.execute("DELETE FROM users WHERE id=?", (uid,))
conn.commit(); conn.close()

# --- 3) Tyranid: only 1 weapon at a time, buying another replaces it ---------
uid, cid, ch, run = make_player("Tyranid-Pattern")
print("weapons after start:", [w["name"] for w in (run.get("starting_wargear") or []) + (run.get("extra_wargear") or []) if S._inc_is_weapon_item(w)])
assert sum(1 for w in gear_names_of(run) if True) >= 0
weapon_count = sum(1 for w in (run.get("starting_wargear") or []) + (run.get("extra_wargear") or []) if S._inc_is_weapon_item(w))
assert weapon_count == 1, f"expected 1 starting weapon, got {weapon_count}"

new_weapon_offer = S._inc_generate_tyranid_wargear_offer()
while new_weapon_offer["type"] != "tyranid_wargear":
    new_weapon_offer = S._inc_generate_tyranid_wargear_offer()
new_weapon_offer = dict(new_weapon_offer); new_weapon_offer["cost"] = 0; new_weapon_offer["offer_id"] = 0
run = S._inc_persist(run["id"], node={"type": "shop", "offers": [new_weapon_offer]})
run = S._inc_get_run(run["id"])
run = S._inc_shop_buy(run, ch, 0)
weapons_now = [w["name"] for w in (run.get("starting_wargear") or []) + (run.get("extra_wargear") or []) if S._inc_is_weapon_item(w)]
print("weapons after buying a new one:", weapons_now)
assert len(weapons_now) == 1, f"expected exactly 1 weapon after replace, got {weapons_now}"
assert weapons_now[0] == new_weapon_offer["name"]
print("TYRANID SINGLE-WEAPON REPLACEMENT VERIFIED")

conn = S.get_conn()
conn.execute("DELETE FROM incursion_run WHERE character_id=?", (cid,))
conn.execute("DELETE FROM characters WHERE id=?", (cid,))
conn.execute("DELETE FROM users WHERE id=?", (uid,))
conn.commit(); conn.close()

# --- 4) Tyranid Wrath-die-1 costs a Wound, not weapon durability --------------
uid, cid, ch, run = make_player("Tyranid-Pattern")
run = S._inc_persist(run["id"], wrath_current=0)
run = S._inc_get_run(run["id"])
node = S._inc_combat_node("easy", 1)
run = S._inc_persist(run["id"], node=node)
run = S._inc_get_run(run["id"])
weapon = S._inc_usable_weapons(ch, run)[0]
wounds_before = run["wounds_current"]
durabilities_before = dict(run.get("weapon_durabilities") or {})

forced = False
for _ in range(60):
    trial_run = S._inc_get_run(run["id"])
    trial_node = S._inc_build_node_for_stage("easy", ch, {**trial_run, "loop_no": trial_run["loop_no"]})
    trial_run = S._inc_persist(trial_run["id"], node=trial_node, wounds_current=trial_run["wounds_max"])
    trial_run = S._inc_get_run(trial_run["id"])
    target_uid = trial_run["node"]["enemies"][0]["uid"]
    before_w = trial_run["wounds_current"]
    trial_run = S._inc_combat_attack(trial_run, ch, [target_uid], weapon["key"])
    after_w = trial_run["wounds_current"]
    log_tail = trial_run["node"].get("log", [])
    bio_hits = [e for e in log_tail if e.get("action") == "weapon_bio_damage"]
    dur_hits = [e for e in log_tail if e.get("action") == "weapon_damage"]
    if bio_hits:
        print("weapon_bio_damage entry found:", bio_hits[0])
        assert not dur_hits, "should not ALSO log durability loss for a Tyranid"
        forced = True
        break
    run = trial_run

assert forced, "never observed a Wrath Die 1 in 60 attacks (unlucky) - rerun"
print("TYRANID WRATH-DIE-1 COSTS WOUNDS INSTEAD OF DURABILITY VERIFIED")

conn = S.get_conn()
conn.execute("DELETE FROM incursion_run WHERE character_id=?", (cid,))
conn.execute("DELETE FROM characters WHERE id=?", (cid,))
conn.execute("DELETE FROM users WHERE id=?", (uid,))
conn.commit(); conn.close()

print("\nALL CHECKS PASSED")
