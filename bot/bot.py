import logging
import os
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from game import Battle, CATALOG, GameError, Store

store = Store(os.getenv('GACHA_DB', str(Path(__file__).with_name('gacha.sqlite3'))))
busy = set()

def unit_label(unit):
    name,rarity,_,_ = CATALOG[unit]
    return f'{name} [{rarity}★]'

class Client(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=discord.Intents.default())

    async def setup_hook(self):
        guild = os.getenv('DISCORD_GUILD_ID')
        if guild:
            target = discord.Object(id=int(guild))
            self.tree.copy_global_to(guild=target)
            try:
                await self.tree.sync(guild=target)
            except discord.Forbidden as error:
                if error.code != 50001:
                    raise
                self.tree.clear_commands(guild=target)
                logging.warning(
                    'Cannot access server %s (Discord 50001). Check the Server ID and '
                    'invite this bot to that server with bot + applications.commands scopes. '
                    'Registering global commands instead; they may take time to appear.', guild)
                await self.tree.sync()
            else:
                logging.info('Registered commands for server %s', guild)
        else:
            await self.tree.sync()

    async def on_ready(self):
        logging.info('Bot connected as %s (ID %s)', self.user, self.user.id)
        invite = discord.utils.oauth_url(
            self.application_id, permissions=discord.Permissions(view_channel=True, send_messages=True),
            scopes=('bot', 'applications.commands'))
        print('Bot online. Invite this bot to your server:', invite, flush=True)

bot = Client()

class Duel(discord.ui.View):
    def __init__(self, challenger, opponent):
        super().__init__(timeout=120)
        self.ids = (challenger,opponent)
        self.battle = None
        self.message = None
        self.closed = False

    def close(self):
        self.closed = True
        busy.difference_update(self.ids)
        for child in self.children:
            child.disabled = True
        self.stop()

    def render(self, text=''):
        if not self.battle:
            return f'<@{self.ids[0]}> ท้า <@{self.ids[1]}> ต่อสู้! ฝ่ายถูกท้ากดรับคำท้าภายใน 120 วินาที'
        lines = [f'<@{f.uid}> • {unit_label(f.unit)} • HP {f.hp} • สกิลรอ {f.cooldown}' for f in self.battle.fighters]
        if self.battle.finished:
            lines.append(f'ผู้ชนะ: <@{self.battle.winner}>' if self.battle.winner else 'เสมอ')
        else:
            lines.append(f'ตาของ <@{self.battle.fighters[self.battle.turn].uid}>')
        return '\n'.join(lines+[text])

    async def on_timeout(self):
        self.close()
        if self.message:
            try:
                await self.message.edit(content='หมดเวลาการต่อสู้ ยกเลิกแมตช์แล้ว', view=self)
            except discord.HTTPException:
                logging.exception('Could not update expired duel')

    async def interaction_check(self, interaction):
        if self.closed or interaction.user.id not in self.ids:
            await interaction.response.send_message('คุณไม่ได้อยู่ในแมตช์นี้ หรือแมตช์จบแล้ว', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='รับคำท้า', style=discord.ButtonStyle.success)
    async def accept(self, interaction, button):
        if self.battle or interaction.user.id != self.ids[1]:
            await interaction.response.send_message('เฉพาะผู้ถูกท้าเท่านั้นที่รับคำท้าได้', ephemeral=True)
            return
        self.battle = Battle(*self.ids,store)
        button.disabled = True
        await interaction.response.edit_message(content=self.render(),view=self)

    @discord.ui.button(label='ปฏิเสธ / ยกเลิก', style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        if self.battle:
            await interaction.response.send_message('ใช้ปุ่มยอมแพ้เพื่อออกจากการต่อสู้',ephemeral=True)
            return
        self.close()
        await interaction.response.edit_message(content='ยกเลิกคำท้าแล้ว',view=self)

    async def move(self, interaction, action):
        if not self.battle:
            await interaction.response.send_message('รอรับคำท้าก่อน',ephemeral=True)
            return
        try:
            text = self.battle.act(interaction.user.id,action)
        except GameError as error:
            await interaction.response.send_message(str(error),ephemeral=True)
            return
        if self.battle.finished:
            self.close()
        await interaction.response.edit_message(content=self.render(text),view=self)

    @discord.ui.button(label='โจมตี', style=discord.ButtonStyle.primary)
    async def attack(self, interaction, button):
        await self.move(interaction,'attack')

    @discord.ui.button(label='สกิล', style=discord.ButtonStyle.danger)
    async def skill(self, interaction, button):
        await self.move(interaction,'skill')

    @discord.ui.button(label='ป้องกัน', row=1)
    async def guard(self, interaction, button):
        await self.move(interaction,'guard')

    @discord.ui.button(label='ยอมแพ้', row=1)
    async def surrender(self, interaction, button):
        await self.move(interaction,'surrender')

@bot.tree.command(name='daily',description='รับ 300 เพชรรายวัน')
async def daily(interaction: discord.Interaction):
    store.daily(interaction.user.id)
    await interaction.response.send_message('รับ 300 เพชรแล้ว!',ephemeral=True)

@bot.tree.command(name='gacha',description='สุ่มตัวละคร 100 เพชร การันตี 5★ ภายใน 50 ครั้ง')
async def gacha(interaction: discord.Interaction):
    unit = store.pull(interaction.user.id)
    gems,pity,_ = store.profile(interaction.user.id)
    await interaction.response.send_message(f'ได้ {unit_label(unit)}!\nเพชร {gems} • การันตี 5★ {pity}/50\nตัวซ้ำเก็บเป็นจำนวนสะสม',ephemeral=True)

@bot.tree.command(name='collection',description='ดูตัวละครและเพชรของคุณ')
async def collection(interaction: discord.Interaction):
    gems,pity,active = store.profile(interaction.user.id)
    rows = [f'{unit_label(u)} ×{n} (`{u}`)' for u,n in store.collection(interaction.user.id)]
    await interaction.response.send_message(f'เพชร {gems} • การันตี 5★ {pity}/50\nตัวที่ใช้: {unit_label(active)}\n'+'\n'.join(rows),ephemeral=True)

@bot.tree.command(name='team',description='เลือกตัวละครลงสนาม PvP แบบ 1 ต่อ 1')
@app_commands.choices(character=[app_commands.Choice(name=unit_label(k),value=k) for k in CATALOG])
async def team(interaction: discord.Interaction, character: app_commands.Choice[str]):
    if interaction.user.id in busy:
        raise GameError('เปลี่ยนตัวละครไม่ได้ระหว่างมีคำท้าหรือกำลังต่อสู้')
    store.equip(interaction.user.id,character.value)
    await interaction.response.send_message(f'เลือก {unit_label(character.value)} แล้ว',ephemeral=True)

@bot.tree.command(name='battle',description='ท้าเพื่อนต่อสู้ PvP แบบเทิร์นเบส')
@app_commands.guild_only()
async def battle(interaction: discord.Interaction, opponent: discord.Member):
    uid = interaction.user.id
    if opponent.bot or opponent.id == uid:
        raise GameError('ต้องท้าผู้เล่นคนอื่นที่ไม่ใช่บอท')
    if uid in busy or opponent.id in busy:
        raise GameError('ผู้เล่นคนใดคนหนึ่งมีคำท้าหรือกำลังต่อสู้อยู่')
    view = Duel(uid,opponent.id)
    busy.update(view.ids)
    try:
        await interaction.response.send_message(view.render(), view=view, allowed_mentions=discord.AllowedMentions(users=True))
        view.message = await interaction.original_response()
    except Exception:
        view.close()
        raise

@bot.tree.error
async def command_error(interaction, error):
    cause = getattr(error,'original',error)
    message = str(cause) if isinstance(cause,GameError) else 'เกิดข้อผิดพลาด ลองใหม่อีกครั้ง'
    if not isinstance(cause,GameError):
        logging.error('Command failed',exc_info=(type(cause),cause,cause.__traceback__))
    if interaction.response.is_done():
        await interaction.followup.send(message,ephemeral=True)
    else:
        await interaction.response.send_message(message,ephemeral=True)

if __name__ == '__main__':
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        raise SystemExit('Set DISCORD_BOT_TOKEN securely in the process environment before starting.')
    bot.run(token)
