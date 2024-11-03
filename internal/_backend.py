from gevent.monkey import patch_all
patch_all() # Monkey patch everything before anything else (converts sync functions to async functions)

from threading import Thread
from typing import Callable, Any
from json import loads, dumps
from random import shuffle
from time import sleep, time
from werkzeug.security import generate_password_hash, check_password_hash
from gevent.pywsgi import WSGIServer
from functools import wraps
from flask import request
from dynamicWebsite import *
from randomisedString import Generator as STR_GEN
from internal.Enums import *
from internal.Methods import *



def getSenderBoard(parentRequired:bool) -> Callable[[Any], Callable[[], dict[str, str | Any] | dict[str, str | bool] | dict[str, str] | Any]]:
    """
    Decorator to fetch BoardID of the request sender, incase the board isn't authenticated,
    create a new board in server and send them a new Bearer for their future requests
    :param parentRequired: Boolean to signify if the board needs to be assigned to a parent for the later function to be executed
    :return:
    """
    def decorator(continueFunction):
        @wraps(continueFunction)
        def wrapper():
            bearer = request.headers.get("Bearer", "") # Check bearer in the Header
            boardID = None if not bearer else readBoardBearer(bearer) # Fetch known BoardID from Bearer
            if boardID:
                if parentRequired:
                    received = SQLConn.execute(f"SELECT ParentID from boards where BoardID=\"{boardID}\"")
                    if received and received[0]["ParentID"]: return continueFunction(boardID) # Continue later function
                    if not SQLConn.execute(f"SELECT BoardID from pending_connections where BoardID=\"{boardID}\""):
                        OTP = generateBoardOTP(boardID)
                        print({"PURPOSE": "CONN", "OTP": OTP})
                        return {"PURPOSE": "CONN", "OTP": OTP} # Send new OTP, if not already made
                    print( {"PURPOSE":"ACCEPT", "STATUS":False})
                    return {"PURPOSE":"ACCEPT", "STATUS":False} # Send Connection-Not-Accepted-By-Parent response, if OTP is present yet parent didn't accept yet
                else: return continueFunction(boardID) # Continue later function
            else:
                bearer = createNewBoard()
                print({"PURPOSE": "AUTH", "BEARER": bearer})
                return {"PURPOSE": "AUTH", "BEARER": bearer} # Bearer unavailable or invalid
        return wrapper
    return decorator



class UserClass:
    def __init__(self):
        self._dummyViewer = {"USERNAME": "", "VIEWERS": []}

        self.activeParentIDs = {"ParentID1": self._dummyViewer}
        self.viewerIDToParentID = {}
        self.usernameToParentID = {}

        self.ByParentID = "UID"
        self.ByViewerID = "VID"
        self.ByUserName = "UN"

    def getParentUserName(self, By, value: str) -> None|str:
        """
        Fetch Parent's username from any other parameter
        :param By: type of parameter
        :param value: value of parameter
        :return:
        """
        if not value: return
        if By == self.ByParentID: # Parameter is parentID
            received = SQLConn.execute(f"SELECT UserName from parent_auth where ParentID=\"{value}\" limit 1")
            if received:
                received = received[0]
                return received.get("UserName")
        elif By == self.ByViewerID: # Parameter is viewerID
            received = SQLConn.execute(f"SELECT ParentID from parent_sessions where ViewerID=\"{value}\" limit 1")
            if received:
                received = received[0]
                return self.getParentUserName(self.ByParentID, received.get("ParentID").decode())

    def getParentID(self, By, value) -> None|str:
        """
        Fetch Parent's ParentID from any other parameter
        :param By: type of parameter
        :param value: value of parameter
        :return:
        """
        if not value: return
        if By == self.ByUserName: # Parameter is Username
            received = SQLConn.execute(f"SELECT ParentID from parent_auth where UserName=\"{value}\" limit 1")
            if received:
                received = received[0]
                return received.get("ParentID").decode()
        elif By == self.ByViewerID: # Parameter is ViewerID
            received = SQLConn.execute(f"SELECT ParentID from parent_sessions where ViewerID=\"{value}\" limit 1")
            if received:
                received = received[0]
                return received.get("ParentID").decode()

    def parentLoginCall(self, viewer: BaseViewer, ParentID):
        username = self.getParentUserName(self.ByParentID, ParentID)
        if ParentID not in self.activeParentIDs:
            self.activeParentIDs[ParentID] = self._dummyViewer
            self.activeParentIDs[ParentID]["USERNAME"] = username
        self.viewerIDToParentID[viewer.viewerID] = ParentID
        self.usernameToParentID[username] = ParentID
        if viewer not in self.activeParentIDs[ParentID]["VIEWERS"]: self.activeParentIDs[ParentID]["VIEWERS"].append(viewer)
        received = SQLConn.execute(f"SELECT ParentID, RemoteAddr, UserAgent, HostURL from parent_sessions where ViewerID=\"{viewer.viewerID}\"")
        addEntry = False
        if received:
            received = received[0]
            if received["ParentID"].decode() != ParentID or received["RemoteAddr"] != viewer.cookie.remoteAddress or received["UserAgent"] != viewer.cookie.UA or received["HostURL"] != viewer.cookie.hostURL:
                SQLConn.execute(f"DELETE from parent_sessions WHERE ViewerID=\"{viewer.viewerID}\"")
                addEntry = True
        else:
            addEntry = True
        if addEntry:
            SQLConn.execute(f"INSERT INTO parent_sessions values (\"{viewer.viewerID}\", \"{ParentID}\", \"{viewer.cookie.remoteAddress}\", \"{viewer.cookie.UA}\", \"{viewer.cookie.hostURL}\")")

    def parentLogoutCall(self, viewer: BaseViewer, logout: bool = False):
        ParentID = self.getParentID(self.ByViewerID, viewer.viewerID)
        username = self.getParentUserName(self.ByViewerID, viewer.viewerID)
        if ParentID is not None and ParentID in self.activeParentIDs and viewer in self.activeParentIDs[ParentID]["VIEWERS"]:
            self.activeParentIDs[ParentID]["VIEWERS"].remove(viewer)
            if len(self.activeParentIDs[ParentID]["VIEWERS"]) == 0: del self.activeParentIDs[ParentID]
        if viewer.viewerID in self.viewerIDToParentID: del self.viewerIDToParentID[viewer.viewerID]
        if username in self.usernameToParentID: del self.usernameToParentID[username]
        if logout: SQLConn.execute(f"DELETE from parent_sessions WHERE ViewerID=\"{viewer.viewerID}\"")
        SQLConn.execute(f"UPDATE parents set ParentOTP=\"\" where ParentID=\"{ParentID}\"")


def getKnownLoggedInParentID(viewer: BaseViewer):
    remoteAddr = viewer.cookie.remoteAddress
    userAgent = viewer.cookie.UA
    hostURL = viewer.cookie.hostURL
    received = SQLConn.execute(f"SELECT ParentID, RemoteAddr, UserAgent, HostURL from parent_sessions where ViewerID=\"{viewer.viewerID}\"")
    if received:
        received = received[0]
        if remoteAddr == received["RemoteAddr"] and userAgent == received["UserAgent"] and hostURL == received["HostURL"]:
            return received["ParentID"].decode()


def readBoardBearer(bearer: str):
    received = SQLConn.execute(f"SELECT BoardID from boards WHERE Bearer=\"{bearer}\"")
    if received:
        return received[0]["BoardID"].decode()


def generateBoardOTP(boardID:str):
    SQLConn.execute(f"DELETE from pending_connections where BoardID=\"{boardID}\"")
    OTP = ""
    while True:
        if len(OTP) > 9:
            sleep(1)
            OTP = stringGen.AlphaNumeric(5, 5)
            continue
        if not OTP or len(OTP) < 5 or SQLConn.execute(f"SELECT BoardID from boards where BoardOTP=\"{OTP}\""):
            OTP += stringGen.AlphaNumeric(1, 1).upper()
        else:
            SQLConn.execute(f"UPDATE boards set BoardOTP=\"{OTP}\" where BoardID=\"{boardID}\"")
            return OTP


def generateParentOTP(parentID:str):
    SQLConn.execute(f"DELETE from pending_connections where ParentID=\"{parentID}\"")
    OTP = ""
    while True:
        if OTP and len(OTP) > 9:
            sleep(1)
            OTP = ""
            continue
        if not OTP or len(OTP) < 5 or SQLConn.execute(f"SELECT ParentID from parents where ParentOTP=\"{OTP}\""):
            OTP += str(int(stringGen.OnlyNumeric(1, 1)) % 3 + 1)
        else:
            SQLConn.execute(f"UPDATE parents set ParentOTP=\"{OTP}\" where ParentID=\"{parentID}\"")
            break
    return OTP



def createNewChild(viewerObj: BaseViewer, form:dict):
    parentID = getKnownLoggedInParentID(viewerObj)
    childName = form.get("name", "")
    while True:
        childID = stringGen.AlphaNumeric(50, 50)
        if not SQLConn.execute(f"SELECT ChildID from children where ChildID=\"{childID}\" limit 1"):
            SQLConn.execute(f"INSERT INTO children values (\"{childID}\", \"{parentID}\", \"\", \"{childName}\", 0, 0, now())")
            sendIdleChildren(viewerObj)
            return childID


def deleteOldChild(viewerObj: BaseViewer, childID:str):
    parentID = getKnownLoggedInParentID(viewerObj)
    received = SQLConn.execute(f"SELECT BoardID from children where ChildID=\"{childID}\"")
    if received:
        received = received[0]
        if received["BoardID"]: return print("Child not idle")
    SQLConn.execute(f"DELETE from children where ChildID=\"{childID}\" and ParentID=\"{parentID}\"")
    SQLConn.execute(f"DELETE from questionhistory where ChildID=\"{childID}\"")
    sendIdleChildren(viewerObj)


def createNewBoard():
    while True:
        boardID = stringGen.AlphaNumeric(50, 50)
        if not SQLConn.execute(f"SELECT BoardID from boards where BoardID=\"{boardID}\""):
            while True:
                bearer = stringGen.AlphaNumeric(50, 50) + boardID
                if not SQLConn.execute(f"SELECT BoardID from boards where Bearer=\"{bearer}\""):
                    SQLConn.execute(f"INSERT INTO boards values (\"{boardID}\", \"\", \"\", \"\", \"{bearer}\", \"\", now())")
                    return bearer


def establishConnection(boardID, boardName, parentID):
    SQLConn.execute(f"DELETE FROM pending_connections where BoardID=\"{boardID}\"")
    SQLConn.execute(f"UPDATE boards set ParentID=\"{parentID}\", Name=\"{boardName}\" where BoardID=\"{boardID}\"")
    for viewerObj in liveCacheManager.activeParentIDs.get(parentID, {"VIEWERS":[]}).get("VIEWERS"):
        sendAssignmentForm(viewerObj)
        sendPendingBoardVerifications(viewerObj)
        sendIdleBoards(viewerObj)


def initiateAssignment(viewerObj:BaseViewer, form:dict):
    boardID = form.get("board", "")
    childID = form.get("child", "")
    parentID = getKnownLoggedInParentID(viewerObj)
    if boardID and childID:
        print(f"UPDATE children set BoardID=\"{boardID}\" where BoardID=\"\" and ChildID=\"{childID}\" and ParentID=\"{parentID}\"")
        SQLConn.execute(f"UPDATE boards set ChildID=\"{childID}\" where ChildID=\"\" and BoardID=\"{boardID}\" and ParentID=\"{parentID}\"")
        SQLConn.execute(f"UPDATE children set BoardID=\"{boardID}\" where BoardID=\"\" and ChildID=\"{childID}\" and ParentID=\"{parentID}\"")



def initiateOwnershipParent(viewerObj: BaseViewer, form:dict):
    parentID = getKnownLoggedInParentID(viewerObj)
    boardName = form.get("name", "")
    boardOTP = form.get("otp", "").upper()
    if not boardOTP: print("Invalid board OTP")
    boardExists = SQLConn.execute(f"SELECT BoardID, ParentID from boards where BoardOTP=\"{boardOTP}\" limit 1")
    if boardExists:
        received = boardExists[0]
        boardID = received["BoardID"].decode()
        if received["ParentID"]:
            print("Board has an active parent")
        else:
            parentOTP = SQLConn.execute(f"SELECT ParentOTP from parents where ParentID=\"{parentID}\"")
            if parentOTP: parentOTP = parentOTP[0]["ParentOTP"].decode()
            else: return print("Parent has no OTP")
            hasPendingConnection =  SQLConn.execute(f"SELECT BoardID from pending_connections where ParentID=\"{parentID}\" and BoardID=\"{boardID}\" and ParentOTP=\"{parentOTP}\" and timestampdiff(MINUTE, Created, now()) < 60 limit 1")
            if hasPendingConnection:
                establishConnection(boardID, boardName, parentID)
                return 1
            else:
                SQLConn.execute(f"INSERT INTO pending_connections VALUES (\"{parentID}\", \"{boardID}\", \"{boardName}\", now(), \"\", \"{boardOTP}\")")
                return 0
    else:
        print("Invalid board OTP")
    return -1


def initiateOwnershipBoard(boardID:str, parentOTP:str):
    if not parentOTP: print("Invalid parent OTP")
    parentExists = SQLConn.execute(f"SELECT ParentID from parents where ParentOTP=\"{parentOTP}\" limit 1")
    if parentExists:
        received = parentExists[0]
        parentID = received["ParentID"].decode()
        boardOTP = SQLConn.execute(f"SELECT BoardOTP from boards where BoardID=\"{boardID}\"")[0]["BoardOTP"].decode()
        if not boardOTP: boardOTP = generateBoardOTP(boardID)
        hasPendingConnection = SQLConn.execute(f"SELECT BoardName from pending_connections where ParentID=\"{parentID}\" and BoardID=\"{boardID}\" and BoardOTP=\"{boardOTP}\" and timestampdiff(MINUTE, Created, now()) < 60 limit 1")
        if hasPendingConnection:
            establishConnection(boardID, hasPendingConnection[0]["BoardName"], parentID)
            return 1
        else:
            SQLConn.execute(f"INSERT INTO pending_connections VALUES (\"{parentID}\", \"{boardID}\", \"\", now(), \"{parentOTP}\", \"\")")
            return 0
    else:
        print("Invalid Parent OTP")
    return -1


def deleteOwnedBoard(viewerObj: BaseViewer, boardID:str):
    parentID = getKnownLoggedInParentID(viewerObj)
    received = SQLConn.execute(f"SELECT ChildID from boards where BoardID=\"{boardID}\"")
    if received:
        received = received[0]
        if received["ChildID"]: return print("Board is not idle")
    SQLConn.execute(f"DELETE from boards where BoardID=\"{boardID}\" and ParentID=\"{parentID}\"")
    SQLConn.execute(f"DELETE from pending_connections where BoardID=\"{boardID}\"")
    sendIdleChildren(viewerObj)


def deleteAssignment(viewerObj:BaseViewer, boardID:str, childID:str):
    parentID = getKnownLoggedInParentID(viewerObj)
    SQLConn.execute(f"UPDATE boards set ChildID=\"\" where BoardID=\"{boardID}\" and parentID=\"{parentID}\"")
    SQLConn.execute(f"UPDATE children set BoardID=\"\" where ChildID=\"{childID}\" and parentID=\"{parentID}\"")


def addNewQuestion(viewerObj:BaseViewer, form:dict):
    subject = form.get("subject", "").strip()
    questionText = form.get("question", "").strip()
    correct = form.get("correct", "").strip()
    incorrect1 = form.get("incorrect1", "").strip()
    incorrect2 = form.get("incorrect2", "").strip()
    incorrect3 = form.get("incorrect3", "").strip()
    incorrect4 = form.get("incorrect4", "").strip()
    incorrect5 = form.get("incorrect5", "").strip()
    incorrect = [incorrect1, incorrect2, incorrect3, incorrect4, incorrect5]
    if subject not in ["Maths", "English", "Science", "GK"]: return viewerObj.queueTurboAction("INVALID Subject", "newQuestionError", viewerObj.turboApp.methods.update)
    elif not questionText: return viewerObj.queueTurboAction("INVALID Question", "newQuestionError", viewerObj.turboApp.methods.update)
    elif not 0<len(questionText)<20: return viewerObj.queueTurboAction("Question too long (max 19 characters)", "newQuestionError", viewerObj.turboApp.methods.update)
    elif not correct: return viewerObj.queueTurboAction("INVALID Correct Option", "newQuestionError", viewerObj.turboApp.methods.update)
    elif correct in incorrect: return viewerObj.queueTurboAction("Correct Option same as incorrect", "newQuestionError", viewerObj.turboApp.methods.update)
    for incorrectOption in incorrect:
        if not incorrectOption: return viewerObj.queueTurboAction("INVALID Wrong Option", "newQuestionError", viewerObj.turboApp.methods.update)
    while True:
        questionID = stringGen.AlphaNumeric(50, 50)
        if not SQLConn.execute(f"SELECT QuestionID from questionbank where QuestionID=\"{questionID}\""):
            SQLConn.execute(f"INSERT into questionbank VALUES (\"{questionID}\", \"{subject}\", \"{questionText}\", \"{correct}\", '{dumps(incorrect)}')")
            return viewerObj.queueTurboAction("Question Added", "newQuestionError", viewerObj.turboApp.methods.update)




##############################################################################################################################
##############################################################################################################################



def acceptBoardAnswer(BoardID:str|None):
    sentAt = request.args.get("T")
    option = int(request.args.get("OPTION")) if request.args.get("OPTION", "").isdigit() else None
    received = SQLConn.execute(f"SELECT Options, CorrectOption, OptionSelected from questionhistory where SentAt=\"{sentAt}\" and BoardID=\"{BoardID}\"")
    if received:
        received = received[0]
        options = loads(received["Options"])
        correctOption = received["CorrectOption"]
        optionsSelected = received["OptionSelected"]
        if optionsSelected == 0:
            SQLConn.execute(f"UPDATE questionhistory SET OptionSelected={option} WHERE BoardID=\"{BoardID}\" and SentAt=\"{sentAt}\"")
        isCorrect = option == correctOption
        received = SQLConn.execute(f"SELECT ChildID, Points, CandiesReceived from children where BoardID=\"{BoardID}\"")
        points = 0
        dropCandy = False
        if received:
            received = received[0]
            childID = received["ChildID"].decode()
            points = received["Points"]
            candiesReceived = received["CandiesReceived"]
            if isCorrect:
                points += 10
                if points >= 30:
                    points = 0
                    dropCandy = True
                    candiesReceived += 1
                SQLConn.execute(f"UPDATE children set Points={points}, CandiesReceived={candiesReceived} where ChildID=\"{childID}\"")
        response = {"PURPOSE": "SCORE", "V": True, "C": isCorrect, "O": options[correctOption - 1], "S": str(points), "D": dropCandy}
        print(response)
        return response
    else:
        return {"PURPOSE": "SCORE", "V": False}


def sendBoardNewQuestion(BoardID:None|str):
    subject = request.args.get("subject", "")
    optionCount = int(request.args.get("optionCount")) if request.args.get("optionCount", "").isdigit() else 3
    if not subject:
        received = SQLConn.execute("SELECT QuestionID, Question, CorrectAnswer, WrongAnswers from questionbank limit 1")
    else:
        received = SQLConn.execute(f"SELECT QuestionID, Question, CorrectAnswer, WrongAnswers from questionbank where Subject=\"{subject}\" limit 1")
    if received:
        received = received[0]
        questionID = received["QuestionID"].decode()
        questionText = received["Question"]
        answerText = received["CorrectAnswer"]
        incorrectOptions = loads(received["WrongAnswers"])
        shuffle(incorrectOptions)
        optionsToProvide = []
        for _ in range(min(optionCount - 1, len(incorrectOptions))): optionsToProvide.append(incorrectOptions.pop())
        optionsToProvide.append(answerText)
        shuffle(optionsToProvide)
        correctOption = optionsToProvide.index(answerText) + 1
        received = SQLConn.execute(f"SELECT ChildID from boards where BoardID=\"{BoardID}\"")
        if received:
            received = received[0]
            childID = received["ChildID"].decode()
        else:
            childID = ""
        sentAt = str(time())
        SQLConn.execute(f"INSERT INTO questionhistory values (\"{BoardID}\", \"{childID}\", \"{questionID}\", \"{sentAt}\", '{dumps(optionsToProvide)}', {correctOption}, 0)")
        response = {"PURPOSE": "QUESTION", "T": sentAt, "Q": questionText, "O": optionsToProvide}
        print(response)
        return response


def acceptBoardOTP(BoardID:None|str):
    OTP = request.args.get("OTP", "")
    status = initiateOwnershipBoard(BoardID, OTP)
    if status == -1:
        return {"PURPOSE": "OTP", "STATUS": "INVALID OTP"}
    elif status == 0:
        return {"PURPOSE": "OTP", "STATUS": "WAITING FOR PARENT"}
    elif status == 1:
        return {"PURPOSE": "OTP", "STATUS": "CONNECTED TO PARENT"}








def webViewerJoined(viewerObj: BaseViewer):
    print(f"Viewer Joined: {viewerObj.viewerID}")
    parentID = getKnownLoggedInParentID(viewerObj)
    if parentID:
        liveCacheManager.parentLoginCall(viewerObj, parentID)
        Thread(target=renderHomePage, args=(viewerObj,)).start()
    else:
        Thread(target=renderAuthPage, args=(viewerObj,)).start()


def webFormSubmit(viewerObj: BaseViewer, form: dict):
    print(f"{viewerObj.viewerID}: {form}")
    if "PURPOSE" not in form: return
    purpose = form.pop("PURPOSE")
    if purpose == "LOGIN":
        loginOldParent(viewerObj, form)
    elif purpose == "REGISTER":
        registerNewParent(viewerObj, form)
    elif purpose == "LOGOUT":
        liveCacheManager.parentLogoutCall(viewerObj, True)
        Thread(target=renderAuthPage, args=(viewerObj,)).start()
    elif purpose == "NEW_BOARD":
        sendNewBoardForm(viewerObj)
        if initiateOwnershipParent(viewerObj, form) != -1:
            sendPendingBoardVerifications(viewerObj)
            sendAssignmentForm(viewerObj)
    elif purpose == "NEW_CHILD":
        sendNewChildForm(viewerObj)
        createNewChild(viewerObj, form)
        sendAssignmentForm(viewerObj)
    elif "REMOVE_BOARD" in purpose:
        deleteOwnedBoard(viewerObj, purpose.replace("REMOVE_BOARD_", ""))
        sendAssignmentForm(viewerObj)
    elif "REMOVE_CHILD" in purpose:
        deleteOldChild(viewerObj, purpose.replace("REMOVE_CHILD_", ""))
        sendAssignmentForm(viewerObj)
    elif purpose == "NEW_ASSIGNMENT":
        initiateAssignment(viewerObj, form)
        sendAssignmentForm(viewerObj)
        sendAssigned(viewerObj)
    elif "REMOVE_ASSIGNMENT" in purpose:
        deleteAssignment(viewerObj, purpose.replace("REMOVE_ASSIGNMENT_", "").split("_")[0], purpose.replace("REMOVE_ASSIGNMENT_", "").split("_")[1])
        sendAssigned(viewerObj)
    elif purpose == "ADD_QUESTION":
        sendNewQuestionForm(viewerObj)
        addNewQuestion(viewerObj, form)


def webViewerLeft(viewerObj: BaseViewer):
    print(f"Viewer Left: {viewerObj.viewerID}")
    liveCacheManager.parentLogoutCall(viewerObj)



def registerNewParent(viewerObj:BaseViewer, form:dict):
    username = form.get("username", "")
    person = form.get("person", "")
    password = form.get("password", "")
    confirm_password = form.get("confirm", "")
    if not username:
        viewerObj.queueTurboAction("Invalid Username", "authWarning", viewerObj.turboApp.methods.update.value)
        sendRegisterForm(viewerObj)
    elif SQLConn.execute(f"SELECT UserName from parent_auth where UserName=\"{username}\" limit 1"):
        viewerObj.queueTurboAction("Username Taken", "authWarning", viewerObj.turboApp.methods.update.value)
        sendRegisterForm(viewerObj)
    elif not person:
        viewerObj.queueTurboAction("Name not valid", "authWarning", viewerObj.turboApp.methods.update.value)
        sendRegisterForm(viewerObj)
    elif password == "" or len(password)<8:
        viewerObj.queueTurboAction("Passwords Not Valid", "authWarning", viewerObj.turboApp.methods.update.value)
        sendRegisterForm(viewerObj)
    elif password!=confirm_password:
        viewerObj.queueTurboAction("Passwords Dont match", "authWarning", viewerObj.turboApp.methods.update.value)
        sendRegisterForm(viewerObj)
    else:
        while True:
            parentID = stringGen.AlphaNumeric(50, 50)
            if not SQLConn.execute(f"SELECT UserName from parent_auth where parentID=\"{parentID}\" limit 1"):
                SQLConn.execute(f"INSERT INTO parents values (\"{parentID}\", \"{person}\", now(), \"\")")
                SQLConn.execute(f"INSERT INTO parent_auth values (\"{parentID}\", \"{username}\", \"{generate_password_hash(password)}\")")
                liveCacheManager.parentLoginCall(viewerObj, parentID)
                Thread(target=renderHomePage, args=(viewerObj,)).start()
                break

def loginOldParent(viewerObj:BaseViewer, form:dict):
    username = form.get("username", "")
    password = form.get("password", "")
    received = SQLConn.execute(f"SELECT ParentID, PWHash from parent_auth where UserName=\"{username}\" limit 1")
    if not received:
        viewerObj.queueTurboAction("Username Dont Match", "authWarning", viewerObj.turboApp.methods.update.value)
        Thread(target=sendLoginForm, args=(viewerObj,)).start()
    else:
        received = received[0]
        if not check_password_hash(received["PWHash"].decode(), password):
            viewerObj.queueTurboAction("Password Dont Match", "authWarning", viewerObj.turboApp.methods.update.value)
            Thread(target=sendLoginForm, args=(viewerObj,)).start()
        else:
            liveCacheManager.parentLoginCall(viewerObj, received["ParentID"].decode())
            Thread(target=renderHomePage, args=(viewerObj,)).start()




def renderHomePage(viewerObj:BaseViewer):
    homepageHTML = \
f"""
<h1><br>Welcome to SmartCandyDispenser</h1>
<div id="parentInfo"></div>
<h2><br>Assigned Boards</h2>
<div id="assigned"></div>
<h2><br>Assign Board to a Child</h2>
<div id="newAssignment"></div>
<br>Add new Child:
<div id="newChild"></div>
<br>Add new Board:
<div id="newBoard"></div>
<br>Pending Boards Verification:
<div id="pendingBoardVerification"></div>
<h2>Idle Children</h2>
<div id="idleChildren"></div>
<h2>Idle Boards</h2>
<div id="idleBoards"></div>
<br>Add new Question:
<div id="newQuestion"></div>
<div id="newQuestionError"></div>
<div id="script_create"></div>
"""
    viewerObj.queueTurboAction(homepageHTML, "mainDiv", viewerObj.turboApp.methods.update)
    Thread(target=sendParentInfo, args=(viewerObj,)).start()
    Thread(target=sendAssigned, args=(viewerObj,)).start()
    Thread(target=sendAssignmentForm, args=(viewerObj,)).start()
    Thread(target=sendNewChildForm, args=(viewerObj,)).start()
    Thread(target=sendNewBoardForm, args=(viewerObj,)).start()
    Thread(target=sendPendingBoardVerifications, args=(viewerObj,)).start()
    Thread(target=sendIdleChildren, args=(viewerObj,)).start()
    Thread(target=sendIdleBoards, args=(viewerObj,)).start()
    Thread(target=sendNewQuestionForm, args=(viewerObj,)).start()



def renderAuthPage(viewerObj:BaseViewer):
    authPage = \
f"""
<div id="loginForm"></div>
<div id="registerForm"></div>
<div id="authWarning"></div>
"""
    viewerObj.queueTurboAction(authPage, "mainDiv", viewerObj.turboApp.methods.update)
    Thread(target=sendRegisterForm, args=(viewerObj,)).start()
    Thread(target=sendLoginForm, args=(viewerObj,)).start()


def sendParentInfo(viewerObj:BaseViewer):
    parentID = liveCacheManager.getParentID(liveCacheManager.ByViewerID, viewerObj.viewerID)
    parentOTP = generateParentOTP(parentID)
    received = SQLConn.execute(f"SELECT ParentName from parents where ParentID=\"{parentID}\"")
    if received: parentName = received[0]["ParentName"]
    else: parentName = "Nameless Parent"
    parentInfoHTML = \
f"""
<form onsubmit="return submit_ws(this)">
{viewerObj.addCSRF("LOGOUT")}
<button type="submit" class="logout-button">Logout</button>
</form>
<p>Welcome {parentName}<br>Your OTP is: {parentOTP}</p>
"""
    viewerObj.queueTurboAction(parentInfoHTML, "parentInfo", viewerObj.turboApp.methods.update)


def sendAssigned(viewerObj:BaseViewer):
    parentID = liveCacheManager.getParentID(liveCacheManager.ByViewerID, viewerObj.viewerID)

    assignedTableHTML = \
"""
<table>
    <thead>
        <tr>
            <th>Board Name</th>
            <th>Child Name</th>
            <th>Score</th>
            <th>Child Stats</th>
            <th>Action</th>
        </tr>
    </thead>
<tbody>
"""
    for board in SQLConn.execute(f"SELECT ChildID, BoardID, Name from boards where parentID=\"{parentID}\""):
        childID = board['ChildID'].decode()
        boardID = board['BoardID'].decode()
        if childID:
            child = SQLConn.execute(f"SELECT Name, Points from children where ChildID=\"{childID}\" and ParentID=\"{parentID}\"")
            if child:
                child = child[0]
                childName = child['Name']
                childPoints = child['Points']
                assignedTableHTML += \
f"""
    <tr>
        <td>{board['Name']}</td>
        <td>{childName}</td>
        <td><div id="{childID}_points">{childPoints}</td>
        <td><form onsubmit="return submit_ws(this)"><button type="submit">VIEW STATS</button>{viewerObj.addCSRF(f"STATS_{childID}")}</form></td>
        <td><form onsubmit="return submit_ws(this)"><button type="submit">SEPARATE</button>{viewerObj.addCSRF(f"REMOVE_ASSIGNMENT_{boardID}_{childID}")}</form></td>
      </form>
    </tr>
"""
    assignedTableHTML += "</tbody></table>"
    viewerObj.queueTurboAction(assignedTableHTML, "assigned", viewerObj.turboApp.methods.update)


def sendAssignmentForm(viewerObj:BaseViewer):
    parentID = liveCacheManager.getParentID(liveCacheManager.ByViewerID, viewerObj.viewerID)
    idleBoards = []
    idleChildren = []
    for board in SQLConn.execute(f'SELECT BoardID, Name from boards where ParentID=\"{parentID}\" and ChildID=\"\"'): idleBoards.append([board["BoardID"].decode(), board["Name"]])
    for child in SQLConn.execute(f'SELECT ChildID, Name from children where ParentID=\"{parentID}\" and BoardID=\"\"'): idleChildren.append([child["ChildID"].decode(), child["Name"]])
    newAssignmentHTML = \
f"""
<form onsubmit="return submit_ws(this)">
    {viewerObj.addCSRF("NEW_ASSIGNMENT")}
    <label for="board">Choose a board:</label>
    <select name="board">
"""
    for board in idleBoards: newAssignmentHTML+= f"<option value=\"{board[0]}\">{board[1]}</option>"
    newAssignmentHTML += "</select>"

    newAssignmentHTML += \
f"""
    <label for="board">Choose a child:</label>
    <select name="child">
"""
    for child in idleChildren: newAssignmentHTML += f"<option value=\"{child[0]}\">{child[1]}</option>"
    newAssignmentHTML += "</select> <input type='submit' Value='Assign'> </form>"
    viewerObj.queueTurboAction(newAssignmentHTML, "newAssignment", viewerObj.turboApp.methods.update)


def sendPendingBoardVerifications(viewerObj:BaseViewer):
    viewerObj.queueTurboAction("<div id='pendingBoardVerification_create'></div>", "pendingBoardVerification", viewerObj.turboApp.methods.update, forceFlush=True)
    parentID = liveCacheManager.getParentID(liveCacheManager.ByViewerID, viewerObj.viewerID)
    for pendingConnection in SQLConn.execute(f"SELECT BoardID, BoardName from pending_connections where ParentID=\"{parentID}\""):
        viewerObj.queueTurboAction(f"{pendingConnection['BoardName']}", "pendingBoardVerification", viewerObj.turboApp.methods.newDiv)


def sendIdleChildren(viewerObj:BaseViewer):
    viewerObj.queueTurboAction(f"<div id='idleChildrenItem_create'></div>", "idleChildren", viewerObj.turboApp.methods.update, forceFlush=True)
    parentID = liveCacheManager.getParentID(liveCacheManager.ByViewerID, viewerObj.viewerID)
    for child in SQLConn.execute(f"SELECT ChildID, Name from children where ParentID=\"{parentID}\" and BoardID=\"\""):
        childElement = \
f"""
<form onsubmit="return submit_ws(this)">
{child['Name']}
{viewerObj.addCSRF(f"REMOVE_CHILD_{child['ChildID'].decode()}")}
<input type="submit" value="Remove"/>
</form>
"""
        viewerObj.queueTurboAction(childElement, "idleChildrenItem", viewerObj.turboApp.methods.newDiv)


def sendIdleBoards(viewerObj:BaseViewer):
    viewerObj.queueTurboAction("<div id='idleBoardItem_create'></div>", "idleBoards", viewerObj.turboApp.methods.update, forceFlush=True)
    parentID = liveCacheManager.getParentID(liveCacheManager.ByViewerID, viewerObj.viewerID)
    for board in SQLConn.execute(f"SELECT BoardID, Name from boards where ParentID=\"{parentID}\" and ChildID=\"\""):
        boardElement = \
            f"""
        <form onsubmit="return submit_ws(this)">
        {board['Name']}
        {viewerObj.addCSRF(f"REMOVE_BOARD_{board['BoardID'].decode()}")}
        <input type="submit" value="Remove"/>
        </form>
        """
        viewerObj.queueTurboAction(boardElement, "idleBoardItem", viewerObj.turboApp.methods.newDiv)


def sendNewBoardForm(viewerObj:BaseViewer):
    newBoardHTML = \
f"""
<form onsubmit="return submit_ws(this)">
{viewerObj.addCSRF("NEW_BOARD")}
<input type="text" name="name" placeholder="Board Name"><br>
<input type="text" name="otp" placeholder="Board OTP"><br>
<button type="submit">Add Board</button>
</form>
"""
    viewerObj.queueTurboAction(newBoardHTML, "newBoard", viewerObj.turboApp.methods.update)


def sendNewChildForm(viewerObj:BaseViewer):
    newChildHTML = \
f"""
<form onsubmit="return submit_ws(this)">
{viewerObj.addCSRF("NEW_CHILD")}
<input type="text" name="name" placeholder="Child Name"><br>
<button type="submit">Add Child</button>
</form>
"""
    viewerObj.queueTurboAction(newChildHTML, "newChild", viewerObj.turboApp.methods.update)



def sendNewQuestionForm(viewerObj:BaseViewer):
    questionHTML = \
        f"""
    <form onsubmit="return submit_ws(this)">
    {viewerObj.addCSRF("ADD_QUESTION")}
    <select name="subject">
        <option value="Maths">Maths</option>
        <option value="English">English</option>
        <option value="Science">Science</option>
        <option value="GK">GK</option>
    </select><br>
    <input type="text" name="question" placeholder="Type Question here" required><br>
    <input type="text" name="correct" placeholder="Correct Answer here" required><br>
    <input type="text" name="incorrect1" placeholder="Incorrect Option" required><br>
    <input type="text" name="incorrect2" placeholder="Incorrect Option" required><br>
    <input type="text" name="incorrect3" placeholder="Incorrect Option" required><br>
    <input type="text" name="incorrect4" placeholder="Incorrect Option" required><br>
    <input type="text" name="incorrect5" placeholder="Incorrect Option" required><br>
    <button type="submit">Upload</button>
    </form>
    """
    viewerObj.queueTurboAction(questionHTML, "newQuestion", viewerObj.turboApp.methods.update)


def sendLoginForm(viewerObj:BaseViewer):
    loginHTML = \
f"""
<form onsubmit="return submit_ws(this)">
{viewerObj.addCSRF("LOGIN")}
<input type="text" name="username" placeholder="username"><br>
<input type="password" name="password" placeholder="password"><br>
<button type="submit">Login</button>
</form>
"""
    viewerObj.queueTurboAction(loginHTML, "loginForm", viewerObj.turboApp.methods.update)



def sendRegisterForm(viewerObj:BaseViewer):
    registerHTML = \
f"""
<form onsubmit="return submit_ws(this)">
{viewerObj.addCSRF("REGISTER")}
<input type="text" name="username" placeholder="UserName"><br>
<input type="text" name="person" placeholder="Name"><br>
<input type="password" name="password" placeholder="Password"><br>
<input type="password" name="confirm" placeholder="ConfirmPassword"><br>
<button type="submit">Register</button>
</form>
"""
    viewerObj.queueTurboAction(registerHTML, "registerForm", viewerObj.turboApp.methods.update)





##############################################################################################################################
##############################################################################################################################



appName =  CoreValues.appName.value
title = CoreValues.title.value
webBase = Routes.webHomePage.value
webWS = Routes.webWS.value
fernetKey = ServerSecrets.webFernetKey.value
extraHeads = """<style>
    /* Global Styles */
    #root {
      font-family: Arial, sans-serif;
      background: linear-gradient(to right, #e0eafc, #cfdef3);
      color: #333;
      margin: 0;
      padding: 20px;
      display: flex;
      justify-content: center;
    }
    #mainDiv {
      max-width: 800px;
      width: 100%;
      background-color: #ffffff;
      padding: 20px;
      border-radius: 8px;
      box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
      position: relative;
    }


     /* Logout Button */
     .logout-button {
      position: absolute;
      top: 20px;
      right: 20px;
      background-color: #f44336;
      color: #ffffff;
      padding: 8px 16px;
      border: none;
      border-radius: 4px;
      cursor: pointer;
      font-size: 14px;
      text-align: center;
    }

    .logout-button:hover {
      background-color: #d32f2f;
    }

    h1, h2 {
      text-align: center;
      color: #0076ff;
    }

    /* Form Styles */
    form {
      margin-bottom: 20px;
    }

    label {
      display: inline-block;
      margin: 8px 0 4px;
      color: #555;
    }

    input[type="text"], select {
      width: 100%;
      padding: 10px;
      margin: 8px 0;
      border: 1px solid #ddd;
      border-radius: 4px;
      box-sizing: border-box;
    }

    button, input[type="submit"] {
      background-color: #0076ff;
      color: #fff;
      padding: 10px 20px;
      border: none;
      border-radius: 4px;
      cursor: pointer;
      font-size: 14px;
    }

    button:hover, input[type="submit"]:hover {
      background-color: #005bb5;
    }

    /* Table Styles */
    table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 10px;
    }

    th, td {
      padding: 10px;
      border: 1px solid #ddd;
      text-align: left;
    }

    th {
      background-color: #0076ff;
      color: #ffffff;
    }

    /* Section Styles */
    #mainDiv > div, #mainDiv > p {
      margin-bottom: 20px;
      padding: 15px;
      border: 1px solid #eee;
      border-radius: 8px;
      background-color: #fafafa;
    }

    #mainDiv > div > form {
      display: flex;
      flex-direction: column;
      align-items: flex-start;
    }

    /* Additional Styling */
    #pendingBoardVerification, #idleChildren, #idleBoards {
      font-size: 14px;
      color: #777;
      padding: 10px;
      border: 1px solid #ddd;
      border-radius: 8px;
    }
  </style>"""
baseBody = """<body><div id="root"><div id="mainDiv">Generating OTP and validating other fields</div></div></body>"""


logger = LogManager()
SQLConn = connectDB(logger)
liveCacheManager = UserClass()
stringGen = STR_GEN()
baseApp, turboApp = createApps(webFormSubmit, webViewerJoined, webViewerLeft, appName, webBase, fernetKey, extraHeads, baseBody, title)


@baseApp.get(Routes.apiForceCheckParentConnection.value)
@getSenderBoard(parentRequired=True)
def apiForceCheckParentConnection(BoardID:str|None):
    print(BoardID, "Has Parent")
    return {"PURPOSE":"PARENT", "STATUS":True}


@baseApp.get(Routes.apiCheckParentAccepted.value)
@getSenderBoard(parentRequired=True)
def apiCheckParentAccepted(BoardID:str|None):
    print(BoardID, "Parent Accepted")
    return {"PURPOSE": "ACCEPT", "STATUS": True}


@baseApp.get(Routes.apiSubmitOTP.value)
@getSenderBoard(parentRequired=False)
def apiSubmitOTP(BoardID:str|None):
    return acceptBoardOTP(BoardID)


@baseApp.get(Routes.apiNewQuestion.value)
@getSenderBoard(parentRequired=True)
def apiNewQuestion(BoardID:str|None):
    return sendBoardNewQuestion(BoardID)


@baseApp.get(Routes.apiSubmitAnswer.value)
@getSenderBoard(parentRequired=True)
def apiSubmitAnswer(BoardID:str|None):
    return acceptBoardAnswer(BoardID)


print(f"http://127.0.0.1:{ServerSecrets.webPort.value}{Routes.webHomePage.value}")
WSGIServer(('0.0.0.0', ServerSecrets.webPort.value,), baseApp, log=None).serve_forever()
