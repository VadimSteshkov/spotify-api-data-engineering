import json
from requests import post, get
import base64
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import spotipy.util as util

CLIENT_ID = ""
CLIENT_SECRET = ""
USERNAME=""
redirect_uri="https://google.com"
scope="user-read-private user-read-email"

def tokenByClientCredentials():
    auth_string = CLIENT_ID + ":" + CLIENT_SECRET
    auth_bytes = auth_string.encode("utf-8")
    auth_base64 = str(base64.b64encode(auth_bytes), "utf-8")

    url = "https://accounts.spotify.com/api/token"
    headers = {
        "Authorization" : "Basic " + auth_base64,
        "Content-Type" : "application/x-www-form-urlencoded"
    } 
    data = {"grant_type" : "client_credentials"}
    result = post(url, headers=headers, data=data)
    json_result = json.loads(result.content)
    token = json_result["access_token"]
    return token

def tokenByAuthorizationCode():
    spoti = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=CLIENT_ID, client_secret=CLIENT_SECRET))
    token = util.prompt_for_user_token(USERNAME, scope, client_id=CLIENT_ID, client_secret=CLIENT_SECRET, redirect_uri=redirect_uri)
    return token

def searchArtist(token, artist_name):
    url = "https://api.spotify.com/v1/search"
    headers = {
        "Authorization" : "Bearer " + token
    }
    query = f"?q={artist_name}&type=artist&limit=1"
    query_url = url + query
    result = get(query_url, headers=headers)
    data = result.json()
    print(data)

def getMyProfile(token):
    url = "https://api.spotify.com/v1/me"
    headers = {
        "Authorization" : "Bearer " + token
    }
    result = get(url, headers=headers)
    data = result.json()
    print(data)




myToken = tokenByAuthorizationCode()
getMyProfile(myToken)
#searchArtist(myToken, "ACDC")