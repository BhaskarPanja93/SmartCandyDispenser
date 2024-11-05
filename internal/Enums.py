from pathlib import Path

try: from internal.SecretEnums import * ## change
except: from SecretEnums import * ## change


for location in HostDetails.possibleFolderLocation.value:
    if Path(location).is_dir():
        folderLocation = location
        break
else:
    input("Project directory not found in SecretEnum...")


class RequiredFiles(Enum):
    webServerRunnable = str(Path(folderLocation, r"internal\_backend.py"))
    webServerRequired = [
        str(Path(folderLocation, r"internal\_backend.py")),
        str(Path(folderLocation, r"run_servers.py"))
    ]


class Subjects(Enum):
    maths = "Maths"


class FormPurposes(Enum):
    register = "registerParent"
    login = "loginParent"


class Routes(Enum):
    webHomePage = "/"
    webChildStats = f"{webHomePage}-child-stats"
    apiForceCheckParentConnection = f"{webHomePage}forceParent"
    apiCheckParentAccepted = f"{webHomePage}parentAccepted"
    apiNewQuestion = f"{webHomePage}newQuestion"
    apiSubmitAnswer = f"{webHomePage}submitAnswer"
    apiSubmitOTP = f"{webHomePage}submitOTP"
    dummyRoute = f"{webHomePage}dummy"


class CoreValues(Enum):
    appName = "CandyDispenser"
    title = "CandyDispenser"


class CDNFileType(Enum):
    font = "font"
    image = "image"
    video = "video"
    css = "css"
    html = "html"
    js = "js"


class Fonts(Enum):
    pass
