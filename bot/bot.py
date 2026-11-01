import logging
import os
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from game import Battle, CATALOG, GameError, Store, skill_cost, banner_is_open
from presentation import unit_label, card, banner_embed, pity_embed, result_embed, battle_embed, STYLE, character_embed

store = Store(os.getenv('GACHA_DB', str(Path(__file__).with_name('gacha.sqlite3'))))
busy = set()

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
            self.application_id, permissions=discord.Permissions(view_channel=True, send_messages=True, embed_links=True, attach_files=True),
            scopes=('bot', 'applications.commands'))
        print('Bot online. Invite this bot to your server:', invite, flush=True)

bot = Client()

class GameView(discord.ui.View):
    async def on_error(self, interaction, error, item):
        message=str(error) if isinstance(error,GameError) else 'เกิดข้อผิดพลาด ลองใหม่อีกครั้ง'
        if not isinstance(error,GameError):
            logging.error('Button failed',exc_info=(type(error),error,error.__traceback__))
        if interaction.response.is_done():
            await interaction.followup.send(message,ephemeral=True)
        else:
            await interaction.response.send_message(message,ephemeral=True)

class SummonView(GameView):
    def __init__(self,banner='standard'):
        super().__init__(timeout=600)
        self.banner=banner
        self.message=None

    async def summon(self,interaction,count):
        try:
            units=store.pull_many(interaction.user.id,count,banner=self.banner)
        except GameError as error:
            await interaction.response.send_message(str(error),ephemeral=True)
            return
        await interaction.response.send_message(embed=result_embed(store,interaction.user.id,units,self.banner),ephemeral=True)

    @discord.ui.button(label='สุ่ม 1 ครั้ง · 100',emoji='💎',style=discord.ButtonStyle.success)
    async def single(self,interaction,button):
        await self.summon(interaction,1)

    @discord.ui.button(label='สุ่ม 10 ครั้ง · 1,000',emoji='🌌',style=discord.ButtonStyle.primary)
    async def ten(self,interaction,button):
        await self.summon(interaction,10)

    @discord.ui.button(label='ดูการันตี',emoji='🎯',style=discord.ButtonStyle.secondary)
    async def pity(self,interaction,button):
        await interaction.response.send_message(embed=pity_embed(store,interaction.user.id,self.banner),ephemeral=True)

    async def on_timeout(self):
        for child in self.children:
            child.disabled=True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                logging.exception('Could not disable expired banner')

class Duel(GameView):
    def __init__(self, challenger, opponent):
        super().__init__(timeout=120)
        self.ids = (challenger,opponent)
        self.battle = None
        self.message = None
        self.closed = False
        self.history=[]
        self.refresh_buttons()

    def refresh_buttons(self):
        for button in (self.attack,self.skill,self.guard,self.surrender):
            button.disabled=self.battle is None or self.closed
        if self.battle and not self.closed:
            actor=self.battle.fighters[self.battle.turn]
            self.skill.label=STYLE[actor.unit][2]+f' · {skill_cost(actor.unit)} MP'
            self.skill.disabled=actor.cooldown>0 or actor.mana<skill_cost(actor.unit)

    def close(self):
        self.closed = True
        busy.difference_update(self.ids)
        for child in self.children:
            child.disabled = True
        self.stop()

    def render(self, text=''):
        return battle_embed(self.ids,self.battle,self.history,ended=text or None)

    async def on_timeout(self):
        self.close()
        if self.message:
            try:
                await self.message.edit(content=None,embed=self.render('⌛ หมดเวลาการต่อสู้ ยกเลิกแมตช์แล้ว'),view=self)
            except discord.HTTPException:
                logging.exception('Could not update expired duel')

    async def interaction_check(self, interaction):
        if self.closed or interaction.user.id not in self.ids:
            await interaction.response.send_message('คุณไม่ได้อยู่ในแมตช์นี้ หรือแมตช์จบแล้ว', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='รับคำท้า',emoji='⚔️',style=discord.ButtonStyle.success,row=0)
    async def accept(self, interaction, button):
        if self.battle or interaction.user.id != self.ids[1]:
            await interaction.response.send_message('เฉพาะผู้ถูกท้าเท่านั้นที่รับคำท้าได้', ephemeral=True)
            return
        self.battle = Battle(*self.ids,store)
        self.remove_item(self.accept)
        self.remove_item(self.cancel)
        self.refresh_buttons()
        await interaction.response.edit_message(content=None,embed=self.render(),view=self)

    @discord.ui.button(label='ปฏิเสธ / ยกเลิก',style=discord.ButtonStyle.secondary,row=0)
    async def cancel(self, interaction, button):
        if self.battle:
            await interaction.response.send_message('ใช้ปุ่มยอมแพ้เพื่อออกจากการต่อสู้',ephemeral=True)
            return
        self.close()
        await interaction.response.edit_message(content=None,embed=self.render('ยกเลิกคำท้าแล้ว'),view=self)

    async def move(self, interaction, action):
        if not self.battle:
            await interaction.response.send_message('รอรับคำท้าก่อน',ephemeral=True)
            return
        try:
            text = self.battle.act(interaction.user.id,action)
        except GameError as error:
            await interaction.response.send_message(str(error),ephemeral=True)
            return
        self.history.append(f'<@{interaction.user.id}> › {text}')
        if self.battle.finished:
            self.close()
        self.refresh_buttons()
        await interaction.response.edit_message(content=None,embed=self.render(),view=self)

    @discord.ui.button(label='โจมตี',emoji='⚔️',style=discord.ButtonStyle.primary,row=1)
    async def attack(self, interaction, button):
        await self.move(interaction,'attack')

    @discord.ui.button(label='สกิล · 20 MP',emoji='✨',style=discord.ButtonStyle.primary,row=1)
    async def skill(self, interaction, button):
        await self.move(interaction,'skill')

    @discord.ui.button(label='ป้องกัน',emoji='🛡️',style=discord.ButtonStyle.secondary,row=1)
    async def guard(self, interaction, button):
        await self.move(interaction,'guard')

    @discord.ui.button(label='ยอมแพ้',emoji='🏳️',style=discord.ButtonStyle.danger,row=2)
    async def surrender(self, interaction, button):
        await self.move(interaction,'surrender')

async def show_banner(interaction,banner='standard'):
    view=SummonView(banner)
    if not banner_is_open(banner):
        view.single.disabled=True
        view.ten.disabled=True
    filename='kuru-banner.png' if banner=='kuru' else 'summon-banner.png'
    image=Path(__file__).with_name('assets')/filename
    await interaction.response.send_message(embed=banner_embed(banner),view=view,file=discord.File(image,filename=filename))
    view.message=await interaction.original_response()

@bot.tree.command(name='daily',description='รับ 300 เพชรรายวัน')
async def daily(interaction: discord.Interaction):
    store.daily(interaction.user.id)
    gems,_,_=store.profile(interaction.user.id)
    await interaction.response.send_message(embed=card('💎 ของขวัญจากดวงดาว',f'รับ **300 เพชร** แล้ว!\nยอดคงเหลือ **{gems:,} 💎**\nเปิด `/banner` เพื่อเริ่มสุ่ม'),ephemeral=True)

@bot.tree.command(name='gacha',description='เปิดตู้กาชา 5★ พร้อมปุ่มสุ่ม 1 / 10 ครั้ง')
async def gacha(interaction: discord.Interaction):
    await show_banner(interaction,'kuru')

@bot.tree.command(name='banner',description='เปิดแบนเนอร์กาชาและดูการันตีส่วนตัว')
@app_commands.choices(banner=[app_commands.Choice(name='🦋 Kuru Limited',value='kuru'),app_commands.Choice(name='🐉 ตู้ถาวร',value='standard')])
async def banner(interaction: discord.Interaction,banner: app_commands.Choice[str]=None):
    await show_banner(interaction,banner.value if banner else 'kuru')

@bot.tree.command(name='character',description='ดูค่าสถานะ อาวุธ และสกิลของตัวละคร')
@app_commands.choices(character=[app_commands.Choice(name=unit_label(k),value=k) for k in CATALOG])
async def character(interaction: discord.Interaction,character: app_commands.Choice[str]):
    await interaction.response.send_message(embed=character_embed(character.value),ephemeral=True)

@bot.tree.command(name='collection',description='ดูตัวละครและเพชรของคุณ')
async def collection(interaction: discord.Interaction):
    gems,pity,active = store.profile(interaction.user.id)
    rows = [f'{STYLE[u][0]} **{unit_label(u)}** ×{n}' for u,n in store.collection(interaction.user.id)]
    embed=card('✦ หอแห่งผู้ร่วมเดินทาง',f'💎 **{gems:,}** · การันตีตู้ถาวร 5★ **{pity}/50**\nลงสนาม: **{unit_label(active)}**')
    limited_pity,_=store.guarantees(interaction.user.id,'kuru')
    embed.add_field(name='🦋 การันตี Kuru Limited',value=f'{limited_pity}/50 · นับแยกจากตู้ถาวร',inline=False)
    embed.add_field(name='คอลเลกชันของคุณ',value='\n'.join(rows),inline=False)
    embed.set_footer(text='ASTRAL • ใช้ /team เพื่อเลือกตัวละครลงสนาม')
    await interaction.response.send_message(embed=embed,ephemeral=True)

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
        await interaction.response.send_message(content=f'<@{opponent.id}> มีคำท้าประลองถึงคุณ',embed=view.render(),view=view,allowed_mentions=discord.AllowedMentions(users=True))
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
