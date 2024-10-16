#include <EEPROM.h>
#include <AccelStepper.h>

#define CLK_PIN 2
#define DT_PIN 3
#define SW_PIN 4

#define MOTOR1_STEP_PIN 5
#define MOTOR1_DIR_PIN 6
#define MOTOR2_STEP_PIN 7
#define MOTOR2_DIR_PIN 8

#define EEPROM_ADDR_MOTOR1_MIN 0
#define EEPROM_ADDR_MOTOR1_MAX 4
#define EEPROM_ADDR_MOTOR2_MIN 8
#define EEPROM_ADDR_MOTOR2_MAX 12

AccelStepper stepper1(AccelStepper::DRIVER, MOTOR1_STEP_PIN, MOTOR1_DIR_PIN);
AccelStepper stepper2(AccelStepper::DRIVER, MOTOR2_STEP_PIN, MOTOR2_DIR_PIN);

volatile int encoderValue = 0;
volatile bool encoderButtonPressed = false;
int lastCLKState;

long motor1Min, motor1Max, motor2Min, motor2Max;
bool settingEndpoints = false;
int currentMotor = 1;
bool settingMin = true;

void setup() {
  pinMode(CLK_PIN, INPUT_PULLUP);
  pinMode(DT_PIN, INPUT_PULLUP);
  pinMode(SW_PIN, INPUT_PULLUP);

  Serial.begin(115200);

  attachInterrupt(digitalPinToInterrupt(CLK_PIN), checkEncoder, CHANGE);
  attachInterrupt(digitalPinToInterrupt(SW_PIN), checkButton, FALLING);

  lastCLKState = digitalRead(CLK_PIN);

  stepper1.setMaxSpeed(1000);
  stepper1.setAcceleration(500);
  stepper2.setMaxSpeed(1000);
  stepper2.setAcceleration(500);

  delay(1000);

  if (digitalRead(SW_PIN) == LOW) {
    settingEndpoints = true;
    Serial.println("Entering endpoint setting mode");
  } else if (loadEndpointsFromEEPROM()) {
    Serial.println("Loaded endpoints from EEPROM");
  } else {
    settingEndpoints = true;
    Serial.println("No valid EEPROM data. Entering endpoint setting mode");
  }

  if (settingEndpoints) {
    setEndpoints();
  }
}

void loop() {
  stepper1.run();
  stepper2.run();

  // PROGRAM LOGIC
}

void checkEncoder() {
  int currentCLKState = digitalRead(CLK_PIN);
  int dtState = digitalRead(DT_PIN);

  if (currentCLKState != lastCLKState && currentCLKState == 0) {
    encoderValue += (dtState != currentCLKState) ? 1 : -1;
  }

  lastCLKState = currentCLKState;
}

void checkButton() {
  encoderButtonPressed = true;
}

bool loadEndpointsFromEEPROM() {
  EEPROM.get(EEPROM_ADDR_MOTOR1_MIN, motor1Min);
  EEPROM.get(EEPROM_ADDR_MOTOR1_MAX, motor1Max);
  EEPROM.get(EEPROM_ADDR_MOTOR2_MIN, motor2Min);
  EEPROM.get(EEPROM_ADDR_MOTOR2_MAX, motor2Max);

  // Simple validation: check if max > min for both motors
  return (motor1Max > motor1Min) && (motor2Max > motor2Min);
}

void saveEndpointsToEEPROM() {
  EEPROM.put(EEPROM_ADDR_MOTOR1_MIN, motor1Min);
  EEPROM.put(EEPROM_ADDR_MOTOR1_MAX, motor1Max);
  EEPROM.put(EEPROM_ADDR_MOTOR2_MIN, motor2Min);
  EEPROM.put(EEPROM_ADDR_MOTOR2_MAX, motor2Max);
}

void setEndpoints() {
  Serial.println("Setting endpoints. Use encoder to adjust position. Press button to set.");

  while (currentMotor <= 2) {
    if (encoderValue != 0) {
      if (currentMotor == 1) {
        stepper1.move(encoderValue);
      } else {
        stepper2.move(encoderValue);
      }
      encoderValue = 0;
    }

    stepper1.run();
    stepper2.run();

    if (encoderButtonPressed) {
      encoderButtonPressed = false;
      if (settingMin) {
        if (currentMotor == 1) {
          motor1Min = stepper1.currentPosition();
          Serial.print("Motor 1 Min set to: ");
          Serial.println(motor1Min);
        } else {
          motor2Min = stepper2.currentPosition();
          Serial.print("Motor 2 Min set to: ");
          Serial.println(motor2Min);
        }
        settingMin = false;
      } else {
        if (currentMotor == 1) {
          motor1Max = stepper1.currentPosition();
          Serial.print("Motor 1 Max set to: ");
          Serial.println(motor1Max);
        } else {
          motor2Max = stepper2.currentPosition();
          Serial.print("Motor 2 Max set to: ");
          Serial.println(motor2Max);
        }
        currentMotor++;
        settingMin = true;
      }
    }
  }

  saveEndpointsToEEPROM();
  Serial.println("Endpoints set and saved to EEPROM");
}