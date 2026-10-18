"""Illustrate the implemented moods; not the upstream project's full gallery.

Keep the schematic pose parameters aligned with src/qiuqiu_motion.h.
Character reference and non-commercial restrictions: assets/qiuqiu/README.md.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'voice-device/assets/qiuqiu'
SCALE = 4


def pose(eyes, mouth=0, dots=False):
    image=Image.open(ASSETS/'texture.png').resize((192*SCALE,192*SCALE),Image.Resampling.LANCZOS)
    draw=ImageDraw.Draw(image)
    for x,y,half,radius,tilt in eyes:
        # Capsule segment rotated like the firmware, rendered at 4x for AA.
        import math
        norm=math.sqrt(1+tilt*tilt)
        vx,vy=tilt*half/norm,half/norm
        a=((x-vx)*SCALE,(y-vy)*SCALE);b=((x+vx)*SCALE,(y+vy)*SCALE)
        draw.line([a,b],fill='#24252c',width=round(2*radius*SCALE))
        for cx,cy in (a,b):draw.ellipse((cx-radius*SCALE,cy-radius*SCALE,cx+radius*SCALE,cy+radius*SCALE),fill='#24252c')
    if mouth:
        ry=1+mouth*8
        draw.ellipse((86*SCALE,(128-ry)*SCALE,106*SCALE,(128+ry)*SCALE),fill='#24252c')
    if dots:
        for i in range(3):
            x=88+i*12
            draw.ellipse(((x-3)*SCALE,48*SCALE,(x+3)*SCALE,54*SCALE),fill=['#8b847b','#554f4a','#26252c'][i])
    return image.resize((192,192),Image.Resampling.LANCZOS)


def main():
    idle=[(76,91,13,5,-.25),(118,83,10,4,-.18)]
    think=[(73,81,9,5,-.32),(115,77,4,5,.22)]
    modes=[('待机','自然眨眼与视线移动',idle,0,False),
           ('录音','睁大眼睛，认真倾听',[(76,87,12,7,-.08),(118,87,12,7,.08)],0,False),
           ('思考','抬眼与跳动的小点',think,0,True),
           ('说话','嘴巴随声音开合',[(76,87,7,5,-.12),(118,85,7,5,.12)],.75,False),
           ('休息','收起眼睛',[(76,91,.5,3,1.3),(118,83,.5,3,1.3)],0,False),
           ('等待审批','目前复用思考表情',think,0,True),
           ('异常','收短眼睛提示异常',[(76,91,3,6,0),(118,83,3,6,0)],0,False)]
    font_path='C:/Windows/Fonts/msyh.ttc'
    title=ImageFont.truetype(font_path,25);label=ImageFont.truetype(font_path,19);small=ImageFont.truetype(font_path,13)
    sheet=Image.new('RGB',(1000,650),'#0b111c');d=ImageDraw.Draw(sheet)
    d.text((28,18),'球球 · 当前已实现的表情',font=title,fill='#edf2ff')
    d.text((28,56),'7 个状态，6 套表情造型；动态节奏和过渡请以实物屏幕为准。',font=small,fill='#a3b1c8')
    for i,(name,note,eyes,mouth,dots) in enumerate(modes):
        x=20+(i%4)*245;y=94+(i//4)*270
        d.rounded_rectangle((x,y,x+230,y+256),radius=16,fill='#111b29',outline='#27374b')
        sheet.paste(pose(eyes,mouth,dots),(x+19,y+8))
        d.text((x+16,y+206),name,font=label,fill='#edf2ff')
        d.text((x+16,y+234),note,font=small,fill='#a3b1c8')
    d.text((760,430),'原角色也完整保留',font=label,fill='#edf2ff')
    d.text((760,467),'可在 Bridge 屏幕图标中切换',font=small,fill='#a3b1c8')
    d.text((22,630),'球球视觉参考 sam70361/aora-bot · 仅限个人非商业学习使用',font=small,fill='#8596ad')
    output=ASSETS/'expressions-preview.png';sheet.save(output);print(output)


if __name__=='__main__':main()
