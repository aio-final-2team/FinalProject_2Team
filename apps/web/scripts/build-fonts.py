"""학교안심 둥근미소 원본(TTF/OTF)에서 웹용 woff2를 만든다(FONTS.md).

사용: python3 scripts/build-fonts.py <둥근미소 보통 파일> <둥근미소 굵게 파일>
필요: pip install fonttools brotli
결과: public/fonts/Dunggeunmiso-400.woff2, Dunggeunmiso-700.woff2
"""
import sys
from fontTools import subset
from fontTools.ttLib import TTFont

# 한글 완성형 11,172자 전부 + 영문·숫자·기호. 아이 이름의 드문 글자도 둥근미소로 나온다.
han = [chr(c) for c in range(0xAC00, 0xD7A4)]
chars = "".join(han) + "".join(chr(c) for c in range(0x3131, 0x3164)) + "".join(chr(c) for c in range(0x20, 0x7F)) + "①②③④⑤⑥⑦⑧⑨⑩·—–…“”‘’‹›→←↑↓✓×"

for src, dst in zip(sys.argv[1:3], ("public/fonts/Dunggeunmiso-400.woff2", "public/fonts/Dunggeunmiso-700.woff2")):
    opt = subset.Options()
    opt.flavor = "woff2"
    opt.layout_features = ["*"]
    opt.name_IDs = ["*"]
    opt.notdef_outline = True
    font = TTFont(src)
    sub = subset.Subsetter(opt)
    sub.populate(text=chars)
    sub.subset(font)
    font.flavor = "woff2"
    font.save(dst)
    print(dst, "저장")
