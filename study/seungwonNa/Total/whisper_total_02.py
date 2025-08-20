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

from transformers import pipeline
from ultralytics import YOLO
from gtts import gTTS


# ========== 설정 ==========
USE_GPU = torch.cuda.is_available()
DEVICE = 0 if USE_GPU else -1
WAKE_WORDS = ["헬로", "hi", "하이", "안녕"]
EXIT_WORDS = ["없어", "됐어", "아니"]
MUSIC_PATH = "/home/naseungwon/reachy_mini/no-copyright-music-1.mp3"

# [초기화: YOLO 모델 로드]
EMOTION_MODEL_PATH = "/home/naseungwon/reachy_mini/yolo_detect/best.pt"
emotion_model = YOLO(EMOTION_MODEL_PATH)
emotion_labels = ['anger', 'fear', 'happy', 'neutral', 'sad']

# ========== 초기화 ==========
pygame.mixer.init()
pygame.mixer.set_num_channels(8)  # 채널 여유 확보
TTS_CH = pygame.mixer.Channel(7)  # TTS 전용 채널 하나 잡기

print("🧠 리치 미니 로딩 중...")
stt_pipeline = pipeline("automatic-speech-recognition", model="openai/whisper-large-v3", device=DEVICE)

model = "google/flan-t5-base"
llm = pipeline("text2text-generation", model=model)

# ========== 유틸 함수 ==========
@contextlib.contextmanager
def suppress_stderr():
    with open(os.devnull, 'w') as fnull:
        stderr = sys.stderr
        sys.stderr = fnull
        try:
            yield
        finally:
            sys.stderr = stderr

def _wait_tts_quiet(extra_ms=250):
    """TTS가 끝날 때까지 대기 (에코 방지) + 약간의 여유 시간"""
    try:
        while TTS_CH.get_busy():
            time.sleep(0.05)
    except Exception:
        pass
    time.sleep(extra_ms / 1000.0)

class _MusicDucker:
    def __init__(self, vol=0.25):
        self.vol = vol
        self.prev = None
    def __enter__(self):
        try:
            self.prev = pygame.mixer.music.get_volume()
            pygame.mixer.music.set_volume(self.vol)
        except Exception:
            pass
    def __exit__(self, exc_type, exc, tb):
        try:
            if self.prev is not None:
                pygame.mixer.music.set_volume(self.prev)
        except Exception:
            pass


# ========== 음성 입력 ==========
def listen_audio(timeout=10, phrase_time_limit=5, filename="input.wav"):
    _wait_tts_quiet()  # 👈 TTS 끝날 때까지 대기 (가장 중요!)
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("🎤 음성을 듣고 있어요...")
        try:
            recognizer.adjust_for_ambient_noise(source, duration=0.3)
        except Exception:
            pass
        with suppress_stderr():
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            with open(filename, "wb") as f:
                f.write(audio.get_wav_data())
            print(f"✅ 저장 완료: {filename}")
    return filename

def clean_audio(input_path="input.wav", output_path="cleaned.wav"):
    try:
        data, rate = sf.read(input_path)
        reduced = nr.reduce_noise(y=data, sr=rate)
        sf.write(output_path, reduced, rate)
        print(f"🔇 노이즈 제거 완료 → {output_path}")
        return output_path
    except Exception as e:
        print("❌ 노이즈 제거 실패:", e)
        return input_path

def transcribe_audio(filename="cleaned.wav"):
    result = stt_pipeline(filename)
    print("📝 인식된 텍스트:", result['text'])
    return result['text'].strip()

# ========== 텍스트 응답 생성 ==========
def generate_response(text):
    prompt = f"질문: {text.strip()}\n대답:"
    result = llm(prompt, max_new_tokens=100)
    response = result[0]["generated_text"].strip()
    return response if response else "죄송해요, 잘 이해하지 못했어요."

# ========== 음성 출력 ==========
def speak(text, lang='ko', blocking=True):
    if not text.strip():
        print("⚠️ 음성으로 출력할 텍스트가 없습니다.")
        return
    print(f"🗣 응답: {text}")
    tts = gTTS(text=text, lang=lang)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
        tts.save(fp.name)
        snd = pygame.mixer.Sound(fp.name)

    # 음악을 살짝 줄이고(TTS 선명도↑) TTS 전용 채널에서 재생
    with _MusicDucker(vol=0.25):
        TTS_CH.play(snd)
        if blocking:
            while TTS_CH.get_busy():
                time.sleep(0.05)


# ========== 음악 재생 ==========
def play_music():
    if os.path.exists(MUSIC_PATH):
        pygame.mixer.music.load(MUSIC_PATH)
        pygame.mixer.music.play()
        print("🎵 음악 재생 중...")
    else:
        speak("죄송해요, 음악 파일을 찾을 수 없어요.")

def stop_music():
    if pygame.mixer.music.get_busy():
        pygame.mixer.music.stop()
        print("⏹ 음악 꺼짐")

def speak_nonblocking(text, lang='ko'):
    tts = gTTS(text=text, lang=lang)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
        tts.save(fp.name)
        sound = pygame.mixer.Sound(fp.name)
        ch = pygame.mixer.find_channel()
        if ch:
            ch.play(sound)

# ========== 날씨 정보 ==========
def get_weather(city="Seoul"):
    API_KEY = "Your API KEY"
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}&lang=kr&units=metric"
    res = requests.get(url)
    if res.status_code == 200:
        data = res.json()
        desc = data["weather"][0]["description"]
        temp = data["main"]["temp"]
        return f"{city}의 현재 날씨는 {desc}, 기온은 {temp:.1f}도입니다."
    else:
        return "날씨 정보를 가져오는 데 실패했어요."

# 감정 인식 함수 정의
def detect_emotion_yolo(timeout=5, show=False):
    try:
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        if not cap.isOpened():
            print("❌ 웹캠을 열 수 없습니다.")
            return None

        print("🧠 감정 인식 중...")
        start_time = time.time()
        detected_emotion = None
        device_arg = 0 if USE_GPU else 'cpu'

        while time.time() - start_time < timeout:
            ret, frame = cap.read()
            if not ret:
                continue

            results = emotion_model.predict(frame, imgsz=640, device=device_arg, verbose=False)[0]
            if len(results.boxes) > 0:
                try:
                    box = max(results.boxes, key=lambda b: (b.xyxy[0][2] - b.xyxy[0][0]) * (b.xyxy[0][3] - b.xyxy[0][1]))
                    class_id = int(box.cls.item())
                    detected_emotion = emotion_labels[class_id]

                    if show:
                        xyxy = box.xyxy[0].cpu().numpy().astype(int)
                        cv2.rectangle(frame, (xyxy[0], xyxy[1]), (xyxy[2], xyxy[3]), (0, 255, 0), 2)
                        cv2.putText(frame, detected_emotion, (xyxy[0], xyxy[1] - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
                        cv2.imshow("Emotion Detection", frame)
                        if cv2.waitKey(1) & 0xFF == ord('q'):
                            break
                    else:
                        # 디버그 미표시 모드에서는 창을 띄우지 않음
                        pass

                    break
                except Exception as e:
                    print(f"❗ 감정 처리 중 오류 발생: {e}")
                    continue
            elif show:
                cv2.imshow("Emotion Detection", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

        cap.release()
        if show:
            cv2.destroyAllWindows()
        return detected_emotion

    except Exception as e:
        print(f"🚨 감정 인식 중 예외 발생: {e}")
        return None


# ========== 메인 루프 ==========
def main():
    print("🤖 '리치 미니'가 사용자를 기다리고 있어요 ...")

    # [1] 웨이크 워드 대기
    while True:
        path = listen_audio()
        cleaned = clean_audio(path)
        transcript = transcribe_audio(cleaned).lower()
        if any(transcript.startswith(wake) or transcript == wake for wake in WAKE_WORDS):
            speak("안녕하세요! 무엇을 도와드릴까요?")
            break

    # [2] 명령 처리 루프 (지속적으로 명령 수용)
    while True:
        path = listen_audio()
        cleaned = clean_audio(path)
        user_text = transcribe_audio(cleaned).lower()

        if any(bye in user_text for bye in EXIT_WORDS):
            speak("프로그램을 종료합니다.")
            break

        # 명령 처리
        if "날씨" in user_text:
            response = get_weather()
            speak(response)

        # 감정 분석 분기 추가
        elif "기분" in user_text or "내 기분" in user_text:
            speak("기분이 어떤지 봐드릴게요. 카메라를 잠시 바라봐주세요.")
            emotion = detect_emotion_yolo(show=False)
            if emotion in ['happy', 'sad']:
                if emotion == 'happy':
                    speak(f"기분이 좋아 보이네요! ({emotion})")
                elif emotion == 'sad':
                    speak(f"기분이 안 좋아 보이네요. 무슨 일 있어요? ({emotion})")
            else:
                speak("얼굴을 제대로 감지하지 못했어요.")

        elif "음악" in user_text or "노래" in user_text:
            speak("음악을 재생할게요.")
            play_music()

            # 음악 재생 중 멈춤 감지 루프
            while True:
                path = listen_audio()
                cleaned = clean_audio(path)
                cmd = transcribe_audio(cleaned).lower()
                if "꺼줘" in cmd:
                    stop_music()
                    speak("음악을 끌게요.")
                    break
                else:
                    speak_nonblocking("죄송해요, 잘 못 알아 들었어요.")
                    # 음악 계속 유지 (중단 안 됨!)

        else:
            response = generate_response(user_text)
            speak(response)

        # 다음 질문 유도
        speak("더 필요한 거 있으신가요?")


if __name__ == "__main__":
    main()
