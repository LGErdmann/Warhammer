import sistema as S
import uuid

S.init_db()

def make_player(origin="Tyranid-Pattern"):
    uname = f"test_wire_{uuid.uuid4().hex[:8]}"
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

def equip_weapon(run, ch, name, rarity):
    w = next(w for w in S.INC_TYRANID_WARGEAR[rarity] if w["name"] == name)
    offer = {"type": "tyranid_wargear", "rarity": rarity, "name": w["name"], "icon": w["icon"],
             "melee": w["melee"], "damage": w["damage"], "ed": w["ed"], "ap": w["ap"],
             "effect": w["effect"], "minion_support": w["minion_support"], "support_value": w["support_value"],
             "cost": 0, "label": w["name"], "detail": "", "offer_id": 0}
    run = S._inc_persist(run["id"], node={"type": "shop", "offers": [offer]})
    run = S._inc_get_run(run["id"])
    return S._inc_shop_buy(run, ch, 0)

def attack_once(run, ch, weapon_key, wounds_max=100000):
    node = S._inc_combat_node("easy", 1)
    enemy = dict(node["enemies"][0])
    enemy["wounds_max"] = wounds_max; enemy["wounds_current"] = wounds_max
    enemy["resilience"] = 0; enemy["defence"] = 0
    node["enemies"] = [enemy]
    run = S._inc_persist(run["id"], node=node)
    run = S._inc_get_run(run["id"])
    target_uid = run["node"]["enemies"][0]["uid"]
    return S._inc_combat_attack(run, ch, [target_uid], weapon_key)

# --- THE STALE-RUN BUG: boost_on_kills across 2 separate kills -------------
uid, cid, ch, run = make_player()
run = equip_weapon(run, ch, "Bio-Plasma Cannon", "Legendary")
w = S._inc_usable_weapons(ch, run)[0]
apex_before = next(m for m in run["minions"] if m["name"] == "Apex Tyranid")
dmg_before, shockmax_before = apex_before["damage"], apex_before["shock_max"]
for i in range(2):
    run = attack_once(run, ch, w["key"], wounds_max=1)
apex_after = next(m for m in run["minions"] if m["name"] == "Apex Tyranid")
print(f"[stale-run fix] apex damage {dmg_before} -> {apex_after['damage']}, shock_max {shockmax_before} -> {apex_after['shock_max']}")
assert apex_after["damage"] == dmg_before + 1, "boost_on_kills should survive across kills that each end their own fight"
assert apex_after["shock_max"] == shockmax_before + 2
print("STALE-RUN BUG FIXED - BOOST_ON_KILLS WORKS ACROSS SEPARATE KILLS\n")
cleanup(uid, cid)

# --- talent_minion: Requisitioned Reinforcements / Hive Instinct (+10 wounds, retroactive + on new) ---
uid, cid, ch, run = make_player()
apex_before = next(m for m in run["minions"] if m["name"] == "Apex Tyranid")
wm_before = apex_before["wounds_max"]
talent = next(t for t in S.INC_MINION_TALENTS["Tyranid-Pattern"] if t["name"] == "Hive Instinct")
offer = {"type": "talent_minion", "name": talent["name"], "effect": talent["effect"], "cost": 0, "rarity": talent["rarity"], "offer_id": 0}
run = S._inc_persist(run["id"], node={"type": "shop", "offers": [offer]})
run = S._inc_get_run(run["id"])
run = S._inc_shop_buy(run, ch, 0)
apex_after = next(m for m in run["minions"] if m["name"] == "Apex Tyranid")
print(f"[Hive Instinct retroactive] apex wounds_max {wm_before} -> {apex_after['wounds_max']}")
assert apex_after["wounds_max"] == wm_before + 10
# now buy a NEW minion while owning the talent -> should also get +10 baked in
base_stats_no_bonus = S._inc_minion_stats("Ripper Swarm", "", "Tyranid-Pattern", "Common", 1, 30)
minion_offer = {"type": "minion", "origin": "Tyranid-Pattern", "rarity": "Common", "name": "Ripper Swarm", "icon": "", "bulk": False, "cost": 0, "offer_id": 0}
run = S._inc_persist(run["id"], node={"type": "shop", "offers": [minion_offer]})
run = S._inc_get_run(run["id"])
run = S._inc_shop_buy(run, ch, 0)
new_minion = next(m for m in run["minions"] if m["name"] == "Ripper Swarm")
print(f"[Hive Instinct on new minion] Ripper Swarm wounds_max = {new_minion['wounds_max']} (base {base_stats_no_bonus['wounds_max']} + 10)")
assert new_minion["wounds_max"] == base_stats_no_bonus["wounds_max"] + 10
print("HIVE INSTINCT (WOUNDS BONUS) WORKS RETROACTIVELY AND ON NEW MINIONS\n")
cleanup(uid, cid)

# --- dynamic: Voice of Command/Synaptic Link pool_bonus reflected in minion attack pool ---
uid, cid, ch, run = make_player()
talent = next(t for t in S.INC_MINION_TALENTS["Tyranid-Pattern"] if t["name"] == "Synaptic Link")
offer = {"type": "talent_minion", "name": talent["name"], "effect": talent["effect"], "cost": 0, "rarity": talent["rarity"], "offer_id": 0}
run = S._inc_persist(run["id"], node={"type": "shop", "offers": [offer]})
run = S._inc_get_run(run["id"])
run = S._inc_shop_buy(run, ch, 0)
mods = S._inc_minion_talent_mods(ch, run)
print("[Synaptic Link] pool_bonus =", mods["pool_bonus"])
assert mods["pool_bonus"] == 3
node = {"log": [], "enemies": [{"name": "Dummy", "uid": "d-0", "alive": True, "resilience": 0,
                                  "wounds_current": 100000, "wounds_max": 100000, "shock_current": 0, "defence": 0}]}
merged = {"attributes": {"Fellowship": 30}}
apex = next(dict(m) for m in run["minions"] if m["name"] == "Apex Tyranid")
apex["shock_current"] = 0
log = S._inc_minion_group_attack([apex], node, merged, mods)
print("minion pool with Synaptic Link:", log[0]["pool"], "(expect fellowship 30 + bonus_die 3 + pool_bonus 3 = 36)")
assert log[0]["pool"] == 30 + 3 + 3
print("SYNAPTIC LINK (POOL BONUS) CONFIRMED APPLIED IN REAL ATTACK\n")
cleanup(uid, cid)

# --- dynamic: Shadow in the Warp enemy_pool_penalty ------------------------
uid, cid, ch, run = make_player()
talent = next(t for t in S.INC_MINION_TALENTS["Tyranid-Pattern"] if t["name"] == "Shadow in the Warp")
offer = {"type": "talent_minion", "name": talent["name"], "effect": talent["effect"], "cost": 0, "rarity": talent["rarity"], "offer_id": 0}
run = S._inc_persist(run["id"], node={"type": "shop", "offers": [offer]})
run = S._inc_get_run(run["id"])
run = S._inc_shop_buy(run, ch, 0)
mods = S._inc_minion_talent_mods(ch, run)
assert mods["enemy_pool_penalty"] == 1
enemy = {"alive": True, "name": "Foe", "attack_pool": 5, "weapon_name": "Claw", "weapon_damage": 1, "weapon_ed": 0,
         "attack_skill": "WS", "tier": 1, "wrath_current": 0, "shock_max": 1, "shock_current": 1}
log = S._inc_enemy_turn([dict(enemy)], {"Defence": 99, "Resilience": 0}, 0, [], mods)
print("[Shadow in the Warp] enemy attack pool logged:", log[0]["pool"], "(expect base 5 - 1 = 4)")
assert log[0]["pool"] == 4
print("SHADOW IN THE WARP (ENEMY POOL PENALTY) CONFIRMED\n")
cleanup(uid, cid)

print("ALL CHECKS PASSED")
