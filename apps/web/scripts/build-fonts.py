"""학교안심 둥근미소 원본(TTF/OTF)에서 웹용 woff2를 만든다(FONTS.md).

사용: python3 scripts/build-fonts.py <둥근미소 보통 파일> <둥근미소 굵게 파일>
필요: pip install fonttools brotli
결과: public/fonts/Dunggeunmiso-400.woff2, Dunggeunmiso-700.woff2
"""
import sys
from fontTools import subset
from fontTools.ttLib import TTFont

# 한글 2,350자(KS X 1001) + 영문·숫자·기호. 이 밖의 글자는 Pretendard로 나온다.
han = []
for hi in range(0xB0, 0xC9):
    for lo in range(0xA1, 0xFF):
        try:
            han.append(bytes([hi, lo]).decode("euc-kr"))
        except UnicodeDecodeError:
            pass
chars = "".join(han) + "".join(chr(c) for c in range(0x20, 0x7F)) + "①②③④⑤⑥⑦⑧⑨⑩·—–…“”‘’‹›→←↑↓✓×"

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
