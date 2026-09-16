import sistema as S
import uuid, json

S.init_db()

def make_player():
    uname = f"test_diagall_{uuid.uuid4().hex[:8]}"
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

def attack_once(run, ch, weapon_key, tough=True):
    node = S._inc_combat_node("easy", 1)
    enemy = dict(node["enemies"][0])
    if tough:
        enemy["wounds_max"] = 100000; enemy["wounds_current"] = 100000
    enemy["resilience"] = 0; enemy["defence"] = 0
    node["enemies"] = [enemy]
    run = S._inc_persist(run["id"], node=node)
    run = S._inc_get_run(run["id"])
    target_uid = run["node"]["enemies"][0]["uid"]
    run = S._inc_combat_attack(run, ch, [target_uid], weapon_key)
    return run

# --- melee flag check ---
uid, cid, ch, run = make_player()
w = S._inc_usable_weapons(ch, run)[0]
print("Chitin Claw melee flag from _inc_usable_weapons:", w["melee"], "(catalog says melee=True)")
cleanup(uid, cid)

# --- bonus_die_on_hit: Spore Mine Launcher (Uncommon) ---
uid, cid, ch, run = make_player()
run = equip_weapon(run, ch, "Spore Mine Launcher", "Uncommon")
w = S._inc_usable_weapons(ch, run)[0]
apex_before = next(m for m in run["minions"] if m["name"] == "Apex Tyranid")
print("apex next_bonus_die before:", apex_before.get("next_bonus_die", 0))
run = attack_once(run, ch, w["key"])
apex_after = next(m for m in run["minions"] if m["name"] == "Apex Tyranid")
print("apex next_bonus_die after 1 hit:", apex_after.get("next_bonus_die", 0), "(expect +2, minus 1 already consumed by its own attack this turn... check log)")
cleanup(uid, cid)

# --- shock_heal_weakest_on_crit: Rending Talons (Rare) - force a crit by rolling many times ---
uid, cid, ch, run = make_player()
run = equip_weapon(run, ch, "Rending Talons", "Rare")
w = S._inc_usable_weapons(ch, run)[0]
minions = [dict(m) for m in run["minions"]]
for m in minions:
    if m["name"] == "Apex Tyranid":
        m["shock_current"] = 0
run = S._inc_persist(run["id"], minions=minions)
run = S._inc_get_run(run["id"])
crit_healed = False
for i in range(60):
    run = attack_once(run, ch, w["key"])
    log_tail = run["node"].get("log", [])
    crits = [e for e in log_tail if e.get("actor") == "player" and e.get("wrath_crit")]
    apex_now = next(m for m in run["minions"] if m["name"] == "Apex Tyranid")
    if crits:
        print(f"attack {i}: CRIT happened. apex shock_current={apex_now['shock_current']}/{apex_now['shock_max']}")
        if apex_now["shock_current"] == apex_now["shock_max"]:
            crit_healed = True
        break
    minions = [dict(m) for m in run["minions"]]
    for m in minions:
        if m["name"] == "Apex Tyranid": m["shock_current"] = 0
    run = S._inc_persist(run["id"], minions=minions)
    run = S._inc_get_run(run["id"])
print("crit_healed:", crit_healed)
cleanup(uid, cid)

# --- revive_on_attack: The Devourer's Maw (Unique) ---
uid, cid, ch, run = make_player()
run = equip_weapon(run, ch, "The Devourer's Maw", "Unique")
w = S._inc_usable_weapons(ch, run)[0]
minions = [dict(m) for m in run["minions"]]
extra_dead = S._inc_minion_stats("Dead Guy", "", "Tyranid-Pattern", "Common", 1)
extra_dead["alive"] = False; extra_dead["wounds_current"] = 0
run = S._inc_persist(run["id"], minions=minions + [extra_dead])
run = S._inc_get_run(run["id"])
run = attack_once(run, ch, w["key"])
dead_guy = next(m for m in run["minions"] if m["name"] == "Dead Guy")
print("Dead Guy after attack with Devourer's Maw: alive=", dead_guy["alive"], "wounds=", dead_guy["wounds_current"])
cleanup(uid, cid)

# --- boost_on_kills: Bio-Plasma Cannon (Legendary), needs 2 kills ---
uid, cid, ch, run = make_player()
run = equip_weapon(run, ch, "Bio-Plasma Cannon", "Legendary")
w = S._inc_usable_weapons(ch, run)[0]
apex_before = next(m for m in run["minions"] if m["name"] == "Apex Tyranid")
dmg_before, shockmax_before = apex_before["damage"], apex_before["shock_max"]
for i in range(2):
    run = attack_once(run, ch, w["key"], tough=False)  # weak enemy -> kill it
apex_after = next(m for m in run["minions"] if m["name"] == "Apex Tyranid")
print(f"apex damage {dmg_before} -> {apex_after['damage']} , shock_max {shockmax_before} -> {apex_after['shock_max']} (expect +1 dmg, +2 shock_max after 2 kills)")
cleanup(uid, cid)

print("\nDONE")
