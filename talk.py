"""Talk to the agent in the terminal, as the customer. Add --voice to hear every reply (gTTS) and save the audio.

    python talk.py                    # type your answers (English, Hinglish or Hindi)
    python talk.py --voice            # also speaks each reply (macOS: afplay)
    python talk.py --model llama3.2:3b --variant few_shot
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from voiceagent.agent import Agent  # noqa: E402
from voiceagent.flow import Call  # noqa: E402
from voiceagent.lang import detect  # noqa: E402
from voiceagent.llm import ChatModel  # noqa: E402


def say(text: str, voice: bool) -> None:
    print(f"\nPriya: {text}")
    if voice:
        from voiceagent.voice.tts import speak
        path, _ = speak(text, detect(text), Path("out") / "talk")
        subprocess.run(["afplay", str(path)], check=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen2.5:3b")
    ap.add_argument("--variant", default="persona", choices=["zero_shot", "few_shot", "persona"])
    ap.add_argument("--voice", action="store_true")
    args = ap.parse_args()

    agent, call = Agent(ChatModel(args.model), variant=args.variant), Call()
    history = [{"speaker": "agent", "text": agent.opening()}]
    say(agent.opening(), args.voice)
    while not call.done:
        said = input("\nYou: ").strip()
        if not said:
            continue
        history.append({"speaker": "customer", "text": said})
        turn = agent.respond(call, history)
        history.append({"speaker": "agent", "text": turn.reply})
        say(turn.reply, args.voice)
        print(f"   [{turn.intent} | stage: {call.state} | collected: {call.slots}]")
    print(f"\nCall ended: {call.outcome}")


if __name__ == "__main__":
    main()
