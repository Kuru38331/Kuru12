import logging
import os
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from game import Battle, TeamBattle, CATALOG, GameError, Store, skill_cost, banner_is_open, ULTIMATES
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

class TargetSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder='เลือกเป้าหมายฝ่ายตรงข้าม',row=0,options=[discord.SelectOption(label='รอเริ่มการต่อสู้',value='0')],disabled=True)
    async def callback(self,interaction):
        await self.view.choose_target(interaction,int(self.values[0]))

class Duel(GameView):
    def __init__(self, challenger, opponent, mode='1v1'):
        super().__init__(timeout=120)
        self.ids = (challenger,opponent)
        self.mode=mode
        self.target=None
        self.selection_turn=None
        self.target_select=TargetSelect() if mode=='4v4' else None
        self.battle = None
        self.message = None
        self.closed = False
        self.history=[]
        self.refresh_buttons()

    def refresh_buttons(self):
        for button in (self.attack,self.skill,self.ultimate,self.guard,self.surrender):
            button.disabled=self.battle is None or self.closed
        if self.target_select:
            self.target_select.disabled=self.battle is None or self.closed
        if self.battle and not self.closed:
            enemies=self.battle.enemies()
            if self.selection_turn!=self.battle.turn or self.target not in enemies:
                self.target=enemies[0]
            self.selection_turn=self.battle.turn
            if self.target_select:
                self.target_select.options=[discord.SelectOption(label=f'{CATALOG[self.battle.fighters[i].unit][0]} · HP {self.battle.fighters[i].hp}',value=str(i),default=i==self.target,emoji=STYLE[self.battle.fighters[i].unit][0]) for i in enemies]
            actor=self.battle.fighters[self.battle.turn]
            self.skill.label=STYLE[actor.unit][2]+f' · {skill_cost(actor.unit)} MP'
            self.skill.disabled=actor.cooldown>0 or actor.mana<skill_cost(actor.unit)
            ultimate=ULTIMATES.get(actor.unit)
            self.ultimate.label=('อันติ · '+ultimate['name']) if ultimate else 'อันติ · ยังไม่มี'
            self.ultimate.disabled=ultimate is None or actor.energy<ultimate['energy_cost']
            self.ultimate.style=discord.ButtonStyle.danger if not self.ultimate.disabled else discord.ButtonStyle.secondary

    def close(self):
        self.closed = True
        busy.difference_update(self.ids)
        for child in self.children:
            child.disabled = True
        self.stop()

    def render(self, text=''):
        embed=battle_embed(self.ids,self.battle,self.history,ended=text or None,target_index=self.target)
        if not self.battle and self.mode=='4v4':
            embed.title='⚔️ ARENA 4v4 • จดหมายท้าประลอง'
            embed.description+='\n⚔️ โหมดทีมคนละ 4 ตัว · ใช้ทีมจาก /squad'
        return embed

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
        self.battle = (TeamBattle if self.mode=='4v4' else Battle)(*self.ids,store)
        self.remove_item(self.accept)
        self.remove_item(self.cancel)
        if self.target_select:self.add_item(self.target_select)
        self.refresh_buttons()
        await interaction.response.edit_message(content=None,embed=self.render(),view=self)

    @discord.ui.button(label='ปฏิเสธ / ยกเลิก',style=discord.ButtonStyle.secondary,row=0)
    async def cancel(self, interaction, button):
        if self.battle:
            await interaction.response.send_message('ใช้ปุ่มยอมแพ้เพื่อออกจากการต่อสู้',ephemeral=True)
            return
        self.close()
        await interaction.response.edit_message(content=None,embed=self.render('ยกเลิกคำท้าแล้ว'),view=self)

    async def choose_target(self,interaction,index):
        if not self.battle or self.closed or self.battle.fighters[self.battle.turn].uid!=interaction.user.id:
            await interaction.response.send_message('เลือกเป้าหมายได้เฉพาะผู้เล่นที่ถึงตา',ephemeral=True)
            return
        if index not in self.battle.enemies():
            await interaction.response.send_message('เป้าหมายนี้เลือกไม่ได้',ephemeral=True)
            return
        self.target=index
        self.refresh_buttons()
        await interaction.response.edit_message(content=None,embed=self.render(),view=self)

    async def move(self, interaction, action):
        if not self.battle:
            await interaction.response.send_message('รอรับคำท้าก่อน',ephemeral=True)
            return
        try:
            text = self.battle.act(interaction.user.id,action,self.target)
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

    @discord.ui.button(label='อันติ · ชาร์จพลัง',emoji='🌘',style=discord.ButtonStyle.secondary,row=2)
    async def ultimate(self, interaction, button):
        await self.move(interaction,'ultimate')

    @discord.ui.button(label='ยอมแพ้',emoji='🏳️',style=discord.ButtonStyle.danger,row=2)
    async def surrender(self, interaction, button):
        await self.move(interaction,'surrender')

async def show_banner(interaction,banner='standard'):
    view=SummonView(banner)
    if not banner_is_open(banner):
        view.single.disabled=True
        view.ten.disabled=True
    filename=banner+'-banner.png' if banner in ('kuru','yuko') else 'summon-banner.png'
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
@app_commands.choices(banner=[app_commands.Choice(name='🦋 Kuru Limited',value='kuru'),app_commands.Choice(name='🌺 Yuko Hanaka Limited',value='yuko'),app_commands.Choice(name='🐉 ตู้ถาวร',value='standard')])
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
    yuko_pity,_=store.guarantees(interaction.user.id,'yuko')
    embed.add_field(name='🌺 การันตี Yuko Limited',value=f'{yuko_pity}/50 · ดูสถานะ 50/50 ในตู้',inline=False)
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

UNIT_CHOICES=[app_commands.Choice(name=unit_label(k),value=k) for k in CATALOG]

@bot.tree.command(name='squad',description='จัดทีมตัวละคร 4 ตัวสำหรับ 4v4 หรือดูทีมที่บันทึก')
@app_commands.choices(slot1=UNIT_CHOICES,slot2=UNIT_CHOICES,slot3=UNIT_CHOICES,slot4=UNIT_CHOICES)
async def squad(interaction: discord.Interaction,slot1: app_commands.Choice[str]=None,slot2: app_commands.Choice[str]=None,slot3: app_commands.Choice[str]=None,slot4: app_commands.Choice[str]=None):
    slots=(slot1,slot2,slot3,slot4)
    if any(slots):
        if not all(slots):raise GameError('กรอกตัวละครให้ครบ 4 ช่อง')
        if interaction.user.id in busy:raise GameError('เปลี่ยนทีมไม่ได้ขณะมีคำท้าหรือกำลังต่อสู้')
        store.set_lineup(interaction.user.id,[slot.value for slot in slots])
    units=store.lineup(interaction.user.id)
    embed=card('⚔️ ทีม 4v4 ของคุณ','\n'.join(f'{i}. {unit_label(unit)}' for i,unit in enumerate(units,1)))
    await interaction.response.send_message(embed=embed,ephemeral=True)

@bot.tree.command(name='battle',description='ท้าเพื่อนต่อสู้ PvP แบบเทิร์นเบส')
@app_commands.guild_only()
@app_commands.choices(mode=[app_commands.Choice(name='1v1',value='1v1'),app_commands.Choice(name='4v4',value='4v4')])
async def battle(interaction: discord.Interaction, opponent: discord.Member,mode: app_commands.Choice[str]=None):
    uid = interaction.user.id
    if opponent.bot or opponent.id == uid:
        raise GameError('ต้องท้าผู้เล่นคนอื่นที่ไม่ใช่บอท')
    if uid in busy or opponent.id in busy:
        raise GameError('ผู้เล่นคนใดคนหนึ่งมีคำท้าหรือกำลังต่อสู้อยู่')
    selected=mode.value if mode else '1v1'
    if selected=='4v4':
        store.lineup(uid)
        store.lineup(opponent.id)
    view = Duel(uid,opponent.id,selected)
    busy.update(view.ids)
    try:
        await interaction.response.send_message(content=f'<@{opponent.id}> มีคำท้าประลองถึงคุณ',embed=view.render(),view=view,allowed_mentions=discord.AllowedMentions(users=True))
        view.message = await interaction.original_response()
    except Exception:
        view.close()
        raise

def require_admin(interaction,member=None):
    if not interaction.guild_id or not interaction.permissions.administrator:
        raise GameError('คำสั่งนี้ใช้ได้เฉพาะ Administrator ในเซิร์ฟเวอร์')
    trusted=os.getenv('ADMIN_GUILD_ID') or os.getenv('DISCORD_GUILD_ID')
    if trusted:
        if not trusted.isascii() or not trusted.isdecimal():
            raise GameError('ตั้งค่า ADMIN_GUILD_ID หรือ DISCORD_GUILD_ID ไม่ถูกต้อง')
        if int(trusted)!=interaction.guild_id:
            raise GameError('คำสั่งแอดมินใช้ได้เฉพาะเซิร์ฟเวอร์ที่กำหนด')
    if member is not None and (member.bot or member.guild.id!=interaction.guild_id):
        raise GameError('เลือกผู้เล่นที่ไม่ใช่บอทและอยู่ในเซิร์ฟเวอร์นี้')

admin=app_commands.Group(name='admin',description='คำสั่งเสกของสำหรับ Administrator',guild_only=True,default_permissions=discord.Permissions(administrator=True))

@admin.command(name='gems',description='เพิ่มเพชรให้ผู้เล่น')
@app_commands.checks.has_permissions(administrator=True)
async def admin_gems(interaction: discord.Interaction,member: discord.Member,amount: app_commands.Range[int,1,1000000000],reason: str='แอดมินแจกของ'):
    require_admin(interaction,member)
    store.admin_grant(interaction.id,interaction.user.id,interaction.guild_id,member.id,'gems',amount,reason=reason)
    gems,_,_=store.profile(member.id)
    await interaction.response.send_message(embed=card('💎 เพิ่มเพชรสำเร็จ',f'ผู้เล่น <@{member.id}>\nเพิ่ม **{amount:,}** · คงเหลือ **{gems:,}**'),ephemeral=True)

@admin.command(name='character',description='เพิ่มตัวละครให้ผู้เล่น รวมตัว Limited')
@app_commands.checks.has_permissions(administrator=True)
@app_commands.choices(character=UNIT_CHOICES)
async def admin_character(interaction: discord.Interaction,member: discord.Member,character: app_commands.Choice[str],copies: app_commands.Range[int,1,1000]=1,reason: str='แอดมินแจกของ'):
    require_admin(interaction,member)
    store.admin_grant(interaction.id,interaction.user.id,interaction.guild_id,member.id,'character',copies,character.value,reason)
    await interaction.response.send_message(embed=card('✦ เพิ่มตัวละครสำเร็จ',f'<@{member.id}> ได้รับ **{unit_label(character.value)} ×{copies}**\nใช้ /team หรือ /squad เพื่อเลือกลงสนาม'),ephemeral=True)

@admin.command(name='team',description='แจก Kuru Eiji Yuko Mala อย่างละ 1 และจัดทีมให้ทันที')
@app_commands.checks.has_permissions(administrator=True)
async def admin_team(interaction: discord.Interaction,member: discord.Member,reason: str='แอดมินแจกทีมทดสอบ'):
    require_admin(interaction,member)
    if member.id in busy:raise GameError('ผู้เล่นกำลังมีคำท้าหรือต่อสู้อยู่ รอจบก่อนแจกและเปลี่ยนทีม')
    store.admin_grant(interaction.id,interaction.user.id,interaction.guild_id,member.id,'team',reason=reason)
    await interaction.response.send_message(embed=card('⚔️ ทีมพร้อมลงสนาม',f'<@{member.id}> ได้ **Kuru / Eiji / Yuko Hanaka / Mala Natsumi** อย่างละ 1\nบันทึกทีม 4v4 แล้ว และเลือก Kuru สำหรับ 1v1'),ephemeral=True)

@admin.command(name='logs',description='ดูประวัติการเสกของล่าสุด 10 รายการของเซิร์ฟเวอร์')
@app_commands.checks.has_permissions(administrator=True)
async def admin_logs(interaction: discord.Interaction):
    require_admin(interaction)
    rows=store.admin_history(interaction.guild_id)
    lines=[f'<t:{timestamp}:R> <@{actor}> → <@{target}> · {action} `{item}` ×{amount:,}' for timestamp,actor,target,action,item,amount in rows]
    await interaction.response.send_message(embed=card('📜 ประวัติแอดมิน','\n'.join(lines) or 'ยังไม่มีรายการ'),ephemeral=True)

bot.tree.add_command(admin)

@bot.tree.error
async def command_error(interaction, error):
    cause = getattr(error,'original',error)
    expected=isinstance(cause,(GameError,app_commands.MissingPermissions,app_commands.NoPrivateMessage))
    message = str(cause) if isinstance(cause,GameError) else 'คำสั่งนี้ใช้ได้เฉพาะ Administrator ในเซิร์ฟเวอร์' if expected else 'เกิดข้อผิดพลาด ลองใหม่อีกครั้ง'
    if not expected:
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
