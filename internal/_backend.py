from gevent.monkey import patch_all
patch_all()


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



def getSenderBoard(parentRequired:bool):
    def decorator(continueFunction):
        @wraps(continueFunction)
        def wrapper():
            bearer = request.headers.get("Bearer", "")
            boardID = None if not bearer else readBoardBearer(bearer)
            if boardID:
                if parentRequired:
                    received = SQLConn.execute(f"SELECT ParentID from boards where BoardID=\"{boardID}\"")
                    if received and received[0]["ParentID"]: return continueFunction(boardID)
                    if not SQLConn.execute(f"SELECT BoardID from pending_connections where BoardID=\"{boardID}\""):
                        OTP = generateBoardOTP(boardID)
                        print({"PURPOSE": "CONN", "OTP": OTP})
                        return {"PURPOSE": "CONN", "OTP": OTP}
                    print( {"PURPOSE":"ACCEPT", "STATUS":False})
                    return {"PURPOSE":"ACCEPT", "STATUS":False}
                else: return continueFunction(boardID)
            else:
                bearer = createNewBoard()
                print({"PURPOSE": "AUTH", "BEARER": bearer})
                return {"PURPOSE": "AUTH", "BEARER": bearer}
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

    def getParentUserName(self, By, value: str):
        if not value: return
        if By == self.ByParentID:
            received = SQLConn.execute(f"SELECT UserName from parent_auth where ParentID=\"{value}\" limit 1")
            if received:
                received = received[0]
                return received.get("UserName")
        elif By == self.ByViewerID:
            received = SQLConn.execute(f"SELECT ParentID from parent_sessions where ViewerID=\"{value}\" limit 1")
            if received:
                received = received[0]
                return self.getParentUserName(self.ByParentID, received.get("ParentID").decode())

    def getParentID(self, By, value):
        if not value: return
        if By == self.ByUserName:
            received = SQLConn.execute(f"SELECT ParentID from parent_auth where UserName=\"{value}\" limit 1")
            if received:
                received = received[0]
                return received.get("ParentID").decode()
        elif By == self.ByViewerID:
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
            parentID = STR_GEN().AlphaNumeric(50, 50)
            if not SQLConn.execute(f"SELECT UserName from parent_auth where parentID=\"{parentID}\" limit 1"):
                SQLConn.execute(f"INSERT INTO parents values (\"{parentID}\", \"{person}\", now(), \"\")")
                SQLConn.execute(f"INSERT INTO parent_auth values (\"{parentID}\", \"{username}\", \"{generate_password_hash(password)}\")")
                liveCacheManager.parentLoginCall(viewerObj, parentID)
                renderHomePage(viewerObj)
                break

def loginOldParent(viewerObj:BaseViewer, form:dict):
    username = form.get("username", "")
    password = form.get("password", "")
    received = SQLConn.execute(f"SELECT ParentID, PWHash from parent_auth where UserName=\"{username}\" limit 1")
    if not received:
        viewerObj.queueTurboAction("Username Dont Match", "authWarning", viewerObj.turboApp.methods.update.value)
        sendLoginForm(viewerObj)
    else:
        received = received[0]
        if not check_password_hash(received["PWHash"].decode(), password):
            viewerObj.queueTurboAction("Password Dont Match", "authWarning", viewerObj.turboApp.methods.update.value)
            sendLoginForm(viewerObj)
        else:
            liveCacheManager.parentLoginCall(viewerObj, received["ParentID"].decode())
            renderHomePage(viewerObj)


def createNewChild(viewerObj: BaseViewer, form:dict):
    parentID = getKnownLoggedInParentID(viewerObj)
    childName = form.get("name", "")
    while True:
        childID = STR_GEN().AlphaNumeric(50, 50)
        if not SQLConn.execute(f"SELECT ChildID from children where ChildID=\"{childID}\" limit 1"):
            SQLConn.execute(f"INSERT INTO children values (\"{childID}\", \"{parentID}\", \"\", \"{childName}\", 0, now())")
            sendIdleChildren(viewerObj)
            return childID


def deleteOldChild(viewerObj: BaseViewer, childID:str):
    parentID = getKnownLoggedInParentID(viewerObj)
    received = SQLConn.execute(f"SELECT BoardID from children where ChildID=\"{childID}\"")
    if received:
        received = received[0]
        if received["BoardID"]: return print("Child not idle")
    SQLConn.execute(f"DELETE from children where ChildID=\"{childID}\" and ParentID=\"{parentID}\"")
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
    sendIdleChildren(viewerObj)


def deleteAssignment(viewerObj:BaseViewer, boardID:str, childID:str):
    parentID = getKnownLoggedInParentID(viewerObj)
    SQLConn.execute(f"UPDATE boards set ChildID=\"\" where BoardID=\"{boardID}\" and parentID=\"{parentID}\"")
    SQLConn.execute(f"UPDATE children set BoardID=\"\" where ChildID=\"{childID}\" and parentID=\"{parentID}\"")



def webViewerJoined(viewerObj: BaseViewer):
    print(f"Viewer Joined: {viewerObj.viewerID}")
    parentID = getKnownLoggedInParentID(viewerObj)
    if parentID:
        liveCacheManager.parentLoginCall(viewerObj, parentID)
        renderHomePage(viewerObj)
    else:
        renderAuthPage(viewerObj)


def webFormSubmit(viewerObj: BaseViewer, form: dict):
    print(f"{viewerObj.viewerID}: {form}")
    if "PURPOSE" not in form: return
    purpose = form.pop("PURPOSE")
    if purpose == "LOGIN":
        loginOldParent(viewerObj, form)
    elif purpose == "REGISTER":
        registerNewParent(viewerObj, form)
    elif purpose == "NEW_BOARD":
        sendNewBoardForm(viewerObj)
        if initiateOwnershipParent(viewerObj, form) != -1:
            sendPendingBoardVerifications(viewerObj)
            sendAssignmentForm(viewerObj)
    elif purpose == "NEW_CHILD":
        sendNewChildForm(viewerObj)
        createNewChild(viewerObj, form)
        sendIdleChildren(viewerObj)
        sendAssignmentForm(viewerObj)
    elif "REMOVE_BOARD" in purpose:
        deleteOwnedBoard(viewerObj, purpose.replace("REMOVE_BOARD_", ""))
        sendIdleBoards(viewerObj)
        sendAssignmentForm(viewerObj)
    elif "REMOVE_CHILD" in purpose:
        deleteOldChild(viewerObj, purpose.replace("REMOVE_CHILD_", ""))
        sendIdleChildren(viewerObj)
        sendAssignmentForm(viewerObj)
    elif purpose == "NEW_ASSIGNMENT":
        initiateAssignment(viewerObj, form)
        sendAssignmentForm(viewerObj)
        sendAssigned(viewerObj)
        sendIdleBoards(viewerObj)
        sendIdleChildren(viewerObj)
    elif "REMOVE_ASSIGNMENT" in purpose:
        deleteAssignment(viewerObj, purpose.replace("REMOVE_ASSIGNMENT_", "").split("_")[0], purpose.replace("REMOVE_ASSIGNMENT_", "").split("_")[1])
        sendAssigned(viewerObj)
        sendIdleBoards(viewerObj)
        sendIdleChildren(viewerObj)


def webViewerLeft(viewerObj: BaseViewer):
    print(f"Viewer Left: {viewerObj.viewerID}")
    liveCacheManager.parentLogoutCall(viewerObj)


def sendAssigned(viewerObj:BaseViewer):
    viewerObj.queueTurboAction("<div id='childBoard_create'></div>", "childBoardAssignments", viewerObj.turboApp.methods.update, forceFlush=True)
    parentID = liveCacheManager.getParentID(liveCacheManager.ByViewerID, viewerObj.viewerID)
    for board in SQLConn.execute(f"SELECT ChildID, BoardID, Name from boards where parentID=\"{parentID}\""):
        childID = board['ChildID'].decode()
        boardID = board['BoardID'].decode()
        childName = ""
        childPoints = ""
        if childID:
            child = SQLConn.execute(f"SELECT Name, Points from children where ChildID=\"{childID}\" and ParentID=\"{parentID}\"")
            if child:
                child = child[0]
                childName = child['Name']
                childPoints = child['Points']
        if childID:
            assignedHTML = f"""
            <form onsubmit="return submit_ws(this)">
            {viewerObj.addCSRF(f"REMOVE_ASSIGNMENT_{boardID}_{childID}")}
            {board['Name']}: {childName}:{childPoints}
            <input type="submit" Value="Separate">
            </form>
            """
            viewerObj.queueTurboAction(assignedHTML, "childBoard", viewerObj.turboApp.methods.newDiv)


def sendAssignmentForm(viewerObj:BaseViewer):
    parentID = liveCacheManager.getParentID(liveCacheManager.ByViewerID, viewerObj.viewerID)
    idleBoards = []
    for board in SQLConn.execute(f'SELECT BoardID, Name from boards where ParentID=\"{parentID}\" and ChildID=\"\"'):
        idleBoards.append([board["BoardID"].decode(), board["Name"]])
    idleChildren = []
    for child in SQLConn.execute(f'SELECT ChildID, Name from children where ParentID=\"{parentID}\" and BoardID=\"\"'):
        idleChildren.append([child["ChildID"].decode(), child["Name"]])
    newAssignmentHTML = f"""<form onsubmit="return submit_ws(this)">
    {viewerObj.addCSRF("NEW_ASSIGNMENT")}
<label for="board">Choose a board:</label>
<select name="board">
"""
    for board in idleBoards:
        newAssignmentHTML+= f"<option value=\"{board[0]}\">{board[1]}</option>"
    newAssignmentHTML += "</select>"

    newAssignmentHTML += f"""
    <label for="board">Choose a child:</label>
    <select name="child">
    """
    for child in idleChildren:
        newAssignmentHTML += f"<option value=\"{child[0]}\">{child[1]}</option>"
    newAssignmentHTML += "</select> <input type='submit' Value='Assign'> </form>"
    viewerObj.queueTurboAction(newAssignmentHTML, "newChildBoardAssignments", viewerObj.turboApp.methods.update)


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


def renderHomePage(viewerObj:BaseViewer):
    parentID = liveCacheManager.getParentID(liveCacheManager.ByViewerID, viewerObj.viewerID)
    parentOTP = generateParentOTP(parentID)
    received = SQLConn.execute(f"SELECT ParentName from parents where ParentID=\"{parentID}\"")
    if received: parentName = received[0]["ParentName"]
    else:
        parentName = "Nameless Parent"

    homepageHTML = \
f"""
Welcome {parentName}<br>
Your OTP is: {parentOTP}<br>
<br><br>Assigned Boards:
<div id="childBoardAssignments"></div>
<br><br>Assign board to a child:
<div id="newChildBoardAssignments"></div>
<br>Add new Child:
<div id="newChild"></div>
<br>Add new Board:
<div id="newBoard"></div>
<br>Pending Boards Verification:
<div id="pendingBoardVerification"></div>
<br>Children Idle:
<div id="idleChildren"></div>
<br>Boards Idle:
<div id="idleBoards"></div>
"""
    viewerObj.queueTurboAction(homepageHTML, "mainDiv", viewerObj.turboApp.methods.update)
    sendAssigned(viewerObj)
    sendAssignmentForm(viewerObj)
    sendNewBoardForm(viewerObj)
    sendNewChildForm(viewerObj)
    sendPendingBoardVerifications(viewerObj)
    sendIdleChildren(viewerObj)
    sendIdleBoards(viewerObj)


def renderAuthPage(viewerObj:BaseViewer):
    authPage = \
f"""
<div id="loginForm"></div>
<div id="registerForm"></div>
<div id="authWarning"></div>
"""
    viewerObj.queueTurboAction(authPage, "mainDiv", viewerObj.turboApp.methods.update)
    sendRegisterForm(viewerObj)
    sendLoginForm(viewerObj)


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



logger = LogManager()
SQLConn = connectDB(logger)
liveCacheManager = UserClass()
stringGen = STR_GEN()




appName =  CoreValues.appName.value
title = CoreValues.title.value
webBase = Routes.webHomePage.value
webWS = Routes.webWS.value
fernetKey = ServerSecrets.webFernetKey.value
extraHeads = ""
baseBody = """
<body> 
<div id="mainDiv">Generating OTP and validating other fields<div>
</body>"""


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
    OTP = request.args.get("OTP", "")
    status = initiateOwnershipBoard(BoardID, OTP)
    if status == -1:
        return {"PURPOSE":"OTP", "STATUS":"INVALID OTP"}
    elif status == 0:
        return {"PURPOSE":"OTP", "STATUS":"WAITING FOR PARENT"}
    elif status == 1:
        return {"PURPOSE":"OTP", "STATUS":"CONNECTED TO PARENT"}



@baseApp.get(Routes.apiNewQuestion.value)
@getSenderBoard(parentRequired=True)
def apiNewQuestion(BoardID:str|None):
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
        correctOption = optionsToProvide.index(answerText)+1
        received = SQLConn.execute(f"SELECT ChildID from boards where BoardID=\"{BoardID}\"")
        if received:
            received = received[0]
            childID = received["ChildID"].decode()
        else: childID = ""
        sentAt = str(time())
        SQLConn.execute(f"INSERT INTO questionhistory values (\"{BoardID}\", \"{childID}\", \"{questionID}\", \"{sentAt}\", '{dumps(optionsToProvide)}', {correctOption}, 0)")
        response = {"PURPOSE":"QUESTION", "T": sentAt, "Q":questionText, "O":optionsToProvide}
        print(response)
        return response


@baseApp.get(Routes.apiSubmitAnswer.value)
@getSenderBoard(parentRequired=True)
def apiSubmitAnswer(BoardID:str|None):
    sentAt = request.args.get("T")
    option =  int(request.args.get("OPTION")) if request.args.get("OPTION", "").isdigit() else None
    received = SQLConn.execute(f"SELECT Options, CorrectOption, OptionSelected from questionhistory where SentAt=\"{sentAt}\" and BoardID=\"{BoardID}\"")
    if received:
        received = received[0]
        options = loads(received["Options"])
        correctOption = received["CorrectOption"]
        optionsSelected = received["OptionSelected"]
        if optionsSelected == 0:
            SQLConn.execute(f"UPDATE questionhistory SET OptionSelected={option} WHERE BoardID=\"{BoardID}\" and SentAt=\"{sentAt}\"")
        isCorrect = option == correctOption
        received = SQLConn.execute(f"SELECT ChildID, Points from children where BoardID=\"{BoardID}\"")
        points = 0
        dropCandy = False
        if received:
            received = received[0]
            childID = received["ChildID"].decode()
            points = received["Points"]
            if isCorrect:
                points += 10
                if points >= 30:
                    points = 0
                    dropCandy = True
                SQLConn.execute(f"UPDATE children set Points={points} where ChildID=\"{childID}\"")
        response = {"PURPOSE":"SCORE", "V": True, "C":isCorrect, "O":options[correctOption-1], "S":str(points), "D":dropCandy}
        print(response)
        return response
    else: return {"PURPOSE":"SCORE", "V": False}


print(f"http://127.0.0.1:{ServerSecrets.webPort.value}{Routes.webHomePage.value}")
WSGIServer(('0.0.0.0', ServerSecrets.webPort.value,), baseApp, log=None).serve_forever()