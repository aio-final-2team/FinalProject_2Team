"""가상 대본 두 목소리를 한 WAV로 만들어요. 실제 녹음은 받지 않아요."""

import argparse
from io import BytesIO
import os
from pathlib import Path
import wave


def make(output):
    output = Path(output).resolve()
    if output.is_relative_to(Path(__file__).resolve().parents[1]):
        raise ValueError("가상 음성 출력은 저장소 밖 경로여야 해요.")
    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY를 설정하면 OpenAI TTS로 가상 상담 WAV를 만들어요. 실제 녹음은 쓰지 않아요.")
        return
    from openai import OpenAI
    turns = [("coral", "이 대화는 가상 상담이에요. 친구들과 어울리는 모습을 알려 주세요."),
             ("onyx", "가상 상담 예시예요. 놀이 중 친구에게 먼저 인사했어요. 다음 상담에서 함께 살펴볼게요.")]
    frames, params = [], None
    with OpenAI(timeout=60, max_retries=0) as client:
        for voice, script in turns:
            response = client.audio.speech.create(model="gpt-4o-mini-tts", voice=voice, input=script, response_format="wav")
            with wave.open(BytesIO(response.content)) as audio:
                current = (audio.getnchannels(), audio.getsampwidth(), audio.getframerate())
                if params is not None and current != params:
                    raise ValueError("두 가상 음성의 WAV 형식이 달라요.")
                params = current
                frames.append(audio.readframes(audio.getnframes()))
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as audio:
        audio.setnchannels(params[0])
        audio.setsampwidth(params[1])
        audio.setframerate(params[2])
        audio.writeframes(b"".join(frames))
    print(f"AI로 만든 가상 음성을 저장했어요: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", help="저장소 밖의 .wav 경로")
    make(parser.parse_args().output)
