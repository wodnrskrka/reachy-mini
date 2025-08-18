from gpiozero import Servo
from time import sleep

# min/max_pulse_width
servo = Servo(18, min_pulse_width=0.0005, max_pulse_width=0.0025)

def move_to_duty(duty_percent):
    # duty_percent(%) → pulse_width ()
    # 100% = 20ms (50Hz), 1% = 0.2ms
    pulse_width = duty_percent * 0.0002
    # 
    value = (pulse_width - 0.0005) / (0.0025 - 0.0005) * 2 - 1
    value = max(-1.0, min(1.0, value))  # clamp 
    servo.value = value
    print(f"Duty {duty_percent:.1f}% → value {value:.3f}")
    sleep(1)

# Pi.GPIO duty cycle
#  move_to_duty(5.0)  # 
move_to_duty(4.98)  # 
move_to_duty(6.0)  # 
#  move_to_duty(10.0) 
