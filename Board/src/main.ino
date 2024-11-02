#define TEST true; // Define TEST to signify code used for test board


#include <EEPROM.h>
#include <LiquidCrystal_I2C.h>
#include <ArduinoJson.h>
#define ARDUINOJSON_ENABLE_STD_STRING 1


#ifdef TEST // If TEST
#include <ESP32Servo.h>
#include <WiFi.h>
#include <HTTPClient.h>
const String ssid = "Wokwi-GUEST";
const String password = "";
const int I1 = 32;
const int I2 = 5;
const int I3 = 0;
const int BuzzerChannel = 27;
const int ServoChannel = 12;
#else // If NOT Test
#include <Servo.h>
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
const String ssid = "Disguised Wi-fi";
const String password = "9991337799";
const int I1 = 14;
const int I2 = 12;
const int I3 = 13;
const int BuzzerChannel = D8;
const int ServoChannel = 0;
#endif




// Servo Motor related variables and functions
Servo servoObj;
const int ServoRefillPos = 35; // Degrees to write to fill new candy
const int ServoDropPos = 0; // Degrees to write to drop the filled candy
int servoCurrentPos = 25; // Initialise the board with a 25 degree value (jerk start) to allow clearing blockages
void refillCandy(bool instant)
{
    // Use this function to align moving port with IN-PORT to allow new candy to fill
    // :param instant: boolean to signify if the motion needs to be done instantly, else will turn in a maximum of 50*35 = 1750ms
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
    // Use this function to align moving port with OUT-PORT to allow filled candy to drop out
    // :param instant: boolean to signify if the motion needs to be done instantly, else will turn in a maximum of 50*35 = 1750ms
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







// LCD-I2C related variables and functions
LiquidCrystal_I2C LCD(0x27, 20, 4);
int LCD_R = 0; // Last known cursor position (R)
int LCD_C = 0; // Last known cursor position (C)
int LCD_R_MAX = 4; // Maximum usable rows
int LCD_C_MAX = 20; // Maximum usable columns
void __print(String nextWord, char c)
{
    // DONT CALL THIS FUNCTION!! Call `print()` instead
    // Private function to print 1 raw word, 
    // :param nextWord: The String word to print
    // :param c: Which character caused the word separation ('\n', '\0', ' ')
    while (LCD_R>=LCD_R_MAX || LCD_C+nextWord.length()>LCD_C_MAX || c=='\n')
    {
        // If word length exceeds the LCD screen horizontally (from current position of cursor), shift to next row
        c = ' ';
        LCD_R += 1;
        LCD_C = 0;
        if (LCD_R>=LCD_R_MAX)
        {
            // If exceeding LCD screen vertically, error out without printing
            Serial.println("WARNING: Exceeding max rows!");
            return;
        }
    }
    cursor(LCD_R, LCD_C); // Place cursor at the exact position
    if (nextWord.length()!=0) nextWord += " "; // If word was not empty, add a space at the end of word
    LCD.print(nextWord); // Print the word on the LCD
    LCD_C += nextWord.length(); // Increment cursor position
}
void print(String s, bool newLine)
{
    // Print String based variables on the LCD with automatic line shifting based on words
    // Makes sure any word isnt split and displayed over 2 lines
    // Only splits on the basis of different words
    // :param s: The string to display
    // :param newLine: boolean to signify if current strign should start on a new line
    if (s[s.length()-1] != '\0' || s[s.length()-1] != ' ' || s[s.length()-1] != '\n') s+=" "; // If string doesnt end with a end character, manually add it
    String nextWord = "";
    if (newLine) __print("", '\n'); // Print an empty line if newLine is positive
    for (int index=0; index<s.length();index++)
    {
        // Keep adding character from the string into a variable nextWord till an end character is received
        if (s[index]==' ' || s[index]=='\n' || s[index]=='\0')
        {
            // Reached an end character, print the formed word
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
    // Clear the screen and bring the cursor back to initial
    LCD.clear();
    cursor(0, 0);
}
void cursor(int r, int c)
{
    // manually set cursor position
    // :param r: Row to set cursor to
    // :param c: Column to set cursor to
    LCD_R = r;
    LCD_C = c;
    LCD.setCursor(c, r);
}








// Bearer related variables and functions
// Bearer is saved as [SIZE_OF_BEARER][BEARER] without the '[' and ']'
String Bearer = ""; // Bearer as in volatile memory
const int BearerStartIndex = 0; // Address bit count in EEPROM to start writing process
void writeBearer(const String &str)
{
    // Write a new Bearer string to EEPROM
    // Write the length of the Bearer, and then the Bearer itself, to make reading easier by signifying the length of the Bearer while reading
    // :param str: String holding the Bearer
	char len = str.length(); // length of the Bearer
    Bearer = ""; // Empty the last known Bearer from volatile memory
	EEPROM.write(BearerStartIndex, len); // Write the length of the Bearer on the first allowed address bit
	for (int i = 0; i < len; i++)
	{
        // Write each letter character by character
		EEPROM.write(BearerStartIndex + 1 + i, str[i]);
        Bearer += str[i];
	}
	EEPROM.commit(); // Commit after writing completes
}
void readBearer()
{
    // Read last saved Bearer string from EEPROM
	int newStrLen = EEPROM.read(0); // Read first address bit which stores the 
	Bearer = ""; // Empty the last known Bearer from volatile memory
	for (int i = 0; i < newStrLen; i++)
	{
        // Read each letter character by character
		char next = EEPROM.read(BearerStartIndex + 1 + i);
		Bearer += next;
	}
}







// WiFi related function
void ensureWiFi()
{
    // Make sure WiFi has the state of CONNECTED, else try to reconnect
    if (WiFi.status() == WL_CONNECTED) { return; }
    else
    {
        // Assign SSID and PASSWORD and start connecting
        WiFi.begin(ssid, password);
        clear();
        print("Connecting to WiFi", false);
        while(WiFi.status() != WL_CONNECTED)
        {
            // Print a dot every 500ms till WiFi connects
            delay(500);
            print(".", false);
        }
        clear();
        print("WiFi Connected", false);
        delay(1000);
    }
}








// HTTP request related variables and functions
String host = "http://bhindi1.ddns.net:61500";
String sendGET(String address)
{
    //Send a GET request to backend
    // :param address: Address of the server to send the request to
    while (HIGH)
    {
        ensureWiFi(); // Check WiFi connection before any request is sent
        String payload = "";
        HTTPClient http;
        WiFiClient client;
        http.setReuse(false); // Prevent using same http object for consecutive requests
        http.begin(client, address);
        http.addHeader("Bearer", Bearer); // Add Bearer according to volatile memory
        int httpResponseCode = http.GET();
        payload = http.getString(); // Fetch the response as a String
        http.end(); // Cleanup the http object
        if (httpResponseCode==200) { return payload; }
    }
}







// JSON related function
JsonDocument parseResponse(String response)
{
    // Used to parse (deserializeJson) a JSON string into a JSON object
    // :param response: The string to parse
    JsonDocument res;
    deserializeJson(res, response);
    return res;
}









// Buttons related variables and function 
int waitForButtonPress(int timeout)
{
    // Wait till user presses one of the 3 input buttons
    // Input is registered only on BUTTON-RELEASE and not BUTTON-PRESS
    // :param timeout: Max time to wait till a NO-INPUT-PROVIDED signal is returned
    int started = millis(); // Time when the function was called
    while (HIGH)
    {
        delay(25); // Check every 25ms for a button state change, increase this value if multiple inputs are (accidentally) being taken for a single press
        if (digitalRead(I1) == LOW)
        {
            while(digitalRead(I1)==LOW) delay(25); // Check every 25ms if the button was released
            return 1; // Return the corresponsing value
        }
        else if (digitalRead(I2) == LOW)
        {
            while(digitalRead(I2)==LOW) delay(25); // Check every 25ms if the button was released
            return 2; // Return the corresponsing value
        }
        else if (digitalRead(I3) == LOW)
        {
            while(digitalRead(I3)==LOW) delay(25); // Check every 25ms if the button was released
            return 3; // Return the corresponsing value
        }
        if (timeout>0 && (millis()-started)>=timeout) break; // If timeout worth time has passed then return the NO-INPUT-PROVIDED signal except when timeout is 0, which means wait eternally
    }
  	return -1; // NO-INPUT-PROVIDED signal
}






// Authentication and Parent Connection related variables and functions 
struct PostEnsureAuth
{ 
    // All responses are passed into this struct to better understand if the response was related to authentication or actual question
    bool handled; // Boolean to signify if the response was already processed (authentication based response)
    JsonDocument response; // The actual JsonDocument 
}; 
String BoardOTP = ""; // Last known BoardOTP received from server
void setBoardOTP(String OTP) {BoardOTP = OTP;} // Function to save a new Bearer to volatile memory
struct PostEnsureAuth ensureAuth(JsonDocument response)
{
    // Check the purpose of the received document and process it if its related to authentication
    // :param response: The JsonDocument received to process
    struct PostEnsureAuth r;
    r.handled = false; // Start with the response as NOT-PROCESSED
    if (response["PURPOSE"] == "AUTH") 
    { 
        // Bearer is received in this type of response
        handleBearerReceived(response);
        r.handled = true;
    }
    else if (response["PURPOSE"] == "CONN") 
    {
        // BoardOTP is received in this type of response
        setBoardOTP(response["OTP"]); 
        handleParentOTP();
        r.handled = true;
    }
    else if (response["PURPOSE"] == "OTP") 
    {
        // OTP Submit Response is received in this type of response
        handleOTPSubmitResponse(response);
        r.handled = true;
    }
    else if (response["PURPOSE"] == "ACCEPT") 
    {
        // Parent Sync Response is received in this type of response
        handleParentAcceptance(response);
        r.handled = true;
    }
    r.response = response;
    return r;
}
void handleBearerReceived(JsonDocument response)
{
    // Save new Bearer
    // :param response: JsonDocument holding new bearer
    clear();
    print("Registered Board in Server", false);
    writeBearer(response["BEARER"]);
    delay(2000);
}
void handleParentOTP()
{
    // Wait for ParentOTP to be entered
    clear();
    print("Board OTP:", false);
    print(BoardOTP, true);
    print("NEW Parent OTP:", true);
    String ParentOTP = "";
    while (HIGH)
    {
        // Wait for 5000ms since the last button press and submit the total OTP that was received so far
        int button = waitForButtonPress(5000); 
        if (button != -1)
        {
            // Button press before 5000ms timeout
            ParentOTP += button; // Add new button pressed to the existing OTP being entered
            cursor(3,0); // Set cursor to 3rd row
            print(ParentOTP, false); // Display the OTP entered so far
        }
        else if (ParentOTP.length() != 0) 
        {
            // 5000ms without a new button press, submit the OTP if its not empty
            ensureAuth(parseResponse(sendGET(host+"/submitOTP?OTP="+ParentOTP)));
            break;
        }
    }
}
void handleOTPSubmitResponse(JsonDocument OTPResponse)
{
    // Check response for ParentOTP
    // :param OTPResponse: JsonDocument holding the response after submitting ParentOTP
    clear();
    if (OTPResponse["STATUS"] == "WAITING FOR PARENT")
    {
        // OTP was correct but parent didnt enter BoardOTP yet
        clear();
        print("Board OTP:", false);
        print(BoardOTP, true);
        print("Restart Board to change Parent OTP", true);
    }
    else if (OTPResponse["STATUS"] == "CONNECTED TO PARENT")
    {
        // OTP was correct and parent had already entered BoardOTP, so connected instantly
        clear();
        print("Connection Successful!", false);
        delay(2000);
    }
    else if (OTPResponse["STATUS"] == "INVALID OTP")
    {
        // OTP was incorrect
        clear();
        print("Invalid OTP", false);
        delay(2000);
        handleParentOTP();
    }
}
void handleParentAcceptance(JsonDocument response)
{
    // Check if parent ACCEPT returned a opsitive status, else delay 3000ms (and check again)
    // :param OTPResponse: JsonDocument holding the response with the ACCEPT status
    if (response["STATUS"]==false) delay(3000);
}












// Question related variables and functions 
String parseQuestion(JsonDocument response)
{
    // Print the question and the options
    // :param response: JsonDocument with the question and options and the question identifier
    clear();
    String sentAt = response["T"]; // Question Instance identifier (used in server)
    print(response["Q"], false); // Question on line 1
    for (int optionIndex=1; optionIndex<response["O"].size()+1; optionIndex++)
    {
        // Decorate each option and display
        String optionText = response["O"][optionIndex-1];
        String option = "";
        option += "(";
        option += optionIndex;
        option += ")";
        option += optionText;
        print(option, true); // New line for every option
    }
    return sentAt;
}
void parseAnswerResponse(JsonDocument response)
{
    // Upon submission of option, parse the response containing score, if the option was correct and if candy si to be dropped
    // :param response: response holding the correct option, if the option was right and the new score
    if (response["V"]==true) // Only continue if the server could properly process the question and the option received
    {
        String score = response["S"]; // New Score for the child (0 if no child is assigned to this board)
        if (response["C"] == true)
        {
            // Option input was right
            clear();
            print("Correct", false);
        }
        else
        {
            // Option input was wrong
            String correctAnswer = response["O"];
            clear();
            print("Wrong", false);
            print("Answer is: "+correctAnswer, true);
        }
        if (response["D"]==true) 
        {
            // Drop a candy
            print("Enjoy your treat :)", true);
            dropCandy(false); // Slowly drop candy (moving part always stays in filled position when idle)
            delay(500); // Wait 500ms for candy to drop
            refillCandy(false); // Slowly send backmoving part to refill position
        }
        else 
        {
            print("Score: "+score, true);
            delay(3000);
        }
    }
    else
    {
        // Error occured in server trying to process the option provided
        clear();
        print("Server didnt know the answer :(", false);
        delay(3000);
    }
}










void setup()
{
    // Board operation starts here
	Serial.begin(9600); // Activate Serial monitor
	EEPROM.begin(150); // Activate EEPROM writing for 150 address bits
    LCD.init(); // Activate LCD
    LCD.backlight();// Turn on LCD backlight
    servoObj.attach(ServoChannel); // Connect Servo on proper pin
    refillCandy(false); // Start with servo at refill position
    pinMode(I1, INPUT_PULLUP);
    pinMode(I2, INPUT_PULLUP);
    pinMode(I3, INPUT_PULLUP);
    pinMode(BuzzerChannel, OUTPUT);
	ensureAuth(parseResponse(sendGET(host+"/forceParent"))); // Dummy check to verify board authentication and parent connection validity
}











void loop()
{
    // Board operation loop
    struct PostEnsureAuth nq = ensureAuth(parseResponse(sendGET(host+"/newQuestion"))); // Get new question 
    if (!nq.handled) // if already handled , ignore (When authentication errors occur mid operation)
    {
        if (nq.response["PURPOSE"] == "QUESTION")
        {
            String sentAt = parseQuestion(nq.response); // Get the Identifier for the question (used by server)
            int optionSelected = waitForButtonPress(0); // Wait infinitely till an option is selected
            struct PostEnsureAuth a = ensureAuth(parseResponse(sendGET(host+"/submitAnswer?T="+sentAt+"&OPTION="+optionSelected))); // Submit the option pressed
            if (!a.handled) // if already handled , ignore (When authentication errors occur mid operation)
            {
                if (a.response["PURPOSE"] == "SCORE") parseAnswerResponse(a.response); // Process the answer response
                else 
                {
                    clear();
                    print("Server didnt send a proper Response", false);
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
