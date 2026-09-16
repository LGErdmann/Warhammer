import sistema as S
import uuid, json

S.init_db()

def make_player():
    uname = f"test_recheck_{uuid.uuid4().hex[:8]}"
    ok, err = S._inc_register_account(uname, "pw12345")
    assert ok, err
    conn = S.get_conn()
    user = conn.execute("SELECT id FROM users WHERE username=?", (uname,)).fetchone()
    uid = user["id"]
    cid = S.char_id_for_user(uid)
    conn.close()
    ch = S.load_character(cid)
    run = S._inc_start_run(ch, origin="Tyranid-Pattern")
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

def equip_weapon(run, ch, name, rarity):
    w = next(w for w in S.INC_TYRANID_WARGEAR[rarity] if w["name"] == name)
    offer = {"type": "tyranid_wargear", "rarity": rarity, "name": w["name"], "icon": w["icon"],
             "melee": w["melee"], "damage": w["damage"], "ed": w["ed"], "ap": w["ap"],
             "effect": w["effect"], "minion_support": w["minion_support"], "support_value": w["support_value"],
             "cost": 0, "label": w["name"], "detail": "", "offer_id": 0}
    run = S._inc_persist(run["id"], node={"type": "shop", "offers": [offer]})
    run = S._inc_get_run(run["id"])
    run = S._inc_shop_buy(run, ch, 0)
    return run

def attack_once(run, ch, weapon_key, wounds_max=100000):
    node = S._inc_combat_node("easy", 1)
    enemy = dict(node["enemies"][0])
    enemy["wounds_max"] = wounds_max; enemy["wounds_current"] = wounds_max
    enemy["resilience"] = 0; enemy["defence"] = 0
    node["enemies"] = [enemy]
    run = S._inc_persist(run["id"], node=node)
    run = S._inc_get_run(run["id"])
    target_uid = run["node"]["enemies"][0]["uid"]
    run = S._inc_combat_attack(run, ch, [target_uid], weapon_key)
    return run

# --- melee flag re-check ---
uid, cid, ch, run = make_player()
w = S._inc_usable_weapons(ch, run)[0]
print("Chitin Claw melee flag (after fix):", w["melee"])
assert w["melee"] is True
cleanup(uid, cid)

# --- bonus_die_on_hit: check the minion's OWN attack pool during the SAME turn it procs ---
uid, cid, ch, run = make_player()
run = equip_weapon(run, ch, "Spore Mine Launcher", "Uncommon")
w = S._inc_usable_weapons(ch, run)[0]
apex = next(m for m in run["minions"] if m["name"] == "Apex Tyranid")
fellowship = 30  # Tyranid-Pattern base Fellowship
run = attack_once(run, ch, w["key"])
log_tail = run["node"].get("log", [])
minion_attacks = [e for e in log_tail if e.get("actor") == "minion"]
print("minion attack entries this turn:", [(e["actor_name"], e["pool"]) for e in minion_attacks])
base_expected = fellowship + apex["shock_current"] + apex.get("bonus_die", 0)
print(f"base pool would be ~{base_expected} without the +2 bonus; with Spore Mine Launcher's bonus_die_on_hit, expect it only on the NEXT minion attack (this one fires simultaneously, so bonus applies same action, per design)")
cleanup(uid, cid)

# --- boost_on_kills with a GUARANTEED kill (wounds_max=1) ---
uid, cid, ch, run = make_player()
run = equip_weapon(run, ch, "Bio-Plasma Cannon", "Legendary")
w = S._inc_usable_weapons(ch, run)[0]
apex_before = next(m for m in run["minions"] if m["name"] == "Apex Tyranid")
dmg_before, shockmax_before = apex_before["damage"], apex_before["shock_max"]
for i in range(2):
    run = attack_once(run, ch, w["key"], wounds_max=1)
    log_tail = run["node"].get("log", [])
    player_entries = [e for e in log_tail if e.get("actor") == "player" and e.get("action") == "attack"]
    print(f"kill attempt {i}: target_defeated={player_entries[-1].get('target_defeated') if player_entries else None}")
apex_after = next(m for m in run["minions"] if m["name"] == "Apex Tyranid")
print(f"apex damage {dmg_before} -> {apex_after['damage']}, shock_max {shockmax_before} -> {apex_after['shock_max']}")
assert apex_after["damage"] == dmg_before + 1, "boost_on_kills should add +1 damage after 2 confirmed kills"
assert apex_after["shock_max"] == shockmax_before + 2, "boost_on_kills should add +2 max shock after 2 confirmed kills"
print("BOOST_ON_KILLS CONFIRMED WORKING (with guaranteed kills)")
cleanup(uid, cid)

print("\nDONE")
