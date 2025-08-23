import numpy as np
import time
from reachy_mini_motor_controller import ReachyMiniMotorController

def main():
    print("=== Reachy Mini 모터 인터랙티브 테스트 ===")
    
    try:
        # COM5 포트 연결
        controller = ReachyMiniMotorController(serialport="COM5")
        print("✓ COM5 포트 연결 성공")
        
        # XL330 모터 골 커런트 설정 (50)
        controller.set_stewart_platform_goal_current([50, 50, 50, 50, 50, 50])
        print("✓ XL330 골 커런트 설정 완료: 50")
        
        # 토크 활성화
        controller.enable_torque()
        print("✓ 토크 활성화 완료")
        
        print("\n사용법:")
        print("- 모터 ID: 1-6 (XL330), 11, 21, 22 (STS3215)")
        print("- 각도: 도 단위 (예: 90)")
        print("- 여러 모터 동시 제어: ID와 각도를 스페이스로 구분")
        print("- 예시: '1 90' (모터 1을 90도로)")
        print("- 예시: '1 2 90 45' (모터 1을 90도, 모터 2를 45도로)")
        print("- 'quit' 입력 시 종료")
        print("- 'status' 입력 시 현재 위치 확인")
        print("- 'home' 입력 시 모든 모터를 0도로")
        print("- 'sin' 입력 시 사인파 모션 시작")
        print()
        
        # 현재 위치 배열 (9개 모터)
        current_positions = [0.0] * 9
        
        while True:
            try:
                # 사용자 입력 받기
                user_input = input("모터 ID와 각도 입력 (예: 1 90 또는 1 2 90 45): ").strip()
                
                if user_input.lower() == 'quit':
                    print("프로그램 종료")
                    break
                    
                elif user_input.lower() == 'status':
                    # 현재 위치 읽기
                    try:
                        positions = controller.read_all_positions()
                        print("\n=== 현재 모터 위치 ===")
                        print(f"모터 11 (베이스): {np.rad2deg(positions[0]):.1f}°")
                        print(f"모터 21 (안테나1): {np.rad2deg(positions[1]):.1f}°")
                        print(f"모터 22 (안테나2): {np.rad2deg(positions[2]):.1f}°")
                        print(f"모터 1 (Stewart): {np.rad2deg(positions[3]):.1f}°")
                        print(f"모터 2 (Stewart): {np.rad2deg(positions[4]):.1f}°")
                        print(f"모터 3 (Stewart): {np.rad2deg(positions[5]):.1f}°")
                        print(f"모터 4 (Stewart): {np.rad2deg(positions[6]):.1f}°")
                        print(f"모터 5 (Stewart): {np.rad2deg(positions[7]):.1f}°")
                        print(f"모터 6 (Stewart): {np.rad2deg(positions[8]):.1f}°")
                        print()
                    except Exception as e:
                        print(f"위치 읽기 오류: {e}")
                    continue
                    
                elif user_input.lower() == 'home':
                    # 모든 모터를 0도로
                    controller.set_all_goal_positions([0.0] * 9)
                    current_positions = [0.0] * 9
                    print("모든 모터를 0도로 이동 중...")
                    continue
                
                elif user_input.lower() == 'sin':
                    # 사인파 모션 시작
                    print("사인파 모션 시작 (Ctrl+C로 중단)...")
                    amp = np.deg2rad(30.0)
                    freq = 0.25
                    t0 = time.time()
                    
                    try:
                        while True:
                            t = time.time() - t0
                            pos = amp * np.sin(2 * np.pi * freq * t)
                            controller.set_all_goal_positions([pos] * 9)
                            time.sleep(0.01)
                    except KeyboardInterrupt:
                        print("사인파 모션 중단")
                    continue
                
                # 입력 파싱
                parts = user_input.split()
                if len(parts) < 2:
                    print("오류: 최소 모터 ID와 각도가 필요합니다.")
                    continue
                    
                if len(parts) % 2 != 0:
                    print("오류: 모터 ID와 각도 쌍이 맞지 않습니다.")
                    continue
                
                # 모터 ID와 각도 쌍 처리
                motor_angles = []
                for i in range(0, len(parts), 2):
                    try:
                        motor_id = int(parts[i])
                        angle_deg = float(parts[i + 1])
                        motor_angles.append((motor_id, angle_deg))
                    except ValueError:
                        print(f"오류: '{parts[i]}' 또는 '{parts[i + 1]}'이 유효한 숫자가 아닙니다.")
                        continue
                
                # 모터 ID를 배열 인덱스로 변환
                id_to_index = {
                    11: 0,  # 베이스 회전
                    21: 1,  # 안테나1
                    22: 2,  # 안테나2
                    1: 3,   # Stewart 1
                    2: 4,   # Stewart 2
                    3: 5,   # Stewart 3
                    4: 6,   # Stewart 4
                    5: 7,   # Stewart 5
                    6: 8    # Stewart 6
                }
                
                # 각도 변환 및 위치 배열 업데이트
                for motor_id, angle_deg in motor_angles:
                    if motor_id not in id_to_index:
                        print(f"오류: 모터 ID {motor_id}는 유효하지 않습니다.")
                        continue
                    
                    index = id_to_index[motor_id]
                    angle_rad = np.deg2rad(angle_deg)
                    current_positions[index] = angle_rad
                    
                    motor_name = {
                        11: "베이스 회전",
                        21: "안테나1", 
                        22: "안테나2",
                        1: "Stewart 1",
                        2: "Stewart 2", 
                        3: "Stewart 3",
                        4: "Stewart 4",
                        5: "Stewart 5",
                        6: "Stewart 6"
                    }[motor_id]
                    
                    print(f"모터 {motor_id} ({motor_name}): {angle_deg}° ({angle_rad:.3f} rad)")
                
                # 모든 모터 위치 설정
                controller.set_all_goal_positions(current_positions)
                print("모터 이동 명령 전송 완료!")
                print()
                
            except KeyboardInterrupt:
                print("\n프로그램 종료")
                break
            except Exception as e:
                print(f"오류 발생: {e}")
                print()
    
    except Exception as e:
        print(f"프로그램 오류: {e}")

if __name__ == "__main__":
    main()
