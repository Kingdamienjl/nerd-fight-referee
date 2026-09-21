import asyncio
import json
from battlebot.common.db import connect_database

GOKU_CANONICAL_ABILITIES = [
    {"id": "goku-superhuman", "name": "Superhuman Physical Characteristics", "description": "Immense superhuman strength, speed, durability, and agility far beyond mortal limits."},
    {"id": "goku-martial-arts", "name": "Martial Arts Master", "description": "Mastery of Turtle School (Kame-style), King Kai style, and divine martial arts under Whis."},
    {"id": "goku-ki-manipulation", "name": "Ki Manipulation & Energy Projection", "description": "Complete mastery of Ki to unleash devastating energy blasts including Kamehameha, Kiai, and energy barriers."},
    {"id": "goku-flight", "name": "Flight & High-Speed Maneuvering", "description": "Levitation and supersonic to MFTL+ flight via Ki propulsion."},
    {"id": "goku-instant-transmission", "name": "Instant Transmission (Teleportation)", "description": "Spatial and dimensional teleportation via ki sensing, locking onto signatures across planetary and cosmic distances."},
    {"id": "goku-kaioken", "name": "Kaioken (Power Amplification)", "description": "Multiplies speed, power, sensory acuity, and combat potency up to 20 times normal base limits."},
    {"id": "goku-spirit-bomb", "name": "Spirit Bomb (Genki Dama)", "description": "Gathers life energy from across planets and the cosmos into a devastating sphere of pure destructive force."},
    {"id": "goku-ki-sensing", "name": "Enhanced Senses & Ki Sensing", "description": "Can sense life energy, power levels, and hostile intent across solar systems without relying on sight."},
    {"id": "goku-solar-flare", "name": "Solar Flare (Taiyoken)", "description": "Emits a brilliant flash of concentrated light that temporarily blinds and disorients opponents."},
    {"id": "goku-destructo-disc", "name": "Destructo Disc (Kienzan)", "description": "Razor-sharp disc of concentrated ki capable of slicing through targets far above his raw physical strength."},
    {"id": "goku-super-saiyan", "name": "Transformation Mastery (Super Saiyan)", "description": "Unlocks successive ascended forms multiplying power exponentially (SSJ1, SSJ2, SSJ3, SSJ God, SSJ Blue)."},
    {"id": "goku-combat-adaptation", "name": "Combat Adaptation & Mimicry", "description": "Rapidly adapts to opponent timing, rhythm, and esoteric techniques mid-combat."},
]

GOKU_EQUIPMENT = [
    {"id": "goku-power-pole", "name": "Power Pole (Nyoibo)", "description": "Indestructible magical staff that extends to immense lengths on command."},
    {"id": "goku-flying-nimbus", "name": "Flying Nimbus (Kinto'un)", "description": "Magical cloud capable of rapid flight and high-altitude traversal."},
    {"id": "goku-senzu-beans", "name": "Senzu Beans (Consumable)", "description": "Mystical beans that fully restore stamina, physical vitality, and heal fatal wounds instantaneously."},
]

KEN_CANONICAL_ABILITIES = [
    {"id": "ken-superhuman", "name": "Superhuman Physical Characteristics", "description": "Peak superhuman strength, hypersonic combat speed, and durability."},
    {"id": "ken-martial-arts", "name": "Martial Arts (Ansatsuken & Shotokan Karate)", "description": "Master practitioner of Ansatsuken-rooted karate emphasizing dynamic, flame-infused offensive strikes."},
    {"id": "ken-pyrokinesis", "name": "Chi Manipulation & Pyrokinesis", "description": "Channels spiritual chi into intense combustion, igniting limbs and energy projections."},
    {"id": "ken-shoryuken", "name": "Shoryuken (Dragon Punch)", "description": "Signature rising uppercut wreathed in flames, breaking through aerial and ground defenses."},
    {"id": "ken-hadouken", "name": "Hadouken (Surge Fist)", "description": "Concentrated chi projectile launched from the palms for spacing and offensive zoning."},
    {"id": "ken-tatsumaki", "name": "Tatsumaki Senpukyaku (Hurricane Kick)", "description": "Rapid spinning airborne kick that carries kinetic momentum through defensive guards."},
    {"id": "ken-acrobatics", "name": "Acrobatics & Kinetic Agility", "description": "High-mobility footwork, target spacing, and aerial dive kicks (Inazuma Kick)."},
    {"id": "ken-focus-attack", "name": "Focus Attack & Counter-Stun", "description": "Absorbs incoming physical impacts with armored frames to deliver a crumpling counter-strike."},
    {"id": "ken-guren-enjinkyaku", "name": "Guren Enjinkyaku", "description": "Multi-strike flame-kick sequence culminating in a fiery vertical finishing blast."},
    {"id": "ken-senses", "name": "Enhanced Senses & Chi Awareness", "description": "Perceives chi flows, kinetic intent, and environmental threats in close combat."},
]

async def update_character(conn, char_id, abilities, equipment=None):
    row = await conn.fetchrow("SELECT profile_id, profile_json FROM character_profiles WHERE character_id = $1", char_id)
    if not row:
        print(f"Profile not found for {char_id}")
        return
    profile_id = row["profile_id"]
    pjson = json.loads(row["profile_json"]) if isinstance(row["profile_json"], str) else (row["profile_json"] or {})
    
    # Update abilities in pjson
    pjson["abilities"] = abilities
    pjson["key_tools"] = [a["name"] for a in abilities[:6]]
    if equipment is not None:
        pjson["equipment"] = equipment
    
    await conn.execute("UPDATE character_profiles SET profile_json = $1, updated_at = now() WHERE profile_id = $2", json.dumps(pjson), profile_id)
    
    # Update profile_abilities table
    await conn.execute("DELETE FROM profile_abilities WHERE profile_id = $1", profile_id)
    for a in abilities:
        await conn.execute("""
            INSERT INTO profile_abilities (
                ability_id, profile_id, name, description, source_ids, tags, targets,
                activation_requirements, counters, resource_dependencies, scope_limitations,
                enrichment, confidence
            ) VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb, $8::jsonb, $9::jsonb, $10::jsonb, $11::jsonb, $12::jsonb, $13)
        """, a["id"], profile_id, a["name"], a["description"], json.dumps([]), json.dumps([]), json.dumps([]), json.dumps([]), json.dumps([]), json.dumps([]), json.dumps([]), json.dumps({"method": "curated_canonical"}), 0.95)
    
    # Update profile_equipment table if provided
    if equipment is not None:
        await conn.execute("DELETE FROM profile_equipment WHERE profile_id = $1", profile_id)
        for eq in equipment:
            await conn.execute("""
                INSERT INTO profile_equipment (
                    equipment_id, profile_id, name, description, source_ids, tags, targets,
                    activation_requirements, counters, resource_dependencies, scope_limitations,
                    enrichment, confidence
                ) VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb, $8::jsonb, $9::jsonb, $10::jsonb, $11::jsonb, $12::jsonb, $13)
            """, eq["id"], profile_id, eq["name"], eq["description"], json.dumps([]), json.dumps([]), json.dumps([]), json.dumps([]), json.dumps([]), json.dumps([]), json.dumps([]), json.dumps({"method": "curated_canonical"}), 0.95)

    print(f"Successfully updated {char_id} (profile_id: {profile_id}) with {len(abilities)} abilities.")

async def main():
    async with connect_database() as conn:
        for cid in ['mixed-crossover-icons-goku', 'anime-dragon-ball-son-goku', 'anime-dragon-ball-son-goku-anime', 'anime-dragon-ball-son-goku-dragon-ball']:
            await update_character(conn, cid, GOKU_CANONICAL_ABILITIES, GOKU_EQUIPMENT)
        await update_character(conn, 'game-street-fighter-ken-masters', KEN_CANONICAL_ABILITIES)

if __name__ == "__main__":
    asyncio.run(main())
