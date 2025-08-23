import pygame
import numpy as np
import time
import argparse
from reachy_mini_motor_controller import ReachyMiniMotorController

class JoystickReader:
    def __init__(self):
        pygame.init()
        pygame.joystick.init()
        
        if pygame.joystick.get_count() == 0:
            raise Exception("조이스틱이 연결되지 않았습니다!")
        
        self.joystick = pygame.joystick.Joystick(0)
        self.joystick.init()
        print(f"조이스틱 연결됨: {self.joystick.get_name()}")
    
    def read(self):
        """현재 조이스틱 상태를 딕셔너리로 반환"""
        pygame.event.pump()
        
        data = {
            'buttons': [],
            'axes': [],
            'hats': []
        }
        
        # 버튼 상태
        for i in range(self.joystick.get_numbuttons()):
            data['buttons'].append(self.joystick.get_button(i))
        
        # 축 상태 (스틱, 트리거)
        for i in range(self.joystick.get_numaxes()):
            data['axes'].append(round(self.joystick.get_axis(i), 3))
        
        # D-pad 상태
        for i in range(self.joystick.get_numhats()):
            data['hats'].append(self.joystick.get_hat(i))
        
        return data

class StewartPlatformIK:
    """Stewart 플랫폼 역기구학 클래스"""
    def __init__(self):
        # Stewart 플랫폼 기하학적 파라미터 (실제 하드웨어에 맞게 조정)
        self.base_radius = 0.1  # 베이스 반지름 (m)
        self.platform_radius = 0.08  # 플랫폼 반지름 (m)
        self.leg_length = 0.15  # 레그 길이 (m)
        self.base_height = 0.022  # 베이스 높이 (22mm로 조정)
        
        # 베이스와 플랫폼의 조인트 위치 (60도 간격)
        self.base_joints = []
        self.platform_joints = []
        
        for i in range(6):
            angle = i * 60 * np.pi / 180
            # 베이스 조인트
            self.base_joints.append([
                self.base_radius * np.cos(angle),
                self.base_radius * np.sin(angle),
                0
            ])
            # 플랫폼 조인트
            self.platform_joints.append([
                self.platform_radius * np.cos(angle),
                self.platform_radius * np.sin(angle),
                0
            ])
    
    def calculate_motor_angles(self, head_pose):
        """
        Head pose를 Stewart 플랫폼 모터 각도로 변환
        
        Args:
            head_pose: [x_rot, y_rot, z_trans] (라디안, 라디안, 미터)
        
        Returns:
            motor_angles: 6개 모터의 각도 (라디안)
        """
        x_rot, y_rot, z_trans = head_pose
        
        # 회전 행렬 계산
        Rx = np.array([
            [1, 0, 0],
            [0, np.cos(x_rot), -np.sin(x_rot)],
            [0, np.sin(x_rot), np.cos(x_rot)]
        ])
        
        Ry = np.array([
            [np.cos(y_rot), 0, np.sin(y_rot)],
            [0, 1, 0],
            [-np.sin(y_rot), 0, np.cos(y_rot)]
        ])
        
        R = Ry @ Rx
        
        motor_angles = []
        
        for i in range(6):
            # 플랫폼 조인트를 회전
            platform_joint = np.array(self.platform_joints[i])
            rotated_joint = R @ platform_joint
            
            # Z축 이동 적용
            rotated_joint[2] += z_trans
            
            # 베이스 조인트
            base_joint = np.array(self.base_joints[i])
            
            # 레그 벡터
            leg_vector = rotated_joint - base_joint
            
            # 레그 길이 계산
            leg_length = np.linalg.norm(leg_vector)
            
            # 모터 각도 계산 (개선된 역기구학)
            # 레그의 수평 거리 계산
            horizontal_distance = np.sqrt(leg_vector[0]**2 + leg_vector[1]**2)
            
            # 모터 각도 계산 (아크탄젠트 사용)
            if horizontal_distance > 0:
                motor_angle = np.arctan2(leg_vector[2], horizontal_distance)
            else:
                motor_angle = np.pi/2 if leg_vector[2] > 0 else -np.pi/2
            
            # -90도 오프셋 적용
            motor_angle_deg = np.rad2deg(motor_angle) - 90
            
            motor_angles.append(np.deg2rad(motor_angle_deg))
        
        return motor_angles

class MotorController:
    def __init__(self, serialport="COM5", nomotor=False, initial_current=50, operating_current=200, current_ratios=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0]):
        self.nomotor = nomotor
        self.initial_current = initial_current
        self.operating_current = operating_current
        self.current_ratios = current_ratios  # Stewart 플랫폼 모터별 골 커런트 비율
        
        if not self.nomotor:
            self.controller = ReachyMiniMotorController(serialport=serialport)
            print("✓ 모터 컨트롤러 연결 성공")
            
            # XL330 모터 초기 골 커런트 설정
            self.controller.set_stewart_platform_goal_current([self.initial_current] * 6)
            print(f"✓ XL330 초기 골 커런트 설정 완료: {self.initial_current}")
            
            # 토크 활성화
            self.controller.enable_torque()
            print("✓ 토크 활성화 완료")
        else:
            print("✓ 시뮬레이션 모드 (실제 모터 제어 없음)")
        
        # 현재 모터 위치 (라디안)
        self.current_positions = [0.0] * 9
        
        # Stewart 플랫폼 역기구학 초기화
        self.stewart_ik = StewartPlatformIK()
        
        # 현재 head pose (라디안, 라디안, 미터)
        self.current_head_pose = [0.0, 0.0, -0.008]  # [x_rot, y_rot, z_trans] - 초기 Z=-8mm (역기구학으로 -100도가 나오도록 조정)
        
        # 초기 위치 설정
        self.set_initial_positions()
    
    def set_initial_positions(self):
        """초기 위치 설정"""
        # 각 모터별 초기 각도 설정 (라디안)
        # 배열 순서: [11(베이스), 21(안테나1), 22(안테나2), 1(Stewart), 2(Stewart), 3(Stewart), 4(Stewart), 5(Stewart), 6(Stewart)]
        initial_positions = [
            np.deg2rad(0),   # 모터 11 (베이스) - STS3215
            np.deg2rad(0),   # 모터 21 (안테나1) - STS3215
            np.deg2rad(0),   # 모터 22 (안테나2) - STS3215
            np.deg2rad(-120),   # 모터 1 (Stewart) - XL330 (안전 범위: -135.3도~-20.2도)
            np.deg2rad(-120),   # 모터 2 (Stewart) - XL330
            np.deg2rad(-120),   # 모터 3 (Stewart) - XL330
            np.deg2rad(-120),   # 모터 4 (Stewart) - XL330
            np.deg2rad(-120),   # 모터 5 (Stewart) - XL330
            np.deg2rad(-120)    # 모터 6 (Stewart) - XL330
        ]
        
        self.current_positions = initial_positions.copy()
        
        if not self.nomotor:
            self.controller.set_all_goal_positions(initial_positions)
            print("✓ 초기 위치 설정 완료")
            
            # 모터가 초기 위치로 이동할 시간 대기
            print("모터 초기화 중... (3초)")
            time.sleep(3.0)
            
            # 초기화 완료 후 골 커런트를 operating_current로 증가 (비율 적용)
            operating_currents = [int(self.operating_current * ratio) for ratio in self.current_ratios]
            self.controller.set_stewart_platform_goal_current(operating_currents)
            print(f"✓ XL330 골 커런트 증가 완료: {operating_currents}")
            print("초기화 완료!")
        else:
            print("✓ 시뮬레이션 초기 위치 설정 완료")
            print(f"초기 각도: {[f'{np.rad2deg(pos):.1f}°' for pos in initial_positions]}")
    
    def adjust_motor_angle(self, motor_index, angle_change_deg):
        """특정 모터의 각도를 조정"""
        if 0 <= motor_index < 9:
            # 각도 변경 (도 → 라디안)
            angle_change_rad = np.deg2rad(angle_change_deg)
            self.current_positions[motor_index] += angle_change_rad
            
            # 각도 범위 제한
            angle_deg = np.rad2deg(self.current_positions[motor_index])
            
            # 모터 타입별 각도 범위 제한
            if 3 <= motor_index <= 8:  # 모터 1-6 (Stewart 플랫폼)
                # -135.3도 ~ -20.2도 범위 제한 (XL330 안전 범위)
                if angle_deg < -135.3:
                    angle_deg = -135.3
                elif angle_deg > -20.2:
                    angle_deg = -20.2
            else:  # 모터 11, 21, 22 (STS3215)
                # -180도 ~ +180도 범위 제한
                if angle_deg > 180:
                    angle_deg -= 360
                elif angle_deg < -180:
                    angle_deg += 360
            
            self.current_positions[motor_index] = np.deg2rad(angle_deg)
            
            # 모터 위치 업데이트
            if not self.nomotor:
                self.controller.set_all_goal_positions(self.current_positions)
            
            # 모터 이름
            motor_names = ["11(베이스)", "21(안테나1)", "22(안테나2)", 
                          "1(Stewart)", "2(Stewart)", "3(Stewart)", 
                          "4(Stewart)", "5(Stewart)", "6(Stewart)"]
            
            current_deg = np.rad2deg(self.current_positions[motor_index])
            print(f"모터 {motor_names[motor_index]}: {current_deg:.1f}°")
    
    def adjust_head_pose(self, axis_index, value_change):
        """Head pose 조정 및 Stewart 플랫폼 모터 각도 계산"""
        if axis_index == 2:  # Z축 이동
            # Z축 높이에 따른 동적 스케일링
            current_z = self.current_head_pose[axis_index]
            
            # Z축이 높아질수록 스케일을 증가시켜 모터 각도 변화를 일정하게 유지
            if current_z < 0.05:  # 50mm 미만
                z_scale = 0.001  # 1mm씩
            elif current_z < 0.1:  # 50-100mm
                z_scale = 0.002  # 2mm씩
            elif current_z < 0.2:  # 100-200mm
                z_scale = 0.005  # 5mm씩
            elif current_z < 0.5:  # 200-500mm
                z_scale = 0.01   # 10mm씩
            else:  # 500mm 이상
                z_scale = 0.02   # 20mm씩
            
            # Z축 이동 (동적 스케일링 적용)
            self.current_head_pose[axis_index] += value_change * z_scale
            
            # Z축 이동 범위 제한 (-0.05m ~ +1.1m) - 음수 허용하여 -120도까지 가능
            if self.current_head_pose[axis_index] > 1.1:
                self.current_head_pose[axis_index] = 1.1
            elif self.current_head_pose[axis_index] < -0.05:
                self.current_head_pose[axis_index] = -0.05
        else:  # X, Y축 회전
            # 회전 각도 변경 (도 → 라디안) - 더 부드럽게 0.5도씩
            angle_change_rad = np.deg2rad(value_change * 0.5)  # 절반 크기로 조정
            self.current_head_pose[axis_index] += angle_change_rad
            
            # 회전 범위 제한 (-30도 ~ +30도)
            angle_deg = np.rad2deg(self.current_head_pose[axis_index])
            if angle_deg > 30:
                angle_deg = 30
            elif angle_deg < -30:
                angle_deg = -30
            self.current_head_pose[axis_index] = np.deg2rad(angle_deg)
        
        # Stewart 플랫폼 역기구학으로 모터 각도 계산
        motor_angles = self.stewart_ik.calculate_motor_angles(self.current_head_pose)
        
        # Stewart 플랫폼 모터 각도 업데이트 (각도 범위 제한 적용)
        for i in range(6):
            angle_deg = np.rad2deg(motor_angles[i])
            
            # 각도 범위 제한 (-135.3도 ~ -20.2도)
            if angle_deg < -135.3:
                angle_deg = -135.3
            elif angle_deg > -20.2:
                angle_deg = -20.2
            
            self.current_positions[i + 3] = np.deg2rad(angle_deg)
        
        # 모터 위치 업데이트
        if not self.nomotor:
            self.controller.set_all_goal_positions(self.current_positions)
        
        # Head pose 출력
        x_rot_deg = np.rad2deg(self.current_head_pose[0])
        y_rot_deg = np.rad2deg(self.current_head_pose[1])
        z_trans_mm = self.current_head_pose[2] * 1000  # 미터를 밀리미터로 변환
        
        # 모터 각도를 도 단위로 변환
        motor_angles_deg = [np.rad2deg(angle) for angle in motor_angles]
        
        print(f"Head Pose: X={x_rot_deg:.1f}°, Y={y_rot_deg:.1f}°, Z={z_trans_mm:.1f}mm")
        print(f"Stewart 모터 각도: {[f'{angle:.1f}°' for angle in motor_angles_deg]}")
    
    def set_stewart_platform_angle(self, target_angle_deg):
        """Stewart 플랫폼 모터들을 특정 각도로 설정"""
        # 각도 범위 제한 확인
        if target_angle_deg < -135.3:
            target_angle_deg = -135.3
        elif target_angle_deg > -20.2:
            target_angle_deg = -20.2
        
        # Stewart 플랫폼 모터들 (인덱스 3-8)을 목표 각도로 설정
        for i in range(6):
            self.current_positions[i + 3] = np.deg2rad(target_angle_deg)
        
        # 모터 위치 업데이트
        if not self.nomotor:
            self.controller.set_all_goal_positions(self.current_positions)
        
        print(f"Stewart 플랫폼 모터들을 {target_angle_deg:.1f}°로 설정 완료")
    
    def get_current_positions(self):
        """현재 모터 위치 읽기"""
        if not self.nomotor:
            try:
                positions = self.controller.read_all_positions()
                self.current_positions = list(positions)
                return positions
            except Exception as e:
                print(f"위치 읽기 오류: {e}")
                return self.current_positions
        else:
            return self.current_positions

def main():
    # 명령행 인수 파싱
    parser = argparse.ArgumentParser(description='조이스틱으로 Reachy Mini 모터 제어')
    parser.add_argument('--nomotor', action='store_true', help='실제 모터 제어 없이 각도만 출력 (시뮬레이션 모드)')
    parser.add_argument('--serialport', default='COM5', help='시리얼 포트 (기본값: COM5)')
    parser.add_argument('--initial-current', type=int, default=30, help='초기 골 커런트 (기본값: 30)')
    parser.add_argument('--operating-current', type=int, default=30, help='운영 골 커런트 (기본값: 30)')
    parser.add_argument('--current-ratios', nargs=6, type=float, default=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0], 
                       help='Stewart 플랫폼 모터별 골 커런트 비율 (기본값: 1.0 1.0 1.0 1.0 1.0 1.0)')
    args = parser.parse_args()
    
    if args.nomotor:
        print("=== 조이스틱 조작 Step 2: 시뮬레이션 모드 ===")
    else:
        print("=== 조이스틱 조작 Step 2: 실시간 모터 제어 ===")
    
    try:
        # 조이스틱과 모터 컨트롤러 초기화
        js = JoystickReader()
        motor_ctrl = MotorController(
            serialport=args.serialport, 
            nomotor=args.nomotor,
            initial_current=args.initial_current,
            operating_current=args.operating_current,
            current_ratios=args.current_ratios
        )
        
        # 각 모터 그룹별 스케일 설정
        antenna_scale = 20.0        # 안테나 (모터 21, 22) 스케일
        body_rotation_scale = 4.0   # 베이스 회전 (모터 11) 스케일
        head_scale = 5.0            # Head pose 스케일 (더 부드럽게)
        
        print("\n조작법:")
        print("- 버튼 6 + Axis 0: 모터 22 (안테나2) 제어")
        print("- 버튼 6 + Axis 3: 모터 21 (안테나1) 제어")
        print("- 버튼 7 + Axis 0: 모터 11 (베이스) 제어")
        print("- 버튼 7 + Axis 1: Head Pose Z 이동")
        print("- 버튼 7 + Axis 3: Head Pose X 회전")
        print("- 버튼 7 + Axis 4: Head Pose Y 회전")
        print("- 버튼 0: Stewart 플랫폼 -120°")
        print("- 버튼 1: Stewart 플랫폼 -60°")
        print("- 버튼 3: Stewart 플랫폼 -90°")
        print("- 버튼 4: Stewart 플랫폼 -30°")
        print("- 각도 범위: STS3215(-180°~+180°), XL330(-135.3°~-20.2°)")
        print("- Head 범위: X/Y 회전(-30°~+30°), Z 이동(-50mm~+1100mm)")
        print(f"- 안테나 스케일: {antenna_scale}도")
        print(f"- 베이스 회전 스케일: {body_rotation_scale}도")
        print(f"- Head pose 스케일: {head_scale}도")
        if not args.nomotor:
            print(f"- 초기 골 커런트: {args.initial_current}")
            print(f"- 운영 골 커런트: {args.operating_current}")
            print(f"- 골 커런트 비율: {args.current_ratios}")
        if args.nomotor:
            print("- 시뮬레이션 모드: 실제 모터 제어 없이 각도만 출력")
        print("- Ctrl+C로 종료")
        print()
        
        last_update_time = time.time()
        update_interval = 0.1  # 100ms마다 업데이트
        
        while True:
            data = js.read()
            
            current_time = time.time()
            if current_time - last_update_time < update_interval:
                time.sleep(0.01)
                continue
            
            # 버튼 6이 눌려있는지 확인
            if len(data['buttons']) > 6 and data['buttons'][6]:
                axis_0 = data['axes'][0] if len(data['axes']) > 0 else 0
                axis_3 = data['axes'][3] if len(data['axes']) > 3 else 0
                
                # Axis 0으로 모터 22 (안테나2) 제어
                if abs(axis_0) > 0.1:
                    angle_change = -axis_0 * antenna_scale
                    motor_ctrl.adjust_motor_angle(2, angle_change)  # 인덱스 2 = 모터 22
                
                # Axis 3으로 모터 21 (안테나1) 제어
                if abs(axis_3) > 0.1:
                    angle_change = -axis_3 * antenna_scale
                    motor_ctrl.adjust_motor_angle(1, angle_change)  # 인덱스 1 = 모터 21
            
            # 버튼 0, 1, 3, 4로 Stewart 플랫폼 각도 설정
            if len(data['buttons']) > 0 and data['buttons'][0]:
                motor_ctrl.set_stewart_platform_angle(-120)
            elif len(data['buttons']) > 1 and data['buttons'][1]:
                motor_ctrl.set_stewart_platform_angle(-60)
            elif len(data['buttons']) > 3 and data['buttons'][3]:
                motor_ctrl.set_stewart_platform_angle(-90)
            elif len(data['buttons']) > 4 and data['buttons'][4]:
                motor_ctrl.set_stewart_platform_angle(-30)
            
            # 버튼 7이 눌려있는지 확인
            if len(data['buttons']) > 7 and data['buttons'][7]:
                axis_0 = data['axes'][0] if len(data['axes']) > 0 else 0
                axis_1 = data['axes'][1] if len(data['axes']) > 1 else 0
                axis_3 = data['axes'][3] if len(data['axes']) > 3 else 0
                axis_4 = data['axes'][4] if len(data['axes']) > 4 else 0
                
                # 중복 적용 방지: 더 큰 값 하나만 적용
                # Axis 0과 Axis 1 중 더 큰 값 선택
                if abs(axis_0) > abs(axis_1) and abs(axis_0) > 0.1:
                    angle_change = -axis_0 * body_rotation_scale
                    motor_ctrl.adjust_motor_angle(0, angle_change)  # 인덱스 0 = 모터 11
                elif abs(axis_1) > 0.1:
                    value_change = -axis_1 * head_scale
                    motor_ctrl.adjust_head_pose(2, value_change)  # Z축 이동 (인덱스 2)
                
                # Axis 3과 Axis 4 중 더 큰 값 선택
                if abs(axis_3) > abs(axis_4) and abs(axis_3) > 0.1:
                    angle_change = -axis_3 * head_scale
                    motor_ctrl.adjust_head_pose(0, angle_change)  # X축 회전 (인덱스 0)
                elif abs(axis_4) > 0.1:
                    angle_change = -axis_4 * head_scale
                    motor_ctrl.adjust_head_pose(1, angle_change)  # Y축 회전 (인덱스 1)
            
            last_update_time = current_time
            
    except KeyboardInterrupt:
        print("\n프로그램 종료")
    except Exception as e:
        print(f"오류: {e}")

if __name__ == "__main__":
    main()
