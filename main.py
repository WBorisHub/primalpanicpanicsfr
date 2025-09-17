import os
import json
import requests
import random
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask, request, jsonify
from datetime import datetime
import threading

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
DB_FILE = "link_codes.json"
LOG_WEBHOOK_URL = os.environ.get("LOG_WEBHOOK_URL")

if not DISCORD_TOKEN or not LOG_WEBHOOK_URL:
    raise ValueError("DISCORD_TOKEN and LOG_WEBHOOK_URL must be set!")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

app = Flask(__name__)

if os.path.exists(DB_FILE):
    with open(DB_FILE, "r") as f:
        link_requests = json.load(f)
else:
    link_requests = {}

def save_db():
    with open(DB_FILE, "w") as f:
        json.dump(link_requests, f, indent=4)

def log_all_linkcodes():
    if not link_requests:
        return

    embed = {
        "title": "📄 All Registered Link Codes",
        "color": 0x00ff00,
        "timestamp": datetime.utcnow().isoformat(),
        "fields": []
    }

    for code, data in link_requests.items():
        embed["fields"].append({
            "name": f"Code: {code}",
            "value": (
                f"PlayFab ID: {data.get('playfab_id','N/A')}\n"
                f"HWID: {data.get('hwid','N/A')}\n"
                f"IP: {data.get('ip','N/A')}\n"
                f"Discord Linked: {data.get('discordLinked', False)}"
            ),
            "inline": False
        })

    try:
        requests.post(LOG_WEBHOOK_URL, json={"embeds": [embed]}, timeout=5)
    except Exception as e:
        print("Failed to send webhook:", e)

@app.route("/")
def home():
    return "Bot server is running!"

@app.route("/register_linkcode", methods=["POST"])
def register_linkcode():
    data = request.get_json()
    if not data or "playfab_id" not in data or "hwid" not in data or "ip" not in data:
        return jsonify({"success": False, "error": "Missing fields"}), 400

    code = str(random.randint(100000, 999999))
    link_requests[code] = {
        "playfab_id": data["playfab_id"],
        "hwid": data["hwid"],
        "ip": data["ip"],
        "discord_id": None,
        "discordLinked": False
    }
    save_db()

    # Log all current codes to webhook
    log_all_linkcodes()

    return jsonify({"success": True, "code": code})

@app.route("/check_linkcode/<code>", methods=["GET"])
def check_linkcode(code):
    data = link_requests.get(code)
    if not data:
        return jsonify({"success": False, "error": "Code not found"}), 404
    return jsonify(data)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot online as {bot.user}")

@bot.tree.command(name="linkcode", description="Link your Discord account using Unity code")
@app_commands.describe(code="6-digit code from Unity")
async def linkcode(interaction: discord.Interaction, code: str):
    data = link_requests.get(code)
    if not data:
        await interaction.response.send_message("❌ Invalid or expired code.", ephemeral=True)
        return

    data["discord_id"] = str(interaction.user.id)
    data["linked_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    data["discordLinked"] = True
    save_db()

    embed = discord.Embed(
        title="✅ Player Linked!",
        color=discord.Color.green(),
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="Master PlayFab ID", value=data.get("playfab_id","N/A"), inline=False)
    embed.add_field(name="HWID", value=data.get("hwid","N/A"), inline=False)
    embed.add_field(name="IP", value=data.get("ip","N/A"), inline=False)
    embed.add_field(name="Link Code", value=code, inline=False)
    embed.add_field(name="Discord ID", value=interaction.user.id, inline=False)
    embed.add_field(name="Status", value="🔗 Linked", inline=False)

    try:
        requests.post(LOG_WEBHOOK_URL, json={"embeds": [embed.to_dict()]}, timeout=5)
    except:
        pass

    del link_requests[code]
    save_db()
    await interaction.response.send_message(embed=embed, ephemeral=True)

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask).start()
bot.run(DISCORD_TOKEN)
