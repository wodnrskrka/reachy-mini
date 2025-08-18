import os
import sys
import tempfile
import requests
import speech_recognition as sr
import contextlib
import pygame
import noisereduce as nr
import soundfile as sf
import torch, cv2
import time

from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqLM
from ultralytics import YOLO
from kittentts import KittenTTS

# ========== 설정 ==========
USE_GPU = torch.cuda.is_available()
DEVICE = 0 if USE_GPU else -1
WAKE_WORDS = ["헬로", "hello", "hi", "하이", "안녕"]
EXIT_WORDS = ["없어", "됐어", "아니", "nothing"]
MUSIC_PATH = "/home/naseungwon/reachy_mini/no-copyright-music-1.mp3"

# [초기화: YOLO 모델 로드]
EMOTION_MODEL_PATH = "/home/naseungwon/reachy_mini/yolo_detect/best.pt"
emotion_model = YOLO(EMOTION_MODEL_PATH)
emotion_labels = ['anger', 'fear', 'happy', 'neutral', 'sad']

# ========== 초기화 ==========
pygame.mixer.init()

print("🧠 Whisper-large-v3 model loading...")
stt_pipeline = pipeline("automatic-speech-recognition", model="openai/whisper-large-v3", device=DEVICE)

model_id = "google/flan-t5-base"
tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForSeq2SeqLM.from_pretrained(model_id)
llm = pipeline("text2text-generation", model=model, tokenizer=tokenizer)

# ========== Kitten TTS 초기화 ==========
try:
    # 24kHz 출력이 기본
    pygame.mixer.quit()
    pygame.mixer.init(frequency=24000)
except Exception:
    # 실패 시 기본 설정으로 재초기화
    pygame.mixer.init()

KITTEN_SR = 24000
VOICE = 'expr-voice-2-f'  # 사용 가능한 보이스: 
# ['expr-voice-2-m','expr-voice-2-f','expr-voice-3-m','expr-voice-3-f',
#  'expr-voice-4-m','expr-voice-4-f','expr-voice-5-m','expr-voice-5-f']  :contentReference[oaicite:3]{index=3}

ktts = KittenTTS("KittenML/kitten-tts-nano-0.1")  # 프리뷰 모델 경로  :contentReference[oaicite:4]{index=4}


# ========== 유틸 함수 ==========
def suppress_stderr_globally():
    sys.stderr = open(os.devnull, 'w')

@contextlib.contextmanager
def suppress_stderr():
    with open(os.devnull, 'w') as fnull:
        stderr = sys.stderr
        sys.stderr = fnull
        try:
            yield
        finally:
            sys.stderr = stderr

# ========== 음성 입력 ==========
def listen_audio(timeout=10, phrase_time_limit=5, filename="input.wav"):
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("🎤 listening your voice...")
        with suppress_stderr():
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            with open(filename, "wb") as f:
                f.write(audio.get_wav_data())
            print(f"✅ save complete: {filename}")
    return filename

def clean_audio(input_path="input.wav", output_path="cleaned.wav"):
    try:
        data, rate = sf.read(input_path)
        reduced = nr.reduce_noise(y=data, sr=rate)
        sf.write(output_path, reduced, rate)
        print(f"🔇 killing noise complete → {output_path}")
        return output_path
    except Exception as e:
        print("❌ killing noise fail:", e)
        return input_path

def transcribe_audio(filename="cleaned.wav"):
    result = stt_pipeline(filename)
    print("📝 recognized text:", result['text'])
    return result['text'].strip()

# ========== 텍스트 응답 생성 ==========
def generate_response(text):
    prompt = f"질문: {text.strip()}\n대답:"
    result = llm(prompt, max_new_tokens=100)
    response = result[0]["generated_text"].strip()
    return response if response else "sorry, I can't understand."

# ========== 음성 출력 ==========
def speak(text):
    text = (text or "").strip()
    if not text:
        print("⚠️ there is no text to spend.")
        return
    print(f"🗣 response: {text}")
    audio = ktts.generate(text, voice=VOICE)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
        sf.write(fp.name, audio, KITTEN_SR)
        pygame.mixer.music.load(fp.name)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pass

# ========== 음악 재생 ==========
music_state = "stopped"  # 상태: "playing", "paused", "stopped"

def play_music():
    if os.path.exists(MUSIC_PATH):
        pygame.mixer.music.load(MUSIC_PATH)
        pygame.mixer.music.play()
        print("🎵 playing music...")
    else:
        speak("Sorry, I can't find music file.")

def stop_music():
    if pygame.mixer.music.get_busy():
        pygame.mixer.music.stop()
        print("⏹ Music  off")

def speak_nonblocking(text, lang='ko'):
    text = (text or "").strip()
    if not text:
        return
    audio = ktts.generate(text, voice=VOICE)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as fp:
        sf.write(fp.name, audio, KITTEN_SR)
        sound = pygame.mixer.Sound(fp.name)
        ch = pygame.mixer.find_channel()
        if ch:
            ch.play(sound)

# ========== 날씨 정보 ==========
def get_weather(city="Seoul"):
    API_KEY = "5d17af980c9cf48721b0e57c1b4fedaf"
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}&lang=kr&units=metric"
    res = requests.get(url)
    if res.status_code == 200:
        data = res.json()
        desc = data["weather"][0]["description"]
        temp = data["main"]["temp"]
        return f"The current weather in {city} is {desc}, and the temperature is {temp:.1f}degrees."
    else:
        return "Failed to get weather information  ."

# 감정 인식 함수 정의
def detect_emotion_yolo(timeout=5):
    try:
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        if not cap.isOpened():
            print("❌ Unable to open your webcam.")
            return None

        print("🧠 recognizing your motion ...")
        start_time = time.time()
        detected_emotion = None

        while time.time() - start_time < timeout:
            ret, frame = cap.read()
            if not ret:
                continue

            results = emotion_model.predict(frame, imgsz=640, verbose=False)[0]
            if len(results.boxes) > 0:
                # 가장 큰 얼굴 기준 (예외 방지용 if 문 보강)
                try:
                    box = max(results.boxes, key=lambda b: (b.xyxy[0][2] - b.xyxy[0][0]) * (b.xyxy[0][3] - b.xyxy[0][1]))
                    class_id = int(box.cls.item())
                    detected_emotion = emotion_labels[class_id]

                    # 바운딩 박스 그리기
                    xyxy = box.xyxy[0].cpu().numpy().astype(int)
                    cv2.rectangle(frame, (xyxy[0], xyxy[1]), (xyxy[2], xyxy[3]), (0, 255, 0), 2)
                    cv2.putText(frame, detected_emotion, (xyxy[0], xyxy[1] - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

                    cv2.imshow("Emotion Detection", frame)
                    cv2.waitKey(1000)
                    break
                except Exception as e:
                    print(f"❗Error occurs during emotion recognition: {e}")
                    continue

            # 얼굴 인식 안 되었을 경우
            cv2.imshow("Emotion Detection", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()

        return detected_emotion

    except Exception as e:
        print(f"🚨 Exception occurs during emotion recognition: {e}")
        return None

# ========== 메인 루프 ==========
def main():
    suppress_stderr_globally()
    print("🤖 'Waiting for Reachy Mini ...")

    # [1] 웨이크 워드 대기
    while True:
        path = listen_audio()
        cleaned = clean_audio(path)
        transcript = transcribe_audio(cleaned).lower()
        if any(transcript.startswith(wake) or transcript == wake for wake in WAKE_WORDS):
            speak("Hello! What can I help you?")
            break

    # [2] 명령 처리 루프 (지속적으로 명령 수용)
    while True:
        path = listen_audio()
        cleaned = clean_audio(path)
        user_text = transcribe_audio(cleaned).lower()

        if any(bye in user_text for bye in EXIT_WORDS):
            speak("Exit the program.")
            break

        # 명령 처리
        if "weather" in user_text:
            response = get_weather()
            speak(response)

        # 감정 분석 분기 추가
        elif "feeling" in user_text or "my feeling" in user_text:
            speak("I'll see how it feels. Please look at the camera for a moment")
            emotion = detect_emotion_yolo()
            if emotion in ['happy', 'sad']:
                if emotion == 'happy':
                    speak(f"You look happy! ({emotion})")
                elif emotion == 'sad':
                    speak(f"You look sad. What's happening? ({emotion})")
            else:
                speak("Sorry, I can't understand you emotion.")

        elif "music" in user_text or "sing" in user_text:
            speak("I'll play the music.")
            play_music()

            # 음악 재생 중 멈춤 감지 루프
            while True:
                path = listen_audio()
                cleaned = clean_audio(path)
                cmd = transcribe_audio(cleaned).lower()
                if "turn off" or "stop" in cmd:
                    stop_music()
                    speak("I'll turn off the music.")
                    break
                else:
                    speak_nonblocking("Sorry, I didn't understand.")
                    # 음악 계속 유지 (중단 안 됨!)

        else:
            response = generate_response(user_text)
            speak(response)

        # 다음 질문 유도
        speak("Is there anything I can help you?")


if __name__ == "__main__":
    main()
