import requests 
from capsolver import solveCaptcha


landline = "02xxx" #Landline (include governorate code 02 for cairo then the number)
password = "xxx"
apiKey = "" #Google ai stuido key for captcha (might add support for manual solve soon)


acctId = "FBB" + landline[1:]
session = requests.Session()

session.headers.update({
    "Connection": "keep-alive",
    "sec-ch-ua-platform": "\"Windows\"",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "sec-ch-ua": "\"Not=A?Brand\";v=\"99\", \"Brave\";v=\"151\", \"Chromium\";v=\"151\"",
    "Content-Type": "application/json; charset=UTF-8",
    "sec-ch-ua-mobile": "?0",
    "Sec-GPC": "1",
    "Origin": "https://my.te.eg",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://my.te.eg/",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "en-US,en;q=0.9"
})

captchaPayload = {
    "merchantName": "E-Care",
    "serviceName": "Login",
    "identifier": landline,
}


response = session.post("https://captcha.te.eg/api/Captcha/GenerateCaptcha", json=captchaPayload)
captcha = response.json()


if captcha["status"] != "Success" :
    print("Captcha request failed")
    exit()

captchaToken = captcha["token"]

if captcha["requireInteraction"] == False :
    print("captcha passed no interaction need")
    answer=""

else :
    print("Trying to solve captcha")
    answer = solveCaptcha(captcha["captcha"] , apiKey)["letters"] # Add recover for error and logs
    print(f"Captcha Solved : {answer}")
    


loginPayload = {
    "acctId": acctId,
    "password": password,
    "imgCacheKey" : captchaToken,
    "appLocale":"en-US", "isSelfcare":"Y", "isMobile":"N",
    "imgCode":answer,"isConvergent":"0"
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
    json=loginPayload 
)
login = response.json()
print(login)
csrf = login["body"]["token"] # header

session.headers.update({
    "csrftoken": csrf  
})

subscriberId = login["body"]["subscriber"]["subscriberId"]

offersPayload = {
    "msisdn": acctId,
    "numberServiceType" :"FBB",
    "groupId": "",

}

response = session.post("https://my.te.eg/echannel/service/besapp/base/rest/busiservice/cz/v1/auth/getSubscribedOfferings" , json = offersPayload )

mainOfferId =response.json()["body"]["offeringList"][0]["mainOfferingId"]



quotaPayload = {
    "subscriberId": subscriberId,
    "needQueryPoint" :"true",
    "mainOfferId": mainOfferId,

}

response = session.post("https://my.te.eg/echannel/service/besapp/base/rest/busiservice/cz/cbs/bb/queryFreeUnit" , json = quotaPayload)

quota = response.json()

print(f"Used : {quota['body'][0]['used']} Gb")
print(f"Remaining : {quota['body'][0]['actualRemain']} Gb from {quota['body'][0]['total']} Gb")