import sys
from src.capsolver import solveCaptcha
from src.gui import StandardSession, load_config

cfg = load_config()
landline = cfg.get("LANDLINE") or "02xxx"
password = cfg.get("MY_WE_PASSWORD") or "xxx"
apiKey   = cfg.get("GOOGLE_API_KEY") or ""

if landline == "02xxx" or password == "xxx":
    print("[INFO] Please configure your landline and password in config.json or via the GUI settings.")

acctId = "FBB" + landline[1:] if len(landline) > 1 else ""
session = StandardSession()

captchaPayload = {
    "merchantName": "E-Care",
    "serviceName": "Login",
    "identifier": landline,
}

response = session.post("https://captcha.te.eg/api/Captcha/GenerateCaptcha", json_data=captchaPayload)
captcha = response.json()

if captcha.get("status") != "Success":
    print("Captcha request failed:", captcha)
    sys.exit(1)

captchaToken = captcha["token"]

if captcha.get("requireInteraction") is False:
    print("Captcha passed: no interaction needed")
    answer = ""
else:
    print("Trying to solve captcha...")
    answer = solveCaptcha(captcha["captcha"], apiKey)["letters"]
    print(f"Captcha Solved: {answer}")

loginPayload = {
    "acctId": acctId,
    "password": password,
    "imgCacheKey": captchaToken,
    "appLocale": "en-US",
    "isSelfcare": "Y",
    "isMobile": "N",
    "imgCode": answer,
    "isConvergent": "0",
}

session.headers.update({
    "channelid": "702",
    "csrftoken": "",
    "languagecode": "en-US",
    "isselfcare": "true",
    "delegatorsubsid": "",
    "iscoporate": "false",
    "ismobile": "false",
    "systemtype": "",
})

response = session.post(
    "https://my.te.eg/echannel/service/besapp/base/rest/busiservice/v1/auth/userAuthenticate",
    json_data=loginPayload,
)
login = response.json()
print("Login response:", login)

try:
    csrf = login["body"]["token"]
except (KeyError, TypeError):
    print("[ERROR] Login failed: check credentials.")
    sys.exit(1)

session.headers.update({"csrftoken": csrf})
subscriberId = login["body"]["subscriber"]["subscriberId"]

offersPayload = {
    "msisdn": acctId,
    "numberServiceType": "FBB",
    "groupId": "",
}

response = session.post(
    "https://my.te.eg/echannel/service/besapp/base/rest/busiservice/cz/v1/auth/getSubscribedOfferings",
    json_data=offersPayload,
)
mainOfferId = response.json()["body"]["offeringList"][0]["mainOfferingId"]

quotaPayload = {
    "subscriberId": subscriberId,
    "needQueryPoint": "true",
    "mainOfferId": mainOfferId,
}

response = session.post(
    "https://my.te.eg/echannel/service/besapp/base/rest/busiservice/cz/cbs/bb/queryFreeUnit",
    json_data=quotaPayload,
)
quota = response.json()

if "body" in quota and quota["body"]:
    used = sum(float(item.get("used", 0)) for item in quota["body"])
    remain = sum(float(item.get("actualRemain", 0)) for item in quota["body"])
    total = sum(float(item.get("total", 0)) for item in quota["body"])
    print(f"Used: {used:.2f} GB")
    print(f"Remaining: {remain:.2f} GB from {total:.0f} GB")
else:
    print("Could not retrieve quota details:", quota)