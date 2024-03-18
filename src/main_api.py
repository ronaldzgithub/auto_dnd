# resumir chunks da transcrição

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import os
from src.GPTController import GPTController
from dotenv import load_dotenv
from src.session_manager import SessionManager, UserManager
load_dotenv()
import sys
import asyncio
import firebase_admin
from firebase_admin import credentials, auth

firebase_app = firebase_admin.initialize_app(credentials.Certificate("firebase_credentials.json"))

def auth_user_token(user_token):
    try:
        decoded_token = auth.verify_id_token(user_token)
        if decoded_token is None:
            print('Auth failed, could not decode token:', user_token)
        return decoded_token
    except Exception as e:
        print('exception on auth_user_token', e)
        return None

# prevents asyncio errors on Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

class UserInput(BaseModel):
    user_token: str
    campaign_id: str
    content: str

class CharacterData(BaseModel):
    name: str
    background: str
    strength: str
    dexterity: str
    constitution: str
    intelligence: str
    wisdom: str
    charisma: str

class NewCampaignInput(BaseModel):
    user_token: str
    character_data: CharacterData

class FetchCampaignsInput(BaseModel):
    user_token: str

class LoadCampaignInput(BaseModel):
    user_token: str
    campaign_id: str

app = FastAPI()

# todo: implement CORS properly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

gpt_controller = GPTController(os.getenv('OPENAI_API_KEY'))
session_manager = SessionManager()
# user_manager = UserManager()

@app.post("/fetch_campaigns/")
async def fetch_campaigns(input: FetchCampaignsInput):
    # auth
    decoded_token = auth_user_token(input.user_token)
    if decoded_token is None:
        return
    try:
        # get user data
        print('fetching campaigns for:', decoded_token['uid'])
        # user_data = user_manager.get_or_create_user_data(decoded_token['uid'])
        user_session_ids = session_manager.filter_sessions_by_owner(decoded_token['uid'])
        session_names = session_manager.get_session_names(user_session_ids)
        session_player_names = session_manager.get_session_player_names(user_session_ids)
        session_player_levels = session_manager.get_session_player_levels(user_session_ids)
        user_sessions_info = []
        for i in range(len(user_session_ids)):
            user_sessions_info.append({
                "campaign_id": user_session_ids[i],
                "campaign_name": session_names[i],
                "player_name": session_player_names[i],
                "player_Level": session_player_levels[i]
            })
        return {"user_campaigns":  user_sessions_info}
    except Exception as e:
        print('exception fetching user campaigns', e)
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/create_campaign/")
async def create_campaign(input: NewCampaignInput):
    # auth
    decoded_token = auth_user_token(input.user_token)
    if decoded_token is None: 
        return
    print('creating new campaign for', decoded_token['uid'])
    print('character data:', input.character_data)
    try:
        campaign_id = session_manager.create_session(decoded_token['uid'])
        session = session_manager.get_session(campaign_id)
        session.set_char_sheet(input.character_data.name, input.character_data.background, 
                             input.character_data.strength, input.character_data.dexterity, input.character_data.constitution, 
                             input.character_data.intelligence, input.character_data.wisdom, input.character_data.charisma)
        return {'campaign_id': campaign_id}
    except Exception as e:
        print('exception create character', e)
        # print('input was', input)
        # print('session was', session)
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/load_campaign/")
async def load_campaign(input: LoadCampaignInput):
    # auth
    decoded_token = auth_user_token(input.user_token)
    if decoded_token is None: 
        return
    try:
        session = session_manager.get_session(input.campaign_id)
        if session is None:
            print('load_campaign failed: campaign', input.campaign_id, 'does not exist')
            return
        if session.owner != decoded_token['uid']:
            print('load_campaign failed: user', decoded_token['uid'], 'does not have access to campaign', input.campaign_id)
            return
        print('sending session data for', decoded_token['uid'])
        return {
            "messages": session.messages[1:], # ignore system msg
            "char_sheet": session.player_char_sheet.get_prompt(),
            "campaign_notes": session.campaign_notes.get_prompt(),
            "is_user_turn": session.user_turn,
        }
    except Exception as e:
        print('exception loading campaign', e)
        raise HTTPException(status_code=500, detail="Internal server error")
        
@app.post("/process_input/")
async def process_input(input: UserInput):
    # auth
    decoded_token = auth_user_token(input.user_token)
    if decoded_token is None:
        return
    try:
        session = session_manager.get_session(input.campaign_id)
        if session is None:
            print('load_campaign failed: campaign', input.campaign_id, 'does not exist')
            return
        if session.owner != decoded_token['uid']:
            print('load_campaign failed: user', decoded_token['uid'], 'does not have access to campaign', input.campaign_id)
            return
        await session.tick_session(input.content, gpt_controller)
        return {
            "messages": session.messages[1:], # ignore system msg
            "char_sheet": session.player_char_sheet.get_prompt(),
            "campaign_notes": session.campaign_notes.get_prompt(),
            "is_user_turn": session.user_turn,
        }
    except Exception as e:
        print('exception process_input', e)
        print('input was', input)
        print('session was', session)
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/")
async def root():
    return {"message": "Hello to Auto D&D!"}
