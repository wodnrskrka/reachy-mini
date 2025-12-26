from reachy_mini import ReachyMini  # 로봇 클래스 불러오기

# 로봇과 대화를 시도합니다.
try:
    with ReachyMini() as mini:
        print("Reachy Mini 연결 성공!")
        state = mini.get_state()
        print(f"로봇의 현재 상태: {state}")
except Exception as e:
    print("연결 또는 실행 중 오류 발생:", repr(e))