"""Discord-native cards. No network requests or database writes during rendering."""
import discord
from game import CATALOG, skill_cost, skill_cooldown, banner_is_open, ULTIMATES, FEATURED

PURPLE = 0xA78BFA
GOLD = 0xF5C76B
CYAN = 0x53D7D9
FOOTER = 'ASTRAL • Gacha & Arena'
STYLE = {
    'knight': ('🛡️','เหล็กกล้า','ดาบพิทักษ์'),
    'mage': ('🔮','อาคม','ระเบิดดารา'),
    'ranger': ('🏹','วายุ','ศรพายุ'),
    'paladin': ('✨','แสง','คำพิพากษา'),
    'dragon': ('🐉','เพลิง','ลมหายใจมังกร'),
    'kuru': ('🦋','มืด','ราตรีผีเสื้อ'),
    'eiji': ('📸','ภาพถ่าย','บันทึกแสง'),
    'yuko': ('🌺','บุปผา','ฮิกังบานสะบั้น'),
    'mala': ('🎵','เสียง','คลื่นเสียงประสาน'),
}

def unit_label(unit):
    name,stars,_,_ = CATALOG[unit]
    return f'{name} [{stars}★]'

def bar(current, maximum, size=10):
    current=max(0,min(current,maximum))
    fill=max(1,round(current/maximum*size)) if current else 0
    return '▰'*fill+'▱'*(size-fill)

def card(title, description='', color=PURPLE):
    embed=discord.Embed(title=title,description=description,color=color)
    embed.set_footer(text=FOOTER)
    return embed

def character_embed(unit):
    name,stars,hp,attack=CATALOG[unit]
    icon,element,skill=STYLE[unit]
    embed=card(f'{icon} {name} • {stars}★'+(' LIMITED' if unit=='kuru' else ''),f'ธาตุ{element} · '+('HP-scaling / Stun DPS' if unit=='kuru' else 'นักสู้'))
    embed.add_field(name='ค่าสถานะ',value=f'HP **{hp}** · MP **100**\n'+('ความเสียหายสเกล **HP สูงสุด**' if unit=='kuru' else f'ATK **{attack}**'),inline=False)
    if unit=='kuru':
        embed.add_field(name='🦋 อาวุธ · ผีเสื้อแห่งราตรี',value='ฝูงผีเสื้อเงามืดคือคมอาวุธของ Kuru',inline=False)
        embed.add_field(name='โจมตี · ปีกเงา',value='ดาเมจ **16% HP สูงสุด** (เริ่มต้น 38) · ฟื้น 10 MP',inline=False)
        embed.add_field(name='สกิล · ราตรีผีเสื้อ',value='ดาเมจ **32% HP สูงสุด** (เริ่มต้น 76) + **สตั้น 1 เทิร์น**\nใช้ **30 MP** · เว้น **3 เทิร์นที่ลงมือได้** ก่อนใช้ซ้ำ',inline=False)
        embed.add_field(name='🌘 อันติ · สุริยคราสพันผีเสื้อ',value='ดาเมจ **60% HP สูงสุด** (เริ่มต้น 144) · ใช้พลังอันติ **100** ไม่ใช้ MP\nใช้ได้เฉพาะเทิร์นตัวเอง · ไม่ติดสตั้น · การป้องกันลดดาเมจได้',inline=False)
        embed.add_field(name='เกจอันติ',value='เริ่ม 0/100 ทุกแมตช์ · โจมตี +25 · สกิล +35 · ป้องกัน +15\nถูกโจมตีแล้วเสีย HP +10 · หลังใช้อันติเกจเหลือ 0',inline=False)
        embed.add_field(name='กลไกสตั้น',value='ข้ามเทิร์นเป้าหมายอัตโนมัติ แสดงในบันทึกการต่อสู้\nการป้องกันลดดาเมจได้ แต่ไม่กันสตั้น · ไม่สตั้นเป้าหมายที่แพ้แล้ว',inline=False)
        embed.add_field(name='ได้รับจาก',value='ตู้ **Kuru Limited** เท่านั้น ไม่อยู่ในตู้ถาวร\n5★ มีโอกาส 50% เป็น Kuru / 50% เป็น Eiji ถ้าหลุดเรท 5★ ครั้งถัดไปเป็น Kuru แน่นอน',inline=False)
    elif unit in ('eiji','yuko','mala'):
        details={
            'eiji':('📸 กล้องบันทึกภาพ','บันทึก HP ที่เสียสะสมสูงสุด 90 ใช้สกิลทำดาเมจ 2×ATK + ครึ่งหนึ่งของภาพบันทึก แล้วล้างบันทึก','อันติ: 3×ATK + ภาพบันทึกทั้งหมด แล้วล้างบันทึก · อยู่ในตู้ถาวรและเป็นตัวหลุดเรท'),
            'yuko':('🌺 ดาบและดอกฮิกังบาน','สกิล 2×ATK + แผลฮิกังบาน 2 เทิร์น แผลสร้างดาเมจ 8% HP สูงสุดของเป้าหมายตอนเริ่มเทิร์น ไม่ถูกลดด้วยการป้องกัน','อันติ: 3×ATK + แผลฮิกังบาน 3 เทิร์น · Limited ตู้แยก ไม่อยู่ตู้ถาวร'),
            'mala':('🎵 เสียง ดนตรี และคลื่นเสียง','สกิล 2×ATK พร้อมฮีลเพื่อนที่มีสัดส่วน HP ต่ำที่สุด 12% HP สูงสุดของเพื่อน','อันติ: 3×ATK พร้อมฮีลทุกคนที่ยังมีชีวิตในทีม 18% HP สูงสุดของแต่ละคน · 4★ พูลร่วม')}
        weapon,effect,ultimate=details[unit]
        embed.add_field(name=weapon,value=effect+'\nใช้ 20 MP · เว้น 2 เทิร์น',inline=False)
        embed.add_field(name='🌘 '+ULTIMATES[unit]['name'],value=ultimate+'\nใช้พลัง 100 ไม่ใช้ MP',inline=False)
        embed.add_field(name='พลังอันติ',value='โจมตี +25 · สกิล +35 · ป้องกัน +15 · เสีย HP +10 · เริ่มแมตช์ที่ 0',inline=False)
    else:
        embed.add_field(name=f'สกิล · {skill}',value=f'ดาเมจ {attack*2} · ใช้ 20 MP · เว้น 2 เทิร์น',inline=False)
    return embed

def banner_embed(banner='standard'):
    if banner in FEATURED:
        unit=FEATURED[banner]
        label=CATALOG[unit][0]
        theme='🦋 ราตรีผีเสื้อ' if unit=='kuru' else '🌺 คมดาบฮิกังบาน'
        embed=card(f'{label.upper()} LIMITED • {theme}',f'**{label} 5★** · ตู้ Limited แยกเฉพาะตัวละคร')
        feature='HP **240** · สกิล **32% HP สูงสุด** + สตั้น 1 เทิร์น\nอันติ **60% HP สูงสุด**' if unit=='kuru' else 'HP **190** · ATK **38** · ดาบและดอกฮิกังบาน\nสกิลและอันติสร้างแผลบุปผาต่อเนื่อง'
        embed.add_field(name='✦ ตัวละครประจำตู้',value=feature,inline=False)
        embed.add_field(name='💎 อธิษฐาน',value='**100 เพชร** / 1 ครั้ง · **1,000 เพชร** / 10 ครั้ง',inline=False)
        embed.add_field(name='🎯 50/50 และการันตี',value=f'5★ ภายใน **50 ครั้ง** · 50% **{label}** / 50% **Eiji**\nถ้าหลุดเป็น Eiji: 5★ ครั้งถัดไปเป็น **{label} แน่นอน**\n4★ ขึ้นไปภายใน **10 ครั้ง** · ตัวนับและสถานะการันตีแยกแต่ละตู้',inline=False)
        embed.add_field(name='อัตราพื้นฐานก่อนการันตี',value='5★ **2%** / 4★ **10%** / 3★ **88%**\n4★: พาลาดิน / Mala Natsumi โอกาสเท่ากัน',inline=False)
        embed.add_field(name='สถานะตู้',value=('เปิดตู้ · ยังไม่กำหนดวันปิด' if banner_is_open(banner) else 'ปิดตู้แล้ว')+'\nLimited ไม่เข้าตู้ถาวร · รางวัลเป็นของผู้กดเท่านั้น',inline=False)
        embed.set_image(url=f'attachment://{banner}-banner.png')
        return embed
    embed=card('✦ ASTRAL SUMMON • พันธสัญญาราชามังกร',
        'เมื่อดวงดาวตอบรับ… ตำนานบทใหม่จะเป็นของคุณ\n'
        'ตู้ถาวร • สะสมตัวละครเพื่อประลองกับเพื่อน')
    embed.add_field(name='👑 ตำนาน 5★',value='**ราชามังกร** · เพลิง\n**Eiji** · ภาพถ่าย\nโอกาสเท่ากันเมื่อได้ 5★',inline=True)
    embed.add_field(name='✨ อัศวิน 4★',value='**พาลาดิน** · แสง\n**Mala Natsumi** · เสียง',inline=True)
    embed.add_field(name='💎 เลือกเส้นทางแห่งโชคชะตา',value='**100 เพชร** / 1 ครั้ง　•　**1,000 เพชร** / 10 ครั้ง',inline=False)
    embed.add_field(name='🎯 การันตีที่เดินไปกับคุณ',value='5★ ภายใน **50 ครั้ง** · 4★ ขึ้นไปภายใน **10 ครั้ง**\nนับรวมทั้งสุ่มเดี่ยวและสุ่มสิบ รีเซ็ตเมื่อได้ระดับที่กำหนด',inline=False)
    embed.add_field(name='อัตราพื้นฐานก่อนการันตี',value='5★ **2%**　/　4★ **10%**　/　3★ **88%**\nทุกคนกดได้ · ใช้เพชรและรับตัวละครเข้าบัญชีผู้กดเท่านั้น',inline=False)
    embed.set_image(url='attachment://summon-banner.png')
    return embed

def pity_embed(store, uid, banner='standard'):
    gems,_,_=store.profile(uid)
    pity,pity4=store.guarantees(uid,banner)
    embed=card('🎯 เส้นทางสู่ดวงดาว',f'กระเป๋าของ <@{uid}> · **{gems:,} 💎**\nตู้ **{CATALOG[FEATURED[banner]][0]+" Limited" if banner in FEATURED else "ถาวร"}**')
    embed.add_field(name=f'5★ · {pity}/50',value=f'`{bar(pity,50)}`\nอีกไม่เกิน **{50-pity} ครั้ง**',inline=False)
    embed.add_field(name=f'4★ ขึ้นไป · {pity4}/10',value=f'`{bar(pity4,10)}`\nอีกไม่เกิน **{10-pity4} ครั้ง**',inline=False)
    if banner in FEATURED:
        embed.add_field(name='สถานะ 50/50',value='5★ ถัดไปเป็นตัวประจำตู้แน่นอน' if store.featured_guaranteed(uid,banner) else '5★ ถัดไปลุ้น 50/50 กับ Eiji',inline=False)
    return embed

def result_embed(store, uid, units, banner='standard'):
    top=max(CATALOG[u][1] for u in units)
    gems,_,_=store.profile(uid)
    pity,pity4=store.guarantees(uid,banner)
    embed=card('✦ ดวงดาวตอบรับคำอธิษฐาน',
        f'ตู้ **{CATALOG[FEATURED[banner]][0]+" Limited" if banner in FEATURED else "ถาวร"}**\nผลสุ่ม **{len(units)} ครั้ง** · ใช้ **{len(units)*100:,} 💎**', GOLD if top==5 else PURPLE if top==4 else CYAN)
    rows=[]
    for index,unit in enumerate(units,1):
        icon,element,_=STYLE[unit]
        stars=CATALOG[unit][1]
        rows.append(f'`{index:02}` {"🌟" if stars==5 else "✦"} **{unit_label(unit)}** {icon} {element}')
    embed.add_field(name='ผู้ร่วมเดินทางคนใหม่',value='\n'.join(rows),inline=False)
    embed.add_field(name='💎 คงเหลือ',value=f'**{gems:,}**',inline=True)
    embed.add_field(name='🎯 การันตี',value=f'5★ `{pity}/50` · 4★+ `{pity4}/10`',inline=True)
    if banner in FEATURED:
        embed.add_field(name='สถานะหลังสุ่ม',value='5★ ถัดไปเป็นตัวประจำตู้แน่นอน' if store.featured_guaranteed(uid,banner) else '5★ ถัดไปลุ้น 50/50 กับ Eiji',inline=False)
    embed.set_footer(text=FOOTER+' • ตัวละครซ้ำสะสมเป็นจำนวนสำเนา')
    return embed

def battle_embed(ids,battle,history=(),ended=None,target_index=None):
    if battle and len(battle.fighters)>2:
        return team_battle_embed(ids,battle,history,ended,target_index)
    if not battle:
        embed=card('⚔️ ARENA • จดหมายท้าประลอง',f'<@{ids[0]}>  **VS**  <@{ids[1]}>\n\nผู้ถูกท้ากด **รับคำท้า** เพื่อเข้าสู่สนาม\nเลือกตัวละครด้วย `/team` ก่อนส่งคำท้า',CYAN)
    else:
        embed=card('⚔️ ASTRAL ARENA • ศึกแห่งดวงดาว',color=GOLD if battle.finished else CYAN)
        for index,fighter in enumerate(battle.fighters):
            _,_,_,attack=CATALOG[fighter.unit]
            maximum=fighter.max_hp
            cost=skill_cost(fighter.unit)
            scaling='HP-scaling 16% / 32%' if fighter.unit=='kuru' else f'ATK **{attack}**'
            icon,element,skill=STYLE[fighter.unit]
            active=not battle.finished and index==battle.turn
            status='🛡️ ตั้งรับ' if fighter.guard else 'พร้อมรบ'
            if fighter.bleed:status+=f' · 🌺 แผล {fighter.bleed} เทิร์น'
            if fighter.unit=='eiji':status+=f' · 📸 บันทึก {fighter.recorded}/90'
            skill_state=f'รอ {fighter.cooldown} เทิร์น' if fighter.cooldown else 'พร้อมใช้' if fighter.mana>=cost else 'MP ไม่พอ'
            ultimate = ''
            if fighter.unit in ULTIMATES:
                ultimate = f'\n\n🌘 **{fighter.energy}/100 พลังอันติ**\n`{bar(fighter.energy,100)}`\n'+('**อันติพร้อมใช้!**' if fighter.energy>=100 else 'สะสมพลังเพื่อปลดปล่อยอันติ')
            embed.add_field(name=f'{"▶ " if active else ""}{icon} {unit_label(fighter.unit)}',
                value=f'<@{fighter.uid}> · {element}\n\n❤️ **{fighter.hp}/{maximum}**\n`{bar(fighter.hp,maximum)}`\n'
                f'💠 **{fighter.mana}/100 MP**\n`{bar(fighter.mana,100)}`\n\n{scaling} · {status}\n✦ {skill} · {cost} MP · {skill_state}{ultimate}',inline=True)
        if battle.finished:
            status=f'🏆 ผู้ชนะ <@{battle.winner}>' if battle.winner else '🤝 เสมอ'
        else:
            status=f'🎯 ตาของ <@{battle.fighters[battle.turn].uid}> · เทิร์นที่ {battle.rounds+1}'
        embed.add_field(name='สถานะสนาม',value=status,inline=False)
        if history:
            embed.add_field(name='📜 บันทึกการต่อสู้',value='\n'.join(history[-3:]),inline=False)
        embed.add_field(name='คำสั่งสนามรบ',value='⚔️ โจมตี: ฟื้น 10 MP · 🛡️ ป้องกัน: ลดดาเมจ 50% / ฟื้น 15 MP\n✦ สกิลทั่วไป: 20 MP / เว้น 2 เทิร์น · Kuru: 30 MP / เว้น 3 เทิร์น + สตั้น 1 เทิร์น\n🌘 อันติ Kuru: ใช้พลัง 100 · ดาเมจ 60% HP สูงสุด · ไม่ใช้ MP',inline=False)
    if ended:
        embed.description=ended
        embed.color=discord.Color.dark_grey()
    embed.set_footer(text=FOOTER+' • หมดเวลาเมื่อไม่มีการเล่น 120 วินาที • สูงสุด 100 เทิร์น')
    return embed


def team_battle_embed(ids,battle,history=(),ended=None,target_index=None):
    embed=card('⚔️ ASTRAL ARENA • 4 VS 4',ended or 'เลือกเป้าหมาย แล้วใช้คำสั่งของตัวละครที่ถึงคิว',GOLD if battle.finished else CYAN)
    for owner in ids:
        rows=[]
        for index,f in enumerate(battle.fighters):
            if f.uid!=owner:continue
            icon=STYLE[f.unit][0]
            active='▶ ' if not battle.finished and index==battle.turn else ''
            status='💀 ล้ม' if not f.hp else ('🛡️' if f.guard else '')
            if f.stunned:status+=' 💫 สตั้น'
            if f.bleed:status+=f' 🌺{f.bleed}'
            energy=f' · 🌘{f.energy}' if f.unit in ULTIMATES else ''
            record=f' · 📸{f.recorded}' if f.unit=='eiji' else ''
            rows.append(f'{active}{icon} **{unit_label(f.unit)}** {status}\n❤️ {f.hp}/{f.max_hp} `{bar(f.hp,f.max_hp,7)}`\n💠 {f.mana} MP · CD {f.cooldown}{energy}{record}')
        embed.add_field(name=f'ทีมของ <@{owner}>',value='\n\n'.join(rows),inline=True)
    if battle.finished:
        text=f'🏆 ผู้ชนะ <@{battle.winner}>' if battle.winner else '🤝 เสมอ'
    else:
        actor=battle.fighters[battle.turn]
        text=f'เทิร์น **{battle.rounds+1}** · <@{actor.uid}> ควบคุม **{CATALOG[actor.unit][0]}**\n✦ {STYLE[actor.unit][2]} · {skill_cost(actor.unit)} MP · CD {actor.cooldown}'
        if target_index in battle.enemies():text+=f'\n🎯 เป้าหมาย: **{CATALOG[battle.fighters[target_index].unit][0]}**'
    embed.add_field(name='คิวและเป้าหมาย',value=text,inline=False)
    if history:embed.add_field(name='📜 บันทึกล่าสุด',value='\n'.join(history[-3:]),inline=False)
    embed.set_footer(text=FOOTER+' • 4 ตัว/ทีม • หมดเวลา 120 วินาที • สูงสุด 200 เทิร์น')
    return embed
