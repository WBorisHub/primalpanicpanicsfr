import os
import json
import requests
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask, request, jsonify
import threading
import sys
import asyncio
from datetime import datetime
import random

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
DB_FILE = "link_codes.json"
LOG_WEBHOOK_URL = os.environ.get("LOG_WEBHOOK_URL")

if not DISCORD_TOKEN or not LOG_WEBHOOK_URL:
    raise ValueError("DISCORD_TOKEN and LOG_WEBHOOK_URL must be set!")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

if os.path.exists(DB_FILE):
    with open(DB_FILE, "r") as f:
        link_requests = json.load(f)
else:
    link_requests = {}

def save_db():
    with open(DB_FILE, "w") as f:
        json.dump(link_requests, f, indent=4)

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

    message = f"✅ Player Linked!\nTime: {data['linked_at']}\nMaster PlayFab ID: {data.get('playfab_id','N/A')}\nHWID: {data.get('hwid','N/A')}\nIP: {data.get('ip','N/A')}\nLink Code: {code}\nDiscord ID: {interaction.user.id}"
    try:
        requests.post(LOG_WEBHOOK_URL, json={"content": message}, timeout=5)
    except:
        pass

    del link_requests[code]
    save_db()
    await interaction.response.send_message("✅ Successfully linked.", ephemeral=True)

@bot.tree.command(name="unlink", description="Unlink your Discord account")
async def unlink(interaction: discord.Interaction):
    await interaction.response.send_message("⚠️ Unlinking is manual in this setup.", ephemeral=True)

@bot.tree.command(name="addlinkcode", description="Manually add a link code")
@app_commands.describe(playfab_id="PlayFab ID", code="6-digit code", hwid="HWID", ip="IP")
async def addlinkcode(interaction: discord.Interaction, playfab_id: str, code: str, hwid: str, ip: str):
    link_requests[code] = {"playfab_id": playfab_id, "hwid": hwid, "ip": ip, "discord_id": None, "discordLinked": False}
    save_db()
    await interaction.response.send_message(f"✅ Code {code} registered.", ephemeral=True)

@bot.tree.command(name="restart", description="Restart the bot")
async def restart(interaction: discord.Interaction):
    await interaction.response.send_message("♻️ Restarting bot...", ephemeral=True)
    await asyncio.sleep(1)
    os.execv(sys.executable, [sys.executable] + sys.argv)

# ------------------ Flask API ------------------
app = Flask(__name__)

@app.route("/register_linkcode", methods=["POST"])
def register_linkcode():
    data = request.get_json()
    playfab_id = data.get("playfab_id")
    hwid = data.get("hwid", "Unknown")
    ip = data.get("ip", "Unknown")

    for code, entry in link_requests.items():
        if entry["playfab_id"] == playfab_id and not entry.get("discordLinked", False):
            entry["hwid"] = hwid
            entry["ip"] = ip
            save_db()
            return jsonify({"success": True, "code": code})

    new_code = str(random.randint(100000, 999999))
    link_requests[new_code] = {
        "playfab_id": playfab_id,
        "hwid": hwid,
        "ip": ip,
        "discord_id": None,
        "discordLinked": False,
        "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    }
    save_db()
    return jsonify({"success": True, "code": new_code})

@app.route("/check_linkcode/<code>", methods=["GET"])
def check_linkcode(code):
    data = link_requests.get(code)
    if not data:
        return jsonify({"valid": False})
    return jsonify({"valid": True, **data})

def run_flask():
    app.run(host="0.0.0.0", port=5000)

threading.Thread(target=run_flask, daemon=True).start()
bot.run(DISCORD_TOKEN)
