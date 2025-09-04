# 100% not chatgpt, 100% not russian
import os
import asyncio
import discord
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")
CATEGORY_ID = int(os.getenv("CATEGORY_ID", "0"))       # категория для личных комнат
LOBBY_CHANNEL_ID = int(os.getenv("LOBBY_CHANNEL_ID", "0"))  # ID голосового "Лобби"

CHANNEL_NAME_PATTERN = "{display_name} — комната"
CLONE_PERMISSIONS_FROM_LOBBY = True
CREATE_COOLDOWN_SEC = 5

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

channel_owner: dict[int, int] = {}   # voice_channel_id -> owner_user_id
owner_channel: dict[int, int] = {}   # owner_user_id -> voice_channel_id
_last_create: dict[int, float] = {}  # антиспам


def in_managed_category(ch):
    return bool(ch and ch.category_id == CATEGORY_ID)


async def create_personal_channel(member: discord.Member, lobby: discord.VoiceChannel):
    now = asyncio.get_event_loop().time()
    if now - _last_create.get(member.id, 0) < CREATE_COOLDOWN_SEC:
        return None
    _last_create[member.id] = now

    # если уже есть канал
    if member.id in owner_channel:
        ch = member.guild.get_channel(owner_channel[member.id])
        if isinstance(ch, discord.VoiceChannel):
            return ch

    channel_name = CHANNEL_NAME_PATTERN.format(display_name=member.display_name)
    overwrites = lobby.overwrites if CLONE_PERMISSIONS_FROM_LOBBY else None
    category = member.guild.get_channel(CATEGORY_ID) or lobby.category

    new_channel = await member.guild.create_voice_channel(
        name=channel_name,
        category=category,
        overwrites=overwrites,
        reason=f"Auto VC for {member}"
    )

    # даём владельцу права управлять каналом
    perms = new_channel.overwrites_for(member)
    perms.manage_channels = True
    perms.move_members = True
    await new_channel.set_permissions(member, overwrite=perms)

    channel_owner[new_channel.id] = member.id
    owner_channel[member.id] = new_channel.id
    return new_channel


async def maybe_delete_empty_channel(channel: discord.VoiceChannel):
    if channel.id not in channel_owner:
        return
    if not channel.members:
        await channel.delete(reason="Empty personal channel")
        owner_id = channel_owner.pop(channel.id, None)
        if owner_id and owner_channel.get(owner_id) == channel.id:
            owner_channel.pop(owner_id, None)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


@bot.event
async def on_voice_state_update(member, before, after):
    # зашёл в лобби
    if after.channel and after.channel.id == LOBBY_CHANNEL_ID:
        new_ch = await create_personal_channel(member, after.channel)
        if new_ch:
            await member.move_to(new_ch)

    # вышел — проверим пустоту
    if before.channel and in_managed_category(before.channel):
        await asyncio.sleep(1)
        ch = member.guild.get_channel(before.channel.id)
        if isinstance(ch, discord.VoiceChannel):
            await maybe_delete_empty_channel(ch)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Нет DISCORD_TOKEN в переменных окружения!")
    bot.run(TOKEN)
