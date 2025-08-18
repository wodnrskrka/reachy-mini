from gpiozero import LED
import time

led = LED(22) #GPIO22 pin(15), GPIO18 pin(8)

print("Ready. Type: 1=ON, 2=OFF, q=quit")
try:
    while True:
        cmd = input(">").strip()
        if cmd == "1":
            led.on()
            print("LED ON")
        elif cmd == "2":
            led.off()
            print("LED OFF")
        elif cmd.lower() in ("q", "quit", "exit"):
            break
        else:
            print("Use 1 or 2 (q to quit)")
except KeyboardInterrupt:
    pass
finally:
    led.close()
    print("Bye")
