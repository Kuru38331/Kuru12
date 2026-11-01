"""Discord-native cards. No network requests or database writes during rendering."""
import discord
from game import CATALOG

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

def banner_embed():
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

def pity_embed(store, uid):
    gems,_,_=store.profile(uid)
    pity,pity4=store.guarantees(uid)
    embed=card('🎯 เส้นทางสู่ดวงดาว',f'กระเป๋าของ <@{uid}> · **{gems:,} 💎**')
    embed.add_field(name=f'5★ · {pity}/50',value=f'`{bar(pity,50)}`\nอีกไม่เกิน **{50-pity} ครั้ง**',inline=False)
    embed.add_field(name=f'4★ ขึ้นไป · {pity4}/10',value=f'`{bar(pity4,10)}`\nอีกไม่เกิน **{10-pity4} ครั้ง**',inline=False)
    return embed

def result_embed(store, uid, units):
    top=max(CATALOG[u][1] for u in units)
    gems,_,_=store.profile(uid)
    pity,pity4=store.guarantees(uid)
    embed=card('✦ ดวงดาวตอบรับคำอธิษฐาน',
        f'ผลสุ่ม **{len(units)} ครั้ง** · ใช้ **{len(units)*100:,} 💎**', GOLD if top==5 else PURPLE if top==4 else CYAN)
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
            _,_,maximum,attack=CATALOG[fighter.unit]
            icon,element,skill=STYLE[fighter.unit]
            active=not battle.finished and index==battle.turn
            status='🛡️ ตั้งรับ' if fighter.guard else 'พร้อมรบ'
            skill_state=f'รอ {fighter.cooldown} เทิร์น' if fighter.cooldown else 'พร้อมใช้' if fighter.mana>=20 else 'MP ไม่พอ'
            embed.add_field(name=f'{"▶ " if active else ""}{icon} {unit_label(fighter.unit)}',
                value=f'<@{fighter.uid}> · {element}\n\n❤️ **{fighter.hp}/{maximum}**\n`{bar(fighter.hp,maximum)}`\n'
                f'💠 **{fighter.mana}/100 MP**\n`{bar(fighter.mana,100)}`\n\nATK **{attack}** · {status}\n✦ {skill} · {skill_state}',inline=True)
        if battle.finished:
            status=f'🏆 ผู้ชนะ <@{battle.winner}>' if battle.winner else '🤝 เสมอ'
        else:
            status=f'🎯 ตาของ <@{battle.fighters[battle.turn].uid}> · เทิร์นที่ {battle.rounds+1}'
        embed.add_field(name='สถานะสนาม',value=status,inline=False)
        if history:
            embed.add_field(name='📜 บันทึกการต่อสู้',value='\n'.join(history[-3:]),inline=False)
        embed.add_field(name='คำสั่งสนามรบ',value='⚔️ โจมตี: ฟื้น 10 MP · ✦ สกิล: ใช้ 20 MP / เว้น 2 เทิร์น\n🛡️ ป้องกัน: ลดดาเมจ 50% / ฟื้น 15 MP',inline=False)
    if ended:
        embed.description=ended
        embed.color=discord.Color.dark_grey()
    embed.set_footer(text=FOOTER+' • หมดเวลาเมื่อไม่มีการเล่น 120 วินาที • สูงสุด 100 เทิร์น')
    return embed
