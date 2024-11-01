#define TEST true;


#include <EEPROM.h>
#include <LiquidCrystal_I2C.h>
#include <ArduinoJson.h>
#define ARDUINOJSON_ENABLE_STD_STRING 1


#ifdef TEST
#include <ESP32Servo.h>
#include <WiFi.h>
#include <HTTPClient.h>
const String ssid = "Wokwi-GUEST";
const String password = "";
String Bearer = "3423qKkMufcApKgs1fxGK1CfcPeYSgCnhpVF1opiaAex6gmrUKhNkGGpCgbNvAaKbr3GmL9c20Y6gn1QLQHuWkLknGu6xPJVno2B";
const int I1 = 32;
const int I2 = 5;
const int I3 = 0;
const int BuzzerChannel = 27;
const int ServoChannel = 12;
#else
#include <Servo.h>
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
const String ssid = "Disguised Wi-fi";
const String password = "9991337799";
String Bearer = "";
const int I1 = 14;
const int I2 = 12;
const int I3 = 13;
const int BuzzerChannel = D8;
const int ServoChannel = 0;
#endif





Servo servoObj;
const int ServoRefillPos = 35;
const int ServoDropPos = 0;
int servoCurrentPos = 10;
void refillCandy(bool instant)
{
	if (instant == true) servoObj.write(ServoRefillPos);
	else
	{
		for (servoCurrentPos; servoCurrentPos!=ServoRefillPos; servoCurrentPos+=1)
        {
            servoObj.write(servoCurrentPos);
            delay(50);
        }
	}
}
void dropCandy(bool instant)
{
	if (instant == true) servoObj.write(ServoDropPos);
	else
	{
		for (servoCurrentPos; servoCurrentPos!=ServoDropPos; servoCurrentPos-=1)
        {
            servoObj.write(servoCurrentPos);
            delay(50);
        }
	}
}







LiquidCrystal_I2C LCD(0x27, 20, 4);
int LCD_R = 0;
int LCD_C = 0;
int LCD_R_MAX = 4;
int LCD_C_MAX = 20;
void __print(String nextWord, char c)
{
    while (LCD_R>=LCD_R_MAX || LCD_C+nextWord.length()>LCD_C_MAX || c=='\n')
    {
        c = ' ';
        LCD_R += 1;
        LCD_C = 0;
        if (LCD_R>=LCD_R_MAX)
        {
            Serial.println("WARNING: Exceeding max rows!");
            return;
        }
    }
    cursor(LCD_R, LCD_C);
    if (nextWord.length()!=0) nextWord += " ";
    LCD.print(nextWord);
    LCD_C += nextWord.length();
}
void print(String s, bool newLine)
{
    if (s[s.length()-1] != '\0' || s[s.length()-1] != ' ' || s[s.length()-1] != '\n') s+=" ";
    String nextWord = "";
    if (newLine) __print("", '\n');
    for (int index=0; index<s.length();index++)
    {
        if (s[index]==' ' || s[index]=='\n' || s[index]=='\0')
        {
            __print(nextWord, s[index]);
            nextWord = "";
        } else {
            nextWord += s[index];
        }
    }
    __print(nextWord, '\0');
}
void clear()
{
    LCD.clear();
    cursor(0, 0);
}
void cursor(int r, int c)
{
    LCD_R = r;
    LCD_C = c;
    LCD.setCursor(c, r);
}







const int BearerStartIndex = 0;
void writeBearer(const String &str)
{
	char len = str.length();
    Bearer = "";
	EEPROM.write(BearerStartIndex, len);
	for (int i = 0; i < len; i++)
	{
		EEPROM.write(BearerStartIndex + 1 + i, str[i]);
        Bearer += str[i];
	}
	EEPROM.commit();
}
void readBearer()
{
	int newStrLen = EEPROM.read(0);
	Bearer = "";
	for (int i = 0; i < newStrLen; i++)
	{
		char next = EEPROM.read(BearerStartIndex + 1 + i);
		Bearer += next;
	}
}







void ensureWiFi()
{
    if (WiFi.status() == WL_CONNECTED) { return; }
    else
    {
        WiFi.begin(ssid, password);
        clear();
        print("Connecting WiFi", false);
        while(WiFi.status() != WL_CONNECTED)
        {
            delay(500);
            print(".", false);
        }
        clear();
        print("Connected", false);
        delay(1000);
    }
}









String sendGET(String address)
{
    /*
    Send a GET request to backend
    */
   while (HIGH)
    {
        ensureWiFi(); // Check WiFi connection before any request is sent
        String payload = "";
        HTTPClient http;
        WiFiClient client;
        http.setReuse(false); // Prevent using same http object for consecutive requests
        http.begin(client, address);
        http.addHeader("Bearer", Bearer);
        int httpResponseCode = http.GET();
        payload = http.getString(); // Fetch the response as a String
        http.end(); // Cleanup the http object
        if (httpResponseCode==200) { return payload; }
    }
}
JsonDocument parseResponse(String response)
{
    JsonDocument res;
    deserializeJson(res, response);
    return res;
}








int waitForButtonPress(int timeout)
{
    int started = millis();
    while (HIGH)
    {
        delay(25);
        if (digitalRead(I1) == LOW)
        {
            while(digitalRead(I1)==LOW) delay(50);
            return 1;
        }
        else if (digitalRead(I2) == LOW)
        {
            while(digitalRead(I2)==LOW) delay(50);
            return 2;
        }
        else if (digitalRead(I3) == LOW)
        {
            while(digitalRead(I3)==LOW) delay(50);
            return 3;
        }
        if (timeout>0 && (millis()-started)>=timeout) break;
    }
  	return -1;
}







struct PostEnsureAuth{ bool handled; JsonDocument response; };





String BoardOTP = "";
void setBoardOTP(String OTP) {BoardOTP = OTP;}
struct PostEnsureAuth ensureAuth(JsonDocument response)
{
    struct PostEnsureAuth r;
    r.handled = false;
    while (HIGH)
    {
        if (response["PURPOSE"] == "AUTH") 
        { 
            handleBearerReceived(response);
            r.handled = true;
        }
        else if (response["PURPOSE"] == "CONN") 
        {
            setBoardOTP(response["OTP"]); 
            handleParentOTP();
            r.handled = true;
        }
        else if (response["PURPOSE"] == "OTP") 
        {
            handleOTPSubmitResponse(response);
            r.handled = true;
        }
        else if (response["PURPOSE"] == "ACCEPT") 
        {
            handleParentAcceptance(response);
            r.handled = true;
        }
        r.response = response;
        return r;
    }
}
void handleBearerReceived(JsonDocument response)
{
    clear();
    print("Registered Board in Server", false);
    writeBearer(response["BEARER"]);
    delay(2000);
}
void handleParentOTP()
{
    clear();
    print("Board OTP:", false);
    print(BoardOTP, true);
    print("NEW Parent OTP:", true);
    String ParentOTP = "";
    while (HIGH)
    {
        int button = waitForButtonPress(5000);
        if (button != -1)
        {
            ParentOTP += button;
            cursor(3,0);
            print(ParentOTP, false);
        }
        else if (ParentOTP.length() != 0) 
        {
            ensureAuth(parseResponse(sendGET("http://bhindi1.ddns.net:61500/submitOTP?OTP="+ParentOTP)));
            return;
        }
        
    }
}
void handleOTPSubmitResponse(JsonDocument OTPResponse)
{
    clear();
    if (OTPResponse["STATUS"] == "WAITING FOR PARENT")
    {
        clear();
        print("Board OTP:", false);
        print(BoardOTP, true);
        print("Restart Board to change Parent OTP", true);
    }
    else if (OTPResponse["STATUS"] == "CONNECTED TO PARENT")
    {
        clear();
        print("Connection Successful!", false);
        delay(2000);
    }
    else if (OTPResponse["STATUS"] == "INVALID OTP")
    {
        clear();
        print("Invalid OTP", false);
        delay(2000);
        handleParentOTP();
    }
}
void handleParentAcceptance(JsonDocument response)
{
    if (response["STATUS"]==false) delay(3000);
}







String parseQuestion(JsonDocument response)
{
    clear();
    String sentAt = response["T"];
    print(response["Q"], false);
    for (int optionIndex=1; optionIndex<response["O"].size()+1; optionIndex++)
    {
        String optionText = response["O"][optionIndex-1];
        String option = "";
        option += "(";
        option += optionIndex;
        option += ")";
        option += optionText;
        print(option, true);
    }
    return sentAt;
}
void parseAnswerResponse(JsonDocument response)
{
    if (response["V"]==true)
    {
        String score = response["S"];
        if (response["C"] == true)
        {
            clear();
            print("Correct", false);
        }
        else
        {
            String correctAnswer = response["O"];
            clear();
            print("Wrong", false);
            print("Answer is: "+correctAnswer, true);
        }
        if (response["D"]==true) 
        {
            print("Enjoy your treat :)", true);
            dropCandy(false);
            delay(500);
            refillCandy(false);
        }
        else 
        {
            print("Score: "+score, true);
            delay(2000);
        }
    }
    else
    {
        clear();
        print("Server didnt know the answer :(", false);
        delay(2000);
    }
}








void setup()
{
	Serial.begin(9600);
	EEPROM.begin(150);
    LCD.init();
    LCD.backlight();
    servoObj.attach(ServoChannel);
    refillCandy(false);
    pinMode(I1, INPUT_PULLUP);
    pinMode(I2, INPUT_PULLUP);
    pinMode(I3, INPUT_PULLUP);
    pinMode(BuzzerChannel, OUTPUT);
	ensureWiFi();
	ensureAuth(parseResponse(sendGET("http://bhindi1.ddns.net:61500/forceParent")));
}








void loop()
{
    struct PostEnsureAuth nq = ensureAuth(parseResponse(sendGET("http://bhindi1.ddns.net:61500/newQuestion")));
    if (!nq.handled)
    {
        if (nq.response["PURPOSE"] == "QUESTION")
        {
            String sentAt = parseQuestion(nq.response);
            int optionSelected = waitForButtonPress(0);
            struct PostEnsureAuth a = ensureAuth(parseResponse(sendGET("http://bhindi1.ddns.net:61500/submitAnswer?T="+sentAt+"&OPTION="+optionSelected)));
            if (!a.handled)
            {
                if (a.response["PURPOSE"] == "SCORE") parseAnswerResponse(a.response);
                else 
                {
                    clear();
                    print("Server didnt send a proper Answer", false);
                    delay(2000);
                }
            }
        }
        else 
        {
            clear();
            print("Server didnt send a proper Question", false);
            delay(2000);
        }
    }
}

