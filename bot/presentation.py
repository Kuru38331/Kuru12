"""Discord-native cards. No network requests or database writes during rendering."""
import discord
from game import CATALOG, skill_cost, skill_cooldown, banner_is_open, ULTIMATES

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
        embed.add_field(name='ได้รับจาก',value='ตู้ **Kuru Limited** เท่านั้น ไม่อยู่ในตู้ถาวร\nเมื่อออก 5★ จากตู้ Kuru จะเป็น Kuru 100% ไม่มี 50/50',inline=False)
    else:
        embed.add_field(name=f'สกิล · {skill}',value=f'ดาเมจ {attack*2} · ใช้ 20 MP · เว้น 2 เทิร์น',inline=False)
    return embed

def banner_embed(banner='standard'):
    if banner=='kuru':
        embed=card('🦋 KURU LIMITED • ราตรีผีเสื้อ',
            'ใต้เงาจันทร์… ทุกปีกที่ขยับคือคำตัดสิน\n'
            '**Kuru 5★ · มืด · HP-scaling Stun DPS**')
        embed.add_field(name='✦ ตัวละคร Limited',value='**Kuru** · อาวุธผีเสื้อ\nHP **240** · สกิล **32% HP สูงสุด** + สตั้น **1 เทิร์น**\n🌘 อันติ **60% HP สูงสุด** · สุริยคราสพันผีเสื้อ',inline=False)
        embed.add_field(name='💎 อธิษฐานแห่งราตรี',value='**100 เพชร** / 1 ครั้ง · **1,000 เพชร** / 10 ครั้ง',inline=False)
        embed.add_field(name='🎯 การันตีเฉพาะตู้นี้',value='5★ ภายใน **50 ครั้ง** · เมื่อออก 5★ เป็น **Kuru 100%**\n4★ ขึ้นไปภายใน **10 ครั้ง** · ตัวนับแยกจากตู้ถาวร',inline=False)
        embed.add_field(name='อัตราพื้นฐานก่อนการันตี',value='5★ **2%** / 4★ **10%** / 3★ **88%**\n4★: พาลาดิน · 3★: อัศวิน จอมเวท นักธนู',inline=False)
        embed.add_field(name='สถานะตู้',value=('เปิดรับคำอธิษฐาน · ยังไม่กำหนดวันปิดตู้' if banner_is_open(banner) else 'ปิดตู้แล้ว')+'\nLimited เฉพาะตู้ ไม่เข้าตู้ถาวร · รางวัลเป็นของผู้กดเท่านั้น',inline=False)
        embed.set_image(url='attachment://kuru-banner.png')
        return embed
    embed=card('✦ ASTRAL SUMMON • พันธสัญญาราชามังกร',
        'เมื่อดวงดาวตอบรับ… ตำนานบทใหม่จะเป็นของคุณ\n'
        'ตู้ถาวร • สะสมตัวละครเพื่อประลองกับเพื่อน')
    embed.add_field(name='👑 ตำนาน 5★',value='**ราชามังกร** · เพลิง\nHP 180 · ATK 42',inline=True)
    embed.add_field(name='✨ อัศวิน 4★',value='**พาลาดิน** · แสง\nHP 170 · ATK 33',inline=True)
    embed.add_field(name='💎 เลือกเส้นทางแห่งโชคชะตา',value='**100 เพชร** / 1 ครั้ง　•　**1,000 เพชร** / 10 ครั้ง',inline=False)
    embed.add_field(name='🎯 การันตีที่เดินไปกับคุณ',value='5★ ภายใน **50 ครั้ง** · 4★ ขึ้นไปภายใน **10 ครั้ง**\nนับรวมทั้งสุ่มเดี่ยวและสุ่มสิบ รีเซ็ตเมื่อได้ระดับที่กำหนด',inline=False)
    embed.add_field(name='อัตราพื้นฐานก่อนการันตี',value='5★ **2%**　/　4★ **10%**　/　3★ **88%**\nทุกคนกดได้ · ใช้เพชรและรับตัวละครเข้าบัญชีผู้กดเท่านั้น',inline=False)
    embed.set_image(url='attachment://summon-banner.png')
    return embed

def pity_embed(store, uid, banner='standard'):
    gems,_,_=store.profile(uid)
    pity,pity4=store.guarantees(uid,banner)
    embed=card('🎯 เส้นทางสู่ดวงดาว',f'กระเป๋าของ <@{uid}> · **{gems:,} 💎**\nตู้ **{"Kuru Limited" if banner=="kuru" else "ถาวร"}**')
    embed.add_field(name=f'5★ · {pity}/50',value=f'`{bar(pity,50)}`\nอีกไม่เกิน **{50-pity} ครั้ง**',inline=False)
    embed.add_field(name=f'4★ ขึ้นไป · {pity4}/10',value=f'`{bar(pity4,10)}`\nอีกไม่เกิน **{10-pity4} ครั้ง**',inline=False)
    return embed

def result_embed(store, uid, units, banner='standard'):
    top=max(CATALOG[u][1] for u in units)
    gems,_,_=store.profile(uid)
    pity,pity4=store.guarantees(uid,banner)
    embed=card('✦ ดวงดาวตอบรับคำอธิษฐาน',
        f'ตู้ **{"Kuru Limited" if banner=="kuru" else "ถาวร"}**\nผลสุ่ม **{len(units)} ครั้ง** · ใช้ **{len(units)*100:,} 💎**', GOLD if top==5 else PURPLE if top==4 else CYAN)
    rows=[]
    for index,unit in enumerate(units,1):
        icon,element,_=STYLE[unit]
        stars=CATALOG[unit][1]
        rows.append(f'`{index:02}` {"🌟" if stars==5 else "✦"} **{unit_label(unit)}** {icon} {element}')
    embed.add_field(name='ผู้ร่วมเดินทางคนใหม่',value='\n'.join(rows),inline=False)
    embed.add_field(name='💎 คงเหลือ',value=f'**{gems:,}**',inline=True)
    embed.add_field(name='🎯 การันตี',value=f'5★ `{pity}/50` · 4★+ `{pity4}/10`',inline=True)
    embed.set_footer(text=FOOTER+' • ตัวละครซ้ำสะสมเป็นจำนวนสำเนา')
    return embed

def battle_embed(ids,battle,history=(),ended=None):
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
