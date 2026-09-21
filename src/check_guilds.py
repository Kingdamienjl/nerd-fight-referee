import asyncio, os, discord

intents = discord.Intents.default()
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"Logged in as: {client.user} (ID: {client.user.id})")
    print(f"Total Guilds: {len(client.guilds)}")
    for g in client.guilds:
        print(f" - {g.name} (ID: {g.id}) | Members: {g.member_count}")
    await client.close()

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    client.run(token)
